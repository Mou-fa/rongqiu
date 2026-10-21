"""固定知识 / 常识基线：盲猜、封顶、遗忘曲线。"""

from __future__ import annotations

from rongqiu import baselines


def test_baseline_constants():
    b = baselines.as_dict()
    assert b["chance_p_yes"] == 0.5
    assert b["chance_brier"] == 0.25
    assert b["confidence_cap"] == 0.8
    assert b["forgetting_note"]
    assert "Ebbinghaus" in b["source"]


def test_forgetting_curve_is_monotonic():
    values = [p["retention"] for p in baselines.EBBINGHAUS]
    assert values == sorted(values, reverse=True)
    assert values[0] > values[-1]
    assert all(0 <= v <= 1 for v in values)
