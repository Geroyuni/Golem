import logging

from discord.ext import commands
import discord

from token_ import token

TRUSTED_ROLES = ("Hero", "Jedi", "Parsec Team")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

for logger in logging.root.manager.loggerDict:
    logging.getLogger(logger).setLevel(logging.WARNING)


class GolemBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents(
            guilds=True, messages=True, message_content=True)

        super().__init__(
            command_prefix=[],
            allowed_mentions=discord.AllowedMentions.none(),
            intents=intents)

    def is_trusted_member(self, member: discord.Member):
        return (
            member == self.user
            or any([role.name in TRUSTED_ROLES for role in member.roles]))

    async def setup_hook(self):
        self.owner = (await self.application_info()).owner
        self.cog_file_names = (
            "tag", "logging", "moderation", "owner", "log")

        for cog in self.cog_file_names:
            await self.load_extension(f"cogs.{cog}")


if __name__ == "__main__":
    bot = GolemBot()
    bot.run(token)
