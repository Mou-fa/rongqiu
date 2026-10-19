"""判断漂移。

同一个决定，隔一段时间再判一次，两次之间什么变了？

    「是事实变了，还是你变了？」

如果是事实变了 → 你该更新判断。
如果是你变了、事实没变 → 那是情绪在替你判。

这是「漂移」和「成长」的区别，而以前没人分得清。

一条关键判据：
    同一个问题在一小时内问五遍，不叫漂移，叫反复纠结。
    所以两次判断之间必须有足够的时间间隔（MIN_GAP_HOURS），
    否则一律不算。

三条纪律：
1. 只陈述差异，不评判对错。两次判断没有哪个更对。
2. 事实没变但结论变了，不是错误，是一个信号。
3. 不推测原因。只说「变了什么」，不说「为什么变」。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from . import journal

MIN_GAP_HOURS = 12       # 两次判断至少隔这么久，才算一次「再判」
CONF_DELTA = 0.10        # 置信度变化小于这个值，视为没变

_CLEAN = re.compile(r"[\s\u3000，。！？、；：「」『』（）【】《》\-—…·,.!?;:\"'()\[\]/]+")


def _norm(s: str) -> str:
    return _CLEAN.sub("", str(s or "")).lower()


def _ts(entry: dict) -> datetime | None:
    try:
        t = datetime.fromisoformat(entry.get("ts", ""))
    except (ValueError, TypeError):
        return None
    return t.astimezone() if t.tzinfo else t


def _facts(entry: dict) -> set[str]:
    out = set()
    for f in entry.get("facts") or []:
        s = (f.get("scene") or "").strip()
        if s:
            out.add(_norm(s))
    return out


def _brief(entry: dict) -> dict:
    return {
        "id": entry.get("id"),
        "ts": entry.get("ts"),
        "lean": entry.get("lean"),
        "confidence": entry.get("confidence"),
        "n": entry.get("n"),
    }


def compare(first: dict, last: dict) -> dict | None:
    """比较同一条判断的两次记录。"""
    t1, t2 = _ts(first), _ts(last)
    if not t1 or not t2:
        return None
    gap_h = abs((t2 - t1).total_seconds()) / 3600
    if gap_h < MIN_GAP_HOURS:
        return None

    f1, f2 = _facts(first), _facts(last)
    added = sorted(f2 - f1)
    removed = sorted(f1 - f2)
    flipped = first.get("lean") != last.get("lean")
    d_conf = round((last.get("confidence") or 0) - (first.get("confidence") or 0), 4)

    if added or removed:
        kind = "facts"          # 事实变了
    elif flipped or abs(d_conf) >= CONF_DELTA:
        kind = "self"           # 事实没变，你变了
    else:
        kind = "none"

    if kind == "none":
        return None

    return {
        "kind": kind,
        "gap_hours": round(gap_h, 1),
        "first": _brief(first),
        "last": _brief(last),
        "added": added[:6],
        "removed": removed[:6],
        "added_count": len(added),
        "removed_count": len(removed),
        "flipped": flipped,
        "confidence_delta": d_conf,
    }


def _message(q: str, c: dict) -> str:
    if c["kind"] == "facts":
        parts = []
        if c["added_count"]:
            parts.append(f"新增 {c['added_count']} 条")
        if c["removed_count"]:
            parts.append(f"消失 {c['removed_count']} 条")
        s = "两次之间，事实变了：" + "、".join(parts) + "。"
        if c["flipped"]:
            s += "结论也跟着翻转了。"
        return s
    # self
    if c["flipped"]:
        return ("两次之间，事实没有增减，但结论从「" +
                ("会" if c["first"]["lean"] == "yes" else "不会") + "」变成了「" +
                ("会" if c["last"]["lean"] == "yes" else "不会") + "」。")
    direction = "上升" if c["confidence_delta"] > 0 else "下降"
    return ("两次之间，事实没有增减，但置信度" + direction + "了 " +
            f"{abs(c['confidence_delta']) * 100:.0f} 个百分点。")


def detect(days: int = 365) -> list[dict]:
    """找出所有「同一个决定隔了一段时间又判了一次」的情况。"""
    entries = journal.load()
    cutoff_ok = True
    by_q: dict[str, list[dict]] = {}
    for e in entries:
        q = (e.get("nucleus") or "").strip()
        t = _ts(e)
        if not q or not t:
            continue
        if cutoff_ok and (datetime.now().astimezone() - t).days > days:
            continue
        by_q.setdefault(_norm(q), []).append(e)

    out = []
    for _, group in by_q.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda e: e.get("ts") or "")
        first, last = group[0], group[-1]
        c = compare(first, last)
        if c is None:
            continue
        c["question"] = last.get("nucleus") or first.get("nucleus") or ""
        c["times"] = len(group)
        c["message"] = _message(c["question"], c)
        out.append(c)

    # 事实变了排前面（更有信息量），其次时间间隔长的
    out.sort(key=lambda x: (x["kind"] != "facts", -x["gap_hours"]))
    return out
