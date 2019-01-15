from redbot.core.bot import Red
from .memento import Memento


def setup(bot: Red):
    bot.add_cog(Memento(bot))
