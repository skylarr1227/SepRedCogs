import asyncio
import logging
from logging import Logger
from typing import Dict

import boto3
import botocore.exceptions
import watchtower
from redbot.core.bot import Red

AWS_CONFIG_COG_NAME = "AWSConfig"
AWS_CONFIG_WAIT_POLL = 0.1
AWS_CONFIG_WAIT_TIMEOUT = 10
CLOUDWATCH_LOG_GROUP_NAME_F = "/discord/red/{}"
CLOUDWATCH_FORMATTER = "%(levelname)s %(module)s %(funcName)s %(lineno)d: %(message)s"


async def set_cloudwatch_handler(cog: object, bot: Red, logger: Logger):
    cog_name = cog.__class__.__name__

    # create a coroutine which will be used to wait for the AWSConfig cog to be loaded
    # the "infinite" while True loop is safe since we will be limiting it with an asyncio timeout
    async def ensure_awsconfig():
        while True:
            cog_loaded = bot.get_cog(AWS_CONFIG_COG_NAME)
            if cog_loaded:
                return  # the cog is loaded
            await asyncio.sleep(AWS_CONFIG_WAIT_POLL)

    # wait for AWSConfig to be loaded
    try:
        await asyncio.wait_for(ensure_awsconfig(), AWS_CONFIG_WAIT_TIMEOUT)
    except asyncio.TimeoutError:
        logger.info(f"[CloudWatch Logs] During {cog_name} init, could not retrieve {AWS_CONFIG_COG_NAME} cog. "
                    f"It may not be loaded.")
        return

    # do another sanity check
    aws_config_cog = bot.get_cog(AWS_CONFIG_COG_NAME)
    if not aws_config_cog:
        return

    aws_config = await aws_config_cog.get_aws_config()  # type: Dict[str, str]
    if not aws_config:  # make sure the config is set and cached
        logger.info(f"[CloudWatch Logs] During {cog_name} init, AWSConfig is loaded, but is not configured.")

    __init_cloudwatch_log_handler(aws_config=aws_config, cog_name=cog_name, bot=bot, logger=logger)


def __init_cloudwatch_log_handler(aws_config: Dict[str, str], cog_name: str, bot: Red,
                                  logger: Logger):
    try:
        session = boto3.Session(aws_access_key_id=aws_config.get("aws_access_key_id"),
                                aws_secret_access_key=aws_config.get("aws_secret_access_key"),
                                region_name=aws_config.get("region"))

        log_group = CLOUDWATCH_LOG_GROUP_NAME_F.format(bot.user)
        cw_handler = watchtower.CloudWatchLogHandler(boto3_session=session, log_group=log_group)
        cw_handler.setFormatter(logging.Formatter(CLOUDWATCH_FORMATTER))
        logger.addHandler(hdlr=cw_handler)
    except botocore.exceptions.ClientError as e:
        logger.error(f"[CloudWatch Logs] Cog: {cog_name} | Error initializing CloudWatch handler. AWS Response: {e}")
        return
    except Exception as ue:
        logger.error(f"[CloudWatch Logs] Cog: {cog_name} | Error initializing CloudWatch handler. "
                     f"An unknown error occurred: {ue}")
        return
