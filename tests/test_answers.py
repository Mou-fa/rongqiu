"""主动询问：二元对立 + 固定接触面。

两条设计约束（用户确定）：
1. 只能是 yes / no，不打字。
   yes = 确定性第一接触面，no = 否定性第一接触面。
   方向由点击直接决定，不经过模型。
2. 主动询问是固定接触面。词条数决定面数，代码里不许写死。
"""

from __future__ import annotations

import pytest

from rongqiu import questions
from rongqiu.node import Node
from rongqiu.nucleus import Nucleus
from rongqiu.triples import SUPPORT, OPPOSE


def test_yes_maps_to_support():
    fs = questions.answers_to_facts([{"id": "last_time", "answer": "yes"}])
    assert len(fs) == 1
    assert fs[0].supports == SUPPORT
    assert "是" in fs[0].scene


def test_no_maps_to_oppose():
    fs = questions.answers_to_facts([{"id": "last_time", "answer": "no"}])
    assert fs[0].supports == OPPOSE
    assert "否" in fs[0].scene


def test_invalid_answer_is_ignored():
    """自由文本一律不接受——只能是 yes / no。"""
    fs = questions.answers_to_facts([
        {"id": "last_time", "answer": "我觉得还行"},
        {"id": "last_time", "answer": ""},
        {"id": "nope", "answer": "yes"},
    ])
    assert fs == []


def test_answering_increases_surface_count():
    assert Node(nucleus="x", facts=[]).judge() is None   # 没有面时节点不成立

    qa = questions.answers_to_facts([{"id": "last_time", "answer": "no"}])
    j = Node(nucleus="x", facts=qa).judge()
    assert j.n == 1
    assert j.total_surfaces == 3             # 1 事实 + 1 假设 + 1 未知


def test_surface_quota_follows_the_bank(monkeypatch, tmp_path):
    """加词条 → 固定询问面变多。代码里没有写死。"""
    bank = tmp_path / "questions.yaml"
    bank.write_text(
        "questions:\n"
        "  - id: a\n"
        "    text: 第一句？\n"
        "  - id: b\n"
        "    text: 第二句？\n",
        encoding="utf-8")
    monkeypatch.setattr(questions, "QUESTIONS_PATH", bank)
    assert questions.surface_quota() == 2

    bank.write_text(
        "questions:\n"
        "  - id: a\n"
        "    text: 第一句？\n",
        encoding="utf-8")
    assert questions.surface_quota() == 1


def test_answers_only_count_questions_that_exist(monkeypatch, tmp_path):
    bank = tmp_path / "questions.yaml"
    bank.write_text("questions:\n  - id: a\n    text: 第一句？\n", encoding="utf-8")
    monkeypatch.setattr(questions, "QUESTIONS_PATH", bank)
    fs = questions.answers_to_facts([
        {"id": "a", "answer": "yes"},
        {"id": "gone", "answer": "no"},      # 词条被删了，回答不算
    ])
    assert len(fs) == 1
