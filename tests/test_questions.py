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


# --- 面类别标注（2026-10-20 起） -------------------------------------------
# 15 类面类别、可多选。词表在 configs/taxonomy.yaml。


def test_taxonomy_is_loaded():
    """词表要能读出来；问句库的标注都以它为准。"""
    names = questions.domain_names()
    assert len(names) >= 10
    # 16 类 v2：4109 条实测复检后加入「信息真伪」
    assert "信息真伪" in names


def test_every_question_is_annotated():
    """M1 解锁条件之一：每个问句必须标注 mk + 至少一个 domain。"""
    assert questions.issues() == []


def test_domains_can_be_multi_select(monkeypatch, tmp_path):
    bank = tmp_path / "q.yaml"
    bank.write_text(
        "questions:\n"
        "  - id: multi\n"
        "    text: 你手头紧不紧？\n"
        "    mk: cause\n"
        "    domains: [经济负担, 家庭责任]\n",
        encoding="utf-8")
    monkeypatch.setattr(questions, "QUESTIONS_PATH", bank)
    got = questions.load()
    assert got[0]["mk"] == "cause"
    assert got[0]["domains"] == ["经济负担", "家庭责任"]


def test_legacy_single_domain_string_is_wrapped(monkeypatch, tmp_path):
    bank = tmp_path / "q.yaml"
    bank.write_text(
        "questions:\n"
        "  - id: legacy\n"
        "    text: 你上次去了吗？\n"
        "    mk: common\n"
        "    domain: 经济负担\n",
        encoding="utf-8")
    monkeypatch.setattr(questions, "QUESTIONS_PATH", bank)
    assert questions.load()[0]["domains"] == ["经济负担"]


def test_invalid_mk_is_dropped_and_flagged(monkeypatch, tmp_path):
    bank = tmp_path / "q.yaml"
    bank.write_text(
        "questions:\n"
        "  - id: bad\n"
        "    text: 你是不是很累？\n"
        "    mk: maybe\n"
        "    domains: []\n",
        encoding="utf-8")
    monkeypatch.setattr(questions, "QUESTIONS_PATH", bank)
    assert questions.load()[0]["mk"] == ""
    problems = questions.issues()
    assert any("mk" in p for p in problems)
    assert any("domains" in p for p in problems)


def test_unknown_domain_is_flagged(monkeypatch, tmp_path):
    bank = tmp_path / "q.yaml"
    bank.write_text(
        "questions:\n"
        "  - id: odd\n"
        "    text: 你是不是很累？\n"
        "    mk: common\n"
        "    domains: [不存在的类]\n",
        encoding="utf-8")
    monkeypatch.setattr(questions, "QUESTIONS_PATH", bank)
    assert any("未知 domain" in p for p in questions.issues())

