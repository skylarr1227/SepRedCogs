from redbot.core.bot import Red
from .sepgg import SepGG


def setup(bot: Red):
    bot.add_cog(SepGG(bot))
