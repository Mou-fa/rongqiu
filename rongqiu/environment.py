"""环境已知面：地区、天气、时间。

这三样是「已经知道的面」——不需要用户描述，系统自己就能拿到。
它们和其他事实一样进入确定槽，方向由模型判。

取材策略（全部不需要 API key）：
    时间    本地时钟，不联网
    天气    open-meteo.com，全球覆盖，无需 key
    地区    bigdatacloud.net 逆地理，无需 key，返回中文

为什么这三样重要：用户犹豫的时候，往往自己都没意识到「现在几点了」
「外面下雨」「明天要上班」正在影响他的判断。系统替他把这些摆出来。

边界（811 权限契约）：
    时间    不做任何请求，永远可用
    位置    必须用户授权浏览器定位，拒绝就用不了
    天气    只有拿到坐标才去查
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# WMO 天气代码 → 中文
WEATHER = {
    0: "晴", 1: "大致晴", 2: "多云", 3: "阴",
    45: "有雾", 48: "雾凇",
    51: "毛毛雨", 53: "小雨", 55: "中雨",
    56: "冻毛毛雨", 57: "冻雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "强阵雨", 82: "暴雨",
    85: "阵雪", 86: "强阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷暴伴冰雹",
}


def _get(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout,
                                context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _period(hour: int) -> str:
    if hour < 6:
        return "深夜"
    if hour < 9:
        return "清晨"
    if hour < 12:
        return "上午"
    if hour < 14:
        return "中午"
    if hour < 18:
        return "下午"
    if hour < 22:
        return "晚上"
    return "深夜"


def time_facts(now: datetime | None = None) -> list[str]:
    """时间：不联网，永远可用。"""
    now = now or datetime.now()
    out = [f"现在是{_period(now.hour)} {now.hour} 点"]
    if now.weekday() >= 5:
        out.append(f"今天是周{'六日'[now.weekday() - 5]}，周末")
    else:
        out.append(f"今天是周{'一二三四五'[now.weekday()]}，工作日")
    return out


def location_facts(lat: float, lon: float) -> list[str]:
    """地区：逆地理。失败就返回空，不阻塞。"""
    try:
        url = ("https://api.bigdatacloud.net/data/reverse-geocode-client"
               f"?latitude={lat}&longitude={lon}&localityLanguage=zh")
        d = _get(url)
    except Exception:
        return []
    city = (d.get("city") or d.get("locality") or "").strip()
    region = (d.get("principalSubdivision") or "").strip()
    if city and region and city not in region:
        return [f"我在{region}{city}"]
    if region or city:
        return [f"我在{region or city}"]
    return []


def weather_facts(lat: float, lon: float) -> list[str]:
    """天气：open-meteo，不需要 key。"""
    try:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}"
               "&current=temperature_2m,relative_humidity_2m,weather_code,"
               "precipitation,wind_speed_10m&timezone=auto")
        d = _get(url)
    except Exception:
        return []
    cur = d.get("current") or {}
    out = []
    t = cur.get("temperature_2m")
    code = cur.get("weather_code")
    desc = WEATHER.get(int(code)) if code is not None else None
    if t is not None and desc:
        out.append(f"现在是 {round(float(t))} 摄氏度，{desc}")
    elif t is not None:
        out.append(f"现在是 {round(float(t))} 摄氏度")
    hum = cur.get("relative_humidity_2m")
    if hum is not None and float(hum) >= 80:
        out.append(f"湿度 {round(float(hum))}%，很闷")
    rain = cur.get("precipitation")
    if rain is not None and float(rain) > 0:
        out.append(f"正在下雨，降水量 {round(float(rain), 1)} 毫米")
    return out


def collect(lat: float | None = None, lon: float | None = None,
            now: datetime | None = None) -> dict:
    """汇总环境已知面。没有坐标就只有时间和天气以外的部分。"""
    groups = {"time": time_facts(now), "location": [], "weather": []}
    if lat is not None and lon is not None:
        groups["location"] = location_facts(lat, lon)
        groups["weather"] = weather_facts(lat, lon)
    facts = groups["time"] + groups["location"] + groups["weather"]
    return {"facts": facts, "groups": groups,
            "has_location": bool(groups["location"] or groups["weather"])}
