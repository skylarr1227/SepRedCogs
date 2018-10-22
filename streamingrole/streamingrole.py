import asyncio
from typing import Optional

import discord
from redbot.core import Config, commands, checks
from redbot.core.bot import Red
from redbot.core.commands import Context

from cog_shared.seplib.classes.basesepcog import BaseSepCog


class StreamingRole(BaseSepCog, commands.Cog):
    ADD_REMOVE_INTERVAL = 0.2

    def __init__(self, bot: Red):

        super(StreamingRole, self).__init__(bot=bot)

        self.guild_role_cache = {}

        self.streaming_tracker = {}
        self.role_queue = asyncio.Queue()

        self._add_future(self.edit_streaming_role_loop())
        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_guild(streaming_role=None)

    async def _init_cache(self):
        await self.bot.wait_until_ready()

        guilds = await self.config.all_guilds()

        active_guilds = dict()

        for guild_id, guild_dict in guilds.items():
            stream_role_id = guild_dict.get("streaming_role")
            if stream_role_id is not None:
                active_guilds[guild_id] = stream_role_id

        self.guild_role_cache = active_guilds

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

    async def __get_streaming_role(self, guild: discord.Guild) -> Optional[discord.Role]:

        # check the cache first
        role_id = self.guild_role_cache.get(guild.id)
        if role_id is None:
            role_id = await self.config.guild(guild).streaming_role()
        if role_id is not None:
            return self.__get_role_by_id(guild=guild, role_id=role_id)

    async def __set_streaming_role(self, guild: discord.Guild, role: discord.Role):
        # update the cache
        self.guild_role_cache[guild.id] = role.id
        await self.config.guild(guild).streaming_role.set(role.id)

    async def __unset_streaming_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        current_role = await self.__get_streaming_role(guild=guild)
        if current_role is not None:
            # pop it off the cache
            self.guild_role_cache.pop(guild.id)
            await self.config.guild(guild).clear()
        return current_role

    async def edit_streaming_role_loop(self):
        await self.bot.wait_until_ready()

        while self == self.bot.get_cog(self.__class__.__name__):
            tracker_key = await self.role_queue.get()

            # get get an item out of the tracker
            tracker_item = self.streaming_tracker.pop(tracker_key, None)

            if tracker_item and tracker_item.get('member'):
                member = tracker_item.get('member')

                current_roles = set(member.roles)
                add_roles = tracker_item.get(True)
                remove_roles = tracker_item.get(False, {member.guild.default_role})

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
                    self.streaming_tracker[tracker_key] = tracker_item
                    await self.role_queue.put(tracker_key)
                except Exception as ue:
                    self.logger.error(f"An unknown error occurred while attempting to add roles. Not re-queueing."
                                      f"Member: {member} | Exception: {ue}.")
                    self.role_queue.task_done()
                else:
                    self.role_queue.task_done()
                finally:
                    await asyncio.sleep(self.ADD_REMOVE_INTERVAL)

    async def on_member_update(self, before_member: discord.Member, after_member: discord.Member):

        streaming_activity = discord.Streaming

        # if both before and after is Streaming, do nothing
        if isinstance(before_member.activity, streaming_activity) and isinstance(after_member.activity, streaming_activity):
            return

        # set the member we're going to acton based on which one has streaming
        if isinstance(before_member.activity, streaming_activity):
            member = before_member
            add_role = False  # They're no longer streaming, remove the role
        elif isinstance(after_member.activity, streaming_activity):
            member = after_member
            add_role = True  # They're now streaming, add the role
        else:
            return  # neither activity is Streaming. We don't care about it.

        # get the streaming role for this server, if it exists
        streaming_role = await self.__get_streaming_role(member.guild)

        if streaming_role is not None:
            tracker_key = "{}|{}".format(member.guild.id, member.id)
            current_action = self.streaming_tracker.get(tracker_key)
            if not current_action:
                current_action = {
                    'member': member,
                    True: set(),
                    False: {member.guild.default_role}
                }

            current_action[add_role].add(streaming_role)
            current_action[not add_role] -= {streaming_role}

            self.streaming_tracker[tracker_key] = current_action
            await self.role_queue.put(tracker_key)
            self.logger.info(f'Queued up role "{add_role}" action for Member {member} on Guild {member.guild.id}.')

    @commands.group(name="streamingrole", invoke_without_command=True)
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def _streamingrole(self, ctx: Context):
        await ctx.send_help()

    @_streamingrole.command(name="set")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def _set(self, ctx: Context, role: discord.Role):
        if not await self.__bot_can_manage_roles(ctx):
            self.logger.info(f"Bot cannot manage roles in guild {ctx.guild.id}. Not proceeding.")
            return await ctx.send("❌ This bot does not have permission to manage roles on the server.")

        existing_role = await self.__get_streaming_role(ctx.guild)

        if existing_role is not None:
            self.logger.info(f"Streaming role is already set up for guild {ctx.guild.id}. Not proceeding.")
            return await ctx.send(f"❌ This server already has a streamer role configured. "
                                  f"Please unset before setting a new role. Current Role: `{existing_role.name}`")

        await self.__set_streaming_role(guild=ctx.guild, role=role)
        self.logger.info(f"Set streaming role on guild: {ctx.guild.id} | Role: {role}")
        await ctx.send(f"SUCCESS: Assigned Streamer Role: `{role.name}`")

    @_streamingrole.command(name="unset")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def _unset(self, ctx: Context):
        if not await self.__bot_can_manage_roles(ctx):
            self.logger.info(f"Bot cannot manage roles in guild {ctx.guild.id}. Not proceeding.")
            return await ctx.send("❌ This bot does not have permission to manage roles on the server.")

        existing_role = await self.__get_streaming_role(ctx.guild)

        if existing_role is None:
            self.logger.info(f"Streaming role is not configured for guild {ctx.guild.id}. Not proceeding.")
            return await ctx.send(f"❌ There is no streaming role configured for this server.")

        await self.__unset_streaming_role(guild=ctx.guild)
        self.logger.info(f"Streaming role unset for guild {ctx.guild.id}. It was previously {existing_role}.")
        await ctx.send(f"SUCCESS: Unset streaming role. It was set to role `{existing_role.name}`")
