"""溯源回流：给每一条三元组定等级。

等级决定它进哪个槽：
    L3/L4 → 确定槽（参与判定）
    L1/L2 → 假设槽（不参与判定，只做标注）
    L0    → 丢弃

这里只做「来源分级」这一件事。真正的逆向追踪（沿着事件链往回到原始记录）
是下一步，它需要外部数据源接入。
"""

from __future__ import annotations

from .triples import Triple

GRADES = {
    "L0": "传闻、群聊、KOL 转述",
    "L1": "新闻报道、二手转述、推测",
    "L2": "当事方声明、口头承诺、聊天记录",
    "L3": "书面契约、审计文件、正式记录、系统日志",
    "L4": "密码学可验证、可公开复算",
    "L5": "物理可测量（传感器、实验）",
}

# 来源标签 → 初始等级
SOURCE_GRADE = {
    "chat": "L2",
    "chat_record": "L2",
    "calendar": "L3",
    "email": "L3",
    "note": "L1",
    "news": "L1",
    "rumor": "L0",
    "onchain": "L4",
    "sensor": "L5",
    "contract": "L3",
    "statement": "L2",
}

CONFIRMED_GRADES = ("L3", "L4", "L5")


def grade_of(triple: Triple) -> str:
    return SOURCE_GRADE.get(triple.source, triple.grade or "L1")


def classify(triple: Triple) -> str:
    """返回该三元组应进的槽：confirmed / assumption / unknown。"""
    if not triple.complete():
        return "unknown"
    if grade_of(triple) in CONFIRMED_GRADES and triple.is_fact():
        return "confirmed"
    return "assumption"


def apply(triples: list[Triple]) -> list[Triple]:
    for t in triples:
        t.grade = grade_of(t)
    return triples


def describe() -> str:
    return "\n".join(f"  {k}: {v}" for k, v in sorted(GRADES.items()))
