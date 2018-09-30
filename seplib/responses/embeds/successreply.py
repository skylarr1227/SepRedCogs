from ...constants.colors import HexColors
from .embedreply import EmbedReply


class SuccessReply(EmbedReply):
    def __init__(self, message: str):
        super(SuccessReply, self).__init__(message=message, color=HexColors.SUCCESS, emoji="\N{WHITE HEAVY CHECK MARK}")