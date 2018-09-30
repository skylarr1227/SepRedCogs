from . import EmbedReply
from . import colors


class InfoEmbedReply(EmbedReply):

    def __init__(self, message: str):
        super(InfoEmbedReply, self).__init__(message=message, color=colors.INFO, emoji="ℹ️")
