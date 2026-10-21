"""危机触发时的本地快照与完整性清单。

原则：
- 只写本机，不上传、不联网、不进入校准、不参与统计；
- 保存用户此刻提供的全部请求数据 + 本地时间/时区 + 当时的 journal 副本；
- 每个事件带 SHA-256 清单，方便家属/警方在合法取得设备后核验原始性；
- 写失败不能影响危机回应：保存是附加动作，接住人是第一动作。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .paths import DATA

SCHEMA = 1
MANIFEST_SCHEMA = 1


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


def save(payload: dict, source: str, journal_path: Path | None = None) -> dict:
    """把一次危机事件完整写到本机 data/crisis/ 下。

    返回 {ok, event_id, path, manifest, sha256} 或 {ok: False, error}；绝不抛异常。
    """
    now = datetime.now().astimezone()
    utc = datetime.now(timezone.utc)
    event_id = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    folder = Path(DATA) / "crisis"
    path = folder / (event_id + ".json")
    manifest_path = folder / (event_id + ".manifest.json")
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
            "manifest": manifest_path.name,
            "note": "本机自动保存；不上传、不进入校准、不参与统计。",
        }
        _write_json_atomic(path, record)
        files = [{"name": path.name, "sha256": _sha256(path)}]
        if journal_copy:
            jp = folder / journal_copy
            files.append({"name": journal_copy, "sha256": _sha256(jp)})
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "event_id": event_id,
            "created_at": now.isoformat(timespec="seconds"),
            "files": files,
            "note": "SHA-256 清单；只证明文件未被改动，不证明内容真实或作者身份。",
        }
        _write_json_atomic(manifest_path, manifest)
        return {"ok": True, "event_id": event_id, "path": str(path),
                "manifest": str(manifest_path), "sha256": files[0]["sha256"]}
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
    """按 manifest 校验一个事件；返回 {ok, checks}。"""
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
