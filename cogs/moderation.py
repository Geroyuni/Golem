from difflib import SequenceMatcher
import datetime
import logging
import re

from discord.ext import commands
import discord

NOTIFICATIONS_CHANNEL = "safety-notifications"
TRUSTED_ROLES = ("Hero", "Jedi", "Parsec Team")


class Moderation(commands.Cog):
    """Handle moderation stuff that Discord itself doesn't do."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.previous_messages = {}
        self.previous_warnings = {}

    def is_trusted_member(self, member: discord.Member):
        return (
            member == self.bot.user
            or any([role.name in TRUSTED_ROLES for role in member.roles]))

    async def message_still_exists(self, message: discord.Message):
        try:
            await message.channel.fetch_message(message.id)
        except discord.NotFound:
            return False
        else:
            return True

    async def is_deleted_message_in_audit_log(self, message: discord.Message):
        """Whether a message is deleted due to moderation action."""
        if not message.guild.me.guild_permissions.view_audit_log:
            return False

        now = datetime.datetime.now(datetime.timezone.utc)
        two_minutes_ago = now - datetime.timedelta(minutes=2)
        actions = (
            discord.AuditLogAction.ban,             # ban auto bulk deletion
            discord.AuditLogAction.message_delete,  # human moderator action
            discord.AuditLogAction.kick,            # bot action
            discord.AuditLogAction.member_update)   # bot action (timeout)

        async for entry in message.guild.audit_logs(after=two_minutes_ago):
            if entry.action in actions and entry.target == message.author:
                return True
        return False

    async def soft_warn(
        self, author: discord.Member, channel: discord.TextChannel, reason: str
    ):
        """Give one warning and timeout, or kick if warned previously."""
        if reason not in self.previous_warnings:
            self.previous_warnings[reason] = set()

        if author in self.previous_warnings[reason]:
            await author.kick(reason=reason)
        else:
            await author.timeout(datetime.timedelta(minutes=1), reason=reason)
            await channel.send(
                reason + ("\n" * 6) + "-# blank space for discord popup",
                allowed_mentions=discord.AllowedMentions(users=[author]),
                delete_after=30)
            self.previous_warnings[reason].add(author)

        # Allow user to post once next time rather than consider a duplicate
        self.previous_messages.pop(author, None)

    async def handle_reposts(self, message: discord.Message):
        """Detect and deal with reposts as is appropriate."""
        previous_messages = self.previous_messages.get(message.author.id, [])
        twenty_minutes = datetime.timedelta(minutes=20)
        reposts = 0

        for previous in reversed(previous_messages):
            is_repost = (
                SequenceMatcher(
                    None, message.content, previous.content).ratio() > 0.9
                and message.created_at - previous.created_at < twenty_minutes
                and await self.message_still_exists(previous))

            if not is_repost:
                break

            reposts += 1

        channels_posted = set(m.channel for m in previous_messages + [message])
        threshold_met = (
            (reposts == 2)
            or (reposts and len(channels_posted) > 1)
            or (reposts and len(message.content) > 15))

        if not threshold_met:
            if not self.previous_messages.get(message.author.id):
                self.previous_messages[message.author.id] = []

            self.previous_messages[message.author.id].append(message)
            del self.previous_messages[message.author.id][:-2]
            return

        if len(channels_posted) > 1:
            reason = (
                f"{message.author.mention} don't post the same message "
                "in two channels. Read <#380811257973833738> to find where "
                "your message should be posted")
        else:
            reason = (
                f"{message.author.mention} don't post the same message "
                "multiple times in a short period of time")

        await self.soft_warn(message.author, message.channel, reason)
        await message.delete()

        for previous in previous_messages:
            await previous.delete()

        self.previous_messages.pop(message.author.id)

    async def report_suspicious_message(
        self, message: discord.Message, targeted_member: discord.Member
    ):
        """Log and warn about deleted message."""
        logging.info(
            f"Suspicious message by {message.author}: {message.content}")

        await message.channel.send(
            f"{targeted_member.mention} if you have been directed by a user "
            f"to get help elsewhere, you may be getting tricked. "
            f"We will never ask you to create a ticket on a different "
            f"Discord server (this is the only official server), and our "
            f"official site is <https://parsec.app>.",
            allowed_mentions=discord.AllowedMentions(users=[targeted_member]))

        channel = discord.utils.get(
            message.guild.channels, name=NOTIFICATIONS_CHANNEL)

        if not channel:
            return

        content_in_quotes = "> " + message.content.replace("\n", "\n> ")

        await channel.send(
            f"{message.author.mention}'s message "
            f"from {discord.utils.format_dt(message.created_at, style='t')} "
            f"was deleted in {message.channel.mention}:"
            f"\n{content_in_quotes or '> (empty)'}",
            suppress_embeds=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Pass each message to the repost handler."""
        if self.is_trusted_member(message.author):
            return
        if message.is_system():
            return
        if not message.content:
            return

        await self.handle_reposts(message)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Check whether message deletion is suspicious.

        Message deletions that are quick and mention one user may be
        attempting to trick said user into getting help via fake tickets.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        five_minutes = datetime.timedelta(minutes=5)
        links = re.findall(r"https?://", message.content)
        mention_ids = re.findall(r"<@!?(\d{17,20})>", message.content)
        targeted_member = None

        if mention_ids:
            try:
                targeted_member = (
                    await message.guild.fetch_member(mention_ids[0]))
            except discord.NotFound:
                pass

        is_considered_normal = (
            self.is_trusted_member(message.author)
            or message.is_system()
            or not links
            or not targeted_member
            or now - message.created_at > five_minutes
            or await self.is_deleted_message_in_audit_log(message)
            or self.is_trusted_member(targeted_member))

        if not is_considered_normal:
            await self.report_suspicious_message(message, targeted_member)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
