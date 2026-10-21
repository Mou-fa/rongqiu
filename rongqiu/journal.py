"""判断日志与事后校准。

绒球的全部分量，都押在一句话上：

    长期命中率 ≈ 输出的置信度

没有这个闭环，811 只是一个漂亮的断言。有了它，811 是一个**可以被证伪的
经验预测**：N=8 的判断，命中率应当接近 80%。

记录的粒度是「一次判断一条」，不聚合、不改写、不删。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import DATA

JOURNAL = DATA / "journal.jsonl"
DEFAULT_RESOLVE_DAYS = 3

# 回收期要跟着问题的时间尺度走。
# 默认 3 天（2026-10-20 从 7 天缩短）：等太久，用户早忘了当时的犹豫，
# 数据也要等一周才开始积累。按问题里的时间词定回收期：今晚的决定明天就能回收。
# 「这周 / 周末」仍然保留 7 天——事件本身要到周末才发生，太早回收只会拿到「还没发生」。
_SHORT = ("今晚", "今天", "明天", "等一下", "马上", "现在")
_WEEK = ("这周", "本周", "周末", "这几天")
_LONG = ("这个月", "下个月", "今年", "年底", "明年")


def resolve_days_for(question: str) -> int:
    q = question or ""
    if any(k in q for k in _SHORT):
        return 1
    if any(k in q for k in _WEEK):
        return 7
    if any(k in q for k in _LONG):
        return 30
    return DEFAULT_RESOLVE_DAYS


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def _norm_question(question: str) -> str:
    return re.sub(r"\s+", "", (question or "").strip())


def _derive_decision_id(question: str, ts: str) -> str:
    """同一句话 + 同一天 = 同一个决策；跨天算新的决策。"""
    day = (ts or "")[:10] or datetime.now().astimezone().strftime("%Y-%m-%d")
    raw = _norm_question(question) + "|" + day
    return "dec_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _decision_key(entry: dict) -> str:
    did = entry.get("decision_id")
    if did:
        return str(did)
    return _derive_decision_id(entry.get("nucleus", ""), entry.get("ts", ""))


def _collapse(entries: list[dict]) -> list[dict]:
    """每个 decision 只留最新 revision；旧数据没有 decision_id 的按 nucleus+日期归并。"""
    latest: dict[str, dict] = {}
    for e in entries:
        key = _decision_key(e)
        cur = latest.get(key)
        if cur is None or str(e.get("ts", "")) >= str(cur.get("ts", "")):
            latest[key] = e
    return list(latest.values())


def p_yes(entry: dict) -> float:
    """把「倾向 + 置信度」还原成 P(原核成立)。

    这是校准的唯一入口。lean 只说明方向，置信度说明强度，
    两者合起来才是概率。
    """
    c = float(entry["confidence"])
    return c if entry["lean"] == "yes" else 1.0 - c


def record(judgment, question: str, resolve_days: int | None = None,
           extra: dict | None = None, user_lean: str | None = None,
           decision_id: str | None = None) -> dict:
    if resolve_days is None:
        resolve_days = resolve_days_for(question)
    DATA.mkdir(parents=True, exist_ok=True)
    now = _now()
    requested = decision_id
    did = decision_id or _derive_decision_id(question, now)
    same = [e for e in load() if _decision_key(e) == did]
    prev = _collapse(same)[0] if same else None
    if requested is None and prev is not None and prev.get("outcome") is not None:
        # 同一个决策已经回收过：再判断算新决策，不覆盖旧结果
        did = did + "-" + datetime.now().strftime("%H%M%S")
        prev = None
    revision = (int(prev.get("revision", 1)) + 1) if prev else 1
    entry = {
        "id": _new_id(),
        "ts": now,
        "decision_id": did,
        "revision": revision,
        "supersedes": prev.get("id") if prev else None,
        "nucleus": question,
        "lean": judgment.lean,
        "confidence": round(float(judgment.confidence), 4),
        "p_yes": round(p_yes({"lean": judgment.lean,
                              "confidence": judgment.confidence}), 4),
        "n": judgment.n,
        "determinability": round(judgment.determinability, 4),
        "support_ratio": round(judgment.support_ratio, 4),
        "rule": judgment.rule,
        "assumption": judgment.assumption,
        "unknown": judgment.unknown,
        "reason": getattr(judgment, "reason", ""),
        "facts": [f.as_dict() for f in judgment.facts],
        "resolve_by": (datetime.now(timezone.utc).astimezone()
                       + timedelta(days=resolve_days)).isoformat(timespec="seconds"),
        "outcome": None,
        "outcome_note": "",
        "resolved_at": None,
        # 用户自己的直觉（会 / 不会）。只用于三方对照：
        # 你的判断、系统的判断、实际结果，谁更准。
        "user_lean": user_lean if user_lean in ("yes", "no") else None,
    }
    if extra:
        entry.update(extra)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load() -> list[dict]:
    if not JOURNAL.exists():
        return []
    out = []
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def pending(as_of: str | None = None) -> list[dict]:
    now = as_of or _now()
    return [e for e in _collapse(load())
            if e.get("outcome") is None and e.get("resolve_by", "") <= now]


def unresolved() -> list[dict]:
    """全部还没回收的，含未到期的。只回最新 revision。"""
    return [e for e in _collapse(load()) if e.get("outcome") is None]


def due_soon(days: int = 7, as_of: str | None = None) -> list[dict]:
    """还没到期但 N 天内会到期的。"""
    now = datetime.fromisoformat(as_of or _now())
    horizon = now + timedelta(days=days)
    out = []
    for e in unresolved():
        try:
            rb = datetime.fromisoformat(e.get("resolve_by", ""))
        except ValueError:
            continue
        if now < rb <= horizon:
            out.append(e)
    return out


def resolve(entry_id: str, outcome: str, note: str = "") -> dict | None:
    """回收一条判断的真实结果。outcome: 'yes' | 'no'"""
    outcome = outcome.strip().lower()
    if outcome not in ("yes", "no"):
        raise ValueError("outcome 只能是 yes 或 no")
    entries = load()
    target = None
    for e in entries:
        if e["id"] == entry_id:
            target = e
            break
    if target is None:
        return None
    key = _decision_key(target)
    latest = next((e for e in _collapse(entries) if _decision_key(e) == key), target)
    latest["decision_id"] = key
    latest["outcome"] = outcome
    latest["outcome_note"] = note
    latest["resolved_at"] = _now()
    target = latest
    with JOURNAL.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return target


def brier(entries: list[dict]) -> float:
    if not entries:
        return float("nan")
    return sum((p_yes(e) - (1.0 if e["outcome"] == "yes" else 0.0)) ** 2
               for e in entries) / len(entries)


def stats(entries: list[dict] | None = None, bins: int = 5) -> dict:
    """校准报告。只看已回收的判断。"""
    if entries is None:
        entries = _collapse(load())
    else:
        collapsible = [e for e in entries if e.get("decision_id") or e.get("nucleus")]
        plain = [e for e in entries if not (e.get("decision_id") or e.get("nucleus"))]
        entries = _collapse(collapsible) + plain
    resolved = [e for e in entries if e.get("outcome") in ("yes", "no")]
    out = {
        "total": len(entries),
        "resolved": len(resolved),
        "pending": len([e for e in entries if e.get("outcome") is None]),
        "brier": None, "baseline_brier": None, "skill": None,
        "hit_rate": None, "mean_confidence": None,
        "calibration_gap": None,
        "reliability": [], "by_n": [], "by_rule": [],
        "mean_p": None, "chance_brier": 0.25, "chance_skill": None,
        "series": [], "three_way": None,
    }
    if not resolved:
        return out

    b = brier(resolved)
    hit = sum(1 for e in resolved if e["lean"] == e["outcome"]) / len(resolved)
    base_rate = sum(1 for e in resolved if e["outcome"] == "yes") / len(resolved)
    base_b = sum((base_rate - (1.0 if e["outcome"] == "yes" else 0.0)) ** 2
                 for e in resolved) / len(resolved)

    # 校准偏差：命中率 - 平均置信度。
    # 正数 = 你比你以为的更准（保守），负数 = 你过度自信。
    # 这是「你自己的偏差画像」里最重要的一行。
    out.update({
        "calibration_gap": round(hit - (sum(e["confidence"] for e in resolved)
                                        / len(resolved)), 4),
        "brier": round(b, 5),
        "baseline_brier": round(base_b, 5),
        "skill": round(1 - b / base_b, 4) if base_b > 0 else None,
        "hit_rate": round(hit, 4),
        "base_rate": round(base_rate, 4),
        "mean_confidence": round(sum(e["confidence"] for e in resolved) / len(resolved), 4),
        # 可靠性曲线的两条均线：预测均值（p_yes）与实际发生比例（base_rate）。
        "mean_p": round(sum(p_yes(e) for e in resolved) / len(resolved), 4),
        # 相对 50% 盲猜的技巧分；比 base-rate 基线直观，也不会在结果全同向时退化成 0。
        "chance_skill": round(1 - b / 0.25, 4),
    })

    # 可靠性曲线：按 p_yes 分箱，比较预测均值与实际频率
    #
    # 必须是连续分箱。第一版写成了 ordered[i::bins]（交错取样），
    # 把排序彻底打乱，于是五个箱的预测均值全是 0.49——曲线看起来
    # 完美，其实是分箱坏了。排序后跨步取样等于把排序作废。
    ordered = sorted(resolved, key=p_yes)
    size = max(1, len(ordered) // bins)
    chunks = [ordered[i * size:(i + 1) * size] for i in range(bins - 1)]
    chunks.append(ordered[(bins - 1) * size:])
    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        out["reliability"].append({
            "bin": i, "n": len(chunk),
            "p_mean": round(sum(p_yes(e) for e in chunk) / len(chunk), 4),
            "obs": round(sum(1 for e in chunk if e["outcome"] == "yes") / len(chunk), 4),
        })

    # 按 N 分组 —— 811 的核心检验：N=8 的命中率应当接近 80%
    for n in sorted({e["n"] for e in resolved}):
        grp = [e for e in resolved if e["n"] == n]
        out["by_n"].append({
            "n": n, "count": len(grp),
            "determinability": round(n / (n + 2), 4),
            "hit_rate": round(sum(1 for e in grp if e["lean"] == e["outcome"]) / len(grp), 4),
        })

    # 逐条序列：时间曲线与三方对照都要用。只陈述，不评判。
    ordered_by_time = sorted(resolved, key=lambda e: e.get("resolved_at") or e.get("ts") or "")
    out["series"] = [{
        "id": e.get("id"), "ts": e.get("ts"), "resolved_at": e.get("resolved_at"),
        "p_yes": round(p_yes(e), 4), "confidence": e.get("confidence"),
        "lean": e.get("lean"), "outcome": e.get("outcome"),
        "hit": 1 if e["lean"] == e["outcome"] else 0,
        "user_lean": e.get("user_lean"),
        "user_hit": (None if e.get("user_lean") not in ("yes", "no")
                     else (1 if e["user_lean"] == e["outcome"] else 0)),
        "agree": (None if e.get("user_lean") not in ("yes", "no")
                  else (1 if e["user_lean"] == e["lean"] else 0)),
        "n": e.get("n"),
    } for e in ordered_by_time]

    # 三方对照：你的直觉 vs 系统判断 vs 实际结果。
    with_user = [e for e in resolved if e.get("user_lean") in ("yes", "no")]
    if with_user:
        div = [e for e in with_user if e["user_lean"] != e["lean"]]
        out["three_way"] = {
            "samples": len(with_user),
            "user_hit_rate": round(sum(1 for e in with_user
                                       if e["user_lean"] == e["outcome"]) / len(with_user), 4),
            "system_hit_rate": round(sum(1 for e in with_user
                                         if e["lean"] == e["outcome"]) / len(with_user), 4),
            "agree_rate": round(sum(1 for e in with_user
                                    if e["user_lean"] == e["lean"]) / len(with_user), 4),
            "diverge": len(div),
            "system_right_when_diverge": sum(1 for e in div if e["lean"] == e["outcome"]),
            "user_right_when_diverge": sum(1 for e in div if e["user_lean"] == e["outcome"]),
        }

    for rule in sorted({e["rule"] for e in resolved}):
        grp = [e for e in resolved if e["rule"] == rule]
        out["by_rule"].append({
            "rule": rule, "count": len(grp),
            "hit_rate": round(sum(1 for e in grp if e["lean"] == e["outcome"]) / len(grp), 4),
            "mean_confidence": round(sum(e["confidence"] for e in grp) / len(grp), 4),
        })
    return out


def render_stats(s: dict) -> str:
    lines = [
        f"判断总数 {s['total']}   已回收 {s['resolved']}   待回收 {s['pending']}",
    ]
    if not s["resolved"]:
        lines.append("")
        lines.append("还没有回收的结果——校准需要时间，这是正常的。")
        return "\n".join(lines)
    skill_txt = f"{s['skill']:+.4f}" if s["skill"] is not None else "无法计算（结果全同向）"
    lines += [
        "",
        f"Brier        {s['brier']:.4f}   （越低越好）",
        f"基准 Brier   {s['baseline_brier']:.4f}   （永远猜基准率）",
        f"技巧分       {skill_txt}",
        f"命中率       {s['hit_rate']:.1%}   平均置信度 {s['mean_confidence']:.1%}",
        f"校准偏差     {s['calibration_gap']:+.1%}   "
        + ("（比你以为的更准）" if s["calibration_gap"] > 0
           else "（过度自信）" if s["calibration_gap"] < 0 else "（完全校准）"),
        "",
        "可靠性曲线：",
    ]
    for r in s["reliability"]:
        gap = r["obs"] - r["p_mean"]
        lines.append(f"  bin{r['bin']}  n={r['n']:<4d} 预测 {r['p_mean']:.2f}  "
                     f"实际 {r['obs']:.2f}  差 {gap:+.2f}")
    lines += ["", "按 N 分组（811 的核心检验）："]
    for b in s["by_n"]:
        lines.append(f"  N={b['n']:<2d}  可确定 {b['determinability']:.0%}  "
                     f"n={b['count']:<4d} 命中率 {b['hit_rate']:.1%}")
    lines += ["", "按判定规则分组："]
    for b in s["by_rule"]:
        lines.append(f"  {b['rule']:<14s} n={b['count']:<4d} "
                     f"命中率 {b['hit_rate']:.1%}  平均置信 {b['mean_confidence']:.1%}")
    return "\n".join(lines)
