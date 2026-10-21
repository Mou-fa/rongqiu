"""离线路径：没有 LLM / 搜索时，固定问句 + probe 答复仍能完成判断。"""
from __future__ import annotations

import app.server as server
from rongqiu import journal


def test_offline_ask_and_judge(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "j.jsonl")
    monkeypatch.setattr(journal, "DATA", tmp_path)

    def no_llm(question):
        raise RuntimeError("no llm")

    monkeypatch.setattr(server.nucleus, "parse", no_llm)

    out = server.api_ask(server.AskBody(question="今天好累，要不要出去玩？"))
    assert out["offline"] is True
    assert out["nucleus"]["binary"]
    assert 1 <= len(out["questions"]) <= 10
    assert out["candidates"] == []

    q = out["questions"][0]
    judged = server.api_judge(server.JudgeBody(
        question="今天好累，要不要出去玩？",
        binary="",
        answers=[server.AnswerItem(id=q["id"], answer="yes")],
        asked=[q["id"]],
    ))
    assert judged["ok"] is True
    assert judged["judgment"]["lean"] in ("yes", "no")
    assert len(journal.load()) == 1


def test_offline_parse_binary():
    from rongqiu import input_layer
    assert input_layer.frame_of("今天好累，要不要出去玩？") == "decision"
    assert input_layer.binary_of("今天好累，要不要出去玩？") == "出去玩"
    assert input_layer.binary_of("该不该跟对象分手？") == "跟对象分手"
    assert input_layer.frame_of("最近好累") == "vent"
    assert input_layer.frame_of("我不想活了") == "crisis"
