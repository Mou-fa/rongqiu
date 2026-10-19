"""第一接触面只收陈述句。

四类句型里只有陈述句能入列。疑问句不是事实、祈使句是建议、感叹句是情绪。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rongqiu import indexer  # noqa: E402


# ---------- 陈述句：通过 ----------

@pytest.mark.parametrize("s", [
    "我参加聚会后经常觉得累",
    "我上次聚餐回家后头疼了一晚上",
    "他每周都会回一次老家",
    "我参加聚会前通常会先睡一觉。",     # 带句号仍是陈述句
])
def test_declarative_passes(s):
    assert indexer.is_declarative(s) is True


# ---------- 疑问句：拒绝 ----------

@pytest.mark.parametrize("s", [
    "聚餐到底该不该去？",
    "我这样算不算社交恐惧?",
    "要不要参加这次聚会呢？",
])
def test_question_rejected(s):
    assert indexer.is_declarative(s) is False


# ---------- 感叹句：拒绝 ----------

@pytest.mark.parametrize("s", [
    "太累了吧！",
    "聚餐真是折磨人!",
])
def test_exclamation_rejected(s):
    assert indexer.is_declarative(s) is False


# ---------- 祈使/建议：拒绝（红线一） ----------

@pytest.mark.parametrize("s", [
    "建议你不要参加聚餐",
    "你应该多参加社交活动",
    "推荐大家饭后散步",
    "最好提前一小时出门",
    "千万别熬夜刷手机",
    "记得带上身份证",
])
def test_imperative_rejected(s):
    assert indexer.is_declarative(s) is False


def test_imperative_reason_is_redline():
    """祈使句被拒的理由是红线一：建议零权重，不能洗成事实。"""
    assert indexer.is_declarative("建议你去参加聚餐") is False


# ---------- 长度 ----------

def test_empty_rejected():
    assert indexer.is_declarative("") is False
    assert indexer.is_declarative("   ") is False
    assert indexer.is_declarative(None) is False


def test_too_short_rejected():
    assert indexer.is_declarative("我累") is False


def test_too_long_rejected():
    assert indexer.is_declarative("我" * 41) is False


# ---------- 边界：观点仍是陈述句，这一步不管 ----------

def test_opinion_is_still_declarative():
    """观点也是陈述句。这一步只筛句型，语义由 REA 可填性在下一级管。"""
    assert indexer.is_declarative("参加聚会有助于维系人际关系") is True


# ---------- 提示词回归 ----------
# 提示词是「第二级过滤」。它一旦被人改回去，第一级只剩 94% 的覆盖率，
# 而且语义层的伪陈述（观点/统计/泛化）会全部漏回来。
# 这几条测试是给提示词上的锁。

@pytest.mark.parametrize("prompt", [indexer.SYSTEM, indexer.BATCH_SYSTEM])
def test_prompt_requires_declarative(prompt):
    assert "陈述句" in prompt
    assert "问号" in prompt


@pytest.mark.parametrize("prompt", [indexer.SYSTEM, indexer.BATCH_SYSTEM])
def test_prompt_has_rea_criterion(prompt):
    """唯一可操作的判据：能不能拆出「谁·做了什么·对什么」。"""
    assert "谁" in prompt and "做了什么" in prompt and "对什么" in prompt


@pytest.mark.parametrize("prompt", [indexer.SYSTEM, indexer.BATCH_SYSTEM])
def test_prompt_rejects_pseudo_facts(prompt):
    for kind in ["疑问句", "祈使句", "感叹句", "观点", "统计", "泛化"]:
        assert kind in prompt, f"提示词里少了拒收类型：{kind}"
