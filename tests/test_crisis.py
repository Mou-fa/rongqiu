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

def test_api_ask_short_circuits():
    pytest.importorskip("fastapi")
    from app.server import AskBody, api_ask

    out = api_ask(AskBody(question="我不想活了"))
    assert out.get("crisis") is True
    # 关键：不能有原核、不能有候选、不能有判断
    assert "nucleus" not in out
    assert "candidates" not in out
    assert "auto" not in out
    assert "structure" not in str(out)
