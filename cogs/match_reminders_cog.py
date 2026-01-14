# cogs/match_reminders_cog.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands, tasks

from config import settings
from storage import store

TZ = settings.league_tz if getattr(settings, "league_tz", None) else timezone.utc


def _load_matches() -> List[Dict[str, Any]]:
    return store.get_scheduled_matches()


def _save_matches(matches: List[Dict[str, Any]]) -> None:
    store.save_scheduled_matches(matches)


def _parse_dt(m: Dict[str, Any]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(m.get("scheduled_iso", "")))
    except Exception:
        return None


def _role_mention(guild: discord.Guild, role_name: str) -> str:
    rn = (role_name or "").strip().lower()
    if not rn:
        return role_name
    role = discord.utils.find(lambda r: (r.name or "").strip().lower() == rn, guild.roles)
    return role.mention if role else role_name


class MatchRemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not self.reminder_loop.is_running():
            self.reminder_loop.start()

    def cog_unload(self):
        if self.reminder_loop.is_running():
            self.reminder_loop.cancel()

    @tasks.loop(seconds=60)
    async def reminder_loop(self):
        matches = _load_matches()
        if not matches:
            return

        now = datetime.now(TZ)

        changed = False

        for m in matches:
            dt = _parse_dt(m)
            if not dt:
                continue

            # Skip past matches (but keep record)
            if dt <= now:
                continue

            guild_id = int(m.get("guild_id") or 0)
            channel_id = int(m.get("channel_id") or 0)
            if guild_id == 0 or channel_id == 0:
                continue

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                try:
                    guild = await self.bot.fetch_guild(guild_id)
                except Exception:
                    continue

            channel = guild.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    continue

            if not isinstance(channel, discord.TextChannel):
                continue

            reminders_sent: Dict[str, Any] = m.get("reminders_sent") if isinstance(m.get("reminders_sent"), dict) else {}
            if not isinstance(reminders_sent, dict):
                reminders_sent = {}

            team = str(m.get("team", "")).strip()
            opp = str(m.get("opponent", "")).strip()
            league = str(m.get("league", "")).strip()
            mid = str(m.get("id", "")).strip()

            # thresholds
            rules = [
                ("24h", timedelta(hours=24)),
                ("1h", timedelta(hours=1)),
            ]

            for key, delta in rules:
                if reminders_sent.get(key):
                    continue

                if now >= dt - delta:
                    # send reminder
                    team_mention = _role_mention(guild, team)
                    opp_mention = _role_mention(guild, opp)
                    ts = int(dt.timestamp()) if dt.tzinfo else None

                    msg = (
                        f"⏰ **Match Reminder ({key})** — `{league}` — ID `{mid}`\n"
                        f"{team_mention} vs {opp_mention}\n"
                        f"When: <t:{ts}:F> (<t:{ts}:R>)"
                    )

                    try:
                        await channel.send(msg)
                        reminders_sent[key] = True
                        m["reminders_sent"] = reminders_sent
                        changed = True
                    except Exception:
                        # Don’t mark as sent if we failed to post
                        pass

        if changed:
            _save_matches(matches)

    @reminder_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


# ============================================================
# Setup
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(MatchRemindersCog(bot))



