const STAGES = [
  { id: "analysis-entry", code: "IN", name: "Analysis Entry", goal: "Accept the target and create the initial job record. This is where the run becomes visible and the first trustworthy status should appear.", aliases: ["analysis-entry", "analyze", "queued"] },
  { id: "s00_setup_baseline", code: "S00A", name: "Setup Baseline", goal: "Prepare the analysis lane, input metadata, and baseline session state. The pipeline is making sure it has enough context to run safely.", aliases: ["s00_setup_baseline", "s00_setup", "s00"] },
  { id: "s00_static_evidence", code: "S00B", name: "Static Evidence", goal: "Extract static facts from the binary such as strings, exports, and obvious capability hints. These facts seed later probing decisions.", aliases: ["s00_static_evidence"] },
  { id: "s00_admission_handoff", code: "S00C", name: "Admission Handoff", goal: "Package the setup evidence into a handoff the rest of the pipeline can consume. This stage decides what gets carried forward.", aliases: ["s00_admission_handoff"] },
  { id: "s01_unlock", code: "S01", name: "Write Unlock", goal: "Discover callable surfaces and any setup needed before writes or probes will work. The goal is to avoid probing functions in an impossible state.", aliases: ["s01_unlock", "s01"] },
  { id: "s02_probe_ordering", code: "S02A", name: "Probe Ordering", goal: "Choose which functions and arguments to probe first. This stage turns evidence into an execution plan.", aliases: ["s02_probe_ordering"] },
  { id: "s02_invocation_execution", code: "S02B", name: "Invocation Execution", goal: "Run the selected probes through the bridge and capture real behavior. This is the stage most likely to show active backend work.", aliases: ["s02_invocation_execution", "s02_probe", "s02"] },
  { id: "s02_evidence_capture", code: "S02C", name: "Evidence Capture", goal: "Normalize probe results into findings the later stages can reason about. Raw calls become structured evidence here.", aliases: ["s02_evidence_capture"] },
  { id: "s03_reconcile", code: "S03", name: "Reconcile", goal: "Compare expected behavior with observed behavior and resolve contradictions. The pipeline is deciding what it really believes.", aliases: ["s03_reconcile", "s03"] },
  { id: "s04_synthesis", code: "S04", name: "Synthesis", goal: "Build a coherent model of the component from the evidence collected so far. This stage turns scattered findings into an explanation.", aliases: ["s04_synthesis", "s04", "s04_synthesis_refresh"] },
  { id: "s05_schema_backfill", code: "S05A", name: "Schema Backfill", goal: "Fill in missing structured fields, schemas, and artifact details. The goal is to make the output easier for tools and humans to inspect.", aliases: ["s05_schema_backfill", "s05_enrichment", "s05"] },
  { id: "s05_verification_replay", code: "S05B", name: "Verification Replay", goal: "Replay important calls to confirm the model is not based on a one-off result. This stage checks whether evidence is repeatable.", aliases: ["s05_verification_replay"] },
  { id: "s05_read_to_write_chaining", code: "S05C", name: "Read-to-Write Chaining", goal: "Connect read results to possible write actions or follow-up probes. The pipeline is looking for useful dependency chains.", aliases: ["s05_read_to_write_chaining"] },
  { id: "s06_gaps", code: "S06", name: "Gap Resolution", goal: "Identify unresolved questions and try targeted fixes or final probes. If the run is stuck, this stage should explain what is missing.", aliases: ["s06_gaps", "s06", "awaiting_clarification"] },
  { id: "s07_finalize", code: "S07", name: "Finalize", goal: "Write final artifacts, summaries, and review surfaces. The run is being packaged into something a developer can act on.", aliases: ["s07_finalize", "s07", "done"] },
];

const HIGH_LEVEL_STAGE = {
  "analysis-entry": "analysis-entry",
  s00_setup_baseline: "s00",
  s00_static_evidence: "s00",
  s00_admission_handoff: "s00",
  s01_unlock: "s01",
  s02_probe_ordering: "s02",
  s02_invocation_execution: "s02",
  s02_evidence_capture: "s02",
  s03_reconcile: "s03",
  s04_synthesis: "s04",
  s05_schema_backfill: "s05",
  s05_verification_replay: "s05",
  s05_read_to_write_chaining: "s05",
  s06_gaps: "s06",
  s07_finalize: "s07",
};

const state = {
  jobs: [],
  job: null,
  selectedJobId: null,
  selectedStageId: null,
  eventSource: null,
  events: [],
  stageDetail: null,
};

const $ = (id) => document.getElementById(id);

function text(value, fallback = "n/a") {
  const out = String(value ?? "").trim();
  return out || fallback;
}

function normalize(value) {
  return String(value || "").trim().toLowerCase().replaceAll("-", "_");
}

function stageForValue(value) {
  const normalized = normalize(value);
  if (!normalized) return null;
  return STAGES.find((stage) => stage.aliases.some((alias) => normalize(alias) === normalized || normalized.includes(normalize(alias)))) || null;
}

function activeStage(job) {
  if (!job) return STAGES[0];
  if (String(job.status || "").toLowerCase() === "error" && !job.explore_stage) return STAGES[0];
  return (
    stageForValue(job.explore_stage) ||
    stageForValue(job.explore_phase) ||
    stageForValue(job.message) ||
    STAGES[0]
  );
}

function stageComplete(job, stage) {
  const completed = (job?.checkpoint_stages_complete || []).map(normalize);
  return stage.aliases.some((alias) => completed.includes(normalize(alias)));
}

function stageSkipped(job, stage) {
  const reasons = job?.stage_skip_reasons || {};
  return Object.keys(reasons).some((key) => {
    const value = normalize(key);
    return stage.aliases.some((alias) => value === normalize(alias) || value.includes(normalize(alias)));
  });
}

function stageState(job, stage) {
  if (!job) return "pending";
  const status = String(job.status || "").toLowerCase();
  const phase = String(job.explore_phase || "").toLowerCase();
  const active = activeStage(job);
  const activeIndex = STAGES.findIndex((item) => item.id === active.id);
  const index = STAGES.findIndex((item) => item.id === stage.id);

  if (stageSkipped(job, stage)) return "skipped";
  if (stageComplete(job, stage)) return "pass";
  if (status === "done" && phase === "done") return "pass";
  if (status === "error" && stage.id === active.id) return "fail";
  if ((status === "running" || phase === "exploring" || phase === "cancel_requested" || phase === "queued") && stage.id === active.id) return "running";
  if (activeIndex > -1 && index > -1 && index < activeIndex) return "pass";
  return "pending";
}

function stateLabel(value) {
  return {
    pass: "passed",
    running: "running",
    fail: "failed",
    skipped: "skipped",
    warn: "warning",
    pending: "pending",
  }[value] || "pending";
}

function renderJobs() {
  const root = $("jobs");
  const filter = normalize($("job-filter").value);
  const jobs = state.jobs.filter((job) => {
    const haystack = normalize(`${job.job_id} ${job.component_name} ${job.status} ${job.explore_phase} ${job.campaign_id}`);
    return !filter || haystack.includes(filter);
  });
  $("job-count").textContent = String(jobs.length);
  root.innerHTML = "";
  if (!jobs.length) {
    root.innerHTML = `<div class="muted">No jobs found.</div>`;
    return;
  }
  jobs.forEach((job) => {
    const button = document.createElement("button");
    button.className = `job-item ${job.job_id === state.selectedJobId ? "active" : ""}`;
    button.innerHTML = `
      <div class="job-item-title">${text(job.component_name || job.job_id)}</div>
      <div class="job-item-meta"><span>${text(job.job_id)}</span><span>${text(job.status)}</span></div>
      <div class="job-item-meta"><span>${text(job.explore_phase)}</span><span>${text(job.explore_progress, "")}</span></div>
    `;
    button.addEventListener("click", () => selectJob(job.job_id));
    root.appendChild(button);
  });
}

function renderSummary() {
  const job = state.job;
  $("job-title").textContent = job ? text(job.component_name || job.job_id) : "No job selected";
  $("job-subtitle").textContent = job ? `${text(job.job_id)} - ${text(job.message || job.explore_message, "No message")}` : "Select a job";
  $("job-status").textContent = job ? text(job.status) : "n/a";
  $("job-stage").textContent = job ? activeStage(job).name : "n/a";
  $("job-progress").textContent = job ? text(job.explore_progress || job.progress) : "n/a";
  $("pipeline-state").textContent = job ? `${text(job.status)} / ${text(job.explore_phase)}` : "idle";
}

function renderPipeline() {
  const root = $("pipeline");
  const job = state.job;
  root.innerHTML = "";
  STAGES.forEach((stage) => {
    const currentState = stageState(job, stage);
    const button = document.createElement("button");
    button.className = `stage ${currentState} ${stage.id === state.selectedStageId ? "active" : ""}`;
    button.innerHTML = `
      <div class="stage-code">${stage.code}</div>
      <div class="stage-name">${stage.name}</div>
      <div class="stage-state">${stateLabel(currentState)}</div>
    `;
    button.addEventListener("click", () => selectStage(stage.id));
    root.appendChild(button);
  });
}

function eventMatchesStage(event, stage) {
  const blob = normalize(`${event.explore_stage} ${event.explore_phase} ${event.explore_message} ${event.message}`);
  return stage.aliases.some((alias) => blob.includes(normalize(alias)));
}

function formatEvent(event) {
  if (event.__done) return "stream closed: terminal job state reached";
  const status = text(event.status, "");
  const phase = text(event.explore_phase, "");
  const stage = text(event.explore_stage, "");
  const progress = text(event.explore_progress || event.progress, "");
  const message = text(event.explore_message || event.message || event.error, "");
  return [`status=${status}`, phase && `phase=${phase}`, stage && `stage=${stage}`, progress && `progress=${progress}`, message].filter(Boolean).join(" | ");
}

async function loadStageDetail() {
  state.stageDetail = null;
  if (!state.selectedJobId || !state.selectedStageId) return;
  const highLevel = HIGH_LEVEL_STAGE[state.selectedStageId] || state.selectedStageId;
  try {
    const payload = await getJson(`/api/dashboard/jobs/${state.selectedJobId}/stage-detail/${highLevel}`);
    state.stageDetail = payload.stage_detail || null;
  } catch (_err) {
    state.stageDetail = null;
  }
}

function renderLog() {
  const job = state.job;
  const stage = STAGES.find((item) => item.id === state.selectedStageId) || activeStage(job);
  $("log-title").textContent = stage ? `${stage.code} ${stage.name} Log` : "Pipeline Log";
  $("event-count").textContent = `${state.events.length} events`;

  const lines = [];
  if (job) {
    lines.push(`job ${job.job_id}`);
    lines.push(`component: ${text(job.component_name)}`);
    lines.push(`status: ${text(job.status)} / ${text(job.explore_phase)}`);
    lines.push(`stage: ${text(job.explore_stage || activeStage(job).id)}`);
    lines.push(`progress: ${text(job.explore_progress || job.progress)}`);
    lines.push(`message: ${text(job.explore_message || job.message || job.error, "No message")}`);
    lines.push("");
  }

  if (state.stageDetail) {
    lines.push("stage detail");
    lines.push(`goal: ${text(state.stageDetail.goal)}`);
    lines.push(`truth: ${text(state.stageDetail.stage_truth)}`);
    lines.push(`next: ${text(state.stageDetail.recommended_next_action)}`);
    lines.push("");
  }

  const matchingEvents = stage ? state.events.filter((event) => eventMatchesStage(event, stage)) : state.events;
  const visibleEvents = matchingEvents.length ? matchingEvents : state.events;
  lines.push("events");
  if (!visibleEvents.length) {
    lines.push("No live events received yet. Refreshing job status still works.");
  } else {
    visibleEvents.slice(-80).forEach((event, index) => {
      lines.push(`${String(index + 1).padStart(2, "0")}  ${formatEvent(event)}`);
    });
  }
  $("log").textContent = lines.join("\n");
}

function renderStageDetails() {
  const root = $("stage-details");
  const job = state.job;
  const stage = STAGES.find((item) => item.id === state.selectedStageId) || activeStage(job);
  const currentState = stageState(job, stage);
  const rows = [
    ["Stage", `${stage.code} ${stage.name}`],
    ["Goal", stage.goal],
    ["State", stateLabel(currentState)],
    ["Current backend stage", text(job?.explore_stage)],
    ["Phase", text(job?.explore_phase)],
    ["Progress", text(job?.explore_progress || job?.progress)],
    ["Last message", text(job?.explore_message || job?.message || job?.error, "No message")],
  ];
  if (state.stageDetail) {
    rows.push(["Backend goal", text(state.stageDetail.goal)]);
    rows.push(["Evidence", text((state.stageDetail.evidence?.items || []).length)]);
    rows.push(["Next action", text(state.stageDetail.recommended_next_action)]);
  }
  root.innerHTML = rows.map(([label, value]) => `
    <div class="detail-row">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `).join("");
}

function renderAll() {
  renderJobs();
  renderSummary();
  renderPipeline();
  renderStageDetails();
  renderLog();
}

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return response.json();
}

async function postJson(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_err) {
    payload = {};
  }
  if (!response.ok) throw new Error(payload.detail || `${path} -> ${response.status}`);
  return payload;
}

async function loadJobs() {
  const payload = await getJson("/api/jobs/recent");
  state.jobs = payload.jobs || [];
  if (!state.selectedJobId && state.jobs[0]) {
    await selectJob(state.jobs[0].job_id);
  } else if (!state.jobs.length) {
    state.job = null;
    state.selectedJobId = null;
    state.selectedStageId = state.selectedStageId || STAGES[0].id;
    state.events = [];
    if (state.eventSource) state.eventSource.close();
    state.eventSource = null;
    renderAll();
  } else {
    renderJobs();
  }
}

async function loadJob() {
  if (!state.selectedJobId) return;
  state.job = await getJson(`/api/jobs/${state.selectedJobId}`);
  if (!state.selectedStageId) state.selectedStageId = activeStage(state.job).id;
  await loadStageDetail();
  renderAll();
}

function watchJob(jobId) {
  if (state.eventSource) state.eventSource.close();
  state.events = [];
  state.eventSource = new EventSource(`/api/jobs/${jobId}/events`);
  state.eventSource.onmessage = async (event) => {
    try {
      const payload = JSON.parse(event.data);
      state.events.push(payload);
      if (!payload.__done) state.job = { ...(state.job || {}), ...payload };
      if (!state.selectedStageId && state.job) state.selectedStageId = activeStage(state.job).id;
      renderAll();
    } catch (_err) {
      state.events.push({ message: event.data });
      renderLog();
    }
  };
  state.eventSource.onerror = () => {
    state.events.push({ message: "event stream disconnected" });
    renderLog();
  };
}

async function selectJob(jobId) {
  state.selectedJobId = jobId;
  state.selectedStageId = null;
  state.stageDetail = null;
  renderJobs();
  await loadJob();
  watchJob(jobId);
}

async function selectStage(stageId) {
  state.selectedStageId = stageId;
  await loadStageDetail();
  renderAll();
}

async function refresh() {
  try {
    await loadJobs();
    await loadJob();
  } catch (err) {
    $("log").textContent = `Refresh failed: ${err.message}`;
  }
}

async function startTestRun() {
  const button = $("test-run");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Starting...";
  $("log").textContent = "Starting bundled test run...";
  try {
    const payload = await postJson("/api/dashboard/simple/test-run");
    await loadJobs();
    if (payload.job_id) {
      await selectJob(payload.job_id);
      $("log").textContent = `Started test run ${payload.job_id}.\nWaiting for pipeline events...`;
    } else {
      await refresh();
    }
  } catch (err) {
    $("log").textContent = `Could not start test run: ${err.message}`;
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

$("test-run").addEventListener("click", startTestRun);
$("refresh").addEventListener("click", refresh);
$("job-filter").addEventListener("input", renderJobs);

refresh();
setInterval(refresh, 5000);
