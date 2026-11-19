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
    assert c.kw["tool_choice"] == {"type": "tool", "name": "classify"}
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
