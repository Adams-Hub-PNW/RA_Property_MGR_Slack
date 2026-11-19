from datetime import datetime
from ruby.notion import NotionMirror, page_id_from_url, TASK_TRACKER
from ruby.store import JsonStore


class FakePages:
    def __init__(self, fail=0):
        self.calls, self.fail, self.n = [], fail, 0
    def create(self, **kw):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("notion down")
        self.n += 1
        self.calls.append(("create", kw))
        return {"url": f"https://app.notion.com/p/{self.n:032x}"}
    def update(self, **kw):
        self.calls.append(("update", kw))
        return {"url": "u"}


class FakeClient:
    def __init__(self, fail=0, rows=None):
        self.pages = FakePages(fail)
        self.rows = rows or []
        self.data_sources = self
    def query(self, **kw):
        return {"results": self.rows, "has_more": False}


def page(pid, title, due=None, prop="Heritage Grove"):
    return {"id": pid, "url": f"https://app.notion.com/p/{pid.replace('-', '')}",
            "properties": {"Task occurrence": {"title": [{"plain_text": title}]},
                           "Due date": {"date": {"start": due} if due else None},
                           "Property": {"select": {"name": prop}}, "Source": {"url": None}}}


def store(tmp_path, client):
    return JsonStore(str(tmp_path / "s.json"), NotionMirror(client))


def test_page_id_from_url():
    assert page_id_from_url("https://app.notion.com/p/41d83c5ff1e1815885fbfbde20a0cab7?pvs=204") == "41d83c5ff1e1815885fbfbde20a0cab7"
    assert page_id_from_url(None) is None


def test_add_creates_in_task_tracker_with_audit_fields(tmp_path):
    c = FakeClient(); s = store(tmp_path, c)
    it = s.add(title="C214 paint", prop="HG", due=datetime(2026, 11, 20, 10), source="https://slack/x")
    kind, kw = c.pages.calls[0]
    assert kind == "create" and kw["parent"]["data_source_id"] == TASK_TRACKER
    p = kw["properties"]
    assert p["Created by Ruby"] == {"checkbox": True}
    assert p["Property"]["select"]["name"] == "Heritage Grove"
    assert p["Source"] == {"url": "https://slack/x"}
    assert it.notion_url and not s.retry_queue


def test_update_is_idempotent_and_done_sets_completed(tmp_path):
    c = FakeClient(); s = store(tmp_path, c)
    it = s.add(title="price sheets", prop="P88")
    s.update(it.id, status="Done")
    assert [k for k, _ in c.pages.calls] == ["create", "update"]
    assert c.pages.calls[1][1]["properties"]["Status"]["select"]["name"] == "Done"
    assert "Completed at" in c.pages.calls[1][1]["properties"]


def test_failed_write_is_queued_then_retried(tmp_path):
    c = FakeClient(fail=1); s = store(tmp_path, c)
    it = s.add(title="x")
    assert it.id in s.retry_queue and it.notion_url is None
    assert s.retry_failed() == 1
    assert not s.retry_queue and s.items[it.id].notion_url


def test_undo_archives_notion_page(tmp_path):
    c = FakeClient(); s = store(tmp_path, c)
    it = s.add(title="x")
    uid = s.register_undo([it.id])
    assert s.do_undo(uid)
    kind, kw = c.pages.calls[-1]
    assert kind == "update" and kw["archived"] is True


def test_sync_rebuilds_state_on_fresh_volume(tmp_path):
    rows = [page("41d83c5f-f1e1-8100-0000-000000000001", "B105 renewal call", "2026-11-20T09:00:00", "Peak 88")]
    s = store(tmp_path, FakeClient(rows=rows))
    assert s.sync_from_notion() == 1
    i = list(s.items.values())[0]
    assert i.title == "B105 renewal call" and i.prop == "P88" and i.due.day == 20
    assert s.sync_from_notion() == 0   # idempotent


def test_sync_closes_local_items_gone_from_notion(tmp_path):
    c = FakeClient(); s = store(tmp_path, c)
    it = s.add(title="x")
    s.sync_from_notion()               # Notion returns no open rows
    assert s.items[it.id].status == "Done"


def test_unwritable_state_path_falls_back_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = JsonStore("/proc/definitely/not/writable/state.json")
    s.add(title="still works")
    assert (tmp_path / "state.json").exists()


def test_missing_state_folder_is_created(tmp_path):
    s = JsonStore(str(tmp_path / "data" / "state.json"))
    s.add(title="x")
    assert (tmp_path / "data" / "state.json").exists()
