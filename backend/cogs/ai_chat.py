"""
================================================================================
COG: AI Chat Module v4.5 — Hidden Hamlet Discord Bot
================================================================================
File        : backend/cogs/ai_chat.py
Deskripsi   : Dual API support — Google AI Studio (Primary) + OpenRouter (Fallback)
              • Google: Native Gemini API via REST (aiohttp)
              • OpenRouter: Fallback kalau Google quota 0 / rate limit / model error
              • Auto-switch logic, tidak perlu restart bot
              • Slash command pakai @app_commands.command()
              • Mention handler (@bot)
              • Channel restriction via dashboard
              • Anti-spam cooldown manual (5 detik/user)
              • Chat history Firestore (max 5 pasang Q&A per user)
              • Temperature dari dashboard (0–1) diteruskan ke API
Models      : gemini-2.5-flash (Google) / google/gemini-2.5-flash:free (OpenRouter)
================================================================================
"""

import os
import asyncio
import traceback
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

import aiohttp

from .firebase_setup import db

# ── Konstanta ──
MAX_HISTORY_PAIRS = 5
COOLDOWN_SECONDS = 5
DEFAULT_PERSONALITY = "friendly"

# ── Google AI Studio Config ──
GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_MODEL = "gemini-2.5-flash"

# ── OpenRouter Config ──
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "google/gemini-2.5-flash:free"

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
        self._cooldowns: Dict[tuple, float] = {}

        # API Keys
        self.google_api_key = os.getenv("GEMINI_API_KEY", "")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")

        if not self.google_api_key:
            print("[AI CHAT] ⚠️ GEMINI_API_KEY tidak ditemukan!")
        if not self.openrouter_api_key:
            print("[AI CHAT] ⚠️ OPENROUTER_API_KEY tidak ditemukan!")

        self.session: aiohttp.ClientSession | None = None
        print("[AI CHAT] ✅ Cog loaded. Dual API: Google + OpenRouter")

    async def cog_load(self):
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        print("[AI CHAT] ✅ HTTP session initialized")

    async def cog_unload(self):
        if self.session:
            await self.session.close()
            print("[AI CHAT] ✅ HTTP session closed")

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
            traceback.print_exc()

    def _build_server_context(self, guild: discord.Guild) -> str:
        if not guild:
            return ""
        try:
            return f"""[CONTEXT SERVER]
• Nama Server : {guild.name}
• ID Server   : {guild.id}
• Total Member: {guild.member_count or 0}
• Boost Level : {guild.premium_tier}
• Dibuat Pada : {guild.created_at.strftime('%Y-%m-%d')}
"""
        except Exception:
            return ""

    # ═══════════════════════════════════════════════════════════════════════
    # API CALLERS
    # ═══════════════════════════════════════════════════════════════════════

    async def _call_google_gemini(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> tuple[str, bool]:
        """Call Google AI Studio. Return (response_text, success)."""
        if not self.google_api_key or not self.session:
            return "", False

        try:
            contents = []
            for item in history:
                role = "model" if item["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": item["content"]}]})
            contents.append({"role": "user", "parts": [{"text": user_message}]})

            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
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
                data = await resp.json()

                if status == 429:
                    error_msg = data.get("error", {}).get("message", "")
                    print(f"[AI CHAT] ⛔ Google Rate Limit: {error_msg[:200]}")
                    if "limit: 0" in error_msg or "Resource has been exhausted" in error_msg:
                        return "QUOTA_ZERO", False
                    return "", False

                if status == 400:
                    err_detail = data.get("error", data)
                    print(f"[AI CHAT] ❌ Google Bad Request (400): {err_detail}")
                    return "", False

                if status == 403:
                    err_detail = data.get("error", data)
                    print(f"[AI CHAT] ❌ Google Forbidden (403): {err_detail}")
                    return "", False

                if status == 404:
                    err_detail = data.get("error", data)
                    print(f"[AI CHAT] ❌ Google Not Found (404): Model '{GOOGLE_MODEL}' mungkin tidak tersedia. {err_detail}")
                    return "", False

                if status != 200:
                    print(f"[AI CHAT] ❌ Google HTTP {status}: {data}")
                    return "", False

                candidates = data.get("candidates", [])
                if not candidates:
                    return "", False

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    return "", False

                return parts[0].get("text", "").strip(), True

        except Exception as e:
            print(f"[AI CHAT] ❌ Google Error: {e}")
            return "", False

    async def _call_openrouter(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> tuple[str, bool]:
        """Call OpenRouter. Return (response_text, success)."""
        if not self.openrouter_api_key or not self.session:
            return "", False

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
                "HTTP-Referer": "https://my-discord-bot-gdew.onrender.com",
                "X-Title": "Hidden Hamlet Discord Bot",
            }

            url = f"{OPENROUTER_API_BASE}/chat/completions"

            async with self.session.post(url, headers=headers, json=payload) as resp:
                status = resp.status
                data = await resp.json()

                if status == 429:
                    print(f"[AI CHAT] ⛔ OpenRouter Rate Limit: {data}")
                    return "", False

                if status == 401:
                    print(f"[AI CHAT] ❌ OpenRouter Unauthorized (401): API key invalid")
                    return "", False

                if status == 404:
                    print(f"[AI CHAT] ❌ OpenRouter Not Found (404): Model '{OPENROUTER_MODEL}' tidak valid. {data}")
                    return "", False

                if status != 200:
                    print(f"[AI CHAT] ❌ OpenRouter HTTP {status}: {data}")
                    return "", False

                choices = data.get("choices", [])
                if not choices:
                    return "", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except Exception as e:
            print(f"[AI CHAT] ❌ OpenRouter Error: {e}")
            return "", False

    async def _call_gemini(
        self, user_message: str, history: List[Dict], system_prompt: str, temperature: float = 0.75
    ) -> str:
        """Dual API: Try Google first, fallback to OpenRouter."""

        # Try Google first
        if self.google_api_key:
            print("[AI CHAT] 🔄 Trying Google AI Studio...")
            response, success = await self._call_google_gemini(
                user_message, history, system_prompt, temperature
            )

            if success and response:
                print("[AI CHAT] ✅ Google success")
                return response

            if response == "QUOTA_ZERO":
                print("[AI CHAT] ⚠️ Google quota = 0, switching to OpenRouter...")
            else:
                print("[AI CHAT] ⚠️ Google failed, trying OpenRouter...")

        # Fallback to OpenRouter
        if self.openrouter_api_key:
            response, success = await self._call_openrouter(
                user_message, history, system_prompt, temperature
            )
            if success and response:
                print("[AI CHAT] ✅ OpenRouter success")
                return response

        # Both failed
        if not self.google_api_key and not self.openrouter_api_key:
            return "❌ Tidak ada API key yang tersedia. Hubungi admin bot."

        if not self.openrouter_api_key:
            return (
                "⚠️ Google AI quota habis (0).\n"
                "OpenRouter belum di-setup. Hubungi admin untuk tambah fallback API."
            )

        return (
            "Waduh, semua AI-nya lagi pusing nih! 🧠💥\n"
            "Google quota = 0, OpenRouter juga rate limit / model error.\n"
            "Coba tanya lagi dalam beberapa menit ya, bro!"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # RESPONSE HELPER
    # ═══════════════════════════════════════════════════════════════════════
    async def _send_response(self, ctx, text: str):
        if isinstance(ctx, discord.Interaction):
            if len(text) > 2000:
                chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
                await ctx.followup.send(chunks[0])
                for chunk in chunks[1:]:
                    await ctx.followup.send(chunk)
            else:
                await ctx.followup.send(text)
        else:
            if len(text) > 2000:
                chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        await ctx.reply(chunk, mention_author=False)
                    else:
                        await ctx.channel.send(chunk)
            else:
                await ctx.reply(text, mention_author=False)

    # ═══════════════════════════════════════════════════════════════════════
    # CORE PROCESSOR
    # ═══════════════════════════════════════════════════════════════════════
    async def _process_ai_chat(self, ctx, user_message: str, guild: discord.Guild, user: discord.User):
        guild_id = str(guild.id)
        user_id = str(user.id)

        settings = await self._get_guild_ai_settings(guild_id)
        if not settings.get("enabled", False):
            await self._send_response(ctx, "⚠️ AI Chat sedang dimatikan oleh admin server. Hubungi admin untuk mengaktifkannya.")
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
            await self._send_response(ctx, "⚠️ AI Chat hanya bisa digunakan di channel yang sudah diatur oleh admin.")
            return

        personality = settings.get("personality", DEFAULT_PERSONALITY)
        temperature = settings.get("temperature", 0.75)
        history = await self._get_chat_history(guild_id, user_id)
        server_ctx = self._build_server_context(guild)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(personality=personality, server_context=server_ctx)

        try:
            async with typing_ctx.typing():
                response_text = await self._call_gemini(user_message, history, system_prompt, temperature)
        except Exception as e:
            print(f"[AI CHAT] ⚠️ Typing error: {e}")
            response_text = await self._call_gemini(user_message, history, system_prompt, temperature)

        await self._save_chat_history(guild_id, user_id, user_message, response_text, personality)
        await self._send_response(ctx, response_text)

    # ═══════════════════════════════════════════════════════════════════════
    # SLASH COMMAND: /ask
    # ═══════════════════════════════════════════════════════════════════════
    @app_commands.command(name="ask", description="Tanya apa saja ke AI Gemini Hidden Hamlet")
    @app_commands.describe(pertanyaan="Apa yang mau ditanyakan?")
    async def ask(self, interaction: discord.Interaction, pertanyaan: str):
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        now = datetime.now(timezone.utc).timestamp()

        # DEFER FIRST — sebelum cooldown check!
        await interaction.response.defer(thinking=False)

        key = (guild_id, user_id)
        last_used = self._cooldowns.get(key, 0)
        if now - last_used < COOLDOWN_SECONDS:
            retry_after = COOLDOWN_SECONDS - (now - last_used)
            await interaction.followup.send(f"⏳ Sabar bro! Tunggu **{retry_after:.1f} detik** lagi.")
            return

        self._cooldowns[key] = now

        try:
            await self._process_ai_chat(
                ctx=interaction,
                user_message=pertanyaan,
                guild=interaction.guild,
                user=interaction.user,
            )
        except Exception as e:
            print(f"[AI CHAT] ❌ Fatal error di /ask: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send("❌ Terjadi error internal. Coba lagi nanti ya!")
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT LISTENER: Mention @HiddenHamlet
    # ═══════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return

        settings = await self._get_guild_ai_settings(str(message.guild.id))
        if not settings.get("enabled", False):
            return

        bot_mentioned = self.bot.user in message.mentions or self.bot.user.id in [m.id for m in message.mentions]
        if not bot_mentioned:
            return

        if not self._is_channel_allowed(settings, str(message.channel.id)):
            return

        content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()

        if not content:
            await message.reply(
                "Halo! Ada yang bisa kubantu? 🤖\nTanya aku langsung atau pakai `/ask`",
                mention_author=False,
            )
            return

        key = (str(message.guild.id), str(message.author.id))
        now = datetime.now(timezone.utc).timestamp()
        last_used = self._cooldowns.get(key, 0)

        if now - last_used < COOLDOWN_SECONDS:
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
            traceback.print_exc()
            try:
                await message.reply("❌ Terjadi error internal. Coba lagi nanti ya!", mention_author=False)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    cog = AIChat(bot)
    await bot.add_cog(cog)
    await cog.cog_load()
