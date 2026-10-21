"""离线输入层：框架 / binary / 按面挑问句。"""
from __future__ import annotations

from rongqiu import input_layer


def test_frame_and_binary():
    assert input_layer.frame_of("今天好累，要不要出去玩？") == "decision"
    assert input_layer.binary_of("今天好累，要不要出去玩？") == "出去玩"
    assert input_layer.binary_of("该不该跟对象分手？") == "跟对象分手"
    assert input_layer.frame_of("最近好累") == "vent"
    assert input_layer.frame_of("我不想活了") == "crisis"


def test_select_questions_spreads_across_surfaces():
    qs = input_layer.select_questions("今天好累，要不要出去玩？")
    ids = [q["id"] for q in qs]
    assert 1 <= len(ids) <= 10
    # health / time 在场；economic / risk / relationship 是缺口
    assert "q01" in ids      # economic
    assert "q13" in ids      # risk
    assert "q19" in ids      # relationship
    blob = " ".join(q["text"] for q in qs)
    for w in ["建议", "应该", "最好", "推荐"]:
        assert w not in blob


def test_select_questions_fallback_when_no_surface():
    qs = input_layer.select_questions("今天天气不错")
    assert 1 <= len(qs) <= 10


def test_water_safety_does_not_ask_money():
    qs = input_layer.select_questions("天气炎热，要不要下河洗澡？")
    ids = [q["id"] for q in qs]
    assert "last_time" in ids and "still_waiting" in ids
    assert "swim_ability" in ids
    assert "swim_before" in ids
    assert "swim_water_info" in ids
    assert "q01" not in ids      # 户外水域不是财务缺口
    assert "q02" not in ids


def test_body_states_are_health():
    for text in ("口渴要不要喝可乐", "脚冷要不要穿袜子？"):
        c = input_layer.compile(text)
        assert "decision.health" in [s["surface_id"] for s in c["surfaces"]], text


def test_weather_alone_is_not_a_surface():
    c = input_layer.compile("天有点冷，要不要烤火？")
    assert c["frame"] == "decision"
    assert "decision.health" not in [s["surface_id"] for s in c["surfaces"]]


GOLDEN_CASES = [
    # (text, frame, binary 应为, 至少包含一个 surface)
    ("我不想活了", "crisis", None, None),
    ("活着没什么意思", "crisis", None, None),
    ("今天心情很差", "vent", None, "decision.emotion"),
    ("心里乱糟糟的", "vent", None, None),
    ("最近睡不好，没精神", "vent", None, "decision.health"),
    ("该不该换城市生活？", "decision", "换城市生活", "decision.time"),
    ("值不值得报这个班？", "decision", "报这个班", "decision.time"),
    ("今天好累，要不要出去玩？", "decision", "出去玩", "decision.health"),
    ("天气炎热，要不要下河洗澡？", "decision", "下河洗澡", "decision.safety"),
]


def test_golden_input_layer_cases():
    for text, frame, binary, surface in GOLDEN_CASES:
        c = input_layer.compile(text)
        assert c["frame"] == frame, (text, c["frame"])
        if binary is not None:
            assert c["binary"] == binary, (text, c["binary"])
        if surface is not None:
            got = [s["surface_id"] for s in c["surfaces"]]
            assert surface in got, (text, got)


def test_cir_v1_contract():
    a = input_layer.compile("今天好累，要不要出去玩？")
    b = input_layer.compile("今天好累，要不要出去玩？")
    assert a["ir_version"] == "cir_input_v1"
    assert len(a["ir_hash"]) == 40
    assert a["ir_hash"] == b["ir_hash"]          # 确定性
    assert a["diagnostics"]["surface_count"] >= 13
    health = next(s for s in a["surfaces"] if s["surface_id"] == "decision.health")
    assert health["name"]
    assert health["evidence"]
    assert "span" in health["evidence"][0]


def test_cir_hash_changes_with_input():
    a = input_layer.compile("今天好累，要不要出去玩？")
    b = input_layer.compile("该不该跟对象分手？")
    assert a["ir_hash"] != b["ir_hash"]
