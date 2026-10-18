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

from .triples import Triple, SUPPORT, OPPOSE, DEPTH_DISCOUNT, MAX_DEPTH

MAX_CONFIDENCE = 0.8        # 811：任何判断不超过 0.8
MAX_DETERMINABILITY = 0.8   # 811：可确定部分的上限也是 0.8

# N 不是我们设定的，是第一接触面的实际数量——由那个事物本身决定。
# 一个复杂事物的接触面数量不固定，系统只能去发现它。
# 但无论 N 多大，可确定部分都不会超过 80%：N/(N+2) 会趋近 1，
# 所以必须封顶，否则就突破了 811。
#   剩下的 10% 是假设、10% 是未知，这两份永远存在。


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
    max_depth: int = 1
    n_raw: int = 0          # 归并前的材料条数，用于展示「有多少条同源」

    def as_dict(self) -> dict:
        return {
            "nucleus": self.nucleus, "lean": self.lean,
            "confidence": round(self.confidence, 4),
            "n": self.n, "n_raw": self.n_raw,
            "total_surfaces": self.total_surfaces,
            "counts": self.counts(),
            "determinability": round(self.determinability, 4),
            # 811 的三段结构：可确定 / 假设 / 未知。后两段永远是固定的 10%。
            "split": self.split(),
            "support_ratio": round(self.support_ratio, 4),
            "rule": self.rule, "max_depth": self.max_depth,
            "over_depth": self.max_depth > MAX_DEPTH,
            "assumption": self.assumption, "unknown": self.unknown,
            "facts": [f.as_dict() for f in self.facts],
        }

    @property
    def total_surfaces(self) -> int:
        """总面数 = 事实面 + 假设 1 + 未知 1。

        用户说的「第一接触面」是这个数：8 条事实对应 10 个面。
        """
        return self.n + 2

    def counts(self) -> dict:
        """支持 / 反对 / 中性，三个数加起来等于总面数。

        中性不只是「事实里判成中性的」，还包括假设和未知这两个槽——
        它们同样是第一接触面，只是永远没有方向。所以：
            support + oppose + neutral = n + 2

        第一版只数了事实里的中性，三个数加起来是 n，和界面上显示的总面数
        对不上，用户一眼就看出来了。
        """
        s = sum(1 for f in self.facts if f.supports == SUPPORT)
        o = sum(1 for f in self.facts if f.supports == OPPOSE)
        n_facts = len(self.facts)
        # 假设 1 + 未知 1 = 2 个没有方向的固定面
        return {"support": s, "oppose": o, "neutral": (n_facts - s - o) + 2}

    def split(self) -> dict:
        """811 的三段结构。

        N 达到 8 或以上时可确定封顶 80%，剩下 20% 按 1:1 分为假设和未知，
        正好是 8:1:1。N 不足 8 时可确定更小，剩下的部分仍然按 1:1 分——
        假设和未知永远对半分，这是结构的恒定性。
        """
        det = self.determinability
        rest = max(0.0, 1.0 - det) / 2
        # 不在这里取整：三段各自取整会让总和变成 1.0001 之类，
        # 而这三段相加必须严格等于 1。展示时再格式化。
        return {"determinable": det, "assumption": rest, "unknown": rest}

    def render(self) -> str:
        side = "会" if self.lean == "yes" else "不会"
        lines = [
            f"原核：{self.nucleus}",
            f"倾向：{side}（置信 {self.confidence:.2f}）",
            (f"第一接触面 = {self.total_surfaces} 个面"
             f"（{self.n} 条事实 + 1 假设 + 1 未知）")
            + (lambda s: f"  可确定 {s['determinable']:.0%} : "
                         f"假设 {s['assumption']:.0%} : 未知 {s['unknown']:.0%}")(self.split())
            + f"  支持率 {self.support_ratio:.0%}",
            f"链长 = {self.max_depth}"
            + ("  ⚠ 超过 3 级，确定性已降到一半以下" if self.max_depth > MAX_DEPTH else ""),
            f"规则：{self.rule}",
            "",
            "确定槽：",
        ]
        for f in self.facts:
            mark = "+" if f.supports == SUPPORT else ("-" if f.supports == OPPOSE else "0")
            freq = f" {f.frequency:.0%}" if f.frequency < 1.0 else ""
            lines.append(f"  [{f.grade}] {mark} {f.as_text()}  （{f.source}{freq}）")
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
        """事实面数量 = 用户确认过的每一条，逐条算。

        不再做同源归并：那是用来防「别人的观点被当成多份证据」的。
        而用户勾选的每一条，是他对自己情况的每一次独立确认，不该被合并。
        第一版把它们归并了，界面上就出现「第一接触面 3，支持/反对 4/1」
        这种自相矛盾的数字。
        """
        return len(self.facts)

    @property
    def determinability(self) -> float:
        return self.n / (self.n + 2)

    def judge(self, tie_break_lean: str = "", tie_break_reason: str = "") -> Judgment | None:
        facts = list(self.facts)
        n = len(facts)
        if n == 0:
            return None

        directional = [f for f in facts if f.supports in (SUPPORT, OPPOSE)]
        weights_of = lambda f: DEPTH_DISCOUNT ** (max(getattr(f, "depth", 1), 1) - 1)

        # 方向只看有方向的那部分；但 N 算全部确认过的事实面。
        # 一条中性的事实不改变方向，但它确实是用户确认过的一个接触面，
        # 所以它算进 N，让「可确定比例」反映观察的丰富程度。
        if directional:
            total_w = sum(weights_of(f) for f in directional)
            yes_w = sum(weights_of(f) for f in directional if f.supports == SUPPORT)
            ratio = yes_w / total_w if total_w else 0.5
        else:
            ratio = 0.5

        max_depth = max(getattr(f, "depth", 1) for f in facts)

        # 链长是整条推理的属性，不是单条事实的属性。
        # 一条链深 4 级的判断，可确定部分上限就是 0.8^3 = 51%——
        # 哪怕你有 8 条证据，它们本身也都是转述了三手的。
        depth_factor = DEPTH_DISCOUNT ** (max_depth - 1)
        # 封顶到 0.8：N 再多，可确定部分也不会超过 80%
        base_det = min(n / (n + 2), MAX_DETERMINABILITY)
        rule = "direct" if base_det * depth_factor > 0.5 else "provisional"
        if abs(ratio - 0.5) < 1e-9:
            # 平票：无弃权，交给 11 决定。
            # 假设槽和未知槽必须给出一个方向，否则二元判定没有依据。
            lean = tie_break_lean or "no"
            rule = "tie_break_11"
            reason = tie_break_reason or "平票，由假设与未知槽决定"
        else:
            lean = "yes" if ratio > 0.5 else "no"
            reason = ""

        det = base_det * depth_factor
        confidence = min(det * (0.5 + abs(ratio - 0.5)), MAX_CONFIDENCE)
        if rule == "tie_break_11":
            confidence = min(confidence, 0.5)   # 平票的判断不该比一半更自信
        return Judgment(
            nucleus=self.nucleus, lean=lean, confidence=confidence,
            n=n, determinability=det, support_ratio=ratio, rule=rule,
            assumption=self.assumption, unknown=self.unknown,
            facts=facts, reason=reason,
            max_depth=max_depth, n_raw=n,
        )


@dataclass
class SlotReport:
    """一条事实的去向。展示层必须用这个，不能自己另算一套判据——
    第一版就是两套判据不一致，界面上显示两条进了确定槽，实际进入节点的是零条。"""
    text: str
    slot: str          # confirmed / assumption / unknown / dropped
    reason: str
    supports: str
    grade: str
    shares: str


def build_from_review(question: str, scenes: list, assumption: str = "",
                      unknown: str = "") -> Node:
    """人工勾选过的场景直接组节点。不再走 trace 分级——因为每一条
    都是用户亲自确认过的，等级由来源决定，不由模型猜。"""
    return Node(nucleus=question, facts=list(scenes),
                assumption=assumption, unknown=unknown)


def build(question: str, extraction, trace_mod, include_assumptions: bool = False,
          require_independence: bool = True, nucleus_resource: str = "",
          report: list | None = None) -> Node:
    """把一次抽取组织成 N11 节点。

    include_assumptions=False 时只让溯源通过的进确定槽（严格按 811）。
    设为 True 时，L1/L2 的事实也参与投票，但在输出里标出来——用于对比
    「严格溯源」和「宽松溯源」两种判定的差别。
    """
    trace_mod.apply(extraction.facts)      # 等级由 build 统一负责，调用方不用记
    facts, assume_extra, unknown_extra = [], [], []
    n_agents, n_sources = trace_mod.independence_pool(extraction.facts)
    independent = require_independence and max(n_agents, n_sources) >= 2
    for t in extraction.facts:
        slot = trace_mod.classify(t, pool_independent=independent)
        reason = ""
        if slot == "confirmed":
            if not (t.structurally_relevant() or t.same_resource(nucleus_resource)):
                slot = "assumption"
                reason = "非结构相关"
                assume_extra.append(f"{t.as_text()}（非结构相关）")
            else:
                reason = f"结构共享：{t.shares or 'norm'}"
                facts.append(t)
        elif slot == "assumption":
            if include_assumptions:
                facts.append(t)
            assume_extra.append(t.as_text())
        if report is not None:
            report.append(SlotReport(text=t.as_text(), slot=slot, reason=reason,
                                     supports=t.supports, grade=t.grade,
                                     shares=t.shares))

    assumption = extraction.assumption
    if assume_extra:
        assumption = (assumption + "；" if assumption else "") + "未溯源：" + "、".join(assume_extra[:3])
    unknown = extraction.unknown
    if unknown_extra:
        unknown = (unknown + "；" if unknown else "") + "、".join(unknown_extra[:3])
    return Node(nucleus=question, facts=facts, assumption=assumption, unknown=unknown)
