"""把评审过的问句草稿导入 configs/questions.yaml。

    python scripts/import_questions.py
    python scripts/import_questions.py --drafts data/question_drafts/draft.yaml --dry-run

只做三件事：校验、合并、写回。不发明问句。
导入后：
- 每条都有 mk（理论三类，单选）+ domains（16 类，可多选）；
- 草稿里带待核标记的，保留成注释字段 note（不参与计算）；
- 原文件头部注释保留。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rongqiu import questions as qbank  # noqa: E402

QUESTIONS_PATH = ROOT / "configs" / "questions.yaml"
DEFAULT_DRAFTS = ROOT / "data" / "question_drafts" / "draft.yaml"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", default=str(DEFAULT_DRAFTS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    drafts = yaml.safe_load(Path(args.drafts).read_text(encoding="utf-8"))["questions"]
    current = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
    known = set(qbank.domain_names())
    mk_ok = set(qbank.MK_VALUES)
    existing_text = {str(q.get("text", "")).strip() for q in current}

    problems: list[str] = []
    imported: list[dict] = []
    for d in drafts:
        text = str(d.get("text", "")).strip()
        if not text:
            problems.append("空问句")
            continue
        if text in existing_text:
            problems.append(f"已存在：{text}")
            continue
        mk = str(d.get("mk", "")).strip()
        if mk not in mk_ok:
            problems.append(f"mk 非法：{text} -> {mk}")
        polarity = str(d.get("polarity", "")).strip()
        if polarity not in ("positive", "negative"):
            problems.append(f"polarity 非法：{text}")
        domains = [str(x).strip() for x in (d.get("domains") or []) if str(x).strip()]
        if not domains or any(x not in known for x in domains):
            problems.append(f"domains 非法：{text} -> {domains}")

        item = {
            "id": "",
            "text": text,
            "when": str(d.get("when", "always")).strip() or "always",
            "polarity": polarity,
            "mk": mk,
            "domains": domains,
            "why": str(d.get("why", "")).strip(),
        }
        flags = d.get("flags") or []
        if flags:
            item["note"] = "导入时待核：" + "；".join(str(f) for f in flags)
        imported.append(item)

    if problems:
        print("发现问题，未写入：")
        for p in problems:
            print(" -", p)
        return 1

    # 编号：保留原有 id；新问句用 q01…，避免和 last_time 之类冲突
    next_n = 1
    for item in imported:
        while True:
            qid = f"q{next_n:02d}"
            next_n += 1
            if qid not in {str(q.get("id", "")) for q in current}:
                item["id"] = qid
                break

    merged = list(current) + imported
    header = QUESTIONS_PATH.read_text(encoding="utf-8").split("\nquestions:", 1)[0]
    header += ("\n# ---\n"
               f"# 2026-10-20：从 4064 条实测语料里批量起草、经使用者全部审定后导入"
               f"（{len(imported)} 条）。\n"
               "# 每条带 mk（理论三类，单选）+ domains（16 类，可多选）。\n"
               "# note 是导入时的待核标记，不参与计算；复核后可删。\n")
    body = yaml.safe_dump({"questions": merged}, allow_unicode=True,
                          sort_keys=False, width=1000)
    if args.dry_run:
        print(f"dry-run: 将导入 {len(imported)} 条，总计 {len(merged)} 条")
        return 0
    QUESTIONS_PATH.write_text(header + body, encoding="utf-8")
    print(f"imported {len(imported)}, total {len(merged)} -> {QUESTIONS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
