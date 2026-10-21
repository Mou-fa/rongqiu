"""固定知识 / 常识基线。

这里的东西不是从用户数据里学出来的，是写死的参考：
盲猜 50%（Brier 0.25）、80% 封顶、艾宾浩斯遗忘曲线。

它们的作用是给校准图一条“世界本来是什么样”的底，
让用户看到的数据有一个可比的参照，而不是悬空的数字。

注意：遗忘曲线是经验曲线，不是定律。
数值来自 Ebbinghaus 1885 年无意义音节实验的粗略引用值；
有意义的、有已有知识挂钩的材料，衰减会慢得多。
"""

from __future__ import annotations

CHANCE_P_YES = 0.5          # 盲猜：会发生 / 不会发生，各一半
CHANCE_BRIER = 0.25         # 盲猜的 Brier 分数
CONFIDENCE_CAP = 0.8        # 811 的 80% 封顶（N=8 时 8/(8+2)）

# 艾宾浩斯遗忘曲线（保存率，粗略参考值）
# 时间 → 还记得的比例
EBBINGHAUS = [
    {"after": "20 分钟", "retention": 0.58},
    {"after": "1 小时", "retention": 0.44},
    {"after": "9 小时", "retention": 0.36},
    {"after": "1 天", "retention": 0.33},
    {"after": "2 天", "retention": 0.28},
    {"after": "6 天", "retention": 0.25},
    {"after": "31 天", "retention": 0.21},
]

EBBINGHAUS_NOTE = (
    "遗忘先快后慢：一天之内掉得最狠，之后趋于平缓。"
    "所以回看和确认要隔一段时间再做，而且以结构为准，不靠回忆。"
)


def as_dict() -> dict:
    """给前端 / API 用的固定知识。只读，不带任何用户数据。"""
    return {
        "chance_p_yes": CHANCE_P_YES,
        "chance_brier": CHANCE_BRIER,
        "confidence_cap": CONFIDENCE_CAP,
        "forgetting": EBBINGHAUS,
        "forgetting_note": EBBINGHAUS_NOTE,
        "source": "Ebbinghaus, Über das Gedächtnis (1885)；数值为粗略引用，非定律",
    }
