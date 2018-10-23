from typing import Tuple, Dict, Union

import discord
from cog_shared.seplib.responses.embeds import ErrorReply
from embedbuilder.types import BasicEmbed, ReplaceEmbed
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

    async def _check_send_channel_permissions(self, channel: discord.TextChannel) -> Tuple[bool, str]:

        if channel is None:
            response = (False, "Specified channel does not exist in this server.")
        else:
            bot_member = channel.guild.me  # type: discord.Member

            if not channel.permissions_for(bot_member).send_messages:
                response = (False, "Bot cannot send messages to this channel.")  # TODO: Strings
            else:
                response = (True, "Permissions passed")

        return response

    async def _check_replace_permissions(self, message: discord.Message):

        if message is None:
            response = (False, "Specified message does not exist in this server.")
        else:
            bot_member = message.channel.guild.me  # type: discord.Member
            if not message.author == bot_member:
                response = (False, "Specified message was not authored by the bot.")
            else:
                response = (True, "Permissions passed")
        return response

    def _parse_basic_message(self, msg: str) -> BasicEmbed:
        channel_id = int(msg.split('# StartChannel\n')[1].split('\n# EndChannel')[0])

        description = msg.split('# StartDescription\n')[1].split('\n# EndDescription')[0]
        color_str = msg.split('# StartColor\n')[1].split('\n# EndColor')[0]
        return BasicEmbed(channel_id=channel_id, description=description, color_str=color_str)

    def _parse_replace_message(self, msg: str) -> ReplaceEmbed:
        basic = self._parse_basic_message(msg)

        message_id = int(msg.split('# StartMessage\n')[1].split('\n# EndMessage')[0])
        return ReplaceEmbed(channel_id=basic.channel_id, description=basic.description, color_str=basic.color_str,
                            message_id=message_id)

    async def _send_basic_embed(self, channel: discord.TextChannel, parsed_embed: BasicEmbed):

        discord_embed = discord.Embed(description=parsed_embed.description, color=parsed_embed.color)

        await channel.send(embed=discord_embed)

    async def _send_replace_basic_embed(self, message: discord.Message,
                                        parsed_embed: ReplaceEmbed):
        discord_embed = discord.Embed(description=parsed_embed.description, color=parsed_embed.color)
        await message.edit(embed=discord_embed)

    @commands.group(name="embed", invoke_without_command=True)
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _embed(self, ctx: Context, *, msg: str):
        self.logger.error('EMBED')
        try:
            parsed_message = self._parse_basic_message(msg)
        except (IndexError, ValueError) as e:
            self.logger.info("Invalid message format found. {}".format(e))
            return await ErrorReply("Invalid embed format.").send(ctx)

        channel = discord.utils.get(iterable=ctx.guild.channels, id=parsed_message.channel_id)

        has_permission, response = await self._check_send_channel_permissions(channel=channel)
        if not has_permission:
            return await ErrorReply(response).send(ctx)

        return await self._send_basic_embed(channel=channel, parsed_embed=parsed_message)

    @_embed.command(name="replace")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def _embed_replace(self, ctx: Context, *, msg: str):
        # parse message -- get message ID from the message
        # confirm the message:
        #   1. Bot needs to be the author of the message
        #   2. Bot has permissions to send_messages
        try:
            parsed_message = self._parse_replace_message(msg)
        except (ValueError, IndexError) as e:
            self.logger.info("Invalid message format found. {}".format(e))
            return await ErrorReply("Invalid embed format.").send(ctx)

        channel = discord.utils.get(iterable=ctx.guild.channels,
                                    id=parsed_message.channel_id)  # type: discord.TextChannel
        has_channel_permissions, response = await self._check_send_channel_permissions(channel=channel)
        if not has_channel_permissions:
            return await ErrorReply(response).send(ctx)
        message = await channel.get_message(id=parsed_message.message_id)

        has_message_permissions, response = await self._check_replace_permissions(message)

        if not has_message_permissions:
            return await ErrorReply(response).send(ctx)

        return await self._send_replace_basic_embed(message=message, parsed_embed=parsed_message)
