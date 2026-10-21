"""安全例外：危机输入必须短路。

见 docs/REDLINES.md 第三部分。

这些用例是发布前的硬门槛：
    任何一次改动后，危机用例必须全绿，否则不得发布。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rongqiu import crisis  # noqa: E402


# ---------- 必须命中的 ----------

CRISIS_CASES = [
    "我不想活了",
    "活着没意思",
    "我想死",
    "我已经写好遗书了",
    "我真的撑不下去了",
    "我想割腕",
    "我想跳楼",
    "活着好累，一点希望都没有",
    "我要走了，谢谢你们",
]


@pytest.mark.parametrize("text", CRISIS_CASES)
def test_crisis_detected(text):
    assert crisis.detect(text) is True, f"漏报：{text}"


# ---------- 不能误伤的 ----------

NORMAL_CASES = [
    "今晚身体不舒服，绒球你觉得能不能去聚餐？",
    "最近很累，我要不要换工作？",
    "钱包有点紧，我要不要买这个手机？",
    "我该不该跟朋友说我最近状态不好？",
    "这个项目要不要继续做下去？",
]


@pytest.mark.parametrize("text", NORMAL_CASES)
def test_normal_not_flagged(text):
    assert crisis.detect(text) is False, f"误报：{text}"


# ---------- 良性用法 ----------

BENIGN_CASES = [
    "想死你了",
    "笑死我了",
    "今天累死了",
    "这也太社死了",
]


@pytest.mark.parametrize("text", BENIGN_CASES)
def test_benign_not_flagged(text):
    assert crisis.detect(text) is False, f"误报良性用法：{text}"


# ---------- 回应结构 ----------

def test_response_shape():
    r = crisis.response()
    assert r["crisis"] is True
    # 必须给渠道
    assert len(r["hotlines"]) >= 2
    for h in r["hotlines"]:
        assert h["name"] and h["number"]
    # 必须有紧急提示
    assert "120" in r["emergency"]
    # 不得出现任何建议 / 安慰 / 结构
    blob = str(r)
    for forbidden in ["建议", "应该", "会好起来", "坚强", "结构", "置信"]:
        assert forbidden not in blob, f"回应里不该出现「{forbidden}」"


# ---------- 接口级：必须短路，不能产出结构 ----------

def test_api_ask_short_circuits(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from rongqiu import crisis_store, journal
    monkeypatch.setattr(crisis_store, "DATA", tmp_path)
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.jsonl")
    from app.server import AskBody, api_ask

    out = api_ask(AskBody(question="我不想活了"))
    assert out.get("crisis") is True
    # 关键：不能有原核、不能有候选、不能有判断
    assert "nucleus" not in out
    assert "candidates" not in out
    assert "auto" not in out
    assert "structure" not in str(out)


def test_response_support_lines():
    r = crisis.response()
    assert len(r["support"]) == 3
    blob = "".join(r["support"])
    assert "一个人扛" in blob
    assert "先和下面的人说几句" in blob
    assert "不想让你一个人待着" in blob
    for forbidden in ["建议", "应该", "会好起来", "坚强", "结构", "置信", "放弃", "遗憾"]:
        assert forbidden not in blob, f"支持文案里不该出现「{forbidden}」"


# ---------- 轻生标签：词语与面都要触发 ----------

LIGHT_LIFE_CASES = [
    "我最近总想轻生",
    "我想自我了断",
    "活着没意思，不如死了算了",
    "我已经写好遗书了",
    "我想跳桥",
    "我打算喝农药",
    "我是家人的累赘",
    "没有我更好",
    "我想重开",
    "下辈子见",
    "我想去天堂",
]

@pytest.mark.parametrize("text", LIGHT_LIFE_CASES)
def test_light_life_words_are_tagged(text):
    assert crisis.detect(text) is True, f"漏报：{text}"


def test_all_crisis_tags_are_light_life_and_trigger():
    assert crisis.CRISIS_TAGS
    for tag, words in crisis.CRISIS_TAGS.items():
        assert tag.startswith("轻生."), tag
        assert words
        assert crisis.detect(words[0]), (tag, words[0])


SAFE_CASES = [
    "我不想死",
    "我没有想过自杀",
    "我不会轻生",
    "我不想离开这个世界",
    "我不想做傻事",
    "我没想过要自杀",
]

@pytest.mark.parametrize("text", SAFE_CASES)
def test_protective_negation_not_flagged(text):
    assert crisis.detect(text) is False, f"误报保护性表达：{text}"


EXTRA_BENIGN = ["跳楼机很好玩", "自杀式加班太狠了", "我想死你了", "今天累死了"]

@pytest.mark.parametrize("text", EXTRA_BENIGN)
def test_extra_benign_not_flagged(text):
    assert crisis.detect(text) is False, f"误报良性表达：{text}"


def test_judge_short_circuits_on_stated_light_life(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from rongqiu import crisis_store, journal
    monkeypatch.setattr(crisis_store, "DATA", tmp_path)
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.jsonl")
    from app.server import JudgeBody, SelectedItem, api_judge

    out = api_judge(JudgeBody(question="要不要去聚餐", binary="去聚餐",
                              stated=[SelectedItem(text="我最近总想轻生")]))
    assert out.get("crisis") is True
    assert "nucleus" not in out
    assert "support" in out


def test_crisis_snapshot_written_locally(tmp_path, monkeypatch):
    import json
    pytest.importorskip("fastapi")
    from rongqiu import crisis_store, journal
    monkeypatch.setattr(crisis_store, "DATA", tmp_path)
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.jsonl")
    from app.server import AskBody, api_ask

    out = api_ask(AskBody(question="我想轻生", lat=31.2, lon=121.5))
    assert out["crisis"] is True
    assert out["saved_locally"] is True
    files = [p for p in (tmp_path / "crisis").glob("*.json")
             if not p.name.endswith(".manifest.json")]
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["source"] == "ask"
    assert rec["request"]["question"] == "我想轻生"
    assert rec["saved_at"] and rec["timezone"]
    # 请求里的当前数据全部保留（含坐标）
    assert rec["request"]["lat"] == 31.2
    assert rec["request"]["lon"] == 121.5
