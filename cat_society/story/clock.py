"""Pure story-day clock used by the island shop and the Music Maker.

A story day starts at dawn (05:30), not midnight.  Keeping a monotonic stamp
behind the friendly day/time display makes deadlines and return appointments
simple and deterministic even when Bal composes through midnight.
"""

from .. import config


DAWN_MINUTE = 5 * 60 + 30
SHOP_OPEN_MINUTE = int(getattr(config, "STORY_SHOP_OPEN", 9 * 60))
SHOP_CLOSE_MINUTE = int(getattr(config, "STORY_SHOP_CLOSE", 18 * 60))


class StoryClock:
    def __init__(self, day=1, minutes=8 * 60 + 30):
        self.day = max(1, int(day))
        self.minutes = float(minutes) % 1440.0

    @property
    def rate(self):
        real_minutes = max(1.0, float(getattr(config, "STORY_DAY_REAL_MINUTES", 20.0)))
        return 1440.0 / (real_minutes * 60.0)

    @property
    def stamp(self):
        cycle = (self.minutes - DAWN_MINUTE) % 1440.0
        return (self.day - 1) * 1440.0 + cycle

    def set_stamp(self, stamp):
        stamp = max(0.0, float(stamp))
        self.day = 1 + int(stamp // 1440.0)
        self.minutes = (DAWN_MINUTE + stamp % 1440.0) % 1440.0

    def set_time(self, minutes):
        self.minutes = float(minutes) % 1440.0

    def advance(self, real_seconds):
        old = self.stamp
        new = old + max(0.0, float(real_seconds)) * self.rate
        events = []
        first_cycle = max(0, int(old // 1440.0) - 1)
        last_cycle = int(new // 1440.0) + 1
        open_offset = SHOP_OPEN_MINUTE - DAWN_MINUTE
        close_offset = SHOP_CLOSE_MINUTE - DAWN_MINUTE
        for cycle in range(first_cycle, last_cycle + 1):
            base = cycle * 1440.0
            for boundary, kind in ((base + open_offset, "shop_open"),
                                   (base + close_offset, "shop_close"),
                                   (base + 1440.0, "new_day")):
                if old < boundary <= new:
                    events.append(kind)
        self.set_stamp(new)
        return events

    @property
    def shop_open(self):
        return SHOP_OPEN_MINUTE <= self.minutes < SHOP_CLOSE_MINUTE

    def format_time(self):
        minute = int(self.minutes + 0.5) % 1440
        hour = minute // 60
        mins = minute % 60
        return "%02d:%02d" % (hour, mins)

    def minutes_until(self, target_stamp):
        return max(0.0, float(target_stamp) - self.stamp)


def stamp_for(day, minutes):
    clock = StoryClock(day, minutes)
    return clock.stamp


def display_from_stamp(stamp):
    clock = StoryClock()
    clock.set_stamp(stamp)
    return clock.day, clock.minutes
