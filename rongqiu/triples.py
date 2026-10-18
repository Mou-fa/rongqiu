"""语义三元组：绒球的最小单位。

语言学的主谓宾和会计学的 REA 是同一个结构：

    主语 = Agent（代理）
    谓语 = Event（事件）
    宾语 = Resource（资源）

这个模块只做一件事：把一段文本里的事件，变成可以被 N11 结构处理的对象。
它不做判断，也不做溯源——它只保证三元组填得满。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 极性：只有「确认发生过」的才是事实。
# 否定和假设都不是事件，它们是关于事件的陈述。
POLARITY_AFFIRM = "affirm"
POLARITY_NEGATE = "negate"
POLARITY_HYPOTHETICAL = "hypothetical"

# 对原核的倾向
SUPPORT = "support"
OPPOSE = "oppose"
NEUTRAL = "neutral"


@dataclass
class Triple:
    agent: str
    event: str
    resource: str
    time: str = ""
    polarity: str = POLARITY_AFFIRM
    supports: str = NEUTRAL
    source: str = ""
    grade: str = "L1"
    evidence: str = ""
    frequency: float = 1.0   # 共识抽取里这条事实出现的频率，1.0 表示每次都抽到
    # 注意：人工勾选的场景走 SceneFact，不走 Triple
    shares: str = ""         # 与原核共享哪几格，逗号分隔：resource,agent,event
    resource_norm: str = ""  # 资源的规范化名称，用于跨表述做实体归一化

    def complete(self) -> bool:
        """REA 三元组是否填满。填不满的不是接触点，只是相关。"""
        return all(str(x).strip() for x in (self.agent, self.event, self.resource))

    def is_fact(self) -> bool:
        """只有确认发生、且三元组完整的，才能进确定槽。"""
        return self.complete() and self.polarity == POLARITY_AFFIRM

    def same_resource(self, norm: str) -> bool:
        """两个资源是否是同一个实体（按规范化名比较）。"""
        a, b = self.resource_norm.strip(), (norm or "").strip()
        return bool(a) and bool(b) and a == b

    def structurally_relevant(self) -> bool:
        """是否与原核结构共享。

        相关性的唯一判据。时间冲突、因果关联、间接影响都不算——
        主谓宾提取本来就把时间和状语剥掉了，所以那三类永远不可能
        出现在结构里。它们属于 11（假设槽/未知槽），不属于确定槽。

        关键是**共享哪一格**：
          共享宾语（资源）  → 相关。资源是识别「这件事是哪件事」的那一格。
          只共享谓语        → 不相关。「参加」「说」「买」这类动词到处都是，
                             只靠动词匹配等于没匹配。
          只共享主语        → 不相关。「我」同样到处都是。
          资源缺失时才退而看「主语+谓语」同时共享。
        """
        parts = {p.strip() for p in self.shares.split(",") if p.strip()}
        if "resource" in parts:
            return True
        return "resource" not in parts and {"agent", "event"} <= parts

    def as_text(self) -> str:
        return f"{self.agent} {self.event} {self.resource}"

    def as_dict(self) -> dict:
        return {
            "agent": self.agent, "event": self.event, "resource": self.resource,
            "time": self.time, "polarity": self.polarity, "supports": self.supports,
            "source": self.source, "grade": self.grade, "evidence": self.evidence,
            "complete": self.complete(), "is_fact": self.is_fact(),
            "frequency": self.frequency, "shares": self.shares,
        }


@dataclass
class SceneFact:
    """一条被人工勾选过倾向的场景。

    全网匹配回来的场景大多是习惯性表述（「我参加聚会后经常觉得累」），
    不是已发生的交换事件，硬抽三元组会丢掉它们。所以这里不再抽取——
    场景原文保留，倾向由人来勾选。

    分工：
        机器负责「找到你没找到的证据」
        人负责「这条证据对这件事意味着什么」
        N11 负责「把这些合起来算」
    """
    scene: str
    supports: str = NEUTRAL     # support / oppose / neutral
    source: str = "web"
    grade: str = "L1"
    order: int = 0
    frequency: float = 1.0

    def complete(self) -> bool:
        return bool(self.scene.strip())

    def is_fact(self) -> bool:
        return self.complete() and self.supports in (SUPPORT, OPPOSE)

    def as_text(self) -> str:
        return self.scene

    def as_dict(self) -> dict:
        return {"scene": self.scene, "supports": self.supports,
                "source": self.source, "grade": self.grade, "order": self.order}


@dataclass
class Extraction:
    """一次抽取的原始结果，还没分类进槽。"""
    question: str
    facts: list[Triple] = field(default_factory=list)
    assumption: str = ""
    unknown: str = ""
    raw: str = ""
    model: str = ""

    def confirmed(self) -> list[Triple]:
        return [t for t in self.facts if t.is_fact()]

    def dropped(self) -> list[Triple]:
        return [t for t in self.facts if not t.is_fact()]
