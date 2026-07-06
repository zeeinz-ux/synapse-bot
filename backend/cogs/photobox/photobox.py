"""
================================================================================
COG: Photobox Cog — Synapse Discord Bot
================================================================================
File    : backend/cogs/photobox/photobox.py
Deskripsi : Slash command /photobox — bikin webhook, kirim link photobox.
  • User menjalankan /photobox di channel mana pun.
  • Bot membuat webhook Discord untuk channel tersebut.
  • Bot mengirim ephemeral message dengan tombol "Buka Photobox 📸".
  • Tombol mengarah ke frontend camera dengan webhook_id & webhook_token
    sebagai query parameter.
  • Frontend menangkap foto dan mengirim langsung via webhook ke channel.
  • Webhook otomatis dihapus setelah 5 menit (timeout).
================================================================================
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

# ── Konstanta ──
PHOTOBOX_TIMEOUT = 300  # 5 menit — webhook auto-delete

BASE_URL = os.getenv(
    "PUBLIC_URL",
    "https://synapse-bot.up.railway.app"
)


class PhotoboxCog(commands.Cog, name="Photobox"):
    """Cog untuk photobox — ambil foto langsung dari browser ke Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("[PHOTOBOX] ✅ PhotoboxCog loaded")

    # ═══════════════════════════════════════════════════════════════════
    # SLASH COMMAND: /photobox
    # ═══════════════════════════════════════════════════════════════════
    @commands.hybrid_command(
        name="photobox",
        description="📸 Buka photobox buat ngambil foto langsung ke channel ini!"
    )
    async def photobox(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        try:
            webhook = await ctx.channel.create_webhook(
                name="Photobox 📸",
                reason="Photobox session"
            )
        except discord.Forbidden:
            await ctx.send(
                "❌ Aku gak punya izin buat bikin webhook di channel ini. "
                "Minta admin buat kasih izin **Manage Webhooks** ya!",
                ephemeral=True
            )
            return
        except Exception as e:
            print(f"[PHOTOBOX] ❌ Gagal bikin webhook: {e}")
            await ctx.send(
                "❌ Gagal bikin sesi photobox. Coba lagi nanti!",
                ephemeral=True
            )
            return

        link = (
            f"{BASE_URL}/photobox"
            f"?whid={webhook.id}&whtoken={webhook.token}"
            f"&channel={ctx.channel.id}"
        )

        view = PhotoboxView(link, webhook, ctx.channel.id)
        await ctx.send(
            "📸 **Photobox siap!** Klik tombol di bawah buka kamera dan "
            "ambil foto langsung — nanti fotonya muncul di channel ini!",
            view=view,
            ephemeral=True
        )

        # ── Background task: hapus webhook kalau gak dipakai 5 menit ──
        async def _cleanup():
            await asyncio.sleep(PHOTOBOX_TIMEOUT)
            try:
                await webhook.delete()
                print(f"[PHOTOBOX] 🧹 Webhook {webhook.id} dihapus (timeout)")
            except Exception:
                pass

        self.bot.loop.create_task(_cleanup())


class PhotoboxView(discord.ui.View):
    """Tombol untuk buka photobox."""

    def __init__(
        self,
        link: str,
        webhook: discord.Webhook,
        channel_id: int
    ):
        super().__init__(timeout=300)
        self.webhook = webhook
        self.channel_id = channel_id

        self.add_item(
            discord.ui.Button(
                label="📸 Buka Photobox",
                url=link,
                style=discord.ButtonStyle.link
            )
        )

    async def on_timeout(self):
        try:
            await self.webhook.delete()
            print(f"[PHOTOBOX] 🧹 Webhook {self.webhook.id} dihapus (view timeout)")
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(PhotoboxCog(bot))
