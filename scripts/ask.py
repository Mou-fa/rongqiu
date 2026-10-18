"""绒球·问一条：用户问题 → 原核 → 全网匹配 → 人工勾选 → N11 判断

    python scripts/ask.py --question "我能不能去参加今晚的聚会"
    python scripts/ask.py --question "..." --answers "s,o,s,n,o,s"   # 脚本化演示
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import extract, journal, match, node, nucleus, review  # noqa: E402

CORPUS = [
    ("web", "我参加聚会前通常会先睡一觉，否则全程提不起精神。"),
    ("web", "我参加聚会一般待两小时就走，主人家也不会介意。"),
    ("web", "我参加聚会后经常觉得累，第二天状态很差。"),
    ("web", "我参加聚会时总是找不到话说，场面很尴尬。"),
    ("web", "我参加聚会最看重的是现场有没有熟人。"),
    ("web", "我参加聚会很少喝酒，一般十点前就回家。"),
    ("chat", "老张：周五晚上聚一下？就我们几个老人，好久没见了。"),
    ("calendar", "10月18日 19:00-21:00 项目复盘会（全员，不可缺席）"),
    ("news", "苹果发布新款手机，售价 7999 元起。"),
    ("note", "最近两周平均每天睡 5.5 小时。"),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--question", default="我能不能去参加今晚的聚会")
    ap.add_argument("--answers", default=None,
                    help="脚本化勾选，逗号分隔：s=支持 o=反对 n=无关")
    ap.add_argument("--assumption", default="")
    ap.add_argument("--unknown", default="")
    ap.add_argument("--min-hits", type=int, default=2)
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args(argv)

    print("=" * 68)
    print("绒球 · 问一条")
    print("=" * 68)
    print(f"用户输入：{args.question}\n")

    print("① 识别：提取主谓宾")
    nu = nucleus.parse(args.question)
    print(f"   原核三元组：{nu.agent} · {nu.event} · {nu.resource}")
    print(f"   二元问题：{nu.binary}，会成立吗？\n")

    print("② 全网匹配：找同一主谓宾构成的场景")
    cands = match.rank(nu, CORPUS, min_hits=args.min_hits)
    print(match.render(cands))
    print(f"\n   {len(CORPUS)} 条文本中 {len(cands)} 条命中原核成分\n")
    if not cands:
        return 1

    print("③ 人工勾选倾向")
    answers = args.answers.split(",") if args.answers else None
    facts = review.interactive(cands, nu, answers=answers)
    print(review.summarize(facts))

    print("\n④ N11 判定")
    assumption = args.assumption or "勾选的场景与我这次的情况相似"
    unknown = args.unknown or "当晚是否另有无法推脱的安排"
    nd = node.build_from_review(nu.binary, facts, assumption=assumption,
                                unknown=unknown)
    j = nd.judge()
    print("-" * 68)
    if j is None:
        print("节点不成立：勾选里没有方向性的证据。")
        return 1
    print(j.render())
    print("-" * 68)

    if not args.no_record:
        entry = journal.record(j, args.question, resolve_days=7)
        print(f"\n已入档：{entry['id']}   7 天后回收结果")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
