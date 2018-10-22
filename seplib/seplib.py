from redbot.core import commands
from redbot.core.bot import Red


class SepLib(commands.Cog):

    def __init__(self, bot: Red):
        super(SepLib, self).__init__()
        self.bot = bot

    # this cog is exclusively for imports
