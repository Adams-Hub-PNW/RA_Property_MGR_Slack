"""Top 3 ranking, in the order from the outline."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from .models import Item


def _rank(i: Item) -> tuple:
    far = datetime.max
    due = i.due.replace(tzinfo=None) if i.due else far
    return (
        0 if i.pinned else 1,                 # Roxy's 📌 always wins
        0 if i.hard_deadline else 1,          # 1. hard deadlines today
        0 if i.move_in_tomorrow_gap else 1,   # 2. tomorrow's move-ins with gaps
        0 if i.starred else 1,                # 3. starred carry-overs
        0 if i.unblocks else 1,               # 4. unblocks a vendor/resident
        due,                                  # 5. by due time
    )


def reason(i: Item) -> str:
    if i.pinned: return "you pinned it"
    if i.hard_deadline: return "hard deadline"
    if i.move_in_tomorrow_gap: return "move-in tomorrow"
    if i.starred: return "carried from yesterday"
    if i.unblocks: return "someone is waiting"
    return "due soon"


def active(items: list[Item], now: Optional[datetime] = None) -> list[Item]:
    now = now or datetime.now()
    out = []
    for i in items:
        if i.status not in ("Due", "In Progress"):
            continue
        if i.snoozed_until and i.snoozed_until.replace(tzinfo=None) > now.replace(tzinfo=None):
            continue
        out.append(i)
    return out


def rank(items: list[Item], now: Optional[datetime] = None) -> list[Item]:
    return sorted(active(items, now), key=_rank)


def top3(items: list[Item], now: Optional[datetime] = None) -> tuple[list[Item], list[Item]]:
    r = rank(items, now)
    return r[:3], r[3:]
