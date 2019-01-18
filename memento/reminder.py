from datetime import datetime
from typing import Dict


class Reminder(object):
    ISO8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

    def __init__(self, id: str, dt: str, text: str, timezone: str = None):
        self.id = id
        self.dt_str = dt
        self.dt_obj = datetime.strptime(dt, self.ISO8601_FORMAT)
        self.text = text
        self.timezone = timezone

    """
    Convert the object into a format suitable for storing in the database;
    """
    def prepare_for_storage(self) -> Dict:
        return {
            'id': self.id,
            'dt': self.dt_obj.strftime(self.ISO8601_FORMAT),
            'text': self.text,
            'timezone': self.timezone
        }
