from datetime import datetime
from typing import List, Tuple

import discord
import timeago
from memento.embeds.mementoembed import MementoEmbedReply
from memento.types.channelreminder import ChannelReminder


class RoleReminderListReply(MementoEmbedReply):
    def __init__(self, reminders: List[Tuple[ChannelReminder, discord.TextChannel]], role: discord.Role):
        super(RoleReminderListReply, self).__init__(message="", title=f"Role Reminder List - Guild: {role.guild.name}")
        self.role = role
        self.reminders = sorted(reminders, key=lambda r: r[0].dt_obj)

    def build_message(self):
        message = f"List of active reminders for `@{self.role.name}`:\n\n"
        for index, rc in enumerate(self.reminders):
            reminder, channel = rc
            count = index + 1
            time_string = timeago.format(date=reminder.dt_obj, now=datetime.utcnow())
            message += "{}. **{}** | {} ({})\n".format(count, reminder.text, time_string, reminder.id)
            message += f"  - {channel.mention}\n"
        return message
