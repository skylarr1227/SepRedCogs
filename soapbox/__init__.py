from redbot.core.bot import Red
from .soapbox import Soapbox


def setup(bot: Red):
    bot.add_cog(Soapbox(bot))
