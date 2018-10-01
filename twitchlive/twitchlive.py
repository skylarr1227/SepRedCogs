import asyncio
from collections import defaultdict
from copy import deepcopy
from typing import Optional, Tuple, Dict, Any, List

import discord
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.responses.embeds import ErrorReply, SuccessReply
from twitchlive.models.common_models import StreamAnnouncement
from twitchlive.twitchapi.twichobjects import TwitchUser
from .twitchapi import TwitchApi

class TwitchLive(BaseSepCog):

    MONITOR_PROCESS_INTERVAL = 5
    TWITCH_API_THROTTLE = 0.2
    COG_CONFIG_SALT = "twitch.tv/seputaes"

    def __init__(self, bot: Red):

        super(TwitchLive, self).__init__(bot=bot)

        self.twitch_api = None  # type: Optional[TwitchApi]

        self.twitch_config_cache = {}
        self.announce_cache = {}
        self.already_announced_cache = set()

        self._add_future(self.__monitor_streams())
        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_global(twitch_config={})
        config.register_guild(announcements={})
        config.register_guild(already_announced=[])

    async def _init_cache(self):
        await self.bot.wait_until_ready()

        # Cache the guild announcements on load
        guilds = await self.config.all_guilds()

        streamer_checks = defaultdict(dict)

        for guild_id, guild_dict in guilds.items():
            announcements = guild_dict.get('announcements', {})
            already_announced = guild_dict.get('already_announced', [])


            for user_id, metadata in announcements.items():
                streamer_checks[str(guild_id)][str(user_id)] = metadata

            self.already_announced_cache | set(already_announced)

        self.announce_cache = streamer_checks

        # cache twitch configuration
        self.twitch_config_cache = await self.config.twitch_config()

        # init the api
        self.__init_twitch_api()

    def __init_twitch_api(self):
        client_id = self.twitch_config_cache.get('client_id')
        client_secret = self.twitch_config_cache.get('client_secret')

        if client_id and client_secret:
            self.twitch_api = TwitchApi(client_id=client_id, client_secret=client_secret)

    async def __add_already_announced(self, guild: discord.Guild, stream_id: str):
        self.already_announced_cache.add(stream_id)

        # get the DB value
        current = await self.config.guild(guild).already_announced()
        if current is None:
            current = []
        current = list(current)
        current.append(stream_id)
        await self.config.guild(guild).already_announced.set(current)

    async def __get_guild_announcements(self, guild: discord.Guild):
        return await self.config.guild(guild).announcements()

    async def __get_current_announcement(self, guild: discord.Guild, user_id: str):
        cur_announcements = await self.__get_guild_announcements(guild)
        return cur_announcements.get(user_id)

    async def __add_current_announcement(self, guild: discord.Guild, role: discord.Role,
                                         channel: discord.TextChannel, user: TwitchUser):

        cur_announcements = await self.__get_guild_announcements(guild)

        metadata = {
            'twitch_name': user.display_name,
            'channel_id': channel.id,
            'role_id': role.id,
            'user_login': user.login,
            'user_thumbnail': user.profile_image_url
        }

        cur_announcements[user.id] = metadata
        # update the cache
        if not self.announce_cache.get(guild.id):
            self.announce_cache[guild.id] = {}

        if isinstance(self.announce_cache.get(guild.id), dict):
            self.announce_cache[guild.id][user.id] = metadata
        await self.config.guild(guild).announcements.set(cur_announcements)

    async def __remove_current_announcement(self, guild: discord.Guild, user_id: str):
        cur_announcements = await self.__get_guild_announcements(guild)

        removed = cur_announcements.pop(user_id)

        # update the cache
        if isinstance(self.announce_cache.get(guild.id), dict):
            self.announce_cache[guild.id].pop(user_id, None)

        if removed:
            await self.config.guild(guild).announcements.set(cur_announcements)

    def __twitch_is_init(self):
        return self.twitch_api is not None

    async def __monitor_streams(self):
        await self.bot.wait_until_ready()

        while self == self.bot.get_cog(self.__class__.__name__):

            work_list = dict()
            batch_size = 100
            to_announce = []

            # we'll batch the calls into groups of 100 (since the API allows us to ask for a max of 100 streams)
            # combine everything into one giant list of dicts
            for guild_id, guild_dict in self.announce_cache.items():
                for user_id, metadata in guild_dict.items():
                    if user_id not in work_list:
                        work_list[user_id] = {
                            'metadata': []
                        }
                    work_list[user_id]['metadata'].append(
                        {
                            'guild_id': guild_id,
                            'role_id': metadata.get('role_id'),
                            'channel_id': metadata.get('channel_id'),
                            'twitch_name': metadata.get('twitch_name'),
                            'user_login': metadata.get('user_login'),
                            'user_thumbnail': metadata.get('user_thumbnail')
                        }
                    )

            for i in range(0, len(work_list), batch_size):
                batch_user_ids = list(work_list.keys())[i:i+batch_size]

                # get streams for these user_ids
                streams = await self.twitch_api.get_streams_for_multiple(batch_user_ids)

                for stream in streams:
                    should_announce = stream.is_live and \
                                      work_list.get(stream.user_id) and \
                                      stream.id not in self.already_announced_cache

                    if should_announce:
                        announce_data = work_list[stream.user_id]['metadata']  # type: List[Dict[str, Any]]

                        for info_dict in announce_data:
                            info_dict['stream_title'] = stream.title
                            info_dict['stream_url'] = "https://twitch.tv/{}".format(info_dict.get('user_login'))
                            info_dict['stream_id'] = stream.id
                            info_dict['stream_thumbnail'] = stream.thumbnail_url

                        to_announce += announce_data
                await asyncio.sleep(self.TWITCH_API_THROTTLE)

            # process the announcement list
            for data in to_announce:

                announcement = StreamAnnouncement(bot=self.bot, **data)

                if not announcement.is_valid:
                    self.logger.error("Announcement is not valid. g:{}|c:{}|s:{}".format(
                        announcement.guild.id, announcement.channel.id, announcement.twitch_name
                    ))
                    print("Stream announcement is not valid. Moving on...")
                    continue

                await self.__add_already_announced(guild=announcement.guild, stream_id=announcement.stream_id)
                self.logger.info("Announcing streamer {}. Guild: {} | Channel: {}".format(
                    announcement.twitch_name, announcement.guild.id, announcement.channel.id
                ))
                await announcement.channel.send(content=announcement.message_content, embed=announcement.embed)

            await asyncio.sleep(self.MONITOR_PROCESS_INTERVAL)

    @staticmethod
    async def __check_announce_permissions(channel: discord.TextChannel, role: discord.Role) -> Tuple[bool, str]:

        guild = channel.guild
        bot_member = guild.me

        if channel.guild is None:
            response = (False, "❌ The specified channel is not part of a server.")
        elif channel.permissions_for(bot_member).send_messages is False:
            response = (False, "❌ The bot does not have permissions to send messages to that channel!")
        elif not role.mentionable:
            response = (False, "❌ That role is not able to be mentioned in chat.")
        else:
            response = (True, "Passed")
        return response

    @staticmethod
    def __get_role_by_id(guild: discord.guild, role_id: int) -> discord.Role:
        """
        Utility method to get a discord.py Role object from a guild by the role's ID./
        :param guild: discord.py Guild object which contains the role
        :param role_id: Integer ID of the role to retrieve
        :return: discord.py Role object for the role
        """
        return discord.utils.get(guild.roles, id=role_id)

    @commands.group(name="twitchlive", aliases=['tl'], invoke_without_command=True)
    @checks.is_owner()
    async def _twitchlive(self, ctx: Context):
        await ctx.send_help()

    @_twitchlive.command(name="configure")
    @checks.is_owner()
    async def _configure(self, ctx: Context, client_id: str, client_secret: str):
        """
        Configures the TwitchLive cog to use the specified client ID and client secret for the Twitch API.

        :param client_id: Twitch application Client ID
        :param client_secret: Twitch application Client Secret
        """

        if ctx.guild is not None and not isinstance(ctx.channel, discord.DMChannel):
            # we're not in a guild. Delete the command message if we can.
            self.logger.warn("Attempted to put client/secret in a chat channel! Deleting! g:{}|c:{}"
                             .format(ctx.guild.id, ctx.channel.id))
            await ctx.channel.delete_messages([ctx.message])
            return await ErrorReply("For security purposes, this command must be run via whisper/DM to me.").send(ctx)

        new_config = {
            'client_id': client_id,
            'client_secret': client_secret
        }
        # update the cache
        current_cache = deepcopy(self.twitch_config_cache)
        current_db_config = deepcopy(await self.config.twitch_config())

        self.twitch_config_cache = new_config
        await self.config.twitch_config.set(new_config)

        # update the client with the new info
        self.__init_twitch_api()

        # do a sanity check to validate it worked
        success, exception = await self.twitch_api._sanity_check()
        if not success:
            self.twitch_config_cache = current_cache
            await self.config.twitch_config.set(current_db_config)
            self.logger.info(exception)
            return await ErrorReply("{}. No changes made.".format(exception)).send(ctx)

        self.logger.info("Twitch API configured for Cog. Client ID: {}".format(client_id))
        await ctx.tick()


    @_twitchlive.command(name="add")
    @commands.guild_only()
    @checks.is_owner()
    async def _add(self, ctx: Context, twitch_user: str, role: discord.Role, channel: discord.TextChannel):
        if not self.__twitch_is_init():
            self.logger.info("Attempted to execute 'add' command without Twitch API configured.")
            return await ErrorReply("Twitch API is not initialized. Please run the `configure` sub-command.").send(ctx)

        success, response_msg = await self.__check_announce_permissions(channel=channel, role=role)

        if not success:
            self.logger.info(f"Bot does not have the proper permissions to announce. c:{channel.id}|{role.id}. Error:"
                             f"{response_msg}")
            return await ErrorReply(response_msg).send(ctx)

        twitch_user = twitch_user.lower()

        users = await self.twitch_api.get_users_by_login(username=twitch_user)

        if not users:
            return await ErrorReply("That Twitch user was not found").send(ctx)

        user = users[0]

        user_ids = await self.twitch_api.get_user_ids_for_logins([user.login])
        user_id = user_ids.get(twitch_user)

        curr_for_user = await self.__get_current_announcement(ctx.guild, user_id)
        if curr_for_user:
            role_id = curr_for_user.get('role_id')
            channel_id = curr_for_user.get('channel_id')
            self.logger.info(f"Announcement already exists for streamer. "
                             f"s:{user.display_name}|c:{channel.id}|r:{role.id}")
            message = f"An annoucement for that Twitch User already exists on this server. " \
                      f"Role: `{role_id}` Channel: `{channel_id}`"
            return await ErrorReply(message).send(ctx)

        await self.__add_current_announcement(guild=ctx.guild, role=role, channel=channel, user=user)
        await ctx.tick()

    @_twitchlive.command(name="remove")
    @commands.guild_only()
    @checks.is_owner()
    async def _remove(self, ctx: Context, twitch_user: str):
        if not self.__twitch_is_init():
            self.logger.info("Attempted to execute 'remove' command without Twitch API configured.")
            return await ErrorReply("Twitch API is not initialized. Please run the `configure` sub-command.").send(ctx)

        twitch_user = twitch_user.lower()

        user_ids = await self.twitch_api.get_user_ids_for_logins([twitch_user])
        user_id = user_ids.get(twitch_user)

        if not user_id:
            return await ErrorReply("That Twitch user was not found").send(ctx)

        curr_for_user = await self.__get_current_announcement(ctx.guild, user_id)
        if not curr_for_user:
            return await ErrorReply("An announcement does not exist for that Twitch user.").send(ctx)

        role_id = curr_for_user.get('role_id')
        role = self.__get_role_by_id(ctx.guild, int(role_id))
        await self.__remove_current_announcement(guild=ctx.guild, user_id=user_id)
        await SuccessReply(f"Removed Announcement. It was assigned to Role: `{role.name}`").send(ctx)
