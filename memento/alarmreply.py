import discord
from cog_shared.seplib.constants.colors import HexColors
from cog_shared.seplib.responses.embeds import EmbedReply


class AlarmReply(EmbedReply):
    TITLE_EMOJI = "\N{ALARM CLOCK}"
    TITLE = "{} Reminder! [Memento]".format(TITLE_EMOJI)

    def __init__(self, message):
        super(AlarmReply, self).__init__(message=message, emoji=None, color=HexColors.Red)

    def build(self) -> discord.Embed:
        return discord.Embed(description=self.build_message(), color=self.color, title=self.TITLE)

