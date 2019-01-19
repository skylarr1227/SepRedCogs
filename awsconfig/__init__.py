from redbot.core.bot import Red
from .awsconfig import AWSConfig


def setup(bot: Red):
    bot.add_cog(AWSConfig(bot))
