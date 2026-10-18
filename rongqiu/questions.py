"""主动询问。

原则由用户从心理咨询师角度确定，这里只负责**按原则执行**，不发明问句。

边界（来自 811 权限契约）：
- 只问「发生过的、能被看见的」——行为、处境、历史
- 不问「为什么」——动机、感受、关系
- 用户不答也没关系，不追问

问句本身放在 configs/questions.yaml，用户可以随时增删。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .triples import SUPPORT, OPPOSE

# 二元对立。所有主动询问只能回答 yes 或 no。
#
# 用户点 yes → 这是一个「确定性第一接触面」
# 用户点 no  → 这是一个「否定性第一接触面」
#
# 方向由用户的一次点击直接决定，不经过模型判断。
# 这是主动询问和全网场景最大的区别：全网场景的方向要模型猜，
# 主动询问的方向是用户自己给的——所以它更硬。
YES, NO = "yes", "no"
ANSWER_LABEL = {YES: "是", NO: "否"}

# 极性：这个词条的「是」，对原核意味着什么。
#
# 大部分问句是正向的：「你上一次最后怎么选的？」答「是（选去做）」→ 倾向会。
# 但有些问句是反向的：「这件事你已经反复想了一阵子了吗？」
#   答「是」= 还在折腾 = 倾向不做 → 方向要反过来。
#
# 没有这个字段的早期词条一律按 positive 处理。
POLARITY_POSITIVE, POLARITY_NEGATIVE = "positive", "negative"


def direction_of(polarity: str, answer: str) -> str:
    """把 (极性, 是/否) 映射成方向。"""
    yes_means_support = (polarity != POLARITY_NEGATIVE)
    if answer == YES:
        return SUPPORT if yes_means_support else OPPOSE
    return OPPOSE if yes_means_support else SUPPORT

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "configs" / "questions.yaml"

DEFAULT = {
    "id": "last_time",
    "text": "你上一次遇到这种情况，最后怎么选的？",
    "when": "always",
    "why": "",
}


def load() -> list[dict]:
    """读问题库。文件不存在就用内置的那一句，不报错。"""
    if not QUESTIONS_PATH.exists():
        return [dict(DEFAULT)]
    try:
        data = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return [dict(DEFAULT)]
    items = data.get("questions") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text", "")).strip()
        if not text:
            continue
        polarity = str(it.get("polarity", POLARITY_POSITIVE)).strip().lower()
        if polarity not in (POLARITY_POSITIVE, POLARITY_NEGATIVE):
            polarity = POLARITY_POSITIVE
        out.append({
            "id": str(it.get("id", "")).strip() or f"q{len(out)}",
            "text": text,
            "when": str(it.get("when", "always")).strip() or "always",
            "polarity": polarity,
            "why": str(it.get("why", "")).strip(),
        })
    return out or [dict(DEFAULT)]


def pick(nucleus, has_history: bool = False) -> list[dict]:
    """挑出该问的问题。

    只返回「现在该问」的，不返回全部。第一次来的人问历史，老用户也问历史——
    'first_time' 留给将来「还没做过类似决定」的场景。
    """
    out = []
    for q in load():
        when = q.get("when", "always")
        if when == "first_time" and has_history:
            continue
        out.append(q)
    return out


def render(question: dict, nucleus) -> dict:
    """把问句里的槽填上。目前只有 {resource}。"""
    text = question["text"]
    resource = getattr(nucleus, "resource", "") or ""
    if "{resource}" in text and resource:
        text = text.replace("{resource}", resource)
    elif "{resource}" in text:
        # 资源为空时去掉占位符，别把花括号露给用户
        text = text.replace("{resource}", "")
    return {**question, "text": text}


def for_nucleus(nucleus, has_history: bool = False) -> list[dict]:
    return [render(q, nucleus) for q in pick(nucleus, has_history)]


def surface_quota() -> int:
    """固定询问面的总数 = 问题库的词条数。

    这个数会随着问题库增删而变化。代码里任何地方都不许写死它，
    必须每次都从库里读——否则加了词条，面数不变，811 的账就错了。
    """
    return len(load())


def answers_to_facts(answers: list, order_start: int = 0) -> list:
    """把 yes/no 回答转成事实。

    answers: [{"id": ..., "answer": "yes"|"no"}, ...]
    yes → 确定性面（support），no → 否定性面（oppose）。

    方向不走模型，所以这些事实不需要（也不应该）再被 direction_of 判一遍——
    否则用户点的 yes 会被模型改成别的。
    """
    from .triples import SceneFact

    bank = {q["id"]: q for q in load()}
    facts = []
    for a in answers:
        qid = a.get("id") if isinstance(a, dict) else getattr(a, "id", "")
        ans = a.get("answer") if isinstance(a, dict) else getattr(a, "answer", "")
        if ans not in (YES, NO) or qid not in bank:
            continue
        q = bank[qid]
        facts.append(SceneFact(
            scene=f"{q['text']}（答：{ANSWER_LABEL[ans]}）",
            supports=direction_of(q.get("polarity", POLARITY_POSITIVE), ans),
            source="主动询问",
            order=order_start + len(facts),
            depth=1,
        ))
    return facts
