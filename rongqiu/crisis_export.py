"""危机本地记录的本地导出。

用途：家属/警方在取得设备或合法授权后，主动导出一份可核验副本。
原则：只读本地 data/crisis/，只写用户指定的目录；不联网、不上传。
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from . import crisis_store

# 默认导出到用户文档目录，方便家属/警方在文件管理器里直接找到。
DEFAULT_EXPORT_ROOT = Path.home() / "Documents" / "RongqiuCrisisExports"
FALLBACK_ROOTS = [
    Path.home() / "RongqiuCrisisExports",
    Path.home() / "Desktop" / "RongqiuCrisisExports",
    Path.cwd() / "exports",
]


def _writable_root() -> Path:
    for candidate in [Path(DEFAULT_EXPORT_ROOT)] + FALLBACK_ROOTS:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate
        except Exception:
            continue
    raise ValueError("找不到可写的导出目录，请用 --out 指定一个位置")


def _hash(path: Path) -> str:
    return crisis_store._sha256(path)


def export_event(event_id: str, out_dir: str | Path | None = None) -> dict:
    src = crisis_store.event_json(event_id)
    if src is None:
        raise ValueError("找不到这个危机事件")
    ver = crisis_store.verify_event(event_id)
    if not ver.get("ok"):
        raise ValueError("哈希校验失败，记录可能被改动过，拒绝导出")

    folder = src.parent
    manifest = folder / (event_id + ".manifest.json")
    if out_dir is None:
        root = _writable_root()
        out = root / event_id
        if out.exists():
            out = root / (event_id + "-" + datetime.now().strftime("%H%M%S"))
    else:
        out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError("导出目录不是空的，换一个目录，避免覆盖旧证据")

    out.mkdir(parents=True, exist_ok=True)
    copied = [src, manifest]
    for p in copied:
        shutil.copy2(p, out / p.name)

    record = json.loads(src.read_text(encoding="utf-8"))
    readme = [
        "绒球危机本地记录 · 导出说明",
        "=" * 36,
        f"事件 ID：{event_id}",
        f"记录时间：{record.get('saved_at')}",
        f"时区：{record.get('timezone')}（UTC 偏移 {record.get('utc_offset_seconds')} 秒）",
        f"来源：{record.get('source')}",
        f"导出时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "文件：",
        f"- {event_id}.json：第一接触面（问题、时间、地区）",
        f"- {event_id}.manifest.json：SHA-256 清单",
        "- 摘要.txt：给家属/警方直接阅读的单页摘要",
        "- SHA256SUMS：本目录副本的 SHA-256 汇总",
        "",
        "校验：",
        "  certutil -hashfile <文件名> SHA256",
        "  或  sha256sum -c SHA256SUMS",
        "",
        "说明：",
        "- 本导出由设备持有者主动执行；绒球没有云端副本，不会自动发送给任何人。",
        "- 只包含第一接触面（问题、时间、地区），不包含历史判断、回答或完整 journal。",
        "- 哈希只能证明文件未被改动，不能证明内容真实或作者身份。",
        "- 请在合法、知情、必要的前提下使用；不要把它变成对当事人的二次伤害。",
        "",
    ]
    (out / "README.txt").write_text("\n".join(readme), encoding="utf-8")

    request = record.get("request") or {}
    summary = [
        "绒球危机记录摘要（第一接触面）",
        "=" * 32,
        f"事件 ID：{event_id}",
        f"时间：{record.get('saved_at')}",
        f"时区：{record.get('timezone')}（UTC 偏移 {record.get('utc_offset_seconds')} 秒）",
        f"地区：{request.get('region') or '（未授权定位，未记录）'}",
        f"问题：{request.get('question') or ''}",
        "",
        "说明：只包含问题、时间、地区；不包含回答、自述、历史判断或 journal。",
        "来源：绒球本机自动保存，由设备持有者主动导出。",
    ]
    (out / "摘要.txt").write_text("\n".join(summary), encoding="utf-8")

    sums = []
    for p in sorted(out.iterdir()):
        if p.name in ("SHA256SUMS", "README.txt"):
            continue
        sums.append(f"{_hash(p)}  {p.name}")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")

    return {"ok": True, "event_id": event_id, "out": str(out),
            "verify": crisis_store.verify_event(event_id)}


def list_events() -> list[dict]:
    return crisis_store.list_events()
