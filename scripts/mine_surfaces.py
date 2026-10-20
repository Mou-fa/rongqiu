"""离线矿工：从公开网页文本里，为一个决策框架生成「面的候选分布」。

定位（重要）：
- 这是**开发期**工具，不是运行时链路的组件。
- 输入是公开的决策框架（如「聚餐」），不是用户的问题；
  因此不会有任何用户输入离开这台机器。
- 输出是给咨询团队审定的**候选**：镜子候选 / 面清单 / 问句草稿。
- 算法**不生成**用户的 N。N 只能由用户认领或回答产生（红线二、不变量三）。

用法：
    python scripts/mine_surfaces.py
    python scripts/mine_surfaces.py --frames 聚餐,换工作
    python scripts/mine_surfaces.py --max-texts 24 --no-search-cache

产物（data/ 已在 .gitignore 里）：
    data/miner/<frame>.json       完整中间数据
    data/miner/report.md          人看的报告
    data/miner/extract_cache.json 抽取缓存（按文本哈希，重跑不重复花钱）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rongqiu import llm, questions as qbank, search  # noqa: E402

OUT_DIR = ROOT / "data" / "miner"
CACHE_PATH = OUT_DIR / "extract_cache.json"
# 提示词或抽取规则一改，缓存就要失效；否则重跑会一直用旧结果。
CACHE_VERSION = "v6"

# ---------------------------------------------------------------------------
# 面类别词表：从 configs/taxonomy.yaml 读（和问句库共用同一份）
#
#   mk      —— 马尔可夫毯关系：因 / 果 / 共同原因（必填、单选）
#   domains —— 面类别：15 类细粒度，**可多选**（展示用，不进 811）
# ---------------------------------------------------------------------------
MKS = qbank.MK_VALUES
DOMAINS = tuple(qbank.domain_names())
DOMAIN_LINES = "\n".join(
    f"    {i + 1}. {d['name']}：{d['definition']}"
    for i, d in enumerate(qbank.load_taxonomy()["domains"]))

# ---------------------------------------------------------------------------
# 三个种子框架。查询刻意按「马尔可夫毯三类 + QA 反演」铺开，
# 并用 site: 走经验型语料（问答 / 小组 / 笔记），不走 SEO 攻略。
# ---------------------------------------------------------------------------
FRAMES = [
    {
        "key": "聚餐",
        "binary": "我会去这次聚餐吗",
        "agent": "我", "event": "参加", "resource": "聚餐",
        "keywords": ["聚餐", "聚会", "饭局", "应酬"],
        "queries": [
            ("cause", "site:zhihu.com 不想去聚餐 为什么"),
            ("cause", "site:zhihu.com 拒绝聚餐 理由"),
            ("cause", "site:douban.com 聚餐 不想去"),
            ("effect", "site:zhihu.com 参加聚餐 之后 累"),
            ("effect", "site:zhihu.com 去了聚餐 后悔"),
            ("effect", "site:zhihu.com 聚餐 结束 感受"),
            ("common", "site:zhihu.com 聚餐 人情 压力"),
            ("common", "site:zhihu.com 同事聚餐 关系 尴尬"),
            ("common", "site:xiaohongshu.com 社恐 聚餐"),
            ("qa", "site:zhihu.com 该不该去聚餐"),
            ("qa", "site:zhihu.com 要不要参加聚餐"),
        ],
    },
    {
        "key": "换工作",
        "binary": "我会换工作吗",
        "agent": "我", "event": "更换", "resource": "工作",
        "keywords": ["换工作", "跳槽", "辞职", "工作"],
        "queries": [
            ("cause", "site:zhihu.com 想换工作 原因"),
            ("cause", "site:zhihu.com 换工作 犹豫"),
            ("cause", "site:douban.com 辞职 纠结"),
            ("effect", "site:zhihu.com 换了工作 后悔"),
            ("effect", "site:zhihu.com 跳槽 之后 感受"),
            ("effect", "site:zhihu.com 换工作 适应 新环境"),
            ("common", "site:zhihu.com 工作 内耗 想辞职"),
            ("common", "site:zhihu.com 职场 人际关系 换工作"),
            ("common", "site:zhihu.com 薪资 涨幅 跳槽"),
            ("qa", "site:zhihu.com 该不该换工作"),
            ("qa", "site:zhihu.com 要不要辞职"),
        ],
    },
    {
        "key": "报班",
        "binary": "我会报这个培训班吗",
        "agent": "我", "event": "报名", "resource": "培训班",
        "keywords": ["报班", "培训班", "课程", "培训"],
        "queries": [
            ("cause", "site:zhihu.com 要不要报培训班"),
            ("cause", "site:zhihu.com 报班 犹豫"),
            ("cause", "site:xiaohongshu.com 报班 值不值"),
            ("effect", "site:zhihu.com 报了培训班 有用吗"),
            ("effect", "site:zhihu.com 培训班 上完 感受"),
            ("effect", "site:zhihu.com 报班 后悔"),
            ("common", "site:zhihu.com 培训 焦虑 报班"),
            ("common", "site:zhihu.com 培训班 套路"),
            ("common", "site:zhihu.com 职场 技能 报班"),
            ("qa", "site:zhihu.com 该不该报培训班"),
            ("qa", "site:zhihu.com 报班 有用吗"),
        ],
    },
]

EXTRACT_SYSTEM = """你是「绒球」的离线矿工。输入是一段公开网页文本，输出其中提到的「做决定时的考虑」。

只收同时满足五条的内容：
1. 具体：能拆出「谁·在什么情况下·因为/将要/需要什么」；
2. 陈述：是陈述句，不是建议、评价、统计、疑问、感叹；
3. 直接：是这个决定的直接原因、直接结果、或共同原因，不是隔两跳的泛泛之谈；
4. 可认领：一个真实的人可能拿它来判断自己的情况；
5. 可回答：把这条改写成「你是不是……」，一个真实的人能明确回答是或否。
   泛泛的人生道理、心理规律、机构层面的解释，答不了，就不要。

一律丢掉：
- 攻略/建议（「建议你不要去」「最好提前走」）
- 观点/评价（「聚餐有助于社交」「培训质量很坑」「机构宣传是虚假的」）
- 统计（「80% 的人」）、疑问、感叹、广告、登录页、翻译页
- 通用人生规律（「自己做的决定事与愿违会更后悔」）
- 只对某个人某一次成立的细节（具体人名、具体数字、一次性事件经过）；
  抽象成同类说法，抽象不了就丢掉

每条考虑换成一句不超过 30 字的陈述句，保留原文里对判断有用的细节，去掉无关的人名和数字，不添加原文没有的信息。
一段文本最多输出 2 条，只留最具体的。

每条同时标注：
- mk：这条是决定的哪一类面。按顺序判：
  1. 说的是「做了之后会发生什么」→ effect（直接果：后果、感受、改变）
  2. 是「我这个人」的稳定背景吗（性格、和某人的关系模式、习惯、身份、长期期待、
     长期处境）→ common（共同原因）
  3. 其余 → cause（直接因：这次的具体触发或约束——这次谁邀请、这次的时间/地点/人员、
     这次的临时状态、这次要花的钱、这次要满足的条件）
  注意：通用事实、政策、行情、行业规律（「房贷利率下限」「手机价格高」）不是 common，
  除非它确实是这次的具体约束，否则算 cause。共同原因最容易被漏掉，但不要为了补它
  把所有「稳定的话」都塞进来。
- domains：这条考虑涉及的面类别，**可多选（1–3 个）**，只能从下面这份词表里选：
{domain_list}
  一条考虑如果同时涉及钱和家庭，就两个都标；只涉及一个就标一个。
- dir：对给定二元问题，普通人看到这条通常倾向 support（会）还是 oppose（不会）；判不出就 none

示例一：
文本：「上次部门聚餐，我坐了两小时，全程插不上话，回家路上就觉得特别累。」
输出：{"items":[{"idx":1,"considerations":[{"text":"聚餐时插不上话，回家路上特别累","mk":"effect","domains":["心理感受","健康风险"],"dir":"oppose"}]}]}

示例二：
文本：「建议你直接说有事，别硬着头皮去。」
输出：{"items":[{"idx":1,"considerations":[]}]}

示例三：
文本：「参加聚会有助于维系人际关系。」
输出：{"items":[{"idx":1,"considerations":[]}]}

示例四：
文本：「我之所以不想去，是因为这次是老同事的局，去了一定会被问工资。」
输出：{"items":[{"idx":1,"considerations":[{"text":"去了会被同事问工资","mk":"cause","domains":["人际压力"],"dir":"oppose"}]}]}

示例五：
文本：「研究发现，人对自己的决定往往会产生事后的后悔。」
输出：{"items":[{"idx":1,"considerations":[]}]}

示例六：
文本：「我和老张关系一般，他的局我本来都不想去，但这次他专门叫我。」
输出：{"items":[{"idx":1,"considerations":[{"text":"和老张关系一般，本来不想去他的局","mk":"common","domains":["人际压力","关系维系"],"dir":"oppose"}]}]}

只输出 JSON：{"items":[{"idx":1,"considerations":[{"text":"","mk":"","domains":[],"dir":""}]}]}"""

# 词表在 import 时填进去；提示词本身保持可读
EXTRACT_SYSTEM_RENDERED = EXTRACT_SYSTEM.replace("{domain_list}", DOMAIN_LINES)

EXTRACT_PROMPT = """决定：{binary}（原核：{agent}·{event}·{resource}）

以下是 {n} 段公开网页文本。逐段输出其中的「考虑」；没有就输出空列表。

{blocks}

只输出 JSON。"""

CLUSTER_SYSTEM = """你是「绒球」的离线矿工。给你一批关于同一个决定的「考虑」（带编号）。
把表达同一件事的合并成一组——同义、换序、口语/书面都算同一组；不要为了合并而合并不同的事。
每组输出：
- label：不超过 8 字的类别名（例如「体力消耗」「人情压力」）
- members：编号列表
- representative：members 里最清楚、最具体的那一条原句（必须逐字来自列表）
只输出 JSON：{"groups":[{"label":"","members":[],"representative":""}]}"""

CLUSTER_PROMPT = """决定：{binary}

编号列表：
{lines}

只输出 JSON。"""

QUESTION_SYSTEM = """你是「绒球」的问句起草员。根据一条「考虑」起草一句固定询问。规则（用户从心理咨询师角度定）：

- 问行为，不问动机；问过去，不问现在；不问「为什么」
- 问「你做没做过 / 是不是这样」，不问「你怎么想 / 你觉不觉得」
- 封闭问句，只能用「是 / 否」回答（含「吗 / 是不是 / 有没有」）
- 不超过 25 字，口语，跨文化普适
- 不得出现：为什么、应该、最好、建议、值得、别、千万
- 用得上资源词就用（{resource}）
- polarity：答「是」对「我会做这件事吗」意味着什么——倾向会 = positive，倾向不会 = negative
  例：「你上一次参加完聚餐，第二天是不是很累？」答是会累 → 倾向不去 → negative
  例：「你手头有没有更好的工作机会？」答是有 → 倾向换工作 → positive

反面例子：❌「你为什么不高兴去聚餐」 ❌「你觉得聚餐值得去吗」 ❌「你最近是不是感到不满」
正面例子：✅「你上一次参加完聚餐，第二天是不是很累？」

只输出 JSON：{"items":[{"idx":1,"text":"","polarity":"positive|negative","why":"不超过20字：这句探到哪个面"}]}"""

QUESTION_PROMPT = """决定：{binary}（资源：{resource}）

{lines}

只输出 JSON。"""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _ckey(text: str) -> str:
    return _hash(CACHE_VERSION + "|" + text)


def _json_of(raw: str) -> dict:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    try:
        data = json.loads(t.strip())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _norm_title(src: str) -> str:
    s = src.split(":", 1)[-1].strip()
    return s[:40]


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                          encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. 检索：按框架的查询清单取公开文本
# ---------------------------------------------------------------------------
def collect(frame: dict, cfg, max_texts: int,
            use_cache: bool = True, workers: int = 3) -> tuple[list[dict], int]:
    seen_text: set[str] = set()
    seen_title: set[str] = set()
    by_query: list[list[dict]] = []
    raw_total = 0

    # 检索是网络 IO，并发跑；每个查询单独一个 bucket，后面轮转取样保证覆盖
    def _one(item):
        mk, query = item
        try:
            return mk, query, search.search(query, cfg, use_cache=use_cache)
        except Exception as exc:  # 单条查询失败不阻塞
            print(f"  [warn] search failed: {query} ({type(exc).__name__})")
            return mk, query, []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        fetched = list(pool.map(_one, frame["queries"]))

    for mk, query, results in fetched:
        raw_total += len(results)
        bucket: list[dict] = []
        for src, text in results:
            text = (text or "").strip()
            if len(text) < 40:
                continue
            title = _norm_title(src)
            key = _hash(text[:200])
            if key in seen_text or title in seen_title:
                continue
            # 相关性预筛：至少提到框架词，否则不值得花模型钱
            if not any(k in text for k in frame["keywords"]):
                continue
            seen_text.add(key)
            seen_title.add(title)
            bucket.append({"text": text[:900], "source": src,
                           "slot": mk, "query": query})
        by_query.append(bucket)

    # 轮转取样：保证每个查询、每个类别都有代表，而不是被第一个查询占满
    picked: list[dict] = []
    round_no = 0
    while len(picked) < max_texts:
        added = False
        for bucket in by_query:
            if round_no < len(bucket):
                picked.append(bucket[round_no])
                added = True
                if len(picked) >= max_texts:
                    break
        if not added:
            break
        round_no += 1
    return picked, raw_total


# ---------------------------------------------------------------------------
# 2. 抽取：文本 -> 考虑（带 mk / domain / dir）
# ---------------------------------------------------------------------------
def extract(frame: dict, texts: list[dict], cache: dict,
            batch_size: int = 6, workers: int = 4) -> list[dict]:
    cfg_llm = llm.load_config()
    if not llm.available(cfg_llm):
        raise SystemExit("llm 不可用：没有找到 key（configs/llm.yaml 或 ../quant-lab/configs/llm.yaml）")

    todo = [t for t in texts if _ckey(t["text"]) not in cache]
    chunks = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]

    def _one(chunk: list[dict]):
        blocks = "\n\n".join(f"【{i+1}】{t['text']}" for i, t in enumerate(chunk))
        prompt = EXTRACT_PROMPT.format(
            binary=frame["binary"], agent=frame["agent"],
            event=frame["event"], resource=frame["resource"],
            n=len(chunk), blocks=blocks)
        raw = llm.complete(prompt, system=EXTRACT_SYSTEM_RENDERED, cfg=cfg_llm)
        return chunk, _json_of(raw)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, c) for c in chunks]
        for fut in as_completed(futures):
            try:
                chunk, parsed = fut.result()
            except Exception as exc:
                print(f"  [warn] extract batch failed ({type(exc).__name__}), skip")
                continue
            for item in parsed.get("items", []) or []:
                try:
                    i = int(item.get("idx", 0)) - 1
                except (TypeError, ValueError):
                    continue
                if not (0 <= i < len(chunk)):
                    continue
                cons = []
                for c in item.get("considerations", []) or []:
                    text = str(c.get("text", "")).strip()
                    if not text or len(text) > 60:
                        continue
                    mk = str(c.get("mk", "")).strip().lower()
                    raw_domains = c.get("domains", c.get("domain", []))
                    if isinstance(raw_domains, str):
                        raw_domains = [raw_domains]
                    domains = [str(x).strip() for x in (raw_domains or [])
                               if str(x).strip() in DOMAINS][:3]
                    direction = str(c.get("dir", "")).strip().lower()
                    cons.append({
                        "text": text,
                        "mk": mk if mk in MKS else "cause",
                        "domains": domains or ["其他"],
                        "dir": direction if direction in ("support", "oppose") else "none",
                    })
                cache[_ckey(chunk[i]["text"])] = cons
            _save_cache(cache)
            print(f"  extract {len(cache)} texts cached")

    out: list[dict] = []
    for t in texts:
        for c in cache.get(_ckey(t["text"]), []):
            out.append({**c, "source": t["source"], "query": t["query"]})
    return out


# ---------------------------------------------------------------------------
# 3. 聚类：把换序/同义的考虑并成一组
# ---------------------------------------------------------------------------
def cluster(frame: dict, cons: list[dict]) -> list[dict]:
    cfg_llm = llm.load_config()
    # 同一句话只留一次（保留任意来源），避免聚类被重复项带偏
    uniq: dict[str, dict] = {}
    for c in cons:
        uniq.setdefault(c["text"], c)
    items = list(uniq.values())
    if not items:
        return []
    if len(items) > 80:
        items = items[:80]

    lines = "\n".join(f"{i}. {c['text']}" for i, c in enumerate(items))
    try:
        raw = llm.complete(
            CLUSTER_PROMPT.format(binary=frame["binary"], lines=lines),
            system=CLUSTER_SYSTEM, cfg=cfg_llm)
        groups_raw = _json_of(raw).get("groups", []) or []
    except Exception as exc:
        print(f"  [warn] cluster failed ({type(exc).__name__}); fallback to singletons")
        groups_raw = []

    groups: list[dict] = []
    used: set[int] = set()
    for g in groups_raw:
        members: list[int] = []
        for m in g.get("members", []) or []:
            try:
                i = int(m)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(items) and i not in used:
                members.append(i)
                used.add(i)
        if not members:
            continue
        group_cons = [items[i] for i in members]
        rep = str(g.get("representative", "")).strip()
        if rep not in {c["text"] for c in group_cons}:
            rep = max(group_cons, key=lambda c: len(c["text"]))["text"]
        srcs = {_norm_title(c["source"]) for c in group_cons}
        groups.append({
            "label": str(g.get("label", "")).strip()[:12] or "未命名",
            "representative": rep,
            "members": [c["text"] for c in group_cons],
            "mk": sorted({c["mk"] for c in group_cons}),
            "domains": sorted({d for c in group_cons for d in c["domains"]}),
            "dir": group_cons[0]["dir"],
            "source_count": len(srcs),
            "sources": sorted(srcs)[:3],
        })
    # 没被归组的，各自成组，不让它们消失
    for i, c in enumerate(items):
        if i in used:
            continue
        groups.append({
            "label": c["domains"][0], "representative": c["text"],
            "members": [c["text"]], "mk": [c["mk"]], "domains": list(c["domains"]),
            "dir": c["dir"], "source_count": 1,
            "sources": [_norm_title(c["source"])],
        })

    groups.sort(key=lambda g: (-g["source_count"], -len(g["members"]), g["label"]))
    return groups


# ---------------------------------------------------------------------------
# 4. 问句草稿：可认领的候选面 -> 固定询问（草案，需人审定）
# ---------------------------------------------------------------------------
ADVICE_WORDS = ("应该", "最好", "建议", "值得", "千万", "别")
FEELING_WORDS = ("觉得", "感到", "认为", "希望")


def lint_question(q: dict) -> list[str]:
    """问句草稿的自动门：过不了的地方标出来，交给人判断。"""
    t = q.get("text", "")
    problems: list[str] = []
    if not t.endswith(("？", "?")):
        problems.append("缺问号")
    if len(t) > 26:
        problems.append("超过 25 字")
    if "为什么" in t:
        problems.append("在问动机")
    for w in ADVICE_WORDS:
        if w in t:
            problems.append(f"含建议词「{w}」")
    for w in FEELING_WORDS:
        if w in t:
            problems.append(f"在问感受「{w}」")
    if "你" not in t:
        problems.append("不是问用户本人")
    if not any(x in t for x in ("吗", "是不是", "有没有", "是否", "会不会", "要不要")):
        problems.append("不像二元问句")
    if q.get("polarity") not in ("positive", "negative"):
        problems.append("polarity 非法")
    return problems


def draft_questions(frame: dict, groups: list[dict], top: int = 6) -> list[dict]:
    cfg_llm = llm.load_config()
    picks = [g for g in groups[:top] if g["representative"]]
    if not picks:
        return []
    lines = "\n".join(
        f"{i+1}. 面类别：{','.join(g['domains'])}；考虑：{g['representative']}"
        for i, g in enumerate(picks))
    try:
        raw = llm.complete(
            QUESTION_PROMPT.format(binary=frame["binary"],
                                   resource=frame["resource"], lines=lines),
            system=QUESTION_SYSTEM.replace("{resource}", frame["resource"]),
            cfg=cfg_llm)
        items = _json_of(raw).get("items", []) or []
    except Exception as exc:
        print(f"  [warn] question draft failed ({type(exc).__name__})")
        return []
    out = []
    for it in items:
        try:
            i = int(it.get("idx", 0)) - 1
        except (TypeError, ValueError):
            continue
        text = str(it.get("text", "")).strip()
        if not (0 <= i < len(picks)) or not text:
            continue
        item = {
            "text": text,
            "polarity": str(it.get("polarity", "positive")).strip(),
            "why": str(it.get("why", "")).strip(),
            "from": picks[i]["representative"],
            "domains": picks[i]["domains"],
        }
        item["lint"] = lint_question(item)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# 5. 报告
# ---------------------------------------------------------------------------
def render_frame(frame: dict, stats: dict, groups: list[dict],
                 questions: list[dict]) -> str:
    lines = [f"## {frame['key']}（{frame['binary']}）", ""]
    lines.append(f"- 查询 {stats['queries']} 条 · 原始结果 {stats['raw']} 条 · "
                 f"去重过滤后 {stats['texts']} 段文本 · 抽取 {stats['cons']} 条考虑 · "
                 f"聚类 {stats['groups']} 组")
    mk_cn = {"cause": "直接因", "effect": "直接果", "common": "共同原因"}
    mk_count: dict[str, int] = {}
    dom_count: dict[str, int] = {}
    for g in groups:
        for m in g["mk"]:
            mk_count[m] = mk_count.get(m, 0) + 1
        for d in g["domains"]:
            dom_count[d] = dom_count.get(d, 0) + 1
    lines.append("- 面的分布：" + " · ".join(
        f"{mk_cn.get(k, k)} {v} 组" for k, v in sorted(mk_count.items())))
    lines.append("- 面类别：" + " · ".join(
        f"{k} {v}" for k, v in sorted(dom_count.items(), key=lambda x: -x[1])))
    lines.append("")
    lines.append("### 镜子候选（用户点选才进 N，不点选只展示）")
    lines.append("")
    for i, g in enumerate(groups[:10], 1):
        mk = "/".join(mk_cn.get(m, m) for m in g["mk"])
        dom = "/".join(g["domains"])
        dir_cn = {"support": "倾向会", "oppose": "倾向不会", "none": "方向不定"}[g["dir"]]
        lines.append(f"{i}. **{g['label']}**（{mk} · {dom} · {dir_cn}）— "
                     f"{g['representative']}")
        lines.append(f"   - 来源 {g['source_count']} 篇独立文本："
                     + "；".join(g["sources"]))
    lines.append("")
    lines.append("### 面清单（不计数、不进 N；后续用来判断「哪些面还没被答到」）")
    lines.append("")
    by_dom: dict[str, list[dict]] = {}
    for g in groups:
        for d in g["domains"]:
            by_dom.setdefault(d, []).append(g)
    seen_rep: set[str] = set()
    for d in DOMAINS:
        if d not in by_dom:
            continue
        picks = [g for g in by_dom[d] if g["representative"] not in seen_rep][:3]
        if not picks:
            continue
        seen_rep.update(g["representative"] for g in picks)
        lines.append(f"- **{d}**：" + "；".join(g["representative"] for g in picks))
    lines.append("")
    lines.append("### 候选问句草稿（**需咨询师审定，不得直接进库**）")
    lines.append("")
    if not questions:
        lines.append("- （本次没有生成）")
    for q in questions:
        warn = ("  ⚠ " + "；".join(q["lint"])) if q.get("lint") else ""
        lines.append(f"- 「{q['text']}」{warn}")
        lines.append(f"  - polarity：{q['polarity']} · 面类别：{'/'.join(q['domains'])}"
                     f" · 来自：{q['from']}")
        if q["why"]:
            lines.append(f"  - 为什么能探到：{q['why']}")
    lines.append("")
    return "\n".join(lines)


CORPUS_SKIP = {"corpus.json", "summary.json", "extract_cache.json", "frames_seed.json",
               "taxonomy_draft.json", "corpus_labels.json", "domains8.json"}


def _domains_of(c: dict) -> list[str]:
    ds = c.get("domains")
    if ds is None:
        d = c.get("domain")
        ds = [d] if d else []
    return [str(x) for x in ds if str(x).strip()]


def build_corpus() -> list[dict]:
    """从所有框架 JSON 汇总语料——按目录扫描，不只当前这次跑到的框架。"""
    items: list[dict] = []
    for p in sorted(OUT_DIR.glob("*.json")):
        if p.name in CORPUS_SKIP:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "considerations" not in d:
            continue
        frame = (d.get("frame") or {}).get("key") or p.stem
        for c in d.get("considerations", []):
            items.append({**c, "frame": frame})
    return items


def write_corpus(corpus: list[dict]) -> None:
    corpus_path = OUT_DIR / "corpus.json"
    corpus_path.write_text(json.dumps(
        {"generated_at": time.strftime("%Y-%m-%d %H:%M"),
         "total": len(corpus), "items": corpus},
        ensure_ascii=False, indent=1), encoding="utf-8")
    by_frame: dict[str, list[dict]] = {}
    for c in corpus:
        by_frame.setdefault(c["frame"], []).append(c)
    clines = [f"# 实测考虑语料 · {len(corpus)} 条", "",
              "> 矿工产出，供归类用。每条：mk / 面类别（可多选）/ 文本。", ""]
    for key, items in by_frame.items():
        clines.append(f"## {key}（{len(items)} 条）")
        for i, c in enumerate(items, 1):
            tags = "/".join(_domains_of(c))
            clines.append(f"{i}. [{c['mk']}/{tags}] {c['text']}")
        clines.append("")
    (OUT_DIR / "corpus.md").write_text("\n".join(clines), encoding="utf-8")
    print(f"corpus -> {corpus_path} total={len(corpus)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="", help="逗号分隔的框架 key；空 = 全部")
    ap.add_argument("--frames-file", default="", help="JSON 框架清单；空 = 内置三个")
    ap.add_argument("--max-texts", type=int, default=30, help="每框架最多抽取多少段")
    ap.add_argument("--batch-size", type=int, default=6)
    ap.add_argument("--search-workers", type=int, default=3)
    ap.add_argument("--extract-workers", type=int, default=4)
    ap.add_argument("--no-search-cache", action="store_true")
    ap.add_argument("--skip-clusters", action="store_true", help="只挖语料，不聚类")
    ap.add_argument("--skip-questions", action="store_true", help="不起草问句")
    ap.add_argument("--rebuild-corpus", action="store_true",
                    help="不挖矿，只按目录里已有的框架 JSON 重建 corpus")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.rebuild_corpus:
        write_corpus(build_corpus())
        return 0

    frames = FRAMES
    if args.frames_file:
        try:
            frames = json.loads(Path(args.frames_file).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"读不了 frames-file：{exc}")
            return 1
    picked = [f for f in frames if not args.frames or f["key"] in args.frames.split(",")]
    if not picked:
        print("没有匹配的框架")
        return 1

    cfg = search.load_config()
    if cfg.provider in ("tavily", "bocha", "serper") and not cfg.api_key:
        print("搜索 key 没配置")
        return 1
    if not llm.available():
        print("llm key 没配置")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = _load_cache()
    report = [f"# 离线矿工报告 · {time.strftime('%Y-%m-%d %H:%M')}", "",
              "> 本报告是**开发期候选**，供咨询团队审定；不是给用户看的输出。",
              "> 所有候选都必须由用户认领才进 N；面清单只作结构展示，不计数。",
              "> mk 是模型判的软标签（两次独立判定一致率约 71%），只作审阅参考，不是测量。", ""]
    summary = []

    for frame in picked:
        t0 = time.time()
        texts, raw_total = collect(frame, cfg, args.max_texts,
                                   use_cache=not args.no_search_cache,
                                   workers=args.search_workers)
        cons = extract(frame, texts, cache, args.batch_size,
                       workers=args.extract_workers)
        groups = [] if args.skip_clusters else cluster(frame, cons)
        questions = ([] if (args.skip_questions or args.skip_clusters)
                     else draft_questions(frame, groups))
        stats = {"queries": len(frame["queries"]), "raw": raw_total,
                 "texts": len(texts), "cons": len(cons), "groups": len(groups)}
        summary.append({"key": frame["key"], "binary": frame["binary"], **stats,
                        "minutes": round((time.time() - t0) / 60, 1)})
        report.append(render_frame(frame, stats, groups, questions))
        result = {"frame": frame, "stats": stats, "texts": texts,
                  "considerations": cons, "groups": groups, "questions": questions}
        out = OUT_DIR / f"{frame['key']}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"frame {frame['key']}: texts={len(texts)} cons={len(cons)} "
              f"groups={len(groups)} q={len(questions)} {time.time()-t0:.0f}s")

    report_path = OUT_DIR / "report.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"report -> {report_path}")
    # 语料：按目录里所有框架 JSON 汇总（不只这次跑到的），供归类用
    write_corpus(build_corpus())
    print(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
