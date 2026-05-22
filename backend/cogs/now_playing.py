"""
Hidden Hamlet v4.6 — Now Playing Cog
=====================================
Tugas:
  1. Update shared state ke Flask setiap 2 detik (thread-safe)
  2. Konsum command queue dari Flask untuk control playback
  3. Bridge antara wavelink.Player ↔ Dashboard Web

Dipasang: backend/cogs/now_playing.py
"""

import discord
from discord.ext import commands, tasks
import wavelink
import asyncio
import sys

from backend.utils.formatters import format_duration


def _get_web_app():
    """Ambil web_app module via sys.modules (avoid circular import)."""
    wa = sys.modules.get("backend.web.web_app")
    if wa is None:
        # Fallback: coba import langsung
        try:
            import backend.web.web_app as wa_mod
            wa = wa_mod
        except Exception as e:
            print(f"[NOW_PLAYING] ⚠️ Cannot import web_app: {e}")
            return None
    return wa


class NowPlaying(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._music_cog = None
        print("[NOW_PLAYING_COG] Cog loaded.")

    async def cog_load(self):
        """Called when cog is loaded."""
        await asyncio.sleep(1)
        self._music_cog = self.bot.get_cog("Music")
        if self._music_cog:
            print("[NOW_PLAYING_COG] ✅ Linked with Music Cog.")
        else:
            print("[NOW_PLAYING_COG] ⚠️ Music Cog not found yet, will retry.")

    # ==========================================================
    # TASK: State Updater (setiap 2 detik)
    # ==========================================================
    @tasks.loop(seconds=2)
    async def state_updater(self):
        if not self._music_cog:
            self._music_cog = self.bot.get_cog("Music")
            if not self._music_cog:
                return

        wa = _get_web_app()
        if not wa:
            return

        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            try:
                state = self._build_state(guild)
                wa.set_music_state(guild_id, state)

                # Sync voice channels untuk dropdown
                voice_channels = [
                    {"id": str(ch.id), "name": ch.name}
                    for ch in guild.voice_channels
                    if ch.permissions_for(guild.me).connect
                ]
                wa.set_music_voice_channels(guild_id, voice_channels)
            except Exception as e:
                print(f"[NOW_PLAYING] State build error for {guild_id}: {e}")

    @state_updater.before_loop
    async def before_state_updater(self):
        await self.bot.wait_until_ready()

    # ==========================================================
    # TASK: Command Consumer (setiap 1 detik)
    # ==========================================================
    @tasks.loop(seconds=1)
    async def command_consumer(self):
        wa = _get_web_app()
        if not wa:
            return

        try:
            cmds = wa.pop_music_commands(max_n=10)
        except Exception as e:
            print(f"[NOW_PLAYING] Pop commands error: {e}")
            return

        for cmd in cmds:
            try:
                await self._execute_command(cmd)
            except Exception as e:
                print(f"[NOW_PLAYING] ❌ Command error: {e}")

    @command_consumer.before_loop
    async def before_command_consumer(self):
        await self.bot.wait_until_ready()

    # ==========================================================
    # BUILD STATE
    # ==========================================================
    def _build_state(self, guild: discord.Guild) -> dict:
        guild_id = guild.id
        player: wavelink.Player = guild.voice_client

        if not player or not player.is_connected():
            return {
                "connected": False,
                "playing": False,
                "paused": False,
                "volume": 100,
                "position": 0,
                "position_fmt": "0:00",
                "channel_name": None,
                "channel_id": None,
                "loop_mode": "off",
                "autoplay": False,
                "track": None,
                "queue": [],
                "queue_count": 0,
                "queue_duration": 0,
            }

        mp = self._music_cog.get_player(guild_id) if self._music_cog else None

        # Current track
        track_data = None
        if player.current:
            t = player.current
            track_data = {
                "title": t.title,
                "artist": t.author or "Unknown",
                "uri": t.uri,
                "thumbnail": t.artwork or "",
                "duration": t.length or 0,
                "duration_fmt": format_duration(t.length),
            }

        # Full queue
        queue_list = []
        total_dur = 0
        for i, t in enumerate(list(player.queue)):
            dur = t.length or 0
            total_dur += dur
            queue_list.append({
                "index": i + 1,
                "title": t.title,
                "artist": t.author or "Unknown",
                "duration": dur,
                "duration_fmt": format_duration(dur),
                "thumbnail": t.artwork or "",
                "uri": t.uri,
            })

        vc = player.channel
        return {
            "connected": True,
            "playing": player.is_playing(),
            "paused": player.is_paused(),
            "volume": getattr(player, "volume", 100),
            "position": getattr(player, "position", 0),
            "position_fmt": format_duration(getattr(player, "position", 0)),
            "channel_name": vc.name if vc else None,
            "channel_id": str(vc.id) if vc else None,
            "loop_mode": mp.loop_mode if mp else "off",
            "autoplay": mp.autoplay if mp else False,
            "track": track_data,
            "queue": queue_list,
            "queue_count": len(queue_list),
            "queue_duration": total_dur,
            "queue_duration_fmt": format_duration(total_dur),
        }

    # ==========================================================
    # EXECUTE COMMAND
    # ==========================================================
    async def _execute_command(self, cmd: dict):
        scope = cmd.get("scope")
        payload = cmd.get("payload", {})
        guild_id = int(payload.get("guild_id", 0))
        action = payload.get("action")

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        player: wavelink.Player = guild.voice_client
        if not player and action not in ("join", "disconnect"):
            return

        mp = self._music_cog.get_player(guild_id) if self._music_cog else None

        # ---------- Now Playing Controls ----------
        if action == "play":
            if player and player.is_paused():
                await player.pause(False)
        elif action == "pause":
            if player:
                await player.pause(True)
        elif action == "skip":
            if player and player.current:
                await player.stop()
        elif action == "prev":
            if player and player.current:
                await player.seek(0)
        elif action == "stop":
            if player:
                await player.stop()
                await player.disconnect()
                if mp:
                    mp.loop_mode = "off"
                    mp.autoplay = False
                    mp._queue_history.clear()
                    mp._single_loop_track = None
        elif action == "volume":
            vol = payload.get("volume", 100)
            if player:
                await player.set_volume(vol)
        elif action == "seek":
            pct = payload.get("position_pct", 0)
            if player and player.current:
                pos = int(pct * player.current.length)
                await player.seek(pos)
        elif action == "join":
            ch_id = int(payload.get("channel_id", 0))
            ch = guild.get_channel(ch_id)
            if ch and isinstance(ch, discord.VoiceChannel):
                if not player:
                    await ch.connect(cls=wavelink.Player, self_deaf=False)
                else:
                    await player.move_to(ch)
        elif action == "disconnect":
            if player:
                await player.disconnect()
        elif action == "shuffle":
            if player and not player.queue.is_empty:
                items = list(player.queue)
                import random
                random.shuffle(items)
                player.queue.clear()
                for item in items:
                    await player.queue.put_wait(item)
                if mp:
                    mp._queue_history.clear()
        elif action == "loop":
            if mp:
                modes = ["off", "single", "queue"]
                current = mp.loop_mode
                next_idx = (modes.index(current) + 1) % len(modes)
                mp.loop_mode = modes[next_idx]
                if mp.loop_mode == "queue":
                    mp._queue_history.clear()
                if mp.loop_mode == "off":
                    mp._single_loop_track = None
        elif action == "clear":
            if player:
                player.queue.clear()
                if mp:
                    mp._queue_history.clear()

        # ---------- Queue Actions ----------
        elif action == "add":
            query = payload.get("query", "")
            source = payload.get("source", "youtube")
            if player and query:
                search_q = query if query.startswith("http") else f"ytsearch:{query}"
                try:
                    results = await wavelink.Playable.search(search_q)
                    if results:
                        track = results[0]
                        await player.queue.put_wait(track)
                        if not player.current:
                            await player.set_volume(100)
                            await asyncio.sleep(0.3)
                            await player.play(player.queue.get())
                except Exception as e:
                    print(f"[NOW_PLAYING] Add error: {e}")
        elif action == "remove":
            idx = payload.get("index", 0)
            if player and not player.queue.is_empty:
                items = list(player.queue)
                if 0 <= idx < len(items):
                    items.pop(idx)
                    player.queue.clear()
                    for item in items:
                        await player.queue.put_wait(item)
        elif action == "move_top":
            idx = payload.get("index", 0)
            if player and not player.queue.is_empty:
                items = list(player.queue)
                if 0 < idx < len(items):
                    track = items.pop(idx)
                    items.insert(0, track)
                    player.queue.clear()
                    for item in items:
                        await player.queue.put_wait(item)

        # ---------- Playlist Load ----------
        elif action == "load_playlist":
            tracks = payload.get("tracks", [])
            if player and tracks:
                for t in tracks:
                    query = t.get("url") or t.get("query") or f"ytsearch:{t.get('title', '')}"
                    try:
                        results = await wavelink.Playable.search(query)
                        if results:
                            await player.queue.put_wait(results[0])
                    except Exception as e:
                        print(f"[NOW_PLAYING] Playlist load error: {e}")
                if not player.current and not player.queue.is_empty:
                    await player.set_volume(100)
                    await asyncio.sleep(0.3)
                    await player.play(player.queue.get())

        # ---------- Settings ----------
        elif action == "setting":
            key = payload.get("key")
            value = payload.get("value")
            if mp:
                if key == "autojoin":
                    pass
                elif key == "247_mode":
                    pass
                elif key == "announce":
                    pass

    # ==========================================================
    # EVENTS
    # ==========================================================
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.state_updater.is_running():
            self.state_updater.start()
            print("[NOW_PLAYING_COG] ✅ State updater started (2s).")
        if not self.command_consumer.is_running():
            self.command_consumer.start()
            print("[NOW_PLAYING_COG] ✅ Command consumer started (1s).")

    async def cog_unload(self):
        self.state_updater.cancel()
        self.command_consumer.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(NowPlaying(bot))
