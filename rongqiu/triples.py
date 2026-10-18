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

    def complete(self) -> bool:
        """REA 三元组是否填满。填不满的不是接触点，只是相关。"""
        return all(str(x).strip() for x in (self.agent, self.event, self.resource))

    def is_fact(self) -> bool:
        """只有确认发生、且三元组完整的，才能进确定槽。"""
        return self.complete() and self.polarity == POLARITY_AFFIRM

    def as_text(self) -> str:
        return f"{self.agent} {self.event} {self.resource}"

    def as_dict(self) -> dict:
        return {
            "agent": self.agent, "event": self.event, "resource": self.resource,
            "time": self.time, "polarity": self.polarity, "supports": self.supports,
            "source": self.source, "grade": self.grade, "evidence": self.evidence,
            "complete": self.complete(), "is_fact": self.is_fact(),
        }


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
