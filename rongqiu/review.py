"""人工点击：从全网命中的场景里，选出「这是我的真实情况」的那几条。

分工是刻意分开的：

    用户   判断「适用性」——这条场景是不是我的真实情况
           只有用户知道自己聚会后累不累、有没有熟人

    系统   判断「倾向性」——这条场景对「去不去」意味着什么
           这是文本语义，机器能判，而且要求前后一致

点击数直接变成 N：选几条，确定槽就增加几条。
"""

from __future__ import annotations

from .llm import available, complete, load_config
from .triples import SceneFact, SUPPORT, OPPOSE, NEUTRAL

DIRECTION_SYSTEM = """你是一个场景倾向判定器。

给定一个原核（一个「是否会发生」的判断）和若干场景，判断每个场景
是让原核更可能成立、还是更不可能成立。

只输出 JSON，形如：
{"items": [{"index": 0, "supports": "support|oppose|neutral"}]}

判断依据：场景描述的是「会发生」的好处/便利 → support；
描述的是「会发生」的阻碍/代价 → oppose；中性描述 → neutral。
不要考虑这个场景是否适用于用户——那是用户自己回答的问题。"""


def select(candidates, selected: list[int] | None = None) -> tuple[list, list]:
    """让用户点选「这是我的真实情况」的场景。

    selected 不为 None 时按给定下标取（供测试/演示），不读 input。
    返回 (选中的候选, 未选中的候选)。
    """
    n = len(candidates)
    print(f"\n全网命中 {n} 条。请只点选「这是你的真实情况」的那几条：")
    print("  用逗号或空格分隔序号，例如 1,3,5。一条都不选就直接回车。\n")
    for i, c in enumerate(candidates):
        print(f"  [{i+1}] {c.text}")

    if selected is not None:
        raw = ",".join(str(i + 1) for i in selected)
        print(f"\n  > {raw or '(不选)'}")
    else:
        try:
            raw = input("\n  > ").strip()
        except EOFError:
            raw = ""

    picked: set[int] = set()
    for token in raw.replace("，", ",").replace(" ", ",").split(","):
        token = token.strip()
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < n:
                picked.add(idx)

    chosen = [candidates[i] for i in sorted(picked)]
    rejected = [candidates[i] for i in range(n) if i not in picked]
    return chosen, rejected


def direction_of(scenes: list[SceneFact], nucleus_binary: str, cfg=None) -> list[SceneFact]:
    """系统判定每条被选中场景的倾向。一次调用判完全部，保证前后一致。"""
    cfg = cfg or load_config()
    if not scenes or not available(cfg):
        for s in scenes:
            s.supports = NEUTRAL
        return scenes

    lines = "\n".join(f"{i}. {s.scene}" for i, s in enumerate(scenes))
    prompt = (f"【原核】{nucleus_binary}，这件事会成立吗？\n\n"
              f"【场景】\n{lines}\n\n"
              "判断每个场景让原核更可能成立（support）、更不可能成立（oppose）、"
              "还是中性（neutral）。只输出 JSON。")
    raw = complete(prompt, system=DIRECTION_SYSTEM, cfg=cfg)
    if not raw:
        for s in scenes:
            s.supports = NEUTRAL
        return scenes
    try:
        import json
        text = raw.strip()
        if text.startswith("```"):
            import re
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"```\s*$", "", text)
        data = json.loads(text.strip())
        for item in data.get("items", []):
            i = int(item.get("index", -1))
            if 0 <= i < len(scenes):
                v = str(item.get("supports", "neutral")).strip().lower()
                scenes[i].supports = v if v in (SUPPORT, OPPOSE, NEUTRAL) else NEUTRAL
    except Exception:
        for s in scenes:
            s.supports = NEUTRAL
    return scenes


def to_scene_facts(chosen, rejected=None) -> list[SceneFact]:
    facts = []
    for i, c in enumerate(chosen):
        facts.append(SceneFact(scene=c.text, source=c.source, order=i))
    return facts


def summarize(facts: list[SceneFact]) -> str:
    sup = sum(1 for f in facts if f.supports == SUPPORT)
    opp = sum(1 for f in facts if f.supports == OPPOSE)
    neu = sum(1 for f in facts if f.supports == NEUTRAL)
    return f"你点选了 {len(facts)} 条；系统判定：支持 {sup} · 反对 {opp} · 中性 {neu}"
