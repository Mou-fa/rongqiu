const $ = (s) => document.querySelector(s);
let STATE = { nucleus: null, candidates: [], picked: new Set(), auto: null };

function show(id) {
  ["step-ask", "step-result", "step-pick"].forEach(s => {
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
    STATE.candidates = d.candidates;
    STATE.picked = new Set();
    STATE.auto = d.auto;

    if (!d.candidates.length) {
      alert("没有找到和这个问题结构相同的场景。换个说法，或者等全网检索接上。");
      return;
    }
    if (!d.auto) {
      alert("找到了场景，但没有形成可判定的方向信息。");
      return;
    }
    renderResult(d.auto, true);
    show("step-result");
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "开始判断";
  }
}

function renderResult(j, isAuto) {
  const n = STATE.nucleus;
  $("#svo").innerHTML =
    '<span class="seg">' + esc(n.agent) + '</span><span class="sep">·</span>' +
    '<span class="seg">' + esc(n.event) + '</span><span class="sep">·</span>' +
    '<span class="seg">' + esc(n.resource) + '</span>';

  const yes = j.lean === "yes";
  $("#lean").textContent = yes ? "更可能是：会" : "更可能是：不会";
  $("#lean").style.color = yes ? "var(--accent)" : "var(--warn)";
  const ruleTxt = j.rule === "direct" ? "直接判定"
    : j.rule === "tie_break_11" ? "平票，由 11 决定" : "暂定判定";
  const depthTxt = "链长 " + (j.max_depth || 1) + (j.over_depth ? " ⚠" : "");
  $("#conf").textContent = "置信 " + (j.confidence * 100).toFixed(0) + "%  ·  " +
    ruleTxt + "  ·  " + depthTxt;

  $("#metrics").innerHTML =
    metric("依据事实", j.n) +
    metric("可确定", Math.round(j.determinability * 100) + "%") +
    metric("支持率", Math.round(j.support_ratio * 100) + "%");

  const ul = $("#evidence");
  ul.innerHTML = "";
  j.facts.forEach(f => {
    const cls = f.supports === "support" ? "p" : f.supports === "oppose" ? "m" : "z";
    const sym = f.supports === "support" ? "+" : f.supports === "oppose" ? "−" : "·";
    const li = document.createElement("li");
    li.innerHTML = '<span class="mark ' + cls + '">' + sym + '</span><span>' + esc(f.scene) + '</span>';
    ul.appendChild(li);
  });

  let slots = "";
  if (j.assumption) slots += '<div class="slot"><b>假设</b>　' + esc(j.assumption) + '</div>';
  if (j.unknown) slots += '<div class="slot"><b>未知</b>　' + esc(j.unknown) + '</div>';
  $("#slots").innerHTML = slots;

  $("#refine-note").innerHTML = isAuto
    ? "系统默认假设上面 " + j.n + " 条都适用于你。"
    : "已按你的点选重算。";
  $("#btn-refine").style.display = State_hasCandidates() ? "" : "none";
}

function State_hasCandidates() { return STATE.candidates.length > 0; }

function metric(k, v) {
  return '<div class="metric"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>';
}

$("#btn-refine").onclick = () => {
  renderPick();
  show("step-pick");
};

function renderPick() {
  const box = $("#candidates");
  box.innerHTML = "";
  STATE.picked = new Set();
  STATE.candidates.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "cand";
    el.innerHTML =
      '<div class="box">✓</div>' +
      '<div><div class="txt">' + esc(c.text) + '</div>' +
      '<div class="src">命中 ' + c.hits + '/3 成分</div></div>';
    el.onclick = () => {
      if (STATE.picked.has(i)) STATE.picked.delete(i); else STATE.picked.add(i);
      el.classList.toggle("on");
      updateBar();
    };
    box.appendChild(el);
  });
  updateBar();
}

function updateBar() {
  const n = STATE.picked.size;
  $("#picked-count").textContent = "已选 " + n + " 条";
  $("#btn-judge").disabled = n === 0;
}

$("#btn-back").onclick = () => show("step-result");

$("#btn-judge").onclick = async () => {
  const btn = $("#btn-judge");
  btn.disabled = true; btn.textContent = "重算中…";
  const selected = [...STATE.picked].sort((a, b) => a - b)
    .map(i => ({ text: STATE.candidates[i].text, source: STATE.candidates[i].source }));
  try {
    const d = await post("/api/judge", {
      question: $("#question").value.trim() || STATE.nucleus.binary,
      binary: STATE.nucleus.binary, selected,
    });
    if (!d.ok) { alert(d.message); return; }
    renderResult(d.judgment, false);
    show("step-result");
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "重新计算";
  }
};

$("#btn-again").onclick = () => {
  $("#question").value = "";
  show("step-ask");
  $("#question").focus();
};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

show("step-ask");

const Q0 = new URLSearchParams(location.search).get("q");
if (Q0) { $("#question").value = Q0; ask(); }
