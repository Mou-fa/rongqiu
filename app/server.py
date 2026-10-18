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
    selected: list[SelectedItem]
    assumption: str = ""
    unknown: str = ""


@app.post("/api/ask")
def api_ask(body: AskBody):
    nu = nucleus.parse(body.question)
    cfg = search.load_config()

    # 组合词展开：聚餐 → 聚会、餐厅、餐饮、饭局…
    # 目的是让整张网都成为候选库，而不是为每个事物建第一接触面数据库。
    terms = search.expand_terms(nu.resource)
    query = " ".join([nu.agent, nu.event] + terms[:10])
    results = search.search(query, cfg)
    cands = indexer.rank(nu, results, min_hits=2)

    # 系统先用 811 + REA 自己判一次，不要求用户做任何操作。
    # 「这些场景适用于我」本来就是假设槽该装的东西，系统可以自己承担这个假设。
    auto = None
    # 用户自述的处境，是整条判断里最硬的事实——来源就是当事人本人。
    stated = [review.SceneFact(scene=b.as_text(), source="用户自述",
                               order=i, depth=1, origin=-10 - i)
              for i, b in enumerate(nu.background)]
    facts = list(stated)
    facts += [review.SceneFact(scene=c.text, source=c.source,
                               order=len(stated) + i, depth=1)
              for i, c in enumerate(cands)]

    if facts:
        review.direction_of(facts, nu.binary)
        # 同源归并只作用于全网材料：用户自述的每一条都是独立的处境，
        # 不能因为「都来自用户」就被归并成一条。
        web = [f for f in facts if f.source != "用户自述"]
        mapping = origin.cluster(web) if web else {}
        for i, f in enumerate(web):
            f.origin = mapping.get(i, -1)
        nd = node.build_from_review(
            nu.binary, facts,
            assumption="全网找到的场景适用于我的情况" if web else "",
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
        "provider": cfg.provider if cfg.api_key else "local",
        "candidates": [c.as_dict() for c in cands],
        "stated": [b.as_dict() for b in nu.background],
        "total_hits": len(results),
        "auto": auto,
    }


@app.post("/api/judge")
def api_judge(body: JudgeBody):
    facts = [review.SceneFact(scene=s.text, source=s.source, order=i)
             for i, s in enumerate(body.selected)]
    nu = nucleus.Nucleus(agent="", event="", resource="", binary=body.binary)
    review.direction_of(facts, body.binary)
    assumption = body.assumption or "我点选的这几条如实反映了我的情况"
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
