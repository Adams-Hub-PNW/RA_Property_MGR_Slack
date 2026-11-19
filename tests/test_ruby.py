from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ruby import quiet, top3, followup
from ruby.core import Ruby
from ruby.models import Item
from ruby.store import JsonStore

TZ = ZoneInfo("America/Los_Angeles")
def at(d, h, m=0): return datetime(2026, 11, d, h, m, tzinfo=TZ)   # Nov 18 2026 = Wed


def test_quiet_window():
    assert quiet.may_send(now=at(18, 7))
    assert not quiet.may_send(now=at(18, 6, 59))
    assert not quiet.may_send(now=at(18, 17, 31))
    assert not quiet.may_send(now=at(21, 9))            # Saturday


def test_urgent_never_overnight_but_beats_pause():
    assert quiet.may_send("legal_deadline", now=at(21, 10))      # Sat 10am ok
    assert not quiet.may_send("legal_deadline", now=at(18, 22))
    assert not quiet.may_send("legal_deadline", now=at(18, 5))
    assert quiet.may_send("move_in_gap", paused_until=at(18, 20), now=at(18, 19))
    assert not quiet.may_send(None, paused_until=at(18, 12), now=at(18, 11))
    assert not quiet.may_send("random", now=at(18, 20))          # not one of the 3 types


def test_top3_order():
    mk = lambda id, **k: Item(id=id, title=id, **k)
    items = [mk("late", due=at(18, 16).replace(tzinfo=None)), mk("star", starred=True),
             mk("legal", hard_deadline=True), mk("movein", move_in_tomorrow_gap=True),
             mk("unblock", unblocks=True), mk("pinned", pinned=True)]
    top, rest = top3.top3(items)
    assert [i.id for i in top] == ["pinned", "legal", "movein"]
    assert [i.id for i in rest][:2] == ["star", "unblock"]


def test_snoozed_hidden():
    i = Item(id="a", title="a", snoozed_until=datetime.now() + timedelta(hours=5))
    assert top3.top3([i]) == ([], [])


def test_rollover_stars():
    i = Item(id="a", title="a")
    moved = followup.nightly_rollover([i], datetime(2026, 11, 18, 17))
    assert moved == [i] and i.starred


class FakeSlack:
    def __init__(self): self.posts, self.updates = [], []
    def conversations_open(self, users): return {"channel": {"id": "D1"}}
    def conversations_list(self, **k): return {"channels": [{"name": n, "id": "C_" + n} for n in
        ["wins", "ruby-log", "make-ready-vendors"]], "response_metadata": {}}
    def chat_postMessage(self, **k): self.posts.append(k); return {"ts": str(len(self.posts))}
    def chat_update(self, **k): self.updates.append(k)


def make(tmp_path):
    s = FakeSlack()
    return s, Ruby(s, JsonStore(str(tmp_path / "s.json")), llm=None, roxy_id="U1")


def test_confirm_then_save_then_undo(tmp_path):
    s, r = make(tmp_path)
    r.handle_dm("C214 HG vacant needs paint carpet")       # no llm -> asks which property
    token = next(iter(r.pending))
    r.clarify_answer(token, "Heritage Grove")
    assert not r.store.items                                # nothing saved before Approve
    token = next(iter(r.pending))
    r.approve(token)
    item = next(iter(r.store.items.values()))
    assert item.prop == "HG"
    undo_id = next(iter(r.store.undo))
    r.undo(undo_id)
    assert not r.store.items


def test_done_posts_to_wins_and_edits_in_place(tmp_path):
    s, r = make(tmp_path)
    it = r.store.add(title="Post ads", prop="P88")
    r.post_channel("make-ready-vendors", "[P88] Post ads", it)
    r.act(it.id, "done")
    assert r.store.items[it.id].status == "Done"
    assert any(p["channel"] == "C_wins" for p in s.posts)
    assert s.updates and "Done" in s.updates[0]["text"]


def test_overwhelm_pauses_and_gates(tmp_path):
    s, r = make(tmp_path)
    r.store.add(title="x", prop="HG", hard_deadline=True)
    r.overwhelm(now=at(18, 14))
    assert r.store.pause_until() is not None
    assert not quiet.may_send(None, r.store.pause_until(), at(18, 14, 30))
    assert "can't wait" not in s.posts[-1]["text"]   # tone: no alarms
    assert "!" not in s.posts[-1]["text"]


def test_gated_initiate_dropped_on_weekend(tmp_path):
    s, r = make(tmp_path)
    assert r.morning(now=at(21, 7)) is False and not s.posts
