from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

# Statuses shown to Roxy: "Overdue" is always rendered as "Still open".
STATUSES = ("Due", "In Progress", "Done", "Skipped")

URGENT_KINDS = ("marked_urgent", "move_in_gap", "legal_deadline")


@dataclass
class Item:
    id: str
    title: str
    prop: str = "Both"            # P88 | HG | Both
    due: Optional[datetime] = None
    status: str = "Due"
    starred: bool = False
    pinned: bool = False
    urgent_kind: Optional[str] = None   # one of URGENT_KINDS
    hard_deadline: bool = False
    move_in_tomorrow_gap: bool = False
    unblocks: bool = False
    snoozed_until: Optional[datetime] = None
    channel: Optional[str] = None       # channel where Ruby's card lives
    slack_ts: Optional[str] = None      # for edit-in-place
    notion_url: Optional[str] = None
    raised: int = 0                     # times surfaced in check-ins (follow-up rule)
    source: Optional[str] = None
    notes: Optional[str] = None         # specifics kept out of the title (terms, bid amounts)
    intent: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        for k in ("due", "snoozed_until"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        for k in ("due", "snoozed_until"):
            if d.get(k):
                d[k] = datetime.fromisoformat(d[k])
        return cls(**d)
