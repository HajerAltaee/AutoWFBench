const $ = (id) => document.getElementById(id);
let runs = [],
  challenges = [],
  selectedRun = null;
const palette = [
  "#197765",
  "#b57831",
  "#4d7ca0",
  "#936c9b",
  "#b55851",
  "#6f8445",
];
const el = (tag, text, className) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (className) e.className = className;
  return e;
};
const cohortKey = (r) =>
  [
    r.challenge_hashes?.definition,
    r.challenge_hashes?.environment,
    r.challenge_hashes?.scorecard,
    r.judge?.mode,
    r.judge?.model,
    r.judge?.prompt_version,
  ].join("|");
const formatSeconds = (n) => (Number.isFinite(n) ? `${n.toFixed(2)} s` : "—");
async function api(path, options) {
  const r = await fetch(path, options);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function option(select, value, text) {
  const e = el("option", text);
  e.value = value;
  select.append(e);
}
function filtered() {
  return runs.filter(
    (r) =>
      r.challenge_id === $("challenge").value &&
      ($("cohort").value === "all" || cohortKey(r) === $("cohort").value) &&
      ($("judge-filter").value === "all" ||
        r.judge?.mode === $("judge-filter").value),
  );
}
function updateCohorts() {
  const old = $("cohort").value;
  $("cohort").replaceChildren();
  option($("cohort"), "all", "All configurations (exploration)");
  const found = new Map();
  runs
    .filter((r) => r.challenge_id === $("challenge").value)
    .forEach((r) => {
      if (r.judge) found.set(cohortKey(r), r);
    });
  for (const [k, r] of found)
    option(
      $("cohort"),
      k,
      `${r.challenge_version} · ${r.judge.model} · ${r.challenge_hashes.scorecard.slice(0, 6)}`,
    );
  if ([...$("cohort").options].some((o) => o.value === old))
    $("cohort").value = old;
}
function render() {
  const list = filtered(),
    scored = list.filter((r) => Number.isFinite(r.score_0_10)),
    successful = scored.filter((r) => r.execution_pass);
  $("stat-runs").textContent = list.length;
  $("stat-best").textContent = scored.length
    ? Math.max(...scored.map((r) => r.score_0_10)).toFixed(2)
    : "—";
  $("stat-fastest").textContent = successful.length
    ? formatSeconds(Math.min(...successful.map((r) => r.duration_seconds)))
    : "—";
  $("stat-pending").textContent = list.length - scored.length;
  const demo = list.some((r) => r.judge?.mode === "demo"),
    mixed = new Set(scored.map(cohortKey)).size > 1;
  $("notice").hidden = !demo && !mixed;
  $("notice").textContent = [
    demo
      ? "Demo results use a simulated judge and are not evidence of LLM-evaluated performance."
      : "",
    mixed
      ? "Multiple benchmark or judge configurations are shown. Select one comparison group before ranking solutions."
      : "",
  ]
    .filter(Boolean)
    .join(" ");
  renderChart(scored);
  $("runs").replaceChildren();
  if (!list.length) {
    const tr = el("tr");
    const td = el(
      "td",
      "No runs yet. Submit a solution or start the local demo.",
      "empty",
    );
    td.colSpan = 6;
    tr.append(td);
    $("runs").append(tr);
  }
  for (const r of list) {
    const tr = el("tr");
    const name = el("td");
    name.append(
      el("strong", r.solution.name),
      el("small", `v${r.solution.version} · ${r.solution.runtime}`),
    );
    const score = el(
      "td",
      Number.isFinite(r.score_0_10) ? r.score_0_10.toFixed(2) : "—",
      "score",
    );
    const execution = el("td");
    execution.append(
      el(
        "span",
        r.execution_pass
          ? "PASS"
          : r.execution_pass === false
            ? "FAIL"
            : "Pending",
        `badge ${r.execution_pass ? "good" : "dim"}`,
      ),
    );
    const status = el("td");
    status.append(
      el(
        "span",
        r.judge?.mode === "demo" ? "SIMULATED" : r.status,
        `badge ${r.judge?.mode === "demo" ? "warn" : "dim"}`,
      ),
    );
    if (r.judge) status.append(el("small", r.judge.model));
    const link = el("td"),
      button = el("button", r.run_id.slice(0, 12), "run-link");
    button.addEventListener("click", () => showRun(r.run_id));
    link.append(button, el("small", `seed ${r.seed}`));
    tr.append(
      name,
      score,
      el("td", formatSeconds(r.duration_seconds)),
      execution,
      status,
      link,
    );
    $("runs").append(tr);
  }
  if (selectedRun) renderDetail(runs.find((r) => r.run_id === selectedRun));
}
function renderChart(list) {
  const ns = "http://www.w3.org/2000/svg",
    svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 1100 340");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    "Scatter plot: score from zero to ten on the vertical axis and execution seconds on the horizontal axis",
  );
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    svg.append(n);
    return n;
  };
  const left = 70,
    right = 1050,
    top = 20,
    bottom = 285,
    max = Math.max(0.1, ...list.map((r) => r.duration_seconds)) * 1.2;
  for (let y = 0; y <= 10; y += 2) {
    const py = bottom - (y / 10) * (bottom - top);
    add("line", {
      x1: left,
      x2: right,
      y1: py,
      y2: py,
      stroke: "#e6ebe5",
      "stroke-dasharray": y ? "3 5" : "0",
    });
    add("text", { x: left - 18, y: py + 4, "text-anchor": "end" }, String(y));
  }
  for (let i = 0; i <= 5; i++) {
    const x = left + (i / 5) * (right - left);
    add(
      "text",
      { x, y: bottom + 24, "text-anchor": "middle" },
      ((max * i) / 5).toFixed(max < 5 ? 2 : 1),
    );
  }
  add(
    "text",
    { x: 18, y: 150, transform: "rotate(-90 18 150)", "text-anchor": "middle" },
    "Score / 10",
  );
  add(
    "text",
    { x: (left + right) / 2, y: 330, "text-anchor": "middle" },
    "Execution time (seconds) →",
  );
  const names = [...new Set(list.map((r) => r.solution.id))];
  for (const r of list) {
    const x = left + (r.duration_seconds / max) * (right - left),
      y = bottom - (r.score_0_10 / 10) * (bottom - top);
    const dot = add("circle", {
      cx: x,
      cy: y,
      r: 8,
      fill:
        r.judge?.mode === "demo"
          ? "#b76a27"
          : palette[names.indexOf(r.solution.id) % palette.length],
      class: "point",
      tabindex: 0,
      "aria-label": `${r.solution.name} version ${r.solution.version}: ${r.score_0_10} points, ${formatSeconds(r.duration_seconds)}`,
    });
    const title = document.createElementNS(ns, "title");
    title.textContent = `${r.solution.name} · v${r.solution.version}\n${r.score_0_10}/10 · ${formatSeconds(r.duration_seconds)}\n${r.judge?.mode === "demo" ? "SIMULATED JUDGE" : r.judge?.model}`;
    dot.append(title);
    dot.addEventListener("click", () => showRun(r.run_id));
    dot.addEventListener("keydown", (e) => {
      if (e.key === "Enter") showRun(r.run_id);
    });
    if (list.length <= 12) {
      add(
        "text",
        {
          x: Math.min(x + 13, right - 100),
          y: y + (y < 45 ? 23 : -12),
          fill: "#51675c",
        },
        `${r.solution.name} v${r.solution.version}`,
      );
    }
  }
  if (!list.length)
    add(
      "text",
      { x: 550, y: 160, "text-anchor": "middle" },
      "Completed scores will appear here. Pending results are never plotted as zero.",
    );
  $("chart").replaceChildren(svg);
}
function renderDetail(r) {
  if (!r) return;
  $("details").hidden = false;
  $("detail-title").textContent = `${r.solution.name} / v${r.solution.version}`;
  $("detail-meta").textContent =
    `${r.run_id} · ${r.status} · ${formatSeconds(r.duration_seconds)} · seed ${r.seed}`;
  $("detail-links").replaceChildren();
  for (const [label, path] of [
    ["Run log · four evidence sources", "log"],
    ["Completed scorecard", "scorecard"],
    ["Frozen challenge package", "package"],
  ]) {
    const a = el("a", label);
    a.href = `/api/runs/${r.run_id}/${path}`;
    a.target = "_blank";
    a.rel = "noopener";
    $("detail-links").append(a);
  }
  const err = r.judge_error || r.error;
  $("detail-error").hidden = !err;
  $("detail-error").textContent = err || "";
  $("criteria").replaceChildren();
  for (const c of r.criteria || []) {
    const tr = el("tr");
    const name = el("td", c.question);
    name.append(el("small", c.id));
    const detail = el("td", c.reason);
    detail.append(el("small", c.evidence_refs.join(", ")));
    tr.append(
      name,
      el("td", c.evaluator),
      el("td", c.answer || "Pending"),
      el(
        "td",
        c.points === null ? "—" : `${c.points.toFixed(2)} / ${c.weight}`,
      ),
      detail,
    );
    $("criteria").append(tr);
  }
}
function showRun(id) {
  selectedRun = id;
  renderDetail(runs.find((r) => r.run_id === id));
  $("details").scrollIntoView({ behavior: "smooth", block: "start" });
}
async function refresh() {
  try {
    runs = await api("/api/runs");
    updateCohorts();
    render();
  } catch (e) {
    $("notice").hidden = false;
    $("notice").textContent = `Cannot load results: ${e.message}`;
  }
}
async function init() {
  try {
    challenges = await api("/api/challenges");
    challenges.forEach((c) => option($("challenge"), c.id, c.name));
    await refresh();
  } catch (e) {
    $("notice").hidden = false;
    $("notice").textContent = e.message;
  }
}
$("challenge").addEventListener("change", () => {
  updateCohorts();
  render();
});
$("cohort").addEventListener("change", render);
$("judge-filter").addEventListener("change", render);
$("refresh").addEventListener("click", refresh);
$("close-detail").addEventListener("click", () => {
  selectedRun = null;
  $("details").hidden = true;
});
$("open-submit").addEventListener("click", () =>
  $("submit-dialog").showModal(),
);
$("close-submit").addEventListener("click", () => $("submit-dialog").close());
$("submit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  $("submit-error").textContent = "";
  try {
    await api("/api/runs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${form.get("token")}`,
      },
      body: JSON.stringify({
        challenge_id: $("challenge").value,
        seed: Number(form.get("seed")),
        solution: {
          id: form.get("id"),
          name: form.get("name"),
          version: form.get("version"),
          endpoint: form.get("endpoint"),
          runtime: form.get("runtime"),
          description: "Submitted from dashboard",
          auth_env: "",
        },
      }),
    });
    $("submit-dialog").close();
    await refresh();
  } catch (err) {
    $("submit-error").textContent = err.message;
  }
});
init();
setInterval(refresh, 4000);
