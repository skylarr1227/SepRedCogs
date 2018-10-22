import asyncio
import datetime
import re
from collections import defaultdict
from typing import Tuple, Union, Optional, Dict, Set

import discord
from discord import RawReactionActionEvent, RawMessageDeleteEvent, RawBulkMessageDeleteEvent
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.responses.embeds import ErrorReply, SuccessReply
from .strings import ErrorStrings, MiscStrings, DateTimeStrings, SuccessStrings
from .utils import Utils


class SimpleReactRoles(BaseSepCog, commands.Cog):

    EMOJI_REGEX = re.compile("<a?:[a-zA-Z0-9_]{2,32}:(\d{1,20})>")
    ADD_REMOVE_INTERVAL = 0.2

    def __init__(self, bot: Red):

        super(SimpleReactRoles, self).__init__(bot=bot)

        self.activated_cache = {}
        self.role_tracker = {}
        self.role_queue = asyncio.Queue()

        self._add_future(self.edit_role_loop())
        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_channel(activated={})
        config.register_guild(queues={})

    async def _init_cache(self):
        """
        Initialize the in memory cache from the Config database.
        :return: None
        """
        await self.bot.wait_until_ready()
        channels = await self.config.all_channels()

        activated_map = defaultdict(dict)

        for channel_id, channel_dict in channels.items():
            chan_active = channel_dict.get("activated", {})
            for message_id, emoji_map in chan_active.items():
                activated_map[str(channel_id)][str(message_id)] = emoji_map

        self.activated_cache = activated_map

    async def edit_role_loop(self):
        """
        Indefinitely running task which polls the role queue for new role addition/removal tasks on Members.
        Calculates the diff between add/remove roles and replaces the member's current roles in place.
        :return: None
        """
        await self.bot.wait_until_ready()

        while self == self.bot.get_cog(self.__class__.__name__):

            tracker_key = await self.role_queue.get()

            # get get an item out of the tracker
            tracker_item = self.role_tracker.pop(tracker_key, None)

            if tracker_item and tracker_item.get('member'):
                member = tracker_item.get('member')

                current_roles = set(member.roles)
                add_roles = tracker_item.get('add')
                remove_roles = tracker_item.get('remove', {member.guild.default_role})

                new_roles = (current_roles | add_roles) - remove_roles
                add_diff = add_roles - remove_roles
                remove_diff = remove_roles - add_roles
                try:
                    await member.edit(roles=new_roles)
                    self.logger.info(f"Edited Roles on Member: {member}, Guild: {member.guild.id} | "
                                     f"Removed: {remove_diff} | Added: {add_diff}")
                except (discord.Forbidden, discord.HTTPException) as de:
                    self.logger.error(f"Error calling Discord member edit API. Member: {member} | Exception: {de}"
                                      f"Will retry...")
                    self.role_tracker[tracker_key] = tracker_item
                    await self.role_queue.put(tracker_key)
                except Exception as ue:
                    self.logger.error(f"An unknown error occurred while attempting to add roles. Not re-queueing."
                                      f"Member: {member} | Exception: {ue}.")
                    self.role_queue.task_done()
                else:
                    self.role_queue.task_done()
                finally:
                    await asyncio.sleep(self.ADD_REMOVE_INTERVAL)

    async def queue_add_remove_role(self, payload: RawReactionActionEvent, add_or_remove: bool):
        """
        Adds a new add/remove role task to the queue.

        The function checks if an existing action exists for the same guild/member and updates it, removing any
        unnecessary roles. Eg. If an Add action and subsequently a Remove action happens in the same period
        of time between execution of edit_role_loop(), it will cancel it out.
        :param payload: RawReactionActionEvent from discord.py which has been validated against the
                        currently activated emoji/channel/messages.
        :param add_or_remove: bool for whether to add or remove a particular role. True = add, False = remove
        :return: None
        """
        channel_id = str(payload.channel_id)
        message_id = str(payload.message_id)
        emoji = Utils.clean_animated_emoji(str(payload.emoji))

        emoji_map = self.activated_cache.get(channel_id, {}).get(message_id, {})
        role_id = emoji_map.get(emoji)

        if role_id is not None:
            self.logger.info(f"Matched Reaction Role | c:{channel_id}|m:{message_id}|r:{role_id}|a:{add_or_remove}")

            channel = self.bot.get_channel(int(payload.channel_id))  # type: discord.TextChannel
            role = self.__get_role_by_id(channel.guild, role_id)
            member = channel.guild.get_member(payload.user_id)  # type: discord.Member

            if role and member and member != channel.guild.me:
                tracker_key = "{}|{}".format(member.guild.id, member.id)
                current_actions = self.role_tracker.get(tracker_key)
                if not current_actions:
                    current_actions = {
                        'member': member,
                        'add': set(),
                        'remove': {member.guild.default_role}
                    }

                add_key = 'add' if add_or_remove else 'remove'
                sub_key = 'remove' if add_or_remove else 'add'

                current_actions[add_key].add(role)
                current_actions[sub_key] -= {role}

                self.role_tracker[tracker_key] = current_actions
                await self.role_queue.put(tracker_key)
                self.logger.info(f'Queued up role "{add_key}" action for Member {member} on Guild {member.guild.id}.')
            else:
                self.logger.info(f"Skipping role action queue put. r:{role}|mem:{member}|a:{add_or_remove}")

    # Monitor events here
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        """
        Gets called on every raw reaction add event.
        Calls queue_add_remove_role to validate whether we own the reaction
        :param payload: RawReactionActionEvent from discord.py
        :return: None
        """
        await self.queue_add_remove_role(payload=payload, add_or_remove=True)

    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        """
        Gets called on every raw reaction remove event.
        Calls queue_add_remove_role to validate whether we own the reaction.
        :param payload: RawReactionActionEvent from discord.py
        :return: None
        """
        await self.queue_add_remove_role(payload=payload, add_or_remove=False)

    async def on_raw_message_delete(self, payload: RawMessageDeleteEvent):
        """
        Gets called on every message delete.
        This allows us to "clean up" any currently activated reaction role maps.
        :param payload: RawMessageDeleteEvent from discord.py
        :return: None
        """
        await self.__remove_activated_reactions(channel_id=payload.channel_id,
                                                message_id=payload.message_id)

    async def on_raw_bulk_message_delete(self, payload: RawBulkMessageDeleteEvent):
        """
        Gets called when a bulk delete event happens.
        Calls "on_raw_message_delete" for every single event in the bulk event.
        :param payload:
        :return:
        """
        single_msg_payload = {
            "channel_id": payload.channel_id, "guild_id": payload.guild_id
        }
        for message_id in payload.message_ids:
            single_msg_payload["id"] = message_id
            await self.on_raw_message_delete(RawMessageDeleteEvent(single_msg_payload))

    @staticmethod
    async def __check_channel_permissions(channel: discord.TextChannel) -> Tuple[bool, str]:
        """
        Utility method to determine if the bot has the necessary permissions to use the functions of the Cog
        on the specified channel.

        Checks if the specified channel is in a guild (vs in a DM)
        Checks if the bot can manage the channel guild's roles.
        Checks if the bot can add reactions to messages in the channel.
        :param channel: Channel on which to check permissions
        :return: Tuple[bool, str]. bool is whether the bot has all the necessary permissions, str is the
                 response error message explaining the failing permission.
        """

        guild = channel.guild
        bot_member = guild.me

        if channel.guild is None:
            response = (False, ErrorStrings.channel_not_part_of_server)
        elif bot_member.guild_permissions.manage_roles is False:
            response = (False, ErrorStrings.perm_not_manage_roles)
        elif channel.permissions_for(bot_member).add_reactions is False:
            response = (False, ErrorStrings.perm_not_add_react)
        else:
            response = (True, MiscStrings.perm_passed)

        return response

    @staticmethod
    async def __get_channel_message(channel: discord.TextChannel, message_id: int) -> Optional[discord.Message]:
        """
        Utility method to safely get a specific discord.py Message object from a channel.
        :param channel: Channel from which to get a message
        :param message_id: Integer ID of the message to retrieve
        :return: The Message object, or None if it can't be retrieved.
        """
        try:
            message = await channel.get_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            message = None
        return message

    @staticmethod
    def __get_role_by_id(guild: discord.guild, role_id: int) -> discord.Role:
        """
        Utility method to get a discord.py Role object from a guild by the role's ID./
        :param guild: discord.py Guild object which contains the role
        :param role_id: Integer ID of the role to retrieve
        :return: discord.py Role object for the role
        """
        return discord.utils.get(guild.roles, id=role_id)

    @staticmethod
    async def __bot_can_manage_roles(ctx: Context):
        """
        Utility method to check if the bot can manage roles for the given Context.
        :param ctx: discord.py Context object to check.
        :return: bool for whether the bot can manage roles.
        """
        return ctx.guild.me.guild_permissions.manage_roles

    async def __get_queue(self, ctx: Context, queue_name: str) -> dict:
        """
        Attempts to retrieve a queue object from the Config.
        :param ctx: discord.py Context object (used to determine the guild)
        :param queue_name: String name of the queue to retrieve.
        :return: The object for the queue, or an empty dict if it doesn't exist.
        """
        queues = await self.config.guild(ctx.guild).queues()
        return queues.get(queue_name, {})

    async def __get_emojis_for_queue(self, ctx: Context, queue_name: str) -> Dict[str, int]:
        """
        Attempts to retrieve an emoji/role map for a given queue name.
        :param ctx: discord.py Context object (used to determine the guild)
        :param queue_name: String name of the queue for which to retrieve the emoji/role map.
        :return: The dict emoji/role map for the specified queue, or an empty dict of it doesn't exist.
        """
        queue = await self.__get_queue(ctx, queue_name)
        return queue.get("emojis", {})

    async def __create_queue(self, ctx: Context, queue_name: str):
        """
        Creates a new queue with the specified name. Does NOT check if the queue already exists.
        Methods calling this function should perform their own validation.
        :param ctx: discord.py Context object
        :param queue_name: String name of the queue to create.
        :return:
        """
        queue_metadata = {
            'created_at': datetime.datetime.utcnow().strftime(DateTimeStrings.iso),
            'created_by_id': ctx.author.id,
            'created_by_username': "{}#{}".format(ctx.author.name, ctx.author.discriminator),
        }

        await Utils.update_config_keys(
            field_func=lambda: self.config.guild(ctx.guild).queues,
            new_data={queue_name: queue_metadata}
        )
        self.logger.info(f'Created queue named "{queue_name}" in guild {ctx.guild.id}.')

    async def __delete_queue(self, ctx: Context, queue_name) -> Union[dict, None]:
        """
        Deletes a queue with the specified name. Does not perform any validation about whether the queue exists.
        :param ctx: discord.py Context object
        :param queue_name: String name of the queue to delete.
        :return: Returns the dict object representation of the queue if it was found, or None if it didn't exist.
        """
        removed_value = await Utils.delete_config_key(
            field_func=lambda: self.config.guild(ctx.guild).queues,
            key=queue_name
        )
        self.logger.info(f'Deleted queue "{queue_name}" for guild {ctx.guild.id}.')
        return removed_value

    def __get_emoji_id(self, emoji: str):
        """
        From a Discord API emoji string (eg. <:x:12345678901123>), extract the actual ID.
        Possible inputs are the actual unicode representation of the emoji or the encoded string.
        If it is the unicode representation, it will simply be returned, otherwise it will return a string
        of the ID.
        :param emoji: string representation of the emoji
        :return: string of the actual unicode emoji, or string of the ID if it is custom
        """
        regex_match = self.EMOJI_REGEX.fullmatch(emoji)
        return emoji if not regex_match else regex_match.group(1)

    def __get_emoji_name(self, emoji: str):
        """
        From a Discord API emoji string (eg. <:x:12345678901123>), extract the name of the emoji. eg ":x:"
        Possible inputs are the actual unicode representation of the emoji or the encoded string.
        If it is the unicode representation, it will return None. Otherwise it will return a string of the name.
        :param emoji: string representation of the emoji
        :return: None if it is a unicode emoji, or string of the name if it is custom
        """
        regex_match = self.EMOJI_REGEX.fullmatch(emoji)
        return None if not regex_match else regex_match.group(0)

    def __get_api_emojis_from_emoji_map(self, emoji_map: Dict[str, int]) -> Set[str]:
        """
        Converts our emoji/role map into a format that is clean for use in the Discord API add/remove API call.
        :param emoji_map: emoji/role map
        :return: Clean string for use in the Discord API
        """
        api_emojis = set()
        for emoji in emoji_map.keys():
            emoji_id = self.__get_emoji_id(emoji)
            emoji_name = self.__get_emoji_name(emoji)

            api_emoji = emoji_id if not emoji_name else "{}:{}".format(emoji_name, emoji_id)
            api_emojis.add(api_emoji)

        return api_emojis

    def __find_bot_emoji(self, emoji_id: Union[int, str]) -> Optional[discord.Emoji]:
        """
        Given an emoji ID (retrieved from __get_emoji_id), attempts to get the actual Emoji object.
        This confirms that the bot has the ability to use the specified object. The user specifying
        the emoji might be in different servers and have access to other emojis that the bot does not.
        :param emoji_id: int or string of the emoji's ID
        :return: discord.py Emoji object if the bot has access, otherwise None
        """
        emoji = None
        for guild in self.bot.guilds:
            emoji = discord.utils.get(guild.emojis, id=int(emoji_id))
            if emoji:
                break
        return emoji

    async def __map_emoji(self, ctx: Context, queue_name: str, emoji: Union[discord.Emoji, str], role: discord.Role):
        """
        Updates a queue to map an emoji/reaction to a role. Does not perform any validation.
        Callers of this function should validate before calling.
        :param ctx: Context of the map command.
        :param queue_name: Queue name to update.
        :param emoji: Emoji to be mapped.
        :param role: Role to be mapped to the emoji.
        :return: None
        """
        emoji_dict = await self.__get_emojis_for_queue(ctx, queue_name)
        emoji_dict[Utils.clean_animated_emoji(str(emoji))] = role.id
        new_data = {
            queue_name: {
                "emojis": emoji_dict
            }
        }
        await Utils.update_config_keys(
            field_func=lambda: self.config.guild(ctx.guild).queues,
            new_data=new_data,
            update=True
        )
        self.logger.info(f'g:{ctx.guild.id}|q:{queue_name} | Added emoji "{emoji}" to the queue.')

    async def __unmap_emoji(self, ctx: Context, queue_name: str, emoji: Union[discord.Emoji, str]):
        """
        Updates a queue to unmap a specified emoji/reaction. This function does not perform any validation.
        Callers of this function should validate before calling.
        :param ctx: Context of the map command.
        :param queue_name: Queue name to update.
        :param emoji: Emoji to be mapped.
        :return: Returns the deleted emoji otherwise None.
        """
        queue = await self.__get_queue(ctx, queue_name)
        deleted_emoji = queue.get("emojis", {}).pop(str(emoji), None)

        new_data = {
            queue_name: queue
        }

        await Utils.update_config_keys(
            field_func=lambda: self.config.guild(ctx.guild).queues,
            new_data=new_data,
        )
        self.logger.info(f'g:{ctx.guild.id}|q:{queue_name} | Removed emoji "{emoji}" from the queue.')
        return deleted_emoji

    async def __add_activated_reactions(self, message_id: int, channel: discord.TextChannel,
                                        emoji_map: Dict[str, int]):
        """
        Adds an activated emoji/roll map record to the Config. Does not perform any validation.
        :param message_id: Integer ID of the message to activate.
        :param channel: discord.py Channel object which contains the message.
        :param emoji_map: emoji/role map dict.
        :return: None
        """
        key = str(message_id)
        activated_data = {
           key: emoji_map
        }

        # update the cache
        self.activated_cache[str(channel.id)][key] = emoji_map

        self.logger.info(f'c:{channel.id}|m:{message_id} Activated emoji map: {emoji_map}.')
        return await Utils.update_config_keys(
            field_func=lambda: self.config.channel(channel).activated,
            new_data=activated_data
        )

    async def __remove_activated_reactions(self, channel_id: int, message_id: int) -> Optional[Dict[str, int]]:
        """
        Removes an activated emoji/role map record from the Config. Does not perform any validation.
        If it existed and was deleted, the associated emoji/role mappings dict will be returned.
        :param channel_id: Integer ID of the Channel which contains the message.
        :param message_id: Integer ID of the Message which contains the activated map.
        :return: emoji/role mapping dict if it existed, otherwise None
        """
        channel = self.bot.get_channel(channel_id)  # type: discord.TextChannel
        channel_key = str(channel_id)
        message_key = str(message_id)

        channel_messages = self.activated_cache.get(channel_key, {})

        emojis = None

        if message_key in channel_messages:
            self.logger.info(f"Message {message_id} deleted, removing it from the activated reaction roles cache.")

            # pop the message off the of the channel cache
            emojis = self.activated_cache.get(channel_key).pop(message_key)

            # check if this is the last message in the channel
            if len(self.activated_cache.get(channel_key)) == 0:
                self.logger.info(f"No remaining reaction messages are in channel {channel_id}. Clear channel config.")
                # pop the channel off of the cache and delete the channel config
                self.activated_cache.pop(channel_key)
                await self.config.channel(channel).clear()
            else:
                db_activated = await self.config.channel(channel).activated()
                # just remove message from the activated
                db_activated.pop(message_key)
                await self.config.channel(channel).activated.set(db_activated)
        return emojis

    # Primary Commands
    @commands.group(name="reactroles", aliases=["rr"], invoke_without_command=True)
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def _reactroles(self, ctx: Context):
        """
        Simple Reaction Roles - Allows members on a Discord server to assign roles to themselves via reactions.

        This command can be used to "queue up" a mapping of emojis/reactions to their role before the message which will contain them exists.
        """
        await ctx.send_help()

    @_reactroles.command(name="create")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def __reactroles_create(self, ctx: Context, queue_name: str):
        """
        Creates a new "queue" for this server on which to create a series of reaction/role mappings.

        This queue can later be activated on a message of your choosing after it exists. This gives you time to properly map the role before crafting the message which will contain it.
        """

        if not await self.__bot_can_manage_roles(ctx):
            self.logger.info(f"CREATE: Bot cannot manage roles in guild {ctx.guild.id}. Not proceeding.")
            return await ErrorReply(ErrorStrings.perm_not_manage_roles).send(ctx)

        if await self.__get_queue(ctx, queue_name):
            self.logger.info(f"CREATE: Queue named {queue_name} exists in guild {ctx.guild.id}. Not proceeding.")
            return await ErrorReply(ErrorStrings.queue_exists_f.format(queue_name)).send(ctx)

        await self.__create_queue(ctx=ctx, queue_name=queue_name)
        await ctx.tick()

    @_reactroles.command(name="delete")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def __reactroles_delete(self, ctx: Context, queue_name: str):
        """
        Deletes a previously created queue for the server.
        """

        if not await self.__bot_can_manage_roles(ctx):
            self.logger.info(f"DELETE: Bot cannot manage roles in guild {ctx.guild.id}. Not proceeding.")
            return await ErrorReply(ErrorStrings.perm_not_manage_roles).send(ctx)

        if not await self.__get_queue(ctx=ctx, queue_name=queue_name):
            self.logger.info(f"DELETE: Queue named {queue_name} doesn't exist in guild {ctx.guild.id}. Not proceeding.")
            return await ErrorReply(ErrorStrings.queue_not_exists_f.format(queue_name)).send(ctx)

        await self.__delete_queue(ctx=ctx, queue_name=queue_name)
        await ctx.tick()

    @_reactroles.command(name="map")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def __reactroles_map(self, ctx: Context, queue_name: str, emoji: str, *, role: discord.Role):
        """
        Maps a reaction/emoji to a the role which should be assigned for the specified queue.
        """
        # confirm the queue exists
        if not await self.__get_queue(ctx=ctx, queue_name=queue_name):
            self.logger.info(f'MAP: Queue "{queue_name}" doesd not exist for guild {ctx.guild.id}.')
            return await ErrorReply(ErrorStrings.queue_not_exists_f.format(queue_name)).send(ctx)

        emoji_id = self.__get_emoji_id(emoji)
        actual_emoji = emoji if not emoji_id.isdigit() else self.__find_bot_emoji(emoji_id)

        # if None, the bot doesn't have access to it in any of its guilds
        if actual_emoji is None:
            self.logger.info(f'MAP: g:{ctx.guild.id}|q:{queue_name} | '
                             f'Bot does not have access to requested emoji "{actual_emoji}. Not proceeding."')
            return await ErrorReply(ErrorStrings.emoji_bot_no_access_f.format(emoji)).send(ctx)

        # check if the emoji already exists in the queue
        current_emojis = await self.__get_emojis_for_queue(ctx, queue_name)
        if emoji in current_emojis:
            self.logger.info(f'MAP: g:{ctx.guild.id}|q:{queue_name} | '
                             f'Requested emoji "{actual_emoji}" already exists in the queue. Not proceeding.')
            role_id = current_emojis.get(emoji)
            role = discord.utils.get(ctx.guild.roles, id=int(role_id))  # type: discord.Role
            return await ErrorReply(ErrorStrings.emoji_exists_f.format(emoji, queue_name, role.name)).send(ctx)

        await self.__map_emoji(ctx=ctx, queue_name=queue_name, emoji=actual_emoji, role=role)
        await SuccessReply(SuccessStrings.emoji_added_f.format(role.name, emoji, queue_name)).send(ctx)

    @_reactroles.command(name="unmap")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def __reactroles_unmap(self, ctx: Context, queue_name: str, emoji: str):
        """
        Unmaps/deletes the mapping for the specified reaction/emoji in the specified queue.
        """
        # confirm the queue exists
        if not await self.__get_queue(ctx=ctx, queue_name=queue_name):
            self.logger.info(f'UNMAP: Queue "{queue_name}" does not exist for guild {ctx.guild.id}.')
            return await ErrorReply(ErrorStrings.queue_not_exists_f.format(queue_name)).send(ctx)

        unset_success = await self.__unmap_emoji(ctx=ctx, queue_name=queue_name, emoji=emoji)
        if not unset_success:
            self.logger.info(f'UNMAP: g:{ctx.guild.id}|q:{queue_name} | '
                             f'Requested emoji "{emoji}" already does not exist in the queue. Not proceeding.')
            return await ErrorReply(ErrorStrings.emoji_not_exists_f.format(emoji, queue_name)).send(ctx)

        await SuccessReply(SuccessStrings.emoji_deleted_f.format(emoji, queue_name, unset_success)).send(ctx)

    @_reactroles.command(name="activate")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def __reactroles_activate(self, ctx: Context, queue_name: str, message_id: int, channel: discord.TextChannel):
        """
        Activates a queue and its mappings on the specified message/channel.

        This also deletes the queue if it was successfully activated on a message.
        """
        # confirm the queue exists
        if not await self.__get_queue(ctx=ctx, queue_name=queue_name):
            self.logger.info(f'ACTIVATE: Queue "{queue_name}" does not exist for guild {ctx.guild.id}.')
            return await ErrorReply(ErrorStrings.queue_not_exists_f.format(queue_name)).send(ctx)

        # confirm we have permissions in the channel specified
        perm_success, response = await self.__check_channel_permissions(channel=channel)

        if not perm_success:
            self.logger.info(f'ACTIVATE: Bot does not have proper permissions in channel {channel.id} | {response}.')
            return await ErrorReply(response).send(ctx)

        message = await self.__get_channel_message(channel=channel, message_id=message_id)

        if not message:
            error_message = ErrorStrings.message_not_found_f.format(message_id, channel.name)
            self.logger.info(f'ACTIVATE: {error_message}')
            return await ErrorReply(error_message).send(ctx)

        # the message is valid, so start adding reactions to it
        emojis = await self.__get_emojis_for_queue(ctx=ctx, queue_name=queue_name)

        if not emojis:
            self.logger.info("The queue has no mapped emojis. Not activating.")
            return await ErrorReply(ErrorStrings.activate_no_mapped_f.format(queue_name)).send(ctx)

        try:
            # add the reactions
            api_emojis = self.__get_api_emojis_from_emoji_map(emojis)

            for api_emoji in api_emojis:
                await message.add_reaction(emoji=api_emoji)

            self.logger.info(f'g:{ctx.guild.id}|q:{queue_name} | '
                             f'Added emojis {emojis.keys()} to message {message_id}.')
            # move the emoji map to the activated config and delete the queue
            await self.__add_activated_reactions(message_id=message_id, channel=channel, emoji_map=emojis)
            await self.__delete_queue(ctx=ctx, queue_name=queue_name)

            await SuccessReply(SuccessStrings.activated_queue_f.format(queue_name, message_id, channel)).send(ctx)

        except (discord.HTTPException, discord.Forbidden, discord.NotFound, discord.InvalidArgument) as de:
            self.logger.error(f"Error calling Discord add_reaction API.. "
                              f"Message:{message.id} | Channel: {channel.id} | Exception: {de}")
            await ErrorReply(ErrorStrings.discord_add_reaction_error).send(ctx)
        except Exception as ue:
            self.logger.error(f"Unknown Error: {ue}")
            await ErrorReply(ErrorStrings.unknown_error_check_logs).send(ctx)

    @_reactroles.command(name="deactivate")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def __reactroles_deactivate(self, ctx: Context, message_id: int, channel: discord.TextChannel):
        """
        Deactivates a previously activated reaction/role assignment on the specified message/channel.

        Additionally, this will remove the bot's reactions on that message.
        """
        message = await self.__get_channel_message(channel=channel, message_id=message_id)

        if not message:
            error_message = ErrorStrings.message_not_found_f.format(message_id, channel.name)
            self.logger.info(f'{error_message}')
            return await ErrorReply(error_message).send(ctx)

        emojis = await self.__remove_activated_reactions(channel.id, message_id)
        self.logger.info(f"m:{message.id}|c:{channel.id} | Removed activated reaction roles.")

        if emojis:
            try:
                api_emojis = self.__get_api_emojis_from_emoji_map(emojis)

                for api_emoji in api_emojis:
                    await message.remove_reaction(api_emoji, ctx.guild.me)

                self.logger.info(f"m:{message.id}|c:{channel.id} | "
                                 f"Removed bot reactions from message: {api_emojis}")
                await SuccessReply(SuccessStrings.deactivated_queue_f.format(message_id, channel.name)).send(ctx)
            except (discord.HTTPException, discord.Forbidden, discord.NotFound, discord.InvalidArgument) as de:
                self.logger.error(f"Error calling Discord remove_reaction API.. "
                                  f"Message:{message.id} | Channel: {channel.id} | Exception: {de}")
                await ErrorReply(ErrorStrings.discord_remove_reaction_error).send(ctx)
            except Exception as ue:
                self.logger.error(f"Unknown Error: {ue}")
                await ErrorReply(ErrorStrings.unknown_error_check_logs).send(ctx)
        else:
            self.logger.error(f"m:{message.id}|c:{channel.id} | Did not find any emojis in the queue for this message.")
            await ErrorReply(ErrorStrings.emoji_not_found_in_queue).send(ctx)
