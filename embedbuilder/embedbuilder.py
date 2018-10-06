import discord
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib.classes.basesepcog import BaseSepCog


class EmbedBuilder(BaseSepCog):

    def __init__(self, bot: Red):
        super(EmbedBuilder, self).__init__(bot=bot)

        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        pass

    async def _init_cache(self):
        pass

    @commands.group(name="embed", invoke_without_command=True)
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _embed(self, ctx: Context):
        await ctx.send_help()


    @_embed.commands(name="create")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _embed(self, ctx: Context, msg: str):
        message = ctx.message  # type: discord.Message

        var = True