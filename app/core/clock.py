from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")


class Clock:
    def now(self):
        return datetime.now(timezone.utc)

    def stamp(self):
        return stamp(self.now())


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def day_key(value):
    return value.astimezone(VN).date().isoformat()


def reset_at(value):
    tomorrow = value.astimezone(VN).date() + timedelta(days=1)
    return stamp(datetime.combine(tomorrow, datetime.min.time(), tzinfo=VN))
