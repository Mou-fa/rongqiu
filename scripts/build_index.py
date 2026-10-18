"""给本地语料建三元组索引。

    python scripts/build_index.py

每条文本只提取一次，结果缓存在 data/triple_index.json。
本地语料改了之后重跑本脚本。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import indexer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    path = ROOT / "data" / "local_corpus.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    texts = [(it.get("source", "local"), it["text"]) for it in items]
    print(f"为 {len(texts)} 条文本建索引...")
    before = len(indexer.load_index())
    idx = indexer.build(texts)
    print(f"完成：索引总数 {len(idx)}（本次新增 {len(idx) - before}）")
    print()
    for src, text in texts[:8]:
        tris = indexer.triples_of(text, idx)
        desc = " | ".join(f"{t['agent']}·{t['event']}·{t['resource']}" for t in tris)
        print(f"  {text[:26]:28s} → {desc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
