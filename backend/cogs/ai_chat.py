import discord
from discord.ext import commands
from discord import app_commands
import os
import aiohttp
import json
import time
import asyncio  # <-- FIX: Ditambahkan
from typing import Dict, List, Optional, Tuple

# Constants
GOOGLE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_HISTORY = 5  # Simpan 5 Q&A (10 pesan)
COOLDOWN_SECONDS = 5

# --- DEFAULT PROMPT SYSTEM ---
DEFAULT_PROMPT = """
Anda adalah "Hidden Hamlet", bot Discord yang canggih dan serbaguna.

Identitas:
• Nama: Hidden Hamlet
• Developer: zeeinz-ux
• Model AI: Google Gemini 1.5 Flash (dengan fallback ke OpenRouter)

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

        print("--- [DEBUG] STATUS KUNCI API ---")
        print(f"[*] Kunci Gemini API Ditemukan: {'Ya' if self.google_api_key else 'Tidak'}")
        print(f"[*] Kunci OpenRouter API Ditemukan: {'Ya' if self.openrouter_api_key else 'Tidak'}")
        print("---------------------------------")

        self.session = aiohttp.ClientSession()
        print("[AI CHAT] ✅ Cog loaded. Dual API: Google + OpenRouter")

    async def cog_load(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
            print("[AI CHAT] ✅ HTTP session initialized")

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()
            print("[AI CHAT] ❌ HTTP session closed")

    async def _get_db_settings(self, guild_id: int) -> dict:
        doc_ref = self.bot.db.collection('guild_settings').document(str(guild_id))
        # FIX: Jalankan operasi sinkron di thread terpisah
        doc = await asyncio.to_thread(doc_ref.get)
        if doc.exists:
            return doc.to_dict()
        return {}

    async def _get_user_history(self, guild_id: int, user_id: int) -> List[Dict[str, str]]:
        history_ref = self.bot.db.collection('guild_settings').document(str(guild_id)).collection('ai_chat').document(str(user_id))
        # FIX: Jalankan operasi sinkron di thread terpisah
        doc = await asyncio.to_thread(history_ref.get)
        if doc.exists:
            return doc.to_dict().get('history', [])
        return []

    async def _save_user_history(self, guild_id: int, user_id: int, history: List[Dict[str, str]]):
        history_ref = self.bot.db.collection('guild_settings').document(str(guild_id)).collection('ai_chat').document(str(user_id))
        # FIX: Jalankan operasi sinkron di thread terpisah
        await asyncio.to_thread(history_ref.set, {'history': history, 'updated_at': time.time()})

    async def _call_google_api(self, messages: List[Dict[str, str]], temperature: float) -> Tuple[str, Optional[str]]:
        if not self.google_api_key:
            return ("FAILED", None)

        payload = {
            "contents": messages,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 1024,
            }
        }
        params = {"key": self.google_api_key}
        
        try:
            async with self.session.post(GOOGLE_API_URL, params=params, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return ("SUCCESS", data['candidates'][0]['content']['parts'][0]['text'])
                elif response.status == 429:
                    error_text = await response.text()
                    print(f"[AI_CHAT_WARNING] Google API rate limit hit (429): {error_text}")
                    return ("QUOTA_EXHAUSTED", None)
                else:
                    error_text = await response.text()
                    print(f"[AI_CHAT_ERROR] Google API Error {response.status}: {error_text}")
                    return ("FAILED", None)
        except Exception as e:
            print(f"[AI_CHAT_ERROR] Exception during Google API call: {e}")
            return ("FAILED", None)

    async def _call_openrouter_api(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        if not self.openrouter_api_key:
            print("[AI_CHAT_ERROR] Fallback ke OpenRouter gagal: OPENROUTER_API_KEY tidak diatur.")
            return None
            
        openrouter_messages = []
        for msg in messages:
            role = "assistant" if msg["role"] == "model" else msg["role"]
            content = msg["parts"][0]["text"]
            openrouter_messages.append({"role": role, "content": content})

        payload = {
            "model": "google/gemini-flash-1.5",
            "messages": openrouter_messages,
            "temperature": temperature
        }
        headers = {"Authorization": f"Bearer {self.openrouter_api_key}"}

        try:
            async with self.session.post(OPENROUTER_API_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                else:
                    print(f"[AI_CHAT_ERROR] OpenRouter API Error {response.status}: {await response.text()}")
                    return None
        except Exception as e:
            print(f"[AI_CHAT_ERROR] Exception during OpenRouter API call: {e}")
            return None

    async def _handle_chat_request(self, interaction: discord.Interaction, question: str):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        
        now = time.time()
        cooldown_key = (guild_id, user_id)
        if cooldown_key in self._cooldowns and (now - self._cooldowns[cooldown_key]) < COOLDOWN_SECONDS:
            remaining = COOLDOWN_SECONDS - (now - self._cooldowns[cooldown_key])
            await interaction.response.send_message(f"⏳ **Cooldown aktif.** Coba lagi dalam **{remaining:.1f} detik**.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=False, thinking=True)
        self._cooldowns[cooldown_key] = now

        settings = await self._get_db_settings(guild_id)
        
        # FIX: Kunci 'ai_chat_enabled' mungkin tidak ada, gunakan .get()
        ai_chat_settings = settings.get('ai_chat', {})
        if not ai_chat_settings.get('enabled', False):
            await interaction.followup.send("Fitur AI Chat sedang tidak aktif di server ini.", ephemeral=True)
            return

        allowed_channel = ai_chat_settings.get('channel_id')
        if allowed_channel and str(interaction.channel.id) != allowed_channel:
            await interaction.followup.send(f"Perintah ini hanya bisa digunakan di <#{allowed_channel}>.", ephemeral=True)
            return

        temperature = ai_chat_settings.get('temperature', 0.75)
        
        history = await self._get_user_history(guild_id, user_id)
        
        formatted_history = []
        for message in history:
            role = "model" if message.get("role") == "assistant" else "user"
            content = message.get("content")
            if role and content:
                 formatted_history.append({"role": role, "parts": [{"text": content}]})

        formatted_history.append({"role": "user", "parts": [{"text": question}]})

        # --- New Fallback Logic ---
        api_used = "Google"
        status, response_text = await self._call_google_api(formatted_history, temperature)

        if status != "SUCCESS":
            print(f"[AI CHAT] Google API failed ({status}). Falling back to OpenRouter...")
            response_text = await self._call_openrouter_api(formatted_history, temperature)
            api_used = "OpenRouter"

        if response_text:
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": response_text})
            
            if len(history) > MAX_HISTORY * 2:
                history = history[-(MAX_HISTORY * 2):]
                
            await self._save_user_history(guild_id, user_id, history)
            
            # Optionally add a footer to know which API was used
            final_message = f"{response_text}\n*— Ditenagai oleh {api_used}*"
            await interaction.followup.send(final_message)
        else:
            await interaction.followup.send("🚫 Waduh, semua AI lagi pusing nih. Google & OpenRouter sepertinya sedang tidak bisa dihubungi. Coba lagi beberapa saat ya!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        if self.bot.user.mentioned_in(message) and message.reference is None:
            ctx = await self.bot.get_context(message)
            question = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            
            if not question:
                 await message.reply("Ada apa panggil-panggil? Kalau mau ngobrol, mention aku sambil kasih pertanyaan ya. Contoh: `@Hidden Hamlet ceritain dong soal server ini`")
                 return
            
            async with message.channel.typing():
                guild_id = message.guild.id
                user_id = message.author.id
                
                now = time.time()
                cooldown_key = (guild_id, user_id)
                if cooldown_key in self._cooldowns and (now - self._cooldowns[cooldown_key]) < COOLDOWN_SECONDS:
                    remaining = COOLDOWN_SECONDS - (now - self._cooldowns[cooldown_key])
                    await message.reply(f"⏳ **Cooldown aktif.** Coba lagi dalam **{remaining:.1f} detik**.", delete_after=10)
                    return
                self._cooldowns[cooldown_key] = now

                settings = await self._get_db_settings(guild_id)
                ai_chat_settings = settings.get('ai_chat', {})
                if not ai_chat_settings.get('enabled', False):
                    return

                allowed_channel = ai_chat_settings.get('channel_id')
                if allowed_channel and str(message.channel.id) != allowed_channel:
                    return

                temperature = ai_chat_settings.get('temperature', 0.75)
D:\Project Gabut\my-discord-bot\discord-bot\backend>python main.py
[FIREBASE] 📁 Menggunakan file: D:\Project Gabut\my-discord-bot\discord-bot\backend\serviceAccountKey.json
[FIREBASE] ✅ Berhasil terhubung ke Firestore!
[FIREBASE] ℹ️ Firebase sudah di-init sebelumnya.
2026-05-22 13:02:29 INFO     discord.client logging in using static token
 * Serving Flask app 'backend.web.web_app'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:8080
 * Running on http://192.168.1.46:8080
Press CTRL+C to quit
[LAVALINK] ⏱️ Node 1 timeout: https://89.106.84.59:4000
An unexpected error occurred while connecting Node(identifier=rLB2AEHil1VqqwQi, uri=https://lavalink.jirayu.net:13592, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host lavalink.jirayu.net:13592 ssl:default [[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1077)]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
An unexpected error occurred while connecting Node(identifier=rLB2AEHil1VqqwQi, uri=https://lavalink.jirayu.net:13592, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host lavalink.jirayu.net:13592 ssl:default [[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1077)]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
An unexpected error occurred while connecting Node(identifier=rLB2AEHil1VqqwQi, uri=https://lavalink.jirayu.net:13592, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host lavalink.jirayu.net:13592 ssl:default [[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1077)]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
[LAVALINK] ⏱️ Node 2 timeout: https://lavalink.jirayu.net:13592
[LAVALINK] ⏱️ Node 3 timeout: https://lava.g3v.co.uk:9008
An unexpected error occurred while connecting Node(identifier=6e0klEAlFDyaJNZA, uri=https://sg1-nodelink.nyxbot.app:3000, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host sg1-nodelink.nyxbot.app:3000 ssl:default [None]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
An unexpected error occurred while connecting Node(identifier=6e0klEAlFDyaJNZA, uri=https://sg1-nodelink.nyxbot.app:3000, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host sg1-nodelink.nyxbot.app:3000 ssl:default [None]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
An unexpected error occurred while connecting Node(identifier=6e0klEAlFDyaJNZA, uri=https://sg1-nodelink.nyxbot.app:3000, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host sg1-nodelink.nyxbot.app:3000 ssl:default [None]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
An unexpected error occurred while connecting Node(identifier=6e0klEAlFDyaJNZA, uri=https://sg1-nodelink.nyxbot.app:3000, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host sg1-nodelink.nyxbot.app:3000 ssl:default [None]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
[LAVALINK] ⏱️ Node 4 timeout: https://sg1-nodelink.nyxbot.app:3000
An unexpected error occurred while connecting Node(identifier=g9sTMXoa5LoWp5Lt, uri=https://lavalink.triniumhost.com:4333, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host lavalink.triniumhost.com:4333 ssl:default [[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1077)]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
An unexpected error occurred while connecting Node(identifier=g9sTMXoa5LoWp5Lt, uri=https://lavalink.triniumhost.com:4333, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host lavalink.triniumhost.com:4333 ssl:default [[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1077)]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
An unexpected error occurred while connecting Node(identifier=g9sTMXoa5LoWp5Lt, uri=https://lavalink.triniumhost.com:4333, status=NodeStatus.CONNECTING, players=0) to Lavalink: "Cannot connect to host lavalink.triniumhost.com:4333 ssl:default [[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1077)]"
If this error persists or wavelink is unable to reconnect, please see: https://github.com/PythonistaGuild/Wavelink/issues
[LAVALINK] ⏱️ Node 5 timeout: https://lavalink.triniumhost.com:4333
[LAVALINK] ✅ Node 6 tersambung: https://lava-v4.ajieblogs.eu.org:443
2026-05-22 13:03:48 INFO     discord.gateway Shard ID None has connected to Gateway (Session ID: 750951ee5d83b74ce8374243c6500994).
==================================================
[STATUS] 🤖 Hidden Hamlet SEKARANG SUDAH ONLINE!
[STATUS] Terhubung ke 2 server Discord.
==================================================
[AI CHAT] ✅ Cog loaded. Dual API: Google + OpenRouter
[AI CHAT] ✅ HTTP session initialized
Unclosed client session
client_session: <aiohttp.client.ClientSession object at 0x0000023E5AF0C2F0>
[AI CHAT] ✅ HTTP session initialized
[COG] 📦 Loaded: ai_chat.py
[COG] 📦 Loaded: boost.py
[COG] 📦 Loaded: donation.py
[COG] 📦 Loaded: general.py
[SPOTIFY] SpotifyDown API resolver aktif (fallback: Official API)
[COG] 📦 Loaded: music.py
[WELCOME] ✅ WelcomeCog v3.7.6 — Cooldown: 30s
[COG] 📦 Loaded: welcome.py
[COG] ✅ Total 6 cogs loaded!
[SYNC] ✅ 27 slash command(s) berhasil di-sync!
  - /ask
  - /cekboost
  - /testboost
  - /donasi
  - /ping
  - /stats
  - /help
  - /play
  - /pause
  - /resume
  - /skip
  - /stop
  - /queue
  - /nowplaying
  - /volume
  - /loop
  - /shuffle
  - /autoplay
  - /seek
  - /remove
  - /move
  - /skipto
  - /disconnect
  - /clearqueue
  - /replay
  - /lyrics
  - /playlist
[LAVALINK] 🔄 Health check loop aktif (60s).
[DASHBOARD] 📊 Stats updater aktif (30s).
==================================================                history = await self._get_user_history(guild_id, user_id)
                
                formatted_history = []
                for h_msg in history:
                    role = "model" if h_msg.get("role") == "assistant" else "user"
                    formatted_history.append({"role": role, "parts": [{"text": h_msg.get("content")}]})
                formatted_history.append({"role": "user", "parts": [{"text": question}]})

                api_used = "Google"
                status, response_text = await self._call_google_api(formatted_history, temperature)

                if status != "SUCCESS":
                    response_text = await self._call_openrouter_api(formatted_history, temperature)
                    api_used = "OpenRouter"

                if response_text:
                    history.append({"role": "user", "content": question})
                    history.append({"role": "assistant", "content": response_text})
                    if len(history) > MAX_HISTORY * 2:
                        history = history[-(MAX_HISTORY * 2):]
                    await self._save_user_history(guild_id, user_id, history)
                    
                    final_message = f"{response_text}\n*— Ditenagai oleh {api_used}*"
                    await message.reply(final_message)
                else:
                    print("[AI CHAT] Both APIs failed for a mention request. Supressing error message.")

    @app_commands.command(name="ask", description="Tanya apa saja ke AI")
    @app_commands.describe(pertanyaan="Pertanyaan yang ingin kamu ajukan ke AI")
    async def ask(self, interaction: discord.Interaction, pertanyaan: str):
        await self._handle_chat_request(interaction, pertanyaan)


async def setup(bot: commands.Bot):
    cog = AIChat(bot)
    await bot.add_cog(cog)
