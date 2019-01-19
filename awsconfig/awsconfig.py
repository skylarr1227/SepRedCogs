from typing import Union, Tuple, Dict

import discord
from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.responses.embeds import ErrorReply
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.commands import Context


class AWSConfig(BaseSepCog, commands.Cog):

    def __init__(self, bot: Red):
        super(AWSConfig, self).__init__(bot=bot)

        self.__aws_config_cache = {}

        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_global(aws_config={})

    async def _init_cache(self):
        await self.bot.wait_until_ready()

        aws_config = await self.config.aws_config()
        self.__aws_config_cache = aws_config if aws_config else {}

    async def get_aws_config(self) -> Dict[str, str]:
        """
        Retrieve the cached AWS configuration.
        :return: Cached AWS configuration dict with key_id, secret, and region.
        """
        if not self.__aws_config_cache:
            self.__aws_config_cache = await self.config.aws_config()
        return self.__aws_config_cache

    async def _update_aws_config(self, aws_config: Dict[str, str]):
        """
        Update both the cache and the database with the provided AWS configuration.
        :param aws_config: Dictionary of AWS configuration.
                           This should consist of one or more of keys:
                           - aws_access_key_id
                           - aws_secret_access_key
                           - region
        :return: None
        """
        self.__aws_config_cache.update(aws_config)
        await self.bot.get_cog("AWSConfig").config.aws_config.set(self.__aws_config_cache)

    async def _set_aws_config(self, ctx: Context, aws_access_key_id: str, aws_secret_access_key: str,
                              region: str = 'us-east-1'):
        """
        Sets the AWS configuration.
        :param ctx: Red-DiscordBot context.
        :param aws_access_key_id: AWS account Access Key ID
        :param aws_secret_access_key: AWS account Secret Access Key
        :param region: AWS Region (us-east-1, us-west-2, etc). If not supplied, defaults to us-east-1.
        :return: None
        """

        aws_config = {
            'aws_access_key_id': aws_access_key_id,
            'aws_secret_access_key': aws_secret_access_key,
            'region': region,
        }

        await self._update_aws_config(aws_config=aws_config)
        self.logger.info(f"{ctx.author} updated the AWS configuration")

    async def _set_single_aws_config(self, ctx: Context, setting: str, value: Union[str, int, dict]):
        """
        Sets a single AWS configuration mapping. No validation is done on the key name.
        :param ctx: Red-DiscordBot context.
        :param setting: AWS configuration mapping key (aws_access_key_id, aws_secret_access_key, etc).
        :param value: Value of the mapping key.
        :return: None
        """
        update_config = {setting: value}
        await self._update_aws_config(aws_config=update_config)
        self.logger.info(f"{ctx.author} updated single AWS config setting: {setting}")

    async def _delete_if_not_dm(self, ctx: Context) -> Tuple[bool, str]:
        """
        Checks if a message/command was executed in a DM. If it wasn't, delete the message (if possible)
        and warn the user not to use this command outside of a DM.
        :param ctx: Red-DiscordBot context in which the command was executed.
        :return: Tuple, with the left value being Success/Error boolean and right value being the error message.
        """
        if ctx.guild is not None and not isinstance(ctx.channel, discord.DMChannel):
            # we're not in a guild. Delete the command message if we can.
            self.logger.warn(f"{ctx.author} Attempted to put AWS access keys in a chat channel! "
                             f"Deleting! g:{ctx.guild.id}|c:{ctx.channel.id}")
            try:
                await ctx.channel.delete_messages([ctx.message])
                return (False, f"{ctx.author.mention} For security purposes, "
                               f"this command must be run via whisper/DM to me.")
            except discord.DiscordException as e:
                self.logger.error("Unable to delete the message because Discord returned an error response. "
                                  f"Error: {e}")
                return (False, f"{ctx.author.mention} For security purposes, "
                               f"this command must be run via whisper/DM to me. Please delete your message!")
        self.logger.info("Command executed in a DM. OK to proceed.")
        return True, ""

    @commands.group(name="awsconfig", aliases=["aws"], invoke_without_command=True)
    async def _awsconfig(self, ctx: Context):
        """
        AWSConfig is a cog used to set and store AWS connection configuration (key, secret, region, etc).

        This configuration can then be used by other supported Cogs to connect to AWS.
        """
        await ctx.send_help()

    @_awsconfig.command(name="config")
    @checks.admin_or_permissions()
    async def _awsconfig_config(self, ctx: Context, aws_access_key_id: str, aws_secret_access_key: str,
                                region: str = "us-east-1"):
        """
        Sets the AWS configuration Access Key ID, Secret Access Key, and region.

        If region is not provided, it will default to "us-east-1".

        Command MUST be executed in a DM to the bot.
        """
        # confirm this command was sent in a DM
        is_dm, response = await self._delete_if_not_dm(ctx)
        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_aws_config(ctx=ctx, aws_access_key_id=aws_access_key_id,
                                   aws_secret_access_key=aws_secret_access_key,
                                   region=region)
        await ctx.tick()

    @_awsconfig.group(name="set", invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _awsconfig_set(self, ctx: Context):
        """
        Sets a single AWS configuration value.

        Commands MUST be executed in a DM to the bot.
        """
        await ctx.send_help()

    @_awsconfig_set.command(name="key_id", invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _awsconfig_set_key_id(self, ctx: Context, aws_access_key_id: str):
        """
        Sets the AWS configuration Access Key ID.
        """
        # confirm this command was sent in a DM
        is_dm, response = await self._delete_if_not_dm(ctx)
        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_single_aws_config(ctx=ctx, setting='aws_access_key_id', value=aws_access_key_id)
        await ctx.tick()

    @_awsconfig_set.command(name="secret", invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _awsconfig_set_secret(self, ctx: Context, aws_secret_access_key: str):
        """
        Sets the AWS configuration Secret Access Key.

        Command MUST be executed in a DM to the bot.
        """
        # confirm this command was sent in a DM
        is_dm, response = await self._delete_if_not_dm(ctx)
        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_single_aws_config(ctx=ctx, setting='aws_secret_access_key', value=aws_secret_access_key)
        await ctx.tick()

    @_awsconfig_set.command(name="region", invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _awsconfig_set_region(self, ctx: Context, region: str):
        """
        Sets the AWS configuration region (us-east-1, us-west-2, etc).

        Command MUST be executed in a DM to the bot.
        """
        # confirm this command was sent in a DM
        is_dm, response = await self._delete_if_not_dm(ctx)
        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_single_aws_config(ctx=ctx, setting='region', value=region)
        await ctx.tick()
