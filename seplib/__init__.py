from redbot.core.bot import Red

from .seplib import SepLib


def setup(bot: Red):
    bot.add_cog(SepLib(bot))