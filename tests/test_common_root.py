"""跨决定共同根因。

核心断言：
    1. 同一个面换个说法能认出来
    2. 不同的面不能误认
    3. 通用问句（主动询问）绝不能算共同根因
    4. 少于两条决定不成组
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rongqiu import common_root as cr  # noqa: E402


# ---------- 归一化与相似度 ----------

def test_normalize_strips_punct():
    assert cr._normalize("我 头不舒服 身体") == "我头不舒服身体"
    assert cr._normalize("我，头不舒服。身体！") == "我头不舒服身体"


def test_same_surface_different_wording():
    # 完全一致
    assert cr.similar("我 最近很累 状态", "我 最近很累 状态")
    # 谓语被省略：主宾一致，谓语包含
    assert cr.similar("我 最近很累 状态", "我 很累 状态")
    # 谓语被截断
    assert cr.similar("我 身体不舒服 身体", "我 不舒服 身体")


def test_opposite_predicate_not_matched():
    # 主宾一样，谓语相反 —— 不是同一个面
    assert not cr.similar("我 最近很累 状态", "我 最近很开心 状态")


def test_different_surface_not_matched():
    assert not cr.similar("我 最近很累 状态", "老张 邀请了我 聚餐")
    assert not cr.similar("我 钱包紧张 钱", "我 最近很累 状态")


# ---------- 只认用户自己的面 ----------

def _entry(id_, nucleus, facts):
    return {"id": id_, "nucleus": nucleus, "ts": "2026-10-19T10:00:00+08:00",
            "outcome": None, "facts": facts}


def test_generic_questions_excluded():
    e = _entry("a", "要不要去聚餐", [
        {"scene": "你上一次遇到这种情况，最后怎么选的？（答：是）",
         "source": "主动询问"},
        {"scene": "我 最近很累 状态", "source": "用户自述"},
    ])
    ss = cr.surfaces_of(e)
    assert ss == ["我 最近很累 状态"]


def test_only_user_sources():
    e = _entry("a", "x", [
        {"scene": "我 最近很累 状态", "source": "用户自述"},
        {"scene": "某篇网文说年轻人应该躺平", "source": "全网"},
        {"scene": "老同学邀你参加聚餐", "source": "认领"},
    ])
    ss = cr.surfaces_of(e)
    assert ss == ["我 最近很累 状态"]


def test_short_surface_dropped():
    e = _entry("a", "x", [{"scene": "我", "source": "用户自述"}])
    assert cr.surfaces_of(e) == []


# ---------- 成组 ----------

def _d(id_, q, surfaces, resolved=False):
    return cr.Decision(id=id_, question=q, ts="2026-10-19T10:00:00+08:00",
                       resolved=resolved, surfaces=surfaces)


def test_group_of_three():
    # 三条记录里模型对同一个事实写了两种长度
    ds = [
        _d("1", "要不要去聚餐", ["我 最近很累 状态"]),
        _d("2", "要不要接这个活", ["我 最近很累 状态"]),
        _d("3", "周末要不要出门", ["我 很累 状态"]),
    ]
    groups = cr.find_groups(ds)
    assert len(groups) == 1
    assert len(groups[0].decisions) == 3


def test_no_common_root():
    ds = [
        _d("1", "要不要换工作", ["我 钱包很紧 钱"]),
        _d("2", "要不要去聚餐", ["老张 邀请我 聚餐"]),
    ]
    assert cr.find_groups(ds) == []


def test_same_question_repeated_is_not_a_group():
    """同一个问题问十遍，是反复纠结，不是跨决定共同根因。"""
    ds = [
        _d("1", "今晚身体不舒服，能不能去聚餐？", ["我 身体不舒服 身体"]),
        _d("2", "今晚身体不舒服，能不能去聚餐？", ["我 身体不舒服 身体"]),
        _d("3", "今晚身体不舒服，能不能去聚餐？", ["我 身体不舒服 身体"]),
    ]
    assert cr.find_groups(ds) == []


def test_two_different_questions_share_surface():
    ds = [
        _d("1", "最近很累，要不要换工作？", ["我 最近很累 状态"]),
        _d("2", "最近很累，要不要接这个新项目？", ["我 最近很累 状态"]),
        _d("3", "最近很累，要不要换工作？", ["我 最近很累 状态"]),   # 重复问
    ]
    groups = cr.find_groups(ds)
    assert len(groups) == 1
    assert len(groups[0].decisions) == 2   # 去重后两个不同问题


def test_single_decision_not_a_group():
    ds = [_d("1", "要不要去聚餐", ["我 最近很累 状态"])]
    assert cr.find_groups(ds) == []


def test_group_shape():
    ds = [
        _d("1", "要不要去聚餐", ["我 最近很累 状态"]),
        _d("2", "要不要接这个活", ["我 最近很累 状态"]),
    ]
    g = cr.find_groups(ds)[0].as_dict()
    assert g["count"] == 2
    assert g["surface"]
    assert {x["question"] for x in g["decisions"]} == {"要不要去聚餐", "要不要接这个活"}
    # 只陈述结构，不得出现建议
    blob = str(g)
    for forbidden in ["建议", "应该", "最好", "推荐"]:
        assert forbidden not in blob


def test_groups_sorted_by_size():
    ds = [
        _d("1", "A", ["我 最近很累 状态"]),
        _d("2", "B", ["我 最近很累 状态"]),
        _d("3", "C", ["我 最近很累 状态"]),
        _d("4", "D", ["我 钱包很紧 钱"]),
        _d("5", "E", ["我 钱包很紧 钱"]),
    ]
    groups = cr.find_groups(ds)
    assert len(groups) == 2
    assert len(groups[0].decisions) == 3   # 大的排前面
