import discord
from discord.ext import commands
import os
import aiohttp
import json
import time
from typing import Dict, List, Optional

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

        # --- KODE DEBUG SEMENTARA ---
        print("--- [DEBUG] STATUS KUNCI API ---")
        print(f"[*] Kunci Gemini API Ditemukan: {'Ya' if self.google_api_key else 'Tidak'}")
        print(f"[*] Kunci OpenRouter API Ditemukan: {'Ya' if self.openrouter_api_key else 'Tidak'}")
        print("---------------------------------")
        # --- AKHIR KODE DEBUG ---

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
        doc = await doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return {}

    async def _get_user_history(self, guild_id: int, user_id: int) -> List[Dict[str, str]]:
        history_ref = self.bot.db.collection('guild_settings').document(str(guild_id)).collection('ai_chat').document(str(user_id))
        doc = await history_ref.get()
        if doc.exists:
            return doc.to_dict().get('history', [])
        return []

    async def _save_user_history(self, guild_id: int, user_id: int, history: List[Dict[str, str]]):
        history_ref = self.bot.db.collection('guild_settings').document(str(guild_id)).collection('ai_chat').document(str(user_id))
        await history_ref.set({'history': history, 'updated_at': time.time()})

    async def _call_google_api(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        if not self.google_api_key:
            return None

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
                    return data['candidates'][0]['content']['parts'][0]['text']
                else:
                    print(f"[AI_CHAT_ERROR] Google API Error {response.status}: {await response.text()}")
                    return None
        except Exception as e:
            print(f"[AI_CHAT_ERROR] Exception during Google API call: {e}")
            return None

    async def _call_openrouter_api(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        if not self.openrouter_api_key:
            return None
            
        # Transform messages to OpenRouter format
        openrouter_messages = []
        for msg in messages:
            # OpenRouter expects "user" and "assistant" roles
            role = msg["role"]
            if role == "model":
                role = "assistant"
            openrouter_messages.append({"role": role, "content": msg["parts"][0]["text"]})


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
        
        # --- Cooldown Check ---
        now = time.time()
        cooldown_key = (guild_id, user_id)
        if cooldown_key in self._cooldowns and (now - self._cooldowns[cooldown_key]) < COOLDOWN_SECONDS:
            remaining = COOLDOWN_SECONDS - (now - self._cooldowns[cooldown_key])
            await interaction.followup.send(f"⏳ **Cooldown aktif.** Coba lagi dalam **{remaining:.1f} detik**.", ephemeral=True)
            return
        
        # Defer before any long operation
        await interaction.response.defer(ephemeral=False, thinking=True)
        self._cooldowns[cooldown_key] = now


        settings = await self._get_db_settings(guild_id)
        
        # --- AI enabled check ---
        if not settings.get('ai_chat_enabled', False):
            await interaction.followup.send("Fitur AI Chat sedang tidak aktif di server ini.", ephemeral=True)
            return

        # --- Channel restriction check ---
        allowed_channel = settings.get('ai_chat', {}).get('channel_id')
        if allowed_channel and str(interaction.channel.id) != allowed_channel:
            await interaction.followup.send(f"Perintah ini hanya bisa digunakan di <#{allowed_channel}>.", ephemeral=True)
            return

        # --- Build prompt & history ---
        temperature = settings.get('ai_chat', {}).get('temperature', 0.75)
        personality = settings.get('ai_chat', {}).get('personality', 'default') # In future, we can load this
        
        server_context_str = f"Nama Server: {interaction.guild.name}\nJumlah Member: {interaction.guild.member_count}"
        system_prompt = DEFAULT_PROMPT.format(server_context=server_context_str)

        history = await self._get_user_history(guild_id, user_id)
        
        # Format for Google API (contents)
        formatted_history = []
        # Add system prompt first
        # formatted_history.append({"role": "user", "parts": [{"text": system_prompt}]})
        # formatted_history.append({"role": "model", "parts": [{"text": "Oke, aku siap."}]})
        
        for message in history:
            role = message.get("role")
            content = message.get("content")
            if role and content:
                 # Gemini uses 'model' for assistant role
                formatted_history.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": content}]})

        formatted_history.append({"role": "user", "parts": [{"text": question}]})

        # --- Call API with Fallback ---
        response_text = await self._call_google_api(formatted_history, temperature)

        if response_text is None:
            # Fallback to OpenRouter
            print("[AI CHAT] Google API failed. Falling back to OpenRouter...")
            response_text = await self._call_openrouter_api(formatted_history, temperature)
        
        if response_text:
            # --- Update History ---
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": response_text})
            
            # Keep history to a max length
            if len(history) > MAX_HISTORY * 2:
                history = history[-(MAX_HISTORY * 2):]
                
            await self._save_user_history(guild_id, user_id, history)
            
            # Send response
            await interaction.followup.send(response_text)
        else:
            await interaction.followup.send("🚫 Maaf, terjadi kesalahan saat menghubungi AI. Kedua API (Google & OpenRouter) sepertinya sedang bermasalah. Coba lagi nanti.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        if self.bot.user.mentioned_in(message) and message.reference is None:
            # It's a direct mention, not a reply
            ctx = await self.bot.get_context(message)
            question = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            
            if not question:
                 await message.reply("Ada apa panggil-panggil? Kalau mau ngobrol, mention aku sambil kasih pertanyaan ya. Contoh: `@Hidden Hamlet ceritain dong soal server ini`")
                 return
            
            # Create a mock Interaction object
            interaction = await self.bot.get_context(message)
            interaction.user = message.author
            interaction.guild = message.guild
            interaction.channel = message.channel
            interaction.response = interaction
            interaction.followup = interaction

            # Mock the defer and send methods
            async def defer_mock(ephemeral=False, thinking=True):
                await message.channel.trigger_typing()

            async def send_mock(content, ephemeral=False):
                if not ephemeral:
                    await message.reply(content)
                else:
                    # Can't send true ephemeral here, so just send a normal message and delete it
                    m = await message.channel.send(f"{message.author.mention}, {content}")
                    await m.delete(delay=10)

            interaction.response.defer = defer_mock
            interaction.followup.send = send_mock
            
            await self._handle_chat_request(interaction, question)


    @commands.slash_command(name="ask", description="Tanya apa saja ke AI")
    async def ask(self, interaction: discord.Interaction, *, pertanyaan: str):
        await self._handle_chat_request(interaction, pertanyaan)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
