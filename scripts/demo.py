"""绒球主干 · 端到端演示

一个真实形态的个人生活微决策：今晚的聚会去不去。

跑通这条链：
    文本 → 语义三元组 → 溯源分槽 → N11 节点 → 二元判定
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import extract, node, trace  # noqa: E402

# 一次微决策的原料。每段都带来源标签——标签决定它的溯源等级。
QUESTION = "今晚的聚会，我应该去吗？"

TEXTS = [
    ("chat", "老张：周五晚上聚一下？就我们几个老人，好久没见了。"),
    ("calendar", "10月18日 19:00-21:00 项目复盘会（全员，不可缺席）"),
    ("chat", "小李：你要是不方便，我们就改下周，反正人也不齐。"),
    ("note", "最近两周平均每天睡 5.5 小时，周三已经推掉一次约了。"),
    ("chat", "老张：这次聚完，老王就调去上海了，可能几年见不着。"),
]


def main() -> int:
    print("=" * 62)
    print("绒球主干 · 端到端")
    print("=" * 62)
    print(f"原核：{QUESTION}\n")
    print("原料：")
    for src, text in TEXTS:
        print(f"  [{src:8s}] {text}")
    print()

    print("① 抽取语义三元组 ...")
    ex = extract.extract(QUESTION, TEXTS)
    print(f"   模型 {ex.model}，抽出 {len(ex.facts)} 条\n")

    print("② 溯源分槽 ...")
    trace.apply(ex.facts)
    for t in ex.facts:
        slot = trace.classify(t)
        print(f"   [{t.grade}] {slot:10s} {t.as_text()}")
    print()

    print("③ 组织 N11 节点 ...")
    nd = node.build(QUESTION, ex, trace)
    agents, sources = trace.independence_pool(ex.facts)
    print(f"   独立观察者 {agents} 个 / 独立来源 {sources} 个 "
          f"→ 独立性{'成立' if max(agents, sources) >= 2 else '不成立（退回只看确定性）'}")
    tb_lean, tb_reason = extract.tie_break_of(QUESTION, TEXTS)
    j = nd.judge(tie_break_lean=tb_lean, tie_break_reason=tb_reason)
    if j is None:
        print("   节点不成立：没有任何可判定的方向信息")
        return 1
    print()
    print("④ 判定（严格溯源：只让 L3+ 进确定槽）")
    print("-" * 62)
    print(j.render())
    print("-" * 62)

    # 对照：宽松溯源，L1/L2 也参与投票
    nd2 = node.build(QUESTION, ex, trace, include_assumptions=True)
    j2 = nd2.judge()
    print()
    print("⑤ 对照（宽松溯源：L1/L2 也参与投票）")
    print("-" * 62)
    if j2:
        print(j2.render())
    print("-" * 62)
    print()
    print("对比：")
    if j and j2:
        print(f"  严格：N={j.n}  倾向={j.lean}  置信={j.confidence:.2f}  规则={j.rule}")
        print(f"  宽松：N={j2.n}  倾向={j2.lean}  置信={j2.confidence:.2f}  规则={j2.rule}")
        if j.lean != j2.lean:
            print("  ⚠ 两种口径结论相反——说明溯源门槛直接决定判断方向")
        else:
            print("  两种口径结论一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
