"""把文本索引成规范化三元组。

用户的问题被规范化成「我 · 购买 · 手机」之后，如果直接和原文做字面匹配，
永远匹配不上——原文里写的是「买」。所以文本也必须经过同一次提取和规范化，
两边落在同一个规范空间里，匹配才有意义。

这就是「提取的主谓宾和语言文本自身的主谓宾匹配一致」的实现：
    问题 → 规范化三元组
    文本 → 规范化三元组
    匹配  → 在规范空间里比
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import match
from .llm import available, complete, load_config
from .nucleus import Nucleus

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "triple_index.json"

SYSTEM = """你是「绒球」的文本索引器。

把一段文本提炼成它与「谁做了什么、对什么做的」相关的规范化三元组。

规则：
1. 事件动词规范化成书面词：「买」→「购买」，「学」→「学习」，「搬」→「搬迁」。
2. 代理、资源也取最通用的名词短语。
3. **必须输出主题三元组**：这段文本讲的是关于哪个「谁·做什么·对什么」的情境。
   例「我去健身房最怕遇到熟人」的主题是「我·前往·健身房」，
   即使正文里没再出现「健身房」三个字，也要把它提炼出来。
4. 除主题外，最多再补 2 个内容三元组。
5. 只输出 JSON：{"triples":[{"agent":"","event":"","resource":""}]}
"""


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_index() -> dict:
    if not INDEX_PATH.exists():
        return {}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_index(idx: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def extract_triples(text: str, cfg=None) -> list[dict]:
    cfg = cfg or load_config()
    if not available(cfg):
        return []
    raw = complete(f"文本：{text}\n\n请输出规范化的三元组 JSON。", system=SYSTEM, cfg=cfg)
    if not raw:
        return []
    t = raw.strip()
    if t.startswith("```"):
        import re
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    try:
        data = json.loads(t.strip())
    except Exception:
        return []
    out = []
    for d in data.get("triples", []) or []:
        a = str(d.get("agent", "")).strip()
        e = str(d.get("event", "")).strip()
        r = str(d.get("resource", "")).strip()
        if a and e and r:
            out.append({"agent": a, "event": e, "resource": r})
    return out


def build(texts: list[tuple[str, str]], cfg=None) -> dict:
    """给一批文本建索引。已有的不重复建。"""
    cfg = cfg or load_config()
    idx = load_index()
    for _, text in texts:
        k = _key(text)
        if k in idx:
            continue
        idx[k] = extract_triples(text, cfg)
    save_index(idx)
    return idx


def triples_of(text: str, idx: dict | None = None) -> list[dict]:
    idx = idx if idx is not None else load_index()
    return idx.get(_key(text), [])


# 口语词与书面词之间的桥。两侧各自规范化之后仍可能落在不同词上，
# 这里用「完全相同 / 互相包含 / 同义词表」三种方式对齐。
SYNONYMS = {
    "前往": {"去", "到", "赶往"},
    "去": {"前往", "到"},
    "更换": {"换", "跳槽", "调动"},
    "换": {"更换", "跳槽"},
    "购买": {"买", "购入", "采购"},
    "买": {"购买", "购入"},
    "学习": {"学", "报班", "进修"},
    "学": {"学习", "进修"},
    "搬迁": {"搬", "搬家", "迁移"},
    "搬": {"搬迁", "搬家"},
    "接受": {"接", "答应", "接下"},
    "参加": {"出席", "参与", "去"},
    "工作": {"职场", "上班", "职业"},
    "手机": {"电话", "智能机"},
}


def similar(a: str, b: str) -> bool:
    """两个成分是不是同一件事。

    单字不做包含匹配：「我」被「我们」包含，但那不是同一个人。
    第一版就是这么错的，导致「我们参加过聚餐」被算成命中原核的「我·参加·聚餐」。
    """
    if not a or not b:
        return False
    if a == b:
        return True
    if a in SYNONYMS.get(b, set()) or b in SYNONYMS.get(a, set()):
        return True
    if len(a) < 2 or len(b) < 2:
        return False
    return a in b or b in a


def rank(nucleus: Nucleus, texts: list[tuple[str, str]],
         idx: dict | None = None, min_hits: int = 2,
         auto_index: bool = True) -> list:
    """在原核和文本的规范化三元组之间做成分匹配。

    没索引过的文本（比如搜索刚返回的新结果）会现场提取并写进索引，
    所以第一次会慢一点，之后都走缓存。
    """
    idx = idx if idx is not None else load_index()
    if auto_index:
        missing = [(s, t) for s, t in texts if _key(t) not in idx]
        if missing:
            cfg = load_config()
            changed = False
            for _, t in missing:
                tris = extract_triples(t, cfg)
                if tris:
                    idx[_key(t)] = tris
                    changed = True
            if changed:
                save_index(idx)
    core = [x for x in (nucleus.agent, nucleus.event, nucleus.resource) if x]
    names = ["agent", "event", "resource"]
    out = []
    for src, text in texts:
        best_hits, best_matched = 0, []
        for t in triples_of(text, idx):
            matched = [core[i] for i in range(3)
                       if any(similar(core[i], t[k]) for k in names)]
            if len(matched) > best_hits:
                best_hits, best_matched = len(matched), matched
        if best_hits >= min_hits:
            out.append(match.Candidate(src, text, best_hits, best_matched))
    out.sort(key=lambda c: -c.hits)
    return out
