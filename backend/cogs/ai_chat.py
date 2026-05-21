"""
================================================================================
COG: AI Chat Module v4.1 — Hidden Hamlet Discord Bot
================================================================================
File        : backend/cogs/ai_chat.py
Deskripsi   : Integrasi Google Gemini AI dengan discord.py v2.x syntax.
              • Slash command pakai @app_commands.command()
              • Mention handler (@bot)
              • Channel restriction (bisa pilih channel via dashboard)
              • Anti-spam cooldown manual (5 detik/user)
              • Rate limit handling (429/ResourceExhausted)
              • Chat history Firestore (max 5 pasang, slice otomatis)
              • Smart server info (hanya channel PUBLIK)
Model       : gemini-2.0-flash (FREE tier)
================================================================================
"""

import os
import asyncio
import traceback
from datetime import datetime, timezone
from typing import List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

# ── Google Gemini ──
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, TooManyRequests

# ── Firebase ──
from .firebase_setup import db

# ── Konstanta ──
MAX_HISTORY_PAIRS = 5          # 5 Q&A = 10 pesan total di Firestore
COOLDOWN_SECONDS = 5           # Anti-spam per user
DEFAULT_PERSONALITY = "friendly"

# ── System Prompt Template ──
SYSTEM_PROMPT_TEMPLATE = """\
Kamu adalah AI Resmi dari bot Discord "Hidden Hamlet". 
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
    """
    Cog AI Chat — mengelola interaksi Gemini AI di Discord.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Manual cooldown storage: {(guild_id, user_id): timestamp}
        self._cooldowns: Dict[tuple, float] = {}

        # ── Inisialisasi Gemini ──
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("[AI CHAT] ⚠️ GEMINI_API_KEY tidak ditemukan di environment!")
        else:
            genai.configure(api_key=api_key)

        self.model_name = "gemini-2.0-flash"
        self.generation_config = genai.types.GenerationConfig(
            max_output_tokens=1024,
            temperature=0.75,
            top_p=0.95,
        )

        print(f"[AI CHAT] ✅ Cog loaded. Model: {self.model_name}")

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Ambil AI Chat settings dari Firestore
    # ═══════════════════════════════════════════════════════════════════════
    def _get_guild_ai_settings(self, guild_id: str) -> dict:
        """
        Ambil seluruh AI Chat settings untuk guild.
        Return: {enabled, channel_id, personality, temperature}
        """
        try:
            doc_ref = db.collection("guild_settings").document(str(guild_id))
            doc = doc_ref.get()
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

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Cek channel restriction
    # ═══════════════════════════════════════════════════════════════════════
    def _is_channel_allowed(self, guild_id: str, channel_id: str) -> bool:
        """
        Jika channel_id di settings kosong → izinkan SEMUA channel.
        Jika terisi → hanya izinkan di channel tersebut.
        """
        settings = self._get_guild_ai_settings(guild_id)
        allowed_channel = settings.get("channel_id", "")
        if not allowed_channel:
            return True
        return str(channel_id) == str(allowed_channel)

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Ambil chat history user dari Firestore
    # ═══════════════════════════════════════════════════════════════════════
    def _get_chat_history(self, guild_id: str, user_id: str) -> List[Dict[str, Any]]:
        try:
            doc_ref = (
                db.collection("guild_settings")
                .document(str(guild_id))
                .collection("ai_chat")
                .document(str(user_id))
            )
            doc = doc_ref.get()
            if not doc.exists:
                return []
            data = doc.to_dict()
            history = data.get("history", [])
            valid_history = []
            for item in history:
                if isinstance(item, dict) and "role" in item and "content" in item:
                    valid_history.append(item)
            return valid_history
        except Exception as e:
            print(f"[AI CHAT] ⚠️ Error ambil history: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Simpan chat history (slice jika >10, pakai merge=True)
    # ═══════════════════════════════════════════════════════════════════════
    def _save_chat_history(
        self,
        guild_id: str,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        personality: str = DEFAULT_PERSONALITY,
    ) -> None:
        try:
            old_history = self._get_chat_history(guild_id, user_id)
            now = datetime.now(timezone.utc).isoformat()
            new_history = old_history + [
                {"role": "user", "content": user_msg, "timestamp": now},
                {"role": "assistant", "content": assistant_msg, "timestamp": now},
            ]

            if len(new_history) > 10:
                new_history = new_history[-10:]

            doc_ref = (
                db.collection("guild_settings")
                .document(str(guild_id))
                .collection("ai_chat")
                .document(str(user_id))
            )
            doc_ref.set(
                {
                    "history": new_history,
                    "personality": personality,
                    "updated_at": datetime.now(timezone.utc),
                },
                merge=True,
            )
        except Exception as e:
            print(f"[AI CHAT] ⚠️ Error simpan history: {e}")
            traceback.print_exc()

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Bangun konteks server (hanya channel PUBLIK)
    # ═══════════════════════════════════════════════════════════════════════
    def _build_server_context(self, guild: discord.Guild) -> str:
        if not guild:
            return ""

        member_count = guild.member_count or len(guild.members)
        bot_count = sum(1 for m in guild.members if m.bot)

        public_text = [
            c for c in guild.text_channels
            if c.permissions_for(guild.default_role).view_channel
        ]
        public_voice = [
            c for c in guild.voice_channels
            if c.permissions_for(guild.default_role).view_channel
        ]

        owner = guild.owner.mention if guild.owner else "Unknown"

        return f"""\
[CONTEXT SERVER]
• Nama Server : {guild.name}
• ID Server   : {guild.id}
• Owner       : {owner}
• Total Member: {member_count} ({member_count - bot_count} manusia, {bot_count} bot)
• Text Channel Publik : {len(public_text)}
• Voice Channel Publik: {len(public_voice)}
• Boost Level         : {guild.premium_tier}
• Dibuat Pada         : {guild.created_at.strftime('%Y-%m-%d')}
"""

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Call Gemini API (async wrapper via to_thread)
    # ═══════════════════════════════════════════════════════════════════════
    async def _call_gemini(
        self,
        user_message: str,
        history: List[Dict[str, Any]],
        system_prompt: str,
    ) -> str:
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt,
                generation_config=self.generation_config,
            )

            gemini_history = []
            for item in history:
                role = item["role"]
                gemini_role = "model" if role == "assistant" else "user"
                gemini_history.append({"role": gemini_role, "parts": [item["content"]]})

            chat = model.start_chat(history=gemini_history)
            response = await asyncio.to_thread(chat.send_message, user_message)

            if response and response.text:
                return response.text.strip()
            return "Hmmm, aku blank sebentar... coba tanya lagi? 🤔"

        except (ResourceExhausted, TooManyRequests) as e:
            print(f"[AI CHAT] ⛔ Rate limit Google: {e}")
            return (
                "Waduh, kepala AI-ku lagi pusing nih! 🧠💥\n"
                "Rate limit dari Google-nya kena. Coba tanya lagi dalam beberapa menit ya, bro!"
            )

        except Exception as e:
            print(f"[AI CHAT] ❌ Error Gemini: {e}")
            traceback.print_exc()
            return "Aduh, ada error di otakku... coba lagi nanti ya! 🛠️"

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Kirim balasan (handle Interaction vs Message)
    # ═══════════════════════════════════════════════════════════════════════
    async def _send_response(self, ctx, text: str):
        """Kirim balasan sesuai tipe context (Interaction atau Message)."""
        if isinstance(ctx, discord.Interaction):
            # Slash command: pakai followup (karena sudah defer)
            if len(text) > 2000:
                chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
                await ctx.followup.send(chunks[0])
                for chunk in chunks[1:]:
                    await ctx.followup.send(chunk)
            else:
                await ctx.followup.send(text)
        else:
            # Mention: pakai reply
            if len(text) > 2000:
                chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        await ctx.reply(chunk, mention_author=False)
                    else:
                        await ctx.channel.send(chunk)
            else:
                await ctx.reply(text, mention_author=False)

    # ═══════════════════════════════════════════════════════════════════════
    # CORE: Proses pertanyaan (slash command & mention)
    # ═══════════════════════════════════════════════════════════════════════
    async def _process_ai_chat(self, ctx, user_message: str, guild: discord.Guild, user: discord.User):
        guild_id = str(guild.id)
        user_id = str(user.id)

        # ── 1. Cek apakah fitur aktif ──
        settings = self._get_guild_ai_settings(guild_id)
        if not settings.get("enabled", False):
            return

        # ── 2. Cek channel restriction ──
        channel_id = ""
        typing_ctx = None
        if isinstance(ctx, discord.Interaction):
            channel_id = str(ctx.channel_id)
            typing_ctx = ctx.channel
        else:
            channel_id = str(ctx.channel.id)
            typing_ctx = ctx.channel

        if not self._is_channel_allowed(guild_id, channel_id):
            return  # Silent ignore

        # ── 3. Ambil personality & history ──
        personality = settings.get("personality", DEFAULT_PERSONALITY)
        history = self._get_chat_history(guild_id, user_id)

        # ── 4. Bangun system prompt ──
        server_ctx = self._build_server_context(guild)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            personality=personality,
            server_context=server_ctx,
        )

        # ── 5. Panggil Gemini dengan typing indicator ──
        async with typing_ctx.typing():
            response_text = await self._call_gemini(
                user_message=user_message,
                history=history,
                system_prompt=system_prompt,
            )

        # ── 6. Simpan ke Firestore ──
        self._save_chat_history(
            guild_id=guild_id,
            user_id=user_id,
            user_msg=user_message,
            assistant_msg=response_text,
            personality=personality,
        )

        # ── 7. Kirim balasan ──
        await self._send_response(ctx, response_text)

    # ═══════════════════════════════════════════════════════════════════════
    # SLASH COMMAND: /ask (discord.py v2.x — pakai app_commands)
    # ═══════════════════════════════════════════════════════════════════════
    @app_commands.command(name="ask", description="Tanya apa saja ke AI Gemini Hidden Hamlet")
    @app_commands.describe(pertanyaan="Apa yang mau ditanyakan?")
    async def ask(self, interaction: discord.Interaction, pertanyaan: str):
        """
        Slash command /ask dengan manual cooldown (5 detik per user).
        """
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        now = datetime.now(timezone.utc).timestamp()

        # ── Manual Cooldown Check ──
        key = (guild_id, user_id)
        last_used = self._cooldowns.get(key, 0)
        if now - last_used < COOLDOWN_SECONDS:
            retry_after = COOLDOWN_SECONDS - (now - last_used)
            embed = discord.Embed(
                title="⏳ Cooldown",
                description=f"Sabar bro! Tunggu **{retry_after:.1f} detik** lagi sebelum tanya lagi.",
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self._cooldowns[key] = now

        # ── Defer & Process ──
        await interaction.response.defer(thinking=False)
        await self._process_ai_chat(
            ctx=interaction,
            user_message=pertanyaan,
            guild=interaction.guild,
            user=interaction.user,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT LISTENER: Mention @HiddenHamlet di text channel
    # ═══════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return

        # Cek mention
        bot_mentioned = (
            self.bot.user in message.mentions
            or self.bot.user.id in [m.id for m in message.mentions]
        )
        if not bot_mentioned:
            return

        # ── Cek channel restriction ──
        if not self._is_channel_allowed(str(message.guild.id), str(message.channel.id)):
            return  # Silent ignore

        # ── Extract text setelah mention ──
        content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(
            f"<@!{self.bot.user.id}>", ""
        ).strip()

        if not content:
            await message.reply(
                "Halo! Ada yang bisa kubantu? 🤖\n"
                "Tanya aku langsung atau pakai `/ask`",
                mention_author=False,
            )
            return

        # ── Manual Cooldown untuk mention ──
        key = (str(message.guild.id), str(message.author.id))
        now = datetime.now(timezone.utc).timestamp()
        last_used = self._cooldowns.get(key, 0)

        if now - last_used < COOLDOWN_SECONDS:
            return  # Silent cooldown

        self._cooldowns[key] = now

        # ── Process ──
        await self._process_ai_chat(
            ctx=message,
            user_message=content,
            guild=message.guild,
            user=message.author,
        )


# ═══════════════════════════════════════════════════════════════════════════
# SETUP: Async setup untuk discord.py v2.x
# ═══════════════════════════════════════════════════════════════════════════
async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))