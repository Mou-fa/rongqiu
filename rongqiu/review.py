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

DIRECTION_SYSTEM = """你是「绒球」的方向判定器。

给定一个原核（「某件事会不会发生」）和一组场景，判断每个场景让这件事
**真的发生**的可能性升高（support）还是降低（oppose）。

【最关键的一条：判「会不会做」，不判「想不想做」】

一个场景完全可能让用户「更想」做某件事，同时让他「更不可能」真的去做。
最典型的就是疲惫：
    累 → 更想逃离现状（意愿上升）
    累 → 没有精力投简历、面试、搬家（行动下降）
原核问的是「会不会」，所以疲惫这一类应当判 oppose。

每判一条之前，先写一句理由，然后才给标签。理由必须回答那个问题：
**如果这件事是真的，这个人真正采取行动的可能性是升还是降？**

【常见判法】
- 已经在行动（投了简历、看了招聘、攒了钱）→ support
- 有推力（公司搬迁、被边缘化、关系破裂）→ support
- 有能力承担后果（有存款、有退路、有下家）→ support
- 有先例（过去反复做过同类决定）→ support
- 现状可接受、没有推力 → oppose
- 身体或时间上不允许（生病、要早起、太累）→ oppose

【硬约束】不允许 neutral。每一条必须在 support 和 oppose 里选一个。

只输出 JSON：
{"items": [{"index": 0, "reason": "一句方向理由", "supports": "support|oppose"}]}"""


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


def direction_of(scenes: list[SceneFact], nucleus_binary: str, cfg=None,
                 runs: int = 3) -> list[SceneFact]:
    """系统判定每条场景的倾向。

    跑 runs 次取多数。单次调用不稳定——同一个场景换个时间判，方向可能反。
    抽取已经用共识解决了随机性，判向不能例外：它直接决定 N 和支持率。
    """
    cfg = cfg or load_config()
    if not scenes or not available(cfg):
        for s in scenes:
            s.supports = NEUTRAL
        return scenes
    if runs > 1:
        votes: dict[int, list[str]] = {}
        for _ in range(runs):
            single = [SceneFact(scene=s.scene, source=s.source, order=s.order)
                      for s in scenes]
            _direction_once(single, nucleus_binary, cfg)
            for s in single:
                votes.setdefault(s.order, []).append(s.supports)
        for s in scenes:
            vs = votes.get(s.order, [])
            if vs:
                s.supports = max(set(vs), key=vs.count)
        return scenes
    _direction_once(scenes, nucleus_binary, cfg)
    return scenes


BINARY_SYSTEM = """你是「绒球」的方向判定器。

给定原核和若干场景，判断每个场景让原核更可能成立（support）
还是更不可能成立（oppose）。

**不允许 neutral。** 每一条都必须在两边里选一个：
如果它确实不直接说明方向，就判断它整体上更偏向哪一边——
像这样"没有明确方向"的情形，在做成决定时也必须落到一边。
这是绒球的原则：不做弃权。

只输出 JSON：{"items": [{"idx": 1, "supports": "support"}, ...]}"""


def force_binary(scenes: list[SceneFact], nucleus_binary: str, cfg=None) -> list[SceneFact]:
    """把中性的事实逼成二元。

    为什么必须这么做：被认领的场景是用户亲手确认「这是我的情况」的，
    它不可能对原核「没有方向」。判成中性等于说「你确认了一件与决定无关的事」，
    那是自相矛盾的。

    这也是「无弃权」在事实层的含义——不只是最终输出不弃权，
    每一条进入判断的事实也不允许弃权。
    """
    from .triples import SUPPORT, OPPOSE
    from .llm import available, complete

    cfg = cfg or load_config()
    if not available(cfg):
        return scenes

    # 最多逼两轮。模型第一次常常还是给中性，第二轮用更强硬的措辞。
    for attempt in range(2):
        pending = [s for s in scenes if s.supports not in (SUPPORT, OPPOSE)]
        if not pending:
            break
        scenes = _force_once(pending, scenes, nucleus_binary, cfg, strict=(attempt > 0))
    return scenes


def _force_once(pending, scenes, nucleus_binary, cfg, strict=False):
    from .triples import SUPPORT, OPPOSE
    from .llm import complete

    lines = "\n".join(f"{i}. {s.scene[:160]}" for i, s in enumerate(pending))
    tail = ("判断每个场景更偏向哪一边。不允许 neutral，只输出 JSON。")
    if strict:
        tail = ("**必须二选一，不许 neutral。** 如果不直接说明方向，就问自己："
                "假如这件事是真的，「原核成立」会变得更可能还是更不可能？"
                "必须落到一边。只输出 JSON。")
    prompt = (f"【原核】{nucleus_binary}，这件事会成立吗？\n\n"
              f"【场景】\n{lines}\n\n{tail}")
    raw = complete(prompt, system=BINARY_SYSTEM, cfg=cfg)
    if not raw:
        return scenes
    try:
        import json
        t = raw.strip()
        if t.startswith("```"):
            import re
            t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
            t = re.sub(r"```\s*$", "", t)
        items = json.loads(t.strip()).get("items", [])
    except Exception:
        return scenes
    for it in items:
        try:
            idx = int(it.get("idx", 0)) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(pending)):
            continue
        v = str(it.get("supports", "")).strip().lower()
        if v in (SUPPORT, OPPOSE):
            pending[idx].supports = v
    return scenes


def _direction_once(scenes: list[SceneFact], nucleus_binary: str, cfg) -> list[SceneFact]:
    lines = "\n".join(f"{i}. {s.scene}" for i, s in enumerate(scenes))
    prompt = (f"【原核】{nucleus_binary}\n\n"
              f"【场景】\n{lines}\n\n"
              "逐条判断：如果这条是真的，原核「真的发生」的可能性升高还是降低？"
              "先写一句理由，再给 support 或 oppose。只输出 JSON。")
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
