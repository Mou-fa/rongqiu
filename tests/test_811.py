"""811 结构本身的测试。

N 不是我们设定的参数，是第一接触面的实际数量。但无论 N 多大，
可确定部分都不能超过 80%——否则就突破了 811。
"""

from __future__ import annotations

import pytest

from rongqiu.node import MAX_DETERMINABILITY, Node
from rongqiu.triples import SceneFact, SUPPORT


def _n_facts(n):
    return [SceneFact(scene=f"场景{i}", supports=SUPPORT, origin=i, order=i)
            for i in range(n)]


def test_nine_surfaces_are_capped_at_eighty_percent():
    """N=9 时 n/(n+2)=82%，必须被压回 80%。"""
    j = Node(nucleus="x", facts=_n_facts(9)).judge()
    assert j.determinability == pytest.approx(MAX_DETERMINABILITY)


def test_many_surfaces_never_exceed_eighty_percent():
    """N 再大也不能突破。这就是 811 恒不变的含义。"""
    for n in (20, 50, 200):
        j = Node(nucleus="x", facts=_n_facts(n)).judge()
        assert j.determinability == pytest.approx(MAX_DETERMINABILITY)


def test_small_n_is_still_below_the_cap():
    """N=3 时 n/(n+2)=60%，在封顶之下，按实际算。"""
    j = Node(nucleus="x", facts=_n_facts(3)).judge()
    assert j.determinability == pytest.approx(3 / 5)


def test_split_always_sums_to_one():
    for n in (2, 5, 8, 30, 100):
        s = Node(nucleus="x", facts=_n_facts(n)).judge().split()
        assert s["determinable"] + s["assumption"] + s["unknown"] == pytest.approx(1.0)


def test_standard_form_is_exactly_eight_one_one():
    """N>=8 时结构正好是 8:1:1。"""
    s = Node(nucleus="x", facts=_n_facts(8)).judge().split()
    assert s["determinable"] == pytest.approx(0.8)
    assert s["assumption"] == pytest.approx(0.1)
    assert s["unknown"] == pytest.approx(0.1)


def test_assumption_and_unknown_are_always_equal():
    """假设和未知永远对半分，这是结构恒定性。"""
    for n in (2, 4, 12):
        s = Node(nucleus="x", facts=_n_facts(n)).judge().split()
        assert s["assumption"] == pytest.approx(s["unknown"])
