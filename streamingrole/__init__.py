from redbot.core.bot import Red
from .streamingrole import StreamingRole


def setup(bot: Red):
    bot.add_cog(StreamingRole(bot))
