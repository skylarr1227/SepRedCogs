from datetime import datetime
from typing import List

import timeago
from memento.embeds.mementoembed import MementoEmbedReply
from memento.types.reminder import Reminder


class ReminderListReply(MementoEmbedReply):
    def __init__(self, reminders: List[Reminder]):
        super(ReminderListReply, self).__init__(message="", title="Reminder List!")
        self.reminders = sorted(reminders, key=lambda r: r.dt_obj)

    def build_message(self):
        message = "Here's your current list of reminders:\n\n"
        for index, reminder in enumerate(self.reminders):
            count = index + 1
            time_string = timeago.format(date=reminder.dt_obj, now=datetime.utcnow())
            message += "{}. **{}** | {} ({})\n".format(count, reminder.text, time_string, reminder.id)
        return message
