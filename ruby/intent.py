"""Intent router. Every DM -> Claude -> {intent, fields, confidence, question?}. Ruby confirms before saving."""
from __future__ import annotations
import json, logging, re
from typing import Optional
from .config import MODEL, OVERWHELM_PHRASES

log = logging.getLogger("ruby.intent")

INTENTS = ["todo", "make_ready", "email_triage", "template_request", "renewal_call", "daily_note",
           "task_done", "move_out", "move_in", "supply", "calendar_event", "recurring_task",
           "reminder", "query", "brain_dump", "overwhelmed", "chitchat", "unknown"]

SYSTEM = """You are Ruby, Roxy's calm, warm, matter-of-fact assistant for two apartment properties
(P88 = Peak 88, HG = Heritage Grove). Roxy writes messy voice-to-text. Classify her message.
Reply with ONLY JSON: {"intent": one of %s, "title": short imperative, "prop": "P88"|"HG"|"Both"|null,
"due": ISO datetime|null, "urgent": bool, "confidence": 0-1, "assumed": string|null,
"question": string|null, "options": [string]}.
If unsure which property or key fact, set a single question with button options. No lectures.
Resident rule: unit # and first name only, never dollar balances in titles.""" % INTENTS


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


def route(text: str, brain: str = "", client=None) -> dict:
    q = quick_intent(text)
    if q:
        return q
    if client is None:
        return {"intent": "todo", "title": text.strip()[:120], "prop": None, "confidence": 0.3,
                "question": "Which property is this for?", "options": ["Peak 88", "Heritage Grove", "Both"]}
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=500,
            system=SYSTEM + ("\n\nRuby's Brain:\n" + brain if brain else ""),
            messages=[{"role": "user", "content": text}])
        raw = resp.content[0].text
        raw = raw[raw.index("{"): raw.rindex("}") + 1]
        out = json.loads(raw)
        if out.get("intent") not in INTENTS:
            out["intent"] = "unknown"
        return out
    except Exception:
        log.exception("intent routing failed")
        return {"intent": "unknown", "confidence": 0.0,
                "question": "I couldn't read that one. Want to save it as a to-do?", "options": ["Save as to-do", "Cancel"]}
