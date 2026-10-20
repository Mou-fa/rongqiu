"""用固定的 15 类面类别，给实测语料打多标签。

    python scripts/classify_corpus.py
    python scripts/classify_corpus.py --corpus data/miner/corpus.json

词表来自 configs/taxonomy.yaml（和问句库共用同一份）。
每条考虑归 1–3 类，用来验证「15 类 + 多选」在 548 条实测语料上的覆盖情况。

产物：
    data/miner/corpus_labels.md
    data/miner/corpus_labels.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rongqiu import llm, questions as qbank  # noqa: E402

OUT_DIR = ROOT / "data" / "miner"

MULTI_SYSTEM = """你是「绒球」的归类员。给你一份面类别词表和一批「做决定时的考虑」，
把每条考虑归到 1–3 个最合适的类。

词表：
{domains}

规则：
- 每条至少 1 类，最多 3 类；
- 一条考虑可以同时属于多个类（例如「养孩子成本」= 经济负担 + 家庭责任）；
- 只能从词表里选，不要自创类名；
- 实在分不清的选「其他」。
只输出 JSON：{"items":[{"idx":1,"classes":[]}]}"""

MULTI_PROMPT = """共 {n} 条：

{lines}

只输出 JSON。"""


def _json_of(raw: str) -> dict:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    try:
        data = json.loads(t.strip())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_unique(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    seen, out = set(), []
    for it in data.get("items", []):
        text = str(it.get("text", "")).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(it)
    return out


def classify(items, names, chunk, workers, cfg):
    name_set = set(names)

    def _one(batch):
        lines = "\n".join(f"{i+1}. {t['text']}" for i, t in enumerate(batch))
        raw = llm.complete(MULTI_PROMPT.format(n=len(batch), lines=lines),
                           system=MULTI_SYSTEM.replace("{domains}", "、".join(names)),
                           cfg=cfg)
        return batch, _json_of(raw).get("items", []) or []

    labels = [["其他"] for _ in items]
    index_of = {id(it): i for i, it in enumerate(items)}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, b)
                   for b in (items[i:i + chunk] for i in range(0, len(items), chunk))]
        for fut in as_completed(futures):
            try:
                batch, raw_items = fut.result()
            except Exception as exc:
                print(f"  [warn] batch failed ({type(exc).__name__})")
                continue
            for it in raw_items:
                try:
                    i = int(it.get("idx", 0)) - 1
                except (TypeError, ValueError):
                    continue
                if not (0 <= i < len(batch)):
                    continue
                cls = [str(x).strip() for x in (it.get("classes") or [])
                       if str(x).strip() in name_set][:3]
                if cls:
                    labels[index_of[id(batch[i])]] = cls
    return labels


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=str(OUT_DIR / "corpus.json"))
    ap.add_argument("--chunk", type=int, default=60)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    cfg = llm.load_config()
    cfg.max_tokens = max(cfg.max_tokens, 3000)
    if not llm.available(cfg):
        print("llm key 没配置")
        return 1
    names = qbank.domain_names()
    if not names:
        print("taxonomy 词表是空的：configs/taxonomy.yaml")
        return 1
    items = load_unique(Path(args.corpus))
    if len(items) < 50:
        print(f"语料太少：{len(items)} 条")
        return 1
    print(f"unique considerations: {len(items)}, classes: {len(names)}")

    t0 = time.time()
    labels = classify(items, names, args.chunk, args.workers, cfg)
    print(f"classified ({time.time()-t0:.0f}s)")

    per = {n: {"count": 0, "frames": set(), "examples": []} for n in names}
    multi = other = 0
    for it, cls in zip(items, labels):
        cls = list(dict.fromkeys(cls))
        if len(cls) > 1:
            multi += 1
        if cls == ["其他"]:
            other += 1
        for c in cls:
            s = per.setdefault(c, {"count": 0, "frames": set(), "examples": []})
            s["count"] += 1
            s["frames"].add(it.get("frame", ""))
            if len(s["examples"]) < 5:
                s["examples"].append(it["text"])

    ordered = sorted(per.items(), key=lambda kv: -kv[1]["count"])
    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "total": len(items), "multi_label": multi, "other_only": other,
        "classes": [{"name": n, "count": s["count"],
                     "frames": sorted(x for x in s["frames"] if x),
                     "examples": s["examples"]} for n, s in ordered],
        # 逐条标签：给问句起草用（哪条考虑属于哪一类面）
        "items": [{"text": it["text"], "frame": it.get("frame", ""),
                   "mk": it.get("mk", ""),
                   "classes": list(dict.fromkeys(cls))}
                  for it, cls in zip(items, labels)],
    }
    (OUT_DIR / "corpus_labels.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"# {len(names)} 类多选打标 · {len(items)} 条实测考虑", "",
             f"- 多标签（≥2 类）：{multi} 条（{100.0*multi/len(items):.1f}%）",
             f"- 只落在「其他」：{other} 条",
             ""]
    for n, s in ordered:
        lines.append(f"- **{n}**：{s['count']} 条")
    lines.append("")
    (OUT_DIR / "corpus_labels.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"multi={multi} other={other}")
    print("labels -> data/miner/corpus_labels.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
