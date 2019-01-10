from typing import Tuple, Optional

import discord
from redbot.core.bot import Red


class StreamAnnouncement(object):

    def __init__(self, bot: Red, guild_id: int, role_id: int, channel_id: int, twitch_name: str, stream_title: str,
                 stream_url: str, stream_id: str, user_login: str, user_thumbnail: str, stream_thumbnail: str):

        self.bot = bot

        self.guild_id = int(guild_id) if guild_id is not None else 0
        self.role_id = int(role_id) if role_id is not None else 0
        self.channel_id = int(channel_id) if channel_id is not None else 0
        self.twitch_user_login = user_login
        self.twitch_name = str(twitch_name) if twitch_name is not None else "UNKNOWN_STREAMER"
        self.stream_title = str(stream_title)
        self.stream_url = str(stream_url)
        self.stream_id = str(stream_id)
        self.user_thumbnail = str(user_thumbnail) if user_thumbnail is not None else ""
        self.stream_thumbnail_f = str(stream_thumbnail) if stream_thumbnail is not None else ""

        valid, guild, role, channel = self.__validate_announcement()

        self.is_valid = valid
        self.guild = guild
        self.role = role
        self.channel = channel

        self.__twitch_logo_url = "https://i.imgur.com/csGI2jA.png"

    def __validate_announcement(self) -> Tuple[bool, Optional[discord.Guild], Optional[discord.Role],
                                               Optional[discord.TextChannel]]:
        guild = discord.utils.get(self.bot.guilds, id=self.guild_id)
        if guild is None:
            return False, None, None, None

        role = discord.utils.get(guild.roles, id=self.role_id)
        if role is None:
            return False, guild, None, None

        channel = self.bot.get_channel(id=self.channel_id)
        if channel is None:
            return False, guild, role, None

        return True, guild, role, channel

    def get_stream_thumbnail(self, width=512, height=288):
        return self.stream_thumbnail_f.format(width=width, height=height)

    @property
    def embed(self) -> discord.Embed:

        embed = discord.Embed(title=self.stream_title, description=f"Watch now: {self.stream_url}", color=0x00ff00)

        embed.set_thumbnail(url=self.__twitch_logo_url)
        embed.set_author(name=self.twitch_name, url=self.stream_url, icon_url=self.user_thumbnail)
        embed.set_image(url=self.get_stream_thumbnail())

        return embed

    @property
    def message_content(self):
        name = self.twitch_name.replace("_", "\\_")
        return f"{self.role.mention} {name} is now live! {self.stream_url}"
