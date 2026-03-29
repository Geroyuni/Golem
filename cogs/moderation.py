from difflib import SequenceMatcher
import datetime
import logging
import re

from discord.ext import commands
import discord

NOTIFICATIONS_CHANNEL = "safety-notifications"
HIGHER_SUPPORT_MODERATION_CHANNELS = ("general", "help", "tech-talk")
TRUSTED_LINKS = ("parsec.app", "parsecgaming.com", "parsec.gg", "unity.com")


class Moderation(commands.Cog):
    """Handle moderation stuff that Discord itself doesn't do."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.previous_messages = {}
        self.previous_warnings = {}
        self.warned_against_user_previously = set()

    @staticmethod
    def has_links(content: str):
        """Return if there are links in a given content.

        This is a somewhat basic implementation, could be improved later."""
        cleaned_content = content.replace("\n", "").replace("> ", "").lower()
        return bool(re.findall(r"https?:", cleaned_content))

    async def fetch_mentions(
        self,
        message: discord.Message,
        exclude_trusted: bool = False,
        exclude_untrusted: bool = False
    ):
        mentioned_members = set(message.mentions)

        for member_id in re.findall(r"<@!?(\d{17,20})>", message.content):
            try:
                mentioned_members.add(
                    await message.guild.fetch_member(member_id))
            except discord.NotFound:
                pass

        for member in list(mentioned_members):
            if exclude_trusted and self.bot.is_trusted_member(member):
                mentioned_members.remove(member)
            if exclude_untrusted and not self.bot.is_trusted_member(member):
                mentioned_members.remove(member)

        return mentioned_members

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
        if self.bot.is_trusted_member(message.author):
            return False
        if message.is_system():
            return False
        if not message.content:
            return False

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
            return False

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
        return True

    async def handle_logging_message_deletion(self, message: discord.Message):
        """Log some deleted messages to check for shady behavior."""
        now = datetime.datetime.now(datetime.timezone.utc)
        twenty_minutes = datetime.timedelta(minutes=20)

        should_not_log = (
            message.channel.name not in HIGHER_SUPPORT_MODERATION_CHANNELS
            or self.bot.is_trusted_member(message.author)
            or message.is_system()
            or now - message.created_at > twenty_minutes
            or await self.is_deleted_message_in_audit_log(message)
            or not (
                self.has_links(message.content)
                or await self.fetch_mentions(message, exclude_trusted=True)
            )
        )

        if should_not_log:
            return

        logging.warning(
            f"Suspicious message by {message.author}: {message.content}")

        channel = discord.utils.get(
            message.guild.channels, name=NOTIFICATIONS_CHANNEL)

        if not channel:
            return

        await channel.send(
            f"{message.author.mention}'s message "
            f"from {discord.utils.format_dt(message.created_at, style='t')} "
            f"was deleted in {message.channel.mention}:"
            f"\n```{message.content or '(empty)'}```",
            suppress_embeds=True)

    async def handle_link_reminder(self, message: discord.Message):
        """Remind users link risks if any are posted by untrusted users."""
        should_not_remind = (
            message.channel.name not in HIGHER_SUPPORT_MODERATION_CHANNELS
            or self.bot.is_trusted_member(message.author)
            or message.is_system()
            or message.author in self.warned_against_user_previously
            or not self.has_links(message.content)
            or any([link in message.content.lower() for link in TRUSTED_LINKS])
            or not await self.fetch_mentions(message, exclude_trusted=True))

        if should_not_remind:
            return

        await message.channel.send(
            "**Reminder**: We will never ask you to create a help ticket "
            "on a different Discord server or unofficial site, and our "
            "official site is <https://parsec.app>. Be weary of shady "
            "websites and notify `@ModTag` if there are any concerns.")

        self.warned_against_user_previously.add(message.author)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        has_reposted = await self.handle_reposts(message)

        if not has_reposted:
            return

        await self.handle_link_reminder(message)

    @commands.Cog.listener()
    async def on_message_edit(self, _, after: discord.Message):
        now = datetime.datetime.now(datetime.timezone.utc)
        ten_minutes = datetime.timedelta(minutes=10)

        if now - after.created_at > ten_minutes:
            return

        await self.handle_link_reminder(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        await self.handle_logging_message_deletion(message)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
