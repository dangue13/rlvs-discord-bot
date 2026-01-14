from __future__ import annotations

# ============================================================
# Imports
# ============================================================

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
from cogs.scheduling_cog import update_schedule_board

from services.http import http
from services.standings import parse_standings


# ============================================================
# Timezone & Regex
# ============================================================

TZ = settings.league_tz if getattr(settings, "league_tz", None) else timezone.utc

_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})\s*$")
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([ap]m)\s*$", re.I)


# ============================================================
# Standings Team Cache
# ============================================================

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


def _can_schedule_any_team(member: discord.Member) -> bool:
    return _is_dev(member) or _is_commissioner(member)


def _can_use_scheduler(member: discord.Member) -> bool:
    if settings.bypass_scheduler_permissions:
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


def _league_keys() -> List[str]:
    return [lg.key for lg in configured_leagues()]


# ============================================================
# Org / Affiliation Helpers
# ============================================================

def _gm_org_key(member: discord.Member) -> Optional[str]:
    org = (settings.gm_org_map or {}).get(int(member.id))
    return org.strip().lower() if isinstance(org, str) else None


def _allowed_teams_for_org(org_key: str) -> Optional[List[str]]:
    return list((settings.org_affiliations or {}).get(org_key) or [])


def _all_affiliated_teams() -> List[str]:
    seen = set()
    out = []
    for teams in (settings.org_affiliations or {}).values():
        for t in teams:
            k = t.lower()
            if k not in seen:
                seen.add(k)
                out.append(t)
    return out


def _team_in_allowed(team: str, allowed: List[str]) -> bool:
    t = team.strip().lower()
    return any(t == a.strip().lower() for a in allowed)


# ============================================================
# Standings Integration (Team Validation)
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

    uniq = []
    seen = set()
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(n)

    _TEAM_CACHE[key] = (now + _TEAM_CACHE_TTL_SECONDS, uniq)
    return uniq


def _best_match_hint(name: str, options: List[str]) -> str:
    opts = {o.lower(): o for o in options}
    close = get_close_matches(name.lower(), opts.keys(), n=3, cutoff=0.6)
    return "Did you mean: " + ", ".join(f"**{opts[c]}**" for c in close) + "?" if close else ""


# ============================================================
# Date / Time Parsing
# ============================================================

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


def _find_match(matches: List[Dict[str, Any]], match_id: str) -> Optional[Dict[str, Any]]:
    mid = match_id.strip().upper()
    return next((m for m in matches if str(m.get("id", "")).upper() == mid), None)


# ============================================================
# Match Scheduler Cog
# ============================================================

class MatchSchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="schedule", description="Schedule a match")
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
        match_id = _new_match_id({m["id"] for m in matches})

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

    @app_commands.command(name="cancelmatch", description="Cancel a scheduled match by ID")
    async def cancelmatch(self, interaction: discord.Interaction, match_id: str):
        await interaction.response.defer(ephemeral=True)

        matches = _load_matches()
        m = _find_match(matches, match_id)
        if not m:
            return await interaction.followup.send("Match not found.", ephemeral=True)

        guild_id = int(interaction.guild_id or 0)
        league_key = m["league"]

        new_matches = [x for x in matches if x["id"] != m["id"]]
        _save_matches(new_matches)

        await update_schedule_board(self.bot, guild_id, league_key)

        await interaction.followup.send(f"🗑️ Match `{match_id}` cancelled.", ephemeral=True)


# ============================================================
# Cog Setup
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(MatchSchedulerCog(bot))
