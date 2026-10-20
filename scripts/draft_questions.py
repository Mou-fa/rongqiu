"""从实测语料批量起草固定询问——给咨询师审的候选稿，不进库。

    python scripts/draft_questions.py
    python scripts/draft_questions.py --per-class 6 --sample 45

输入：data/miner/corpus_labels.json（4064 条考虑 + 16 类逐条标签）
输出：
    data/question_drafts/draft.yaml   机器可读草稿（status: draft，待审）
    data/question_drafts/review.md    人看的评审稿

不变量：
- 问句由人定稿。这里只起草，status 永远是 draft；
- 自动 lint 只挡硬违规（问动机、建议词、非二元、超长），挡不住「不好」；
- 每条草稿都带来源考虑，方便审阅时核对。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rongqiu import llm, questions as qbank  # noqa: E402

IN_PATH = ROOT / "data" / "miner" / "corpus_labels.json"
OUT_DIR = ROOT / "data" / "question_drafts"

ADVICE_WORDS = ("应该", "最好", "建议", "值得", "千万", "别")
FEELING_WORDS = ("觉得", "感到", "认为", "希望")
MOTIVE_WORDS = ("怕", "担心", "愿意", "打算", "想过", "想要", "期待")


def lint(text: str) -> list[str]:
    """问句的硬门。过不了 lint 的草稿不进评审稿。"""
    t = str(text or "").strip()
    bad: list[str] = []
    if not t:
        return ["空问句"]
    if not t.endswith(("？", "?")):
        bad.append("缺问号")
    if len(t) > 27:
        bad.append("超过 25 字")
    if "为什么" in t:
        bad.append("在问动机")
    for w in ADVICE_WORDS:
        if w in t:
            bad.append(f"含建议词「{w}」")
    for w in FEELING_WORDS:
        if w in t:
            bad.append(f"在问感受「{w}」")
    for w in MOTIVE_WORDS:
        if w in t:
            bad.append(f"在问动机/感受「{w}」")
    if "或" in t:
        bad.append("一次问了两件事（含「或」）")
    if "你" not in t:
        bad.append("不是问用户本人")
    if not any(x in t for x in ("吗", "是不是", "有没有", "是否", "会不会", "要不要")):
        bad.append("不像二元问句")
    return bad


def _norm(t: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", str(t or ""))


def _dup(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 8 and len(nb) >= 8 and (na in nb or nb in na):
        return abs(len(na) - len(nb)) <= 6
    return False


DRAFT_SYSTEM = """你是「绒球」的问句起草员。下面给你「{cls}」这一类面下的真实考虑（来自很多不同的决定），
请归纳它们背后的「面」，并为每种面起草 1–2 句固定询问。

固定询问的规则（用户从心理咨询师角度定）：
- 只问「已经发生的、能被看见的」事实：过去的做法、最近的身体/时间/钱/关系状况
- 不问打算、感受、想法、评价；不问「为什么」
- 必须是二元问句，只能用「是 / 否」回答
- 不超过 25 字，口语，跨文化普适
- 不得出现：为什么、应该、最好、建议、值得、别、千万、觉得、感到、认为、怕、担心、愿意、打算、想要、期待
- 一句只问一件事，不要用「或」把两件事并在一起
- 不能绑死在某一个具体决定上；要能用于至少 3 类决定
- 不要与这两句重复：「你上一次遇到这种情况，最后怎么选的？」「这件事你已经反复想了一阵子，是吗？」

每条输出：
- text：问句（结尾带问号）
- polarity：答「是」对「会做这件事」意味着什么——positive=倾向会，negative=倾向不会
- mk：这句探测的是哪类面——cause（这次的具体触发/约束）/ effect（做了之后的后果）/ common（我这个人或我长期处境的稳定背景）
- pattern：不超过 8 字，这一问归纳的是哪种面
- why：不超过 20 字，为什么这句能探到它
- comes_from：它归纳自下面哪些编号的考虑（1–3 个）
- applies_to：这句话能用在哪些类型的决定上（列 3–5 个，用「、」分隔）
只输出 JSON：{"drafts":[{"text":"","polarity":"","mk":"","pattern":"","why":"","comes_from":[],"applies_to":""}]}"""

DRAFT_PROMPT = """这一类面：{cls}（定义：{definition}）

考虑（共 {n} 条）：
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


def sample_for_class(items: list[dict], limit: int) -> list[dict]:
    """按框架轮转取样，保证多样性。"""
    by_frame: dict[str, list[dict]] = {}
    seen = set()
    for it in items:
        text = it["text"]
        if text in seen:
            continue
        seen.add(text)
        by_frame.setdefault(it.get("frame", ""), []).append(it)
    picked: list[dict] = []
    round_no = 0
    while len(picked) < limit:
        added = False
        for group in by_frame.values():
            if round_no < len(group):
                picked.append(group[round_no])
                added = True
                if len(picked) >= limit:
                    break
        if not added:
            break
        round_no += 1
    return picked


MERGE_SYSTEM = """你是「绒球」的问句库编辑。下面是一批候选固定询问（编号），有些在问同一件事。
请把问同一件事的合并成一组；每组选一条最通用、最口语、最能直接回答的作为保留项。
不要合并不同的事。宁可多分一组，不要硬并。
只输出 JSON：{"groups":[{"keep":1,"members":[1,5,9]}]}"""

MERGE_PROMPT = """共 {n} 条：

{lines}

只输出 JSON。"""


def cluster_drafts(drafts: list[dict], cfg) -> tuple[list[dict], int]:
    """跨类合并：不同类里冒出来的同一件事，只留一条；保留所有类作为 domains。"""
    if len(drafts) <= 1:
        return drafts, 0
    lines = "\n".join(f"{i + 1}. {d['text']}" for i, d in enumerate(drafts))
    raw = llm.complete(MERGE_PROMPT.format(n=len(drafts), lines=lines),
                       system=MERGE_SYSTEM, cfg=cfg)
    groups = _json_of(raw).get("groups", []) or []
    keep_map: dict[int, list[int]] = {}
    for g in groups:
        try:
            k = int(g.get("keep", 0)) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= k < len(drafts)):
            continue
        members: list[int] = []
        for m in g.get("members", []) or []:
            try:
                mi = int(m) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= mi < len(drafts):
                members.append(mi)
        if k not in members:
            members.append(k)
        keep_map[k] = members
    if not keep_map:
        return drafts, 0
    kept: list[dict] = []
    for k in sorted(keep_map):
        d = dict(drafts[k])
        # 合并进来的类都算它的 domains（可多选），覆盖不丢
        d["domains"] = sorted({drafts[m]["class"] for m in keep_map[k]})
        kept.append(d)
    return kept, len(drafts) - len(kept)


STABLE_SYSTEM = """你是「绒球」的立场官。给你一批候选固定询问，逐条判断：
答「是」对「我会做这件事吗」的方向，是否跨决定稳定？

- 如果这句话答「是」，在不同类型的决定里都倾向「做」或都倾向「不做」→ stable=true，
  并给 direction（positive=倾向做，negative=倾向不做）；
- 如果能找到一类决定答「是」倾向做、另一类决定答「是」倾向不做 → stable=false，
  并给两类决定的例子。

只输出 JSON：{"items":[{"idx":1,"stable":true,"direction":"positive|negative","note":"不超过20字"}]}"""

STABLE_PROMPT = """共 {n} 条：

{lines}

只输出 JSON。"""


def review_stability(drafts: list[dict], cfg) -> None:
    """固定问句的极性必须跨决定稳定，否则不同决定里方向会反。"""
    if not drafts:
        return
    lines = "\n".join(f"{i + 1}. {d['text']}" for i, d in enumerate(drafts))
    try:
        raw = llm.complete(STABLE_PROMPT.format(n=len(drafts), lines=lines),
                           system=STABLE_SYSTEM, cfg=cfg)
        items = _json_of(raw).get("items", []) or []
    except Exception as exc:
        print(f"  [warn] stability review failed ({type(exc).__name__})")
        items = []
    by_idx = {}
    for it in items:
        try:
            i = int(it.get("idx", 0)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(drafts):
            by_idx[i] = it
    for i, d in enumerate(drafts):
        it = by_idx.get(i, {})
        d["stable"] = bool(it.get("stable", True))
        d["stable_dir"] = str(it.get("direction", "")).strip().lower()
        d["stable_note"] = str(it.get("note", "")).strip()[:30]


def ensure_coverage(kept: list[dict], originals: list[dict],
                    min_per_class: int = 3) -> tuple[list[dict], int]:
    """跨类合并容易把某一类吃光；按类补回原始草稿，保证每类至少 min 条。"""
    have: dict[str, int] = {}
    for d in kept:
        for dom in (d.get("domains") or [d["class"]]):
            have[dom] = have.get(dom, 0) + 1
    classes = list(dict.fromkeys(d["class"] for d in originals))
    added = 0
    for cls in classes:
        if have.get(cls, 0) >= min_per_class:
            continue
        for d in originals:
            if d["class"] != cls:
                continue
            if any(_dup(d["text"], k["text"]) for k in kept):
                continue
            nd = dict(d)
            nd["domains"] = [cls]
            kept.append(nd)
            have[cls] = have.get(cls, 0) + 1
            added += 1
            if have[cls] >= min_per_class:
                break
    return kept, added


def _applies_count(text: str) -> int:
    parts = [p for p in re.split(r"[、，,/；;]", str(text or "")) if p.strip()]
    return len(parts)


REVIEW_SYSTEM = """你是「绒球」的问句审稿人（立场官视角）。下面是一批候选固定询问，逐条审。
合格标准：
1. 只问「已经发生的、能被看见的」事实（行为、处境、历史），不问打算、感受、想法、评价、动机；
2. 必须是二元问句（是 / 否）；
3. 不超过 25 字；
4. 不得有引导性：不暗示答案、不含评价/建议/比较；
5. 能跨至少 3 类决定，不绑死在某一个具体决定上；
6. 与其它条目明显重复的，只留最早的一条。
对每条输出 idx、keep（true / false）、reason（不超过 15 字）。
只输出 JSON：{"items":[{"idx":1,"keep":true,"reason":""}]}"""

REVIEW_PROMPT = """共 {n} 条：

{lines}

只输出 JSON。"""


def review_drafts(drafts: list[dict], cfg) -> None:
    """独立复核：模型当审稿人，把不合格/重复的标出来。"""
    if not drafts:
        return
    lines = "\n".join(f"{i + 1}. {d['text']}" for i, d in enumerate(drafts))
    try:
        raw = llm.complete(REVIEW_PROMPT.format(n=len(drafts), lines=lines),
                           system=REVIEW_SYSTEM, cfg=cfg)
        items = _json_of(raw).get("items", []) or []
    except Exception as exc:
        print(f"  [warn] review failed ({type(exc).__name__})")
        items = []
    by_idx = {}
    for it in items:
        try:
            i = int(it.get("idx", 0)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(drafts):
            by_idx[i] = it
    for i, d in enumerate(drafts):
        it = by_idx.get(i)
        if it is None:
            d["review_keep"] = True
            d["review_reason"] = ""
        else:
            d["review_keep"] = bool(it.get("keep", True))
            d["review_reason"] = str(it.get("reason", "")).strip()[:30]


def draft_one(cls: str, definition: str, items: list[dict],
              per_class: int, cfg) -> list[dict]:
    lines = "\n".join(f"{i + 1}. {it['text']}" for i, it in enumerate(items))
    raw = llm.complete(DRAFT_PROMPT.format(cls=cls, definition=definition,
                                          n=len(items), lines=lines),
                       system=DRAFT_SYSTEM.replace("{cls}", cls), cfg=cfg)
    drafts = _json_of(raw).get("drafts", []) or []

    out = []
    for d in drafts[:per_class]:
        text = str(d.get("text", "")).strip()
        if not text:
            continue
        covers = []
        for c in d.get("comes_from", []) or []:
            try:
                i = int(c) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(items):
                covers.append(i)
        covers = list(dict.fromkeys(covers))[:3]
        out.append({
            "text": text,
            "polarity": str(d.get("polarity", "")).strip().lower(),
            "mk": str(d.get("mk", "")).strip().lower(),
            "pattern": str(d.get("pattern", "")).strip()[:12],
            "why": str(d.get("why", "")).strip(),
            "comes_from": [items[i]["text"] for i in covers],
            "applies_to": str(d.get("applies_to", "")).strip(),
            "class": cls,
            "lint": lint(text),
        })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(IN_PATH))
    ap.add_argument("--per-class", type=int, default=6)
    ap.add_argument("--sample", type=int, default=45)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not items:
        print("corpus_labels.json 里没有逐条标签：先跑 scripts/classify_corpus.py")
        return 1
    tax = qbank.load_taxonomy()["domains"]
    existing = [q["text"] for q in qbank.load()]

    cfg = llm.load_config()
    cfg.max_tokens = max(cfg.max_tokens, 3000)
    if not llm.available(cfg):
        print("llm key 没配置")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    jobs = []
    for d in tax:
        cls, definition = d["name"], d["definition"]
        cls_items = [it for it in items if cls in (it.get("classes") or [])]
        picked = sample_for_class(cls_items, args.sample)
        if len(picked) < 8:
            print(f"skip {cls}: only {len(picked)} items")
            continue
        jobs.append((cls, definition, picked))
    print(f"classes: {len(jobs)}")

    drafts: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(draft_one, cls, definition, picked,
                               args.per_class, cfg) for cls, definition, picked in jobs]
        for fut in as_completed(futures):
            try:
                drafts.extend(fut.result())
            except Exception as exc:
                print(f"  [warn] draft batch failed ({type(exc).__name__})")
    print(f"raw drafts: {len(drafts)} ({time.time()-t0:.0f}s)")

    # 先跨类合并（问同一件事的只留一条），再给每类保底，最后走硬规则
    original_drafts = list(drafts)
    before = len(drafts)
    drafts, merged = cluster_drafts(drafts, cfg)
    drafts, added_back = ensure_coverage(drafts, original_drafts, 3)
    print(f"after merge+coverage: {len(drafts)} (merged {merged}, added back {added_back}, in {before})")

    # 去重：和现有问句、以及草稿之间
    kept, dropped_dup, dropped_lint = [], [], []
    for d in drafts:
        if d["lint"]:
            dropped_lint.append(d)
            continue
        if any(_dup(d["text"], e) for e in existing):
            dropped_dup.append(d)
            continue
        if any(_dup(d["text"], k["text"]) for k in kept):
            dropped_dup.append(d)
            continue
        kept.append(d)
    print(f"kept: {len(kept)} | lint 挡掉 {len(dropped_lint)} | 重复挡掉 {len(dropped_dup)}")

    # 编号
    for i, d in enumerate(kept, 1):
        d["id"] = f"draft_{i:02d}"

    # 独立复核（模型当审稿人）+ 极性稳定性（固定问句的极性必须跨决定稳定）
    review_drafts(kept, cfg)
    review_stability(kept, cfg)
    for d in kept:
        d["stable"] = bool(d.get("stable", True))
        d["polarity_ok"] = (not d["stable_dir"]) or (d["stable_dir"] == d["polarity"])
        flags = []
        if not d.get("review_keep", True):
            flags.append("审稿:" + (d.get("review_reason") or "复核未过"))
        if not d["stable"]:
            flags.append("极性不稳:" + (d.get("stable_note") or ""))
        elif not d["polarity_ok"]:
            flags.append("极性可能反了")
        d["flags"] = flags
        d["recommend"] = d["stable"] and d["polarity_ok"]
    rec_count = sum(1 for d in kept if d["recommend"])
    flag_count = sum(1 for d in kept if d["flags"])
    print(f"recommended: {rec_count}/{len(kept)}, flagged: {flag_count}")

    def _dump(items_list, title):
        head = (f"# 绒球问句库 · {title}\n"
                "# 自动生成，status 永远是 draft。**必须由咨询师逐条审定后才能进 questions.yaml。**\n"
                f"# 生成时间：{time.strftime('%Y-%m-%d %H:%M')}\n"
                f"# 来源：{len(items)} 条实测考虑 / {len(tax)} 类面\n")
        return head + yaml.safe_dump({"questions": items_list}, allow_unicode=True,
                                     sort_keys=False)

    yaml_items = []
    for d in kept:
        yaml_items.append({
            "id": d["id"],
            "text": d["text"],
            "when": "always",
            "polarity": d["polarity"],
            "mk": d["mk"],
            "domains": d.get("domains") or [d["class"]],
            "why": d["why"],
            "pattern": d["pattern"],
            "applies_to": d["applies_to"],
            "recommend": d["recommend"],
            "polarity_stable": d.get("stable", True),
            "flags": d.get("flags", []),
            "comes_from": d["comes_from"],
            "status": "draft",
        })
    (OUT_DIR / "draft.yaml").write_text(_dump(yaml_items, "候选草稿"),
                                        encoding="utf-8")
    rec_items = [q for q in yaml_items if q["recommend"]]
    (OUT_DIR / "recommended.yaml").write_text(_dump(rec_items, "推荐候选（待审）"),
                                              encoding="utf-8")

    # 评审稿
    by_class: dict[str, list[dict]] = {}
    for d in kept:
        by_class.setdefault(d["class"], []).append(d)
    lines = [f"# 问句库候选草稿 · {len(kept)} 条", "",
             f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
             f"- 来源：{len(items)} 条实测考虑，{len(tax)} 类面",
             f"- 原始 {before} 条 → 跨类合并掉 {merged} → 每类保底补回 {added_back} → "
             f"lint 挡掉 {len(dropped_lint)} → 重复挡掉 {len(dropped_dup)} → 保留 {len(kept)} 条",
             f"- **推荐 {rec_count} 条**（极性稳定且方向一致，★）；{flag_count} 条带待核标记",
             "- **全部是 draft，必须咨询师审定后才能进 questions.yaml**", ""]
    coverage = []
    for d in tax:
        cls = d["name"]
        ds = by_class.get(cls, [])
        rec_n = sum(1 for x in ds if x["recommend"])
        coverage.append(f"{cls} {len(ds)}" + (f"（荐 {rec_n}）" if ds else ""))
        lines.append(f"## {cls}（{len(ds)} 条）")
        if not ds:
            lines.append("")
            lines.append("（这一类没有生成可用的问句）")
            lines.append("")
            continue
        ds.sort(key=lambda x: (not x["recommend"], x["text"]))
        lines.append("")
        lines.append("| 问句 | 荐 | 警 | polarity | domains | mk | 归纳的面 |")
        lines.append("|---|---|---|---|---|---|---|")
        for x in ds:
            lines.append(f"| {x['text']} | {'★' if x['recommend'] else ''} | "
                         f"{'⚠' if x['flags'] else ''} | {x['polarity']} | "
                         f"{'/'.join(x.get('domains') or [x['class']])} | "
                         f"{x['mk']} | {x['pattern']} |")
        flagged = [x for x in ds if x["flags"]]
        if flagged:
            lines.append("")
            lines.append("待人工核：")
            for x in flagged:
                lines.append(f"- {x['text']}（{'；'.join(x['flags'])}）")
        lines.append("")
        for x in ds[:2]:
            if x["comes_from"]:
                lines.append(f"- 例（{x['pattern']}）：" + "；".join(x["comes_from"]))
        lines.append("")
    lines.append("## 覆盖")
    lines.append("")
    lines.append("- " + " · ".join(coverage))
    lines.append("")
    (OUT_DIR / "review.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"recommended: {rec_count}")
    print("draft -> data/question_drafts/draft.yaml")
    print("recommended -> data/question_drafts/recommended.yaml")
    print("review -> data/question_drafts/review.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
