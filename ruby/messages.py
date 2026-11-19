"""Block Kit builders. Shape: one-line headline, <=5 short lines, buttons at bottom.
Tone: calm, "still open" not "overdue", one emoji max, property tag first."""
from __future__ import annotations
from .models import Item
from . import top3 as t3


def _sec(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _btn(label: str, action_id: str, value: str = "", style: str | None = None) -> dict:
    b = {"type": "button", "text": {"type": "plain_text", "text": label}, "action_id": action_id, "value": value or "x"}
    if style:
        b["style"] = style
    return b


def _actions(*btns: dict, block_id: str | None = None) -> dict:
    d = {"type": "actions", "elements": list(btns)}
    if block_id:
        d["block_id"] = block_id
    return d


def line(i: Item) -> str:
    star = "★ " if i.starred else ""
    return f"{star}[{i.prop}] {i.title}"


def reminder_buttons(item_id: str) -> dict:
    return _actions(
        _btn("Done", "item_done", item_id, "primary"),
        _btn("Later today", "item_later", item_id),
        _btn("Tomorrow", "item_tomorrow", item_id),
        {"type": "overflow", "action_id": "item_more", "options": [
            {"text": {"type": "plain_text", "text": t}, "value": f"{v}|{item_id}"}
            for t, v in [("Next week", "next_week"), ("Pick a date", "pick_date"),
                         ("Not needed", "skip"), ("Open in Notion", "notion")]]},
    )


def morning(items: list[Item], calendar: str = "") -> tuple[str, list]:
    top, rest = t3.top3(items)
    if not top:
        text = "Good morning. Nothing is due today."
        return text, [_sec(text), _actions(_btn("Brain dump", "brain_dump"))]
    starred = sum(1 for i in rest if i.starred)
    body = "Good morning. Here's what matters most today:\n" + "\n".join(
        f"{n}. {line(i)}" for n, i in enumerate(top, 1))
    more = f"+ {len(rest)} more today" + (f" · {starred} starred from yesterday" if starred else "") if rest else ""
    blocks = [_sec(body)]
    if more:
        blocks.append(_sec(more))
    if calendar:
        blocks.append(_sec(f"Calendar: {calendar}"))
    blocks.append(_actions(_btn("Show all", "show_all"), _btn("Brain dump", "brain_dump"),
                           _btn("I'm overwhelmed", "overwhelmed")))
    return body, blocks


def checkin(items: list[Item], label: str, extra: str = "") -> tuple[str, list]:
    top, rest = t3.top3(items)
    done_n = 0  # filled by caller via extra when relevant
    if not top:
        text = f"{label}: you're clear for now."
        return text, [_sec(text)]
    lines = [f"{label}. Still open:"] + [f"• {line(i)}" for i in top]
    if extra:
        lines.append(extra)
    if rest:
        lines.append(f"+ {len(rest)} more folded in Show all")
    text = "\n".join(lines[:6])
    return text, [_sec(text), _actions(_btn("Show all", "show_all"), _btn("Brain dump", "brain_dump"),
                                       _btn("I'm overwhelmed", "overwhelmed"))]


def show_all(items: list[Item]) -> tuple[str, list]:
    r = t3.rank(items)
    if not r:
        return "Nothing open.", [_sec("Nothing open.")]
    blocks = [_sec("*Everything still open*")]
    for prop in ("P88", "HG", "Both"):
        group = [i for i in r if i.prop == prop]
        if not group:
            continue
        blocks.append(_sec(f"*{ {'P88':'Peak 88','HG':'Heritage Grove','Both':'Both'}[prop] }*"))
        for i in group[:20]:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": line(i)},
                           "accessory": _btn("Done", "item_done", i.id)})
    return "Everything still open", blocks[:50]


def confirmation(summary: str, token: str) -> tuple[str, list]:
    return summary, [_sec(summary), _actions(
        _btn("Approve", "confirm_approve", token, "primary"),
        _btn("Edit", "confirm_edit", token),
        _btn("Cancel", "confirm_cancel", token, "danger"), block_id=f"confirm_{token}")]


def filed(summary: str, undo_id: str) -> tuple[str, list]:
    return summary, [_sec(summary), _actions(_btn("Undo", "undo", undo_id))]


def question(text: str, options: list[str], token: str) -> tuple[str, list]:
    return text, [_sec(text), _actions(*[_btn(o, "answer", f"{token}|{o}") for o in options])]


def draft(text: str, token: str) -> list[tuple[str, list]]:
    """Drafts go out as TWO messages: the plain draft alone (long-press / hover copies only it),
    then the controls. Slack Block Kit has no copy-to-clipboard button."""
    return [(text, []), ("Draft above. Copy it from the message.", [
        _actions(_btn("Shorter", "draft_shorter", token), _btn("Warmer", "draft_warmer", token),
                 _btn("More formal", "draft_formal", token), _btn("Mark as sent", "draft_sent", token))])]


def overwhelm(due_now: Item | None, next_step: str, until_label: str, can_wait: int) -> tuple[str, list]:
    if due_now:
        text = (f"I've paused reminders until {until_label}.\nOnly one thing truly needs today: {line(due_now)}.\n"
                f"Next small step: {next_step}\nEverything else can wait until tomorrow.")
    else:
        text = f"I've paused reminders until {until_label}.\nNothing truly needs today. Everything can wait until tomorrow."
    btns = []
    if can_wait:
        btns.append(_btn("Move the rest to tomorrow", "move_rest_tomorrow"))
    btns += [_btn("Done: what's next?", "next_step"), _btn("Give me 15 min", "pause_15")]
    return text, [_sec(text), _actions(*btns)]


def shutdown(done: list[Item], moved: list[Item]) -> tuple[str, list]:
    text = (f"Done today: {len(done)} things (see #wins)\nMoved to tomorrow: {len(moved)} (already rescheduled)\n"
            "Nothing waiting on you to send.\n\nYou're clear. See you at 7.")
    return text, [_sec(text)]


def home_view(items: list[Item]) -> dict:
    top, rest = t3.top3(items)
    body = "\n".join(f"{n}. {line(i)}" for n, i in enumerate(top, 1)) or "Nothing due today."
    return {"type": "home", "blocks": [
        {"type": "header", "text": {"type": "plain_text", "text": "Ruby HQ"}},
        _sec(f"*Today's Top 3*\n{body}"),
        _sec("*Check-ins* 7:00 · 11:00 · 2:00 · 4:00 DAR · 5:00 shutdown"),
        _actions(_btn("Brain dump", "brain_dump"), _btn("I'm overwhelmed", "overwhelmed"),
                 _btn("Show my week", "show_week"))]}
