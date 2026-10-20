"""按原核挑面：从问句库里挑这次该问的，挑不出来退回整库。"""

from __future__ import annotations

import json

from rongqiu import questions
from rongqiu.nucleus import Nucleus


def _nu():
    return Nucleus(agent="我", event="参加", resource="聚餐",
                   binary="我会去聚餐吗")


def test_select_falls_back_to_full_library(monkeypatch):
    monkeypatch.setattr(questions.llm, "available", lambda cfg=None: False)
    got = questions.select(_nu())
    assert len(got) == len(questions.load())


def test_select_uses_model_picks(monkeypatch, tmp_path):
    ids = [q["id"] for q in questions.load()[:2]]
    monkeypatch.setattr(questions, "SELECT_CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(questions.llm, "load_config", lambda: None)
    monkeypatch.setattr(questions.llm, "available", lambda cfg=None: True)
    calls = {"n": 0}

    def fake_complete(prompt, system=None, cfg=None):
        calls["n"] += 1
        return json.dumps({"ids": ids, "why": "test"})

    monkeypatch.setattr(questions.llm, "complete", fake_complete)
    got = questions.select(_nu())
    assert [q["id"] for q in got] == ids
    # 第二次走缓存，不再调模型
    got2 = questions.select(_nu())
    assert [q["id"] for q in got2] == ids
    assert calls["n"] == 1


def test_select_ignores_unknown_ids(monkeypatch, tmp_path):
    known = questions.load()[0]["id"]
    monkeypatch.setattr(questions, "SELECT_CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(questions.llm, "load_config", lambda: None)
    monkeypatch.setattr(questions.llm, "available", lambda cfg=None: True)
    monkeypatch.setattr(questions.llm, "complete",
                        lambda prompt, system=None, cfg=None:
                        json.dumps({"ids": ["不存在的id", known]}))
    got = questions.select(_nu())
    assert [q["id"] for q in got] == [known]


def test_unanswered_returns_asked_minus_answered():
    qs = questions.load()[:2]
    asked = [q["id"] for q in qs]
    got = questions.unanswered(asked, {asked[0]})
    assert [q["id"] for q in got] == [asked[1]]
