# cogs/standings_cog.py
from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from leagues import configured_leagues, get_leagues
from storage import store
from services.standings import fetch_standings_embed_for_league, upsert_league_standings_message


class StandingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="poststandings", description="Create (or find) the standings message(s) and update them")
    async def poststandings(self, interaction: discord.Interaction):
        await interaction.response.send_message("Posting/updating standings…", ephemeral=True)

        leagues = configured_leagues()
        if not leagues:
            msg = (
                "No standings channels configured yet.\n"
                "Set these in `.env` (use real integer channel IDs):\n"
                "- CHAMPION_STANDINGS_CHANNEL_ID\n"
                "- CHALLENGER_STANDINGS_CHANNEL_ID\n"
            )
            await interaction.followup.send(msg, ephemeral=True)
            return

        results = []
        for league in leagues:
            try:
                key, embed = await fetch_standings_embed_for_league(league)
                store.set_last_hash(league.key, key)
                msg = await upsert_league_standings_message(self.bot, league, embed)
                results.append(f"✅ {league.name}: updated (msg {msg.id})")
            except Exception as e:
                results.append(f"❌ {league.name}: {e}")

        await interaction.followup.send("\n".join(results), ephemeral=True)

    @app_commands.command(name="forcecheck", description="Force update standings for all leagues (even if unchanged)")
    async def forcecheck(self, interaction: discord.Interaction):
        await interaction.response.send_message("Force updating standings…", ephemeral=True)

        leagues = configured_leagues()
        if not leagues:
            await interaction.followup.send(
                "No standings channels configured yet (Champion/Challenger channel IDs are still standby).",
                ephemeral=True
            )
            return

        results = []
        for league in leagues:
            try:
                key, embed = await fetch_standings_embed_for_league(league)
                store.set_last_hash(league.key, key)
                await upsert_league_standings_message(self.bot, league, embed)
                results.append(f"✅ {league.name}: forced update complete")
            except Exception as e:
                results.append(f"❌ {league.name}: {e}")

        await interaction.followup.send("\n".join(results), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(StandingsCog(bot))

