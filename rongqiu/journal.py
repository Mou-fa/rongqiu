"""判断日志与事后校准。

绒球的全部分量，都押在一句话上：

    长期命中率 ≈ 输出的置信度

没有这个闭环，811 只是一个漂亮的断言。有了它，811 是一个**可以被证伪的
经验预测**：N=8 的判断，命中率应当接近 80%。

记录的粒度是「一次判断一条」，不聚合、不改写、不删。
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
JOURNAL = DATA / "journal.jsonl"
DEFAULT_RESOLVE_DAYS = 7

# 回收期要跟着问题的时间尺度走。
# 「今晚去不去聚餐」锁死 7 天再问，用户早忘了当时的犹豫；而且数据要等一周
# 才开始积累。按问题里的时间词定回收期，今晚的决定明天就能回收。
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


def p_yes(entry: dict) -> float:
    """把「倾向 + 置信度」还原成 P(原核成立)。

    这是校准的唯一入口。lean 只说明方向，置信度说明强度，
    两者合起来才是概率。
    """
    c = float(entry["confidence"])
    return c if entry["lean"] == "yes" else 1.0 - c


def record(judgment, question: str, resolve_days: int | None = None,
           extra: dict | None = None) -> dict:
    if resolve_days is None:
        resolve_days = resolve_days_for(question)
    DATA.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": _new_id(),
        "ts": _now(),
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
    return [e for e in load() if e.get("outcome") is None and e.get("resolve_by", "") <= now]


def unresolved() -> list[dict]:
    """全部还没回收的，含未到期的。"""
    return [e for e in load() if e.get("outcome") is None]


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
    target["outcome"] = outcome
    target["outcome_note"] = note
    target["resolved_at"] = _now()
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
    entries = entries if entries is not None else load()
    resolved = [e for e in entries if e.get("outcome") in ("yes", "no")]
    out = {
        "total": len(entries),
        "resolved": len(resolved),
        "pending": len([e for e in entries if e.get("outcome") is None]),
        "brier": None, "baseline_brier": None, "skill": None,
        "hit_rate": None, "mean_confidence": None,
        "calibration_gap": None,
        "reliability": [], "by_n": [], "by_rule": [],
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
