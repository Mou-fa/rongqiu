# 绒球 · Rongqiu

> ## 状态：可运行原型（v0.2）
>
> **主链路已跑通；第三层第一版已落地（按原核挑面 / 半知 / 翻转阈值）；问句库 54 条。**
> **但校准数据 0 条、真实用户 0 个——它还没有被真实使用验证过，不是成品。**
>
> 剩下的工作见文末「还没做完的」。如果你只是路过，看一眼就行。

---

> **不告诉你该怎么做，只让你看清自己在拿什么做决定。**

一个个人决策校准系统。你带着一个正在犹豫的问题进来，
它把问题拆成结构，给出一个参考倾向和置信度，记录归档，
到期回来问你「那件事最后发生了吗」，然后形成你自己的校准曲线。

**它不给建议，不预测未来，不替你决定。**

---

## 它做什么

```
输入：一句自然语言的犹豫（文字；未来语音）
  ↓
拆主谓宾 → 找第一接触面 → 按原核挑面（8–12 条）→ 二元判向 → 计数
  ↓
输出：N 个事实面 + 1 个半知 + 1 个未知
      可确定 ≤ 80% 的参考倾向
  ↓
沉淀：判断归档 → 到期回收 → 个人校准曲线
```

## 四条设计原则

| 原则 | 含义 |
|---|---|
| **他人观点零权重** | 只有你自己的陈述和真实发生的交换算事实 |
| **事实二元** | 支持或反对，中性只存在于半知和未知 |
| **80% 封顶** | N 再多也超不过 80%，那 20% 永远拿不到 |
| **不引导** | 只给结构，不给方向建议 |

---

## 快速开始

```powershell
# 0. 需要 Python 3.10+
python --version

# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置模型（必填，否则只能跑本地语料）
copy configs\llm.example.yaml configs\llm.yaml
# 填入你的 API key（任何兼容 OpenAI 接口的服务都行）

# 3. 配置搜索（可选）
copy configs\search.example.yaml configs\search.yaml
# 填入你的 Tavily key

# 3. 启动
.\scripts\serve.ps1
```

打开 `http://127.0.0.1:8780`。
手机同网段访问：`http://<你的局域网IP>:8780`（见 [docs/LAN.md](docs/LAN.md)）

---

## 桌面版（Windows）

不想碰命令行，可以打包成独立窗口程序：双击即用。

```powershell
# 需要先装打包工具
pip install pyinstaller

# 构建（第一次会自动下载 WebView2 SDK）
.\scripts\build_app.ps1

# 产物（整个文件夹一起用）
dist\Rongqiu\Rongqiu.exe
```

- 窗口是**内嵌 WebView2**：`RongqiuWindow.exe`（由 `tools\RongqiuWindow.cs` 编译），不依赖外部浏览器窗口；
- 数据默认在 `%APPDATA%\Rongqiu`；不可写时退回程序旁的 `RongqiuData\`；
- 首次打开去「设置」页填模型 API Key（留空不覆盖已保存的值）；
- 当前是 API key 模式；本地模型（内容不出设备）放在 v0.4；
- 未签名，Windows 可能弹 SmartScreen 提示，选「仍要运行」。

---

## 目录结构

```
rongqiu/
  rongqiu/              核心库
    nucleus.py          主谓宾抽取
    extract.py          背景事实抽取
    indexer.py          三元组索引与检索
    questions.py        问句库、按原核挑面
    input_layer.py      输入层：框架/面/gaps/固定问句
    surfaces.py         面配置与 probe -> 面映射（按面校准用）
    review.py           方向判定（二元）
    node.py             811 结构计算
    journal.py          归档、回收、校准
    environment.py      环境讯息（只展示不计面）
    search.py           多源检索
  app/                  Web 应用
    server.py           FastAPI
    static/             前端
  launcher.py           桌面版入口（启动服务 + 打开内嵌窗口）
  tools/RongqiuWindow.cs 内嵌窗口宿主（C# + WebView2）
  scripts/build_app.ps1 打包脚本（PyInstaller + csc）
  configs/
    questions.yaml      问句库（59 条）
    taxonomy.yaml       面类别词表（16 类，可多选）
    search.yaml         搜索配置（不入库）
    surfaces.jsonl      面与固定问句的映射（离线输入层用）
    lexicon.jsonl       离线触发词表（实体 / 状态 / 正则）
  data/                 语料、索引、判断日志（不入库）
  scripts/              工具脚本
  tests/                205 个测试
  docs/                 全部文档
```

---

## 文档

| 文档 | 内容 |
|---|---|
| [**HANDOFF.md**](docs/HANDOFF.md) | **交接文档**：新会话先读这个。现状 / 七条原则 / 陷阱 / 下一步 |
| [**PROPOSAL.md**](docs/PROPOSAL.md) | **立项书**：问题、主张、架构、里程碑、指标、风险 |
| [**REDLINES.md**](docs/REDLINES.md) | **红线报告**：五条不可逾越条款 + 三条算法不变量 |
| [**DATA-CONSTITUTION.md**](docs/DATA-CONSTITUTION.md) | **数据宪法**：留形状不留内容；司法/政府请求怎么答；全球化数据架构 |
| [**CAPABILITIES.md**](docs/CAPABILITIES.md) | **能力说明书**：13 项能力的判据、边界、与红线的关系 |
| [COMPETITORS.md](docs/COMPETITORS.md) | 竞品跟踪：国内外理念相近的产品、差异与威胁模型 |
| [INPUT-LAYER.md](docs/INPUT-LAYER.md) | **输入层**：框架判定、面选择、固定问句、离线/在线 |
| [CONCEPT-EVOLUTION.md](docs/CONCEPT-EVOLUTION.md) | **概念演化**：三条不变量 / 已发生的扩展 / 待验证假设 |
| [LAYER-MAP.md](docs/LAYER-MAP.md) | **层地图**：纵向流水线 + 11 个底座层 + 层间契约 + 优先级 |
| [THEORY.md](docs/THEORY.md) | 理论：811、第一接触面、二元对立、分形 |
| [FOUNDATIONS.md](docs/FOUNDATIONS.md) | 理论支撑：马尔可夫毯、Ashby、校准研究等 |
| [VOICE.md](docs/VOICE.md) | 语音三层与第三层设计（研究线） |
| [AUDIT.md](docs/AUDIT.md) | 自查记录 |
| [PRIVACY.md](docs/PRIVACY.md) | 数据与隐私 |
| [LAN.md](docs/LAN.md) | 手机访问与网络排查 |
| [ICON.md](docs/ICON.md) | 图标来源与生成方式 |

---

## 当前状态

| 项 | 状态 |
|---|---|
| 版本 | M0 + M1 第一版 |
| 判向准确率 | 96%（25 题自建评测集） |
| 测试 | 211 个，全绿 |
| 问句库 | 59 条（16 类面，mk + domains） |
| 本地语料 | 39 条 |
| 三元组索引 | 789 条 |
| 判断日志 | 204 条（0 条已回收） |
| 手机访问 | ✅ 同网段可用 |

### 下一步

- [x] **M1（第一版）**：按原核挑面 / 未答面进半知 / 翻转阈值
- [x] **M2**：跨决定共同根因、校准缺口预警
- [ ] **M3**：校准闭环跑真实数据、公开基准库
- [ ] **M4**：移动端、语音输入（ASR + 确认）、本地优先、声景音频、沉默的面、框架效应检测
- [ ] **语音第三层**：声音 → 状态 → 结构（研究线，见 [docs/VOICE.md](docs/VOICE.md)）
- [ ] **M5**：组织版、机构版、教育版

六个潜藏能力见 [PROPOSAL.md 第六章](docs/PROPOSAL.md)，
日活层（讯息 + 声景）见 [第九章](docs/PROPOSAL.md)。

---

## 测试

```powershell
python -m pytest tests -q
```

## 评测

```powershell
python scripts/eval_direction.py
```

---

## 参与贡献

**技术开放，理念不开放。**

欢迎 bug 修复、测试、文档、翻译、问句候选、隐私增强；
不接受任何改变核心思想与红线的改动——那些要走 [REDLINES.md](docs/REDLINES.md) 第六部分的程序，不是 PR。

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 许可证

本项目使用 **GNU AGPL-3.0**。

简单说：**你可以自由使用、修改、分发；但如果你把它改成在线服务，
你的修改也必须同样开源。**

这条协议是有意选的——绒球的核心是「不引导」，
如果允许闭源改写，任何人都能加一个推荐算法再拿去做成商业产品，
那这些红线就白写了。

---

## 还没做完的

诚实列一下，免得有人以为它已经能用了。

| # | 缺什么 | 状态 | 为什么重要 |
|---|---|---|---|
| 1 | **问句库 54 条** | 已导入（2026-10-20） | 但还没有咨询团队正式复核；挑面质量待真实回收验证 |
| 2 | **第三层完善** | 第一版已落地 | 系统自主挑面 / 半知 / 翻转阈值已通；还缺「还缺什么」清单和挑面校准 |
| 3 | **校准数据 0 条** | 机器就绪 | 一条判断都还没回收过，校准曲线画不出来 |
| 4 | **真实用户 0 个** | — | 上面几件的共同原因，**现在是唯一真瓶颈** |
| 5 | 声景库只有策展位 | 音频未接入 | 见 [PROPOSAL.md 第九章](docs/PROPOSAL.md) |
| 6 | 语音输入 | 只有 stub | 设计见 [docs/VOICE.md](docs/VOICE.md) |
| 7 | 语音第三层（状态→结构） | 研究线，未开始 | 同上；不阻塞当前主链路 |
| 8 | 移动端打磨 | 可用，但粗糙 | — |

**其中最要紧的是 3 和 4。**
**没有真实回收数据，绒球还是一个「结构计算器」，还不是「镜子」。**

---

## 底线

**这个项目最值钱的不是代码，是它守不守得住 [REDLINES.md](docs/REDLINES.md)。**

**代码可以重写，红线丢了就长不回来。**