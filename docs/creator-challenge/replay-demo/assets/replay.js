const state = {
  index: null,
  runs: new Map(),
  selectedRunId: null,
};

const $ = (id) => document.getElementById(id);

function formatBool(value) {
  return value ? "yes" : "no";
}

function formatDuration(value) {
  const n = Number(value || 0);
  if (!n) return "n/a";
  if (n < 90) return `${n.toFixed(1)}s`;
  return `${Math.floor(n / 60)}m ${Math.round(n % 60)}s`;
}

function statusClass(value) {
  if (value === true || value === "pass" || value === "comparable") return "pass";
  if (value === false || value === "fail") return "fail";
  if (String(value || "").includes("diagnostic") || value === "warn") return "warn";
  return "";
}

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return response.json();
}

function renderRunList() {
  const root = $("run-list");
  root.innerHTML = "";
  state.index.runs.forEach((run) => {
    const button = document.createElement("button");
    button.className = `run-button ${run.id === state.selectedRunId ? "active" : ""}`;
    button.innerHTML = `
      <strong>${run.label}</strong>
      <span>${run.difficulty}</span>
      <span>${run.target_count ?? 0} targets · ${formatDuration(run.duration_sec)}</span>
    `;
    button.addEventListener("click", () => selectRun(run.id));
    root.appendChild(button);
  });
}

function renderSummary(run) {
  $("run-tier").textContent = run.tier;
  $("run-title").textContent = run.label;
  $("run-summary").textContent = `${run.difficulty}. ${run.why_it_matters}`;

  $("metric-targets").textContent = String(run.summary.target_count ?? 0);
  $("metric-duration").textContent = formatDuration(run.summary.total_duration_sec);
  $("metric-compare").textContent = formatBool(run.summary.safe_to_compare);
  $("metric-compare").className = statusClass(run.summary.safe_to_compare);
  $("metric-green").textContent = run.summary.green_contract_level || "n/a";
  $("metric-green").className = run.summary.product_green_eligible ? "pass" : "warn";
}

function renderSpans(run) {
  const root = $("span-list");
  root.innerHTML = "";
  run.otel.spans.forEach((span) => {
    const item = document.createElement("div");
    item.className = "span-item";
    item.innerHTML = `
      <div class="span-top">
        <strong>${span.name}</strong>
        <span class="pill ${statusClass(span.status)}">${span.stage} · ${span.status}</span>
      </div>
      <div class="muted small">${span.message}</div>
      <div class="small">${formatDuration(span.duration_sec)}</div>
    `;
    root.appendChild(item);
  });
}

function renderTelemetry(run) {
  const root = $("metric-list");
  root.innerHTML = "";
  run.otel.metrics.forEach((metric) => {
    const value = typeof metric.value === "object" ? JSON.stringify(metric.value) : String(metric.value);
    const item = document.createElement("div");
    item.className = "telemetry-item";
    item.innerHTML = `
      <div class="telemetry-top">
        <strong>${metric.name}</strong>
        <span class="pill ${statusClass(metric.status)}">${metric.status}</span>
      </div>
      <div class="small"><code>${value}</code> ${metric.unit || ""}</div>
      <div class="muted small">${metric.why}</div>
    `;
    root.appendChild(item);
  });
}

function renderFlow(run) {
  const root = $("flow-list");
  root.innerHTML = "";
  const flows = run.symbol_flow
    ? [
        ["Expected", run.symbol_flow.expected || []],
        ["Discovered", run.symbol_flow.discovered || []],
        ["Semantic", run.symbol_flow.semantic || []],
      ]
    : [["Selected runtime targets", (run.selected_runtime_targets || []).map((item) => item.target)]];
  flows.forEach(([label, values]) => {
    const item = document.createElement("div");
    item.className = "flow-item";
    item.innerHTML = `<strong>${label}</strong><div class="muted small">${values.length ? values.join(" → ") : "n/a"}</div>`;
    root.appendChild(item);
  });
}

function renderArtifacts(run) {
  const root = $("artifact-list");
  root.innerHTML = "";
  (run.artifact_summary || []).forEach((artifact) => {
    const item = document.createElement("div");
    item.className = "artifact-item";
    item.innerHTML = `
      <strong>${artifact.name}</strong>
      <div class="muted small">${artifact.kind} · ${artifact.included}</div>
      <div class="small"><code>${artifact.path}</code></div>
    `;
    root.appendChild(item);
  });
  const note = document.createElement("div");
  note.className = "artifact-item";
  note.innerHTML = `<strong>Ground truth boundary</strong><div class="muted small">${run.ground_truth_note}</div>`;
  root.appendChild(note);
}

function renderTargets(run) {
  const root = $("target-table");
  root.innerHTML = "";
  (run.targets || []).forEach((target) => {
    const name = target.target || target.binary_name || "target";
    const status = target.status || target.role || "n/a";
    const duration = target.duration_sec ? formatDuration(target.duration_sec) : target.dependency_confidence || "n/a";
    const evidence = target.required_semantic_checkpoint || target.selection_reason || target.claim_ceiling || "";
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${name}</strong><div class="muted small">${target.binary_name || target.source_path || ""}</div></td>
      <td class="${statusClass(target.safe_to_compare ?? status)}">${status}</td>
      <td>${duration}</td>
      <td class="muted small">${evidence}</td>
    `;
    root.appendChild(row);
  });
}

async function selectRun(runId) {
  state.selectedRunId = runId;
  if (!state.runs.has(runId)) {
    const entry = state.index.runs.find((item) => item.id === runId);
    state.runs.set(runId, await getJson(entry.path));
  }
  const run = state.runs.get(runId);
  renderRunList();
  renderSummary(run);
  renderSpans(run);
  renderTelemetry(run);
  renderFlow(run);
  renderArtifacts(run);
  renderTargets(run);
}

async function init() {
  try {
    state.index = await getJson("data/index.json");
    state.selectedRunId = state.index.runs[0]?.id || null;
    renderRunList();
    if (state.selectedRunId) await selectRun(state.selectedRunId);
  } catch (error) {
    $("run-title").textContent = "Replay data failed to load";
    $("run-summary").textContent = error.message;
  }
}

init();
