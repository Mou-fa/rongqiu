# 绒球图标

![icon](icon-512.png)

## 回到蒲公英

最初的灵感就是蒲公英。中间试过五版「毛球 + 旋」，全部被否——
最后一版被指出**像病毒**。

病毒感的根源不是配色，是结构：**圆形实心体 + 四周放射状的刺**。
只要这个结构在，画的是毛、是刺、是光，读起来都是病毒。

蒲公英不会像病毒，因为它有三样病毒永远没有的东西：

| | 病毒 | 蒲公英 |
|---|---|---|
| 中心 | 实心球 | **空的** |
| 线端 | 疙瘩 | **一撮小伞（冠毛）** |
| 命运 | 不动 | **种子会飞走** |

第三条是蒲公英唯一的签名。而且它正好承载了理论：

> **球上有一个缺口，一颗种子已经飞走了。**
> **那颗飞走的，就是 811 里那 20% 永远抓不到的未知。**
> **留下来的每一根，才是你能数的第一接触面。**

## 元素

| 元素 | 含义 |
|---|---|
| 种子球 | 绒球本身 |
| 每一根带冠毛的丝 | 一个第一接触面 |
| 右上角的缺口 | 抓不到的那一份 |
| 飞走的绿色种子 | 那 20% 的未知，已经走了 |
| 中心一点绿 | 原核 |

## 两套尺寸

细密的绒毛在 32px 下会糊成一片，所以做了两个版本：

| 尺寸 | 母版 | 处理 |
|---|---|---|
| 512 / 256 / 128 | `icon.svg` | 标准版，绒毛细密 |
| 64 / 32 / 16 + favicon | `icon-compact.svg` | 简化版：线粗 1.9 倍、颜色加深、种子减半 |

这是图标设计的常规做法——**小尺寸不是简单缩放，是另画一版。**

## 文件

| 文件 | 用途 |
|---|---|
| `icon.svg` | 标准版母版 |
| `icon-compact.svg` | 小尺寸母版 |
| `icon-{512,256,128,64,32,16}.png` | 各尺寸成品 |
| `favicon.ico` | 16/32/48 三档 |
| `../app/static/icon.svg` | 应用内头部 logo |
| `../app/static/favicon.ico` | 浏览器标签页 |

## 重新生成

```bash
python scripts/make_icon_svg.py              # 标准版 → docs/icon.svg
python scripts/make_icon_svg.py --compact    # 简化版 → docs/icon-compact.svg
python scripts/make_icon_preview.py icon.svg
python scripts/make_icon_preview.py icon-compact.svg
# 用 Edge 分别把两个 _preview_*.html 截成 512px 母版
python scripts/make_icon.py                  # 生成全套尺寸和 favicon
```