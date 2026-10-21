"""离线输入层：没有 LLM 时，从一句话里取出二元的「原核」与交互框架。

只做确定性规则，不调用模型、不联网。
这是「固定问句 + probe 答复」链路的入口：LLM 不可用时，产品仍能问固定问句、
用用户的 yes/no 直接生成事实，完成一次 811 判断。
"""
from __future__ import annotations

import re

from . import crisis
from .nucleus import Nucleus

DECISION_MARKERS = (
    "要不要", "该不该", "能不能", "会不会", "是否", "值不值得",
    "去不去", "来不来", "买不买", "做不做", "参加不参加",
)
VENT_MARKERS = ("累", "烦", "焦虑", "难受", "压力", "委屈", "想哭",
                "崩溃", "纠结", "内耗", "睡不着", "疲惫")

# 「还是」型：A 还是 B
_EITHER = re.compile(r"^(.*?)(?:还是)(.+?)[?？]?$")


def frame_of(question: str) -> str:
    text = (question or "").strip()
    if crisis.detect(text):
        return "crisis"
    if any(m in text for m in DECISION_MARKERS) or _EITHER.search(text):
        return "decision"
    if any(m in text for m in VENT_MARKERS):
        return "vent"
    return "chat"


def binary_of(question: str) -> str:
    """从「要不要 X / 该不该 X / A 还是 B」里取出二元问题的对象。

    抽不出时退回整句（去掉标点），至少让后续 811 有一个标签。
    """
    text = (question or "").strip()
    if not text:
        return ""
    for marker in DECISION_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            tail = text[idx + len(marker):].strip()
            tail = tail.strip("，。！？?！,.;：: ")
            if tail:
                return tail
    m = _EITHER.search(text)
    if m:
        a = m.group(1).strip("，。！？?！,.;：: ")
        b = m.group(2).strip("，。！？?！,.;：: ")
        if a and b:
            return a + "还是" + b
    return text.strip("，。！？?！,.;：: ")


def parse(question: str) -> Nucleus:
    """离线原核：没有 agent/event/resource 的细粒度，但有 binary 和 raw。"""
    binary = binary_of(question)
    return Nucleus(agent="", event="", resource="", binary=binary,
                   raw_question=question or "")
