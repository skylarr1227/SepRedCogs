from typing import Optional

import discord


class EmbedReply(object):

    def __init__(self, message: str, color: int, emoji: Optional[str] = None):
        self.message = message
        self.color = color
        self.emoji = emoji

        self.content = None  # type: Optional[str]

    def build_message(self):
        return_msg = "{}" + self.message
        prefix = f"{self.emoji} " if self.emoji is not None else ""
        return return_msg.format(prefix)

    def build(self) -> discord.Embed:
        return discord.Embed(description=self.build_message(), color=self.color)

    def set_content(self, content: str):
        self.content = content

    async def send(self, target: discord.abc.Messageable):
        return await target.send(content=self.content, embed=self.build())
