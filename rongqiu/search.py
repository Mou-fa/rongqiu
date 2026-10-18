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

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "search.yaml"
CACHE_DIR = ROOT / "data" / "search_cache"


@dataclass
class SearchConfig:
    provider: str = "local"
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
    body = _post("https://api.tavily.com/search",
                 {"api_key": cfg.api_key, "query": query,
                  "max_results": cfg.max_results, "search_depth": "basic"},
                 {}, cfg.timeout) or {}
    return [(r.get("url", "web"), r.get("content") or r.get("title", ""))
            for r in body.get("results", []) if (r.get("content") or r.get("title"))]


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


PROVIDERS = {"tavily": _tavily, "bocha": _bocha, "serper": _serper}


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


def search(query: str, cfg: SearchConfig | None = None,
           use_cache: bool = True) -> list[tuple[str, str]]:
    """按原核三元组去搜场景文本。失败返回空列表，绝不抛异常。"""
    cfg = cfg or load_config()
    if cfg.provider == "local" or not cfg.api_key:
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
        return []
    try:
        cache_file.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return results
