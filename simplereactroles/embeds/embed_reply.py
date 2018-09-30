from typing import Optional

import discord

class EmbedReply(object):

    def __init__(self, message: str, color: int, emoji: Optional[str] = None):
        self.emoji = emoji
        self.message = message
        self.color = color

    def build_message(self):
        return_msg = "{}" + self.message
        prefix = f"{self.emoji} " if self.emoji is not None else ""
        return return_msg.format(prefix)

    def build(self) -> discord.Embed:
        return discord.Embed(description=self.build_message(), color=self.color)

    async def send(self, messageable: discord.abc.Messageable):
        return await messageable.send(embed=self.build())
