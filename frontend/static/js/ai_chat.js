"""
================================================================================
COG: AI Chat Module v4.7 — Hidden Hamlet Discord Bot
================================================================================
File    : backend/cogs/ai_chat.py
Deskripsi : Triple API Fallback — Google AI Studio (T1) → Groq (T2) → OpenRouter (T3)
  • Tier 1: Google AI Studio — Primary (Gemini 3.5 Flash)
  • Tier 2: Groq — Backup (Llama 3.3 70B Versatile)
  • Tier 3: OpenRouter — Last Resort (Gemini 2.5 Flash Free)
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
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

import aiohttp
import tenacity

from ..database.firebase_setup import db
from ...utils.spam_engine import SpamEngine

# ── Konstanta ──
MAX_HISTORY_PAIRS = 5
COOLDOWN_SECONDS = 5
DEFAULT_PERSONALITY = "friendly"

# ── Tier 1: Google AI Studio ──
GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_MODEL = "gemini-3.5-flash"

# ── Tier 2: Groq ──
GROQ_API_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Tier 3: OpenRouter ──
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "google/gemini-2.5-flash:free"

# ── Circuit Breaker ──
CIRCUIT_BREAKER_THRESHOLD = 3       # fail streak sebelum circuit open
CIRCUIT_BREAKER_COOLDOWN = 7200     # 2 jam (detik)

# ── System Prompt Template ──
SYSTEM_PROMPT_TEMPLATE = """Kamu adalah AI Resmi dari bot Discord "Hidden Hamlet".
Personality saat ini: {personality}

Gaya bahasa:
• Default: Gaul, keren, santai, pakai Bahasa Indonesia kasual (lu-gue/kamu-aku sesuai konteks).
• Bisa berubah formal jika pertanyaan terdeteksi serius/teknikal.
• WAJIB merespons dalam bahasa yang sama dengan pertanyaan user (multilingual support).

Aturan:
• Jawab singkat, padat, relevan. Maksimal 4 kalimat kecuali diminta panjang.
• Jangan berikan informasi pribadi atau data sensitif.
• Jika ditanya hal terkait server, gunakan [CONTEXT SERVER] di bawah ini sebagai referensi UTAMA.

{server_context}
"""


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.engine = SpamEngine()
        self._cooldowns: Dict[tuple, float] = {}

        # API Keys
        self.google_api_key = os.getenv("GEMINI_API_KEY", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")

        # Circuit Breaker State (Tier 1: Gemini)
        self._gemini_circuit_open = False
        self._gemini_circuit_until = 0.0
        self._gemini_fail_streak = 0

        if not self.google_api_key:
            print("[AI CHAT] ⚠️ GEMINI_API_KEY tidak ditemukan!")
        if not self.groq_api_key:
            print("[AI CHAT] ⚠️ GROQ_API_KEY tidak ditemukan!")
        if not self.openrouter_api_key:
            print("[AI CHAT] ⚠️ OPENROUTER_API_KEY tidak ditemukan!")

        self.session: aiohttp.ClientSession | None = None

        # Cache compiled regex untuk strip mention bot di on_message
        # (di-build sekali saat dibutuhkan, lihat on_message)
        self._mention_pattern: "re.Pattern | None" = None

        print("[AI CHAT] ✅ Cog loaded. Triple API: Google → Groq → OpenRouter")

    async def cog_load(self):
        if self.session and not self.session.closed:
            return
      
        timeout = aiohttp.ClientTimeout(
            total=30,
            connect=10
        )
      
        self.session = aiohttp.ClientSession(
            timeout=timeout
        )
      
        print("[AI CHAT] ✅ HTTP session initialized")

    async def cog_unload(self):
        if self.session:
            await self.session.close()
            print("[AI CHAT] ✅ HTTP session closed")

    async def analyze_spam(self, content: str) -> bool:
        """
        Fungsi ringan untuk deteksi spam. 
        Mengembalikan True jika spam, False jika aman.
        """
        try:
            # Gunakan prompt singkat
            prompt = f"Analisis pesan berikut, apakah ini spam/scam/iklan judi? Jawab HANYA 'YA' atau 'TIDAK'. Pesan: {content}"
            
            # Panggil Master Engine (_call_ai)
            # Kita kirim history kosong [] dan system_prompt sederhana
            response = await self._call_ai(
                user_message=prompt, 
                history=[], 
                system_prompt="Anda adalah moderator konten bot yang bertugas mendeteksi spam secara tegas.",
                temperature=0.1 # Temperatur rendah agar jawaban konsisten
            )
            
            return "YA" in response.upper()
        except Exception as e:
            print(f"[AI MOD] Error saat cek spam: {e}")
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
                "personality": ai_chat.get("personality", DEFAULT_PERSONALITY),
                "temperature": ai_chat.get("temperature", 0.75),
            }
        except Exception as e:
            print(f"[AI CHAT] ⚠️ Error ambil settings: {e}")
            return {"enabled": False, "channel_id": ""}

    def _is_channel_allowed(self, settings: dict, channel_id: str) -> bool:
        allowed_channel = settings.get("channel_id", "")
        if not allowed_channel:
            return True
        return str(channel_id) == str(allowed_channel)

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
            await asyncio.to_thread(
                doc_ref.set,
                {"history": new_history, "personality": personality, "updated_at": datetime.now(timezone.utc)},
                merge=True,
            )
        except Exception as e:
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
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10), 
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_result(lambda res: res[1] is False)
    )
    async def _call_google_gemini(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> tuple[str, bool]:
        """Call Google AI Studio. Return (response_text, success)."""
        if not self.google_api_key or not self.session:
            return "API_KEY_MISSING", False

        try:
            contents = []
            for item in history:
                role = "model" if item["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": item["content"]}]})
            contents.append({"role": "user", "parts": [{"text": user_message}]})

            payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.95,
                "maxOutputTokens": 1024,
            },
        }

            url = f"{GOOGLE_API_BASE}/models/{GOOGLE_MODEL}:generateContent?key={self.google_api_key}"

            async with self.session.post(url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    err_msg = data.get("error", {}).get("message", "Rate limit or quota exhausted.")
                    print(f"[AI CHAT] ⛔ Google Rate Limit (429): {err_msg[:100]}")
                    return "RATE_LIMIT", False

                if status != 200:
                    print(f"[AI CHAT] ❌ Google HTTP {status}")
                    return f"HTTP_{status}", False

                candidates = data.get("candidates", [])
                if not candidates:
                    return "EMPTY_CANDIDATES", False

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    return "EMPTY_PARTS", False

                return parts[0].get("text", "").strip(), True

        except Exception as e:
            print(f"[AI CHAT] ❌ Google Exception: {type(e).__name__}")
            return "EXCEPTION", False

    # ═══════════════════════════════════════════════════════════════════════
    # TIER 2: Groq (Llama 3.3 70B)
    # ═══════════════════════════════════════════════════════════════════════

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10), 
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_result(lambda res: res[1] is False)
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
                "max_tokens": 1024,
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
    # TIER 3: OpenRouter
    # ═══════════════════════════════════════════════════════════════════════

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10), 
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_result(lambda res: res[1] is False)
    )
    async def _call_openrouter(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> tuple[str, bool]:
        """Call OpenRouter. Return (response_text, success)."""
        if not self.openrouter_api_key or not self.session:
            return "API_KEY_MISSING", False

        try:
            messages = [{"role": "system", "content": system_prompt}]
            for item in history:
                role = "assistant" if item["role"] == "assistant" else "user"
                messages.append({"role": role, "content": item["content"]})
            messages.append({"role": "user", "content": user_message})

            payload = {
                "model": OPENROUTER_MODEL,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 1024,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "HTTP-Referer": "https://my-discord-bot-my-discord-bot.up.railway.app/dashboard/1290376615439892591/ai-chat",
                "X-Title": "Hidden Hamlet Discord Bot",
            }

            url = f"{OPENROUTER_API_BASE}/chat/completions"

            async with self.session.post(url, headers=headers, json=payload) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    print("[AI CHAT] ⛔ OpenRouter Rate Limit (429)")
                    return "RATE_LIMIT", False

                if status != 200:
                    print(f"[AI CHAT] ❌ OpenRouter HTTP {status}")
                    return f"HTTP_{status}", False

                choices = data.get("choices", [])
                if not choices:
                    return "EMPTY_CHOICES", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except Exception as e:
            print(f"[AI CHAT] ❌ OpenRouter Exception: {type(e).__name__}")
            return "EXCEPTION", False
        
    # ═══════════════════════════════════════════════════════════════════════
    # MASTER FALLBACK ENGINE (Triple Tier)
    # ═══════════════════════════════════════════════════════════════════════

    async def _call_ai(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> str:
        """Triple API Fallback Engine with Lightweight Circuit Breaker."""

        now = datetime.now(timezone.utc).timestamp()

        # ── Tier 1: Google AI Studio (Primary) ──
        if self.google_api_key:
            # Circuit breaker check
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
                    user_message, history, system_prompt, temperature
                )
                if success and response:
                    self._gemini_fail_streak = 0
                    print("[AI CHAT] ✅ Tier 1 Success (Gemini)")
                    return response

                # Gemini failed — increment streak & check circuit breaker
                self._gemini_fail_streak += 1
                if self._gemini_fail_streak >= CIRCUIT_BREAKER_THRESHOLD:
                    self._gemini_circuit_open = True
                    self._gemini_circuit_until = now + CIRCUIT_BREAKER_COOLDOWN
                    print(f"[AI CHAT] 🔴 Tier 1 Circuit OPEN ({CIRCUIT_BREAKER_COOLDOWN // 3600}h) — {self._gemini_fail_streak}x fail")
                else:
                    print(f"[AI CHAT] ⚠️ Tier 1 Fail ({response}). Switching to Tier 2 (Groq)...")

        # ── Tier 2: Groq (Backup) ──
        if self.groq_api_key:
            print("[AI CHAT] 🚀 [TIER 2] Trying Groq (Llama 3.3 70B)...")
            response, success = await self._call_groq(
                user_message, history, system_prompt, temperature
            )
            if success and response:
                print("[AI CHAT] ✅ Tier 2 Success (Groq)")
                return response
            print(f"[AI CHAT] ⚠️ Tier 2 Fail ({response}). Switching to Tier 3 (OpenRouter)...")

        # ── Tier 3: OpenRouter (Last Resort) ──
        if self.openrouter_api_key:
            print("[AI CHAT] 🌐 [TIER 3] Trying OpenRouter...")
            response, success = await self._call_openrouter(
                user_message, history, system_prompt, temperature
            )
            if success and response:
                print("[AI CHAT] ✅ Tier 3 Success (OpenRouter)")
                return response
            print(f"[AI CHAT] ❌ Tier 3 Fail ({response})")

        # ── All Tiers Failed ──
        if not self.google_api_key and not self.groq_api_key and not self.openrouter_api_key:
            return "❌ Tidak ada API key yang tersedia di environment (.env). Hubungi admin bot."

        if self._gemini_circuit_open and not self.groq_api_key and not self.openrouter_api_key:
            return (
                "⚠️ Kuota harian Google AI Studio lu udah habis dan tidak ada backup API tersedia.\n"
                "Tunggu beberapa jam lagi ya bro!"
            )

        return (
            "Waduh, semua mesin AI-nya lagi pusing nih, bro! 🧠💥\n"
            "Google AI Studio limit (circuit open), Groq juga down, dan OpenRouter ikut error.\n"
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
    # CORE PROCESSOR
    # ═══════════════════════════════════════════════════════════════════════
    async def _process_ai_chat(self, ctx, user_message: str, guild: discord.Guild, user: discord.User):
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

        personality = settings.get("personality", DEFAULT_PERSONALITY)
        temperature = settings.get("temperature", 0.75)
        history = await self._get_chat_history(guild_id, user_id)
        server_ctx = self._build_server_context(guild)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(personality=personality, server_context=server_ctx)

        # ── Typing indicator langsung membungkus pemanggilan API ──
        # Sengaja TIDAK dibungkus try-except tambahan: _call_ai sudah aman
        # (semua exception per-tier ditangkap di dalamnya dan tidak pernah
        # bubble up), jadi try-except ekstra di sini hanya akan menambah
        # risiko _call_ai terpanggil dua kali (boros kuota API) tanpa
        # benar-benar menyelamatkan typing indicator. Kalau typing_ctx.typing()
        # sendiri gagal (misal izin channel), error akan ditangani oleh
        # try-except di level pemanggil (/ask atau on_message).
        async with typing_ctx.typing():
            response_text = await self._call_ai(user_message, history, system_prompt, temperature)

        await self._save_chat_history(guild_id, user_id, user_message, response_text, personality)
        await self._send_response(ctx, user_id, response_text)

    @app_commands.command(name="ask", description="Tanya apa saja ke AI Hidden Hamlet")
    @app_commands.describe(pertanyaan="Apa yang mau ditanyakan?")
    async def ask(self, interaction: discord.Interaction, pertanyaan: str):
        
        # 1. Setup Data
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        now = datetime.now(timezone.utc).timestamp()

        # 2. Cooldown Check
        key = (guild_id, user_id)
        last_used = self._cooldowns.get(key, 0)
        if now - last_used < COOLDOWN_SECONDS:
            retry_after = COOLDOWN_SECONDS - (now - last_used)
            await interaction.response.send_message(
                f"⏳ Sabar bro! Tunggu **{retry_after:.1f} detik** lagi.", 
                ephemeral=True
            )
            return

        # 3. Fast Defer (Panggil helper yang sudah kita buat)
        # Fungsi ini akan menangani defer dan error handling 429 secara terpusat
        await self._defer_interaction(interaction)

        # 4. Set Cooldown Setelah Lolos Defer
        self._cooldowns[key] = now

        # 5. Proses AI Chat
        try:
            await self._process_ai_chat(
                ctx=interaction,
                user_message=pertanyaan,
                guild=interaction.guild,
                user=interaction.user,
            )
        except Exception as e:
            print(f"[AI CHAT] ❌ Fatal error di /ask: {e}")
            # Karena sudah di-defer, kita pakai followup untuk kirim pesan error
            try:    
                await interaction.followup.send("❌ Terjadi error internal. Coba lagi nanti ya!")
            except Exception as e_followup:
                print(f"[AI CHAT] ❌ Gagal kirim error message: {e_followup}")

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT LISTENER: Mention @HiddenHamlet
    # ═══════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # 1. Cleanup memory (WAJIB)
        self._cleanup_cooldowns()

        # 2. Check Mention
        # Cara paling aman cek mention adalah dengan memeriksa list 'mentions'
        if self.bot.user not in message.mentions:
            return

        settings = await self._get_guild_ai_settings(str(message.guild.id))
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
        content = self._mention_pattern.sub("", message.content).strip()

        if not content:
            await message.reply("Halo! Ada yang bisa kubantu? 🤖", mention_author=False)
            return

        # 4. Cooldown Check
        key = (str(message.guild.id), str(message.author.id))
        now = datetime.now(timezone.utc).timestamp()
        
        if now - self._cooldowns.get(key, 0) < COOLDOWN_SECONDS:
            return

        self._cooldowns[key] = now

        try:
            await self._process_ai_chat(
                ctx=message,
                user_message=content,
                guild=message.guild,
                user=message.author,
            )
        except Exception as e:
            print(f"[AI CHAT] ❌ Fatal error di on_message: {e}")
            try:
                await message.reply("❌ Terjadi error internal. Coba lagi nanti ya!", mention_author=False)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
