from redbot.core.bot import Red
from .twitchlive import TwitchLive


def setup(bot: Red):
    bot.add_cog(TwitchLive(bot))
