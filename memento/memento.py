import asyncio
import datetime
from collections import defaultdict
from typing import Optional, Tuple, List, Dict

import discord
import pytz
import recurrent
from cog_shared.seplib.constants.colors import HexColors
from cog_shared.seplib.responses.embeds import ErrorReply, SuccessReply, EmbedReply
from cog_shared.seplib.utils.random_utils import random_string
from memento.alarmreply import AlarmReply
from memento.timezonestrings import TimezoneStrings
from pytz.tzinfo import DstTzInfo
from redbot.core import commands, Config

from cog_shared.seplib.classes.basesepcog import BaseSepCog
from redbot.core.bot import Red
from redbot.core.commands import Context


class Memento(BaseSepCog, commands.Cog):

    ISO8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    DEFAULT_TIMEZONE = 'US/Pacific'
    USER_MESSAGE_INTERVAL = 0.1
    MONITOR_PROCESS_INTERVAL = 5
    MESSAGE_EMOJI = "\N{ALARM CLOCK}"

    def __init__(self, bot: Red):

        super(Memento, self).__init__(bot=bot)
        self.user_config_cache = {}
        self.user_reminder_cache = {}

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
                user_reminders[str(user_id)] = reminders

        self.user_config_cache = user_config
        self.user_reminder_cache = user_reminders

    async def __monitor_reminders(self):
        await self.bot.wait_until_ready()

        while self == self.bot.get_cog(self.__class__.__name__):
            users_to_notify = defaultdict(list)  # type: Dict[discord.User, List[str]]

            for user_id, user_reminders in self.user_reminder_cache.items():
                for user_reminder in user_reminders:
                    dt_string = user_reminder.get('dt')
                    if dt_string is None:
                        break

                    reminder_dt = datetime.datetime.strptime(dt_string, self.ISO8601_FORMAT)
                    now = datetime.datetime.utcnow()

                    if reminder_dt < now:
                        user = self.bot.get_user(id=int(user_id))  # type: discord.User
                        id_ = user_reminder.get('id')
                        await self._delete_reminder(user=user, reminder_id=id_)
                        users_to_notify[user].append(user_reminder.get('text'))
                        self.logger.info(f"User reminder queued up. User: {user.id} | id: {id_}")

            for user, reminders in users_to_notify.items():
                for reminder in reminders:
                    await AlarmReply(message=reminder).send(user)
                    await asyncio.sleep(self.USER_MESSAGE_INTERVAL)

            await asyncio.sleep(self.MONITOR_PROCESS_INTERVAL)

    async def _set_user_timezone(self, user: discord.User, timezone: str):
        user_id = str(user.id)

        cache = self.user_config_cache.get(user_id, {})

        cache['timezone'] = timezone

        self.user_config_cache[user_id] = cache
        await self.config.user(user).config.set(cache)
        self.logger.info(f"Updated timezone config for User: {user.id} | Timezone: {timezone}")

    async def _update_user_reminders(self, user: discord.User, reminders: List[Dict]):
        self.user_reminder_cache[str(user.id)] = reminders
        await self.config.user(user).reminders.set(reminders)

    async def _set_user_reminder(self, user: discord.User, reminder_dt: datetime.datetime, reminder_text: str):
        user_reminders = await self._get_use_reminders(user)
        user_reminders.append({
            'id': random_string(),
            'dt': reminder_dt.strftime(self.ISO8601_FORMAT),
            'text': reminder_text
        })
        await self._update_user_reminders(user=user, reminders=user_reminders)

    async def _get_use_reminders(self, user: discord.User) -> List[Dict]:
        user_id = str(user.id)
        return self.user_reminder_cache.get(user_id, [])

    async def _delete_reminder(self, user: discord.User, reminder_id: str):
        current_reminders = await self._get_use_reminders(user)
        new_reminders = []

        if reminder_id is None:
            return

        for reminder in current_reminders:
            if reminder.get("id") != reminder_id:
                new_reminders.append(reminder)

        await self._update_user_reminders(user=user, reminders=new_reminders)

    async def _get_recurrent_object(self, user_timezone: DstTzInfo) -> recurrent.RecurringEvent:
        now = datetime.datetime.utcnow()
        user_now = pytz.UTC.localize(now).astimezone(user_timezone).replace(tzinfo=None)
        return recurrent.RecurringEvent(now_date=user_now)

    async def _get_user_timezone(self, user: discord.User) -> DstTzInfo:
        user_timezone = self.user_config_cache.get(str(user.id), {}).get('timezone')

        if user_timezone is None:
            return pytz.timezone(self.DEFAULT_TIMEZONE)

        return pytz.timezone(user_timezone)

    async def _parse_reminder_time(self, user: discord.User, reminder_time: str) -> Optional[datetime.datetime]:
        user_timezone = await self._get_user_timezone(user)
        user_recurrent = await self._get_recurrent_object(user_timezone)
        dt = user_timezone.localize(user_recurrent.parse(reminder_time))
        if dt is not None:
            utc_dt = dt.astimezone(tz=pytz.UTC)
            return utc_dt
        return None

    def _parse_reminder_string(self, reminder_string: str) -> Optional[Tuple[str, str]]:
        try:
            reminder_time, reminder_message = reminder_string.split("|", maxsplit=1)
        except ValueError as e:
            self.logger.error("Error parsing reminder string: {} | Error: {}".format(reminder_string, e))
            return None
        return reminder_time, reminder_message

    @commands.group(name="memento", aliases=['remindme'], invoke_without_command=True)
    async def _memento(self, ctx: Context, *, reminder_string: str):
        reminder_time, reminder_string = self._parse_reminder_string(reminder_string)
        reminder_dt = await self._parse_reminder_time(user=ctx.author, reminder_time=reminder_time)

        if None not in [reminder_dt, reminder_string]:

            if reminder_dt <= datetime.datetime.now(tz=pytz.UTC):
                await ErrorReply("The time you specified is in the past!").send(ctx)
                return

            await self._set_user_reminder(user=ctx.author, reminder_dt=reminder_dt, reminder_text=reminder_string)
            await ctx.tick()
            return
        await ErrorReply("I was unable to understand that time. Please try again.").send(ctx)

    @_memento.command(name="tz", aliases=['timezone'])
    async def _memento_tz(self, ctx: Context, timezone: str):
        pytz_string = TimezoneStrings.get_pytz_string(timezone)
        if pytz_string is None:
            valid_options = ', '.join(TimezoneStrings.get_timezone_options())
            return await ErrorReply("Timezone is not valid. Please choose from one of {}".format(valid_options))\
                .send(ctx)

        await self._set_user_timezone(ctx.author, pytz_string)
        await ctx.tick()



