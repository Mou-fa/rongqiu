"""绒球 Web 界面。

    python -m uvicorn app.server:app --host 127.0.0.1 --port 8780

三步交互：
    1. 输入一句要决定的事
    2. 系统回显它理解的原核（主谓宾），并列出命中的场景
    3. 你点选「这是我的真实情况」，系统给出二元倾向
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from rongqiu.paths import ROOT  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from rongqiu import baselines, calibration, common_root, crisis, crisis_store, drift, environment, indexer, input_layer, journal, llm, node, nucleus, origin, paths, questions, review, search, soundscape, surfaces, topology  # noqa: E402

app = FastAPI(title="绒球")
STATIC = ROOT / "app" / "static"


class AskBody(BaseModel):
    question: str
    lat: float | None = None      # 浏览器授权定位后才有
    lon: float | None = None
    region: str = ""              # 当前地区（只用于危机本地快照）


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
    asked: list[str] = []                 # 这次实际被问到的问句 id（用于算未答面 → 半知）
    assumption: str = ""
    unknown: str = ""
    user_lean: str | None = None          # 用户自己的直觉：yes / no；不选就是 None
    region: str = ""                      # 当前地区（只用于危机本地快照）


def _crisis_response(payload: dict, source: str) -> dict:
    """固定危机回应 + 本机完整快照。保存失败不影响回应。"""
    resp = crisis.response()
    try:
        saved = crisis_store.save(payload, source)
        resp["saved_locally"] = bool(saved.get("ok"))
        if saved.get("ok"):
            resp["saved_event_id"] = saved.get("event_id")
    except Exception:
        resp["saved_locally"] = False
    return resp


@app.post("/api/ask")
def api_ask(body: AskBody):
    # 安全例外：命中最优先，短路一切流程。
    # 见 docs/REDLINES.md 第三部分；先把这一刻留在本机。
    if crisis.detect(body.question):
        return _crisis_response({"question": body.question,
                                 "region": body.region}, "ask")

    offline = False
    compiled = input_layer.compile(body.question)
    try:
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
    except Exception:
        # 没有 LLM / 搜索不可用时，走确定性输入层：
        # 仍然给出 binary + 固定问句，让用户用 yes/no 完成判断。
        offline = True
        nu = input_layer.parse(body.question)
        cfg = None
        terms = []
        query = ""
        results = []
        cands = []
    if not (nu.binary or "").strip():
        nu.binary = compiled["binary"]

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
            entry = journal.record(j, body.question)
            auto = j.as_dict()
            auto["id"] = entry["id"]
            related = common_root.related_to(entry["id"])

    # 按原核挑面（M1 第三层的基础）：从问句库里挑这次最该问的 8–12 条。
    # 挑不出来时 select() 会退回整库——不把问题藏起来，也不假装知道该问什么。
    selected = input_layer.select_questions(body.question,
                                             has_history=bool(journal.load()),
                                             limit=10)
    if not selected:
        selected = questions.select(nu, has_history=bool(journal.load()), limit=10)

    provider = "local"
    if cfg is not None:
        provider = cfg.provider if (cfg.api_key or cfg.provider in ("sogou", "local")) else "local"
    return {
        "nucleus": nu.as_dict(),
        "query": query,
        "terms": terms,
        "provider": provider,
        "candidates": [c.as_dict() for c in cands],
        "stated": [b.as_dict() for b in nu.background],
        "total_hits": len(results),
        "offline": offline,
        "frame": compiled["frame"],
        "surfaces": compiled["surfaces"],
        "gaps": compiled["gaps"],
        "ir_version": compiled.get("ir_version"),
        "ir_hash": compiled.get("ir_hash"),
        "diagnostics": compiled.get("diagnostics"),
        "auto": auto,
        # 跨决定共同根因：这个决定和别的决定共享的面（只陈述，不引导）
        "related": related if stated else [],
        # 主动询问：问句来自 configs/questions.yaml，由用户确定，系统不发明。
        # 这里只返回「这次挑出来的」，不是整库。
        # 环境讯息：只给界面展示，不参与任何计数
        "env": env_text,
        "questions": [questions.render(q, nu) for q in selected],
        "probe_count": len(selected),
        # 固定询问面总数：等于问题库的词条数。用户加词条它就变，代码不写死。
        "surface_quota": questions.surface_quota(),
    }


@app.post("/api/judge")
def api_judge(body: JudgeBody):
    # 安全例外同样适用：用户的问题和自述，任何一段命中都立刻停。
    if crisis.detect_any([body.question] + [x.text for x in body.stated]):
        return _crisis_response({"question": body.question,
                                 "region": body.region}, "judge")

    # 主动询问的 yes/no 回答：方向由用户点击直接决定，不经过模型。
    # 必须单独建、单独放，不能混进 direction_of——否则用户点的 yes
    # 会被模型重新判一遍，可能改成中性甚至反对。
    binary = (body.binary or "").strip() or input_layer.binary_of(body.question)
    qa_answers = [a.model_dump() for a in body.answers]
    qa_facts = questions.answers_to_facts(qa_answers)
    surface_answers = surfaces.for_answers(qa_answers, qa_facts)

    others = [review.SceneFact(scene=s.text, source="用户自述",
                               order=i, origin=-10 - i)
              for i, s in enumerate(body.stated)]
    others += [review.SceneFact(scene=s.text, source=s.source,
                                order=len(others) + i)
               for i, s in enumerate(body.selected)]
    if others:
        review.direction_of(others, binary)
        # 认领过的事实不允许弃权：判成中性的，逼它选一边。
        # 用户点了「这是我的情况」，这件事就不可能对决定没有方向。
        review.force_binary(others, binary)

    facts = qa_facts + others
    # 主动询问的答案方向已定；但如果其他事实全被判成中性，也要兜一次
    review.force_binary(facts, binary)
    nu = nucleus.Nucleus(agent="", event="", resource="", binary=binary)
    web = [f for f in facts if f.source not in ("用户自述", "主动询问")]
    if web:
        mapping = origin.cluster(web)
        for i, f in enumerate(web):
            f.origin = mapping.get(i, -1)
    # 这次挑出来、但用户还没答的面 → 半知槽的候选。
    # 注意：这是「系统已找到、用户未确认」，不是系统替用户假设结论。
    answered_ids = {a.id for a in body.answers}
    missing = questions.unanswered(body.asked, answered_ids) if body.asked else []
    missing_domains = sorted({d for q in missing for d in q.get("domains", [])})

    if missing:
        assumption = ("系统探到、你还没确认的面："
                      + "、".join(missing_domains[:5])
                      + f"（{len(missing)} 条未答）")
    elif body.assumption:
        assumption = body.assumption
    elif body.selected:
        assumption = "我点选的这几条如实反映了我的情况"
    elif qa_facts or others:
        assumption = "我回答的和我说出的，就是这次判断的全部依据"
    else:
        assumption = "全网场景都不适用于我，只看我自己说出的处境"
    unknown = body.unknown or "当时是否存在我没考虑到的其他情况"
    nd = node.build_from_review(binary, facts, assumption=assumption,
                                unknown=unknown)
    j = nd.judge()
    if j is None:
        # 一条事实都没有：既没勾选场景，问题里也没说出自己的处境。
        # 这不是错误，只是还缺一个接触面——告诉用户怎么补，别把他堵死。
        return {"ok": False, "need": "surface",
                "message": "还没有可判断的第一接触面。勾选一条场景，"
                           "或者把你的处境写进问题里（比如「今天身体不舒服，要不要去聚餐」）。"}
    entry = journal.record(j, body.question, user_lean=body.user_lean,
                           surface_answers=surface_answers)
    # 跨决定共同根因：这个决定有没有和别的决定共享同一个面。
    # 只陈述结构，不给建议。
    related = common_root.related_to(entry["id"])
    jd = j.as_dict()
    # 校准缺口：这一类历史上的命中率 vs 平均置信度。
    # 只说「你以前是什么样」，不说「你这次该怎样」。样本不足时返回 None。
    gap = calibration.gap_for(body.question, jd.get("confidence") or 0)
    return {"ok": True, "judgment": jd, "id": entry["id"],
            "resolve_by": entry["resolve_by"], "related": related, "gap": gap,
            # 半知缺口（元信息）：这次探到、但用户没答的面
            "unanswered": [{"id": q["id"], "text": q["text"]} for q in missing],
            "missing_domains": missing_domains}


@app.get("/api/soundscape")
def api_soundscape():
    """声景库：按时刻组织的公共曲库。

    不是推荐。不做个性化，不产生使用数据，判断流程中由前端强制静音。
    违反红线的曲目会被 soundscape.check() 拒绝，不会出现在这里。
    """
    return soundscape.catalog()


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

    def due_and_days(e: dict) -> tuple[bool, int]:
        try:
            rb = datetime.fromisoformat(e.get("resolve_by", ""))
        except ValueError:
            return True, 0
        delta = (rb - now).total_seconds()
        if delta <= 0:
            return True, 0
        # 向上取整：还剩 23 小时也算「1 天后」，不能一创建就标成可回收。
        return False, max(1, int((delta + 86399) // 86400))

    def brief(e: dict) -> dict:
        due, days_left = due_and_days(e)
        return {"id": e["id"], "question": e["nucleus"], "ts": e["ts"],
                "lean": e["lean"], "confidence": e["confidence"],
                "p_yes": e.get("p_yes"), "n": e["n"],
                "resolve_by": e.get("resolve_by"),
                "days_left": days_left,
                "due": due}

    # 只给最新 revision；否则同一个决策重判几次就出现几条待回收。
    items = [brief(e) for e in journal.unresolved()]
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


class SettingsBody(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    provider: str = ""
    search_api_key: str = ""


def _read_flat(path) -> dict:
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _write_flat(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}: {v}" if v else f"{k}:" for k, v in data.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _is_local(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


@app.get("/api/settings")
def api_settings_get(request: Request):
    """读取设置。API key 只返回「是否已配置」，不返回明文。"""
    if not _is_local(request):
        return {"ok": False, "message": "设置只允许在本机访问"}
    paths.ensure_home()
    lp = paths.CONFIG / "llm.yaml"
    sp = paths.CONFIG / "search.yaml"
    llm_raw = _read_flat(lp) if lp.exists() else {}
    search_raw = _read_flat(sp) if sp.exists() else {}
    return {
        "ok": True,
        "llm": {
            "base_url": llm_raw.get("base_url", "https://api.deepseek.com"),
            "model": llm_raw.get("model", "deepseek-chat"),
            "api_key_set": bool(llm_raw.get("api_key")),
        },
        "search": {
            "provider": search_raw.get("provider", "tavily"),
            "api_key_set": bool(search_raw.get("api_key")),
        },
        "configured": bool(llm_raw.get("api_key")) or llm.available(),
    }


@app.post("/api/settings")
def api_settings_post(body: SettingsBody, request: Request):
    """保存设置到用户目录。留空的 api_key 不覆盖已保存的值。"""
    if not _is_local(request):
        return {"ok": False, "message": "设置只允许在本机访问"}
    paths.ensure_home()
    lp = paths.CONFIG / "llm.yaml"
    sp = paths.CONFIG / "search.yaml"
    old_llm = _read_flat(lp) if lp.exists() else {}
    old_search = _read_flat(sp) if sp.exists() else {}
    llm_data = {
        "base_url": body.base_url.strip() or old_llm.get("base_url", "https://api.deepseek.com"),
        "model": body.model.strip() or old_llm.get("model", "deepseek-chat"),
        "api_key": body.api_key.strip() or old_llm.get("api_key", ""),
    }
    _write_flat(lp, llm_data)
    search_data = {
        "provider": body.provider.strip() or old_search.get("provider", "tavily"),
        "api_key": body.search_api_key.strip() or old_search.get("api_key", ""),
    }
    _write_flat(sp, search_data)
    return {"ok": True, "configured": bool(llm_data["api_key"])}


@app.get("/api/app")
def api_app():
    """前端据此判断是不是桌面版（决定要不要显示退出按钮）。"""
    return {"desktop": paths.FROZEN}


@app.post("/api/shutdown")
def api_shutdown(request: Request):
    """桌面版退出：本机请求才允许。"""
    if not _is_local(request):
        return {"ok": False, "message": "只允许本机退出"}
    threading.Timer(0.4, os._exit, args=(0,)).start()
    return {"ok": True}


@app.get("/api/baselines")
def api_baselines():
    """固定知识 / 常识基线：盲猜 50%、80% 封顶、艾宾浩斯遗忘曲线。

    不是用户数据，不随用户变化；校准图用它当“世界本来是什么样”的参照。
    """
    return baselines.as_dict()


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
            # 校准图要用的：预测/实际均线、逐条序列、三方对照、相对盲猜技巧分
            "mean_p": s.get("mean_p"), "chance_brier": s.get("chance_brier", 0.25),
            "chance_skill": s.get("chance_skill"),
            "series": s.get("series", []), "three_way": s.get("three_way"),
            "surfaces": s.get("surfaces", []),
            # 按决定类型的校准缺口（立项书 6.6）
            "by_category": calibration.by_category()}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
