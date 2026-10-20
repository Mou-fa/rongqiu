# 绒球 · 竞品跟踪

| 项 | 内容 |
|---|---|
| **用途** | 市场扫描、差异化定位、威胁预警 |
| **扫描日期** | 2026-10-21 |
| **方法** | 网页搜索 + App Store 元数据（自述）+ GitHub / Product Hunt；未做付费实测、未做用户访谈 |
| **覆盖** | 英文市场为主，中国 iOS 部分覆盖；**安卓、微信小程序、私域产品未穷尽** |
| **更新** | 每季度一次，或大版本发布后 |
| **结论** | **有相似，且比预想多；但没有完整同款。** |

---

## 0. 一页结论

1. **需求被验证**：国内外都有一小簇独立开发者在做「决策日记 / 校准」产品，时间集中在 2025–2026；品类在形成期，**没有主导者**。
2. **最接近的不是同类 App，而是「嵌进 AI 助手的结构层」**——Boundary MCP 的口号几乎和绒球同源。它占的是入口。
3. **同类 App 都停在「自由文本日志」**：没有谁把判断拆成 N / 面 / 半知 / 未知，也没有谁做问句探针。
4. **没有人同时具备**：结构化判断 + 探针库 + 校准闭环 + 内容不出设备 + 人生档案 + 公开红线。
5. **绒球的差异叙事**：**他们在你决策的那一刻帮你分析；绒球在决策之后帮你校准，并用一生积累。** 一个是顾问，一个是镜子。

---

## 1. 最接近的产品

| 产品 | 平台 | 理念重合点 | 与绒球的差别 | 威胁 |
|---|---|---|---|---|
| [**Boundary MCP**](https://github.com/wh131462/mcp-boundary) | 中国 / 开源 MCP 插件 | 口号几乎同款：「不告诉你该怎么做，只帮你看清你在赌什么」；原则「不做决定 / 不给答案 / 不预测 / 不迎合」；把问题翻成结构、变量、约束、不确定性 | 是给 AI 助手用的**决策结构分析器**（Claude Code / Desktop 插件）；输出策略空间与概率分布（已接近建议）；**无日志、无回收、无校准、无问句库**；仓库小且停更（1 star，2026-01 建） | **中高**（理念最像 + 入口层） |
| [**决断 Verdict**](https://apps.apple.com/us/app/verdict-decision-journal/id6794278297) | 中国开发者 / iOS | **价值观最接近**：本地、无账号、无服务器、无 AI、无统计 SDK、无打卡徽章、不做召回式推送；校准图、分领域后悔率、原则库、1/3/6/12 个月周年回顾、一次买断 | 自由文本决策日志（pre-mortem → 复盘 → 原则）；**没有结构化判断**（N/面/半知/未知），没有问句探针，没有「他人观点零权重」的算法约束，没有七年/人生阶段 | 中 |
| [**谋断 Afterwise**](https://apps.apple.com/us/app/afterwise-decision-journal/id6768229252) | 中国开发者 / iOS | 明说「It does not tell you what to choose」；记录选项/选择/理由/假设/最大风险/回看日期 | 纯文本日志，无结构探针、无校准曲线、无群体校准 | 中低 |
| [**Reckon**](https://apps.apple.com/us/app/reckon-decision-journal/id6762766246) | 海外 / iOS | **机制最接近「七年回看」**：置信度 → 到期揭晓 → 30–60 天后再问「would you make this call again?」；长期看校准 | 自由文本单条记录；无 811 结构、无问句库、无人生档案 | 中 |
| [**Foresee 预测追踪器**](https://apps.apple.com/us/app/prediction-tracker-journal/id6779216934) | 海外 / iOS | **校准机制最接近**：Brier 分数、校准曲线、分类准确度；本地、无账号、无广告、无分析 SDK（自述） | 做「预测」不做「个人决定」；无结构探针、无回看/人生线 | 中低 |
| [**Brier**](https://peerlist.io/varunthkkr3/project/brier) | 海外 / Web | 「给你的判断打分的决策日记」：置信度 → 到期邮件提醒 → 校准曲线；免注册 demo | 轻量工具；无结构、无探针、无长周期 | 低 |
| [**Sharper**](https://apps.apple.com/us/app/sharper-decision-diary/id6471383280) | 海外 / iOS | 「给未来自己发消息」的时间胶囊；全设备本地 | 时间胶囊，不是校准系统 | 低 |
| [**Beslisflow**](https://www.producthunt.com/products/beslisflow) | 海外 / Product Hunt | 标语几乎同款：**「No coaching. No advice. Just clarity on your decision.」** | 详情待跟踪（页面被反爬）；看起来是轻量决策澄清工具 | 待观察 |

---

## 2. 相邻 / 方向相反的产品

**AI 决策 / 日记（方向是「帮你思考」，不是「不引导」）：**

- [Socratica](https://apps.apple.com/us/app/socratica-stoic-ai-journal/id6782961673)：苏格拉底式 AI 日记 + Decision Lab，先问更好的问题，但会给哲学家式反思与引导；
- [Decidra](https://apps.apple.com/us/app/decidra/id6754671866)：AI 决策助手，自动提问 + 信号/噪音 + 置信度 + 可执行任务——典型建议型；
- [Pausa](https://apps.apple.com/us/app/pausa-honest-journaling-coach/id6502012412)：AI 教练式日记，直接指出你的模式——反馈/教练型。

**校准 / 预测训练（概念源流，不是个人决策产品）：**

- [Farnam Street 的 Decision Journal](https://fs.blog/decision-journal/)：决策日志经典模板（Kahneman、Annie Duke 传统）；
- [Clearer Thinking 预测训练](https://www.clearerthinking.org/post/2019/10/16/practice-making-accurate-predictions-with-our-new-tool)、[Good Judgment](https://goodjudgment.com/)、[Metaculus](https://www.metaculus.com/)、[Fatebook](https://blog.beeminder.com/fatebook/)：校准/预测平台——证明「校准」是真需求，但都停在预测，不碰个人决定与隐私架构。

---

## 3. 绒球真正不一样的地方

| # | 差异 | 说明 |
|---|---|---|
| 1 | **结构 vs 文本** | 它们记「你写了什么」；绒球拆「你拿什么做决定」——N / 支持 / 反对 / 半知 / 未知 / 80% 封顶 |
| 2 | **探针 vs 日志** | 它们不主动探测你没想到的面；绒球有问句库（54 条 → 挑面） |
| 3 | **红线 vs 建议** | 它们多数仍给策略、分布、教练反馈；绒球把「不引导 / 他人观点零权重 / 环境只展示」写成算法约束 |
| 4 | **闭环 vs 单次** | 它们最多做到 30–60 天二次回看；绒球做 1/3/7 年 + 人生阶段 + 人生底片 |
| 5 | **数据宪法 vs 隐私声明** | Verdict / Foresee 的「本地、无账号」已经很接近，但没有公开架构契约、AGPL 可审计、内容不出设备的硬约束 |

---

## 4. 威胁模型与观察指标

**最该盯的三类：**

1. **Boundary MCP 这类「AI 里的结构层」**：如果它加上持久化、回看、校准，就从「思路同源」变成直接竞品；如果它进入主流 AI 客户端的默认工具集，就占住入口。**观察**：star 增长、MCP 目录收录、是否加日志/校准、是否商业化。
2. **Verdict / Reckon 这类「记录 + 校准」工具**：如果它们加上结构化判断（N/面/半知）或问句提示，会非常接近。**观察**：版本更新、是否引入「问题清单」。
3. **大厂 AI 助手加「决策模式」**：一旦主流助手内置「不装确定 + 校准」功能，就是形态级威胁。**观察**：OpenAI / Anthropic / Apple / 国内助手的决策类功能。

**观察渠道：** App Store 搜索词（decision journal / decision diary / calibration / Brier / prediction tracker / 决策日记 / 决策日志 / 复盘 / 校准）、Product Hunt、GitHub（decision journal / MCP decision）、小红书/即刻/少数派。

---

## 5. 应对策略

- **不拼功能多、不拼 AI 聪明**：拼结构深度 + 纵向数据 + 信任架构 + 本地化 + 人生档案；
- **把公开文档当信任资产**：[REDLINES.md](REDLINES.md)、[DATA-CONSTITUTION.md](DATA-CONSTITUTION.md)、透明度报告——竞品可以抄功能，抄不了「可审计的克制」；
- **入口层可以合作而非对抗**：未来可考虑以本地模型 + MCP/插件形式接入其他 AI（前提：内容不出设备、数据宪法不破），但**不是现在的优先级**；
- **每季度复查本表**，新发现直接追加。

---

## 6. 本次扫描的局限

- 未做付费实测、未做用户访谈，功能描述主要来自产品自述；
- 安卓市场、微信小程序、私域社群产品未穷尽；
- 部分产品（如 Beslisflow）页面反爬，信息不完整；
- 榜单/下载量未核实——「没有主导者」是定性判断，不是数据结论。

---

## 7. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-21 | v0.1 | 首次扫描：8 个最近似产品 + 相邻品类 + 威胁模型 |
