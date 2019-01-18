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
from memento.alarmreply import AlarmReply
from memento.mementoembed import MementoEmbedReply
from memento.reminder import Reminder
from memento.reminderlistreply import ReminderListReply
from memento.timezonestrings import TimezoneStrings
from pytz.tzinfo import DstTzInfo
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.commands import Context


class Memento(BaseSepCog, commands.Cog):

    ISO8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    CONFIRM_DT_FORMAT = "%b %d, %Y @ %I:%M:%S%p"
    DEFAULT_TIMEZONE = 'US/Pacific'
    USER_MESSAGE_INTERVAL = 0.1
    MONITOR_PROCESS_INTERVAL = 5
    MESSAGE_EMOJI = "\N{ALARM CLOCK}"

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
                        self.logger.error("Error converting database reminders to Reminder class. Error: {}".format(e))
                        continue
                user_reminders[str(user_id)] = cache_reminders

        self.user_config_cache = user_config
        self.user_reminder_cache = user_reminders

    """
    Given a pytz DstTzInfo object, return the Recurrent library Recurring event parser object 
    with the startime time localized to the user's timezone.
    :param user_timezone: pytz Timezone Info object for the user's timezone.
    """
    @staticmethod
    async def _get_recurrent_object(user_timezone: DstTzInfo) -> recurrent.RecurringEvent:
        now = datetime.datetime.utcnow()
        user_now = pytz.UTC.localize(now).astimezone(user_timezone).replace(tzinfo=None)
        return recurrent.RecurringEvent(now_date=user_now)

    """
    Loop which iterates overall set reminders and checks if it's time to announce them to the user.
    """
    async def __monitor_reminders(self):
        await self.bot.wait_until_ready()

        while self == self.bot.get_cog(self.__class__.__name__):
            users_to_notify = defaultdict(list)  # type: Dict[discord.User, List[str]]

            for user_id, user_reminders in self.user_reminder_cache.items():
                for user_reminder in user_reminders:
                    dt_string = user_reminder.dt_str
                    if dt_string is None:
                        break

                    reminder_dt = datetime.datetime.strptime(dt_string, self.ISO8601_FORMAT)
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

    """
    Sets the given pytz timezone string as the timezone for the given user.
    This will overwrite any existing user timezone preference.
    
    :param user: Discord.py user for which to set the timezone preference.
    :param timezone: pytz timezone string. Assumes that validation has already happened.
    """
    async def _set_user_timezone(self, user: discord.User, timezone: str):
        user_id = str(user.id)

        cache = self.user_config_cache.get(user_id, {})

        cache['timezone'] = timezone

        self.user_config_cache[user_id] = cache
        await self.config.user(user).config.set(cache)
        self.logger.info(f"Updated timezone config for User: {user.id} | Timezone: {timezone}")

    """
    Overwrites a user's reminders to the new list of reminders.
    :param user: discord.py user
    :param reminders: List of "Reminder" entities to save for the user. Will overwrite any existing reminders.
    """
    async def _update_user_reminders(self, user: discord.User, reminders: List[Reminder]):
        self.user_reminder_cache[str(user.id)] = reminders
        db_reminders = [r.prepare_for_storage() for r in reminders]
        await self.config.user(user).reminders.set(db_reminders)

    """
    Adds a new reminder for the user. Assumes that the reminder datetime has already been converted to UTC.
    :param user: discord.py user
    :param reminder_dt: Timezone-agnostic UTC datetime for when the reminder should trigger.
    :param reminder_text: Text to send to the user in the reminder.
    """
    async def _set_user_reminder(self, user: discord.User, reminder_dt: datetime.datetime, reminder_text: str):
        user_reminders = await self._get_user_reminders(user)
        user_reminders.append(
            Reminder(dt=reminder_dt.strftime(Reminder.ISO8601_FORMAT), text=reminder_text)
        )
        self.logger.info("Adding reminder. Time: {} | User: {} | Total Reminders: {}"
                         .format(reminder_dt.strftime(Reminder.ISO8601_FORMAT), user.id, len(user_reminders)))
        await self._update_user_reminders(user=user, reminders=user_reminders)

    """
    Retrieves a list of "Reminder" entities from the cache for the given user.
    :param user: discord.py user
    """
    async def _get_user_reminders(self, user: discord.User) -> List[Reminder]:
        user_id = str(user.id)
        return self.user_reminder_cache.get(user_id, [])

    """
    Deletes a reminder with the given reminder ID for the given user.
    :param user: discord.py user
    :param reminder_id: ID of a reminder.
    """
    async def _delete_reminder(self, user: discord.User, reminder_id: str):
        current_reminders = await self._get_user_reminders(user)
        new_reminders = []

        if reminder_id is None:
            self.logger.debug("User attempted to delete a reminder, but it was not found. Id: {} | User: {}"
                              .format(reminder_id, user.id))
            return

        for reminder in current_reminders:
            if reminder.id != reminder_id:
                new_reminders.append(reminder)
        self.logger.info("Deleting reminder for user: Id: {} | User: {}".format(reminder_id, user.id))
        await self._update_user_reminders(user=user, reminders=new_reminders)

    """
    Retrieves the user's preferred timezone. If the user does not have one set, returns Memento's default.
    :param user: discord.py user.
    """
    async def _get_user_timezone(self, user: discord.User) -> DstTzInfo:
        user_timezone = self.user_config_cache.get(str(user.id), {}).get('timezone')

        if user_timezone is None:
            self.logger.debug("User does not have a timezone set. Returning default: {} | User: {}"
                              .format(self.DEFAULT_TIMEZONE, user.id))
            return pytz.timezone(self.DEFAULT_TIMEZONE)

        return pytz.timezone(user_timezone)

    """
    Converts a user's reminder string into a timezone-agnostic UTC datetime, offset from the user's timezone.
    If the string was not understood, returns None.
    
    :param user: discord.py user.
    :param reminder_time: User supplied reminder string (from command parameters).
    """
    async def _parse_reminder_time(self, user: discord.User, reminder_time: str) -> Optional[datetime.datetime]:
        user_timezone = await self._get_user_timezone(user)
        user_recurrent = await self._get_recurrent_object(user_timezone)
        user_parsed_time = user_recurrent.parse(reminder_time)

        if user_parsed_time is not None:
            dt = user_timezone.localize(user_parsed_time)
            utc_dt = dt.astimezone(tz=pytz.UTC)
            return utc_dt
        self.logger.debug("Unable to parse user supplied reminder time: {}".format(reminder_time))
        return None

    """
    Parses a Memento command string into the reminder time and reminder message.
    If the command is not in the correct format, will return None.
    :param reminder_string: Raw command from the Memento command.
    """
    def _parse_reminder_string(self, reminder_string: str) -> Optional[Tuple[str, str]]:
        try:
            reminder_time, reminder_message = reminder_string.split("|", maxsplit=1)
        except (ValueError, TypeError) as e:
            self.logger.error("Error parsing reminder string: {} | Error: {}".format(reminder_string, e))
            return None
        return reminder_time, reminder_message

    """
    Main Memento command to set reminders.
    :param ctx: Red Bot context.
    :param reminder_string: Raw string for everything after the prefix and command.
    """
    @commands.group(name="memento", aliases=['remindme'], invoke_without_command=True)
    async def _memento(self, ctx: Context, *, reminder_string: str):
        parsed_string = self._parse_reminder_string(reminder_string)
        if parsed_string is None:
            return await ctx.send_help()
        reminder_time, reminder_message = parsed_string
        reminder_dt = await self._parse_reminder_time(user=ctx.author, reminder_time=reminder_time)

        if None not in [reminder_dt, reminder_string]:

            if reminder_dt <= datetime.datetime.now(tz=pytz.UTC):
                await ErrorReply("The time you specified is in the past!").send(ctx)
                return

            message = "Please confirm that the following date/time is correct:\n\n"

            dt_user_tz = reminder_dt.astimezone(await self._get_user_timezone(user=ctx.author))
            dt_user_tz_str = dt_user_tz.strftime(self.CONFIRM_DT_FORMAT)

            message += "> **{}**".format(dt_user_tz_str)

            confirm_embed = MementoEmbedReply(message=message, title="Confirmation").build()
            confirmed = await InteractiveActions.yes_or_no_action(ctx=ctx,embed=confirm_embed)

            if confirmed:
                await self._set_user_reminder(user=ctx.author, reminder_dt=reminder_dt, reminder_text=reminder_string)
                return await ctx.tick()
            return

        await ErrorReply("I was unable to understand that time. Please try again.").send(ctx)

    """
    Memento command for setting the user's timezone preference
    :param ctx: Red Bot context
    :param timezone: Raw user supplied timezone string
    """
    @_memento.command(name="tz", aliases=['timezone'])
    async def _memento_tz(self, ctx: Context, timezone: str):
        pytz_string = TimezoneStrings.get_pytz_string(timezone)
        if pytz_string is None:
            valid_options = ', '.join(TimezoneStrings.get_timezone_options())
            return await ErrorReply("Timezone is not valid. Please choose from one of {}".format(valid_options))\
                .send(ctx)

        await self._set_user_timezone(ctx.author, pytz_string)
        await ctx.tick()

    """
    Memento command for retrieving a list of reminders.
    Responds to the user in a DM with a sorted (by time) list of reminders and their contents.
    :param ctx: Red Bot context.
    """
    @_memento.command(name="list")
    async def _memento_list(self, ctx: Context):

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
        user_id = str(ctx.author.id)
        user_reminders = self.user_reminder_cache.get(user_id, [])

        for reminder in user_reminders:
            if reminder.id == id_:
                await self._delete_reminder(user=ctx.author, reminder_id=reminder.id)
                return await ctx.tick()

        await ErrorReply('You have no reminders with ID "{}". '
                         'Use the "list" command to get your reminders and their IDs.'.format(id_)).send(ctx)
