"""绒球·问一条：从用户问题走到二元判断。

完整链路：
    用户问题（文本；语音是同一个入口的适配器）
        → 原核解析：三元组（代理·事件·资源）
        → 在语料里找第一接触面（先结构预筛，后模型判相关性）
        → 共识抽取稳定事实
        → N11 判定
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rongqiu import extract, match, node, nucleus, trace  # noqa: E402

QUESTION = "今晚的聚会，我应该去吗？"

CORPUS = [
    # 相关
    ("chat", "老张：周五晚上聚一下？就我们几个老人，好久没见了。"),
    ("calendar", "10月18日 19:00-21:00 项目复盘会（全员，不可缺席）"),
    ("chat", "小李：你要是不方便，我们就改下周，反正人也不齐。"),
    ("note", "最近两周平均每天睡 5.5 小时，周三已经推掉一次约了。"),
    ("chat", "老张：这次聚完，老王就调去上海了，可能几年见不着。"),
    # 无关
    ("news", "苹果发布新款手机，售价 7999 元起。"),
    ("chat", "王经理：下季度的预算表我发你邮箱了。"),
    ("note", "牛奶快喝完了，记得买。"),
    ("news", "央行宣布下调存款准备金率 0.25 个百分点。"),
    ("chat", "小李：明天上午的代码评审改到下午三点。"),
]


def main() -> int:
    print("=" * 64)
    print("绒球 · 问一条")
    print("=" * 64)
    print(f"用户输入：{QUESTION}\n")

    print("① 原核解析（问题 → 三元组）")
    nu = nucleus.parse(QUESTION)
    print(f"   {nu.render()}\n")

    print("② 找第一接触面（结构预筛）")
    cands = match.rank(nu, CORPUS, min_overlap=0.0, limit=10)
    print(match.render(cands))
    print()
    print("   注意：字符重叠只是廉价预筛。看看它有没有漏掉真正相关的——")
    keep = [c for c in cands if c.overlap >= 0.15]
    print(f"   按 0.15 门槛，只有 {len(keep)} 条进入下一轮。")
    if len(keep) < 3:
        print("   ⚠ 预筛漏掉了大部分相关内容——中文改写让字面重叠失效。")
        print("     这里先放行全部候选，把相关性交给模型判断。")
        keep = cands
    print()

    print("③ 抽取 + 共识（3 次）")
    texts = [(c.source, c.text) for c in keep]
    ex = extract.consensus(nu, texts, runs=3, min_freq=0.6)
    print(f"   保留 {len(ex.facts)} 条稳定事实\n")

    print("④ N11 判定")
    tb_lean, tb_reason = extract.tie_break_of(nu.binary, texts)
    nd = node.build(nu.binary, ex, trace)
    j = nd.judge(tie_break_lean=tb_lean, tie_break_reason=tb_reason)
    if j is None:
        print("   节点不成立")
        return 1
    print("-" * 64)
    print(j.render())
    print("-" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
