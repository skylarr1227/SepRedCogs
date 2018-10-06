from redbot.core.bot import Red
from .embedbuilder import EmbedBuilder


def setup(bot: Red):
    bot.add_cog(EmbedBuilder(bot))
