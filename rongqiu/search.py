"""搜索适配器：把用户的原核三元组，变成全网的场景文本。

为什么做成可插拔：这台机器上可达的搜索服务有好几家（Tavily、博查、
Serper、Bing），但都不便宜、也可能随时改协议。绒球不该绑死在其中一家。

配置（configs/search.yaml，已在 .gitignore 里）：

    provider: tavily
    api_key: tvly-...
    max_results: 10

或者环境变量 RONGQIU_SEARCH_KEY。

没有 key 时退回 local provider，读本地语料文件——这样开发和测试
不需要联网，也不会产生费用。
"""

from __future__ import annotations

import html as htmlmod
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "search.yaml"
CACHE_DIR = ROOT / "data" / "search_cache"


@dataclass
class SearchConfig:
    provider: str = "tavily"
    base_url_llm: str = "https://api.deepseek.com"
    api_key: str = ""
    max_results: int = 60
    timeout: float = 25.0


def _parse_yaml(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_config() -> SearchConfig:
    cfg = SearchConfig()
    if CONFIG_PATH.exists():
        try:
            raw = _parse_yaml(CONFIG_PATH.read_text(encoding="utf-8"))
            if raw.get("provider"):
                cfg.provider = str(raw["provider"])
            if raw.get("api_key"):
                cfg.api_key = str(raw["api_key"])
            if raw.get("max_results"):
                cfg.max_results = int(raw["max_results"])
        except Exception:
            pass
    env = os.environ.get("RONGQIU_SEARCH_KEY", "").strip()
    if env:
        cfg.api_key = env
    return cfg


def _post(url: str, payload: dict, headers: dict, timeout: float) -> dict | None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"search HTTP {exc.code}") from exc
    except Exception as exc:
        raise RuntimeError(f"search failed: {type(exc).__name__}: {exc}") from exc


def _tavily(query: str, cfg: SearchConfig) -> list[tuple[str, str]]:
    """Tavily：专为 AI 设计，返回的是页面正文片段而不是截断的摘要。

    这正是绒球需要的——我们要的是能读懂的场景文本，不是关键词高亮。
    key 同时放在 body 和 Authorization 头里：新旧两版 API 的取法不同。
    """
    body = _post("https://api.tavily.com/search",
                 {"api_key": cfg.api_key, "query": query,
                  "max_results": min(cfg.max_results, 20),
                  "search_depth": "basic",
                  "include_answer": False,
                  "include_raw_content": False},
                 {"Authorization": "Bearer " + cfg.api_key}, cfg.timeout) or {}
    out = []
    for r in body.get("results", []):
        text = (r.get("content") or "").strip()
        if not text:
            continue
        out.append((f"tavily:{r.get('title', '')[:36]}", text))
    return out


def _bocha(query: str, cfg: SearchConfig) -> list[tuple[str, str]]:
    body = _post("https://api.bochaai.com/v1/web-search",
                 {"query": query, "count": cfg.max_results, "summary": True},
                 {"Authorization": "Bearer " + cfg.api_key}, cfg.timeout) or {}
    pages = (body.get("data") or {}).get("webPages", {}).get("value", [])
    return [(p.get("url", "web"), p.get("summary") or p.get("snippet", ""))
            for p in pages if (p.get("summary") or p.get("snippet"))]


def _serper(query: str, cfg: SearchConfig) -> list[tuple[str, str]]:
    body = _post("https://google.serper.dev/search",
                 {"q": query, "num": cfg.max_results},
                 {"X-API-KEY": cfg.api_key}, cfg.timeout) or {}
    return [(r.get("link", "web"), r.get("snippet", ""))
            for r in body.get("organic", []) if r.get("snippet")]


def _sogou(query: str, cfg: SearchConfig) -> list[tuple[str, str]]:
    """搜狗网页搜索。不需要 API key。

    为什么用它做默认：这台机器上 Bing 的 HTML 抓取会系统性返回首词字典
    释义（查询「参加聚会后觉得很累」会返回「参加」的词典条目），Baidu
    直接返回 1438 字节的被拦页面。搜狗返回的是真实内容，能拿到关于
    「参加聚会累」的实际文章摘要。

    做法是抓搜索结果页的摘要，不是给每个网页建索引——搜狗已经建好了。
    """
    url = "https://www.sogou.com/web?query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout,
                                    context=ssl.create_default_context()) as resp:
            html_text = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(f"sogou failed: {type(exc).__name__}") from exc

    def strip_tags(s: str) -> str:
        return htmlmod.unescape(re.sub(r"<[^>]+>", "", s)).strip()

    out: list[tuple[str, str]] = []
    blocks = re.findall(r'<div class="(?:vrwrap|rb)".*?(?=<div class="(?:vrwrap|rb)"|$)',
                        html_text, re.S)
    for block in blocks[:cfg.max_results]:
        title_m = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        paras = [strip_tags(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", block, re.S)]
        paras = [p for p in paras if len(p) > 15]
        if not paras:
            continue
        title = strip_tags(title_m.group(1)) if title_m else ""
        body = paras[0]
        out.append((f"sogou:{title[:40]}" if title else "sogou", body))
    return out


PROVIDERS = {"tavily": _tavily, "bocha": _bocha, "serper": _serper, "sogou": _sogou}


def _local(query: str, cfg: SearchConfig) -> list[tuple[str, str]]:
    """无 key 时的退路：把本地语料整批当作「搜索结果」返回。

    这里**故意不做关键词过滤**。查询词是规范化之后的（「更换」），
    而原文里写的是口语（「换」）——如果在这里按字面过滤，相关内容在
    进入匹配之前就被杀光了。相关性判断交给 indexer 在三元组空间里做。

    真实搜索 API 的行为也是这样：搜索引擎按语义返回一批结果，
    由我们自己的匹配层来筛。
    """
    path = ROOT / "data" / "local_corpus.json"
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [(it.get("source", "local"), it.get("text", ""))
            for it in items if it.get("text")][:cfg.max_results]


EXPAND_SYSTEM = """你是「绒球」的检索词展开器。

把用户问题里的核心名词，拆成它的构词成分，再展开成相关的检索词。
例：「聚餐」→ 聚：聚会、聚拢 / 餐：餐厅、餐饮、餐食、餐盘、餐馆
   → 输出 聚餐、聚会、餐厅、餐饮、餐馆、饭局

目的：全网的文本里不一定出现「聚餐」这个词，但会出现「聚会」「餐厅」。
展开之后，整张网都变成了第一接触面的候选库——不需要为每个事物建数据库。

只输出 JSON：{"terms": ["", ""]}"""


def expand_terms(resource: str, cfg: SearchConfig | None = None,
                 limit: int = 12) -> list[str]:
    """把核心名词展开成相关检索词。失败时退回原词，不阻塞判断。"""
    if not resource:
        return []
    try:
        from .llm import available as _avail
        from .llm import complete as _complete
        from .llm import load_config as _lc

        lcfg = _lc()
        if not _avail(lcfg):
            return [resource]
        raw = _complete(f"名词：{resource}", system=EXPAND_SYSTEM, cfg=lcfg)
        if not raw:
            return [resource]
        t = raw.strip()
        if t.startswith("```"):
            import re as _re
            t = _re.sub(r"^```[a-zA-Z]*\s*", "", t)
            t = _re.sub(r"```\s*$", "", t)
        terms = json.loads(t.strip()).get("terms", [])
        out = [str(x).strip() for x in terms if str(x).strip()]
        merged = [resource] + [x for x in out if x != resource]
        return merged[:limit]
    except Exception:
        return [resource]


def multi_search(terms: list[str], event: str = "",
                 cfg: SearchConfig | None = None,
                 per_query: int = 12, max_queries: int = 6,
                 max_total: int = 40) -> list[tuple[str, str]]:
    """每个组合词单独搜一次，再合并去重。

    把十个词塞进一个查询，搜索引擎只认前几个。分开搜，每个词各拿到
    一批结果，覆盖才够——而 N 就是从这里来的。
    """
    cfg = cfg or load_config()
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for term in terms[:max_queries]:
        q = (event + term) if event else term
        try:
            batch = search(q, cfg, use_cache=True)
        except Exception:
            continue
        for src, text in batch[:per_query]:
            key = text[:60]
            if key in seen:
                continue
            seen.add(key)
            out.append((src, text))
            if len(out) >= max_total:
                return out
    return out


def search(query: str, cfg: SearchConfig | None = None,
           use_cache: bool = True) -> list[tuple[str, str]]:
    """按原核三元组去搜场景文本。失败返回空列表，绝不抛异常。"""
    cfg = cfg or load_config()
    # sogou 不需要 key；其余 API provider 没 key 时退回本地语料
    if cfg.provider not in ("sogou", "local") and not cfg.api_key:
        return _local(query, cfg)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / (str(abs(hash(query))) + ".json")
    if use_cache and cache_file.exists():
        try:
            return [tuple(x) for x in json.loads(cache_file.read_text(encoding="utf-8"))]
        except Exception:
            pass

    fn = PROVIDERS.get(cfg.provider)
    if fn is None:
        return _local(query, cfg)
    try:
        results = fn(query, cfg)
    except RuntimeError:
        return _local(query, cfg) if cfg.provider != "local" else []
    try:
        cache_file.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return results
