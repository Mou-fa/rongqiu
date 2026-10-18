"""人工勾选：把全网匹配回来的场景，逐条交给用户定倾向。

为什么倾向必须由人来勾，而不交给模型：

1. 场景大多是习惯性表述（「我参加聚会后经常觉得累」），它不是已发生事件，
   硬抽三元组要么丢掉、要么变形。
2. 「这条证据对我意味着什么」依赖用户的处境，模型不知道。
3. 模型判倾向不稳——同一个场景两次判定可能相反，而这是要进 N11 计数的。

机器负责「找到你没找到的证据」，人负责「这条证据对你意味着什么」。
"""

from __future__ import annotations

from .triples import SceneFact, SUPPORT, OPPOSE, NEUTRAL

KEYS = {"s": SUPPORT, "o": OPPOSE, "n": NEUTRAL, "": NEUTRAL}


def interactive(candidates, nucleus, answers: list[str] | None = None) -> list[SceneFact]:
    """逐条问倾向。answers 不为 None 时按顺序取，不读 input（供测试/演示）。"""
    facts: list[SceneFact] = []
    n = len(candidates)
    print(f"\n找到 {n} 条符合原核的场景，请逐条勾选倾向：")
    print("  [s] 让我更倾向去做   [o] 让我更倾向不做   [n] 无关\n")

    for i, c in enumerate(candidates):
        print(f"[{i+1}/{n}] {c.text}")
        if nucleus:
            print(f"       （命中原核成分：{'+'.join(c.matched)}）")
        if answers is not None:
            key = answers[i] if i < len(answers) else ""
            print(f"       > {key or '(跳过)'}")
        else:
            try:
                key = input("       > ").strip().lower()
            except EOFError:
                key = ""
        tendency = KEYS.get(key, NEUTRAL)
        facts.append(SceneFact(scene=c.text, supports=tendency,
                               source=c.source, order=i))
        print()

    return facts


def summarize(facts: list[SceneFact]) -> str:
    sup = sum(1 for f in facts if f.supports == SUPPORT)
    opp = sum(1 for f in facts if f.supports == OPPOSE)
    neu = sum(1 for f in facts if f.supports == NEUTRAL)
    return f"勾选结果：支持 {sup} · 反对 {opp} · 无关 {neu}"
