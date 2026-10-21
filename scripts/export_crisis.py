"""本地导出危机记录（不联网、不上传）。

用法：
    python scripts/export_crisis.py --list
    python scripts/export_crisis.py --event 20261022-060645-29e7d5aa --out exports/case1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rongqiu import crisis_export


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="列出本机危机记录")
    p.add_argument("--migrate", action="store_true", help="把旧快照收敛为只保留问题/时间/地区")
    p.add_argument("--event", help="事件 ID")
    p.add_argument("--out", help="导出目录（默认：文档/RongqiuCrisisExports/<event_id>）")
    p.add_argument("--open", action="store_true", help="导出后打开所在文件夹")
    args = p.parse_args()

    if args.migrate:
        from rongqiu import crisis_store
        print(json.dumps(crisis_store.migrate_v2(), ensure_ascii=False, indent=1))
        return 0
    if args.list:
        events = crisis_export.list_events()
        print(json.dumps(events, ensure_ascii=False, indent=1))
        return 0
    if not args.event:
        p.error("需要 --event；或用 --list / --migrate")
    try:
        result = crisis_export.export_event(args.event, args.out)
    except ValueError as exc:
        print("导出失败：" + str(exc))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if args.open:
        try:
            os.startfile(result["out"])
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
