"""校准缺口预警。

它回答一个问题：

    「这次你说 85%。但你在这一类上，历史命中是 61%。」

注意这是唯一一种「用数据帮用户」又不算引导的方式：
它说的是「你以前是什么样」，不是「你这次该怎样」。

三条纪律：
1. 样本不够不说。少于 MIN_SAMPLES 条已回收记录，沉默。
2. 只说数字，不给建议。不写「所以你应该降低预期」。
3. 缺口小的时候不说。±THRESHOLD 以内视为校准良好。
"""

from __future__ import annotations

from . import journal

# 决定类型。关键词是给「分类」用的，不是给「判断」用的，
# 所以命中几个词不重要，取命中最多的一类。
CATEGORIES: dict[str, tuple[str, ...]] = {
    "工作": ("工作", "加班", "老板", "同事", "项目", "面试", "offer", "跳槽",
             "辞职", "升职", "汇报", "开会", "客户", "团队", "岗位", "转岗",
             "任务", "出差", "绩效", "创业"),
    "社交": ("聚餐", "聚会", "朋友", "约", "见面", "回复", "婚礼", "生日",
             "团建", "群", "聊天", "表白", "关系", "社交", "邀请", "同学",
             "亲戚", "爸妈", "家人"),
    "消费": ("买", "钱", "预算", "花", "贵", "便宜", "手机", "电脑", "订阅",
             "付费", "退货", "消费", "价格", "存款", "理财", "房租", "账单"),
    "健康": ("身体", "累", "睡", "病", "医院", "药", "运动", "跑步", "头",
             "不舒服", "熬夜", "体检", "健康", "医生", "疼", "疲", "休息"),
    "学习": ("学", "课", "考试", "书", "报名", "证书", "考研", "论文",
             "培训", "读书", "背", "复习"),
}

OTHER = "其他"
MIN_SAMPLES = 5        # 少于这么多条已回收记录，不预警
THRESHOLD = 0.10       # 缺口小于这个值，视为校准良好


def category_of(question: str) -> str:
    """按关键词给决定归类。取命中最多的一类，平票按固定顺序。"""
    q = str(question or "")
    best, best_hits = OTHER, 0
    for name, words in CATEGORIES.items():
        hits = sum(1 for w in words if w in q)
        if hits > best_hits:
            best, best_hits = name, hits
    return best


def _resolved(entries: list[dict] | None = None) -> list[dict]:
    entries = entries if entries is not None else journal.load()
    return [e for e in entries if e.get("outcome") in ("yes", "no")]


def summarize(entries: list[dict]) -> dict:
    """一组已回收记录：平均置信度 vs 实际命中率，以及缺口。"""
    n = len(entries)
    if not n:
        return {"samples": 0, "hit_rate": None, "mean_confidence": None,
                "gap": None, "direction": None}
    hit = sum(1 for e in entries if e.get("lean") == e.get("outcome")) / n
    conf = sum(float(e.get("confidence") or 0) for e in entries) / n
    gap = hit - conf          # 负数 = 高估（过度自信）
    if gap <= -THRESHOLD:
        direction = "over"
    elif gap >= THRESHOLD:
        direction = "under"
    else:
        direction = "ok"
    return {
        "samples": n,
        "hit_rate": round(hit, 4),
        "mean_confidence": round(conf, 4),
        "gap": round(gap, 4),
        "direction": direction,
    }


def by_category(entries: list[dict] | None = None) -> list[dict]:
    """按决定类型分组的校准报告。只列有回收记录的类型。"""
    resolved = _resolved(entries)
    buckets: dict[str, list[dict]] = {}
    for e in resolved:
        cat = category_of(e.get("nucleus") or e.get("question") or "")
        buckets.setdefault(cat, []).append(e)

    out = []
    for cat, group in buckets.items():
        s = summarize(group)
        s["category"] = cat
        s["enough"] = len(group) >= MIN_SAMPLES
        out.append(s)
    # 样本多的排前面，其次缺口大的
    out.sort(key=lambda x: (-x["samples"], -abs(x["gap"] or 0)))
    return out


def gap_for(question: str, confidence: float,
            entries: list[dict] | None = None) -> dict | None:
    """这次判断所在类型的校准缺口。

    样本不足或缺口不大时返回 None——沉默比凑合说一句好。
    """
    cat = category_of(question)
    resolved = _resolved(entries)
    group = [e for e in resolved
             if category_of(e.get("nucleus") or e.get("question") or "") == cat]
    if len(group) < MIN_SAMPLES:
        return None

    s = summarize(group)
    if s["direction"] == "ok":
        return None

    current = round(float(confidence or 0), 4)
    s.update({
        "category": cat,
        "current_confidence": current,
        # 这次给的把握，比历史平均水平高/低多少
        "current_vs_history": round(current - s["mean_confidence"], 4),
    })
    s["message"] = (
        f"这一类（{cat}）你给了 {current * 100:.0f}% 的把握。"
        f"过去 {s['samples']} 条同类判断，你平均给 "
        f"{s['mean_confidence'] * 100:.0f}%，实际命中 {s['hit_rate'] * 100:.0f}%。"
    )
    return s
