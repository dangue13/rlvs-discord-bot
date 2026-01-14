# cogs/match_scheduler_cog.py
from __future__ import annotations

import re
import secrets
import time
from datetime import datetime, timezone
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from leagues import configured_leagues, League
from storage import store
from cogs.scheduling_cog import update_schedule_board, post_matches_for_league

from services.http import http
from services.standings import parse_standings

TZ = settings.league_tz if getattr(settings, "league_tz", None) else timezone.utc

_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})\s*$")
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([ap]m)\s*$", re.I)

_TEAM_CACHE: dict[str, tuple[float, List[str]]] = {}
_TEAM_CACHE_TTL_SECONDS = 10 * 60


def _league_choices() -> List[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=lg.name, value=lg.key)
        for lg in configured_leagues()
    ]


async def _team_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    league_key = interaction.namespace.league
    lg = next(l for l in configured_leagues() if l.key == league_key)

    now = time.time()
    cached = _TEAM_CACHE.get(lg.key)
    if not cached or cached[0] < now:
        html = await http.fetch_html(lg.standings_url)
        rows = parse_standings(html)
        names = sorted({team for (_r, team, *_rest) in rows})
        _TEAM_CACHE[lg.key] = (now + _TEAM_CACHE_TTL_SECONDS, names)
    else:
        names = cached[1]

    matches = get_close_matches(current, names, n=10, cutoff=0.0)
    return [app_commands.Choice(name=n, value=n) for n in matches[:10]]


def _parse_mmdd_time(date_mmdd: str, time_str: str) -> datetime:
    m = _DATE_RE.match(date_mmdd)
    t = _TIME_RE.match(time_str)
    if not m or not t:
        raise ValueError("Invalid date or time format.")

    month, day = int(m[1]), int(m[2])
    hour, minute, ampm = int(t[1]), int(t[2]), t[3].lower()

    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0

    now = datetime.now(TZ)
    dt = datetime(now.year, month, day, hour, minute, tzinfo=TZ)
    if dt.date() < now.date():
        dt = dt.replace(year=now.year + 1)
    return dt


def _load_matches() -> List[Dict[str, Any]]:
    return store.get_scheduled_matches()


def _save_matches(matches: List[Dict[str, Any]]) -> None:
    store.save_scheduled_matches(matches)


def _new_match_id(existing: set[str]) -> str:
    while True:
        mid = secrets.token_hex(3).upper()
        if mid not in existing:
            return mid


class MatchSchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="schedule", description="Schedule a match")
    @app_commands.choices(league=_league_choices())
    @app_commands.autocomplete(team=_team_autocomplete, opponent=_team_autocomplete)
    async def schedule(
        self,
        interaction: discord.Interaction,
        league: str,
        team: str,
        opponent: str,
        date: str,
        time: str,
    ):
        await interaction.response.defer(ephemeral=True)

        lg = next(l for l in configured_leagues() if l.key == league)
        when = _parse_mmdd_time(date, time)

        matches = _load_matches()
        match_id = _new_match_id({m["id"] for m in matches})

        guild_id = int(interaction.guild_id or 0)

        rec = {
            "id": match_id,
            "league": lg.key,
            "week": store.get_current_week(guild_id, lg.key),
            "team": team,
            "opponent": opponent,
            "scheduled_iso": when.isoformat(),
            "guild_id": guild_id,
            "created_by": int(interaction.user.id),
        }

        matches.append(rec)
        _save_matches(matches)

        await update_schedule_board(self.bot, guild_id, lg.key)

        await interaction.followup.send(
            f"✅ **{team}** vs **{opponent}** scheduled for <t:{int(when.timestamp())}:F>",
            ephemeral=True,
        )

    @app_commands.command(name="postmatches", description="Post scheduled matches for all leagues")
    async def postmatches(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = int(interaction.guild_id or 0)

        for lg in configured_leagues():
            await post_matches_for_league(self.bot, guild_id, lg.key)

        await interaction.followup.send("✅ Match boards posted/updated.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchSchedulerCog(bot))
