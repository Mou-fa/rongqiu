# 数据流向：什么会离开这台机器

> **规范性版本见 [DATA-CONSTITUTION.md](DATA-CONSTITUTION.md)。本文件只描述现状数据流。**

这是隐私项目，所以把「哪些数据会出机器」写清楚，不靠口头承诺。

## 一、绒球代码自己会连的外部服务

| 服务 | 地址 | 什么时候连 | 传出去什么 |
|---|---|---|---|
| DeepSeek API | api.deepseek.com | 每次判断 | **用户的问题原文、检索到的网页正文** |
| Tavily | api.tavily.com/search | 每次判断 | **检索词**（从用户问题里的核心名词展开） |
| 博查 | api.bochaai.com | 仅当 provider=bocha | 同上 |
| Serper | google.serper.dev | 仅当 provider=serper | 同上 |
| 搜狗 | www.sogou.com/web | 仅当 provider=sogou | 同上（已废弃，会被限流） |

**默认配置下只有两个出站：DeepSeek + Tavily。**

## 二、不会离开的东西

- 前端**没有任何外部请求**。页面只连 127.0.0.1:8780，没有 CDN、没有统计、没有字体外链。
- 判断记录存在本地 `data/journal.jsonl`。
- 三元组索引存在本地 `data/triple_index.json`。
- 搜索缓存存在本地 `data/search_cache/`。
- **危机触发时**，会在本地 `data/crisis/` 写一份完整快照：
  - 用户此刻提供的全部请求数据（问题、自述、勾选、回答、坐标等）；
  - 本地时间、UTC、时区、UTC 偏移；
  - 当时的 `journal.jsonl` 副本；
  - 只写本机，不上传、不进入校准、不参与统计；`data/` 已被 git 忽略。
  - 每个事件带 SHA-256 清单；`scripts/export_crisis.py` 可在本地导出可核验副本。
  - **不会自动交给警方或家属**；第三方访问边界见 [CRISIS-RECORD.md](CRISIS-RECORD.md)。
  - 这是用户明确要求保留的内容型本地记录，也是当前唯一不遵守「只留形状」的本地数据；删除时直接删 `data/crisis/` 即可，加密要等 B1/B3 底座层。
- **代码和文档有 git 远程**（github.com/Mou-fa/rongqiu），但 `data/`、`configs/llm.yaml`、`configs/search.yaml` 被 git 忽略，不会随代码推送。

## 三、如果要做成「完全离线」

把 `configs/llm.yaml` 指向本地模型（Ollama / vLLM 等任何 OpenAI 兼容接口），
把 `configs/search.yaml` 的 provider 改成 `local`。

这样绒球会完全离线，不出机器。代价是：
- 本地模型质量决定判断质量
- `local` provider 只读 `data/local_corpus.json`（39 条），第一接触面会很少

## 四、密钥管理

- `configs/search.yaml`、`configs/llm.yaml` 都已加入 `.gitignore`
- `configs/search.yaml` 曾在一小时内被 git 跟踪过（commit bbbcaa4），已从跟踪中移除；
  但 git 历史里仍然留着一份，且仓库已有远程。**如果这个 key 还没作废，先去 Tavily 后台作废并重新生成。**
  作废之后历史里那份就是废纸；要彻底清掉历史需要改写提交并 force push。

## 五、这个文件管不到的部分

**我们这次对话本身经过了模型服务。** 这是任何在线 AI 都无法避免的，
包括我。如果绒球的内容需要绝对不外传，那么：

- 不要在任何在线 AI 里描述它的实现细节
- 本地代码和文档不经由对话外发（这台机器上的文件本身是安全的）
- 需要 AI 协助时，只提供抽象到无法还原的最小片段