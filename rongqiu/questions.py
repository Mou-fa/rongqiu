"""主动询问。

原则由用户从心理咨询师角度确定，这里只负责**按原则执行**，不发明问句。

边界（来自 811 权限契约）：
- 只问「发生过的、能被看见的」——行为、处境、历史
- 不问「为什么」——动机、感受、关系
- 用户不答也没关系，不追问

问句本身放在 configs/questions.yaml，用户可以随时增删。
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "configs" / "questions.yaml"

DEFAULT = {
    "id": "last_time",
    "text": "你上一次遇到这种情况，最后怎么选的？",
    "when": "always",
    "why": "",
}


def load() -> list[dict]:
    """读问题库。文件不存在就用内置的那一句，不报错。"""
    if not QUESTIONS_PATH.exists():
        return [dict(DEFAULT)]
    try:
        data = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return [dict(DEFAULT)]
    items = data.get("questions") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text", "")).strip()
        if not text:
            continue
        out.append({
            "id": str(it.get("id", "")).strip() or f"q{len(out)}",
            "text": text,
            "when": str(it.get("when", "always")).strip() or "always",
            "why": str(it.get("why", "")).strip(),
        })
    return out or [dict(DEFAULT)]


def pick(nucleus, has_history: bool = False) -> list[dict]:
    """挑出该问的问题。

    只返回「现在该问」的，不返回全部。第一次来的人问历史，老用户也问历史——
    'first_time' 留给将来「还没做过类似决定」的场景。
    """
    out = []
    for q in load():
        when = q.get("when", "always")
        if when == "first_time" and has_history:
            continue
        out.append(q)
    return out


def render(question: dict, nucleus) -> dict:
    """把问句里的槽填上。目前只有 {resource}。"""
    text = question["text"]
    resource = getattr(nucleus, "resource", "") or ""
    if "{resource}" in text and resource:
        text = text.replace("{resource}", resource)
    elif "{resource}" in text:
        # 资源为空时去掉占位符，别把花括号露给用户
        text = text.replace("{resource}", "")
    return {**question, "text": text}


def for_nucleus(nucleus, has_history: bool = False) -> list[dict]:
    return [render(q, nucleus) for q in pick(nucleus, has_history)]
