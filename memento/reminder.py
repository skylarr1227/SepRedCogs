import hashlib
from datetime import datetime
from typing import Dict


class Reminder(object):
    ISO8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

    def __init__(self, dt: str, text: str, timezone: str = None, id: str = None):
        if id is None:
            id = self.generate_random_id(text, dt)
        self.id = id  # type: str
        self.dt_str = dt
        self.dt_obj = datetime.strptime(dt, self.ISO8601_FORMAT)
        self.text = text
        self.timezone = timezone

    @staticmethod
    def generate_random_id(text: str, dt: str) -> str:
        input = "{}{}".format(text, dt)
        return hashlib.sha1(input.encode("utf-8")).hexdigest()[0:8]

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
