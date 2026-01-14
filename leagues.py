# leagues.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from config import settings


@dataclass(frozen=True)
class League:
    key: str          # storage key, e.g. "champion"
    name: str         # display name
    standings_url: str
    channel_id: int   # 0 means not configured


def get_leagues() -> List[League]:
    return [
        League(
            key="champion",
            name="Champion",
            standings_url=settings.champion_standings_url,
            channel_id=settings.champion_standings_channel_id,
        ),
        League(
            key="challenger",
            name="Challenger",
            standings_url=settings.challenger_standings_url,
            channel_id=settings.challenger_standings_channel_id,
        ),
    ]


def configured_leagues() -> List[League]:
    """
    Only leagues with a real channel_id should auto-post.
    'standby' in .env becomes channel_id=0 and will be skipped.
    """
    return [l for l in get_leagues() if l.channel_id and l.standings_url]
