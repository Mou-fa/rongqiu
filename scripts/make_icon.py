"""用用户提供的原图直接生成图标。

只做三件事，不改设计：
    1. 黄黑对调：黄底黑线 → 黑底黄线
    2. 裁到内容包围盒（去掉原图四周的空白和边框）
    3. 放大到撑满画布

黄色取原图背景色 (255,255,0)，线条的透明度用原图亮度反推，
这样抗锯齿边缘也能保留。
"""

import argparse
import pathlib

from PIL import Image
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
STATIC = ROOT / "app" / "static"

# 原图路径由命令行传入：
#     python scripts/make_icon.py 原图.png
# 之前这里写死了一个本机绝对路径，开源时必须去掉。
_ap = argparse.ArgumentParser(description="从原图生成绒球图标")
_ap.add_argument("source", help="原图路径（黄底黑线）")
SRC = _ap.parse_args().source
YELLOW = (255, 255, 0)
BLACK = (0, 0, 0)
SIZE = 512
MARGIN = 0.035          # 四周留 3.5%，尽量大但不贴边

im = Image.open(SRC).convert("RGB")
a = np.asarray(im).astype(np.float32)
lum = a.mean(axis=2)

# 1) 内容包围盒（暗像素），先排除最外圈边框
pad = 6
inner = lum[pad:-pad, pad:-pad]
ys, xs = np.where(inner < 150)
x0, x1 = xs.min() + pad, xs.max() + pad
y0, y1 = ys.min() + pad, ys.max() + pad

# 2) 裁切并补成正方形
w, h = x1 - x0 + 1, y1 - y0 + 1
side = max(w, h)
cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
half = side // 2 + 2
L = max(0, cx - half)
T = max(0, cy - half)
Rr = min(im.width, cx + half)
Bb = min(im.height, cy + half)
crop_lum = lum[T:Bb, L:Rr]

# 3) 黄黑对调：alpha = 1 - 亮度/255，黑线 → alpha 1（黄），黄底 → alpha 0（黑）
# 原图是纯黄 (255,255,0) 底 + 纯黑线。黄的亮度约 170，黑的约 0。
# 用固定区间映射，不依赖任何统计量——统计量会被抗锯齿和压缩噪声带偏，
# 第一版就是拿「最大亮度」当基准，结果背景成了暗橄榄色。
HI, LO = 150.0, 85.0       # 亮度 > HI 视为纯背景，< LO 视为纯线条
alpha = np.clip((HI - crop_lum) / (HI - LO), 0.0, 1.0)
alpha = alpha ** 1.15      # 让线条实一点，边缘过渡更干净

fh, fw = alpha.shape
canvas = np.zeros((fh, fw, 3), dtype=np.float32)
canvas[:, :, 0] = YELLOW[0] * alpha
canvas[:, :, 1] = YELLOW[1] * alpha
canvas[:, :, 2] = YELLOW[2] * alpha

img = Image.fromarray(canvas.astype(np.uint8), "RGB")

# 4) 放到正方形画布上，撑满（只留 MARGIN）
inner_size = int(SIZE * (1 - 2 * MARGIN))
img = img.resize((inner_size, inner_size), Image.LANCZOS)
out = Image.new("RGB", (SIZE, SIZE), BLACK)
off = (SIZE - inner_size) // 2
out.paste(img, (off, off))

out.save(DOCS / "icon-512.png")
for s in (256, 128, 64, 32, 16):
    out.resize((s, s), Image.LANCZOS).save(DOCS / f"icon-{s}.png")
print("生成尺寸:", [512, 256, 128, 64, 32, 16])

# favicon
frames = [out.resize((s, s), Image.LANCZOS) for s in (16, 32, 48)]
frames[0].save(DOCS / "favicon.ico", format="ICO",
               sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[1:])
print("docs/favicon.ico")

# 应用内
STATIC.mkdir(parents=True, exist_ok=True)
out.resize((128, 128), Image.LANCZOS).save(STATIC / "icon-128.png")
out.save(STATIC / "icon-512.png")

# 同时生成一个 SVG 包装（只嵌位图，保持引用一致）
import base64, io as _io
buf = _io.BytesIO()
out.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode()
svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
       f'<image href="data:image/png;base64,{b64}" width="512" height="512"/></svg>')
(DOCS / "icon.svg").write_text(svg, encoding="utf-8")
(STATIC / "icon.svg").write_text(svg, encoding="utf-8")
print("icon.svg（内嵌位图）")
