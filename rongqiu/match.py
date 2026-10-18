"""原核 ↔ 世界：按主谓宾成分做匹配。

不是实体归一化，是成分匹配。用户问题的三元组提取时已经剥掉了时间和修饰语：

    「我能不能去参加今晚的聚会」→ 我 · 参加 · 聚会

然后拿这三个成分去全网文本里找。文本里同时出现「我」「参加」「聚会」的，
就是候选第一接触面。

不需要判断「今晚的聚会」和「周五晚上聚会」是不是同一个实体——
提取阶段已经把修饰语扔掉了，剩下的三个成分就是匹配键。
"""

from __future__ import annotations

from dataclasses import dataclass

from .nucleus import Nucleus


@dataclass
class Candidate:
    source: str
    text: str
    hits: int          # 命中了几个成分（0-3）
    matched: list      # 命中的成分

    @property
    def overlap(self) -> float:
        return self.hits / 3.0

    def as_dict(self) -> dict:
        return {"source": self.source, "text": self.text,
                "hits": self.hits, "matched": self.matched}


def components(nucleus: Nucleus) -> list[tuple[str, str]]:
    return [("agent", nucleus.agent), ("event", nucleus.event),
            ("resource", nucleus.resource)]


def rank(nucleus: Nucleus, texts: list[tuple[str, str]],
         min_hits: int = 2, limit: int = 20) -> list[Candidate]:
    """按命中的成分数排序。至少命中 min_hits 个才算候选。"""
    out = []
    for src, text in texts:
        matched = [name for name, value in components(nucleus)
                   if value and value in text]
        if len(matched) >= min_hits:
            out.append(Candidate(src, text, len(matched), matched))
    out.sort(key=lambda c: -c.hits)
    return out[:limit]


def render(cands: list[Candidate]) -> str:
    if not cands:
        return "  （没有候选：没有文本同时命中足够多的主谓宾成分）"
    return "\n".join(
        f"  [{c.source:8s}] 命中 {c.hits}/3 {'+'.join(c.matched):22s} {c.text[:44]}"
        for c in cands)
