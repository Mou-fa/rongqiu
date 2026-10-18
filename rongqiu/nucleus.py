"""原核解析：把用户的问题变成一条规范化的三元组。

用户输入是文本或语音。无论哪种，最后都落成同一句话：

    代理 · 事件 · 资源

这条三元组就是原核。它有三重作用：

1. **固定** —— 「今晚的聚会我该去吗」和「今晚聚会要去吗」解析成同一条三元组，
   同一个问题不会因为换了个说法就变成另一个原核。
2. **可比** —— 互联网上抽出来的三元组是同一套结构，所以可以在同一个空间里
   做匹配。没有这个统一表示，你没法回答「哪条信息和我的问题有关」。
3. **可判** —— 补上二元问题「是否成立」之后，才谈得上判定和校准。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import available, complete, load_config

SYSTEM = """你是「绒球」系统的原核解析器。

你的任务：把用户的问题，解析成一条规范化三元组。

三元组结构：代理 · 事件 · 资源（对应主语 · 谓语 · 宾语）

规则：
1. 代理必须是具体的：能是人、机构、也可以是「我」。不要用「人们」「大家」。
2. 事件必须是动作，而且要**规范化成书面词**。
   用户说的是口语、方言、缩写，都归一到标准书面表达：
   「买」→「购买」，「学」→「学习」，「搬」→「搬迁」，「上班」→「工作」。
   因为下游要把你的三元组和文本抽出来的三元组做匹配，
   两边都规范化到同一个书面词，才可能对上。
3. 资源必须填出来，不能空。如果原话里没有明确对象，就用最贴近的名词短语补上
   （「我该不该搬到另一个城市」→ 资源是「城市」）。
   同时资源必须是**最裸的名词**：时间、地点、数量、修饰语一律剥掉。
   例：「今晚的聚会」→「聚会」；「周五晚上的北京之旅」→「北京之旅」；
      「我那个用了三年的手机」→「手机」。
   剥干净是必须的——提取出来的三元组要和全网文本里的三元组做成分匹配，
   留着修饰语就永远匹配不上。
4. 若问题里有多重动作，只保留**最核心的那一个**——即用户真正想知道结果的那个。
5. 若某一格实在填不出（比如「他会同意吗」缺少资源），把那一格留空，
   并在 clarify 里写出需要用户补充什么。
6. binary 是把三元组变成一个「是/否」问题，例如：
   三元组「我·参加·今晚的聚会」→ binary「我参加今晚的聚会」
   判定时问的就是：这件事会成立吗？

只输出 JSON。"""

PROMPT = """用户问题：{question}

注意：用户往往会在一句话里说两件事——
  1. 他要你判断的那件事（原核）
  2. 他顺带说出的自己的处境/麻烦（背景事实）

例：「今天身体不舒服，绒球你觉得能不能去聚餐？」
  原核：我 · 去 · 聚餐
  背景事实：我 · 身体不适 · 今天

背景事实是用户亲口说的、关于他自己身上的事，不是别人的观点，
也不是统计数据。它比任何外部材料都更硬。必须单独抽出来。

请输出：
{{
  "agent": "",
  "event": "",
  "resource": "",
  "binary": "把三元组写成一个陈述句，判定时问它是否成立",
  "resource_norm": "资源的规范化名称，去掉时间和修饰语，只留最通用的名词短语",
  "clarify": "若某格填不出，写需要用户补充什么；否则留空",
  "background": [
    {{"agent": "", "event": "", "resource": ""}}
  ]
}}

background 是用户自己说出的处境事实，来自他的原话，不能推测。
没有就输出空数组。"""


@dataclass
class StatedFact:
    """用户自己说出的处境事实。

    这不是别人的观点，也不是统计数据——是用户身上正在发生的事。
    它是整条判断里最硬的一类证据，因为来源就是当事人本人。
    """
    agent: str
    event: str
    resource: str
    raw: str = ""

    def complete(self) -> bool:
        return all(str(x).strip() for x in (self.agent, self.event, self.resource))

    def as_text(self) -> str:
        return f"{self.agent} {self.event} {self.resource}"

    def as_dict(self) -> dict:
        return {"agent": self.agent, "event": self.event,
                "resource": self.resource, "raw": self.raw}


@dataclass
class Nucleus:
    agent: str
    event: str
    resource: str
    binary: str
    raw_question: str = ""
    clarify: str = ""
    resource_norm: str = ""
    background: list = field(default_factory=list)

    def complete(self) -> bool:
        return all(str(x).strip() for x in (self.agent, self.event, self.resource))

    def as_text(self) -> str:
        return f"{self.agent}|{self.event}|{self.resource}"

    def as_dict(self) -> dict:
        return {"agent": self.agent, "event": self.event, "resource": self.resource,
                "binary": self.binary, "raw_question": self.raw_question,
                "clarify": self.clarify, "complete": self.complete(),
                "resource_norm": self.resource_norm,
                "background": [b.as_dict() if hasattr(b, "as_dict") else b
                               for b in self.background]}

    def render(self) -> str:
        lines = [f"原核：{self.agent} · {self.event} · {self.resource}",
                 f"二元问题：{self.binary} 会成立吗？"]
        if self.clarify:
            lines.append(f"需要补充：{self.clarify}")
        return "\n".join(lines)


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
    return text.strip()


BACKGROUND_SYSTEM = """你是「绒球」的处境抽取器。

只做一件事：从用户的话里，抽出**他自己说出的处境**。

【最重要的一条】
人提问时，几乎总会在问题前面先说一句自己的情况。那一句就是处境，
**必须抽出来，不许判成"没有处境"**：

  「最近很累，我要不要换工作？」     → 我·感到疲惫·状态
  「今天身体不舒服，能不能去聚餐？」 → 我·身体不适·身体
  「钱包有点紧，要不要买手机？」     → 我·资金紧张·钱包
  「明天要早起，还去不去聚会？」     → 我·需要早起·明天
  「好久没见他们了，去不去聚会？」   → 我·久未与朋友见面·朋友

常见处境词：累、困、饿、不舒服、生病、忙、闲、没钱、紧、有时间、
没时间、心情差、烦、压力大、期待、担心、好久没、刚、已经

只有整句话仅仅是「我要不要 X」这种纯问题结构，才返回空数组。

【边界】
- 只抽用户亲口说的、关于他自己的状态
- 不要抽他要判断的那件事（那是原核）
- 不要推测用户没说的

只输出 JSON：{"background": [{"agent": "", "event": "", "resource": ""}]}"""

BACKGROUND_PROMPT = """用户的话：{question}

抽出他自己说出的处境。没有就返回空数组。"""


def extract_background(question: str, cfg=None) -> list:
    """单独抽一次背景处境。

    为什么不跟原核放在一个 prompt 里：
    一个 prompt 干两件事时，模型会顾此失彼——同一个问题，
    有时抽出背景，有时直接返回空。而背景是整条判断里最硬的事实，
    丢了它，第一接触面就少一拍，用户立刻看得出来。

    拆成独立调用只多花一次请求，换来的是稳定。
    """
    cfg = cfg or load_config()
    if not available(cfg):
        return []
    raw = complete(BACKGROUND_PROMPT.format(question=question),
                   system=BACKGROUND_SYSTEM, cfg=cfg)
    if not raw:
        return []
    try:
        t = raw.strip()
        if t.startswith("```"):
            import re
            t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
            t = re.sub(r"```\s*$", "", t)
        data = json.loads(t.strip())
    except Exception:
        return []
    out = []
    for b in (data.get("background") or []):
        sf = StatedFact(agent=str(b.get("agent", "")).strip(),
                        event=str(b.get("event", "")).strip(),
                        resource=str(b.get("resource", "")).strip(),
                        raw=question)
        if sf.complete():
            out.append(sf)
    return out


def parse(question: str, cfg=None) -> Nucleus:
    cfg = cfg or load_config()
    if not available(cfg):
        raise RuntimeError("没有可用的 LLM 配置")
    raw = complete(PROMPT.format(question=question), system=SYSTEM, cfg=cfg)
    if not raw:
        raise RuntimeError("原核解析失败：模型没有返回")
    try:
        d = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"原核解析返回的不是 JSON：{raw[:120]}") from exc
    agent = str(d.get("agent", "")).strip()
    event = str(d.get("event", "")).strip()
    resource = str(d.get("resource", "")).strip()
    binary = str(d.get("binary", "")).strip() or f"{agent}{event}{resource}"
    background = []
    for b in (d.get("background") or []):
        sf = StatedFact(agent=str(b.get("agent", "")).strip(),
                        event=str(b.get("event", "")).strip(),
                        resource=str(b.get("resource", "")).strip(),
                        raw=question)
        if sf.complete():
            background.append(sf)
    # 背景以独立抽取为准，主解析的结果只作兜底。
    #
    # 为什么不是合并：两次调用会把同一件事抽出两个近义写法
    # （「身体不适」和「身体不舒服」），合并去重按精确元组去不掉，
    # 于是同一件事被算成两个面。宁可丢掉主解析那份，也不能让面数虚高。
    independent = extract_background(question, cfg)
    if independent:
        background = independent

    return Nucleus(agent=agent, event=event, resource=resource, binary=binary,
                   raw_question=question, clarify=str(d.get("clarify", "")).strip(),
                   resource_norm=str(d.get("resource_norm", "")).strip(),
                   background=background)


# ---------------------------------------------------------------- 语音输入
def transcribe(audio_path: str) -> str:
    """语音转文字。当前未接入 ASR，接口先留在这里。

    用户的问题可能来自语音，但语音在进入绒球之前必须先变成文字，
    之后和文本输入走完全相同的路径——三元组解析、匹配、判定。
    这样语音不是一条特殊通道，只是输入端的一个适配器。
    """
    raise NotImplementedError(
        "语音输入尚未接入 ASR。目前请用文本；接入后调用本函数即可，"
        "下游（原核解析、匹配、判定）完全不用改。"
    )
