# 输入层（Input Layer）

> 定位：绒球的第一接触面在「一句话」上执行的地方。
> 状态：已进产品（2026-10-22），在线 / 离线共用同一套面选择逻辑。

---

## 它解决什么

旧路径是：用户文本 → 原核解析（LLM）→ 搜索 → 抽事实 → 811。
问题不是它不能跑，而是：

- 没有框架判定：求解、倾诉、危机走同一条路；
- 问句由模型自由挑：不稳定、不可审计、不可复现；
- 没有面的概念：事实从哪来、缺哪些面，全靠即兴。

输入层把它改成：

    text
     → crisis（确定性，最高优先级）
     → F 交互框架（decision / vent / crisis / chat）
     → surface 命中 + gaps（缺哪些面）
     → 固定问句（probes）
     → 用户 yes/no
     → 事实 → 811

关键点：**问句的方向由用户点击直接决定，不经过模型**；
LLM 只负责原核解析与搜索，不负责挑面。

---

## 组件

| 文件 | 作用 |
|---|---|
| `rongqiu/input_layer.py` | 框架判定、binary 兜底、lexicon 匹配、按面挑问句 |
| `configs/surfaces.jsonl` | 面 → 固定问句的映射（当前 13 个面） |
| `configs/lexicon.jsonl` | 触发词表（实体 / 状态 / 动作 / 正则） |
| `configs/questions.yaml` | 固定问句库（当前 59 条） |
| `rongqiu/questions.py` | `answers_to_facts`：yes/no → 事实方向 |

---

## CIR v1 契约

`input_layer.compile(question)` 的输出是下游唯一入口：

| 字段 | 含义 |
|---|---|
| `ir_version` | 当前 `cir_input_v1`；改接口必须升版本 |
| `frame` | decision / vent / crisis / chat |
| `binary` | 从原句抽出的二元问题对象 |
| `surfaces` | 命中的面类别，每个带 name / confidence / evidence（pattern、span） |
| `gaps` | 该补的面 |
| `question_ids` | 本次挑出的固定问句 |
| `diagnostics` | 规则名、surface 数、lexicon 数 |
| `ir_hash` | 确定性哈希，不含时间；同输入同输出 |

下游（分析/计数/输出）只能吃这个结构，不能自己重新解释原句。
改字段、改语义必须改 `ir_version`。

## 在线 / 离线

**在线**（有 LLM / 搜索）：
- LLM 解析原核、搜索候选；
- 但挑问句仍然走 `input_layer.select_questions`（按面 + 缺口）；
- 用户回答 → `answers_to_facts` → 811。

**离线**（无 LLM / 无网络）：
- `input_layer.parse` 用确定性规则取 binary 与框架；
- 跳过搜索；
- 同样按面挑问句，用户回答即可完成一次 811 判断。

两条路的问句选择逻辑是同一套，避免「在线一个样、离线一个样」。

---

## 硬规则

1. **危机优先**：自伤/自杀/绝望信号确定性短路，不进入结构；
2. **环境不计面**：天气、时间、地区只展示，不变成判断依据；
3. **不给建议**：输入层只输出面、缺口、问句，不输出方向；
4. **不排序**：问句顺序只用于轮转覆盖，不展示「哪个更重要」；
5. **允许少问**：非核心域不补财务缺口；没有命中面时只问通用 probe；
6. **他人观点零权重**：固定问句问的是用户自己的行为/处境，不是别人的看法。

---

## 覆盖审计工具

    python scripts/audit_input_layer.py

只读 `data/journal.jsonl`，统计：框架分布、面命中率、没命中面的样本、各面出现次数，
输出 `data/input_layer_audit.json`。用它决定下一步补哪个面，而不是凭感觉加词。

## 当前边界

- lexicon / surface / probe 覆盖仍偏「钱、职业、关系、健康」；户外安全刚补了 5 条；
- 离线 binary 是规则抽取，复杂句会退化；
- 还没有语音输入；
- 问句库是护城河：新增 probe 必须人工审，不自动生成。

---

## 按面校准

用户每回答一条 probe，服务端会把它归到所属面，写入 journal 的 `surface_answers`。
回收后 `journal.stats()` 输出每个面的：

- `facts`：这个面被回答过多少条事实；
- `decisions`：涉及多少个决策；
- `hits` / `hit_rate`：方向与最终结果同向的比例；
- `brier`：按「support=会发生 / oppose=不会发生」算的 Brier。

旧记录没有 `surface_answers` 的，从「主动询问」事实的 scene 反推面。
少于 5 条事实的面在校准页只显示样本，不显示命中率。

## 与 811 / journal 的关系

- 用户回答固定问句 → 事实 → `node.judge` → 811；
- journal 用 `decision_id` 去重：同一决策重判只追加 revision；
- 回收页只展示每个决策的最新 revision；
- 未满 24 小时不会标成「现在可以回收」。

---

## 设计原则

输入层的目标不是「更聪明」，是**更稳定、更可解释、更少引导**。
如果一个问题需要模型猜面，那说明面库还不够；先补库，不要先补 prompt。
