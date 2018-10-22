import discord
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib.classes.basesepcog import BaseSepCog


class EmbedBuilder(BaseSepCog, commands.Cog):

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
        """
        This is the help
        """
        self.logger.error('embed group')
        await ctx.send_help()

    @_embed.command(name="basic")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _embed_basic(self, ctx: Context, *, msg: str):
        """
        Creates a basic embed with only a description/color, posted in the specified channel. See full command help for detailed message format.


        # StartDescription
        This is the embed's description text.
        It can have multiple lines and contain **markdown** and `code blocks``

        It can even contain

        ```
        Multiline Code
        Blocks
        ```

        Here's one last line to show that line breaks matter.
        # EndDescription

        # StartColor
        0x0000ff
        # EndColor

        # StartChannel
        01234567890
        # EndChannel
        """
        message_text = ctx.message.content

        channel_id = message_text.split('# StartChannel\n')[1].split('\n# EndChannel')[0]
        channel = discord.utils.get(ctx.guild.channels, id=int(channel_id))

        description = message_text.split('# StartDescription\n')[1].split('\n# EndDescription')[0]
        color_str = message_text.split('# StartColor\n')[1].split('\n# EndColor')[0]

        embed = discord.Embed(description=description, color=int(color_str, 0))
        await channel.send(embed=embed)
        pass
