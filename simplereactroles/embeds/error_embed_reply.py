from . import EmbedReply
from . import colors


class ErrorEmbedReply(EmbedReply):

    def __init__(self, message: str):
        super(ErrorEmbedReply, self).__init__(message=message, color=colors.ERROR, emoji="❌")
