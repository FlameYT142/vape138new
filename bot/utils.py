import re
from datetime import datetime
from zoneinfo import ZoneInfo
from bot.config import TZ

DURATION_RE = re.compile(r"^(\d+)([мчд])$")

def now_local():
    return datetime.now(ZoneInfo(TZ))

def parse_duration(text):
    text = text.strip().lower()
    if text in ("навсегда", "forever", "вечно"):
        return None, "навсегда"
    m = DURATION_RE.match(text)
    if not m:
        return "ERROR", None
    value, unit = int(m.group(1)), m.group(2)
    if unit == "м":
        return value * 60, f"{value} минут"
    if unit == "ч":
        return value * 3600, f"{value} часов"
    if unit == "д":
        return value * 86400, f"{value} дней"
    return "ERROR", None

def seconds_to_text(sec):
    if sec is None:
        return "навсегда"
    if sec % 86400 == 0:
        return f"{sec // 86400} дней"
    if sec % 3600 == 0:
        return f"{sec // 3600} часов"
    return f"{sec // 60} минут"

def apply_vip(duration_sec):
    if duration_sec is None:
        return None
    return max(duration_sec // 2, 30)

def apply_recurrence(duration_sec):
    if duration_sec is None:
        return None
    return min(duration_sec * 2, 30 * 86400)

def is_quiet_hours():
    """True, если сейчас 23:00–05:00 по Братску (правило 22)."""
    h = now_local().hour
    return h >= 23 or h < 5