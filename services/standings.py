# services/standings.py
from __future__ import annotations

import hashlib
import json
from typing import List, Tuple, Optional

import discord
from bs4 import BeautifulSoup

from leagues import League
from services.http import http
from storage import store

Row = Tuple[int, str, str, str, str, str, str]  # rank, team, wl, gw, gl, pm, gb


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pick_biggest_table(soup: BeautifulSoup):
    tables = soup.find_all("table")
    if not tables:
        return None
    return max(tables, key=lambda t: len(t.find_all("tr")))


def parse_standings(html: str) -> List[Row]:
    lowered = html.lower()
    if "cloudflare" in lowered and ("attention required" in lowered or "verify you are human" in lowered):
        raise RuntimeError("Blocked by Cloudflare / bot protection.")

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    table = _pick_biggest_table(soup)
    if not table:
        raise RuntimeError("No standings table found.")

    rows = table.find_all("tr")
    if not rows:
        raise RuntimeError("Standings table has no rows.")

    header_idx = None
    headers: List[str] = []

    for i, r in enumerate(rows[:12]):
        if r.find_all("th"):
            headers = [c.get_text(" ", strip=True).upper() for c in r.find_all(["th", "td"])]
            header_idx = i
            break

        tds = [c.get_text(" ", strip=True).upper() for c in r.find_all("td")]
        if not tds:
            continue

        hits = 0
        for cell in tds:
            if ("TEAM" in cell) or ("W-L" in cell) or ("GAMES" in cell) or ("GB" in cell) or ("PTS" in cell):
                hits += 1
        if hits >= 2:
            headers = tds
            header_idx = i
            break

    def get_cell(cells: List[str], idx: int, default: str = "—") -> str:
        if 0 <= idx < len(cells):
            val = (cells[idx] or "").strip()
            return val if val else default
        return default

    if header_idx is not None and headers:
        try:
            def col(*names: str) -> int:
                for j, h in enumerate(headers):
                    for n in names:
                        if n in h:
                            return j
                raise RuntimeError

            TEAM_COL = col("TEAM")
            WL_COL   = col("W-L", "W – L", "W/L")
            GW_COL   = col("GAMES WON", "WON")
            GL_COL   = col("GAMES LOST", "LOST")
            PM_COL   = col("+/-", "+/−", "+−", "DIFF")
            GB_COL   = col("GB")

            data_rows = rows[header_idx + 1 :]
        except Exception:
            TEAM_COL, WL_COL, GW_COL, GL_COL, PM_COL, GB_COL = 1, 2, 3, 4, 5, 7
            data_rows = rows
            header_idx = None
    else:
        TEAM_COL, WL_COL, GW_COL, GL_COL, PM_COL, GB_COL = 1, 2, 3, 4, 5, 7
        data_rows = rows

    parsed: List[Row] = []
    for r in data_rows:
        cells = [c.get_text(" ", strip=True) for c in r.find_all("td")]
        if not cells:
            continue
        if header_idx is None and len(cells) < 8:
            continue

        rank_raw = (cells[0] or "").strip()
        if not rank_raw.isdigit():
            continue

        rank = int(rank_raw)
        team = get_cell(cells, TEAM_COL)
        wl   = get_cell(cells, WL_COL)
        gw   = get_cell(cells, GW_COL, "0")
        gl   = get_cell(cells, GL_COL, "0")
        pm   = get_cell(cells, PM_COL, "0")
        gb   = get_cell(cells, GB_COL, "-")

        if gb in {"—", ""}:
            gb = "-"
        if pm in {"—", ""}:
            pm = "0"

        parsed.append((rank, team, wl, gw, gl, pm, gb))

    if not parsed:
        raise RuntimeError("No team rows parsed from standings (table structure may have changed).")

    parsed.sort(key=lambda x: x[0])
    return parsed


def build_standings_embed(rows: List[Row], standings_url: str, league_name: str, top_n: int = 12) -> Tuple[str, discord.Embed]:
    key = _sha(json.dumps(rows, ensure_ascii=False))

    lines: List[str] = []
    for (rank, team, wl, _gw, _gl, _pm, gb) in rows[:top_n]:
        wl = (wl or "—").strip()
        gb = (gb or "-").strip()
        if gb in {"—", ""}:
            gb = "-"
        lines.append(f"**{rank}. {team}**  •  `{wl}`  •  `GB {gb}`")

    embed = discord.Embed(
        title=f"🏆 {league_name} Standings",
        description="\n\n".join(lines) if lines else "—",
        url=standings_url,
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Velocity Series • LeagueRepublic")
    embed.timestamp = discord.utils.utcnow()
    return key, embed


async def fetch_standings_embed_for_league(league: League) -> Tuple[str, discord.Embed]:
    html = await http.fetch_html(league.standings_url)
    rows = parse_standings(html)
    return build_standings_embed(rows, standings_url=league.standings_url, league_name=league.name)


async def _get_text_channel(bot: discord.Client, channel_id: int) -> discord.TextChannel:
    ch = bot.get_channel(channel_id)
    if ch is None:
        ch = await bot.fetch_channel(channel_id)
    if not isinstance(ch, discord.TextChannel):
        raise RuntimeError("Channel ID must point to a text channel.")
    return ch


def _resolve_standings_channel_id(guild_id: int, league: League) -> int:
    # Admin-configured per-guild channel takes priority; env is fallback
    cid = store.get_standings_channel(guild_id, league.key)
    if cid:
        return int(cid)
    if league.channel_id:
        return int(league.channel_id)
    return 0


async def upsert_league_standings_message(
    bot: discord.Client,
    guild_id: int,
    league: League,
    embed: discord.Embed,
) -> discord.Message:
    channel_id = _resolve_standings_channel_id(guild_id, league)
    if not channel_id:
        raise RuntimeError(f"{league.name} standings channel not configured yet.")

    channel = await _get_text_channel(bot, channel_id)
    existing_id: Optional[int] = store.get_standings_message_id(league.key)

    if existing_id:
        try:
            msg = await channel.fetch_message(existing_id)
            await msg.edit(embed=embed)
            return msg
        except (discord.NotFound, discord.HTTPException):
            pass

    msg = await channel.send(embed=embed)
    store.set_standings_message_id(league.key, msg.id)
    return msg
