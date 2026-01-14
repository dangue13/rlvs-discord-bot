# ============================================================
# cogs/match_scheduler_cog.py
# ============================================================

from __future__ import annotations

import re
import secrets
import time
from datetime import datetime, timezone
from difflib import get_close_matches
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from leagues import configured_leagues, League
from storage import store
from cogs.scheduling_cog import update_schedule_board, post_matches_for_league

from services.http import http
from services.standings import parse_standings


# ============================================================
# Constants
# ============================================================

TZ = settings.league_tz if getattr(settings, "league_tz", None) else timezone.utc

_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})\s*$")
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([ap]m)\s*$", re.I)

_TEAM_CACHE: dict[str, Tuple[float, List[str]]] = {}
_TEAM_CACHE_TTL_SECONDS = 10 * 60


# ============================================================
# Permission Helpers
# ============================================================

def _has_role_name(member: discord.Member, role_name_lower: str) -> bool:
    want = (role_name_lower or "").strip().lower()
    return any((r.name or "").strip().lower() == want for r in member.roles)


def _has_any_role_names(member: discord.Member, role_names_lower: List[str]) -> bool:
    want = {x.strip().lower() for x in role_names_lower or [] if x.strip()}
    return any((r.name or "").strip().lower() in want for r in member.roles)


def _is_dev(member: discord.Member) -> bool:
    return int(member.id) in set(settings.dev_user_ids or set())


def _is_commissioner(member: discord.Member) -> bool:
    return _has_any_role_names(member, settings.commissioner_roles)


def _is_org_gm(member: discord.Member) -> bool:
    return _has_role_name(member, settings.org_gm_role)


def _can_use_scheduler(member: discord.Member) -> bool:
    if getattr(settings, "bypass_scheduler_permissions", False):
        return True
    return _is_dev(member) or _is_commissioner(member) or _is_org_gm(member)


# ============================================================
# League Helpers
# ============================================================

def _league_by_key_or_name(value: str) -> League:
    v = (value or "").strip().lower()
    for lg in configured_leagues():
        if lg.key.lower() == v or lg.name.lower() == v:
            return lg
    raise ValueError(f"Unknown league '{value}'.")


def _league_choices() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=lg.name, value=lg.key) for lg in configured_leagues()]


# ============================================================
# Standings Integration (Autocomplete)
# ============================================================

async def _team_names_for_league(league: League) -> List[str]:
    key = league.key.lower()
    now = time.time()

    cached = _TEAM_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]

    html = await http.fetch_html(league.standings_url)
    rows = parse_standings(html)
    names = [team.strip() for (_r, team, *_rest) in rows if team.strip()]

    uniq: List[str] = []
    seen = set()
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(n)

    _TEAM_CACHE[key] = (now + _TEAM_CACHE_TTL_SECONDS, uniq)
    return uniq


async def _team_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    league_val = getattr(interaction.namespace, "league", None)
    if not league_val:
        return []

    try:
        lg = _league_by_key_or_name(str(league_val))
    except Exception:
        return []

    options = await _team_names_for_league(lg)
    if not options:
        return []

    q = (current or "").strip()
    if not q:
        return [app_commands.Choice(name=o, value=o) for o in options[:25]]

    close = get_close_matches(q, options, n=25, cutoff=0.2)
    return [app_commands.Choice(name=o, value=o) for o in close[:25]]


# ============================================================
# Date / Time Parsing
# ============================================================

def _parse_mmdd_time(date_mmdd: str, time_str: str) -> datetime:
    m = _DATE_RE.match(date_mmdd)
    t = _TIME_RE.match(time_str)
    if not m or not t:
        raise ValueError(
            "Invalid date or time format. Use M/D and H:MMam/pm (e.g. 1/14 and 9:30pm)."
        )

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


# ============================================================
# Storage Helpers
# ============================================================

def _load_matches() -> List[Dict[str, Any]]:
    return store.get_scheduled_matches()


def _save_matches(matches: List[Dict[str, Any]]) -> None:
    store.save_scheduled_matches(matches)


def _new_match_id(existing: set[str]) -> str:
    while True:
        mid = secrets.token_hex(3).upper()
        if mid not in existing:
            return mid


def _find_match(
    matches: List[Dict[str, Any]],
    match_id: str,
) -> Optional[Dict[str, Any]]:
    mid = match_id.strip().upper()
    return next(
        (m for m in matches if str(m.get("id", "")).upper() == mid),
        None,
    )


# ============================================================
# Cog
# ============================================================

class MatchSchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----------------------------
    # /schedule
    # ----------------------------
    @app_commands.guilds(discord.Object(id=settings.guild_id))
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

        if not isinstance(interaction.user, discord.Member):
            return

        member = interaction.user
        if not _can_use_scheduler(member):
            return await interaction.followup.send("Permission denied.", ephemeral=True)

        lg = _league_by_key_or_name(league)
        when = _parse_mmdd_time(date, time)

        matches = _load_matches()
        match_id = _new_match_id({str(m.get("id", "")).upper() for m in matches})

        guild_id = int(interaction.guild_id or 0)
        league_key = lg.key.lower()

        rec = {
            "id": match_id,
            "league": league_key,
            "week": store.get_current_week(guild_id, league_key),
            "team": team,
            "opponent": opponent,
            "scheduled_iso": when.isoformat(),
            "guild_id": guild_id,
            "created_by": int(member.id),
        }

        matches.append(rec)
        _save_matches(matches)

        await update_schedule_board(self.bot, guild_id, league_key)

        await interaction.followup.send(
            f"✅ **{team}** vs **{opponent}** scheduled for <t:{int(when.timestamp())}:F>",
            ephemeral=True,
        )

    # ----------------------------
    # /postmatches
    # ----------------------------
    @app_commands.guilds(discord.Object(id=settings.guild_id))
    @app_commands.command(
        name="postmatches",
        description="Post scheduled matches for all leagues",
    )
    async def postmatches(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild_id = int(interaction.guild_id or 0)
        for lg in configured_leagues():
            await post_matches_for_league(self.bot, guild_id, lg.key)

        await interaction.followup.send(
            "✅ Match boards posted/updated.",
            ephemeral=True,
        )

    # ----------------------------
    # /cancelmatch
    # ----------------------------
    @app_commands.guilds(discord.Object(id=settings.guild_id))
    @app_commands.command(
        name="cancelmatch",
        description="Cancel a scheduled match by ID",
    )
    async def cancelmatch(self, interaction: discord.Interaction, match_id: str):
        await interaction.response.defer(ephemeral=True)

        matches = _load_matches()
        m = _find_match(matches, match_id)
        if not m:
            return await interaction.followup.send(
                "Match not found.",
                ephemeral=True,
            )

        guild_id = int(interaction.guild_id or 0)
        league_key = str(m.get("league", "")).lower()

        new_matches = [
            x for x in matches
            if str(x.get("id", "")).upper() != str(m.get("id", "")).upper()
        ]
        _save_matches(new_matches)

        await update_schedule_board(self.bot, guild_id, league_key)

        await interaction.followup.send(
            f"🗑️ Match `{match_id.strip().upper()}` cancelled.",
            ephemeral=True,
        )


# ============================================================
# Setup
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(MatchSchedulerCog(bot))
