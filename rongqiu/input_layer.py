"""离线输入层：没有 LLM 时，从一句话里取出二元原核、框架、相关固定问句。

只做确定性规则，不调用模型、不联网。
这是「固定问句 + probe 答复」链路的入口：LLM 不可用时，产品仍能按面挑问句，
用用户的 yes/no 直接生成事实，完成一次 811 判断。
"""
from __future__ import annotations

import hashlib
import json
import re

from . import crisis
from .nucleus import Nucleus
from .paths import config_file

IR_VERSION = "cir_input_v1"

SURFACES_PATH = config_file("surfaces.jsonl")
LEXICON_PATH = config_file("lexicon.jsonl")

UNIVERSAL_PROBES = ["last_time", "still_waiting"]

# 这些面在场时，才把 baseline gaps 补进来；否则只问和当前动作有关的面。
CORE_SURFACES = {
    "decision.economic", "decision.time", "decision.career",
    "decision.relationship", "decision.eligibility", "decision.information",
}

BASELINE_GAPS = [
    "decision.economic",
    "decision.time",
    "decision.risk",
    "decision.relationship",
    "decision.alternatives",
]

DECISION_MARKERS = (
    "要不要", "该不该", "能不能", "会不会", "是否", "值不值得",
    "去不去", "来不来", "买不买", "做不做", "参加不参加",
)
VENT_MARKERS = ("累", "烦", "焦虑", "难受", "压力", "委屈", "想哭",
                "崩溃", "纠结", "内耗", "睡不着", "疲惫",
                "心情", "乱糟糟", "睡不好", "没精神", "没意思",
                "低落", "不想动", "烦死")

_EITHER = re.compile(r"^(.*?)(?:还是)(.+?)[?？]?$")


def _load_jsonl(path) -> list[dict]:
    try:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    except Exception:
        return []


def load_surfaces() -> list[dict]:
    return _load_jsonl(SURFACES_PATH)


def load_lexicon() -> list[dict]:
    return _load_jsonl(LEXICON_PATH)


def _find(text: str, pattern: str) -> list[tuple[int, str]]:
    if pattern.startswith("re:"):
        return [(m.start(), m.group(0)) for m in re.finditer(pattern[3:], text)]
    out = []
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx < 0:
            break
        out.append((idx, pattern))
        start = idx + max(1, len(pattern))
    return out


def match_surfaces(text: str) -> list[dict]:
    """lexicon -> surface 命中，带名称与命中证据。"""
    names = {s["surface_id"]: s.get("name") or s["surface_id"]
             for s in load_surfaces() if s.get("surface_id")}
    agg: dict[str, float] = {}
    evidence: dict[str, list[dict]] = {}
    for e in load_lexicon():
        surfaces = e.get("surfaces") or []
        if not surfaces:
            continue
        hits = []
        for pat in e.get("patterns") or []:
            for span, matched in _find(text, pat):
                hits.append({"pattern": pat, "span": span,
                             "matched": matched, "lexicon": e.get("id", "")})
        if not hits:
            continue
        w = float(e.get("weight", 0.15))
        for sid in surfaces:
            agg[sid] = min(0.95, agg.get(sid, 0.5) + w)
            for h in hits:
                if len(evidence.setdefault(sid, [])) < 8:
                    evidence[sid].append(h)
    # 兜底：lexicon 缺失时用 surfaces 自带的 triggers
    if not agg:
        for s in load_surfaces():
            for t in (s.get("triggers") or []):
                idx = text.find(t) if t else -1
                if t and idx >= 0:
                    sid = s["surface_id"]
                    agg[sid] = 0.6
                    evidence.setdefault(sid, []).append(
                        {"pattern": t, "span": idx, "matched": t, "lexicon": "trigger"})
    out = []
    for sid, c in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0])):
        ev = sorted(evidence.get(sid, []), key=lambda x: (x["span"], x["pattern"]))
        out.append({"surface_id": sid, "name": names.get(sid, sid),
                    "confidence": round(c, 3), "evidence": ev})
    return out


def gaps_for(hits: list[dict]) -> list[str]:
    present = {h["surface_id"] for h in hits}
    return [sid for sid in BASELINE_GAPS if sid not in present]


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
    """从「要不要 X / 该不该 X / A 还是 B」里取出二元问题的对象。"""
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
    return Nucleus(agent="", event="", resource="", binary=binary_of(question),
                   raw_question=question or "")


def compile(question: str) -> dict:
    """CIR v1：框架 + binary + 面（含证据）+ 缺口 + 问句。"""
    hits = match_surfaces(question or "")
    gaps = gaps_for(hits)
    question_ids = [q["id"] for q in select_questions(question, hits=hits)]
    core = {
        "ir_version": IR_VERSION,
        "frame": frame_of(question),
        "binary": binary_of(question),
        "surfaces": hits,
        "gaps": gaps,
        "question_ids": question_ids,
    }
    canonical = json.dumps({
        "ir_version": core["ir_version"],
        "frame": core["frame"],
        "binary": core["binary"],
        "surfaces": [{"surface_id": s["surface_id"], "confidence": s["confidence"]}
                     for s in core["surfaces"]],
        "gaps": core["gaps"],
        "question_ids": core["question_ids"],
    }, ensure_ascii=False, sort_keys=True)
    core["diagnostics"] = {
        "rule": "lexicon",
        "surface_count": len(load_surfaces()),
        "lexicon_count": len(load_lexicon()),
    }
    core["ir_hash"] = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
    return core


def select_questions(question: str, has_history: bool = False,
                     limit: int = 10, hits: list[dict] | None = None) -> list[dict]:
    """按 lexicon 命中的面 + 缺口，从问句库挑这次该问的固定问句。"""
    from . import questions

    bank = {q["id"]: q for q in questions.load()}
    if not bank:
        return []
    surfaces = {s["surface_id"]: s for s in load_surfaces()}
    hits = hits if hits is not None else match_surfaces(question or "")
    # 环境事实（天气/时间等）只展示、不进面；如果只提到天气，hits 会是空的。
    core_hit = any(h["surface_id"] in CORE_SURFACES for h in hits)
    gaps = gaps_for(hits) if core_hit else []
    order = [h["surface_id"] for h in hits] + gaps

    # 先放两条通用 probe：过去行为 + 是否反复想。它们对几乎所有决定都成立。
    ids: list[str] = [pid for pid in UNIVERSAL_PROBES
                      if pid in bank and not (bank[pid].get("when") == "first_time" and has_history)]

    # 每个面一条；核心域再轮转补到 limit，非核心域只取第一圈（避免用财务/收入类问题凑数）。
    per_surface: list[list[str]] = []
    for sid in order:
        probes = []
        for pid in (surfaces.get(sid, {}).get("probes") or []):
            q = bank.get(pid)
            if q is None or pid in probes:
                continue
            if q.get("when") == "first_time" and has_history:
                continue
            probes.append(pid)
        if probes:
            per_surface.append(probes)

    max_rounds = 10
    for round_idx in range(max_rounds):
        added = False
        for probes in per_surface:
            if round_idx < len(probes):
                pid = probes[round_idx]
                if pid not in ids:
                    ids.append(pid)
                    added = True
            if len(ids) >= limit:
                break
        if len(ids) >= limit or not added:
            break

    return [bank[i] for i in ids if i in bank][:max(1, limit)]

