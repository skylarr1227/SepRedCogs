from . import EmbedReply
from . import colors


class SuccessEmbedReply(EmbedReply):

    def __init__(self, message: str):
        super(SuccessEmbedReply, self).__init__(message=message, color=colors.SUCCESS, emoji="✅")
