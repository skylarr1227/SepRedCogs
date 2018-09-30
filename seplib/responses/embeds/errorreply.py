from ...constants.colors import HexColors
from .embedreply import EmbedReply


class ErrorReply(EmbedReply):
    def __init__(self, message: str):
        super(ErrorReply, self).__init__(message=message, color=HexColors.ERROR, emoji="\N{CROSS MARK}")