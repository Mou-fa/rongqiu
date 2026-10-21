"""危机触发时的本地快照。

原则：
- 只写本机，不上传、不联网、不进入校准、不参与统计；
- 保存用户此刻提供的全部请求数据 + 本地时间/时区 + 当时的 journal 副本；
- 写失败不能影响危机回应：保存是附加动作，接住人是第一动作。
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .paths import DATA

SCHEMA = 1


def save(payload: dict, source: str, journal_path: Path | None = None) -> dict:
    """把一次危机事件完整写到本机 data/crisis/ 下。

    返回 {ok, event_id, path} 或 {ok: False, error}；绝不抛异常。
    """
    now = datetime.now().astimezone()
    utc = datetime.now(timezone.utc)
    event_id = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    folder = Path(DATA) / "crisis"
    path = folder / (event_id + ".json")
    journal_copy = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if journal_path is not None and Path(journal_path).exists():
            copy_path = folder / (event_id + ".journal.jsonl")
            shutil.copy2(journal_path, copy_path)
            journal_copy = copy_path.name
        record = {
            "schema": SCHEMA,
            "event_id": event_id,
            "saved_at": now.isoformat(timespec="seconds"),
            "utc": utc.isoformat(timespec="seconds"),
            "timezone": now.tzname(),
            "utc_offset_seconds": int((now.utcoffset() or utc.utcoffset()).total_seconds()),
            "source": source,
            "request": payload,
            "journal_snapshot": journal_copy,
            "note": "本机自动保存；不上传、不进入校准、不参与统计。",
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
        return {"ok": True, "event_id": event_id, "path": str(path)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}
