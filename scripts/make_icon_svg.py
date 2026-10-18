"""生成 docs/icon.svg —— 绒球图标 v7（手绘蒲公英，黑底黄线）。

按用户提供的草图重绘：
    两株蒲公英，左大右小，各有双线茎
    三颗飞走的种子（细梗 + 小圆环）
    线条粗、圆头、小圆环收尾，手绘感

配色按用户要求把原图的黑黄对调：
    原图：黄底黑线  →  现在：黑底黄线
并尽量撑满画布。

坐标按原图比例换算过来（原图 410-830 × 215-640 的方形区域映射到 256）。
"""

import math
import pathlib

W = H = 256
BG = "#000000"
FG = "#F5E500"

SW_LINE = 6.2
SW_RING = 5.2
R_TIP = 6.8
R_HUB = 8.6

parts = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BG}"/>']


def ring(x, y):
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{R_TIP}" fill="{BG}" '
            f'stroke="{FG}" stroke-width="{SW_RING}"/>')


def flower(cx, cy, R, n, phase):
    out = [f'<circle cx="{cx}" cy="{cy}" r="{R_HUB}" fill="{BG}" '
           f'stroke="{FG}" stroke-width="{SW_RING}"/>']
    for i in range(n):
        ang = phase + 2 * math.pi * i / n
        out.append(
            f'<line x1="{cx + (R_HUB + 4) * math.cos(ang):.2f}" '
            f'y1="{cy + (R_HUB + 4) * math.sin(ang):.2f}" '
            f'x2="{cx + R * math.cos(ang):.2f}" y2="{cy + R * math.sin(ang):.2f}" '
            f'stroke="{FG}" stroke-width="{SW_LINE}" stroke-linecap="round"/>'
        )
        out.append(ring(cx + R * math.cos(ang), cy + R * math.sin(ang)))
    return "".join(out)


def stem(x0, y0, x1, y1, gap=10.0):
    """双线茎：两条平行线，底端不封口（原图就是开口的）。"""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    out = []
    for s in (-1, 1):
        ax, ay = x0 + nx * gap / 2 * s, y0 + ny * gap / 2 * s
        bx, by = x1 + nx * gap / 2 * s, y1 + ny * gap / 2 * s
        mx = (ax + bx) / 2 + nx * 4 * s
        my = (ay + by) / 2 + ny * 4 * s
        out.append(f'<path d="M{ax:.2f},{ay:.2f} Q{mx:.2f},{my:.2f} {bx:.2f},{by:.2f}" '
                   f'stroke="{FG}" stroke-width="{SW_LINE}" stroke-linecap="round" fill="none"/>')
    return "".join(out)


def seed(x, y, ang, length=28, curve=0.55):
    """飞走的种子：一截弯梗 + 顶端小圆环。"""
    x2 = x + length * math.cos(ang)
    y2 = y + length * math.sin(ang)
    mx = x + length * 0.6 * math.cos(ang + curve)
    my = y + length * 0.6 * math.sin(ang + curve)
    return (f'<path d="M{x:.2f},{y:.2f} Q{mx:.2f},{my:.2f} {x2:.2f},{y2:.2f}" '
            f'stroke="{FG}" stroke-width="{SW_LINE}" stroke-linecap="round" fill="none"/>'
            + ring(x2, y2))


# ---- 左大花 ----
LX, LY, LR = 74, 78, 62
parts.append(stem(LX + 10, LY + 48, LX + 26, 236))
parts.append(flower(LX, LY, LR, 10, phase=math.radians(-96)))

# ---- 右小花 ----
RX, RY, RR = 182, 134, 45
parts.append(stem(RX - 10, RY + 34, RX - 34, 232))
parts.append(flower(RX, RY, RR, 8, phase=math.radians(28)))

# ---- 飞走的种子 ----
parts.append(seed(160, 60, math.radians(-72), 30, 0.6))
parts.append(seed(212, 82, math.radians(-34), 26, 0.5))
parts.append(seed(224, 128, math.radians(18), 22, 0.55))

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
  {''.join(parts)}
</svg>
'''

pathlib.Path("docs/icon.svg").write_text(svg, encoding="utf-8")
pathlib.Path("docs/icon-compact.svg").write_text(svg, encoding="utf-8")
print("wrote docs/icon.svg", len(svg), "bytes")
