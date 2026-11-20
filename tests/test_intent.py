from types import SimpleNamespace as NS
from datetime import datetime
from ruby import intent
from ruby.config import TZ


class FakeClaude:
    def __init__(self, payload=None, boom=False):
        self.payload, self.boom, self.kw = payload, boom, None
        self.messages = self
    def create(self, **kw):
        self.kw = kw
        if self.boom:
            raise RuntimeError("api down")
        return NS(content=[NS(type="text", text="ignore"), NS(type="tool_use", input=self.payload)])


NOW = datetime(2026, 11, 19, 14, 5, tzinfo=TZ)


def test_quick_phrases_skip_claude():
    c = FakeClaude(boom=True)
    assert intent.route("I'm overwhelmed", client=c)["intent"] == "overwhelmed"
    assert intent.route("quiet for 30", client=c)["minutes"] == 30
    assert c.kw is None


def test_forced_tool_call_with_brain_date_and_recent_context():
    c = FakeClaude({"intent": "make_ready", "title": "C214 paint and carpet", "confidence": 0.9,
                    "prop": "HG", "unit": "c214", "work_needed": ["Paint", "Carpet", "Bogus"]})
    out = intent.route("C214 at Heritage Grove is vacant, needs paint and carpet",
                       brain="drafts only", client=c, recent=["hi"], now=NOW)
    assert c.kw["tools"][0]["name"] == "classify" and "tool_choice" not in c.kw   # this model rejects forced tool_choice
    assert "drafts only" in c.kw["system"][1]["text"]
    assert "2026-11-19 14:05" in c.kw["messages"][0]["content"] and "- hi" in c.kw["messages"][0]["content"]
    assert out["unit"] == "C214" and out["work_needed"] == ["Paint", "Carpet"] and out["prop"] == "HG"


def test_normalize_cleans_untrusted_model_output():
    out = intent.normalize({"intent": "nonsense", "title": "B105 Maria wants $50 off", "confidence": "high",
                            "prop": "Mars", "due": "next tuesday", "unit": "not a unit"})
    assert out["intent"] == "unknown" and out["prop"] is None and out["due"] is None and out["unit"] is None
    assert "$" not in out["title"] and "$50" in out["details"]
    assert out["confidence"] == 0.5


def test_api_failure_asks_instead_of_crashing():
    out = intent.route("anything", client=FakeClaude(boom=True))
    assert out["intent"] == "unknown" and out["options"]


def test_no_client_asks_for_property():
    assert intent.route("order blinds", client=None)["question"]


def test_task_done_closes_matching_item_instead_of_creating(tmp_path):
    from ruby.core import Ruby
    from ruby.store import JsonStore
    sent = []
    slack = NS(chat_postMessage=lambda **k: sent.append(k) or {"ts": "1"},
               conversations_open=lambda **k: {"channel": {"id": "D1"}},
               conversations_list=lambda **k: {"channels": []})
    s = JsonStore(str(tmp_path / "s.json"))
    it = s.add(title="Post price sheets", prop="P88")
    r = Ruby(slack, s, FakeClaude({"intent": "task_done", "title": "price sheets", "confidence": 0.95}), roxy_id="U1")
    r.handle_dm("done with price sheets")
    assert s.items[it.id].status == "Done" and len(s.items) == 1


def test_replies_in_the_dm_it_came_from_even_if_user_id_is_wrong(tmp_path):
    from ruby.core import Ruby
    from ruby.store import JsonStore
    sent = []
    def bad_open(**k): raise RuntimeError("user_not_found")
    slack = NS(chat_postMessage=lambda **k: sent.append(k) or {"ts": "1"}, conversations_open=bad_open)
    r = Ruby(slack, JsonStore(str(tmp_path / "s.json")), None, roxy_id="WRONG")
    r.use_dm_channel("D999")
    r.say("hello")
    assert sent[0]["channel"] == "D999"


def test_text_answer_with_json_is_salvaged():
    c = FakeClaude()
    c.create = lambda **kw: NS(content=[NS(type="text", text='Sure: {"intent": "todo", "title": "x", "confidence": 0.8}')])
    assert intent.route("do x", client=c)["intent"] == "todo"


def test_question_buttons_have_unique_action_ids():
    from ruby import messages as M
    _, blocks = M.question("Which property?", ["Peak 88", "Heritage Grove", "Both"], "tok")
    ids = [b["action_id"] for b in blocks[1]["elements"]]
    assert len(ids) == len(set(ids))


def test_pre_move_out_due_is_14_days_after_notice_not_model_guess():
    out = intent.normalize({"intent": "pre_move_out", "title": "C214 pre-move-out inspection", "confidence": 0.9,
                            "notice_date": "2026-11-10", "due": "2026-11-25T17:00:00-08:00", "unit": "C214"})
    assert out["due"].startswith("2026-11-24T17:00") and "14 days" in out["assumed"]


def test_pre_move_out_checklist_shown_and_saved(tmp_path):
    from ruby.core import Ruby
    from ruby.store import JsonStore
    calls, sent = [], []
    class M:
        def upsert(self, i): return None
        def archive(self, i): pass
        def pull_open(self): return []
        def read_brain(self): return ""
        def create_pre_move_out(self, out, source=None): calls.append(out)
        def set_permission_to_enter(self, unit, value): return 'https://notion/x'
    slack = NS(chat_postMessage=lambda **k: sent.append(k) or {"ts": "1"},
               conversations_open=lambda **k: {"channel": {"id": "D1"}},
               conversations_list=lambda **k: {"channels": []})
    payload = {"intent": "pre_move_out", "title": "C214 pre-move-out", "confidence": 0.95, "prop": "HG",
               "unit": "C214", "notice_date": "2026-11-10"}
    r = Ruby(slack, JsonStore(str(tmp_path / "s.json"), M()), FakeClaude(payload), roxy_id="U1")
    r.handle_dm("C214 gave notice 11/10")
    assert "NTV uploaded to Yardi CRM IQ" in sent[0]["text"] and "HappyCo" in sent[0]["text"]
    token = next(iter(r.pending))
    r.approve(token)
    assert calls and calls[0]["unit"] == "C214"
    assert next(iter(r.store.items.values())).hard_deadline


def test_permission_no_creates_call_reminder_before_inspection_deadline(tmp_path):
    from ruby.core import Ruby, call_reminder_time
    from ruby.store import JsonStore
    sent, perms = [], []
    class M:
        def upsert(self, i): return None
        def archive(self, i): pass
        def pull_open(self): return []
        def read_brain(self): return ""
        def set_permission_to_enter(self, unit, value): perms.append((unit, value)); return 'https://notion/row'
    slack = NS(chat_postMessage=lambda **k: sent.append(k) or {"ts": "1"},
               conversations_open=lambda **k: {"channel": {"id": "D1"}},
               conversations_list=lambda **k: {"channels": []})
    s = JsonStore(str(tmp_path / "s.json"), M())
    s.add(title="C214 pre-move-out", prop="HG", intent="pre_move_out", due=datetime(2026, 11, 24, 17, tzinfo=TZ))
    r = Ruby(slack, s, None, roxy_id="U1")
    r.permission_to_enter({"unit": "C214", "permission": "No"}, now=datetime(2026, 11, 20, 10, 0, tzinfo=TZ))
    assert perms == [("C214", "No")]
    call = [i for i in s.items.values() if i.title.startswith("Call C214")][0]
    assert call.due == datetime(2026, 11, 20, 16, 0, tzinfo=TZ) and call.prop == "HG"
    txt = sent[-1]["text"]
    assert "Saved to Notion" in txt and "Permission to enter = No" in txt and "https://notion/row" in txt
    # Friday after 3:30pm rolls to Monday 9am; never past the deadline
    assert call_reminder_time(datetime(2026, 11, 20, 16, 0, tzinfo=TZ)) == datetime(2026, 11, 23, 9, 0, tzinfo=TZ)
    assert call_reminder_time(datetime(2026, 11, 23, 16, 0, tzinfo=TZ), datetime(2026, 11, 24, 17, tzinfo=TZ)) == datetime(2026, 11, 24, 9, 0, tzinfo=TZ)


def test_permission_yes_only_records(tmp_path):
    from ruby.core import Ruby
    from ruby.store import JsonStore
    sent = []
    slack = NS(chat_postMessage=lambda **k: sent.append(k) or {"ts": "1"},
               conversations_open=lambda **k: {"channel": {"id": "D1"}})
    s = JsonStore(str(tmp_path / "s.json"))
    Ruby(slack, s, None, roxy_id="U1").permission_to_enter({"unit": "C214", "permission": "Yes"})
    assert len(s.items) == 0 and "allows entry" in sent[0]["text"]


def test_permission_reports_when_notion_did_not_save(tmp_path):
    from ruby.core import Ruby
    from ruby.store import JsonStore
    sent = []
    class Down:
        def upsert(self, i): return None
        def archive(self, i): pass
        def pull_open(self): return []
        def read_brain(self): return ""
        def set_permission_to_enter(self, u, v): raise RuntimeError("down")
    slack = NS(chat_postMessage=lambda **k: sent.append(k) or {"ts": "1"},
               conversations_open=lambda **k: {"channel": {"id": "D1"}},
               conversations_list=lambda **k: {"channels": []})
    Ruby(slack, JsonStore(str(tmp_path / "s.json"), Down()), None, roxy_id="U1").permission_to_enter(
        {"unit": "C214", "permission": "No"})
    assert "Not saved to Notion yet" in sent[-1]["text"]
