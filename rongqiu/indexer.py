"""把文本索引成「规范化三元组 + 一句浓缩话」。

为什么需要浓缩：

搜索 API 返回的是正文片段，几百字。直接把这种文本塞进候选框，
用户看到的是文章，不是可以用来判断的一句话。

而且原始片段里往往夹着登录页、翻译页、广告——浓缩这一步天然把它们滤掉：
模型没法把「请登录后查看」浓缩成一句有内容的话。

浓缩的格式固定为主谓宾状补，和原核的三元组同构：
    主语 · 谓语 · 宾语 · 状语/补语
    「我参加聚会前通常会先睡一觉」
这样用户一眼就能判断「这说的是不是我」。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import match
from .llm import available, complete, load_config
from .nucleus import Nucleus

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "triple_index.json"

SYSTEM = """你是「绒球」的文本索引器。

对一段文本，输出两样东西：

1. **三元组**：把文本里「谁做了什么、对什么做的」提炼成规范化三元组。
   动词规范化成书面词：「买」→「购买」，「学」→「学习」。
   **必须输出主题三元组**：这段文本讲的是关于哪个情境。
   例「我去健身房最怕遇到熟人」的主题是「我·前往·健身房」。
   一段文本最多 3 个三元组。

2. **浓缩句**：把这段文本的核心事实，浓缩成**一句主谓宾状补结构的中文**。
   - 不超过 30 个字
   - 保留原文说的核心事实，不添加原文没有的内容
   - 不要评价、不要建议
   - 如果这段文本没有可提炼的内容（登录页、广告、翻译页、报错页），
     sentence 输出空字符串

只输出 JSON：
{"triples": [{"agent": "", "event": "", "resource": ""}], "sentence": ""}"""

PROMPT = """文本：
{text}

请输出三元组和一句主谓宾状补的浓缩句。"""


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


def _entry(raw: str) -> dict:
    t = raw.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    try:
        data = json.loads(t.strip())
    except Exception:
        return {"triples": [], "sentence": ""}
    triples = []
    for d in data.get("triples", []) or []:
        a = str(d.get("agent", "")).strip()
        e = str(d.get("event", "")).strip()
        r = str(d.get("resource", "")).strip()
        if a and e and r:
            triples.append({"agent": a, "event": e, "resource": r})
    return {"triples": triples, "sentence": str(data.get("sentence", "")).strip()}


def extract(text: str, cfg=None) -> dict:
    cfg = cfg or load_config()
    if not available(cfg):
        return {"triples": [], "sentence": ""}
    raw = complete(PROMPT.format(text=text[:1200]), system=SYSTEM, cfg=cfg)
    if not raw:
        return {"triples": [], "sentence": ""}
    return _entry(raw)


def build(texts: list[tuple[str, str]], cfg=None) -> dict:
    cfg = cfg or load_config()
    idx = load_index()
    for _, text in texts:
        k = _key(text)
        if k in idx:
            # 旧格式（纯三元组列表）自动升级
            if isinstance(idx[k], list):
                idx[k] = {"triples": idx[k], "sentence": ""}
            continue
        idx[k] = extract(text, cfg)
    save_index(idx)
    return idx


def _norm_entry(v) -> dict:
    if isinstance(v, list):
        return {"triples": v, "sentence": ""}
    if isinstance(v, dict):
        return {"triples": v.get("triples", []) or [],
                "sentence": v.get("sentence", "") or ""}
    return {"triples": [], "sentence": ""}


def triples_of(text: str, idx: dict | None = None) -> list[dict]:
    idx = idx if idx is not None else load_index()
    return _norm_entry(idx.get(_key(text))).get("triples", [])


def sentence_of(text: str, idx: dict | None = None) -> str:
    idx = idx if idx is not None else load_index()
    return _norm_entry(idx.get(_key(text))).get("sentence", "")


# 口语词与书面词之间的桥
SYNONYMS = {
    "前往": {"去", "到", "赶往"}, "去": {"前往", "到"},
    "更换": {"换", "跳槽", "调动"}, "换": {"更换", "跳槽"},
    "购买": {"买", "购入", "采购"}, "买": {"购买", "购入"},
    "学习": {"学", "报班", "进修"}, "学": {"学习", "进修"},
    "搬迁": {"搬", "搬家", "迁移"}, "搬": {"搬迁", "搬家"},
    "接受": {"接", "答应", "接下"}, "参加": {"出席", "参与", "去"},
    "工作": {"职场", "上班", "职业"}, "手机": {"电话", "智能机"},
}


def similar(a: str, b: str) -> bool:
    """两个成分是不是同一件事。

    单字不做包含匹配：「我」被「我们」包含，但那不是同一个人。
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

    返回的候选带 sentence —— 那是给用户看的浓缩句，不是原文。
    """
    idx = idx if idx is not None else load_index()
    if auto_index:
        missing = [(s, t) for s, t in texts if _key(t) not in idx]
        if missing:
            cfg = load_config()
            changed = False
            for _, t in missing:
                e = extract(t, cfg)
                if e["triples"] or e["sentence"]:
                    idx[_key(t)] = e
                    changed = True
            if changed:
                save_index(idx)

    core = [x for x in (nucleus.agent, nucleus.event, nucleus.resource) if x]
    names = ["agent", "event", "resource"]
    out = []
    for src, text in texts:
        best_hits, best_matched, best_triple = 0, [], None
        for t in triples_of(text, idx):
            matched = [core[i] for i in range(len(core))
                       if any(similar(core[i], t[k]) for k in names)]
            if len(matched) > best_hits:
                best_hits, best_matched, best_triple = len(matched), matched, t
        if best_hits < min_hits:
            continue
        sentence = sentence_of(text, idx)
        if not sentence:
            # 没有可提炼内容的（登录页、广告），即使命中成分也丢掉
            continue
        cand = match.Candidate(src, sentence, best_hits, best_matched)
        cand.raw = text
        out.append(cand)
    out.sort(key=lambda c: -c.hits)
    return out
