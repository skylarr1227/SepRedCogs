from redbot.core.bot import Red
from .botstats import BotStats


def setup(bot: Red):
    bot.add_cog(BotStats(bot))
