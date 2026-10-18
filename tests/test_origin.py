"""来源归并的测试。

三个朋友在同一个群里说同一件事，标签上是三个来源，实质是一份证据。
不归并的话 N 会被抬虚，置信度跟着虚高。
"""

from __future__ import annotations

import pytest

from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT, OPPOSE


def _f(scene, supports, origin=-1, depth=1, order=0):
    return SceneFact(scene=scene, supports=supports, origin=origin,
                     depth=depth, order=order)


def test_same_origin_facts_count_once():
    """三条同源的支持 + 两条独立反对：独立源头是 3 个，不是 5 个。"""
    facts = [
        _f("群友A说聚会好玩", SUPPORT, origin=0, order=0),
        _f("群友B说聚会好玩", SUPPORT, origin=0, order=1),
        _f("群友C说聚会好玩", SUPPORT, origin=0, order=2),
        _f("我很累", OPPOSE, origin=1, order=3),
        _f("有别的安排", OPPOSE, origin=2, order=4),
    ]
    j = Node(nucleus="我参加聚会", facts=facts).judge()
    assert j.n == 3            # 同源的三条只算一份
    assert j.n_raw == 5
    assert j.support_ratio == pytest.approx(1 / 3)
    assert j.lean == "no"


def test_without_origin_each_fact_counts():
    facts = [_f(f"场景{i}", SUPPORT, order=i) for i in range(5)]
    j = Node(nucleus="x", facts=facts).judge()
    assert j.n == 5


def test_origin_group_votes_with_majority():
    """同一个源头里意见不一致时，组内按加权多数表态。"""
    facts = [
        _f("同源支持A", SUPPORT, origin=0, order=0),
        _f("同源支持B", SUPPORT, origin=0, order=1),
        _f("同源反对C", OPPOSE, origin=0, order=2),
        _f("独立反对", OPPOSE, origin=1, order=3),
    ]
    j = Node(nucleus="x", facts=facts).judge()
    assert j.n == 2
    assert j.support_ratio == pytest.approx(0.5)   # 1:1，平票


def test_depth_weights_origin_votes():
    """同一个方向，浅源头的票比深源头重。"""
    facts = [
        _f("浅支持", SUPPORT, origin=0, depth=1, order=0),
        _f("深反对", OPPOSE, origin=1, depth=4, order=1),
    ]
    j = Node(nucleus="x", facts=facts).judge()
    assert j.lean == "yes"           # 浅的权重 1.0 > 深的 0.512
    assert j.support_ratio > 0.6
