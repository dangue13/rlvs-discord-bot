# bot.py
from __future__ import annotations

import discord
from discord.ext import commands, tasks

from config import settings
from leagues import configured_leagues
from services.standings import fetch_standings_embed_for_league, upsert_league_standings_message
from storage import store

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

print("Starting bot.py…")


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.standings_cog")
    await bot.load_extension("cogs.match_scheduler_cog")
    await bot.load_extension("cogs.match_reminders_cog")
    await bot.load_extension("cogs.admin_cog")
    await bot.load_extension("cogs.scheduling_cog")

    guild_id = getattr(settings, "guild_id", None)

    if guild_id:
        try:
            await bot.tree.sync(guild=discord.Object(id=int(guild_id)))
            print(f"[sync] Synced commands to guild_id={guild_id}")
        except Exception as e:
            print(f"[sync] Error syncing to guild_id={guild_id}: {e}")
    else:
        await bot.tree.sync()
        print("[sync] Synced commands globally")

    if not poll.is_running():
        poll.start()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")


@tasks.loop(seconds=settings.poll_seconds)
async def poll():
    leagues = configured_leagues()
    if not leagues:
        return

    # single-guild bot: use configured guild_id if provided, else first guild
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
            print(f"[poll] {league.name}: {e}")


def run():
    bot.run(settings.discord_token)


if __name__ == "__main__":
    run()
