# cogs/scheduling_cog.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import discord
from discord.ext import commands

from storage import store


def _fmt_match(m: Dict) -> str:
    ts = int(datetime.fromisoformat(m["scheduled_iso"]).timestamp())
    return f"• **{m['team']}** vs **{m['opponent']}** — <t:{ts}:F> (`{m['id']}`)"


async def update_schedule_board(bot: commands.Bot, guild_id: int, league_key: str):
    channel_id = store.get_schedule_channel(guild_id, league_key)
    if not channel_id:
        return

    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    matches = [
        m for m in store.get_scheduled_matches()
        if m["guild_id"] == guild_id and m["league"] == league_key
    ]

    lines = [_fmt_match(m) for m in matches] or ["_No matches scheduled._"]

    embed = discord.Embed(
        title=f"📅 {league_key.capitalize()} Schedule",
        description="\n".join(lines),
        color=discord.Color.green(),
    )
    embed.timestamp = discord.utils.utcnow()

    msg_id = store.get_schedule_message_id(guild_id, league_key)
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except Exception:
            pass

    msg = await channel.send(embed=embed)
    store.set_schedule_message_id(guild_id, league_key, msg.id)


async def post_matches_for_league(bot: commands.Bot, guild_id: int, league_key: str):
    await update_schedule_board(bot, guild_id, league_key)


async def setup(bot: commands.Bot):
    pass
