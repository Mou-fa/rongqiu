"""绒球的应用路径。

开发时：数据与配置就在仓库里（和以前一样）。
打包版：只读资源在程序目录，用户数据在 %APPDATA%\\Rongqiu。
环境变量 RONGQIU_HOME 可以覆盖用户目录（测试 / 绿色版用）。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    ROOT = Path(__file__).resolve().parents[1]

def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


_home_env = os.environ.get("RONGQIU_HOME", "").strip()
if _home_env:
    HOME = Path(_home_env)
elif FROZEN:
    # 用户数据目录：优先 AppData；不可写就退回程序旁边的便携目录。
    candidates = []
    for env in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(env, "").strip()
        if base:
            candidates.append(Path(base) / "Rongqiu")
    candidates.append(Path(sys.executable).resolve().parent / "RongqiuData")
    candidates.append(Path.home() / "RongqiuData")
    HOME = next((c for c in candidates if _writable(c)), candidates[-1])
else:
    HOME = ROOT

DATA = HOME / "data"
CONFIG = HOME / "configs"


def _copy_once(src: Path, dst: Path) -> None:
    if dst.exists() or not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(src, dst)
    except OSError:
        pass


def ensure_home() -> None:
    """确保用户目录存在；打包版首次运行时把只读资源复制过去。"""
    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)
    if not FROZEN:
        return
    for name in ("questions.yaml", "taxonomy.yaml", "soundscape.yaml"):
        _copy_once(ROOT / "configs" / name, CONFIG / name)
    for name in ("triple_index.json", "local_corpus.json"):
        _copy_once(ROOT / "data" / name, DATA / name)


def config_file(name: str) -> Path:
    """用户配置优先；没有就用包内默认（只读）。"""
    user = CONFIG / name
    if user.exists():
        return user
    return ROOT / "configs" / name


ensure_home()
