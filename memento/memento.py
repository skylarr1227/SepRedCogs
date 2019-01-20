import asyncio
import datetime
from collections import defaultdict
from typing import Optional, Tuple, List, Dict

import discord
import pytz
import recurrent
from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.responses.embeds import ErrorReply
from cog_shared.seplib.responses.interactive_actions import InteractiveActions
from memento.embeds.alarmreply import AlarmReply
from memento.embeds.mementoembed import MementoEmbedReply
from memento.types.reminder import Reminder
from memento.embeds.reminderlistreply import ReminderListReply
from memento.data.timezonestrings import TimezoneStrings
from pytz.tzinfo import DstTzInfo
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.commands import Context


class Memento(BaseSepCog, commands.Cog):

    CONFIRM_DT_FORMAT = "%b %d, %Y @ %I:%M:%S%p"
    DEFAULT_TIMEZONE = 'US/Pacific'
    USER_MESSAGE_INTERVAL = 0.1
    MONITOR_PROCESS_INTERVAL = 5
    MESSAGE_EMOJI = "\N{ALARM CLOCK}"
    TIMEZONES_URL = "https://sep.gg/timezones"

    def __init__(self, bot: Red):

        super(Memento, self).__init__(bot=bot)
        self.user_config_cache = {}
        self.user_reminder_cache = {}  # type: Dict[str, List[Reminder]]

        self._add_future(self.__monitor_reminders())
        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_user(config={})
        config.register_user(reminders=[])

    async def _init_cache(self):
        await self.bot.wait_until_ready()

        users = await self.config.all_users()

        user_config = {}
        user_reminders = {}

        for user_id, user_dict in users.items():
            config = user_dict.get('config')
            reminders = user_dict.get('reminders')
            if config is not None:
                user_config[str(user_id)] = config
            if reminders is not None:
                cache_reminders = []
                for reminder in reminders:
                    try:
                        cache_reminders.append(Reminder(**reminder))
                    except TypeError as e:
                        self.logger.error(f"Error converting database reminders to Reminder class. Error: {e}")
                        continue
                user_reminders[str(user_id)] = cache_reminders

        self.user_config_cache = user_config
        self.user_reminder_cache = user_reminders

    @staticmethod
    async def _get_recurrent_object(user_timezone: DstTzInfo) -> recurrent.RecurringEvent:

        """
        Given a pytz DstTzInfo object, return the Recurrent library Recurring event parser object
        with the start time localized to the user's timezone.
        :param user_timezone: pytz timezone into object for the user's timezone.
        :return: Recurrent library Recurring event parser.
        """
        now = datetime.datetime.utcnow()
        user_now = pytz.UTC.localize(now).astimezone(user_timezone).replace(tzinfo=None)
        return recurrent.RecurringEvent(now_date=user_now)

    async def __monitor_reminders(self):
        """
        Loop which runs as a future and iterates over all set reminders and checks if it's time to announce them.
        :return: None
        """
        await self.bot.wait_until_ready()

        while self == self.bot.get_cog(self.__class__.__name__):
            users_to_notify = defaultdict(list)  # type: Dict[discord.User, List[str]]

            for user_id, user_reminders in self.user_reminder_cache.items():
                for user_reminder in user_reminders:
                    dt_string = user_reminder.dt_str
                    if dt_string is None:
                        break

                    reminder_dt = datetime.datetime.strptime(dt_string, Reminder.ISO8601_FORMAT)
                    now = datetime.datetime.utcnow()

                    if reminder_dt < now:
                        user = self.bot.get_user(id=int(user_id))  # type: discord.User
                        await self._delete_reminder(user=user, reminder_id=user_reminder.id)
                        users_to_notify[user].append(user_reminder.text)
                        self.logger.info(f"User reminder queued up. User: {user.id} | id: {user_reminder.id}")

            for user, reminders in users_to_notify.items():
                for reminder in reminders:
                    await AlarmReply(message=reminder).send(user)
                    await asyncio.sleep(self.USER_MESSAGE_INTERVAL)

            await asyncio.sleep(self.MONITOR_PROCESS_INTERVAL)

    def _check_permissions(self, channel: discord.TextChannel, role: discord.Role) -> Tuple[bool, str]:
        """
        Utility method to determine if the bot has the necessary permissions to use the functions of the Cog
        on the specified channel and role.

        :param channel: Channel on which to check permissions.
        :return: Tuple[bool, str]. bool is whether the bot has all the necessary permissions, str is the response
                error message explaining the failing permission.
        """

        if channel.guild is None:
            response = (False, "The specified channel is not part of a server.")
        elif not isinstance(channel, discord.TextChannel):
            response = (False, "That channel is not a Text channel.")
        elif channel.guild != role.guild:
            response = (False, "The role and channel are not part of the same server.")
        elif channel.guild.me.guild_permissions.send_messages is False:
            response = (False, "The bot does not have permission to speak in that channel.")
        elif role.mentionable is False:
            response = (False, "That role is not able to be mentioned.")
        else:
            response = (True, "Bot passed all permissions checks.")

        return response

    async def _set_user_timezone(self, user: discord.User, timezone: str):
        """
        Sets the given pytz timezone string as the timezone for the given user.
        This will overwrite any existing user timezone preference.

        :param user: Discord.py user for which to set the timezone preference.
        :param timezone: pytz timezone string. Assumes that validation has already happened.
        :return: None
        """
        user_id = str(user.id)

        cache = self.user_config_cache.get(user_id, {})

        cache['timezone'] = timezone

        self.user_config_cache[user_id] = cache
        await self.config.user(user).config.set(cache)
        self.logger.info(f"Updated timezone config for User: {user.id} | Timezone: {timezone}")

    async def _update_user_reminders(self, user: discord.User, reminders: List[Reminder]):
        """
        Overwrites a user's reminders to the new list of reminders.

        :param user: discord.py user
        :param reminders: List of "Reminder" entities to save for the user. Will overwrite any existing reminders.
        :return: None
        """
        self.user_reminder_cache[str(user.id)] = reminders
        db_reminders = [r.prepare_for_storage() for r in reminders]
        await self.config.user(user).reminders.set(db_reminders)

    async def _set_user_reminder(self, user: discord.User, reminder_dt: datetime.datetime, reminder_text: str,
                                 timezone: str):
        """
        Adds a new reminder for the user. Assumes that the reminder datetime has already been converted to UTC.

        :param user: discord.py user
        :param reminder_dt: Timezone-agnostic UTC datetime for when the reminder should trigger.
        :param reminder_text: Text to send to the user in the reminder.
        :param timezone: pytz timestone string.
        :return: None
        """
        user_reminders = await self._get_user_reminders(user)
        user_reminders.append(
            Reminder(dt=reminder_dt.strftime(Reminder.ISO8601_FORMAT), text=reminder_text, timezone=timezone)
        )
        self.logger.info(f"Adding reminder. Time: {reminder_dt.strftime(Reminder.ISO8601_FORMAT)} "
                         f"| User: {user.id} | Total Reminders: {len(user_reminders)}")
        await self._update_user_reminders(user=user, reminders=user_reminders)

    async def _get_user_reminders(self, user: discord.User) -> List[Reminder]:
        """
        Retrieves a list of Reminders from the cache for the given user.
        :param user: discord.py user
        :return: List of Reminders for the user.
        """
        user_id = str(user.id)
        return self.user_reminder_cache.get(user_id, [])

    async def _delete_reminder(self, user: discord.User, reminder_id: str):
        """
        Deletes a reminder with the given reminder ID for the given user.
        :param user: discord.py user
        :param reminder_id: Unique ID of the reminder.
        :return: None
        """
        current_reminders = await self._get_user_reminders(user)
        new_reminders = []

        if reminder_id is None:
            self.logger.debug("User attempted to delete a reminder, but it was not found. "
                              f"Id: {reminder_id} | User: {user.id}")
            return

        for reminder in current_reminders:
            if reminder.id != reminder_id:
                new_reminders.append(reminder)
        self.logger.info(f"Deleting reminder for user: Id: {reminder_id} | User: {user.id}")
        await self._update_user_reminders(user=user, reminders=new_reminders)

    def _get_user_tz_string(self, user: discord.User) -> str:
        """
        Retrieves the string value of the user's timezone from the cache/database.
        If no preference is set, returns Memento's default.
        :param user: discord.py user
        :return: User's preferred timezone string (for pytz), or Memento's default if not set.
        """
        return self.user_config_cache.get(str(user.id), {}).get('timezone', self.DEFAULT_TIMEZONE)

    async def _get_user_timezone(self, user: discord.User) -> DstTzInfo:
        """
        Retrieves the user's preferred timezone. If the user does not have one set, returns Memento's default.
        :param user: discord.py user
        :return: pytz Timezone Info object
        """
        user_timezone = self._get_user_tz_string(user=user)
        return pytz.timezone(user_timezone)

    async def _parse_reminder_time(self, user: discord.User, reminder_time: str) -> Optional[datetime.datetime]:
        """
        Converts a user's reminder string into a timezone-agnostic UTC datetime, offset from the user's timezone.
        If the string was not understood, returns None.

        :param user: discord.py user.
        :param reminder_time: User supplied reminder string (from command parameters).
        :return: Timezone-agnostic UTC datetime, offset from the user's timezone. None if parsing failed.
        """
        user_timezone = await self._get_user_timezone(user)
        user_recurrent = await self._get_recurrent_object(user_timezone)
        user_parsed_time = user_recurrent.parse(reminder_time)

        if user_parsed_time is not None:
            dt = user_timezone.localize(user_parsed_time)
            utc_dt = dt.astimezone(tz=pytz.UTC)
            return utc_dt
        self.logger.debug(f"Unable to parse user supplied reminder time: {reminder_time}")
        return None

    def _parse_reminder_string(self, reminder_string: str) -> Optional[Tuple[str, str]]:
        """
        Parses a Memento command string into the reminder time and reminder message.
        If the command is not in the correct format, will return None.

        :param reminder_string: Raw command from the user.
        :return:
        """
        try:
            reminder_time, reminder_message = reminder_string.split("|", maxsplit=1)
        except (ValueError, TypeError) as e:
            self.logger.error("Error parsing reminder string: {reminder_string} | Error: {e}")
            return None
        return reminder_time, reminder_message

    @commands.group(name="memento", aliases=['remindme'], invoke_without_command=True)
    async def _memento(self, ctx: Context, *, command_str: str):
        """
        Sets a reminder at a specified time and a message which the bot will DM you, in the format of: time | message

        You can use common natural language for the time. For example:

          - tomorrow at 9pm | Call Sarah.
          - in 3 hours | Check if the turkey is done
          - friday at noon | Open loot boxes in Overwatch

        The message is the message which the bot will send you in a DM when the time of the reminder passes.
        """
        parsed_string = self._parse_reminder_string(command_str)
        if parsed_string is None:
            return await ctx.send_help()
        reminder_time, reminder_message = parsed_string
        reminder_dt = await self._parse_reminder_time(user=ctx.author, reminder_time=reminder_time)

        if None not in [reminder_dt, reminder_message]:

            if reminder_dt <= datetime.datetime.now(tz=pytz.UTC):
                await ErrorReply("The time you specified is in the past!").send(ctx)
                return

            confirm_message = "Please confirm that the following date/time is correct:\n\n"

            dt_user_tz = reminder_dt.astimezone(await self._get_user_timezone(user=ctx.author))
            dt_user_tz_str = dt_user_tz.strftime(self.CONFIRM_DT_FORMAT)

            confirm_message += f"> **{dt_user_tz_str}**"

            confirm_embed = MementoEmbedReply(message=confirm_message, title="Confirmation").build()
            confirmed = await InteractiveActions.yes_or_no_action(ctx=ctx, embed=confirm_embed)

            if confirmed:
                await self._set_user_reminder(user=ctx.author, reminder_dt=reminder_dt, reminder_text=reminder_message,
                                              timezone=self._get_user_tz_string(user=ctx.author))
                return await ctx.tick()
            return

        await ErrorReply("I was unable to understand that time. Please try again.").send(ctx)

    @_memento.command(name="tz", aliases=['timezone'])
    async def _memento_tz(self, ctx: Context, timezone: str):
        """
        Sets your preferred timezone, which will be the basis for all reminders.

        If you do not have a preferred timezone, US/Pacific will be used.

        For a complete list of timezones, see: https://sep.gg/timezones
        """
        pytz_string = TimezoneStrings.get_pytz_string(timezone)
        if pytz_string is None:
            valid_options = ', '.join(TimezoneStrings.get_timezone_options())

            return await ErrorReply(f'"{timezone}" is not a valid timezone. '
                                    f'Please choose from one of: {valid_options}.\n\n'
                                    f'For a ***complete*** list of timezones, see: {self.TIMEZONES_URL}').send(ctx)

        await self._set_user_timezone(ctx.author, pytz_string)
        await ctx.tick()

    @_memento.command(name="list")
    async def _memento_list(self, ctx: Context):
        """
        DM's you a list of your current reminders and about how long is left until time is up.

        The ID of the reminder is also included, which can be used to delete th reminder.
        """

        user_id = str(ctx.author.id)
        user_reminders = self.user_reminder_cache.get(user_id)

        # Respond with an error to the current context if the user does not have any reminder set.
        if not user_reminders:
            return await ErrorReply("You have no reminders set.").send(ctx)

        await ReminderListReply(reminders=user_reminders).send(ctx.author)

    """
    Deletes a reminder given the ID.
    :param ctx: Red Bot context.
    :param id_: ID of the reminder.
    """
    @_memento.command(name="delete", aliases=["del"])
    async def _memento_delete(self, ctx: Context, id_: str):
        """
        Deletes a reminder for the given ID.

        You can get the ID of the reminder by using the "list" command.
        """
        user_id = str(ctx.author.id)
        user_reminders = self.user_reminder_cache.get(user_id, [])

        for reminder in user_reminders:
            if reminder.id == id_:
                await self._delete_reminder(user=ctx.author, reminder_id=reminder.id)
                return await ctx.tick()

        await ErrorReply(f'You have no reminders with ID "{id_}". '
                         'Use the "list" command to get your reminders and their IDs.').send(ctx)

    @commands.group(name="remindrole", aliases=["mementorole"], invoke_without_command=True)
    @commands.guild_only()
    async def _remindrole(self, ctx: Context, role: discord.Role, channel: discord.TextChannel, *, command_str: str):

        bot_passed, response = self._check_permissions(channel=channel, role=role)

        if not bot_passed:
            return await ErrorReply(response).send(ctx)

        parsed_command = self._parse_reminder_string(command_str)
        if parsed_command is None:
            return ErrorReply("Unable to parse the command. Please check the help docs for usage.").send(ctx)

        reminder_time, reminder_message = parsed_command
        reminder_dt = await self._parse_reminder_time(user=ctx.author, reminder_time=reminder_time)

        if None not in [reminder_dt, reminder_message]:
            if reminder_dt <= datetime.datetime.now(tz=pytz.UTC):
                await ErrorReply("The time you specified is in the past!").send(ctx)
                return

            confirm_message = "Please confirm that the following date/time is correct:\n\n"

            dt_user_tz = reminder_dt.astimezone(await self._get_user_timezone(user=ctx.author))
            dt_user_tz_str = dt_user_tz.strftime(self.CONFIRM_DT_FORMAT)

            confirm_message += f"> **{dt_user_tz_str}**"

            confirm_embed = MementoEmbedReply(message=confirm_message, title="Confirmation").build()
            confirmed = await InteractiveActions.yes_or_no_action(ctx=ctx, embed=confirm_embed)

            if confirmed:
                await ctx.send(f"{role.name} | {channel.name} | {dt_user_tz}")
                return await ctx.tick()
            return

        await ErrorReply("I was unable to understand that time. Please try again.").send(ctx)
