from __future__ import annotations

import asyncio, os, json, re, time as time_module
from typing import List

import discord
from discord.ext import commands

from ..database.firebase_setup import db
from .agent_tools import (
    TOOL_DEFINITIONS, TOOL_DESCRIPTION, DISCORD_PERMISSIONS_KNOWLEDGE,
    parse_tool_call, execute_tool,
)

MAX_AGENT_STEPS = 15
AGENT_TIMEOUT = 120


class AIChatAgent(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_sessions: set[int] = set()
        self._agent_channels: dict[int, float] = {}  # channel_id -> timestamp

    def _is_recent_agent_channel(self, channel_id: int) -> bool:
        ts = self._agent_channels.get(channel_id)
        if ts and time_module.time() - ts < 120:
            return True
        return False

    # ── Settings ──

    async def _get_agent_config(self, guild_id: str) -> dict:
        try:
            doc = await asyncio.to_thread(
                lambda: db.collection("guild_settings").document(str(guild_id)).get()
            )
            if not doc.exists:
                return {"agent_enabled": False, "agent_mode": "admin"}
            data = doc.to_dict()
            agent = data.get("agent", {}) if isinstance(data.get("agent"), dict) else {}
            return {
                "agent_enabled": agent.get("enabled", False),
                "agent_mode": agent.get("mode", "admin"),
            }
        except Exception as e:
            print(f"[AGENT] Error load config: {e}")
            return {"agent_enabled": False, "agent_mode": "admin"}

    async def _save_agent_config(self, guild_id: str, config: dict):
        try:
            payload = {
                "enabled": config.get("agent_enabled", False),
                "mode": config.get("agent_mode", "admin"),
            }
            await asyncio.to_thread(
                lambda: db.collection("guild_settings").document(str(guild_id)).set(
                    {"agent": payload}, merge=True
                )
            )
        except Exception as e:
            print(f"[AGENT] Error save config: {e}")

    # ── Permission check ──

    def _can_use_agent(self, member: discord.Member, config: dict) -> bool:
        if member == member.guild.owner:
            return True
        mode = config.get("agent_mode", "admin")
        if mode == "owner":
            return False
        return member.guild_permissions.administrator

    # ── Get AI Provider ──

    def _get_provider(self):
        ai = self.bot.get_cog("AIChat")
        if not ai:
            return None, None
        for p in ai._providers:
            if not p or not p.is_available:
                continue
            # Skip Gemini jika circuit breaker open / quota habis
            if p.name == "Gemini" and hasattr(p, "can_use_for_text") and not p.can_use_for_text():
                continue
            return ai, p
        # Fallback: coba Gemini walau quota/circuit lagi masalah
        for p in ai._providers:
            if p and p.is_available:
                return ai, p
        return ai, None

    def _get_next_provider(self, ai_cog, current_provider):
        if not ai_cog or not current_provider:
            return None
        found_current = False
        for p in ai_cog._providers:
            if not p:
                continue
            if not found_current:
                if p is current_provider:
                    found_current = True
                continue
            if p.is_available:
                if p.name == "Gemini" and hasattr(p, "can_use_for_text") and not p.can_use_for_text():
                    continue
                return p
        return None

    # ── ReAct Loop ──

    async def _agent_react(
        self,
        guild: discord.Guild,
        user_message: str,
        author: discord.Member,
    ) -> str:
        ai_cog, provider = self._get_provider()
        if not provider:
            return "Tidak ada provider AI yang tersedia saat ini."
        if not ai_cog:
            return "Sistem AI tidak tersedia."

        tools_json = json.dumps(TOOL_DEFINITIONS, indent=2)
        system_prompt = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Berikut adalah tool yang tersedia:\n{tools_json}\n\n"
            f"{DISCORD_PERMISSIONS_KNOWLEDGE}\n\n"
            f"Server ini: {guild.name} (ID: {guild.id})\n"
            f"Owner: {guild.owner}\n"
            f"Kamu adalah AI Agent profesional yang paham seluruh struktur Discord server.\n"
            f"Gunakan pengetahuan permission di atas untuk memberikan saran terbaik ke user.\n"
            f"Ikuti aturan dengan ketat."
        )

        # History untuk dikirim ke provider (tanpa system prompt)
        history: list[dict] = []
        # Pesan user saat ini
        current_message = user_message
        step_count = 0
        conversation = []

        while step_count < MAX_AGENT_STEPS:
            step_count += 1

            response, success = await provider.call(
                user_message=current_message,
                history=history,
                system_prompt=system_prompt,
                temperature=0.3,
            )

            if not success or not response:
                print(f"[AGENT] Provider {provider.name} failed: success={success}, response='{response}'")
                # Fallback ke provider berikutnya
                next_provider = self._get_next_provider(ai_cog, provider)
                if next_provider and step_count == 1:
                    print(f"[AGENT] Fallback ke {next_provider.name}")
                    provider = next_provider
                    step_count -= 1
                    continue
                if conversation:
                    final = "\n\n".join(t for _, t in conversation)
                    return f"{final}\n\n---\nMaaf, terjadi error di langkah {step_count}. Coba lagi dengan permintaan yang lebih sederhana."
                return "Maaf, terjadi error saat memproses permintaan. Coba lagi nanti."

            tool_calls = parse_tool_call(response)
            if not tool_calls:
                conversation.append(("AI", response))
                break

            for tc in tool_calls:
                fn_name = tc.get("function", "unknown")
                conversation.append(("TOOL_CALL", f"Memanggil {fn_name}..."))

                result = await execute_tool(guild, tc, self.bot)
                conversation.append(("TOOL_RESULT", result[:500]))

                # Simpan interaksi ke history untuk konteks berikutnya
                history.append({"role": "user", "content": current_message})
                history.append({"role": "assistant", "content": response})
                # Hasil tool dikirim sebagai user message berikutnya (truncated biar gak overload context)
                truncated = result[:1500]
                if len(result) > 1500:
                    truncated += "\n\n...(dipotong, total terlalu panjang)"
                current_message = f"Hasil eksekusi {fn_name}:\n{truncated}\n\nLanjutkan atau berikan respon ke user."

                await asyncio.sleep(0.3)

        if step_count >= MAX_AGENT_STEPS:
            conversation.append(("AI", "Saya sudah mencapai batas maksimum langkah. Berikut ringkasan apa yang sudah dilakukan."))

        final_text = [t for speaker, t in conversation if speaker == "AI"]
        return "\n\n".join(final_text) if final_text else response

    # ── Slash Commands ──

    @commands.hybrid_command(
        name="agent",
        description="AI Agent untuk bantu manage server. Khusus owner/admin.",
    )
    async def agent(self, ctx: commands.Context, *, request: str):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        if not config.get("agent_enabled", False):
            await ctx.send(
                "⚠️ **AI Agent belum diaktifkan** di server ini.\n"
                "Minta owner untuk mengaktifkannya lewat dashboard atau `/agent-toggle`.",
                ephemeral=True,
            )
            return

        if not self._can_use_agent(ctx.author, config):
            await ctx.send(
                "❌ **Tidak punya akses.**\n"
                "AI Agent hanya bisa digunakan oleh **Owner Server** "
                + ("dan Admin." if config.get("agent_mode") == "admin" else "."),
                ephemeral=True,
            )
            return

        if ctx.author.id in self._active_sessions:
            await ctx.send(
                "⏳ Kamu masih punya sesi agent yang berjalan. Tunggu sampai selesai.",
                ephemeral=True,
            )
            return

        defer_msg = await ctx.defer(ephemeral=False)

        self._active_sessions.add(ctx.author.id)
        try:
            result = await asyncio.wait_for(
                self._agent_react(ctx.guild, request, ctx.author),
                timeout=AGENT_TIMEOUT,
            )
            self._agent_channels[ctx.channel.id] = time_module.time()
            if len(result) > 1900:
                chunks = [result[i:i+1900] for i in range(0, len(result), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await ctx.send(f"🤖 **AI Agent — {ctx.author.display_name}**\n\n{chunk}")
                    else:
                        await ctx.send(chunk)
            else:
                await ctx.send(f"🤖 **AI Agent — {ctx.author.display_name}**\n\n{result}")
        except asyncio.TimeoutError:
            await ctx.send("⏰ **Waktu habis.** Agent butuh waktu terlalu lama. Coba dengan permintaan yang lebih sederhana.")
        except Exception as e:
            await ctx.send(f"❌ **Error:** {type(e).__name__}: {str(e)[:500]}")
        finally:
            self._active_sessions.discard(ctx.author.id)

    @commands.hybrid_command(
        name="agent-toggle",
        description="Aktifkan/nonaktifkan AI Agent di server ini. Khusus owner/admin.",
    )
    async def agent_toggle(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        if not ctx.author.guild_permissions.administrator and ctx.author != ctx.guild.owner:
            await ctx.send("❌ Hanya owner dan admin yang bisa menggunakan ini.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        config["agent_enabled"] = not config.get("agent_enabled", False)
        await self._save_agent_config(str(ctx.guild.id), config)

        status = "✅ **Diaktifkan**" if config["agent_enabled"] else "❌ **Dinonaktifkan**"
        mode = f"Mode: {'Owner + Admin' if config.get('agent_mode') == 'admin' else 'Owner Only'}"
        await ctx.send(f"{status}\n{mode}\nGunakan `/agent-mode` untuk mengubah siapa yang bisa akses.", ephemeral=True)

    @commands.hybrid_command(
        name="agent-mode",
        description="Ubah mode akses AI Agent: owner-only atau admin+owner.",
    )
    async def agent_mode(self, ctx: commands.Context, mode: str = "admin"):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        if ctx.author != ctx.guild.owner:
            await ctx.send("❌ Hanya **Owner Server** yang bisa mengubah mode akses ini.", ephemeral=True)
            return

        mode = mode.lower()
        if mode not in ("owner", "admin"):
            await ctx.send("Mode harus `owner` atau `admin`.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        config["agent_mode"] = mode
        await self._save_agent_config(str(ctx.guild.id), config)

        desc = "Hanya Owner Server" if mode == "owner" else "Owner + Admin"
        await ctx.send(f"✅ Mode akses AI Agent diubah ke: **{desc}**", ephemeral=True)

    @commands.hybrid_command(
        name="agent-status",
        description="Cek status AI Agent di server ini.",
    )
    async def agent_status(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        enabled = config.get("agent_enabled", False)
        mode = config.get("agent_mode", "admin")
        can_use = self._can_use_agent(ctx.author, config)

        embed = discord.Embed(
            title="🤖 AI Agent Status",
            color=discord.Color.green() if enabled else discord.Color.red(),
        )
        embed.add_field(name="Status", value="✅ Aktif" if enabled else "❌ Nonaktif", inline=False)
        embed.add_field(name="Mode Akses", value="Owner + Admin" if mode == "admin" else "Owner Only", inline=False)
        embed.add_field(name="Akses Kamu", value="✅ Bisa menggunakan" if can_use else "❌ Tidak bisa", inline=False)

        ai = self.bot.get_cog("AIChat")
        if ai:
            provider_names = [p.name for p in ai._providers if p and p.is_available]
            embed.add_field(name="Provider Tersedia", value=", ".join(provider_names) or "Tidak ada", inline=False)

        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChatAgent(bot))
