"""Roz ki fixed time (jaise subah 8 baje Pakistan) par report: time ke helpers."""
from __future__ import annotations

PKT_HOURS = 5.0                      # Pakistan UTC+5 (DST nahi)


def parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("report_daily_at HH:MM hona chahiye, jaise 08:00")
    return h, m


def last_slot(now: float, hhmm: str, tz_hours: float = PKT_HOURS) -> float:
    """Sabse recent 'roz HH:MM (local)' ka epoch seconds jo `now` se pehle ya barabar ho."""
    h, m = parse_hhmm(hhmm)
    local = now + tz_hours * 3600
    day_start = local - local % 86400
    slot = day_start + h * 3600 + m * 60
    if slot > local:
        slot -= 86400
    return slot - tz_hours * 3600


def fmt_local(ms: int, tz_hours: float = PKT_HOURS, name: str = "PKT") -> str:
    import time
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000 + tz_hours * 3600)) + f" {name}"
