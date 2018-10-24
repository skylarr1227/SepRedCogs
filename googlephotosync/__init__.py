from redbot.core.bot import Red
from .googlephotosync import GooglePhotoSync


def setup(bot: Red):
    bot.add_cog(GooglePhotoSync(bot))
