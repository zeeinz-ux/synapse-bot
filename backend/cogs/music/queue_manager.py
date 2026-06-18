# backend/cogs/music/queue_manager.py

import asyncio

class MusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.loop_mode = "off"
        self.autoplay = False
        self._queue_history = []
        self._single_loop_track = None
        self._last_track_id = None
        self._last_embed_time = 0
        self._track_lock = asyncio.Lock()
        self._alone_task = None
