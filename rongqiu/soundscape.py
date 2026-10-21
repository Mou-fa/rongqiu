"""声景库。

见 docs/PROPOSAL.md 第九章。

它不是音乐推荐。区别在四个地方：

    推荐（❌）              声景（✅）
    依据是「你是谁」         依据是「此刻是几点」
    按情绪个性化            对所有人一样
    系统推送                用户自己选
    目标是多待              目标是有一个地方待

这个模块做三件事：
    1. 读曲库
    2. 校验红线（选曲理由不得宣称疗效）
    3. 按时刻分组

第 2 件是重点：红线写在文档里会被忘记，写在校验器里不会。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .paths import config_file

CONFIG = config_file("soundscape.yaml")

# 允许的时刻。只许客观维度，不许「按你的状态」。
MOMENTS = ("dawn", "noon", "night", "rain", "commute", "alone")

# 选曲理由里禁止出现的词。
# 这些词一旦出现，就从「描述音乐」滑进了「宣称疗效」——
# 而「音乐治疗」是有资质要求的领域。见 REDLINES.md。
FORBIDDEN = (
    "治疗", "疗愈", "缓解", "改善", "焦虑", "抑郁",
    "失眠", "助眠", "疗效", "医学", "处方", "康复",
    "抗压", "镇静", "安神",
)

MAX_NOTE = 30      # 选曲理由长度上限（字）


class RedlineError(ValueError):
    """曲目违反红线。"""


def _load() -> dict:
    try:
        return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def check(track: dict) -> list[str]:
    """校验一个曲目。返回问题列表，空列表表示通过。"""
    problems = []
    note = str(track.get("note") or "")
    title = str(track.get("title") or "")

    if not title:
        problems.append("缺少曲名")
    if not track.get("duration"):
        problems.append("缺少时长")
    if track.get("moment") not in MOMENTS:
        problems.append(f"时刻标签非法：{track.get('moment')}")

    for w in FORBIDDEN:
        if w in note:
            problems.append(f"选曲理由出现「{w}」——这是疗效宣称，不是描述音乐")
        if w in title:
            problems.append(f"曲名出现「{w}」——这是疗效宣称")
    if len(note) > MAX_NOTE:
        problems.append(f"选曲理由超过 {MAX_NOTE} 字（当前 {len(note)}）")
    return problems


def validate() -> dict:
    """整库校验。返回 {ok, problems}，问题按曲目分组。"""
    data = _load()
    tracks = data.get("tracks") or []
    problems = {}
    for i, t in enumerate(tracks):
        p = check(t)
        if p:
            problems[t.get("title") or f"第 {i+1} 条"] = p
    return {"ok": not problems, "problems": problems, "total": len(tracks)}


def catalog() -> dict:
    """给界面的曲库：按时刻分组。

    不排序、不个性化、不推荐——只按固定顺序列出。
    """
    data = _load()
    names = {m["id"]: m["name"] for m in (data.get("moments") or [])
             if isinstance(m, dict) and m.get("id") in MOMENTS}
    tracks = [t for t in (data.get("tracks") or [])
              if isinstance(t, dict) and not check(t)]

    groups = []
    for mid in MOMENTS:
        items = [t for t in tracks if t.get("moment") == mid]
        if not items:
            continue
        groups.append({
            "id": mid,
            "name": names.get(mid, mid),
            "tracks": [{
                "title": t.get("title"),
                "duration": t.get("duration"),
                "note": t.get("note", ""),
                "url": t.get("url", ""),
                "source": t.get("source", ""),
                "playable": bool(t.get("url")),
            } for t in items],
        })

    rejected = [{"title": t.get("title"), "problems": check(t)}
                for t in (data.get("tracks") or [])
                if isinstance(t, dict) and check(t)]

    return {
        "groups": groups,
        "total": len(tracks),
        "rejected": rejected,
        # 这一层永远不收费，也永远不产生任何使用数据
        "free": True,
        "personalized": False,
    }
