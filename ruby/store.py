"""State + Notion boundary.

Notion is the permanent memory. `Store` is the interface the rest of Ruby uses; the
default `JsonStore` keeps working state on disk so Phase 1 runs without Notion.
`ruby.notion.NotionMirror` writes to Notion; `NullMirror` is used when no token is set.
Every write goes through a retry queue so nothing is silently dropped.
"""
from __future__ import annotations
import json, os, uuid, logging
from datetime import datetime
from typing import Optional
from .models import Item

log = logging.getLogger("ruby.store")


class NullMirror:
    """No-op mirror used when NOTION_TOKEN is not set (local dev, tests)."""
    def upsert(self, item: Item) -> Optional[str]:
        return None
    def archive(self, item: Item) -> None:
        return None
    def pull_open(self) -> list[Item]:
        return []
    def read_brain(self) -> str:
        return ""
    def create_row(self, ds_key, props, children=None):
        return None
    def find_by_title(self, ds_key, title_prop, contains):
        return None
    def update_page(self, page_id, props):
        return None
    def archive_page(self, page_id):
        return None
    def preflight(self) -> list:
        return []
    def set_permission_to_enter(self, unit: str, value: str):
        return None


def _usable_path(path: str) -> str:
    """Create the state folder if needed; if it can't be written (e.g. no Railway volume at /data),
    fall back to a local file so Ruby keeps working. State then resets on redeploy; Notion is the record."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        probe = path + ".probe"
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return path
    except OSError:
        fallback = os.path.join(os.getcwd(), os.path.basename(path))
        log.warning("State path %s is not writable; using %s (resets on redeploy). Add a volume to keep it.",
                    path, fallback)
        return fallback


class JsonStore:
    def __init__(self, path: str, mirror=None):
        self.path = _usable_path(path)
        self.mirror = mirror or NullMirror()
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
        item = self.items.pop(item_id, None)
        self.retry_queue = [i for i in self.retry_queue if i != item_id]
        try:
            if item:
                self.mirror.archive(item)
        except Exception:
            log.exception("notion archive failed")
        self.save()

    def sync_from_notion(self) -> int:
        """Rebuild state from Notion (fresh volume / restart). Notion wins on conflicts:
        its open rows are added if unknown, and local items whose Notion row is gone or closed
        are left alone only if they are still waiting in the retry queue."""
        try:
            remote = self.mirror.pull_open()
        except Exception:
            log.exception("notion sync failed; continuing with local state")
            return 0
        known = {i.notion_url: i for i in self.items.values() if i.notion_url}
        added = 0
        for r in remote:
            if r.notion_url in known:
                local = known[r.notion_url]
                local.title, local.due, local.prop = r.title, r.due, r.prop
            else:
                self.items[r.id] = r
                added += 1
        remote_urls = {r.notion_url for r in remote}
        for i in list(self.items.values()):
            if i.notion_url and i.notion_url not in remote_urls and i.id not in self.retry_queue \
                    and i.status in ("Due", "In Progress"):
                i.status = "Done"   # closed or archived in Notion
        self.save()
        return added

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
    def register_undo(self, created_ids: list[str], pages: Optional[list[str]] = None) -> str:
        uid = uuid.uuid4().hex[:8]
        from datetime import timedelta
        self.undo[uid] = {"created": created_ids, "pages": pages or [],
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
        for pid in rec.get("pages", []):
            try:
                self.mirror.archive_page(pid)
            except Exception:
                log.exception("could not archive Notion page %s", pid)
        return True

    # ---- pause / quiet
    def pause_until(self) -> Optional[datetime]:
        v = self.state.get("pause_until")
        return datetime.fromisoformat(v) if v else None

    def set_pause(self, until: Optional[datetime]):
        self.state["pause_until"] = until.isoformat() if until else None
        self.save()
