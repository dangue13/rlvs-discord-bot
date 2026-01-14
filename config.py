# config.py
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import os
import json
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any


# ============================================================
# Helpers
# ============================================================

def _int_env(name: str, default: int = 0) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer (got {raw!r})")


def _int_env_optional(name: str, default: int = 0) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw or raw.lower() == "standby":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _csv_lower(name: str, default: str) -> list[str]:
    raw = (os.getenv(name) or default or "").strip()
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _csv_int_set(name: str) -> set[int]:
    raw = (os.getenv(name) or "").strip()
    return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}


def _load_json_file(path: Path, default: Any):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# ============================================================
# Org affiliations (Champion first, Challenger second)
# ============================================================

ORG_AFFILIATIONS: dict[str, list[str]] = {
    "angels":      ["Angels", "Saints"],
    "devils":      ["Devils", "Demons"],
    "dragons":     ["Dragons", "Dracos"],
    "reapers":     ["Reapers", "Ghouls"],
    "lumberjacks": ["Lumberjacks", "Miners"],
    "tigers":      ["Tigers", "Panthers"],
    "ninjas":      ["Ninjas", "Samurais"],
    "orcas":       ["Orcas", "Sharks"],
    "rockets":     ["Rockets", "Astronauts"],
    "spartans":    ["Spartans", "Warriors"],
}


# ============================================================
# Settings
# ============================================================

@dataclass(frozen=True)
class Settings:
    # Discord
    discord_token: str
    guild_id: int
    poll_seconds: int

    # Standings URLs
    champion_standings_url: str
    challenger_standings_url: str

    # Standings Channels
    champion_standings_channel_id: int
    challenger_standings_channel_id: int

    # Permissions / Roles
    bypass_scheduler_permissions: bool
    dev_user_ids: set[int]
    commissioner_roles: list[str]
    gm_roles: list[str]

    # Misc
    league_tz: object
    state_path: Path
    headers: dict[str, str]

    # Org Match Scheduling
    org_gm_role: str
    gm_org_map_path: Path
    gm_org_map: dict[int, str]
    org_affiliations: dict[str, list[str]]


# ============================================================
# Load settings
# ============================================================

def load_settings() -> Settings:
    discord_token = (os.getenv("DISCORD_TOKEN") or "").strip()
    guild_id = _int_env("GUILD_ID", 0)
    poll_seconds = _int_env("POLL_SECONDS", 180)

    champion_standings_url = (os.getenv("STANDINGS_URL") or "").strip()
    challenger_standings_url = (os.getenv(
        "CHALLENGER_STANDINGS_URL",
        ""
    ) or "").strip()

    champion_channel_id = _int_env_optional("CHAMPION_STANDINGS_CHANNEL_ID", 0)
    challenger_channel_id = _int_env_optional("CHALLENGER_STANDINGS_CHANNEL_ID", 0)

    bypass = _bool_env("BYPASS_SCHEDULER_PERMISSIONS", False)
    dev_user_ids = _csv_int_set("DEV_USER_IDS")

    commissioner_roles = _csv_lower("COMMISSIONER_ROLES", "Commissioner")
    gm_roles = _csv_lower("GM_ROLES", "GM")

    tz_name = (os.getenv("LEAGUE_TZ", "America/New_York") or "").strip()
    try:
        league_tz = ZoneInfo(tz_name)
    except Exception:
        league_tz = timezone.utc

    state_path = Path(os.getenv("STATE_PATH", "state.json"))

    # ---- Org GM scheduling ----
    org_gm_role = (os.getenv("ORG_GM_ROLE", "Org GM") or "").strip().lower()

    gm_org_map_path = Path(os.getenv("GM_ORG_MAP_PATH", "gm_orgs.json"))
    raw_orgs = _load_json_file(gm_org_map_path, {})

    gm_org_map: dict[int, str] = {}
    if isinstance(raw_orgs, dict):
        for uid, org in raw_orgs.items():
            try:
                uid_int = int(uid)
            except Exception:
                continue
            if isinstance(org, str) and org.strip():
                gm_org_map[uid_int] = org.strip()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    # ---- Validation ----
    if not discord_token:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")

    if not champion_standings_url:
        raise RuntimeError("Missing STANDINGS_URL in .env")

    if poll_seconds < 30:
        raise RuntimeError("POLL_SECONDS must be at least 30 seconds")

    if guild_id == 0:
        print("⚠️  Tip: set GUILD_ID for instant slash-command sync")

    return Settings(
        discord_token=discord_token,
        guild_id=guild_id,
        poll_seconds=poll_seconds,
        champion_standings_url=champion_standings_url,
        challenger_standings_url=challenger_standings_url,
        champion_standings_channel_id=champion_channel_id,
        challenger_standings_channel_id=challenger_channel_id,
        bypass_scheduler_permissions=bypass,
        dev_user_ids=dev_user_ids,
        commissioner_roles=commissioner_roles,
        gm_roles=gm_roles,
        league_tz=league_tz,
        state_path=state_path,
        headers=headers,
        org_gm_role=org_gm_role,
        gm_org_map_path=gm_org_map_path,
        gm_org_map=gm_org_map,
        org_affiliations=ORG_AFFILIATIONS,
    )


settings = load_settings()
