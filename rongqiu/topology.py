"""决策拓扑排序。

决定之间有依赖，而依赖是可以画的。

    「要不要换工作」  ← 面：我 可能要搬家 住处
    「要不要搬家」    ← 这一个在最上游

这个模块做的事：找出「一个决定的结果，会变成另一个决定的第一接触面」。

三条纪律：
1. 只画结构，不排优先级。输出是「A 影响 B」，不是「所以先做 A」。
2. 没有边就是没有边。宁可空着，不硬连。
3. 环要露出来。互相依赖的两个决定不是错误，是一种需要被看到的状态。

实现上的关键取舍：
原核解析是 LLM 调用，很贵。但日志里同一个问题会被问很多遍，
所以先按问题去重，再逐条解析，结果写进 data/nucleus_cache.json。
第二次起就是纯读文件，零成本。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import journal, nucleus

from .paths import DATA

CACHE = DATA / "nucleus_cache.json"

MAX_QUESTIONS = 40      # 最多解析这么多个不同问题
MIN_WORD = 2            # 少于两个字的词不当作依赖信号

_CLEAN = re.compile(r"[\s\u3000，。！？、；：「」『』（）【】《》\-—…·,.!?;:\"'()\[\]/]+")


def _norm(s: str) -> str:
    return _CLEAN.sub("", str(s or "")).lower()


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def parse_cached(question: str, cache: dict | None = None) -> dict:
    """解析一个问题的主谓宾。命中缓存不调模型。"""
    cache = cache if cache is not None else _load_cache()
    key = _norm(question)
    if key in cache:
        return cache[key]
    try:
        nu = nucleus.parse(question)
        data = {"agent": nu.agent, "event": nu.event,
                "resource": nu.resource or nu.resource_norm}
    except Exception:
        data = {"agent": "", "event": "", "resource": ""}
    cache[key] = data
    return data


@dataclass
class Node:
    id: str
    question: str
    resource: str = ""
    event: str = ""
    surfaces: list[str] = field(default_factory=list)
    resolved: bool = False

    def as_dict(self) -> dict:
        return {"id": self.id, "question": self.question,
                "resource": self.resource, "resolved": self.resolved}


@dataclass
class Edge:
    src: str      # 上游决定
    dst: str      # 下游决定
    via: str      # 靠哪个词连上的

    def as_dict(self) -> dict:
        return {"from": self.src, "to": self.dst, "via": self.via}


def _keywords(node: Node) -> list[str]:
    """一个决定可能成为别人接触面的词。资源优先，其次事件。"""
    out = []
    for w in (node.resource, node.event):
        w = _norm(w)
        if len(w) >= MIN_WORD:
            out.append(w)
    return out


def build_edges(nodes: list[Node]) -> list[Edge]:
    """A 的上游词出现在 B 的面文本里 → A 影响 B。

    只看用户自己说出的面（surfaces），不看问题文本——
    否则「我要不要搬家」自己就会和「搬家」这个资源自连。
    """
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for a in nodes:
        for b in nodes:
            if a.id == b.id:
                continue
            blob = _norm(" ".join(b.surfaces))
            if not blob:
                continue
            for w in _keywords(a):
                if w in blob:
                    key = (a.id, b.id)
                    if key not in seen:
                        seen.add(key)
                        edges.append(Edge(src=a.id, dst=b.id, via=w))
                    break
    return edges


def topo(nodes: list[Node], edges: list[Edge]) -> dict:
    """拓扑排序（上游在前）。有环就单独列出来，不假装能排。"""
    ids = [n.id for n in nodes]
    indeg = {i: 0 for i in ids}
    out: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        if e.src in indeg and e.dst in indeg:
            out[e.src].append(e.dst)
            indeg[e.dst] += 1

    order: list[str] = []
    queue = [i for i in ids if indeg[i] == 0]
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in out.get(cur, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)

    cycles = [i for i in ids if i not in order]
    return {"order": order, "cycles": cycles}


def analyze(parse_fn=None, limit: int = MAX_QUESTIONS) -> dict:
    """完整分析：读日志 → 去重解析 → 建边 → 排序。"""
    parse_fn = parse_fn or parse_cached
    cache = _load_cache()

    entries = journal.load()
    by_q: dict[str, dict] = {}
    for e in entries:
        q = (e.get("nucleus") or "").strip()
        if not q:
            continue
        k = _norm(q)
        if k not in by_q or (e.get("ts") or "") > (by_q[k].get("ts") or ""):
            by_q[k] = e

    items = sorted(by_q.values(), key=lambda e: e.get("ts") or "", reverse=True)[:limit]

    nodes: list[Node] = []
    for e in items:
        q = e.get("nucleus") or ""
        tri = parse_fn(q, cache)
        surfaces = []
        for f in e.get("facts") or []:
            if (f.get("source") or "") in ("主动询问",):
                continue
            s = (f.get("scene") or "").strip()
            if s:
                surfaces.append(s)
        nodes.append(Node(
            id=e.get("id", ""), question=q,
            resource=tri.get("resource", ""), event=tri.get("event", ""),
            surfaces=surfaces, resolved=bool(e.get("outcome")),
        ))
    _save_cache(cache)

    edges = build_edges(nodes)
    t = topo(nodes, edges)
    index = {n.id: n for n in nodes}
    return {
        "nodes": [n.as_dict() for n in nodes],
        "edges": [{"from": e.src, "to": e.dst, "via": e.via,
                   "from_q": index[e.src].question if e.src in index else "",
                   "to_q": index[e.dst].question if e.dst in index else ""}
                  for e in edges],
        "order": [{"id": i, "question": index[i].question}
                  for i in t["order"] if i in index],
        "cycles": [{"id": i, "question": index[i].question}
                   for i in t["cycles"] if i in index],
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }
