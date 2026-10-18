"""校准闭环的测试。

绒球的全部分量押在「长期命中率 ≈ 输出的置信度」上。没有这个闭环，
811 只是一个漂亮的断言。这些测试钉住闭环的每个环节。
"""

from __future__ import annotations

import pytest

from rongqiu import journal
from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT


def _judgment(n=5):
    facts = [SceneFact(scene=f"场景{i}", supports=SUPPORT, origin=i, order=i)
             for i in range(n)]
    return Node(nucleus="x", facts=facts).judge()


def test_resolve_window_follows_the_question():
    """今晚的决定明天就能回收，不该等七天。"""
    assert journal.resolve_days_for("今晚要不要去聚餐") == 1
    assert journal.resolve_days_for("明天去不去") == 1
    assert journal.resolve_days_for("最近要不要换工作") == 7
    assert journal.resolve_days_for("这个月要不要买手机") == 30


def test_short_horizon_questions_are_recorded_with_one_day(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)
    e = journal.record(_judgment(), "今晚要不要去聚餐")
    assert "resolve_by" in e
    from datetime import datetime
    delta = datetime.fromisoformat(e["resolve_by"]) - datetime.fromisoformat(e["ts"])
    assert delta.days == 1


def test_record_and_resolve_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)
    e = journal.record(_judgment(), "要不要学英语")
    assert journal.pending(as_of="2099-01-01T00:00:00+00:00")  # 到期后才出现
    assert not journal.pending()                                 # 现在还没到期
    got = journal.resolve(e["id"], "yes", "学了")
    assert got["outcome"] == "yes"
    assert journal.pending(as_of="2099-01-01T00:00:00+00:00") == []


def test_calibration_gap_sign(tmp_path, monkeypatch):
    """系统全判「会」且很自信，结果全是「没发生」→ 偏差为负，过度自信。"""
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)
    j = _judgment()                    # 5 条支持 → 判 yes，置信 0.71
    ids = [journal.record(j, "要不要学英语")["id"] for _ in range(4)]
    for i in ids:
        journal.resolve(i, "no")       # 结果全是没发生 → 全错
    s = journal.stats()
    assert s["resolved"] == 4
    assert s["hit_rate"] == 0.0
    # 偏差 = 命中率 - 平均置信度 = 0 - 0.71
    assert s["calibration_gap"] == pytest.approx(-s["mean_confidence"], abs=0.01)
    assert s["calibration_gap"] < -0.5


def test_brier_and_skill_are_computed(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)
    e = journal.record(_judgment(), "要不要学英语")
    journal.resolve(e["id"], "yes")
    s = journal.stats()
    assert s["brier"] is not None
    assert s["baseline_brier"] is not None
    assert 0 <= s["brier"] <= 1


def test_by_n_is_the_811_test(tmp_path, monkeypatch):
    """按面数分组：每一行都是「这个 N 的判断到底准不准」。"""
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)
    for n in (3, 5, 8):
        e = journal.record(_judgment(n), "要不要学英语")
        journal.resolve(e["id"], "no")
    s = journal.stats()
    assert {b["n"] for b in s["by_n"]} == {3, 5, 8}
    for b in s["by_n"]:
        assert 0.0 <= b["hit_rate"] <= 1.0
