"""decision_id 去重与旧数据兼容。"""
from __future__ import annotations

import json

from rongqiu import journal
from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT


def _judgment(n=5):
    facts = [SceneFact(scene=f"场景{i}", supports=SUPPORT, origin=i, order=i)
             for i in range(n)]
    return Node(nucleus="x", facts=facts).judge()


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)


def test_same_decision_same_day_dedupes(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    e1 = journal.record(_judgment(), "今晚要不要去聚餐", resolve_days=0)
    e2 = journal.record(_judgment(), "今晚要不要去聚餐", resolve_days=0)
    assert e1["decision_id"] == e2["decision_id"]
    assert e2["revision"] == 2
    assert len(journal.load()) == 2
    journal.resolve(e1["id"], "yes")
    s = journal.stats()
    assert s["total"] == 1
    assert s["resolved"] == 1


def test_pending_dedupes(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    journal.record(_judgment(), "今晚要不要去聚餐", resolve_days=0)
    journal.record(_judgment(), "今晚要不要去聚餐", resolve_days=0)
    assert len(journal.pending()) == 1


def test_old_entries_without_decision_id_collapse(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    base = {"nucleus": "旧问题", "ts": "2026-10-21T10:00:00+08:00",
            "resolve_by": "2026-10-21T10:00:00+08:00", "outcome": None,
            "lean": "yes", "confidence": 0.6, "n": 3,
            "determinability": 0.6, "rule": "direct", "id": "old-1"}
    other = dict(base, id="old-2", ts="2026-10-21T11:00:00+08:00")
    journal.JOURNAL.write_text(
        json.dumps(base, ensure_ascii=False) + chr(10) +
        json.dumps(other, ensure_ascii=False) + chr(10), encoding="utf-8")
    assert journal.stats()["total"] == 1
    assert len(journal.pending()) == 1
