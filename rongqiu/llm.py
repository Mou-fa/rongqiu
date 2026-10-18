"""LLM 客户端：只负责把文本读成事件。

绒球对它的要求有边界：
- 它可以补主语、辨否定、消指代、定时间、统一粒度
- 它不可以判定事件真假（那是溯源的工作）
- 它不可以给出最终倾向（那是 N11 的工作）

配置查找顺序：rongqiu/configs/llm.yaml → ../quant-lab/configs/llm.yaml
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_CANDIDATES = [
    ROOT / "configs" / "llm.yaml",
    ROOT.parent / "quant-lab" / "configs" / "llm.yaml",
]


@dataclass
class LLMConfig:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    api_key: str = ""
    timeout: float = 60.0
    max_tokens: int = 1600
    temperature: float = 0.0     # 同一个问题两次判定必须一致，先压住随机性


def _parse_yaml(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_config() -> LLMConfig:
    cfg = LLMConfig()
    for path in CONFIG_CANDIDATES:
        if not path.exists():
            continue
        try:
            raw = _parse_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for f in ("base_url", "model", "api_key"):
            if raw.get(f):
                setattr(cfg, f, str(raw[f]))
        if cfg.api_key:
            break
    env = os.environ.get("QLAB_LLM_KEY", "").strip() or os.environ.get("RONGQIU_LLM_KEY", "").strip()
    if env:
        cfg.api_key = env
    return cfg


def available(cfg: LLMConfig | None = None) -> bool:
    return bool((cfg or load_config()).api_key)


def complete(prompt: str, system: str | None = None,
             cfg: LLMConfig | None = None) -> str | None:
    cfg = cfg or load_config()
    if not cfg.api_key:
        return None
    payload = {
        "model": cfg.model,
        "messages": ([{"role": "system", "content": system}] if system else [])
        + [{"role": "user", "content": prompt}],
        "max_tokens": cfg.max_tokens,
        "temperature": cfg.temperature,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        cfg.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg.api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LLM HTTP {exc.code}") from exc
    except Exception as exc:
        raise RuntimeError(f"LLM call failed: {type(exc).__name__}: {exc}") from exc
