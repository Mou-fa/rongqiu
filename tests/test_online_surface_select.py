"""在线路径也必须遵循输入层：按 surface 挑问句，而不是让模型自由挑。"""
from __future__ import annotations

from types import SimpleNamespace

import app.server as server
from rongqiu import journal
from rongqiu.nucleus import Nucleus


def test_online_ask_uses_surface_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)

    monkeypatch.setattr(server.nucleus, "parse",
                        lambda q: Nucleus(agent="我", event="去", resource="出去玩",
                                          binary="出去玩"))
    monkeypatch.setattr(server.search, "load_config",
                        lambda: SimpleNamespace(provider="local", api_key=""))
    monkeypatch.setattr(server.search, "expand_terms", lambda resource: ["出去玩"])
    monkeypatch.setattr(server.search, "multi_search",
                        lambda terms, event=None, cfg=None: [])
    monkeypatch.setattr(server.indexer, "rank", lambda nu, results: [])

    out = server.api_ask(server.AskBody(question="今天好累，要不要出去玩？"))
    ids = [q["id"] for q in out["questions"]]
    assert out["offline"] is False
    assert out["frame"] == "decision"
    assert "q01" in ids and "q13" in ids and "q19" in ids
    assert out["surfaces"]
    assert out["gaps"]
