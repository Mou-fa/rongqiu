const $ = (s) => document.querySelector(s);
let STATE = { nucleus: null, candidates: [], picked: new Set(), auto: null, stated: [] };

function show(id) {
  ["step-ask", "step-result"].forEach(s => {
    $("#" + s).classList.toggle("hidden", s !== id);
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
    const d = await post("/api/ask", { question: q });
    STATE.nucleus = d.nucleus;
    STATE.candidates = d.candidates || [];
    STATE.auto = d.auto;
    STATE.stated = d.stated || [];
    STATE.picked = new Set();
    STATE.query = q;
    STATE.questions = d.questions || [];
    STATE.quota = d.surface_quota || (d.questions || []).length;
    STATE.answers = [];
    renderAll(d);
    show("step-result");
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "开始判断";
  }
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

  renderStructure(STATE.auto);
  renderQuestions();
  renderPrompts();
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
    '<div class="split-line">811 结构：可确定 ' + Math.round(sp.determinable * 100) +
    '% · 假设 ' + Math.round(sp.assumption * 100) +
    '% · 未知 ' + Math.round(sp.unknown * 100) +
    '%   链长 ' + (j.max_depth || 1) + '</div>' +
    '<div class="label" style="margin-top:16px">依据（全部公开）</div>' +
    '<ul class="evidence">' + j.facts.map(f => {
      const cls = f.supports === "support" ? "p" : f.supports === "oppose" ? "m" : "z";
      const sym = f.supports === "support" ? "+" : f.supports === "oppose" ? "−" : "·";
      return '<li><span class="mark ' + cls + '">' + sym + '</span><span>' +
        esc(f.scene) + '</span></li>';
    }).join("") + '</ul>' +
    (j.assumption ? '<div class="slots"><div class="slot"><b>假设</b>　' + esc(j.assumption) + '</div></div>' : '') +
    (j.unknown ? '<div class="slots"><div class="slot"><b>未知</b>　' + esc(j.unknown) + '</div></div>' : '') +
    '<div class="tiny-ref"><span>系统参考倾向</span>' +
    '<b style="color:' + (j.lean === "yes" ? "var(--accent)" : "var(--warn)") + '">' +
    (j.lean === "yes" ? "更可能是：会" : "更可能是：不会") + '</b>' +
    '<span>置信 ' + (j.confidence * 100).toFixed(0) + '%</span></div>';
}

function renderPrompts() {
  const box = $("#prompts");
  if (!STATE.candidates.length) { box.innerHTML = ""; return; }
  box.innerHTML =
    '<div class="label" style="margin-top:22px">这些可能也是你的情况</div>' +
    '<p class="hint">从全网找到的原文，已浓缩成一句话。本身不算证据，' +
    '点选真正符合你的，才加入判断。</p>' +
    '<div class="cands" id="cand-list"></div>' +
    '<div class="bar"><span id="picked-count">已选 0 条</span>' +
    '<button id="btn-judge" class="primary">加入判断</button></div>' +
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
}

function updateBar() {
  const n = STATE.picked.size;
  const c = $("#picked-count");
  if (c) c.textContent = n === 0 ? "已选 0 条（当前显示：只用你自己的处境）" : "已选 " + n + " 条";
  const b = $("#btn-judge");
  if (!b) return;
  // 永远可点：用户要来回比对，不能因为取消到 0 条就锁死。
  // 0 条时的语义是「还原」——只用用户自述重新算一遍。
  b.disabled = false;
  b.textContent = n === 0 ? "还原判断" : "加入判断";
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
    renderStructure(d.judgment);
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    updateBar();
  }
}

$("#btn-again").onclick = () => {
  $("#question").value = "";
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
async function loadStats() {
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
