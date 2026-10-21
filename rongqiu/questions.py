"""主动询问。

原则由用户从心理咨询师角度确定，这里只负责**按原则执行**，不发明问句。

边界（来自 811 权限契约）：
- 只问「发生过的、能被看见的」——行为、处境、历史
- 不问「为什么」——动机、感受、关系
- 用户不答也没关系，不追问

问句本身放在 configs/questions.yaml，用户可以随时增删。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from . import llm
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

from .paths import DATA, config_file

QUESTIONS_PATH = config_file("questions.yaml")
TAXONOMY_PATH = config_file("taxonomy.yaml")

# 理论分类（FOUNDATIONS §1 马尔可夫毯）：必填、单选。
MK_VALUES = ("cause", "effect", "common")
MK_LABELS = {"cause": "直接因", "effect": "直接果", "common": "共同原因"}

DEFAULT = {
    "id": "last_time",
    "text": "你上一次遇到这种情况，最后怎么选的？",
    "when": "always",
    "why": "",
    "mk": "",
    "domains": [],
}


def load_taxonomy() -> dict:
    """读面类别词表。文件缺失时返回空表，不报错。"""
    if not TAXONOMY_PATH.exists():
        return {"mk": [], "domains": []}
    try:
        data = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"mk": [], "domains": []}

    def _items(key: str) -> list[dict]:
        out = []
        for it in data.get(key) or []:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            out.append({"name": name,
                        "definition": str(it.get("definition", "")).strip()})
        return out

    return {"mk": _items("mk"), "domains": _items("domains")}


def domain_names() -> list[str]:
    """面类别词表（展示用，可多选）。顺序即 taxonomy.yaml 里的顺序。"""
    return [d["name"] for d in load_taxonomy()["domains"]]


def issues() -> list[str]:
    """问句库标注的自检。给测试和发布前检查用，不抛异常。"""
    known = set(domain_names())
    out = []
    for q in load():
        if q["mk"] not in MK_VALUES:
            out.append(f"{q['id']}: mk 缺失或非法（应为 {'/'.join(MK_VALUES)}）")
        if not q["domains"]:
            out.append(f"{q['id']}: domains 为空（至少要标一类面）")
        for d in q["domains"]:
            if known and d not in known:
                out.append(f"{q['id']}: 未知 domain「{d}」")
    return out


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
        mk = str(it.get("mk", "")).strip().lower()
        if mk not in MK_VALUES:
            mk = ""
        # domains 可以多选；也兼容只写一个字符串的旧写法
        raw_domains = it.get("domains", it.get("domain", []))
        if isinstance(raw_domains, str):
            raw_domains = [raw_domains]
        domains = [str(x).strip() for x in (raw_domains or [])
                   if str(x).strip()]
        out.append({
            "id": str(it.get("id", "")).strip() or f"q{len(out)}",
            "text": text,
            "when": str(it.get("when", "always")).strip() or "always",
            "polarity": polarity,
            "why": str(it.get("why", "")).strip(),
            "mk": mk,
            "domains": domains,
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


# ---------------------------------------------------------------------------
# 按原核挑面（M1 第三层的基础）
#
# 问句库是弹药库，不是每次全问。这里让模型按原核挑出这次最该问的 8–12 条：
# 只挑和这个决定直接相关的、覆盖不同面类别的，不要凑数。
# 挑不出来时退回整库（不藏着问题，也不假装知道该问什么）。
# ---------------------------------------------------------------------------
SELECT_CACHE_PATH = DATA / "question_select_cache.json"

SELECT_SYSTEM = """你是「绒球」的探测规划器。用户正在犹豫一个问题，下面是从问句库里挑出的固定询问。
请挑出这次最该问的 8–12 条：
- 只挑和这个决定直接相关的；
- 覆盖不同的面类别，不要都问同一类；
- 不要凑数：不相关的一条也别挑。

判断标准：
- 这个问句的答案，会不会改变「要不要做这件事」的方向？
- 它问的是不是用户自己身上、已经发生或稳定存在的事实？
- 不同问句之间不要问同一件事。

只输出 JSON：{"ids":["q01","q02"],"why":"不超过30字"}"""

SELECT_PROMPT = """决定：{binary}
原核：{agent} · {event} · {resource}
{stated}

问句列表（id｜问句｜mk｜domains）：
{lines}

只输出 JSON。"""


def _select_key(nucleus) -> str:
    raw = "|".join([
        str(getattr(nucleus, "binary", "")),
        str(getattr(nucleus, "agent", "")),
        str(getattr(nucleus, "event", "")),
        str(getattr(nucleus, "resource", "")),
        ";".join(b.as_text() for b in getattr(nucleus, "background", []) or []),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _load_select_cache() -> dict:
    try:
        return json.loads(SELECT_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_select_cache(cache: dict) -> None:
    try:
        SELECT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SELECT_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    except Exception:
        pass


def select(nucleus, has_history: bool = False, limit: int = 10) -> list[dict]:
    """按原核从问句库里挑出这次该问的面。失败时退回整库。"""
    pool = [q for q in load()
            if not (q.get("when") == "first_time" and has_history)]
    if not pool:
        return []
    cfg = llm.load_config()
    if not llm.available(cfg):
        return pool

    key = _select_key(nucleus)
    cache = _load_select_cache()
    ids = cache.get(key)
    if not isinstance(ids, list) or not ids:
        stated = ""
        bg = getattr(nucleus, "background", []) or []
        if bg:
            stated = "用户自述：" + "；".join(b.as_text() for b in bg)
        lines = "\n".join(
            f"{q['id']}｜{q['text']}｜{q['mk']}｜{'/'.join(q['domains'])}"
            for q in pool)
        prompt = SELECT_PROMPT.format(
            binary=getattr(nucleus, "binary", ""),
            agent=getattr(nucleus, "agent", ""),
            event=getattr(nucleus, "event", ""),
            resource=getattr(nucleus, "resource", ""),
            stated=stated, lines=lines)
        try:
            raw = llm.complete(prompt, system=SELECT_SYSTEM, cfg=cfg) or ""
            text = raw.strip()
            if text.startswith("```"):
                import re as _re
                text = _re.sub(r"^```[a-zA-Z]*\s*", "", text)
                text = _re.sub(r"```\s*$", "", text)
            data = json.loads(text)
            ids = [str(x) for x in (data.get("ids") or []) if str(x).strip()]
        except Exception:
            return pool
        valid = {q["id"] for q in pool}
        ids = [i for i in ids if i in valid][:max(1, limit)]
        if not ids:
            return pool
        cache[key] = ids
        _save_select_cache(cache)

    by_id = {q["id"]: q for q in pool}
    out = [by_id[i] for i in ids if i in by_id][:max(1, limit)]
    return out or pool


def unanswered(asked_ids: list[str], answered_ids: set[str]) -> list[dict]:
    """这次挑出来、但用户还没答的面。它们就是半知槽的候选。"""
    by_id = {q["id"]: q for q in load()}
    return [by_id[i] for i in asked_ids
            if i in by_id and i not in answered_ids]


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
