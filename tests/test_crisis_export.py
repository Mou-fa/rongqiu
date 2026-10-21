"""危机快照的完整性清单与本地导出。"""
from __future__ import annotations

import json

import pytest

from rongqiu import crisis_export, crisis_store


def _save(tmp_path, monkeypatch):
    monkeypatch.setattr(crisis_store, "DATA", tmp_path / "data")
    journal = tmp_path / "journal.jsonl"
    journal.write_text('{"decision_id": "d1"}\n', encoding="utf-8")
    res = crisis_store.save({"question": "测试问题", "lat": 31.2, "lon": 121.5},
                            "ask", journal_path=journal)
    assert res["ok"], res
    return res


def test_snapshot_has_manifest_and_verifies(tmp_path, monkeypatch):
    res = _save(tmp_path, monkeypatch)
    eid = res["event_id"]
    folder = tmp_path / "data" / "crisis"
    assert (folder / (eid + ".json")).exists()
    assert (folder / (eid + ".manifest.json")).exists()
    assert (folder / (eid + ".journal.jsonl")).exists()
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
    readme = (out / "README.txt").read_text(encoding="utf-8")
    assert "不会自动发送给任何人" in readme
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
