import logging

from discord.ext import commands
import discord

from token_ import token


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

for logger in logging.root.manager.loggerDict:
    logging.getLogger(logger).setLevel(logging.WARNING)


class GolemBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=[],
            allowed_mentions=discord.AllowedMentions.none(),
            intents=discord.Intents.default())

    async def setup_hook(self):
        self.owner = (await self.application_info()).owner
        self.cog_file_names = ("tag", "logging", "owner")

        for cog in self.cog_file_names:
            await self.load_extension(f"cogs.{cog}")


bot = GolemBot()
bot.run(token)
