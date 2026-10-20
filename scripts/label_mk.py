"""给已矿出的「考虑」重新标 mk（直接因 / 直接果 / 共同原因）。

背景：4098 条实测里 cause 57.7% / effect 29.7% / common 12.6%，
共同原因被严重低估。这个脚本用一套更可判的规则重标一遍，
用来验证偏差有多大、以及修正后的判据是否有效。

判据（按顺序）：
1. 这条说的是「做了之后会发生什么」吗？→ effect
2. 换成同类事情、换一天、换一个对象，这条还成立吗？
   - 还成立（性格、关系模式、习惯、身份、长期期待、长期处境）→ common
   - 只对这一次成立（这次谁邀请、这次的时间/地点/人员、这次的临时状态）→ cause

    python scripts/label_mk.py
    python scripts/label_mk.py --sample 300 --workers 4

产物：data/miner/corpus_mk.md / .json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rongqiu import llm  # noqa: E402

OUT_DIR = ROOT / "data" / "miner"
MKCN = {"cause": "直接因", "effect": "直接果", "common": "共同原因"}

SYSTEM = """你是「绒球」的面分类器。给你一个决定（框架）和若干条「考虑」，给每条标 mk。

按顺序判断：
1. 这条说的是「做了之后会发生什么」吗？→ effect
2. 这条是「我这个人」的稳定背景吗？
   （我的性格、我和某人的关系模式、我的习惯、我的身份、我的长期期待、我长期处的处境）
   → common
3. 其余一律 → cause（这次的具体触发或约束：这次谁邀请、这次的时间/地点/人员、
   这次的临时状态、这次要花的钱、这次要满足的条件）

容易错的地方：
- 「社恐 / 内向 / 怕生」→ common
- 「和某人关系一般 / 一直不喜欢这个圈子」→ common
- 「我一直工资低 / 长期手头紧」→ common；「这个月要还房贷」→ cause
- 「这次是老同事的局 / 这次身体不舒服 / 这周太忙」→ cause
- **通用事实、政策、行情、行业规律不是「共同原因」**：
  「房贷利率下限」「手机价格高」「缺牙越久骨越萎缩」这类，除非确实是这次的具体约束，
  否则留在 cause，别塞进 common。
- 共同原因最容易被漏掉，但不要为了补它把所有「稳定的话」都算进来。

只输出 JSON：{"items":[{"idx":1,"mk":"cause|effect|common","why":"不超过12字"}]}"""

PROMPT = """决定：{frame}

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


def label(items: list[dict], chunk: int, workers: int, cfg) -> list[dict]:
    # 按框架分组，批量时同框架一起送，模型判断更稳
    buckets: dict[str, list[dict]] = {}
    for it in items:
        buckets.setdefault(it.get("frame", ""), []).append(it)
    jobs = []
    for frame, group in buckets.items():
        for i in range(0, len(group), chunk):
            jobs.append((frame, group[i:i + chunk]))

    def _one(job):
        frame, batch = job
        lines = "\n".join(f"{i+1}. {t['text']}" for i, t in enumerate(batch))
        raw = llm.complete(PROMPT.format(frame=frame, lines=lines),
                           system=SYSTEM, cfg=cfg)
        return batch, _json_of(raw).get("items", []) or []

    out: list[dict] = [dict(it) for it in items]
    index_of = {id(it): i for i, it in enumerate(items)}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, job) for job in jobs]
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
                mk = str(it.get("mk", "")).strip().lower()
                if mk not in MKCN:
                    continue
                rec = out[index_of[id(batch[i])]]
                rec["mk_new"] = mk
                rec["mk_why"] = str(it.get("why", "")).strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=str(OUT_DIR / "corpus.json"))
    ap.add_argument("--sample", type=int, default=0, help="只试跑 N 条；0 = 全部")
    ap.add_argument("--chunk", type=int, default=25)
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args(argv)

    cfg = llm.load_config()
    cfg.max_tokens = max(cfg.max_tokens, 4000)
    if not llm.available(cfg):
        print("llm key 没配置")
        return 1
    items = load_unique(Path(args.corpus))
    if args.sample:
        random.seed(7)
        items = random.sample(items, min(args.sample, len(items)))
    print(f"items: {len(items)}")

    t0 = time.time()
    labeled = label(items, args.chunk, args.workers, cfg)
    got = [x for x in labeled if "mk_new" in x]
    print(f"labeled {len(got)}/{len(labeled)} in {time.time()-t0:.0f}s")

    from collections import Counter
    old = Counter(x.get("mk", "") for x in got)
    new = Counter(x["mk_new"] for x in got)
    confusion = Counter((x.get("mk", ""), x["mk_new"]) for x in got)
    moved = [x for x in got if x["mk_new"] == "common" and x.get("mk") != "common"]

    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "total": len(got),
        "old": dict(old), "new": dict(new),
        "confusion": {f"{a}->{b}": n for (a, b), n in confusion.most_common()},
        "sample_moved_to_common": [
            {"text": x["text"], "frame": x.get("frame", ""),
             "old": x.get("mk", ""), "why": x.get("mk_why", "")} for x in moved[:30]],
    }
    (OUT_DIR / "corpus_mk.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    def pct(c, n):
        return f"{100.0 * c / n:.1f}%"
    lines = [f"# mk 重标结果 · {len(got)} 条", "",
             f"- 旧：{dict(old)}",
             f"- 新：{dict(new)}",
             f"- common 占比：{pct(old.get('common', 0), len(got))} → {pct(new.get('common', 0), len(got))}",
             "", "## 旧 → 新", ""]
    for (a, b), n in confusion.most_common():
        if a != b:
            lines.append(f"- {MKCN.get(a, a)} → {MKCN.get(b, b)}：{n}")
    lines.append("")
    lines.append("## 被改判为共同原因的例子")
    for x in moved[:15]:
        lines.append(f"- [{x.get('frame', '')}] {x['text']}（{x.get('mk_why', '')}）")
    (OUT_DIR / "corpus_mk.md").write_text("\n".join(lines), encoding="utf-8")
    print("old", dict(old))
    print("new", dict(new))
    print("-> data/miner/corpus_mk.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
