"""api/routes_session.py – Session-snapshot and report endpoints.

Extracted from main.py so the main app router stays focused on job/explore
dispatch while the large session-artefact assembly logic lives here.

Registered in main.py via:
    from api.routes.routes_session import router as session_router
    app.include_router(session_router)
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import (
    _download_blob,
    _get_job_status,
    _upload_to_blob,
    _load_findings,
    _list_blob_names,
)
from api.infra.storage_api import get_invocables_map
from api.analysis.cohesion import emit_contract_artifacts
from api.pipeline.core.handoff_contract import STAGE_CONTRACTS
from api.pipeline.core.helpers import _infer_param_desc

import logging
logger = logging.getLogger("mcp_factory.api")

router = APIRouter()
SNAPSHOT_SCHEMA_VERSION = "1.0.0"

LEGACY_CAPTURE_STAGE_ALIASES: dict[str, dict[str, Any]] = {
    "stage-00-setup": {
        "canonical_stage_ids": ["S-00", "S-01"],
        "kind": "legacy_capture_alias",
        "note": "Historical capture folder that bundles setup and write-unlock artifacts.",
    },
    "stage-01-probe-loop": {
        "canonical_stage_ids": ["S-02"],
        "kind": "legacy_capture_alias",
        "note": "Historical probe-loop capture folder.",
    },
    "stage-02-synthesis": {
        "canonical_stage_ids": ["S-02", "S-04", "S-05"],
        "kind": "legacy_capture_alias",
        "note": "Historical mixed capture folder containing probe findings, synthesis output, and post-backfill schema views.",
    },
    "stage-03-gap-resolution": {
        "canonical_stage_ids": ["S-06"],
        "kind": "legacy_capture_alias",
        "note": "Historical gap-resolution capture folder.",
    },
    "stage-04-clarification": {
        "canonical_stage_ids": [],
        "kind": "review_surface",
        "note": "Review-only clarification surface; not a canonical pipeline stage in handoff_contract.py.",
    },
    "stage-05-finalization": {
        "canonical_stage_ids": ["S-07"],
        "kind": "legacy_capture_alias",
        "note": "Historical finalization capture folder.",
    },
}

FUTURE_S00_CAPTURE_STAGE_ALIASES: dict[str, dict[str, Any]] = {
    "evidence/stage-00a-setup-baseline": {
        "canonical_stage_id": "s00_setup_baseline",
        "parent_stage": "s00_setup",
        "kind": "future_runtime_stage_alias",
        "note": "Compatibility-safe future home for setup baseline artifacts.",
    },
    "evidence/stage-00b-static-evidence": {
        "canonical_stage_id": "s00_static_evidence",
        "parent_stage": "s00_setup",
        "kind": "future_runtime_stage_alias",
        "note": "Compatibility-safe future home for static evidence artifacts.",
    },
    "evidence/stage-00c-admission-handoff": {
        "canonical_stage_id": "s00_admission_handoff",
        "parent_stage": "s00_setup",
        "kind": "future_runtime_stage_alias",
        "note": "Compatibility-safe future home for the S-00 to S-01 handoff packet.",
    },
}

FUTURE_S02_CAPTURE_STAGE_ALIASES: dict[str, dict[str, Any]] = {
    "evidence/stage-02a-probe-ordering": {
        "canonical_stage_id": "s02_probe_ordering",
        "parent_stage": "s02_probe",
        "kind": "future_runtime_stage_alias",
        "note": "Compatibility-safe future home for probe-ordering artifacts.",
    },
    "evidence/stage-02b-invocation-execution": {
        "canonical_stage_id": "s02_invocation_execution",
        "parent_stage": "s02_probe",
        "kind": "future_runtime_stage_alias",
        "note": "Compatibility-safe future home for invocation execution artifacts.",
    },
    "evidence/stage-02c-evidence-capture": {
        "canonical_stage_id": "s02_evidence_capture",
        "parent_stage": "s02_probe",
        "kind": "future_runtime_stage_alias",
        "note": "Compatibility-safe future home for persisted probe evidence.",
    },
}


def _canonical_stage_model_payload() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for stage in STAGE_CONTRACTS:
        payload.append(
            {
                "id": stage.id,
                "name": stage.name,
                "canonical_artifact_roots": sorted(
                    {
                        req.canonical_path.split("/")[0] + "/" + req.canonical_path.split("/")[1]
                        for req in (
                            stage.required_inputs
                            + stage.required_outputs
                            + stage.required_context
                            + stage.required_reasoning
                        )
                        if "/" in req.canonical_path
                    }
                ),
                "required_outputs": [req.canonical_path for req in stage.required_outputs],
                "required_context": [req.canonical_path for req in stage.required_context],
                "required_reasoning": [req.canonical_path for req in stage.required_reasoning],
                "optional_when": stage.optional_when,
            }
        )
    return payload


def _stage_surface_readme() -> str:
    return "\n".join(
        [
            "# Stage Surfaces",
            "",
            "The semantic source of truth for stage names is:",
            "",
            "- `api/pipeline/core/handoff_contract.py`",
            "",
            "The session snapshot still includes legacy `stage-xx-*` folders for",
            "backward compatibility, but those folders are capture-layout aliases.",
            "They must not be treated as the canonical pipeline stage model.",
            "",
            "Use these files first:",
            "",
            "- `stage-index.json`",
            "- `canonical-stage-model.json`",
            "- `capture-layout-stage-aliases.json`",
            "- `evidence/`",
            "",
            "Important note:",
            "",
            "- `stage-04-clarification/` is a review surface, not a canonical",
            "  stage from `handoff_contract.py`.",
            "",
            "If a chart and a legacy snapshot folder disagree, the chart should",
            "follow the canonical stage model and the snapshot folder should be",
            "read as a compatibility surface only.",
        ]
    )


@router.get("/api/jobs/{job_id}/session-snapshot")
async def session_snapshot(job_id: str, profile: str = Query(default="full")):
    """Return a ZIP archive containing every artifact for this job.

    The ZIP preserves the historical capture layout for backward compatibility,
    but the canonical stage model lives in `handoff_contract.py`, `stage-index.json`,
    `canonical-stage-model.json`, and `evidence/`.

    Historical compatibility folders still included in the ZIP:

      session-meta.json               ← job_id, component, timestamps, counts
      hints.txt                       ← user hints + use_cases verbatim

      stage-00-setup/
          explore_config.json         ← cap profile + limits used this run
          static_analysis.json        ← G-4/G-7/G-8/G-9 binary analysis
          sentinel_calibration.json   ← Phase 0.5 DLL-specific error codes
          schema.json                 ← mcp_schema before any LLM enrichment

      stage-01-probe-loop/
          explore_probe_log.json      ← every probe call and its result
          schema-before.json          ← schema before per-function enrichment
          schema-after.json           ← schema after per-function enrichment

      stage-02-synthesis/
          findings.json               ← all recorded findings (post-synthesis)
          api_reference.md            ← LLM-synthesized API reference doc
          schema-before.json          ← schema before backfill
          schema-after.json           ← schema after backfill / post-discovery

      stage-03-gap-resolution/
          gap_resolution_log.json     ← per-function gap resolution outcomes
          schema-before.json          ← schema before gap resolution
          schema-after.json           ← schema after gap resolution
          mini_session_transcript.txt ← gap-answer mini-session probing log
          mini-schema-before.json     ← schema before mini-session probing
          mini-schema-after.json      ← schema after mini-session probing

      stage-04-clarification/
          clarification-questions.md  ← formatted unanswered confidence gaps
          schema-before.json          ← schema before clarification
          schema-after.json           ← schema after clarification

      stage-05-finalization/
          findings.json               ← final findings after harmonization
          vocab.json                  ← cross-session vocabulary table
          behavioral_spec.py          ← typed Python API contract stub
          invocables_map.json         ← enriched function schema map
          sentinel_catalog.json       ← S1 error-code classifications
          harmonization_report.json   ← deterministic harmonization summary

      diagnostics/
          chat_transcript.txt         ← full LLM chat transcript
          executor_trace.json         ← structured per-call diagnostics
          model_context.txt           ← exact system message the LLM receives
          diagnosis_raw.json          ← per-message diagnosis records
          mini_session_transcript.txt ← also here for convenience
    """
    import io
    import zipfile as _zf

    def _try_blob(blob_name: str) -> bytes | None:
        try:
            return _download_blob(ARTIFACT_CONTAINER, blob_name)
        except Exception:
            return None

    def _zwrite(zf: _zf.ZipFile, zip_name: str, blob_name: str) -> None:
        """Write blob to zip at zip_name; silently skip if blob does not exist."""
        data = _try_blob(blob_name)
        if data is not None:
            zf.writestr(zip_name, data)

    def _zwrite_first(zf: _zf.ZipFile, zip_name: str, blob_names: list[str]) -> None:
        for blob_name in blob_names:
            data = _try_blob(blob_name)
            if data is not None:
                zf.writestr(zip_name, data)
                return

    def _zwrite_json_or_default(zf: _zf.ZipFile, zip_name: str, blob_name: str, default_payload: Any) -> None:
        data = _try_blob(blob_name)
        if data is None:
            zf.writestr(zip_name, json.dumps(default_payload, indent=2))
        else:
            zf.writestr(zip_name, data)

    def _zwrite_job_relative(zf: _zf.ZipFile, rel_name: str) -> None:
        _zwrite(zf, rel_name, f"{job_id}/{rel_name}")

    status = _get_job_status(job_id) or {}

    def _is_terminal_snapshot_state(status_payload: dict[str, Any]) -> bool:
        terminal_values = {
            "done",
            "awaiting_clarification",
            "error",
            "failed",
            "cancelled",
            "canceled",
            "complete",
            "completed",
        }
        explore_phase = str((status_payload or {}).get("explore_phase") or "").strip().lower()
        run_status = str((status_payload or {}).get("status") or "").strip().lower()
        return explore_phase in terminal_values or run_status in terminal_values

    terminal_run = _is_terminal_snapshot_state(status)
    if not terminal_run and _try_blob(f"{job_id}/checkpoints/s07_finalize.json") is not None:
        terminal_run = True
    contract_blob_names = (
        "session-meta.json",
        "stage-index.json",
        "transition-index.json",
        "cohesion-report.json",
    )
    missing_contract_blobs = [
        name for name in contract_blob_names if _try_blob(f"{job_id}/{name}") is None
    ]
    if terminal_run and missing_contract_blobs:
        try:
            emit_contract_artifacts(job_id)
            logger.info(
                "[%s] session-snapshot regenerated missing contract blobs: %s",
                job_id,
                ",".join(missing_contract_blobs),
            )
        except Exception as exc:
            logger.warning(
                "[%s] session-snapshot contract artifact regeneration failed: %s",
                job_id,
                exc,
            )

    snapshot_profile = str(profile or "full").strip().lower()
    if snapshot_profile not in {"full", "compact"}:
        snapshot_profile = "full"
    compact = snapshot_profile == "compact"

    zbuf = io.BytesIO()
    with _zf.ZipFile(zbuf, "w", _zf.ZIP_DEFLATED) as zf:

        # ── stage-00-setup ────────────────────────────────────────────────────
        _zwrite(zf, "stage-00-setup/explore_config.json",
                f"{job_id}/explore_config.json")
        _zwrite(zf, "stage-00-setup/static_analysis.json",
                f"{job_id}/static_analysis.json")
        _zwrite(zf, "stage-00-setup/sentinel_calibration.json",
                f"{job_id}/sentinel_calibration.json")
        _zwrite(zf, "stage-00-setup/s01-handoff-packet.json",
                f"{job_id}/s01_handoff_packet.json")
        # Q16: write-unlock probe outcome (T-18 evidence)
        _zwrite(zf, "stage-00-setup/write-unlock-probe.json",
                f"{job_id}/write_unlock_probe.json")
        _zwrite(zf, "stage-00-setup/schema.json",
                f"{job_id}/mcp_schema_t0.json")

        # ── stage-01-probe-loop ───────────────────────────────────────────────
        _zwrite(zf, "stage-01-probe-loop/explore_probe_log.json",
                f"{job_id}/explore_probe_log.json")
        _zwrite(zf, "stage-01-probe-loop/schema-before.json",
                f"{job_id}/mcp_schema_t0.json")
        _zwrite(zf, "stage-01-probe-loop/schema-after.json",
                f"{job_id}/mcp_schema_post_enrichment.json")
        if not compact:
            _zwrite(zf, "stage-01-probe-loop/model_context.txt",
                    f"{job_id}/model_context_phase_01_probe_loop.txt")

        # ── stage-02-synthesis ────────────────────────────────────────────────
        _zwrite(zf, "stage-02-synthesis/findings.json",
                f"{job_id}/findings.json")
        _zwrite(zf, "stage-02-synthesis/api_reference.md",
                f"{job_id}/api_reference.md")
        _zwrite(zf, "stage-02-synthesis/schema-before.json",
                f"{job_id}/mcp_schema_post_enrichment.json")
        # Use post-discovery as the "after backfill" snapshot; fall back to
        # the live mcp_schema.json if post-discovery blob is absent.
        _schema_after_backfill = (
            _try_blob(f"{job_id}/mcp_schema_post_discovery.json")
            or _try_blob(f"{job_id}/mcp_schema.json")
        )
        if _schema_after_backfill:
            zf.writestr("stage-02-synthesis/schema-after.json", _schema_after_backfill)
        if not compact:
            _zwrite(zf, "stage-02-synthesis/model_context.txt",
                    f"{job_id}/model_context_phase_06_synthesis.txt")

        # ── stage-03-gap-resolution ───────────────────────────────────────────
        _zwrite(zf, "stage-03-gap-resolution/gap_resolution_log.json",
                f"{job_id}/gap_resolution_log.json")
        _zwrite(zf, "stage-03-gap-resolution/schema-before.json",
                f"{job_id}/mcp_schema_pre_gap_resolution.json")
        _zwrite(zf, "stage-03-gap-resolution/schema-after.json",
                f"{job_id}/mcp_schema_post_gap_resolution.json")
        if not compact:
            _zwrite(zf, "stage-03-gap-resolution/model_context.txt",
                    f"{job_id}/model_context_phase_08_gap_resolution.txt")
            _zwrite(zf, "stage-03-gap-resolution/mini_session_transcript.txt",
                    f"{job_id}/mini_session_transcript.txt")
        _zwrite(zf, "stage-03-gap-resolution/mini-schema-before.json",
                f"{job_id}/mcp_schema_pre_mini_session.json")
        _zwrite(zf, "stage-03-gap-resolution/mini-schema-after.json",
                f"{job_id}/mcp_schema_post_mini_session.json")

        # ── stage-04-clarification ────────────────────────────────────────────
        _zwrite(zf, "stage-04-clarification/schema-before.json",
                f"{job_id}/mcp_schema_pre_clarification.json")
        _zwrite(zf, "stage-04-clarification/schema-after.json",
                f"{job_id}/mcp_schema_post_clarification.json")

        # Build clarification-questions.md from explore_questions in job status
        gaps = status.get("explore_questions") or []
        if gaps:
            _vocab_for_gaps: dict = {}
            try:
                _vocab_for_gaps = json.loads(
                    _download_blob(ARTIFACT_CONTAINER, f"{job_id}/vocab.json")
                )
            except Exception:
                pass
            _gap_answers = _vocab_for_gaps.get("gap_answers") or {}
            lines = ["# Clarification Questions from Discovery\n"]
            for i, g in enumerate(gaps, 1):
                q = g.get("question") or g.get("uncertainty") or ""
                td = g.get("technical_detail") or ""
                fn = g.get("function") or "general"
                lines.append(f"## {i}. {fn}\n**Question:** {q}\n")
                if td:
                    lines.append(f"**Technical detail:** `{td}`\n")
                ans = _gap_answers.get(fn, "")
                lines.append(f"**Answer:** {ans if ans else '(unanswered)'}\n")
            zf.writestr("stage-04-clarification/clarification-questions.md",
                        "\n".join(lines))

        # ── stage-05-finalization ─────────────────────────────────────────────
        _zwrite(zf, "stage-05-finalization/findings.json",
                f"{job_id}/findings.json")
        _zwrite(zf, "stage-05-finalization/vocab.json",
                f"{job_id}/vocab.json")
        _zwrite(zf, "stage-05-finalization/behavioral_spec.py",
                f"{job_id}/behavioral_spec.py")
        _zwrite(zf, "stage-05-finalization/invocables_map.json",
                f"{job_id}/invocables_map.json")
        _zwrite(zf, "stage-05-finalization/sentinel_catalog.json",
                f"{job_id}/sentinel_catalog.json")
        _zwrite(zf, "stage-05-finalization/harmonization_report.json",
                f"{job_id}/harmonization_report.json")

        # ── micro coordinator decisions + winning init sequence ────────────
        _zwrite(zf, "mc-decisions/mc3-post-reconcile.json",
                f"{job_id}/mc-decisions/mc3-post-reconcile.json")
        _zwrite(zf, "mc-decisions/mc4-post-synthesis.json",
                f"{job_id}/mc-decisions/mc4-post-synthesis.json")
        _zwrite(zf, "mc-decisions/mc5-post-verification.json",
                f"{job_id}/mc-decisions/mc5-post-verification.json")
        _zwrite(zf, "mc-decisions/mc6-post-gap-resolution.json",
                f"{job_id}/mc-decisions/mc6-post-gap-resolution.json")
        _zwrite(zf, "mc-decisions/winning-init-sequence.json",
                f"{job_id}/winning_init_sequence.json")
        _zwrite(zf, "mc-decisions/verification-report.json",
                f"{job_id}/verification-report.json")

        # ── diagnostics ───────────────────────────────────────────────────────
        if not compact:
            _chat_data = _try_blob(f"{job_id}/chat_transcript.txt")
            zf.writestr(
                "diagnostics/chat_transcript.txt",
                _chat_data or b"(No transcript recorded yet. Start a chat session to generate one.)",
            )
            _zwrite(zf, "diagnostics/executor_trace.json",
                    f"{job_id}/executor_trace.json")
            _zwrite(zf, "diagnostics/executor-trace.json",
                    f"{job_id}/executor_trace.json")
            _zwrite(zf, "diagnostics/diagnosis_raw.json",
                    f"{job_id}/diagnosis_raw.json")
            _zwrite(zf, "diagnostics/mini_session_transcript.txt",
                    f"{job_id}/mini_session_transcript.txt")

        # Canonical diagnostics names from contract (retain legacy names above).
        if not compact:
            _zwrite(zf, "diagnostics/transcript.txt", f"{job_id}/chat_transcript.txt")
        _zwrite(zf, "diagnostics/probe-log.json", f"{job_id}/explore_probe_log.json")
        if not compact:
            _zwrite(zf, "diagnostics/chat-model-context.txt", f"{job_id}/model_context_phase_01_probe_loop.txt")
            _zwrite_first(
                zf,
                "diagnostics/chat-system-context-turn0.txt",
                [
                    f"{job_id}/chat_system_context_turn0.txt",
                    f"{job_id}/diagnostics/chat-system-context.txt",
                ],
            )

        # Model operating context (exact system message the LLM receives)
        if not compact:
            try:
                from api.services.chat import _build_system_message
                _inv_raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/invocables_map.json")
                _inv_map_data = json.loads(_inv_raw)
                _invocables = (
                    list(_inv_map_data.values()) if isinstance(_inv_map_data, dict)
                    else _inv_map_data
                )
                _sys_msg = _build_system_message(_invocables, job_id)
                _ctx_text = (
                    "# Model Operating Context\n"
                    "# This is the exact system message injected into every chat session for this job.\n"
                    "# Captured at snapshot time — regenerate after any vocab/enrichment change.\n\n"
                    + _sys_msg["content"]
                )
                zf.writestr("diagnostics/model_context.txt", _ctx_text)
            except Exception:
                pass  # non-fatal — snapshot still valid without it

        # ── Top-level files ───────────────────────────────────────────────────

        # Contract-first machine artifacts
        _zwrite(zf, "session-meta.json", f"{job_id}/session-meta.json")
        _zwrite(zf, "stage-index.json", f"{job_id}/stage-index.json")
        _zwrite(zf, "transition-index.json", f"{job_id}/transition-index.json")
        _zwrite(zf, "cohesion-report.json", f"{job_id}/cohesion-report.json")
        zf.writestr(
            "canonical-stage-model.json",
            json.dumps(_canonical_stage_model_payload(), indent=2),
        )
        zf.writestr(
            "capture-layout-stage-aliases.json",
            json.dumps(
                {
                    "legacy": LEGACY_CAPTURE_STAGE_ALIASES,
                    "future_s00_runtime_split": FUTURE_S00_CAPTURE_STAGE_ALIASES,
                    "future_s02_runtime_split": FUTURE_S02_CAPTURE_STAGE_ALIASES,
                },
                indent=2,
            ),
        )
        zf.writestr("README-STAGES.md", _stage_surface_readme())

        # hints.txt — strip DOMAIN ANSWER entries (those are gap answers, not user hints)
        _raw_hints_txt = status.get("hints", "") or ""
        _clean_hints_txt = " | ".join(
            p.strip() for p in _raw_hints_txt.split(" | ")
            if p.strip() and not p.strip().startswith("DOMAIN ANSWER")
        )
        hints_lines = []
        if _clean_hints_txt:
            hints_lines.append("# User Hints\n")
            hints_lines.append(_clean_hints_txt)
        if status.get("use_cases"):
            hints_lines.append("\n\n# Use Cases\n")
            hints_lines.append(status["use_cases"])
        zf.writestr("hints.txt", "\n".join(hints_lines) if hints_lines else "(none)")

        # session-meta.json fallback (for runs that do not emit contract artifact yet)
        # D-7: gap_count reflects unresolved functions (error status), not
        # clarification question count, for an accurate "still-broken" signal.
        _raw_hints = status.get("hints", "") or ""
        _clean_hints = " | ".join(
            p.strip() for p in _raw_hints.split(" | ")
            if p.strip() and not p.strip().startswith("DOMAIN ANSWER")
        )
        _all_findings_for_meta = _load_findings(job_id)
        _fn_latest: dict[str, str] = {}
        for _f in _all_findings_for_meta:
            _fn_name = _f.get("function")
            if _fn_name:
                _fn_latest[_fn_name] = _f.get("status", "error")
        _unresolved_count = sum(1 for _s in _fn_latest.values() if _s != "success")
        meta = {
            "job_id":         job_id,
            "component":      status.get("component_name", "unknown"),
            "dll_path":       status.get("target_path") or status.get("file_path"),
            "dll_sha256":     status.get("dll_sha256"),
            "analysis_entrypoint": status.get("analysis_entrypoint"),
            "binary_origin":  status.get("binary_origin"),
            "explore_phase":  status.get("explore_phase"),
            "hints":          _clean_hints,
            "use_cases":      status.get("use_cases", ""),
            "created_at":     status.get("created_at"),
            "updated_at":     status.get("updated_at"),
            "gap_count":      _unresolved_count,
            "finding_count":  len(_all_findings_for_meta),
            "question_count": len(gaps),
            "functions_total": len(_fn_latest),
            "functions_success": sum(1 for s in _fn_latest.values() if s == "success"),
            "functions_error": _unresolved_count,
            "write_unlock_outcome": status.get("write_unlock_outcome"),
            "write_unlock_sentinel": status.get("write_unlock_sentinel"),
            "write_unlock_resolved_at": status.get("write_unlock_resolved_at"),
            "sentinel_new_codes_this_run": status.get("sentinel_new_codes_this_run", 0),
            "prior_job_id": status.get("explore_runtime", {}).get("prior_job_id"),
            "prior_findings_seeded": status.get("prior_findings_seeded", 0),
            "verification_verified": status.get("verification_verified", 0),
            "verification_inferred": status.get("verification_inferred", 0),
            "verification_error": status.get("verification_error", 0),
            "prompt_profile_id": status.get("prompt_profile_id"),
            "layer": status.get("layer"),
            "ablation_variable": status.get("ablation_variable"),
            "ablation_value": status.get("ablation_value"),
            "run_set_id": status.get("run_set_id"),
            "coordinator_cycle": status.get("coordinator_cycle"),
            "playbook_step": status.get("playbook_step"),
            "checkpoint_id": (status.get("explore_runtime") or {}).get("checkpoint_id"),
            "focus_functions": (status.get("explore_runtime") or {}).get("focus_functions"),
            "skip_to_stage": (status.get("explore_runtime") or {}).get("skip_to_stage"),
            "analysis_profile": (status.get("explore_runtime") or {}).get("analysis_profile"),
            "snapshot_profile": snapshot_profile,
            "parallel_runs": (status.get("explore_runtime") or {}).get("parallel_runs", 1),
            "variant_configs_count": len((status.get("explore_runtime") or {}).get("variant_configs") or []),
            "lane_id": (status.get("explore_runtime") or {}).get("lane_id"),
            "variant_id": (status.get("explore_runtime") or {}).get("variant_id"),
            "cross_dll_prior_job_ids": (status.get("explore_runtime") or {}).get("cross_dll_prior_job_ids") or [],
            "graph_epoch": (status.get("explore_runtime") or {}).get("graph_epoch") or "none",
        }
        if not _try_blob(f"{job_id}/session-meta.json"):
            zf.writestr("session-meta.json", json.dumps(meta, indent=2))

        # Canonical evidence paths from contract layout (retain legacy stage-* paths above).
        _zwrite(zf, "evidence/stage-00-setup/schema-t0.json", f"{job_id}/mcp_schema_t0.json")
        _zwrite(zf, "evidence/stage-00-setup/invocables-map.json", f"{job_id}/invocables_map.json")
        _zwrite(zf, "evidence/stage-00-setup/stage-checks.json", f"{job_id}/explore_config.json")
        _zwrite(zf, "evidence/stage-00-setup/s01-handoff-packet.json", f"{job_id}/s01_handoff_packet.json")
        _zwrite(zf, "evidence/stage-00a-setup-baseline/sentinel-calibration.json", f"{job_id}/sentinel_calibration.json")
        _zwrite(zf, "evidence/stage-00a-setup-baseline/vocab.json", f"{job_id}/vocab.json")
        _zwrite(zf, "evidence/stage-00b-static-evidence/static-analysis.json", f"{job_id}/static_analysis.json")
        _zwrite(zf, "evidence/stage-00b-static-evidence/static-enrichment.json", f"{job_id}/static_enrichment.json")
        _zwrite(zf, "evidence/stage-00b-static-evidence/call-graph.json", f"{job_id}/call_graph.json")
        _zwrite(zf, "evidence/stage-00b-static-evidence/ghidra-data-types.json", f"{job_id}/ghidra_data_types.json")
        _zwrite(zf, "evidence/stage-00c-admission-handoff/s01-handoff-packet.json", f"{job_id}/s01_handoff_packet.json")

        # hints.txt is assembled from status fields, not stored as a blob.
        # Reuse the same content written at the top-level hints.txt path.
        _hints_content = "\n".join(hints_lines) if hints_lines else "(none)"
        zf.writestr("evidence/stage-01-pre-probe/hints.txt", _hints_content)
        _zwrite(zf, "evidence/stage-01-pre-probe/vocab.json", f"{job_id}/vocab.json")
        _zwrite(zf, "evidence/stage-01-pre-probe/static-analysis.json", f"{job_id}/static_analysis.json")
        _zwrite(zf, "evidence/stage-01-pre-probe/sentinel-calibration.json", f"{job_id}/sentinel_calibration.json")
        _zwrite(zf, "evidence/stage-01-pre-probe/write-unlock-probe.json", f"{job_id}/write_unlock_probe.json")

        _zwrite(zf, "evidence/stage-02-probe-loop/probe-log.json", f"{job_id}/explore_probe_log.json")
        _zwrite(zf, "evidence/stage-02-probe-loop/findings.json", f"{job_id}/findings.json")
        _zwrite(
            zf,
            "evidence/stage-02a-probe-ordering/prerequisite-state-machine.json",
            f"{job_id}/prerequisite_state_machine.json",
        )
        _zwrite(
            zf,
            "evidence/stage-02c-evidence-capture/probe-log.json",
            f"{job_id}/explore_probe_log.json",
        )
        _zwrite(
            zf,
            "evidence/stage-02c-evidence-capture/findings.json",
            f"{job_id}/findings.json",
        )
        if not compact:
            _zwrite(
                zf,
                "evidence/stage-02b-invocation-execution/stage-context.txt",
                f"{job_id}/model_context_phase_01_probe_loop.txt",
            )
            _zwrite(
                zf,
                "evidence/stage-02b-invocation-execution/probe-user-message-sample.txt",
                f"{job_id}/probe_user_message_sample.txt",
            )
            _zwrite(zf, "evidence/stage-02-probe-loop/stage-context.txt", f"{job_id}/model_context_phase_01_probe_loop.txt")
            _zwrite(zf, "evidence/stage-02-probe-loop/probe-user-message-sample.txt", f"{job_id}/probe_user_message_sample.txt")

        _zwrite(zf, "evidence/stage-03-post-probe/sentinel-catalog.json", f"{job_id}/sentinel_catalog.json")
        _zwrite(zf, "evidence/stage-03-post-probe/harmonization-report.json", f"{job_id}/harmonization_report.json")

        _zwrite(zf, "evidence/stage-04-synthesis/api-reference.md", f"{job_id}/api_reference.md")
        if not compact:
            _zwrite(zf, "evidence/stage-04-synthesis/stage-context.txt", f"{job_id}/model_context_phase_06_synthesis.txt")

        _zwrite(zf, "evidence/stage-05-backfill/backfill-report.json", f"{job_id}/backfill_result.json")
        _zwrite(zf, "evidence/stage-05-backfill/schema-post-backfill.json", f"{job_id}/mcp_schema_post_discovery.json")
        _zwrite(zf, "evidence/stage-05a-schema-backfill/backfill-report.json", f"{job_id}/backfill_result.json")
        _zwrite(zf, "evidence/stage-05a-schema-backfill/schema-post-backfill.json", f"{job_id}/mcp_schema_post_discovery.json")
        _zwrite(zf, "evidence/stage-05b-verification-replay/verification-report.json", f"{job_id}/verification-report.json")
        _zwrite(zf, "evidence/stage-05c-read-to-write-chaining/mc5-post-verification.json",
                f"{job_id}/mc-decisions/mc5-post-verification.json")

        _zwrite(zf, "evidence/stage-06-gap-resolution/gap-resolution-log.json", f"{job_id}/gap_resolution_log.json")
        if not compact:
            _zwrite(zf, "evidence/stage-06-gap-resolution/mini-session-transcript.txt", f"{job_id}/mini_session_transcript.txt")
        _zwrite(zf, "evidence/stage-06-gap-resolution/schema-pre-mini-session.json", f"{job_id}/mcp_schema_pre_mini_session.json")
        _zwrite(zf, "evidence/stage-06-gap-resolution/schema-post-mini-session.json", f"{job_id}/mcp_schema_post_mini_session.json")

        _zwrite(zf, "evidence/stage-07-finalize/behavioral-spec.py", f"{job_id}/behavioral_spec.py")
        _zwrite(zf, "evidence/stage-07-finalize/final-vocab.json", f"{job_id}/vocab.json")
        _zwrite(zf, "evidence/stage-07-finalize/final-status.json", f"{job_id}/status.json")
        _zwrite(zf, "evidence/stage-07-finalize/schema-evolution.json", f"{job_id}/schema_evolution.json")
        _zwrite(zf, "evidence/stage-07-finalize/schema-final.json", f"{job_id}/mcp_schema.json")

        # MC coordinator decisions and verification evidence
        _zwrite(zf, "evidence/mc-decisions/mc3-post-reconcile.json",
                f"{job_id}/mc-decisions/mc3-post-reconcile.json")
        _zwrite(zf, "evidence/mc-decisions/mc4-post-synthesis.json",
                f"{job_id}/mc-decisions/mc4-post-synthesis.json")
        _zwrite(zf, "evidence/mc-decisions/mc5-post-verification.json",
                f"{job_id}/mc-decisions/mc5-post-verification.json")
        _zwrite(zf, "evidence/mc-decisions/mc6-post-gap-resolution.json",
                f"{job_id}/mc-decisions/mc6-post-gap-resolution.json")
        _zwrite(zf, "evidence/mc-decisions/winning-init-sequence.json",
                f"{job_id}/winning_init_sequence.json")
        _zwrite(zf, "evidence/mc-decisions/verification-report.json",
                f"{job_id}/verification-report.json")

        # ── Reasoning artifacts (probe loop decision trail) ───────────────
        _zwrite(zf, "evidence/stage-00-calibrate/sentinel-calibration-decisions.json",
                f"{job_id}/evidence/stage-00-calibrate/sentinel-calibration-decisions.json")
        _zwrite(zf, "evidence/stage-01-pre-probe/probe-vocab-snapshot.json",
                f"{job_id}/evidence/stage-01-pre-probe/probe-vocab-snapshot.json")
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02-probe-loop/param-rename-decisions.json",
            f"{job_id}/evidence/stage-02-probe-loop/param-rename-decisions.json",
            [],
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02c-evidence-capture/param-rename-decisions.json",
            f"{job_id}/evidence/stage-02-probe-loop/param-rename-decisions.json",
            [],
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02-probe-loop/probe-round-reasoning.json",
            f"{job_id}/evidence/stage-02-probe-loop/probe-round-reasoning.json",
            [],
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02c-evidence-capture/probe-round-reasoning.json",
            f"{job_id}/evidence/stage-02-probe-loop/probe-round-reasoning.json",
            [],
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02-probe-loop/probe-stop-reasons.json",
            f"{job_id}/evidence/stage-02-probe-loop/probe-stop-reasons.json",
            [],
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02c-evidence-capture/probe-stop-reasons.json",
            f"{job_id}/evidence/stage-02-probe-loop/probe-stop-reasons.json",
            [],
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02-probe-loop/probe-strategy-summary.json",
            f"{job_id}/evidence/stage-02-probe-loop/probe-strategy-summary.json",
            [],
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-02c-evidence-capture/probe-strategy-summary.json",
            f"{job_id}/evidence/stage-02-probe-loop/probe-strategy-summary.json",
            [],
        )
        _zwrite(zf, "evidence/stage-02-probe-loop/probe-user-message-sample.txt",
                f"{job_id}/probe_user_message_sample.txt")

        # ── Synthesis reasoning ───────────────────────────────────────────
        _zwrite_json_or_default(
            zf,
            "evidence/stage-04-synthesis/synthesis-input-snapshot.json",
            f"{job_id}/evidence/stage-04-synthesis/synthesis-input-snapshot.json",
            {},
        )
        _zwrite_json_or_default(
            zf,
            "evidence/stage-04-synthesis/synthesis-coverage-check.json",
            f"{job_id}/evidence/stage-04-synthesis/synthesis-coverage-check.json",
            {},
        )

        # ── Backfill reasoning ────────────────────────────────────────────
        _zwrite(zf, "evidence/stage-06-backfill/backfill-decision-log.json",
                f"{job_id}/evidence/stage-06-backfill/backfill-decision-log.json")

        # ── Gap resolution reasoning ──────────────────────────────────────
        _zwrite(zf, "evidence/stage-05-gap-resolution/expert-answer-interpretation.json",
                f"{job_id}/evidence/stage-05-gap-resolution/expert-answer-interpretation.json")
        _zwrite(zf, "evidence/stage-05-gap-resolution/mini-session-reasoning.json",
                f"{job_id}/evidence/stage-05-gap-resolution/mini-session-reasoning.json")

        # Snapshot profile marker so the collector knows which evidence to enforce
        zf.writestr("snapshot-profile.json", json.dumps({"profile": snapshot_profile}))

        # ── Checkpoints (pipeline resumability data) ──────────────────────
        _zwrite(zf, "checkpoints/latest.json",
                f"{job_id}/checkpoints/latest.json")
        _zwrite(zf, "checkpoints/s00_setup.json",
                f"{job_id}/checkpoints/s00_setup.json")
        _zwrite(zf, "checkpoints/s01_unlock.json",
                f"{job_id}/checkpoints/s01_unlock.json")
        _zwrite(zf, "checkpoints/s02_probe.json",
                f"{job_id}/checkpoints/s02_probe.json")
        _zwrite(zf, "checkpoints/s03_reconcile.json",
                f"{job_id}/checkpoints/s03_reconcile.json")
        _zwrite(zf, "checkpoints/s04_synthesis.json",
                f"{job_id}/checkpoints/s04_synthesis.json")
        _zwrite(zf, "checkpoints/s05_enrichment.json",
                f"{job_id}/checkpoints/s05_enrichment.json")
        _zwrite(zf, "checkpoints/s05_schema_backfill.json",
                f"{job_id}/checkpoints/s05_schema_backfill.json")
        _zwrite(zf, "checkpoints/s05_verification_replay.json",
                f"{job_id}/checkpoints/s05_verification_replay.json")
        _zwrite(zf, "checkpoints/s05_read_to_write_chaining.json",
                f"{job_id}/checkpoints/s05_read_to_write_chaining.json")
        _zwrite(zf, "checkpoints/s06_gaps.json",
                f"{job_id}/checkpoints/s06_gaps.json")
        _zwrite(zf, "checkpoints/s07_finalize.json",
                f"{job_id}/checkpoints/s07_finalize.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s00_setup.json",
                f"{job_id}/checkpoints/stage_snapshots/s00_setup.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s01_unlock.json",
                f"{job_id}/checkpoints/stage_snapshots/s01_unlock.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s02_probe.json",
                f"{job_id}/checkpoints/stage_snapshots/s02_probe.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s03_reconcile.json",
                f"{job_id}/checkpoints/stage_snapshots/s03_reconcile.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s04_synthesis.json",
                f"{job_id}/checkpoints/stage_snapshots/s04_synthesis.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s05_enrichment.json",
                f"{job_id}/checkpoints/stage_snapshots/s05_enrichment.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s05_schema_backfill.json",
                f"{job_id}/checkpoints/stage_snapshots/s05_schema_backfill.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s05_verification_replay.json",
                f"{job_id}/checkpoints/stage_snapshots/s05_verification_replay.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s05_read_to_write_chaining.json",
                f"{job_id}/checkpoints/stage_snapshots/s05_read_to_write_chaining.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s06_gaps.json",
                f"{job_id}/checkpoints/stage_snapshots/s06_gaps.json")
        _zwrite(zf, "checkpoints/stage_snapshots/s07_finalize.json",
                f"{job_id}/checkpoints/stage_snapshots/s07_finalize.json")

        # ── Forward-gap KPI telemetry artifacts (optional) ─────────────────
        _zwrite_job_relative(zf, "llm_usage.json")
        _zwrite_job_relative(zf, "stage_events.json")
        _zwrite_job_relative(zf, "queue_metrics.json")
        _zwrite_job_relative(zf, "variant_contributions.json")
        _zwrite(zf, "evidence/meta/llm-usage.json", f"{job_id}/llm_usage.json")
        _zwrite(zf, "evidence/meta/stage-events.json", f"{job_id}/stage_events.json")
        _zwrite(zf, "evidence/meta/queue-metrics.json", f"{job_id}/queue_metrics.json")
        _zwrite(
            zf,
            "evidence/meta/variant-contributions.json",
            f"{job_id}/variant_contributions.json",
        )

        # ── NxM stage namespace artifacts (optional) ───────────────────────
        # Include variant and merged outputs when present so save-session can
        # validate cross-variant provenance for parallel runs.
        try:
            stage_blob_names = _list_blob_names(ARTIFACT_CONTAINER, f"{job_id}/stages/")
        except Exception:
            stage_blob_names = []
        for blob_name in stage_blob_names:
            rel_name = blob_name[len(job_id) + 1 :] if blob_name.startswith(f"{job_id}/") else blob_name
            if rel_name.startswith("stages/s02_probe/variants/") or rel_name.startswith("stages/s02_probe/merged/"):
                _zwrite(zf, rel_name, blob_name)

        checkpoint_files = [
            name for name in (
                "checkpoints/latest.json",
                "checkpoints/s00_setup.json",
                "checkpoints/s01_unlock.json",
                "checkpoints/s02_probe.json",
                "checkpoints/s03_reconcile.json",
                "checkpoints/s04_synthesis.json",
                "checkpoints/s05_enrichment.json",
                "checkpoints/s06_gaps.json",
                "checkpoints/s07_finalize.json",
                "checkpoints/stage_snapshots/s00_setup.json",
                "checkpoints/stage_snapshots/s01_unlock.json",
                "checkpoints/stage_snapshots/s02_probe.json",
                "checkpoints/stage_snapshots/s03_reconcile.json",
                "checkpoints/stage_snapshots/s04_synthesis.json",
                "checkpoints/stage_snapshots/s05_enrichment.json",
                "checkpoints/stage_snapshots/s06_gaps.json",
                "checkpoints/stage_snapshots/s07_finalize.json",
            )
            if _try_blob(f"{job_id}/{name}") is not None
        ]
        zf.writestr(
            "checkpoints/manifest.json",
            json.dumps(
                {
                    "schema_version": SNAPSHOT_SCHEMA_VERSION,
                    "snapshot_kind": "job_checkpoint_set",
                    "snapshot_profile": snapshot_profile,
                    "checkpoint_files": checkpoint_files,
                },
                indent=2,
            ),
        )
        zf.writestr(
            "session-manifest.json",
            json.dumps(
                {
                    "schema_version": SNAPSHOT_SCHEMA_VERSION,
                    "snapshot_kind": "job",
                    "snapshot_profile": snapshot_profile,
                    "roots": [
                        "stage-00-setup/",
                        "stage-01-probe-loop/",
                        "stage-02-synthesis/",
                        "stage-03-gap-resolution/",
                        "stage-04-clarification/",
                        "stage-05-finalization/",
                        "README-STAGES.md",
                        "canonical-stage-model.json",
                        "capture-layout-stage-aliases.json",
                        "evidence/",
                        "mc-decisions/",
                        "diagnostics/",
                        "checkpoints/",
                    ],
                    "origin_semantics": {
                        "emitted": "artifact emitted by the pipeline or included directly from blob storage",
                        "recovered": "artifact reconstructed or defaulted during save-session assembly",
                        "synthesized_summary": "artifact assembled by the snapshot layer for readability",
                    },
                },
                indent=2,
            ),
        )

    zbuf.seek(0)
    return StreamingResponse(
        iter([zbuf.read()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="session-{job_id}.zip"'},
    )


@router.get("/api/jobs/{job_id}/report")
async def get_report(job_id: str):
    """Generate a markdown documentation report for a job.

    Combines the enriched invocables schema with LLM-recorded findings.
    Returns a markdown document as text/markdown for direct download.
    """
    # Load invocables
    inv_map = get_invocables_map(job_id)

    findings = _load_findings(job_id)
    findings_by_fn: dict[str, list] = {}
    for f in findings:
        fn = f.get("function", "unknown")
        findings_by_fn.setdefault(fn, []).append(f)

    lines: list[str] = [
        "# MCP Factory — DLL Documentation Report",
        "",
        f"**Job ID:** `{job_id}`  ",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  ",
        f"**Functions documented:** {len(inv_map)}",
        "",
        "---",
        "",
    ]

    for fn_name, inv in sorted(inv_map.items()):
        desc = inv.get("description") or inv.get("doc") or inv.get("signature") or ""
        lines.append(f"## `{fn_name}`")
        lines.append("")
        if desc:
            lines.append(desc)
            lines.append("")

        fn_findings = findings_by_fn.get(fn_name, [])
        params = inv.get("parameters") or []
        if params:
            lines.append("**Parameters:**")
            lines.append("")
            lines.append("| Name | Type | Description |")
            lines.append("|------|------|-------------|")
            for p in params:
                pname = p.get("name", "?")
                ptype = p.get("type") or p.get("json_type") or "unknown"
                pdesc = p.get("description", "")
                # Replace useless Ghidra boilerplate with a human-readable description
                if not pdesc or pdesc.startswith("Parameter recovered by Ghidra"):
                    pdesc = _infer_param_desc(pname, ptype, fn_findings)
                lines.append(f"| `{pname}` | `{ptype}` | {pdesc} |")
            lines.append("")

        ret_type = inv.get("return_type") or (inv.get("signature", {}) or {}) .get("return_type") if isinstance(inv.get("signature"), dict) else None
        if ret_type:
            lines.append(f"**Returns:** `{ret_type}`")
            lines.append("")

        if fn_findings:
            lines.append("**Findings from exploration:**")
            lines.append("")
            for f in fn_findings:
                param_part = f" (`{f['param']}`)" if f.get("param") else ""
                lines.append(f"- {param_part}{f.get('finding', '')}")
                if f.get("working_call"):
                    lines.append(f"  - Working call: `{json.dumps(f['working_call'])}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    markdown = "\n".join(lines)

    # Also persist to blob for later download
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/report.md",
            markdown.encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to persist report to blob: %s", job_id, exc)

    from fastapi.responses import Response as _Response
    return _Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="report-{job_id}.md"'},
    )

