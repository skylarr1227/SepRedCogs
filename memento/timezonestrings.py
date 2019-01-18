import typing

import pytz
from pytz.tzinfo import DstTzInfo


class TimezoneStrings(object):

    Hawaii = "US/Hawaii"
    Alaska = "US/Alaska"
    Pacific = "US/Pacific"
    Mountain = "US/Mountain"
    Central = "US/Central"
    Eastern = "US/Eastern"
    Atlantic = "Canada/Atlantic"
    UTC = "UTC"

    _MAP = {
        "Hawaii": Hawaii,
        "Alaska": Alaska,
        "Pacific": Pacific,
        "Mountain": Mountain,
        "Central": Central,
        "Eastern": Eastern,
        "Atlantic": Atlantic,
        "UTC": UTC
    }

    @staticmethod
    def get_timezone_options() -> typing.List[str]:
        return sorted(TimezoneStrings._MAP.keys())

    @staticmethod
    def is_valid_timezone(tz: str) -> bool:
        return tz.title() in TimezoneStrings._MAP or tz in pytz.all_timezones

    @staticmethod
    def get_pytz_string(tz: str) -> str:
        if TimezoneStrings.is_valid_timezone(tz):
            if tz in pytz.all_timezones:
                return tz
            return TimezoneStrings._MAP.get(tz)

    @staticmethod
    def get_pytz_timezone(tz: str) -> DstTzInfo:
        if TimezoneStrings.is_valid_timezone(tz):
            return pytz.timezone(TimezoneStrings.get_pytz_string(tz))
