"""
================================================================================
COG: AI Chat Module v4.7 — Synapse Discord Bot
================================================================================
File    : backend/cogs/ai_chat.py
Deskripsi : Triple API Fallback — Google AI Studio (T1) → Groq (T2) → OpenRouter (T3)
  • Tier 1: Google AI Studio — Primary (Gemini 3.5 Flash / 3.1 Flash vision)
  • Tier 2: Groq — Backup (Llama 3.3 70B Versatile)
  • Tier 3: Atomesus — Last Resort (Cipher 8B)
  • Lightweight Circuit Breaker: Gemini auto-skip 2h setelah 3x fail berturut-turut
  • Compact structured logging — 1 line per tier switch
  • Slash command /ask + Mention handler (@bot)
  • Channel restriction, personality, temperature via dashboard
  • Chat history Firestore (max 5 pasang Q&A per user)
  • [v4.7] Spam Detection Guard — analyze_spam() aktif di awal _process_ai_chat
  • [v4.7] Personalized Mention — setiap respons AI diawali <@user_id>
  • [v4.7] Regex-accurate bot-mention stripping di on_message
  • [v4.7] typing() langsung membungkus _call_ai tanpa try-except ganda
================================================================================
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
import tenacity

from ..database.firebase_setup import db
from ...utils.spam_engine import SpamEngine
from ...utils.intent_router import detect_intent
from ...utils.firestore_stats import (
    firestore_circuit_open,
    trip_firestore_circuit,
    firestore_retry_after,
    _is_quota_error,
)
from .prompt import SYSTEM_PROMPT_TEMPLATE

# ── Konstanta ──
MAX_HISTORY_PAIRS = 5
COOLDOWN_SECONDS = 5
DEFAULT_PERSONALITY = "friendly"

# ── Daily Quota ──
DAILY_QUOTA_LIMIT = 1500      # Gemini free tier ~1500 request/hari
RESPONSE_CACHE_TTL = 300       # cache response 5 menit

# ── Tier 1: Google AI Studio ──
GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_MODEL = "gemini-3.5-flash"

GOOGLE_VISION_MODEL = "gemini-3.1-flash"
# ── Tier 2: Groq ──
GROQ_API_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Tier 3: Mistral ──
MISTRAL_API_BASE = "https://api.mistral.ai/v1"
MISTRAL_MODEL = "open-mistral-nemo"

# ── Tier 4: Cohere ──
COHERE_API_BASE = "https://api.cohere.com/v2"
COHERE_MODEL = "command-r-plus"

# ── Circuit Breaker ──
CIRCUIT_BREAKER_THRESHOLD = 3       # fail streak sebelum circuit open
CIRCUIT_BREAKER_COOLDOWN = 7200     # 2 jam (detik)
# FUNGSI INI WAJIB ADA: Mencegah RetryError crash, dan oper balik status gagal
def return_failure_tuple(retry_state):
    return "RETRY_LIMIT_EXCEEDED", False

class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.engine = SpamEngine()
        self._cooldowns: Dict[tuple, float] = {}

        # API Keys
        self.google_api_key = os.getenv("GEMINI_API_KEY", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY", "")
        self.cohere_api_key = os.getenv("COHERE_API_KEY", "")

        # Circuit Breaker State (Tier 1: Gemini)
        self._gemini_circuit_open = False
        self._gemini_circuit_until = 0.0
        self._gemini_fail_streak = 0

        if not self.google_api_key:
            print("[AI CHAT] ⚠️ GEMINI_API_KEY tidak ditemukan!")
        if not self.groq_api_key:
            print("[AI CHAT] ⚠️ GROQ_API_KEY tidak ditemukan!")
        if not self.mistral_api_key:
            print("[AI CHAT] ⚠️ MISTRAL_API_KEY tidak ditemukan!")
        if not self.cohere_api_key:
            print("[AI CHAT] ⚠️ COHERE_API_KEY tidak ditemukan!")

        self.session: aiohttp.ClientSession | None = None

        # Spam analysis cache (content hash -> (timestamp, result))
        self._spam_cache: dict[str, tuple[float, bool]] = {}
        self._spam_cache_ttl = 300  # 5 menit
        self._spam_last_check: float = 0.0  # ratelimit antar spam check
        self._spam_min_interval = 1.0  # minimal 1 detik antar panggilan spam AI

        # Cache compiled regex untuk strip mention bot di on_message
        # (di-build sekali saat dibutuhkan, lihat on_message)
        self._mention_pattern: "re.Pattern | None" = None

        # ── Daily quota tracking ──
        self._daily_count = 0
        self._daily_quota_date = datetime.now(timezone.utc).date()

        # ── Response cache (content_hash -> (response, timestamp)) ──
        self._response_cache: dict[str, tuple[str, float]] = {}

        self._last_history_prune: float = 0.0

        print("[AI CHAT] ✅ Cog loaded. Quad API: Google → Groq → Mistral → Cohere")

    async def cog_load(self):
        if self.session and not self.session.closed:
            return
      
        timeout = aiohttp.ClientTimeout(
            total=60,
            connect=20
        )
      
        self.session = aiohttp.ClientSession(
            timeout=timeout
        )

        self.history_prune_loop.start()
      
        print("[AI CHAT] ✅ HTTP session initialized")

    async def cog_unload(self):
        self.history_prune_loop.cancel()
        if self.session:
            await self.session.close()
            print("[AI CHAT] ✅ HTTP session closed")

    async def analyze_spam(self, content: str, risk_score: int = 0, account_age_days: int = 0, matched_keywords: list[str] | None = None) -> bool:
        """
        Deteksi spam berbasis AI dengan cache + rate-limit.
        Groq diprioritaskan (lebih cepat, free tier lebih longgar).
        """
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        now = time_module.time()

        # ── Cache ──
        if content_hash in self._spam_cache:
            cached_time, cached_result = self._spam_cache[content_hash]
            if now - cached_time < self._spam_cache_ttl:
                return cached_result

        # ── Rate-limit ──
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
                system_prompt=(
                    "Anda adalah moderator spam yang tegas dan konsisten. "
                    "Analisis pesan berdasarkan konten dan konteks. "
                    "Anggap mencurigakan jika: promosi judi/slot, scam giveaway, "
                    "link phishing, akun baru kirim link mencurigakan. "
                    "Jawab HANYA 'YA' atau 'TIDAK'."
                ),
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
        """Gemini Vision: analisis apakah gambar mengandung spam/judi/scam."""
        if not self.google_api_key or not self.session:
            return False

        try:
            import base64
            b64 = base64.b64encode(image_data).decode()

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Analisis gambar ini. Apakah mengandung: promosi judi/slot, scam, "
                                 "konten penipuan, atau phishing? Jawab HANYA 'YA' atau 'TIDAK'."},
                        {"inline_data": {"mime_type": mime_type, "data": b64}},
                    ]
                }],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 64},
            }

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={self.google_api_key}"

            async with self.session.post(url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return False
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return "YA" in text.upper()
        except Exception as e:
            print(f"[AI VISION] Error: {e}")
            return False

    def _cleanup_cooldowns(self):
       now = datetime.now(timezone.utc).timestamp()
       # Hanya simpan user yang cooldown-nya masih aktif (< 60 detik)
       self._cooldowns = {k: v for k, v in self._cooldowns.items() if now - v < 60}
        
    
    async def _defer_interaction(self, interaction: discord.Interaction):
        try:
            # Respon instan agar interaksi tidak expired
            await interaction.response.defer(thinking=True)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print(f"[AI CHAT] ⚠️ Kena Rate Limit saat defer! Bot sedang sibuk.")
            else:
                print(f"[AI CHAT] Error lain saat defer: {e}")
            

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Firestore Settings (ASYNC)
    # ═══════════════════════════════════════════════════════════════════════
    async def _get_guild_ai_settings(self, guild_id: str) -> dict:
        try:
            doc_ref = db.collection("guild_settings").document(str(guild_id))
            doc = await asyncio.to_thread(doc_ref.get)
            if not doc.exists:
                return {"enabled": False, "channel_id": ""}
            data = doc.to_dict()
            ai_chat = data.get("ai_chat", {})
            return {
                "enabled": data.get("ai_chat_enabled", False),
                "channel_id": ai_chat.get("channel_id", ""),
                "personality": ai_chat.get(
                    "personality",
                    DEFAULT_PERSONALITY
                ),
                "temperature": ai_chat.get(
                    "temperature",
                    0.75
                ),
                "dedicated_ai_channel": ai_chat.get(
                    "dedicated_ai_channel",
                    False
                ),
            }
        except Exception as e:
            print(f"[AI CHAT] ⚠️ Error ambil settings: {e}")
            return {"enabled": False, "channel_id": ""}

    def _is_channel_allowed(self, settings: dict, channel_id: str) -> bool:
        allowed_channel = settings.get("channel_id", "")
        if not allowed_channel:
            return True
        # Dedicated mode: channel_id cuma nentuin channel auto-response.
        # Channel lain tetap boleh pake mention/ask.
        if settings.get("dedicated_ai_channel", False):
            return True
        # Restriction mode: cuma channel_id yang boleh pake AI (mention/ask).
        return str(channel_id) == str(allowed_channel)
    
    def _is_dedicated_ai_channel(
        self,
        settings: dict,
        channel_id: str
    ) -> bool:
        return (
            settings.get("dedicated_ai_channel", False)
            and str(settings.get("channel_id", "")) == str(channel_id)
        )

    async def _get_chat_history(self, guild_id: str, user_id: str) -> List[Dict[str, Any]]:
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
            return [h for h in history if isinstance(h, dict) and "role" in h and "content" in h]
        except Exception as e:
            print(f"[AI CHAT] ⚠️ Error ambil history: {e}")
            return []

    async def _save_chat_history(
        self, guild_id: str, user_id: str, user_msg: str, assistant_msg: str, personality: str = DEFAULT_PERSONALITY
    ) -> None:
        # Skip entirely if the shared Firestore circuit breaker is open.
        # Prevents cascading 429s when stats writes already tripped it.
        if firestore_circuit_open():
            return

        try:
            old_history = await self._get_chat_history(guild_id, user_id)
            now = datetime.now(timezone.utc).isoformat()
            new_history = old_history + [
                {"role": "user", "content": user_msg, "timestamp": now},
                {"role": "assistant", "content": assistant_msg, "timestamp": now},
            ]
            # max 5 pasang = 10 entries
            if len(new_history) > 10:
                new_history = new_history[-10:]

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
        except Exception as e:
            # Trip the SHARED circuit breaker if Firestore returned 429,
            # so other cogs (leveling, stats) stop hammering too.
            if _is_quota_error(e):
                trip_firestore_circuit()
                retry = firestore_retry_after()
                print(f"[AI CHAT] ⚠️ Quota exceeded; circuit breaker tripped for {int(retry)}s. Dropping history save.")
            else:
                print(f"[AI CHAT] ⚠️ Error simpan history: {e}")

    def _build_server_context(self, guild: discord.Guild) -> str:
        if not guild:
            return ""
        try:
            return f"""[CONTEXT SERVER]
• Nama Server : {guild.name}
• ID Server : {guild.id}
• Total Member: {guild.member_count or 0}
• Boost Level : {guild.premium_tier}
• Dibuat Pada : {guild.created_at.strftime('%Y-%m-%d')}
"""
        except Exception:
            return ""

    # ═══════════════════════════════════════════════════════════════════════
    # TIER 1: Google AI Studio
    # ═══════════════════════════════════════════════════════════════════════
    
    @tenacity.retry(
        wait=tenacity.wait_exponential(min=1, max=2), 
        stop=tenacity.stop_after_attempt(1),
        retry=tenacity.retry_if_result(lambda res: res[1] is False), # <--- PAKAI KOMA!
        retry_error_callback=return_failure_tuple
    )

    async def _call_google_gemini(
        self, user_message: str, history: List[Dict], system_prompt: str,
        temperature: float = 0.75, images: list[dict] | None = None
    ) -> tuple[str, bool]:
        """Call Google AI Studio. Return (response_text, success)."""
        if not self.google_api_key or not self.session:
            return "API_KEY_MISSING", False

        has_images = bool(images)
        parts = [{"text": user_message}]
        if has_images:
            for img in images:
                parts.append({
                    "inline_data": {
                        "mime_type": img["mime_type"],
                        "data": img["data"]
                    }
                })

        contents = []
        for item in history:
            role = "model" if item["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})
        contents.append({"role": "user", "parts": parts})

        payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        },
    }
        if not has_images:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        else:
            parts[0]["text"] = f"{system_prompt}\n\n{user_message}"

        models_to_try = [GOOGLE_MODEL]
        if has_images:
            models_to_try = [GOOGLE_MODEL, GOOGLE_VISION_MODEL]

        last_status = 0
        for model in models_to_try:
            try:
                url = f"{GOOGLE_API_BASE}/models/{model}:generateContent?key={self.google_api_key}"
                if has_images:
                    print(f"[AI VISION] 🖼️ Trying model={model}, {len(images)} image(s)")

                vision_timeout = aiohttp.ClientTimeout(total=120, connect=30) if has_images else None
                async with self.session.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=vision_timeout) as resp:
                    status = resp.status
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {}

                    if status == 429:
                        err_msg = data.get("error", {}).get("message", "Rate limit or quota exhausted.")
                        print(f"[AI CHAT] ⛔ Google Rate Limit (429): {err_msg[:100]}")
                        return "RATE_LIMIT", False

                    if status == 503 and model != models_to_try[-1]:
                        print(f"[AI VISION] ⚠️ {model} returned 503, falling back to next model...")
                        last_status = status
                        continue

                    if status != 200:
                        print(f"[AI CHAT] ❌ Google HTTP {status} ({model})")
                        return f"HTTP_{status}", False

                    candidates = data.get("candidates", [])
                    if not candidates:
                        return "EMPTY_CANDIDATES", False

                    ret_parts = candidates[0].get("content", {}).get("parts", [])
                    if not ret_parts:
                        return "EMPTY_PARTS", False

                    return ret_parts[0].get("text", "").strip(), True

            except asyncio.TimeoutError:
                if model != models_to_try[-1]:
                    print(f"[AI VISION] ⏱️ {model} timed out, falling back to next model...")
                    continue
                print(f"[AI VISION] ⏱️ {model} timed out (last model)")
                return "TIMEOUT", False
            except Exception as e:
                if model != models_to_try[-1]:
                    print(f"[AI VISION] ⚠️ {model} error ({type(e).__name__}), falling back...")
                    continue
                print(f"[AI CHAT] ❌ Google Exception ({model}): {type(e).__name__}")
                return "EXCEPTION", False

        return f"HTTP_{last_status}", False

    # ═══════════════════════════════════════════════════════════════════════
    # TIER 2: Groq (Llama 3.3 70B)
    # ═══════════════════════════════════════════════════════════════════════

    @tenacity.retry(
        wait=tenacity.wait_exponential(min=1, max=2), 
        stop=tenacity.stop_after_attempt(2),
        retry=tenacity.retry_if_result(lambda res: res[1] is False),
        retry_error_callback=return_failure_tuple 
    )

    async def _call_groq(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> tuple[str, bool]:
        """Call Groq API. Return (response_text, success)."""
        if not self.groq_api_key or not self.session:
            return "API_KEY_MISSING", False

        try:
            messages = [{"role": "system", "content": system_prompt}]
            for item in history:
                role = "assistant" if item["role"] == "assistant" else "user"
                messages.append({"role": role, "content": item["content"]})
            messages.append({"role": "user", "content": user_message})

            payload = {
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 8192,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.groq_api_key}",
            }

            url = f"{GROQ_API_BASE}/chat/completions"
            groq_timeout = aiohttp.ClientTimeout(total=10, connect=5)

            async with self.session.post(url, headers=headers, json=payload, timeout=groq_timeout) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    err_msg = data.get("error", {}).get("message", "Rate limit")
                    print(f"[AI CHAT] ⛔ Groq Rate Limit (429): {err_msg[:100]}")
                    return "RATE_LIMIT", False

                if status in (401, 403):
                    print(f"[AI CHAT] ❌ Groq Auth Error ({status})")
                    return f"AUTH_{status}", False

                if status != 200:
                    print(f"[AI CHAT] ❌ Groq HTTP {status}")
                    return f"HTTP_{status}", False

                choices = data.get("choices", [])
                if not choices:
                    return "EMPTY_CHOICES", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except asyncio.TimeoutError:
            print("[AI CHAT] ⏱️ Groq Timeout (10s)")
            return "TIMEOUT", False
        except Exception as e:
            print(f"[AI CHAT] ❌ Groq Exception: {type(e).__name__}")
            return "EXCEPTION", False

    # ═══════════════════════════════════════════════════════════════════════
    # TIER 3: Mistral (OpenAI-compatible)
    # ═══════════════════════════════════════════════════════════════════════

    @tenacity.retry(
        wait=tenacity.wait_exponential(min=1, max=2), 
        stop=tenacity.stop_after_attempt(2),
        retry=tenacity.retry_if_result(lambda res: res[1] is False),
        retry_error_callback=return_failure_tuple
    )

    async def _call_mistral(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> tuple[str, bool]:
        """Call Mistral (open-mistral-nemo). Return (response_text, success)."""
        if not self.mistral_api_key or not self.session:
            return "API_KEY_MISSING", False

        try:
            messages = [{"role": "system", "content": system_prompt}]
            for item in history:
                role = "assistant" if item["role"] == "assistant" else "user"
                messages.append({"role": role, "content": item["content"]})
            messages.append({"role": "user", "content": user_message})

            payload = {
                "model": MISTRAL_MODEL,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 8192,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.mistral_api_key}",
            }

            url = f"{MISTRAL_API_BASE}/chat/completions"

            async with self.session.post(url, headers=headers, json=payload) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    print("[AI CHAT] ⛔ Mistral Rate Limit (429)")
                    return "RATE_LIMIT", False

                if status != 200:
                    print(f"[AI CHAT] ❌ Mistral HTTP {status}")
                    return f"HTTP_{status}", False

                choices = data.get("choices", [])
                if not choices:
                    return "EMPTY_CHOICES", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except Exception as e:
            print(f"[AI CHAT] ❌ Mistral Exception: {type(e).__name__}")
            return "EXCEPTION", False

    # ═══════════════════════════════════════════════════════════════════════
    # TIER 4: Cohere (v2 OpenAI-compatible)
    # ═══════════════════════════════════════════════════════════════════════

    @tenacity.retry(
        wait=tenacity.wait_exponential(min=1, max=2), 
        stop=tenacity.stop_after_attempt(2),
        retry=tenacity.retry_if_result(lambda res: res[1] is False),
        retry_error_callback=return_failure_tuple
    )

    async def _call_cohere(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> tuple[str, bool]:
        """Call Cohere (command-r-plus). Return (response_text, success)."""
        if not self.cohere_api_key or not self.session:
            return "API_KEY_MISSING", False

        try:
            messages = [{"role": "system", "content": system_prompt}]
            for item in history:
                role = "assistant" if item["role"] == "assistant" else "user"
                messages.append({"role": role, "content": item["content"]})
            messages.append({"role": "user", "content": user_message})

            payload = {
                "model": COHERE_MODEL,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 8192,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cohere_api_key}",
            }

            url = f"{COHERE_API_BASE}/chat"

            async with self.session.post(url, headers=headers, json=payload) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    print("[AI CHAT] ⛔ Cohere Rate Limit (429)")
                    return "RATE_LIMIT", False

                if status != 200:
                    print(f"[AI CHAT] ❌ Cohere HTTP {status}")
                    return f"HTTP_{status}", False

                choices = data.get("choices", [])
                if not choices:
                    return "EMPTY_CHOICES", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except Exception as e:
            print(f"[AI CHAT] ❌ Cohere Exception: {type(e).__name__}")
            return "EXCEPTION", False
        
    # ═══════════════════════════════════════════════════════════════════════
    # MASTER FALLBACK ENGINE (Triple Tier)
    # ═══════════════════════════════════════════════════════════════════════

    def _check_daily_quota(self) -> bool:
        today = datetime.now(timezone.utc).date()
        if today != self._daily_quota_date:
            self._daily_count = 0
            self._daily_quota_date = today
        return self._daily_count < DAILY_QUOTA_LIMIT

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

    async def _call_ai(
        self, user_message: str, history: List[Dict], system_prompt: str,
        temperature: float = 0.75, images: list[dict] | None = None
    ) -> str:
        """Triple API Fallback Engine with Lightweight Circuit Breaker.

        images: list of {"mime_type": str, "data": base64_str} — only Gemini tier supports vision.
        """

        now = datetime.now(timezone.utc).timestamp()

        # ── Response Cache Check (skip when images present) ──
        if not history and not images:
            cached = self._get_cached_response(user_message, system_prompt, temperature)
            if cached:
                print("[AI CHAT] 💾 Response cache HIT")
                return cached

        has_images = bool(images)

        # ── Daily Quota Check ──
        if not self._check_daily_quota():
            print(f"[AI CHAT] ⚠️ Daily quota ({DAILY_QUOTA_LIMIT}) exhausted. Skipping Gemini, fallback only.")
            if has_images:
                return "❌ Maaf, fitur gambar lagi tidak tersedia karena kuota Gemini habis. Coba tanpa gambar ya!"
            # Skip Gemini, langsung ke Groq/OpenRouter

        # ── Tier 1: Google AI Studio (Primary) ──
        if self.google_api_key:
            if self._gemini_circuit_open:
                if now >= self._gemini_circuit_until:
                    self._gemini_circuit_open = False
                    self._gemini_fail_streak = 0
                    print("[AI CHAT] 🟢 Tier 1 Circuit CLOSED — retrying Gemini")
                else:
                    remaining = int(self._gemini_circuit_until - now)
                    print(f"[AI CHAT] ⚠️ Tier 1 Circuit OPEN ({remaining}s left). Skip to Tier 2 (Groq)...")

            if not self._gemini_circuit_open:
                response, success = await self._call_google_gemini(
                    user_message, history, system_prompt, temperature, images
                )
                if success and response:
                    self._gemini_fail_streak = 0
                    self._daily_count += 1
                    if not history and not has_images:
                        self._set_cached_response(user_message, system_prompt, temperature, response)
                    print(f"[AI CHAT] ✅ Tier 1 Success (Gemini) [{self._daily_count}/{DAILY_QUOTA_LIMIT}]")
                    return response

                self._gemini_fail_streak += 1
                if self._gemini_fail_streak >= CIRCUIT_BREAKER_THRESHOLD:
                    self._gemini_circuit_open = True
                    self._gemini_circuit_until = now + CIRCUIT_BREAKER_COOLDOWN
                    print(f"[AI CHAT] 🔴 Tier 1 Circuit OPEN ({CIRCUIT_BREAKER_COOLDOWN // 3600}h) — {self._gemini_fail_streak}x fail")
                else:
                    print(f"[AI CHAT] ⚠️ Tier 1 Fail ({response}). Switching to Tier 2 (Groq)...")

            # If images present and Gemini failed, don't fallback — other tiers don't support vision
            if has_images:
                return "❌ Maaf, fitur gambar cuma didukung oleh Gemini. Coba lagi nanti ya!"

        # ── Tier 2: Groq (Backup) ──
        if self.groq_api_key:
            print("[AI CHAT] 🚀 [TIER 2] Trying Groq (Llama 3.3 70B)...")
            response, success = await self._call_groq(
                user_message, history, system_prompt, temperature
            )
            if success and response:
                if not history:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                print("[AI CHAT] ✅ Tier 2 Success (Groq)")
                return response
            print(f"[AI CHAT] ⚠️ Tier 2 Fail ({response}). Switching to Tier 3 (Mistral)...")

        # ── Tier 3: Mistral ──
        if self.mistral_api_key:
            print("[AI CHAT] 🚀 [TIER 3] Trying Mistral (open-mistral-nemo)...")
            response, success = await self._call_mistral(
                user_message, history, system_prompt, temperature
            )
            if success and response:
                if not history:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                print("[AI CHAT] ✅ Tier 3 Success (Mistral)")
                return response
            print(f"[AI CHAT] ⚠️ Tier 3 Fail ({response}). Switching to Tier 4 (Cohere)...")

        # ── Tier 4: Cohere ──
        if self.cohere_api_key:
            print("[AI CHAT] 🚀 [TIER 4] Trying Cohere (command-r-plus)...")
            response, success = await self._call_cohere(
                user_message, history, system_prompt, temperature
            )
            if success and response:
                if not history:
                    self._set_cached_response(user_message, system_prompt, temperature, response)
                print("[AI CHAT] ✅ Tier 4 Success (Cohere)")
                return response
            print(f"[AI CHAT] ❌ Tier 4 Fail ({response})")

        # ── All Tiers Failed ──
        if not self.google_api_key and not self.groq_api_key and not self.mistral_api_key and not self.cohere_api_key:
            return "❌ Tidak ada API key yang tersedia di environment (.env). Hubungi admin bot."

        if self._gemini_circuit_open and not self.groq_api_key and not self.mistral_api_key and not self.cohere_api_key:
            return (
                "⚠️ Kuota harian Google AI Studio lu udah habis dan tidak ada backup API tersedia.\n"
                "Tunggu beberapa jam lagi ya bro!"
            )

        return (
            "Waduh, semua mesin AI-nya lagi pusing nih, bro! 🧠💥\n"
            "Google AI Studio limit (circuit open), Groq juga down, Mistral dan Cohere error.\n"
            "Coba tunggu beberapa menit lagi baru chat gua ya!"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # RESPONSE HELPER
    # ═══════════════════════════════════════════════════════════════════════
    async def _send_response(self, ctx, user_id: str, text: str):
        """
        Mengirim balasan ke user. Setiap respons WAJIB diawali mention user
        (<@user_id>) supaya percakapan terasa personal.

        Mention disisipkan SEKALI di depan teks SEBELUM proses chunking,
        sehingga ia hanya muncul pada chunk pertama dan tidak ikut terpotong
        atau terduplikasi di chunk-chunk berikutnya saat pesan terlalu panjang.
        """
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
    # IMAGE EXTRACTION HELPER
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
    # CORE PROCESSOR
    # ═══════════════════════════════════════════════════════════════════════
    async def _process_ai_chat(self, ctx, user_message: str, guild: discord.Guild, user: discord.User, images: list[dict] | None = None):
        guild_id = str(guild.id)
        user_id = str(user.id)

        # ── [NEW] REVISI: Gatekeeper (Local Check) ──
        # Kita buat objek tiruan (Mock) agar SpamEngine bisa membaca data pesan
        class MockMsg:
            def __init__(self, content, author, guild):
                self.content = content
                self.author = author
                self.guild = guild
                self.mention_everyone = False 
        
        mock_msg = MockMsg(user_message, user, guild)

        # 1. Cek Heuristic (Keyword & Link) - LAPIS 1
        if self.engine.is_spam_heuristic(mock_msg):
            print(f"[AI MOD] 🚫 Spam terdeteksi via Heuristic dari user {user_id}")
            await self._send_response(ctx, user_id, "🚫 Pesan diblokir karena terdeteksi spam/link mencurigakan.")
            return

        # 2. Cek Akun Baru (Anti-Spammer Baru) - LAPIS 2
        if self.engine.is_new_account(mock_msg):
            print(f"[AI MOD] 🚫 User baru ({user_id}) diblokir.")
            await self._send_response(ctx, user_id, "🚫 Akun kamu terlalu baru untuk menggunakan fitur AI Chat.")
            return

        # ======================================================================
        # 🚨 [UPDATE OPTIMASI] DI-COMMENT BIAR GAK DOUBLE API CALL
        # Karena filter spam AI sudah di-handle terpusat di moderation.py
        # ======================================================================
        # # 3. Guard AI Detection - LAPIS 3 (Hanya jika lolos Lapis 1 & 2)
        # is_spam = await self.analyze_spam(user_message)
        # if is_spam:
        #     print(f"[AI MOD] 🚫 Pesan spam terdeteksi dari user {user_id} (guild {guild_id})")
        #     warning_text = (
        #         "🚫 Pesan kamu terdeteksi sebagai **spam/scam/iklan ilegal** dan "
        #         "tidak diproses oleh AI. Mohon gunakan fitur AI Chat dengan semestinya, ya!"
        #     )
        #     await self._send_response(ctx, user_id, warning_text)
        #     return
        # ======================================================================

        settings = await self._get_guild_ai_settings(guild_id)

        if not settings.get("enabled", False):
            await self._send_response(
                ctx, user_id, "⚠️ AI Chat sedang dimatikan oleh admin server. Hubungi admin untuk mengaktifkannya."
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
                ctx, user_id, "⚠️ AI Chat hanya bisa digunakan di channel yang sudah diatur oleh admin."
            )
            return

        personality = settings.get(
            "personality",
            DEFAULT_PERSONALITY
        )

        intent = detect_intent(user_message)

        print(
            f"[AI ROUTER] "
            f"guild={guild_id} "
            f"user={user_id} "
            f"intent={intent.value}"
        )

        temperature = settings.get(
            "temperature",
            0.75
        )
        history = await self._get_chat_history(guild_id, user_id)
        server_ctx = self._build_server_context(guild)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.replace("{personality}", personality).replace("{server_context}", server_ctx)

        # ── Typing indicator langsung membungkus pemanggilan API ──
        # Sengaja TIDAK dibungkus try-except tambahan: _call_ai sudah aman
        # (semua exception per-tier ditangkap di dalamnya dan tidak pernah
        # bubble up), jadi try-except ekstra di sini hanya akan menambah
        # risiko _call_ai terpanggil dua kali (boros kuota API) tanpa
        # benar-benar menyelamatkan typing indicator. Kalau typing_ctx.typing()
        # sendiri gagal (misal izin channel), error akan ditangani oleh
        # try-except di level pemanggil (/ask atau on_message).
        async with typing_ctx.typing():
            response_text = await self._call_ai(
                user_message,
                history,
                system_prompt,
                temperature,
                images
            )

        await self._save_chat_history(guild_id, user_id, user_message, response_text, personality)
        await self._send_response(ctx, user_id, response_text)

    # ═══════════════════════════════════════════════════════════════════════
    # BACKGROUND: History Pruning (setiap 6 jam)
    # ═══════════════════════════════════════════════════════════════════════

    @tasks.loop(hours=6)
    async def history_prune_loop(self):
        """Hapus history chat yg udah >30 hari gak ada interaksi."""
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
                            print(f"[AI PRUNE] 🗑️ Hapus history user {chat_doc.id} (guild {guild_id})")

            print("[AI PRUNE] ✅ Selesai prune history")
        except Exception as e:
            print(f"[AI PRUNE] ⚠️ Error: {e}")

    @history_prune_loop.before_loop
    async def before_history_prune(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="ask", description="Tanya apa saja ke AI Synapse")
    async def ask(self, ctx: commands.Context, pertanyaan: str, gambar: discord.Attachment | None = None):
        
        # 0. Cleanup stale cooldowns
        self._cleanup_cooldowns()

        # 1. Setup Data
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        now = datetime.now(timezone.utc).timestamp()

        # 2. Cooldown Check
        key = (guild_id, user_id)
        last_used = self._cooldowns.get(key, 0)
        if now - last_used < COOLDOWN_SECONDS:
            retry_after = COOLDOWN_SECONDS - (now - last_used)
            await ctx.send(
                f"⏳ Sabar bro! Tunggu **{retry_after:.1f} detik** lagi.", 
                ephemeral=True
            )
            return

        # 3. Defer
        await ctx.defer()

        # 4. Set Cooldown Setelah Lolos Defer
        self._cooldowns[key] = now

        # 5. Extract image if provided
        images = []
        if gambar:
            if gambar.content_type not in self._ALLOWED_IMAGE_TYPES:
                await ctx.send("❌ Tipe file gambar tidak didukung. Gunakan PNG, JPG, GIF, atau WEBP.")
                return
            if gambar.size > self._MAX_IMAGE_SIZE:
                await ctx.send("❌ Ukuran gambar terlalu besar (maks 4MB).")
                return
            try:
                data = await gambar.read()
                b64 = base64.b64encode(data).decode()
                images.append({"mime_type": gambar.content_type, "data": b64})
                print(f"[AI VISION] 📸 /ask with image ({gambar.content_type})")
            except Exception as e:
                print(f"[AI VISION] ⚠️ Gagal baca gambar: {e}")
                await ctx.send("❌ Gagal membaca gambar. Coba lagi ya!")
                return

        # 6. Proses AI Chat
        try:
            await self._process_ai_chat(
                ctx=ctx,
                user_message=pertanyaan,
                guild=ctx.guild,
                user=ctx.author,
                images=images or None,
            )
        except Exception as e:
            traceback.print_exc()
            print(f"[AI CHAT] ❌ Fatal error di /ask: {e}")
            try:    
                await ctx.send("❌ Terjadi error internal. Coba lagi nanti ya!")
            except Exception as e_followup:
                print(f"[AI CHAT] ❌ Gagal kirim error message: {e_followup}")

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT LISTENER: Mention @Synapse
    # ═══════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # 1. Cleanup memory (WAJIB)
        self._cleanup_cooldowns()

        # 2. Check Mention
        # Cara paling aman cek mention adalah dengan memeriksa list 'mentions'
        settings = await self._get_guild_ai_settings(
            str(message.guild.id)
        )

        # Hitung ulang untuk debug
        is_mentioned = self.bot.user in message.mentions

        is_dedicated_channel = self._is_dedicated_ai_channel(
            settings,
            str(message.channel.id)
        )

        # print("========== AI DEBUG ==========")
        # print(settings)
        # print(f"channel_id={message.channel.id}")
        # print(f"mentioned={is_mentioned}")
        # print(f"dedicated={is_dedicated_channel}")
        # print("==============================")

        # print("========== AI DEBUG ==========")
        # print(settings)
        # print(f"channel={message.channel.id}")
        # print("==============================")

        if not is_mentioned and not is_dedicated_channel:
            return

        if not settings.get("enabled", False):
            return

        if not self._is_channel_allowed(settings, str(message.channel.id)):
            return

        # 3. Clean content
        # Pakai regex yang match persis format mention Discord (<@id> atau <@!id>)
        # alih-alih clean_content.replace(display_name) yang rapuh — gagal kalau
        # display_name user diubah (nickname), mengandung karakter khusus, atau
        # bot punya nama tampilan yang juga muncul sebagai substring di teks user.
        if self._mention_pattern is None:
            self._mention_pattern = re.compile(rf"<@!?{self.bot.user.id}>")
        if is_mentioned:
            content = self._mention_pattern.sub(
                "",
                message.content
            ).strip()
        else:
            content = message.content.strip()

        if not content:
            await message.reply("Halo! Ada yang bisa kubantu? 🤖", mention_author=False)
            return

        # 4. Cooldown Check
        key = (str(message.guild.id), str(message.author.id))
        now = datetime.now(timezone.utc).timestamp()
        
        if now - self._cooldowns.get(key, 0) < COOLDOWN_SECONDS:
            return

        self._cooldowns[key] = now

        # 5. Extract images from attachments
        images = await self._extract_images_from_attachments(message.attachments)
        if images:
            print(f"[AI VISION] 📸 {len(images)} image(s) attached")

        try:
            await self._process_ai_chat(
                ctx=message,
                user_message=content,
                guild=message.guild,
                user=message.author,
                images=images,
            )
        except Exception as e:
            print(f"[AI CHAT] ❌ Fatal error di on_message: {e}")
            try:
                await message.reply("❌ Terjadi error internal. Coba lagi nanti ya!", mention_author=False)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
