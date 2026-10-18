const $ = (s) => document.querySelector(s);
let STATE = { nucleus: null, candidates: [], picked: new Set() };

function show(id) {
  ["step-ask", "step-pick", "step-result"].forEach(s => {
    $("#" + s).classList.toggle("hidden", s !== id);
  });
}

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  btn.disabled = true; btn.textContent = "正在拆解问题…";
  try {
    const d = await post("/api/ask", { question: q });
    STATE.nucleus = d.nucleus;
    STATE.candidates = d.candidates;
    STATE.picked = new Set();
    renderPick(d);
    show("step-pick");
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "开始判断";
  }
}

function renderPick(d) {
  const n = d.nucleus;
  $("#svo").innerHTML =
    '<span class="seg">' + esc(n.agent) + '</span><span class="sep">·</span>' +
    '<span class="seg">' + esc(n.event) + '</span><span class="sep">·</span>' +
    '<span class="seg">' + esc(n.resource) + '</span>';
  $("#binary").textContent = "判断：" + n.binary + "，会成立吗？";

  $("#hit-count").textContent = d.candidates.length;
  const box = $("#candidates");
  box.innerHTML = "";
  if (!d.candidates.length) {
    box.innerHTML = '<p class="hint">没有找到同类场景。换个说法试试。</p>';
    return;
  }
  d.candidates.forEach((c, i) => {
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

$("#btn-judge").onclick = async () => {
  const btn = $("#btn-judge");
  btn.disabled = true; btn.textContent = "判定中…";
  const selected = [...STATE.picked].sort((a, b) => a - b)
    .map(i => ({ text: STATE.candidates[i].text, source: STATE.candidates[i].source }));
  try {
    const d = await post("/api/judge", {
      question: $("#question").value.trim() || STATE.nucleus.binary,
      binary: STATE.nucleus.binary,
      selected,
    });
    if (!d.ok) { alert(d.message); return; }
    renderResult(d.judgment);
    show("step-result");
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "看结论";
  }
};

function renderResult(j) {
  const yes = j.lean === "yes";
  $("#lean").textContent = yes ? "更可能是：会" : "更可能是：不会";
  $("#lean").style.color = yes ? "var(--accent)" : "var(--warn)";
  $("#conf").textContent = "置信 " + (j.confidence * 100).toFixed(0) + "%  ·  " +
    (j.rule === "direct" ? "直接判定" : j.rule === "tie_break_11" ? "平票，由 11 决定" : "暂定判定");

  $("#metrics").innerHTML =
    metric("选中事实", j.n) +
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
}

function metric(k, v) {
  return '<div class="metric"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>';
}

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

// ?q=问题 直接进入（方便分享和截图）
const Q0 = new URLSearchParams(location.search).get("q");
if (Q0) { $("#question").value = Q0; ask(); }

// ?pick=1,2,3 自动勾选；再加 &auto=1 直接看结论
const PICK0 = new URLSearchParams(location.search).get("pick");
if (PICK0) {
  const idx = PICK0.split(",").map(x => parseInt(x, 10) - 1);
  const timer = setInterval(() => {
    const cards = document.querySelectorAll(".cand");
    if (cards.length) {
      clearInterval(timer);
      idx.forEach(i => { if (cards[i]) cards[i].click(); });
      if (new URLSearchParams(location.search).get("auto")) {
        setTimeout(() => $("#btn-judge").click(), 500);
      }
    }
  }, 200);
  setTimeout(() => clearInterval(timer), 60000);
}
