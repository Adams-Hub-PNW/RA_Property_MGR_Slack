"""Notion mirror: writes Ruby's items to the Task Tracker database and reads them back on startup.

Notion is the system of record. `JsonStore` calls `upsert`/`archive` on every change; failures
raise so the store's retry queue can re-run them. Only unit # + first name ever go in titles.
"""
from __future__ import annotations
import json, logging, os, re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Item

log = logging.getLogger("ruby.notion")

IDS = json.loads((Path(__file__).parent / "notion_ids.json").read_text())
TASK_TRACKER = IDS["data_sources"]["task_tracker"]

PROP_TO_NOTION = {"P88": "Peak 88", "HG": "Heritage Grove", "Both": "Both"}
NOTION_TO_PROP = {v: k for k, v in PROP_TO_NOTION.items()}
# Ruby's four statuses -> Task Tracker's four. "In Progress" is still open in Notion.
STATUS_TO_NOTION = {"Due": "Due", "In Progress": "Due", "Done": "Done", "Skipped": "Skipped"}
OPEN_NOTION = ("Due", "Overdue")

_HEX32 = re.compile(r"([0-9a-f]{32})(?:\?|$)", re.I)


def page_id_from_url(url: Optional[str]) -> Optional[str]:
    m = _HEX32.search(url or "")
    return m.group(1) if m else None


def _props(item: Item) -> dict:
    p = {
        "Task occurrence": {"title": [{"text": {"content": item.title[:2000]}}]},
        "Status": {"select": {"name": STATUS_TO_NOTION.get(item.status, "Due")}},
        "Property": {"select": {"name": PROP_TO_NOTION.get(item.prop, "Both")}},
        "Created by Ruby": {"checkbox": True},
        "Due date": {"date": {"start": item.due.isoformat()} if item.due else None},
    }
    if item.notes:
        p["Notes"] = {"rich_text": [{"text": {"content": item.notes[:2000]}}]}
    if item.source:
        p["Source"] = {"url": item.source}
    if item.status == "Done":
        p["Completed at"] = {"date": {"start": datetime.now().astimezone().isoformat()}}
    return p


class NotionMirror:
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_env(cls) -> Optional["NotionMirror"]:
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            return None
        from notion_client import Client
        return cls(Client(auth=token))

    # ---- writes (raise on failure so the store queues a retry)
    def upsert(self, item: Item) -> Optional[str]:
        pid = page_id_from_url(item.notion_url)
        if pid:
            r = self.client.pages.update(page_id=pid, properties=_props(item))
        else:
            r = self.client.pages.create(
                parent={"type": "data_source_id", "data_source_id": TASK_TRACKER},
                properties=_props(item))
        return r.get("url")

    # ---- generic row operations used by ruby.handlers
    def create_row(self, ds_key: str, props: dict, children: Optional[list] = None) -> dict:
        kw = {"parent": {"type": "data_source_id", "data_source_id": IDS["data_sources"][ds_key]}, "properties": props}
        if children:
            kw["children"] = children
        r = self.client.pages.create(**kw)
        return {"id": r.get("id"), "url": r.get("url")}

    def find_by_title(self, ds_key: str, title_prop: str, contains: str) -> Optional[dict]:
        r = self.client.data_sources.query(
            data_source_id=IDS["data_sources"][ds_key], page_size=1,
            filter={"property": title_prop, "title": {"contains": contains}},
            sorts=[{"timestamp": "created_time", "direction": "descending"}])
        return r["results"][0] if r["results"] else None

    def update_page(self, page_id: str, props: dict) -> Optional[str]:
        return self.client.pages.update(page_id=page_id, properties=props).get("url")

    def archive_page(self, page_id: str) -> None:
        self.client.pages.update(page_id=page_id, archived=True)

    def preflight(self) -> list[str]:
        """Compare every column Ruby writes against the live workspace. Returns human-readable problems."""
        from .handlers import SCHEMAS
        problems = []
        for key, cols in SCHEMAS.items():
            try:
                live = self.client.data_sources.retrieve(data_source_id=IDS["data_sources"][key])["properties"]
            except Exception as e:
                problems.append(f"{key}: cannot read database ({type(e).__name__}); is it shared with the integration?")
                continue
            for name, typ in cols.items():
                if name not in live:
                    problems.append(f"{key}: missing column '{name}'")
                elif live[name]["type"] != typ:
                    problems.append(f"{key}: column '{name}' is {live[name]['type']}, expected {typ}")
        return problems

    def set_permission_to_enter(self, unit: str, value: str) -> Optional[str]:
        """Set Permission to enter (Yes / No) on the newest Move-Outs row for this unit.
        Returns the row's URL, or None if the unit has no Move-Outs row."""
        r = self.client.data_sources.query(
            data_source_id=IDS["data_sources"]["move_outs"], page_size=1,
            filter={"property": "Unit #", "rich_text": {"equals": unit}},
            sorts=[{"timestamp": "created_time", "direction": "descending"}])
        if not r["results"]:
            return None
        row = self.client.pages.update(page_id=r["results"][0]["id"],
                                       properties={"Permission to enter": {"select": {"name": value}}})
        return row.get("url") or r["results"][0].get("url") or "saved"

    def archive(self, item: Item) -> None:
        pid = page_id_from_url(item.notion_url)
        if pid:
            self.client.pages.update(page_id=pid, archived=True)

    # ---- reads
    def pull_open(self) -> list[Item]:
        """Open Task Tracker rows as Items (used to rebuild state on a fresh volume)."""
        out, cursor = [], None
        while True:
            kw = {"data_source_id": TASK_TRACKER, "page_size": 100,
                  "filter": {"or": [{"property": "Status", "select": {"equals": s}} for s in OPEN_NOTION]}}
            if cursor:
                kw["start_cursor"] = cursor
            r = self.client.data_sources.query(**kw)
            for page in r["results"]:
                out.append(_item_from_page(page))
            if not r.get("has_more"):
                return out
            cursor = r["next_cursor"]

    def read_brain(self) -> str:
        """Plain text of Ruby's Brain page (rules, schedule, voice guide)."""
        lines, cursor = [], None
        while True:
            kw = {"block_id": IDS["pages"]["brain"], "page_size": 100}
            if cursor:
                kw["start_cursor"] = cursor
            r = self.client.blocks.children.list(**kw)
            for b in r["results"]:
                rich = (b.get(b["type"]) or {}).get("rich_text") or []
                text = "".join(t.get("plain_text", "") for t in rich)
                if text:
                    lines.append(text)
            if not r.get("has_more"):
                return "\n".join(lines)
            cursor = r["next_cursor"]


def _item_from_page(page: dict) -> Item:
    pr = page["properties"]
    title = "".join(t.get("plain_text", "") for t in pr["Task occurrence"]["title"])
    due = (pr.get("Due date", {}).get("date") or {}).get("start")
    prop = NOTION_TO_PROP.get(((pr.get("Property") or {}).get("select") or {}).get("name"), "Both")
    return Item(id=page["id"].replace("-", "")[:10], title=title, prop=prop,
                due=datetime.fromisoformat(due) if due else None, status="Due",
                notion_url=page.get("url"), source=pr.get("Source", {}).get("url"))
