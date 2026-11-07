const STAGES = [
  { id: "analysis-entry", label: "Analysis Entry" },
  { id: "s00", label: "Setup" },
  { id: "s01", label: "Discovery" },
  { id: "s02", label: "Probe" },
  { id: "s03", label: "Model" },
  { id: "s04", label: "Cross DLL" },
  { id: "s05", label: "Enrich" },
  { id: "s06", label: "Verify" },
  { id: "s07", label: "Finalize" },
];

const state = {
  currentJobId: null,
  currentIterationId: null,
  currentCampaignId: null,
  currentJob: null,
  activeStageId: "s00",
  activeDiagnosisId: null,
  activeFamilyId: null,
  activeView: "triage",
  eventSource: null,
  diagnoses: [],
  familyBlockers: [],
  overview: null,
  decisionBasis: null,
  evidenceStack: [],
  iterationSummary: null,
  stageDetail: null,
  artifacts: null,
  health: null,
  recentJobs: [],
  activeTiers: new Set(["tier1"]),
  showAllTier1Evidence: false,
};

function isSingletonLayout() {
  return state.overview?.layout_mode === "singleton";
}

function getActiveFamily() {
  const activeDiagnosis = state.diagnoses.find((item) => item.diagnosis_id === state.activeDiagnosisId);
  const familyId = state.activeFamilyId || activeDiagnosis?.family_id;
  return state.familyBlockers.find((item) => item.family_id === familyId) || null;
}

const SURFACE_SOURCES = {
  investigation_focus: [
    "/api/jobs/{job_id}/diagnostics",
    "/api/jobs/{job_id}/causal-summary",
    "/api/jobs/{job_id}/artifacts",
    "/api/dashboard/jobs/{job_id}/diagnoses",
    "/api/dashboard/jobs/{job_id}/stage-detail/{stage_id}",
  ],
  artifact_tiers: [
    "/api/jobs/{job_id}/verdict-hierarchy",
    "/api/jobs/{job_id}/validation-status",
    "/api/jobs/{job_id}/causal-summary",
    "/api/jobs/{job_id}/artifacts",
    "/api/jobs/{job_id}/report",
    "/api/findings/{job_id}",
  ],
};

const $ = (id) => document.getElementById(id);

function humanizeStepToken(raw) {
  const text = String(raw || "").trim();
  if (!text) return "Current Step";
  const match = text.match(/^(\d+)[-_ ]*(.*)$/);
  let prefix = "";
  let core = text;
  if (match) {
    prefix = `${String(match[1]).padStart(2, "0")} `;
    core = match[2] || "";
  }
  if (core.includes(".")) {
    core = core.split(".", 1)[0];
  }
  if (core.startsWith("spectrum_")) {
    core = core.slice("spectrum_".length);
  }
  const label = core
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
  return `${prefix}${label || text}`.trim();
}

function chainStepLabel(job) {
  return humanizeStepToken(job?.playbook_step || job?.component_name || job?.job_id || "current-step");
}

function setDot(id, status) {
  const el = $(id);
  if (!el) return;
  const tone = String(status || "").toLowerCase();
  el.style.background =
    tone === "ok" || tone === "valid" ? "var(--ok)" :
    tone === "degraded" || tone === "warn" ? "var(--warn)" :
    tone === "invalid" || tone === "error" ? "var(--danger)" :
    "var(--muted)";
}

async function getJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function postJson(path) {
  const res = await fetch(path, { method: "POST" });
  let payload = {};
  try {
    payload = await res.json();
  } catch (_err) {
    payload = {};
  }
  if (!res.ok) throw new Error(payload.detail || `${path} -> ${res.status}`);
  return payload;
}

function renderEvidence(targetId, items) {
  const root = typeof targetId === "string" ? $(targetId) : targetId;
  if (!root) return;
  root.innerHTML = "";
  const payload = Array.isArray(items) ? { items } : (items || {});
  const allItems = payload.items || [];
  const visibleItems = allItems.filter((item) => !item.tier || state.activeTiers.has(item.tier));
  if (!allItems.length) {
    root.innerHTML = `<div class="small-note">No ranked evidence emitted yet.</div>`;
    return;
  }
  let finalItems = visibleItems;
  if (!state.showAllTier1Evidence) {
    const visibleDefaultCount = payload.visible_default_count || 3;
    const tier1Visible = visibleItems.filter((item) => item.tier === "tier1");
    const nonTier1Visible = visibleItems.filter((item) => item.tier !== "tier1");
    finalItems = [...tier1Visible.slice(0, visibleDefaultCount), ...nonTier1Visible];
  }
  if (!finalItems.length) {
    const hidden = document.createElement("div");
    hidden.className = "evidence-collapsed";
    hidden.textContent = "Current evidence is in collapsed tiers. Enable Tier 2 or Tier 3 to inspect deeper evidence.";
    root.appendChild(hidden);
    return;
  }
  finalItems.forEach((item) => {
    const card = document.createElement("div");
    const type = item.evidence_type || "supporting evidence";
    const typeClass = String(type).toLowerCase().replaceAll(" ", "-");
    card.className = `evidence-card ${typeClass}`;
    const why = item.why_it_matters || item.summary || "";
    const preview = item.preview_text || item.summary || "";
    card.innerHTML = `
      <div class="evidence-head">
        <div class="diagnosis-title">${item.label || "Evidence"}</div>
        <span class="tier-pill ${typeClass}">${type}</span>
      </div>
      ${item.summary ? `<div class="small-note">${item.summary}</div>` : ""}
      ${why ? `<div class="small-note"><strong>Why it matters:</strong> ${why}</div>` : ""}
      ${preview ? `<div class="evidence-preview">${preview}</div>` : ""}
      <div class="evidence-actions">
        <div class="small-note">${(item.tier || "tier1").toUpperCase()}</div>
        ${item.raw_url || item.url ? `<a class="evidence-link secondary" href="${item.raw_url || item.url}" target="_blank">Open raw</a>` : ""}
      </div>
    `;
    root.appendChild(card);
  });
  if (payload.has_more_tier1 && !state.showAllTier1Evidence && state.activeTiers.has("tier1")) {
    const more = document.createElement("div");
    more.className = "evidence-stack-more";
    more.innerHTML = `<button class="action">${payload.more_label || "Show more Tier 1 evidence"}</button>`;
    more.querySelector("button")?.addEventListener("click", () => {
      state.showAllTier1Evidence = true;
      renderEvidence(root, payload);
    });
    root.appendChild(more);
  }
}

function renderSimpleList(targetId, rows) {
  const root = $(targetId);
  if (!root) return;
  root.innerHTML = "";
  (rows || []).forEach((row) => {
    const item = document.createElement("div");
    item.className = "kv";
    item.innerHTML = `<span>${row.label}</span><span>${row.value}</span>`;
    root.appendChild(item);
  });
}

function renderDenseGroup(root, title, rows) {
  const group = document.createElement("div");
  group.className = "summary-group";
  group.innerHTML = `
    <div class="summary-group-title">${title}</div>
    <div class="metric-grid">
      ${(rows || []).map((row) => `
        <div class="metric-cell">
          <div class="metric-label">${row.label}</div>
          <div class="metric-value">${row.value}</div>
        </div>
      `).join("")}
    </div>
  `;
  root.appendChild(group);
}

function renderOperatorAnalysis(target, operatorView, analysisView) {
  const root = typeof target === "string" ? $(target) : target;
  if (!root) return;
  const wrapper = document.createElement("div");
  wrapper.className = "side-by-side";
  const operator = document.createElement("div");
  operator.className = "oa-card";
  operator.innerHTML = `
    <div class="panel-title tight">Operator View</div>
    <div class="small-note">${operatorView?.summary || operatorView?.headline || "No operator summary emitted."}</div>
    ${operatorView?.next_action ? `<div class="small-note"><strong>Next:</strong> ${operatorView.next_action}</div>` : ""}
  `;
  const analysis = document.createElement("div");
  const rows = buildReadableAnalysisRows(analysisView);
  analysis.className = "oa-card";
  analysis.innerHTML = `
    <div class="panel-title tight">Analysis View</div>
    ${rows.length ? `<div class="analysis-list">${rows.map((row) => `<div class="analysis-row"><span>${row.label}</span><span>${row.value}</span></div>`).join("")}</div>` : `<div class="small-note">No readable analysis summary emitted.</div>`}
    <details class="analysis-details">
      <summary>Open structured analysis</summary>
      <pre class="analysis-pre">${JSON.stringify(analysisView || {}, null, 2)}</pre>
    </details>
  `;
  wrapper.appendChild(operator);
  wrapper.appendChild(analysis);
  root.appendChild(wrapper);
}

function buildReadableAnalysisRows(analysisView) {
  if (!analysisView || typeof analysisView !== "object") return [];
  if (analysisView.readable_analysis_rows && Array.isArray(analysisView.readable_analysis_rows)) {
    return analysisView.readable_analysis_rows;
  }
  if (analysisView.layers && typeof analysisView.layers === "object") {
    return Object.entries(analysisView.layers).slice(0, 4).map(([key, value]) => ({
      label: key.replaceAll("_", " "),
      value: value?.status || value?.summary || "unknown",
    }));
  }
  if (analysisView.root_failure && typeof analysisView.root_failure === "object") {
    return [
      { label: "job status", value: analysisView.root_failure.job_status || "unknown" },
      { label: "job error", value: analysisView.root_failure.error_excerpt || "n/a" },
      { label: "findings", value: analysisView.root_failure.has_findings ? "present" : "missing" },
      { label: "stage index", value: analysisView.root_failure.has_stage_index ? "present" : "missing" },
      { label: "transition index", value: analysisView.root_failure.has_transition_index ? "present" : "missing" },
    ];
  }
  if (analysisView.causal_summary_text || analysisView.error_excerpt || analysisView.artifact_count !== undefined) {
    return [
      { label: "causal summary", value: analysisView.causal_summary_text || "n/a" },
      { label: "blast radius", value: analysisView.blast_radius_summary || "n/a" },
      { label: "error excerpt", value: analysisView.error_excerpt || "n/a" },
      { label: "findings", value: analysisView.emitted_findings || "unknown" },
      { label: "artifact count", value: String(analysisView.artifact_count ?? "0") },
      { label: "manifest present", value: analysisView.manifest_present || "unknown" },
    ];
  }
  if (analysisView.promoted_because || analysisView.demoted_candidates) {
    return [
      { label: "promoted reasons", value: String((analysisView.promoted_because || []).length) },
      { label: "demoted reasons", value: String((analysisView.demoted_candidates || []).length) },
      { label: "confidence", value: String(analysisView.confidence ?? "n/a") },
    ];
  }
  return Object.entries(analysisView)
    .slice(0, 6)
    .map(([key, value]) => ({
      label: key.replaceAll("_", " "),
      value: typeof value === "object" ? JSON.stringify(value) : String(value),
    }));
}

function renderInvestigationSources() {
  const root = $("investigation-sources");
  if (!root) return;
  root.innerHTML = "";
  const rows = [
    `/api/jobs/${state.currentJobId || "job"}/verdict-hierarchy`,
    `/api/jobs/${state.currentJobId || "job"}/validation-status`,
    `/api/jobs/${state.currentJobId || "job"}/causal-summary`,
    `/api/jobs/${state.currentJobId || "job"}/diagnostics`,
    `/api/jobs/${state.currentJobId || "job"}/artifacts`,
    `/api/dashboard/jobs/${state.currentJobId || "job"}/decision-basis`,
    `/api/dashboard/jobs/${state.currentJobId || "job"}/evidence-stack`,
    `/api/dashboard/jobs/${state.currentJobId || "job"}/stage-detail/${state.activeStageId || "stage"}`,
  ];
  rows.forEach((row) => {
    const item = document.createElement("div");
    item.className = "source-code";
    item.textContent = row;
    root.appendChild(item);
  });
}

function renderInvestigationFocus() {
  const root = $("investigation-focus");
  if (!root) return;
  root.innerHTML = "";
  const visibleDiagnoses = getVisibleDiagnoses();
  const diagnosis = visibleDiagnoses.find((item) => item.diagnosis_id === state.activeDiagnosisId) || visibleDiagnoses[0];
  const family = getActiveFamily();
  if (!diagnosis) {
    root.innerHTML = `<div class="small-note">Select a job to see the active diagnosis, why it matters, and which hooks are driving this summary.</div>`;
    return;
  }
  const card = document.createElement("div");
  card.className = `diagnosis-summary severity-${diagnosis.severity || "low"}`;
  const whyPromoted = state.decisionBasis?.promoted_because?.[0] || "Earliest trustworthy blocker";
  const narrative = diagnosis.narrative || state.overview?.top_blocker?.operator_view?.summary || diagnosis.primary_evidence.summary;
  const nextStep = diagnosis.recommended_next_action;
  const representativeEvidence = family?.representative_evidence?.summary || diagnosis.primary_evidence.summary;
  card.innerHTML = `
    <div class="diagnosis-top">
      <div class="diagnosis-title">${diagnosis.title}</div>
      <span class="pill ${diagnosis.severity}">${diagnosis.severity}</span>
    </div>
    <div class="narrative-block">
      <div class="narrative-text">${narrative}</div>
      <div class="narrative-text">Promoted because ${whyPromoted.toLowerCase()}. Next: ${nextStep}</div>
    </div>
    <div class="meta-chip-grid">
      ${family && isSingletonLayout() ? `<div class="meta-chip"><span>Family</span><strong>${family.title}</strong></div>` : ""}
      <div class="meta-chip"><span>Stage</span><strong>${diagnosis.first_failing_stage}</strong></div>
      <div class="meta-chip"><span>Owner</span><strong>${diagnosis.owner_layer}</strong></div>
      <div class="meta-chip"><span>Trust</span><strong>${diagnosis.trust_impact}</strong></div>
      <div class="meta-chip"><span>Severity</span><strong>${diagnosis.severity}</strong></div>
      ${family && isSingletonLayout() ? `<div class="meta-chip"><span>Diag count</span><strong>${family.affected_diagnosis_count}</strong></div>` : ""}
      ${family && isSingletonLayout() ? `<div class="meta-chip"><span>Stage count</span><strong>${family.affected_stage_count}</strong></div>` : ""}
    </div>
    <div class="representative-line">
      <span class="metric-label">Representative evidence</span>
      <span class="small-note">${representativeEvidence}</span>
    </div>
    <div class="source-block">
      <div class="panel-title">Trace Sources</div>
      <div class="stack small source-code">
        ${SURFACE_SOURCES.investigation_focus.map((path) => `<div>${path.replaceAll("{job_id}", state.currentJobId || "job").replaceAll("{stage_id}", state.activeStageId || "stage")}</div>`).join("")}
      </div>
    </div>
  `;
  root.appendChild(card);
  renderOperatorAnalysis(root, diagnosis.operator_view || state.overview?.top_blocker?.operator_view, diagnosis.analysis_view || state.overview?.top_blocker?.analysis_view);
  renderInvestigationSources();
}

function renderIterationSummary(summary) {
  const root = $("iteration-summary");
  if (!root) return;
  root.innerHTML = "";
  if (!summary) {
    root.innerHTML = `<div class="small-note">Select an iteration to see verdict layers, delta, and current stage context.</div>`;
    return;
  }
  const groups = summary.groups || {};
  renderDenseGroup(root, "Run status", groups.run_status || []);
  renderDenseGroup(root, "Verdict layers", groups.verdict_layers || []);
  renderDenseGroup(root, "Delta", groups.delta || []);
  renderOperatorAnalysis(root, summary.operator_view, summary.analysis_view);
}

function renderCurrentContext() {
  const root = $("current-context");
  if (!root) return;
  root.innerHTML = "";
  const context = state.overview?.current_context || {};
  const rows = [
    { label: "Campaign", value: state.currentCampaignId || context.campaign_id || "n/a" },
    { label: "Iteration", value: state.currentIterationId || context.iteration_id || "n/a" },
    { label: "Chain Step", value: context.chain_step_label || chainStepLabel(state.currentJob) || "n/a" },
    { label: "Pipeline Stage", value: context.pipeline_stage_label || state.iterationSummary?.pipeline_stage_label || "n/a" },
    { label: "Family", value: state.activeFamilyId || context.family_title || context.family_id || "n/a" },
    {
      label: "Diagnosis",
      value:
        state.diagnoses.find((item) => item.diagnosis_id === state.activeDiagnosisId)?.title ||
        context.diagnosis_title ||
        "n/a",
    },
    {
      label: "Evidence Tiers",
      value: Array.from(state.activeTiers).sort().join(", ") || "n/a",
    },
  ];
  rows.forEach((row) => {
    const item = document.createElement("div");
    item.className = "context-card";
    item.innerHTML = `<div class="kv"><span>${row.label}</span><span>${row.value}</span></div>`;
    root.appendChild(item);
  });
}

function renderChainContext() {
  const root = $("chain-context");
  if (!root) return;
  root.innerHTML = "";
  const chain = state.decisionBasis?.chain_context || state.iterationSummary?.chain_context;
  if (!chain) {
    root.innerHTML = `<div class="small-note">Select a job to see predecessor, current step, and blocked downstream chain context.</div>`;
    return;
  }
  [
    { label: "Predecessor Step", value: chain.predecessor_step_label || chain.predecessor || "n/a" },
    { label: "Chain Step", value: chain.current_step_label || chain.current_step || "n/a" },
    { label: "Pipeline Stage", value: chain.pipeline_stage_label || "n/a" },
    { label: "Downstream Blocked", value: (chain.downstream_blocked || []).join("; ") || "not emitted" },
    {
      label: "Scope",
      value: `campaign ${state.currentCampaignId || "n/a"} / iteration ${state.currentIterationId || "n/a"} / stage ${chain.pipeline_stage_label || state.activeStageId || "n/a"}`,
    },
  ].forEach((row) => {
    const item = document.createElement("div");
    item.className = "context-card";
    item.innerHTML = `<div class="kv"><span>${row.label}</span><span>${row.value}</span></div>`;
    root.appendChild(item);
  });
}

function renderChainSteps() {
  const root = $("chain-steps");
  if (!root) return;
  root.innerHTML = "";
  const chain = state.iterationSummary?.chain_context || state.decisionBasis?.chain_context;
  const steps = chain?.chain_steps || [];
  if (!steps.length) {
    root.innerHTML = `<div class="small-note">Chain-step context is not available for the selected iteration.</div>`;
    return;
  }
  steps.forEach((step) => {
    const node = document.createElement("div");
    node.className = `chain-step-node ${step.status || "pending"} ${step.selected ? "selected" : ""}`;
    node.innerHTML = `
      <div class="chain-step-order">${step.label}</div>
      <div class="small-note">${step.selected ? "active focus" : (step.status || "pending")}</div>
    `;
    root.appendChild(node);
  });
}

function renderFamilyBlockers() {
  const root = $("family-blockers");
  if (!root) return;
  root.innerHTML = "";
  root.classList.add("family-blockers-compact");
  if (!state.familyBlockers.length) {
    root.innerHTML = `<div class="small-note">No family blockers emitted yet for the selected iteration.</div>`;
    return;
  }
  state.familyBlockers.forEach((family) => {
    const card = document.createElement("button");
    card.className = `family-card ${family.family_id === state.activeFamilyId ? "active" : ""}`;
    card.innerHTML = `
      <div class="diagnosis-top">
        <div class="diagnosis-title">${family.title}</div>
        <span class="pill ${family.severity}">${family.severity}</span>
      </div>
      <div class="kv"><span>Diagnoses</span><span>${family.affected_diagnosis_count}</span></div>
      <div class="kv"><span>Stages</span><span>${family.affected_stage_count}</span></div>
      <div class="small-note">${family.representative_evidence.summary}</div>
    `;
    card.addEventListener("click", async () => {
      state.activeFamilyId = state.activeFamilyId === family.family_id ? null : family.family_id;
      const visibleDiagnoses = getVisibleDiagnoses();
      state.activeDiagnosisId = visibleDiagnoses[0]?.diagnosis_id || null;
      if (visibleDiagnoses[0]) {
        state.activeStageId = visibleDiagnoses[0].first_failing_stage;
      }
      renderFamilyBlockers();
      await loadDiagnoses();
      await loadStageDetail();
      renderCurrentContext();
      renderChainContext();
    });
    root.appendChild(card);
  });
}

function renderProofSummary() {
  const root = $("proof-summary");
  if (!root) return;
  root.innerHTML = "";
  const summary = state.overview?.proof_summary;
  if (!summary) {
    root.innerHTML = `<div class="small-note">Proof summary will appear once a job is selected.</div>`;
    return;
  }
  root.innerHTML = `
    <div class="tier-card">
      <div class="diagnosis-title">Proof Summary</div>
      <div class="stack small">
        <div class="small-note">${summary.proof_posture || "Proof posture is not available yet."}</div>
        <div class="proof-list">
          <div class="metric-label">Present proof</div>
          <div class="small-note">${(summary.present_proof || []).join(", ") || "n/a"}</div>
        </div>
        <div class="proof-list">
          <div class="metric-label">Missing proof</div>
          <div class="small-note">${(summary.missing_proof || []).join(", ") || "n/a"}</div>
        </div>
        <div class="kv"><span>Visible Tier 1</span><span>${summary.visible_tier1_count}</span></div>
        <div class="kv"><span>Hidden Tier 1</span><span>${summary.hidden_tier1_count}</span></div>
        <div class="kv"><span>Hidden Tier 2</span><span>${summary.hidden_tier2_count}</span></div>
        <div class="kv"><span>Hidden Tier 3</span><span>${summary.hidden_tier3_count}</span></div>
      </div>
    </div>
  `;
}

function applyAdaptiveLayout() {
  const content = document.querySelector(".content");
  if (!content) return;
  const singleton = isSingletonLayout();
  content.classList.toggle("singleton-layout", singleton);
  $("family-blockers-panel")?.classList.toggle("hidden", singleton);
  $("investigation-sources-panel")?.classList.toggle("hidden", singleton);
  $("diagnoses-panel")?.classList.toggle("compact-singleton", singleton);
}

function renderArtifactTiers() {
  const root = $("artifact-tiers");
  if (!root) return;
  root.innerHTML = "";
  [
    {
      key: "tier1",
      label: "Tier 1",
      title: "Decision now",
      detail: "Top blocker, canonical diagnosis, primary evidence, and the single next action.",
    },
    {
      key: "tier2",
      label: "Tier 2",
      title: "Context for the blocker",
      detail: "Stage detail, verdict layers, blast radius, and trust frontier.",
    },
    {
      key: "tier3",
      label: "Tier 3",
      title: "Deep inspection",
      detail: "Raw findings, report artifacts, and event log support for manual investigation.",
    },
  ].forEach((tier) => {
    const card = document.createElement("div");
    card.className = "tier-card";
    card.innerHTML = `
      <div class="tier-head">
        <div class="diagnosis-title">${tier.title}</div>
        <span class="tier-pill">${tier.label}${state.activeTiers.has(tier.key) ? " active" : " hidden"}</span>
      </div>
      <div class="small-note">${tier.detail}</div>
    `;
    root.appendChild(card);
  });
  const source = document.createElement("div");
  source.className = "tier-card";
  source.innerHTML = `
    <div class="panel-title">Trace Sources</div>
    <div class="stack small source-code">
      ${SURFACE_SOURCES.artifact_tiers.map((path) => `<div>${path.replaceAll("{job_id}", state.currentJobId || "job")}</div>`).join("")}
    </div>
  `;
  root.appendChild(source);
  if (state.artifacts) {
    renderOperatorAnalysis(root, state.artifacts.operator_view, state.artifacts.analysis_view);
  }
  renderProofSummary();
}

function renderDecisionBasis() {
  const root = $("decision-basis");
  const pill = $("alignment-status-pill");
  if (!root || !pill) return;
  root.innerHTML = "";
  const basis = state.decisionBasis;
  if (!basis) {
    root.innerHTML = `<div class="small-note">Select a job to see why the cockpit promoted the current blocker and what it explicitly demoted.</div>`;
    pill.textContent = "alignment pending";
    pill.className = "scope-pill";
    return;
  }
  pill.textContent = basis.alignment_status === "aligned" ? "operator-agent aligned" : basis.alignment_status;
  pill.className = `scope-pill ${basis.alignment_status === "aligned" ? "aligned" : basis.alignment_status === "misaligned" ? "misaligned" : "partial"}`;
  const sections = [
    { title: "Promoted Because", items: basis.promoted_because || [] },
    { title: "Not Promoted Because", items: basis.demoted_candidates || [] },
    { title: "Source Routes", items: basis.source_routes || [] },
  ];
  sections.forEach((section) => {
    const block = document.createElement("div");
    block.className = "tier-card";
    block.innerHTML = `
      <div class="diagnosis-title">${section.title}</div>
      <div class="stack small">${(section.items.length ? section.items : ["n/a"]).map((item) => `<div class="small-note">${item}</div>`).join("")}</div>
    `;
    root.appendChild(block);
  });
  renderOperatorAnalysis(root, basis.operator_view, basis.analysis_view);
  renderChainContext();
}

function applyTierFilters() {
  document.querySelectorAll(".tier-filter").forEach((button) => {
    button.classList.toggle("active", state.activeTiers.has(button.dataset.tier));
  });
  document.querySelectorAll(".tier-surface").forEach((surface) => {
    const tier = surface.dataset.tier;
    surface.classList.toggle("surface-hidden", !state.activeTiers.has(tier));
  });
  renderArtifactTiers();
  renderEvidence("supporting-evidence", state.evidenceStack);
  renderCurrentContext();
}

function updatePackageIntakeCopy() {
  const shape = $("intake-shape")?.value || "package";
  const note = $("package-intake-note");
  if (!note) return;
  if (shape === "package") {
    note.textContent = "Package mode is preferred. Today it still routes through the same path-based backend hook.";
  } else if (shape === "fixture") {
    note.textContent = "Fixture mode is useful for controlled repro. It selects a known path but still uses the same backend intake route.";
  } else {
    note.textContent = "DLL mode is still supported for narrow debugging, but it is not the preferred product workflow.";
  }
}

function renderRecentJobs() {
  const root = $("recent-jobs");
  if (!root) return;
  root.innerHTML = "";
  const query = String($("recent-jobs-filter")?.value || "").trim().toLowerCase();
  const jobs = (state.recentJobs || []).filter((job) => {
    if (!query) return true;
    const haystack = [
      job.component_name,
      job.job_id,
      job.campaign_id,
    ].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(query);
  });
  jobs.slice(0, 12).forEach((job) => {
    const btn = document.createElement("button");
    btn.className = "job-btn";
    btn.textContent = `${chainStepLabel(job)} (${job.verified_count || 0}/${job.total_count || 0})`;
    btn.addEventListener("click", () => selectJob(job.job_id, job.campaign_id));
    root.appendChild(btn);
  });
  if (!jobs.length) {
    root.innerHTML = `<div class="small-note">No jobs match the current filter.</div>`;
  }
}

function renderIterationSelector() {
  const selector = $("iteration-selector");
  if (!selector) return;
  const current = state.currentIterationId || "";
  selector.innerHTML = `<option value="">Select iteration</option>`;
  (state.recentJobs || []).slice(0, 24).forEach((job) => {
    const option = document.createElement("option");
    option.value = job.job_id;
    option.textContent = `${chainStepLabel(job)} (${job.job_id})`;
    if (job.job_id === current) {
      option.selected = true;
    }
    selector.appendChild(option);
  });
}

function getVisibleDiagnoses() {
  return (state.diagnoses || []).filter((diagnosis) => {
    if (state.activeFamilyId && diagnosis.family_id !== state.activeFamilyId) return false;
    if (state.activeStageId && diagnosis.first_failing_stage !== state.activeStageId) {
      const anyInStage = (state.diagnoses || []).some((item) => {
        const familyMatch = state.activeFamilyId ? item.family_id === state.activeFamilyId : true;
        return familyMatch && item.first_failing_stage === state.activeStageId;
      });
      if (anyInStage) return false;
    }
    return true;
  });
}

function inferStage(job) {
  if (String(job?.status || "").toLowerCase() === "error") return "analysis-entry";
  const phase = String(job?.explore_phase || "").toLowerCase();
  const mapped = STAGES.find((stage) => phase.includes(stage.id));
  if (mapped) return mapped.id;
  if (phase === "done") return "s07";
  if (phase === "error") return "analysis-entry";
  return "s00";
}

function stageIndex(stageId) {
  return STAGES.findIndex((stage) => stage.id === stageId);
}

function setLabBanner(health, detail) {
  const banner = $("lab-banner");
  const detailEl = $("lab-banner-detail");
  const copyEl = $("lab-status-copy");
  if (!banner || !detailEl || !copyEl) return;
  const offline = !health || !health.apiOk || !health.bridgeOk;
  banner.classList.toggle("hidden", !offline);
  if (offline) {
    const message = detail || "The dashboard is reachable, but the API or bridge is offline. Refresh if the state is stale, or restart the lab services if launch hooks are failing.";
    detailEl.textContent = message;
    copyEl.textContent = message;
  } else {
    copyEl.textContent = "The lab is healthy enough for launch and job selection. Restart is only needed when API and bridge stay down or hook routes keep returning 500s.";
  }
}

function buildStageTrack(job) {
  const root = $("stage-track");
  if (!root) return;
  root.innerHTML = "";
  const active = state.activeStageId || inferStage(job);
  const activeDiagnosis = (state.diagnoses || []).find((item) => item.diagnosis_id === state.activeDiagnosisId);
  const currentJob = state.currentJob || job || {};
  const currentStatus = String(currentJob?.status || "").toLowerCase();
  const activeIndex = stageIndex(active);
  STAGES.forEach((stage) => {
    let stageState = "pending";
    const idx = stageIndex(stage.id);
    if (stage.id === active) {
      stageState = currentStatus === "error" ? "fail" : (currentStatus === "done" ? "pass" : "warn");
    } else if (active === "analysis-entry") {
      stageState = "pending";
    } else if (idx > -1 && activeIndex > -1 && idx < activeIndex) {
      stageState = currentStatus === "error" || currentStatus === "done" ? "pass" : "warn";
    } else if (activeDiagnosis && stage.id === activeDiagnosis.first_failing_stage) {
      stageState = "fail";
    }
    const node = document.createElement("button");
    node.className = `stage-node ${stage.id === active ? "active" : ""} ${stageState}`;
    node.innerHTML = `<div>${stage.id.toUpperCase()}</div><div class="small-note">${stage.label}</div>`;
    node.addEventListener("click", async () => {
      state.activeStageId = stage.id;
      await loadDiagnoses();
      await loadStageDetail();
      buildStageTrack(job);
    });
    root.appendChild(node);
  });
}

async function loadHealth() {
  try {
    const lab = await getJson("/api/lab/status");
    const health = {
      apiOk: String(lab.api?.status || "").toLowerCase() === "ok",
      bridgeOk: String(lab.bridge?.status || "").toLowerCase() === "ok",
      modelOk: String(lab.model?.status || "").toLowerCase() === "ok",
      storageOk: String(lab.storage?.status || "").toLowerCase() === "ok",
      laneOk: String(lab.lane_validity?.status || "").toLowerCase() === "ok",
    };
    state.health = health;
    setDot("health-api", lab.api?.status);
    setDot("health-bridge", lab.bridge?.status);
    setDot("health-model", lab.model?.status);
    setDot("health-storage", lab.storage?.status);
    setDot("health-lane", lab.lane_validity?.status);
    setLabBanner(health, !health.laneOk ? "The lab is up, but lane validity is degraded. Treat the cockpit as triage-first until the lane is healthy again." : "");
    return health;
  } catch (err) {
    state.health = { apiOk: false, bridgeOk: false, modelOk: false, storageOk: false, laneOk: false };
    ["health-api", "health-bridge", "health-model", "health-storage", "health-lane"].forEach((id) => setDot(id, "error"));
    setLabBanner(state.health, `Health check failed: ${err.message}`);
    return state.health;
  }
}

async function loadFixtures() {
  const root = $("fixtures");
  const select = $("fixture-select");
  if (root) root.innerHTML = "";
  if (select) select.innerHTML = `<option value="">Select a fixture</option>`;
  try {
    const payload = await getJson("/api/fixtures");
    (payload.fixtures || []).slice(0, 12).forEach((fixture) => {
      if (root) {
        const btn = document.createElement("button");
        btn.className = "fixture-btn";
        btn.textContent = fixture.name || fixture.path;
        btn.addEventListener("click", () => runPath(fixture.path));
        root.appendChild(btn);
      }
      if (select) {
        const option = document.createElement("option");
        option.value = fixture.path;
        option.textContent = fixture.name || fixture.path;
        select.appendChild(option);
      }
    });
  } catch (err) {
    if (root) root.innerHTML = `<div class="small-note">Could not load fixtures: ${err.message}</div>`;
  }
}

async function loadRecentJobs() {
  const root = $("recent-jobs");
  if (!root) return;
  root.innerHTML = "";
  try {
    const payload = await getJson("/api/jobs/recent");
    state.recentJobs = payload.jobs || [];
    renderRecentJobs();
    renderIterationSelector();
    const first = state.recentJobs[0];
    if (first && !state.currentJobId) {
      selectJob(first.job_id, first.campaign_id);
    }
  } catch (err) {
    state.recentJobs = [];
    root.innerHTML = `<div class="small-note">Could not load recent jobs: ${err.message}</div>`;
  }
}

async function loadHookReadiness() {
  const payload = await getJson("/api/dashboard/hooks");
  renderSimpleList("hook-readiness", [
    { label: "Ready Now", value: String((payload.ready_now || []).length) },
    { label: "Derived Placeholders", value: String((payload.dashboard_derived_placeholder || []).length) },
    { label: "Native Hooks Needed", value: String((payload.pipeline_native_route_still_needed || []).length) },
  ]);
}

async function refreshDashboard() {
  await Promise.allSettled([loadHealth(), loadFixtures(), loadRecentJobs(), loadHookReadiness()]);
  if (state.currentJobId) {
    await Promise.allSettled([
      loadOverview(),
      loadEvidenceStack(),
      loadDecisionBasis(),
      loadDiagnoses(),
      loadRunDiff(),
      loadTrustFrontier(),
      loadBlastRadius(),
      loadStageDetail(),
    ]);
    if (state.activeView === "campaign") {
      await Promise.allSettled([loadCampaignOverview()]);
    }
  }
}

async function restartLab() {
  const logRoot = $("event-log");
  try {
    const payload = await postJson("/api/dashboard/lab/restart");
    if (logRoot) {
      logRoot.innerHTML = `<div class="event-item">${payload.detail}</div>`;
    }
    setLabBanner({ apiOk: false, bridgeOk: false }, "Restart requested. Waiting for bridge 8090 and API 8201 to recover.");
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const health = await loadHealth();
      if (health?.apiOk && health?.bridgeOk) {
        await refreshDashboard();
        if (logRoot) {
          logRoot.innerHTML = `<div class="event-item">Lab services recovered and the cockpit reloaded current hooks.</div>`;
        }
        return;
      }
    }
    if (logRoot) {
      logRoot.innerHTML = `<div class="event-item">Restart was requested, but the lab did not recover within the expected window. Re-run .\\start.ps1 if needed.</div>`;
    }
  } catch (err) {
    if (logRoot) {
      logRoot.innerHTML = `<div class="event-item">${err.message}</div>`;
    }
  }
}

async function runPath(path) {
  const trimmed = String(path || "").trim();
  if (!trimmed) return;
  const res = await fetch("/api/analyze-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: trimmed }),
  });
  const payload = await res.json();
  if (!res.ok || !payload.job_id) {
    throw new Error(payload.detail || "Could not launch analysis.");
  }
  selectJob(payload.job_id, payload.campaign_id);
}

function resolveIntakePath() {
  const shape = $("intake-shape")?.value || "package";
  if (shape === "fixture") {
    return $("fixture-select")?.value || "";
  }
  return $("custom-path")?.value || "";
}

function watchEvents(jobId) {
  if (state.eventSource) state.eventSource.close();
  const log = $("event-log");
  if (log) log.innerHTML = "";
  state.eventSource = new EventSource(`/api/jobs/${jobId}/events`);
  state.eventSource.onmessage = (event) => {
    const logRoot = $("event-log");
    if (!logRoot) return;
    const item = document.createElement("div");
    item.className = "event-item";
    item.textContent = event.data;
    logRoot.prepend(item);
  };
}

async function loadOverview() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/overview`);
  const overview = payload.overview;
  state.overview = overview;
  $("top-blocker-title").textContent = overview.top_blocker.title;
  $("top-blocker-meta").textContent = `${overview.top_blocker.operator_view?.summary || `${overview.top_blocker.severity} - ${overview.top_blocker.class} - ${overview.top_blocker.owner_layer}`}`;
  $("trust-delta").textContent = `${overview.trust_delta_vs_last_good.verified_count_delta >= 0 ? "+" : ""}${overview.trust_delta_vs_last_good.verified_count_delta}`;
  $("trust-delta-meta").textContent = overview.trust_delta_vs_last_good.operator_view?.summary || `Contradiction delta ${overview.trust_delta_vs_last_good.contradiction_delta}. ${overview.trust_delta_vs_last_good.placeholder ? "Derived from current hooks." : ""}`;
  $("iteration-change").textContent = `${overview.what_changed_this_iteration.job_status || "unknown"} / ${overview.what_changed_this_iteration.explore_phase || "unknown"}`;
  $("iteration-change-meta").textContent = `${overview.what_changed_this_iteration.verified_count || 0}/${overview.what_changed_this_iteration.total_count || 0} verified`;
  $("blast-radius-summary").textContent = overview.blast_radius.summary;
  $("blast-radius-meta").textContent = overview.blast_radius.operator_view?.summary || `${(overview.blast_radius.affected_targets || []).join(", ") || "No affected targets emitted."}${overview.blast_radius.locally_green_but_globally_untrusted ? " Local green is not globally trusted." : ""}`;
  $("next-action").textContent = overview.recommended_next_action;
  $("next-action-meta").textContent = overview.alignment_status === "aligned" ? "Operator and agent are currently aligned on this next move." : (overview.placeholder ? "This recommendation is derived until native summary hooks exist." : "Pipeline-native summary.");
  $("primary-cause").textContent = overview.primary_cause || "n/a";
  $("secondary-consequence").textContent = overview.secondary_consequence || "n/a";
  $("not-promoted").textContent = overview.not_promoted || "n/a";
  renderCurrentContext();
  renderArtifactTiers();
  applyAdaptiveLayout();
}

async function loadEvidenceStack() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/evidence-stack`);
  state.evidenceStack = payload.evidence_stack || { items: [] };
  state.showAllTier1Evidence = false;
  renderEvidence("supporting-evidence", state.evidenceStack);
}

async function loadDecisionBasis() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/decision-basis`);
  state.decisionBasis = payload.decision_basis;
  renderDecisionBasis();
  applyAdaptiveLayout();
}

async function loadIterationSummary() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/iteration-summary`);
  state.iterationSummary = payload.iteration_summary;
  renderIterationSummary(state.iterationSummary);
  renderChainSteps();
  renderCurrentContext();
  renderChainContext();
}

async function loadFamilyBlockers() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/family-blockers`);
  state.familyBlockers = payload.family_blockers || [];
  if (state.activeFamilyId && !state.familyBlockers.some((item) => item.family_id === state.activeFamilyId)) {
    state.activeFamilyId = null;
  }
  renderFamilyBlockers();
  applyAdaptiveLayout();
}

async function loadDiagnoses() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/diagnoses`);
  state.diagnoses = (payload.diagnoses || []).map((diagnosis) => ({
    ...diagnosis,
    family_id: diagnosis.family_id || deriveDiagnosisFamilyId(diagnosis),
  }));
  const root = $("diagnoses");
  root.innerHTML = "";
  const visibleDiagnoses = getVisibleDiagnoses();
  if (!state.activeDiagnosisId || !visibleDiagnoses.some((item) => item.diagnosis_id === state.activeDiagnosisId)) {
    state.activeDiagnosisId = visibleDiagnoses[0]?.diagnosis_id || null;
  }
  const activeDiagnosis = visibleDiagnoses.find((item) => item.diagnosis_id === state.activeDiagnosisId) || visibleDiagnoses[0];
  state.activeStageId = activeDiagnosis?.first_failing_stage || state.activeStageId;
  visibleDiagnoses.forEach((diagnosis) => {
    const card = document.createElement("button");
    card.className = `diagnosis-card ${diagnosis.diagnosis_id === state.activeDiagnosisId ? "active" : ""}`;
    card.innerHTML = `
      <div class="diagnosis-top">
        <div class="diagnosis-title">${diagnosis.title}</div>
        <span class="pill ${diagnosis.severity}">${diagnosis.severity}</span>
      </div>
      <div class="kv"><span>${diagnosis.class}</span><span>${diagnosis.owner_layer}</span></div>
      <div class="kv"><span>${diagnosis.first_failing_stage}</span><span>${diagnosis.first_failing_iteration}</span></div>
      <div class="small-note">${diagnosis.primary_evidence.summary}</div>
    `;
    card.addEventListener("click", async () => {
      state.activeDiagnosisId = diagnosis.diagnosis_id;
      state.activeStageId = diagnosis.first_failing_stage;
      buildStageTrack({ explore_phase: diagnosis.first_failing_stage });
      await loadDiagnoses();
      await loadStageDetail();
    });
    root.appendChild(card);
  });
  renderInvestigationFocus();
  applyAdaptiveLayout();
}

async function loadRunDiff() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/run-diff`);
  const diff = payload.run_diff;
  renderSimpleList("run-diff", [
    { label: "Verified Delta", value: String(diff.verified_count_delta) },
    { label: "Regression Count", value: String(diff.regression_count) },
    { label: "Contradiction Delta", value: String(diff.contradiction_delta) },
    { label: "Ingest Success", value: diff.verdict_layers.ingest_success.current.status },
    { label: "Semantic Success", value: diff.verdict_layers.semantic_success.current.status },
    { label: "Run Validity", value: diff.verdict_layers.run_validity.current.status },
    { label: "Validation", value: diff.verdict_layers.validation_completeness.current.status },
  ]);
}

async function loadTrustFrontier() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/trust-frontier`);
  const counts = payload.trust_frontier.counts;
  renderSimpleList("trust-frontier", [
    { label: "Verified", value: String(counts.verified) },
    { label: "Inferred", value: String(counts.inferred) },
    { label: "Unresolved", value: String(counts.unresolved) },
    { label: "Contradictory", value: String(counts.contradictory) },
    { label: "Validation Incomplete", value: String(counts.validation_incomplete) },
  ]);
}

async function loadBlastRadius() {
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/blast-radius`);
  const blast = payload.blast_radius;
  renderSimpleList("blast-radius-detail", [
    { label: "Summary", value: blast.summary },
    { label: "Expected Surface", value: String((blast.expected_surface || []).length) },
    { label: "Extra Surface", value: String((blast.additional_discovered_surface || []).length) },
    { label: "Affected Targets", value: (blast.affected_targets || []).join(", ") || "n/a" },
    { label: "Global Trust", value: blast.locally_green_but_globally_untrusted ? "local green only" : "trusted" },
  ]);
}

async function loadStageDetail() {
  const familyQuery = state.activeFamilyId ? `?family_id=${encodeURIComponent(state.activeFamilyId)}` : "";
  const payload = await getJson(`/api/dashboard/jobs/${state.currentJobId}/stage-detail/${state.activeStageId}${familyQuery}`);
  const detail = payload.stage_detail;
  state.stageDetail = detail;
  const root = $("stage-detail");
  root.innerHTML = "";
  const header = document.createElement("div");
  header.className = "definition-grid";
  [
    { label: "Stage", value: detail.stage_id },
    { label: "Stage Truth", value: detail.stage_truth || "unknown" },
    { label: "Goal", value: detail.goal },
    { label: "First Failure", value: detail.first_failure.title },
    { label: "Cause", value: detail.first_failure.cause },
    { label: "Owner Layer", value: detail.first_failure.owner_layer },
    { label: "Next Action", value: detail.recommended_next_action },
  ].forEach((row) => {
    const item = document.createElement("div");
    item.className = "definition-item";
    item.innerHTML = `<span class="metric-label">${row.label}</span><strong>${row.value}</strong>`;
    header.appendChild(item);
  });
  root.appendChild(header);
  const evidenceWrap = document.createElement("div");
  evidenceWrap.className = "stack";
  root.appendChild(evidenceWrap);
  renderEvidence(evidenceWrap, detail.evidence || []);
  renderOperatorAnalysis(root, detail.operator_view, detail.analysis_view);
  renderInvestigationFocus();
  renderCurrentContext();
  applyAdaptiveLayout();
}

function deriveDiagnosisFamilyId(diagnosis) {
  const raw = String(
    diagnosis?.blast_radius?.summary ||
    diagnosis?.class ||
    diagnosis?.owner_layer ||
    ""
  ).toLowerCase();
  if (raw.includes("lineage") || raw.includes("state")) return "state-lineage";
  if (raw.includes("contract")) return "contract-mismatch";
  if (raw.includes("capture") || raw.includes("artifact")) return "capture-gap";
  if (raw.includes("validation")) return "validation-failure";
  if (raw.includes("architect") || raw.includes("cross-dll")) return "architecture-bottleneck";
  if (raw.includes("contradict")) return "contradiction-cluster";
  if ((diagnosis?.owner_layer || "").toLowerCase() === "measurement") return "measurement-gap";
  return "measurement-gap";
}

async function loadCampaignOverview() {
  const root = $("campaign-overview");
  if (!state.currentCampaignId) {
    root.innerHTML = `<div class="small-note">No campaign id available for the current job.</div>`;
    return;
  }
  const payload = await getJson(`/api/dashboard/campaigns/${state.currentCampaignId}/overview`);
  const overview = payload.overview;
  root.innerHTML = "";
  [
    { label: "Title", value: overview.title },
    { label: "Summary", value: overview.summary },
    { label: "Recurring Families", value: String((overview.recurring_diagnosis_families || []).length) },
    { label: "Targets", value: String((overview.targets || []).length) },
  ].forEach((row) => {
    const item = document.createElement("div");
    item.className = "kv";
    item.innerHTML = `<span>${row.label}</span><span>${row.value}</span>`;
    root.appendChild(item);
  });
}

function applyView() {
  document.querySelectorAll(".tab[data-view]").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === state.activeView);
  });
  document.querySelectorAll(".campaign-only").forEach((el) => el.classList.toggle("hidden", state.activeView !== "campaign"));
  document.querySelectorAll(".review-only").forEach((el) => el.classList.toggle("hidden", state.activeView === "campaign"));
}

async function selectJob(jobId, campaignId = null) {
  state.currentJobId = jobId;
  state.currentIterationId = jobId;
  state.currentCampaignId = campaignId || null;
  state.activeFamilyId = null;
  const job = await getJson(`/api/jobs/${jobId}`);
  state.currentJob = job;
  if (!state.currentCampaignId && job?.explore_runtime?.campaign_id) {
    state.currentCampaignId = job.explore_runtime.campaign_id;
  }
  state.activeStageId = inferStage(job);
  try {
    state.artifacts = await getJson(`/api/jobs/${jobId}/artifacts`);
  } catch (_err) {
    state.artifacts = null;
  }
  renderIterationSelector();
  buildStageTrack(job);
  watchEvents(jobId);
  await Promise.all([loadOverview(), loadIterationSummary(), loadFamilyBlockers(), loadDiagnoses(), loadRunDiff(), loadTrustFrontier(), loadBlastRadius()]);
  await Promise.all([loadEvidenceStack(), loadDecisionBasis()]);
  await loadStageDetail();
  renderCurrentContext();
  renderChainContext();
  applyAdaptiveLayout();
  if (state.activeView === "campaign") await loadCampaignOverview();
}

document.querySelectorAll(".tab[data-view]").forEach((tab) => {
  tab.addEventListener("click", async () => {
    state.activeView = tab.dataset.view;
    applyView();
    if (state.activeView === "campaign" && state.currentJobId) {
      await loadCampaignOverview();
    }
  });
});

$("run-custom").addEventListener("click", async () => {
  try {
    await runPath(resolveIntakePath());
  } catch (err) {
    $("event-log").innerHTML = `<div class="event-item">${err.message}</div>`;
  }
});

$("recent-jobs-filter").addEventListener("input", renderRecentJobs);
$("iteration-selector").addEventListener("change", async (event) => {
  const jobId = event.target.value;
  if (!jobId) return;
  const match = (state.recentJobs || []).find((job) => job.job_id === jobId);
  await selectJob(jobId, match?.campaign_id || null);
});
$("intake-shape").addEventListener("change", updatePackageIntakeCopy);
$("fixture-select").addEventListener("change", () => {
  if ($("intake-shape").value === "fixture") {
    $("custom-path").value = $("fixture-select").value || "";
  }
});

document.querySelectorAll(".tier-filter").forEach((button) => {
  button.addEventListener("click", () => {
    const tier = button.dataset.tier;
    if (state.activeTiers.has(tier)) {
      if (state.activeTiers.size === 1) return;
      state.activeTiers.delete(tier);
    } else {
      state.activeTiers.add(tier);
    }
    applyTierFilters();
  });
});

async function bootstrap() {
  applyView();
  applyTierFilters();
  updatePackageIntakeCopy();
  renderInvestigationFocus();
  renderArtifactTiers();
  renderDecisionBasis();
  renderCurrentContext();
  renderChainContext();
  applyAdaptiveLayout();
  await refreshDashboard();
}

$("refresh-health").addEventListener("click", refreshDashboard);
$("refresh-health-sidebar").addEventListener("click", refreshDashboard);
$("restart-lab").addEventListener("click", restartLab);
$("restart-lab-sidebar").addEventListener("click", restartLab);

bootstrap();
