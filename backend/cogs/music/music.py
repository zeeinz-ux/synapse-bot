import discord
from discord.ext import commands
import asyncio
import os
import time

try:
    from backend.cogs.database.firebase_setup import db
    _HAS_FS = True
except Exception:
    db = None
    _HAS_FS = False

LOFI_DEFAULT_URL = "https://play.streamafrica.net/lofiradio"
LOFI_KEYWORDS = {"lofi", "lo-fi", "lo_fi", "lofi radio", "default", "radio"}
VOICE_STATE_COLLECTION = "voice_state"
COLOR = 0x5865F2


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_states: dict[int, dict] = {}
        self._intentional_stop: set[int] = set()

    def _save_state(self, guild_id: int, channel_id: int, url: str):
        data = {"guild_id": guild_id, "channel_id": channel_id, "url": url, "updated_at": time.time()}
        self._voice_states[guild_id] = data
        if _HAS_FS and db is not None:
            try:
                asyncio.ensure_future(asyncio.to_thread(
                    lambda: db.collection(VOICE_STATE_COLLECTION).document(str(guild_id)).set(data)
                ))
            except Exception:
                pass

    def _clear_state(self, guild_id: int):
        self._voice_states.pop(guild_id, None)
        if _HAS_FS and db is not None:
            try:
                asyncio.ensure_future(asyncio.to_thread(
                    lambda: db.collection(VOICE_STATE_COLLECTION).document(str(guild_id)).delete()
                ))
            except Exception:
                pass

    async def _restore_states(self):
        if not _HAS_FS or db is None:
            return
        try:
            docs = await asyncio.to_thread(
                lambda: list(db.collection(VOICE_STATE_COLLECTION).stream())
            )
        except Exception:
            return
        for doc in docs:
            data = doc.to_dict()
            if not data:
                continue
            gid = data.get("guild_id")
            cid = data.get("channel_id")
            url = data.get("url", LOFI_DEFAULT_URL)
            if not gid or not cid:
                continue
            guild = self.bot.get_guild(int(gid))
            if not guild:
                continue
            channel = guild.get_channel(int(cid))
            if not channel or not isinstance(channel, discord.VoiceChannel):
                continue
            vc = guild.voice_client
            if vc:
                continue
            try:
                vc = await channel.connect()
                await asyncio.sleep(0.5)
                self._play_looping(vc, url)
                self._save_state(guild.id, channel.id, url)
                print(f"[MUSIC] Auto-resume: {guild.name} / {channel.name}")
            except Exception as e:
                print(f"[MUSIC] Auto-resume failed for {guild.name}: {e}")

    def _play_looping(self, vc, url: str):
        gid = vc.guild.id if vc and vc.guild else None
        if gid is not None:
            self._intentional_stop.discard(gid)
        try:
            ffmpeg_opts = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1 -reconnect_on_network_error 1",
                "options": "-vn",
            }
            source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            vc.play(source, after=lambda e: self._on_track_end(vc, url, e))
        except Exception as e:
            print(f"[MUSIC] _play_looping error: {e}")

    def _on_track_end(self, vc, url: str, error):
        gid = vc.guild.id if vc and vc.guild else None
        if gid and gid in self._intentional_stop:
            self._intentional_stop.discard(gid)
            print(f"[MUSIC] Intentional stop for guild {gid}, not restarting.")
            return
        if error:
            print(f"[MUSIC] Audio error: {error}")
        if not vc or not vc.is_connected():
            return
        print(f"[MUSIC] Stream ended, restarting...")
        self._play_looping(vc, url)

    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(3)
        await self._restore_states()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return
        if before.channel and after.channel and before.channel.id != after.channel.id:
            state = self._voice_states.get(member.guild.id)
            if state:
                state["channel_id"] = after.channel.id
                self._save_state(member.guild.id, after.channel.id, state["url"])
                print(f"[MUSIC] Moved to {after.channel.name}, state updated")
            return
        if before.channel and not after.channel:
            print(f"[MUSIC] Disconnected from {before.channel.name}, state preserved for restart auto-resume")

    @commands.command(name="connect", aliases=["joinvc"])
    async def connect(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        if not channel:
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                embed = discord.Embed(description="Sebut nama voice channel atau join voice dulu biar bot ngikut.", color=COLOR)
                await ctx.send(embed=embed)
                return
        vc = ctx.guild.voice_client
        if vc:
            if vc.channel.id == channel.id:
                embed = discord.Embed(description=f"Udah di {channel.mention} kok.", color=COLOR)
                await ctx.send(embed=embed)
                return
            if vc.is_playing():
                self._intentional_stop.add(ctx.guild.id)
            await vc.disconnect()
            await asyncio.sleep(0.5)
        try:
            vc = await channel.connect()
        except discord.Forbidden:
            embed = discord.Embed(description="Gak punya izin Connect/Speak di channel itu.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        except Exception as e:
            embed = discord.Embed(description=f"\u274c Gagal: {e}", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        await asyncio.sleep(0.5)
        try:
            self._play_looping(vc, LOFI_DEFAULT_URL)
            self._save_state(ctx.guild.id, channel.id, LOFI_DEFAULT_URL)
            embed = discord.Embed(
                title="\u25b6 Connected",
                description=f"Join **{channel.name}** dan muterin LoFi radio.",
                color=COLOR
            )
            await ctx.send(embed=embed)
        except discord.ClientException:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}** (voice tersambung, tapi audio error)", color=COLOR)
            await ctx.send(embed=embed)
        except Exception:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}**", color=COLOR)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="play", aliases=["p"], description="Putar LoFi radio")
    @discord.app_commands.describe(query="Kata kunci (kosongkan atau 'lofi' untuk LoFi radio)")
    async def play(self, ctx: commands.Context, *, query: str = None):
        await ctx.defer()
        vc = ctx.guild.voice_client
        if not vc:
            if ctx.author.voice and ctx.author.voice.channel:
                vc = await ctx.author.voice.channel.connect()
            else:
                embed = discord.Embed(description="Bot gak di voice. Pake `!connect` dulu atau join voice dulu.", color=COLOR)
                await ctx.send(embed=embed)
                return
        q = (query or "").strip().lower()
        if q and q not in LOFI_KEYWORDS:
            embed = discord.Embed(description=f"Maaf, hanya LoFi radio yang tersedia. Gunakan `{ctx.clean_prefix}play` atau `{ctx.clean_prefix}play lofi`.", color=COLOR)
            await ctx.send(embed=embed)
            return
        self._intentional_stop.add(ctx.guild.id)
        vc.stop()
        await asyncio.sleep(0.3)
        self._play_looping(vc, LOFI_DEFAULT_URL)
        self._save_state(ctx.guild.id, vc.channel.id, LOFI_DEFAULT_URL)
        embed = discord.Embed(
            title="\u25b6 Now Playing",
            description="**LoFi Radio** \ud83c\udfb5",
            color=COLOR
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="stop", description="Hentikan audio")
    async def stop(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            embed = discord.Embed(description="Gak ada audio yang diputar.", color=COLOR)
            await ctx.send(embed=embed)
            return
        self._intentional_stop.add(ctx.guild.id)
        vc.stop()
        embed = discord.Embed(description="\u23f9 Stopped", color=COLOR)
        await ctx.send(embed=embed)

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc:
            embed = discord.Embed(description="Gak ada di voice channel.", color=COLOR)
            await ctx.send(embed=embed)
            return
        name = vc.channel.name
        if vc.is_playing():
            self._intentional_stop.add(ctx.guild.id)
            vc.stop()
        await vc.disconnect()
        self._clear_state(ctx.guild.id)
        embed = discord.Embed(description=f"\U0001f44b Leave **{name}**", color=COLOR)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
