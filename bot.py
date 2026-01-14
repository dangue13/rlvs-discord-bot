from __future__ import annotations

import os
import asyncio
import traceback
import sys

import discord
from discord.ext import commands

from config import settings


# ----------------------------
# Bot setup
# ----------------------------
intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)

print("Starting bot.py…")


# ----------------------------
# Helpful: always print crashes (Render restarts on exit)
# ----------------------------
def _excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    sys.exit(1)

sys.excepthook = _excepthook


# ----------------------------
# Slash command + cog loading
# ----------------------------
@bot.event
async def setup_hook():
    print("BOOT: setup_hook start")

    # Load cogs
    await bot.load_extension("cogs.standings_cog")
    await bot.load_extension("cogs.match_scheduler_cog")
    await bot.load_extension("cogs.match_reminders_cog")
    await bot.load_extension("cogs.admin_cog")
    await bot.load_extension("cogs.scheduling_cog")

    # Slash command sync (guild = instant)
    if settings.guild_id:
        guild = discord.Object(id=int(settings.guild_id))

        # Push global commands into the guild (instant availability)
        bot.tree.copy_global_to(guild=guild)

        # Clear stale guild commands
        bot.tree.clear_commands(guild=guild)

        synced = await bot.tree.sync(guild=guild)
        print(f"[sync] cleared+synced {len(synced)} commands to guild_id={settings.guild_id}")
    else:
        synced = await bot.tree.sync()
        print(f"[sync] synced {len(synced)} commands globally")


@bot.event
async def on_ready():
    print(f"READY: Logged in as {bot.user} (id={bot.user.id})")
    if bot.guilds:
        print("[guilds] Bot is in:")
        for g in bot.guilds:
            print(f" - {g.name} ({g.id})")


# ----------------------------
# Run the bot (Render)
# ----------------------------
def _get_token() -> str:
    token = (os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "Missing bot token. Set DISCORD_TOKEN (recommended) or BOT_TOKEN in Render Environment."
        )
    return token


async def main():
    async with bot:
        await bot.start(_get_token())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
