"""The single quiet-hours gate. Every Ruby-initiated message passes through `may_send`."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from .config import TZ, WORK_START, WORK_END, URGENT_START, URGENT_END
from .models import URGENT_KINDS


def _now(now: Optional[datetime]) -> datetime:
    return (now or datetime.now(TZ)).astimezone(TZ)


def in_work_window(now: Optional[datetime] = None) -> bool:
    n = _now(now)
    return n.weekday() < 5 and WORK_START <= n.time() <= WORK_END


def in_urgent_window(now: Optional[datetime] = None) -> bool:
    """Urgent items may go out 6:00-21:00 on any day, never overnight."""
    n = _now(now)
    return URGENT_START <= n.time() <= URGENT_END


def may_send(urgent_kind: Optional[str] = None, paused_until: Optional[datetime] = None,
             now: Optional[datetime] = None) -> bool:
    """urgent_kind must be one of the three allowed urgent types; anything else is not urgent."""
    n = _now(now)
    if urgent_kind in URGENT_KINDS:
        return in_urgent_window(n)          # urgent beats /quiet pauses, but not overnight
    if paused_until and n < paused_until.astimezone(TZ):
        return False
    return in_work_window(n)
