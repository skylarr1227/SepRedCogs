from typing import List, Union, Tuple

import discord
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.constants.colors import HexColors
from cog_shared.seplib.responses.embeds import ErrorReply, InfoReply, SuccessReply


class Soapbox(BaseSepCog, commands.Cog):
    DEFAULT_SOAPBOX_SUFFIX = "| \N{TIMER CLOCK}"
    DEFAULT_MAX_USER_SOAPBOXES = 2

    def __init__(self, bot: Red):

        super(Soapbox, self).__init__(bot=bot)

        self.guild_config_cache = {}

        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_guild(config={})

    async def _init_cache(self):

        await self.bot.wait_until_ready()

        guilds = await self.config.all_guilds()

        guild_config = {}

        for guild_id, guild_dict in guilds.items():
            config = guild_dict.get('config')
            if config is not None:
                guild_config[str(guild_id)] = config

        self.guild_config_cache = guild_config

    async def _set_soapbox_config(self, guild: discord.Guild, trigger: discord.VoiceChannel,
                                  category: discord.CategoryChannel, max_user_channels: int,
                                  suffix: str):

        guild_cache = {
            'trigger': str(trigger.id),
            'category': str(category.id),
            'usermax': max_user_channels,
            'max_user_channels': int(max_user_channels),
            'suffix': suffix
        }

        # update the cache
        self.guild_config_cache[str(guild.id)] = guild_cache
        # update the db
        await self.config.guild(guild).config.set(guild_cache)
        self.logger.info(f"Updated the configuration for Guild: {guild.id} | {guild_cache}")

    async def _set_single_config(self, guild: discord.Guild, setting: str,
                           value: Union[str, int, discord.CategoryChannel, discord.VoiceChannel]):

        if isinstance(value, (discord.CategoryChannel, discord.VoiceChannel)):
            value = str(value.id)

        cache = self.guild_config_cache.get(str(guild.id), {})

        cache[setting] = value

        self.guild_config_cache[(str(guild.id))] = cache
        await self.config.guild(guild).config.set(cache)
        self.logger.info(f"Updated config for Guild: {guild.id} | k:{setting}|v:{value}")


    def _validate_config_setting(self, setting: str,
                                 value: Union[discord.CategoryChannel,
                                              discord.VoiceChannel, str, int]) -> Tuple[bool, str]:

        if setting.lower() == 'usermax' and value < 1:
            return (False, "Max User Channels must be greater than 0")

        return (True, "")

    def _bot_can_manage_category(self, category: discord.CategoryChannel) -> bool:
        return category.permissions_for(category.guild.me).manage_channels

    def _bot_can_manage_channels(self, channel: discord.VoiceChannel) -> bool:
        return channel.category.permissions_for(channel.guild.me).manage_channels

    def _bot_can_move_members(self, channel: discord.VoiceChannel) -> bool:
        return channel.permissions_for(channel.guild.me).move_members

    def _get_trigger_channel_id(self, guild: discord.Guild) -> str:
        return self.guild_config_cache.get(str(guild.id), {}).get('trigger')

    def _get_new_category_id(self, guild: discord.Guild) -> str:
        return self.guild_config_cache.get(str(guild.id), {}).get('category')

    def _get_max_user_channels(self, guild: discord.guild) -> int:
        value = self.guild_config_cache.get(str(guild.id), {}).get('max_user_channels')
        if value is None:
            self.logger.warn(f"Suffix not found in the cahce for Guild {guild.id}. Returning default.")
            return self.DEFAULT_MAX_USER_SOAPBOXES
        return value


    async def _is_trigger_channel(self, channel: discord.VoiceChannel) -> bool:
        return str(channel.id) == self._get_trigger_channel_id(channel.guild)

    def _get_suffix(self, guild: discord.Guild) -> str:
        suffix = self.guild_config_cache.get(str(guild.id), {}).get('suffix')  # type: str
        if suffix is None:
            self.logger.warn(f"Suffix not found in the cahce for Guild {guild.id}. Returning default.")
            return self.DEFAULT_SOAPBOX_SUFFIX
        return suffix.rstrip()

    def _is_soapbox_channel(self, channel: discord.VoiceChannel) -> bool:
        return channel.name.endswith(self._get_suffix(guild=channel.guild))

    def _channel_is_empty(self, channel: discord.VoiceChannel) -> bool:
        voice_channel = channel.guild.get_channel(channel_id=channel.id)
        return len(voice_channel.members) == 0

    async def _create_channel(self, category: discord.CategoryChannel, name: str) -> discord.VoiceChannel:
        self.logger.info(f"Creating new channel. Name: {name} | Category: {category.name}")
        return await category.guild.create_voice_channel(category=category, name=name,
                                                         reason="Created by Soapbox Cog. Temporary voice channel.")

    async def _move_member_to_channel(self, member: discord.Member, channel: discord.VoiceChannel):
        self.logger.info(f"Moving member into channel. m:{member}|c:{channel.id}")
        return await member.move_to(channel=channel, reason="Moved by Soapbox Cog. Temporary voice channel.")

    async def _move_member_and_delete_channel(self, member: discord.Member):
        self.logger.info(f"Too many user channels. Creating temporary kick channel for member {member.nick}")
        kick_channel = await member.guild.create_voice_channel(name="_DEL_{}".format(member.nick))
        self.logger.info(f"Moving member {member.nick} to kick channel: {kick_channel.name}")
        await member.move_to(kick_channel, reason="Soapbox Cog. Too many user channels. "
                                                  "Temporary channel Create to Kick.")
        self.logger.info(f"Deleting member {member.nick} kick channel: {kick_channel.name}")
        await kick_channel.delete(reason="Soapbox Cog. Delete temoprary kick channel")

    async def _create_channel_and_move(self, category_id: str, channel_name: str, member: discord.Member):
        category = discord.utils.get(member.guild.categories, id=int(category_id))  # type: discord.CategoryChannel
        new_channel = await self._create_channel(category=category, name=channel_name)
        await self._move_member_to_channel(member=member, channel=new_channel)

    @commands.group(name="soapbox", invoke_without_command=True)
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox(self, ctx: Context):
        """
        Soapbox allows members to create their own "temporary" voice channels by entering a designated Voice channel.

        **WARNING:** If you configure Soapbox, it will result in empty voice channels matching the Soapbox format to be deleted. Use the "suffix" subcommand to view the current suffix.
        """
        await ctx.send_help()

    @_soapbox.command(name="setup")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_setup(self, ctx: Context, trigger_channel: discord.VoiceChannel,
                             target_category: discord.CategoryChannel):
        """
        Configures Soapbox with the trigger voice channel and target category for the new Soapbox channel.

        This will use the default suffix and Max User Channels. To change these (and any other) config in the future, use the "soapbox set" command.

        :trigger_channel: Name of the voice channel which will trigger a new voice channel to be created on join. Use quotes if the channel name has spaces.
        :target_category: Category where the new voice channel will be created. The new channel will have the same permissions as the category. Use quotes if the category name has spaces.
        """

        # check that we can manage channels for the category
        if not self._bot_can_manage_category(target_category):
            return await ErrorReply("The bot does not have permissions to manage channels in that category.").send(ctx)

        if not self._bot_can_move_members(trigger_channel):
            return await ErrorReply("The bot does not have permissions to move members "
                                    "out of the trigger channel").send(ctx)

        await self._set_soapbox_config(guild=ctx.guild, trigger=trigger_channel, category=target_category,
                                       max_user_channels=self.DEFAULT_MAX_USER_SOAPBOXES,
                                       suffix=self.DEFAULT_SOAPBOX_SUFFIX)
        await ctx.tick()

    @_soapbox.group(name="set")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_set(self, ctx: Context):
        """
        Sets one of soapbox's configuration options for this server.
        """
        await ctx.send_help()

    @_soapbox_set.command(name="trigger")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_set_trigger(self, ctx: Context, *, voice_channel: discord.VoiceChannel):
        valid, response = self._validate_config_setting(ctx.command.name, voice_channel)
        if not valid:
            return await ErrorReply(response).send(ctx)

        await self._set_single_config(guild=ctx.guild, setting=ctx.command.name, value=voice_channel)
        await SuccessReply(f"Set the Soapbox trigger voice channel to `{voice_channel.name}`").send(ctx)

    @_soapbox_set.command(name="category")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_set_category(self, ctx: Context, * , category: discord.CategoryChannel):
        valid, response = self._validate_config_setting(ctx.command.name, category)
        if not valid:
            return await ErrorReply(response).send(ctx)

        await self._set_single_config(guild=ctx.guild, setting=ctx.command.name, value=category)
        await SuccessReply(f"Set the Soapbox category to `{category.name}").send(ctx)

    @_soapbox_set.command(name="usermax")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_set_usermax(self, ctx: Context, user_max_channels: int):
        valid, response = self._validate_config_setting(ctx.command.name, user_max_channels)
        if not valid:
            return await ErrorReply(response).send(ctx)
        await self._set_single_config(guild=ctx.guild, setting=ctx.command.name, value=user_max_channels)
        await ctx.tick()

    @_soapbox_set.command(name="suffix")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_set_suffix(self, ctx: Context, *, suffix: str):
        valid, response = self._validate_config_setting(ctx.command.name, suffix)
        if not valid:
            return await ErrorReply(response).send(ctx)

        await self._set_single_config(guild=ctx.guild, setting=ctx.command.name, value=suffix.rstrip())
        await SuccessReply(f"Set the Soapbox channel suffix to `{suffix}`. **NOTE:** You will need to manually "
                           f"cleanup old Soapbox channels.").send(ctx)

    @_soapbox.command(name="suffix")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_suffix(self, ctx: Context):
        """
        Displays the current Soapbox suffix which is appended to new temporary voice channels.
        """
        return await InfoReply("The current Soapbox suffix is set to: `{}`"
                               .format(self._get_suffix(ctx.guild))).send(ctx)

    @_soapbox.command(name="cleanup")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _soapbox_cleanup(self, ctx: Context):
        """
        Deletes all empty Soapbox channels (if possible).
        """
        channels = ctx.guild.voice_channels  # type: List[discord.VoiceChannel]

        soapbox_channels = [sb for sb in channels if sb.name.endswith(self._get_suffix(ctx.guild))]

        deleted_channels = []
        error_channels = []

        for sb in soapbox_channels:
            if self._bot_can_manage_channels(sb):
                if  len(sb.members) == 0:
                    self.logger.info(f"Deleted channel {sb.id} by user {ctx.author}")
                    await sb.delete(reason=f"Deleted by Soapbox Cog Cleanup by user {ctx.author}")
                    deleted_channels.append(sb)
            else:
                error_channels.append(sb)

        embed = discord.Embed(title="Soapbox Cleanup Report", color=HexColors.INFO)

        if not deleted_channels and not error_channels:
            embed.description = "No empty Soapbox channels were found."

        if deleted_channels:
            embed.add_field(name="Successfully Deleted", value="\n".join([f"- {dc.name}" for dc in deleted_channels]),
                            inline=False)

        if error_channels:
            embed.add_field(name="Error (permissions)", value="\n".join([f"- {dc.name}" for dc in error_channels]),
                            inline=False)

        return await ctx.send(embed=embed)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):

        before_channel = before.channel  # type: discord.VoiceChannel
        after_channel = after.channel   # type: discord.VoiceChannel


        if before_channel is None and after_channel is None:
            return  # we don't care

        # see if we can manage channels
        if after_channel is not None:
            if not self._bot_can_manage_channels(after_channel):
                self.logger.error("The bot does not have permissions to manage channels in this category: {}"
                                  .format(before_channel.category.name))
                return
            # check if this is the trigger channel
            if await self._is_trigger_channel(after_channel):
                for i in range(1, self._get_max_user_channels(after_channel.guild) + 1):
                    new_channel_name = "{member} {discr} {suffix}".format(member=member.display_name, discr=i,
                                                                          suffix=self._get_suffix(after_channel.guild))

                    # see if it exists
                    check_channel = discord.utils.get(member.guild.voice_channels, name=new_channel_name)
                    if check_channel is None:
                        # category validation
                        category = self._get_new_category_id(after_channel.guild)
                        if category is None:
                            self.logger.error(f"Soapbox category has not been configured for guild {after_channel.guild.id}")
                            return  # do nothing
                        # create the channel and move the user into it
                        return await self._create_channel_and_move(
                            category_id=self._get_new_category_id(after_channel.guild),
                            channel_name=new_channel_name,
                            member=member)
                # otherwise, message the user and tell them they can't have any more channels
                self.logger.info(f"Member: {member.id} is not allowed to create more Soapbox channels.")
                await member.send("You're only allowed to have {} temporary channels on this server."
                                         .format(self._get_max_user_channels(after_channel.guild)))
                # remove them from the trigger channel
                await self._move_member_and_delete_channel(member=member)

        elif before_channel is not None:
            if not self._bot_can_manage_channels(before_channel):
                self.logger.error("The bot does not have permissions to manage channels in this category: {}"
                                  .format(before_channel.category.name))
                return
            if self._is_soapbox_channel(before_channel) and self._channel_is_empty(before_channel):
                # channel is empty, delete it
                self.logger.info(f"Soapbox channel is empty. "
                                 f"Deleting channel: {before_channel.name}|{before_channel.id}")
                await before_channel.delete(reason="Deleted by Soapbox cog. Channel was empty")
