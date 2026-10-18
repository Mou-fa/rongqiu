"""链长（推理深度）的测试。

理论：每多一级推理，确定性乘以 0.8。
0.8^1=80%  0.8^2=64%  0.8^3=51%  0.8^4=41%

所以链长超过 3，可确定部分就掉到一半以下，只能出暂定判定。
这条在代码里必须真的生效——不然「链长 ≤ 3」只是一句口号。
"""

from __future__ import annotations

import pytest

from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT, OPPOSE, DEPTH_DISCOUNT


def _facts(n, depth, supports=None):
    supports = supports or ([SUPPORT] * n)
    return [SceneFact(scene=f"场景{i}", supports=supports[i % len(supports)],
                      depth=depth, order=i) for i in range(n)]


def test_depth_one_is_unchanged():
    """深度 1 的判定必须和加链长之前完全一样，不能引入回归。"""
    node = Node(nucleus="我参加聚会", facts=_facts(5, 1))
    j = node.judge()
    assert j.n == pytest.approx(5.0)
    assert j.determinability == pytest.approx(5 / 7)


def test_depth_caps_the_whole_chain():
    """链长是整条推理的属性：深 3 级的判断，可确定上限就是 0.8^2。"""
    node = Node(nucleus="我参加聚会", facts=_facts(5, 3))
    j = node.judge()
    assert j.n == 5
    assert j.determinability == pytest.approx((5 / 7) * DEPTH_DISCOUNT ** 2)


def test_depth_four_drops_below_half():
    """链长 4 的时候可确定部分必须掉到一半以下，规则自动变成暂定。"""
    node = Node(nucleus="我参加聚会", facts=_facts(8, 4))
    j = node.judge()
    assert j.determinability < 0.5
    assert j.rule == "provisional"
    assert j.max_depth == 4


def test_mixed_depth_weights_more_for_shallower_evidence():
    """五条浅证据 + 五条深证据：方向应当由浅的那批决定。"""
    shallow = _facts(5, 1, [SUPPORT])
    deep = [SceneFact(scene=f"深{i}", supports=OPPOSE, depth=4, order=10 + i)
            for i in range(5)]
    j = Node(nucleus="我参加聚会", facts=shallow + deep).judge()
    assert j.lean == "yes"                    # 浅的权重更大
    assert j.support_ratio > 0.6


def test_depth_is_reported():
    j = Node(nucleus="x", facts=_facts(3, 2)).judge()
    assert j.max_depth == 2
    assert j.as_dict()["max_depth"] == 2
    assert j.as_dict()["over_depth"] is False
