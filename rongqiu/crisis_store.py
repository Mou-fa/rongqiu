"""危机触发时的本地快照与完整性清单。

只保留这一刻的第一接触面：问题、时间、地区。
不保存回答、自述、历史判断或 journal 副本——避免记录被误读成
「绒球的历史判断导致了轻生」。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .paths import DATA

SCHEMA = 2
MANIFEST_SCHEMA = 1
NOTE = "本机自动保存；只保留问题、时间、地区；不上传、不进入校准、不参与统计。"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _first_contact(payload: dict) -> dict:
    return {
        "question": str(payload.get("question") or ""),
        "region": str(payload.get("region") or ""),
    }


def _write_manifest(folder: Path, event_id: str, now: datetime) -> dict:
    path = folder / (event_id + ".json")
    manifest_path = folder / (event_id + ".manifest.json")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "event_id": event_id,
        "created_at": now.isoformat(timespec="seconds"),
        "files": [{"name": path.name, "sha256": _sha256(path)}],
        "note": "SHA-256 清单；只证明文件未被改动，不证明内容真实或作者身份。",
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest


def save(payload: dict, source: str) -> dict:
    """保存一次危机事件的第一接触面；绝不抛异常。"""
    now = datetime.now().astimezone()
    utc = datetime.now(timezone.utc)
    event_id = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    folder = Path(DATA) / "crisis"
    path = folder / (event_id + ".json")
    manifest_path = folder / (event_id + ".manifest.json")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": SCHEMA,
            "event_id": event_id,
            "saved_at": now.isoformat(timespec="seconds"),
            "utc": utc.isoformat(timespec="seconds"),
            "timezone": now.tzname(),
            "utc_offset_seconds": int((now.utcoffset() or utc.utcoffset()).total_seconds()),
            "source": source,
            "request": _first_contact(payload),
            "manifest": manifest_path.name,
            "note": NOTE,
        }
        _write_json_atomic(path, record)
        _write_manifest(folder, event_id, now)
        return {"ok": True, "event_id": event_id, "path": str(path),
                "manifest": str(manifest_path),
                "sha256": _sha256(path)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def event_json(event_id: str) -> Path | None:
    path = Path(DATA) / "crisis" / (event_id + ".json")
    return path if path.exists() else None


def list_events() -> list[dict]:
    folder = Path(DATA) / "crisis"
    if not folder.exists():
        return []
    out = []
    for p in sorted(folder.glob("*.json"), reverse=True):
        if p.name.endswith(".manifest.json"):
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "event_id": rec.get("event_id", p.stem),
            "saved_at": rec.get("saved_at"),
            "source": rec.get("source"),
            "path": str(p),
            "manifest": bool((folder / (p.stem + ".manifest.json")).exists()),
        })
    return out


def verify_event(event_id: str) -> dict:
    folder = Path(DATA) / "crisis"
    path = event_json(event_id)
    manifest_path = folder / (event_id + ".manifest.json")
    if path is None:
        return {"ok": False, "error": "event_not_found", "checks": []}
    if not manifest_path.exists():
        return {"ok": False, "error": "manifest_missing", "checks": []}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "error": "manifest_invalid", "checks": []}
    checks = []
    for f in manifest.get("files") or []:
        name = f.get("name")
        p = folder / name
        actual = _sha256(p) if p.exists() else None
        checks.append({"name": name, "expected": f.get("sha256"),
                       "actual": actual,
                       "ok": actual is not None and actual == f.get("sha256")})
    return {"ok": bool(checks) and all(c["ok"] for c in checks),
            "event_id": event_id, "checks": checks}


def migrate_v2() -> dict:
    """把旧版快照收敛到只保留问题/时间/地区。

    - 删除旧版 journal 副本；
    - request 只留 question / region；
    - 重建 SHA-256 清单。
    """
    folder = Path(DATA) / "crisis"
    if not folder.exists():
        return {"ok": True, "migrated": 0, "removed_journals": 0}
    removed = 0
    for p in folder.glob("*.journal.jsonl"):
        try:
            p.unlink()
            removed += 1
        except Exception:
            pass
    migrated = 0
    now = datetime.now().astimezone()
    for p in folder.glob("*.json"):
        if p.name.endswith(".manifest.json"):
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            rec["schema"] = SCHEMA
            rec["request"] = _first_contact(rec.get("request") or {})
            rec.pop("journal_snapshot", None)
            rec["manifest"] = p.stem + ".manifest.json"
            rec["note"] = NOTE
            _write_json_atomic(p, rec)
            _write_manifest(folder, p.stem, now)
            migrated += 1
        except Exception:
            continue
    return {"ok": True, "migrated": migrated, "removed_journals": removed}
