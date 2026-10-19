"""决策拓扑排序。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rongqiu import topology as tp  # noqa: E402


def _n(id_, q, resource="", event="", surfaces=None, resolved=False):
    return tp.Node(id=id_, question=q, resource=resource, event=event,
                   surfaces=surfaces or [], resolved=resolved)


# ---------- 建边 ----------

def test_edge_when_resource_in_surface():
    # 「搬家」这个决定，出现在「换工作」的面里
    a = _n("a", "要不要搬家", resource="住处")
    b = _n("b", "要不要换工作", resource="工作",
           surfaces=["我 可能要搬家 住处"])
    edges = tp.build_edges([a, b])
    assert len(edges) == 1
    assert edges[0].src == "a" and edges[0].dst == "b"
    assert edges[0].via == "住处"


def test_no_edge_when_unrelated():
    a = _n("a", "要不要搬家", resource="住处")
    b = _n("b", "要不要换工作", resource="工作",
           surfaces=["我 最近很累 状态"])
    assert tp.build_edges([a, b]) == []


def test_no_self_edge():
    a = _n("a", "要不要搬家", resource="搬家",
           surfaces=["我 要搬家 住处"])
    # 自己提到自己的资源，不能连成自环
    assert [e for e in tp.build_edges([a]) if e.src == e.dst] == []


def test_short_words_ignored():
    # 一个字的资源不当作依赖信号
    a = _n("a", "要不要买", resource="钱")
    b = _n("b", "要不要换工作", surfaces=["我 钱紧 钱包"])
    # 「钱」只有一个字，MIN_WORD=2，不该连
    assert tp.build_edges([a, b]) == []


# ---------- 排序 ----------

def test_topo_chain():
    a, b, c = (_n("a", "A"), _n("b", "B"), _n("c", "C"))
    edges = [tp.Edge("a", "b", "x"), tp.Edge("b", "c", "y")]
    t = tp.topo([a, b, c], edges)
    assert t["order"] == ["a", "b", "c"]
    assert t["cycles"] == []


def test_topo_detects_cycle():
    a, b = _n("a", "A"), _n("b", "B")
    edges = [tp.Edge("a", "b", "x"), tp.Edge("b", "a", "y")]
    t = tp.topo([a, b], edges)
    # 互相依赖的两个决定，不该被硬排成一条链
    assert t["cycles"] and set(t["cycles"]) == {"a", "b"}


# ---------- 完整分析（注入假解析器，不调模型） ----------

def test_analyze_with_fake_parser(monkeypatch):
    entries = [
        {"id": "1", "nucleus": "要不要搬家", "ts": "2026-10-19T10:00:00+08:00",
         "outcome": None, "facts": [
             {"scene": "我 住处 远", "source": "用户自述"}]},
        {"id": "2", "nucleus": "要不要换工作", "ts": "2026-10-19T11:00:00+08:00",
         "outcome": None, "facts": [
             {"scene": "我 可能要搬家 住处", "source": "用户自述"},
             {"scene": "你上一次遇到这种情况？", "source": "主动询问"}]},
    ]
    monkeypatch.setattr(tp.journal, "load", lambda: entries)

    table = {
        "要不要搬家": {"agent": "我", "event": "搬迁", "resource": "住处"},
        "要不要换工作": {"agent": "我", "event": "更换", "resource": "工作"},
    }

    def fake_parse(q, cache=None):
        return table.get(q, {"agent": "", "event": "", "resource": ""})

    out = tp.analyze(parse_fn=fake_parse)
    assert out["total_nodes"] == 2
    assert out["total_edges"] == 1
    assert out["edges"][0]["from"] == "1"
    assert out["edges"][0]["to"] == "2"
    # 主动询问的面不能参与依赖判定
    assert all("主动询问" not in str(n) for n in out["nodes"])
    # 输出里不能有建议
    blob = str(out)
    for forbidden in ["建议", "应该", "最好", "推荐"]:
        assert forbidden not in blob


def test_analyze_dedupes_same_question(monkeypatch):
    entries = [
        {"id": str(i), "nucleus": "要不要换工作",
         "ts": f"2026-10-19T1{i}:00:00+08:00", "outcome": None,
         "facts": [{"scene": "我 最近很累 状态", "source": "用户自述"}]}
        for i in range(5)
    ]
    monkeypatch.setattr(tp.journal, "load", lambda: entries)
    out = tp.analyze(parse_fn=lambda q, c=None: {"resource": "工作", "event": "更换"})
    # 同一个问题问五遍，只是一个节点
    assert out["total_nodes"] == 1
