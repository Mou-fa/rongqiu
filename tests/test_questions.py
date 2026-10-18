"""主动询问的测试。

问句由用户从心理咨询师角度确定，系统不发明。这里测的是容器：
读库、填槽、按条件挑、找不到时退回内置那一句。
"""

from __future__ import annotations

import pytest

from rongqiu import questions
from rongqiu.nucleus import Nucleus


def _nu(resource="聚餐"):
    return Nucleus(agent="我", event="参加", resource=resource, binary="我会去聚餐吗")


def test_builtin_question_is_the_canonical_one():
    """默认问句就是那句经典的万能句，一个字都不能走样。"""
    got = questions.load()
    assert len(got) >= 1
    assert got[0]["text"] == "你上一次遇到这种情况，最后怎么选的？"


def test_question_asks_behavior_not_motive():
    """边界：问句里不能出现「为什么」——那是在问动机，属于永远不碰的 10%。"""
    for q in questions.load():
        assert "为什么" not in q["text"]


def test_render_fills_resource_slot():
    q = {"id": "t", "text": "你上一次去{resource}是什么时候？", "when": "always"}
    assert "聚餐" in questions.render(q, _nu())["text"]


def test_render_drops_empty_slot():
    """资源为空时不能把花括号露给用户。"""
    q = {"id": "t", "text": "你上一次去{resource}是什么时候？", "when": "always"}
    out = questions.render(q, _nu(""))["text"]
    assert "{" not in out and "}" not in out


def test_for_nucleus_returns_rendered_list():
    got = questions.for_nucleus(_nu())
    assert got and all("text" in g and "{" not in g["text"] for g in got)


def test_missing_file_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(questions, "QUESTIONS_PATH", tmp_path / "nope.yaml")
    got = questions.load()
    assert len(got) == 1
    assert got[0]["text"] == "你上一次遇到这种情况，最后怎么选的？"
