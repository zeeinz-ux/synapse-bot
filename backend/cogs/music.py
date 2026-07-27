import discord
from discord.ext import commands
import asyncio

LOFI_DEFAULT_URL = "https://play.streamafrica.net/lofiradio"


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="connect", aliases=["joinvc"])
    async def connect(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        if not channel:
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                await ctx.send("Sebut nama voice channel atau join voice dulu biar bot ngikut.")
                return
        vc = ctx.guild.voice_client
        if vc:
            if vc.channel.id == channel.id:
                await ctx.send(f"Udah di {channel.mention} kok.")
                return
            await vc.disconnect()
            await asyncio.sleep(0.5)
        try:
            vc = await channel.connect()
        except discord.Forbidden:
            await ctx.send("Gak punya izin Connect/Speak di channel itu.")
            return
        except Exception as e:
            await ctx.send(f"❌ Gagal: {e}")
            return
        url = LOFI_DEFAULT_URL
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }
        try:
            source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            vc.play(source)
            await ctx.send(f"✅ Join **{channel.name}** 🎵 LoFi")
        except Exception:
            await ctx.send(f"✅ Join **{channel.name}**")

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc:
            await ctx.send("Gak ada di voice channel.")
            return
        name = vc.channel.name
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        await ctx.send(f"✅ Leave **{name}**")

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, stream: str = None):
        vc = ctx.guild.voice_client
        if not vc:
            if ctx.author.voice and ctx.author.voice.channel:
                await ctx.author.voice.channel.connect()
                vc = ctx.guild.voice_client
            else:
                await ctx.send("Bot gak di voice. Pake `!join` dulu atau join voice dulu.")
                return
        url = stream or LOFI_DEFAULT_URL
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }
        vc.stop()
        try:
            source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            vc.play(source)
            label = "LoFi default" if not stream else url[:60]
            await ctx.send(f"🎵 Putar **{label}**")
        except Exception as e:
            await ctx.send(f"❌ Gagal putar audio: {e}")

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            await ctx.send("Gak ada audio yang diputar.")
            return
        vc.stop()
        await ctx.send("⏹ Audio dihentikan")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
