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

from rongqiu import calibration, common_root, crisis, drift, environment, indexer, journal, node, nucleus, origin, questions, review, search, topology  # noqa: E402

app = FastAPI(title="绒球")
STATIC = ROOT / "app" / "static"


class AskBody(BaseModel):
    question: str
    lat: float | None = None      # 浏览器授权定位后才有
    lon: float | None = None


class SelectedItem(BaseModel):
    text: str
    source: str = "web"


@app.get("/api/env")
def api_env(lat: float | None = None, lon: float | None = None):
    """环境已知面：时间永远有，天气和地区要坐标。"""
    return environment.collect(lat, lon)


class AnswerItem(BaseModel):
    id: str
    answer: str = ""      # "yes" | "no"


class JudgeBody(BaseModel):
    question: str
    binary: str
    selected: list[SelectedItem] = []     # 用户认领的全网场景
    stated: list[SelectedItem] = []       # 用户自述（自动带入）
    answers: list[AnswerItem] = []        # 主动询问的 yes/no 回答
    assumption: str = ""
    unknown: str = ""


@app.post("/api/ask")
def api_ask(body: AskBody):
    # 安全例外：命中最优先，短路一切流程。
    # 见 docs/REDLINES.md 第三部分。
    if crisis.detect(body.question):
        return crisis.response()

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
    related: list = []
    # 自动判定只用「用户自述」——那是他自己身上正在发生的事，是最硬的事实。
    #
    # 全网找到的内容是【提示】，不是证据：它们是文章、观点、统计，
    # 属于别人的东西。按原则它们零权重，只作为镜子给用户看，
    # 用户认领了才升级成事实。
    # 环境信息（时间 / 地区 / 天气）：只展示，不进判断。
    #
    # 它是讯息，不是工作内容。用户看到「现在是深夜 3 点，外面下着毛毛雨」
    # 自己会有判断，但系统不替他把天气换算成一个「面」——
    # 那会把客观信息硬拗成方向，是编造。
    env_text = environment.collect(body.lat, body.lon)["facts"]

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
            related = common_root.related_to(entry["id"])

    return {
        "nucleus": nu.as_dict(),
        "query": query,
        "terms": terms,
        "provider": cfg.provider if (cfg.api_key or cfg.provider in ("sogou", "local")) else "local",
        "candidates": [c.as_dict() for c in cands],
        "stated": [b.as_dict() for b in nu.background],
        "total_hits": len(results),
        "auto": auto,
        # 跨决定共同根因：这个决定和别的决定共享的面（只陈述，不引导）
        "related": related if stated else [],
        # 主动询问：问句来自 configs/questions.yaml，由用户确定，系统不发明。
        # 只问「发生过的、能被看见的」——不问为什么。
        # 环境讯息：只给界面展示，不参与任何计数
        "env": env_text,
        "questions": questions.for_nucleus(nu, has_history=bool(journal.load())),
        # 固定询问面总数：等于问题库的词条数。用户加词条它就变，代码不写死。
        "surface_quota": questions.surface_quota(),
    }


@app.post("/api/judge")
def api_judge(body: JudgeBody):
    # 安全例外同样适用：任何一步输入命中，都立刻停。
    if crisis.detect(body.question):
        return crisis.response()

    # 主动询问的 yes/no 回答：方向由用户点击直接决定，不经过模型。
    # 必须单独建、单独放，不能混进 direction_of——否则用户点的 yes
    # 会被模型重新判一遍，可能改成中性甚至反对。
    qa_facts = questions.answers_to_facts([a.model_dump() for a in body.answers])

    others = [review.SceneFact(scene=s.text, source="用户自述",
                               order=i, origin=-10 - i)
              for i, s in enumerate(body.stated)]
    others += [review.SceneFact(scene=s.text, source=s.source,
                                order=len(others) + i)
               for i, s in enumerate(body.selected)]
    if others:
        review.direction_of(others, body.binary)
        # 认领过的事实不允许弃权：判成中性的，逼它选一边。
        # 用户点了「这是我的情况」，这件事就不可能对决定没有方向。
        review.force_binary(others, body.binary)

    facts = qa_facts + others
    # 主动询问的答案方向已定；但如果其他事实全被判成中性，也要兜一次
    review.force_binary(facts, body.binary)
    nu = nucleus.Nucleus(agent="", event="", resource="", binary=body.binary)
    web = [f for f in facts if f.source not in ("用户自述", "主动询问")]
    if web:
        mapping = origin.cluster(web)
        for i, f in enumerate(web):
            f.origin = mapping.get(i, -1)
    if body.assumption:
        assumption = body.assumption
    elif body.selected:
        assumption = "我点选的这几条如实反映了我的情况"
    elif qa_facts or others:
        assumption = "我回答的和我说出的，就是这次判断的全部依据"
    else:
        assumption = "全网场景都不适用于我，只看我自己说出的处境"
    unknown = body.unknown or "当时是否存在我没考虑到的其他情况"
    nd = node.build_from_review(body.binary, facts, assumption=assumption,
                                unknown=unknown)
    j = nd.judge()
    if j is None:
        # 一条事实都没有：既没勾选场景，问题里也没说出自己的处境。
        # 这不是错误，只是还缺一个接触面——告诉用户怎么补，别把他堵死。
        return {"ok": False, "need": "surface",
                "message": "还没有可判断的第一接触面。勾选一条场景，"
                           "或者把你的处境写进问题里（比如「今天身体不舒服，要不要去聚餐」）。"}
    entry = journal.record(j, body.question, resolve_days=7)
    # 跨决定共同根因：这个决定有没有和别的决定共享同一个面。
    # 只陈述结构，不给建议。
    related = common_root.related_to(entry["id"])
    jd = j.as_dict()
    # 校准缺口：这一类历史上的命中率 vs 平均置信度。
    # 只说「你以前是什么样」，不说「你这次该怎样」。样本不足时返回 None。
    gap = calibration.gap_for(body.question, jd.get("confidence") or 0)
    return {"ok": True, "judgment": jd, "id": entry["id"],
            "resolve_by": entry["resolve_by"], "related": related, "gap": gap}


@app.get("/api/drift")
def api_drift():
    """判断漂移：同一个决定隔了一段时间又判一次，两次之间什么变了。

    只陈述差异。两次判断没有哪个更对。
    """
    items = drift.detect()
    return {"items": items, "total": len(items)}


@app.get("/api/topology")
def api_topology():
    """决策拓扑：哪些决定之间有依赖，谁在最上游。

    只画结构。不排优先级，不说「所以先做哪个」。
    原核解析有缓存（data/nucleus_cache.json），第一次会慢，之后是纯读文件。
    """
    return topology.analyze()


@app.get("/api/common-root")
def api_common_root(days: int = 90):
    """跨决定共同根因：哪几个决定其实共享同一个第一接触面。

    只陈述结构。不说「所以你该先解决它」——那是建议，不是判断。
    """
    groups = common_root.all_groups(days=days)
    return {"groups": groups, "total": len(groups)}


@app.get("/api/pending")
def api_pending():
    """待回收的判断：到期的排前面，未到期的也列出来（标注还有几天）。"""
    from datetime import datetime
    now = datetime.now().astimezone()

    def days_left(e: dict) -> int:
        try:
            rb = datetime.fromisoformat(e.get("resolve_by", ""))
            return max(0, (rb - now).days)
        except ValueError:
            return 0

    def brief(e: dict) -> dict:
        return {"id": e["id"], "question": e["nucleus"], "ts": e["ts"],
                "lean": e["lean"], "confidence": e["confidence"],
                "p_yes": e.get("p_yes"), "n": e["n"],
                "resolve_by": e.get("resolve_by"),
                "days_left": days_left(e),
                "due": days_left(e) == 0}

    items = [brief(e) for e in journal.load() if e.get("outcome") is None]
    items.sort(key=lambda x: (not x["due"], x["days_left"]))
    return {"items": items[:60], "due": len([x for x in items if x["due"]]),
            "total": len(items)}


class ResolveBody(BaseModel):
    id: str
    outcome: str          # yes = 原核成立（事情发生了）；no = 没发生
    note: str = ""


@app.post("/api/resolve")
def api_resolve(body: ResolveBody):
    try:
        e = journal.resolve(body.id, body.outcome, body.note)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    if e is None:
        return {"ok": False, "message": "找不到这条判断"}
    return {"ok": True, "entry": {"id": e["id"], "outcome": e["outcome"]},
            "stats": journal.stats()}


@app.get("/api/stats")
def api_stats():
    s = journal.stats()
    return {"total": s["total"], "resolved": s["resolved"],
            "pending": s["pending"], "skill": s["skill"],
            "hit_rate": s["hit_rate"], "brier": s["brier"],
            "baseline_brier": s["baseline_brier"],
            "mean_confidence": s["mean_confidence"],
            "calibration_gap": s["calibration_gap"],
            "reliability": s["reliability"], "by_n": s["by_n"],
            "by_rule": s["by_rule"], "base_rate": s.get("base_rate"),
            # 按决定类型的校准缺口（立项书 6.6）
            "by_category": calibration.by_category()}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
