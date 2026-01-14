# bot.py
from __future__ import annotations

import discord
from discord.ext import commands, tasks

from config import settings
from leagues import configured_leagues
from services.standings import fetch_standings_embed_for_league, upsert_league_standings_message
from storage import store
from cogs.admin_cog import AdminsCog



intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

print("Starting bot.py…")

@bot.event
async def setup_hook():
    # Load cogs
    await bot.load_extension("cogs.standings_cog")
    await bot.load_extension("cogs.match_scheduler_cog")
    await bot.load_extension("cogs.match_reminders_cog")
    await bot.load_extension("cogs.admin_cog")
    await bot.load_extension("cogs.scheduling_cog")

    
    # sync command
    await bot.tree.sync()




    # Sync slash commands
    if settings.guild_id:
        guild = discord.Object(id=settings.guild_id)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print("Slash commands synced to guild.")
    else:
        await bot.tree.sync()
        print("Slash commands synced globally.")

    # Start polling
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

    for league in leagues:
        try:
            key, embed = await fetch_standings_embed_for_league(league)
            last = store.get_last_hash(league.key)
            if last == key:
                continue

            store.set_last_hash(league.key, key)
            await upsert_league_standings_message(bot, league, embed)

        except Exception as e:
            print(f"[poll] {league.name}: {e}")


def run():
    bot.run(settings.discord_token)

if __name__ == "__main__":
    run()

