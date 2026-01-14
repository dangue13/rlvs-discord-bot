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


@bot.event
async def setup_hook():
    print("BOOT: setup_hook start", flush=True)

    # Load cogs one-by-one so you can see exactly which one fails
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

    guild_id = getattr(settings, "guild_id", None)

    try:
        if guild_id:
            await bot.tree.sync(guild=discord.Object(id=int(guild_id)))
            print(f"[sync] Synced commands to guild_id={guild_id}", flush=True)
        else:
            await bot.tree.sync()
            print("[sync] Synced commands globally", flush=True)
    except Exception as e:
        print(f"[sync] FAILED: {e}", flush=True)
        traceback.print_exc()
        raise

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
    # Force unbuffered stdout in some hosts
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    bot.run(settings.discord_token)


if __name__ == "__main__":
    run()
