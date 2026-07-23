"""
===============================================================================
COG: AI Chat Module v5.0 — Synapse Discord Bot
===============================================================================
File    : backend/cogs/ai_chat/ai_chat.py
Deskripsi : 5-Tier API Fallback Engine — modular provider system
  • Tier 1: Gemini — Primary (text + vision), circuit breaker, quota reserve
  • Tier 2: Groq — Backup (Llama 3.3 70B)
  • Tier 3: Mistral — Third (open-mistral-nemo)
  • Tier 4: Cohere — Fourth (command-a-03-2025)
  • Tier 5: OpenRouter — Last resort (auto-prioritize free models)
  • Slash command /ask + Mention handler (@bot)
  • Channel restriction, personality, temperature via dashboard
  • Chat history Firestore (max 5 pasang Q&A per user)
  • v5.0: Provider system dipisah ke backend/cogs/ai_chat/providers/
===============================================================================
"""
import re
import os
import base64
import hashlib
import traceback
import time as time_module
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

import discord
from discord.ext import commands, tasks

import aiohttp

from ..database.firebase_setup import db
from ...utils.spam_engine import SpamEngine
from ...utils.intent_router import detect_intent
from ...utils.firestore_stats import (
    firestore_circuit_open,
    trip_firestore_circuit,
    firestore_retry_after,
    _is_quota_error,
)
from .prompt import SYSTEM_PROMPT_TEMPLATE, get_intent_instructions, SPAM_ANALYSIS_SYSTEM_PROMPT, get_few_shot_examples, CHAIN_OF_THOUGHT_INSTRUCTION
from .chat_enhancer import (
    run_tools,
    get_user_prefs,
    enhance_server_context,
    update_user_style_prefs,
)
from .web_search import search_web, needs_web_search
from .providers import (
    GeminiProvider,
    GroqProvider,
    MistralProvider,
    CohereProvider,
    OpenRouterProvider,
)

# ── Konstanta ──
MAX_HISTORY_PAIRS = 5
COOLDOWN_SECONDS = 5
DEFAULT_PERSONALITY = "friendly"

# ── Rate limit per-user (defaults, overridable per-guild) ──
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 30
RATE_LIMIT_COOLDOWN = 60

# ── Cache ──
RESPONSE_CACHE_TTL = 300

# ── In-memory cache untuk Firestore reads ──
_HISTORY_CACHE: Dict[str, tuple] = {}
_HISTORY_TTL = 60
_USER_RATE_LIMITS: Dict[int, list] = {}
_GUILD_DAILY_LIMITS: Dict[str, dict] = {}
_GUILD_RAG_CACHE: Dict[str, tuple] = {}  # guild_id -> (chunks, load_timestamp)
_SETTINGS_CACHE: Dict[str, tuple] = {}  # guild_id -> (settings, timestamp)
_SETTINGS_CACHE_TTL = 60
_PREFS_CACHE: Dict[str, tuple] = {}  # guild_id_user_id -> (prefs, timestamp)
_PREFS_CACHE_TTL = 60
RAG_CACHE_MAX_CHUNKS = 5000
RAG_CACHE_TTL = 300  # 5 menit

# ── Guild daily limit (per-server) ──
GUILD_DAILY_MAX = 100

# ── Gemini quota constants (used in orchestrator for log messages) ──
DAILY_QUOTA_LIMIT = 1500
CIRCUIT_BREAKER_COOLDOWN = 7200


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.engine = SpamEngine()
        self._cooldowns: Dict[tuple, float] = {}

        # API Keys (passed to providers on cog_load)
        self.google_api_key = os.getenv("GEMINI_API_KEY", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY", "")
        self.cohere_api_key = os.getenv("COHERE_API_KEY", "")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")

        self.session: aiohttp.ClientSession | None = None

        # Providers (initialized in cog_load)
        self.gemini: GeminiProvider | None = None
        self.groq: GroqProvider | None = None
        self.mistral: MistralProvider | None = None
        self.cohere: CohereProvider | None = None
        self.openrouter: OpenRouterProvider | None = None

        self._providers: list = []

        # Spam analysis cache
        self._spam_cache: dict[str, tuple[float, bool]] = {}
        self._spam_cache_ttl = 300
        self._spam_last_check: float = 0.0
        self._spam_min_interval = 1.0

        # Response cache (shared across providers)
        self._response_cache: dict[str, tuple[str, float]] = {}

        self._mention_pattern: re.Pattern | None = None
        self._last_history_prune: float = 0.0
        self._owner_id: int | None = None
        self._creator_name: str = "Developer"

        if not self.google_api_key:
            print("[AI CHAT] GEMINI_API_KEY tidak ditemukan!")
        if not self.groq_api_key:
            print("[AI CHAT] GROQ_API_KEY tidak ditemukan!")
        if not self.mistral_api_key:
            print("[AI CHAT] MISTRAL_API_KEY tidak ditemukan!")
        if not self.cohere_api_key:
            print("[AI CHAT] COHERE_API_KEY tidak ditemukan!")
        if not self.openrouter_api_key:
            print("[AI CHAT] OPENROUTER_API_KEY tidak ditemukan!")

    async def cog_load(self):
        if self.session and not self.session.closed:
            return

        timeout = aiohttp.ClientTimeout(total=60, connect=20)
        self.session = aiohttp.ClientSession(timeout=timeout)

        self.gemini = GeminiProvider(self.session, self.google_api_key)
        self.groq = GroqProvider(self.session, self.groq_api_key)
        self.mistral = MistralProvider(self.session, self.mistral_api_key)
        self.cohere = CohereProvider(self.session, self.cohere_api_key)
        self.openrouter = OpenRouterProvider(self.session, self.openrouter_api_key)

        await self.openrouter.initialize()

        self._providers = [
            self.gemini,
            self.groq,
            self.mistral,
            self.cohere,
            self.openrouter,
        ]

        self.history_prune_loop.start()

        # Fetch creator info from Discord app
        try:
            app = await self.bot.application_info()
            self._creator_name = app.owner.name if app.owner else "Developer"
            self._owner_id = app.owner.id if app.owner else None
            print(f"[AI CHAT] Creator: {self._creator_name} (ID tersimpan)")
        except Exception as e:
            print(f"[AI CHAT] Gagal fetch app info: {e}")

        # Preload RAG cache for all guilds
        guild_ids = [str(g.id) for g in self.bot.guilds if g]
        if guild_ids:
            await asyncio.gather(*[self._get_rag_chunks(gid) for gid in guild_ids], return_exceptions=True)
            loaded = sum(1 for gid in guild_ids if _GUILD_RAG_CACHE.get(gid))
            print(f"[RAG] Preloaded cache for {loaded}/{len(guild_ids)} guilds")

        print("[AI CHAT] Cog loaded. 5-Tier: Gemini -> Groq -> Mistral -> Cohere -> OpenRouter")

    async def cog_unload(self):
        self.history_prune_loop.cancel()
        if self.session:
            await self.session.close()
            print("[AI CHAT] HTTP session closed")

    # ── Response cache ──

    def _get_cached_response(self, user_message: str, system_prompt: str, temperature: float) -> str | None:
        cache_key = hashlib.md5(f"{user_message}|{system_prompt}|{temperature}".encode()).hexdigest()[:32]
        cached = self._response_cache.get(cache_key)
        if cached:
            text, ts = cached
            if time_module.time() - ts < RESPONSE_CACHE_TTL:
                return text
            del self._response_cache[cache_key]
        return None

    def _set_cached_response(self, user_message: str, system_prompt: str, temperature: float, response: str):
        cache_key = hashlib.md5(f"{user_message}|{system_prompt}|{temperature}".encode()).hexdigest()[:32]
        self._response_cache[cache_key] = (response, time_module.time())
        if len(self._response_cache) > 200:
            cutoff = time_module.time() - RESPONSE_CACHE_TTL
            self._response_cache = {k: v for k, v in self._response_cache.items() if v[1] > cutoff}

    # ── Spam analysis ──

    async def analyze_spam(self, content: str, risk_score: int = 0, account_age_days: int = 0, matched_keywords: list[str] | None = None) -> bool:
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        now = time_module.time()

        if content_hash in self._spam_cache:
            cached_time, cached_result = self._spam_cache[content_hash]
            if now - cached_time < self._spam_cache_ttl:
                return cached_result

        since_last = now - self._spam_last_check
        if since_last < self._spam_min_interval:
            return False
        self._spam_last_check = now

        try:
            keywords_str = ", ".join(matched_keywords) if matched_keywords else "tidak ada"
            prompt = (
                f"Pesan: \"\"\"{content}\"\"\"\n"
                f"Konteks: skor_risiko={risk_score}, usia_akun={account_age_days}hari, keyword_terdeteksi=[{keywords_str}]\n"
                f"Analisis apakah ini spam/scam/iklan judi. Jawab HANYA 'YA' atau 'TIDAK'."
            )

            response = await self._call_ai(
                user_message=prompt,
                history=[],
                system_prompt=SPAM_ANALYSIS_SYSTEM_PROMPT,
                temperature=0.1,
            )

            result = "YA" in response.upper()
        except Exception as e:
            print(f"[AI MOD] Error saat cek spam: {e}")
            result = False

        self._spam_cache[content_hash] = (time_module.time(), result)
        if len(self._spam_cache) > 500:
            cutoff = time_module.time() - self._spam_cache_ttl
            self._spam_cache = {k: v for k, v in self._spam_cache.items() if v[0] > cutoff}

        return result

    async def analyze_image_spam(self, image_data: bytes, mime_type: str = "image/png") -> bool:
        if self.gemini and self.gemini.quota_available:
            result = await self.gemini.analyze_image_spam(image_data, mime_type)
            if result:
                return True
        if self.openrouter and self.openrouter.is_available:
            is_safe, reason = await self.openrouter.check_content_safety(
                "Analisis gambar ini. Apakah mengandung: promosi judi/slot, scam, konten penipuan, atau phishing?",
                image_data, mime_type,
            )
            if not is_safe:
                return True
        return False

    # ── Helpers ──

    def _cleanup_cooldowns(self):
        now = datetime.now(timezone.utc).timestamp()
        self._cooldowns = {k: v for k, v in self._cooldowns.items() if now - v < 60}

    async def _defer_interaction(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(thinking=True)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                    print(f"[AI CHAT] Kena Rate Limit saat defer! Bot sedang sibuk.")
            else:
                print(f"[AI CHAT] Error lain saat defer: {e}")

    # ── Firestore Settings ──

    async def _get_guild_ai_settings(self, guild_id: str) -> dict:
        now = time_module.time()
        cached = _SETTINGS_CACHE.get(guild_id)
        if cached and now - cached[1] < _SETTINGS_CACHE_TTL:
            return cached[0]
        try:
            doc_ref = db.collection("guild_settings").document(str(guild_id))
            doc = await asyncio.to_thread(doc_ref.get)
            if not doc.exists:
                return {"enabled": False, "channel_id": ""}
            data = doc.to_dict()
            ai_chat = data.get("ai_chat", {})
            result = {
                "enabled": data.get("ai_chat_enabled", False),
                "channel_id": ai_chat.get("channel_id", ""),
                "personality": ai_chat.get("personality", DEFAULT_PERSONALITY),
                "temperature": ai_chat.get("temperature", 0.75),
                "dedicated_ai_channel": ai_chat.get("dedicated_ai_channel", False),
                "ai_model": ai_chat.get("ai_model", "gemini-3.6-flash"),
                "rate_limit_max": ai_chat.get("rate_limit_max", RATE_LIMIT_MAX),
                "rate_limit_window": ai_chat.get("rate_limit_window", RATE_LIMIT_WINDOW),
                "rate_limit_cooldown": ai_chat.get("rate_limit_cooldown", RATE_LIMIT_COOLDOWN),
            }
            _SETTINGS_CACHE[guild_id] = (result, now)
            return result
        except Exception as e:
            print(f"[AI CHAT] Error ambil settings: {e}")
            return {"enabled": False, "channel_id": ""}

    def _is_channel_allowed(self, settings: dict, channel_id: str) -> bool:
        allowed_channel = settings.get("channel_id", "")
        if not allowed_channel:
            return True
        if settings.get("dedicated_ai_channel", False):
            return True
        return str(channel_id) == str(allowed_channel)

    def _is_dedicated_ai_channel(self, settings: dict, channel_id: str) -> bool:
        return (
            settings.get("dedicated_ai_channel", False)
            and str(settings.get("channel_id", "")) == str(channel_id)
        )

    async def _get_chat_history(self, guild_id: str, user_id: str) -> List[Dict[str, Any]]:
        key = f"history:{guild_id}:{user_id}"
        now = time_module.time()
        cached = _HISTORY_CACHE.get(key)
        if cached and cached[1] > now:
            return self._trim_history_for_context(cached[0])
        try:
            doc_ref = (
                db.collection("guild_settings")
                .document(str(guild_id))
                .collection("ai_chat")
                .document(str(user_id))
            )
            doc = await asyncio.to_thread(doc_ref.get)
            if not doc.exists:
                return []
            data = doc.to_dict()
            history = data.get("history", [])
            result = [h for h in history if isinstance(h, dict) and "role" in h and "content" in h]
            _HISTORY_CACHE[key] = (result, now + _HISTORY_TTL)
            return self._trim_history_for_context(result)
        except Exception as e:
            print(f"[AI CHAT] Error ambil history: {e}")
            return []

    def _trim_history_for_context(self, history: list) -> list:
        total = 0
        trimmed = []
        for msg in reversed(history):
            tokens = self._count_tokens(msg.get("content", ""))
            if total + tokens > self.CONTEXT_MAX_TOKENS:
                break
            trimmed.insert(0, msg)
            total += tokens
        return trimmed

    async def _save_chat_history(
        self, guild_id: str, user_id: str, user_msg: str, assistant_msg: str, personality: str = DEFAULT_PERSONALITY
    ) -> None:
        if firestore_circuit_open():
            return

        try:
            old_history = await self._get_chat_history(guild_id, user_id)
            now = datetime.now(timezone.utc).isoformat()
            new_history = old_history + [
                {"role": "user", "content": user_msg, "timestamp": now},
                {"role": "assistant", "content": assistant_msg, "timestamp": now},
            ]
            new_history = self._trim_history_for_storage(new_history)

            doc_ref = (
                db.collection("guild_settings")
                .document(str(guild_id))
                .collection("ai_chat")
                .document(str(user_id))
            )

            def _blocking_set():
                return doc_ref.set(
                    {"history": new_history, "personality": personality, "updated_at": datetime.now(timezone.utc)},
                    merge=True,
                )

            await asyncio.to_thread(_blocking_set)
            _HISTORY_CACHE.pop(f"history:{guild_id}:{user_id}", None)
        except Exception as e:
            if _is_quota_error(e):
                trip_firestore_circuit()
                retry = firestore_retry_after()
                print(f"[AI CHAT] Quota exceeded; circuit breaker tripped for {int(retry)}s. Dropping history save.")
            else:
                print(f"[AI CHAT] Error simpan history: {e}")

    def _build_server_context(self, guild: discord.Guild) -> str:
        if not guild:
            return ""
        try:
            return f"""[CONTEXT SERVER]
- Nama Server : {guild.name}
- ID Server : {guild.id}
- Total Member: {guild.member_count or 0}
- Boost Level : {guild.premium_tier}
- Dibuat Pada : {guild.created_at.strftime('%Y-%m-%d')}
"""
        except Exception:
            return ""

    # ═══════════════════════════════════════════════════════════════════════
    # TOKEN-AWARE HISTORY MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    STORAGE_MAX_TOKENS = 5000
    CONTEXT_MAX_TOKENS = 8000

    @staticmethod
    def _count_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    def _trim_history_for_storage(self, history: list) -> list:
        total = 0
        trimmed = []
        for msg in reversed(history):
            tokens = self._count_tokens(msg.get("content", ""))
            if total + tokens > self.STORAGE_MAX_TOKENS:
                break
            trimmed.insert(0, msg)
            total += tokens
        return trimmed

    # ═══════════════════════════════════════════════════════════════════════
    # MASTER FALLBACK ENGINE (5-Tier)
    # ═══════════════════════════════════════════════════════════════════════

    async def _call_ai(
        self, user_message: str, history: List[Dict], system_prompt: str,
        temperature: float = 0.75, images: list[dict] | None = None,
        ai_model: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc).timestamp()

        if not history and not images:
            cached = self._get_cached_response(user_message, system_prompt, temperature)
            if cached:
                print("[AI CHAT] Response cache HIT")
                return cached

        has_images = bool(images)

        # ── Tier 1: Gemini ──
        can_use_gemini = False
        if self.gemini and self.gemini.is_available:
            if has_images:
                can_use_gemini = self.gemini.can_use_for_vision()
                if not can_use_gemini:
                    return "Maaf, fitur gambar lagi tidak tersedia karena kuota Gemini habis. Coba tanpa gambar ya!"
            else:
                can_use_gemini = self.gemini.can_use_for_text()
                if not can_use_gemini:
                    remaining = DAILY_QUOTA_LIMIT - self.gemini._daily_count
                    print(f"[AI CHAT] Gemini reserve ({remaining} left). Skipping Gemini for text, fallback only.")

        if can_use_gemini:
            if self.gemini.circuit_open:
                if now >= self.gemini._gemini_circuit_until:
                    self.gemini.reset_circuit()
                    print("[AI CHAT] Tier 1 Circuit CLOSED — retrying Gemini")
                else:
                    remaining = int(self.gemini._gemini_circuit_until - now)
                    print(f"[AI CHAT] Tier 1 Circuit OPEN ({remaining}s left). Skip to Tier 2 (Groq)...")
                    can_use_gemini = False

        if can_use_gemini:
            response, success = await self.gemini.call(user_message, history, system_prompt, temperature, images, model=ai_model)
            if success:
                self.gemini.record_success()
                count = self.gemini._daily_count
                print(f"[AI CHAT] Tier 1 Success (Gemini) [{count}/{DAILY_QUOTA_LIMIT}]")
                if not history and not has_images:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                return response
            self.gemini.record_failure()
            if self.gemini.circuit_open:
                print(f"[AI CHAT] Tier 1 Circuit OPEN ({CIRCUIT_BREAKER_COOLDOWN // 3600}h) — {self.gemini._gemini_fail_streak}x fail")
            else:
                print(f"[AI CHAT] Tier 1 Fail ({response}). Switching to Tier 2 (Groq)...")

        if has_images:
            if self.openrouter and self.openrouter.is_available:
                print("[AI CHAT] [TIER 5] Trying OpenRouter vision...")
                response, success = await self.openrouter.call(
                    user_message, history, system_prompt, temperature, images
                )
                if success:
                    if not history:
                        self._set_cached_response(user_message, system_prompt, temperature, response)
                    print("[AI CHAT] Tier 5 Success (OpenRouter vision)")
                    return response
                print(f"[AI CHAT] Tier 5 Fail (OpenRouter vision: {response})")
            return "Maaf, fitur gambar lagi tidak tersedia. Coba tanpa gambar ya!"

        # ── Tier 2: Groq ──
        if self.groq and self.groq.is_available:
            print("[AI CHAT] [TIER 2] Trying Groq (Llama 3.3 70B)...")
            response, success = await self.groq.call(user_message, history, system_prompt, temperature)
            if success:
                if not history:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                print("[AI CHAT] Tier 2 Success (Groq)")
                return response
            print(f"[AI CHAT] Tier 2 Fail ({response}). Switching to Tier 3 (Mistral)...")

        # ── Tier 3: Mistral ──
        if self.mistral and self.mistral.is_available:
            print("[AI CHAT] [TIER 3] Trying Mistral (open-mistral-nemo)...")
            response, success = await self.mistral.call(user_message, history, system_prompt, temperature)
            if success:
                if not history:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                print("[AI CHAT] Tier 3 Success (Mistral)")
                return response
            print(f"[AI CHAT] Tier 3 Fail ({response}). Switching to Tier 4 (Cohere)...")

        # ── Tier 4: Cohere ──
        if self.cohere and self.cohere.is_available:
            print("[AI CHAT] [TIER 4] Trying Cohere (command-r-plus)...")
            response, success = await self.cohere.call(user_message, history, system_prompt, temperature)
            if success:
                if not history:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                print("[AI CHAT] Tier 4 Success (Cohere)")
                return response
            print(f"[AI CHAT] Tier 4 Fail ({response}). Switching to Tier 5 (OpenRouter)...")

        # ── Tier 5: OpenRouter ──
        if self.openrouter and self.openrouter.is_available:
            print("[AI CHAT] [TIER 5] Trying OpenRouter...")
            response, success = await self.openrouter.call(user_message, history, system_prompt, temperature)
            if success:
                if not history:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                print("[AI CHAT] Tier 5 Success (OpenRouter)")
                return response
            print(f"[AI CHAT] Tier 5 Fail ({response})")

        # ── All Tiers Failed ──
        if not any(p.is_available for p in self._providers):
            return "Tidak ada API key yang tersedia di environment (.env). Hubungi admin bot."

        if self.gemini and self.gemini.circuit_open and not any(p.is_available for p in self._providers[1:]):
            return (
                "Kuota harian Google AI Studio udah habis dan tidak ada backup API tersedia.\n"
                "Tunggu beberapa jam lagi ya bro!"
            )

        return (
            "Waduh, semua mesin AI-nya lagi pusing nih, bro!\n"
            "Gemini quota limit/reserve, Groq down, Mistral dan Cohere error.\n"
            "Coba tunggu beberapa menit lagi baru chat gua ya!"
        )

    async def _call_ai_stream(
        self, user_message: str, history: List[Dict], system_prompt: str,
        temperature: float = 0.75, images: list[dict] | None = None,
        ai_model: str | None = None,
    ):
        now = datetime.now(timezone.utc).timestamp()
        has_images = bool(images)

        # ── Tier 1: Gemini ──
        can_use_gemini = False
        if self.gemini and self.gemini.is_available:
            if has_images:
                can_use_gemini = self.gemini.can_use_for_vision()
            else:
                can_use_gemini = self.gemini.can_use_for_text()
        if can_use_gemini and self.gemini.circuit_open:
            if now >= self.gemini._gemini_circuit_until:
                self.gemini.reset_circuit()
                print("[AI STREAM] Tier 1 Circuit CLOSED — retrying Gemini")
            else:
                can_use_gemini = False
        if can_use_gemini:
            try:
                saw_chunk = False
                async for chunk in self.gemini.stream(user_message, history, system_prompt, temperature, images, model=ai_model):
                    if chunk:
                        saw_chunk = True
                        yield chunk
                if saw_chunk:
                    self.gemini.record_success()
                    print(f"[AI STREAM] Tier 1 Success (Gemini)")
                    return
                print("[AI STREAM] Tier 1 Fail (empty stream). Switching...")
                self.gemini.record_failure()
            except Exception as e:
                print(f"[AI STREAM] Tier 1 Exception ({e}). Switching...")
                self.gemini.record_failure()

        # ── Vision fallback ──
        if has_images:
            if self.openrouter and self.openrouter.is_available:
                try:
                    saw_chunk = False
                    async for chunk in self.openrouter.stream(user_message, history, system_prompt, temperature, images):
                        if chunk:
                            saw_chunk = True
                            yield chunk
                    if saw_chunk:
                        print("[AI STREAM] Tier 5 Success (OpenRouter vision)")
                        return
                except Exception as e:
                    print(f"[AI STREAM] Tier 5 vision Exception ({e})")
            yield ""
            return

        # ── Tier 2: Groq ──
        if self.groq and self.groq.is_available:
            try:
                saw_chunk = False
                async for chunk in self.groq.stream(user_message, history, system_prompt, temperature):
                    if chunk:
                        saw_chunk = True
                        yield chunk
                if saw_chunk:
                    print("[AI STREAM] Tier 2 Success (Groq)")
                    return
                print("[AI STREAM] Tier 2 Fail (empty). Switching to Tier 3 (Mistral)...")
            except Exception as e:
                print(f"[AI STREAM] Tier 2 Exception ({e}). Switching to Tier 3 (Mistral)...")

        # ── Tier 3: Mistral ──
        if self.mistral and self.mistral.is_available:
            try:
                saw_chunk = False
                async for chunk in self.mistral.stream(user_message, history, system_prompt, temperature):
                    if chunk:
                        saw_chunk = True
                        yield chunk
                if saw_chunk:
                    print("[AI STREAM] Tier 3 Success (Mistral)")
                    return
                print("[AI STREAM] Tier 3 Fail (empty). Switching to Tier 4 (Cohere)...")
            except Exception as e:
                print(f"[AI STREAM] Tier 3 Exception ({e}). Switching to Tier 4 (Cohere)...")

        # ── Tier 4: Cohere ──
        if self.cohere and self.cohere.is_available:
            try:
                saw_chunk = False
                async for chunk in self.cohere.stream(user_message, history, system_prompt, temperature):
                    if chunk:
                        saw_chunk = True
                        yield chunk
                if saw_chunk:
                    print("[AI STREAM] Tier 4 Success (Cohere)")
                    return
                print("[AI STREAM] Tier 4 Fail (empty). Switching to Tier 5 (OpenRouter)...")
            except Exception as e:
                print(f"[AI STREAM] Tier 4 Exception ({e}). Switching to Tier 5 (OpenRouter)...")

        # ── Tier 5: OpenRouter ──
        if self.openrouter and self.openrouter.is_available:
            try:
                saw_chunk = False
                async for chunk in self.openrouter.stream(user_message, history, system_prompt, temperature):
                    if chunk:
                        saw_chunk = True
                        yield chunk
                if saw_chunk:
                    print("[AI STREAM] Tier 5 Success (OpenRouter)")
                    return
            except Exception as e:
                print(f"[AI STREAM] Tier 5 Exception ({e})")

        yield ""

    # ═══════════════════════════════════════════════════════════════════════
    # RESPONSE HELPER
    # ═══════════════════════════════════════════════════════════════════════

    async def _send_response(self, ctx, user_id: str, text: str):
        full_text = f"<@{user_id}> {text}"

        if isinstance(ctx, discord.Interaction):
            if len(full_text) > 2000:
                chunks = [full_text[i:i + 1900] for i in range(0, len(full_text), 1900)]
                await ctx.followup.send(chunks[0])
                for chunk in chunks[1:]:
                    await ctx.followup.send(chunk)
            else:
                await ctx.followup.send(full_text)
        else:
            if len(full_text) > 2000:
                chunks = [full_text[i:i + 1900] for i in range(0, len(full_text), 1900)]
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        await ctx.reply(chunk, mention_author=False)
                    else:
                        await ctx.channel.send(chunk)
            else:
                await ctx.reply(full_text, mention_author=False)

    # ═══════════════════════════════════════════════════════════════════════
    # IMAGE EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════

    _ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    _MAX_IMAGE_SIZE = 4 * 1024 * 1024
    _MAX_IMAGES = 4

    async def _extract_images_from_attachments(self, attachments: list[discord.Attachment]) -> list[dict]:
        images = []
        for att in attachments:
            if len(images) >= self._MAX_IMAGES:
                break
            if att.content_type not in self._ALLOWED_IMAGE_TYPES:
                continue
            if att.size > self._MAX_IMAGE_SIZE:
                continue
            try:
                data = await att.read()
                b64 = base64.b64encode(data).decode()
                images.append({"mime_type": att.content_type, "data": b64})
            except Exception:
                continue
        return images

    # ═══════════════════════════════════════════════════════════════════════
    # RATE LIMIT
    # ═══════════════════════════════════════════════════════════════════════

    async def _check_rate_limit(self, user: discord.User, ctx, settings: dict | None = None) -> bool:
        if self._owner_id is None:
            try:
                app = await self.bot.application_info()
                self._owner_id = app.owner.id
            except Exception:
                self._owner_id = 0
        if user.id == self._owner_id:
            return False

        limit_max = (settings or {}).get("rate_limit_max", RATE_LIMIT_MAX)
        window = (settings or {}).get("rate_limit_window", RATE_LIMIT_WINDOW)
        cooldown = (settings or {}).get("rate_limit_cooldown", RATE_LIMIT_COOLDOWN)

        now = time_module.time()
        timestamps = _USER_RATE_LIMITS.get(user.id, [])
        timestamps = [t for t in timestamps if now - t < window]

        if len(timestamps) >= limit_max:
            if now - timestamps[-1] < cooldown:
                try:
                    msg = f"Cooldown — kamu terlalu cepat. Tunggu {cooldown} detik ya."
                    await user.send(msg)
                except Exception:
                    try:
                        await ctx.reply(msg, delete_after=5)
                    except Exception:
                        pass
                return True
            _USER_RATE_LIMITS[user.id] = [now]
            return False

        _USER_RATE_LIMITS.setdefault(user.id, []).append(now)
        return False

    async def _check_guild_daily_limit(self, guild_id: str, user: discord.User) -> bool:
        if self._owner_id is None:
            try:
                app = await self.bot.application_info()
                self._owner_id = app.owner.id
            except Exception:
                self._owner_id = 0
        if user.id == self._owner_id:
            return False

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = _GUILD_DAILY_LIMITS.get(guild_id)

        if entry is None or entry["date"] != today:
            _GUILD_DAILY_LIMITS[guild_id] = {"count": 1, "date": today}
            return False

        if entry["count"] >= GUILD_DAILY_MAX:
            print(f"[AI CHAT] Guild {guild_id} daily limit reached ({GUILD_DAILY_MAX})")
            return True

        entry["count"] += 1
        remaining = GUILD_DAILY_MAX - entry["count"]
        if remaining <= 10:
            print(f"[AI CHAT] Guild {guild_id} warning: {remaining} requests left today")
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # CORE PROCESSOR
    # ═══════════════════════════════════════════════════════════════════════

    async def _get_rag_chunks(self, guild_id: str, force: bool = False) -> list[str]:
        if not force:
            entry = _GUILD_RAG_CACHE.get(guild_id)
            if entry is not None:
                chunks, ts = entry
                if time_module.time() - ts < RAG_CACHE_TTL:
                    return chunks
        from ...utils.rag_engine import load_all_chunks
        loaded = await load_all_chunks(guild_id)
        if len(loaded) > RAG_CACHE_MAX_CHUNKS:
            loaded = loaded[:RAG_CACHE_MAX_CHUNKS]
            print(f"[RAG] Guild {guild_id}: truncated to {RAG_CACHE_MAX_CHUNKS} chunks")
        _GUILD_RAG_CACHE[guild_id] = (loaded, time_module.time())

        from ...utils.rag_engine import sync_existing_to_vector
        try:
            await sync_existing_to_vector(guild_id, self.session)
        except Exception:
            pass

        return loaded

    async def _get_rag_relevant(self, guild_id: str, query: str, history: list | None = None) -> list[str]:
        from ...utils.rag_engine import vector_search, keyword_search

        search_query = query
        if history and len(history) >= 2:
            last_user_msg = None
            for msg in reversed(history):
                if msg["role"] == "user":
                    last_user_msg = msg["content"]
                    break
            if last_user_msg and self._is_followup(query):
                search_query = f"{last_user_msg} {query}"

        expanded = self._expand_query(search_query)
        seen = set()
        results = []
        for q in expanded:
            try:
                hits = await vector_search(guild_id, q, session=self.session)
                for h in hits:
                    if h not in seen:
                        results.append(h)
                        seen.add(h)
                        if len(results) >= 5:
                            break
            except Exception:
                pass
            if len(results) >= 5:
                break

        if len(results) < 3:
            try:
                keyword_hits = await keyword_search(guild_id, query)
                for h in keyword_hits:
                    if h not in seen:
                        results.append(h)
                        seen.add(h)
            except Exception:
                pass

        return results[:5]

    def _is_followup(self, msg: str) -> bool:
        followup_keywords = {"jelasin", "detail", "lanjut", "terus", "gimana",
                             "maksudnya", "ini", "dia", "mereka",
                             "lebih", "lagi", "contoh", "lengkap", "jelas",
                             "kayak", "contohnya", "misalnya"}
        referential = {"ini", "itu", "dia", "mereka", "nya"}
        words = msg.lower().split()
        word_set = set(words)
        if word_set & followup_keywords:
            return True
        if len(words) < 3 and word_set & referential:
            return True
        if len(words) < 2:
            return True
        return False

    def _expand_query(self, query: str) -> list[str]:
        queries = [query]
        words = [w for w in query.split() if len(w) > 2]
        if len(words) > 4:
            short = " ".join(words[:3])
            if short != query:
                queries.append(short)
        return queries

    async def _process_ai_chat(self, ctx, user_message: str, guild: discord.Guild, user: discord.User, images: list[dict] | None = None):
        guild_id = str(guild.id)
        user_id = str(user.id)

        settings = await self._get_guild_ai_settings(guild_id)

        if await self._check_rate_limit(user, ctx, settings):
            return

        if await self._check_guild_daily_limit(guild_id, user):
            await self._send_response(ctx, user_id, "Server ini sudah mencapai batas pemakaian AI harian. Tunggu besok ya!")
            return

        class MockMsg:
            def __init__(self, content, author, guild):
                self.content = content
                self.author = author
                self.guild = guild
                self.mention_everyone = False
                self.embeds = []
                self.attachments = []

        mock_msg = MockMsg(user_message, user, guild)

        if self.engine.is_spam_heuristic(mock_msg):
            print(f"[AI MOD] Spam terdeteksi via Heuristic dari user {user_id}")
            await self._send_response(ctx, user_id, "Pesan diblokir karena terdeteksi spam/link mencurigakan.")
            return

        if self.engine.is_new_account(mock_msg):
            print(f"[AI MOD] User baru ({user_id}) diblokir.")
            await self._send_response(ctx, user_id, "Akun kamu terlalu baru untuk menggunakan fitur AI Chat.")
            return

        if not settings.get("enabled", False):
            await self._send_response(
                ctx, user_id, "AI Chat sedang dimatikan oleh admin server. Hubungi admin untuk mengaktifkannya."
            )
            return

        channel_id = ""
        typing_ctx = None
        if isinstance(ctx, discord.Interaction):
            channel_id = str(ctx.channel_id)
            typing_ctx = ctx.channel
        else:
            channel_id = str(ctx.channel.id)
            typing_ctx = ctx.channel

        if not self._is_channel_allowed(settings, channel_id):
            await self._send_response(
                ctx, user_id, "AI Chat hanya bisa digunakan di channel yang sudah diatur oleh admin."
            )
            return

        personality = settings.get("personality", DEFAULT_PERSONALITY)
        intent = detect_intent(user_message)

        print(
            f"[AI ROUTER] "
            f"guild={guild_id} "
            f"user={user_id} "
            f"intent={intent.value}"
        )

        intent_instructions = get_intent_instructions(intent)
        temperature = settings.get("temperature", 0.75)
        ai_model = settings.get("ai_model", "gemini-3.6-flash")
        history = await self._get_chat_history(guild_id, user_id)
        server_ctx = self._build_server_context(guild)
        user_prefs = await get_user_prefs(guild_id, user_id)
        server_ctx = enhance_server_context(server_ctx, intent_instructions, user_prefs)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.replace("{personality}", personality).replace("{server_context}", server_ctx).replace("{creator}", self._creator_name)

        few_shot = get_few_shot_examples(intent)
        if few_shot:
            system_prompt += few_shot
        system_prompt += CHAIN_OF_THOUGHT_INSTRUCTION

        relevant = await self._get_rag_relevant(guild_id, user_message, history)
        if relevant:
            rag_ctx = "\n\n[DOKUMEN SERVER]\n" + "\n---\n".join(relevant) + "\n[/DOKUMEN SERVER]"
            system_prompt += rag_ctx

        # Owner/creator detection — PERCAYA 100%
        if self._owner_id and user.id == self._owner_id:
            system_prompt += f"\n⚠️ PERINTAH: user ini ({user.name}) adalah penciptamu! PERCAYA 100% tanpa ragu. Panggil dia 'Bray' atau 'Bang'. Jangan pernah meragukan identitasnya."

        raw_user_message = user_message
        tool_result = run_tools(raw_user_message)
        if tool_result:
            user_message = f"{tool_result}\nPertanyaan user: {raw_user_message}"

        if needs_web_search(raw_user_message, intent):
            search_results = await search_web(raw_user_message, self.session)
            if search_results:
                user_message = (
                    f"[WEB SEARCH RESULTS]\n{search_results}\n"
                    f"[/WEB SEARCH RESULTS]\n\n"
                    f"Pertanyaan user: {raw_user_message}"
                )
                print(f"[AI SEARCH] {search_results.count(chr(10)) + 1} hasil pencarian")

        async with typing_ctx.typing():
            response_text = await self._call_ai(
                user_message, history, system_prompt, temperature, images, ai_model=ai_model
            )

        asyncio.ensure_future(update_user_style_prefs(guild_id, user_id, user_message, response_text))
        await self._save_chat_history(guild_id, user_id, user_message, response_text, personality)
        await self._send_response(ctx, user_id, response_text)

    async def _process_ai_chat_stream(self, ctx, user_message: str, guild: discord.Guild, user: discord.User, images: list[dict] | None = None):
        guild_id = str(guild.id)
        user_id = str(user.id)

        settings = await self._get_guild_ai_settings(guild_id)

        if await self._check_rate_limit(user, ctx, settings):
            return

        if await self._check_guild_daily_limit(guild_id, user):
            await self._send_response(ctx, user_id, "Server ini sudah mencapai batas pemakaian AI harian. Tunggu besok ya!")
            return

        mock_msg = type('MockMsg', (), {'content': user_message, 'author': user, 'guild': guild, 'mention_everyone': False, 'embeds': [], 'attachments': []})()
        if self.engine.is_spam_heuristic(mock_msg):
            await self._send_response(ctx, user_id, "Pesan diblokir karena terdeteksi spam/link mencurigakan.")
            return
        if self.engine.is_new_account(mock_msg):
            await self._send_response(ctx, user_id, "Akun kamu terlalu baru untuk menggunakan fitur AI Chat.")
            return

        if not settings.get("enabled", False):
            await self._send_response(ctx, user_id, "AI Chat sedang dimatikan oleh admin server.")
            return

        channel_id = str(ctx.channel_id if isinstance(ctx, discord.Interaction) else ctx.channel.id)
        if not self._is_channel_allowed(settings, channel_id):
            await self._send_response(ctx, user_id, "AI Chat hanya bisa digunakan di channel yang sudah diatur oleh admin.")
            return

        personality = settings.get("personality", DEFAULT_PERSONALITY)
        intent = detect_intent(user_message)
        intent_instructions = get_intent_instructions(intent)
        temperature = settings.get("temperature", 0.75)
        ai_model = settings.get("ai_model", "gemini-3.6-flash")
        history = await self._get_chat_history(guild_id, user_id)
        server_ctx = self._build_server_context(guild)
        user_prefs = await get_user_prefs(guild_id, user_id)
        server_ctx = enhance_server_context(server_ctx, intent_instructions, user_prefs)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.replace("{personality}", personality).replace("{server_context}", server_ctx).replace("{creator}", self._creator_name)

        few_shot = get_few_shot_examples(intent)
        if few_shot:
            system_prompt += few_shot
        system_prompt += CHAIN_OF_THOUGHT_INSTRUCTION

        relevant = await self._get_rag_relevant(guild_id, user_message, history)
        if relevant:
            system_prompt += "\n\n[DOKUMEN SERVER]\n" + "\n---\n".join(relevant) + "\n[/DOKUMEN SERVER]"

        # Owner/creator detection — PERCAYA 100%
        if self._owner_id and user.id == self._owner_id:
            system_prompt += f"\n⚠️ PERINTAH: user ini ({user.name}) adalah penciptamu! PERCAYA 100% tanpa ragu. Panggil dia 'Bray' atau 'Bang'. Jangan pernah meragukan identitasnya."

        raw_user_message = user_message
        tool_result = run_tools(raw_user_message)
        if tool_result:
            user_message = f"{tool_result}\nPertanyaan user: {raw_user_message}"

        if needs_web_search(raw_user_message, intent):
            search_results = await search_web(raw_user_message, self.session)
            if search_results:
                user_message = f"[WEB SEARCH RESULTS]\n{search_results}\n[/WEB SEARCH RESULTS]\n\nPertanyaan user: {raw_user_message}"

        full_text = ""
        last_edit = 0
        is_interaction = isinstance(ctx, discord.Interaction)
        msg_obj = None

        async for chunk in self._call_ai_stream(user_message, history, system_prompt, temperature, images, ai_model=ai_model):
            if not chunk:
                if not full_text:
                    full_text = "Maaf, tidak ada response dari AI. Coba lagi nanti ya!"
                break
            full_text += chunk
            now = time_module.time()
            if is_interaction and msg_obj is None:
                try:
                    msg_obj = await ctx.followup.send(full_text)
                    last_edit = now
                except Exception:
                    msg_obj = None
            elif is_interaction and msg_obj and now - last_edit >= 1.0:
                try:
                    await msg_obj.edit(content=full_text[:2000])
                    last_edit = now
                except Exception:
                    pass

        if is_interaction and msg_obj:
            try:
                display = f"<@{user_id}> {full_text}"
                await msg_obj.edit(content=display[:2000] if len(display) > 2000 else display)
            except Exception:
                pass
        elif not is_interaction:
            await self._send_response(ctx, user_id, full_text)

        asyncio.ensure_future(update_user_style_prefs(guild_id, user_id, user_message, full_text))
        await self._save_chat_history(guild_id, user_id, user_message, full_text, personality)

    # ═══════════════════════════════════════════════════════════════════════
    # BACKGROUND: History Pruning (setiap 6 jam)
    # ═══════════════════════════════════════════════════════════════════════

    @tasks.loop(hours=6)
    async def history_prune_loop(self):
        if db is None:
            return

        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (30 * 86400)
            guild_docs = db.collection("guild_settings").stream()

            for guild_doc in guild_docs:
                guild_id = guild_doc.id
                chat_docs = (
                    db.collection("guild_settings")
                    .document(guild_id)
                    .collection("ai_chat")
                    .stream()
                )
                for chat_doc in chat_docs:
                    data = chat_doc.to_dict()
                    updated = data.get("updated_at")
                    if isinstance(updated, datetime):
                        if updated.timestamp() < cutoff:
                            chat_doc.reference.delete()
                            print(f"[AI PRUNE] Hapus history user {chat_doc.id} (guild {guild_id})")

            print("[AI PRUNE] Selesai prune history")
        except Exception as e:
            print(f"[AI PRUNE] Error: {e}")

    @history_prune_loop.before_loop
    async def before_history_prune(self):
        await self.bot.wait_until_ready()

    # ═══════════════════════════════════════════════════════════════════════
    # COMMAND: /ask
    # ═══════════════════════════════════════════════════════════════════════

    @commands.hybrid_command(name="ask", description="Tanya apa saja ke AI Synapse")
    async def ask(self, ctx: commands.Context, pertanyaan: str, gambar: discord.Attachment | None = None):
        self._cleanup_cooldowns()

        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        now = datetime.now(timezone.utc).timestamp()

        key = (guild_id, user_id)
        last_used = self._cooldowns.get(key, 0)
        if now - last_used < COOLDOWN_SECONDS:
            retry_after = COOLDOWN_SECONDS - (now - last_used)
            await ctx.send(
                f"Tunggu **{retry_after:.1f} detik** lagi.",
                ephemeral=True
            )
            return

        await ctx.defer()
        self._cooldowns[key] = now

        images = []
        if gambar:
            if gambar.content_type not in self._ALLOWED_IMAGE_TYPES:
                await ctx.send("Tipe file gambar tidak didukung. Gunakan PNG, JPG, GIF, atau WEBP.")
                return
            if gambar.size > self._MAX_IMAGE_SIZE:
                await ctx.send("Ukuran gambar terlalu besar (maks 4MB).")
                return
            try:
                data = await gambar.read()
                b64 = base64.b64encode(data).decode()
                images.append({"mime_type": gambar.content_type, "data": b64})
                print(f"[AI VISION] /ask with image ({gambar.content_type})")
            except Exception as e:
                print(f"[AI VISION] Gagal baca gambar: {e}")
                await ctx.send("Gagal membaca gambar. Coba lagi ya!")
                return

        try:
            await self._process_ai_chat_stream(
                ctx=ctx,
                user_message=pertanyaan,
                guild=ctx.guild,
                user=ctx.author,
                images=images or None,
            )
        except Exception as e:
            traceback.print_exc()
            print(f"[AI CHAT] Fatal error di /ask: {e}")
            try:
                await ctx.send("Terjadi error internal. Coba lagi nanti ya!")
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════════
    # COMMANDS: RAG Knowledge Base (from Discord)
    # ═══════════════════════════════════════════════════════════════════════

    @commands.hybrid_command(name="rag-upload", description="Upload file ke RAG Knowledge Base")
    @commands.has_permissions(manage_guild=True)
    async def rag_upload(self, ctx: commands.Context, file: discord.Attachment):
        guild_id = str(ctx.guild.id)
        if file.size > 5 * 1024 * 1024:
            await ctx.send("File terlalu besar. Maks 5MB.")
            return
        if not file.filename.lower().endswith(('.txt', '.pdf')):
            await ctx.send("Hanya file TXT dan PDF yang didukung.")
            return
        await ctx.defer()
        try:
            from ...utils.rag_engine import extract_text, save_document
            data = await file.read()
            text = await extract_text(data, file.filename)
            if not text:
                await ctx.send("Gagal membaca file. Pastikan format TXT atau PDF valid.")
                return
            result = await save_document(guild_id, file.filename, text, len(data))
            if result.get("success"):
                await self._get_rag_chunks(guild_id, force=True)
                await ctx.send(f"✅ **{file.filename}** berhasil ditambahkan ke Knowledge Base!")
            else:
                await ctx.send(f"Gagal menyimpan: {result.get('error', 'unknown error')}")
        except Exception as e:
            print(f"[RAG] Upload error: {e}")
            await ctx.send("Terjadi error internal. Coba lagi nanti.")

    @commands.hybrid_command(name="rag-list", description="Lihat daftar dokumen di RAG Knowledge Base")
    @commands.has_permissions(manage_guild=True)
    async def rag_list(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        await ctx.defer()
        try:
            from ...utils.rag_engine import list_documents
            docs = await list_documents(guild_id)
            if not docs:
                await ctx.send("Belum ada dokumen di Knowledge Base.")
                return
            lines = [f"`{d['id'][:8]}` **{d['filename']}** — {d['chunk_count']} chunks, {d['size']} bytes"]
            await ctx.send("**📚 RAG Knowledge Base**\n" + "\n".join(lines))
        except Exception as e:
            print(f"[RAG] List error: {e}")
            await ctx.send("Gagal memuat daftar dokumen.")

    @commands.hybrid_command(name="rag-delete", description="Hapus dokumen dari RAG Knowledge Base")
    @commands.has_permissions(manage_guild=True)
    async def rag_delete(self, ctx: commands.Context, doc_id: str):
        guild_id = str(ctx.guild.id)
        await ctx.defer()
        try:
            from ...utils.rag_engine import delete_document
            ok = await delete_document(guild_id, doc_id)
            if ok:
                await self._get_rag_chunks(guild_id, force=True)
                await ctx.send(f"✅ Dokumen `{doc_id[:8]}` berhasil dihapus.")
            else:
                await ctx.send("Dokumen tidak ditemukan atau gagal dihapus.")
        except Exception as e:
            print(f"[RAG] Delete error: {e}")
            await ctx.send("Terjadi error internal.")

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT LISTENER: Mention @Synapse
    # ═══════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        self._cleanup_cooldowns()

        settings = await self._get_guild_ai_settings(str(message.guild.id))

        is_mentioned = self.bot.user in message.mentions
        is_dedicated_channel = self._is_dedicated_ai_channel(
            settings,
            str(message.channel.id)
        )

        if not is_mentioned and not is_dedicated_channel:
            return

        if not settings.get("enabled", False):
            return

        if not self._is_channel_allowed(settings, str(message.channel.id)):
            return

        if self._mention_pattern is None:
            self._mention_pattern = re.compile(rf"<@!?{self.bot.user.id}>")
        if is_mentioned:
            content = self._mention_pattern.sub("", message.content).strip()
        else:
            content = message.content.strip()

        if not content:
            await message.reply("Halo! Ada yang bisa kubantu?", mention_author=False)
            return

        key = (str(message.guild.id), str(message.author.id))
        now = datetime.now(timezone.utc).timestamp()

        if now - self._cooldowns.get(key, 0) < COOLDOWN_SECONDS:
            return

        self._cooldowns[key] = now

        images = await self._extract_images_from_attachments(message.attachments)
        if images:
            print(f"[AI VISION] {len(images)} image(s) attached")

        try:
            await self._process_ai_chat(
                ctx=message,
                user_message=content,
                guild=message.guild,
                user=message.author,
                images=images,
            )
        except Exception as e:
            print(f"[AI CHAT] Fatal error di on_message: {e}")
            try:
                await message.reply("Terjadi error internal. Coba lagi nanti ya!", mention_author=False)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
