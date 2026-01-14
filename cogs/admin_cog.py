# cogs/admin_cog.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from storage import store


def _is_admin(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not interaction.user:
        return False
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_guild


@dataclass
class _ChannelTarget:
    kind: Literal["standings", "schedule", "logs", "announcements"]
    league_key: Optional[Literal["champion", "challenger"]] = None


def _fmt_channel(ch_id: Optional[int]) -> str:
    return f"<#{ch_id}>" if ch_id else "Not set"


def _build_status(guild_id: int) -> str:
    champ_st = store.get_standings_channel(guild_id, "champion")
    chal_st = store.get_standings_channel(guild_id, "challenger")
    champ_sched = store.get_schedule_channel(guild_id, "champion")
    chal_sched = store.get_schedule_channel(guild_id, "challenger")
    logs = store.get_logs_channel(guild_id)
    ann = store.get_announcements_channel(guild_id)

    lines = [
        f"**Standings (Champion):** {_fmt_channel(champ_st)}",
        f"**Standings (Challenger):** {_fmt_channel(chal_st)}",
        f"**Schedule (Champion):** {_fmt_channel(champ_sched)}",
        f"**Schedule (Challenger):** {_fmt_channel(chal_sched)}",
        f"**Logs:** {_fmt_channel(logs)}",
        f"**Announcements:** {_fmt_channel(ann)}",
    ]
    return "\n".join(lines)


def _target_label(t: Optional[_ChannelTarget]) -> str:
    if not t:
        return "None selected"
    if t.kind == "standings":
        return f"Standings — {t.league_key}"
    if t.kind == "schedule":
        return f"Schedule — {t.league_key}"
    return t.kind.capitalize()


class _AdminChannelsView(discord.ui.View):
    def __init__(self, guild_id: int, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.target: Optional[_ChannelTarget] = None
        self.selected_channel_id: Optional[int] = None

        self.add_item(_TargetSelect(self))
        self.add_item(_ChannelSelect(self))
        self.add_item(_SaveButton(self))
        self.add_item(_CloseButton(self))

    def render_content(self) -> str:
        return (
            "## Admin Channel Setup\n"
            f"**Selected target:** `{_target_label(self.target)}`\n"
            f"**Selected channel:** {_fmt_channel(self.selected_channel_id)}\n\n"
            "### Current configuration\n"
            f"{_build_status(self.guild_id)}\n\n"
            "_Tip: Choose a target, pick a channel, then press **Save**._"
        )


class _TargetSelect(discord.ui.Select):
    def __init__(self, parent: _AdminChannelsView):
        self.parent_view = parent
        options = [
            discord.SelectOption(label="Standings — Champion", value="standings:champion"),
            discord.SelectOption(label="Standings — Challenger", value="standings:challenger"),
            discord.SelectOption(label="Schedule — Champion", value="schedule:champion"),
            discord.SelectOption(label="Schedule — Challenger", value="schedule:challenger"),
            discord.SelectOption(label="Logs", value="logs"),
            discord.SelectOption(label="Announcements", value="announcements"),
        ]
        super().__init__(
            placeholder="What do you want to configure?",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        raw = self.values[0]

        if raw.startswith("standings:"):
            league = raw.split(":", 1)[1]
            self.parent_view.target = _ChannelTarget(kind="standings", league_key=league)  # type: ignore[arg-type]
        elif raw.startswith("schedule:"):
            league = raw.split(":", 1)[1]
            self.parent_view.target = _ChannelTarget(kind="schedule", league_key=league)  # type: ignore[arg-type]
        elif raw == "logs":
            self.parent_view.target = _ChannelTarget(kind="logs")
        else:
            self.parent_view.target = _ChannelTarget(kind="announcements")

        await interaction.response.edit_message(
            content=self.parent_view.render_content(),
            view=self.parent_view,
        )


class _ChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent: _AdminChannelsView):
        self.parent_view = parent
        super().__init__(
            placeholder="Pick a channel…",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
        )

    async def callback(self, interaction: discord.Interaction):
        ch = self.values[0]
        self.parent_view.selected_channel_id = ch.id
        await interaction.response.edit_message(
            content=self.parent_view.render_content(),
            view=self.parent_view,
        )


class _SaveButton(discord.ui.Button):
    def __init__(self, parent: _AdminChannelsView):
        self.parent_view = parent
        super().__init__(label="Save", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        t = self.parent_view.target
        ch_id = self.parent_view.selected_channel_id

        if not t:
            await interaction.response.send_message("Pick **what** you’re configuring first.", ephemeral=True)
            return
        if not ch_id:
            await interaction.response.send_message("Pick a **channel** first.", ephemeral=True)
            return

        guild_id = self.parent_view.guild_id

        if t.kind == "standings":
            store.set_standings_channel(guild_id, t.league_key, ch_id)
            msg = f"✅ Saved: **Standings ({t.league_key})** → <#{ch_id}>"
        elif t.kind == "schedule":
            store.set_schedule_channel(guild_id, t.league_key, ch_id)
            msg = f"✅ Saved: **Schedule ({t.league_key})** → <#{ch_id}>"
        elif t.kind == "logs":
            store.set_logs_channel(guild_id, ch_id)
            msg = f"✅ Saved: **Logs** → <#{ch_id}>"
        else:
            store.set_announcements_channel(guild_id, ch_id)
            msg = f"✅ Saved: **Announcements** → <#{ch_id}>"

        await interaction.response.edit_message(
            content=self.parent_view.render_content(),
            view=self.parent_view,
        )
        await interaction.followup.send(msg, ephemeral=True)


class _CloseButton(discord.ui.Button):
    def __init__(self, parent: _AdminChannelsView):
        self.parent_view = parent
        super().__init__(label="Close", style=discord.ButtonStyle.gray)

    async def callback(self, interaction: discord.Interaction):
        for item in self.parent_view.children:
            item.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(
            content="✅ Closed admin channel setup.",
            view=self.parent_view,
        )


class AdminsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="List all bot commands")
    async def help(self, interaction: discord.Interaction):
        cmds = sorted(self.bot.tree.get_commands(), key=lambda c: c.name)

        lines = []
        for c in cmds:
            desc = c.description or "No description"
            lines.append(f"**/{c.name}** — {desc}")

        embed = discord.Embed(
            title="📖 Bot Commands",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="admin_channels",
        description="Interactive setup for bot channels (standings/schedule/logs/announcements)",
    )
    async def admin_channels(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        view = _AdminChannelsView(interaction.guild_id)
        await interaction.response.send_message(view.render_content(), ephemeral=True, view=view)

    @app_commands.command(name="admin_status", description="Show current bot channel configuration")
    async def admin_status(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.send_message(
            "## Current configuration\n" + _build_status(interaction.guild_id),
            ephemeral=True,
        )

    @app_commands.command(name="resync", description="Resync slash commands (admin only)")
    async def resync(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        guild_id = getattr(settings, "guild_id", None) or interaction.guild_id

        try:
            if guild_id:
                await self.bot.tree.sync(guild=discord.Object(id=int(guild_id)))
                await interaction.followup.send(f"✅ Resynced commands to guild `{guild_id}`.", ephemeral=True)
            else:
                await self.bot.tree.sync()
                await interaction.followup.send("✅ Resynced commands globally.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Resync failed: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminsCog(bot))
