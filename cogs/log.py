from io import BytesIO
import re

from discord import app_commands, Interaction, Attachment
from discord.ext import commands
import discord


REGEX_LOG_TIMESTAMP = r"\[\w \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}]"
REGEX_IPV4 = r"\d+\.\d+\.\d+\.\d+"
REGEX_IPV6 = r"(?:[a-f0-9]*\:){7}[a-f0-9]*"
REGEX_USER = r"(\S+)(#\d{1,9})"
REGEX_USER_B = r"Initial Username '(.+)'"


class CommandsLog(commands.Cog):
    """Implementation for the log command and detection of logs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command()
    @app_commands.describe(
        attachment="The log file (in %appdata%/Parsec, %programdata%/Parsec, "
        "~/.parsec or /Users/Shared/.parsec)")
    async def log(self, itx: Interaction, attachment: Attachment):
        """Upload a Parsec log file with names and IPs removed."""
        if not attachment.filename.lower().endswith(".txt"):
            await itx.response.send_message(
                "Upload a text (.txt) Parsec log file.", ephemeral=True)
            return

        await itx.response.defer()

        contents = (await attachment.to_file()).fp.read().decode()

        for ip in set(re.findall(f"{REGEX_IPV4}|{REGEX_IPV6}", contents)):
            separator = "." if "." in ip else ":"
            numbers = ip.split(separator)

            for i, number in enumerate(list(numbers)):
                if i + 1 > len(numbers) / 2:
                    numbers[i] = "X" * len(number)

            contents = contents.replace(ip, separator.join(numbers))

        for names in set(re.findall(f"{REGEX_USER}|{REGEX_USER_B}", contents)):
            for name in filter(None, names):
                if name.startswith("#"):
                    censored = "#" + ("X" * (len(name) - 1))
                    contents = contents.replace(name, censored)
                else:
                    third = int(len(name) / 3)
                    censored = name[:third] + ("X" * (len(name) - third))
                    contents = contents.replace(name, censored)

        data = BytesIO(contents.encode())
        filtered_file = discord.File(data, filename=attachment.filename)
        await itx.followup.send(file=filtered_file)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.bot.is_trusted_member(message.author):
            return
        if not message.attachments:
            return

        for attachment in message.attachments:
            if not attachment.filename.lower().endswith(".txt"):
                continue

            regex_list = REGEX_IPV4, REGEX_IPV6, REGEX_USER, REGEX_USER_B
            contents = (await attachment.to_file()).fp.read().decode()

            if not re.findall(REGEX_LOG_TIMESTAMP, contents):
                continue
            if not any(re.findall(regex, contents) for regex in regex_list):
                continue

            allowed_mentions = discord.AllowedMentions(users=[message.author])

            await message.delete()
            await message.channel.send(
                f"{message.author.mention} you appear to have uploaded a "
                f"Parsec log with sensitive information. Use the "
                f"`/log` command to safely upload it.",
                allowed_mentions=allowed_mentions,
                delete_after=30)


async def setup(bot):
    await bot.add_cog(CommandsLog(bot))
