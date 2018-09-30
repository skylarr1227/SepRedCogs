from ...constants.colors import HexColors
from .embedreply import EmbedReply


class InfoReply(EmbedReply):
    def __init__(self, message: str):
        super(InfoReply, self).__init__(message=message, color=HexColors.INFO, emoji="\N{INFORMATION SOURCE}")