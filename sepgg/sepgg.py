import json
import re
from typing import Union, Tuple

import discord
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib import validators
from cog_shared.seplib.aws.sqs import SQS
from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.responses.embeds import ErrorReply


class SepGG(BaseSepCog):

    SHORTLINK_PATH_REGEX = re.compile("^[A-Za-z\d][A-Za-z\d_]*$")

    def __init__(self, bot: Red):
        super(SepGG, self).__init__(bot=bot)

        self.aws_config_cache = {}

        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_global(aws_config={})
        config.register_global(shortlink_queue="")

    async def _init_cache(self):
        await self.bot.wait_until_ready()

        aws_config = await self.config.aws_config()

        self.aws_config_cache = aws_config

    async def _set_aws_config(self, ctx: Context, access_key: str, access_secret: str, region: str = 'us-east-1'):

        aws_config = {
            'access_key': access_key,
            'access_secret': access_secret,
            'region': region,
        }

        # update the cache
        self.aws_config_cache.update(aws_config)
        # update the db
        await self.config.aws_config.set(self.aws_config_cache)
        self.logger.info(f"{ctx.author} updated the AWS configuration")

    async def _set_single_aws_config(self, ctx: Context, setting: str, value: Union[str, int, dict]):

        self.aws_config_cache[setting] = value

        await self.config.aws_config.set(self.aws_config_cache)
        self.logger.info(f"{ctx.author} updated single AWS config setting: {setting}")

    async def _is_not_guild_and_delete(self, ctx: Context) -> Tuple[bool, str]:
        if ctx.guild is not None and not isinstance(ctx.channel, discord.DMChannel):
            # we're not in a guild. Delete the command message if we can.
            self.logger.warn(f"{ctx.author} Attempted to put AWS access keys in a chat channel! "
                             f"Deleting! g:{ctx.guild.id}|c:{ctx.channel.id}")
            await ctx.channel.delete_messages([ctx.message])
            return (False, f"{ctx.author.mention} For security purposes, "
                           f"this command must be run via whisper/DM to me.")
        self.logger.info("Command not executed in a guild. Continuing...")
        return True, ""

    async def _get_shortlink_queue_name(self):
        return await self.config.shortlink_queue()

    async def _set_shortlink_queue_name(self, queue_name: str):
        return await self.config.shortlink_queue.set(queue_name)

    @staticmethod
    def _clean_shortlink_path(path: str) -> str:
        return path.lstrip('/').rstrip('/')

    def _is_valid_shortlink_path(self, path: str) -> bool:
        clean_path = self._clean_shortlink_path(path)

        return True if self.SHORTLINK_PATH_REGEX.match(clean_path) is not None else False

    async def _add_shortlink_to_sqs_queue(self, clean_path: str, url: str):
        queue_name = await self._get_shortlink_queue_name()

        sqs = SQS(**self.aws_config_cache)

        message_body = json.dumps({
            'key': clean_path,
            'url': url
        })

        self.logger.info(f"Adding shortlink to SQS queue: q:{queue_name}|k:{clean_path}|u:{url}")
        response = sqs.send_message(queue_name=queue_name, body=message_body)
        self.logger.info(f"Successfully added shortlink: {clean_path}")
        return response

    @commands.group(name='sepgg', invoke_without_command=True)
    @checks.mod_or_permissions()
    async def _sepgg(self, ctx: Context):
        """
        Set of commands for configuring sep.gg related items.
        """
        return await ctx.send_help()

    @_sepgg.group(name='config', invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _sepgg_config(self, ctx: Context):
        """
        Configuration submodule for sep.gg
        """
        return await ctx.send_help()

    @_sepgg_config.command(name='aws')
    @checks.admin_or_permissions()
    async def _sepgg_config_aws(self, ctx: Context, aws_key_id: str, aws_key_secret: str, region: str = 'us-east-1'):
        """
        Sets the AWS configuration that the Cog will use.

        You are responsible for creating this IAM user in your AWS account.

        Allow Policy Actions:
        - sqs:DeleteMessage
        - sqs:GetQueueUrl
        - sqs:DeleteMessageBatch
        - sqs:SendMessageBatch
        - sqs:PurgeQueue
        - sqs:SendMessage
        - sqs:GetQueueAttributes
        """
        is_dm, response = await self._is_not_guild_and_delete(ctx)

        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_aws_config(ctx=ctx, access_key=aws_key_id, access_secret=aws_key_secret, region=region)
        await ctx.tick()

    @_sepgg.group(name='set', invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _sepgg_set(self, ctx: Context):
        """
        Set a specific configuration value for a cog submodule.
        """
        return await ctx.send_help()

    @_sepgg_set.group(name='aws', invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _sepgg_set_aws(self, ctx: Context):
        """
        Set a specific value for the Cog's AWS configuration.
        """
        return await ctx.send_help()

    @_sepgg_set_aws.command(name='key')
    @checks.admin_or_permissions()
    async def _sepgg_set_aws_key(self, ctx: Context, aws_key_id: str):
        """
        Sets the AWS Access Key ID for the Cog's IAM user.
        """
        is_dm, response = self._is_not_guild_and_delete(ctx)

        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_single_aws_config(ctx=ctx, setting='access_key', value=aws_key_id)
        await ctx.tick()

    @_sepgg_set_aws.command(name='secret')
    @checks.admin_or_permissions()
    async def _sepgg_set_aws_secret(self, ctx: Context, aws_key_secret: str):
        """
        Sets the AWS Access Key Secret the Cog's IAM user.
        """
        is_dm, response = self._is_not_guild_and_delete(ctx)

        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_single_aws_config(ctx=ctx, setting='access_secret', value=aws_key_secret)
        await ctx.tick()

    @_sepgg_set_aws.command(name='region')
    @checks.admin_or_permissions()
    async def _sepgg_set_aws_region(self, ctx: Context, region: str):
        """
        Sets the AWS Region for the Cog.
        """
        is_dm, response = self._is_not_guild_and_delete(ctx)

        if not is_dm:
            return await ErrorReply(response).send(ctx)

        await self._set_single_aws_config(ctx=ctx, setting='region', value=region)
        await ctx.tick()

    @_sepgg_set.group(name='shortlink', invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _sepgg_set_shortlink(self, ctx: Context):
        """
        Set a specific value for the Cog's Shortlink configuration.
        """
        await ctx.send_help()

    @_sepgg_set_shortlink.command(name='queue')
    @checks.admin_or_permissions()
    async def _sepgg_set_shortlink_queue(self, ctx: Context, queue_name: str):
        """
        Sets the AWS SQS queue name to use for adding shortlinks.

        This queue triggers an AWS Lambda function which adds it to the sep.gg shortlink Redis database.
        """
        await self._set_shortlink_queue_name(queue_name=queue_name)
        await ctx.tick()

    @_sepgg.group(name="shortlink", aliases=['sl'], invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _sepgg_sl(self, ctx: Context):
        """
        Control shortlinks on sep.gg
        """
        return await ctx.send_help()

    @_sepgg_sl.command(name='add')
    @checks.admin_or_permissions()
    async def _sepgg_sl_add(self, ctx: Context, path: str, url: str):
        """
        Add or overwrite a shortlink.

        - Path must contain alpha-numeric characters or underscore.
        - Path must not start with an underscore.
        - URL must be prefixed with http or https.
        - URL must be in a valid format.
        """
        if not validators.url.is_valid_url(url=url):
            return await ErrorReply("That is not a valid URL").send(ctx)

        if not self._is_valid_shortlink_path(path):
            return await ErrorReply("That is not a valid shortlink path.").send(ctx)

        # confirm AWS i configures
        if None in [self.aws_config_cache.get(k) for k in ('access_key', 'access_secret', 'region')]:
            return await ErrorReply("AWS is not configured. Please run the `configure aws` command.").send(ctx)
        if self._get_shortlink_queue_name is None:
            return await ErrorReply("Shortlink SQS queue name is not specified. "
                                    "Please run the `set shortlink queue` command.").send(ctx)

        await self._add_shortlink_to_sqs_queue(clean_path=self._clean_shortlink_path(path), url=url)
        await ctx.tick()
