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
  btn.disabled = true; btn.textContent = "正在判断…";
  try {
    const d = await post("/api/ask", { question: q });
    STATE.nucleus = d.nucleus;
    STATE.candidates = d.candidates || [];
    STATE.auto = d.auto;
    STATE.stated = d.stated || [];
    STATE.picked = new Set();
    STATE.query = q;
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
  renderPrompts();
}

function renderStructure(j) {
  const box = $("#structure");
  if (!j) {
    box.innerHTML = '<p class="hint">你没有在问题里说出自己的处境，所以系统没有可判定的' +
      '第一接触面。下面是从网上找到的、可能符合你的情况——点选之后加入判断。</p>';
    return;
  }
  const sp = j.split || { determinable: j.determinability, assumption: 0.1, unknown: 0.1 };
  box.innerHTML =
    '<div class="metrics">' +
    metric("第一接触面", j.n) +
    metric("可确定", Math.round(sp.determinable * 100) + "%") +
    metric("支持 / 反对", supportSplit(j)) +
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
    '<button id="btn-judge" class="primary" disabled>加入判断</button></div>';
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
  if (c) c.textContent = "已选 " + n + " 条";
  const b = $("#btn-judge");
  if (b) b.disabled = n === 0;
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
  const btn = $("#btn-judge");
  btn.disabled = true; btn.textContent = "重算中…";
  const selected = [...STATE.picked].sort((a, b) => a - b)
    .map(i => ({ text: STATE.candidates[i].text, source: STATE.candidates[i].source }));
  try {
    const d = await post("/api/judge", {
      question: STATE.query, binary: STATE.nucleus.binary,
      selected, stated: STATE.stated.map(b => ({ text: b.agent + " " + b.event + " " + b.resource })),
    });
    if (!d.ok) { alert(d.message); return; }
    STATE.auto = d.judgment;
    renderStructure(d.judgment);
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "加入判断";
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
const Q0 = new URLSearchParams(location.search).get("q");
if (Q0) { $("#question").value = Q0; ask(); }
