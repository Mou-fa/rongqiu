"""检查搜索配置，并跑一次真实检索。

    python scripts/check_search.py
    python scripts/check_search.py --query "参加聚会 累"

先显示配置（key 打码），然后真的搜一次，把返回的文本打印出来。
key 填进 configs/search.yaml 就行，不用发给任何人。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import search  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query", default="参加聚会后觉得很累")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)

    cfg = search.load_config()
    key = cfg.api_key
    masked = (key[:6] + "..." + key[-4:]) if len(key) > 12 else ("(空)" if not key else "(过短)")
    print(f"provider    : {cfg.provider}")
    print(f"api_key     : {masked}")
    print(f"配置来源    : {'configs/search.yaml' if search.CONFIG_PATH.exists() else '默认值'}")
    print(f"max_results : {cfg.max_results}")
    print()

    if cfg.provider in ("tavily", "bocha", "serper") and not cfg.api_key:
        print("这个 provider 需要 key，但 configs/search.yaml 里还是空的。")
        print("填好之后重跑本脚本。")
        return 1

    print(f"检索：{args.query}")
    t0 = time.time()
    try:
        results = search.search(args.query, cfg, use_cache=not args.no_cache)
    except Exception as exc:
        print(f"失败：{type(exc).__name__}: {exc}")
        return 1
    dt = time.time() - t0
    print(f"返回 {len(results)} 条（{dt:.1f}s）")
    print()
    if not results:
        print("0 条结果。可能是 key 无效、额度用完，或被限流。")
        return 1
    for i, (src, text) in enumerate(results[:6]):
        print(f"[{i+1}] {src}")
        print(f"    {text[:200]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
