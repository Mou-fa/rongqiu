"""环境已知面：时间 / 地区 / 天气。

这三样是系统自己就能拿到的客观事实，不需要用户描述。
全部使用免费、无 key 的接口：
    时间  本地时钟
    天气  open-meteo.com
    地区  bigdatacloud.net
"""

from __future__ import annotations

from datetime import datetime

import pytest

from rongqiu import environment


def test_time_facts_always_available():
    """时间不联网，永远能拿到。"""
    facts = environment.time_facts(datetime(2026, 10, 19, 3, 0))   # 周一凌晨
    assert len(facts) == 2
    assert "深夜" in facts[0]
    assert "3 点" in facts[0]
    assert "工作日" in facts[1]


def test_period_mapping():
    assert environment._period(3) == "深夜"
    assert environment._period(7) == "清晨"
    assert environment._period(10) == "上午"
    assert environment._period(12) == "中午"
    assert environment._period(15) == "下午"
    assert environment._period(20) == "晚上"
    assert environment._period(23) == "深夜"


def test_weekend_vs_workday():
    assert "周末" in environment.time_facts(datetime(2026, 10, 17, 10))[1]   # 周六
    assert "工作日" in environment.time_facts(datetime(2026, 10, 19, 10))[1]  # 周一


def test_collect_without_coords_only_time():
    d = environment.collect()
    assert len(d["facts"]) == 2
    assert d["has_location"] is False


def test_collect_with_coords(monkeypatch):
    monkeypatch.setattr(environment, "location_facts", lambda a, b: ["我在北京市"])
    monkeypatch.setattr(environment, "weather_facts", lambda a, b: ["现在是 8 摄氏度，晴"])
    d = environment.collect(39.9, 116.4)
    assert "我在北京市" in d["facts"]
    assert "现在是 8 摄氏度，晴" in d["facts"]
    assert d["has_location"] is True


def test_weather_and_location_fail_soft(monkeypatch):
    """接口挂了不能阻塞判断，只是少几条环境事实。"""
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(environment, "_get", boom)
    assert environment.weather_facts(1, 2) == []
    assert environment.location_facts(1, 2) == []


def test_weather_code_mapping():
    assert environment.WEATHER[0] == "晴"
    assert environment.WEATHER[61] == "小雨"
    assert environment.WEATHER[95] == "雷阵雨"
