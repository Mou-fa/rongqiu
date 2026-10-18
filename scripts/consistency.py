"""同输入一致性验证。

如果同一个问题交进去两次，出来两个不同的判断，那校准就没有基础：
你没法记录一个每次都变的东西。「长期命中率 ≈ 置信度」要求判断本身是先
可复现、后才可能有校准。

测三件事：
    1. 结论一致率 —— 多少次给出同一个 lean
    2. N 稳定度   —— 事实数量的波动
    3. 三元组稳定度 —— 哪些事实是每次都在的
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import extract, node, trace  # noqa: E402

QUESTION = "今晚的聚会，我应该去吗？"
TEXTS = [
    ("chat", "老张：周五晚上聚一下？就我们几个老人，好久没见了。"),
    ("calendar", "10月18日 19:00-21:00 项目复盘会（全员，不可缺席）"),
    ("chat", "小李：你要是不方便，我们就改下周，反正人也不齐。"),
    ("note", "最近两周平均每天睡 5.5 小时，周三已经推掉一次约了。"),
    ("chat", "老张：这次聚完，老王就调去上海了，可能几年见不着。"),
]


def norm(t) -> str:
    return f"{t.agent}|{t.event}|{t.resource}"


def main() -> int:
    runs = 10
    leans, ns, triple_sets = [], [], []
    print(f"问题：{QUESTION}")
    print(f"相同输入跑 {runs} 次\n")

    for i in range(runs):
        ex = extract.extract(QUESTION, TEXTS)
        tb_lean, tb_reason = extract.tie_break_of(QUESTION, TEXTS)
        nd = node.build(QUESTION, ex, trace)
        j = nd.judge(tie_break_lean=tb_lean, tie_break_reason=tb_reason)
        if j is None:
            print(f"  第 {i+1:2d} 次：节点不成立")
            continue
        leans.append(j.lean)
        ns.append(j.n)
        triple_sets.append({norm(t) for t in j.facts})
        print(f"  第 {i+1:2d} 次：lean={j.lean:3s}  N={j.n}  置信={j.confidence:.2f}  "
              f"支持率={j.support_ratio:.0%}  规则={j.rule}")

    if not leans:
        print("\n全部失败")
        return 1

    print()
    print("=" * 56)
    print("一致性报告")
    print("=" * 56)

    # 1. 结论一致率
    c = Counter(leans)
    top, top_n = c.most_common(1)[0]
    print(f"结论分布：{dict(c)}")
    print(f"结论一致率：{top_n/len(leans):.0%}  （{top}）")
    print(f"  判据：>=90% 才算可复现")

    # 2. N 稳定度
    import statistics
    print(f"N 分布：{dict(Counter(ns))}")
    print(f"N 均值 {statistics.mean(ns):.2f}  标准差 {statistics.pstdev(ns):.2f}")
    print(f"  判据：标准差 <=1 才算稳定")

    # 3. 三元组稳定度
    all_t = set().union(*triple_sets)
    always = set.intersection(*triple_sets)
    print(f"出现过的事实种类：{len(all_t)}")
    print(f"每次都出现的事实：{len(always)}  （{len(always)/max(len(all_t),1):.0%}）")
    print()
    print("每次都在的：")
    for t in sorted(always):
        print(f"  [稳定] {t}")
    unstable = all_t - always
    if unstable:
        print()
        print("时有时无的：")
        for t in sorted(unstable):
            cnt = sum(1 for s in triple_sets if t in s)
            print(f"  [{cnt}/{len(triple_sets)}] {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
