"""文本 → 语义三元组。

LLM 在这里只干五件清洗工作，都是纯语法/语义的，不涉及判断：

    1. 补主语        「买了面包」→ 谁买的
    2. 辨否定/模态    「他没买」「他可能买」都不是事件
    3. 消指代        「他」是谁
    4. 定时间        过去发生的是事件，将来的不是
    5. 统一粒度       太碎和太粗都不可用

它不做的事：判断真假（溯源做）、给倾向（N11 做）。
"""

from __future__ import annotations

import json
import re

from .llm import available, complete, load_config
from .triples import (Extraction, Triple, POLARITY_AFFIRM, POLARITY_NEGATE,
                      POLARITY_HYPOTHETICAL, SUPPORT, OPPOSE, NEUTRAL)

SYSTEM = """你是「绒球」系统的语义三元组抽取器。

你的唯一任务：从文本中抽取与【原核】相关的语义三元组。

三元组结构固定为 代理 · 事件 · 资源，对应语言学的主谓宾：
  主语 = 代理（谁做的）
  谓语 = 事件（做了什么）
  宾语 = 资源（对什么做的）

必须遵守：
1. 三元格必须填满。填不满的不要输出——那不是接触点，只是相关。
2. 只有「确认已经发生」的才是事件。否定（没做）、假设（可能会做）、
   将来（打算做）都不是事件，polarity 分别标 negate / hypothetical。
3. 补全省略的主语。中文常省略主语，根据上下文推断，推断不出就整条丢弃。
4. 消解代词。把「他」「那个」换成具体的人或物。
5. 统一粒度。**一个事件只输出一条三元组。**
   反例：同一个会议，不要分别输出「安排会议」「要求参加」「规定不可缺席」——
   那是同一个事件的三种说法，只保留最能代表它的那一条。
6. supports 表示这条事件对【原核】的倾向：
   support = 支持原核成立 / oppose = 反对 / neutral = 无关倾向
7. 只输出与判断原核有关的三元组，3 到 10 条。

另外输出：
  assumption = 你必须假设、但文本里没有证据的一件事（一句话）
  unknown = 你完全无法从文本得知、但可能推翻结论的一件事（一句话）
"""

PROMPT = """【原核】
{question}

【文本】（来源：{source}）
{text}

请输出 JSON：
{{
  "facts": [
    {{"agent": "", "event": "", "resource": "", "time": "",
      "polarity": "affirm|negate|hypothetical",
      "supports": "support|oppose|neutral",
      "evidence": "原文里的依据"}}
  ],
  "assumption": "",
  "unknown": ""
}}"""


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _to_triple(d: dict, source: str) -> Triple | None:
    agent = str(d.get("agent", "")).strip()
    event = str(d.get("event", "")).strip()
    resource = str(d.get("resource", "")).strip()
    if not (agent and event and resource):
        return None
    polarity = str(d.get("polarity", POLARITY_AFFIRM)).strip().lower()
    if polarity not in (POLARITY_AFFIRM, POLARITY_NEGATE, POLARITY_HYPOTHETICAL):
        polarity = POLARITY_AFFIRM
    supports = str(d.get("supports", NEUTRAL)).strip().lower()
    if supports not in (SUPPORT, OPPOSE, NEUTRAL):
        supports = NEUTRAL
    return Triple(
        agent=agent, event=event, resource=resource,
        time=str(d.get("time", "")).strip(),
        polarity=polarity, supports=supports,
        source=source, evidence=str(d.get("evidence", "")).strip(),
    )


def extract(question: str, texts: list[tuple[str, str]],
            cfg=None) -> Extraction:
    """从多段文本中抽取。texts = [(来源标签, 文本内容), ...]"""
    cfg = cfg or load_config()
    if not available(cfg):
        raise RuntimeError("没有可用的 LLM 配置，无法抽取。见 configs/llm.yaml")

    out = Extraction(question=question, model=cfg.model)
    merged: dict[str, Triple] = {}

    for source, text in texts:
        raw = complete(PROMPT.format(question=question, source=source, text=text),
                       system=SYSTEM, cfg=cfg)
        if not raw:
            continue
        out.raw += raw
        try:
            data = json.loads(_strip_fence(raw))
        except json.JSONDecodeError:
            continue
        for d in data.get("facts", []) or []:
            t = _to_triple(d, source)
            if t is None:
                continue
            key = t.as_text()
            if key in merged:
                # 两个来源说了同一件事：加一个交叉印证标记
                merged[key].evidence += f" | 另见 {source}"
                continue
            merged[key] = t
        if not out.assumption and data.get("assumption"):
            out.assumption = str(data["assumption"]).strip()
        if not out.unknown and data.get("unknown"):
            out.unknown = str(data["unknown"]).strip()

    out.facts = _dedup(list(merged.values()))
    return out


def _dedup(triples: list[Triple]) -> list[Triple]:
    """同一个代理 + 同一个资源，视为同一个事件的不同说法，只保留第一条。

    事件数决定 N，N 决定置信度。把一件事拆成三条，等于把确定性凭空抬高
    ——这个 bug 在第一次跑通时就出现了：「安排/要求/规定 复盘会」本来是
    一个会议，被算成了三个接触点。
    """
    seen: dict[tuple[str, str], Triple] = {}
    out: list[Triple] = []
    for t in triples:
        key = (t.agent.strip(), t.resource.strip())
        if key in seen:
            seen[key].evidence += f" | 同事件复述：{t.event}"
            continue
        seen[key] = t
        out.append(t)
    return out
