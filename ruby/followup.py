"""Follow-up rule: raise once more at next check-in, then star + move to tomorrow at 5 PM. Never nag."""
from datetime import datetime, timedelta
from .models import Item


def after_checkin(items: list[Item]) -> None:
    for i in items:
        if i.status in ("Due", "In Progress") and not i.starred:
            i.raised += 1


def nightly_rollover(items: list[Item], today: datetime) -> list[Item]:
    """5 PM shutdown: still-open items move to tomorrow, starred. Returns moved items."""
    moved = []
    tomorrow = (today + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
    for i in items:
        if i.status == "Due":
            i.starred = True
            i.due = tomorrow if (i.due is None or i.due.replace(tzinfo=None) < tomorrow.replace(tzinfo=None)) else i.due
            i.raised = 0
            moved.append(i)
    return moved
