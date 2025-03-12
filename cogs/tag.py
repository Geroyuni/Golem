import xml.etree.ElementTree as ET
from contextlib import suppress
from typing import Union
import pickle
import string

from discord import app_commands, Interaction
from discord.ext import commands, tasks
import discord
import aiohttp


URL_CODES_JSON = "https://public.parsec.app/data/errors/codes.json"
URL_SITEMAP_XML = "https://support.parsec.app/hc/sitemap.xml"
USERS_WITH_EDIT_PERMISSION = (
    124207277174423552,  # Kodikuu
    141336932213981184,  # Skippy
    289887222310764545)  # Borgo


class CommandsTag(commands.Cog):
    """Implementation for the tag commands used for support."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = self.load_db()
        self.codes = {}
        self.articles = {}

        self.auto_db_save.start()
        self.auto_fetch_codes_and_sitemap.start()

        self.bot.tree.add_command(app_commands.ContextMenu(
            name="Send tags in this message",
            callback=self.send_tags_menu))

    def load_db(self):
        """Load pickle database."""
        try:
            with open("db.p", "rb") as file:
                db = pickle.load(file)
        except FileNotFoundError:
            db = {}

        return db

    def save_db(self):
        """Save pickle database if applicable."""
        if not self.db:
            return

        with open("db.p", "wb") as file:
            pickle.dump(self.db, file)

    async def fetch_codes_and_sitemap(self):
        """Fetch the Parsec codes and the support page sitemap."""
        xml = None
        with suppress(aiohttp.ClientConnectorError):
            async with aiohttp.ClientSession() as session:
                async with session.get(URL_CODES_JSON) as resp:
                    if resp.status == 200:
                        self.codes = await resp.json()

                async with session.get(URL_SITEMAP_XML) as resp:
                    if resp.status == 200:
                        xml = await resp.text()

        if not xml:
            return

        namespaces = {"ns0": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        root = ET.fromstring(xml)

        for url in root.findall("ns0:url/ns0:loc", namespaces):
            if url.text == "https://support.parsec.app/hc/en-us":
                continue

            url, title = url.text.replace("/en-us/", "/").split("-", 1)
            title = title.replace("-", " ")

            self.articles[title] = url

    @tasks.loop(minutes=1)
    async def auto_db_save(self):
        """Save database every minute to avoid unexpected data loss."""
        self.save_db()

    @tasks.loop(hours=5)
    async def auto_fetch_codes_and_sitemap(self):
        """Keep stored codes and sitemap updated by fetching every 5 hours."""
        await self.fetch_codes_and_sitemap()

    @staticmethod
    def can_edit(itx: Interaction):
        """Check to allow bot owner and specific user IDs to edit tags."""
        return (
            itx.user == itx.client.owner
            or itx.user.id in USERS_WITH_EDIT_PERMISSION)

    def get_custom_tag_responses(self, query: str):
        """Get responses for custom tags in database based on the query."""
        custom_tag_responses = []
        for main_tag_name, value in self.db.items():
            for name in [main_tag_name] + value["aliases"]:
                if name in query.lower():
                    custom_tag_responses.append(value["content"])
                    break

        return custom_tag_responses

    def get_code_responses(self, query: str):
        """Get responses for error codes based on the query."""
        for character in string.punctuation.replace("-", ""):
            query = query.replace(character, "")

        code_responses = []
        codes_sorted_decreasing_and_signless = sorted(
            self.codes.items(), key=lambda i: abs(int(i[0])), reverse=True)

        for code, details in codes_sorted_decreasing_and_signless:
            if code in query.split() or code.replace("-", "") in query.split():
                code_response = [
                    f"## [{code}] {details['title'] or details['desc']}"]

                if details["title"]:
                    code_response.append(details["desc"])
                if details["url"]:
                    code_response.append(
                        f"[**Read the article for more details**]"
                        f"(<{details['url']}>)")

                code_responses.append("\n".join(code_response))

        return code_responses

    async def tag_base(
        self,
        itx: Interaction,
        query: str,
        mention_user: Union[discord.Member, discord.User, None],
        private: bool = False
    ):
        """The tag functionality for tag command and the context menu."""

        if mention_user == itx.client.user:
            await itx.response.send_message("yep thats me.", ephemeral=True)
            return

        response = []
        allowed_mentions = discord.AllowedMentions.none()

        if query in self.articles:
            response.append(f"**[{query}](<{self.articles[query]}>)**")
        else:
            response.extend(self.get_custom_tag_responses(query))
            response.extend(self.get_code_responses(query))

        if not response:
            await itx.response.send_message("(nothing found)", ephemeral=True)
            return

        if len(response) > 4:
            await itx.response.send_message(
                "there are just too many tags in this", ephemeral=True)
            return

        if mention_user:
            response.insert(0, f"-# (for {mention_user.mention})")
            allowed_mentions.users = [mention_user]

        await itx.response.send_message(
            "\n".join(response),
            ephemeral=private,
            allowed_mentions=allowed_mentions)

    @app_commands.command()
    async def tag(
        self,
        itx: Interaction,
        query: str,
        mention_user: Union[discord.Member, discord.User, None],
        private: bool = False
    ):
        """Search for a code, article or bot tag.

        :param query: Error code, article name or custom bot tag
        :param mention_user: A specific user to mention in the bot message
        :param private: Show result only to you (false by default)
        """

        await self.tag_base(itx, query, mention_user, private)

    @app_commands.check(can_edit)
    @app_commands.command()
    async def edit_tag(self, itx: Interaction, tag_name: str):
        """Edit a custom tag."""
        for main_tag_name, value in self.db.items():
            for name in [main_tag_name] + value["aliases"]:
                if tag_name.lower().strip() == name:
                    tag_name = main_tag_name
                    break

        await itx.response.send_modal(
            EditTagModal(self.db, tag_name.lower().strip()))

    def autocomplete_base(self, current, *, custom_tags_only=False):
        """Autocomplete for /tag and /edit_tag commands."""
        choices = []

        for name, value in self.db.items():
            if value["aliases"]:
                aliases = ", ".join(value["aliases"])
                choices.append(app_commands.Choice(
                    name=f"{name} (aliases: {aliases})"[:99], value=name))
            else:
                choices.append(app_commands.Choice(name=name[:99], value=name))

        if current and not custom_tags_only:
            for name in list(self.codes.keys()) + list(self.articles.keys()):
                choices.append(app_commands.Choice(name=name[:99], value=name))

        return [c for c in choices if current.lower() in c.name.lower()][:15]

    @tag.autocomplete("query")
    async def tag_autocomplete(self, itx: Interaction, current: str):
        return self.autocomplete_base(current)

    @edit_tag.autocomplete("tag_name")
    async def edit_tag_autocomplete(self, itx: Interaction, current: str):
        return self.autocomplete_base(current, custom_tags_only=True)

    async def send_tags_menu(self, itx: Interaction, message: discord.Message):
        await self.tag_base(itx, message.clean_content, message.author)

    async def cog_unload(self):
        self.save_db()


class EditTagModal(discord.ui.Modal, title="Edit tag"):
    """The modal that pops up when editing a custom tag with /edit_tag."""

    def __init__(self, db, tag_name):
        super().__init__()
        self.db = db
        self.tag_name = tag_name
        self.tag_dict = self.db.get(tag_name)
        self.content = self.tag_dict["content"] if self.tag_dict else None
        self.aliases = self.tag_dict["aliases"] if self.tag_dict else []

        self.add_item(discord.ui.TextInput(
            label="Name",
            default=self.tag_name,
            placeholder="Leave empty to remove tag",
            required=False))

        self.add_item(discord.ui.TextInput(
            label="Content",
            default=self.content,
            placeholder="Type the content or leave empty to remove tag.",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=False))

        self.add_item(discord.ui.TextInput(
            label="Aliases (split by ,)",
            default=", ".join(self.aliases),
            placeholder="dog, water",
            max_length=2000,
            required=False))

    async def on_submit(self, itx: Interaction):
        tag_name, content, aliases = [c.value for c in self.children]

        if not tag_name or not content:
            self.db.pop(self.tag_name, None)
        else:
            tag_name = tag_name.lower().strip()
            content = content.strip()
            aliases = [a.lower().strip() for a in aliases.split(",")]

            if not aliases[0]:
                aliases = []

            if self.tag_name != tag_name:
                self.db.pop(self.tag_name, None)

            self.db[tag_name] = {}
            self.db[tag_name]["content"] = content
            self.db[tag_name]["aliases"] = aliases

        await itx.response.defer()


async def setup(bot):
    await bot.add_cog(CommandsTag(bot))
