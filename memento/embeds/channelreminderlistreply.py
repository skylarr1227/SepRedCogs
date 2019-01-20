from datetime import datetime
from typing import List

import discord
import timeago
from memento.embeds.mementoembed import MementoEmbedReply
from memento.types.channelreminder import ChannelReminder


class ChannelReminderListReply(MementoEmbedReply):
    def __init__(self, reminders: List[ChannelReminder], channel: discord.TextChannel):
        super(ChannelReminderListReply, self).__init__(message="",
                                                       title=f"Channel Reminder List - Guild: {channel.guild.name}")
        self.channel = channel
        self.reminders = sorted(reminders, key=lambda r: r.dt_obj)

    def build_message(self):
        message = f"List of active reminders for {self.channel.mention}:\n\n"
        for index, reminder in enumerate(self.reminders):
            try:
                role = self.channel.guild.get_role(int(reminder.role_id)).name
            except Exception:
                role = reminder.role_id
            count = index + 1
            time_string = timeago.format(date=reminder.dt_obj, now=datetime.utcnow())
            message += "{}. **{}** | {} ({})\n".format(count, reminder.text, time_string, reminder.id)
            message += f"  - `@{role}`\n"
        return message
