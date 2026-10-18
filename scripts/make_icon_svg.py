"""生成 docs/icon.svg —— 绒球图标。

设计：
    球体     柔粉径向渐变实心圆，先给住「一颗球」的形体
    边缘绒   两圈短毛向外发散，制造蓬松感
    旋       右上角一撮毛往里卷成绿色螺旋——毛球定理说的那个梳不平的旋，
             也就是 811 里那 20% 永远拿不到的未知
    原核     中心一点绿

为什么是「实心球 + 边缘绒」而不是「从圆心发散的辐条」：
辐条在 32px 下会糊成一只海胆，看不出是球。实心球缩小后仍然是一颗球。

改颜色/密度/大小都在这里调，然后：
    python scripts/make_icon_svg.py
    # 用 Edge 渲染 docs/icon.svg → docs/icon-512.png
    python scripts/make_icon.py
"""

import math
import random
import pathlib

W = H = 256
CX = CY = 128
random.seed(31)

BODY_R = 50
SWIRL = math.radians(-46)      # 旋的位置：右上
SWIRL_HALF = math.radians(20)  # 旋的角宽度
FILL = 1.72                    # 整体放大到填满画布


def polar(ang, r):
    return CX + r * math.cos(ang), CY + r * math.sin(ang)


parts = []
parts.append(f'<circle cx="{CX}" cy="{CY}" r="{BODY_R}" fill="url(#body)"/>')

# 边缘绒：两圈短毛
RINGS = [
    (120, BODY_R - 3, 17, 1.15, 0.55),
    (88, BODY_R - 10, 10, 1.5, 0.85),
]
for n, r0, span, width, opacity in RINGS:
    for i in range(n):
        ang = 2 * math.pi * i / n + random.uniform(-0.06, 0.06)
        length = r0 + span * (0.78 + 0.22 * random.random())
        d = abs((ang - SWIRL + math.pi) % (2 * math.pi) - math.pi)
        bend = random.uniform(-0.08, 0.08)

        if d < SWIRL_HALF:
            # 越靠近旋心，毛越往切线倒、越短 → 形成一处分缝
            k = 1 - d / SWIRL_HALF
            side = 1 if math.sin(ang - SWIRL) > 0 else -1
            bend += side * k * math.radians(120)
            length -= span * 0.45 * k

        x1, y1 = polar(ang, r0)
        x2, y2 = polar(ang + bend, length)
        mx, my = polar(ang + bend * 0.35, (r0 + length) / 2)
        parts.append(
            f'<path d="M{x1:.2f},{y1:.2f} Q{mx:.2f},{my:.2f} {x2:.2f},{y2:.2f}" '
            f'stroke="url(#hair)" stroke-width="{width}" '
            f'stroke-opacity="{opacity}" stroke-linecap="round" fill="none"/>'
        )

# 旋：三圈逐渐收小的绿色螺旋
sx, sy = polar(SWIRL, BODY_R - 6)
for j, (r0, r1, turn, w) in enumerate(
        [(1.5, 9, 280, 2.0), (2.5, 14, 240, 1.5), (3.5, 18, 205, 1.1)]):
    pts = []
    steps = 26
    for t in range(steps):
        a = SWIRL + math.radians(turn) * (t / (steps - 1))
        r = r0 + (r1 - r0) * (t / (steps - 1))
        pts.append(f"{sx + r * math.cos(a):.2f},{sy + r * math.sin(a):.2f}")
    parts.append(
        f'<polyline points="{" ".join(pts)}" fill="none" '
        f'stroke="url(#swirl)" stroke-width="{w}" stroke-linecap="round" '
        f'stroke-linejoin="round" stroke-opacity="{0.85 - j * 0.20:.2f}"/>'
    )

# 原核
parts.append(f'<circle cx="{CX}" cy="{CY}" r="4.5" fill="url(#core)"/>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
  <defs>
    <radialGradient id="body" cx="38%" cy="32%" r="72%">
      <stop offset="0%" stop-color="#ffdbe5"/>
      <stop offset="55%" stop-color="#ffb9cb"/>
      <stop offset="100%" stop-color="#f58aab"/>
    </radialGradient>
    <linearGradient id="hair" x1="0.2" y1="0" x2="0.8" y2="1">
      <stop offset="0%" stop-color="#ffd0dc"/>
      <stop offset="60%" stop-color="#ffa6bd"/>
      <stop offset="100%" stop-color="#ef7ba1"/>
    </linearGradient>
    <linearGradient id="swirl" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#9ccfae"/>
      <stop offset="100%" stop-color="#4f8064"/>
    </linearGradient>
    <radialGradient id="core" cx="34%" cy="30%" r="78%">
      <stop offset="0%" stop-color="#a8d8ba"/>
      <stop offset="100%" stop-color="#3f6b4f"/>
    </radialGradient>
  </defs>
  <g transform="translate(128,128) scale({FILL}) translate(-128,-128)">
    {''.join(parts)}
  </g>
</svg>
'''

out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "icon.svg"
out.write_text(svg, encoding="utf-8")
print("wrote", out, len(svg), "bytes")
