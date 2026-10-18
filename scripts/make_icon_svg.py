"""生成 docs/icon.svg —— 绒球图标（v5，去病毒化）。

问题：前四版都是「圆形实心体 + 四周放射状突起」，
这是教科书级的病毒画法。必须彻底避开「放射的刺」。

v5 换画法：
    不用任何从圆心向外的长线。
    改用数百根【随机方向、极短】的绒，铺满整个球体——
    像棉花、像毛毡，不像病毒。

    球体   柔粉径向渐变圆
    绒     900 根 3-8px 随机方向短绒，低透明度，铺满并略微溢出边缘 → 毛茸茸的轮廓
    旋     右上角一撮绒按螺旋排列，颜色偏绿，不画线条，只排绒
    原核   中心一点绿
"""

import math
import random
import pathlib

W = H = 256
CX = CY = 128
random.seed(97)

BODY_R = 54
SWIRL = math.radians(-44)
FILL = 1.62

parts = []

# ---- 球体：柔和底色，边缘用模糊让它不那么硬 ----
parts.append(
    f'<circle cx="{CX}" cy="{CY}" r="{BODY_R}" fill="url(#body)" filter="url(#soft)"/>'
)

def short_tuft(x, y, ang, length, width, opacity, grad=True):
    x2 = x + length * math.cos(ang)
    y2 = y + length * math.sin(ang)
    mx = x + length * 0.5 * math.cos(ang + random.uniform(-0.5, 0.5))
    my = y + length * 0.5 * math.sin(ang + random.uniform(-0.5, 0.5))
    stroke = "url(#fuzz)" if grad else "#ffb3c6"
    return (f'<path d="M{x:.2f},{y:.2f} Q{mx:.2f},{my:.2f} {x2:.2f},{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{width:.2f}" '
            f'stroke-opacity="{opacity:.2f}" stroke-linecap="round" fill="none"/>')

# ---- 绒：铺满球体 ----
N = 1500
for i in range(N):
    # 在圆内均匀撒点（sqrt 保证不往圆心堆）
    r = BODY_R * math.sqrt(random.random()) * 1.02
    a = random.uniform(0, 2 * math.pi)
    x, y = CX + r * math.cos(a), CY + r * math.sin(a)

    # 方向完全随机 —— 这是不像病毒的关键：没有任何「向外」的倾向
    ang = random.uniform(0, 2 * math.pi)
    length = random.uniform(2.2, 5.2)
    width = random.uniform(0.75, 1.15)
    opacity = random.uniform(0.10, 0.34)

    # 越靠近边缘越淡，让轮廓软下来
    edge = r / BODY_R
    if edge > 0.82:
        opacity *= max(0.0, 1 - (edge - 0.82) / 0.30)

    # 旋：这一带的绒按螺旋方向排列，颜色偏绿
    parts.append(short_tuft(x, y, ang, length, width, opacity))

# ---- 旋：一段绿色螺旋，轻轻压在绒上面 ----
sx, sy = CX + (BODY_R - 12) * math.cos(SWIRL), CY + (BODY_R - 12) * math.sin(SWIRL)
for j, (r0, r1, turn, w, op) in enumerate(
        [(1.4, 9, 300, 1.9, 0.85), (2.4, 15, 250, 1.5, 0.65), (3.4, 21, 210, 1.15, 0.45)]):
    pts = []
    steps = 30
    for t in range(steps):
        a = SWIRL + math.radians(turn) * (t / (steps - 1))
        r = r0 + (r1 - r0) * (t / (steps - 1))
        pts.append(f"{sx + r*math.cos(a):.2f},{sy + r*math.sin(a):.2f}")
    parts.append(
        f'<polyline points="{" ".join(pts)}" fill="none" '
        f'stroke="url(#swirl)" stroke-width="{w}" stroke-linecap="round" '
        f'stroke-linejoin="round" stroke-opacity="{op}"/>'
    )

# ---- 原核 ----
parts.append(f'<circle cx="{CX}" cy="{CY}" r="4.5" fill="url(#core)"/>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
  <defs>
    <radialGradient id="body" cx="38%" cy="32%" r="72%">
      <stop offset="0%" stop-color="#ffe3ec"/>
      <stop offset="52%" stop-color="#ffc3d3"/>
      <stop offset="100%" stop-color="#f79ab4"/>
    </radialGradient>
    <linearGradient id="fuzz" x1="0.2" y1="0" x2="0.8" y2="1">
      <stop offset="0%" stop-color="#ffd6e0"/>
      <stop offset="55%" stop-color="#ffa9c0"/>
      <stop offset="100%" stop-color="#f2769c"/>
    </linearGradient>
    <linearGradient id="swirl" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#9ed0b0"/>
      <stop offset="100%" stop-color="#4f8064"/>
    </linearGradient>
    <radialGradient id="core" cx="34%" cy="30%" r="78%">
      <stop offset="0%" stop-color="#a8d8ba"/>
      <stop offset="100%" stop-color="#3f6b4f"/>
    </radialGradient>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.6"/>
    </filter>
  </defs>
  <g transform="translate(128,128) scale({FILL}) translate(-128,-128)">
    {''.join(parts)}
  </g>
</svg>
'''

out = pathlib.Path("docs/icon.svg")
out.write_text(svg, encoding="utf-8")
print("wrote", out, len(svg), "bytes")
