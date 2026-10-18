"""共识抽取的测试（不打网络，用假的 extract）。"""

from __future__ import annotations

import pytest

from rongqiu import extract
from rongqiu.triples import Triple


def test_consensus_keeps_only_stable_facts(monkeypatch):
    calls = {"n": 0}

    def fake_extract(question, texts, cfg=None):
        calls["n"] += 1
        i = calls["n"]
        from rongqiu.triples import Extraction
        stable = Triple("老张", "邀请", "我", source="chat")
        out = Extraction(question=question, facts=[stable], assumption="a", unknown="u")
        if i == 1:      # 只出现一次的事实，应该被丢掉
            out.facts.append(Triple("小李", "说", "改期", source="chat"))
        return out

    monkeypatch.setattr(extract, "extract", fake_extract)
    monkeypatch.setattr(extract, "load_config", lambda: type("C", (), {"model": "fake", "api_key": "k"})())
    monkeypatch.setattr(extract, "available", lambda cfg=None: True)

    ex = extract.consensus("问题", [("chat", "文本")], runs=3, min_freq=0.6)
    keys = {f"{t.agent}|{t.event}" for t in ex.facts}
    assert "老张|邀请" in keys
    assert "小李|说" not in keys
    kept = [t for t in ex.facts if t.agent == "老张"][0]
    assert kept.frequency == pytest.approx(1.0)


def test_dedup_merges_the_same_event_described_twice():
    a = Triple("项目组", "安排", "复盘会", source="calendar")
    b = Triple("项目组", "要求参加", "复盘会", source="calendar")
    c = Triple("小王", "请假", "一天", source="chat")
    out = extract._dedup([a, b, c])
    assert len(out) == 2
    assert "同事件复述" in out[0].evidence
