"""N11 节点：绒球的最小判断单元。

结构：
    N 个事实（溯源通过，进确定槽）
    + 1 个假设
    + 1 个未知

判定：
    可确定比例 = N/(N+2)
    > 50%（N>=3）→ 直接判定，11 不启动
    <= 50%（N<=2）→ 核算 11，出暂定判定
    无弃权，永远给二元倾向
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .triples import Triple, SUPPORT, OPPOSE

MAX_CONFIDENCE = 0.8     # 811：任何判断不超过 0.8


@dataclass
class Judgment:
    nucleus: str
    lean: str                 # "yes" | "no"
    confidence: float
    n: int
    determinability: float
    support_ratio: float
    rule: str                 # "direct" | "provisional"
    assumption: str
    unknown: str
    facts: list[Triple] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "nucleus": self.nucleus, "lean": self.lean,
            "confidence": round(self.confidence, 4),
            "n": self.n, "determinability": round(self.determinability, 4),
            "support_ratio": round(self.support_ratio, 4),
            "rule": self.rule,
            "assumption": self.assumption, "unknown": self.unknown,
            "facts": [f.as_dict() for f in self.facts],
        }

    def render(self) -> str:
        side = "会" if self.lean == "yes" else "不会"
        lines = [
            f"原核：{self.nucleus}",
            f"倾向：{side}（置信 {self.confidence:.2f}）",
            f"N = {self.n}  可确定 = {self.n}/{self.n + 2} = {self.determinability:.0%}"
            f"  支持率 = {self.support_ratio:.0%}",
            f"规则：{self.rule}",
            "",
            "确定槽：",
        ]
        for f in self.facts:
            mark = "+" if f.supports == SUPPORT else ("-" if f.supports == OPPOSE else "0")
            lines.append(f"  [{f.grade}] {mark} {f.as_text()}  （{f.source}）")
        if self.assumption:
            lines.append(f"假设槽：{self.assumption}")
        if self.unknown:
            lines.append(f"未知槽：{self.unknown}")
        if self.reason:
            lines.append(f"平票理由：{self.reason}")
        return "\n".join(lines)


@dataclass
class Node:
    nucleus: str
    facts: list[Triple]
    assumption: str = ""
    unknown: str = ""

    @property
    def n(self) -> int:
        return len([f for f in self.facts if f.supports in (SUPPORT, OPPOSE)])

    @property
    def determinability(self) -> float:
        return self.n / (self.n + 2)

    def judge(self, tie_break_lean: str = "", tie_break_reason: str = "") -> Judgment | None:
        directional = [f for f in self.facts if f.supports in (SUPPORT, OPPOSE)]
        n = len(directional)
        if n == 0:
            return None          # 节点不成立：没有任何可判定的方向信息
        yes = len([f for f in directional if f.supports == SUPPORT])
        ratio = yes / n

        rule = "direct" if n / (n + 2) > 0.5 else "provisional"
        if abs(ratio - 0.5) < 1e-9:
            # 平票：无弃权，交给 11 决定。
            # 假设槽和未知槽必须给出一个方向，否则二元判定没有依据。
            lean = tie_break_lean or "no"
            rule = "tie_break_11"
            reason = tie_break_reason or "平票，由假设与未知槽决定"
        else:
            lean = "yes" if ratio > 0.5 else "no"
            reason = ""

        det = n / (n + 2)
        confidence = min(det * (0.5 + abs(ratio - 0.5)), MAX_CONFIDENCE)
        if rule == "tie_break_11":
            confidence = min(confidence, 0.5)   # 平票的判断不该比一半更自信
        return Judgment(
            nucleus=self.nucleus, lean=lean, confidence=confidence,
            n=n, determinability=det, support_ratio=ratio, rule=rule,
            assumption=self.assumption, unknown=self.unknown,
            facts=directional, reason=reason,
        )


def build(question: str, extraction, trace_mod, include_assumptions: bool = False,
          require_independence: bool = True) -> Node:
    """把一次抽取组织成 N11 节点。

    include_assumptions=False 时只让溯源通过的进确定槽（严格按 811）。
    设为 True 时，L1/L2 的事实也参与投票，但在输出里标出来——用于对比
    「严格溯源」和「宽松溯源」两种判定的差别。
    """
    facts, assume_extra, unknown_extra = [], [], []
    n_agents, n_sources = trace_mod.independence_pool(extraction.facts)
    independent = require_independence and max(n_agents, n_sources) >= 2
    for t in extraction.facts:
        slot = trace_mod.classify(t, pool_independent=independent)
        if slot == "confirmed":
            facts.append(t)
        elif slot == "assumption":
            if include_assumptions:
                facts.append(t)
            assume_extra.append(t.as_text())

    assumption = extraction.assumption
    if assume_extra:
        assumption = (assumption + "；" if assumption else "") + "未溯源：" + "、".join(assume_extra[:3])
    unknown = extraction.unknown
    if unknown_extra:
        unknown = (unknown + "；" if unknown else "") + "、".join(unknown_extra[:3])
    return Node(nucleus=question, facts=facts, assumption=assumption, unknown=unknown)
