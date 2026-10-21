"""输入层覆盖审计：用现有 journal 的真实问题，检查框架/面命中情况。

只读 data/journal.jsonl，不修改数据。
用法（仓库根目录）：
    python scripts/audit_input_layer.py
    python scripts/audit_input_layer.py --limit 200
输出：
    data/input_layer_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rongqiu import input_layer, journal


def load_texts(limit: int) -> list[str]:
    seen = set()
    out = []
    for e in journal.load():
        text = (e.get("nucleus") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--out", default="data/input_layer_audit.json")
    args = p.parse_args()

    texts = load_texts(args.limit)
    frames = Counter()
    surfaces = Counter()
    gaps = Counter()
    no_surface = []
    rows = []
    for text in texts:
        c = input_layer.compile(text)
        frames[c["frame"]] += 1
        for s in c["surfaces"]:
            surfaces[s["surface_id"]] += 1
        for g in c["gaps"]:
            gaps[g] += 1
        if not c["surfaces"]:
            no_surface.append({"text": text, "frame": c["frame"]})
        rows.append({
            "text": text,
            "frame": c["frame"],
            "binary": c["binary"],
            "surfaces": [s["surface_id"] for s in c["surfaces"]],
            "gaps": c["gaps"],
            "question_ids": c["question_ids"],
        })

    out = {
        "texts": len(texts),
        "frames": dict(frames),
        "surface_hit_texts": len(texts) - len(no_surface),
        "no_surface_texts": len(no_surface),
        "surfaces": dict(surfaces.most_common()),
        "gaps": dict(gaps.most_common()),
        "no_surface_samples": no_surface[:50],
        "rows": rows,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in
                      ("texts", "surface_hit_texts", "no_surface_texts",
                       "frames", "surfaces")}, ensure_ascii=False))
    print("written", path)


if __name__ == "__main__":
    main()
