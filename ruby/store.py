"""State + Notion boundary.

Notion is the permanent memory. `Store` is the interface the rest of Ruby uses; the
default `JsonStore` keeps working state on disk so Phase 1 runs without Notion.
`NotionMirror` is the seam where Notion writes go (stubbed until the Notion phase).
Every write goes through a retry queue so nothing is silently dropped.
"""
from __future__ import annotations
import json, os, uuid, logging
from datetime import datetime
from typing import Optional
from .models import Item

log = logging.getLogger("ruby.store")


class NotionMirror:
    """Replace the bodies with notion-client calls in the Notion phase."""
    def upsert(self, item: Item) -> Optional[str]:
        return None  # return Notion page URL
    def archive(self, item_id: str) -> None:
        return None


class JsonStore:
    def __init__(self, path: str, mirror: Optional[NotionMirror] = None):
        self.path = path
        self.mirror = mirror or NotionMirror()
        self.items: dict[str, Item] = {}
        self.undo: dict[str, dict] = {}       # undo_id -> {"created": [ids], "expires": iso}
        self.retry_queue: list[str] = []      # item ids whose Notion write failed
        self.state: dict = {"pause_until": None, "last_dm_channel": None}
        self._load()

    # ---- persistence
    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            raw = json.load(f)
        self.items = {k: Item.from_dict(v) for k, v in raw.get("items", {}).items()}
        self.undo = raw.get("undo", {})
        self.retry_queue = raw.get("retry_queue", [])
        self.state.update(raw.get("state", {}))

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"items": {k: v.to_dict() for k, v in self.items.items()},
                       "undo": self.undo, "retry_queue": self.retry_queue,
                       "state": self.state}, f)
        os.replace(tmp, self.path)

    # ---- items
    def add(self, **kw) -> Item:
        item = Item(id=uuid.uuid4().hex[:10], **kw)
        self.items[item.id] = item
        self._mirror(item)
        self.save()
        return item

    def update(self, item_id: str, **kw) -> Optional[Item]:
        item = self.items.get(item_id)
        if not item:
            return None
        for k, v in kw.items():
            setattr(item, k, v)
        self._mirror(item)
        self.save()
        return item

    def remove(self, item_id: str):
        self.items.pop(item_id, None)
        try:
            self.mirror.archive(item_id)
        except Exception:
            log.exception("notion archive failed")
        self.save()

    def open_items(self) -> list[Item]:
        return [i for i in self.items.values() if i.status in ("Due", "In Progress")]

    def _mirror(self, item: Item):
        try:
            url = self.mirror.upsert(item)
            if url:
                item.notion_url = url
            if item.id in self.retry_queue:
                self.retry_queue.remove(item.id)
        except Exception:
            log.exception("notion write failed; queued for retry")
            if item.id not in self.retry_queue:
                self.retry_queue.append(item.id)

    def retry_failed(self) -> int:
        n = 0
        for iid in list(self.retry_queue):
            item = self.items.get(iid)
            if item:
                self._mirror(item)
                n += iid not in self.retry_queue
        self.save()
        return n

    # ---- undo (24h window)
    def register_undo(self, created_ids: list[str]) -> str:
        uid = uuid.uuid4().hex[:8]
        from datetime import timedelta
        self.undo[uid] = {"created": created_ids,
                          "expires": (datetime.now() + timedelta(hours=24)).isoformat()}
        self.save()
        return uid

    def do_undo(self, uid: str) -> bool:
        rec = self.undo.pop(uid, None)
        if not rec or datetime.fromisoformat(rec["expires"]) < datetime.now():
            self.save()
            return False
        for iid in rec["created"]:
            self.remove(iid)
        return True

    # ---- pause / quiet
    def pause_until(self) -> Optional[datetime]:
        v = self.state.get("pause_until")
        return datetime.fromisoformat(v) if v else None

    def set_pause(self, until: Optional[datetime]):
        self.state["pause_until"] = until.isoformat() if until else None
        self.save()
