"""判断漂移。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rongqiu import drift  # noqa: E402


def _e(id_, ts, lean, conf, facts, q="要不要换工作"):
    return {"id": id_, "ts": ts, "nucleus": q, "lean": lean, "confidence": conf,
            "n": len(facts), "outcome": None,
            "facts": [{"scene": s, "source": "用户自述"} for s in facts]}


# ---------- 时间间隔 ----------

def test_too_close_is_not_drift():
    a = _e("1", "2026-10-19T10:00:00+08:00", "yes", 0.6, ["我 最近很累 状态"])
    b = _e("2", "2026-10-19T10:05:00+08:00", "no", 0.6, ["我 最近很累 状态"])
    # 五分钟内问两次，是反复纠结，不是漂移
    assert drift.compare(a, b) is None


def test_enough_gap_counts():
    a = _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.8, ["我 最近很累 状态"])
    b = _e("2", "2026-10-19T10:00:00+08:00", "no", 0.8, ["我 最近很累 状态"])
    c = drift.compare(a, b)
    assert c is not None
    assert c["gap_hours"] == 24.0


# ---------- 分类 ----------

def test_facts_changed():
    a = _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.6, ["我 最近很累 状态"])
    b = _e("2", "2026-10-19T10:00:00+08:00", "yes", 0.6,
           ["我 最近很累 状态", "老板 批准了 请假"])
    c = drift.compare(a, b)
    assert c["kind"] == "facts"
    assert c["added_count"] == 1


def test_self_changed_by_flip():
    a = _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.6, ["我 最近很累 状态"])
    b = _e("2", "2026-10-19T10:00:00+08:00", "no", 0.6, ["我 最近很累 状态"])
    c = drift.compare(a, b)
    assert c["kind"] == "self"
    assert c["flipped"] is True


def test_self_changed_by_confidence():
    a = _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.9, ["我 最近很累 状态"])
    b = _e("2", "2026-10-19T10:00:00+08:00", "yes", 0.6, ["我 最近很累 状态"])
    c = drift.compare(a, b)
    assert c["kind"] == "self"
    assert c["confidence_delta"] < 0


def test_no_change_is_none():
    a = _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.6, ["我 最近很累 状态"])
    b = _e("2", "2026-10-19T10:00:00+08:00", "yes", 0.62, ["我 最近很累 状态"])
    assert drift.compare(a, b) is None


# ---------- 文案 ----------

def test_messages_have_no_advice():
    a = _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.8, ["我 最近很累 状态"])
    for b in [
        _e("2", "2026-10-19T10:00:00+08:00", "no", 0.8, ["我 最近很累 状态"]),
        _e("2", "2026-10-19T10:00:00+08:00", "yes", 0.8,
           ["我 最近很累 状态", "老板 批准了 请假"]),
    ]:
        c = drift.compare(a, b)
        msg = drift._message("要不要换工作", c)
        for forbidden in ["建议", "应该", "最好", "推荐", "你该"]:
            assert forbidden not in msg, f"文案里不该出现「{forbidden}」：{msg}"


def test_message_facts_kind():
    a = _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.6, ["我 最近很累 状态"])
    b = _e("2", "2026-10-19T10:00:00+08:00", "yes", 0.6,
           ["我 最近很累 状态", "老板 批准了 请假"])
    c = drift.compare(a, b)
    assert "事实变了" in drift._message("q", c)


# ---------- 整体检测 ----------

def test_detect_groups_and_sorts(monkeypatch):
    entries = [
        # 事实变了，间隔 24h
        _e("1", "2026-10-18T10:00:00+08:00", "yes", 0.6, ["我 最近很累 状态"]),
        _e("2", "2026-10-19T10:00:00+08:00", "yes", 0.6,
           ["我 最近很累 状态", "老板 批准了 请假"]),
        # 同一问题五分钟内又问一次 —— 不该产生额外条目
        _e("3", "2026-10-19T10:05:00+08:00", "yes", 0.6,
           ["我 最近很累 状态", "老板 批准了 请假"]),
        # 另一个问题，只问过一次
        _e("4", "2026-10-18T10:00:00+08:00", "no", 0.5, ["我 钱包紧 钱"],
           q="要不要买手机"),
    ]
    monkeypatch.setattr(drift.journal, "load", lambda: entries)
    out = drift.detect()
    assert len(out) == 1
    assert out[0]["kind"] == "facts"
    assert out[0]["question"] == "要不要换工作"
