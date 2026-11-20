import pytest
from types import SimpleNamespace as NS
from ruby import handlers
from ruby.core import Ruby
from ruby.notion import NotionMirror
from ruby.store import JsonStore


class Rec:
    """Mirror that records every Notion write."""
    def __init__(self):
        self.rows, self.archived, self.n, self.existing = [], [], 0, None
    def upsert(self, i): return f"https://app.notion.com/p/{'a' * 32}"
    def archive(self, i): pass
    def pull_open(self): return []
    def read_brain(self): return ""
    def create_row(self, ds, props, children=None):
        self.n += 1; self.rows.append((ds, props, children))
        return {"id": f"id{self.n}", "url": f"https://notion/{ds}/{self.n}"}
    def find_by_title(self, ds, tp, contains): return self.existing
    def update_page(self, pid, props): self.rows.append(("UPDATE:" + pid, props, None)); return "https://notion/upd"
    def archive_page(self, pid): self.archived.append(pid)


def make(tmp_path, mirror):
    sent = []
    slack = NS(chat_postMessage=lambda **k: sent.append(k) or {"ts": "1"},
               conversations_open=lambda **k: {"channel": {"id": "D1"}},
               conversations_list=lambda **k: {"channels": []})
    return Ruby(slack, JsonStore(str(tmp_path / "s.json"), mirror), None, roxy_id="U1"), sent


def approve(r, out):
    r.propose({"confidence": 0.9, **out}, "orig")
    r.approve(next(iter(r.pending)))


CASES = [
    ({"intent": "daily_note", "title": "Toured 1x1 at Peak", "prop": "P88", "note_type": "Tour"}, ["daily_notes"], False),
    ({"intent": "supply", "title": "Peak model supplies", "prop": "P88", "supply_items": ["paper towels", "air freshener"],
      "supply_for": "Model Unit"}, ["supply_list", "supply_list"], False),
    ({"intent": "email_triage", "title": "Reply to Robin", "prop": "Both",
      "email": {"sender": "Robin", "subject": "Q4 report", "topic": "Reporting", "urgency": "Today",
                "summary": "Wants the Q4 report.", "action_items": ["Send Q4 report"]}}, ["email_triage"], True),
    ({"intent": "make_ready", "title": "C214 turn", "prop": "HG", "unit": "C214", "work_needed": ["Paint", "Carpet"]},
     ["make_ready"], True),
    ({"intent": "move_out", "title": "B105 move-out", "prop": "P88", "unit": "B105", "move_out_date": "2026-12-01"},
     ["move_outs", "make_ready"], True),
    ({"intent": "pre_move_out", "title": "C214 pre-move-out", "prop": "HG", "unit": "C214", "notice_date": "2026-11-10"},
     ["move_outs"], True),
    ({"intent": "move_in", "title": "A101 move-in", "prop": "P88", "unit": "A101", "move_in_date": "2026-12-05"},
     ["move_ins"], True),
    ({"intent": "work_order", "title": "WO 4471", "prop": "P88", "wo_number": "4471", "issue": "leaky faucet"},
     ["work_orders"], True),
    ({"intent": "recurring_task", "title": "Market survey", "prop": "Both",
      "recurrence": {"cadence": "Weekly", "due_rule": "every Monday"}}, ["recurring_tasks"], False),
    ({"intent": "lead", "title": "FB Marketplace: Dana", "prop": "HG", "lead_source": "Facebook Marketplace"}, ["leads"], False),
    ({"intent": "checklist", "title": "Fire drill prep", "prop": "P88", "checklist_items": ["Test alarms", "Walk exits"]},
     ["checklists"], True),
]


@pytest.mark.parametrize("out,dbs,task", CASES, ids=[c[0]["intent"] for c in CASES])
def test_each_intent_writes_the_right_databases(tmp_path, out, dbs, task):
    m = Rec(); r, sent = make(tmp_path, m)
    approve(r, out)
    assert [row[0] for row in m.rows] == dbs
    for ds, props, _ in m.rows:                 # every property name/type is valid for that database
        assert set(props) <= set(handlers.SCHEMAS[ds])
        assert props["Created by Ruby"] == {"checkbox": True}
    reply = sent[-1]["text"]
    assert reply.count("✓ Saved to Notion") >= len(dbs) and "⚠" not in reply
    has_task = any(i.intent == out["intent"] for i in r.store.items.values())
    assert has_task == task or out["intent"] == "email_triage"


def test_checklist_page_has_todo_boxes(tmp_path):
    m = Rec(); r, sent = make(tmp_path, m)
    approve(r, CASES[-1][0])
    kids = m.rows[0][2]
    assert [k["to_do"]["rich_text"][0]["text"]["content"] for k in kids] == ["Test alarms", "Walk exits"]
    assert "☐ Test alarms" in sent[-1]["text"]


def test_email_action_items_become_reminders(tmp_path):
    m = Rec(); r, _ = make(tmp_path, m)
    approve(r, CASES[2][0])
    assert any(i.title == "Send Q4 report" for i in r.store.items.values())


def test_renewal_call_updates_existing_row_and_logs_call(tmp_path):
    m = Rec(); m.existing = {"id": "ren1", "url": "https://notion/ren1"}
    r, sent = make(tmp_path, m)
    approve(r, {"intent": "renewal_call", "title": "B105 Maria counter", "prop": "P88", "unit": "B105",
                "resident_first_name": "Maria", "renewal_status": "Counter Offer", "details": "Wants $50 off",
                "contact_method": "Call", "call_outcome": "Counter"})
    kinds = [row[0] for row in m.rows]
    assert kinds == ["UPDATE:ren1", "renewal_call_log"]
    assert m.rows[0][1]["Status"] == {"select": {"name": "Counter Offer"}}
    assert m.rows[1][1]["Renewal"] == {"relation": [{"id": "ren1"}]}
    assert "Wants $50 off" in m.rows[0][1]["Counter offer details"]["rich_text"][0]["text"]["content"]


def test_renewal_call_creates_renewal_when_none_exists(tmp_path):
    m = Rec(); r, _ = make(tmp_path, m)
    approve(r, {"intent": "renewal_call", "title": "B105 Maria", "prop": "P88", "unit": "B105",
                "resident_first_name": "Maria", "renewal_status": "Contacted"})
    assert [row[0] for row in m.rows] == ["renewals", "renewal_call_log"]
    assert m.rows[1][1]["Renewal"] == {"relation": [{"id": "id1"}]}


def test_failed_notion_write_is_reported_not_hidden(tmp_path):
    m = Rec()
    def boom(*a, **k): raise RuntimeError("down")
    m.create_row = boom
    r, sent = make(tmp_path, m)
    approve(r, CASES[0][0])
    assert "Not saved to Notion: Daily Notes" in sent[-1]["text"]


def test_undo_archives_the_notion_pages(tmp_path):
    m = Rec(); r, _ = make(tmp_path, m)
    approve(r, CASES[0][0])
    uid = next(iter(r.store.undo))
    assert r.store.do_undo(uid) and m.archived == ["id1"]


def test_both_is_dropped_where_database_has_no_both_option(tmp_path):
    assert handlers._prop("make_ready", {"prop": "Both"}) is None
    assert handlers._prop("daily_notes", {"prop": "Both"}) == "Both"


def test_preflight_flags_missing_and_wrong_columns():
    class C:
        class data_sources:
            @staticmethod
            def retrieve(data_source_id):
                return {"properties": {"Note": {"type": "title"}, "Date": {"type": "rich_text"}}}
    problems = NotionMirror(C()).preflight()
    assert any("daily_notes: column 'Date' is rich_text, expected date" in p for p in problems)
    assert any("daily_notes: missing column 'Type'" in p for p in problems)
