"""Intent -> Notion writers. Each handler turns one approved request into rows in the right database(s).

Property names and types live in SCHEMAS, which is also what `NotionMirror.preflight()` checks against the
live workspace at startup, so a renamed column shows up in the logs instead of as a silent failure.
Only unit # + first name go into titles. Nothing here sends, posts or schedules anything outside Notion.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

log = logging.getLogger("ruby.handlers")

PROP_NAME = {"P88": "Peak 88", "HG": "Heritage Grove", "Both": "Both"}

# ds_key -> {property name: notion type}. Columns every Ruby write may set are in COMMON.
COMMON = {"Created by Ruby": "checkbox", "Source": "url", "Notes": "rich_text"}
SCHEMAS: dict[str, dict[str, str]] = {
    "daily_notes": {"Note": "title", "Date": "date", "Type": "select", "Note text": "rich_text",
                    "Include in DAR": "checkbox", "Property": "select"},
    "supply_list": {"Item": "title", "For": "select", "Qty": "number", "Status": "select", "Store": "rich_text",
                    "Property": "select"},
    "email_triage": {"Subject": "title", "Sender name": "rich_text", "Received date": "date", "Topic": "select",
                     "Urgency": "select", "Status": "select", "Summary": "rich_text", "Property": "select"},
    "renewals": {"Renewal": "title", "Resident first name": "rich_text", "Status": "select",
                 "Counter offer details": "rich_text", "Next action": "rich_text", "Property": "select"},
    "renewal_call_log": {"Call": "title", "Date/time": "date", "Renewal": "relation", "Method": "select",
                         "Outcome": "select", "How it went": "rich_text", "Property": "select"},
    "make_ready": {"Unit": "title", "Property": "select", "Status": "status", "Work needed": "multi_select",
                   "Move-out date": "date"},
    "move_outs": {"Move-out": "title", "Unit #": "rich_text", "Resident first name": "rich_text",
                  "Move-out date": "date", "Notice given date": "date", "Permission to enter": "select",
                  "Added to Make Ready board": "checkbox", "Property": "select"},
    "move_ins": {"Move-in": "title", "Resident first name": "rich_text", "Move-in date": "date",
                 "Property": "select"},
    "work_orders": {"WO #": "title", "Issue": "rich_text", "Status": "select", "Property": "select"},
    "recurring_tasks": {"Task": "title", "Cadence": "select", "Due rule": "rich_text", "Property": "select",
                        "Active": "checkbox"},
    "leads": {"Name or handle": "title", "Lead source": "select", "Interest": "rich_text", "Status": "select",
              "Property": "select"},
    "checklists": {"Checklist": "title", "Due date": "date", "Status": "select", "Property": "select"},
}
for _s in SCHEMAS.values():
    _s.update(COMMON)
# Databases whose Property select has no "Both" option.
NO_BOTH = {"renewals", "renewal_call_log", "make_ready", "move_outs", "move_ins", "work_orders"}

TITLE_PROP = {k: next(n for n, t in v.items() if t == "title") for k, v in SCHEMAS.items()}


def _rt(text: str) -> list:
    return [{"type": "text", "text": {"content": str(text)[:2000]}}]


def build(ds_key: str, values: dict) -> dict:
    """{name: python value} -> Notion API properties, validated against SCHEMAS. None/'' values are skipped."""
    schema, props = SCHEMAS[ds_key], {}
    for name, v in values.items():
        if v is None or v == "" or v == []:
            continue
        t = schema[name]                      # KeyError = a typo in a handler, caught by tests
        props[name] = {
            "title": lambda: {"title": _rt(v)},
            "rich_text": lambda: {"rich_text": _rt(v)},
            "select": lambda: {"select": {"name": v}},
            "status": lambda: {"status": {"name": v}},
            "multi_select": lambda: {"multi_select": [{"name": x} for x in v]},
            "date": lambda: {"date": {"start": v}},
            "checkbox": lambda: {"checkbox": bool(v)},
            "number": lambda: {"number": v},
            "url": lambda: {"url": v},
            "relation": lambda: {"relation": [{"id": x} for x in v]},
        }[t]()
    return props


def _prop(ds_key: str, out: dict) -> Optional[str]:
    p = PROP_NAME.get(out.get("prop"))
    return None if p == "Both" and ds_key in NO_BOTH else p


@dataclass
class Written:
    label: str                 # human label, e.g. "Daily Notes"
    url: Optional[str] = None  # None = failed
    page_id: Optional[str] = None
    error: bool = False


def _create(m, ds_key: str, label: str, values: dict, children: Optional[list] = None, out=None) -> Written:
    values = {**values, "Created by Ruby": True}
    if out and out.get("source_url"):
        values["Source"] = out["source_url"]
    try:
        r = m.create_row(ds_key, build(ds_key, values), children)
    except Exception:
        log.exception("notion write failed: %s", label)
        return Written(label, error=True)
    if r is None:                       # NullMirror: no Notion configured
        return Written(label, error=True)
    return Written(label, r.get("url"), r.get("id"))


def _unit_name(out: dict) -> str:
    return " ".join(x for x in (out.get("unit"), out.get("resident_first_name")) if x)


# ---------------------------------------------------------------- handlers
def daily_note(m, out):
    return [_create(m, "daily_notes", "Daily Notes", {
        "Note": out.get("title") or "Note", "Date": datetime.now().astimezone().isoformat(),
        "Type": out.get("note_type") or "Other", "Note text": out.get("details") or out.get("title"),
        "Include in DAR": True, "Property": _prop("daily_notes", out)}, out=out)]


def supply(m, out):
    items = out.get("supply_items") or [out.get("title")]
    return [_create(m, "supply_list", f"Supply List: {i}", {
        "Item": i, "For": out.get("supply_for"), "Qty": 1, "Status": "Needed", "Store": out.get("store"),
        "Property": _prop("supply_list", out)}, out=out) for i in items if i]


def email_triage(m, out):
    e = out.get("email") or {}
    return [_create(m, "email_triage", "Email Triage", {
        "Subject": e.get("subject") or out.get("title"), "Sender name": e.get("sender"),
        "Received date": datetime.now().astimezone().date().isoformat(), "Topic": e.get("topic"),
        "Urgency": e.get("urgency") or ("Urgent" if out.get("urgent") else None), "Status": "Open",
        "Summary": e.get("summary") or out.get("details"), "Property": _prop("email_triage", out)}, out=out)]


def renewal_call(m, out):
    unit = out.get("unit") or ""
    res = []
    row = None
    try:
        row = m.find_by_title("renewals", "Renewal", unit) if unit else None
    except Exception:
        log.exception("renewal lookup failed")
    if row is None:
        w = _create(m, "renewals", "Renewals", {
            "Renewal": f"{_unit_name(out) or out.get('title')} renewal", "Resident first name": out.get("resident_first_name"),
            "Status": out.get("renewal_status") or "Contacted", "Counter offer details":
                out.get("details") if out.get("renewal_status") == "Counter Offer" else None,
            "Next action": None, "Property": _prop("renewals", out)}, out=out)
        res.append(w)
        rid = w.page_id
    else:
        rid = row["id"]
        upd = {k: v for k, v in {"Status": out.get("renewal_status"),
               "Counter offer details": out.get("details") if out.get("renewal_status") == "Counter Offer" else None}.items() if v}
        if upd:
            try:
                url = m.update_page(rid, build("renewals", upd))
                res.append(Written("Renewals (updated)", url, rid))
            except Exception:
                log.exception("renewal update failed")
                res.append(Written("Renewals (updated)", error=True))
        else:
            res.append(Written("Renewals (found)", row.get("url"), rid))
    res.append(_create(m, "renewal_call_log", "Renewal Call Log", {
        "Call": f"{_unit_name(out) or out.get('title')} {out.get('contact_method') or 'call'}",
        "Date/time": datetime.now().astimezone().isoformat(), "Renewal": [rid] if rid else None,
        "Method": out.get("contact_method") or "Call", "Outcome": out.get("call_outcome"),
        "How it went": out.get("details") or out.get("title"), "Property": _prop("renewal_call_log", out)}, out=out))
    return res


def make_ready(m, out):
    return [_create(m, "make_ready", "Make Ready", {
        "Unit": out.get("unit") or out.get("title"), "Property": _prop("make_ready", out),
        "Status": "Vacant - Not Started", "Work needed": out.get("work_needed"),
        "Move-out date": out.get("move_out_date")}, out=out)]


def move_out(m, out):
    """Move-Outs checklist row (also holds the pre-move-out steps) + the Make Ready card, per the PRD."""
    res = [_create(m, "move_outs", "Move-Outs checklist", {
        "Move-out": f"{_unit_name(out) or out.get('title')} move-out", "Unit #": out.get("unit"),
        "Resident first name": out.get("resident_first_name"), "Move-out date": out.get("move_out_date"),
        "Notice given date": out.get("notice_date"), "Permission to enter": "Not asked yet",
        "Added to Make Ready board": out.get("intent") == "move_out", "Property": _prop("move_outs", out)}, out=out)]
    if out.get("intent") == "move_out":
        res += make_ready(m, out)
    return res


def move_in(m, out):
    return [_create(m, "move_ins", "Move-Ins checklist", {
        "Move-in": f"{_unit_name(out) or out.get('title')} move-in", "Resident first name": out.get("resident_first_name"),
        "Move-in date": out.get("move_in_date"), "Property": _prop("move_ins", out)}, out=out)]


def work_order(m, out):
    return [_create(m, "work_orders", "Work Orders", {
        "WO #": out.get("wo_number") or out.get("title"), "Issue": out.get("issue") or out.get("details"),
        "Status": "Needs Scheduling", "Property": _prop("work_orders", out)}, out=out)]


def recurring_task(m, out):
    r = out.get("recurrence") or {}
    return [_create(m, "recurring_tasks", "Recurring Tasks", {
        "Task": out.get("title"), "Cadence": r.get("cadence"), "Due rule": r.get("due_rule"),
        "Property": _prop("recurring_tasks", out), "Active": True}, out=out)]


def lead(m, out):
    return [_create(m, "leads", "Leads", {
        "Name or handle": out.get("title"), "Lead source": out.get("lead_source") or "Other",
        "Interest": out.get("details"), "Status": "New", "Property": _prop("leads", out)}, out=out)]


def checklist(m, out):
    kids = [{"object": "block", "type": "to_do",
             "to_do": {"rich_text": _rt(i), "checked": False}} for i in out.get("checklist_items") or []]
    return [_create(m, "checklists", "Checklists", {
        "Checklist": out.get("title"), "Due date": (out.get("due") or "")[:10] or None, "Status": "Open",
        "Property": _prop("checklists", out)}, children=kids, out=out)]


HANDLERS: dict[str, Callable] = {
    "daily_note": daily_note, "supply": supply, "email_triage": email_triage, "renewal_call": renewal_call,
    "make_ready": make_ready, "move_out": move_out, "pre_move_out": move_out, "move_in": move_in,
    "work_order": work_order, "recurring_task": recurring_task, "lead": lead, "checklist": checklist,
}
# Intents that also become a reminder in the Task Tracker (and so can reach the Top 3). Everything
# else lives only in its own database. Unlisted/unknown intents fall back to a plain task.
TASK_TOO = {"pre_move_out", "move_out", "move_in", "make_ready", "work_order", "checklist"}
# Where Ruby posts the quiet update for each intent.
CHANNEL = {"make_ready": "make-ready-vendors", "email_triage": "inbox-emails", "renewal_call": "residents",
           "move_out": "residents", "pre_move_out": "inspections", "move_in": "residents", "work_order": "residents",
           "daily_note": "dar-notes", "supply": "supplies", "calendar_event": "make-ready-vendors",
           "lead": "residents", "task_done": "wins"}


def save(mirror, out: dict) -> list[Written]:
    h = HANDLERS.get(out.get("intent"))
    return h(mirror, out) if h else []
