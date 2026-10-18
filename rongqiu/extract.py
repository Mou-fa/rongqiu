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
  tie_break = 当支持与反对的证据数量完全相等时，结合上面 assumption 和 unknown
              这两项，你倾向哪一个方向，以及理由（一句话）
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
  "unknown": "",
  "tie_break": {{"lean": "yes|no", "reason": ""}}
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


def _norm(t: Triple) -> str:
    return f"{t.agent.strip()}|{t.event.strip()}|{t.resource.strip()}"


def consensus(question: str, texts: list[tuple[str, str]], runs: int = 5,
              min_freq: float = 0.6, cfg=None) -> Extraction:
    """共识抽取：同一个问题抽 K 次，只保留足够稳定的事实。

    LLM 抽取有随机性。第一次一致性测试里，同一个会议被抽成四种形态，
    其中三种各只出现 1-2 次，却都能算成反对票——于是支持率在 40% 和
    67% 之间摇摆，结论跟着翻。

    频率本身就是可靠性信号：每次都抽到的事实，比时有时无的事实可信。
    这里把频率记在 Triple.frequency 上，下游可以据此加权或过滤。
    """
    cfg = cfg or load_config()
    counts: dict[str, int] = {}
    exemplar: dict[str, Triple] = {}
    merged_meta = {"assumption": "", "unknown": ""}

    for _ in range(runs):
        ex = extract(question, texts, cfg=cfg)
        for t in ex.facts:
            key = _norm(t)
            counts[key] = counts.get(key, 0) + 1
            if key not in exemplar:
                exemplar[key] = t
        if not merged_meta["assumption"] and ex.assumption:
            merged_meta["assumption"] = ex.assumption
        if not merged_meta["unknown"] and ex.unknown:
            merged_meta["unknown"] = ex.unknown

    kept: list[Triple] = []
    for key, c in counts.items():
        freq = c / runs
        if freq < min_freq:
            continue
        t = exemplar[key]
        t.frequency = round(freq, 3)
        kept.append(t)

    out = Extraction(question=question, model=cfg.model)
    out.facts = kept
    out.assumption = merged_meta["assumption"]
    out.unknown = merged_meta["unknown"]
    out.raw = f"consensus over {runs} runs, kept {len(kept)}/{len(counts)}"
    return out


def tie_break_of(question: str, texts: list[tuple[str, str]], cfg=None) -> tuple[str, str]:
    """平票时，用 11（假设 + 未知）决定方向。

    这是一次独立的追问，不重新读事实，只让它回答：
    「证据打平了，你写的假设和未知把你推向哪边？」
    """
    cfg = cfg or load_config()
    if not available(cfg):
        return "", ""
    joined = "\n".join(f"[{s}] {t}" for s, t in texts)
    prompt = (
        f"【原核】{question}\n\n【全部原料】\n{joined}\n\n"
        "现在假设你对这个问题的支持证据与反对证据数量完全相等，无法分胜负。\n"
        "请只依据下面两项给出倾向：\n"
        "1. 你必须假设、但没有证据的事\n"
        "2. 你完全无法知道、但可能推翻结论的事\n\n"
        '输出 JSON：{"assumption": "", "unknown": "", "lean": "yes|no", "reason": ""}'
    )
    raw = complete(prompt, system=SYSTEM, cfg=cfg)
    if not raw:
        return "", ""
    try:
        data = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        return "", ""
    return str(data.get("lean", "")).strip().lower(), str(data.get("reason", "")).strip()


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
