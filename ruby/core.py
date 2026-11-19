"""Ruby's behavior, independent of Bolt wiring so it can be tested with a fake Slack client."""
from __future__ import annotations
import logging, re, uuid, time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from . import messages as M, quiet, followup, top3 as t3
from .config import TZ, ROXY_USER_ID, OVERWHELM_PAUSE_MIN, REACTIONS, EMOJI_KEY
from .intent import route, PRE_MOVE_OUT_CHECKLIST
from .store import JsonStore

log = logging.getLogger("ruby.core")

CHANNEL_FOR_INTENT = {"make_ready": "make-ready-vendors", "email_triage": "inbox-emails",
                      "renewal_call": "residents", "move_out": "residents", "pre_move_out": "residents", "move_in": "residents",
                      "daily_note": "dar-notes", "task_done": "wins", "supply": "supplies",
                      "calendar_event": "make-ready-vendors"}


class Ruby:
    def __init__(self, slack, store: JsonStore, llm=None, roxy_id: str = ROXY_USER_ID):
        self.slack, self.store, self.llm, self.roxy_id = slack, store, llm, roxy_id
        self.pending: dict[str, dict] = {}       # confirmation token -> proposal
        self._dm_channel: Optional[str] = store.state.get("last_dm_channel")
        self._channel_ids: dict[str, str] = {}
        self.recent: deque = deque(maxlen=3)     # Roxy's last few messages, context only
        self._brain: tuple[float, str] = (0.0, "")

    # ------------------------------------------------------------ plumbing
    def dm_channel(self) -> str:
        if not self._dm_channel:
            r = self.slack.conversations_open(users=self.roxy_id)
            self._dm_channel = r["channel"]["id"]
            self.store.state["last_dm_channel"] = self._dm_channel
            self.store.save()
        return self._dm_channel

    def use_dm_channel(self, channel: str):
        if channel and channel != self._dm_channel:
            self._dm_channel = channel
            self.store.state["last_dm_channel"] = channel
            self.store.save()

    def channel_id(self, name: str) -> Optional[str]:
        if name not in self._channel_ids:
            cursor = None
            while True:
                r = self.slack.conversations_list(types="public_channel", limit=200, cursor=cursor)
                for c in r["channels"]:
                    self._channel_ids[c["name"]] = c["id"]
                cursor = (r.get("response_metadata") or {}).get("next_cursor")
                if not cursor:
                    break
        return self._channel_ids.get(name)

    def brain(self, ttl: int = 900) -> str:
        """Ruby's Brain page from Notion, cached; empty if Notion is unreachable."""
        ts, text = self._brain
        if time.time() - ts > ttl:
            try:
                text = self.store.mirror.read_brain()
            except Exception:
                log.exception("could not read Ruby's Brain; using last copy")
            self._brain = (time.time(), text)
        return text

    def say(self, text: str, blocks: Optional[list] = None, thread_ts: Optional[str] = None):
        """Reply in the DM. Replies to Roxy always go out, any hour."""
        return self.slack.chat_postMessage(channel=self.dm_channel(), text=text,
                                           blocks=blocks or None, thread_ts=thread_ts)

    def initiate(self, text: str, blocks: Optional[list] = None, urgent_kind: Optional[str] = None,
                 now: Optional[datetime] = None) -> bool:
        """Ruby-initiated DM. Passes the quiet-hours gate or is dropped (caller may retry later)."""
        if not quiet.may_send(urgent_kind, self.store.pause_until(), now):
            log.info("gated: %s", text[:40])
            return False
        self.say(text, blocks)
        return True

    def post_channel(self, name: str, text: str, item=None, blocks: Optional[list] = None):
        """One message per item, edited in place when it already exists."""
        cid = self.channel_id(name)
        if not cid:
            log.warning("channel #%s missing; run setup_workspace", name)
            return None
        if item is not None and item.slack_ts and item.channel == cid:
            self.slack.chat_update(channel=cid, ts=item.slack_ts, text=text, blocks=blocks or None)
            return item.slack_ts
        r = self.slack.chat_postMessage(channel=cid, text=text, blocks=blocks or None)
        if item is not None:
            self.store.update(item.id, slack_ts=r["ts"], channel=cid)
        return r["ts"]

    def log_audit(self, line: str):
        try:
            self.post_channel("ruby-log", line)
        except Exception:
            log.exception("audit log failed")

    # ------------------------------------------------------------ incoming DM
    def handle_dm(self, text: str):
        out = route(text, brain=self.brain(), client=self.llm, recent=list(self.recent))
        self.recent.append(text[:200])
        intent = out.get("intent")

        if intent == "overwhelmed":
            return self.overwhelm()
        if intent == "brain_dump":
            return self.say("Ready. Send everything in one go, in any order. Voice or text.")
        if intent == "quiet":
            return self.quiet(out.get("minutes", 60))
        if intent == "query":
            return self.send_week() if out.get("title") == "week" else self.send_top3()
        if intent == "task_done":
            item = self.match_open_item(out.get("title") or text)
            if item:
                return self.say(f"{self.act(item.id, 'done')} [{item.prop}] {item.title}")
            return self.say("I couldn't find that on your list. Which one did you finish?")
        if intent == "chitchat":
            return self.say(out.get("title") or "I'm here.")
        if out.get("question") and out.get("confidence", 1) < 0.6:
            token = uuid.uuid4().hex[:8]
            self.pending[token] = {"kind": "clarify", "text": text, "out": out}
            t, b = M.question(out["question"], out.get("options") or ["Save as to-do", "Cancel"], token)
            return self.say(t, b)
        return self.propose(out, text)

    def match_open_item(self, phrase: str):
        """Best open item whose title shares the most words with `phrase` (needs at least one)."""
        words = {w for w in re.findall(r"[a-z0-9]+", phrase.lower()) if len(w) > 2}
        best, score = None, 0
        for it in self.store.open_items():
            n = len(words & set(re.findall(r"[a-z0-9]+", it.title.lower())))
            if n > score:
                best, score = it, n
        return best

    def propose(self, out: dict, original: str):
        token = uuid.uuid4().hex[:8]
        chan = CHANNEL_FOR_INTENT.get(out.get("intent"), None)
        prop = out.get("prop") or "Both"
        title = out.get("title") or original.strip()[:120]
        summary = f"I'll add this" + (f" to #{chan}" if chan else " to your list") + f":\n[{prop}] {title}"
        facts = [f"{k}: {v}" for k, v in (
            ("Unit", out.get("unit")), ("Resident", out.get("resident_first_name")), ("Vendor", out.get("vendor")),
            ("Work", ", ".join(out.get("work_needed") or [])), ("Items", ", ".join(out.get("supply_items") or [])),
            ("Status", out.get("renewal_status")), ("Due", out.get("due")),
            ("Repeats", " ".join((out.get("recurrence") or {}).values())),
            ("Email", (out.get("email") or {}).get("summary")), ("Details", out.get("details"))) if v]
        if facts:
            summary += "\n" + "\n".join(facts)
        if out.get("intent") == "pre_move_out":
            summary += "\nChecklist:\n" + "\n".join("☐ " + c for c in PRE_MOVE_OUT_CHECKLIST)
        if out.get("assumed"):
            summary += f"\nI assumed: {out['assumed']}"
        self.pending[token] = {"kind": "create", "out": out, "title": title, "prop": prop, "chan": chan}
        t, b = M.confirmation(summary, token)
        return self.say(t, b)

    # ------------------------------------------------------------ confirmations
    def approve(self, token: str):
        p = self.pending.pop(token, None)
        if not p:
            return self.say("That one already went through or expired.")
        if p["kind"] == "clarify":
            return self.handle_dm(p["text"])
        out = p["out"]
        due = None
        if out.get("due"):
            try:
                due = datetime.fromisoformat(out["due"])
            except ValueError:
                pass
        urgent = out.get("urgent")
        item = self.store.add(title=p["title"], prop=p["prop"], due=due,
                              urgent_kind="marked_urgent" if urgent else None, source="slack_dm",
                              notes=out.get("details") or (out.get("email") or {}).get("summary"),
                              intent=out.get("intent"))
        extra = ""
        if out.get("intent") == "pre_move_out":
            self.store.update(item.id, hard_deadline=True)
            try:
                self.store.mirror.create_pre_move_out({**out, "prop": item.prop}, source=None)
                extra = "\nChecklist added to Pre-Move-Outs in Notion."
            except Exception:
                log.exception("pre-move-out checklist not saved to Notion")
                extra = "\nThe Notion checklist didn't save yet. The task is saved."
        if p["chan"]:
            self.post_channel(p["chan"], f"[{item.prop}] {item.title}", item)
        self.log_audit(f"Created: [{item.prop}] {item.title}")
        undo = self.store.register_undo([item.id])
        t, b = M.filed(f"Saved. [{item.prop}] {item.title}{extra}", undo)
        return self.say(t, b)

    def cancel(self, token: str):
        self.pending.pop(token, None)
        return self.say("Cancelled. Nothing saved.")

    def clarify_answer(self, token: str, answer: str):
        p = self.pending.pop(token, None)
        if not p:
            return self.say("That question already closed.")
        if answer in ("Cancel",):
            return self.say("Okay, left it alone.")
        out = dict(p["out"])
        prop_map = {"Peak 88": "P88", "Heritage Grove": "HG", "Both": "Both"}
        if answer in prop_map:
            out["prop"] = prop_map[answer]
        out.pop("question", None)
        return self.propose(out, p["text"])

    def undo(self, uid: str):
        ok = self.store.do_undo(uid)
        return self.say("Undone." if ok else "I can't undo that one anymore (24 hour window).")

    # ------------------------------------------------------------ item actions (buttons + emoji)
    def act(self, item_id: str, action: str, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(TZ)
        item = self.store.items.get(item_id)
        if not item:
            return "Couldn't find that item."
        tomorrow = (now + timedelta(days=1 if now.weekday() < 4 else 7 - now.weekday())).replace(
            hour=7, minute=0, second=0, microsecond=0)
        upd: dict
        msg: str
        if action == "done":
            upd, msg = {"status": "Done", "starred": False}, "Done."
        elif action == "tomorrow":
            upd, msg = {"snoozed_until": tomorrow, "due": tomorrow}, "Moved to tomorrow's 7:00 list."
        elif action == "later":
            upd, msg = {}, "I'll bring it back at the next check-in."
        elif action == "pin":
            upd, msg = {"pinned": True}, "Pinned to your next Top 3."
        elif action == "urgent":
            upd, msg = {"urgent_kind": "marked_urgent"}, "Marked urgent."
        elif action == "skip":
            upd, msg = {"status": "Skipped"}, "Skipped. Not counted as missed."
        elif action == "in_progress":
            upd, msg = {"status": "In Progress"}, "In progress. I'll leave it until the next check-in."
        elif action == "next_week":
            nxt = (now + timedelta(days=7 - now.weekday())).replace(hour=7, minute=0, second=0, microsecond=0)
            upd, msg = {"snoozed_until": nxt, "due": nxt}, "Moved to next Monday."
        elif action == "notion":
            return item.notion_url or "Notion link not available yet."
        else:
            return "Not sure what to do with that."
        self.store.update(item_id, **upd)
        if action == "done":
            self.post_channel("wins", f"Done: [{item.prop}] {item.title}")
        if item.channel and item.slack_ts:
            label = {"done": "✓ Done", "skip": "Skipped"}.get(action)
            if label:
                try:
                    self.slack.chat_update(channel=item.channel, ts=item.slack_ts,
                                           text=f"{label} · [{item.prop}] {item.title}")
                except Exception:
                    log.exception("edit-in-place failed")
        self.log_audit(f"{action}: [{item.prop}] {item.title}")
        return msg

    def on_reaction(self, emoji: str, message_text: str):
        """React on a Ruby message. Match by item title shown in the text."""
        action = REACTIONS.get(emoji)
        if not action:
            return
        for item in self.store.items.values():
            if item.title and item.title in message_text:
                return self.say(self.act(item.id, action))

    # ------------------------------------------------------------ scheduled beats
    def send_top3(self):
        t, b = M.morning(self.store.open_items())
        return self.say(t, b)

    def send_week(self):
        t, b = M.show_all(self.store.open_items())
        return self.say(t, b)

    def morning(self, now=None):
        t, b = M.morning(self.store.open_items())
        return self.initiate(t, b, now=now)

    def checkin(self, label: str, now=None):
        items = self.store.open_items()
        t, b = M.checkin(items, label)
        sent = self.initiate(t, b, now=now)
        if sent:
            followup.after_checkin(items)
            self.store.save()
        return sent

    def dar_prompt(self, now=None):
        text = "Anything to add before I draft your DAR?"
        return self.initiate(text, [M._sec(text), M._actions(M._btn("Draft it now", "dar_draft"),
                                                              M._btn("Add notes first", "dar_notes"))], now=now)

    def shutdown(self, now=None):
        now = now or datetime.now(TZ)
        items = list(self.store.items.values())
        done = [i for i in items if i.status == "Done" and i.due is not None]
        moved = followup.nightly_rollover(items, now.replace(tzinfo=None))
        self.store.save()
        t, b = M.shutdown(done, moved)
        sent = self.initiate(t, b, now=now)
        if sent:
            self.post_channel("wins", f"Daily wins: {len(done)} done today.")
        return sent

    def friday_recap(self, now=None):
        self.post_channel("wins", "Weekly wins recap. Next week's big deadlines are in Monday's 7:00 list.")

    def stuck_units(self, now=None):
        self.post_channel("make-ready-vendors", "Stuck units check: nothing waiting longer than 3 days.")

    def monthly_7th(self, now=None):
        text = "The delinquency cycle starts today. Paste the unpaid list when you're ready."
        self.post_channel("collections", "Delinquency cycle started.")
        return self.initiate(text, now=now)

    def monthly_inspections(self, now=None):
        self.post_channel("inspections", "Monthly HappyCo, landscape and light inspections: checklist open for both properties.")

    # ------------------------------------------------------------ overwhelm / quiet
    def overwhelm(self, minutes: int = OVERWHELM_PAUSE_MIN, now=None):
        now = now or datetime.now(TZ)
        until = now + timedelta(minutes=minutes)
        self.store.set_pause(until)
        r = t3.rank(self.store.open_items())
        must = next((i for i in r if i.hard_deadline or i.urgent_kind), None) or (r[0] if r else None)
        t, b = M.overwhelm(must, "open it and do just the first part." if must else "",
                           until.strftime("%-I:%M"), max(len(r) - (1 if must else 0), 0))
        return self.say(t, b)

    def quiet(self, minutes: int, now=None):
        now = now or datetime.now(TZ)
        self.store.set_pause(now + timedelta(minutes=minutes))
        return self.say(f"Quiet for {minutes} minutes. I'll hold everything except true urgent items.")

    def move_rest_tomorrow(self, now=None):
        r = t3.rank(self.store.open_items())
        n = 0
        for i in r:
            if i.hard_deadline or i.urgent_kind:
                continue
            self.act(i.id, "tomorrow", now)
            n += 1
        return self.say(f"Moved {n} to tomorrow. This one can't wait; everything else can.")
