"""校准图的数据结构：用户直觉、逐条序列、三方对照。"""

from __future__ import annotations

from rongqiu import journal
from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT


def _judgment(n=5):
    facts = [SceneFact(scene=f"场景{i}", supports=SUPPORT, origin=i, order=i)
             for i in range(n)]
    return Node(nucleus="x", facts=facts).judge()


def test_user_lean_series_and_three_way(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)
    e = journal.record(_judgment(), "今晚要不要去聚餐", resolve_days=0, user_lean="no")
    journal.resolve(e["id"], "no")

    s = journal.stats()
    assert s["resolved"] == 1
    assert s["series"][0]["user_lean"] == "no"
    assert s["series"][0]["user_hit"] == 1
    assert s["three_way"]["samples"] == 1
    assert s["three_way"]["user_hit_rate"] == 1.0
    assert s["three_way"]["system_hit_rate"] == 0.0
    assert s["chance_brier"] == 0.25
    assert s["chance_skill"] is not None
    assert s["mean_p"] is not None


def test_invalid_user_lean_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)
    e = journal.record(_judgment(), "测试问题", resolve_days=0, user_lean="maybe")
    assert e["user_lean"] is None
