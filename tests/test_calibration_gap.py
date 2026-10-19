"""校准缺口预警。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rongqiu import calibration as cal  # noqa: E402


# ---------- 分类 ----------

@pytest.mark.parametrize("q,cat", [
    ("最近很累，要不要换工作？", "工作"),
    ("老板让我加班，去不去？", "工作"),
    ("今晚要不要去聚餐？", "社交"),
    ("朋友邀请我参加婚礼", "社交"),
    ("钱包有点紧，要不要买这个手机？", "消费"),
    ("这个订阅值不值得付钱？", "消费"),
    ("头不舒服想睡觉", "健康"),
    ("最近要不要去医院体检？", "健康"),
    ("要不要报名这个课程？", "学习"),
])
def test_category_of(q, cat):
    assert cal.category_of(q) == cat


def test_category_other():
    assert cal.category_of("要不要把这个想法说出口") == cal.OTHER


# ---------- 汇总 ----------

def _e(lean, conf, outcome, q="要不要换工作"):
    return {"nucleus": q, "lean": lean, "confidence": conf, "outcome": outcome}


def test_summarize_overconfident():
    # 都说 0.9，实际对一半 → 严重高估
    es = [_e("yes", 0.9, "yes"), _e("yes", 0.9, "no"),
          _e("yes", 0.9, "no"), _e("yes", 0.9, "yes")]
    s = cal.summarize(es)
    assert s["direction"] == "over"
    assert s["gap"] < 0


def test_summarize_calibrated():
    es = [_e("yes", 0.5, "yes"), _e("yes", 0.5, "no")]
    s = cal.summarize(es)
    assert s["direction"] == "ok"


def test_summarize_underconfident():
    es = [_e("yes", 0.3, "yes"), _e("yes", 0.3, "yes"),
          _e("yes", 0.3, "yes"), _e("yes", 0.3, "no")]
    s = cal.summarize(es)
    assert s["direction"] == "under"


# ---------- 预警：什么时候该沉默 ----------

def test_gap_for_silent_when_too_few():
    es = [_e("yes", 0.9, "no")] * 3          # 不足 MIN_SAMPLES
    assert cal.gap_for("要不要换工作", 0.9, entries=es) is None


def test_gap_for_silent_when_gap_small():
    # 4 对 2 错，置信 0.62 → 命中 0.67，缺口很小
    es = [_e("yes", 0.62, "yes")] * 4 + [_e("yes", 0.62, "no")] * 2
    assert cal.gap_for("要不要换工作", 0.62, entries=es) is None


# ---------- 预警：该说话的时候 ----------

def test_gap_for_warns_on_overconfidence():
    es = [_e("yes", 0.9, "no")] * 6          # 6 条全错，置信 0.9
    w = cal.gap_for("要不要换工作", 0.9, entries=es)
    assert w is not None
    assert w["category"] == "工作"
    assert w["direction"] == "over"
    assert w["samples"] == 6
    assert "过去" in w["message"]


def test_gap_for_only_counts_same_category():
    es = ([_e("yes", 0.9, "no")] * 6)                        # 工作类
    es += [_e("yes", 0.9, "yes")] * 6                        # 别的类
    for e in es[6:]:
        e["nucleus"] = "要不要去聚餐"
    w = cal.gap_for("要不要换工作", 0.9, entries=es)
    assert w is not None
    assert w["category"] == "工作"
    assert w["samples"] == 6            # 不能把社交类的算进来


def test_message_has_no_advice():
    es = [_e("yes", 0.9, "no")] * 6
    w = cal.gap_for("要不要换工作", 0.9, entries=es)
    for forbidden in ["建议", "应该", "最好", "推荐", "也许你该"]:
        assert forbidden not in w["message"]


# ---------- 分组 ----------

def test_by_category_groups():
    es = [_e("yes", 0.9, "yes")] * 3 + [_e("yes", 0.9, "no")] * 3
    es += [_e("yes", 0.5, "yes")] * 2
    for e in es[6:]:
        e["nucleus"] = "要不要去聚餐"
    out = cal.by_category(es)
    cats = {x["category"]: x for x in out}
    assert cats["工作"]["samples"] == 6
    assert cats["工作"]["enough"] is True
    assert cats["社交"]["samples"] == 2
    assert cats["社交"]["enough"] is False
