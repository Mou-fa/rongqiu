"""原核 ↔ 世界：在三元组空间里找第一接触面。

为什么要先做结构预筛：互联网上的文本是海量的，不可能全部塞给模型。
但三元组的表示统一之后，可以先做一次廉价的字符重叠匹配，把候选从
几千条压到几十条，再让模型做语义层面的相关性判断。

这一步是骨架，不是装饰——没有它，绒球只能处理你手动喂给它的几段文本。
"""

from __future__ import annotations

from dataclasses import dataclass

from .nucleus import Nucleus


@dataclass
class Candidate:
    source: str
    text: str
    overlap: float

    def as_dict(self) -> dict:
        return {"source": self.source, "text": self.text, "overlap": round(self.overlap, 3)}


def _bigrams(s: str) -> set[str]:
    s = "".join(ch for ch in s if not ch.isspace())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def overlap(nucleus: Nucleus, text: str) -> float:
    """原核三元组和一段文本的字符二元组重叠度。

    中文没有空格，分词又依赖词典。二元组重叠是一个足够便宜、且不依赖
    外部词典的近似——用于把候选量级压下来，不用于最终判断。
    """
    core = _bigrams(f"{nucleus.agent}{nucleus.event}{nucleus.resource}")
    if not core:
        return 0.0
    body = _bigrams(text)
    if not body:
        return 0.0
    return len(core & body) / len(core)


def rank(nucleus: Nucleus, texts: list[tuple[str, str]],
         min_overlap: float = 0.15, limit: int = 12) -> list[Candidate]:
    scored = [Candidate(src, text, overlap(nucleus, text)) for src, text in texts]
    scored = [c for c in scored if c.overlap >= min_overlap]
    scored.sort(key=lambda c: -c.overlap)
    return scored[:limit]


def render(cands: list[Candidate]) -> str:
    if not cands:
        return "  （没有候选）"
    return "\n".join(f"  [{c.source:8s}] 重叠 {c.overlap:.2f}  {c.text[:48]}"
                     for c in cands)
