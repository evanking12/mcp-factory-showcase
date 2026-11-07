from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.pipeline.core.finding_status import normalize_status

PIPELINE_URL: str = os.getenv("PIPELINE_URL", "http://127.0.0.1:8201").rstrip("/")
GUI_BRIDGE_URL: str = os.getenv("GUI_BRIDGE_URL", "http://127.0.0.1:8090").rstrip("/")
ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
SPECTRUM_CASES_DIR = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "cases"
)
LAB_RESTART_SCRIPT = REPO_ROOT / "sessions" / "restart_dashboard_lab.ps1"
SIMPLE_TEST_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "contoso_config" / "contoso_cs.dll"
STAGES: list[dict[str, str]] = [
    {"id": "analysis-entry", "label": "Analysis Entry"},
    {"id": "s00", "label": "Setup"},
    {"id": "s01", "label": "Discovery"},
    {"id": "s02", "label": "Probe"},
    {"id": "s03", "label": "Model"},
    {"id": "s04", "label": "Cross DLL"},
    {"id": "s05", "label": "Enrich"},
    {"id": "s06", "label": "Verify"},
    {"id": "s07", "label": "Finalize"},
]
STAGE_GOALS = {
    "analysis-entry": "Enter analysis and emit the first trustworthy discovery artifacts.",
    "s00": "Initialize the lane, inputs, and session state.",
    "s01": "Discover exports, signatures, and candidate callable surface.",
    "s02": "Probe functions, calibrate sentinels, and test direct behavior.",
    "s03": "Refine model hypotheses and argument understanding.",
    "s04": "Assess cross-DLL handoffs, dependency shape, and contradictions.",
    "s05": "Enrich artifacts, evidence, and documentation surfaces.",
    "s06": "Verify callable behavior and wrapper-level confidence.",
    "s07": "Finalize artifacts, summaries, and review surfaces.",
}
VERDICT_LAYER_MISSING_HOOKS = [
    "campaign-summary",
    "stage-summary",
]

app = FastAPI(title="MCP Factory Dashboard", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))

_http: httpx.AsyncClient | None = None


def _load_spectrum_case_registry() -> dict[str, list[str]]:
    registry: dict[str, list[str]] = {}
    if not SPECTRUM_CASES_DIR.exists():
        return registry
    for path in SPECTRUM_CASES_DIR.glob("*-manifest.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        case_id = str(payload.get("case_id") or "").strip()
        active_modules_raw = payload.get("active_modules")
        active_modules = (
            [str(item).strip() for item in active_modules_raw if str(item).strip()]
            if isinstance(active_modules_raw, list)
            else []
        )
        if case_id and active_modules:
            registry[case_id] = active_modules
    return registry


SPECTRUM_CASE_REGISTRY = _load_spectrum_case_registry()


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(base_url=PIPELINE_URL, timeout=60.0)
    return _http


def _port_label(url: str, fallback: str) -> str:
    match = re.search(r":(\d+)$", url)
    return match.group(1) if match else fallback


def _stage_sort_key(stage_id: str) -> int:
    for idx, stage in enumerate(STAGES):
        if stage["id"] == stage_id:
            return idx
    return len(STAGES) + 1


def _severity_rank(value: str) -> int:
    return {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4,
    }.get(str(value or "").lower(), 5)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _clean_title(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _trust_impact_for_status(status: str, finding: dict[str, Any]) -> str:
    contradiction = str(finding.get("contradiction_state") or "").lower()
    if contradiction in {"confirmed", "blocked"}:
        return "high"
    if status == "failure":
        return "high"
    if status == "functional_precondition_unmet":
        return "medium"
    if status == "inferred_success":
        return "medium"
    return "low"


def _class_for_status(status: str, finding: dict[str, Any]) -> str:
    contradiction = str(finding.get("contradiction_state") or "").lower()
    if contradiction in {"tentative", "blocked", "confirmed"}:
        return "contradiction"
    if finding.get("blocker_family"):
        return "missing prerequisite"
    if status == "failure":
        return "blocker"
    if status == "functional_precondition_unmet":
        return "warning"
    if status == "inferred_success":
        return "warning"
    return "warning"


def _severity_for_status(status: str, finding: dict[str, Any]) -> str:
    contradiction = str(finding.get("contradiction_state") or "").lower()
    if contradiction in {"blocked", "confirmed"}:
        return "critical"
    if status == "failure":
        return "high"
    if status == "functional_precondition_unmet":
        return "medium"
    if status == "inferred_success":
        return "low"
    return "low"


def _owner_layer_for_finding(finding: dict[str, Any]) -> str:
    raw = str(
        _coalesce(
            finding.get("owner_layer"),
            finding.get("layer"),
            finding.get("likely_regression_cause"),
            finding.get("blocker_family"),
        )
        or ""
    ).lower()
    if "contract" in raw:
        return "contract"
    if "capture" in raw or "artifact" in raw:
        return "capture"
    if "measure" in raw or "validation" in raw:
        return "measurement"
    if "arch" in raw or "cross-dll" in raw:
        return "architecture"
    if "plateau" in raw:
        return "plateau"
    if "contradict" in raw:
        return "contradiction"
    return "state"


def _confidence_for_finding(status: str, finding: dict[str, Any]) -> float:
    if finding.get("working_call"):
        return 0.9
    if finding.get("blocker_family"):
        return 0.8
    if status == "failure":
        return 0.72
    if status == "functional_precondition_unmet":
        return 0.66
    if status == "inferred_success":
        return 0.52
    return 0.4


def _first_iteration_label(job: dict[str, Any], finding: dict[str, Any]) -> str:
    return str(
        _coalesce(
            finding.get("first_failing_iteration"),
            finding.get("iteration"),
            job.get("iteration"),
            f"job:{job.get('job_id', 'unknown')}",
        )
    )


def _primary_evidence(job_id: str, finding: dict[str, Any], report_available: bool) -> dict[str, Any]:
    function_name = str(finding.get("function") or "unknown")
    details = str(
        _coalesce(
            finding.get("finding"),
            finding.get("detail"),
            finding.get("summary"),
            finding.get("stop_reason"),
            finding.get("blocker_family"),
            "No primary evidence text emitted yet.",
        )
    )
    url = f"/api/findings/{job_id}"
    label = f"Finding evidence for {function_name}"
    source = "pipeline-route"
    if report_available and not details:
        url = f"/api/jobs/{job_id}/report"
        label = f"Report evidence for {function_name}"
        source = "report-route"
    return {
        "label": label,
        "url": url,
        "source": source,
        "summary": details,
    }


def _supporting_evidence(job_id: str, report_available: bool) -> list[dict[str, Any]]:
    items = [
        {
            "label": "Findings JSON",
            "url": f"/api/findings/{job_id}",
            "source": "pipeline-route",
            "summary": "Recorded findings for the selected iteration.",
            "evidence_type": "supporting evidence",
            "why_it_matters": "Findings show whether the run emitted blocker-class outputs at all.",
        },
        {
            "label": "Macro verdict",
            "url": f"/api/jobs/{job_id}/verdict",
            "source": "pipeline-route",
            "summary": "Legacy macro verdict surface.",
            "evidence_type": "supporting evidence",
            "why_it_matters": "Useful only after the root blocker and verdict hierarchy are understood.",
        },
    ]
    if report_available:
        items.insert(
            0,
            {
                "label": "Markdown report",
                "url": f"/api/jobs/{job_id}/report",
                "source": "pipeline-route",
                "summary": "Human-readable report for the selected iteration.",
                "evidence_type": "supporting evidence",
                "why_it_matters": "A zero-function report can itself be evidence of pre-artifact failure.",
            },
        )
    return items


def _first_line(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text.splitlines()[0].strip() or fallback


def _humanize_step_token(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "Current Step"
    match = re.match(r"^(\d+)[-_ ]*(.*)$", text)
    prefix = ""
    core = text
    if match:
        prefix = f"{match.group(1).zfill(2)} "
        core = match.group(2) or ""
    core = core.strip()
    if "." in core:
        core = core.split(".", 1)[0]
    if core.startswith("spectrum_"):
        core = core[len("spectrum_") :]
    words = [part.capitalize() for part in re.split(r"[_\-\s]+", core) if part]
    pretty = " ".join(words) if words else text
    return f"{prefix}{pretty}".strip()


def _pipeline_stage_for_job(job: dict[str, Any]) -> str:
    if str(job.get("status") or "").lower() == "error":
        return "analysis-entry"
    phase = str(job.get("explore_phase") or "").lower()
    for stage in STAGES:
        if phase == stage["id"] or phase.endswith(stage["id"]) or stage["id"] in phase:
            return stage["id"]
    if phase == "done":
        return "s07"
    if phase == "error":
        return "analysis-entry"
    return "s00"


def _pipeline_stage_label(stage_id: str) -> str:
    for stage in STAGES:
        if stage["id"] == stage_id:
            return stage["label"]
    return _humanize_step_token(stage_id)


def _compact_chain_step(job: dict[str, Any]) -> str:
    raw = str(job.get("playbook_step") or job.get("component_name") or job.get("job_id") or "current-step").strip()
    return raw if raw else "current-step"


def _spectrum_case_id_for_job(job: dict[str, Any]) -> str:
    runtime = job.get("explore_runtime") if isinstance(job.get("explore_runtime"), dict) else {}
    candidates = [
        job.get("lane_id"),
        runtime.get("lane_id"),
        runtime.get("campaign_id"),
        job.get("campaign_id"),
        job.get("component_name"),
        job.get("hints"),
    ]
    for raw in candidates:
        text = str(raw or "").strip().lower()
        match = re.search(r"(easy|medium|hard)[-_]?0?(\d+)", text)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}"
    return ""


def _authored_chain_steps(job: dict[str, Any]) -> list[str]:
    case_id = _spectrum_case_id_for_job(job)
    return list(SPECTRUM_CASE_REGISTRY.get(case_id) or [])


def _derive_chain_steps(job: dict[str, Any], predecessor: str) -> tuple[list[dict[str, Any]], str, int]:
    authored = _authored_chain_steps(job)
    current_component = str(job.get("component_name") or "").strip()
    current_step_id = _compact_chain_step(job)
    if authored and current_component in authored:
        current_index = authored.index(current_component)
        steps = []
        status = str(job.get("status") or "").lower()
        for idx, module in enumerate(authored):
            if idx < current_index:
                step_status = "pass"
            elif idx == current_index:
                step_status = "fail" if status == "error" else ("pass" if status == "done" else "warn")
            else:
                step_status = "pending"
            steps.append(
                {
                    "step_id": module,
                    "raw_id": module,
                    "label": f"{idx + 1:02d} {_humanize_step_token(module)}",
                    "status": step_status,
                    "selected": idx == current_index,
                }
            )
        return steps, current_component, current_index

    steps: list[dict[str, Any]] = []
    if predecessor:
        steps.append(
            {
                "step_id": predecessor,
                "raw_id": predecessor,
                "label": _humanize_step_token(predecessor),
                "status": "pass",
                "selected": False,
            }
        )
    status = str(job.get("status") or "").lower()
    current_status = "fail" if status == "error" else ("pass" if status == "done" else "warn")
    steps.append(
        {
            "step_id": current_component or current_step_id,
            "raw_id": current_step_id,
            "label": _humanize_step_token(current_step_id or current_component),
            "status": current_status,
            "selected": True,
        }
    )
    if status == "error":
        steps.append(
            {
                "step_id": "blocked-downstream",
                "raw_id": "blocked-downstream",
                "label": "Blocked Downstream Steps",
                "status": "pending",
                "selected": False,
            }
        )
    return steps, current_component or current_step_id, max(len(steps) - 2, 0)


def _chain_context(bundle: dict[str, Any]) -> dict[str, Any]:
    job = bundle["job"]
    current = _compact_chain_step(job)
    predecessor_ids = [str(item) for item in _as_list(job.get("cross_dll_prior_job_ids")) if item]
    prior_job_id = str(job.get("prior_job_id") or "").strip()
    if prior_job_id:
        predecessor_ids.insert(0, prior_job_id)
    predecessor_ids = [item for item in predecessor_ids if item]
    predecessor = predecessor_ids[0] if predecessor_ids else ""
    status = str(job.get("status") or "").lower()
    current_component = str(job.get("component_name") or job.get("job_id") or "current-job")
    chain_steps, current_step_id, current_index = _derive_chain_steps(job, predecessor)
    blocked = [item["label"] for idx, item in enumerate(chain_steps) if idx > current_index and item["status"] == "pending"]
    pipeline_stage_id = _pipeline_stage_for_job(job)
    pipeline_stage_label = _pipeline_stage_label(pipeline_stage_id)
    return {
        "current_step": current,
        "current_step_id": current_step_id,
        "current_step_label": next((item["label"] for item in chain_steps if item["selected"]), _humanize_step_token(current)),
        "predecessor": predecessor,
        "predecessor_step_label": _humanize_step_token(predecessor) if predecessor else "",
        "downstream_blocked": blocked or ([f"Downstream chained steps after {_humanize_step_token(current_component)} did not run."] if status == "error" else []),
        "downstream_step_labels": blocked,
        "pipeline_stage_id": pipeline_stage_id,
        "pipeline_stage_label": pipeline_stage_label,
        "chain_steps": chain_steps,
        "summary": (
            f"{_humanize_step_token(current)} is the active iteration step at {_pipeline_stage_label(pipeline_stage_id)}."
            if not predecessor
            else f"{_humanize_step_token(current)} followed predecessor job {predecessor} and failed at {_pipeline_stage_label(pipeline_stage_id)}."
        ),
    }


def _evidence_item(
    *,
    label: str,
    summary: str,
    why_it_matters: str,
    evidence_type: str,
    preview_text: str,
    raw_url: str,
    tier: str,
    source: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "summary": summary,
        "why_it_matters": why_it_matters,
        "evidence_type": evidence_type,
        "preview_text": preview_text,
        "raw_url": raw_url,
        "tier": tier,
        "source": source,
    }


def _verdict_preview_lines(verdict_hierarchy: dict[str, Any], derived_layers: dict[str, dict[str, Any]]) -> str:
    native_layers = verdict_hierarchy.get("layers") if isinstance(verdict_hierarchy.get("layers"), dict) else {}
    current = {
        "ingest": ((native_layers.get("ingest_success") or {}).get("status") or derived_layers["ingest_success"]["status"]),
        "semantic": ((native_layers.get("semantic_success") or {}).get("status") or derived_layers["semantic_success"]["status"]),
        "run validity": ((native_layers.get("run_validity") or {}).get("status") or derived_layers["run_validity"]["status"]),
        "validation": ((native_layers.get("validation_completeness") or {}).get("status") or derived_layers["validation_completeness"]["status"]),
    }
    return "; ".join(f"{label}: {value}" for label, value in current.items())


def _artifact_summary_lines(artifacts: dict[str, Any]) -> tuple[str, str]:
    canonical_map = _as_list(artifacts.get("canonical_map"))
    analysis_bundle = artifacts.get("analysis_bundle") if isinstance(artifacts.get("analysis_bundle"), dict) else {}
    manifest_present = bool(analysis_bundle.get("manifest_present"))
    artifact_count = _safe_int(artifacts.get("artifact_count"), 0)
    summary = (
        "No artifact map or session manifest was emitted."
        if artifact_count == 0 and not manifest_present
        else f"{artifact_count} artifact(s) indexed; manifest {'present' if manifest_present else 'missing'}."
    )
    preview = (
        f"artifact count: {artifact_count}; "
        f"manifest: {'present' if manifest_present else 'missing'}; "
        f"canonical map: {len(canonical_map)}"
    )
    return summary, preview


def _native_payload(bundle: dict[str, Any], key: str) -> dict[str, Any]:
    payload = bundle.get(key)
    return payload if isinstance(payload, dict) else {}


def _extract_findings(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("findings")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _parse_validation(report_text: str) -> dict[str, Any]:
    if not report_text:
        return {
            "status": "unknown",
            "detail": "No validation report hook is available yet.",
            "source": "derived",
            "placeholder": True,
            "missing_hooks": ["validation-status"],
        }
    checked_match = re.search(r"Checked:\s*(\d+)", report_text)
    checked = _safe_int(checked_match.group(1)) if checked_match else -1
    if checked == 0:
        return {
            "status": "invalid",
            "detail": "Validation reported Checked: 0, so wrapper or behavior validation did not actually run.",
            "source": "derived",
            "placeholder": False,
            "missing_hooks": ["validation-status"],
        }
    if "not defined" in report_text.lower() or "import failure" in report_text.lower():
        return {
            "status": "invalid",
            "detail": "Validation artifacts mention an import or runtime failure during wrapper validation.",
            "source": "derived",
            "placeholder": False,
            "missing_hooks": ["validation-status"],
        }
    if checked > 0:
        return {
            "status": "valid",
            "detail": f"Validation reported Checked: {checked}.",
            "source": "derived",
            "placeholder": False,
            "missing_hooks": ["validation-status"],
        }
    return {
        "status": "unknown",
        "detail": "Validation completeness could not be derived from the current report text.",
        "source": "derived",
        "placeholder": True,
        "missing_hooks": ["validation-status"],
    }


def _report_documented_count(report_text: str) -> int:
    match = re.search(r"Functions documented:\**\s*(\d+)", report_text or "")
    return _safe_int(match.group(1), -1) if match else -1


def _derive_analysis_entry_failure(job: dict[str, Any], findings: list[dict[str, Any]], report_text: str) -> dict[str, Any] | None:
    if str(job.get("status") or "").lower() != "error":
        return None
    if findings:
        return None
    documented_count = _report_documented_count(report_text)
    if documented_count not in {0, -1}:
        return None
    error_excerpt = str(job.get("error") or job.get("message") or "Analysis failed before discovery artifacts were emitted.").splitlines()[0].strip()
    return {
        "diagnosis_id": f"{job.get('job_id', 'job')}-analysis-entry",
        "title": "Analysis failed before discovery artifacts were emitted",
        "class": "analysis entry failure",
        "severity": "critical",
        "trust_impact": "high",
        "first_failing_stage": "analysis-entry",
        "first_failing_iteration": f"job:{job.get('job_id', 'unknown')}",
        "affected_targets": [str(job.get("component_name") or job.get("job_id") or "current-job")],
        "primary_evidence": {
            "label": "Current job status",
            "url": f"/api/jobs/{job.get('job_id')}",
            "source": "pipeline-route",
            "summary": error_excerpt,
            "evidence_type": "proving evidence",
            "why_it_matters": "Shows that the job failed before findings, staged artifacts, or trustworthy validation could exist.",
        },
        "blast_radius": {
            "summary": "This iteration failed before downstream chained steps could run.",
            "affected_count": 1,
        },
        "recommended_next_action": "Inspect the job error and discovery entrypoint before rerunning downstream stages.",
        "confidence": 0.98,
        "owner_layer": "capture",
        "family_id": "analysis-entry-failure",
        "layer": "pipeline truth weakness",
        "source": "derived",
        "placeholder": True,
        "missing_hooks": ["causal-summary", "artifact-index"],
        "operator_view": {
            "summary": error_excerpt,
            "next_action": "Inspect the job error and discovery entrypoint before rerunning downstream stages.",
        },
        "analysis_view": {
            "job_status": str(job.get("status") or ""),
            "job_message": str(job.get("message") or ""),
            "error_excerpt": error_excerpt,
            "documented_function_count": documented_count,
            "findings_count": 0,
        },
    }


def _build_verdict_layers(
    job: dict[str, Any],
    verdict: dict[str, Any],
    findings: list[dict[str, Any]],
    report_text: str,
) -> dict[str, dict[str, Any]]:
    job_status = str(job.get("status") or "").lower()
    explore_phase = str(job.get("explore_phase") or "").lower()
    failure_count = 0
    warn_count = 0
    for finding in findings:
        status = normalize_status(_coalesce(finding.get("status_canonical"), finding.get("status")))
        if status == "failure":
            failure_count += 1
        elif status in {"functional_precondition_unmet", "inferred_success"}:
            warn_count += 1
    ingest = {
        "status": "pass" if job_status in {"done", "exploring", "queued"} else "fail",
        "detail": f"Job status is {job_status or 'unknown'}.",
        "source": "job-status",
        "placeholder": False,
        "missing_hooks": [],
    }
    semantic_status = "unknown"
    semantic_detail = "No canonical semantic success hook exists yet."
    if failure_count:
        semantic_status = "fail"
        semantic_detail = f"{failure_count} failure-class finding(s) remain."
    elif findings:
        semantic_status = "pass" if warn_count == 0 else "warn"
        semantic_detail = (
            "No failure-class findings remain."
            if warn_count == 0
            else f"{warn_count} warning-class finding(s) remain."
        )
    validity_status = "unknown"
    validity_detail = "Run validity is being inferred from job state until a native verdict hierarchy route exists."
    if job_status == "done" and explore_phase == "done":
        validity_status = "pass"
        validity_detail = "Job and explore phase are both terminal done."
    elif job_status == "error" or explore_phase == "error":
        validity_status = "fail"
        validity_detail = "Job status or explore phase ended in error."
    elif explore_phase in {"cancel_requested", "awaiting_clarification"}:
        validity_status = "warn"
        validity_detail = f"Explore phase is {explore_phase}, so the run is not fully trustworthy yet."
    validation = _parse_validation(report_text)
    return {
        "ingest_success": ingest,
        "semantic_success": {
            "status": semantic_status,
            "detail": semantic_detail,
            "source": "derived",
            "placeholder": True,
            "missing_hooks": ["verdict-hierarchy", "canonical-diagnostics-feed"],
        },
        "run_validity": {
            "status": validity_status,
            "detail": validity_detail,
            "source": "derived",
            "placeholder": True,
            "missing_hooks": ["verdict-hierarchy"],
        },
        "validation_completeness": validation,
    }


def _build_diagnoses(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    native = _native_payload(bundle, "native_diagnostics")
    native_diagnoses = native.get("diagnoses")
    if isinstance(native_diagnoses, list) and native_diagnoses:
        return [item for item in native_diagnoses if isinstance(item, dict)]
    job = bundle["job"]
    findings = bundle["findings"]
    report_text = bundle["report_text"]
    diagnoses: list[dict[str, Any]] = []
    report_available = bool(report_text)
    analysis_entry_failure = _derive_analysis_entry_failure(job, findings, report_text)
    if analysis_entry_failure:
        diagnoses.append(analysis_entry_failure)
    for idx, finding in enumerate(findings):
        status = normalize_status(_coalesce(finding.get("status_canonical"), finding.get("status")))
        contradiction = str(finding.get("contradiction_state") or "").lower()
        if status == "verified_success" and contradiction in {"", "none"}:
            continue
        title = _clean_title(
            _coalesce(
                finding.get("title"),
                finding.get("finding"),
                finding.get("detail"),
                finding.get("summary"),
                finding.get("function"),
            ),
            f"Finding {idx + 1}",
        )
        function_name = str(finding.get("function") or "unknown")
        diagnoses.append(
            {
                "diagnosis_id": f"{job.get('job_id', 'job')}-{idx}-{function_name}",
                "title": title,
                "class": _class_for_status(status, finding),
                "severity": _severity_for_status(status, finding),
                "trust_impact": _trust_impact_for_status(status, finding),
                "first_failing_stage": str(
                    _coalesce(
                        finding.get("first_blocking_stage"),
                        finding.get("source_stage"),
                        finding.get("first_stage"),
                        job.get("explore_phase"),
                        "s02",
                    )
                ),
                "first_failing_iteration": _first_iteration_label(job, finding),
                "affected_targets": [
                    name
                    for name in {
                        function_name,
                        str(finding.get("downstream_function") or ""),
                        str(finding.get("dependent_function") or ""),
                    }
                    if name
                ],
                "primary_evidence": _primary_evidence(str(job.get("job_id") or ""), finding, report_available),
                "blast_radius": {
                    "summary": str(
                        _coalesce(
                            finding.get("blocker_family"),
                            finding.get("likely_regression_cause"),
                            "No explicit blast radius emitted yet.",
                        )
                    ),
                    "affected_count": max(1, len(_as_list(finding.get("dependency_chain"))) or 1),
                },
                "recommended_next_action": str(
                    _coalesce(
                        finding.get("suggested_next_step"),
                        finding.get("next_action"),
                        "Inspect the linked evidence and resolve the first failing stage before rerunning broad exploration.",
                    )
                ),
                "confidence": _confidence_for_finding(status, finding),
                "owner_layer": _owner_layer_for_finding(finding),
                "family_id": _family_bucket_for_diagnosis(
                    {
                        "class": _class_for_status(status, finding),
                        "owner_layer": _owner_layer_for_finding(finding),
                        "blast_radius": {
                            "summary": str(
                                _coalesce(
                                    finding.get("blocker_family"),
                                    finding.get("likely_regression_cause"),
                                    ""
                                )
                            )
                        },
                    }
                ),
                "layer": "pipeline truth weakness" if status == "failure" else "aggregation weakness",
                "source": "derived",
                "placeholder": True,
                "missing_hooks": ["canonical-diagnostics-feed", "causal-summary", "artifact-index"],
            }
        )
    validation = _parse_validation(report_text)
    if validation["status"] == "invalid" and not analysis_entry_failure:
        diagnoses.append(
            {
                "diagnosis_id": f"{job.get('job_id', 'job')}-validation-gap",
                "title": "Validation completeness is broken or missing",
                "class": "readiness failure",
                "severity": "high",
                "trust_impact": "high",
                "first_failing_stage": "analysis-entry" if str(job.get("status") or "").lower() == "error" else "s06",
                "first_failing_iteration": f"job:{job.get('job_id', 'unknown')}",
                "affected_targets": [str(job.get("component_name") or job.get("job_id") or "current-job")],
                "primary_evidence": {
                    "label": "Validation summary from markdown report",
                    "url": f"/api/jobs/{job.get('job_id')}/report",
                    "source": "report-route",
                    "summary": validation["detail"],
                },
                "blast_radius": {
                    "summary": "Wrapper or behavior validation cannot be treated as trustworthy until this is resolved.",
                    "affected_count": 1,
                },
                "recommended_next_action": "Repair wrapper validation or publish a canonical validation-status hook before claiming trustworthy coverage.",
                "confidence": 0.9,
                "owner_layer": "measurement",
                "family_id": "validation-failure",
                "layer": "pipeline truth weakness",
                "source": "derived",
                "placeholder": False,
                "missing_hooks": ["validation-status"],
            }
        )
    if not diagnoses:
        diagnoses.append(
            {
                "diagnosis_id": f"{job.get('job_id', 'job')}-placeholder",
                "title": "No blocker-class diagnosis emitted by current hooks",
                "class": "warning",
                "severity": "low",
                "trust_impact": "low",
                "first_failing_stage": str(job.get("explore_phase") or "s07"),
                "first_failing_iteration": f"job:{job.get('job_id', 'unknown')}",
                "affected_targets": [str(job.get("component_name") or job.get("job_id") or "current-job")],
                "primary_evidence": {
                    "label": "Review current report",
                    "url": f"/api/jobs/{job.get('job_id')}/report",
                    "source": "report-route",
                    "summary": "Current hooks do not emit a richer canonical diagnosis yet.",
                },
                "blast_radius": {"summary": "No blast radius available.", "affected_count": 0},
                "recommended_next_action": "Inspect report and findings, then add richer canonical diagnostics to the pipeline.",
                "confidence": 0.3,
                "owner_layer": "measurement",
                "family_id": "measurement-gap",
                "layer": "aggregation weakness",
                "source": "derived",
                "placeholder": True,
                "missing_hooks": ["canonical-diagnostics-feed", "causal-summary"],
            }
        )
    diagnoses.sort(
        key=lambda item: (
            _severity_rank(item["severity"]),
            _stage_sort_key(item["first_failing_stage"]),
            item["title"],
        )
    )
    return diagnoses


def _build_run_diff(bundle: dict[str, Any]) -> dict[str, Any]:
    job = bundle["job"]
    verdict_hierarchy = _native_payload(bundle, "native_verdict_hierarchy")
    recent_jobs = bundle["recent_jobs"]
    current_verified = _safe_int(job.get("verified_count"))
    current_total = _safe_int(job.get("total_count"))
    current_contradictions = sum(
        1
        for finding in bundle["findings"]
        if str(finding.get("contradiction_state") or "").lower() not in {"", "none"}
    )
    baseline = next((item for item in recent_jobs if item.get("job_id") != job.get("job_id")), None)
    previous_verified = _safe_int((baseline or {}).get("verified_count"))
    previous_total = _safe_int((baseline or {}).get("total_count"))
    previous_contradictions = _safe_int((baseline or {}).get("contradiction_count"))
    verdict_layers = verdict_hierarchy.get("layers") if isinstance(verdict_hierarchy.get("layers"), dict) else bundle["verdict_layers"]
    previous_layers = {
        key: {"status": "unknown", "detail": "No previous comparable verdict surface yet."}
        for key in verdict_layers
    }
    return {
        "source": "native-route" if verdict_hierarchy else "derived",
        "placeholder": baseline is None or not verdict_hierarchy,
        "missing_hooks": ["campaign-summary"] if baseline is None else [],
        "baseline_job_id": (baseline or {}).get("job_id"),
        "verified_count_delta": current_verified - previous_verified,
        "total_count_delta": current_total - previous_total,
        "regression_count": max(0, previous_verified - current_verified),
        "contradiction_delta": current_contradictions - previous_contradictions,
        "observer_failure_delta": 0,
        "duration_delta": None,
        "cost_delta": None,
        "verdict_layers": {
            key: {
                "current": verdict_layers[key],
                "previous": previous_layers[key],
            }
            for key in verdict_layers
        },
    }


def _build_trust_frontier(bundle: dict[str, Any]) -> dict[str, Any]:
    diagnoses = _build_diagnoses(bundle)
    validation_payload = _native_payload(bundle, "native_validation_status")
    counts = {
        "verified": 0,
        "inferred": 0,
        "unresolved": 0,
        "contradictory": 0,
        "regressed": 0,
        "validation_incomplete": 0,
    }
    for diagnosis in diagnoses:
        cls = str(diagnosis.get("class") or "").lower()
        severity = str(diagnosis.get("severity") or "").lower()
        if cls == "contradiction":
            counts["contradictory"] += 1
        if severity in {"critical", "high"}:
            counts["unresolved"] += 1
        elif cls == "warning":
            counts["inferred"] += 1
        else:
            counts["verified"] += 1
    if str(validation_payload.get("status") or "").lower() in {"invalid", "warn", "partial", "unknown"}:
        counts["validation_incomplete"] = 1
    return {
        "source": "native-route" if validation_payload else "derived",
        "placeholder": not bool(validation_payload),
        "missing_hooks": [] if validation_payload else ["validation-status"],
        "counts": counts,
        "locally_green_but_globally_untrusted": counts["validation_incomplete"] > 0 or counts["contradictory"] > 0,
    }


def _build_blast_radius(bundle: dict[str, Any], diagnoses: list[dict[str, Any]]) -> dict[str, Any]:
    causal = _native_payload(bundle, "native_causal_summary")
    job = bundle["job"]
    runtime = job.get("explore_runtime") if isinstance(job.get("explore_runtime"), dict) else {}
    expected = _as_list(runtime.get("selected_invocable_names"))
    discovered = {str(finding.get("function") or "") for finding in bundle["findings"] if finding.get("function")}
    extra = sorted(name for name in discovered if name and name not in expected)
    top = diagnoses[0]
    return {
        "source": "native-route" if causal else "derived",
        "placeholder": not bool(causal),
        "missing_hooks": [] if causal else ["causal-summary", "artifact-index"],
        "top_blocker_id": top["diagnosis_id"],
        "summary": str(causal.get("blast_radius_summary") or top["blast_radius"]["summary"]),
        "expected_surface": expected,
        "additional_discovered_surface": extra,
        "locally_green_but_globally_untrusted": _build_trust_frontier(bundle)["locally_green_but_globally_untrusted"],
        "affected_targets": top["affected_targets"],
        "affected_stages": causal.get("affected_stages") or [],
        "affected_transitions": causal.get("affected_transitions") or [],
    }


def _build_stage_detail(
    bundle: dict[str, Any],
    stage_id: str,
    diagnoses: list[dict[str, Any]],
    family_id: str | None = None,
) -> dict[str, Any]:
    causal = _native_payload(bundle, "native_causal_summary")
    artifacts = _native_payload(bundle, "native_artifacts")
    filtered = diagnoses
    if family_id:
        filtered = [item for item in diagnoses if _family_bucket_for_diagnosis(item) == family_id]
    stage_diagnoses = [item for item in filtered if item["first_failing_stage"] == stage_id]
    top = stage_diagnoses[0] if stage_diagnoses else (filtered[0] if filtered else diagnoses[0])
    stage_truth = "native" if causal.get("first_failing_stage") == stage_id else "inferred"
    primary_artifacts = [
        {**item, "tier": str(item.get("tier") or "tier1")}
        for item in (artifacts.get("primary_artifacts") or [top["primary_evidence"]])
    ]
    visible_default_count = min(2, len(primary_artifacts))
    error_excerpt = _first_line(bundle["job"].get("error") or bundle["job"].get("message"), "No explicit job error emitted.")
    artifact_summary, artifact_preview = _artifact_summary_lines(artifacts)
    readable_analysis_rows = [
        {"label": "causal summary", "value": str(causal.get("cause_summary") or top["primary_evidence"]["summary"])},
        {"label": "blast radius", "value": str(causal.get("blast_radius_summary") or top["blast_radius"]["summary"])},
        {"label": "error excerpt", "value": error_excerpt},
        {"label": "findings emitted", "value": "yes" if bundle["findings"] else "no"},
        {"label": "artifact count", "value": str(_safe_int(artifacts.get("artifact_count"), 0))},
        {
            "label": "manifest present",
            "value": "yes" if (artifacts.get("analysis_bundle") or {}).get("manifest_present") else "no",
        },
    ]
    return {
        "stage_id": stage_id,
        "stage_truth": stage_truth,
        "goal": STAGE_GOALS.get(stage_id, "No explicit goal registered."),
        "iteration_id": str(bundle["job"].get("job_id") or "current-job"),
        "inputs": [
            "job status",
            "macro verdict",
            "findings",
            "report text" if bundle["report_text"] else "report text unavailable",
        ],
        "outputs": [
            "diagnosis rollup",
            "first failure within stage" if stage_diagnoses else "no stage-local failure emitted",
            "recommended next action",
        ],
        "blockers": [item["title"] for item in stage_diagnoses] or ["No stage-specific blockers emitted yet."],
        "first_failure": {
            "title": top["title"],
            "cause": str(causal.get("cause_summary") or top["primary_evidence"]["summary"]),
            "owner_layer": top["owner_layer"],
            "family_id": _family_bucket_for_diagnosis(top),
        },
        "operator_view": causal.get("operator_view") or {"summary": top["title"]},
        "analysis_view": {
            "causal_summary_text": str(causal.get("cause_summary") or top["primary_evidence"]["summary"]),
            "blast_radius_summary": str(causal.get("blast_radius_summary") or top["blast_radius"]["summary"]),
            "error_excerpt": error_excerpt,
            "emitted_findings": "present" if bundle["findings"] else "missing",
            "stage_index": "present" if causal.get("first_failing_stage") else "missing",
            "transition_index": "present" if _as_list(causal.get("affected_transitions")) else "missing",
            "artifact_count": str(_safe_int(artifacts.get("artifact_count"), 0)),
            "manifest_present": "yes" if (artifacts.get("analysis_bundle") or {}).get("manifest_present") else "no",
            "artifact_summary_text": artifact_summary,
            "artifact_preview": artifact_preview,
            "readable_analysis_rows": readable_analysis_rows,
        },
        "evidence": {
            "items": primary_artifacts,
            "visible_default_count": visible_default_count,
            "has_more_tier1": len(primary_artifacts) > visible_default_count,
            "tier1_total": len(primary_artifacts),
            "more_label": "Show more stage evidence",
        },
        "recommended_next_action": top["recommended_next_action"],
        "source": "native-route" if causal or artifacts else "derived",
        "placeholder": not bool(causal and artifacts),
        "missing_hooks": ([] if causal else ["causal-summary"]) + ([] if artifacts else ["artifact-index"]),
    }


def _build_evidence_stack(bundle: dict[str, Any], diagnoses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    job = bundle["job"]
    job_id = str(job.get("job_id") or "")
    verdict_hierarchy = _native_payload(bundle, "native_verdict_hierarchy")
    validation_status = _native_payload(bundle, "native_validation_status")
    causal = _native_payload(bundle, "native_causal_summary")
    diagnostics = _native_payload(bundle, "native_diagnostics")
    findings = bundle["findings"]
    report_text = bundle["report_text"]
    documented_count = _report_documented_count(report_text)
    artifact_summary, artifact_preview = _artifact_summary_lines(bundle.get("native_artifacts") or {})
    top = diagnoses[0]
    evidence: list[dict[str, Any]] = [
        _evidence_item(
            label="Current job status",
            summary=_first_line(job.get("error") or job.get("message"), "No explicit job error emitted."),
            why_it_matters="Shows whether analysis ended before trustworthy artifacts were emitted.",
            evidence_type="proving evidence",
            preview_text="\n".join(
                [
                    f"status: {job.get('status') or 'unknown'}",
                    f"message: {_first_line(job.get('message'), 'n/a')}",
                    f"error: {_first_line(job.get('error'), 'n/a')}",
                ]
            ),
            raw_url=f"/api/jobs/{job_id}",
            tier="tier1",
            source="pipeline-route",
        ),
        _evidence_item(
            label="Verdict hierarchy",
            summary=str(
                _coalesce(
                    (verdict_hierarchy.get("operator_view") or {}).get("summary"),
                    verdict_hierarchy.get("operator_summary"),
                    "No trustworthy verdict can be formed because the iteration failed before core artifacts existed.",
                )
            ),
            why_it_matters="Summarizes the strongest trustworthy success and failure layers currently available.",
            evidence_type="proving evidence",
            preview_text=_verdict_preview_lines(verdict_hierarchy, bundle["verdict_layers"]),
            raw_url=f"/api/jobs/{job_id}/verdict-hierarchy",
            tier="tier1",
            source="pipeline-route",
        ),
        _evidence_item(
            label="Causal summary",
            summary=str(
                _coalesce(
                    (causal.get("operator_view") or {}).get("summary"),
                    causal.get("cause_summary"),
                    top["blast_radius"]["summary"],
                )
            ),
            why_it_matters="Shows where the iteration failed first and what was blocked downstream.",
            evidence_type="proving evidence",
            preview_text=(
                f"{_first_line(causal.get('cause_summary') or top['primary_evidence']['summary'], 'n/a')} "
                f"Blocked chain: {_first_line(causal.get('blast_radius_summary') or top['blast_radius']['summary'], 'n/a')}"
            ),
            raw_url=f"/api/jobs/{job_id}/causal-summary",
            tier="tier1",
            source="pipeline-route",
        ),
        _evidence_item(
            label="Diagnostics",
            summary=top["title"],
            why_it_matters="Provides the canonical blocker and recommended next action currently promoted by the cockpit.",
            evidence_type="proving evidence",
            preview_text="\n".join(
                [
                    f"class: {top['class']}",
                    f"stage: {top['first_failing_stage']}",
                    f"next: {_first_line(top['recommended_next_action'], 'n/a')}",
                ]
            ),
            raw_url=f"/api/jobs/{job_id}/diagnostics",
            tier="tier1",
            source="pipeline-route",
        ),
        _evidence_item(
            label="Validation status",
            summary=str(
                _coalesce(
                    (validation_status.get("operator_view") or {}).get("summary"),
                    validation_status.get("operator_summary"),
                    "Validation status is missing.",
                )
            ),
            why_it_matters="Validation gaps matter, but they should not outrank an earlier analysis-entry failure.",
            evidence_type="missing evidence",
            preview_text="\n".join(
                [
                    f"status: {validation_status.get('status') or 'unknown'}",
                    f"checked: {validation_status.get('checked', 0)}",
                    f"verified_1to1: {validation_status.get('verified_1to1', 0)}",
                ]
            ),
            raw_url=f"/api/jobs/{job_id}/validation-status",
            tier="tier2",
            source="pipeline-route",
        ),
        _evidence_item(
            label="Findings",
            summary="Recorded findings." if findings else "No findings were emitted.",
            why_it_matters=(
                "Findings show what the run proved."
                if findings
                else "An empty findings set can itself be evidence that analysis failed before usable outputs were emitted."
            ),
            evidence_type="supporting evidence" if findings else "empty evidence",
            preview_text=(
                "\n".join(_first_line(item.get("finding") or item.get("summary") or item.get("function"), "n/a") for item in findings[:3])
                if findings
                else "No findings emitted for this iteration."
            ),
            raw_url=f"/api/findings/{job_id}",
            tier="tier3",
            source="pipeline-route",
        ),
        _evidence_item(
            label="Report",
            summary=(
                f"Report documents {documented_count} function(s)."
                if documented_count >= 0
                else "No readable report content was emitted."
            ),
            why_it_matters="A report with zero documented functions supports the artifact-emission failure story.",
            evidence_type="supporting evidence" if documented_count > 0 else "empty evidence",
            preview_text=(
                f"{documented_count} functions documented."
                if documented_count >= 0
                else _first_line(report_text, "No report preview available.")
            ),
            raw_url=f"/api/jobs/{job_id}/report",
            tier="tier3",
            source="pipeline-route",
        ),
        _evidence_item(
            label="Artifacts",
            summary=artifact_summary,
            why_it_matters="Artifact availability determines whether later evidence can be trusted or is simply missing downstream of the root failure.",
            evidence_type="missing evidence" if "No artifact map" in artifact_summary else "supporting evidence",
            preview_text=artifact_preview,
            raw_url=f"/api/jobs/{job_id}/artifacts",
            tier="tier2",
            source="pipeline-route",
        ),
    ]
    return evidence


def _build_evidence_stack_payload(bundle: dict[str, Any], diagnoses: list[dict[str, Any]]) -> dict[str, Any]:
    items = _build_evidence_stack(bundle, diagnoses)
    tier1_items = [item for item in items if item.get("tier") == "tier1"]
    visible_default_count = min(3, len(tier1_items))
    return {
        "items": items,
        "visible_default_count": visible_default_count,
        "has_more_tier1": len(tier1_items) > visible_default_count,
        "tier1_total": len(tier1_items),
    }


def _build_proof_summary(
    evidence_payload: dict[str, Any],
    diagnoses: list[dict[str, Any]],
    families: list[dict[str, Any]],
) -> dict[str, Any]:
    items = evidence_payload.get("items") or []
    tier1_total = _safe_int(evidence_payload.get("tier1_total"), 0)
    visible_default_count = _safe_int(evidence_payload.get("visible_default_count"), min(3, tier1_total))
    evidence_types: dict[str, int] = {}
    tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0}
    for item in items:
        evidence_type = str(item.get("evidence_type") or "supporting evidence")
        evidence_types[evidence_type] = evidence_types.get(evidence_type, 0) + 1
        tier = str(item.get("tier") or "tier1")
        if tier in tier_counts:
            tier_counts[tier] += 1
    present_proof = [item["label"] for item in items if item.get("tier") == "tier1"][:3]
    missing_proof = [item["label"] for item in items if item.get("evidence_type") in {"missing evidence", "empty evidence"}][:4]
    posture = (
        "Root failure is well-supported by job status, verdict layers, and the causal summary."
        if present_proof
        else "Proof posture is still weak because no Tier 1 evidence is visible."
    )
    return {
        "visible_tier1_count": min(visible_default_count, tier1_total),
        "hidden_tier1_count": max(tier1_total - visible_default_count, 0),
        "hidden_tier2_count": tier_counts["tier2"],
        "hidden_tier3_count": tier_counts["tier3"],
        "evidence_types": evidence_types,
        "family_count": len(families),
        "diagnosis_count": len(diagnoses),
        "stage_count": len({item.get("first_failing_stage") for item in diagnoses if item.get("first_failing_stage")}),
        "proof_posture": posture,
        "present_proof": present_proof,
        "missing_proof": missing_proof,
    }


def _build_decision_basis(bundle: dict[str, Any], diagnoses: list[dict[str, Any]]) -> dict[str, Any]:
    job = bundle["job"]
    findings = bundle["findings"]
    report_text = bundle["report_text"]
    top = diagnoses[0]
    promoted_because: list[str] = []
    demoted_candidates: list[str] = []
    documented_count = _report_documented_count(report_text)
    if str(job.get("status") or "").lower() == "error":
        promoted_because.append("job status is error")
    if not findings:
        promoted_because.append("findings are empty")
    if documented_count == 0:
        promoted_because.append("report documents 0 functions")
    if top.get("first_failing_stage") == "analysis-entry":
        promoted_because.append("no stage or transition artifacts were emitted")
    validation_status = _native_payload(bundle, "native_validation_status")
    validation_summary = str(
        _coalesce(
            (validation_status.get("operator_view") or {}).get("summary"),
            validation_status.get("operator_summary"),
            "",
        )
    ).strip()
    if validation_summary:
        demoted_candidates.append(f"Validation status was not promoted because it is downstream: {validation_summary}")
    chain = _chain_context(bundle)
    source_routes = [
        f"/api/jobs/{job.get('job_id')}",
        f"/api/jobs/{job.get('job_id')}/diagnostics",
        f"/api/jobs/{job.get('job_id')}/verdict-hierarchy",
        f"/api/jobs/{job.get('job_id')}/causal-summary",
        f"/api/jobs/{job.get('job_id')}/artifacts",
    ]
    return {
        "job_id": str(job.get("job_id") or ""),
        "alignment_status": "aligned" if promoted_because else "partially_aligned",
        "confidence": top.get("confidence", 0.0),
        "promoted_because": promoted_because,
        "demoted_candidates": demoted_candidates,
        "source_routes": source_routes,
        "chain_context": chain,
        "operator_view": {
            "summary": f"{top['title']} is promoted because the earliest trustworthy evidence points there first.",
            "next_action": top["recommended_next_action"],
        },
        "analysis_view": {
            "promoted_because": promoted_because,
            "demoted_candidates": demoted_candidates,
            "confidence": top.get("confidence", 0.0),
            "chain_context": chain,
        },
        "readable_analysis_rows": [
            {"label": "promoted reasons", "value": str(len(promoted_because))},
            {"label": "demoted reasons", "value": str(len(demoted_candidates))},
            {"label": "confidence", "value": str(top.get("confidence", 0.0))},
        ],
        "source": "derived",
        "placeholder": True,
        "missing_hooks": [],
    }


def _build_overview(bundle: dict[str, Any], diagnoses: list[dict[str, Any]]) -> dict[str, Any]:
    job = bundle["job"]
    verdict_hierarchy = _native_payload(bundle, "native_verdict_hierarchy")
    causal = _native_payload(bundle, "native_causal_summary")
    artifacts = _native_payload(bundle, "native_artifacts")
    diagnostics = _native_payload(bundle, "native_diagnostics")
    top = diagnoses[0]
    chain = _chain_context(bundle)
    run_diff = _build_run_diff(bundle)
    blast = _build_blast_radius(bundle, diagnoses)
    decision_basis = _build_decision_basis(bundle, diagnoses)
    active_family_id = _family_bucket_for_diagnosis(top)
    families = _build_family_blockers(bundle, diagnoses)
    evidence_payload = _build_evidence_stack_payload(bundle, diagnoses)
    active_counts = {
        "family_count": len(families),
        "diagnosis_count": len(diagnoses),
        "stage_count": len({item.get("first_failing_stage") for item in diagnoses if item.get("first_failing_stage")}),
    }
    layout_mode = "singleton" if active_counts["family_count"] == 1 and active_counts["diagnosis_count"] == 1 else "multi_blocker"
    return {
        "top_blocker": {
            "title": top["title"],
            "severity": top["severity"],
            "class": top["class"],
            "owner_layer": top["owner_layer"],
            "operator_view": top.get("operator_view") or diagnostics.get("operator_view") or {},
            "analysis_view": top.get("analysis_view") or diagnostics.get("analysis_view") or {},
        },
        "active_iteration": {
            "iteration_id": str(job.get("job_id") or "current-job"),
            "component_name": str(job.get("component_name") or job.get("job_id") or "unknown-target"),
            "campaign_id": str(_coalesce(job.get("campaign_id"), (job.get("explore_runtime") or {}).get("campaign_id")) or ""),
        },
        "trust_delta_vs_last_good": {
            "verified_count_delta": run_diff["verified_count_delta"],
            "contradiction_delta": run_diff["contradiction_delta"],
            "placeholder": run_diff["placeholder"],
            "operator_view": verdict_hierarchy.get("operator_view") or {},
            "analysis_view": verdict_hierarchy.get("analysis_view") or {},
        },
        "what_changed_this_iteration": {
            "job_status": job.get("status"),
            "explore_phase": job.get("explore_phase"),
            "verified_count": job.get("verified_count"),
            "total_count": job.get("total_count"),
        },
        "blast_radius": {
            "summary": blast["summary"],
            "affected_targets": blast["affected_targets"],
            "locally_green_but_globally_untrusted": blast["locally_green_but_globally_untrusted"],
            "operator_view": causal.get("operator_view") or {},
            "analysis_view": causal.get("analysis_view") or {},
        },
        "recommended_next_action": top["recommended_next_action"],
        "primary_cause": top["title"],
        "secondary_consequence": str(
            _coalesce(
                (bundle.get("native_validation_status") or {}).get("operator_summary"),
                ((bundle.get("native_validation_status") or {}).get("operator_view") or {}).get("summary"),
                "Validation status is missing.",
            )
        ),
        "not_promoted": "Downstream validation absence is not promoted when an earlier analysis-entry failure explains it.",
        "alignment_status": decision_basis["alignment_status"],
        "promotion_basis": decision_basis["promoted_because"],
        "demoted_candidates": decision_basis["demoted_candidates"],
        "supporting_evidence": evidence_payload["items"],
        "layout_mode": layout_mode,
        "active_counts": active_counts,
        "proof_summary": _build_proof_summary(evidence_payload, diagnoses, families),
        "current_context": {
            "campaign_id": str(_coalesce(job.get("campaign_id"), (job.get("explore_runtime") or {}).get("campaign_id")) or "n/a"),
            "iteration_id": str(job.get("job_id") or "current-job"),
            "chain_step_label": chain.get("current_step_label") or _humanize_step_token(chain.get("current_step") or job.get("component_name")),
            "stage_id": str(top["first_failing_stage"] or "unknown"),
            "pipeline_stage_label": chain.get("pipeline_stage_label") or _pipeline_stage_label(str(top["first_failing_stage"] or "unknown")),
            "family_id": active_family_id,
            "family_title": _family_title(active_family_id),
            "diagnosis_id": str(top["diagnosis_id"] or ""),
            "diagnosis_title": str(top["title"] or ""),
            "active_tiers_default": ["tier1"],
            "layout_mode": layout_mode,
        },
        "source": "native-route" if verdict_hierarchy and causal and diagnostics and artifacts else "derived",
        "placeholder": not bool(verdict_hierarchy and causal and diagnostics and artifacts),
        "missing_hooks": [
            *([] if verdict_hierarchy else ["verdict-hierarchy"]),
            *([] if causal else ["causal-summary"]),
            *([] if diagnostics else ["canonical-diagnostics-feed"]),
            *([] if artifacts else ["artifact-index"]),
        ],
    }


def _build_campaign_overview(campaign_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(campaign_payload, dict) or not campaign_payload:
        return {
            "source": "derived",
            "placeholder": True,
            "missing_hooks": ["campaign-overview"],
            "title": "No campaign context available yet",
            "summary": "The selected job did not expose a campaign-level payload through current hooks.",
            "recurring_diagnosis_families": [],
            "targets": [],
        }
    return {
        "source": "pipeline-route",
        "placeholder": False,
        "missing_hooks": [],
        "title": str(_coalesce(campaign_payload.get("campaign_id"), "Campaign overview")),
        "summary": str(
            _coalesce(
                campaign_payload.get("summary"),
                campaign_payload.get("status"),
                "Campaign payload is available but does not expose a richer summary yet.",
            )
        ),
        "recurring_diagnosis_families": _as_list(campaign_payload.get("dominant_blocker_families")),
        "targets": _as_list(campaign_payload.get("jobs")),
    }


def _family_bucket_for_diagnosis(diagnosis: dict[str, Any]) -> str:
    explicit_family_id = str(diagnosis.get("family_id") or "").strip().lower()
    if explicit_family_id:
        return explicit_family_id
    explicit = str(
        _coalesce(
            diagnosis.get("family"),
            diagnosis.get("family_key"),
            diagnosis.get("blast_radius", {}).get("summary"),
            diagnosis.get("class"),
            diagnosis.get("owner_layer"),
        )
        or ""
    ).strip().lower()
    if explicit:
        if "lineage" in explicit or "state" in explicit:
            return "state-lineage"
        if "contract" in explicit:
            return "contract-mismatch"
        if "capture" in explicit or "artifact" in explicit:
            return "capture-gap"
        if "measure" in explicit or "validation" in explicit:
            return "validation-failure"
        if "architect" in explicit or "cross-dll" in explicit:
            return "architecture-bottleneck"
        if "contradict" in explicit:
            return "contradiction-cluster"
    owner_layer = str(diagnosis.get("owner_layer") or "").lower()
    if owner_layer == "state":
        return "state-lineage"
    if owner_layer == "contract":
        return "contract-mismatch"
    if owner_layer == "capture":
        return "capture-gap"
    if owner_layer == "measurement":
        return "validation-failure"
    if owner_layer == "architecture":
        return "architecture-bottleneck"
    if owner_layer == "contradiction":
        return "contradiction-cluster"
    return "measurement-gap"


def _family_title(family_id: str) -> str:
    return {
        "analysis-entry-failure": "Analysis entry failure",
        "state-lineage": "State lineage",
        "contract-mismatch": "Contract mismatch",
        "capture-gap": "Capture gap",
        "measurement-gap": "Measurement gap",
        "architecture-bottleneck": "Architecture bottleneck",
        "contradiction-cluster": "Contradiction cluster",
        "validation-failure": "Validation failure",
    }.get(family_id, family_id.replace("-", " ").title())


def _build_family_blockers(bundle: dict[str, Any], diagnoses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    iteration_id = str(bundle["job"].get("job_id") or "current-job")
    native_diagnostics = _native_payload(bundle, "native_diagnostics")
    for diagnosis in diagnoses:
        family_id = _family_bucket_for_diagnosis(diagnosis)
        current = grouped.setdefault(
            family_id,
            {
                "family_id": family_id,
                "title": _family_title(family_id),
                "severity": diagnosis["severity"],
                "affected_diagnosis_ids": [],
                "affected_stage_ids": set(),
                "affected_iteration_ids": set(),
                "representative_evidence": diagnosis["primary_evidence"],
                "recommended_next_action": diagnosis["recommended_next_action"],
                "source": "derived",
                "placeholder": not bool(native_diagnostics),
                "missing_hooks": [] if native_diagnostics else ["canonical-diagnostics-feed", "causal-summary"],
            },
        )
        if _severity_rank(diagnosis["severity"]) < _severity_rank(current["severity"]):
            current["severity"] = diagnosis["severity"]
            current["representative_evidence"] = diagnosis["primary_evidence"]
            current["recommended_next_action"] = diagnosis["recommended_next_action"]
        current["affected_diagnosis_ids"].append(diagnosis["diagnosis_id"])
        current["affected_stage_ids"].add(diagnosis["first_failing_stage"])
        current["affected_iteration_ids"].add(iteration_id)
    families: list[dict[str, Any]] = []
    for item in grouped.values():
        item["affected_stage_ids"] = sorted(item["affected_stage_ids"])
        item["affected_iteration_ids"] = sorted(item["affected_iteration_ids"])
        item["affected_diagnosis_count"] = len(item["affected_diagnosis_ids"])
        item["affected_stage_count"] = len(item["affected_stage_ids"])
        families.append(item)
    families.sort(key=lambda item: (_severity_rank(item["severity"]), -item["affected_diagnosis_count"], item["title"]))
    return families


def _build_iteration_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    job = bundle["job"]
    run_diff = _build_run_diff(bundle)
    verdict_hierarchy = _native_payload(bundle, "native_verdict_hierarchy")
    verdict_layers = run_diff["verdict_layers"]
    chain = _chain_context(bundle)
    groups = {
        "run_status": [
            {"label": "iteration", "value": str(job.get("job_id") or "current-job")},
            {"label": "target", "value": str(job.get("component_name") or job.get("job_id") or "unknown-target")},
            {"label": "job status", "value": str(job.get("status") or "unknown")},
            {"label": "chain step", "value": chain.get("current_step_label") or "n/a"},
            {"label": "pipeline stage", "value": chain.get("pipeline_stage_label") or "n/a"},
            {"label": "downstream", "value": "; ".join(chain.get("downstream_blocked") or []) or "not emitted"},
        ],
        "verdict_layers": [
            {"label": "ingest", "value": verdict_layers["ingest_success"]["current"]["status"]},
            {"label": "semantic", "value": verdict_layers["semantic_success"]["current"]["status"]},
            {"label": "run validity", "value": verdict_layers["run_validity"]["current"]["status"]},
            {"label": "validation", "value": verdict_layers["validation_completeness"]["current"]["status"]},
        ],
        "delta": [
            {"label": "verified", "value": f"{_safe_int(job.get('verified_count'))}/{_safe_int(job.get('total_count'))}"},
            {"label": "verified delta", "value": str(run_diff.get("verified_count_delta"))},
            {"label": "contradiction delta", "value": str(run_diff.get("contradiction_delta"))},
        ],
    }
    return {
        "iteration_id": str(job.get("job_id") or "current-job"),
        "job_id": str(job.get("job_id") or "current-job"),
        "campaign_id": str(_coalesce(job.get("campaign_id"), (job.get("explore_runtime") or {}).get("campaign_id")) or ""),
        "component_name": str(job.get("component_name") or job.get("job_id") or "unknown-target"),
        "job_status": str(job.get("status") or "unknown"),
        "explore_phase": str(job.get("explore_phase") or "unknown"),
        "chain_context": chain,
        "pipeline_stage_id": chain.get("pipeline_stage_id") or "unknown",
        "pipeline_stage_label": chain.get("pipeline_stage_label") or "Unknown",
        "verified_count": _safe_int(job.get("verified_count")),
        "total_count": _safe_int(job.get("total_count")),
        "verdict_layers": verdict_layers,
        "operator_view": verdict_hierarchy.get("operator_view") or {},
        "analysis_view": verdict_hierarchy.get("analysis_view") or {},
        "groups": groups,
        "delta_vs_previous": {
            "baseline_job_id": run_diff.get("baseline_job_id"),
            "verified_count_delta": run_diff.get("verified_count_delta"),
            "total_count_delta": run_diff.get("total_count_delta"),
            "regression_count": run_diff.get("regression_count"),
            "contradiction_delta": run_diff.get("contradiction_delta"),
        },
        "source": "native-route" if verdict_hierarchy else "derived",
        "placeholder": not bool(verdict_hierarchy),
        "missing_hooks": [] if verdict_hierarchy else ["verdict-hierarchy"],
    }


def _hook_catalog() -> dict[str, Any]:
    return {
        "ready_now": [
            "/api/lab/status",
            "/api/jobs/recent",
            "/api/jobs/{job_id}",
            "/api/jobs/{job_id}/verdict",
            "/api/jobs/{job_id}/verdict-hierarchy",
            "/api/jobs/{job_id}/validation-status",
            "/api/jobs/{job_id}/causal-summary",
            "/api/jobs/{job_id}/diagnostics",
            "/api/jobs/{job_id}/artifacts",
            "/api/findings/{job_id}",
            "/api/jobs/{job_id}/report",
            "/api/fixtures",
            "/api/analyze-path",
            "/api/jobs/{job_id}/events",
        ],
        "dashboard_derived_placeholder": [
            "/api/dashboard/jobs/{job_id}/overview",
            "/api/dashboard/jobs/{job_id}/decision-basis",
            "/api/dashboard/jobs/{job_id}/evidence-stack",
            "/api/dashboard/jobs/{job_id}/iteration-summary",
            "/api/dashboard/jobs/{job_id}/diagnoses",
            "/api/dashboard/jobs/{job_id}/family-blockers",
            "/api/dashboard/jobs/{job_id}/run-diff",
            "/api/dashboard/jobs/{job_id}/trust-frontier",
            "/api/dashboard/jobs/{job_id}/stage-detail/{stage_id}",
            "/api/dashboard/jobs/{job_id}/blast-radius",
            "/api/dashboard/campaigns/{campaign_id}/overview",
        ],
        "pipeline_native_route_still_needed": VERDICT_LAYER_MISSING_HOOKS,
        "groups": [
            {
                "name": "health_and_recovery",
                "human_coverage": "Decide whether the lab is trustworthy, retryable, or needs restart.",
                "hooks": ["/api/lab/status", "/api/dashboard/lab/restart", "/api/dashboard/hooks"],
            },
            {
                "name": "job_selection_and_launch",
                "human_coverage": "Choose a target, launch intake, and move from dead screen to active work.",
                "hooks": ["/api/fixtures", "/api/analyze-path", "/api/jobs/recent", "/api/jobs/{job_id}"],
            },
            {
                "name": "triage_and_verdict",
                "human_coverage": "See the top blocker, trust delta, and verdict-layer disagreement without reading raw logs.",
                "hooks": [
                    "/api/jobs/{job_id}/verdict-hierarchy",
                    "/api/jobs/{job_id}/diagnostics",
                    "/api/dashboard/jobs/{job_id}/overview",
                    "/api/dashboard/jobs/{job_id}/decision-basis",
                    "/api/dashboard/jobs/{job_id}/evidence-stack",
                    "/api/dashboard/jobs/{job_id}/iteration-summary",
                    "/api/dashboard/jobs/{job_id}/diagnoses",
                    "/api/dashboard/jobs/{job_id}/family-blockers",
                    "/api/dashboard/jobs/{job_id}/run-diff",
                    "/api/dashboard/jobs/{job_id}/trust-frontier",
                ],
            },
            {
                "name": "causal_drilldown",
                "human_coverage": "Understand where the failure started, what it poisoned downstream, and what to do next.",
                "hooks": [
                    "/api/jobs/{job_id}/causal-summary",
                    "/api/dashboard/jobs/{job_id}/stage-detail/{stage_id}",
                    "/api/dashboard/jobs/{job_id}/blast-radius",
                    "/api/jobs/{job_id}/events",
                ],
            },
            {
                "name": "evidence_and_review",
                "human_coverage": "Move from triage to proof using canonical findings, verdict, and report artifacts.",
                "hooks": ["/api/jobs/{job_id}/artifacts", "/api/findings/{job_id}", "/api/jobs/{job_id}/verdict", "/api/jobs/{job_id}/report"],
            },
            {
                "name": "campaign_rollup",
                "human_coverage": "Review recurring blocker families and system-level targeting over multiple jobs.",
                "hooks": ["/api/dashboard/campaigns/{campaign_id}/overview"],
            },
        ],
    }


def _restart_dashboard_lab() -> dict[str, Any]:
    if not LAB_RESTART_SCRIPT.exists():
        return {
            "queued": False,
            "status": "missing-script",
            "detail": f"Restart script not found at {LAB_RESTART_SCRIPT}.",
        }
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAB_RESTART_SCRIPT),
        ],
        cwd=str(REPO_ROOT),
        creationflags=creationflags,
    )
    return {
        "queued": True,
        "status": "restart-requested",
        "detail": f"Restarting the dashboard lab services for bridge {_port_label(GUI_BRIDGE_URL, '8090')} and API {_port_label(PIPELINE_URL, '8201')}.",
        "script": str(LAB_RESTART_SCRIPT),
        "expected_services": [
            f"bridge:{_port_label(GUI_BRIDGE_URL, '8090')}",
            f"api:{_port_label(PIPELINE_URL, '8201')}",
        ],
    }


async def _fetch_json(path: str) -> tuple[dict[str, Any] | list[Any] | None, dict[str, Any] | None]:
    try:
        response = await _client().get(path)
        if response.status_code >= 400:
            return None, {
                "path": path,
                "status_code": response.status_code,
                "detail": response.text[:240],
            }
        return response.json(), None
    except Exception as exc:
        return None, {
            "path": path,
            "status_code": 502,
            "detail": str(exc),
        }


async def _fetch_text(path: str) -> tuple[str, dict[str, Any] | None]:
    try:
        response = await _client().get(path)
        if response.status_code >= 400:
            return "", {
                "path": path,
                "status_code": response.status_code,
                "detail": response.text[:240],
            }
        return response.text, None
    except Exception as exc:
        return "", {
            "path": path,
            "status_code": 502,
            "detail": str(exc),
        }


async def _collect_job_bundle(job_id: str) -> dict[str, Any]:
    job_payload, verdict_payload, findings_payload, report_text, recent_payload, verdict_hierarchy_payload, validation_payload, causal_payload, diagnostics_payload, artifacts_payload = await asyncio.gather(
        _fetch_json(f"/api/jobs/{job_id}"),
        _fetch_json(f"/api/jobs/{job_id}/verdict"),
        _fetch_json(f"/api/findings/{job_id}"),
        _fetch_text(f"/api/jobs/{job_id}/report"),
        _fetch_json("/api/jobs/recent"),
        _fetch_json(f"/api/jobs/{job_id}/verdict-hierarchy"),
        _fetch_json(f"/api/jobs/{job_id}/validation-status"),
        _fetch_json(f"/api/jobs/{job_id}/causal-summary"),
        _fetch_json(f"/api/jobs/{job_id}/diagnostics"),
        _fetch_json(f"/api/jobs/{job_id}/artifacts"),
    )
    job = (job_payload[0] if isinstance(job_payload[0], dict) else {}) or {"job_id": job_id}
    if not job.get("job_id"):
        job["job_id"] = job_id
    findings = _extract_findings(findings_payload[0])
    report_value = report_text[0] if isinstance(report_text[0], str) else ""
    bundle = {
        "job": job,
        "verdict": verdict_payload[0] if isinstance(verdict_payload[0], dict) else {},
        "findings": findings,
        "report_text": report_value,
        "recent_jobs": _as_list((recent_payload[0] or {}).get("jobs") if isinstance(recent_payload[0], dict) else []),
        "native_verdict_hierarchy": verdict_hierarchy_payload[0] if isinstance(verdict_hierarchy_payload[0], dict) else {},
        "native_validation_status": validation_payload[0] if isinstance(validation_payload[0], dict) else {},
        "native_causal_summary": causal_payload[0] if isinstance(causal_payload[0], dict) else {},
        "native_diagnostics": diagnostics_payload[0] if isinstance(diagnostics_payload[0], dict) else {},
        "native_artifacts": artifacts_payload[0] if isinstance(artifacts_payload[0], dict) else {},
        "errors": [
            item
            for item in [
                job_payload[1],
                verdict_payload[1],
                findings_payload[1],
                report_text[1],
                recent_payload[1],
                verdict_hierarchy_payload[1],
                validation_payload[1],
                causal_payload[1],
                diagnostics_payload[1],
                artifacts_payload[1],
            ]
            if item
        ],
    }
    bundle["verdict_layers"] = _build_verdict_layers(bundle["job"], bundle["verdict"], bundle["findings"], bundle["report_text"])
    return bundle


def _proxy_error_response(path: str, detail: str, status_code: int = 502) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "upstream_path": f"/api/{path}",
            "source": "dashboard-proxy",
            "upstream_available": False,
        },
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "pipeline_url": PIPELINE_URL}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/simple", response_class=HTMLResponse)
def simple_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "simple.html", {})


@app.post("/api/dashboard/simple/test-run")
async def simple_test_run() -> JSONResponse:
    if not SIMPLE_TEST_FIXTURE.exists():
        return JSONResponse(
            status_code=404,
            content={
                "detail": "The bundled test fixture was not found.",
                "path": str(SIMPLE_TEST_FIXTURE),
            },
        )
    try:
        response = await _client().post(
            "/api/analyze-path",
            json={
                "path": str(SIMPLE_TEST_FIXTURE),
                "skip_cache": True,
                "analysis_profile": "strict_dll",
            },
        )
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=502,
            content={"detail": f"Could not start the test run: {exc}"},
        )
    try:
        payload = response.json()
    except ValueError:
        return JSONResponse(
            status_code=502,
            content={"detail": "The pipeline returned a non-JSON test-run response."},
        )
    return JSONResponse(content=payload, status_code=response.status_code)


@app.get("/api/dashboard/hooks")
def dashboard_hooks() -> dict[str, Any]:
    return _hook_catalog()


@app.post("/api/dashboard/lab/restart")
async def dashboard_lab_restart() -> JSONResponse:
    return JSONResponse(_restart_dashboard_lab(), status_code=202)


@app.get("/api/dashboard/jobs/{job_id}/overview")
async def dashboard_job_overview(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    diagnoses = _build_diagnoses(bundle)
    return JSONResponse({"job_id": job_id, "overview": _build_overview(bundle, diagnoses), "errors": bundle["errors"]})


@app.get("/api/dashboard/jobs/{job_id}/decision-basis")
async def dashboard_job_decision_basis(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    diagnoses = _build_diagnoses(bundle)
    return JSONResponse({"job_id": job_id, "decision_basis": _build_decision_basis(bundle, diagnoses), "errors": bundle["errors"]})


@app.get("/api/dashboard/jobs/{job_id}/evidence-stack")
async def dashboard_job_evidence_stack(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    diagnoses = _build_diagnoses(bundle)
    return JSONResponse({"job_id": job_id, "evidence_stack": _build_evidence_stack_payload(bundle, diagnoses), "errors": bundle["errors"]})


@app.get("/api/dashboard/jobs/{job_id}/iteration-summary")
async def dashboard_job_iteration_summary(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    return JSONResponse(
        {
            "job_id": job_id,
            "iteration_summary": _build_iteration_summary(bundle),
            "errors": bundle["errors"],
        }
    )


@app.get("/api/dashboard/jobs/{job_id}/diagnoses")
async def dashboard_job_diagnoses(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    return JSONResponse({"job_id": job_id, "diagnoses": _build_diagnoses(bundle), "errors": bundle["errors"]})


@app.get("/api/dashboard/jobs/{job_id}/family-blockers")
async def dashboard_job_family_blockers(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    diagnoses = _build_diagnoses(bundle)
    return JSONResponse(
        {
            "job_id": job_id,
            "family_blockers": _build_family_blockers(bundle, diagnoses),
            "errors": bundle["errors"],
        }
    )


@app.get("/api/dashboard/jobs/{job_id}/run-diff")
async def dashboard_job_run_diff(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    return JSONResponse({"job_id": job_id, "run_diff": _build_run_diff(bundle), "errors": bundle["errors"]})


@app.get("/api/dashboard/jobs/{job_id}/trust-frontier")
async def dashboard_job_trust_frontier(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    return JSONResponse({"job_id": job_id, "trust_frontier": _build_trust_frontier(bundle), "errors": bundle["errors"]})


@app.get("/api/dashboard/jobs/{job_id}/blast-radius")
async def dashboard_job_blast_radius(job_id: str) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    diagnoses = _build_diagnoses(bundle)
    return JSONResponse({"job_id": job_id, "blast_radius": _build_blast_radius(bundle, diagnoses), "errors": bundle["errors"]})


@app.get("/api/dashboard/jobs/{job_id}/stage-detail/{stage_id}")
async def dashboard_stage_detail(job_id: str, stage_id: str, family_id: str | None = None) -> JSONResponse:
    bundle = await _collect_job_bundle(job_id)
    diagnoses = _build_diagnoses(bundle)
    return JSONResponse(
        {
            "job_id": job_id,
            "stage_detail": _build_stage_detail(bundle, stage_id, diagnoses, family_id=family_id),
            "errors": bundle["errors"],
        }
    )


@app.get("/api/dashboard/campaigns/{campaign_id}/overview")
async def dashboard_campaign_overview(campaign_id: str) -> JSONResponse:
    payload, error = await _fetch_json(f"/api/campaigns/{campaign_id}")
    return JSONResponse(
        {
            "campaign_id": campaign_id,
            "overview": _build_campaign_overview(payload if isinstance(payload, dict) else {}),
            "errors": [error] if error else [],
        }
    )


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str) -> Response:
    url = f"{PIPELINE_URL}/api/{path}"
    query = str(request.url.query)
    if query:
        url = f"{url}?{query}"

    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:

        async def stream_forward():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    request.method,
                    url,
                    headers=headers,
                    content=body,
                ) as upstream:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            stream_forward(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            upstream = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
    except httpx.HTTPError as exc:
        return _proxy_error_response(path, f"Upstream pipeline request failed: {exc}")
    content_type = upstream.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            payload: Any = upstream.json()
        except ValueError:
            return _proxy_error_response(path, "Upstream returned invalid JSON.", status_code=502)
        return JSONResponse(content=payload, status_code=upstream.status_code)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=content_type or None,
    )
