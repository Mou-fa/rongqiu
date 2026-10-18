"""共识抽取后的复现性检验。

对比两种抽法：
    单次抽取          —— 一致性 90%、三元组稳定度 40%
    3 次共识抽取      —— 只保留出现 >=2/3 的事实

看共识能不能把结论钉住。
"""

from __future__ import annotations

import statistics
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


def norm(t):
    return f"{t.agent.strip()}|{t.event.strip()}|{t.resource.strip()}"


def judge_once(consensus_runs: int):
    if consensus_runs > 1:
        ex = extract.consensus(QUESTION, TEXTS, runs=consensus_runs, min_freq=0.6)
    else:
        ex = extract.extract(QUESTION, TEXTS)
    tb_lean, tb_reason = extract.tie_break_of(QUESTION, TEXTS)
    nd = node.build(QUESTION, ex, trace)
    j = nd.judge(tie_break_lean=tb_lean, tie_break_reason=tb_reason)
    return ex, j


def report(label, results):
    leans = [r[1].lean for r in results if r[1] is not None]
    ns = [r[1].n for r in results if r[1] is not None]
    if not leans:
        print(f"{label}: 全部失败")
        return
    c = Counter(leans)
    top, top_n = c.most_common(1)[0]
    print(f"{label}")
    print(f"  结论分布 {dict(c)}   一致率 {top_n/len(leans):.0%}")
    print(f"  N 分布 {dict(Counter(ns))}   均值 {statistics.mean(ns):.2f} "
          f"标准差 {statistics.pstdev(ns):.2f}")
    sets = [{norm(t) for t in r[0].facts} for r in results if r[1] is not None]
    if sets:
        all_t = set().union(*sets)
        always = set.intersection(*sets)
        print(f"  事实种类 {len(all_t)}   每次都出现 {len(always)}")
    print()


def main() -> int:
    print("=" * 58)
    print("复现性检验：单次抽取 vs 3 次共识抽取")
    print("=" * 58)
    print()

    single = []
    for i in range(6):
        ex, j = judge_once(1)
        single.append((ex, j))
        print(f"  单次 {i+1}: lean={j.lean if j else '-'} N={j.n if j else 0}")
    print()

    cons = []
    for i in range(6):
        ex, j = judge_once(3)
        cons.append((ex, j))
        print(f"  共识 {i+1}: lean={j.lean if j else '-'} N={j.n if j else 0}")
    print()

    report("单次抽取", single)
    report("3 次共识抽取", cons)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
