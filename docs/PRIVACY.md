# 数据流向：什么会离开这台机器

这是密码项目，所以把「哪些数据会出机器」写清楚，不靠口头承诺。

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
- **没有 git 远程仓库**，代码和文档不会自动推送到任何地方。

## 三、如果要做成「完全离线」

把 `configs/llm.yaml` 指向本地模型（Ollama / vLLM 等任何 OpenAI 兼容接口），
把 `configs/search.yaml` 的 provider 改成 `local`。

这样绒球会完全离线，不出机器。代价是：
- 本地模型质量决定判断质量
- `local` provider 只读 `data/local_corpus.json`（39 条），第一接触面会很少

## 四、密钥管理

- `configs/search.yaml`、`configs/llm.yaml` 都已加入 `.gitignore`
- `configs/search.yaml` 曾在一小时内被 git 跟踪过（commit bbbcaa4），
  已从跟踪中移除。**因为仓库没有远程，它没有通过 git 离开这台机器。**
- 但历史里仍然留着一份。**建议直接去 Tavily 后台把这个 key 作废、重新生成一个。**
  这是最省事、最彻底的做法——作废之后历史里那份就是废纸。

## 五、这个文件管不到的部分

**我们这次对话本身经过了模型服务。** 这是任何在线 AI 都无法避免的，
包括我。如果绒球的内容需要绝对不外传，那么：

- 不要在任何在线 AI 里描述它的实现细节
- 本地代码和文档不经由对话外发（这台机器上的文件本身是安全的）
- 需要 AI 协助时，只提供抽象到无法还原的最小片段