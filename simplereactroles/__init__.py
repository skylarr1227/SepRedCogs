from redbot.core.bot import Red
from .simplereactroles import SimpleReactRoles


def setup(bot: Red):
    bot.add_cog(SimpleReactRoles(bot))
