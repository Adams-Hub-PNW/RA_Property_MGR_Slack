"""Bolt wiring (Socket Mode)."""
from __future__ import annotations
import logging, os
from slack_bolt import App
from . import messages as M
from .config import STATE_PATH
from .core import Ruby
from .store import JsonStore
from .notion import NotionMirror

log = logging.getLogger("ruby.app")


def build(bolt_token: str | None = None) -> tuple[App, Ruby]:
    log.info("Starting Ruby: notion=%s claude=%s state=%s", bool(os.environ.get("NOTION_TOKEN")),
             bool(os.environ.get("ANTHROPIC_API_KEY")), STATE_PATH)
    app = App(token=bolt_token or os.environ["SLACK_BOT_TOKEN"])
    llm = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        llm = anthropic.Anthropic()
    store = JsonStore(STATE_PATH, NotionMirror.from_env())
    store.sync_from_notion()
    ruby = Ruby(app.client, store, llm)
    register(app, ruby)
    return app, ruby


def register(app: App, ruby: Ruby):
    @app.event("message")
    def on_message(event, say):
        if event.get("channel_type") == "im" and not event.get("bot_id") and not event.get("subtype"):
            ruby.roxy_id = ruby.roxy_id or event["user"]
            ruby.use_dm_channel(event["channel"])   # reply where she wrote, whatever the env var says
            log.info("DM received (%d chars)", len(event.get("text", "")))
            ruby.handle_dm(event.get("text", ""))
        elif event.get("channel_type") == "channel" and not event.get("bot_id") and not event.get("subtype"):
            app.client.chat_postMessage(channel=event["channel"], thread_ts=event["ts"],
                                        text="Got it. Next time you can just DM me.")
            ruby.handle_dm(event.get("text", ""))

    @app.event("reaction_added")
    def on_reaction(event):
        item = event.get("item", {})
        if item.get("type") != "message":
            return
        hist = app.client.conversations_history(channel=item["channel"], latest=item["ts"], inclusive=True, limit=1)
        msgs = hist.get("messages") or []
        if msgs and msgs[0].get("bot_id"):
            ruby.on_reaction(event["reaction"], msgs[0].get("text", ""))

    @app.event("app_home_opened")
    def home(event, client):
        client.views_publish(user_id=event["user"], view=M.home_view(ruby.store.open_items()))

    @app.action("confirm_approve")
    def a_approve(ack, action): ack(); ruby.approve(action["value"])
    @app.action("confirm_cancel")
    def a_cancel(ack, action): ack(); ruby.cancel(action["value"])
    @app.action("confirm_edit")
    def a_edit(ack, action, body, client):
        ack()
        token = action["value"]
        p = ruby.pending.get(token)
        if not p:
            return
        client.views_open(trigger_id=body["trigger_id"], view={
            "type": "modal", "callback_id": "edit_item", "private_metadata": token,
            "title": {"type": "plain_text", "text": "Edit"}, "submit": {"type": "plain_text", "text": "Save"},
            "blocks": [{"type": "input", "block_id": "t", "label": {"type": "plain_text", "text": "What"},
                        "element": {"type": "plain_text_input", "action_id": "v", "initial_value": p.get("title", "")}}]})
    @app.view("edit_item")
    def v_edit(ack, view):
        ack()
        token = view["private_metadata"]
        if token in ruby.pending:
            ruby.pending[token]["title"] = view["state"]["values"]["t"]["v"]["value"]
            ruby.approve(token)
    @app.action("answer")
    def a_answer(ack, action):
        ack(); token, ans = action["value"].split("|", 1); ruby.clarify_answer(token, ans)
    @app.action("undo")
    def a_undo(ack, action): ack(); ruby.undo(action["value"])

    for aid, act in [("item_done", "done"), ("item_later", "later"), ("item_tomorrow", "tomorrow")]:
        def make(act):
            def h(ack, action): ack(); ruby.say(ruby.act(action["value"], act))
            return h
        app.action(aid)(make(act))

    @app.action("item_more")
    def a_more(ack, action):
        ack()
        v, iid = action["selected_option"]["value"].split("|", 1)
        ruby.say(ruby.act(iid, v))
    @app.action("show_all")
    def a_all(ack): ack(); ruby.send_week()
    @app.action("brain_dump")
    def a_dump(ack): ack(); ruby.handle_dm("dump")
    @app.action("overwhelmed")
    def a_ow(ack): ack(); ruby.overwhelm()
    @app.action("move_rest_tomorrow")
    def a_move(ack): ack(); ruby.move_rest_tomorrow()
    @app.action("pause_15")
    def a_p15(ack): ack(); ruby.quiet(15)
    @app.action("show_week")
    def a_week(ack): ack(); ruby.send_week()

    @app.command("/dump")
    def c_dump(ack, command): ack(); ruby.handle_dm(command.get("text") or "dump")
    @app.command("/top3")
    def c_top(ack): ack(); ruby.send_top3()
    @app.command("/week")
    def c_week(ack): ack(); ruby.send_week()
    @app.command("/overwhelmed")
    def c_ow(ack): ack(); ruby.overwhelm()
    @app.command("/quiet")
    def c_quiet(ack, command):
        ack()
        txt = (command.get("text") or "60").strip()
        ruby.quiet(int(txt) if txt.isdigit() else 60)

    @app.shortcut("brain_dump_global")
    def s_global(ack, body, client):
        ack()
        client.views_open(trigger_id=body["trigger_id"], view={
            "type": "modal", "callback_id": "dump_modal", "title": {"type": "plain_text", "text": "Brain dump"},
            "submit": {"type": "plain_text", "text": "Send to Ruby"},
            "blocks": [{"type": "input", "block_id": "t", "label": {"type": "plain_text", "text": "Everything"},
                        "element": {"type": "plain_text_input", "action_id": "v", "multiline": True}}]})
    @app.view("dump_modal")
    def v_dump(ack, view):
        ack(); ruby.handle_dm(view["state"]["values"]["t"]["v"]["value"])
    @app.shortcut("send_to_ruby")
    def s_msg(ack, shortcut):
        ack(); ruby.handle_dm(shortcut["message"].get("text", ""))
