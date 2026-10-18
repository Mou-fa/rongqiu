"""绒球 Web 界面。

    python -m uvicorn app.server:app --host 127.0.0.1 --port 8780

三步交互：
    1. 输入一句要决定的事
    2. 系统回显它理解的原核（主谓宾），并列出命中的场景
    3. 你点选「这是我的真实情况」，系统给出二元倾向
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from rongqiu import indexer, journal, node, nucleus, origin, review, search  # noqa: E402

app = FastAPI(title="绒球")
STATIC = ROOT / "app" / "static"


class AskBody(BaseModel):
    question: str


class SelectedItem(BaseModel):
    text: str
    source: str = "web"


class JudgeBody(BaseModel):
    question: str
    binary: str
    selected: list[SelectedItem]          # 用户认领的全网场景
    stated: list[SelectedItem] = []       # 用户自述（自动带入）
    assumption: str = ""
    unknown: str = ""


@app.post("/api/ask")
def api_ask(body: AskBody):
    nu = nucleus.parse(body.question)
    cfg = search.load_config()

    # 组合词展开：聚餐 → 聚会、餐厅、餐饮、饭局…
    # 目的是让整张网都成为候选库，而不是为每个事物建第一接触面数据库。
    terms = search.expand_terms(nu.resource)
    query = " ".join(terms[:10])
    # 每个组合词单独搜，合并去重。塞进一个查询会被搜索引擎截断。
    results = search.multi_search(terms, event=nu.event, cfg=cfg)
    # min_hits 交给 indexer 的默认值（1）——真正的相关性判据是「共享资源」，
    # 不是「命中几个成分」。写死 2 会把只出现资源的文章全筛掉。
    cands = indexer.rank(nu, results)

    # 系统先用 811 + REA 自己判一次，不要求用户做任何操作。
    # 「这些场景适用于我」本来就是假设槽该装的东西，系统可以自己承担这个假设。
    auto = None
    # 自动判定只用「用户自述」——那是他自己身上正在发生的事，是最硬的事实。
    #
    # 全网找到的内容是【提示】，不是证据：它们是文章、观点、统计，
    # 属于别人的东西。按原则它们零权重，只作为镜子给用户看，
    # 用户认领了才升级成事实。
    stated = [review.SceneFact(scene=b.as_text(), source="用户自述",
                               order=i, depth=1, origin=-10 - i)
              for i, b in enumerate(nu.background)]

    if stated:
        review.direction_of(stated, nu.binary)
        nd = node.build_from_review(
            nu.binary, stated,
            assumption="",
            unknown="我这次的具体情况，以及我还没说出来的约束")
        j = nd.judge()
        if j is not None:
            entry = journal.record(j, body.question, resolve_days=7)
            auto = j.as_dict()
            auto["id"] = entry["id"]

    return {
        "nucleus": nu.as_dict(),
        "query": query,
        "terms": terms,
        "provider": cfg.provider if (cfg.api_key or cfg.provider in ("sogou", "local")) else "local",
        "candidates": [c.as_dict() for c in cands],
        "stated": [b.as_dict() for b in nu.background],
        "total_hits": len(results),
        "auto": auto,
    }


@app.post("/api/judge")
def api_judge(body: JudgeBody):
    facts = [review.SceneFact(scene=s.text, source="用户自述", order=i,
                              origin=-10 - i)
             for i, s in enumerate(body.stated)]
    facts += [review.SceneFact(scene=s.text, source=s.source,
                               order=len(facts) + i)
              for i, s in enumerate(body.selected)]
    nu = nucleus.Nucleus(agent="", event="", resource="", binary=body.binary)
    review.direction_of(facts, body.binary)
    web = [f for f in facts if f.source != "用户自述"]
    if web:
        mapping = origin.cluster(web)
        for i, f in enumerate(web):
            f.origin = mapping.get(i, -1)
    if body.assumption:
        assumption = body.assumption
    elif body.selected:
        assumption = "我点选的这几条如实反映了我的情况"
    else:
        assumption = "全网场景都不适用于我，只看我自己说出的处境"
    unknown = body.unknown or "当时是否存在我没考虑到的其他情况"
    nd = node.build_from_review(body.binary, facts, assumption=assumption,
                                unknown=unknown)
    j = nd.judge()
    if j is None:
        return {"ok": False, "message": "选中的场景里没有方向性证据，节点不成立。"}
    entry = journal.record(j, body.question, resolve_days=7)
    return {"ok": True, "judgment": j.as_dict(), "id": entry["id"],
            "resolve_by": entry["resolve_by"]}


@app.get("/api/stats")
def api_stats():
    from dataclasses import asdict
    s = journal.stats()
    return {"total": s["total"], "resolved": s["resolved"],
            "pending": s["pending"], "skill": s["skill"],
            "hit_rate": s["hit_rate"], "brier": s["brier"]}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
