import discord
from discord.ext import commands, tasks
from discord import ui
import asyncio
import time
import os
import logging
from ..database.firebase_setup import db

log = logging.getLogger(__name__)

TRIGGER_CHANNEL = "➕ Create Caffee'"
INTERFACE_CHANNEL = "✨・interface"
GAME_CATEGORY = "🎮 Game"
VOICE_CATEGORY = "💬 Create Voice"
GRACE_PERIOD = 300
EMPTY_DELETE_DELAY = 10
ROOM_NAME_TEMPLATE = "\U0001f5e3\ufe0f {name}'s Caffee"

_rooms: dict[int, dict[int, 'VoiceRoom']] = {}
_interface_msgs: dict[int, int] = {}
_empty_timers: dict[int, asyncio.Task] = {}
_owner_leave_timers: dict[int, asyncio.Task] = {}
_delete_tasks: dict[int, asyncio.Task] = {}
_user_prefs: dict[int, dict] = {}  # {user_id: {locked, visible, waiting_room, limit, region}}
_ephemeral_msgs: dict[int, list[discord.Message]] = {}  # {user_id: [ephemeral msgs]}

class VoiceRoom:
    __slots__ = (
        'owner_id', 'channel_id', 'guild_id',
        'locked', 'visible', 'limit', 'waiting_room',
        'blocked_users', 'trusted_users', 'waiting_users',
        'chat_channel_id', 'region',
        'created_at', 'owner_left_at',
    )

    def __init__(self, owner_id: int, channel_id: int, guild_id: int):
        self.owner_id = owner_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.locked = False
        self.visible = True
        self.limit = None
        self.waiting_room = False
        self.blocked_users: set[int] = set()
        self.trusted_users: set[int] = set()
        self.waiting_users: set[int] = set()
        self.chat_channel_id = None
        self.region = None
        self.created_at = time.time()
        self.owner_left_at = None

    @property
    def members(self) -> list[int]:
        guild = _get_guild(self.guild_id)
        if not guild:
            return []
        ch = guild.get_channel(self.channel_id)
        if not isinstance(ch, discord.VoiceChannel):
            return []
        return [m.id for m in ch.members]

def _get_guild(guild_id: int):
    for g in (bot_ref.guilds if bot_ref else []):
        if g.id == guild_id:
            return g
    return None

bot_ref: commands.Bot = None

def _get_room(guild_id: int, user_id: int):
    guild_rooms = _rooms.get(guild_id, {})
    for room in guild_rooms.values():
        if room.owner_id == user_id:
            return room
    return None

def _get_room_by_channel(guild_id: int, channel_id: int):
    guild_rooms = _rooms.get(guild_id, {})
    return guild_rooms.get(channel_id)

async def _check_premium(guild_id: int, user_id: int) -> bool:
    if db is None:
        return False
    try:
        doc = await asyncio.to_thread(
            lambda: db.collection("guild_settings").document(str(guild_id)).get()
        )
        if doc.exists:
            premium_users = doc.to_dict().get("premium_users", {})
            user_data = premium_users.get(str(user_id))
            if user_data and isinstance(user_data, dict):
                return user_data.get("expiry", 0) > time.time()
    except Exception:
        pass
    return False

class MemberSelect(ui.Select['TempView']):
    def __init__(self, placeholder: str, members: list[discord.Member], cog, action: str, room_channel_id: int):
        options = [
            discord.SelectOption(label=m.display_name[:100], value=str(m.id), emoji="\U0001f464")
            for m in members[:25]
        ]
        if not options:
            options = [discord.SelectOption(label="No members", value="none")]
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)
        self._cog = cog
        self._action = action
        self._room_channel_id = room_channel_id

    async def callback(self, interaction: discord.Interaction):
        await self._cog._handle_member_select(interaction, self._action, self._room_channel_id, int(self.values[0]))
        self.view.stop()

class PrivacySelect(ui.Select['TempView']):
    def __init__(self, cog, room_channel_id: int, current_lock: bool, current_visible: bool, chat_open: bool):
        options = [
            discord.SelectOption(label="Lock", value="lock", emoji="\U0001f512", description="Kunci room"),
            discord.SelectOption(label="Unlock", value="unlock", emoji="\U0001f513", description="Buka kunci room"),
            discord.SelectOption(label="Hide", value="hide", emoji="\U0001f648", description="Sembunyikan room"),
            discord.SelectOption(label="Show", value="show", emoji="\U0001f441\ufe0f", description="Tampilkan room"),
            discord.SelectOption(label="Open Chat", value="open_chat", emoji="\U0001f4ac", description="Buka text chat"),
            discord.SelectOption(label="Close Chat", value="close_chat", emoji="\U0001f515", description="Tutup text chat"),
        ]
        super().__init__(placeholder="Pilih opsi privacy...", options=options, min_values=1, max_values=1)
        self._cog = cog
        self._room_channel_id = room_channel_id

    async def callback(self, interaction: discord.Interaction):
        await self._cog._handle_privacy_action(interaction, self._room_channel_id, self.values[0])

class TempView(ui.View):
    def __init__(self, *items: ui.Item, timeout: float = 120):
        super().__init__(timeout=timeout)
        for item in items:
            self.add_item(item)

class RoomNameModal(ui.Modal):
    def __init__(self, cog, room_channel_id: int):
        super().__init__(title="Rename Voice Room")
        self._cog = cog
        self._room_channel_id = room_channel_id
        self.add_item(ui.TextInput(label="Room Name", placeholder="Enter new room name...", max_length=100))

    async def on_submit(self, interaction: discord.Interaction):
        await self._cog._handle_rename(interaction, self._room_channel_id, self.children[0].value)

class UserIdModal(ui.Modal):
    def __init__(self, cog, room_channel_id: int, action: str):
        super().__init__(title=f"{action} User")
        self._cog = cog
        self._room_channel_id = room_channel_id
        self._action = action
        self.add_item(ui.TextInput(label="User ID", placeholder="Enter Discord user ID...", max_length=30))

    async def on_submit(self, interaction: discord.Interaction):
        await self._cog._handle_user_id_modal(interaction, self._room_channel_id, self._action, self.children[0].value)

class LimitModal(ui.Modal):
    def __init__(self, cog, room_channel_id: int):
        super().__init__(title="Set User Limit")
        self._cog = cog
        self._room_channel_id = room_channel_id
        self.add_item(ui.TextInput(label="Limit", placeholder="1-99, or 0 for unlimited", max_length=3))

    async def on_submit(self, interaction: discord.Interaction):
        await self._cog._handle_limit(interaction, self._room_channel_id, self.children[0].value)

class ConfirmDeleteView(ui.View):
    def __init__(self, cog, room_channel_id: int, owner_id: int):
        super().__init__(timeout=30)
        self._cog = cog
        self._room_channel_id = room_channel_id
        self._owner_id = owner_id

    async def _cleanup(self, interaction: discord.Interaction):
        try:
            msg = await interaction.original_response()
            await msg.delete()
        except Exception:
            pass
        msgs = _ephemeral_msgs.pop(self._owner_id, [])
        for msg in msgs:
            try:
                await msg.delete()
            except Exception:
                pass

    @ui.button(label="\u2714\ufe0f Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await self._cleanup(interaction)
        await self._cog._handle_delete_room(interaction, self._room_channel_id)
        self.stop()

    @ui.button(label="\u274c Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await self._cleanup(interaction)
        self.stop()

class VoiceControlView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self._cog = cog

    async def _get_room(self, interaction: discord.Interaction) -> VoiceRoom | None:
        return _get_room(interaction.guild_id, interaction.user.id)

    async def _owner_only(self, interaction: discord.Interaction) -> VoiceRoom | None:
        room = await self._get_room(interaction)
        if not room:
            await interaction.response.send_message("Kamu gak punya voice room. Join **\u2795 Create Caffee'** untuk buat room!", ephemeral=True, delete_after=8)
            return None
        return room

    @ui.button(label="\u270f\ufe0f Rename", style=discord.ButtonStyle.secondary, row=0)
    async def rename_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        await interaction.response.send_modal(RoomNameModal(self._cog, room.channel_id))

    @ui.button(label="\U0001f512 Privacy", style=discord.ButtonStyle.secondary, row=0)
    async def privacy_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        guild_rooms = _rooms.get(interaction.guild_id, {})
        r = guild_rooms.get(room.channel_id)
        chat_open = r.chat_channel_id is not None if r else False
        view = TempView(PrivacySelect(self._cog, room.channel_id, room.locked, room.visible, chat_open))
        await interaction.response.send_message("Pilih pengaturan privacy:", ephemeral=True, view=view)
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass

    @ui.button(label="\U0001f465 Limit", style=discord.ButtonStyle.secondary, row=0)
    async def limit_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        await interaction.response.send_modal(LimitModal(self._cog, room.channel_id))

    @ui.button(label="\U0001f6aa Waiting", style=discord.ButtonStyle.secondary, row=0)
    async def waiting_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        await self._cog._handle_waiting_toggle(interaction, room)

    @ui.button(label="\u2705 Trust", style=discord.ButtonStyle.success, row=1)
    async def trust_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        guild = interaction.guild
        members = [m for m in guild.members if not m.bot and m.id != room.owner_id and m.id not in room.trusted_users and m.id not in room.blocked_users]
        if not members:
            await interaction.response.send_message("No users to trust.", ephemeral=True, delete_after=8)
            return
        await interaction.response.send_message("Select a user to trust:", ephemeral=True, view=TempView(
            MemberSelect("Select user...", members[:25], self._cog, "trust", room.channel_id)
        ))
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass

    @ui.button(label="\u274c Untrust", style=discord.ButtonStyle.danger, row=1)
    async def untrust_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        if not room.trusted_users:
            await interaction.response.send_message("No trusted users.", ephemeral=True, delete_after=8)
            return
        guild = interaction.guild
        members = [m for m in guild.members if m.id in room.trusted_users]
        if not members:
            await interaction.response.send_message("No trusted users found in server.", ephemeral=True, delete_after=8)
            return
        await interaction.response.send_message("Select a user to untrust:", ephemeral=True, view=TempView(
            MemberSelect("Select user...", members[:25], self._cog, "untrust", room.channel_id)
        ))
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass

    @ui.button(label="\U0001f6ab Block", style=discord.ButtonStyle.danger, row=1)
    async def block_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        await interaction.response.send_modal(UserIdModal(self._cog, room.channel_id, "Block"))

    @ui.button(label="\U0001f513 Unblock", style=discord.ButtonStyle.secondary, row=1)
    async def unblock_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        if not room.blocked_users:
            await interaction.response.send_message("No blocked users.", ephemeral=True, delete_after=8)
            return
        guild = interaction.guild
        members = [m for m in guild.members if m.id in room.blocked_users]
        if not members:
            await interaction.response.send_message("No blocked users found in server.", ephemeral=True, delete_after=8)
            return
        await interaction.response.send_message("Select a user to unblock:", ephemeral=True, view=TempView(
            MemberSelect("Select user...", members[:25], self._cog, "unblock", room.channel_id)
        ))
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass

    @ui.button(label="\U0001f50a Kick", style=discord.ButtonStyle.danger, row=2)
    async def kick_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        members = room.members
        others = [m for m in (interaction.guild.get_member(uid) for uid in members) if m and m.id != room.owner_id]
        if not others:
            await interaction.response.send_message("No other members in your room.", ephemeral=True, delete_after=8)
            return
        await interaction.response.send_message("Select a user to kick:", ephemeral=True, view=TempView(
            MemberSelect("Select user...", others[:25], self._cog, "kick", room.channel_id)
        ))
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass

    @ui.button(label="\U0001f4e8 Invite", style=discord.ButtonStyle.secondary, row=2)
    async def invite_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        await interaction.response.send_modal(UserIdModal(self._cog, room.channel_id, "Invite"))

    @ui.button(label="\U0001f310 Region", style=discord.ButtonStyle.secondary, row=2)
    async def region_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        regions = [
            discord.SelectOption(label="Automatic", value="auto", emoji="\U0001f310"),
            discord.SelectOption(label="Brazil", value="brazil", emoji="\U0001f1e7\U0001f1f7"),
            discord.SelectOption(label="Hong Kong", value="hongkong", emoji="\U0001f1ed\U0001f1f0"),
            discord.SelectOption(label="India", value="india", emoji="\U0001f1ee\U0001f1f3"),
            discord.SelectOption(label="Japan", value="japan", emoji="\U0001f1ef\U0001f1f5"),
            discord.SelectOption(label="Rotterdam", value="rotterdam", emoji="\U0001f1f3\U0001f1f1"),
            discord.SelectOption(label="Russia", value="russia", emoji="\U0001f1f7\U0001f1fa"),
            discord.SelectOption(label="Singapore", value="singapore", emoji="\U0001f1f8\U0001f1ec"),
            discord.SelectOption(label="South Africa", value="southafrica", emoji="\U0001f1ff\U0001f1e6"),
            discord.SelectOption(label="South Korea", value="south-korea", emoji="\U0001f1f0\U0001f1f7"),
            discord.SelectOption(label="Sydney", value="sydney", emoji="\U0001f1e6\U0001f1fa"),
            discord.SelectOption(label="US Central", value="us-central", emoji="\U0001f1fa\U0001f1f8"),
            discord.SelectOption(label="US East", value="us-east", emoji="\U0001f1fa\U0001f1f8"),
            discord.SelectOption(label="US South", value="us-south", emoji="\U0001f1fa\U0001f1f8"),
            discord.SelectOption(label="US West", value="us-west", emoji="\U0001f1fa\U0001f1f8"),
        ]
        select = ui.Select(placeholder="Select voice region...", options=regions)
        async def region_cb(sel_interaction: discord.Interaction):
            await self._cog._handle_region(sel_interaction, room, sel_interaction.data["values"][0])
        select.callback = region_cb
        view = TempView(select)
        await interaction.response.send_message("Select voice region:", ephemeral=True, view=view)
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass

    @ui.button(label="\U0001f5d1\ufe0f Delete", style=discord.ButtonStyle.danger, row=2)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._owner_only(interaction)
        if not room:
            return
        await interaction.response.send_message("Are you sure you want to delete your voice room?", ephemeral=True, view=ConfirmDeleteView(self._cog, room.channel_id, interaction.user.id))
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass

    @ui.button(label="\u2b50 Claim", style=discord.ButtonStyle.primary, row=3)
    async def claim_btn(self, interaction: discord.Interaction, button: ui.Button):
        guild_rooms = _rooms.get(interaction.guild_id, {})
        claimable = []
        for ch_id, room in guild_rooms.items():
            if room.owner_left_at and (time.time() - room.owner_left_at) > GRACE_PERIOD:
                ch = interaction.guild.get_channel(ch_id)
                if ch and any(m.id == interaction.user.id for m in ch.members):
                    claimable.append(room)
        if not claimable:
            await interaction.response.send_message("No claimable rooms. Owner must be offline >5 menit dan kamu masih di room.", ephemeral=True, delete_after=8)
            return
        if len(claimable) == 1:
            await self._cog._handle_claim(interaction, claimable[0])
        else:
            options = []
            for r in claimable:
                ch = interaction.guild.get_channel(r.channel_id)
                name = ch.name if ch else "Unknown"
                options.append(discord.SelectOption(label=name[:100], value=str(r.channel_id)))
            select = ui.Select(placeholder="Select room to claim...", options=options[:25])
            async def claim_cb(sel_interaction: discord.Interaction):
                ch_id = int(sel_interaction.data["values"][0])
                room = guild_rooms.get(ch_id)
                if room:
                    await self._cog._handle_claim(sel_interaction, room)
            select.callback = claim_cb
            await interaction.response.send_message("Select a room to claim:", ephemeral=True, view=TempView(select))
            try:
                _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
            except Exception:
                pass

    @ui.button(label="\U0001f4e4 Transfer", style=discord.ButtonStyle.primary, row=3)
    async def transfer_btn(self, interaction: discord.Interaction, button: ui.Button):
        room = await self._get_room(interaction)
        if not room:
            await interaction.response.send_message("Kamu gak punya voice room.", ephemeral=True, delete_after=8)
            return
        is_premium = await _check_premium(interaction.guild_id, interaction.user.id)
        if not is_premium:
            await interaction.response.send_message("\u2b50 Fitur Transfer adalah premium. Upgrade untuk menggunakan fitur ini.", ephemeral=True, delete_after=8)
            return
        members = room.members
        others = [m for m in (interaction.guild.get_member(uid) for uid in members) if m and m.id != room.owner_id]
        if not others:
            await interaction.response.send_message("No other members to transfer to.", ephemeral=True, delete_after=8)
            return
        await interaction.response.send_message("Select new owner:", ephemeral=True, view=TempView(
            MemberSelect("Select member...", others[:25], self._cog, "transfer", room.channel_id)
        ))
        try:
            _ephemeral_msgs.setdefault(interaction.user.id, []).append(await interaction.original_response())
        except Exception:
            pass


class VoiceInterfaceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        global bot_ref
        bot_ref = bot
        _rooms.clear()
        _interface_msgs.clear()
        self.premium_cleanup.start()

    def cog_unload(self):
        self.premium_cleanup.cancel()

    @tasks.loop(hours=1)
    async def premium_cleanup(self):
        if db is None:
            return
        now = time.time()
        try:
            guilds_snapshot = await asyncio.to_thread(
                lambda: list(db.collection("guild_settings").stream())
            )
            for doc in guilds_snapshot:
                data = doc.to_dict()
                premium_users = data.get("premium_users", {})
                if not premium_users:
                    continue
                expired = [uid for uid, udata in premium_users.items()
                           if isinstance(udata, dict) and udata.get("expiry", 0) <= now]
                if expired:
                    for uid in expired:
                        del premium_users[uid]
                    await asyncio.to_thread(
                        lambda: doc.reference.update({"premium_users": premium_users})
                    )
        except Exception:
            pass

    @premium_cleanup.before_loop
    async def before_premium_cleanup(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        log.info("VoiceInterfaceCog loaded, registering persistent view")
        try:
            self.bot.add_view(VoiceControlView(self))
            log.info("VoiceControlView registered successfully")
        except Exception as e:
            log.error(f"Failed to register VoiceControlView: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.name == INTERFACE_CHANNEL:
            try:
                await message.delete()
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"on_ready fired, {len(self.bot.guilds)} guild(s)")
        for guild in self.bot.guilds:
            try:
                await self._restore_guild(guild)
            except Exception as e:
                log.error(f"_restore_guild failed for {guild.id}: {e}")
            try:
                await self._ensure_interface(guild)
            except Exception as e:
                log.error(f"_ensure_interface failed for {guild.id}: {e}")

    async def _restore_guild(self, guild: discord.Guild):
        cat = discord.utils.get(guild.categories, name=GAME_CATEGORY)
        if not cat:
            return
        for ch in cat.voice_channels:
            if ch.name.startswith("\U0001f5e3\ufe0f") or ch.name.endswith("'s Caffee"):
                room = VoiceRoom(0, ch.id, guild.id)
                member_ids = [m.id for m in ch.members]
                if member_ids:
                    room.owner_id = member_ids[0]
                _rooms.setdefault(guild.id, {})[ch.id] = room

    async def _ensure_interface(self, guild: discord.Guild):
        trigger = discord.utils.get(guild.voice_channels, name=TRIGGER_CHANNEL)
        if not trigger:
            log.info(f"_ensure_interface: guild {guild.id} has no trigger channel, skipping")
            return
        ch = discord.utils.get(guild.text_channels, name=INTERFACE_CHANNEL)
        if not ch:
            log.warning(f"_ensure_interface: channel '{INTERFACE_CHANNEL}' not found in guild {guild.id}")
            return
        embed = self._build_embed(guild)
        view = VoiceControlView(self)
        old_msg_id = _interface_msgs.get(guild.id)
        if old_msg_id:
            try:
                old_msg = await ch.fetch_message(old_msg_id)
                await old_msg.edit(embed=embed, view=view)
                log.info(f"_ensure_interface: edited msg {old_msg.id} in #{ch.name} guild {guild.id}")
                return
            except Exception:
                pass
        found = None
        async for msg in ch.history(limit=20):
            if msg.author.id == self.bot.user.id and msg.embeds:
                for e in msg.embeds:
                    if e.title and "Voice Room Controls" in e.title:
                        if found is None:
                            found = msg
                        else:
                            try:
                                await msg.delete()
                                log.info(f"_ensure_interface: deleted duplicate msg {msg.id}")
                            except Exception:
                                pass
                        break
        if found:
            try:
                await found.edit(embed=embed, view=view)
                _interface_msgs[guild.id] = found.id
                log.info(f"_ensure_interface: found & edited msg {found.id} in #{ch.name} guild {guild.id}")
                return
            except Exception:
                pass
        try:
            msg = await ch.send(embed=embed, view=view)
            _interface_msgs[guild.id] = msg.id
            log.info(f"_ensure_interface: sent msg {msg.id} in #{ch.name} guild {guild.id}")
        except Exception as e:
            log.error(f"_ensure_interface: failed to send message in #{ch.name}: {e}")

    def _build_embed(self, guild: discord.Guild) -> discord.Embed:
        guild_rooms = _rooms.get(guild.id, {})
        embed = discord.Embed(
            title="\U0001f39b\ufe0f Voice Room Controls",
            color=discord.Color.blurple(),
        )
        if guild_rooms:
            lines = []
            for ch_id, room in guild_rooms.items():
                vc = guild.get_channel(ch_id)
                if not vc:
                    continue
                name = vc.name
                members = len(vc.members)
                status = []
                if room.locked:
                    status.append("\U0001f512 Locked")
                if not room.visible:
                    status.append("\U0001f441\ufe0f Hidden")
                if room.waiting_room:
                    status.append("\U0001f6aa Waiting")
                status_str = " | ".join(status) if status else "\u2705 Active"
                owner = guild.get_member(room.owner_id)
                owner_name = owner.display_name if owner else "Unknown"
                lines.append(f"\u2022 **{name}** — {members} member ({status_str}) — Owner: {owner_name}")
            embed.description = "\n".join(lines) if lines else "No active voice rooms."
        else:
            embed.description = "Belum ada voice room aktif.\n\nJoin **\u2795 Create Caffee'** untuk buat room!"
        embed.set_footer(text=f"{len(guild_rooms)} active room(s) \u2022 Butir premium: \u2b50 Claim & Transfer")
        return embed

    async def _update_interface(self, guild: discord.Guild):
        ch = discord.utils.get(guild.text_channels, name=INTERFACE_CHANNEL)
        if not ch:
            return
        msg_id = _interface_msgs.get(guild.id)
        if msg_id:
            try:
                msg = await ch.fetch_message(msg_id)
                await msg.edit(embed=self._build_embed(guild))
                return
            except Exception:
                pass
        await self._ensure_interface(guild)

    # ── Voice State Listener ──

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        guild = member.guild

        # Joined trigger channel → create room
        if after.channel:
            log.info(f"Voice state: {member.display_name} joined #{after.channel.name} (trigger={TRIGGER_CHANNEL})")
        if after.channel and after.channel.name == TRIGGER_CHANNEL:
            cat = discord.utils.get(guild.categories, name=GAME_CATEGORY)
            if not cat:
                cat = after.channel.category
            await self._create_room(member, cat)
            return

        # Left a room → update state
        if before.channel:
            guild_rooms = _rooms.get(guild.id, {})
            room = guild_rooms.get(before.channel.id)
            if room:
                remaining = [m for m in before.channel.members if not m.bot]
                if member.id == room.owner_id:
                    await self._delete_room(before.channel.id, guild.id)
                    return
                if not remaining:
                    await self._schedule_empty_delete(room)

        # Joined a tracked room
        if after.channel:
            guild_rooms = _rooms.get(guild.id, {})
            room = guild_rooms.get(after.channel.id)
            if room:
                if member.id in room.blocked_users:
                    try:
                        await member.move_to(None)
                    except Exception:
                        try:
                            await after.channel.set_permissions(member, connect=False)
                        except Exception:
                            pass
                    return
                if room.waiting_room and member.id != room.owner_id and member.id not in room.trusted_users:
                    room.waiting_users.add(member.id)
                    try:
                        await member.edit(mute=True, reason="Waiting room")
                    except Exception:
                        pass

    # ── User Prefs (Firestore) ──

    async def _load_user_prefs(self, user_id: int) -> dict | None:
        if db is None:
            return None
        try:
            doc = await asyncio.to_thread(
                lambda: db.collection("user_voice_prefs").document(str(user_id)).get()
            )
            if doc.exists:
                data = doc.to_dict()
                _user_prefs[user_id] = data
                return data
        except Exception:
            pass
        return None

    async def _save_user_prefs(self, user_id: int):
        prefs = _user_prefs.get(user_id)
        if prefs is None or db is None:
            return
        try:
            await asyncio.to_thread(
                lambda: db.collection("user_voice_prefs").document(str(user_id)).set(prefs)
            )
        except Exception:
            pass

    # ── Room Lifecycle ──

    async def _create_room(self, member: discord.Member, category: discord.CategoryChannel):
        guild = member.guild
        if _get_room(guild.id, member.id):
            log.warning(f"{member.display_name} already has a room in guild {guild.id}")
            return
        name = ROOM_NAME_TEMPLATE.format(name=member.display_name)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True),
        }
        try:
            vc = await guild.create_voice_channel(name, category=category, overwrites=overwrites, reason="Temp voice room")
        except Exception as e:
            log.error(f"Failed to create voice room for {member.display_name}: {e}")
            return
        room = VoiceRoom(member.id, vc.id, guild.id)
        _rooms.setdefault(guild.id, {})[vc.id] = room
        prefs = _user_prefs.get(member.id)
        if prefs is None:
            prefs = await self._load_user_prefs(member.id)
        if prefs:
            room.locked = prefs.get("locked", False)
            room.visible = prefs.get("visible", True)
            room.waiting_room = prefs.get("waiting_room", False)
            room.limit = prefs.get("limit", None)
            room.region = prefs.get("region", None)
            if room.locked:
                try:
                    await vc.set_permissions(guild.default_role, connect=False)
                except Exception:
                    pass
            if not room.visible:
                try:
                    await vc.set_permissions(guild.default_role, view_channel=False)
                except Exception:
                    pass
        try:
            await member.move_to(vc)
        except Exception as e:
            log.error(f"Failed to move {member.display_name} to new room: {e}")
        await self._update_interface(guild)

    async def _delete_room(self, channel_id: int, guild_id: int):
        guild_rooms = _rooms.get(guild_id, {})
        room = guild_rooms.pop(channel_id, None)
        _empty_timers.pop(channel_id, None)
        _owner_leave_timers.pop(channel_id, None)
        _delete_tasks.pop(channel_id, None)
        if not room:
            return
        guild = _get_guild(guild_id)
        if guild:
            vc = guild.get_channel(channel_id)
            if isinstance(vc, discord.VoiceChannel):
                try:
                    for m in vc.members:
                        try:
                            await m.move_to(None)
                        except Exception:
                            pass
                    await vc.delete(reason="Temp voice room deleted")
                except Exception:
                    pass
            if room.chat_channel_id:
                chat = guild.get_channel(room.chat_channel_id)
                if chat:
                    try:
                        await chat.delete(reason="Temp voice chat deleted")
                    except Exception:
                        pass
        msgs = _ephemeral_msgs.pop(room.owner_id, [])
        for msg in msgs:
            try:
                await msg.delete()
            except Exception:
                pass
        await self._update_interface(guild) if guild else None

    async def _schedule_empty_delete(self, room: VoiceRoom):
        ch_id = room.channel_id
        if ch_id in _delete_tasks:
            return

        async def _delayed_delete():
            try:
                await asyncio.sleep(EMPTY_DELETE_DELAY)
                guild_rooms = _rooms.get(room.guild_id, {})
                r = guild_rooms.get(ch_id)
                if r:
                    guild = _get_guild(room.guild_id)
                    if guild:
                        vc = guild.get_channel(ch_id)
                        if isinstance(vc, discord.VoiceChannel) and len([m for m in vc.members if not m.bot]) == 0:
                            await self._delete_room(ch_id, room.guild_id)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_delayed_delete())
        _delete_tasks[ch_id] = task

    async def _schedule_claim_check(self, room: VoiceRoom):
        old = _owner_leave_timers.get(room.channel_id)
        if old:
            old.cancel()

        async def _check():
            try:
                await asyncio.sleep(GRACE_PERIOD)
                room.owner_left_at = None
            except asyncio.CancelledError:
                pass

        _owner_leave_timers[room.channel_id] = asyncio.create_task(_check())

    # ── Button Handlers ──

    async def _handle_rename(self, interaction: discord.Interaction, channel_id: int, new_name: str):
        room = _get_room_by_channel(interaction.guild_id, channel_id)
        if not room or room.owner_id != interaction.user.id:
            await interaction.response.send_message("Kamu bukan owner room ini.", ephemeral=True, delete_after=8)
            return
        guild = interaction.guild
        vc = guild.get_channel(channel_id)
        if not isinstance(vc, discord.VoiceChannel):
            await interaction.response.send_message("Room not found.", ephemeral=True, delete_after=8)
            return
        try:
            await vc.edit(name=new_name[:100], reason="Room renamed")
            await interaction.response.send_message(f"Room renamed to **{new_name}**", ephemeral=True, delete_after=8)
            await self._update_interface(guild)
        except Exception as e:
            await interaction.response.send_message(f"Failed to rename: {e}", ephemeral=True, delete_after=8)

    async def _handle_limit(self, interaction: discord.Interaction, channel_id: int, limit_str: str):
        room = _get_room_by_channel(interaction.guild_id, channel_id)
        if not room or room.owner_id != interaction.user.id:
            await interaction.response.send_message("Kamu bukan owner room ini.", ephemeral=True, delete_after=8)
            return
        guild = interaction.guild
        vc = guild.get_channel(channel_id)
        if not isinstance(vc, discord.VoiceChannel):
            return
        try:
            limit = int(limit_str)
            if limit < 0:
                limit = 0
            if limit > 99:
                limit = 99
        except ValueError:
            await interaction.response.send_message("Invalid number. Use 0-99.", ephemeral=True, delete_after=8)
            return
        room.limit = limit if limit > 0 else None
        _user_prefs[interaction.user.id] = {
            "locked": room.locked,
            "visible": room.visible,
            "waiting_room": room.waiting_room,
            "limit": room.limit,
            "region": room.region,
        }
        await self._save_user_prefs(interaction.user.id)
        try:
            await vc.edit(user_limit=limit)
            msg = f"User limit set to {limit}" if limit > 0 else "User limit removed (unlimited)"
            await interaction.response.send_message(msg, ephemeral=True, delete_after=8)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True, delete_after=8)

    async def _handle_privacy_action(self, interaction: discord.Interaction, channel_id: int, action: str):
        guild = interaction.guild
        room = _get_room_by_channel(interaction.guild_id, channel_id)
        if not room or room.owner_id != interaction.user.id:
            await interaction.response.send_message("Kamu bukan owner room ini.", ephemeral=True, delete_after=8)
            return
        vc = guild.get_channel(channel_id)
        if not isinstance(vc, discord.VoiceChannel):
            await interaction.response.send_message("Room tidak ditemukan.", ephemeral=True, delete_after=8)
            return
        try:
            if action == "lock":
                room.locked = True
                await vc.set_permissions(guild.default_role, connect=False)
                await interaction.response.send_message("\U0001f512 Room dikunci", ephemeral=True, delete_after=8)
            elif action == "unlock":
                room.locked = False
                await vc.set_permissions(guild.default_role, connect=True)
                await interaction.response.send_message("\U0001f513 Room dibuka", ephemeral=True, delete_after=8)
            elif action == "hide":
                room.visible = False
                await vc.set_permissions(guild.default_role, view_channel=False)
                await interaction.response.send_message("\U0001f648 Room disembunyikan", ephemeral=True, delete_after=8)
            elif action == "show":
                room.visible = True
                await vc.set_permissions(guild.default_role, view_channel=True)
                await interaction.response.send_message("\U0001f441\ufe0f Room ditampilkan", ephemeral=True, delete_after=8)
            elif action == "open_chat":
                if room.chat_channel_id:
                    await interaction.response.send_message("Chat sudah terbuka.", ephemeral=True, delete_after=8)
                else:
                    chat = await guild.create_text_channel(
                        f"\U0001f4ac-{vc.name[:20]}",
                        category=vc.category,
                        reason="Voice room chat",
                    )
                    room.chat_channel_id = chat.id
                    await interaction.response.send_message(f"\U0001f4ac Chat dibuat: {chat.mention}", ephemeral=True, delete_after=8)
            elif action == "close_chat":
                if not room.chat_channel_id:
                    await interaction.response.send_message("Belum ada chat.", ephemeral=True, delete_after=8)
                else:
                    chat = guild.get_channel(room.chat_channel_id)
                    if chat:
                        await chat.delete(reason="Voice chat closed")
                    room.chat_channel_id = None
                    await interaction.response.send_message("\U0001f515 Chat ditutup", ephemeral=True, delete_after=8)
            _user_prefs[interaction.user.id] = {
                "locked": room.locked,
                "visible": room.visible,
                "waiting_room": room.waiting_room,
                "limit": room.limit,
                "region": room.region,
            }
            await self._save_user_prefs(interaction.user.id)
            await self._update_interface(guild)
        except Exception as e:
            log.error(f"Privacy action error: {e}")
            try:
                await interaction.response.send_message(f"Gagal: {e}", ephemeral=True, delete_after=8)
            except Exception:
                try:
                    await interaction.followup.send(f"Gagal: {e}", ephemeral=True, delete_after=8)
                except Exception:
                    pass

    async def _handle_waiting_toggle(self, interaction: discord.Interaction, room: VoiceRoom):
        guild = interaction.guild
        room.waiting_room = not room.waiting_room
        if not room.waiting_room:
            for uid in room.waiting_users:
                m = guild.get_member(uid)
                if m:
                    try:
                        await m.edit(mute=False)
                    except Exception:
                        pass
            room.waiting_users.clear()
        _user_prefs[interaction.user.id] = {
            "locked": room.locked,
            "visible": room.visible,
            "waiting_room": room.waiting_room,
            "limit": room.limit,
            "region": room.region,
        }
        await self._save_user_prefs(interaction.user.id)
        status = "\U0001f6aa Waiting Room: On" if room.waiting_room else "\U0001f6aa Waiting Room: Off"
        await interaction.response.send_message(status, ephemeral=True, delete_after=8)
        await self._update_interface(guild)

    async def _handle_member_select(self, interaction: discord.Interaction, action: str, channel_id: int, target_id: int):
        guild = interaction.guild
        room = _get_room_by_channel(interaction.guild_id, channel_id)
        if not room or room.owner_id != interaction.user.id:
            await interaction.response.send_message("Kamu bukan owner room ini.", ephemeral=True, delete_after=8)
            return
        vc = guild.get_channel(channel_id)
        if not isinstance(vc, discord.VoiceChannel):
            return
        target = guild.get_member(target_id)
        if not target:
            await interaction.response.send_message("User not found.", ephemeral=True, delete_after=8)
            return

        try:
            if action == "trust":
                room.trusted_users.add(target_id)
                await vc.set_permissions(target, connect=True, speak=True)
                await interaction.response.send_message(f"\u2705 {target.display_name} ditambahkan sebagai trusted", ephemeral=True, delete_after=8)
            elif action == "untrust":
                room.trusted_users.discard(target_id)
                await vc.set_permissions(target, overwrite=None)
                await interaction.response.send_message(f"\u274c {target.display_name} di-untrust", ephemeral=True, delete_after=8)
            elif action == "kick":
                await target.move_to(None)
                await interaction.response.send_message(f"\U0001f50a {target.display_name} di-kick dari room", ephemeral=True, delete_after=8)
                room.trusted_users.discard(target_id)
            elif action == "unblock":
                room.blocked_users.discard(target_id)
                await vc.set_permissions(target, overwrite=None)
                await interaction.response.send_message(f"\U0001f513 {target.display_name} di-unblock", ephemeral=True, delete_after=8)
            elif action == "transfer":
                is_premium = await _check_premium(interaction.guild_id, interaction.user.id)
                if not is_premium:
                    await interaction.response.send_message("\u2b50 Premium feature.", ephemeral=True, delete_after=8)
                    return
                room.owner_id = target_id
                room.owner_left_at = None
                await interaction.response.send_message(f"\U0001f4e4 Ownership transferred to {target.display_name}", ephemeral=True, delete_after=8)
            await self._update_interface(guild)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True, delete_after=8)

    async def _handle_user_id_modal(self, interaction: discord.Interaction, channel_id: int, action: str, user_id_str: str):
        room = _get_room_by_channel(interaction.guild_id, channel_id)
        if not room or room.owner_id != interaction.user.id:
            await interaction.response.send_message("Kamu bukan owner room ini.", ephemeral=True, delete_after=8)
            return
        guild = interaction.guild
        vc = guild.get_channel(channel_id)
        if not isinstance(vc, discord.VoiceChannel):
            return
        try:
            target_id = int(user_id_str.strip())
        except ValueError:
            await interaction.response.send_message("Invalid user ID.", ephemeral=True, delete_after=8)
            return
        target = guild.get_member(target_id)
        if not target:
            await interaction.response.send_message("User not found in server.", ephemeral=True, delete_after=8)
            return

        try:
            if action == "Invite":
                await vc.set_permissions(target, connect=True)
                room.trusted_users.add(target_id)
                await interaction.response.send_message(f"\U0001f4e8 {target.display_name} di-invite ke room", ephemeral=True, delete_after=8)
            elif action == "Block":
                room.blocked_users.add(target_id)
                room.trusted_users.discard(target_id)
                await vc.set_permissions(target, connect=False)
                if target.id in room.members:
                    await target.move_to(None)
                await interaction.response.send_message(f"\U0001f6ab {target.display_name} di-block dari room", ephemeral=True, delete_after=8)
            await self._update_interface(guild)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True, delete_after=8)

    async def _handle_region(self, interaction: discord.Interaction, room: VoiceRoom, region_str: str):
        guild = interaction.guild
        vc = guild.get_channel(room.channel_id)
        if not isinstance(vc, discord.VoiceChannel):
            return
        try:
            rtc_region = None if region_str == "auto" else discord.VoiceRegion(region_str)
            await vc.edit(rtc_region=rtc_region)
            room.region = region_str
            _user_prefs[interaction.user.id] = {
                "locked": room.locked,
                "visible": room.visible,
                "waiting_room": room.waiting_room,
                "limit": room.limit,
                "region": room.region,
            }
            await self._save_user_prefs(interaction.user.id)
            await interaction.response.send_message(f"\U0001f310 Region set to {region_str}", ephemeral=True, delete_after=8)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True, delete_after=8)

    async def _handle_delete_room(self, interaction: discord.Interaction, channel_id: int):
        room = _get_room_by_channel(interaction.guild_id, channel_id)
        if not room or room.owner_id != interaction.user.id:
            await interaction.response.send_message("Kamu bukan owner room ini.", ephemeral=True, delete_after=8)
            return
        await self._delete_room(channel_id, interaction.guild_id)
        await interaction.response.send_message("\U0001f5d1\ufe0f Room deleted.", ephemeral=True, delete_after=8)

    async def _handle_claim(self, interaction: discord.Interaction, room: VoiceRoom):
        if not room.owner_left_at:
            await interaction.response.send_message("Owner masih aktif di room.", ephemeral=True, delete_after=8)
            return
        if (time.time() - room.owner_left_at) < GRACE_PERIOD:
            remaining = int(GRACE_PERIOD - (time.time() - room.owner_left_at))
            await interaction.response.send_message(f"Owner baru offline {remaining} detik. Tunggu {remaining} detik lagi.", ephemeral=True, delete_after=8)
            return
        is_premium = await _check_premium(interaction.guild_id, interaction.user.id)
        if not is_premium:
            await interaction.response.send_message("\u2b50 Claim adalah fitur premium.", ephemeral=True, delete_after=8)
            return
        room.owner_id = interaction.user.id
        room.owner_left_at = None
        await interaction.response.send_message(f"\U0001f3e6 Kamu sekarang owner dari room ini!", ephemeral=True, delete_after=8)
        await self._update_interface(interaction.guild)


async def setup(bot):
    await bot.add_cog(VoiceInterfaceCog(bot))