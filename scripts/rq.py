"""绒球命令行。

    python scripts/rq.py judge --question "今晚的聚会，我应该去吗？" \
        --text "chat|老张：周五晚上聚一下？" \
        --text "calendar|10月18日 19:00 项目复盘会（不可缺席）"

    python scripts/rq.py pending
    python scripts/rq.py resolve --id 20261019-000000-abcd --outcome no --note "没去，后悔"
    python scripts/rq.py stats
    python scripts/rq.py simulate --n 400        # 用合成数据验证校准机器本身
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import extract, journal, node, trace  # noqa: E402


def _parse_texts(items: list[str]) -> list[tuple[str, str]]:
    out = []
    for item in items:
        if "|" not in item:
            raise SystemExit(f"--text 格式应为 '来源|内容'，收到：{item}")
        src, text = item.split("|", 1)
        out.append((src.strip(), text.strip()))
    return out


def cmd_judge(args) -> int:
    texts = _parse_texts(args.text)
    ex = extract.extract(args.question, texts)
    tb_lean, tb_reason = extract.tie_break_of(args.question, texts)
    nd = node.build(args.question, ex, trace)
    j = nd.judge(tie_break_lean=tb_lean, tie_break_reason=tb_reason)
    if j is None:
        print("节点不成立：没有任何可判定的方向信息")
        return 1
    print(j.render())
    entry = journal.record(j, args.question, resolve_days=args.resolve_days)
    print(f"\n已入档：{entry['id']}  回收截止 {entry['resolve_by']}")
    return 0


def cmd_pending(args) -> int:
    rows = journal.pending()
    if not rows:
        print("没有到期未回收的判断。")
        return 0
    print(f"{'id':22s} {'N':>3s} {'倾向':>4s} {'置信':>5s}  {'截止':10s}  原核")
    for e in rows:
        print(f"{e['id']:22s} {e['n']:>3d} {e['lean']:>4s} {e['confidence']:>5.2f}  "
              f"{e['resolve_by'][:10]}  {e['nucleus'][:30]}")
    return 0


def cmd_resolve(args) -> int:
    e = journal.resolve(args.id, args.outcome, args.note)
    if e is None:
        print(f"找不到判断 {args.id}")
        return 1
    print(f"已回收 {e['id']}：{e['lean']} → 实际 {e['outcome']}  "
          f"（{'命中' if e['lean'] == e['outcome'] else '未命中'}）")
    return 0


def cmd_stats(args) -> int:
    print(journal.render_stats(journal.stats()))
    return 0


def cmd_simulate(args) -> int:
    """合成数据验证校准机器：按 p_yes 生成结果，看能否复原。"""
    rng = random.Random(args.seed)
    entries = []
    for i in range(args.n):
        n = rng.choice([2, 3, 4, 6, 8])
        det = n / (n + 2)
        ratio = rng.uniform(0.5, 1.0)
        conf = min(det * (0.5 + abs(ratio - 0.5)), 0.8)
        lean = rng.choice(["yes", "no"])
        p = conf if lean == "yes" else 1 - conf
        outcome = "yes" if rng.random() < p else "no"
        entries.append({"n": n, "confidence": conf, "lean": lean,
                        "rule": "direct" if det > 0.5 else "provisional",
                        "outcome": outcome})
    print(journal.render_stats(journal.stats(entries)))
    print()
    print("（合成数据按置信度生成结果。若机器正确，可靠性曲线应贴近对角线。）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("judge", help="做一次判断并入库")
    p.add_argument("--question", required=True)
    p.add_argument("--text", action="append", required=True, help="来源|内容")
    p.add_argument("--resolve-days", type=int, default=7)
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("pending", help="到期未回收的判断")
    p.set_defaults(func=cmd_pending)

    p = sub.add_parser("resolve", help="回收结果")
    p.add_argument("--id", required=True)
    p.add_argument("--outcome", required=True, choices=["yes", "no"])
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("stats", help="校准报告")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("simulate", help="用合成数据验证校准机器")
    p.add_argument("--n", type=int, default=400)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=cmd_simulate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
