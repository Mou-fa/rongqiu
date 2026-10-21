const $ = (s) => document.querySelector(s);
// 声景是否已加载。必须在这里声明——放在 switchTab 后面会踩 TDZ：
// 页面带 #soundscape 进来时，switchTab 在变量初始化之前就调用了 loadSoundscape。
let SS_LOADED = false;
let STATE = { nucleus: null, candidates: [], picked: new Set(), auto: null,
              stated: [], env: [], coords: null, engaged: false, related: [],
              // 上一次计算时用的输入快照。用来判断「现在选的这些，算进去了没有」。
              // 没有它的时候，界面会显示「已选 2 条」但数字还是上一次的——
              // 文案在说谎，这和之前「还原判断」那个 bug 是同一类。
              computedSig: null, userLean: null };

// 上次授权过的坐标记在本地，不用每次都问
try {
  const saved = localStorage.getItem("rq_coords");
  if (saved) STATE.coords = JSON.parse(saved);
} catch (e) { /* 忽略 */ }

// ---------------------------------------------------------------
// 声景播放器。
//
// 它只有一个职责：确保声音不会跑到判断流程里去。
// 音乐改变情绪，情绪改变判断——那不叫氛围，那叫污染。
//
// 所以：离开声景页立刻停；开始判断立刻停；出结果立刻停；危机界面立刻停。
// ---------------------------------------------------------------
const SOUND = {
  el: null,
  url: "",
  stop() {
    if (this.el) {
      try { this.el.pause(); this.el.currentTime = 0; } catch (e) { /* 忽略 */ }
    }
    this.url = "";
  },
  play(track) {
    if (!track || !track.url) return false;
    if (!this.el) { this.el = new Audio(); }
    if (this.url !== track.url) { this.el.src = track.url; this.url = track.url; }
    this.el.play().catch(() => { /* 浏览器不允许自动播放时静默失败 */ });
    return true;
  },
  playing() { return !!(this.el && !this.el.paused); },
};

// 输入快照：勾选了哪些场景、答了哪些问句。
// 用它对比「当前输入」和「上次计算用的输入」。
function inputSig() {
  return JSON.stringify({
    picked: [...(STATE.picked || [])].sort((a, b) => a - b),
    answers: (STATE.answers || [])
      .map(a => a.id + "=" + a.answer).sort(),
  });
}

// 当前输入里，有多少条还没被算进去。
// 只用来提示，不参与任何判断。
function pendingCount() {
  if (STATE.computedSig === null) return 0;
  if (STATE.computedSig === inputSig()) return 0;
  return (STATE.picked ? STATE.picked.size : 0) + (STATE.answers || []).length;
}

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
  if (b.classList.contains("prior-btn")) return;
  b.onclick = () => { $("#question").value = b.dataset.q; ask(); };
});

// 用户自己的直觉：会 / 不会 / 说不好。
// 只存二元，不解释、不诱导；用于「你 / 系统 / 实际」三方对照。
function paintPrior() {
  document.querySelectorAll(".prior-btn").forEach(b => {
    b.classList.toggle("on", (b.dataset.prior || null) === STATE.userLean);
  });
}
document.querySelectorAll(".prior-btn").forEach(b => {
  b.onclick = () => {
    const v = b.dataset.prior || null;
    STATE.userLean = (STATE.userLean === v) ? null : v;
    paintPrior();
  };
});

const SURFACE_NAMES = {
  "decision.economic": "经济",
  "decision.information": "信息",
  "decision.risk": "风险",
  "decision.health": "健康",
  "decision.time": "时间",
  "decision.eligibility": "条件",
  "decision.self_fit": "个人适配",
  "decision.relationship": "关系",
  "decision.career": "职业",
  "decision.emotion": "情绪",
  "decision.alternatives": "替代方案",
  "decision.convenience": "便利",
  "decision.safety": "安全"
};

async function ask() {
  const q = $("#question").value.trim();
  if (!q) return;
  SOUND.stop();   // 物理隔离：判断流程中绝对静音
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
    STATE.surfaces = d.surfaces || [];
    STATE.gaps = d.gaps || [];
    STATE.probeCount = d.probe_count || (d.questions || []).length;
    STATE.quota = d.surface_quota || (d.questions || []).length;
    STATE.answers = [];
    // 新问题进来，明细默认收起
    const db = $("#detail-block");
    if (db) db.classList.add("hidden");
    const dt = $("#btn-detail");
    if (dt) dt.textContent = "▸ 查看明细";
    renderAll(d);
    // 自动判定只用了用户自述，勾选和回答都还没算
    STATE.computedSig = inputSig();
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
  SOUND.stop();
  const title = $("#crisis-title");
  if (title && d.title) title.textContent = d.title;
  const say = $("#crisis-say");
  if (say) say.innerHTML = (d.support || []).map(esc).join("<br>");
  const lead = $("#crisis-lead");
  if (lead && d.lead) lead.textContent = d.lead;
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
  // 问句库是弹药库，不是每次全问。没有挑选结果时才退回整库显示。
  const surfaceNames = (STATE.surfaces || [])
    .map(s => SURFACE_NAMES[s.surface_id] || s.surface_id)
    .filter(Boolean);
  const surfaceLine = surfaceNames.length
    ? '<div class="surfaceline">识别到：' + esc(surfaceNames.join("、")) + '</div>'
    : '';
  box.innerHTML = surfaceLine +
    '<div class="surfquota">这次挑出 ' + (STATE.probeCount || (STATE.questions || []).length) +
    ' 条（问句库共 ' + (STATE.quota || 0) + ' 条）· 答一条就多一个面</div>' +
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
    // 翻转阈值：元信息，只陈述「还差几条事实」，不说该怎么做
    (j.flip
      ? '<div class="split-line">距离翻转还差 ' + j.flip.need + ' 条' +
        (j.flip.direction === 'oppose' ? '反对' : '支持') + '事实</div>'
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
  // 输入变了但还没重算 → 这个结论是旧的，变淡提醒
  el.classList.toggle("stale", pendingCount() > 0 && !JUDGING);
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
    // 勾选后自动重算。和答问句保持一致——
    // 不一致会让用户猜「这几个算进去了没有」。
    el.onclick = async () => {
      if (STATE.picked.has(i)) STATE.picked.delete(i); else STATE.picked.add(i);
      el.classList.toggle("on");
      updateBar();
      await judgeAgain();
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
    // 已经点了、但还没重算 —— 必须说出来。
    // 不说的话，用户会以为数字已经包含了他刚勾的那几条。
    // 正在算的时候不提示，因为按钮上已经写着「计算中…」了。
    if (pendingCount() > 0 && !JUDGING) parts.push("尚未计入，点右侧重算");
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

// 自动重算的两个保护：
//   JUDGING    —— 正在算的时候再点，不并发发请求，只记一个「算完再来一次」
//   JUDGE_RERUN —— 那个「再来一次」的标记
// 没有这两个，连勾三个候选会并发三次模型调用。
let JUDGING = false;
let JUDGE_RERUN = false;

async function judgeAgain() {
  // 只有真的提供了输入（勾了场景或答了询问），才算用户参与过。
  // 什么都没选就点「重算」，出来的结果和初始状态一样，
  // 那就不该显示倾向——否则「还原」会还原出一个结论来。
  STATE.engaged = (STATE.picked.size > 0 || (STATE.answers || []).length > 0);

  // 回到初始状态：没有勾选、没有回答、也没有用户自述 —— 什么都不用算
  if (!STATE.engaged && STATE.stated.length === 0) {
    updateBar();
    updateVerdict();
    return;
  }

  if (JUDGING) { JUDGE_RERUN = true; return; }
  JUDGING = true;
  const btn = $("#btn-judge");
  if (btn) { btn.textContent = "计算中…"; btn.disabled = true; }

  const selected = [...STATE.picked].sort((a, b) => a - b)
    .map(i => ({ text: STATE.candidates[i].text, source: STATE.candidates[i].source }));
  SOUND.stop();   // 物理隔离：出结果时也不能有声音
  const stated = STATE.stated.map(b => ({
    text: b.agent + " " + b.event + " " + b.resource,
  }));
  try {
    const d = await post("/api/judge", {
      question: STATE.query, binary: STATE.nucleus.binary,
      selected, stated,
      answers: STATE.answers || [],
      // 把「这次实际问了哪些」带回服务端，才能算出「探到但没答」的面 → 半知
      asked: (STATE.questions || []).map(q => q.id),
      // 用户自己的直觉（会 / 不会 / 不选）。只用于三方对照，不影响判断。
      user_lean: STATE.userLean || null,
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
    // 记下这次计算用了哪些输入。之后用户再勾选/再回答，就能对比出来「有没有算进去」。
    STATE.computedSig = inputSig();
    renderRelated(STATE.related);
    renderGap(d.gap || null);
    renderStructure(d.judgment);
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    JUDGING = false;
    updateBar();
    // 算的时候又点过（改了输入）→ 再算一次，保证数字和输入一致
    if (JUDGE_RERUN) { JUDGE_RERUN = false; judgeAgain(); }
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
  STATE.userLean = null;
  paintPrior();
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
if (TAB0 === "pending" || TAB0 === "stats" || TAB0 === "settings" || TAB0 === "soundscape") switchTab(TAB0);

const Q0 = new URLSearchParams(location.search).get("q");
if (Q0) { $("#question").value = Q0; ask(); }
// ---------- 标签页 ----------
function switchTab(name) {
  document.querySelectorAll(".tabs button").forEach(b => {
    b.classList.toggle("on", b.dataset.tab === name);
  });
  ["ask", "pending", "stats", "settings", "soundscape"].forEach(t => {
    const sec = document.getElementById("step-" + t);
    if (sec) sec.classList.toggle("hidden", t !== name);
  });
  // 声景只在声景页存在。离开就停——这是约束一的一半。
  if (name !== "soundscape") SOUND.stop();
  if (name === "pending") loadPending();
  if (name === "stats") loadStats();
  if (name === "settings") loadSettings();
  if (name === "soundscape") loadSoundscape();
}

// ---------- 声景 ----------
async function loadSoundscape() {
  const box = document.getElementById("soundscape-body");
  if (!box || SS_LOADED) return;
  try {
    const r = await fetch("/api/soundscape");
    const d = await r.json();
    let h = '';
    d.groups.forEach(g => {
      h += '<div class="ss-group"><div class="ss-moment">' + esc(g.name) + '</div>';
      g.tracks.forEach(t => {
        h += '<div class="ss-track' + (t.playable ? '' : ' off') + '">' +
          '<button class="ss-play" ' + (t.playable ? '' : 'disabled') + '>▶</button>' +
          '<div class="ss-body">' +
            '<div class="ss-title">' + esc(t.title) +
              '<span class="ss-dur">' + esc(t.duration) + '</span></div>' +
            '<div class="ss-note">' + esc(t.note) + '</div>' +
            (t.source ? '<div class="ss-src">' + esc(t.source) + '</div>' : '') +
          '</div></div>';
      });
      h += '</div>';
    });
    h += '<div class="ss-foot">按时刻组织，不按你的状态。<br>' +
      '不收费 · 不做个性化 · 不产生任何使用数据。<br>' +
      '判断流程中不会播放——音乐改变情绪，情绪改变判断。</div>';
    box.innerHTML = h;

    // 绑定播放（只有接了音频的才可点）
    let idx = 0;
    const flat = [];
    d.groups.forEach(g => g.tracks.forEach(t => flat.push(t)));
    box.querySelectorAll(".ss-play").forEach(btn => {
      const t = flat[idx++];
      btn.onclick = () => {
        if (!t || !t.playable) return;
        if (SOUND.url === t.url && SOUND.playing()) { SOUND.stop(); btn.textContent = "▶"; }
        else if (SOUND.play(t)) { btn.textContent = "❚❚"; }
      };
    });
    SS_LOADED = true;
  } catch (err) {
    box.innerHTML = '<p class="hint">加载失败：' + esc(err.message) + '</p>';
  }
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

// 判断漂移：同一个决定隔时间又判了一次，两次之间什么变了。
// 只说「变了什么」，不说「为什么变」，更不说「哪个更对」。
async function loadDrift() {
  const box = document.getElementById("drift-body");
  if (!box) return;
  try {
    const r = await fetch("/api/drift");
    const d = await r.json();
    if (!d.total) {
      box.innerHTML = '<p class="hint">还没有发现漂移。' +
        '同一件事隔一段时间再判一次（至少 12 小时），这里会记录两次之间的差异。' +
        '一小时内问五遍不算——那是反复纠结。</p>';
      return;
    }
    let h = '';
    d.items.slice(0, 6).forEach(it => {
      const days = Math.round(it.gap_hours / 24 * 10) / 10;
      const when = days >= 1 ? days + " 天" : it.gap_hours + " 小时";
      h += '<div class="drift-card">' +
        '<div class="drift-head">' +
          '<span class="drift-q">' + esc(truncate(it.question, 36)) + '</span>' +
          '<span class="drift-gap">间隔 ' + when + ' · 判过 ' + it.times + ' 次</span>' +
        '</div>' +
        '<p class="drift-msg">' + esc(it.message) + '</p>' +
        '<div class="drift-pair">' +
          '<span class="drift-cell">' + (it.first.lean === "yes" ? "会" : "不会") +
            ' · ' + Math.round(it.first.confidence * 100) + '%</span>' +
          '<span class="drift-arrow">→</span>' +
          '<span class="drift-cell on">' + (it.last.lean === "yes" ? "会" : "不会") +
            ' · ' + Math.round(it.last.confidence * 100) + '%</span>' +
        '</div>' +
      '</div>';
    });
    h += '<p class="hint" style="margin-top:14px">' +
      '两次判断没有哪个更对。这里只记录差异。</p>';
    box.innerHTML = h;
  } catch (err) {
    box.innerHTML = '<p class="hint">加载失败：' + esc(err.message) + '</p>';
  }
}


// ---------- 固定知识 / 常识基线 ----------
// 这些不是从用户数据学出来的，是写死的参考。
function svgForgetting(points) {
  const arr = points || [];
  if (!arr.length) return "";
  const W = 380, H = 160, P = 28;
  function X(i) { return P + (arr.length <= 1 ? 0.5 : i / (arr.length - 1)) * (W - P * 2); }
  function Y(v) { return H - P - v / 100 * (H - P * 2); }
  let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart" role="img">';
  [0, 50, 100].forEach(function (v) {
    g += '<line x1="' + X(0) + '" y1="' + Y(v) + '" x2="' + X(arr.length - 1) + '" y2="' + Y(v) + '" class="cgrid"/>';
    g += '<text x="' + (P - 6) + '" y="' + (Y(v) + 4) + '" class="cax" text-anchor="end">' + v + '%</text>';
  });
  const pts = arr.map(function (p, i) { return X(i) + "," + Y(p.retention * 100); });
  g += '<polyline points="' + pts.join(" ") + '" class="cline2"/>';
  arr.forEach(function (p, i) {
    g += '<circle cx="' + X(i) + '" cy="' + Y(p.retention * 100) + '" r="3.2" class="cdotb"/>';
  });
  const marks = [0, 3, 6];
  marks.forEach(function (i) {
    if (!arr[i]) return;
    g += '<text x="' + X(i) + '" y="' + (H - 8) + '" class="cax" text-anchor="middle">' + arr[i].after + '</text>';
  });
  g += '</svg>';
  return g;
}

function renderBaselines(b) {
  let h = '<div class="label" style="margin-top:22px">常识基线</div>';
  h += '<div class="basecard">';
  h += '<div class="basegrid">';
  h += '<div class="baseitem"><div class="k">盲猜</div><div class="v">50% · Brier 0.250</div></div>';
  h += '<div class="baseitem"><div class="k">置信封顶</div><div class="v">80%（N=8 时 8/10）</div></div>';
  h += '<div class="baseitem"><div class="k">遗忘曲线</div><div class="v">20 分钟 58% → 1 天 33% → 31 天 21%</div></div>';
  h += '</div>';
  h += svgForgetting(b.forgetting);
  h += '<p class="hint">' + esc(b.forgetting_note) + '<br>来源：' + esc(b.source) + '</p>';
  h += '</div>';
  return h;
}

async function loadStats() {
  loadCommonRoots();
  loadTopology();
  loadDrift();
  const box = document.getElementById("stats-body");
  try {
    const rs = await Promise.all([fetch("/api/stats"), fetch("/api/baselines")]);
    const r = rs[0], rb = rs[1];
    const s = await r.json();
    const b = rb.ok ? await rb.json() : null;
    if (!s.resolved) {
      box.innerHTML = '<p class="hint">还没有回收的结果。先去「回收」页回答几条——校准需要时间，这是正常的。</p>' +
        '<div class="metrics">' + metric("判断总数", s.total) + metric("待回收", s.pending) +
        metric("已回收", s.resolved) + '</div>';
      return;
    }
    box.innerHTML = renderCalibration(s, b);
  } catch (err) {
    box.innerHTML = '<p class="hint">加载失败：' + esc(err.message) + '</p>';
  }
}

function pct(v) { return v == null ? "—" : Math.round(v * 100) + "%"; }

function calPanel(title, hint, body) {
  return '<div class="calpanel"><div class="calhead"><b>' + title + '</b>' +
    '<span class="calhint">' + hint + '</span></div>' + body + '</div>';
}

function calWait(have, need, label) {
  const w = Math.max(0, Math.min(100, Math.round(have / need * 100)));
  return '<div class="calwait"><div class="calbar"><i style="width:' + w + '%"></i></div>' +
    '<p class="hint">' + label + '：已有 ' + have + ' / ' + need + '，还差 ' +
    Math.max(0, need - have) + ' 条。样本不够时不下结论。</p></div>';
}

function svgReliability(s) {
  const W = 340, H = 240, P = 34;
  function X(v) { return P + v / 100 * (W - P * 2); }
  function Y(v) { return H - P - v / 100 * (H - P * 2); }
  let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart" role="img">';
  [0, 50, 100].forEach(function (v) {
    g += '<line x1="' + X(0) + '" y1="' + Y(v) + '" x2="' + X(100) + '" y2="' + Y(v) + '" class="cgrid"/>';
    g += '<text x="' + (X(0) - 6) + '" y="' + (Y(v) + 4) + '" class="cax" text-anchor="end">' + v + '%</text>';
    g += '<text x="' + X(v) + '" y="' + (Y(0) + 16) + '" class="cax" text-anchor="middle">' + v + '%</text>';
  });
  g += '<line x1="' + X(0) + '" y1="' + Y(0) + '" x2="' + X(100) + '" y2="' + Y(100) + '" class="cdiag"/>';
  g += '<line x1="' + X(0) + '" y1="' + Y(50) + '" x2="' + X(100) + '" y2="' + Y(50) + '" class="cchance"/>';
  const mp = s.mean_p == null ? null : s.mean_p * 100;
  const mo = s.base_rate == null ? null : s.base_rate * 100;
  if (mp != null) {
    g += '<line x1="' + X(mp) + '" y1="' + Y(0) + '" x2="' + X(mp) + '" y2="' + Y(100) + '" class="cmean"/>';
  }
  if (mo != null) {
    g += '<line x1="' + X(0) + '" y1="' + Y(mo) + '" x2="' + X(100) + '" y2="' + Y(mo) + '" class="cmean"/>';
    if (mp != null) {
      g += '<line x1="' + X(mp) + '" y1="' + Y(mp) + '" x2="' + X(mp) + '" y2="' + Y(mo) + '" class="cgap"/>';
    }
  }
  (s.reliability || []).forEach(function (b) {
    const px = X(b.p_mean * 100), py = Y(b.obs * 100);
    const rr = 4 + Math.min(9, Math.sqrt(b.n) * 2.2);
    g += '<circle cx="' + px + '" cy="' + py + '" r="' + rr.toFixed(1) + '" class="cdot"/>';
    g += '<text x="' + px + '" y="' + (py - rr - 4) + '" class="cax" text-anchor="middle">n=' + b.n + '</text>';
  });
  g += '<text x="' + (W / 2) + '" y="' + (H - 4) + '" class="cax" text-anchor="middle">预测概率</text>';
  g += '</svg>';
  return g;
}

function relLegend() {
  return '<div class="legend">对角线 = 完美校准 · 横虚线 = 盲猜 50% · ' +
    '细虚线 = 预测均值（竖）/ 实际均值（横）</div>';
}

function svgTime(s) {
  const arr = s.series || [];
  const W = 340, H = 240, P = 34;
  function X(i) { return P + (arr.length <= 1 ? 0.5 : i / (arr.length - 1)) * (W - P * 2); }
  function Y(v) { return H - P - v / 100 * (H - P * 2); }
  let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart" role="img">';
  [0, 50, 80, 100].forEach(function (v) {
    g += '<line x1="' + X(0) + '" y1="' + Y(v) + '" x2="' + X(arr.length - 1) + '" y2="' + Y(v) + '" class="cgrid"/>';
    g += '<text x="' + (P - 6) + '" y="' + (Y(v) + 4) + '" class="cax" text-anchor="end">' + v + '%</text>';
  });
  g += '<line x1="' + X(0) + '" y1="' + Y(50) + '" x2="' + X(arr.length - 1) + '" y2="' + Y(50) + '" class="cchance"/>';
  g += '<line x1="' + X(0) + '" y1="' + Y(80) + '" x2="' + X(arr.length - 1) + '" y2="' + Y(80) + '" class="ccap"/>';
  let cp = 0, co = 0, a = [], b = [];
  arr.forEach(function (e, i) {
    cp += e.p_yes;
    co += (e.outcome === "yes" ? 1 : 0);
    a.push(X(i) + "," + Y(cp / (i + 1) * 100));
    b.push(X(i) + "," + Y(co / (i + 1) * 100));
  });
  g += '<polyline points="' + a.join(" ") + '" class="cline1"/>';
  g += '<polyline points="' + b.join(" ") + '" class="cline2"/>';
  g += '<text x="' + (W / 2) + '" y="' + (H - 4) + '" class="cax" text-anchor="middle">回收顺序（越右越新）</text>';
  g += '</svg>';
  return g;
}

function timeLegend() {
  return '<div class="legend">实线 = 预测均值（累计）· 虚线 = 实际发生比例（累计）· ' +
    '浅虚线 = 盲猜 50% / 80% 封顶</div>';
}

function svgByN(s) {
  const bins = s.by_n || [];
  const W = 340, H = 240, P = 34;
  function X(v) { return P + v * (W - P * 2); }
  function Y(v) { return H - P - v * (H - P * 2); }
  let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart" role="img">';
  [0, 0.5, 0.8, 1].forEach(function (v) {
    g += '<line x1="' + X(0) + '" y1="' + Y(v) + '" x2="' + X(1) + '" y2="' + Y(v) + '" class="cgrid"/>';
    g += '<text x="' + (P - 6) + '" y="' + (Y(v) + 4) + '" class="cax" text-anchor="end">' + Math.round(v * 100) + '%</text>';
    g += '<text x="' + X(v) + '" y="' + (Y(0) + 16) + '" class="cax" text-anchor="middle">' + Math.round(v * 100) + '%</text>';
  });
  g += '<line x1="' + X(0) + '" y1="' + Y(0) + '" x2="' + X(1) + '" y2="' + Y(1) + '" class="cdiag"/>';
  g += '<line x1="' + X(0) + '" y1="' + Y(0.8) + '" x2="' + X(1) + '" y2="' + Y(0.8) + '" class="ccap"/>';
  bins.forEach(function (b) {
    const rr = 4 + Math.min(9, Math.sqrt(b.count) * 2.2);
    g += '<circle cx="' + X(b.determinability) + '" cy="' + Y(b.hit_rate) + '" r="' + rr.toFixed(1) + '" class="cdotb"/>';
    g += '<text x="' + X(b.determinability) + '" y="' + (Y(b.hit_rate) - rr - 4) + '" class="cax" text-anchor="middle">N=' + (b.n + 2) + ' · ' + b.count + '条</text>';
  });
  g += '<text x="' + (W / 2) + '" y="' + (H - 4) + '" class="cax" text-anchor="middle">可确定度 N/(N+2)</text>';
  g += '</svg>';
  return g;
}

function bynLegend() {
  return '<div class="legend">对角线 = 结构成立（命中率 = 可确定度）· 浅虚线 = 80% 封顶</div>';
}

function renderThreeWay(s) {
  const tw = s.three_way;
  const items = (s.series || []).filter(function (e) {
    return e.user_lean === "yes" || e.user_lean === "no";
  }).slice(-12);
  let h = '<div class="twsum">' +
    '<span>样本 <b>' + tw.samples + '</b></span>' +
    '<span>你命中 <b>' + pct(tw.user_hit_rate) + '</b></span>' +
    '<span>绒球命中 <b>' + pct(tw.system_hit_rate) + '</b></span>' +
    '<span>一致 <b>' + pct(tw.agree_rate) + '</b></span></div>';
  h += '<p class="hint">分歧 ' + tw.diverge + ' 次：你对 ' + tw.user_right_when_diverge +
    ' 次，绒球对 ' + tw.system_right_when_diverge + ' 次。</p>';
  h += '<div class="tw"><div class="tw-head"><span></span>' +
    items.map(function (e, i) { return '<span>' + (i + 1) + '</span>'; }).join("") + '</div>';
  const rows = [
    ["你", function (e) { return e.user_lean; }, function (e) { return e.user_hit; }],
    ["绒球", function (e) { return e.lean; }, function (e) { return e.hit; }],
    ["实际", function (e) { return e.outcome; }, function (e) { return 1; }]
  ];
  rows.forEach(function (row) {
    h += '<div class="tw-row"><span class="twk">' + row[0] + '</span>';
    items.forEach(function (e) {
      const v = row[1](e);
      const ok = row[2](e);
      h += '<span class="twc ' + (v === "yes" ? "yes" : "no") + (ok ? "" : " miss") + '">' +
        (v === "yes" ? "会" : "不会") + '</span>';
    });
    h += '</div>';
  });
  h += '</div><div class="legend">灰掉 = 与「实际」不一致。左到右为由旧到新。</div>';
  return h;
}

function renderSurfaceTable(s) {
  const rows = s.surfaces || [];
  let h = '<div class="label" style="margin-top:20px">按面校准</div>';
  if (!rows.length) {
    return h + '<p class="hint">还没有带面标记的回收记录。回答固定问句后再回收，才会按面统计。</p>';
  }
  h += '<div class="tbl"><div class="tr th"><span>面</span><span>事实</span><span>决策</span>' +
    '<span>命中率</span><span>Brier</span></div>';
  rows.forEach(function (r) {
    const enough = r.facts >= 5;
    h += '<div class="tr"><span>' + esc(SURFACE_NAMES[r.surface] || r.surface) + '</span>' +
      '<span>' + r.facts + '</span><span>' + r.decisions + '</span>' +
      '<span>' + (enough ? pct(r.hit_rate) : '—') + '</span>' +
      '<span>' + (enough && r.brier != null ? r.brier.toFixed(3) : '—') + '</span></div>';
  });
  h += '</div><p class="hint">少于 5 条事实的面不显示命中率，只累计样本。旧记录按「主动询问」事实自动回填面。</p>';
  return h;
}

function renderCalibration(s, b) {
  const res = s.resolved;
  const sk = s.chance_skill == null ? "—" : s.chance_skill.toFixed(3);
  let h = '<div class="metrics">' +
    metric("已回收", res) + metric("Brier", s.brier.toFixed(3)) +
    metric("相对盲猜", sk) + metric("预测均值", pct(s.mean_p)) +
    metric("实际命中", pct(s.base_rate)) + '</div>';
  h += '<p class="hint" style="margin-top:10px">盲猜 Brier = 0.250；相对盲猜 > 0 才是比瞎猜准。样本不足时，格子保持沉默。</p>';
  h += '<div class="calgrid">';
  if (res >= 10 && (s.reliability || []).length >= 2) {
    h += calPanel("可靠性曲线", "预测概率 vs 实际发生比例", svgReliability(s) + relLegend());
  } else {
    h += calPanel("可靠性曲线", "预测概率 vs 实际发生比例", calWait(res, 10, "可靠性曲线"));
  }
  if (res >= 5 && (s.series || []).length >= 3) {
    h += calPanel("时间曲线", "预测均值 vs 实际发生（累计）", svgTime(s) + timeLegend());
  } else {
    h += calPanel("时间曲线", "预测均值 vs 实际发生（累计）", calWait(res, 5, "时间曲线"));
  }
  const groups = (s.by_n || []).filter(function (b) { return b.count >= 3; });
  if (res >= 10 && groups.length >= 2) {
    h += calPanel("811 结构曲线", "可确定度 vs 实际命中率", svgByN(s) + bynLegend());
  } else {
    h += calPanel("811 结构曲线", "可确定度 vs 实际命中率", calWait(res, 10, "811 曲线"));
  }
  if (s.three_way && s.three_way.samples >= 3) {
    h += calPanel("三方对照", "你的直觉 / 系统判断 / 实际结果", renderThreeWay(s));
  } else {
    h += calPanel("三方对照", "你的直觉 / 系统判断 / 实际结果",
      calWait(s.three_way ? s.three_way.samples : 0, 3, "三方对照（提问时选『你的直觉』）"));
  }
  h += '</div>';
  h += renderSurfaceTable(s);
  if (b) h += renderBaselines(b);
  if (s.by_category && s.by_category.length) {
    h += '<div class="label" style="margin-top:20px">按决定类型</div>';
    h += '<div class="tbl"><div class="tr th"><span>类型</span><span>样本</span>' +
      '<span>平均置信</span><span>命中率</span><span>缺口</span></div>';
    s.by_category.forEach(function (c) {
      const g = Math.round((c.gap || 0) * 100);
      h += '<div class="tr"><span>' + esc(c.category) + '</span><span>' + c.samples +
        '</span><span>' + Math.round((c.mean_confidence || 0) * 100) + '%</span><span>' +
        Math.round((c.hit_rate || 0) * 100) + '%</span><span class="' + (g >= 0 ? "pos" : "neg") +
        '">' + (g >= 0 ? "+" : "") + g + '%</span></div>';
    });
    h += '</div><p class="hint">缺口 = 命中率 − 平均置信。少于 5 条样本的类型不预警。</p>';
  }
  return h;
}

// 启动时看一下有没有到期的
fetch("/api/pending").then(r => r.json()).then(d => {
  const badge = document.getElementById("due-badge");
  if (d.due > 0) { badge.textContent = d.due; badge.classList.remove("hidden"); }
}).catch(() => {});

// ---------- 设置 ----------
async function loadSettings() {
  const note = document.getElementById("settings-note");
  try {
    const r = await fetch("/api/settings");
    const d = await r.json();
    if (!d.ok) { if (note) note.textContent = d.message || "读取失败"; return; }
    const base = document.getElementById("set-base");
    const model = document.getElementById("set-model");
    const provider = document.getElementById("set-provider");
    if (base) base.value = d.llm.base_url || "";
    if (model) model.value = d.llm.model || "";
    if (provider) provider.value = d.search.provider || "";
    if (note) {
      note.textContent = "模型：" + (d.llm.api_key_set ? "已配置" : "未配置") +
        " · 搜索：" + (d.search.api_key_set ? "已配置" : "未配置") +
        "（key 不会显示明文）";
    }
  } catch (e) {
    if (note) note.textContent = "读取失败：" + e.message;
  }
}

async function saveSettings() {
  const note = document.getElementById("settings-note");
  const btn = document.getElementById("btn-save-settings");
  if (btn) { btn.disabled = true; btn.textContent = "保存中…"; }
  try {
    const d = await post("/api/settings", {
      base_url: (document.getElementById("set-base") || {}).value || "",
      model: (document.getElementById("set-model") || {}).value || "",
      api_key: (document.getElementById("set-key") || {}).value || "",
      provider: (document.getElementById("set-provider") || {}).value || "",
      search_api_key: (document.getElementById("set-search-key") || {}).value || "",
    });
    if (d.ok) {
      if (note) note.textContent = d.configured ? "已保存。模型已配置。" : "已保存，但模型 key 仍是空的。";
      const k = document.getElementById("set-key"); if (k) k.value = "";
      const sk = document.getElementById("set-search-key"); if (sk) sk.value = "";
      refreshSetupHint();
    } else if (note) note.textContent = d.message || "保存失败";
  } catch (e) {
    if (note) note.textContent = "保存失败：" + e.message;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "保存"; }
  }
}

async function refreshSetupHint() {
  const box = document.getElementById("setup-hint");
  if (!box) return;
  try {
    const r = await fetch("/api/settings");
    const d = await r.json();
    if (d.ok && !d.configured) {
      box.className = "setup-banner";
      box.innerHTML = "还没有配置模型。判断需要模型来读你的问题——去「设置」填一个 API Key 才能用。";
    } else {
      box.className = "hidden";
      box.innerHTML = "";
    }
  } catch (e) { /* 忽略 */ }
}

const saveBtn = document.getElementById("btn-save-settings");
if (saveBtn) saveBtn.onclick = saveSettings;
refreshSetupHint();

// ---------- 桌面版退出 ----------
fetch("/api/app").then(function (r) { return r.json(); }).then(function (d) {
  if (!d.desktop) return;
  const b = document.getElementById("btn-quit");
  if (!b) return;
  b.classList.remove("hidden");
  b.onclick = async function () {
    b.disabled = true;
    b.textContent = "正在退出…";
    try { await fetch("/api/shutdown", { method: "POST" }); } catch (e) { /* 进程可能已退出 */ }
    document.body.innerHTML = '<div style="padding:48px;font-family:system-ui;color:#5f5a52">绒球已退出，可以关闭窗口。</div>';
  };
}).catch(function () { /* 忽略 */ });
