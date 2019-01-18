import discord
from cog_shared.seplib.constants.colors import HexColors
from cog_shared.seplib.responses.embeds import EmbedReply


class MementoEmbedReply(EmbedReply):

    TITLE_EMOJI = "\N{ALARM CLOCK}"

    def __init__(self, title: str, message: str, color=HexColors.Red):
        super(MementoEmbedReply, self).__init__(message=message, emoji=None, color=color)
        self.title_text = title
        self.TITLE = "{} {} [Memento]".format(self.TITLE_EMOJI, self.title_text)

    def build(self):
        return discord.Embed(description=self.build_message(), color=self.color, title=self.TITLE)
