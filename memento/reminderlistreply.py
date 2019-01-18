from datetime import datetime
from typing import List

import discord
import timeago
from cog_shared.seplib.constants.colors import HexColors
from cog_shared.seplib.responses.embeds import EmbedReply
from memento.reminder import Reminder


class ReminderListReply(EmbedReply):
    TITLE_EMOJI = "\N{ALARM CLOCK}"
    TITLE = "{} Reminder List! [Memento]".format(TITLE_EMOJI)

    def __init__(self, reminders: List[Reminder]):
        super(ReminderListReply, self).__init__(message="", color=HexColors.Red, emoji=None)
        self.reminders = reminders

    def build_message(self):

        message = "Here's your current list of reminders:\n\n"
        for index, reminder in enumerate(self.reminders):
            count = index + 1
            time_string = timeago.format(date=reminder.dt_obj, now=datetime.utcnow())
            message += "{}. **{}** | {} ({})\n".format(count, reminder.text, time_string, reminder.id)
        return message

    def build(self):
        return discord.Embed(description=self.build_message(), color=self.color, title=self.TITLE)
