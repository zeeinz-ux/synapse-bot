"""
Hidden Hamlet v4.6 — Playlist Cog
====================================
Tugas: Playlist load dari dashboard + slash commands.
Dipasang: backend/cogs/playlist.py

NOTE: Playlist save/store via dashboard menggunakan localStorage (browser).
Cog ini hanya menangani:
  1. Load playlist dari dashboard (POST /api/music/queue/bulk)
  2. Slash commands Discord untuk playlist (save/load/list/delete)
  3. Sinkronisasi ke Firestore (opsional, kalau user mau)
"""

import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio
import os
from datetime import datetime, timezone

from backend.utils.formatters import format_duration

def get_db():
    try:
        from backend.cogs.firebase_setup import db
        return db
    except Exception as e:
        print(f"[PLAYLIST_COG] ⚠️ Firebase import failed: {e}")
        return None


class PlaylistManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._music_cog = None
        print("[PLAYLIST_COG] Cog loaded.")

    async def cog_load(self):
        await asyncio.sleep(1)
        self._music_cog = self.bot.get_cog("Music")
        if self._music_cog:
            print("[PLAYLIST_COG] ✅ Linked with Music Cog.")

    # ==========================================================
    # SLASH COMMANDS
    # ==========================================================
    playlist = app_commands.Group(name="playlist", description="Simpan dan muat playlist lagu")

    @playlist.command(name="save", description="Simpan queue saat ini sebagai playlist")
    @app_commands.describe(name="Nama playlist")
    async def playlist_save(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        player = interaction.guild.voice_client
        tracks = []
        if player and player.current:
            tracks.append({
                "title": player.current.title,
                "uri": player.current.uri,
                "author": player.current.author or "Unknown",
                "artwork": player.current.artwork or "",
                "length": player.current.length or 0,
            })
        if player:
            for track in list(player.queue):
                tracks.append({
                    "title": track.title,
                    "uri": track.uri,
                    "author": track.author or "Unknown",
                    "artwork": track.artwork or "",
                    "length": track.length or 0,
                })
        if not tracks:
            await interaction.response.send_message("📭 Tidak ada lagu untuk disimpan.", ephemeral=True)
            return
        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        db.collection("playlists").document(doc_id).set({
            "guild_id": str(interaction.guild_id),
            "user_id": str(interaction.user.id),
            "name": name,
            "tracks": tracks,
            "created_at": datetime.now(timezone.utc),
        })
        await interaction.response.send_message(f"💾 Playlist **{name}** disimpan! ({len(tracks)} lagu)")

    @playlist.command(name="load", description="Muat playlist ke queue")
    @app_commands.describe(name="Nama playlist")
    async def playlist_load(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        await interaction.response.defer()
        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        doc = db.collection("playlists").document(doc_id).get()
        if not doc.exists:
            await interaction.followup.send(f"❌ Playlist **{name}** tidak ditemukan.")
            return
        data = doc.to_dict()
        track_data = data.get("tracks", [])
        if not track_data:
            await interaction.followup.send("📭 Playlist kosong.")
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ Kamu harus join voice channel dulu!")
            return
        vc = interaction.user.voice.channel
        player = interaction.guild.voice_client
        if not player:
            player = await vc.connect(cls=wavelink.Player, self_deaf=False)
            player.home = interaction.channel
        elif player.channel != vc:
            await player.move_to(vc, self_deaf=False)
            player.home = interaction.channel
        added = 0
        failed = 0
        for t in track_data:
            try:
                results = await wavelink.Playable.search(t["uri"])
                if results:
                    await player.queue.put_wait(results[0])
                    added += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"[PLAYLIST LOAD ERROR] {e}")
                failed += 1
        if not player.current and not player.queue.is_empty:
            await player.play(player.queue.get())
        msg = f"📂 Playlist **{name}** dimuat! ({added} lagu ditambahkan)"
        if failed:
            msg += f" | {failed} gagal dimuat"
        await interaction.followup.send(msg)

    @playlist.command(name="list", description="Lihat daftar playlist-mu")
    async def playlist_list(self, interaction: discord.Interaction):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        playlists = (db.collection("playlists")
            .where("guild_id", "==", str(interaction.guild_id))
            .where("user_id", "==", str(interaction.user.id))
            .stream())
        embed = discord.Embed(title="📂 Playlist-mu", color=discord.Color.blue())
        count = 0
        for doc in playlists:
            data = doc.to_dict()
            track_count = len(data.get("tracks", []))
            created = data.get("created_at")
            if created:
                created_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)
            else:
                created_str = "Unknown"
            embed.add_field(name=data["name"], value=f"{track_count} lagu · {created_str}", inline=False)
            count += 1
        if count == 0:
            embed.description = "📭 Belum ada playlist. Gunakan `/playlist save` untuk membuat satu."
        await interaction.response.send_message(embed=embed)

    @playlist.command(name="delete", description="Hapus playlist")
    @app_commands.describe(name="Nama playlist yang mau dihapus")
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        doc_ref = db.collection("playlists").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            await interaction.response.send_message(f"❌ Playlist **{name}** tidak ditemukan.", ephemeral=True)
            return
        doc_ref.delete()
        await interaction.response.send_message(f"🗑️ Playlist **{name}** dihapus.")


async def setup(bot: commands.Bot):
    await bot.add_cog(PlaylistManager(bot))
