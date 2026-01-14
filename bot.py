import discord
from discord.ext import commands

from config import settings

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)

print("Starting bot.py…")


@bot.event
async def setup_hook():
    print("BOOT: setup_hook start")

    # Load cogs
    await bot.load_extension("cogs.standings_cog")
    await bot.load_extension("cogs.match_scheduler_cog")
    await bot.load_extension("cogs.match_reminders_cog")
    await bot.load_extension("cogs.admin_cog")
    await bot.load_extension("cogs.scheduling_cog")

    # Slash command sync
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
