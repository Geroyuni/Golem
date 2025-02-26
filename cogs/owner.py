import sys
import os

from discord import app_commands, Interaction
from discord.ext import commands
import discord


class CommandsOwner(commands.Cog):
    """All of the owner commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def is_owner(itx: Interaction):
        return itx.user == itx.client.owner

    @app_commands.check(is_owner)
    @app_commands.command()
    @app_commands.allowed_installs(guilds=False, users=True)
    async def owner(
        self,
        itx: Interaction,
        restart: str = None,
        sync: str = None,
        shutdown: bool = False,
    ):
        """Bot owner command 🤔. I can't hide this, blame Discord"""
        if restart:
            return await self.restart(itx, restart)
        if sync:
            return await self.sync(itx, sync)
        if shutdown:
            return await self.shutdown(itx)

    async def restart(self, itx: Interaction, cog: str):
        """Restart specific cog of the bot or all of it."""
        await itx.response.defer(ephemeral=True)

        if cog == "full":
            await itx.followup.send("(restarting)")
            await self.bot.close()
            os.execl(sys.executable, sys.executable, *sys.argv)

        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await itx.followup.send(f"Reloaded 'cogs.{cog}'", ephemeral=True)
        except Exception as e:
            await itx.followup.send(e)

    async def sync(self, itx: Interaction, guild_id: str):
        """Sync changes that should be reflected on the Discord UI."""
        if guild_id == "global":
            await self.bot.tree.sync()
        else:
            await self.bot.tree.sync(guild=discord.Object(id=int(guild_id)))

        await itx.response.send_message("synced.", ephemeral=True)

    async def shutdown(self, itx: Interaction):
        """Shutdown the bot properly."""
        await itx.response.send_message("(shutting down)", ephemeral=True)
        await self.bot.close()

    @owner.autocomplete("restart")
    async def restart_autocomplete(self, itx: Interaction, current: str):
        names = ["full"]
        names.extend(self.bot.cog_file_names)

        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()]

    @owner.autocomplete("sync")
    async def sync_autocomplete(self, itx: Interaction, current: str):
        if itx.user != self.bot.owner:
            return []  # don't leak the bot guild names for no reason

        guilds = [
            app_commands.Choice(name=g.name, value=str(g.id))
            for g in self.bot.guilds if current.lower() in g.name.lower()]

        guilds.sort(key=lambda i: i.name.lower())

        if current.lower() in "global":
            guilds.insert(
                0, app_commands.Choice(name="global", value="global"))

        return guilds


async def setup(bot):
    await bot.add_cog(CommandsOwner(bot))
