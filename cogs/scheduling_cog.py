from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands, tasks

from storage import store


NY = ZoneInfo("America/New_York")
LEAGUES = ["champion", "challenger"]


def _is_admin(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.administrator or perms.manage_guild


def _match_line(m: Dict[str, Any]) -> str:
    # Expect keys like: "home", "away", "when" (ISO string) or "time"
    home = m.get("home", "TBD")
    away = m.get("away", "TBD")

    when = m.get("when") or m.get("time") or ""
    # Keep it flexible; display raw if it isn't parseable
    try:
        dt = datetime.fromisoformat(when)
        when_str = dt.astimezone(NY).strftime("%a %b %d, %I:%M %p ET")
    except Exception:
        when_str = str(when) if when else "Time TBD"

    return f"• **{home}** vs **{away}** — {when_str}"


def _render_schedule(guild_id: int, league_key: str) -> str:
    week = store.get_current_week(guild_id, league_key)

    # Your scheduled_matches is currently global list[dict]
    matches = store.get_scheduled_matches()

    # Filter by guild + league if present; otherwise include anything league-matching
    filtered: List[Dict[str, Any]] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        if m.get("league") != league_key:
            continue
        # If you store guild_id in match dicts, honor it; otherwise show all
        mgid = m.get("guild_id")
        if mgid is not None and int(mgid) != int(guild_id):
            continue
        # If you store week in match dicts, honor it; otherwise assume current week
        mw = m.get("week")
        if mw is not None:
            try:
                if int(mw) != int(week):
                    continue
            except Exception:
                pass
        filtered.append(m)

    filtered.sort(key=lambda x: str(x.get("when") or x.get("time") or ""))

    header = f"## {league_key.capitalize()} League — Week {week}\n"
    sub = "_This message updates automatically when matches are scheduled or cancelled._\n\n"

    if not filtered:
        body = "No matches scheduled yet for this week.\n"
    else:
        body = "\n".join(_match_line(m) for m in filtered) + "\n"

    footer = f"\n_Last updated: {datetime.now(NY).strftime('%Y-%m-%d %I:%M %p ET')}_"
    return header + sub + body + footer


async def _ensure_schedule_message(
    bot: commands.Bot, guild_id: int, league_key: str
) -> Optional[discord.Message]:
    channel_id = store.get_schedule_channel(guild_id, league_key)
    if not channel_id:
        return None

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return None

    if not isinstance(channel, discord.TextChannel):
        return None

    msg_id = store.get_schedule_message_id(guild_id, league_key)
    if msg_id:
        try:
            return await channel.fetch_message(msg_id)
        except Exception:
            # message deleted or not accessible -> recreate
            pass

    content = _render_schedule(guild_id, league_key)
    msg = await channel.send(content)
    store.set_schedule_message_id(guild_id, league_key, msg.id)
    return msg


async def update_schedule_board(bot: commands.Bot, guild_id: int, league_key: str) -> None:
    msg = await _ensure_schedule_message(bot, guild_id, league_key)
    if not msg:
        return
    content = _render_schedule(guild_id, league_key)
    try:
        await msg.edit(content=content)
    except Exception:
        # If editing fails, recreate it once
        try:
            new_msg = await msg.channel.send(content)
            store.set_schedule_message_id(guild_id, league_key, new_msg.id)
        except Exception:
            return


class SchedulingCog(commands.Cog):
    """
    Keeps one schedule-board message updated per league.
    Also rolls week number forward every Sunday (ET).
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_rollover.start()

    def cog_unload(self):
        self.weekly_rollover.cancel()

    @tasks.loop(time=time(hour=0, minute=5, tzinfo=NY))
    async def weekly_rollover(self):
        # Runs every day at 00:05 ET; only acts on Sundays
        now = datetime.now(NY)
        if now.weekday() != 6:  # Sunday = 6
            return

        for guild in self.bot.guilds:
            for league_key in LEAGUES:
                current = store.get_current_week(guild.id, league_key)
                store.set_current_week(guild.id, league_key, current + 1)
                await update_schedule_board(self.bot, guild.id, league_key)

    @weekly_rollover.before_loop
    async def before_weekly_rollover(self):
        await self.bot.wait_until_ready()

    # Optional admin command to force update (handy for testing)
    @commands.hybrid_command(name="force_schedule_update")
    async def force_schedule_update(self, ctx: commands.Context, league: str):
        if not isinstance(ctx.author, discord.Member) or not _is_admin(ctx.author):
            await ctx.reply("❌ Admins only.", ephemeral=True)  # ephemeral works only for interactions; ok anyway
            return

        league = league.lower().strip()
        if league not in LEAGUES:
            await ctx.reply("League must be: champion or challenger")
            return

        await update_schedule_board(self.bot, ctx.guild.id, league)
        await ctx.reply("✅ Schedule board updated.")
        

async def setup(bot: commands.Bot):
    await bot.add_cog(SchedulingCog(bot))
