"""声景库。重点是红线校验。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rongqiu import soundscape as ss  # noqa: E402


def _t(title="某曲", duration="3:00", moment="night", note="低音为主，留白多"):
    return {"title": title, "duration": duration, "moment": moment, "note": note}


# ---------- 红线：宣称疗效 ----------

@pytest.mark.parametrize("word", ["治疗", "疗愈", "缓解", "改善", "焦虑", "助眠", "安神"])
def test_note_with_therapeutic_word_rejected(word):
    p = ss.check(_t(note=f"这首可以{word}你的情绪"))
    assert any(word in x for x in p)


def test_title_with_therapeutic_word_rejected():
    p = ss.check(_t(title="助眠曲"))
    assert p


def test_plain_description_passes():
    assert ss.check(_t(note="和弦简单，没有突然的高音")) == []


# ---------- 其他校验 ----------

def test_note_too_long_rejected():
    p = ss.check(_t(note="很" * 31))
    assert any("30" in x for x in p)


def test_invalid_moment_rejected():
    p = ss.check(_t(moment="随心情"))
    assert any("时刻标签非法" in x for x in p)


def test_missing_fields_rejected():
    p = ss.check({"moment": "night"})
    assert any("曲名" in x for x in p)
    assert any("时长" in x for x in p)


# ---------- 整库 ----------

def test_shipped_catalog_is_valid():
    """仓库里的曲库必须过校验——不过就是红线破了。"""
    v = ss.validate()
    assert v["ok"] is True, f"曲库未通过校验：{v['problems']}"


def test_catalog_groups_by_moment():
    c = ss.catalog()
    assert c["groups"], "曲库不该是空的"
    moments = [g["id"] for g in c["groups"]]
    assert moments == [m for m in ss.MOMENTS if m in moments]


def test_catalog_is_not_personalized():
    c = ss.catalog()
    assert c["personalized"] is False
    assert c["free"] is True
    # 输出里不能出现任何「针对你」的措辞
    blob = str(c)
    for w in ["为你", "推荐", "可能喜欢", "适合你", "根据你"]:
        assert w not in blob


def test_tracks_without_url_are_not_playable():
    c = ss.catalog()
    for g in c["groups"]:
        for t in g["tracks"]:
            assert t["playable"] is (bool(t["url"]))


def test_moments_are_objective_only():
    """时刻标签只能客观维度，不能是情绪状态。"""
    banned = {"开心", "难过", "焦虑", "低落", "兴奋", "烦躁", "压力大"}
    assert not (set(ss.MOMENTS) & banned)
