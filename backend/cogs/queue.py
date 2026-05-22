"""
Hidden Hamlet v4.6 — Queue Cog
================================
Tugas: Queue manipulation commands + bridge ke dashboard.
Dipasang: backend/cogs/queue.py
"""

import discord
from discord.ext import commands, tasks
import wavelink
import asyncio

from backend.utils.formatters import format_duration

_web_app = None


def _get_web_app():
    global _web_app
    if _web_app is None:
        try:
            from backend.web.web_app import pop_music_commands
            _web_app = {"pop_music_commands": pop_music_commands}
        except Exception as e:
            print(f"[QUEUE_COG] ⚠️ Web app import failed: {e}")
    return _web_app


class QueueManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._music_cog = None
        print("[QUEUE_COG] Cog loaded.")

    async def cog_load(self):
        await asyncio.sleep(1)
        self._music_cog = self.bot.get_cog("Music")
        if self._music_cog:
            print("[QUEUE_COG] ✅ Linked with Music Cog.")

    # ==========================================================
    # TASK: Command Consumer (fallback kalau now_playing.py tidak aktif)
    # ==========================================================
    @tasks.loop(seconds=2)
    async def command_consumer(self):
        wa = _get_web_app()
        if not wa:
            return
        cmds = wa["pop_music_commands"](max_n=10)
        for cmd in cmds:
            scope = cmd.get("scope")
            if scope == "queue":
                try:
                    await self._execute_queue_cmd(cmd)
                except Exception as e:
                    print(f"[QUEUE_COG] ❌ Queue cmd error: {e}")

    @command_consumer.before_loop
    async def before_consumer(self):
        await self.bot.wait_until_ready()

    async def _execute_queue_cmd(self, cmd: dict):
        payload = cmd.get("payload", {})
        guild_id = int(payload.get("guild_id", 0))
        action = payload.get("action")
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        player: wavelink.Player = guild.voice_client
        if not player:
            return

        if action == "add":
            query = payload.get("query", "")
            if not query:
                return
            search_q = query if query.startswith("http") else f"ytsearch:{query}"
            try:
                results = await wavelink.Playable.search(search_q)
                if results:
                    await player.queue.put_wait(results[0])
                    if not player.current:
                        await player.set_volume(100)
                        await asyncio.sleep(0.3)
                        await player.play(player.queue.get())
            except Exception as e:
                print(f"[QUEUE_COG] Add error: {e}")

        elif action == "remove":
            idx = payload.get("index", 0)
            if player.queue.is_empty:
                return
            items = list(player.queue)
            if 0 <= idx < len(items):
                items.pop(idx)
                player.queue.clear()
                for item in items:
                    await player.queue.put_wait(item)

        elif action == "move_top":
            idx = payload.get("index", 0)
            if player.queue.is_empty:
                return
            items = list(player.queue)
            if 0 < idx < len(items):
                track = items.pop(idx)
                items.insert(0, track)
                player.queue.clear()
                for item in items:
                    await player.queue.put_wait(item)

        elif action == "clear":
            player.queue.clear()
            if self._music_cog:
                mp = self._music_cog.get_player(guild_id)
                if mp:
                    mp._queue_history.clear()

        elif action == "shuffle":
            if not player.queue.is_empty:
                items = list(player.queue)
                import random
                random.shuffle(items)
                player.queue.clear()
                for item in items:
                    await player.queue.put_wait(item)
                if self._music_cog:
                    mp = self._music_cog.get_player(guild_id)
                    if mp:
                        mp._queue_history.clear()

    # ==========================================================
    # SLASH COMMANDS
    # ==========================================================
    @app_commands.command(name="queue", description="Lihat antrian lagu")
    async def queue_cmd(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return

        mp = self._music_cog.get_player(interaction.guild_id) if self._music_cog else None
        embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.purple())

        if player.current:
            loop_emoji = {"single": "🔁", "queue": "🔂", "off": ""}.get(mp.loop_mode if mp else "off", "")
            embed.add_field(
                name=f"▶️ Now Playing {loop_emoji}",
                value=f"**{player.current.title}**\n`{format_duration(player.current.length)}`",
                inline=False,
            )

        items = list(player.queue)
        if items:
            total_ms = sum(t.length or 0 for t in items)
            queue_text = ""
            for i, track in enumerate(items[:15], 1):
                duration = format_duration(track.length) if track.length else "?"
                queue_text += f"`{i:02d}.` {track.title[:40]}{'...' if len(track.title) > 40 else ''} (`{duration}`)\n"
            embed.add_field(name="⏭️ Up Next", value=queue_text or "...", inline=False)
            embed.set_footer(text=f"{len(items)} lagu | Total durasi: {format_duration(total_ms)}")
        else:
            embed.set_footer(text="Queue kosong — tambah lagu dengan /play")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove", description="Hapus lagu dari queue berdasarkan nomor")
    @app_commands.describe(index="Nomor lagu di /queue")
    async def remove_cmd(self, interaction: discord.Interaction, index: int):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return
        if index < 1:
            await interaction.response.send_message("❌ Nomor harus mulai dari 1.", ephemeral=True)
            return

        items = list(player.queue)
        if index > len(items):
            await interaction.response.send_message(f"❌ Queue cuma ada {len(items)} lagu.", ephemeral=True)
            return

        mp = self._music_cog.get_player(interaction.guild_id) if self._music_cog else None
        if mp:
            async with mp._track_lock:
                removed = items.pop(index - 1)
                player.queue.clear()
                for item in items:
                    await player.queue.put_wait(item)
        else:
            removed = items.pop(index - 1)
            player.queue.clear()
            for item in items:
                await player.queue.put_wait(item)

        await interaction.response.send_message(f"🗑️ Dihapus dari queue: **{removed.title}**")

    @app_commands.command(name="move", description="Pindah posisi lagu di queue")
    @app_commands.describe(from_index="Posisi asal", to_index="Posisi tujuan")
    async def move_cmd(self, interaction: discord.Interaction, from_index: int, to_index: int):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return

        items = list(player.queue)
        if not (1 <= from_index <= len(items)) or not (1 <= to_index <= len(items)):
            await interaction.response.send_message(f"❌ Index harus antara 1 dan {len(items)}.", ephemeral=True)
            return

        mp = self._music_cog.get_player(interaction.guild_id) if self._music_cog else None
        if mp:
            async with mp._track_lock:
                track = items.pop(from_index - 1)
                items.insert(to_index - 1, track)
                player.queue.clear()
                for item in items:
                    await player.queue.put_wait(item)
        else:
            track = items.pop(from_index - 1)
            items.insert(to_index - 1, track)
            player.queue.clear()
            for item in items:
                await player.queue.put_wait(item)

        await interaction.response.send_message(f"↔️ Dipindah: **{track.title}** ke posisi `{to_index}`")

    @app_commands.command(name="clearqueue", description="Kosongkan queue tanpa menghentikan lagu yang sedang diputar")
    async def clearqueue_cmd(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue sudah kosong.", ephemeral=True)
            return
        player.queue.clear()
        if self._music_cog:
            mp = self._music_cog.get_player(interaction.guild_id)
            if mp:
                mp._queue_history.clear()
        await interaction.response.send_message("🧹 Queue dikosongkan. Lagu yang sedang diputar tetap jalan.")

    @app_commands.command(name="shuffle", description="Acak antrian lagu")
    async def shuffle_cmd(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue kosong, tidak ada yang bisa diacak.", ephemeral=True)
            return
        mp = self._music_cog.get_player(interaction.guild_id) if self._music_cog else None
        items = list(player.queue)
        import random
        random.shuffle(items)
        player.queue.clear()
        for item in items:
            await player.queue.put_wait(item)
        if mp:
            mp._queue_history.clear()
        await interaction.response.send_message(f"🔀 Queue diacak! ({len(items)} lagu)")

    # ==========================================================
    # EVENTS
    # ==========================================================
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.command_consumer.is_running():
            self.command_consumer.start()
            print("[QUEUE_COG] ✅ Command consumer started (2s).")

    async def cog_unload(self):
        self.command_consumer.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueManager(bot))
