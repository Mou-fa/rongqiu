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

# 单次查询最多索引多少条。索引是整个链路最慢的一步，
# 每次调用都要等模型——这个上限决定了用户等待时间的长短。
MAX_INDEX_PER_QUERY = 18

# 候选最多显示这么多条。太多了用户看不过来。
MAX_CANDIDATES = 12

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


BATCH_SYSTEM = """你是「绒球」的文本索引器。

给你多段文本，逐段输出：

1. **三元组**：文本里「谁做了什么、对什么做的」的规范化形式。
   动词规范化成书面词。必须输出主题三元组（这段讲的是关于哪个情境）。
   每段最多 3 个。
2. **浓缩句**：把这段文本的核心事实浓缩成一句**主谓宾状补结构的中文**，
   不超过 30 字，不添加原文没有的内容，不评价。
   如果这段没有可提炼的内容（登录页、广告、翻译页、报错页），sentence 为空字符串。

只输出 JSON：
{"items": [{"idx": 1, "triples": [{"agent":"","event":"","resource":""}], "sentence": ""}]}"""

BATCH_PROMPT = """以下是 {n} 段文本：

{blocks}

请逐段输出三元组和浓缩句。"""


def _parse_batch(raw: str, n: int) -> dict[int, dict]:
    t = raw.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    try:
        data = json.loads(t.strip())
    except Exception:
        return {}
    out: dict[int, dict] = {}
    for item in data.get("items", []) or []:
        try:
            i = int(item.get("idx", 0)) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= i < n):
            continue
        triples = []
        for d in item.get("triples", []) or []:
            a = str(d.get("agent", "")).strip()
            e = str(d.get("event", "")).strip()
            r = str(d.get("resource", "")).strip()
            if a and e and r:
                triples.append({"agent": a, "event": e, "resource": r})
        out[i] = {"triples": triples,
                  "sentence": str(item.get("sentence", "")).strip()}
    return out


def extract_batch(texts: list[str], cfg=None, size: int = 6) -> list[dict]:
    """一次给模型多段文本，逐段产出。比一条一调快 3-5 倍。

    索引是整个链路最慢的一步：一次检索回来 40 条，一条一调就是 40 次
    LLM 调用。批量之后 40 条只要 7 次。
    """
    cfg = cfg or load_config()
    results = [{"triples": [], "sentence": ""} for _ in texts]
    if not available(cfg):
        return results
    for start in range(0, len(texts), size):
        chunk = texts[start:start + size]
        blocks = "\n\n".join(
            f"【{i+1}】{t[:900]}" for i, t in enumerate(chunk))
        raw = complete(BATCH_PROMPT.format(n=len(chunk), blocks=blocks),
                       system=BATCH_SYSTEM, cfg=cfg)
        if not raw:
            continue
        parsed = _parse_batch(raw, len(chunk))
        for i, e in parsed.items():
            results[start + i] = e
    return results


def build(texts: list[tuple[str, str]], cfg=None) -> dict:
    cfg = cfg or load_config()
    idx = load_index()
    pending: list[str] = []
    for _, text in texts:
        k = _key(text)
        if k in idx:
            if isinstance(idx[k], list):
                idx[k] = {"triples": idx[k], "sentence": ""}
            continue
        if text not in pending:
            pending.append(text)
    if pending:
        new = extract_batch(pending, cfg)
        for text, e in zip(pending, new):
            idx[_key(text)] = e
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
         idx: dict | None = None, min_hits: int = 1,
         auto_index: bool = True) -> list:
    """在原核和文本的规范化三元组之间做成分匹配。

    返回的候选带 sentence —— 那是给用户看的浓缩句，不是原文。
    """
    idx = idx if idx is not None else load_index()

    if auto_index:
        # 先粗筛再索引：只有含原核成分的文本才值得送进模型。
        # 不筛的话，一次检索 40 条全要索引——每条一次 LLM 调用，
        # 用户会盯着「正在判断…」等好几分钟。
        core_terms = [x for x in (nucleus.agent, nucleus.event, nucleus.resource) if x]
        short_terms = [t for t in core_terms if len(t) >= 1]

        def worth(text: str) -> bool:
            return any(t in text for t in short_terms)

        missing = [t for _, t in texts
                   if _key(t) not in idx and worth(t)][:MAX_INDEX_PER_QUERY]
        if missing:
            new = extract_batch(missing, load_config())
            changed = False
            for text, e in zip(missing, new):
                if e["triples"] or e["sentence"]:
                    idx[_key(text)] = e
                    changed = True
            if changed:
                save_index(idx)

    core = [x for x in (nucleus.agent, nucleus.event, nucleus.resource) if x]
    names = ["agent", "event", "resource"]
    out = []
    for src, text in texts:
        best_hits, best_matched = 0, []
        for t in triples_of(text, idx):
            matched = [core[i] for i in range(len(core))
                       if any(similar(core[i], t[k]) for k in names)]
            if len(matched) > best_hits:
                best_hits, best_matched = len(matched), matched
        # 判据是「共享资源（宾语）」，不是「命中两个成分」。
        # 资源才是识别「这件事是哪件事」的那一格；网页文章里常常只出现
        # 资源而不出现「我」，按命中数筛会把它们全丢掉——问「要不要喝水」
        # 时，讲喝水好处的文章就一条都进不来。
        if best_hits < min_hits:
            continue
        resource_ok = (not nucleus.resource) or any(
            similar(nucleus.resource, t["resource"]) for t in triples_of(text, idx))
        if not resource_ok:
            continue
        sentence = sentence_of(text, idx)
        if not sentence:
            # 没有可提炼内容的（登录页、广告），即使命中成分也丢掉
            continue
        cand = match.Candidate(src, sentence, best_hits, best_matched)
        cand.raw = text
        out.append(cand)

    if not out:
        return out
    out.sort(key=lambda c: -c.hits)

    # 自适应门槛：有命中 2 个以上成分的，就不要只命中 1 个的。
    # 「天气」这种词太泛，只共享一个资源也会把「天气预报 APP」拉进来，
    # 那些跟用户的决定毫无关系。门槛跟着手上最好的那批走。
    best = out[0].hits
    if best >= 2:
        out = [c for c in out if c.hits >= 2]
    return out[:MAX_CANDIDATES]
