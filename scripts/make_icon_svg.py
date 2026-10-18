"""生成绒球图标 SVG —— 蒲公英。

用法：
    python scripts/make_icon_svg.py            # 标准版 → docs/icon.svg
    python scripts/make_icon_svg.py --compact  # 小尺寸版 → docs/icon-compact.svg

为什么要两个版本：
    512px 下好看的设计，缩到 32px 会消失——线太细、颜色太浅、绒太密。
    小尺寸需要加粗线条、加深颜色、减少数量。这是图标设计的常规做法。

设计：
    蒲公英种子球 + 一个缺口 + 飞走的种子

    缺口和那颗飞走的绿色种子，就是 811 里那 20% 永远抓不到的未知。
    留下来的每一根，才是你能数的第一接触面。
"""

import argparse
import math
import random
import pathlib

W = H = 256
CX, CY = 128, 128


def build(compact: bool) -> str:
    random.seed(2026)

    R_IN = 9
    GAP = math.radians(-38)
    GAP_HALF = math.radians(10)

    # 小尺寸版：线更粗、颜色更深、种子更少、光晕更实
    line_mul = 1.9 if compact else 1.0
    op_mul = 1.25 if compact else 1.0
    rings = ([(30, 78)] if compact else [(72, 86), (44, 66)])
    pappus_len = 6.2 if compact else 5.4
    pappus_n = 3 if compact else 5

    c_fil = ("#e0678f", "#f28cac", "#ffb3c8") if compact else ("#f39ab7", "#ffb8cc", "#ffe0e9")
    c_pap = ("#e88ab0", "#d9608c") if compact else ("#ffc3d4", "#f78aa8")

    parts = []

    def pappus(x, y, ang, size, opacity):
        out = []
        for i in range(pappus_n):
            d = -0.62 + 1.24 * i / (pappus_n - 1)
            x2 = x + size * math.cos(ang + d)
            y2 = y + size * math.sin(ang + d)
            out.append(
                f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="url(#pappus)" stroke-width="{0.85 * line_mul:.2f}" '
                f'stroke-opacity="{min(1.0, opacity * op_mul):.2f}" stroke-linecap="round"/>'
            )
        return "".join(out)

    for n, r_out in rings:
        width = (1.05 if n < 60 else 1.25) * line_mul
        opacity = (0.62 if n < 60 else 0.85) * op_mul
        for i in range(n):
            ang = 2 * math.pi * i / n + random.uniform(-0.05, 0.05)
            d = abs((ang - GAP + math.pi) % (2 * math.pi) - math.pi)
            if d < GAP_HALF:
                continue
            r_end = r_out * (0.95 + 0.05 * random.random())
            bend = random.uniform(-0.06, 0.06)
            x1 = CX + R_IN * math.cos(ang)
            y1 = CY + R_IN * math.sin(ang)
            x2 = CX + r_end * math.cos(ang + bend)
            y2 = CY + r_end * math.sin(ang + bend)
            mx = CX + (R_IN + r_end) * 0.5 * math.cos(ang + bend * 0.3)
            my = CY + (R_IN + r_end) * 0.5 * math.sin(ang + bend * 0.3)
            parts.append(
                f'<path d="M{x1:.2f},{y1:.2f} Q{mx:.2f},{my:.2f} {x2:.2f},{y2:.2f}" '
                f'stroke="url(#filament)" stroke-width="{width:.2f}" '
                f'stroke-opacity="{min(1.0, opacity):.2f}" stroke-linecap="round" fill="none"/>'
            )
            parts.append(pappus(x2, y2, ang + bend, pappus_len, opacity))

    def flying(ox, oy, ang, scale, grad, opacity=1.0):
        x2 = ox + 24 * scale * math.cos(ang)
        y2 = oy + 24 * scale * math.sin(ang)
        mx = ox + 12 * scale * math.cos(ang - 0.3)
        my = oy + 12 * scale * math.sin(ang - 0.3)
        out = [f'<path d="M{ox:.2f},{oy:.2f} Q{mx:.2f},{my:.2f} {x2:.2f},{y2:.2f}" '
               f'stroke="{grad}" stroke-width="{1.1 * scale * line_mul:.2f}" '
               f'stroke-opacity="{opacity}" stroke-linecap="round" fill="none"/>']
        for i in range(pappus_n):
            d = -0.75 + 1.5 * i / (pappus_n - 1)
            fx = x2 + 8.5 * scale * math.cos(ang + d)
            fy = y2 + 8.5 * scale * math.sin(ang + d)
            out.append(f'<line x1="{x2:.2f}" y1="{y2:.2f}" x2="{fx:.2f}" y2="{fy:.2f}" '
                       f'stroke="{grad}" stroke-width="{1.0 * scale * line_mul:.2f}" '
                       f'stroke-opacity="{opacity}" stroke-linecap="round"/>')
        return "".join(out)

    g0x = CX + 96 * math.cos(GAP)
    g0y = CY + 96 * math.sin(GAP)
    parts.append(flying(g0x, g0y, GAP, 0.95, "url(#swirl)"))

    a = GAP + math.radians(-22)
    parts.append(flying(CX + 104 * math.cos(a), CY + 104 * math.sin(a),
                        a, 0.8, "url(#pappus)", 0.85))

    parts.append(f'<circle cx="{CX}" cy="{CY}" r="{R_IN}" fill="url(#receptacle)"/>')
    parts.append(f'<circle cx="{CX}" cy="{CY}" r="{4.6 if not compact else 5.6}" fill="url(#core)"/>')

    halo_op = 0.75 if compact else 0.55
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="filament" x1="0.1" y1="0" x2="0.9" y2="1">
      <stop offset="0%" stop-color="{c_fil[0]}"/>
      <stop offset="55%" stop-color="{c_fil[1]}"/>
      <stop offset="100%" stop-color="{c_fil[2]}"/>
    </linearGradient>
    <linearGradient id="pappus" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c_pap[0]}"/>
      <stop offset="100%" stop-color="{c_pap[1]}"/>
    </linearGradient>
    <linearGradient id="swirl" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#8cc4a1"/>
      <stop offset="100%" stop-color="#3f6b4f"/>
    </linearGradient>
    <radialGradient id="halo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffd6e2" stop-opacity="{halo_op}"/>
      <stop offset="70%" stop-color="#ffe4ec" stop-opacity="{halo_op * 0.4:.2f}"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="receptacle" cx="38%" cy="32%" r="70%">
      <stop offset="0%" stop-color="#ffd9e4"/>
      <stop offset="100%" stop-color="#ef7fa4"/>
    </radialGradient>
    <radialGradient id="core" cx="34%" cy="30%" r="78%">
      <stop offset="0%" stop-color="#a8d8ba"/>
      <stop offset="100%" stop-color="#3f6b4f"/>
    </radialGradient>
  </defs>
  <g transform="translate(-9,0)">
    <circle cx="{CX}" cy="{CY}" r="104" fill="url(#halo)"/>
    {''.join(parts)}
  </g>
</svg>
'''


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--compact", action="store_true", help="小尺寸专用：线更粗、颜色更深")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parents[1]
    name = "icon-compact.svg" if args.compact else "icon.svg"
    out = root / "docs" / name
    out.write_text(build(args.compact), encoding="utf-8")
    print("wrote", out)
