from discord.ext import commands
import discord

NOTIFICATIONS_CHANNEL = "safety_notifications"


class Moderation(commands.Cog):
    """Handle moderation stuff that Discord itself doesn't do."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Warn in notifications channel about any user deleted message."""
        if message.author.bot:
            return

        channel = discord.utils.get(
            message.guild.channels, name=NOTIFICATIONS_CHANNEL)

        if not channel:
            return

        content_in_quotes = "> " + message.content.replace("\n", "\n> ")

        await channel.send(
            f"{message.author.mention}'s message was deleted "
            f"in {message.channel.mention}:"
            f"\n{content_in_quotes or '> (empty)'}",
            suppress_embeds=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
