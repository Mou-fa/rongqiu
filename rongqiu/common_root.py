"""跨决定共同根因。

人以为自己有五个问题，其实常常只有一个。

这个模块做的事：把用户所有的判断记录放在一起，找出「同一个第一接触面
出现在多个决定里」的情况。

    「要不要去聚餐」  ← 面：我 最近很累
    「要不要接这个活」 ← 面：我 最近很累
    「周末要不要出门」 ← 面：我 最近很累
                          ↑
                    同一个根

注意三条纪律：

1. 只陈述结构，不给建议。
   输出是「这三个决定共享同一个面」，不是「所以你应该先解决累的问题」。

2. 排除通用问句。
   「你上一次遇到这种情况最后怎么选的」在每个决定里都出现，
   但它不是共同根因，它是问卷本身。必须排除。

3. 只认用户自己的面。
   用户自述（最硬）和用户认领的场景。系统自己找的网络内容不算。

已知边界：匹配是基于字面的（三段式对齐 + 字符重合），不是语义的。
「最近很累」和「比较累」这种同义改写认不出来——它们需要 embedding。
但同一个抽取管线对同一个事实通常写法稳定，字面匹配能覆盖绝大多数情况。
真要上语义匹配，那是把 LLM 用在「比对」上，成本高且有稳定性风险，
不值得为这一点召回率付。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import journal

# 可以参与共同根因判定的来源
SURFACE_SOURCES = ("用户自述",)
# 这些来源在每个决定里内容都一样，是问卷本身，不能当根因
GENERIC_SOURCES = ("主动询问",)

_MIN_LEN = 3          # 太短的片段不参与匹配，避免「我」这种噪声
_SIMILAR = 0.72       # 字符二元组 Jaccard 阈值

_CLEAN = re.compile(r"[\s\u3000，。！？、；：「」『』（）【】《》\-—…·,.!?;:\"'()\[\]/]+")


def _normalize(text: str) -> str:
    """去掉空白、标点、连接符，只留内容字符。"""
    if not text:
        return ""
    return _CLEAN.sub("", str(text)).lower()


def _bigrams(s: str) -> set[str]:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _dice(a: str, b: str) -> float:
    ga, gb = _bigrams(a), _bigrams(b)
    if not ga or not gb:
        return 0.0
    return 2 * len(ga & gb) / (len(ga) + len(gb))


def similar(a: str, b: str) -> bool:
    """两个面是不是同一个面。

    事实的写法是「主 谓 宾」，三段用空格分开。所以优先做三段式比较：
    主语和宾语对齐、谓语相近，才算同一个面。

    为什么不用整串相似度：中文同义改写靠字符重合度会漏
    （「最近很累」vs「很累」几乎不重合），但整串又容易误判
    （「最近很累」vs「最近很开心」宾语一样、谓语相反）。
    三段式正好把这两个毛病都挡掉。
    """
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True

    # 一个包含另一个：截断或省略的情况
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) >= 4 and short in long:
        return True

    # 三段式：主语 + 宾语必须一致，谓语相近
    pa = [p for p in str(a).split() if p.strip()]
    pb = [p for p in str(b).split() if p.strip()]
    if len(pa) == 3 and len(pb) == 3:
        if _normalize(pa[0]) == _normalize(pb[0]) and _normalize(pa[2]) == _normalize(pb[2]):
            ea, eb = _normalize(pa[1]), _normalize(pb[1])
            if ea == eb or ea in eb or eb in ea:
                return True
            if _dice(ea, eb) >= 0.6:
                return True

    # 兜底：整串高度重合
    return _dice(na, nb) >= 0.8


@dataclass
class Decision:
    id: str
    question: str
    ts: str
    resolved: bool
    surfaces: list[str] = field(default_factory=list)


@dataclass
class Group:
    surface: str        # 显示用的那句话（取组里出现最多的原始写法）
    decisions: list[Decision]

    def as_dict(self) -> dict:
        return {
            "surface": self.surface,
            "count": len(self.decisions),
            "decisions": [
                {"id": d.id, "question": d.question, "ts": d.ts, "resolved": d.resolved}
                for d in self.decisions
            ],
        }


def surfaces_of(entry: dict) -> list[str]:
    """一条判断记录里，属于用户自己的第一接触面。"""
    out = []
    for f in entry.get("facts") or []:
        src = f.get("source") or ""
        if src in GENERIC_SOURCES:
            continue
        if src not in SURFACE_SOURCES:
            continue
        scene = (f.get("scene") or "").strip()
        if len(_normalize(scene)) >= _MIN_LEN:
            out.append(scene)
    return out


def load_decisions(days: int = 90) -> list[Decision]:
    """近 N 天的判断记录。默认 90 天——太久以前的决定不该混进「正在纠结的」。"""
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    out = []
    for e in journal.load():
        try:
            ts = datetime.fromisoformat(e.get("ts", ""))
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.astimezone()
        if ts < cutoff:
            continue
        out.append(Decision(
            id=e.get("id", ""),
            question=e.get("nucleus", "") or e.get("question", ""),
            ts=e.get("ts", ""),
            resolved=bool(e.get("outcome")),
            surfaces=surfaces_of(e),
        ))
    return out


def find_groups(decisions: list[Decision], min_count: int = 2) -> list[Group]:
    """把共享同一个面的「不同决定」聚成组。

    关键：必须按「问题」去重。

    同一个人把同一件事问十遍，那叫反复纠结，不叫跨决定共同根因。
    测试日志里就出过这个坑：12 个组全是同一个问题被重复记录，
    看起来像发现，实际什么都不是。

    所以判据是「至少 min_count 个不同的问题，共享同一个面」。
    """
    # 面 → 参与的决定
    buckets: list[tuple[str, set[str]]] = []   # (代表写法, {decision_id})
    index: dict[str, Decision] = {}

    for d in decisions:
        index[d.id] = d
        for s in d.surfaces:
            for label, ids in buckets:
                if similar(s, label):
                    ids.add(d.id)
                    break
            else:
                buckets.append((s, {d.id}))

    groups = []
    for label, ids in buckets:
        members = [index[i] for i in ids if i in index]
        if not members:
            continue

        # 按问题去重：同一件事只留最近一次
        by_q: dict[str, Decision] = {}
        for d in members:
            k = _normalize(d.question)
            if k not in by_q or d.ts > by_q[k].ts:
                by_q[k] = d
        distinct = list(by_q.values())

        if len(distinct) < min_count:
            continue

        distinct.sort(key=lambda x: x.ts, reverse=True)
        groups.append(Group(surface=label, decisions=distinct))

    groups.sort(key=lambda g: (-len(g.decisions), g.decisions[0].ts))
    return groups


def all_groups(days: int = 90) -> list[dict]:
    return [g.as_dict() for g in find_groups(load_decisions(days))]


def related_to(entry_id: str, days: int = 90) -> list[dict]:
    """和某一条判断共享面的「其他决定」。用于判断完成后当场显示。

    注意：同一条记录反复问同一个问题，不算「其他决定」。
    所以这里按问题去重之后再排除自己。
    """
    ds = load_decisions(days)
    me = next((d for d in ds if d.id == entry_id), None)
    if me is None:
        return []
    my_q = _normalize(me.question)

    for g in find_groups(ds):
        questions = {_normalize(d.question) for d in g.decisions}
        if my_q not in questions:
            continue
        others = [d for d in g.decisions if _normalize(d.question) != my_q]
        if not others:
            continue
        return [{
            "surface": g.surface,
            "count": len(others),
            "decisions": [
                {"id": d.id, "question": d.question, "ts": d.ts}
                for d in others
            ],
        }]
    return []
