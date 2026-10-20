"""翻转阈值：只陈述「还差几条事实」，不是建议。"""

from __future__ import annotations

from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT, OPPOSE


def _f(supports, depth=1, scene="s"):
    return SceneFact(scene=scene, supports=supports, source="用户自述",
                     order=0, depth=depth)


def _judge(facts):
    return Node(nucleus="我会去聚餐吗", facts=facts).judge()


def test_flip_support_majority():
    j = _judge([_f(SUPPORT, scene="a"), _f(SUPPORT, scene="b"), _f(OPPOSE, scene="c")])
    f = j.flip_distance()
    assert f["lean"] == "yes"
    assert f["direction"] == "oppose"
    # 2:1，再加 1 条反对会平票（交给 11），再加第 2 条才确定翻转
    assert f["need"] == 2


def test_flip_oppose_majority():
    j = _judge([_f(SUPPORT, scene="a"), _f(OPPOSE, scene="b"), _f(OPPOSE, scene="c")])
    f = j.flip_distance()
    assert f["lean"] == "no"
    assert f["direction"] == "support"
    assert f["need"] == 2


def test_flip_on_tie_needs_one():
    j = _judge([_f(SUPPORT, scene="a"), _f(OPPOSE, scene="b")])
    f = j.flip_distance()
    # 平票由 11 决定方向；再加一条同向就明确翻转
    assert f["need"] == 1


def test_flip_respects_depth_weight():
    # 0.8 vs 1.0：当前倾向 no；再加 1 条支持（权重 1）就明确翻转
    j = _judge([_f(SUPPORT, depth=2, scene="a"), _f(OPPOSE, depth=1, scene="b")])
    f = j.flip_distance()
    assert f["lean"] == "no"
    assert f["need"] == 1


def test_flip_in_judgment_dict():
    j = _judge([_f(SUPPORT), _f(OPPOSE)])
    d = j.as_dict()
    assert "flip" in d and d["flip"]["need"] >= 1
