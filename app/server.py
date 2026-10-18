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

from rongqiu import indexer, journal, node, nucleus, review, search  # noqa: E402

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
    query = f"{nu.agent} {nu.event} {nu.resource}"
    results = search.search(query, cfg)
    cands = indexer.rank(nu, results, min_hits=2)
    return {
        "nucleus": nu.as_dict(),
        "query": query,
        "provider": cfg.provider if cfg.api_key else "local",
        "candidates": [c.as_dict() for c in cands],
        "total_hits": len(results),
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
