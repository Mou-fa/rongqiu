"""来源归并的测试。

注意：归并**不参与判定**了。

用户明确过：每勾选一个，就形成他自己的一个确定第一接触面，逐条算。
同源归并是用来处理「别人的观点被当成多份证据」的——但别人的观点本来
就不该进事实层（它们是提示，零权重）。所以判定里不再归并。

origin.py 保留为工具函数，用于将来的材料去重（同一件事被转述多次）。
"""

from __future__ import annotations

import pytest

from rongqiu import origin
from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT, OPPOSE


def _f(scene, supports, origin_id=-1, depth=1, order=0):
    return SceneFact(scene=scene, supports=supports, origin=origin_id,
                     depth=depth, order=order)


def test_every_confirmed_fact_counts_independently():
    """用户勾选 5 条 → N 就是 5，不因为「都来自用户」而被归并。"""
    facts = [_f(f"场景{i}", SUPPORT, order=i) for i in range(5)]
    j = Node(nucleus="x", facts=facts).judge()
    assert j.n == 5
    assert j.total_surfaces == 7          # 5 事实 + 1 假设 + 1 未知


def test_total_surfaces_matches_the_eight_one_one_shape():
    """8 条事实 → 10 个面，正好是 8:1:1。"""
    facts = [_f(f"场景{i}", SUPPORT, order=i) for i in range(8)]
    j = Node(nucleus="x", facts=facts).judge()
    assert j.total_surfaces == 10
    assert j.determinability == pytest.approx(0.8)
    s = j.split()
    assert s["assumption"] == pytest.approx(0.1)
    assert s["unknown"] == pytest.approx(0.1)


def test_counts_split_support_oppose_neutral():
    """三个数加起来必须等于总面数。

    中性只能存在于 11：假设 1 + 未知 1，永远是 2。
    事实层全是二元对立，判不出方向的不是事实，会被丢掉。
    """
    facts = [_f("a", SUPPORT, order=0), _f("b", SUPPORT, order=1),
             _f("c", OPPOSE, order=2), _f("d", "neutral", order=3)]
    j = Node(nucleus="x", facts=facts).judge()
    c = j.counts()
    assert c["support"] == 2
    assert c["oppose"] == 1
    assert c["neutral"] == 2              # 只有假设和未知
    assert sum(c.values()) == j.total_surfaces
    assert j.n == 3                       # 中性事实被丢掉了
    assert j.dropped == 1


def test_neutral_facts_are_dropped_from_n():
    """事实层不允许中性。判不出方向的，不进 N。"""
    facts = [_f("支持", SUPPORT, order=0), _f("中性", "neutral", order=1)]
    j = Node(nucleus="x", facts=facts).judge()
    assert j.n == 1
    assert j.total_surfaces == 3
    assert j.dropped == 1
    assert all(f.supports in ("support", "oppose") for f in j.facts)


def test_all_neutral_means_no_node():
    """全部都是中性 → 一条事实都没有 → 节点不成立。"""
    facts = [_f("中性A", "neutral", order=0), _f("中性B", "neutral", order=1)]
    assert Node(nucleus="x", facts=facts).judge() is None


def test_origin_field_no_longer_affects_the_judgment():
    """同样 5 条，无论 origin 是否相同，N 都是 5。"""
    same = [_f(f"场景{i}", SUPPORT, origin_id=0, order=i) for i in range(5)]
    diff = [_f(f"场景{i}", SUPPORT, origin_id=i, order=i) for i in range(5)]
    assert Node(nucleus="x", facts=same).judge().n == 5
    assert Node(nucleus="x", facts=diff).judge().n == 5


def test_cluster_utility_still_works(monkeypatch):
    """origin.cluster 作为工具函数仍然可用（将来做材料去重会用到）。"""
    monkeypatch.setattr(origin, "available", lambda cfg=None: False)
    scenes = [type("S", (), {"scene": "a", "source": "chat"})(),
              type("S", (), {"scene": "b", "source": "chat"})()]
    mapping = origin.cluster(scenes)
    assert origin.effective_count(mapping) == 2      # 不能归并时各算一个
