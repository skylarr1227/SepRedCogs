import hashlib
from datetime import datetime
from typing import Dict

from memento.types.reminder import Reminder


class ChannelReminder(Reminder):

    def __init__(self, dt: str, text: str, role_id: str, timezone, id: str = None):
        super(ChannelReminder, self).__init__(dt=dt, text=text, timezone=timezone, id=id)
        self.role_id = role_id

    """
    Convert the object into a format suitable for storing in the database;
    """
    def prepare_for_storage(self) -> Dict:
        pfs = super(ChannelReminder, self).prepare_for_storage()
        pfs['role_id'] = self.role_id
        return pfs
