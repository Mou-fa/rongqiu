"""生成绒球的全套图标：多尺寸 PNG + favicon.ico。

两套母版：
    512px 以上  用 docs/icon-512.png（标准版，绒毛细密）
    128px 以下  用 docs/icon-compact-512.png（简化版，线更粗更深）
                因为细密的绒毛一缩小就糊成一片，什么也看不见。

用法：
    python scripts/make_icon.py
"""

import pathlib
import shutil

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
STATIC = ROOT / "app" / "static"

full = Image.open(DOCS / "icon-512.png").convert("RGBA")
compact = Image.open(DOCS / "icon-compact-512.png").convert("RGBA")

# 大尺寸用标准版，小尺寸用简化版
LARGE = {512, 256, 128}
for size in (512, 256, 128, 64, 32, 16):
    src = full if size in LARGE else compact
    img = src.resize((size, size), Image.LANCZOS)
    img.save(DOCS / f"icon-{size}.png")
    print(f"  docs/icon-{size}.png  ({'标准版' if size in LARGE else '简化版'})")

# favicon：小尺寸，全用简化版
ico_sizes = [16, 32, 48]
frames = [compact.resize((s, s), Image.LANCZOS) for s in ico_sizes]
frames[0].save(DOCS / "favicon.ico", format="ICO",
               sizes=[(s, s) for s in ico_sizes], append_images=frames[1:])
print("  docs/favicon.ico")

# 应用内使用
STATIC.mkdir(parents=True, exist_ok=True)
shutil.copy(DOCS / "icon.svg", STATIC / "icon.svg")
shutil.copy(DOCS / "favicon.ico", STATIC / "favicon.ico")
shutil.copy(DOCS / "icon-128.png", STATIC / "icon-128.png")
print("  app/static/icon.svg + favicon.ico + icon-128.png")
