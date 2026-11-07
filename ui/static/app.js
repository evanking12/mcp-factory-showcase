/* ═══════════════════════════════════════════════════════════
   MCP Factory SPA – client-side logic
═══════════════════════════════════════════════════════════ */

// ── State ────────────────────────────────────────────────
const state = {
  jobId: null,
  invocables: [],      // raw list from discovery
  tools: [],           // generated MCP tool schemas
  schemaBlob: null,
  findings: [],
  prereqGraph: null,
  messages: [],        // chat history [{role, content}]
  labStatus: null,
  currentJobStatus: null,
  currentVerdict: null,
  currentCampaign: null,
  featuredShowcase: null,
};

// Temporary hardcoded dev preset pulled from sessions/contoso_cs/contoso_cs.txt
const DEV_HINTS_PRESET = `Customer IDs follow the format CUST-NNN (3-digit zero-padded number, e.g. CUST-001, CUST-042).
Order IDs follow the format ORD-YYYYMMDD-NNNN (e.g. ORD-20260315-0117).
Monetary amounts (payments, refunds, balances) are in integer cents — $25.00 = 2500, $0.01 = 1.
Loyalty points are plain integers, not dollars.
CS_Initialize must be called before any other customer operation; calling functions without it returns error sentinels.`;

const DEV_USE_CASES_PRESET = `Customer service operations for a CRM loyalty system: look up customer profiles, check account status and balances, process payments and refunds, redeem loyalty points, unlock locked accounts, retrieve order status. Customer IDs are CUST-NNN format. Used by call-center agents to handle inbound service requests end-to-end.`;

// ── Preset definitions ─────────────────────────────────
const _PRESETS = {
  'fast-triage': {
    mode: 'dev', capProfile: 'dev', maxRounds: 2, maxToolCalls: 5, maxFunctions: 50,
    gap: false, clarify: false, floor: 1, skipDocumented: false, deterministicFallback: true,
  },
  'balanced': {
    mode: 'normal', capProfile: 'deploy', maxRounds: 5, maxToolCalls: 10, maxFunctions: 50,
    gap: true, clarify: true, floor: 1, skipDocumented: true, deterministicFallback: true,
  },
  'deep': {
    mode: 'extended', capProfile: 'deploy', maxRounds: 7, maxToolCalls: 14, maxFunctions: 100,
    gap: true, clarify: true, floor: 2, skipDocumented: true, deterministicFallback: true,
  },
};

function _presetDefaults(name) {
  return _PRESETS[name] || _PRESETS['fast-triage'];
}

function _modeDefaults(mode) {
  return _presetDefaults(mode === 'extended' ? 'deep' : mode === 'normal' ? 'balanced' : 'fast-triage');
}

function _syncModeBadge() {
  const mode = ($('explore-mode')?.value || 'dev').toLowerCase();
  const badge = $('mode-badge');
  if (!badge) return;
  badge.style.display = 'inline-flex';
  badge.textContent = `Mode: ${mode}`;
}

function _applyContosoPreset(target = 'all') {
  if ((target === 'hints' || target === 'all') && $('hints')) {
    $('hints').value = DEV_HINTS_PRESET;
  }
  if ((target === 'use-cases' || target === 'all') && $('use-cases')) {
    $('use-cases').value = DEV_USE_CASES_PRESET;
  }
}

function _syncSettingsFromPreset(name) {
  const p = _presetDefaults(name);
  if ($('explore-mode'))   $('explore-mode').value = p.mode;
  if ($('cap-profile'))    $('cap-profile').value = p.capProfile;
  if ($('max-rounds'))     $('max-rounds').value = String(p.maxRounds);
  if ($('max-tool-calls')) $('max-tool-calls').value = String(p.maxToolCalls);
  if ($('max-functions'))  $('max-functions').value = p.maxFunctions > 0 ? String(p.maxFunctions) : '';
  if ($('toggle-gap'))     $('toggle-gap').checked = p.gap;
  if ($('toggle-clarify')) $('toggle-clarify').checked = p.clarify;
  if ($('probe-floor'))    $('probe-floor').value = String(p.floor);
  if ($('toggle-skip-documented'))        $('toggle-skip-documented').checked = p.skipDocumented;
  if ($('toggle-deterministic-fallback')) $('toggle-deterministic-fallback').checked = p.deterministicFallback;
  _syncModeBadge();
}

function _syncExploreToggleDefaultsFromMode() {
  const mode = ($('explore-mode')?.value || 'dev').toLowerCase();
  _syncSettingsFromPreset(mode === 'extended' ? 'deep' : mode === 'normal' ? 'balanced' : 'fast-triage');
}

function _exploreSettingsPayload() {
  const mode        = ($('explore-mode')?.value  || 'dev').toLowerCase();
  const capProfile  = ($('cap-profile')?.value   || 'dev').toLowerCase();
  const maxRounds   = Number($('max-rounds')?.value   || 2);
  const maxTCalls   = Number($('max-tool-calls')?.value || 5);
  const maxFnRaw    = $('max-functions')?.value?.trim() || '';
  const modelOvr    = $('model-override')?.value?.trim() || '';
  const gap         = $('toggle-gap')?.checked                  ?? false;
  const clarify     = $('toggle-clarify')?.checked              ?? false;
  const floor       = Number($('probe-floor')?.value            || 1);
  const skipDoc     = $('toggle-skip-documented')?.checked      ?? false;
  const detFallback = $('toggle-deterministic-fallback')?.checked ?? true;

  const payload = {
    mode,
    cap_profile:  capProfile,
    max_rounds:   Math.max(1, Math.min(12, Number.isFinite(maxRounds)  ? maxRounds  : 2)),
    max_tool_calls: Math.max(1, Math.min(24, Number.isFinite(maxTCalls) ? maxTCalls  : 5)),
    min_direct_probes_per_function: Math.max(1, Math.min(5, Number.isFinite(floor)  ? floor : 1)),
    skip_documented:               !!skipDoc,
    deterministic_fallback_enabled: !!detFallback,
    gap_resolution_enabled:         !!gap,
    clarification_questions_enabled: !!clarify,
  };
  const maxFn = maxFnRaw ? Number(maxFnRaw) : NaN;
  if (Number.isFinite(maxFn) && maxFn > 0) payload.max_functions = maxFn;
  if (modelOvr) payload.model = modelOvr;

  // Checkpoint / focus / skip-to-stage controls
  const checkpointId = ($('checkpoint-id')?.value || '').trim();
  const focusFnsRaw  = ($('focus-functions')?.value || '').trim();
  const skipToStage  = ($('skip-to-stage')?.value || '').trim();
  if (checkpointId) payload.checkpoint_id = checkpointId;
  if (focusFnsRaw)  payload.focus_functions = focusFnsRaw.split(',').map(s => s.trim()).filter(Boolean);
  if (skipToStage)  payload.skip_to_stage = skipToStage;

  return payload;
}

// ── Recent jobs (localStorage) ──────────────────────────────
const _RECENT_JOBS_KEY = 'mcp_factory_recent_jobs';
const _MAX_RECENT_JOBS = 20;

function _loadRecentJobs() {
  try { return JSON.parse(localStorage.getItem(_RECENT_JOBS_KEY) || '[]'); }
  catch { return []; }
}

function _saveRecentJob(jobId, label) {
  if (!jobId) return;
  const jobs = _loadRecentJobs().filter(j => j.id !== jobId);
  jobs.unshift({ id: jobId, label: label || jobId, ts: Date.now() });
  if (jobs.length > _MAX_RECENT_JOBS) jobs.length = _MAX_RECENT_JOBS;
  localStorage.setItem(_RECENT_JOBS_KEY, JSON.stringify(jobs));
  _renderRecentJobs();
}

function _renderRecentJobs() {
  const sel = $('recent-jobs-select');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">— new run —</option>';
  for (const j of _loadRecentJobs()) {
    const opt = document.createElement('option');
    opt.value = j.id;
    const ago = _timeAgo(j.ts);
    opt.textContent = `${j.label} (${ago})`;
    sel.appendChild(opt);
  }
  sel.value = current;
}

async function _fetchRecentJobsFromAPI() {
  try {
    const res = await fetch('/api/jobs/recent');
    if (!res.ok) return;
    const data = await res.json();
    const jobs = data.jobs || [];
    if (!jobs.length) return;
    const sel = $('recent-jobs-select');
    if (!sel) return;
    const existing = new Set([...sel.options].map(o => o.value));
    for (const j of jobs) {
      if (existing.has(j.job_id)) continue;
      const opt = document.createElement('option');
      opt.value = j.job_id;
      const cov = j.total_count ? ` (${j.verified_count}/${j.total_count}, ${j.coverage_pct}%)` : '';
      const phase = j.explore_phase ? ` [${j.explore_phase}]` : '';
      const ago = j.created_at ? _timeAgo(j.created_at * 1000) : '';
      opt.textContent = `${j.component_name || j.job_id}${cov}${phase} — ${ago}`;
      opt.dataset.meta = JSON.stringify(j);
      sel.appendChild(opt);
    }
  } catch(_e) { /* non-fatal */ }
}

const _PREV_SCANS_MAX = 5;

async function _renderPreviousScansBar() {
  const wrap = $('previous-scans-wrap');
  const chips = $('previous-scans-chips');
  const empty = $('previous-scans-empty');
  if (!wrap || !chips || !empty) return;
  chips.innerHTML = '';
  try {
    const res = await fetch('/api/jobs/recent');
    if (!res.ok) { wrap.style.display = 'none'; return; }
    const data = await res.json();
    const jobs = (data.jobs || []).slice(0, _PREV_SCANS_MAX);
    wrap.style.display = 'block';
    if (!jobs.length) {
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';
    for (const j of jobs) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary scan-chip';
      const cov = (j.total_count != null && j.total_count > 0)
        ? ` (${j.verified_count ?? 0}/${j.total_count})`
        : '';
      const label = (j.component_name || j.job_id || '').trim() || j.job_id;
      btn.textContent = `${label}${cov}`;
      btn.title = `${j.job_id}${j.explore_phase ? ' — ' + j.explore_phase : ''}`;
      btn.addEventListener('click', () => _openScannedJob(j.job_id, label));
      chips.appendChild(btn);
    }
  } catch (_e) {
    wrap.style.display = 'none';
  }
}

async function _openScannedJob(jobId, label) {
  if (!jobId) return;
  clearError('upload-error');
  const wrap = $('previous-scans-wrap');
  if (wrap) wrap.style.opacity = '0.65';
  try {
    const jr = await fetch(`/api/jobs/${jobId}`);
    if (!jr.ok) throw new Error((await jr.text()).slice(0, 240));
    const s = await jr.json();
    if (s.status !== 'done') {
      showError('upload-error',
        `Job ${jobId} is not ready (status: ${s.status ?? 'unknown'}). Finish analysis or pick another job.`);
      return;
    }
    let inv = null;
    const resInv = s.result && s.result.invocables;
    if (Array.isArray(resInv) && resInv.length) {
      inv = resInv;
    } else {
      const ir = await fetch(`/api/jobs/${jobId}/invocables`);
      if (!ir.ok) {
        const detail = await ir.text();
        throw new Error(detail.slice(0, 200) || 'Could not load invocables');
      }
      const idata = await ir.json();
      inv = idata.invocables;
    }
    if (!Array.isArray(inv) || !inv.length) {
      throw new Error('No invocables found for this job.');
    }
    state.jobId = jobId;
    await _updateRunReviewFromStatus(s);
    _loadAndShowVerdict(jobId);
    state.invocables = flattenInvocables(inv);
    const stem = String(label || jobId).replace(/\.[^.]+$/, '');
    $('component-name').value = stem || 'mcp-component';
    $('checkpoint-id').value = jobId;
    const sel = $('recent-jobs-select');
    if (sel && [...sel.options].some(o => o.value === jobId)) sel.value = jobId;
    _saveRecentJob(jobId, label || jobId);
    buildInvocablesList();
    showSection(1);
    _updateChainInfo(jobId);
  } catch (e) {
    showError('upload-error', `Could not open scanned job: ${e.message || e}`);
  } finally {
    if (wrap) wrap.style.opacity = '1';
  }
}

function _timeAgo(ts) {
  const d = Date.now() - ts;
  if (d < 60000) return 'just now';
  if (d < 3600000) return Math.floor(d / 60000) + 'm ago';
  if (d < 86400000) return Math.floor(d / 3600000) + 'h ago';
  return Math.floor(d / 86400000) + 'd ago';
}

function _formatTimestamp(ts) {
  if (!ts) return 'unknown';
  const num = Number(ts);
  if (!Number.isFinite(num)) return String(ts);
  const ms = num > 1e12 ? num : num * 1000;
  return new Date(ms).toLocaleString();
}

function _statusTone(status) {
  const s = String(status || '').toLowerCase();
  if (s === 'ok' || s === 'valid' || s === 'done') return 'status-valid';
  if (s === 'degraded' || s === 'awaiting_clarification' || s === 'cancel_requested') return 'status-degraded';
  if (s === 'invalid' || s === 'error' || s === 'failed') return 'status-invalid';
  return 'status-unknown';
}

function _setStatusCell(statusId, detailId, payload, fallbackLabel) {
  const statusEl = $(statusId);
  const detailEl = $(detailId);
  if (!statusEl || !detailEl) return;
  const status = payload?.status || 'unknown';
  statusEl.className = `lab-metric-status ${_statusTone(status)}`;
  statusEl.textContent = fallbackLabel ? `${fallbackLabel}: ${status}` : status;
  detailEl.textContent = payload?.detail || 'No detail available.';
}

function _renderLabStatus(payload) {
  state.labStatus = payload || null;
  const overall = $('lab-overall');
  if (overall) {
    overall.className = `lab-overall ${_statusTone(payload?.status)}`;
    overall.textContent = payload?.status || 'unknown';
  }
  _setStatusCell('lab-api-status', 'lab-api-detail', payload?.api, '');
  _setStatusCell('lab-bridge-status', 'lab-bridge-detail', payload?.bridge, '');
  _setStatusCell('lab-model-status', 'lab-model-detail', payload?.model, '');
  _setStatusCell('lab-storage-status', 'lab-storage-detail', payload?.storage, '');
  _setStatusCell('lab-lane-status', 'lab-lane-detail', payload?.lane_validity, '');

  const runStatus = $('lab-run-status');
  const runDetail = $('lab-run-detail');
  const active = payload?.active_run;
  if (runStatus && runDetail) {
    if (active) {
      const label = active.component_name || active.job_id || 'job';
      runStatus.className = `lab-metric-status ${_statusTone(active.status || active.explore_phase)}`;
      runStatus.textContent = `${label} (${active.status || 'unknown'})`;
      runDetail.textContent = [
        active.job_id ? `job ${active.job_id}` : '',
        active.explore_phase ? `phase ${active.explore_phase}` : '',
        active.total_count ? `${active.verified_count ?? 0}/${active.total_count} verified` : '',
      ].filter(Boolean).join(' • ') || 'No active run detail available.';
    } else {
      runStatus.className = 'lab-metric-status status-unknown';
      runStatus.textContent = 'No active run';
      runDetail.textContent = 'No live or recent job summary available.';
    }
  }

  const noteWrap = $('lab-notes');
  const noteList = $('lab-notes-list');
  if (noteWrap && noteList) {
    noteList.innerHTML = '';
    const notes = [
      ...(payload?.lane_validity?.reasons || []),
      ...(payload?.lane_validity?.warnings || []),
    ];
    if (notes.length) {
      noteWrap.style.display = 'block';
      for (const note of notes) {
        const li = document.createElement('li');
        li.textContent = note;
        noteList.appendChild(li);
      }
    } else {
      noteWrap.style.display = 'none';
    }
  }
}

async function _refreshLabStatus() {
  try {
    const res = await fetch('/api/lab/status');
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const data = await res.json();
    _renderLabStatus(data);
  } catch (e) {
    _renderLabStatus({
      status: 'invalid',
      api: { status: 'invalid', detail: `Lab status fetch failed: ${e.message || e}` },
      bridge: { status: 'unknown', detail: 'Unavailable because the aggregate lab status request failed.' },
      model: { status: 'unknown', detail: 'Unavailable because the aggregate lab status request failed.' },
      storage: { status: 'unknown', detail: 'Unavailable because the aggregate lab status request failed.' },
      lane_validity: { status: 'invalid', detail: 'Lab preflight failed.', reasons: ['Aggregate lab status request failed'], warnings: [] },
      active_run: null,
    });
  }
}

async function _loadCampaignSummary(campaignId) {
  if (!campaignId) {
    state.currentCampaign = null;
    return null;
  }
  try {
    const res = await fetch(`/api/campaigns/${campaignId}`);
    if (!res.ok) throw new Error(`${res.status}`);
    const payload = await res.json();
    state.currentCampaign = payload;
    return payload;
  } catch (_e) {
    state.currentCampaign = null;
    return null;
  }
}

function _terminalReviewState(jobStatus) {
  const status = String(jobStatus?.status || '').toLowerCase();
  const phase = String(jobStatus?.explore_phase || '').toLowerCase();
  return ['done', 'error'].includes(status) || ['done', 'awaiting_clarification', 'canceled', 'cancelled', 'error'].includes(phase);
}

function _renderRunReview() {
  const header = $('run-review-header');
  const panel = $('run-review');
  const status = state.currentJobStatus;
  if (!header || !panel) return;
  if (!status || !_terminalReviewState(status)) {
    header.style.display = 'none';
    panel.style.display = 'none';
    return;
  }

  header.style.display = 'flex';
  panel.style.display = 'block';
  const verdict = state.currentVerdict || status.macro_verdict || null;
  const campaign = state.currentCampaign || null;
  const summary = $('run-review-summary');
  const sessionValue = $('run-review-session');
  const sessionDetail = $('run-review-session-detail');
  const coverageValue = $('run-review-coverage');
  const coverageDetail = $('run-review-coverage-detail');
  const campaignValue = $('run-review-campaign');
  const campaignDetail = $('run-review-campaign-detail');
  const issuesWrap = $('run-review-notes');
  const issuesList = $('run-review-issues');
  const campaignBtn = $('review-campaign-btn');

  if (summary) {
    summary.textContent = [
      status.component_name || status.job_id || 'run',
      `status ${status.status || 'unknown'}`,
      status.explore_phase ? `phase ${status.explore_phase}` : '',
      `updated ${_formatTimestamp(status.updated_at || status.created_at)}`,
    ].filter(Boolean).join(' • ');
  }
  if (sessionValue) {
    sessionValue.textContent = status.component_name || status.job_id || 'Session';
  }
  if (sessionDetail) {
    sessionDetail.textContent = [
      status.job_id ? `job ${status.job_id}` : '',
      status.created_at ? `created ${_formatTimestamp(status.created_at)}` : '',
      status.checkpoint_id ? `checkpoint ${status.checkpoint_id}` : '',
    ].filter(Boolean).join(' • ') || 'No session detail available.';
  }
  if (coverageValue) {
    coverageValue.textContent = verdict
      ? `${verdict.verified_count ?? 0}/${verdict.total_count ?? 0} verified (${verdict.coverage_pct ?? 0}%)`
      : 'No macro verdict yet';
  }
  if (coverageDetail) {
    coverageDetail.textContent = verdict
      ? `Macro status: ${verdict.status || 'unknown'}`
      : 'Coverage will populate after a macro verdict is available.';
  }
  if (campaignValue) {
    campaignValue.textContent = campaign
      ? (campaign.phase || campaign.status || campaign.campaign_id || 'Campaign attached')
      : (status.campaign_id || 'No campaign attached');
  }
  if (campaignDetail) {
    campaignDetail.textContent = campaign
      ? [
          campaign.campaign_id ? `campaign ${campaign.campaign_id}` : '',
          Array.isArray(campaign.dll_entries) ? `${campaign.dll_entries.length} DLL entries` : '',
        ].filter(Boolean).join(' • ')
      : 'Campaign summary appears when the run belongs to a multi-DLL campaign.';
  }
  if (issuesWrap && issuesList) {
    issuesList.innerHTML = '';
    const issues = [];
    if (status.bridge_warning) issues.push(status.bridge_warning);
    if (status.explore_error) issues.push(status.explore_error);
    if (Array.isArray(verdict?.unresolved_functions)) {
      for (const fn of verdict.unresolved_functions.slice(0, 8)) {
        issues.push(`Unresolved: ${fn}`);
      }
    }
    if (Array.isArray(status.explore_questions) && status.explore_questions.length) {
      issues.push(`${status.explore_questions.length} clarification question(s) remain`);
    }
    if (issues.length) {
      issuesWrap.style.display = 'block';
      for (const issue of issues) {
        const li = document.createElement('li');
        li.textContent = issue;
        issuesList.appendChild(li);
      }
    } else {
      issuesWrap.style.display = 'none';
    }
  }
  if (campaignBtn) {
    campaignBtn.style.display = status.campaign_id ? 'inline-flex' : 'none';
  }
}

async function _updateRunReviewFromStatus(jobStatus) {
  state.currentJobStatus = jobStatus || null;
  const campaignId = jobStatus?.campaign_id || '';
  if (campaignId) {
    await _loadCampaignSummary(campaignId);
  } else {
    state.currentCampaign = null;
  }
  _renderRunReview();
}

function _canonicalStatusClass(finding) {
  const s = String(finding?.status_canonical || finding?.status || '').toLowerCase();
  if (s.includes('verified_success') || s.includes('safe-to-expose') || s === 'success') return 'verified';
  if (s.includes('inferred')) return 'inferred';
  return 'blocked';
}

function _truncateText(text, limit = 160) {
  const raw = String(text || '').trim();
  if (!raw) return 'No evidence text available.';
  return raw.length > limit ? `${raw.slice(0, limit - 1)}…` : raw;
}

function _formatWorkingCall(call) {
  if (!call || typeof call !== 'object' || Array.isArray(call) || !Object.keys(call).length) {
    return 'No working call captured.';
  }
  const entries = Object.entries(call).slice(0, 3).map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`);
  return entries.join(' • ');
}

function _renderFeaturedShowcase() {
  const featured = state.featuredShowcase || null;
  if (!featured) return;

  $('hero-eyebrow').textContent = 'Featured Batch B Milestone';
  $('hero-title').textContent = `Recovered ${featured.verified_count ?? 0}/${featured.total_functions ?? 0} callable surfaces across an 8-DLL business suite.`;
  $('hero-copy').textContent = 'This demo opens on the latest trusted Batch B campaign: a dense multi-DLL proving run that stays honest about what is verified, what still regresses under package pressure, and why those remaining seams matter for productization.';
  $('hero-verified-metric').textContent = `${featured.verified_count ?? 0}/${featured.total_functions ?? 0}`;
  $('hero-overlap-metric').textContent = String(featured.overlap_delta ?? 'n/a');
  $('hero-frontier-metric').textContent = String(featured.remaining_regression_count ?? 0);
  $('story-title').textContent = `${featured.package_label || 'Featured package'} • campaign ${featured.campaign_id || 'unknown'}`;
  $('story-find').textContent = 'Recovered a trustworthy callable surface across 8 DLLs with clean lane trust and comparable overlap.';
  $('story-verify').textContent = `Current best package milestone: ${featured.verified_count ?? 0}/${featured.total_functions ?? 0} verified, improved from ${featured.previous_verified_count ?? 0}/${featured.previous_total_functions ?? 0}.`;
  $('story-dependencies').textContent = 'The representative workflow job shows prerequisite chains, handle routing, and state-machine continuity instead of isolated single-call success.';
  $('story-frontier').textContent = `${featured.remaining_regression_count ?? 0} overlap regressions remain, concentrated in config, workflow state, and pricing policy/state seams.`;
}

function _setModalOpen(id, open) {
  const el = $(id);
  if (!el) return;
  el.classList.toggle('open', !!open);
}

function _showPreviewModal(title, subtitle, content) {
  $('preview-modal-title').textContent = title || 'Preview';
  $('preview-modal-subtitle').textContent = subtitle || 'Loaded from the current showcase surface.';
  $('preview-modal-body').textContent = String(content || 'No preview available.');
  _setModalOpen('preview-modal', true);
}

function _sanitizeMermaidLabel(text) {
  return String(text || '').replace(/"/g, '\\"');
}

function _buildMermaidGraph() {
  const graph = state.prereqGraph || {};
  const roles = Array.isArray(graph.roles) ? graph.roles : [];
  const ranked = roles
    .filter(r => Array.isArray(r.prerequisites) && r.prerequisites.length)
    .sort((a, b) => (b.sequence_confidence || 0) - (a.sequence_confidence || 0))
    .slice(0, 8);

  if (!ranked.length) {
    return 'flowchart LR\n  A["Load a representative workflow proof job"] --> B["Rebuild prerequisite graph"] --> C["Inspect state chains"]';
  }

  const nodeIds = new Map();
  let nextId = 0;
  const ensureId = (name) => {
    if (!nodeIds.has(name)) nodeIds.set(name, `N${nextId++}`);
    return nodeIds.get(name);
  };

  const lines = ['flowchart LR'];
  for (const role of ranked) {
    const targetName = role.name || 'target';
    const targetId = ensureId(targetName);
    lines.push(`  ${targetId}["${_sanitizeMermaidLabel(targetName)}"]`);
    for (const prereq of role.prerequisites.slice(0, 3)) {
      const prereqId = ensureId(prereq);
      lines.push(`  ${prereqId}["${_sanitizeMermaidLabel(prereq)}"] --> ${targetId}`);
    }
  }
  return lines.join('\n');
}

async function _openGraphModal() {
  const src = _buildMermaidGraph();
  $('graph-mermaid-source').textContent = src;
  $('graph-modal-subtitle').textContent = state.currentJobStatus?.component_name
    ? `Expanded prerequisite view for ${state.currentJobStatus.component_name}.`
    : 'Expanded prerequisite view of the current showcase graph.';
  const host = $('graph-mermaid-view');
  host.innerHTML = '';
  const mount = document.createElement('div');
  mount.className = 'mermaid';
  mount.textContent = src;
  host.appendChild(mount);
  _setModalOpen('graph-modal', true);
  try {
    if (window.mermaid) {
      window.mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
      await window.mermaid.run({ nodes: [mount] });
    }
  } catch (_e) {
    // Fallback stays as raw source below.
  }
}

function _buildCampaignMermaid() {
  const featured = state.featuredShowcase || {};
  const dlls = Array.isArray(featured.per_dll) ? featured.per_dll : [];
  if (!dlls.length) {
    return 'flowchart LR\n  P["Contoso Business Suite"] --> W["Load featured campaign summary"]';
  }
  const lines = ['flowchart LR', '  PKG["Contoso Business Suite"]'];
  dlls.forEach((dll, idx) => {
    const nodeId = `D${idx}`;
    const short = String(dll.filename || `dll-${idx + 1}`).replace('.dll', '');
    const label = `${short}\\n${dll.verified_count ?? 0}/${dll.total_functions ?? 0}\\n${dll.blocker_family_primary || 'stable'}`.replace(/"/g, '\\"');
    lines.push(`  ${nodeId}["${label}"]`);
    lines.push(`  PKG --> ${nodeId}`);
  });
  return lines.join('\n');
}

function _buildCampaignReuseMermaid() {
  const featured = state.featuredShowcase || {};
  const dlls = Array.isArray(featured.per_dll) ? featured.per_dll : [];
  if (!dlls.length) {
    return 'flowchart LR\n  P["Campaign reuse topology unavailable"]';
  }
  const byJobId = new Map(dlls.map((dll, idx) => [dll.job_id, { dll, idx }]));
  const lines = ['flowchart LR'];
  for (const [idx, dll] of dlls.entries()) {
    lines.push(`  C${idx}["${_sanitizeMermaidLabel(String(dll.filename || `dll-${idx + 1}`).replace('.dll', ''))}"]`);
  }
  let edgeCount = 0;
  for (const [idx, dll] of dlls.entries()) {
    const priors = Array.isArray(dll.cross_dll_prior_job_ids) ? dll.cross_dll_prior_job_ids : [];
    for (const prior of priors) {
      const priorEntry = byJobId.get(prior);
      if (!priorEntry) continue;
      lines.push(`  C${priorEntry.idx} --> C${idx}`);
      edgeCount += 1;
    }
  }
  if (!edgeCount) {
    lines.push('  P["No cross-DLL reuse edges recorded"]');
  }
  return lines.join('\n');
}

async function _openCampaignModal() {
  const featured = state.featuredShowcase || null;
  const host = $('campaign-mermaid-view');
  const reuseHost = $('campaign-reuse-view');
  const reuseSource = $('campaign-reuse-source');
  const summary = $('campaign-summary-body');
  if (!host || !reuseHost || !reuseSource || !summary) return;
  const src = _buildCampaignMermaid();
  const reuseSrc = _buildCampaignReuseMermaid();
  host.innerHTML = '';
  const mount = document.createElement('div');
  mount.className = 'mermaid';
  mount.textContent = src;
  host.appendChild(mount);
  reuseHost.innerHTML = '';
  const reuseMount = document.createElement('div');
  reuseMount.className = 'mermaid';
  reuseMount.textContent = reuseSrc;
  reuseHost.appendChild(reuseMount);
  reuseSource.textContent = reuseSrc;
  const lines = [];
  if (featured) {
    lines.push(`${featured.package_label || 'Campaign'} — ${featured.verified_count ?? 0}/${featured.total_functions ?? 0} verified`);
    lines.push(`Overlap delta: ${featured.overlap_delta ?? 'n/a'} • Remaining regressions: ${featured.remaining_regression_count ?? 0}`);
    lines.push('');
    for (const dll of (featured.per_dll || [])) {
      lines.push(`${dll.filename || 'unknown'}: ${dll.verified_count ?? 0}/${dll.total_functions ?? 0} verified • blocker ${dll.blocker_family_primary || 'none'}`);
    }
  }
  summary.textContent = lines.join('\n');
  $('campaign-modal-subtitle').textContent = featured
    ? `Whole-package view for campaign ${featured.campaign_id || 'unknown'}, with each DLL's current verified coverage and primary blocker family.`
    : 'Whole-package view of the featured Batch B checkpoint.';
  _setModalOpen('campaign-modal', true);
  try {
    if (window.mermaid) {
      window.mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
      await window.mermaid.run({ nodes: [mount, reuseMount] });
    }
  } catch (_e) {
    // raw summary remains visible below
  }
  _renderCampaignDllButtons();
}

function _buildRoleMermaidGraph(graph) {
  const roles = Array.isArray(graph?.roles) ? graph.roles : [];
  const ranked = roles
    .filter(r => Array.isArray(r.prerequisites) && r.prerequisites.length)
    .sort((a, b) => (b.sequence_confidence || 0) - (a.sequence_confidence || 0))
    .slice(0, 10);

  if (!ranked.length) {
    return 'flowchart LR\n  A["No prerequisite graph available"]';
  }

  const nodeIds = new Map();
  let nextId = 0;
  const ensureId = (name) => {
    if (!nodeIds.has(name)) nodeIds.set(name, `R${nextId++}`);
    return nodeIds.get(name);
  };

  const lines = ['flowchart LR'];
  for (const role of ranked) {
    const targetName = role.name || 'target';
    const targetId = ensureId(targetName);
    lines.push(`  ${targetId}["${_sanitizeMermaidLabel(targetName)}"]`);
    for (const prereq of role.prerequisites.slice(0, 4)) {
      const prereqId = ensureId(prereq);
      lines.push(`  ${prereqId}["${_sanitizeMermaidLabel(prereq)}"] --> ${targetId}`);
    }
  }
  return lines.join('\n');
}

async function _renderCampaignDrilldownForDll(dllEntry) {
  const view = $('campaign-drilldown-view');
  const source = $('campaign-drilldown-source');
  const subtitle = $('campaign-modal-subtitle');
  if (!view || !source || !dllEntry?.job_id) return;

  let graph = null;
  try {
    const res = await fetch(`/api/download/${dllEntry.job_id}/prerequisite_state_machine.json`);
    if (res.ok) {
      graph = await res.json();
    }
  } catch (_e) {
    graph = null;
  }

  const mermaidSrc = _buildRoleMermaidGraph(graph);
  subtitle.textContent = `${dllEntry.filename || 'DLL'} • ${dllEntry.verified_count ?? 0}/${dllEntry.total_functions ?? 0} verified • blocker ${dllEntry.blocker_family_primary || 'unknown'}`;
  view.innerHTML = '';
  const mount = document.createElement('div');
  mount.className = 'mermaid';
  mount.textContent = mermaidSrc;
  view.appendChild(mount);
  source.textContent = mermaidSrc;
  try {
    if (window.mermaid) {
      window.mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
      await window.mermaid.run({ nodes: [mount] });
    }
  } catch (_e) {
    // raw source remains visible
  }
}

function _renderCampaignDllButtons() {
  const wrap = $('campaign-dll-actions');
  const featured = state.featuredShowcase || null;
  if (!wrap || !featured) return;
  wrap.innerHTML = '';
  const dlls = Array.isArray(featured.per_dll) ? featured.per_dll : [];
  for (const dll of dlls) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary';
    btn.textContent = `${String(dll.filename || 'dll').replace('.dll', '')} (${dll.verified_count ?? 0}/${dll.total_functions ?? 0})`;
    btn.addEventListener('click', () => _renderCampaignDrilldownForDll(dll));
    wrap.appendChild(btn);
  }
  if (dlls.length) {
    _renderCampaignDrilldownForDll(dlls.find(d => d.filename === 'contoso_workflow.dll') || dlls[0]);
  }
}

function _renderShowcaseSnapshot() {
  const findings = Array.isArray(state.findings) ? state.findings : [];
  const verified = findings.filter(f => _canonicalStatusClass(f) === 'verified');
  const featured = state.featuredShowcase || null;
  const unresolved = (featured?.remaining_regressions || state.currentVerdict?.unresolved_functions || []).filter(Boolean);
  const workingCalls = verified.filter(f => f.working_call && typeof f.working_call === 'object' && Object.keys(f.working_call).length);

  $('showcase-verified-count').textContent = String(featured?.verified_count ?? verified.length);
  $('showcase-unresolved-count').textContent = String(unresolved.length);
  $('showcase-working-calls').textContent = String(workingCalls.length);

  $('showcase-status-line').textContent = featured
    ? `Batch B milestone: ${featured.verified_count ?? 0}/${featured.total_functions ?? 0} verified • overlap delta ${featured.overlap_delta ?? 'n/a'} • ${featured.verdict || 'in progress'}`
    : state.currentVerdict
    ? `${state.currentVerdict.verified_count ?? verified.length}/${state.currentVerdict.total_count ?? findings.length} verified (${state.currentVerdict.coverage_pct ?? 0}%)`
    : (findings.length ? `${verified.length}/${findings.length} findings currently verified` : 'Run a verified lane to populate the snapshot.');

  const summaryList = $('showcase-summary-list');
  if (!summaryList) return;
  summaryList.innerHTML = '';
  const bullets = [];
  if (featured?.package_label) bullets.push(`Featured package: ${featured.package_label}`);
  if (state.currentJobStatus?.component_name) bullets.push(`Representative proof job: ${state.currentJobStatus.component_name}`);
  if (featured?.package_internal_truth_ready && featured?.overlap_baseline_comparable) bullets.push('Trust is clean and the overlap baseline is comparable, so the package result is worth showing publicly.');
  if (featured?.previous_overlap_delta !== undefined && featured?.overlap_delta !== undefined) bullets.push(`Overlap improved from ${featured.previous_overlap_delta} to ${featured.overlap_delta} after system-contract and seam-gate cleanup.`);
  if (state.currentVerdict?.reasoning) bullets.push(_truncateText(state.currentVerdict.reasoning, 150));
  if (unresolved.length) bullets.push(`Top unresolved: ${unresolved.slice(0, 4).join(', ')}`);
  if (workingCalls.length) bullets.push(`Recent working call: ${verified.find(f => f.working_call)?.function || verified[0]?.function || 'available'}`);
  if (!bullets.length) bullets.push('Coverage, blocker counts, and working calls will appear here.');
  for (const bullet of bullets.slice(0, 4)) {
    const li = document.createElement('li');
    li.textContent = bullet;
    summaryList.appendChild(li);
  }
}

function _renderShowcaseGraph() {
  const graph = state.prereqGraph || {};
  const roles = Array.isArray(graph.roles) ? graph.roles : [];
  const graphList = $('graph-list');
  const graphSummary = $('graph-summary');
  if (!graphList || !graphSummary) return;
  graphList.innerHTML = '';

  const ranked = roles
    .filter(r => Array.isArray(r.prerequisites) && r.prerequisites.length)
    .sort((a, b) => (b.sequence_confidence || 0) - (a.sequence_confidence || 0))
    .slice(0, 4);

  if (!ranked.length) {
    graphSummary.textContent = state.featuredShowcase
      ? 'The featured workflow proof uses prerequisite chains and state continuity; load the representative job to inspect the live edges.'
      : 'The workflow-style prerequisite view appears after exploration artifacts exist.';
    graphList.innerHTML = `
      <div class="graph-line">
        <span class="graph-node">Analyze a DLL</span>
        <span class="graph-arrow">→</span>
        <span class="graph-node">Run verification</span>
        <span class="graph-arrow">→</span>
        <span class="graph-node">Inspect state chains</span>
      </div>
    `;
    return;
  }

  graphSummary.textContent = `${ranked.length} high-confidence sequence edges from the current prerequisite classifier.`;
  for (const role of ranked) {
    const line = document.createElement('div');
    line.className = 'graph-line';
    for (const prereq of role.prerequisites.slice(0, 3)) {
      const node = document.createElement('span');
      node.className = 'graph-node';
      node.textContent = prereq;
      line.appendChild(node);
      const arrow = document.createElement('span');
      arrow.className = 'graph-arrow';
      arrow.textContent = '→';
      line.appendChild(arrow);
    }
    const target = document.createElement('span');
    target.className = 'graph-node';
    target.textContent = role.name || 'target';
    line.appendChild(target);
    graphList.appendChild(line);
  }
}

function _renderShowcaseEvidence() {
  const findings = Array.isArray(state.findings) ? state.findings : [];
  const verified = findings.find(f => _canonicalStatusClass(f) === 'verified');
  const blockedNames = new Set((state.featuredShowcase?.remaining_regressions || state.currentVerdict?.unresolved_functions || []).filter(Boolean));
  const blocked = findings.find(f => blockedNames.has(f.function)) || findings.find(f => _canonicalStatusClass(f) !== 'verified');

  $('showcase-verified-name').textContent = verified?.function || 'No verified example yet';
  $('showcase-verified-status').textContent = verified ? (verified.status_canonical || verified.status || 'verified') : 'Waiting for findings';
  $('showcase-verified-body').textContent = verified
    ? `${_truncateText(verified.finding || verified.notes || 'Verified evidence available.', 180)} Working call: ${_formatWorkingCall(verified.working_call)}`
    : 'Verified working-call evidence will appear here.';

  $('showcase-blocked-name').textContent = blocked?.function || 'No unresolved example yet';
  $('showcase-blocked-status').textContent = blocked ? (blocked.status_canonical || blocked.status || 'unresolved') : 'Waiting for findings';
  $('showcase-blocked-body').textContent = blocked
    ? _truncateText(blocked.finding || blocked.notes || blocked.stop_reason || 'Blocked or unresolved reasoning available.', 220)
    : 'Blocked or unresolved reasoning will appear here.';

  const frontierList = $('frontier-list');
  if (!frontierList) return;
  frontierList.innerHTML = '';
  const frontierBullets = [];
  if ((state.featuredShowcase?.remaining_regressions || state.currentVerdict?.unresolved_functions || []).length) {
    frontierBullets.push(`Remaining frontier: ${(state.featuredShowcase?.remaining_regressions || state.currentVerdict?.unresolved_functions || []).slice(0, 5).join(', ')}`);
  }
  if ((state.featuredShowcase?.dominant_blockers || []).length) {
    frontierBullets.push(`Current blocker families: ${(state.featuredShowcase.dominant_blockers || []).slice(0, 3).map(b => b.family || b).join(', ')}`);
  }
  if (state.currentJobStatus?.explore_questions?.length) {
    frontierBullets.push(`${state.currentJobStatus.explore_questions.length} clarification question(s) still remain for this surface.`);
  }
  frontierBullets.push('Real callback-heavy or flag-space APIs remain a weaker public-demo target.');
  frontierBullets.push('Only include a real-world DLL canary if the recovery story is legible and reproducible.');
  for (const bullet of frontierBullets.slice(0, 4)) {
    const li = document.createElement('li');
    li.textContent = bullet;
    frontierList.appendChild(li);
  }
}

async function _refreshShowcaseArtifacts(jobId) {
  if (!jobId) {
    state.findings = [];
    state.prereqGraph = null;
    _renderShowcaseSnapshot();
    _renderShowcaseGraph();
    _renderShowcaseEvidence();
    return;
  }
  try {
    const [findingsRes, graphRes] = await Promise.all([
      fetch(`/api/findings/${jobId}`),
      fetch(`/api/download/${jobId}/prerequisite_state_machine.json`),
    ]);

    if (findingsRes.ok) {
      const findingsPayload = await findingsRes.json();
      state.findings = Array.isArray(findingsPayload.findings)
        ? findingsPayload.findings
        : Array.isArray(findingsPayload) ? findingsPayload : [];
    } else {
      state.findings = [];
    }

    if (graphRes.ok) {
      try {
        state.prereqGraph = await graphRes.json();
      } catch (_e) {
        state.prereqGraph = null;
      }
    } else {
      state.prereqGraph = null;
    }
  } catch (_e) {
    state.findings = [];
    state.prereqGraph = null;
  }

  _renderShowcaseSnapshot();
  _renderShowcaseGraph();
  _renderShowcaseEvidence();
}

// ── Stage progress stepper ──────────────────────────────
const _STAGE_ORDER = ['s00_setup','s01_unlock','s02_probe','s03_reconcile','s04_synthesis','s05_enrichment','s06_gaps','s07_finalize'];
const _STAGE_SHORT = ['s00','s01','s02','s03','s04','s05','s06','s07'];

function _updateStageStepper(jobStatus) {
  const stepper = $('stage-stepper');
  if (!stepper) return;
  const phase = (jobStatus.explore_phase || '').toLowerCase();
  const msg = (jobStatus.explore_message || '').toLowerCase();
  if (!phase || phase === 'queued') { stepper.style.display = 'none'; return; }
  stepper.style.display = 'flex';

  let activeIdx = -1;
  for (let i = 0; i < _STAGE_SHORT.length; i++) {
    if (msg.includes(`s-0${i}`) || msg.toLowerCase().includes(_STAGE_ORDER[i])) {
      activeIdx = i;
    }
  }
  if (activeIdx < 0 && phase === 'exploring') activeIdx = 0;

  const checkpoint = jobStatus.checkpoint_stages_complete || [];
  const steps = stepper.querySelectorAll('.stage-step');
  const conns = stepper.querySelectorAll('.stage-conn');
  steps.forEach((step, i) => {
    step.classList.remove('complete', 'active', 'error');
    const stageName = _STAGE_ORDER[i];
    if (checkpoint.includes(stageName) || checkpoint.includes(_STAGE_SHORT[i])) {
      step.classList.add('complete');
    } else if (i === activeIdx && (phase === 'exploring' || phase === 'cancel_requested')) {
      step.classList.add('active');
    } else if (phase === 'error' && i === activeIdx) {
      step.classList.add('error');
    }
  });
  conns.forEach((conn, i) => {
    conn.classList.toggle('done',
      steps[i]?.classList.contains('complete') || false);
  });
}

// ── Verdict panel ───────────────────────────────────────
async function _loadAndShowVerdict(jobId) {
  if (!jobId) return;
  try {
    const res = await fetch(`/api/jobs/${jobId}/verdict`);
    if (!res.ok) return;
    const data = await res.json();
    const v = data.verdict;
    state.currentVerdict = v || null;
    _renderRunReview();
    if (!v) return;
    _renderVerdict(v);
    _renderShowcaseSnapshot();
    _renderShowcaseEvidence();
  } catch(_e) { /* non-fatal */ }
}

function _renderVerdict(v) {
  const panel = $('verdict-panel');
  if (!panel || !v) return;
  panel.style.display = 'block';
  panel.className = 'verdict-panel ' + (
    v.status === 'done' ? 'verdict-done' :
    v.status === 'loop_again' ? 'verdict-loop' :
    'verdict-clarify'
  );

  const icon = v.status === 'done' ? '✅' : v.status === 'loop_again' ? '🔄' : '❓';
  $('verdict-title').textContent = `${icon} Macro Coordinator: ${v.status.replace(/_/g, ' ')}`;

  const stats = $('verdict-stats');
  stats.innerHTML = `
    <div class="verdict-stat">
      <span class="verdict-stat-val">${v.coverage_pct}%</span>
      <span class="verdict-stat-lbl">Coverage</span>
    </div>
    <div class="verdict-stat">
      <span class="verdict-stat-val">${v.verified_count}/${v.total_count}</span>
      <span class="verdict-stat-lbl">Verified</span>
    </div>
    <div class="verdict-stat">
      <span class="verdict-stat-val">${(v.unresolved_functions||[]).length}</span>
      <span class="verdict-stat-lbl">Unresolved</span>
    </div>
  `;

  $('verdict-reasoning').textContent = v.reasoning || '';

  const adj = v.strategy_adjustments || {};
  const sugBox = $('verdict-suggestions');
  const adjList = $('verdict-adj-list');
  const rerunBtn = $('verdict-rerun-btn');
  if (Object.keys(adj).length > 0) {
    sugBox.style.display = 'block';
    adjList.innerHTML = '';
    if (adj.focus_functions) {
      const li = document.createElement('li');
      li.textContent = `Focus on: ${adj.focus_functions.join(', ')}`;
      adjList.appendChild(li);
    }
    if (adj.skip_to_stage) {
      const li = document.createElement('li');
      li.textContent = `Skip to: ${adj.skip_to_stage}`;
      adjList.appendChild(li);
    }
    if (adj.focus_write_unlock) {
      const li = document.createElement('li');
      li.textContent = 'Focus write-unlock with expanded init mode sweep';
      adjList.appendChild(li);
    }
    if (adj.increase_budget) {
      const li = document.createElement('li');
      li.textContent = 'Increase max_rounds and max_tool_calls';
      adjList.appendChild(li);
    }
    if (adj.reasoning) {
      const li = document.createElement('li');
      li.style.fontStyle = 'italic';
      li.textContent = adj.reasoning;
      adjList.appendChild(li);
    }
    if (v.status === 'loop_again') {
      rerunBtn.style.display = 'inline-flex';
      rerunBtn.onclick = () => _applyVerdictSuggestions(adj);
    } else {
      rerunBtn.style.display = 'none';
    }
  } else {
    sugBox.style.display = 'none';
    rerunBtn.style.display = 'none';
  }
}

function _applyVerdictSuggestions(adj) {
  if (adj.focus_functions && $('focus-functions')) {
    $('focus-functions').value = adj.focus_functions.join(', ');
  }
  if (adj.skip_to_stage && $('skip-to-stage')) {
    $('skip-to-stage').value = adj.skip_to_stage;
  }
  if (adj.increase_budget) {
    if ($('max-rounds')) $('max-rounds').value = String(Math.min(12, parseInt($('max-rounds').value || '2') + 2));
    if ($('max-tool-calls')) $('max-tool-calls').value = String(Math.min(24, parseInt($('max-tool-calls').value || '5') + 4));
  }
  $('verdict-panel').style.display = 'none';
  $('discover-btn')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ── MC decision viewer ──────────────────────────────────
async function _loadAndShowMCDecisions(jobId) {
  if (!jobId) return;
  try {
    const res = await fetch(`/api/jobs/${jobId}/mc-decisions`);
    if (!res.ok) return;
    const data = await res.json();
    const decisions = data.decisions || {};
    _renderMCDecisions(decisions);
  } catch(_e) { /* non-fatal */ }
}

function _renderMCDecisions(decisions) {
  const viewer = $('mc-viewer');
  const body = $('mc-viewer-body');
  if (!viewer || !body) return;

  const mcNames = {
    'mc3-post-reconcile': 'MC-3: Write Failure Classification',
    'mc4-post-synthesis': 'MC-4: Init Sequence Clues',
    'mc5-post-verification': 'MC-5: Read-to-Write Chaining',
    'mc6-post-gap-resolution': 'MC-6: Final Comprehensive Unlock',
  };

  let hasAny = false;
  body.innerHTML = '';
  for (const [mcId, entries] of Object.entries(decisions)) {
    const card = document.createElement('div');
    card.className = 'mc-card';
    const header = document.createElement('div');
    header.className = 'mc-card-header';
    header.textContent = mcNames[mcId] || mcId;
    card.appendChild(header);

    if (!entries || entries.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'mc-card-empty';
      empty.textContent = 'No decisions recorded';
      card.appendChild(empty);
    } else {
      hasAny = true;
      for (const entry of entries) {
        const div = document.createElement('div');
        div.className = 'mc-entry';
        const trigger = entry.trigger || entry.action || entry.type || 'decision';
        const summary = entry.summary || entry.result || JSON.stringify(entry).slice(0, 120);
        div.innerHTML = `<strong>${_escHtml(trigger)}</strong>: ${_escHtml(summary)}`;
        card.appendChild(div);
      }
    }
    body.appendChild(card);
  }
  viewer.style.display = hasAny ? 'block' : 'none';
}

function _escHtml(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

// ── Prior job chain info ────────────────────────────────
function _updateChainInfo(jobId) {
  const info = $('chain-info');
  if (!info) return;
  if (!jobId) { info.style.display = 'none'; return; }
  const sel = $('recent-jobs-select');
  const opt = sel?.querySelector(`option[value="${jobId}"]`);
  if (opt?.dataset?.meta) {
    try {
      const m = JSON.parse(opt.dataset.meta);
      info.style.display = 'block';
      info.innerHTML = `<strong>Chain from:</strong> ${_escHtml(m.component_name || m.job_id)}` +
        (m.total_count ? ` — ${m.verified_count}/${m.total_count} verified (${m.coverage_pct}%)` : '') +
        (m.explore_phase ? ` — ${m.explore_phase}` : '');
    } catch(_e) { info.style.display = 'none'; }
  } else {
    info.style.display = 'block';
    info.innerHTML = `<strong>Chain from:</strong> ${_escHtml(jobId)}`;
  }
}

// ── DOM refs ─────────────────────────────────────────────
const $ = id => document.getElementById(id);

const sections = ['sec-upload','sec-invocables','sec-generate','sec-chat'];
const stepItems = [1,2,3,4].map(n => $(`step${n}-item`));
const connectors = ['conn12','conn23','conn34'].map(id => $(id));

function showSection(idx) {
  sections.forEach((id, i) => $s(id).classList.toggle('hidden', i !== idx));
  stepItems.forEach((el, i) => {
    el.classList.remove('active','done');
    if (i < idx)  el.classList.add('done');
    if (i === idx) el.classList.add('active');
  });
  connectors.forEach((el, i) => el.classList.toggle('done', i < idx));
}

function $s(id) { return document.getElementById(id); }

// ── Error helpers ─────────────────────────────────────────
function showError(elId, msg) {
  const el = $(elId);
  el.textContent = msg; el.classList.add('show');
}
function clearError(elId) { $(elId).classList.remove('show'); }

// ── File drop ─────────────────────────────────────────────
const fileInput = $('file-input');
const fileDrop  = $('file-drop');

fileInput.addEventListener('change', () => {
  const name = fileInput.files[0]?.name || '';
  $('file-name').textContent = name ? `✓ ${name}` : '';
  // clear the path field when a file is chosen
  if (name) $('dir-path').value = '';
  _syncAnalyzeBtn();
  clearError('upload-error');
});

$('dir-path').addEventListener('input', () => {
  // clear file selection when a path is typed
  if ($('dir-path').value.trim()) {
    fileInput.value = '';
    $('file-name').textContent = '';
  }
  _syncAnalyzeBtn();
  clearError('upload-error');
});

function _syncAnalyzeBtn() {
  const hasFile = !!fileInput.files[0];
  const hasPath = !!$('dir-path').value.trim();
  $('analyze-btn').disabled = !hasFile && !hasPath;
}

['dragover','dragleave','drop'].forEach(ev =>
  fileDrop.addEventListener(ev, e => {
    e.preventDefault();
    if (ev === 'dragover') fileDrop.classList.add('dragover');
    else fileDrop.classList.remove('dragover');
    if (ev === 'drop') {
      fileInput.files = e.dataTransfer.files;
      fileInput.dispatchEvent(new Event('change'));
    }
  })
);

// ── Analyze ───────────────────────────────────────────────
$('analyze-btn').addEventListener('click', async () => {
  clearError('upload-error');
  const file    = fileInput.files[0];
  const dirPath = $('dir-path').value.trim();
  if (!file && !dirPath) return;

  const btn = $('analyze-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Analyzing…';

  try {
    let data;
    if (dirPath) {
      // §2.b installed-path route
      const res = await fetch('/api/analyze-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dirPath, hints: $('hints').value.trim(), use_cases: $('use-cases').value.trim() }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`${res.status}: ${err}`);
      }
      data = await res.json();
    } else {
      // §2.a file-upload route
      const fd = new FormData();
      fd.append('file', file);
      fd.append('hints', $('hints').value.trim());
      fd.append('use_cases', $('use-cases').value.trim());
      const res = await fetch('/api/analyze', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`${res.status}: ${err}`);
      }
      data = await res.json();
    }
    // Both routes return 202 {job_id, status_url} — poll until done
    const jobId = data.job_id;
    state.jobId = jobId;
    if (!jobId) throw new Error('No job_id in response');

    // Poll GET /api/jobs/{id} until status is done or error
    let jobResult = null;
    let jobState = null;
    let _pollMisses = 0;
    for (let i = 0; i < 200; i++) {
      await new Promise(r => setTimeout(r, 3000));
      btn.innerHTML = `<span class="spinner"></span> Analyzing… (${(i+1)*3}s)`;
      const poll = await fetch(`/api/jobs/${jobId}`);
      await _refreshLabStatus();
      if (!poll.ok) {
        // Tolerate transient cross-pod 404s and proxy/network blips (502/503/504)
        // up to 5 consecutive misses before giving up.
        if ([404, 502, 503, 504].includes(poll.status) && ++_pollMisses <= 5) continue;
        throw new Error(`Poll failed: ${poll.status}`);
      }
      _pollMisses = 0;
      const s = await poll.json();
      jobState = s;
      if (s.status === 'done') { jobResult = s.result; break; }
      if (s.status === 'error') throw new Error(s.error || 'Discovery failed');
    }
    if (!jobResult) throw new Error('Analysis timed out after 600s');

    await _updateRunReviewFromStatus(jobState);
    _loadAndShowVerdict(jobId);
    _refreshShowcaseArtifacts(jobId);
    state.invocables = flattenInvocables(jobResult.invocables);
    const _label = fileInput.files[0]?.name || $('dir-path').value.split(/[\/\\]/).pop() || state.jobId;
    _saveRecentJob(state.jobId, _label);
    buildInvocablesList();
    showSection(1);
  } catch(e) {
    showError('upload-error', `Analysis failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Analyze Binary';
  }
});

// ── Flatten invocables from the discovery JSON ────────────
function flattenInvocables(raw) {
  // The discovery JSON can come in several shapes; normalise to a flat array.
  // Always normalise individual items so `doc`, `signature`, and `execution`
  // are reliably present for the rest of the UI.
  function normalise(inv) {
    return {
      ...inv,
      // discovery uses `description`; older formats may use `doc`/`signature`
      doc: inv.doc ?? inv.description ?? '',
      signature: inv.signature ?? inv.description ?? inv.name ?? '',
      parameters: inv.parameters ?? [],
      execution: inv.execution ?? {},
      tier: inv.tier ?? inv.confidence_tier ?? 2,
    };
  }

  // Plain array – already normalised (the API now always returns this)
  if (Array.isArray(raw)) return raw.map(normalise);

  // Nested discovery format: {metadata:{}, invocables:[…], summary:{}}
  // Also handles the case where the API accidentally passes the full JSON dict.
  if (raw && Array.isArray(raw.invocables)) return raw.invocables.map(normalise);

  // OpenAI function-call tool schema: {tools: [{type:"function", function:{…}}]}
  if (raw && Array.isArray(raw.tools)) return raw.tools.map(t => normalise({
    name: t.function?.name ?? t.name,
    signature: t.function?.description ?? '',
    doc: t.function?.description ?? '',
    parameters: Object.entries(t.function?.parameters?.properties ?? {}).map(([k,v])=>({name:k,type:v.type})),
    tier: 1,
    execution: t.execution ?? {},
  }));

  // Legacy flat object {name: {signature, doc, …}}
  // Guard against top-level metadata/summary keys sneaking in.
  if (raw && typeof raw === 'object') {
    const skip = new Set(['metadata', 'summary', 'mcp_version', 'component']);
    return Object.entries(raw)
      .filter(([k]) => !skip.has(k))
      .map(([name, info]) => normalise({
        name,
        signature: info.signature ?? name,
        doc: info.doc ?? info.description ?? '',
        parameters: info.parameters ?? [],
        tier: info.tier ?? 2,
        execution: info.execution ?? {},
      }));
  }
  return [];
}

function buildInvocablesList() {
  const list = $('inv-list');
  list.innerHTML = '';

  if (!state.invocables.length) {
    list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted)">No invocables discovered.</div>';
    return;
  }

  state.invocables.forEach((inv, idx) => {
    const item = document.createElement('div');
    item.className = 'inv-item';

    const tier = inv.tier ?? 2;
    const tierLabel = ['','T1','T2','T3'][tier] ?? 'T?';
    const tierClass = `tier-${Math.min(tier,3)}`;

    item.innerHTML = `
      <input type="checkbox" id="cb${idx}" checked />
      <div style="flex:1;min-width:0">
        <div class="inv-name">${esc(inv.name)}</div>
        ${inv.signature && inv.signature !== inv.name
          ? `<div class="inv-sig">${esc(inv.signature)}</div>` : ''}
        ${inv.doc ? `<div class="inv-doc">${esc(inv.doc)}</div>` : ''}
      </div>
      <span class="inv-tier ${tierClass}">${tierLabel}</span>
    `;

    item.querySelector('input').addEventListener('change', updateSelCount);
    item.addEventListener('click', e => {
      if (e.target.tagName !== 'INPUT') item.querySelector('input').click();
    });
    list.appendChild(item);
  });

  updateSelCount();
  const f = fileInput.files[0];
  if (f) {
    $('component-name').value = f.name.replace(/\.\w+$/,'') || 'mcp-component';
  }
}

function updateSelCount() {
  const total = state.invocables.length;
  const n = document.querySelectorAll('#inv-list input[type=checkbox]:checked').length;
  $('sel-count').textContent = `${n} / ${total} selected`;
  $('generate-btn').disabled = n === 0;
}

async function _generateSchemaForSelection(selected, opts = {}) {
  const showChat = !!opts.showChat;
  clearError('inv-error');

  const btn = $('generate-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generatingâ€¦';

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: state.jobId,
        selected,
        component_name: $('component-name').value.trim() || 'mcp-component',
      }),
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const data = await res.json();
    state.tools = data.mcp_schema?.tools ?? [];
    state.schemaBlob = data.schema_blob;
    $('schema-preview').textContent = JSON.stringify(data.mcp_schema, null, 2);
    showSection(showChat ? 3 : 2);
    _refreshShowcaseArtifacts(state.jobId);
    _checkSchemaQuality(data.mcp_schema);
    return data;
  } catch(e) {
    showError('inv-error', `Generation failed: ${e.message}`);
    throw e;
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Generate MCP Schema';
  }
}

$('sel-all-btn').addEventListener('click',  () => {
  document.querySelectorAll('#inv-list input[type=checkbox]').forEach(cb => cb.checked = true);
  updateSelCount();
});
$('sel-none-btn').addEventListener('click', () => {
  document.querySelectorAll('#inv-list input[type=checkbox]').forEach(cb => cb.checked = false);
  updateSelCount();
});

// ── Generate ──────────────────────────────────────────────
$('generate-btn').addEventListener('click', async () => {
  clearError('inv-error');
  const checked = [...document.querySelectorAll('#inv-list input[type=checkbox]:checked')];
  const selected = checked.map(cb => {
    const idx = parseInt(cb.id.replace('cb',''));
    return state.invocables[idx];
  });
  return await _generateSchemaForSelection(selected);

  const btn = $('generate-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating…';

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: state.jobId,
        selected,
        component_name: $('component-name').value.trim() || 'mcp-component',
      }),
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    const data = await res.json();
    state.tools = data.mcp_schema?.tools ?? [];
    state.schemaBlob = data.schema_blob;
    $('schema-preview').textContent = JSON.stringify(data.mcp_schema, null, 2);
    showSection(2);
    _refreshShowcaseArtifacts(state.jobId);
    // Show discover bar if schema has generic param names (param_1, param_2…)
    _checkSchemaQuality(data.mcp_schema);
  } catch(e) {
    showError('inv-error', `Generation failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Generate MCP Schema';
  }
});

// ── Schema quality check → show Discover bar ─────────────
function _checkSchemaQuality(schema) {
  if (!schema) return;
  const tools = schema.tools ?? [];
  const genericRe = /^param_\d+$/;
  let allGeneric = tools.length > 0;
  for (const t of tools) {
    const props = Object.keys(t.function?.parameters?.properties ?? {});
    if (props.some(p => !genericRe.test(p))) { allGeneric = false; break; }
  }
  const bar = $('discover-bar');
  if (allGeneric && tools.length > 0) {
    bar.style.display = 'flex';
  } else {
    bar.style.display = 'none';
  }
  // Always show download-doc-btn if findings already exist
  _maybeShowDownloadDoc();
}

async function _maybeShowDownloadDoc() {
  if (!state.jobId) return;
  try {
    const r = await fetch(`/api/findings/${state.jobId}`);
    if (r.ok) {
      const d = await r.json();
      if (d.findings && d.findings.length > 0) {
        $('download-doc-btn').style.display = 'inline-flex';
      }
    }
  } catch(_e) { /* non-fatal */ }
}

async function _bootstrapShowcaseDefaults() {
  try {
    const res = await fetch(`/api/showcase/bootstrap${window.location.search || ''}`);
    if (!res.ok) return;
    const bootstrap = await res.json();
    state.featuredShowcase = bootstrap.featured || null;
    _renderFeaturedShowcase();
    _renderShowcaseSnapshot();
    _renderShowcaseGraph();
    _renderShowcaseEvidence();
    const jobId = (bootstrap.default_job_id || '').trim();
    if (!jobId) return;

    await _openScannedJob(jobId, jobId);

    if (bootstrap.auto_generate_schema && state.invocables.length > 0) {
      await _generateSchemaForSelection(state.invocables, { showChat: true });
    }
  } catch(_e) { /* non-fatal */ }
}

let _explorePoller = null;

_syncExploreToggleDefaultsFromMode();
_renderRecentJobs();
_fetchRecentJobsFromAPI();
_renderPreviousScansBar();
_bootstrapShowcaseDefaults();
$('explore-mode').addEventListener('change', _syncExploreToggleDefaultsFromMode);
$('autofill-hints-btn').addEventListener('click', () => _applyContosoPreset('hints'));
$('autofill-use-cases-btn').addEventListener('click', () => _applyContosoPreset('use-cases'));

// Recent-jobs: selecting a job pre-fills checkpoint ID, loads chain info, verdict, and MC decisions
$('recent-jobs-select').addEventListener('change', () => {
  const jobId = $('recent-jobs-select').value;
  if (jobId) {
    $('checkpoint-id').value = jobId;
    state.jobId = jobId;
    _updateChainInfo(jobId);
    _loadAndShowVerdict(jobId);
    _loadAndShowMCDecisions(jobId);
    _refreshShowcaseArtifacts(jobId);
  } else {
    $('chain-info').style.display = 'none';
    $('verdict-panel').style.display = 'none';
    $('mc-viewer').style.display = 'none';
    _refreshShowcaseArtifacts('');
  }
});

// Preset buttons
document.querySelectorAll('.preset-btn[data-preset]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _syncSettingsFromPreset(btn.dataset.preset);
  });
});

$('cancel-explore-btn').addEventListener('click', async () => {
  if (!state.jobId) return;
  try {
    await fetch(`/api/jobs/${state.jobId}/explore-cancel`, { method: 'POST' });
    $('discover-bar-msg').textContent = 'Cancellation requested — finalizing partial results…';
  } catch (_e) {
    $('discover-bar-msg').textContent = 'Cancel request failed. Try again.';
  }
});

$('discover-btn').addEventListener('click', async () => {
  if (!state.jobId) return;
  const btn = $('discover-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Discovering…';
  $('cancel-explore-btn').style.display = 'inline-flex';
  $('last-run-time').style.display = 'none';
  $('discover-bar-msg').textContent = 'Starting exploration…';
  _syncModeBadge();

  try {
    const checkedBoxes = [...document.querySelectorAll('#inv-list input[type=checkbox]:checked')];
    const selectedInvocables = checkedBoxes.length > 0
      ? checkedBoxes.map(cb => state.invocables[parseInt(cb.id.replace('cb',''))])
      : state.invocables;
    const res = await fetch(`/api/jobs/${state.jobId}/explore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        invocables: selectedInvocables,
        explore_settings: _exploreSettingsPayload(),
      }),
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);

    // Poll job status for explore_phase progress
    _explorePoller = setInterval(async () => {
      try {
        const pr = await fetch(`/api/jobs/${state.jobId}`);
        await _refreshLabStatus();
        if (!pr.ok) return;
        const s = await pr.json();
        state.currentJobStatus = s;
        const phase = s.explore_phase;
        const progress = s.explore_progress ?? '';
        const msg = s.explore_message ?? '';
        const runtime = s.explore_runtime || {};
        if (runtime.mode) {
          $('mode-badge').textContent = `Mode: ${runtime.mode}`;
          $('mode-badge').style.display = 'inline-flex';
        }

        _updateStageStepper(s);

        if (phase === 'exploring' || phase === 'cancel_requested') {
          $('discover-bar-msg').textContent =
            `Exploring functions… (${progress})${msg ? ' — ' + msg : ''}`;
        } else if (phase === 'done' || phase === 'awaiting_clarification' || phase === 'canceled') {
          clearInterval(_explorePoller);
          if (phase === 'awaiting_clarification') {
            $('discover-bar-msg').textContent =
              `✓ Discovery complete (${progress}) — clarification questions pending`;
          } else if (phase === 'canceled') {
            $('discover-bar-msg').textContent =
              `⚠ Discovery canceled (${progress}) — partial data preserved`;
          } else {
            $('discover-bar-msg').textContent =
              `✓ Discovery complete (${progress} functions documented)`;
          }
          if (s.explore_last_run_seconds != null) {
            $('last-run-time').textContent = `Last run: ${Number(s.explore_last_run_seconds).toFixed(1)}s`;
            $('last-run-time').style.display = 'inline';
          }
          btn.disabled = false;
          btn.innerHTML = '🔍 Discover';
          $('cancel-explore-btn').style.display = 'none';
          $('download-doc-btn').style.display = 'inline-flex';
          // Save to recent jobs with explore result info
          if (state.jobId) {
            const _lbl = fileInput.files[0]?.name || $('dir-path').value.split(/[\/\\]/).pop() || state.jobId;
            _saveRecentJob(state.jobId, _lbl + ' [explored]');
          }
          // Refresh schema preview
          try {
            const sr = await fetch(`/api/download/${state.jobId}/mcp_schema.json`);
            if (sr.ok) {
              const newSchema = await sr.json();
              state.tools = newSchema.tools ?? state.tools;
              $('schema-preview').textContent = JSON.stringify(newSchema, null, 2);
            }
          } catch(_e) { /* non-fatal */ }
          // Surface confidence gap questions if any were generated
          const gaps = s.explore_questions;
          renderGapQuestions(gaps);
          // Show Python spec download button and refine panel
          $('download-spec-btn').style.display = 'inline-flex';
          $('download-schema-btn').style.display = 'inline-flex';
          $('refine-box').style.display = 'block';
          // Load verdict and MC decisions after explore completes
          _loadAndShowVerdict(state.jobId);
          _loadAndShowMCDecisions(state.jobId);
          await _updateRunReviewFromStatus(s);
          await _refreshShowcaseArtifacts(state.jobId);
          // Re-render gap questions after refinement completes
          try {
            const sr2 = await fetch(`/api/jobs/${state.jobId}`);
            if (sr2.ok) { const s2 = await sr2.json(); renderGapQuestions(s2.explore_questions); }
          } catch(_e) {}
        } else if (phase === 'error') {
          clearInterval(_explorePoller);
          $('discover-bar-msg').textContent = `Discovery error: ${s.explore_error ?? 'unknown'}`;
          btn.disabled = false;
          btn.innerHTML = '🔍 Discover';
          $('cancel-explore-btn').style.display = 'none';
        }
      } catch(_e) { /* poll failures are non-fatal */ }
    }, 3000);

  } catch(e) {
    $('discover-bar-msg').textContent = `Discovery failed: ${e.message}`;
    btn.disabled = false;
    btn.innerHTML = '🔍 Discover';
    $('cancel-explore-btn').style.display = 'none';
  }
});

$('download-doc-btn').addEventListener('click', () => {
  if (!state.jobId) return;
  window.location.href = `/api/jobs/${state.jobId}/report`;
});

$('download-spec-btn').addEventListener('click', () => {
  if (!state.jobId) return;
  window.location.href = `/api/download/${state.jobId}/behavioral_spec.py`;
});

$('download-schema-btn').addEventListener('click', () => {
  if (!state.jobId) return;
  window.location.href = `/api/download/${state.jobId}/mcp_schema.json`;
});

// ── Gap question helpers ──────────────────────────────────
function renderGapQuestions(gaps) {
  if (!gaps || gaps.length === 0) return;
  const list = $('gap-questions-list');
  list.innerHTML = '';
  gaps.forEach((g, idx) => {
    const li = document.createElement('li');
    li.style.marginBottom = '10px';
    li.innerHTML = `<span style="font-weight:500">${g.question || g.uncertainty || ''}</span>`;
    const detail = g.technical_detail || g.uncertainty;
    if (detail) {
      const sub = document.createElement('span');
      sub.style.cssText = 'display:block;font-size:.76rem;color:#6b7280;margin-top:2px;font-family:monospace';
      sub.textContent = `Technical detail: ${detail}`;
      li.appendChild(sub);
    }
    // Answer input
    const ansWrap = document.createElement('div');
    ansWrap.style.cssText = 'margin-top:5px;display:flex;gap:6px;align-items:center';
    const ta = document.createElement('input');
    ta.type = 'text';
    ta.dataset.gapIdx = idx;
    ta.dataset.gapFn = g.function || 'general';
    ta.dataset.gapQ = g.question || g.uncertainty || '';
    ta.placeholder = 'Type your answer here…';
    ta.style.cssText = 'flex:1;padding:4px 7px;border:1px solid #f59e0b;border-radius:5px;font-size:.8rem;background:#fffdf0';
    ansWrap.appendChild(ta);
    li.appendChild(ansWrap);
    list.appendChild(li);
  });
  $('gap-questions-box').style.display = 'block';
  $('gap-answers-row').style.display = 'flex';
}

$('submit-gap-answers-btn').addEventListener('click', async () => {
  if (!state.jobId) return;
  const inputs = $('gap-questions-list').querySelectorAll('input[data-gap-idx]');
  const answers = [];
  inputs.forEach(inp => {
    if (inp.value.trim()) {
      answers.push({ function: inp.dataset.gapFn, question: inp.dataset.gapQ, answer: inp.value.trim() });
    }
  });
  if (!answers.length) {
    $('gap-answers-msg').textContent = 'Enter at least one answer first.';
    return;
  }
  $('submit-gap-answers-btn').disabled = true;
  $('gap-answers-msg').textContent = 'Saving…';
  try {
    const res = await fetch(`/api/jobs/${state.jobId}/answer-gaps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers }),
    });
    if (!res.ok) throw new Error(await res.text());
    $('gap-answers-msg').textContent = `✓ ${answers.length} answer(s) saved — re-running discovery on affected functions…`;

    // Auto-trigger refinement on only the functions that had gap questions answered.
    // The user should never have to manually re-run discover after answering gaps.
    const targetFns = [...new Set(answers.map(a => a.function).filter(f => f && f !== 'general'))];
    const refineRes = await fetch(`/api/jobs/${state.jobId}/refine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_functions: targetFns,
        explore_settings: _exploreSettingsPayload(),
      }),
    });
    if (refineRes.ok) {
      $('gap-answers-msg').textContent = `✓ Answers saved — refining ${targetFns.length || 'all'} function(s)…`;
      $('discover-bar-msg').textContent = 'Refining with your answers…';
      $('discover-bar').style.display = 'flex';
      $('cancel-explore-btn').style.display = 'inline-flex';
      // Reuse explore poller
      if (_explorePoller) clearInterval(_explorePoller);
      _explorePoller = setInterval(async () => {
        try {
          const pr = await fetch(`/api/jobs/${state.jobId}`);
          await _refreshLabStatus();
          if (!pr.ok) return;
          const s = await pr.json();
          state.currentJobStatus = s;
          if (s.explore_phase === 'exploring' || s.explore_phase === 'cancel_requested') {
            $('discover-bar-msg').textContent = `Refining… (${s.explore_progress ?? ''}) — ${s.explore_message ?? ''}`;
          } else if (s.explore_phase === 'done' || s.explore_phase === 'awaiting_clarification' || s.explore_phase === 'canceled') {
            clearInterval(_explorePoller);
            if (s.explore_phase === 'awaiting_clarification') {
              $('discover-bar-msg').textContent = `✓ Refinement complete — clarification questions pending`;
            } else if (s.explore_phase === 'canceled') {
              $('discover-bar-msg').textContent = `⚠ Refinement canceled — partial updates preserved`;
            } else {
              $('discover-bar-msg').textContent = `✓ Refinement complete — schema updated`;
            }
            $('submit-gap-answers-btn').disabled = false;
            $('cancel-explore-btn').style.display = 'none';
            await _updateRunReviewFromStatus(s);
            const newGaps = s.explore_questions || [];
            if (newGaps.length > 0) {
              $('gap-answers-msg').textContent = `✓ Done — ${newGaps.length} new question(s) need your input.`;
              renderGapQuestions(newGaps);
            } else {
              $('gap-answers-msg').textContent = `✓ Done — all gaps resolved.`;
            }
            // Refresh schema preview
            try {
              const sr = await fetch(`/api/download/${state.jobId}/mcp_schema.json`);
              if (sr.ok) {
                const ns = await sr.json();
                state.tools = ns.tools ?? state.tools;
                $('schema-preview').textContent = JSON.stringify(ns, null, 2);
              }
            } catch (_) {}
          }
        } catch (_) {}
      }, 2500);
    } else {
      $('gap-answers-msg').textContent = `✓ ${answers.length} answer(s) saved.`;
      $('submit-gap-answers-btn').disabled = false;
    }
  } catch(e) {
    $('gap-answers-msg').textContent = `Failed: ${e.message}`;
    $('submit-gap-answers-btn').disabled = false;
  }
});

$('refine-btn').addEventListener('click', async () => {
  if (!state.jobId) return;
  const corrections = $('refine-corrections').value.trim();
  const missing     = $('refine-missing').value.trim();
  const targetsRaw  = $('refine-targets').value.trim();
  const targets     = targetsRaw ? targetsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];

  if (!corrections && !missing) {
    $('refine-msg').textContent = 'Enter a correction or missing function description first.';
    return;
  }

  const btn = $('refine-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Refining…';
  $('refine-msg').textContent = '';

  try {
    const res = await fetch(`/api/jobs/${state.jobId}/refine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        corrections,
        missing,
        target_functions: targets,
        explore_settings: _exploreSettingsPayload(),
      }),
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);

    $('refine-msg').textContent = 'Refinement started — watch the progress bar above.';
    // Re-use the same explore poller to watch progress
    $('discover-bar-msg').textContent = 'Refining…';
    $('cancel-explore-btn').style.display = 'inline-flex';
    _explorePoller = setInterval(async () => {
      try {
        const pr = await fetch(`/api/jobs/${state.jobId}`);
        if (!pr.ok) return;
        const s = await pr.json();
        state.currentJobStatus = s;
        const phase = s.explore_phase;
        const progress = s.explore_progress ?? '';
        if (phase === 'exploring' || phase === 'cancel_requested') {
          $('discover-bar-msg').textContent = `Refining… (${progress}) — ${s.explore_message ?? ''}`;
        } else if (phase === 'done' || phase === 'awaiting_clarification' || phase === 'canceled') {
          clearInterval(_explorePoller);
          if (phase === 'awaiting_clarification') {
            $('discover-bar-msg').textContent = `✓ Refinement complete (${progress}) — clarification questions pending`;
          } else if (phase === 'canceled') {
            $('discover-bar-msg').textContent = `⚠ Refinement canceled (${progress})`;
          } else {
            $('discover-bar-msg').textContent = `✓ Refinement complete (${progress})`;
          }
          btn.disabled = false;
          btn.textContent = '🔄 Run Refinement';
          $('cancel-explore-btn').style.display = 'none';
          await _updateRunReviewFromStatus(s);
          // Re-render updated gap questions
          const newGaps = s.explore_questions || [];
          if (newGaps.length > 0) {
            $('refine-msg').textContent = `Done. Schema updated — ${newGaps.length} new question(s) surfaced.`;
            renderGapQuestions(newGaps);
          } else {
            $('refine-msg').textContent = 'Done. Schema and spec have been updated.';
          }
          // Refresh schema preview
          try {
            const sr = await fetch(`/api/download/${state.jobId}/mcp_schema.json`);
            if (sr.ok) {
              const ns = await sr.json();
              state.tools = ns.tools ?? state.tools;
              $('schema-preview').textContent = JSON.stringify(ns, null, 2);
            }
          } catch(_e) {}
        } else if (phase === 'error') {
          clearInterval(_explorePoller);
          $('discover-bar-msg').textContent = `Refinement error: ${s.explore_error ?? 'unknown'}`;
          btn.disabled = false;
          btn.textContent = '🔄 Run Refinement';
          $('cancel-explore-btn').style.display = 'none';
        }
      } catch(_e) {}
    }, 3000);
  } catch(e) {
    $('refine-msg').textContent = `Refinement failed: ${e.message}`;
    btn.disabled = false;
    btn.textContent = '🔄 Run Refinement';
    $('cancel-explore-btn').style.display = 'none';
  }
});

// ── Chat ──────────────────────────────────────────────────
$('to-chat-btn').addEventListener('click', () => showSection(3));

async function sendMessage() {
  const input = $('chat-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  clearError('chat-error');

  appendChatMsg('user', text);
  state.messages.push({ role: 'user', content: text });

  const btn = $('send-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  // Streaming response — create a placeholder bubble and fill it live
  let assistantBubble = null;
  let assistantText   = '';
  let roundCount      = 1;

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages:   state.messages,
        tools:      state.tools,
        invocables: state.invocables,
        job_id:     state.jobId,
      }),
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buf     = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += decoder.decode(value, { stream: true });

      // SSE lines are separated by \n\n; process every complete event
      let boundary;
      while ((boundary = buf.indexOf('\n\n')) !== -1) {
        const raw = buf.slice(0, boundary).trim();
        buf = buf.slice(boundary + 2);

        if (!raw.startsWith('data:')) continue;
        let evt;
        try { evt = JSON.parse(raw.slice(5).trim()); }
        catch { continue; }

        if (evt.type === 'token') {
          // Append to the live assistant bubble
          assistantText += evt.content;
          if (!assistantBubble) {
            assistantBubble = appendChatBubble('assistant', assistantText);
          } else {
            assistantBubble.textContent = assistantText;
            $('chat-window').scrollTop = $('chat-window').scrollHeight;
          }

        } else if (evt.type === 'tool_call') {
          const argStr = typeof evt.args === 'string' ? evt.args : JSON.stringify(evt.args ?? {});
          appendChatMsg('tool-call', `🔧 ${evt.name}(${argStr})`);

        } else if (evt.type === 'tool_result') {
          appendChatMsg('tool-call', `   ↳ ${evt.result ?? ''}`);

        } else if (evt.type === 'status') {
          appendChatMsg('tool-call', `⏳ ${evt.message ?? 'Working...'}`);

        } else if (evt.type === 'done') {
          roundCount = evt.rounds ?? 1;

        } else if (evt.type === 'error') {
          throw new Error(evt.message);
        }
      }
    }

    // If no text tokens came through at all (shouldn't happen after server fix,
    // but keep a non-alarming fallback just in case).
    if (!assistantBubble && !assistantText) {
      assistantText = 'Done.';
      assistantBubble = appendChatBubble('assistant', assistantText);
    }
    if (roundCount > 1) {
      appendChatMsg('tool-call', `ℹ️ Completed in ${roundCount} agentic round(s)`);
    }
    state.messages.push({ role: 'assistant', content: assistantText });

  } catch(e) {
    showError('chat-error', `Chat error: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Send';
  }
}

function appendChatBubble(role, text) {
  const win = $('chat-window');
  $('chat-empty')?.remove();
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
  return div;
}

function appendChatMsg(role, text) {
  appendChatBubble(role, text);
}

$('send-btn').addEventListener('click', sendMessage);

$('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

// ── Download (transcript only — schema download is in Generate section) ──
$('transcript-btn').addEventListener('click', () => {
  const lines = state.messages
    .filter(m => m.role !== 'system')
    .map(m => `[${m.role.toUpperCase()}]\n${m.content ?? ''}`)
    .join('\n\n---\n\n');
  const blob = new Blob([lines], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `mcp-transcript-${state.jobId ?? 'session'}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
});

$('lab-refresh-btn').addEventListener('click', _refreshLabStatus);

$('refresh-review-btn').addEventListener('click', async () => {
  if (!state.jobId) return;
  try {
    const res = await fetch(`/api/jobs/${state.jobId}`);
    if (!res.ok) throw new Error(`${res.status}`);
    const status = await res.json();
    await _updateRunReviewFromStatus(status);
    await _loadAndShowVerdict(state.jobId);
    await _refreshShowcaseArtifacts(state.jobId);
  } catch (_e) { /* non-fatal */ }
});

$('review-report-btn').addEventListener('click', () => {
  if (!state.jobId) return;
  fetch(`/api/jobs/${state.jobId}/report`)
    .then(async res => {
      if (!res.ok) throw new Error(`${res.status}`);
      return await res.text();
    })
    .then(text => _showPreviewModal('Verification Report', `Job ${state.jobId}`, text))
    .catch(() => _showPreviewModal('Verification Report', `Job ${state.jobId}`, 'The report could not be loaded into the preview panel.'));
});

$('review-schema-btn').addEventListener('click', () => {
  if (!state.jobId) return;
  fetch(`/api/download/${state.jobId}/mcp_schema.json`)
    .then(async res => {
      if (!res.ok) throw new Error(`${res.status}`);
      return await res.json();
    })
    .then(payload => _showPreviewModal('MCP Schema', `Job ${state.jobId}`, JSON.stringify(payload, null, 2)))
    .catch(() => _showPreviewModal('MCP Schema', `Job ${state.jobId}`, 'The schema could not be loaded into the preview panel.'));
});

$('review-findings-btn').addEventListener('click', async () => {
  if (!state.jobId) return;
  try {
    const res = await fetch(`/api/findings/${state.jobId}`);
    if (!res.ok) throw new Error(`${res.status}`);
    const payload = await res.json();
    _showPreviewModal('Findings JSON', `Job ${state.jobId}`, JSON.stringify(payload, null, 2));
  } catch (_e) { /* non-fatal */ }
});

$('review-session-btn').addEventListener('click', () => {
  if (!state.jobId) return;
  window.open(`/api/jobs/${state.jobId}/session-snapshot`, '_blank');
});

$('showcase-report-btn').addEventListener('click', () => $('review-report-btn').click());
$('showcase-schema-btn').addEventListener('click', () => $('review-schema-btn').click());
$('showcase-findings-btn').addEventListener('click', () => $('review-findings-btn').click());
$('showcase-session-btn').addEventListener('click', () => $('review-session-btn').click());

$('review-campaign-btn').addEventListener('click', () => {
  const campaignId = state.currentJobStatus?.campaign_id;
  if (!campaignId) return;
  window.open(`/api/campaigns/${campaignId}/session-snapshot`, '_blank');
});

$('graph-expand-btn').addEventListener('click', _openGraphModal);
$('campaign-expand-btn').addEventListener('click', _openCampaignModal);
$('preview-modal-close').addEventListener('click', () => _setModalOpen('preview-modal', false));
$('graph-modal-close').addEventListener('click', () => _setModalOpen('graph-modal', false));
$('campaign-modal-close').addEventListener('click', () => _setModalOpen('campaign-modal', false));
$('preview-modal').addEventListener('click', (e) => {
  if (e.target.id === 'preview-modal') _setModalOpen('preview-modal', false);
});
$('graph-modal').addEventListener('click', (e) => {
  if (e.target.id === 'graph-modal') _setModalOpen('graph-modal', false);
});
$('campaign-modal').addEventListener('click', (e) => {
  if (e.target.id === 'campaign-modal') _setModalOpen('campaign-modal', false);
});

// ── Navigation ────────────────────────────────────────────
$('back1-btn').addEventListener('click',  () => showSection(0));
$('back2-btn').addEventListener('click',  () => showSection(1));
$('back3-btn').addEventListener('click',  () => showSection(2));

$('restart-btn').addEventListener('click', () => {
  state.jobId = null; state.invocables = []; state.tools = [];
  state.schemaBlob = null; state.findings = []; state.prereqGraph = null; state.messages = [];
  state.currentJobStatus = null; state.currentVerdict = null; state.currentCampaign = null;
  fileInput.value = ''; $('file-name').textContent = '';
  $('dir-path').value = ''; $('hints').value = ''; $('use-cases').value = '';
  $('analyze-btn').disabled = true;
  $('run-review-header').style.display = 'none';
  $('run-review').style.display = 'none';
  $('chat-window').innerHTML =
    '<div class="chat-empty" id="chat-empty">Send a message to start the conversation.<br/><span style="font-size:.75rem;">e.g. "What tools are available?" or "Run add(3, 4)"</span></div>';
  _refreshShowcaseArtifacts('');
  showSection(0);
});

// ── Utility ───────────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// Init
showSection(0);
_refreshShowcaseArtifacts('');
_refreshLabStatus();
setInterval(_refreshLabStatus, 30000);