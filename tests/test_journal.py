"""校准机器的测试。

绒球的全部有效性押在「长期命中率 ≈ 置信度」上。
如果这台机器算错了，整套系统的自我检验就是假的。
"""

from __future__ import annotations

import random

import pytest

from rongqiu import journal


def _entry(lean: str, conf: float, outcome: str | None, n: int = 8, rule: str = "direct"):
    return {"id": "t", "lean": lean, "confidence": conf, "n": n,
            "rule": rule, "outcome": outcome}


def test_p_yes_converts_lean_and_confidence_into_a_probability():
    assert journal.p_yes(_entry("yes", 0.7, None)) == pytest.approx(0.7)
    assert journal.p_yes(_entry("no", 0.7, None)) == pytest.approx(0.3)
    assert journal.p_yes(_entry("no", 0.3, None)) == pytest.approx(0.7)


def test_brier_of_a_confident_correct_call_is_small():
    e = _entry("yes", 0.9, "yes")
    assert journal.brier([e]) == pytest.approx((0.9 - 1) ** 2)


def test_brier_of_a_confident_wrong_call_is_large():
    e = _entry("yes", 0.9, "no")
    assert journal.brier([e]) == pytest.approx(0.9 ** 2)


def test_perfect_calibration_recovers_the_diagonal():
    """按 p_yes 生成结果，可靠性曲线必须贴着对角线。

    这是对分箱逻辑的直接检验。第一版用交错取样把排序打乱了，
    五个箱的预测均值全是 0.49，曲线看起来完美但其实是坏的。
    """
    rng = random.Random(11)
    entries = []
    for _ in range(4000):
        p = rng.uniform(0.05, 0.95)
        lean = "yes" if p >= 0.5 else "no"
        conf = p if lean == "yes" else 1 - p
        outcome = "yes" if rng.random() < p else "no"
        entries.append(_entry(lean, conf, outcome))
    s = journal.stats(entries, bins=5)
    for r in s["reliability"]:
        assert abs(r["obs"] - r["p_mean"]) < 0.06, r


def test_overconfidence_is_detected():
    """全部说 90%，但只有一半对——可靠性曲线必须显示为过度自信。"""
    entries = [_entry("yes", 0.9, "yes" if i % 2 == 0 else "no") for i in range(400)]
    s = journal.stats(entries, bins=3)
    top = s["reliability"][-1]
    assert top["obs"] < top["p_mean"] - 0.3


def test_stats_survive_a_single_direction_sample():
    """结果全同向时基准 Brier 为 0，技巧分无法计算，但不能崩。"""
    s = journal.stats([_entry("yes", 0.5, "no"), _entry("yes", 0.6, "no")])
    assert s["skill"] is None
    assert "无法计算" in journal.render_stats(s)


def test_by_n_groups_for_the_811_test():
    entries = [_entry("yes", 0.8, "yes", n=8) for _ in range(3)]
    entries += [_entry("no", 0.4, "no", n=2) for _ in range(2)]
    s = journal.stats(entries)
    ns = {b["n"]: b for b in s["by_n"]}
    assert ns[8]["count"] == 3 and ns[8]["determinability"] == pytest.approx(0.8)
    assert ns[2]["hit_rate"] == pytest.approx(1.0)


def test_record_and_resolve_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "DATA", tmp_path)
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.jsonl")

    from rongqiu.node import Judgment
    from rongqiu.triples import Triple

    j = Judgment(nucleus="测试问题", lean="yes", confidence=0.6, n=8,
                 determinability=0.8, support_ratio=0.7, rule="direct",
                 assumption="假设", unknown="未知",
                 facts=[Triple("a", "b", "c", source="chat")])
    e = journal.record(j, "测试问题", resolve_days=0)
    assert journal.load()[0]["id"] == e["id"]
    assert len(journal.pending()) == 1
    journal.resolve(e["id"], "no", "没发生")
    assert journal.pending() == []
    s = journal.stats()
    assert s["resolved"] == 1 and s["hit_rate"] == 0.0
