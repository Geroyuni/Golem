from difflib import SequenceMatcher
import datetime

from discord.ext import commands
import discord

IGNORED_ROLES = ("Hero", "Jedi", "Parsec Team")


class Moderation(commands.Cog):
    """Handle moderation stuff that Discord itself doesn't do."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.previous_message = {}
        self.warned_previously = set()

    def is_ignored_member(self, member: discord.Member):
        return (
            member == self.bot.user
            or any([role.name in IGNORED_ROLES for role in member.roles]))

    async def soft_warn(
        self, author: discord.Member, channel: discord.TextChannel, reason: str
    ):
        """Give one warning and timeout, or kick if warned previously."""
        if author in self.warned_previously:
            await author.kick(reason=reason)
        else:
            await author.timeout(
                datetime.timedelta(minutes=1), reason=reason)
            await channel.send(
                reason,
                allowed_mentions=discord.AllowedMentions(users=[author]),
                delete_after=20)
            self.warned_previously.add(author)

        # Allow user to post once next time rather than consider a duplicate
        self.previous_message.pop(author, None)

    async def handle_repost(self, message: discord.Message):
        """Detect and deal with reposts as is appropriate."""
        previous = self.previous_message.get(message.author.id)
        twenty_minutes = datetime.timedelta(minutes=20)

        is_reposted_message = (
            previous
            and SequenceMatcher(
                None, message.content, previous.content).ratio() > 0.9
            and message.created_at - previous.created_at < twenty_minutes
            and await previous.channel.fetch_message(previous.id))

        if not is_reposted_message:
            self.previous_message[message.author.id] = message
            return

        if previous.channel != message.channel:
            reason = (
                f"{message.author.mention} don't post the same message "
                "in two channels. Read <#380811257973833738> to find where "
                "your message should be posted")
        else:
            reason = (
                f"{message.author.mention} don't post the same message "
                "twice in a short period of time")

        await self.soft_warn(message.author, message.channel, reason)
        await message.delete()
        await previous.delete()

        self.previous_message.pop(message.author.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.is_ignored_member(message.author):
            return
        if message.is_system():
            return

        await self.handle_repost(message)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
