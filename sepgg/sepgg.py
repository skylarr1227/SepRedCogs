import json
import re
from typing import Union, Tuple, Dict

import discord
from awsconfig import AWSConfig
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib import validators
from cog_shared.seplib.aws.sqs import SQS
from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.responses.embeds import ErrorReply


class SepGG(BaseSepCog, commands.Cog):

    SHORTLINK_PATH_REGEX = re.compile("^[A-Za-z\d][A-Za-z\d_]*$")

    def __init__(self, bot: Red):
        super(SepGG, self).__init__(bot=bot)

        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_global(shortlink_queue="")

    async def _init_cache(self):
        pass

    async def _get_aws_config(self) -> Dict[str, str]:
        awsconfig_cog = self.bot.get_cog("AWSConfig")  # type: AWSConfig

        aws_config = {}
        if awsconfig_cog is not None:
            aws_config = await awsconfig_cog.get_aws_config()
        return aws_config

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
        aws_config = await self._get_aws_config()
        sqs = SQS(**aws_config)

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

    @_sepgg.group(name='set', invoke_without_command=True)
    @checks.admin_or_permissions()
    async def _sepgg_set(self, ctx: Context):
        """
        Set a specific configuration value for a cog submodule.
        """
        return await ctx.send_help()

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

        The IAM user configured with AWSConfig must have the following policy allowances on the queue ARN:

        Allow Policy Actions:
        - sqs:DeleteMessage
        - sqs:GetQueueUrl
        - sqs:DeleteMessageBatch
        - sqs:SendMessageBatch
        - sqs:PurgeQueue
        - sqs:SendMessage
        - sqs:GetQueueAttributes
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
        aws_config = await self._get_aws_config()
        if None in [aws_config.get(k) for k in ('aws_access_key_id', 'aws_secret_access_key', 'region')]:
            return await ErrorReply("AWS is not configured. Please make sure you have the AWSConfig cog installed "
                                    "and configured.").send(ctx)
        if self._get_shortlink_queue_name is None:
            return await ErrorReply("Shortlink SQS queue name is not specified. "
                                    "Please run the `[p]sepgg set shortlink queue` command.").send(ctx)

        await self._add_shortlink_to_sqs_queue(clean_path=self._clean_shortlink_path(path), url=url)
        await ctx.tick()
