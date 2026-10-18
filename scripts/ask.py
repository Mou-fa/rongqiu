"""绒球·问一条

    用户问题 → 原核（主谓宾）→ 全网匹配 → 用户点选「这是我的情况」
    → 系统判倾向 → N11 → 二元判断

    python scripts/ask.py --question "我能不能去参加今晚的聚会"
    python scripts/ask.py --question "..." --picked "1,2,3,4"   # 脚本化演示
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import indexer, journal, node, nucleus, review, search  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--question", default="我能不能去参加今晚的聚会")
    ap.add_argument("--picked", default=None,
                    help="脚本化点选，逗号分隔序号，如 1,2,3,4")
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

    cfg = search.load_config()
    query = f"{nu.agent} {nu.event} {nu.resource}"
    print(f"② 全网检索：{query}")
    print(f"   provider = {cfg.provider}"
          + ("（本地语料，未配置搜索 key）" if cfg.provider == "local" or not cfg.api_key else ""))
    results = search.search(query, cfg)
    print(f"   检索返回 {len(results)} 条")

    cands = indexer.rank(nu, results, min_hits=args.min_hits)
    print(f"   其中 {len(cands)} 条命中原核成分")
    if not cands:
        print("   没有找到符合原核的场景。")
        return 1

    print("\n③ 点选：哪几条是你的真实情况")
    picked = [int(x) - 1 for x in args.picked.split(",")] if args.picked else None
    chosen, rejected = review.select(cands, selected=picked)
    if not chosen:
        print("\n一条都没选——没有确定接触面，节点不成立。")
        return 1

    print(f"\n④ 系统判定倾向（一次判完全部，保证前后一致）")
    facts = review.to_scene_facts(chosen)
    review.direction_of(facts, nu.binary)
    for f in facts:
        mark = {"support": "+", "oppose": "-"}.get(f.supports, "0")
        print(f"   {mark} {f.scene}")
    print(f"\n   {review.summarize(facts)}")

    print("\n⑤ N11 判定")
    assumption = args.assumption or "我点选的这几条如实反映了我的情况"
    unknown = args.unknown or "当晚是否另有无法推脱的安排"
    nd = node.build_from_review(nu.binary, facts, assumption=assumption,
                                unknown=unknown)
    j = nd.judge()
    print("-" * 68)
    if j is None:
        print("节点不成立：选中的场景里没有方向性证据。")
        return 1
    print(j.render())
    print("-" * 68)

    if not args.no_record:
        entry = journal.record(j, args.question, resolve_days=7)
        print(f"\n已入档：{entry['id']}   7 天后回收结果")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
