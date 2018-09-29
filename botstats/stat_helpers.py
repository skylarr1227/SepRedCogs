import datetime
import os
import time
from typing import Tuple

from hurry.filesize import size
import psutil


class StatHelpers(object):

    @staticmethod
    def _raw_bot_memory_usage():
        process = psutil.Process(os.getpid())
        return process.memory_info().rss

    @staticmethod
    def bot_memory_usage() -> str:
        return "{} ({:.3f}%)".format(size(StatHelpers._raw_bot_memory_usage()), StatHelpers._raw_bot_per_used_memory())

    @staticmethod
    def _raw_bot_per_used_memory():
        bot_used = StatHelpers._raw_bot_memory_usage()
        total = StatHelpers._raw_sys_total_memory()
        return (bot_used / total) * 100

    @staticmethod
    def _raw_sys_memory_usage():
        return psutil.virtual_memory().used

    @staticmethod
    def sys_memory_usage() -> str:
        return size(StatHelpers._raw_sys_memory_usage())

    @staticmethod
    def _raw_sys_total_memory():
        return psutil.virtual_memory().total

    @staticmethod
    def sys_total_memory() -> str:
        return size(StatHelpers._raw_sys_total_memory())

    @staticmethod
    def _raw_sys_per_used_memory():
        used = StatHelpers._raw_sys_memory_usage()
        total = StatHelpers._raw_sys_total_memory()
        return (used / total) * 100

    @staticmethod
    def memory_used_over_total() -> str:
        return "{} / {} ({:.1f}%)".format(StatHelpers.sys_memory_usage(), StatHelpers.sys_total_memory(),
                                          StatHelpers._raw_sys_per_used_memory())

    @staticmethod
    def cpu_sys_usage() -> str:
        return "{}%".format(psutil.cpu_percent())

    @staticmethod
    def _raw_uptime_seconds():
        return int(time.time() - psutil.boot_time())

    @staticmethod
    def _get_dhms_tuple_From_seconds(seconds: int):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)

        return (d, h, m, s)

    @staticmethod
    def system_uptime_tuple() -> Tuple[int, int, int, int]:
        uptime_seconds = StatHelpers._raw_uptime_seconds()
        return StatHelpers._get_dhms_tuple_From_seconds(seconds=uptime_seconds)

    @staticmethod
    def _format_dhms_str(dhms_tuple: Tuple[int, int, int, int], short=True):
        d, h, m, s = dhms_tuple

        day_string = "d" if short else ("days" if d != 1 else "day")
        hour_string = "h" if short else ("hours" if h != 1 else "hour")
        min_string = "m" if short else ("minutes" if m != 1 else "minute")
        sec_string = "s" if short else ("seconds" if s != 1 else "second")

        return f"{d}{day_string}, {h}{hour_string}, {m}{min_string}, {s}{sec_string}"


    @staticmethod
    def system_uptime_str(short=True):
        uptime_tuple = StatHelpers.system_uptime_tuple()
        return StatHelpers._format_dhms_str(uptime_tuple, short)

    @staticmethod
    def bot_uptime_str(bot_uptime_dt: datetime.datetime, short=True):
        bot_start_epoch = int(time.mktime(bot_uptime_dt.timetuple()))

        now_dt = datetime.datetime.utcnow()
        now_epoch = int(time.mktime(now_dt.timetuple()))

        uptime_seconds = now_epoch - bot_start_epoch

        uptime_tuple = StatHelpers._get_dhms_tuple_From_seconds(uptime_seconds)

        return StatHelpers._format_dhms_str(uptime_tuple, short=short)
