"""给索引补浓缩句。

索引里已有的条目如果是旧格式（只有三元组、没有浓缩句），重新提取一次。
新条目在索引时会自动带上浓缩句，不需要这个脚本。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import indexer  # noqa: E402
from rongqiu.llm import load_config  # noqa: E402

# 需要知道原文才能重新提取。索引只存了 hash，所以原文从搜索缓存里取。
import json


def main() -> int:
    cfg = load_config()
    idx = indexer.load_index()
    print(f"索引条目 {len(idx)}")

    todo = [k for k, v in idx.items() if isinstance(v, list)
            or not (isinstance(v, dict) and v.get("sentence"))]
    print(f"需要补浓缩句：{len(todo)}")

    # 从搜索缓存里恢复原文（缓存文件是 [[source, text], ...]）
    cache_dir = indexer.ROOT / "data" / "search_cache"
    by_key: dict[str, str] = {}
    if cache_dir.exists():
        for f in cache_dir.glob("*.json"):
            try:
                rows = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for row in rows:
                if isinstance(row, list) and len(row) == 2:
                    by_key[indexer._key(row[1])] = row[1]
    print(f"从搜索缓存恢复原文：{len(by_key)} 条")

    done, skipped = 0, 0
    for i, k in enumerate(todo, 1):
        text = by_key.get(k)
        if not text:
            skipped += 1
            continue
        e = indexer.extract(text, cfg)
        idx[k] = e
        done += 1
        if i % 10 == 0:
            indexer.save_index(idx)
            print(f"  {i}/{len(todo)}  done={done} skipped={skipped}", flush=True)
        time.sleep(0.05)

    indexer.save_index(idx)
    print(f"完成：补了 {done} 条，跳过 {skipped} 条（找不到原文）")
    with_sentence = sum(1 for v in idx.values()
                        if isinstance(v, dict) and v.get("sentence"))
    print(f"现在有浓缩句的条目：{with_sentence}/{len(idx)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
