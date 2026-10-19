const $ = (s) => document.querySelector(s);
let STATE = { nucleus: null, candidates: [], picked: new Set(), auto: null,
              stated: [], env: [], coords: null, engaged: false, related: [] };

// 上次授权过的坐标记在本地，不用每次都问
try {
  const saved = localStorage.getItem("rq_coords");
  if (saved) STATE.coords = JSON.parse(saved);
} catch (e) { /* 忽略 */ }

function show(id) {
  ["step-ask", "step-result", "step-crisis"].forEach(s => {
    const el = document.getElementById(s);
    if (el) el.classList.toggle("hidden", s !== id);
  });
}

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return await r.json();
}

$("#btn-ask").onclick = ask;
$("#question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
});
document.querySelectorAll(".chip").forEach(b => {
  b.onclick = () => { $("#question").value = b.dataset.q; ask(); };
});

async function ask() {
  const q = $("#question").value.trim();
  if (!q) return;
  const btn = $("#btn-ask");
  btn.disabled = true; btn.textContent = "正在检索和判断…（约 20-40 秒）";
  try {
    const body = { question: q };
    if (STATE.coords) { body.lat = STATE.coords.lat; body.lon = STATE.coords.lon; }
    const d = await post("/api/ask", body);
    // 安全例外：命中最优先。不进入任何判断流程。
    if (d.crisis) { showCrisis(d); return; }
    STATE.nucleus = d.nucleus;
    STATE.candidates = d.candidates || [];
    STATE.auto = d.auto;
    STATE.related = d.related || [];
    STATE.gap = null;
    STATE.stated = d.stated || [];
    STATE.picked = new Set();
    STATE.engaged = false;   // 用户还没有任何输入，先不给倾向
    STATE.query = q;
    STATE.questions = d.questions || [];
    STATE.quota = d.surface_quota || (d.questions || []).length;
    STATE.answers = [];
    // 新问题进来，明细默认收起
    const db = $("#detail-block");
    if (db) db.classList.add("hidden");
    const dt = $("#btn-detail");
    if (dt) dt.textContent = "▸ 查看明细";
    renderAll(d);
    show("step-result");
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "开始判断";
  }
}

// 危机回应：只给渠道，不给安慰、不给分析、不给结构。
// 文案来自服务端固定内容，前端不做任何发挥。
function showCrisis(d) {
  $("#crisis-lines").innerHTML = (d.hotlines || []).map(h =>
    '<li><span class="ci-name">' + esc(h.name) + '</span>' +
    '<a class="ci-num" href="tel:' + esc(h.number) + '">' + esc(h.number) + '</a></li>'
  ).join("");
  show("step-crisis");
}

function renderAll(d) {
  const n = STATE.nucleus;

  // 原核
  $("#svo").innerHTML =
    '<span class="seg">' + esc(n.agent) + '</span><span class="sep">·</span>' +
    '<span class="seg">' + esc(n.event) + '</span><span class="sep">·</span>' +
    '<span class="seg">' + esc(n.resource) + '</span>';

  // 用户自述
  if (STATE.stated.length) {
    $("#stated-wrap").classList.remove("hidden");
    $("#stated").innerHTML = STATE.stated
      .map(b => '<div class="item">' + esc(b.agent + " " + b.event + " " + b.resource) + '</div>')
      .join("");
  } else {
    $("#stated-wrap").classList.add("hidden");
  }

  renderRelated(STATE.related);
  renderGap(STATE.gap);
  renderStructure(STATE.auto);
  renderQuestions();
  renderPrompts();
  if (d && d.env) {
    STATE.env = d.env;
    renderEnv({ facts: d.env });
  } else {
    loadEnv();
  }
}

// ---------- 环境已知面：时间 / 地区 / 天气 ----------
async function loadEnv() {
  let url = "/api/env";
  if (STATE.coords) {
    url += "?lat=" + STATE.coords.lat + "&lon=" + STATE.coords.lon;
  }
  try {
    const r = await fetch(url);
    const d = await r.json();
    STATE.env = d.facts || [];
    renderEnv(d);
  } catch (e) {
    $("#env-block").innerHTML = "";
  }
}

function renderEnv(d) {
  const box = $("#env-note");
  if (!box) return;
  const facts = (d && d.facts) || [];
  const canLocate = !!(navigator.geolocation);

  // 便签：页面一打开就有时间，不会空着等判断
  let h = '<div class="note-tape"></div>' +
          '<div class="note-title">此刻</div>';
  if (facts.length) {
    h += '<ul class="note-list">' +
      facts.map(f => '<li>' + esc(f) + '</li>').join("") + '</ul>';
  } else {
    h += '<p class="note-empty">正在取时间…</p>';
  }
  if (!STATE.coords && canLocate) {
    h += '<button id="btn-locate" class="note-btn">允许定位，补上地区和天气</button>';
  } else if (!STATE.coords) {
    h += '<p class="note-empty">浏览器不支持定位</p>';
  }
  h += '<div class="note-foot">讯息，仅供参考，不计入面数</div>';
  box.innerHTML = h;
  const b = $("#btn-locate");
  if (b) b.onclick = requestLocation;
}

function requestLocation() {
  if (!navigator.geolocation) return;
  const btn = $("#btn-locate");
  if (btn) { btn.disabled = true; btn.textContent = "正在定位…"; }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      STATE.coords = { lat: +pos.coords.latitude.toFixed(4),
                       lon: +pos.coords.longitude.toFixed(4) };
      try { localStorage.setItem("rq_coords", JSON.stringify(STATE.coords)); } catch (e) {}
      loadEnv().then(() => judgeAgain());
    },
    () => {
      if (btn) { btn.disabled = false; btn.textContent = "定位失败，点这里重试"; }
    },
    { timeout: 8000, maximumAge: 600000 }
  );
}

function renderQuestions() {
  const box = $("#ask-question");
  if (!STATE.questions || !STATE.questions.length) { box.innerHTML = ""; return; }

  // 只能二选一，不打字。
  // yes = 确定性第一接触面，no = 否定性第一接触面，方向由点击直接决定。
  box.innerHTML =
    '<div class="surfquota">固定询问面 ' + (STATE.quota || 0) +
    ' 条 · 答一条就多一个面</div>' +
    STATE.questions.map((q, i) =>
      '<div class="askcard" data-qid="' + esc(q.id) + '">' +
        '<div class="qtxt">' + esc(q.text) + '</div>' +
        '<div class="yn" data-i="' + i + '">' +
          '<button class="ynbtn" data-v="yes">是</button>' +
          '<button class="ynbtn" data-v="no">否</button>' +
        '</div>' +
      '</div>'
    ).join("");

  box.querySelectorAll(".yn").forEach(g => {
    const i = Number(g.dataset.i);
    const q = STATE.questions[i];
    g.querySelectorAll(".ynbtn").forEach(b => {
      b.onclick = async () => {
        const v = b.dataset.v;
        const cur = (STATE.answers || []).find(a => a.id === q.id);
        if (cur && cur.answer === v) {
          // 再点一次取消，支持来回比对
          STATE.answers = STATE.answers.filter(a => a.id !== q.id);
        } else {
          STATE.answers = (STATE.answers || []).filter(a => a.id !== q.id);
          STATE.answers.push({ id: q.id, answer: v });
        }
        paintAnswers();
        updateBar();
        await judgeAgain();
      };
    });
  });
  paintAnswers();
}

function paintAnswers() {
  document.querySelectorAll("#ask-question .askcard").forEach((card, i) => {
    const q = STATE.questions[i];
    const a = (STATE.answers || []).find(x => x.id === q.id);
    card.querySelectorAll(".ynbtn").forEach(b => {
      b.classList.toggle("on", !!a && a.answer === b.dataset.v);
      b.classList.toggle("yes", b.dataset.v === "yes");
      b.classList.toggle("no", b.dataset.v === "no");
    });
  });
}

function renderStructure(j) {
  const box = $("#structure");
  if (!j) {
    box.innerHTML = '<p class="hint">你没有在问题里说出自己的处境，所以系统没有可判定的' +
      '第一接触面。下面是从网上找到的、可能符合你的情况——点选之后加入判断。</p>';
    return;
  }
  const sp = j.split || { determinable: j.determinability, assumption: 0.1, unknown: 0.1 };
  const c = j.counts || {
    support: j.facts.filter(f => f.supports === "support").length,
    oppose: j.facts.filter(f => f.supports === "oppose").length,
    neutral: j.facts.filter(f => f.supports !== "support" && f.supports !== "oppose").length,
  };
  const total = j.total_surfaces || (j.n + 2);
  box.innerHTML =
    '<div class="metrics">' +
    metric("第一接触面", total) +
    metric("可确定", Math.round(sp.determinable * 100) + "%") +
    metric("支持/反对/中性", c.support + "/" + c.oppose + "/" + c.neutral) +
    '</div>' +
    '<div class="split-line">中性只存在于 11（半知+未知）· ' +
    '811 结构：可确定 ' + Math.round(sp.determinable * 100) +
    '% · 半知 ' + Math.round(sp.assumption * 100) +
    '% · 未知 ' + Math.round(sp.unknown * 100) +
    '%   链长 ' + (j.max_depth || 1) + '</div>' +
    (j.dropped > 0
      ? '<div class="dropline">有 ' + j.dropped + ' 条场景判不出方向，未计入' +
        '（事实层只允许二元对立）</div>'
      : '') +
    (j.assumption ? '<div class="slots"><div class="slot"><b>半知</b>　' + esc(j.assumption) + '</div></div>' : '') +
    (j.unknown ? '<div class="slots"><div class="slot"><b>未知</b>　' + esc(j.unknown) + '</div></div>' : '');

  // 倾向不放在结构块里了——它挪到底部操作栏，紧挨着按钮。
  // 这样「结构」区永远是纯事实，结论单独待在一个位置。
  STATE.lastJudgment = j;
  updateVerdict();
}

// 把参考倾向填进底部操作栏。
// 只在用户真的动过之后才出现：测试还没开始就给出「更可能是：不会」，
// 会被读成一个已经判完的结论，那是误导。
function updateVerdict() {
  const el = document.getElementById("verdict");
  if (!el) return;
  const j = STATE.lastJudgment;
  if (!j || !STATE.engaged) {
    el.innerHTML = "";
    return;
  }
  const yes = j.lean === "yes";
  // 结论是主角，按钮是配角。
  el.innerHTML =
    '<b style="color:' + (yes ? "var(--accent)" : "var(--warn)") + '">' +
    (yes ? "更可能是：会" : "更可能是：不会") + '</b>' +
    '<span class="vconf">置信 ' + (j.confidence * 100).toFixed(0) + '%</span>';
}

function renderPrompts() {
  const box = $("#prompts");
  if (!STATE.candidates.length) { box.innerHTML = ""; return; }
  box.innerHTML =
    '<div class="label" style="margin-top:22px">这些可能也是你的情况</div>' +
    '<p class="hint">从全网找到的原文，已浓缩成一句话。本身不算证据，' +
    '点选真正符合你的，才加入判断。</p>' +
    '<div class="cands" id="cand-list"></div>' +
    // 结论独立成块，不放在操作行里。
    // 放在 flex 行里时，窄屏下它会被压缩裁掉、按钮会被挤出屏幕。
    '<div id="verdict" class="verdict-block"></div>' +
    '<div class="bar">' +
      '<span id="picked-count">已选 0 条</span>' +
      '<button id="btn-judge" class="bar-btn">加入判断</button>' +
    '</div>' +
    '<div id="judge-note" class="judge-note hidden"></div>';
  const list = $("#cand-list");
  STATE.candidates.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "cand";
    el.innerHTML = '<div class="box">✓</div><div><div class="txt">' + esc(truncate(c.text, 90)) +
      '</div><div class="src">命中 ' + c.hits + '/3 成分 · 原文已浓缩</div></div>';
    el.onclick = () => {
      if (STATE.picked.has(i)) STATE.picked.delete(i); else STATE.picked.add(i);
      el.classList.toggle("on");
      updateBar();
    };
    list.appendChild(el);
  });
  $("#btn-judge").onclick = judgeAgain;
  updateBar();
  updateVerdict();
}

// 跨决定共同根因：只陈述「这几个决定共享同一个面」。
// 绝不写「所以你应该先解决它」——那是建议，不是结构。
function renderRelated(list) {
  const box = $("#related-block");
  if (!box) return;
  const r = (list || [])[0];
  if (!r) { box.innerHTML = ""; return; }
  box.innerHTML =
    '<div class="rel-card">' +
      '<div class="label">跨决定</div>' +
      '<p class="rel-lead">这个判断和另外 ' + r.count + ' 个决定，共享同一个面：</p>' +
      '<p class="rel-surface">「' + esc(r.surface) + '」</p>' +
      '<ul class="rel-list">' +
        (r.decisions || []).map(d =>
          '<li>' + esc(truncate(d.question, 42)) + '</li>').join("") +
      '</ul>' +
    '</div>';
}

// 校准缺口：只用陈述句。
// 不写「所以你应该降低预期」——那是建议。写「你给了 90%，过去同类命中 0%」。
function renderGap(g) {
  const box = $("#gap-block");
  if (!box) return;
  if (!g) { box.innerHTML = ""; return; }
  const dir = g.direction === "over" ? "高估" : "低估";
  box.innerHTML =
    '<div class="gap-card">' +
      '<div class="label">校准缺口</div>' +
      '<p class="gap-line">' +
        '这一类（' + esc(g.category) + '）你给了 <b>' +
        Math.round(g.current_confidence * 100) + '%</b> 的把握。' +
      '</p>' +
      '<p class="gap-hist">过去 ' + g.samples + ' 条同类判断，你平均给 ' +
        Math.round(g.mean_confidence * 100) + '%，实际命中 ' +
        Math.round(g.hit_rate * 100) + '%。' +
      '</p>' +
      '<p class="gap-tag">方向：' + dir + '</p>' +
    '</div>';
}

function updateBar() {
  const nSel = STATE.picked.size;
  const nAns = (STATE.answers || []).length;
  const c = $("#picked-count");
  const b = $("#btn-judge");

  // 文案必须说真话：当前判断里到底包含什么。
  // 第一版不管有没有答过询问，0 条时一律写「只用你自己的处境」，
  // 但那时明明已经答过两条——文案在撒谎。
  if (c) {
    const parts = [];
    if (nSel > 0) parts.push("已选 " + nSel + " 条");
    else parts.push("已选 0 条");
    if (nAns > 0) parts.push(nAns + " 条询问回答");
    parts.push(nSel === 0 && nAns === 0 ? "只用你自己说出的处境" : "");
    c.textContent = parts.filter(Boolean).join(" · ");
  }

  if (!b) return;
  // 永远可点：用户要来回比对，不能因为取消到 0 条就锁死。
  b.disabled = false;
  // 什么输入都没有时，这个按钮的语义是「重算」——
  // 算出来的结果和初始状态一样，所以倾向也应该收起来。
  b.textContent = (nSel === 0 && nAns === 0) ? "重算"
                 : (nSel === 0 ? "用询问回答重算" : "加入判断");
}

function supportSplit(j) {
  const s = j.facts.filter(f => f.supports === "support").length;
  const o = j.facts.filter(f => f.supports === "oppose").length;
  return s + " / " + o;
}

function metric(k, v) {
  return '<div class="metric"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>';
}

async function judgeAgain() {
  // 只有真的提供了输入（勾了场景或答了询问），才算用户参与过。
  // 什么都没选就点「重算」，出来的结果和初始状态一样，
  // 那就不该显示倾向——否则「还原」会还原出一个结论来。
  STATE.engaged = (STATE.picked.size > 0 || (STATE.answers || []).length > 0);

  const selected = [...STATE.picked].sort((a, b) => a - b)
    .map(i => ({ text: STATE.candidates[i].text, source: STATE.candidates[i].source }));
  const stated = STATE.stated.map(b => ({
    text: b.agent + " " + b.event + " " + b.resource,
  }));
  try {
    const d = await post("/api/judge", {
      question: STATE.query, binary: STATE.nucleus.binary,
      selected, stated,
      answers: STATE.answers || [],
    });
    if (!d.ok) {
      // 不弹窗，也不清空已有结果——只在候选区下面给一句能照做的话。
      const note = $("#judge-note");
      if (note) {
        note.textContent = d.message || "还没有可判断的第一接触面。";
        note.classList.remove("hidden");
      }
      return;
    }
    const note = $("#judge-note");
    if (note) note.classList.add("hidden");
    STATE.auto = d.judgment;
    STATE.related = d.related || [];
    renderRelated(STATE.related);
    renderGap(d.gap || null);
    renderStructure(d.judgment);
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    updateBar();
  }
}

// 明细默认收起：结论和操作在上半屏，明细要看再点开
$("#btn-detail").onclick = () => {
  const box = $("#detail-block");
  const btn = $("#btn-detail");
  const willOpen = box.classList.contains("hidden");
  box.classList.toggle("hidden", !willOpen);
  btn.textContent = willOpen ? "▾ 收起明细" : "▸ 查看明细";
};

$("#btn-crisis-back").onclick = () => {
  $("#question").value = "";
  show("step-ask");
};

$("#btn-again").onclick = () => {
  $("#question").value = "";
  // 下次进来明细保持收起
  $("#detail-block").classList.add("hidden");
  $("#btn-detail").textContent = "▸ 查看明细";
  show("step-ask");
  $("#question").focus();
};

function truncate(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

show("step-ask");
loadEnv();                 // 便签先出时间，不等判断

const TAB0 = (location.hash || "").replace("#", "");
if (TAB0 === "pending" || TAB0 === "stats") switchTab(TAB0);

const Q0 = new URLSearchParams(location.search).get("q");
if (Q0) { $("#question").value = Q0; ask(); }
// ---------- 标签页 ----------
function switchTab(name) {
  document.querySelectorAll(".tabs button").forEach(b => {
    b.classList.toggle("on", b.dataset.tab === name);
  });
  ["ask", "pending", "stats"].forEach(t => {
    const sec = t === "ask"
      ? document.getElementById("step-ask")
      : document.getElementById("step-" + t);
    if (sec) sec.classList.toggle("hidden", t !== name);
  });
  if (name === "pending") loadPending();
  if (name === "stats") loadStats();
}

document.querySelectorAll(".tabs button").forEach(b => {
  b.onclick = () => switchTab(b.dataset.tab);
});

// ---------- 回收 ----------
async function loadPending() {
  const box = document.getElementById("pending-list");
  box.innerHTML = '<p class="hint">加载中…</p>';
  try {
    const r = await fetch("/api/pending");
    const d = await r.json();
    const badge = document.getElementById("due-badge");
    if (d.due > 0) { badge.textContent = d.due; badge.classList.remove("hidden"); }
    else badge.classList.add("hidden");

    if (!d.items.length) {
      box.innerHTML = '<p class="hint">没有待回收的判断。先去做几个判断吧。</p>';
      return;
    }
    box.innerHTML = "";
    d.items.forEach(e => {
      const el = document.createElement("div");
      el.className = "pend" + (e.due ? " due" : "");
      const when = e.due ? "现在可以回收" : e.days_left + " 天后可回收";
      el.innerHTML =
        '<div class="q">' + esc(e.question) + '</div>' +
        '<div class="meta">系统当初判断 <b>' + (e.lean === "yes" ? "会" : "不会") +
        '</b> · 置信 ' + Math.round(e.confidence * 100) + '% · ' +
        (e.n + 2) + ' 个面 · ' + when + '</div>' +
        '<div class="acts">' +
        (e.due
          ? '<button class="mini yes">这件事发生了</button>' +
            '<button class="mini no">没有发生</button>'
          : '<span class="wait">等时间到</span>') +
        '</div>';
      if (e.due) {
        el.querySelector(".yes").onclick = () => doResolve(e.id, "yes", el);
        el.querySelector(".no").onclick = () => doResolve(e.id, "no", el);
      }
      box.appendChild(el);
    });
  } catch (err) {
    box.innerHTML = '<p class="hint">加载失败：' + esc(err.message) + '</p>';
  }
}

async function doResolve(id, outcome, el) {
  try {
    const r = await fetch("/api/resolve", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, outcome, note: "" }),
    });
    const d = await r.json();
    if (!d.ok) { alert(d.message); return; }
    el.classList.add("done");
    el.querySelector(".acts").innerHTML =
      '<span class="ok">已记录：' + (outcome === "yes" ? "发生了" : "没有发生") + '</span>';
    loadStats();
  } catch (err) { alert("出错了：" + err.message); }
}

// ---------- 校准 ----------

// 跨决定共同根因的全量视图。
// 只列「哪些决定共享同一个面」。不写「所以该先解决它」。
async function loadCommonRoots() {
  const box = document.getElementById("common-root-body");
  if (!box) return;
  try {
    const r = await fetch("/api/common-root");
    const d = await r.json();
    if (!d.total) {
      box.innerHTML = '<p class="hint">还没有出现「共享同一个面」的不同决定。' +
        '多做几次判断、让它们各自说出处境的细节，这里会慢慢长出来。</p>';
      return;
    }
    let h = '<p class="hint" style="margin-bottom:14px">' +
      '下面每组决定，看起来各不相同，但共享同一个第一接触面。</p>';
    d.groups.slice(0, 8).forEach(g => {
      h += '<div class="crg">' +
        '<div class="crg-head"><span class="crg-surface">「' + esc(g.surface) + '」</span>' +
        '<span class="crg-count">' + g.count + ' 个决定</span></div>' +
        '<ul class="crg-list">' +
        g.decisions.map(x => '<li>' + esc(truncate(x.question, 46)) + '</li>').join("") +
        '</ul></div>';
    });
    h += '<p class="hint" style="margin-top:14px">' +
      '同一个面出现在多个决定里，是结构事实，不是建议。</p>';
    box.innerHTML = h;
  } catch (err) {
    box.innerHTML = '<p class="hint">加载失败：' + esc(err.message) + '</p>';
  }
}

// 决策拓扑：只画「谁影响谁」。
// 不写「所以先做上游那个」——那是建议，不是结构。
async function loadTopology() {
  const box = document.getElementById("topology-body");
  if (!box) return;
  try {
    const r = await fetch("/api/topology");
    const d = await r.json();
    if (!d.total_edges) {
      box.innerHTML = '<p class="hint">还没有发现决定之间的依赖。' +
        '当一个决定的结果出现在另一个决定的处境里，这里会连起来。</p>';
      return;
    }
    let h = '<p class="hint" style="margin-bottom:14px">' +
      '下面这些决定不是独立的：一个的结果，会变成另一个的接触面。</p>';
    h += '<div class="topo-chains">';
    d.edges.slice(0, 6).forEach(e => {
      h += '<div class="topo-edge">' +
        '<div class="topo-node">' + esc(truncate(e.from_q, 40)) + '</div>' +
        '<div class="topo-arrow">↓<span>因为「' + esc(e.via) + '」出现在下一个决定的处境里</span></div>' +
        '<div class="topo-node">' + esc(truncate(e.to_q, 40)) + '</div>' +
        '</div>';
    });
    h += '</div>';
    if (d.cycles && d.cycles.length) {
      h += '<div class="topo-cycle"><div class="label">互相依赖</div>' +
        '<p class="hint">下面这些决定彼此影响，没有先后可言。' +
        '这不是错误，是一种需要被看到的状态。</p><ul class="crg-list">' +
        d.cycles.map(c => '<li>' + esc(truncate(c.question, 46)) + '</li>').join("") +
        '</ul></div>';
    }
    box.innerHTML = h;
  } catch (err) {
    box.innerHTML = '<p class="hint">加载失败：' + esc(err.message) + '</p>';
  }
}

async function loadStats() {
  loadCommonRoots();
  loadTopology();
  const box = document.getElementById("stats-body");
  try {
    const r = await fetch("/api/stats");
    const s = await r.json();
    if (!s.resolved) {
      box.innerHTML = '<p class="hint">还没有回收的结果。先去「回收」页回答几条——' +
        '校准需要时间，这是正常的。</p>' +
        '<div class="metrics">' +
        metric("判断总数", s.total) + metric("待回收", s.pending) +
        metric("已回收", s.resolved) + '</div>';
      return;
    }
    const gap = s.calibration_gap;
    const gapTxt = gap > 0.05 ? "你比自己以为的<b>更准</b>"
      : gap < -0.05 ? "你<b>过度自信</b>了" : "你的置信度校准得不错";
    let h = '<div class="metrics">' +
      metric("已回收", s.resolved) +
      metric("命中率", Math.round(s.hit_rate * 100) + "%") +
      metric("平均置信", Math.round(s.mean_confidence * 100) + "%") +
      '</div>';
    h += '<div class="gapbox">校准偏差 <b>' + (gap >= 0 ? "+" : "") +
      Math.round(gap * 100) + '%</b>　' + gapTxt + '</div>';
    h += '<div class="split-line">Brier ' + s.brier.toFixed(3) +
      ' · 基准 ' + s.baseline_brier.toFixed(3) +
      ' · 技巧分 ' + (s.skill === null ? "—" : s.skill.toFixed(3)) + '</div>';

    if (s.reliability && s.reliability.length) {
      h += '<div class="label" style="margin-top:20px">可靠性曲线</div>';
      h += '<div class="rel">';
      s.reliability.forEach(b => {
        const pm = Math.round(b.p_mean * 100), ob = Math.round(b.obs * 100);
        h += '<div class="relrow"><span class="relk">预测 ' + pm + '%</span>' +
          '<span class="bars"><i style="width:' + pm + '%"></i>' +
          '<em style="width:' + ob + '%"></em></span>' +
          '<span class="relv">实际 ' + ob + '%</span></div>';
      });
      h += '</div><p class="hint">灰条比彩条低 = 过度自信；高 = 保守。</p>';
    }

    if (s.by_n && s.by_n.length) {
      h += '<div class="label" style="margin-top:20px">按面数分组（811 检验）</div>';
      h += '<div class="tbl"><div class="tr th"><span>面数</span>' +
        '<span>样本</span><span>可确定</span><span>命中率</span><span>偏差</span></div>';
      s.by_n.forEach(b => {
        const d = b.hit_rate - b.determinability;
        h += '<div class="tr"><span>' + (b.n + 2) + '</span><span>' + b.count +
          '</span><span>' + Math.round(b.determinability * 100) + '%</span><span>' +
          Math.round(b.hit_rate * 100) + '%</span><span class="' +
          (d >= 0 ? "pos" : "neg") + '">' + (d >= 0 ? "+" : "") +
          Math.round(d * 100) + '%</span></div>';
      });
      h += '</div><p class="hint">811 的检验：N=8 那行的命中率，应该接近 80%。</p>';
    }
    if (s.by_category && s.by_category.length) {
      h += '<div class="label" style="margin-top:20px">按决定类型</div>';
      h += '<div class="tbl"><div class="tr th"><span>类型</span>' +
        '<span>样本</span><span>平均置信</span><span>命中率</span><span>缺口</span></div>';
      s.by_category.forEach(c => {
        const g = Math.round((c.gap || 0) * 100);
        h += '<div class="tr"><span>' + esc(c.category) + '</span>' +
          '<span>' + c.samples + '</span>' +
          '<span>' + Math.round((c.mean_confidence || 0) * 100) + '%</span>' +
          '<span>' + Math.round((c.hit_rate || 0) * 100) + '%</span>' +
          '<span class="' + (g >= 0 ? "pos" : "neg") + '">' +
          (g >= 0 ? "+" : "") + g + '%</span></div>';
      });
      h += '</div><p class="hint">缺口 = 命中率 − 平均置信。负数 = 高估自己。' +
        ' 少于 5 条样本的类型不预警。</p>';
    }
    box.innerHTML = h;
  } catch (err) {
    box.innerHTML = '<p class="hint">加载失败：' + esc(err.message) + '</p>';
  }
}

// 启动时看一下有没有到期的
fetch("/api/pending").then(r => r.json()).then(d => {
  const badge = document.getElementById("due-badge");
  if (d.due > 0) { badge.textContent = d.due; badge.classList.remove("hidden"); }
}).catch(() => {});
