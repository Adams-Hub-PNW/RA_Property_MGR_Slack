"""Intent router. Every DM -> Claude (forced tool call) -> a normalized dict. Ruby confirms before saving.

Local `quick_intent` handles the phrases that must always work even if Claude is down.
`route` never raises: on any failure it returns an `unknown` result that asks Roxy what to do.
"""
from __future__ import annotations
import logging, re
from datetime import datetime
from typing import Optional
from .config import MODEL, OVERWHELM_PHRASES, TZ

log = logging.getLogger("ruby.intent")

INTENTS = ["todo", "make_ready", "email_triage", "template_request", "renewal_call", "daily_note",
           "task_done", "move_out", "move_in", "supply", "calendar_event", "recurring_task",
           "work_order", "lead", "reminder", "query", "brain_dump", "overwhelmed", "chitchat", "unknown"]
PROPS = ("P88", "HG", "Both")
WORK_NEEDED = ["Paint", "Carpet", "Cleaning", "Resurfacing", "Repairs", "Appliances", "Junk Haul",
               "Pest", "Flooring", "Blinds", "Other"]
CADENCES = ["Daily", "Weekly", "Monthly", "Quarterly", "Annual", "Per Event"]
TOPICS = ["Leasing", "Maintenance", "Vendor", "Collections", "Corporate", "Reporting", "Resident",
          "Compliance", "Other"]
URGENCY = ["Urgent", "Today", "This Week", "FYI"]
RENEWAL_STATUS = ["Need to Call", "Contacted", "No Response", "Counter Offer", "Renewed/Signed", "Giving Notice"]

SYSTEM = """You are Ruby, Roxy's calm, warm, matter-of-fact assistant. Roxy is the property manager of two
apartment communities: Peak 88 (P88) and Heritage Grove (HG), in Renton WA. She writes messy voice-to-text.
Classify her message by calling the `classify` tool. Never answer in prose.

Rules:
- intent: pick the single best fit. A long pasted email (From/Subject/Hi/Dear, a signature) is `email_triage`.
  "done with X" / "finished X" is `task_done` (title = X). Tours, prospects, small observations are `daily_note`.
  A vendor/unit that needs work ("C214 is vacant, needs paint and carpet") is `make_ready`.
  A call, text or visit with a resident about renewing is `renewal_call`. Need-to-buy items are `supply`.
  Asking for a saved message ("applicant hasn't finished Two Dots") is `template_request`.
  Appointments with a date/time are `calendar_event`. "Every Monday ..." style is `recurring_task`.
- prop: P88, HG or Both. Infer from names, unit letters or context only when clear; otherwise null and ask ONE question.
- Units look like a letter + 3 digits (C214, B105). Residents: first name only.
- Privacy: titles carry unit # and first name only. Never put dollar amounts, balances, phone numbers or
  emails in `title`; put terms or amounts in `details`. For emails, summarize in 2-3 lines; do not copy the body.
- Ruby only drafts; never claim anything was sent, posted or scheduled.
- due: ISO 8601 local datetime (Pacific) resolved from the current time given in the message, else null.
- confidence 0-1. If below 0.6 or a key fact is missing, set `question` (one short question) and 2-3 `options`.
- `assumed`: one short phrase for anything you guessed. No lectures, no filler."""

TOOL = {
    "name": "classify",
    "description": "Return the structured reading of Roxy's message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": INTENTS},
            "title": {"type": "string", "description": "Short imperative title, max 90 chars, no dollar amounts"},
            "prop": {"type": ["string", "null"], "enum": [*PROPS, None]},
            "due": {"type": ["string", "null"]},
            "urgent": {"type": "boolean"},
            "confidence": {"type": "number"},
            "assumed": {"type": ["string", "null"]},
            "question": {"type": ["string", "null"]},
            "options": {"type": "array", "items": {"type": "string"}},
            "details": {"type": ["string", "null"], "description": "Specifics kept out of the title"},
            "unit": {"type": ["string", "null"]},
            "resident_first_name": {"type": ["string", "null"]},
            "vendor": {"type": ["string", "null"]},
            "work_needed": {"type": "array", "items": {"type": "string", "enum": WORK_NEEDED}},
            "supply_items": {"type": "array", "items": {"type": "string"}},
            "renewal_status": {"type": ["string", "null"], "enum": [*RENEWAL_STATUS, None]},
            "recurrence": {"type": ["object", "null"], "properties": {
                "cadence": {"type": "string", "enum": CADENCES}, "due_rule": {"type": "string"}}},
            "email": {"type": ["object", "null"], "properties": {
                "sender": {"type": "string"}, "subject": {"type": "string"},
                "topic": {"type": "string", "enum": TOPICS}, "urgency": {"type": "string", "enum": URGENCY},
                "summary": {"type": "string"}, "action_items": {"type": "array", "items": {"type": "string"}}}},
        },
        "required": ["intent", "title", "confidence"],
    },
}

_UNIT = re.compile(r"^[A-Za-z]\s?-?\d{3}$")
_DOLLARS = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")


def quick_intent(text: str) -> Optional[dict]:
    """Cheap local routing for the phrases that must always work, even if Claude is down."""
    t = text.lower().strip()
    if any(p in t for p in OVERWHELM_PHRASES) and len(t) < 40:
        return {"intent": "overwhelmed", "confidence": 1.0}
    if t in ("dump", "brain dump"):
        return {"intent": "brain_dump", "confidence": 1.0}
    if t in ("what's left today?", "whats left today", "what's left today", "top 3", "top3"):
        return {"intent": "query", "title": "top3", "confidence": 1.0}
    if t in ("show my week", "week"):
        return {"intent": "query", "title": "week", "confidence": 1.0}
    m = re.match(r"quiet (?:for )?(\d+)", t)
    if m:
        return {"intent": "quiet", "minutes": int(m.group(1)), "confidence": 1.0}
    if "quiet for an hour" in t:
        return {"intent": "quiet", "minutes": 60, "confidence": 1.0}
    return None


def normalize(out: dict) -> dict:
    """Clamp model output to what the rest of Ruby can trust."""
    out = dict(out)
    if out.get("intent") not in INTENTS:
        out["intent"] = "unknown"
    try:
        out["confidence"] = min(1.0, max(0.0, float(out.get("confidence", 0.5))))
    except (TypeError, ValueError):
        out["confidence"] = 0.5
    if out.get("prop") not in PROPS:
        out["prop"] = None
    title = (out.get("title") or "").strip()
    if _DOLLARS.search(title):                      # amounts never live in titles
        out["details"] = " ".join(filter(None, [out.get("details"), " ".join(_DOLLARS.findall(title))]))
        title = re.sub(r"\s{2,}", " ", _DOLLARS.sub("", title)).strip(" ,-:")
    out["title"] = title[:120]
    unit = out.get("unit")
    out["unit"] = re.sub(r"[\s-]", "", unit).upper() if unit and _UNIT.match(unit.strip()) else None
    out["work_needed"] = [w for w in (out.get("work_needed") or []) if w in WORK_NEEDED]
    out["options"] = [str(o) for o in (out.get("options") or [])][:4]
    if out.get("due"):
        try:
            datetime.fromisoformat(out["due"])
        except ValueError:
            out["due"] = None
    return out


def _unknown(question: str = "I couldn't read that one. Want to save it as a to-do?") -> dict:
    return {"intent": "unknown", "confidence": 0.0, "question": question,
            "options": ["Save as to-do", "Cancel"]}


def route(text: str, brain: str = "", client=None, recent: Optional[list[str]] = None,
          now: Optional[datetime] = None) -> dict:
    q = quick_intent(text)
    if q:
        return q
    if client is None:
        return {"intent": "todo", "title": text.strip()[:120], "prop": None, "confidence": 0.3,
                "question": "Which property is this for?", "options": ["Peak 88", "Heritage Grove", "Both"]}
    now = now or datetime.now(TZ)
    system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    if brain:
        system.append({"type": "text", "text": "Ruby's Brain (Roxy's rules and facts):\n" + brain,
                       "cache_control": {"type": "ephemeral"}})
    ctx = f"Current time: {now.strftime('%A %Y-%m-%d %H:%M')} {getattr(now.tzinfo, 'key', 'America/Los_Angeles')}"
    if recent:
        ctx += "\nRoxy's previous messages (oldest first), for context only:\n- " + "\n- ".join(r[:200] for r in recent)
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=900, system=system, tools=[TOOL],
            tool_choice={"type": "tool", "name": "classify"},
            messages=[{"role": "user", "content": f"{ctx}\n\nMessage:\n{text}"}])
        block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
        return normalize(block.input)
    except Exception:
        log.exception("intent routing failed")
        return _unknown()
