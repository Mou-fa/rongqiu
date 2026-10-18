"""判向质量评测。

判向是整个链路里唯一「机器替人做判断」的环节——用户自述的方向由模型猜。
它是错的，后面所有数字都跟着错。

所以先建度量：一组带标准答案的 (原核, 场景) 对，跑出准确率。
不建度量的优化就是瞎改。
"""

from __future__ import annotations

import sys
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from rongqiu import review  # noqa: E402
from rongqiu.triples import SUPPORT, OPPOSE, NEUTRAL  # noqa: E402

# (原核, 场景, 期望方向, 为什么)
CASES = [
    # --- 换工作 ---
    ("我会更换工作吗", "我感到疲惫", OPPOSE, "累让人不想动弹，更倾向维持现状"),
    ("我会更换工作吗", "我已经投了很多简历", SUPPORT, "已经在行动"),
    ("我会更换工作吗", "我对现在的工作很满意", OPPOSE, "没有推力"),
    ("我会更换工作吗", "公司明年要搬到我通勤两小时的地方", SUPPORT, "强推力"),
    ("我会更换工作吗", "我26岁从事第三份技术工作", SUPPORT, "有换工作的先例"),
    ("我会更换工作吗", "我正好有一笔够花一年的存款", SUPPORT, "有承担风险的能力"),
    ("我会更换工作吗", "我昨天加班到凌晨三点", OPPOSE, "疲惫，不是推力"),

    # --- 聚餐 ---
    ("我会去聚餐吗", "我今天身体不舒服", OPPOSE, "身体状态不允许"),
    ("我会去聚餐吗", "我很久没见这些朋友了", SUPPORT, "社交需求"),
    ("我会去聚餐吗", "我明天早上六点要起床", OPPOSE, "时间冲突"),
    ("我会去聚餐吗", "是我最好的朋友邀请的", SUPPORT, "关系强度"),

    # --- 买手机 ---
    ("我会购买手机吗", "我现在的手机已经用了三年，卡得厉害", SUPPORT, "替代需求"),
    ("我会购买手机吗", "我信用卡还欠着钱", OPPOSE, "支付能力不足"),

    # === 以下是改完提示词之后才加的留出题，用来检验是不是过拟合 ===
    ("我会更换工作吗", "我在这家公司干了整整十年", OPPOSE, "沉没成本与稳定"),
    ("我会更换工作吗", "我领导昨天当着全组的面批评了我", SUPPORT, "推力"),
    ("我会更换工作吗", "我下个月要还房贷", OPPOSE, "风险承受能力不足"),
    ("我会更换工作吗", "我最近在偷偷准备面试", SUPPORT, "已经在行动"),
    ("我会去聚餐吗", "这个聚会是公司要求的应酬", SUPPORT, "不得不去"),
    ("我会去聚餐吗", "我上周刚聚过一次", OPPOSE, "边际递减，刚满足过"),
    ("我会去聚餐吗", "组织者是我最不想见的人", OPPOSE, "回避动机"),
    ("我会学习英语吗", "我每天上下班通勤两小时", SUPPORT, "有时间窗口"),
    ("我会学习英语吗", "我下个月要考雅思", SUPPORT, "有明确目标和期限"),
    ("我会学习英语吗", "我日常工作和生活完全用不到英语", OPPOSE, "没有需求"),
    ("我会购买手机吗", "我现在的手机屏幕碎了", SUPPORT, "迫切的替代需求"),
    ("我会购买手机吗", "我在等三个月后的新款发布", OPPOSE, "主动推迟"),
]


def main() -> int:
    ok = 0
    fails = []
    for i, (nu, scene, expect, why) in enumerate(CASES, 1):
        facts = [review.SceneFact(scene=scene, order=0)]
        review.direction_of(facts, nu, runs=1)
        got = facts[0].supports
        hit = got == expect
        ok += hit
        mark = "✓" if hit else "✗"
        print(f"{mark} [{i:2d}] {nu[:12]:14s} | {scene[:22]:24s} "
              f"期望 {expect:8s} 实得 {got:8s}  {why if not hit else ''}")
        if not hit:
            fails.append((scene, expect, got, why))
    print()
    print(f"准确率 {ok}/{len(CASES)} = {ok/len(CASES):.0%}")
    if fails:
        print()
        print("错判明细：")
        for scene, expect, got, why in fails:
            print(f"  {scene[:30]}  应 {expect} 实 {got}  —— {why}")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
