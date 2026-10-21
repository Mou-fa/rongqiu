"""回收页：只显示最新 revision；未满 24 小时不能标成「现在可以回收」。"""
from __future__ import annotations

import app.server as server
from rongqiu import journal
from rongqiu.node import Node
from rongqiu.triples import SceneFact, SUPPORT


def _judgment(n=5):
    facts = [SceneFact(scene=f"场景{i}", supports=SUPPORT, origin=i, order=i)
             for i in range(n)]
    return Node(nucleus="x", facts=facts).judge()


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)


def test_pending_dedupes_and_not_due_early(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    journal.record(_judgment(), "腰酸背痛，要不要现在去睡觉？", resolve_days=1)
    journal.record(_judgment(), "腰酸背痛，要不要现在去睡觉？", resolve_days=1)
    out = server.api_pending()
    assert out["total"] == 1          # 两条 revision -> 一个决策
    assert out["due"] == 0            # 还没到 24 小时
    assert out["items"][0]["due"] is False
    assert out["items"][0]["days_left"] >= 1


def test_pending_due_when_window_closed(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    journal.record(_judgment(), "今晚要不要去聚餐", resolve_days=0)
    out = server.api_pending()
    assert out["total"] == 1
    assert out["due"] == 1
    assert out["items"][0]["due"] is True
