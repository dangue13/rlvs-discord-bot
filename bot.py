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
    # Load cogs (each cog file must define: async def setup(bot): await bot.add_cog(...)
    await bot.load_extension("cogs.standings_cog")
    await bot.load_extension("cogs.match_scheduler_cog")
    await bot.load_extension("cogs.match_reminders_cog")
    await bot.load_extension("cogs.admins_cog")      # <- make sure filename is admins_cog.py
    await bot.load_extension("cogs.scheduling_cog")

    # Sync commands: try guild sync if configured + bot is actually in that guild,
    # otherwise fall back to global sync. Never hard-crash on Forbidden.
    guild_id = getattr(settings, "guild_id", None)

    if guild_id:
        g = bot.get_guild(int(guild_id))
        if g is None:
            print(f"[sync] Skipping guild sync: bot is not in guild_id={guild_id}. Falling back to global sync.")
        else:
            try:
                await bot.tree.sync(guild=discord.Object(id=int(guild_id)))
                print(f"[sync] Synced commands to guild_id={guild_id}")
            except discord.Forbidden as e:
                print(f"[sync] Forbidden syncing to guild_id={guild_id}: {e}. Falling back to global sync.")
                await bot.tree.sync()
                print("[sync] Synced commands globally")
    else:
        await bot.tree.sync()
        print("[sync] Synced commands globally")

    if not poll.is_running():
        poll.start()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    # Helpful to debug Render guild_id issues
    try:
        print("[guilds] Bot is in:")
        for g in bot.guilds:
            print(f" - {g.name} ({g.id})")
    except Exception:
        pass


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
