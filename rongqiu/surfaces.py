"""面配置：读取 configs/surfaces.jsonl，做 probe→面 的映射。

输入层的选择器已经用这份配置；这里补的是「回答之后」：
把用户答的 probe 归回它所属的面，供按面校准使用。
"""
from __future__ import annotations

import json

from .paths import config_file

SURFACES_PATH = config_file("surfaces.jsonl")


def load() -> list[dict]:
    try:
        if not SURFACES_PATH.exists():
            return []
        return [json.loads(x) for x in
                SURFACES_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
    except Exception:
        return []


def probe_map() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for s in load():
        sid = s.get("surface_id")
        if not sid:
            continue
        for pid in s.get("probes") or []:
            out.setdefault(pid, []).append(sid)
    return out


def for_answers(answers: list, facts: list) -> list[dict]:
    """answers 与 facts 按顺序一一对应；返回 [{surface, direction}]。"""
    mapping = probe_map()
    out = []
    for i, a in enumerate(answers):
        if i >= len(facts):
            break
        qid = a.get("id") if isinstance(a, dict) else getattr(a, "id", "")
        direction = getattr(facts[i], "supports", "")
        for sid in mapping.get(qid, []):
            out.append({"surface": sid, "direction": direction})
    return out


def names() -> dict[str, str]:
    return {s.get("surface_id"): s.get("name") or s.get("surface_id")
            for s in load() if s.get("surface_id")}
