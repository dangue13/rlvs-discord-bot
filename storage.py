# storage.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings

@dataclass
class GuildConfig:
    guild_id: int
    standings_channel_id: Optional[int] = None
    logs_channel_id: Optional[int] = None
    announcements_channel_id: Optional[int] = None
    scheduler_enabled: bool = True


@dataclass
class StateStore:
    path: Path
    _state: Dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "StateStore":
        if not path.exists():
            return cls(path=path, _state={})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return cls(path=path, _state=data)

    def save(self) -> None:
        self.path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    # -------------------------
    # Backward-compatible globals
    # -------------------------
    def get_last_hash_global(self) -> Optional[str]:
        val = self._state.get("last_hash")
        return val if isinstance(val, str) else None

    def set_last_hash_global(self, new_hash: str) -> None:
        self._state["last_hash"] = new_hash
        self.save()

    def get_standings_message_id_global(self) -> Optional[int]:
        val = self._state.get("standings_message_id")
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except Exception:
            return None

    def set_standings_message_id_global(self, message_id: int) -> None:
        self._state["standings_message_id"] = int(message_id)
        self.save()

    # -------------------------
    # Per-guild admin config
    # -------------------------
    def _guild_bucket(self, guild_id: int) -> Dict[str, Any]:
        guilds = self._state.setdefault("guilds", {})
        if not isinstance(guilds, dict):
            guilds = {}
            self._state["guilds"] = guilds

        bucket = guilds.setdefault(str(guild_id), {})
        if not isinstance(bucket, dict):
            bucket = {}
            guilds[str(guild_id)] = bucket
        return bucket

    def get_guild_config(self, guild_id: int) -> GuildConfig:
        b = self._guild_bucket(guild_id)
        return GuildConfig(
            guild_id=guild_id,
            standings_channel_id=b.get("standings_channel_id"),
            logs_channel_id=b.get("logs_channel_id"),
            announcements_channel_id=b.get("announcements_channel_id"),
            scheduler_enabled=bool(b.get("scheduler_enabled", True)),
        )

    def set_channel(self, guild_id: int, channel_type: str, channel_id: int) -> None:
        b = self._guild_bucket(guild_id)
        channel_type = channel_type.lower()

        if channel_type == "standings":
            b["standings_channel_id"] = int(channel_id)
        elif channel_type == "logs":
            b["logs_channel_id"] = int(channel_id)
        elif channel_type == "announcements":
            b["announcements_channel_id"] = int(channel_id)
        else:
            raise ValueError(f"Unknown channel_type: {channel_type}")

        self.save()

    def set_scheduler_enabled(self, guild_id: int, enabled: bool) -> None:
        b = self._guild_bucket(guild_id)
        b["scheduler_enabled"] = bool(enabled)
        self.save()

    def get_channel(self, guild_id: int, channel_type: str) -> Optional[int]:
        cfg = self.get_guild_config(guild_id)
        channel_type = channel_type.lower()

        if channel_type == "standings":
            return cfg.standings_channel_id
        if channel_type == "logs":
            return cfg.logs_channel_id
        if channel_type == "announcements":
            return cfg.announcements_channel_id

        raise ValueError(f"Unknown channel_type: {channel_type}")
    
    # -------------------------
    # Schedule (per guild, per league)
    # -------------------------
    def set_schedule_channel(self, guild_id: int, league_key: str, channel_id: int) -> None:
        b = self._guild_bucket(guild_id)
        schedule_channels = b.setdefault("schedule_channels", {})
        if not isinstance(schedule_channels, dict):
            schedule_channels = {}
            b["schedule_channels"] = schedule_channels

        schedule_channels[str(league_key)] = int(channel_id)
        self.save()

    def get_schedule_channel(self, guild_id: int, league_key: str) -> Optional[int]:
        b = self._guild_bucket(guild_id)
        schedule_channels = b.get("schedule_channels", {})
        if not isinstance(schedule_channels, dict):
            return None
        val = schedule_channels.get(str(league_key))
        try:
            return int(val)
        except Exception:
            return None

    def set_schedule_message_id(self, guild_id: int, league_key: str, message_id: int) -> None:
        b = self._guild_bucket(guild_id)
        msg_ids = b.setdefault("schedule_message_ids", {})
        if not isinstance(msg_ids, dict):
            msg_ids = {}
            b["schedule_message_ids"] = msg_ids

        msg_ids[str(league_key)] = int(message_id)
        self.save()

    def get_schedule_message_id(self, guild_id: int, league_key: str) -> Optional[int]:
        b = self._guild_bucket(guild_id)
        msg_ids = b.get("schedule_message_ids", {})
        if not isinstance(msg_ids, dict):
            return None
        val = msg_ids.get(str(league_key))
        try:
            return int(val)
        except Exception:
            return None

    def get_current_week(self, guild_id: int, league_key: str) -> int:
        b = self._guild_bucket(guild_id)
        weeks = b.setdefault("current_week", {})
        if not isinstance(weeks, dict):
            weeks = {}
            b["current_week"] = weeks

        val = weeks.get(str(league_key), 1)
        try:
            return int(val)
        except Exception:
            return 1

    def set_current_week(self, guild_id: int, league_key: str, week: int) -> None:
        b = self._guild_bucket(guild_id)
        weeks = b.setdefault("current_week", {})
        if not isinstance(weeks, dict):
            weeks = {}
            b["current_week"] = weeks

        weeks[str(league_key)] = int(week)
        self.save()


    
    # -------------------------
    # Per-guild channels (with per-league standings channels)
    # -------------------------
    def _guild_bucket(self, guild_id: int) -> Dict[str, Any]:
        guilds = self._state.setdefault("guilds", {})
        if not isinstance(guilds, dict):
            guilds = {}
            self._state["guilds"] = guilds

        bucket = guilds.setdefault(str(guild_id), {})
        if not isinstance(bucket, dict):
            bucket = {}
            guilds[str(guild_id)] = bucket
        return bucket

    def set_logs_channel(self, guild_id: int, channel_id: int) -> None:
        b = self._guild_bucket(guild_id)
        b["logs_channel_id"] = int(channel_id)
        self.save()

    def get_logs_channel(self, guild_id: int) -> Optional[int]:
        b = self._guild_bucket(guild_id)
        val = b.get("logs_channel_id")
        try:
            return int(val)
        except Exception:
            return None

    def set_announcements_channel(self, guild_id: int, channel_id: int) -> None:
        b = self._guild_bucket(guild_id)
        b["announcements_channel_id"] = int(channel_id)
        self.save()

    def get_announcements_channel(self, guild_id: int) -> Optional[int]:
        b = self._guild_bucket(guild_id)
        val = b.get("announcements_channel_id")
        try:
            return int(val)
        except Exception:
            return None

    def set_standings_channel(self, guild_id: int, league_key: str, channel_id: int) -> None:
        b = self._guild_bucket(guild_id)
        standings_channels = b.setdefault("standings_channels", {})
        if not isinstance(standings_channels, dict):
            standings_channels = {}
            b["standings_channels"] = standings_channels

        standings_channels[str(league_key)] = int(channel_id)
        self.save()

    def get_standings_channel(self, guild_id: int, league_key: str) -> Optional[int]:
        b = self._guild_bucket(guild_id)
        standings_channels = b.get("standings_channels", {})
        if not isinstance(standings_channels, dict):
            return None
        val = standings_channels.get(str(league_key))
        try:
            return int(val)
        except Exception:
            return None

    # -------------------------
    # Per-league standings state
    # -------------------------
    def _standings_bucket(self, league_key: str) -> Dict[str, Any]:
        standings = self._state.setdefault("standings", {})
        if not isinstance(standings, dict):
            standings = {}
            self._state["standings"] = standings

        bucket = standings.setdefault(league_key, {})
        if not isinstance(bucket, dict):
            bucket = {}
            standings[league_key] = bucket
        return bucket

    def get_last_hash(self, league_key: str) -> Optional[str]:
        bucket = self._standings_bucket(league_key)
        val = bucket.get("last_hash")
        return val if isinstance(val, str) else None

    def set_last_hash(self, league_key: str, new_hash: str) -> None:
        bucket = self._standings_bucket(league_key)
        bucket["last_hash"] = new_hash
        self.save()

    def get_standings_message_id(self, league_key: str) -> Optional[int]:
        bucket = self._standings_bucket(league_key)
        val = bucket.get("message_id")
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except Exception:
            return None

    def set_standings_message_id(self, league_key: str, message_id: int) -> None:
        bucket = self._standings_bucket(league_key)
        bucket["message_id"] = int(message_id)
        self.save()

    # -------------------------
    # scheduled_matches (unchanged)
    # -------------------------
    def get_scheduled_matches(self) -> List[Dict[str, Any]]:
        matches = self._state.get("scheduled_matches", [])
        if not isinstance(matches, list):
            return []
        out: List[Dict[str, Any]] = []
        for m in matches:
            if isinstance(m, dict):
                out.append(m)
        return out

    def save_scheduled_matches(self, matches: List[Dict[str, Any]]) -> None:
        self._state["scheduled_matches"] = list(matches)
        self.save()


store = StateStore.load(settings.state_path)
