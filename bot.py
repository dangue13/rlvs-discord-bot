# bot.py
from __future__ import annotations

import sys
import traceback

import discord
from discord.ext import commands, tasks

from config import settings
from leagues import configured_leagues
from services.standings import fetch_standings_embed_for_league, upsert_league_standings_message
from storage import store


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

print("BOOT: bot.py loaded", flush=True)

_DID_SYNC = False


async def _load_extensions() -> None:
    for ext in [
        "cogs.standings_cog",
        "cogs.match_scheduler_cog",
        "cogs.match_reminders_cog",
        "cogs.admin_cog",
        "cogs.scheduling_cog",
    ]:
        try:
            await bot.load_extension(ext)
            print(f"BOOT: loaded {ext}", flush=True)
        except Exception as e:
            print(f"BOOT: FAILED loading {ext}: {e}", flush=True)
            traceback.print_exc()
            raise


async def _sync_commands() -> None:
    global _DID_SYNC
    if _DID_SYNC:
        return

    guild_id = getattr(settings, "guild_id", 0) or 0

    try:
        if guild_id:
            g = discord.Object(id=int(guild_id))
            bot.tree.clear_commands(guild=g)
            await bot.tree.sync(guild=g)
            print(f"[sync] cleared+synced guild commands to {guild_id}", flush=True)
        else:
            await bot.tree.sync()
            print("[sync] synced global commands", flush=True)

        _DID_SYNC = True
    except Exception as e:
        print(f"[sync] FAILED: {e}", flush=True)
        traceback.print_exc()
        raise


@bot.event
async def setup_hook():
    print("BOOT: setup_hook start", flush=True)
    await _load_extensions()
    await _sync_commands()

    if not poll.is_running():
        poll.start()
        print("BOOT: poll started", flush=True)


@bot.event
async def on_ready():
    print(f"READY: Logged in as {bot.user} (id={bot.user.id})", flush=True)
    try:
        print("[guilds] Bot is in:", flush=True)
        for g in bot.guilds:
            print(f" - {g.name} ({g.id})", flush=True)
    except Exception:
        pass


@tasks.loop(seconds=settings.poll_seconds)
async def poll():
    leagues = configured_leagues()
    if not leagues:
        return

    guild_id = int(getattr(settings, "guild_id", 0) or 0)
    if not guild_id and bot.guilds:
        guild_id = int(bot.guilds[0].id)
    if not guild_id:
        return

    for league in leagues:
        try:
            key, embed = await fetch_standings_embed_for_league(league)
            last = store.get_last_hash(league.key)
            if last == key:
                continue

            store.set_last_hash(league.key, key)
            await upsert_league_standings_message(bot, guild_id, league, embed)
        except Exception as e:
            print(f"[poll] {league.name}: {e}", flush=True)


def run():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    bot.run(settings.discord_token)


if __name__ == "__main__":
    run()
