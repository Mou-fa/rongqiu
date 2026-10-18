"""生成绒球的全套图标：SVG + 多尺寸 PNG + favicon.ico。

设计依据见 docs/ICON.md。改颜色/尺寸都在这里调，然后重跑。
"""

import pathlib
import shutil

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
STATIC = ROOT / "app" / "static"

# 512 母版（由 Edge 渲染 docs/icon.svg 得到）
master_path = DOCS / "icon-512.png"
if not master_path.exists():
    raise SystemExit("缺少 docs/icon-512.png，先用 Edge 渲染 docs/icon.svg")

master = Image.open(master_path).convert("RGBA")

for size in (512, 256, 128, 64, 32, 16):
    img = master.resize((size, size), Image.LANCZOS)
    img.save(DOCS / f"icon-{size}.png")
    print(f"  docs/icon-{size}.png")

# favicon.ico：16/32/48 三档，浏览器自己挑
ico_sizes = [16, 32, 48]
frames = [master.resize((s, s), Image.LANCZOS) for s in ico_sizes]
frames[0].save(DOCS / "favicon.ico", format="ICO",
               sizes=[(s, s) for s in ico_sizes], append_images=frames[1:])
print("  docs/favicon.ico")

# 给应用用的副本
STATIC.mkdir(parents=True, exist_ok=True)
shutil.copy(DOCS / "icon.svg", STATIC / "icon.svg")
shutil.copy(DOCS / "favicon.ico", STATIC / "favicon.ico")
print("  app/static/icon.svg + favicon.ico")
