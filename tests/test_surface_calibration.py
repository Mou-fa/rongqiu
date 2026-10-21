"""按面校准：回答归属于哪个面，回收后单独统计。"""
from __future__ import annotations

import app.server as server
from rongqiu import journal, surfaces
from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)


def _judgment(n=3):
    facts = [SceneFact(scene=f"场景{i}", supports=SUPPORT, origin=i, order=i)
             for i in range(n)]
    return Node(nucleus="x", facts=facts).judge()


def test_surface_calibration_counts_hits(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    e1 = journal.record(_judgment(), "问题一", resolve_days=0,
                        surface_answers=[{"surface": "decision.health", "direction": "support"}])
    journal.resolve(e1["id"], "yes")
    e2 = journal.record(_judgment(), "问题二", resolve_days=0,
                        surface_answers=[{"surface": "decision.health", "direction": "oppose"}])
    journal.resolve(e2["id"], "yes")

    rows = journal.stats()["surfaces"]
    health = next(r for r in rows if r["surface"] == "decision.health")
    assert health["facts"] == 2
    assert health["decisions"] == 2
    assert health["hits"] == 1
    assert health["hit_rate"] == 0.5
    assert health["brier"] == 0.5


def test_judge_records_surface_answers(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    expected = surfaces.probe_map()["q33"]
    out = server.api_judge(server.JudgeBody(
        question="最近身体不舒服，要不要去医院？",
        binary="去医院",
        answers=[server.AnswerItem(id="q33", answer="yes")],
        asked=["q33"],
    ))
    assert out["ok"] is True
    entry = journal.load()[-1]
    got = [x["surface"] for x in entry["surface_answers"]]
    assert got == expected
    assert entry["surface_answers"][0]["direction"] in ("support", "oppose")


def test_legacy_facts_backfill_surface():
    rows = journal.surface_calibration([{
        "id": "legacy1", "decision_id": "d1", "outcome": "yes",
        "facts": [{"scene": "你会游泳吗？（答：是）", "source": "主动询问",
                   "supports": "support"}],
    }])
    assert rows
    assert rows[0]["surface"] == "decision.safety"
    assert rows[0]["facts"] == 1
    assert rows[0]["hits"] == 1
