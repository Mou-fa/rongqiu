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
from dataclasses import dataclass

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

请输出：
{{
  "agent": "",
  "event": "",
  "resource": "",
  "binary": "把三元组写成一个陈述句，判定时问它是否成立",
  "resource_norm": "资源的规范化名称，去掉时间和修饰语，只留最通用的名词短语",
  "clarify": "若某格填不出，写需要用户补充什么；否则留空"
}}"""


@dataclass
class Nucleus:
    agent: str
    event: str
    resource: str
    binary: str
    raw_question: str = ""
    clarify: str = ""
    resource_norm: str = ""

    def complete(self) -> bool:
        return all(str(x).strip() for x in (self.agent, self.event, self.resource))

    def as_text(self) -> str:
        return f"{self.agent}|{self.event}|{self.resource}"

    def as_dict(self) -> dict:
        return {"agent": self.agent, "event": self.event, "resource": self.resource,
                "binary": self.binary, "raw_question": self.raw_question,
                "clarify": self.clarify, "complete": self.complete()}

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
    return Nucleus(agent=agent, event=event, resource=resource, binary=binary,
                   raw_question=question, clarify=str(d.get("clarify", "")).strip(),
                   resource_norm=str(d.get("resource_norm", "")).strip())


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
