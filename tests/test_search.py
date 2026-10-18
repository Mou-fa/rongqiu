"""搜索适配器的测试（用 local provider，不联网）。"""

from __future__ import annotations

import json

import pytest

from rongqiu import search


def _write_corpus(tmp_path, items):
    """代码读的是 ROOT/data/local_corpus.json，测试必须写在同一个位置。"""
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "local_corpus.json").write_text(json.dumps(items, ensure_ascii=False),
                                         encoding="utf-8")


def test_local_provider_filters_by_terms(tmp_path, monkeypatch):
    _write_corpus(tmp_path, [
        {"source": "web", "text": "我参加聚会前会先睡一觉"},
        {"source": "web", "text": "苹果发布新款手机"},
        {"source": "web", "text": "我参加聚会后很累"},
    ])
    monkeypatch.setattr(search, "ROOT", tmp_path)
    monkeypatch.setattr(search, "CACHE_DIR", tmp_path / "cache")

    cfg = search.SearchConfig(provider="local")
    out = search.search("我 参加 聚会", cfg)
    assert len(out) == 2
    assert all("聚会" in text for _, text in out)


def test_missing_corpus_returns_empty_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(search, "ROOT", tmp_path)
    monkeypatch.setattr(search, "CACHE_DIR", tmp_path / "cache")
    assert search.search("任何词", search.SearchConfig(provider="local")) == []


def test_unknown_provider_falls_back_to_local(tmp_path, monkeypatch):
    monkeypatch.setattr(search, "ROOT", tmp_path)
    monkeypatch.setattr(search, "CACHE_DIR", tmp_path / "cache")
    cfg = search.SearchConfig(provider="不存在的服务", api_key="x")
    assert search.search("词", cfg) == []


def test_no_key_uses_local_even_if_provider_is_tavily(tmp_path, monkeypatch):
    _write_corpus(tmp_path, [{"source": "web", "text": "我参加聚会"}])
    monkeypatch.setattr(search, "ROOT", tmp_path)
    monkeypatch.setattr(search, "CACHE_DIR", tmp_path / "cache")
    cfg = search.SearchConfig(provider="tavily", api_key="")
    assert len(search.search("我 聚会", cfg)) == 1
