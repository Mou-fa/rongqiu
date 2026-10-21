"""危机快照的完整性清单与本地导出。"""
from __future__ import annotations

import json

import pytest

from rongqiu import crisis_export, crisis_store


def _save(tmp_path, monkeypatch):
    monkeypatch.setattr(crisis_store, "DATA", tmp_path / "data")
    res = crisis_store.save({"question": "测试问题",
                             "region": "湖北省恩施土家族苗族自治州"}, "ask")
    assert res["ok"], res
    return res


def test_snapshot_has_manifest_and_verifies(tmp_path, monkeypatch):
    res = _save(tmp_path, monkeypatch)
    eid = res["event_id"]
    folder = tmp_path / "data" / "crisis"
    assert (folder / (eid + ".json")).exists()
    assert (folder / (eid + ".manifest.json")).exists()
    assert not (folder / (eid + ".journal.jsonl")).exists()
    ver = crisis_store.verify_event(eid)
    assert ver["ok"] is True
    rec = json.loads((folder / (eid + ".json")).read_text(encoding="utf-8"))
    assert rec["manifest"] == eid + ".manifest.json"
    assert rec["schema"] == crisis_store.SCHEMA


def test_export_copies_verifiable_files(tmp_path, monkeypatch):
    res = _save(tmp_path, monkeypatch)
    eid = res["event_id"]
    out = tmp_path / "export_case"
    result = crisis_export.export_event(eid, out)
    assert result["ok"] is True
    assert (out / (eid + ".json")).exists()
    assert (out / (eid + ".manifest.json")).exists()
    assert (out / "README.txt").exists()
    assert (out / "SHA256SUMS").exists()
    assert not (out / (eid + ".journal.jsonl")).exists()
    readme = (out / "README.txt").read_text(encoding="utf-8")
    assert "不会自动发送给任何人" in readme
    assert "不包含历史判断、回答或完整 journal" in readme
    sums = (out / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
    assert len(sums) >= 2
    with pytest.raises(ValueError):
        crisis_export.export_event(eid, out)


def test_verify_detects_tamper(tmp_path, monkeypatch):
    res = _save(tmp_path, monkeypatch)
    eid = res["event_id"]
    path = tmp_path / "data" / "crisis" / (eid + ".json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["request"]["question"] = "被改过"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ver = crisis_store.verify_event(eid)
    assert ver["ok"] is False
    with pytest.raises(ValueError):
        crisis_export.export_event(eid, tmp_path / "tampered_export")


def test_migrate_v2_removes_journal_and_strips_request(tmp_path, monkeypatch):
    monkeypatch.setattr(crisis_store, "DATA", tmp_path / "data")
    folder = tmp_path / "data" / "crisis"
    folder.mkdir(parents=True)
    eid = "old-event"
    (folder / (eid + ".journal.jsonl")).write_text("history\n", encoding="utf-8")
    (folder / (eid + ".json")).write_text(json.dumps({
        "schema": 1, "event_id": eid, "saved_at": "2026-10-22T06:00:00+08:00",
        "source": "ask",
        "request": {"question": "旧问题", "lat": 31.0, "lon": 121.0},
        "journal_snapshot": eid + ".journal.jsonl",
    }, ensure_ascii=False), encoding="utf-8")
    out = crisis_store.migrate_v2()
    assert out["ok"] is True
    assert out["removed_journals"] == 1
    assert not (folder / (eid + ".journal.jsonl")).exists()
    rec = json.loads((folder / (eid + ".json")).read_text(encoding="utf-8"))
    assert rec["schema"] == crisis_store.SCHEMA
    assert rec["request"] == {"question": "旧问题", "region": ""}
    assert "journal_snapshot" not in rec
    assert crisis_store.verify_event(eid)["ok"] is True
