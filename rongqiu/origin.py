"""来源谱系：判断几条材料是不是同一个源头。

为什么需要它：

现在的独立性判据是「来源标签不同就算独立」。但用户拖进来的聊天记录、
截图、通知，大量是同源的——

    三个朋友在同一个群里说同一件事
    十家媒体转载同一条通稿
    同一个人转述了三遍

它们在标签上各不相同，但**误差是同向的，加总不会稀释**。
把同源的材料当成多份独立证据，会直接把 N 和置信度抬虚。

判据：材料追到同一个源头，就只能算一份。
"""

from __future__ import annotations

import json
import re

from .llm import available, complete, load_config

CLUSTER_SYSTEM = """你是「绒球」的来源归并器。

给定一组材料（每条带来源标签和文本），判断哪些是**同一个源头**。

判为同源的典型情况：
- 同一个群聊、同一个人说的同一件事
- 同一张截图被重复转发
- 几家媒体转载同一篇通稿
- 一个人转述另一个人的话（后者是源头）

判为不同源的情况：
- 不同的人各自独立观察到同一现象
- 不同渠道各自独立记录

输出 JSON：{"groups": [[0,2],[1],[3]]} ，每组是同一个源头的材料下标。
每条材料必须恰好出现在一个组里。"""

PROMPT = """材料列表：
{items}

请把同源的归为一组，输出 JSON。"""


def _strip(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    return t.strip()


def _fallback(n: int) -> dict[int, int]:
    """不能归并时，每条各算一个源头。"""
    return {i: i for i in range(n)}


def cluster(scenes: list, cfg=None, use_llm: bool = True) -> dict[int, int]:
    """把场景按来源归并。返回 下标 -> 源头组号。

    失败时退回「每条各算一个源头」——不阻止判断，但不假装归并过。
    """
    n = len(scenes)
    if n <= 1:
        return _fallback(n)
    cfg = cfg or load_config()
    if not use_llm or not available(cfg):
        return _fallback(n)

    items = "\n".join(
        f"{i}. [来源: {getattr(s, 'source', '未知')}] {getattr(s, 'scene', '')}"
        for i, s in enumerate(scenes))
    raw = complete(PROMPT.format(items=items), system=CLUSTER_SYSTEM, cfg=cfg)
    if not raw:
        return _fallback(n)
    try:
        data = json.loads(_strip(raw))
        groups = data.get("groups", []) or []
    except Exception:
        return _fallback(n)

    mapping: dict[int, int] = {}
    gid = 0
    for g in groups:
        members = [int(x) for x in g if 0 <= int(x) < n]
        if not members:
            continue
        for m in members:
            if m not in mapping:
                mapping[m] = gid
        gid += 1
    for i in range(n):
        if i not in mapping:
            mapping[i] = gid
            gid += 1
    return mapping


def effective_count(mapping: dict[int, int]) -> int:
    """归并之后，实际有几个独立源头。"""
    return len(set(mapping.values())) if mapping else 0


def describe(mapping: dict[int, int], scenes: list) -> str:
    groups: dict[int, list[int]] = {}
    for idx, g in mapping.items():
        groups.setdefault(g, []).append(idx)
    lines = [f"材料 {len(scenes)} 条，归并为 {len(groups)} 个独立源头："]
    for g, members in sorted(groups.items()):
        tag = "" if len(members) == 1 else f"  ← {len(members)} 条同源"
        lines.append(f"  源头{g}: " + "、".join(str(m) for m in members) + tag)
    return "\n".join(lines)
