from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from api.pipeline.core.finding_status import (
    CANONICAL_DISCOVERED_STATUSES,
    CANONICAL_VERIFIED_STATUSES,
    normalize_status,
)
from api.pipeline.core.semantic_continuation import SPECTRUM_MEDIUM01_RETRY_SCOPE_TARGETS
from api.pipeline.core.spectrum_runtime_adoption import build_branch_trust_observer_payload


REPO_ROOT = Path(__file__).resolve().parents[3]
SPECTRUM_COMPILED_SUITE_ID = "spectrum_transaction_release_settlement_suite"
SPECTRUM_COMPILED_CASE_ID = "easy-01"
SPECTRUM_COMPILED_MEDIUM01_CASE_ID = "medium-01"
SPECTRUM_COMPILED_MEDIUM02_CASE_ID = "medium-02"
SPECTRUM_COMPILED_HARD01_CASE_ID = "hard-01"
SPECTRUM_COMPILED_HARD02_CASE_ID = "hard-02"
SPECTRUM_COMPILED_HARD03_CASE_ID = "hard-03"
SPECTRUM_COMPILED_FIXTURE_ROOT = (
    REPO_ROOT / "tests" / "fixtures" / "spectrum_transaction_release_settlement_suite"
)
SPECTRUM_COMPILED_PACKAGE_MANIFEST = SPECTRUM_COMPILED_FIXTURE_ROOT / "package_manifest.json"
SPECTRUM_COMPILED_TRUTH_MANIFEST = SPECTRUM_COMPILED_FIXTURE_ROOT / "truth_manifest.json"
SPECTRUM_AUTHORED_TRUTH_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "truth_manifest.json"
)
SPECTRUM_AUTHORED_EASY_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "cases"
    / "easy-01-manifest.json"
)
SPECTRUM_AUTHORED_MEDIUM01_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "cases"
    / "medium-01-manifest.json"
)
SPECTRUM_AUTHORED_MEDIUM02_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "cases"
    / "medium-02-manifest.json"
)
SPECTRUM_AUTHORED_HARD01_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "cases"
    / "hard-01-manifest.json"
)
SPECTRUM_AUTHORED_HARD02_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "cases"
    / "hard-02-manifest.json"
)
SPECTRUM_AUTHORED_HARD03_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "engineScaling"
    / "engineScaling_SpectrumDesignSuite"
    / "SpectrumDesignSuite_Source"
    / "transaction_release_settlement_suite"
    / "cases"
    / "hard-03-manifest.json"
)

SPECTRUM_COMPILED_EASY01_CHAIN_PLAN: tuple[dict[str, Any], ...] = (
    {
        "target_name": "session_bootstrap",
        "staged_name": "spectrum_session_bootstrap.dll",
        "module_name": "session_bootstrap",
        "required_semantic_checkpoint": "SP_OpenOperatorSession",
        "predecessor_targets": [],
    },
    {
        "target_name": "reservation_stage",
        "staged_name": "spectrum_reservation_stage.dll",
        "module_name": "reservation_stage",
        "required_semantic_checkpoint": "SP_IssueReleaseHold",
        "predecessor_targets": ["session_bootstrap"],
    },
    {
        "target_name": "release_commit",
        "staged_name": "spectrum_release_commit.dll",
        "module_name": "release_commit",
        "required_semantic_checkpoint": "SP_CommitRelease",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
    },
    {
        "target_name": "audit_trace",
        "staged_name": "spectrum_audit_trace.dll",
        "module_name": "audit_trace",
        "required_semantic_checkpoint": "SP_RecordReleaseReceipt",
        "predecessor_targets": ["session_bootstrap", "reservation_stage", "release_commit"],
    },
)

SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN: tuple[dict[str, Any], ...] = (
    {
        "target_name": "session_bootstrap",
        "staged_name": "spectrum_session_bootstrap.dll",
        "module_name": "session_bootstrap",
        "required_semantic_checkpoint": "SP_OpenOperatorSession",
        "predecessor_targets": [],
    },
    {
        "target_name": "reservation_stage",
        "staged_name": "spectrum_reservation_stage.dll",
        "module_name": "reservation_stage",
        "required_semantic_checkpoint": "SP_IssueReleaseHold",
        "predecessor_targets": ["session_bootstrap"],
    },
    {
        "target_name": "dispatch_preview",
        "staged_name": "spectrum_dispatch_preview.dll",
        "module_name": "dispatch_preview",
        "required_semantic_checkpoint": "SP_PrepareReleasePreview",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
    },
    {
        "target_name": "fee_quote",
        "staged_name": "spectrum_fee_quote.dll",
        "module_name": "fee_quote",
        "required_semantic_checkpoint": "SP_StageReleaseFeeQuote",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
    },
    {
        "target_name": "settlement_reconcile",
        "staged_name": "spectrum_settlement_reconcile.dll",
        "module_name": "settlement_reconcile",
        "required_semantic_checkpoint": "SP_VerifyReservedRelease",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "dispatch_preview",
            "fee_quote",
        ],
    },
)

SPECTRUM_COMPILED_MEDIUM02_CHAIN_PLAN: tuple[dict[str, Any], ...] = (
    {
        "target_name": "session_bootstrap",
        "staged_name": "spectrum_session_bootstrap.dll",
        "module_name": "session_bootstrap",
        "required_semantic_checkpoint": "SP_OpenOperatorSession",
        "predecessor_targets": [],
    },
    {
        "target_name": "reservation_stage",
        "staged_name": "spectrum_reservation_stage.dll",
        "module_name": "reservation_stage",
        "required_semantic_checkpoint": "SP_IssueReleaseHold",
        "predecessor_targets": ["session_bootstrap"],
    },
    {
        "target_name": "dispatch_preview",
        "staged_name": "spectrum_dispatch_preview.dll",
        "module_name": "dispatch_preview",
        "required_semantic_checkpoint": "SP_PrepareReleasePreview",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
        "support_only": True,
    },
    {
        "target_name": "fee_quote",
        "staged_name": "spectrum_fee_quote.dll",
        "module_name": "fee_quote",
        "required_semantic_checkpoint": "SP_StageReleaseFeeQuote",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
        "support_only": True,
    },
    {
        "target_name": "attestation_stage",
        "staged_name": "spectrum_attestation_stage.dll",
        "module_name": "attestation_stage",
        "required_semantic_checkpoint": "SP_EmitReleaseAttestation",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "dispatch_preview",
            "fee_quote",
        ],
    },
    {
        "target_name": "invoice_sync",
        "staged_name": "spectrum_invoice_sync.dll",
        "module_name": "invoice_sync",
        "required_semantic_checkpoint": "SP_StageReleaseInvoice",
        "predecessor_targets": ["session_bootstrap", "reservation_stage", "attestation_stage"],
    },
    {
        "target_name": "entitlement_sync",
        "staged_name": "spectrum_entitlement_sync.dll",
        "module_name": "entitlement_sync",
        "required_semantic_checkpoint": "SP_StageCustomerEntitlementUpdate",
        "predecessor_targets": ["session_bootstrap", "reservation_stage", "attestation_stage"],
    },
    {
        "target_name": "settlement_reconcile",
        "staged_name": "spectrum_settlement_reconcile.dll",
        "module_name": "settlement_reconcile",
        "required_semantic_checkpoint": "SP_ConfirmAttestedRelease",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "invoice_sync",
            "entitlement_sync",
        ],
    },
)

SPECTRUM_COMPILED_HARD01_CHAIN_PLAN: tuple[dict[str, Any], ...] = (
    {
        "target_name": "session_bootstrap",
        "staged_name": "spectrum_session_bootstrap.dll",
        "module_name": "session_bootstrap",
        "required_semantic_checkpoint": "SP_OpenOperatorSession",
        "predecessor_targets": [],
    },
    {
        "target_name": "reservation_stage",
        "staged_name": "spectrum_reservation_stage.dll",
        "module_name": "reservation_stage",
        "required_semantic_checkpoint": "SP_IssueReleaseHold",
        "predecessor_targets": ["session_bootstrap"],
    },
    {
        "target_name": "dispatch_preview",
        "staged_name": "spectrum_dispatch_preview.dll",
        "module_name": "dispatch_preview",
        "required_semantic_checkpoint": "SP_PrepareReleasePreview",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
        "support_only": True,
    },
    {
        "target_name": "fee_quote",
        "staged_name": "spectrum_fee_quote.dll",
        "module_name": "fee_quote",
        "required_semantic_checkpoint": "SP_StageReleaseFeeQuote",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
        "support_only": True,
    },
    {
        "target_name": "attestation_stage",
        "staged_name": "spectrum_attestation_stage.dll",
        "module_name": "attestation_stage",
        "required_semantic_checkpoint": "SP_EmitReleaseAttestation",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "dispatch_preview",
            "fee_quote",
        ],
    },
    {
        "target_name": "release_commit",
        "staged_name": "spectrum_release_commit.dll",
        "module_name": "release_commit",
        "required_semantic_checkpoint": "SP_CommitRelease",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
    },
    {
        "target_name": "replay_branch",
        "staged_name": "spectrum_replay_branch.dll",
        "module_name": "replay_branch",
        "required_semantic_checkpoint": "SP_ReplayReleaseBranch",
        "predecessor_targets": ["session_bootstrap", "reservation_stage", "release_commit"],
    },
    {
        "target_name": "settlement_reconcile",
        "staged_name": "spectrum_settlement_reconcile.dll",
        "module_name": "settlement_reconcile",
        "required_semantic_checkpoint": "SP_SelectTrustedBranch",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "release_commit",
            "replay_branch",
        ],
    },
    {
        "target_name": "audit_trace",
        "staged_name": "spectrum_audit_trace.dll",
        "module_name": "audit_trace",
        "required_semantic_checkpoint": "SP_InvalidateUntrustedBranch",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "release_commit",
            "replay_branch",
            "settlement_reconcile",
        ],
    },
)

SPECTRUM_COMPILED_HARD02_CHAIN_PLAN: tuple[dict[str, Any], ...] = (
    {
        "target_name": "session_bootstrap",
        "staged_name": "spectrum_session_bootstrap.dll",
        "module_name": "session_bootstrap",
        "required_semantic_checkpoint": "SP_OpenOperatorSession",
        "predecessor_targets": [],
    },
    {
        "target_name": "reservation_stage",
        "staged_name": "spectrum_reservation_stage.dll",
        "module_name": "reservation_stage",
        "required_semantic_checkpoint": "SP_IssueReleaseHold",
        "predecessor_targets": ["session_bootstrap"],
    },
    {
        "target_name": "dispatch_preview",
        "staged_name": "spectrum_dispatch_preview.dll",
        "module_name": "dispatch_preview",
        "required_semantic_checkpoint": "SP_PrepareReleasePreview",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
        "support_only": True,
    },
    {
        "target_name": "fee_quote",
        "staged_name": "spectrum_fee_quote.dll",
        "module_name": "fee_quote",
        "required_semantic_checkpoint": "SP_StageReleaseFeeQuote",
        "predecessor_targets": ["session_bootstrap", "reservation_stage"],
        "support_only": True,
    },
    {
        "target_name": "attestation_stage",
        "staged_name": "spectrum_attestation_stage.dll",
        "module_name": "attestation_stage",
        "required_semantic_checkpoint": "SP_EmitReleaseAttestation",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "dispatch_preview",
            "fee_quote",
        ],
    },
    {
        "target_name": "invoice_sync",
        "staged_name": "spectrum_invoice_sync.dll",
        "module_name": "invoice_sync",
        "required_semantic_checkpoint": "SP_StageReleaseInvoice",
        "predecessor_targets": ["session_bootstrap", "reservation_stage", "attestation_stage"],
    },
    {
        "target_name": "entitlement_sync",
        "staged_name": "spectrum_entitlement_sync.dll",
        "module_name": "entitlement_sync",
        "required_semantic_checkpoint": "SP_StageCustomerEntitlementUpdate",
        "predecessor_targets": ["session_bootstrap", "reservation_stage", "attestation_stage"],
    },
    {
        "target_name": "settlement_reconcile",
        "staged_name": "spectrum_settlement_reconcile.dll",
        "module_name": "settlement_reconcile",
        "required_semantic_checkpoint": "SP_InvalidateStaleAttestedRelease",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "invoice_sync",
            "entitlement_sync",
        ],
    },
    {
        "target_name": "audit_trace",
        "staged_name": "spectrum_audit_trace.dll",
        "module_name": "audit_trace",
        "required_semantic_checkpoint": "SP_RecordStaleAttestationInvalidation",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "invoice_sync",
            "entitlement_sync",
            "settlement_reconcile",
        ],
    },
)

SPECTRUM_COMPILED_HARD03_CHAIN_PLAN: tuple[dict[str, Any], ...] = (
    *SPECTRUM_COMPILED_HARD02_CHAIN_PLAN,
    {
        "target_name": "quarantine_gate",
        "staged_name": "spectrum_quarantine_gate.dll",
        "module_name": "quarantine_gate",
        "required_semantic_checkpoint": "SP_QuarantineUnsupportedTarget",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "audit_trace",
        ],
    },
    {
        "target_name": "quarantine_audit",
        "staged_name": "spectrum_quarantine_audit.dll",
        "module_name": "quarantine_audit",
        "required_semantic_checkpoint": "SP_RecordUnsupportedTargetQuarantine",
        "predecessor_targets": [
            "session_bootstrap",
            "reservation_stage",
            "audit_trace",
            "quarantine_gate",
        ],
    },
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compiled_spectrum_fixture_root() -> Path:
    return SPECTRUM_COMPILED_FIXTURE_ROOT


def load_spectrum_compiled_package_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_COMPILED_PACKAGE_MANIFEST)


def load_spectrum_compiled_truth_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_COMPILED_TRUTH_MANIFEST)


def load_spectrum_authored_truth_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_AUTHORED_TRUTH_MANIFEST)


def load_spectrum_authored_easy_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_AUTHORED_EASY_MANIFEST)


def load_spectrum_authored_medium01_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_AUTHORED_MEDIUM01_MANIFEST)


def load_spectrum_authored_medium02_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_AUTHORED_MEDIUM02_MANIFEST)


def load_spectrum_authored_hard01_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_AUTHORED_HARD01_MANIFEST)


def load_spectrum_authored_hard02_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_AUTHORED_HARD02_MANIFEST)


def load_spectrum_authored_hard03_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_AUTHORED_HARD03_MANIFEST)


def _resolve_repo_path(relative_path: str) -> Path:
    return (REPO_ROOT / str(relative_path or "").strip()).resolve()


def _selected_targets_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in list(manifest.get("selected_runtime_targets") or [])]


def _bundled_targets_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in list(manifest.get("bundled_dlls") or [])]


def _resolve_targets_for_chain(
    manifest: dict[str, Any],
    chain_plan: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    selected_by_target = {
        str(item.get("target_name") or "").strip(): dict(item)
        for item in _selected_targets_from_manifest(manifest)
        if str(item.get("target_name") or "").strip()
    }
    bundled_by_name = {
        str(item.get("staged_name") or "").strip(): dict(item)
        for item in _bundled_targets_from_manifest(manifest)
        if str(item.get("staged_name") or "").strip()
    }
    ordered: list[dict[str, Any]] = []
    for chain_step in chain_plan:
        target_name = str(chain_step["target_name"])
        merged = dict(chain_step)
        if target_name in selected_by_target:
            merged.update(selected_by_target[target_name])
        else:
            staged_name = str(chain_step["staged_name"])
            if staged_name not in bundled_by_name:
                raise ValueError(f"missing compiled runtime target: {target_name}")
            merged.update(bundled_by_name[staged_name])
            merged.setdefault("target_name", target_name)
        ordered.append(merged)
    return ordered


def ordered_spectrum_compiled_easy01_targets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return _resolve_targets_for_chain(manifest, SPECTRUM_COMPILED_EASY01_CHAIN_PLAN)


def ordered_spectrum_compiled_medium01_targets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return _resolve_targets_for_chain(manifest, SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN)


def ordered_spectrum_compiled_medium02_targets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return _resolve_targets_for_chain(manifest, SPECTRUM_COMPILED_MEDIUM02_CHAIN_PLAN)


def ordered_spectrum_compiled_hard01_targets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return _resolve_targets_for_chain(manifest, SPECTRUM_COMPILED_HARD01_CHAIN_PLAN)


def ordered_spectrum_compiled_hard02_targets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return _resolve_targets_for_chain(manifest, SPECTRUM_COMPILED_HARD02_CHAIN_PLAN)


def ordered_spectrum_compiled_hard03_targets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return _resolve_targets_for_chain(manifest, SPECTRUM_COMPILED_HARD03_CHAIN_PLAN)


def ensure_spectrum_compiled_package_built() -> dict[str, Any]:
    manifest = load_spectrum_compiled_package_manifest()
    bundled = _bundled_targets_from_manifest(manifest)
    if bundled and all(_resolve_repo_path(item["source_path"]).exists() for item in bundled):
        return manifest

    build_script = compiled_spectrum_fixture_root() / "build-package.ps1"
    subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(build_script)],
        cwd=str(REPO_ROOT),
        check=True,
    )
    return load_spectrum_compiled_package_manifest()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_findings(run_dir: Path) -> list[dict[str, Any]]:
    payload = _read_json(run_dir / "findings.json", [])
    return list(payload or []) if isinstance(payload, list) else []


def _read_verification_entries(run_dir: Path) -> list[dict[str, Any]]:
    payload = _read_json(run_dir / "session" / "verification-report.json", {})
    entries = payload.get("entries") if isinstance(payload, dict) else []
    return list(entries or []) if isinstance(entries, list) else []


def _pick_finding(findings: list[dict[str, Any]], function_name: str) -> dict[str, Any]:
    first_match: dict[str, Any] = {}
    for row in findings:
        if str(row.get("function") or "").strip() == function_name:
            candidate = dict(row)
            if not first_match:
                first_match = candidate
            direct_target_truth = dict(candidate.get("direct_target_truth") or {})
            if candidate.get("working_call") or direct_target_truth.get("working_call"):
                return candidate
    return first_match


def _pick_verification_entry(entries: list[dict[str, Any]], function_name: str) -> dict[str, Any]:
    for row in entries:
        if str(row.get("function") or "").strip() == function_name:
            return dict(row)
    return {}


def _normalize_branch_candidate(branch_id: Any, candidate_branch_ids: list[str]) -> str:
    raw = str(branch_id or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    for candidate in candidate_branch_ids:
        canonical = str(candidate or "").strip().lower()
        if not canonical:
            continue
        if lowered == canonical or lowered.endswith(f"-{canonical}") or lowered.endswith(f"_{canonical}"):
            return candidate
    return raw


def _extract_verification_branch_ids(entry: dict[str, Any], candidate_branch_ids: list[str]) -> dict[str, str]:
    result_text = str(entry.get("result") or "")
    trusted_match = re.search(r"out_trusted_branch_id='([^']+)'", result_text)
    rejected_match = re.search(r"out_rejected_branch_id='([^']+)'", result_text)
    trusted_branch_id = _normalize_branch_candidate(
        trusted_match.group(1) if trusted_match else "",
        candidate_branch_ids,
    )
    rejected_branch_id = _normalize_branch_candidate(
        rejected_match.group(1) if rejected_match else "",
        candidate_branch_ids,
    )
    return {
        "trusted_branch_id": trusted_branch_id,
        "rejected_branch_id": rejected_branch_id,
    }


def _extract_audit_token(value: Any) -> str:
    return str(value or "").strip()


def _branch_invalidation_authority_from_records(
    *,
    trusted_branch_id: str,
    rejected_branch_ids: list[str],
    candidate_branch_ids: list[str],
    audit_row: dict[str, Any],
    audit_finding: dict[str, Any],
    late_invalidation_refs: list[str],
) -> dict[str, Any]:
    rejected_branch_id = str(rejected_branch_ids[0] if rejected_branch_ids else "").strip()
    audit_working_call = dict(audit_finding.get("working_call") or {})
    audit_trusted_branch_id = _normalize_branch_candidate(
        audit_working_call.get("trusted_branch_id"),
        candidate_branch_ids,
    )
    audit_rejected_branch_id = _normalize_branch_candidate(
        audit_working_call.get("rejected_branch_id"),
        candidate_branch_ids,
    )
    audit_token = _extract_audit_token(audit_working_call.get("out_audit_token"))
    audit_status = normalize_status(audit_finding.get("status_canonical") or audit_finding.get("status"))
    latest_status_map = dict(audit_row.get("latest_status_map") or {})
    latest_audit_status = normalize_status(latest_status_map.get("SP_InvalidateUntrustedBranch"))

    checks = {
        "branch_ids_present": bool(trusted_branch_id and rejected_branch_id),
        "branch_ids_canonical": trusted_branch_id in candidate_branch_ids and rejected_branch_id in candidate_branch_ids,
        "trusted_rejected_distinct": bool(trusted_branch_id and rejected_branch_id and trusted_branch_id != rejected_branch_id),
        "audit_call_present": bool(audit_working_call),
        "audit_call_uses_selected_pair": bool(
            audit_trusted_branch_id
            and audit_rejected_branch_id
            and audit_trusted_branch_id == trusted_branch_id
            and audit_rejected_branch_id == rejected_branch_id
        ),
        "audit_token_present": bool(audit_token),
        "audit_token_tied_to_rejected_branch": bool(audit_token and rejected_branch_id and rejected_branch_id in audit_token.lower()),
        "audit_status_verified_success": audit_status == "verified_success" and latest_audit_status == "verified_success",
    }
    reason_code = ""
    if not checks["branch_ids_present"]:
        reason_code = "branch_selection_authority_missing"
    elif not checks["branch_ids_canonical"]:
        reason_code = "branch_selection_not_canonical"
    elif not checks["trusted_rejected_distinct"]:
        reason_code = "branch_selection_trusted_equals_rejected"
    elif not checks["audit_call_present"]:
        reason_code = "branch_invalidation_call_missing"
    elif not checks["audit_call_uses_selected_pair"]:
        reason_code = "branch_invalidation_call_mismatch"
    elif not checks["audit_token_present"]:
        reason_code = "branch_invalidation_token_missing"
    elif not checks["audit_token_tied_to_rejected_branch"]:
        reason_code = "branch_invalidation_token_not_tied_to_rejected"
    elif not checks["audit_status_verified_success"]:
        reason_code = "branch_invalidation_not_verified"

    authority_present = all(checks.values())
    return {
        "schema_version": "1.0.0",
        "authority_name": "enterprise_branch_invalidation_authority",
        "authority_present": authority_present,
        "safe_to_compare": authority_present,
        "semantic_proof_satisfied": authority_present,
        "blocking_signal": "" if authority_present else "branch_invalidation_authority_missing",
        "reason_code": "branch_invalidation_authority_present" if authority_present else reason_code,
        "trusted_branch_id": trusted_branch_id,
        "rejected_branch_id": rejected_branch_id,
        "audit_trusted_branch_id": audit_trusted_branch_id,
        "audit_rejected_branch_id": audit_rejected_branch_id,
        "audit_status": audit_status,
        "latest_audit_status": latest_audit_status,
        "audit_token_present": bool(audit_token),
        "evidence_refs": late_invalidation_refs,
        "checks": checks,
    }


def _branch_trust_observer_from_hard01_run_records(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_branch_ids = ["primary", "replay"]
    report_rows = {str(row.get("dll_name") or "").strip(): dict(row) for row in run_records}
    replay_row = report_rows.get("spectrum_replay_branch.dll", {})
    settlement_row = report_rows.get("spectrum_settlement_reconcile.dll", {})
    audit_row = report_rows.get("spectrum_audit_trace.dll", {})

    settlement_findings = _read_findings(Path(str(settlement_row.get("run_dir") or ""))) if settlement_row else []
    settlement_verification_entries = (
        _read_verification_entries(Path(str(settlement_row.get("run_dir") or ""))) if settlement_row else []
    )
    settlement_finding = _pick_finding(settlement_findings, "SP_SelectTrustedBranch")
    settlement_verification = _pick_verification_entry(settlement_verification_entries, "SP_SelectTrustedBranch")
    working_call = dict(settlement_finding.get("working_call") or {})
    verified_branch_ids = _extract_verification_branch_ids(settlement_verification, candidate_branch_ids)

    semantic_selection_complete = _is_verified_semantic_checkpoint(settlement_row, "SP_SelectTrustedBranch")
    replay_semantics_complete = _is_verified_semantic_checkpoint(replay_row, "SP_ReplayReleaseBranch")
    trusted_branch_id = str(verified_branch_ids.get("trusted_branch_id") or "").strip()
    rejected_branch_id = str(verified_branch_ids.get("rejected_branch_id") or "").strip()
    if not trusted_branch_id:
        trusted_branch_id = _normalize_branch_candidate(working_call.get("out_trusted_branch_id"), candidate_branch_ids)
    if not rejected_branch_id:
        rejected_branch_id = _normalize_branch_candidate(working_call.get("out_rejected_branch_id"), candidate_branch_ids)
    if not trusted_branch_id and semantic_selection_complete:
        trusted_branch_id = "primary"
    if not rejected_branch_id and semantic_selection_complete:
        rejected_branch_id = "replay"

    rejected_branch_ids = [rejected_branch_id] if rejected_branch_id else []
    evidence_refs: list[str] = []
    if replay_row:
        evidence_refs.append(f"{Path(str(replay_row.get('run_dir') or '')).as_posix()}/findings.json")
    if settlement_row:
        evidence_refs.append(f"{Path(str(settlement_row.get('run_dir') or '')).as_posix()}/session/verification-report.json")
        evidence_refs.append(f"{Path(str(settlement_row.get('run_dir') or '')).as_posix()}/findings.json")
    late_invalidation_refs: list[str] = []
    audit_finding: dict[str, Any] = {}
    if audit_row:
        audit_run_dir = Path(str(audit_row.get("run_dir") or ""))
        late_invalidation_refs.append(f"{audit_run_dir.as_posix()}/findings.json")
        audit_finding = _pick_finding(_read_findings(audit_run_dir), "SP_InvalidateUntrustedBranch")

    branch_ids_are_canonical = (
        not trusted_branch_id or trusted_branch_id in candidate_branch_ids
    ) and all(branch_id in candidate_branch_ids for branch_id in rejected_branch_ids)
    branch_invalidation_authority = _branch_invalidation_authority_from_records(
        trusted_branch_id=trusted_branch_id,
        rejected_branch_ids=rejected_branch_ids,
        candidate_branch_ids=candidate_branch_ids,
        audit_row=audit_row,
        audit_finding=audit_finding,
        late_invalidation_refs=late_invalidation_refs,
    )

    observer_status = "warn"
    confidence = "low"
    decision_reason = "late branch-trust decision is not yet explicit enough to trust globally"
    if semantic_selection_complete:
        confidence = "medium"
        decision_reason = "settlement reconciliation emitted a branch-selection surface, but replay and invalidation evidence are not yet fully coherent"
    if semantic_selection_complete and not branch_ids_are_canonical:
        decision_reason = "branch selection emitted noncanonical branch identifiers, so trust still depends on inferred provenance"
    elif semantic_selection_complete and not replay_semantics_complete:
        decision_reason = "settlement reconciliation selected a trusted branch before replay provenance was semantically resolved"
    elif semantic_selection_complete and replay_semantics_complete and not branch_invalidation_authority["authority_present"]:
        decision_reason = "replay provenance exists, but late invalidation evidence is missing or invalid"
    elif semantic_selection_complete and replay_semantics_complete and branch_invalidation_authority["authority_present"]:
        observer_status = "pass"
        confidence = "high"
        decision_reason = "branch trust, replay provenance, and late invalidation evidence are coherent"

    payload = build_branch_trust_observer_payload(
        candidate_branch_ids=candidate_branch_ids,
        trusted_branch_id=trusted_branch_id,
        rejected_branch_ids=rejected_branch_ids,
        provenance_inputs={
            "primary_commit_receipt": str(working_call.get("primary_commit_receipt") or "").strip(),
            "replay_commit_receipt": str(working_call.get("replay_commit_receipt") or "").strip(),
        },
        decision_reason=decision_reason,
        evidence_refs=evidence_refs,
        late_invalidation_refs=late_invalidation_refs,
        observer_status=observer_status,
        confidence=confidence,
    )
    payload["branch_invalidation_authority"] = branch_invalidation_authority
    return payload


def _is_success_like_status(status: Any) -> bool:
    return normalize_status(status) in CANONICAL_DISCOVERED_STATUSES


def _is_trustworthy_terminal_run(record: dict[str, Any]) -> bool:
    control_plane = dict(record.get("measurement_control_plane") or {})
    if control_plane and not bool(control_plane.get("safe_to_compare")):
        return False

    valid_run = record.get("valid_run")
    if valid_run is not None and not bool(valid_run):
        return False

    phase = str(record.get("phase") or "").strip().lower()
    if phase and phase != "done":
        return False

    verdict = record.get("verdict")
    verdict_status = str(((verdict or {}).get("status") if isinstance(verdict, dict) else "") or "").strip().lower()
    if verdict_status and verdict_status != "done":
        return False

    job_status_snapshot = record.get("job_status_snapshot")
    job_status = str(
        ((job_status_snapshot or {}).get("status") if isinstance(job_status_snapshot, dict) else "") or ""
    ).strip().lower()
    if job_status and job_status != "done":
        return False

    return True


def _is_verified_semantic_checkpoint(record: dict[str, Any], function_name: str) -> bool:
    latest_status_map = dict(record.get("latest_status_map") or {})
    return _is_trustworthy_terminal_run(record) and normalize_status(
        latest_status_map.get(function_name)
    ) in CANONICAL_VERIFIED_STATUSES


def _record_safe_to_compare(record: dict[str, Any]) -> bool:
    measurement_terminalization = dict(record.get("measurement_terminalization") or {})
    if measurement_terminalization:
        return bool(measurement_terminalization.get("safe_to_compare"))
    control_plane = dict(record.get("measurement_control_plane") or {})
    if control_plane and not bool(control_plane.get("safe_to_compare")):
        return False
    return bool(
        ((record.get("run_authority") or {}).get("safe_to_steer_next_prompt") if isinstance(record.get("run_authority"), dict) else False)
    )


def build_spectrum_compiled_easy01_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    compiled_truth_manifest: dict[str, Any],
    authored_truth_manifest: dict[str, Any],
    authored_easy_manifest: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_active_modules = list(authored_easy_manifest.get("active_modules") or [])
    expected_flow = list(authored_easy_manifest.get("execution_flow") or [])
    compiled_targets = ordered_spectrum_compiled_easy01_targets(package_manifest)
    compiled_target_names = [str(item.get("staged_name") or "").strip() for item in compiled_targets]

    expected_exports = {
        str(item.get("dll_name") or "").strip(): list(item.get("exports") or [])
        for item in list(compiled_truth_manifest.get("dlls") or [])
    }

    per_run: list[dict[str, Any]] = []
    discovered_flow_steps: list[str] = []
    semantic_flow_steps: list[str] = []
    static_artifact_ok = True
    for record in run_records:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
        session_meta = _read_json(run_dir / "session" / "session-meta.json", {})
        stage_index = _read_json(run_dir / "session" / "stage-index.json", {})
        invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
        invocable_names = sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))
        dll_name = str(record.get("dll_name") or "").strip()
        expected_for_dll = expected_exports.get(dll_name, [])
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_match = all(name in invocable_names for name in expected_for_dll)
        semantic_checkpoint_match = all(_is_success_like_status(latest_status_map.get(name)) for name in expected_for_dll)

        if not invocables:
            static_artifact_ok = False
        if not session_meta or not stage_index:
            static_artifact_ok = False

        for function_name in expected_for_dll:
            if function_name in invocable_names and function_name not in discovered_flow_steps:
                discovered_flow_steps.append(function_name)
            if _is_success_like_status(latest_status_map.get(function_name)) and function_name not in semantic_flow_steps:
                semantic_flow_steps.append(function_name)

        per_run.append(
            {
                "dll_name": dll_name,
                "job_id": record.get("job_id"),
                "entry_surface": "upload",
                "binary_hash": record.get("binary_hash"),
                "expected_exports": expected_for_dll,
                "discovered_invocables": invocable_names,
                "export_contract_match": export_match,
                "semantic_checkpoint_statuses": {
                    name: str(latest_status_map.get(name) or "") for name in expected_for_dll
                },
                "semantic_checkpoint_match": semantic_checkpoint_match,
                "run_valid": bool(record.get("valid_run", True)),
                "run_phase": str(record.get("phase") or ""),
                "macro_verdict_status": str(((record.get("verdict") or {}).get("status") if isinstance(record.get("verdict"), dict) else "") or ""),
                "job_status": str(((record.get("job_status_snapshot") or {}).get("status") if isinstance(record.get("job_status_snapshot"), dict) else "") or ""),
                "session_artifacts_present": bool(session_meta) and bool(stage_index),
            }
        )

    expected_symbol_flow = [
        str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_EASY01_CHAIN_PLAN
    ]
    missing_flow = [name for name in expected_symbol_flow if name not in discovered_flow_steps]
    semantic_checkpoint_gap = [name for name in expected_symbol_flow if name not in semantic_flow_steps]
    compiled_ingest_success = static_artifact_ok and not missing_flow and all(
        item["export_contract_match"] for item in per_run
    )
    semantic_checkpoint_alignment_succeeded = not semantic_checkpoint_gap

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_CASE_ID,
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "compiled_fixture_root": str(compiled_spectrum_fixture_root()),
        "compiled_targets": compiled_target_names,
        "expected_active_modules": expected_active_modules,
        "expected_execution_flow": expected_flow,
        "expected_symbol_flow": expected_symbol_flow,
        "discovered_symbol_flow": discovered_flow_steps,
        "semantic_symbol_flow": semantic_flow_steps,
        "binary_ingest_proof_succeeded": compiled_ingest_success,
        "binary_embodiment_gap": [] if compiled_ingest_success else missing_flow or ["artifact_or_export_gap"],
        "semantic_checkpoint_alignment_succeeded": semantic_checkpoint_alignment_succeeded,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "per_run": per_run,
        "comparison_note": (
            "compiled binary ingest proof succeeded and easy-01 semantic checkpoints aligned"
            if compiled_ingest_success and semantic_checkpoint_alignment_succeeded
            else (
                "compiled binary ingest proof succeeded, but semantic checkpoint alignment remains incomplete"
                if compiled_ingest_success
                else "compiled binary embodiment diverged from authored semantics"
            )
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "authored_truth_manifest": str(SPECTRUM_AUTHORED_TRUTH_MANIFEST),
        "compiled_truth_manifest": str(SPECTRUM_COMPILED_TRUTH_MANIFEST),
        "package_manifest": str(SPECTRUM_COMPILED_PACKAGE_MANIFEST),
        "product_validity": "compiled_local_binary",
        "northstar_classification": "architecture-proof",
        "spectrum_source_classification": "architecture-proof",
        "spectrum_compiled_classification": "product-valid",
        "authored_suite_id": str(authored_truth_manifest.get("suite_id") or ""),
    }


def build_spectrum_compiled_medium01_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    compiled_truth_manifest: dict[str, Any],
    authored_truth_manifest: dict[str, Any],
    authored_medium_manifest: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_active_modules = list(authored_medium_manifest.get("active_modules") or [])
    expected_flow = list(authored_medium_manifest.get("execution_flow") or [])
    compiled_targets = ordered_spectrum_compiled_medium01_targets(package_manifest)
    compiled_target_names = [str(item.get("staged_name") or "").strip() for item in compiled_targets]

    chain_by_dll = {
        str(item["staged_name"]): dict(item) for item in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    }
    truth_by_dll = {
        str(item.get("dll_name") or "").strip(): dict(item)
        for item in list(compiled_truth_manifest.get("dlls") or [])
    }

    per_run: list[dict[str, Any]] = []
    discovered_flow_steps: list[str] = []
    semantic_flow_steps: list[str] = []
    static_artifact_ok = True
    for record in run_records:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
        session_meta = _read_json(run_dir / "session" / "session-meta.json", {})
        stage_index = _read_json(run_dir / "session" / "stage-index.json", {})
        invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
        invocable_names = sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))
        dll_name = str(record.get("dll_name") or "").strip()
        expected_step = chain_by_dll.get(dll_name, {})
        expected_for_dll = [str(expected_step.get("required_semantic_checkpoint") or "").strip()]
        expected_for_dll = [name for name in expected_for_dll if name]
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_match = all(name in invocable_names for name in expected_for_dll)
        semantic_checkpoint_match = all(_is_success_like_status(latest_status_map.get(name)) for name in expected_for_dll)

        if not invocables:
            static_artifact_ok = False
        if not session_meta or not stage_index:
            static_artifact_ok = False

        for function_name in expected_for_dll:
            if function_name in invocable_names and function_name not in discovered_flow_steps:
                discovered_flow_steps.append(function_name)
            if _is_success_like_status(latest_status_map.get(function_name)) and function_name not in semantic_flow_steps:
                semantic_flow_steps.append(function_name)

        additional_discovered = [
            name
            for name in invocable_names
            if name not in expected_for_dll and name in list(truth_by_dll.get(dll_name, {}).get("exports") or [])
        ]

        measurement_terminalization = dict(record.get("measurement_terminalization") or {})
        measurement_control_plane = dict(record.get("measurement_control_plane") or {})
        safe_to_compare = _record_safe_to_compare(record)
        per_run.append(
            {
                "dll_name": dll_name,
                "job_id": record.get("job_id"),
                "entry_surface": "upload",
                "binary_hash": record.get("binary_hash"),
                "expected_exports": expected_for_dll,
                "discovered_invocables": invocable_names,
                "additional_discovered_invocables": additional_discovered,
                "export_contract_match": export_match,
                "semantic_checkpoint_statuses": {
                    name: str(latest_status_map.get(name) or "") for name in expected_for_dll
                },
                "semantic_checkpoint_match": semantic_checkpoint_match,
                "run_valid": bool(record.get("valid_run", True)),
                "run_phase": str(record.get("phase") or ""),
                "macro_verdict_status": str(((record.get("verdict") or {}).get("status") if isinstance(record.get("verdict"), dict) else "") or ""),
                "job_status": str(((record.get("job_status_snapshot") or {}).get("status") if isinstance(record.get("job_status_snapshot"), dict) else "") or ""),
                "session_artifacts_present": bool(session_meta) and bool(stage_index),
            }
        )

    expected_symbol_flow = [
        str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    ]
    missing_flow = [name for name in expected_symbol_flow if name not in discovered_flow_steps]
    semantic_checkpoint_gap = [name for name in expected_symbol_flow if name not in semantic_flow_steps]
    compiled_ingest_success = static_artifact_ok and not missing_flow and all(
        item["export_contract_match"] for item in per_run
    )
    semantic_checkpoint_alignment_succeeded = not semantic_checkpoint_gap

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "compiled_fixture_root": str(compiled_spectrum_fixture_root()),
        "compiled_targets": compiled_target_names,
        "expected_active_modules": expected_active_modules,
        "expected_execution_flow": expected_flow,
        "expected_symbol_flow": expected_symbol_flow,
        "discovered_symbol_flow": discovered_flow_steps,
        "semantic_symbol_flow": semantic_flow_steps,
        "binary_ingest_proof_succeeded": compiled_ingest_success,
        "binary_embodiment_gap": [] if compiled_ingest_success else missing_flow or ["artifact_or_export_gap"],
        "semantic_checkpoint_alignment_succeeded": semantic_checkpoint_alignment_succeeded,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "per_run": per_run,
        "comparison_note": (
            "compiled binary ingest proof succeeded and medium-01 semantic checkpoints aligned"
            if compiled_ingest_success and semantic_checkpoint_alignment_succeeded
            else (
                "compiled binary ingest proof succeeded, but medium-01 semantic checkpoint alignment remains incomplete"
                if compiled_ingest_success
                else "compiled binary embodiment diverged from authored medium-01 semantics"
            )
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "authored_truth_manifest": str(SPECTRUM_AUTHORED_TRUTH_MANIFEST),
        "compiled_truth_manifest": str(SPECTRUM_COMPILED_TRUTH_MANIFEST),
        "package_manifest": str(SPECTRUM_COMPILED_PACKAGE_MANIFEST),
        "product_validity": "compiled_local_binary",
        "northstar_classification": "architecture-proof",
        "spectrum_source_classification": "architecture-proof",
        "spectrum_compiled_classification": "product-valid",
        "authored_suite_id": str(authored_truth_manifest.get("suite_id") or ""),
    }


def build_spectrum_compiled_medium02_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    compiled_truth_manifest: dict[str, Any],
    authored_truth_manifest: dict[str, Any],
    authored_medium_manifest: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_active_modules = list(authored_medium_manifest.get("active_modules") or [])
    expected_flow = list(authored_medium_manifest.get("execution_flow") or [])
    compiled_targets = ordered_spectrum_compiled_medium02_targets(package_manifest)
    compiled_target_names = [str(item.get("staged_name") or "").strip() for item in compiled_targets]
    support_target_names = [
        str(item.get("target_name") or "").strip()
        for item in compiled_targets
        if bool(item.get("support_only"))
    ]

    chain_by_dll = {
        str(item["staged_name"]): dict(item) for item in SPECTRUM_COMPILED_MEDIUM02_CHAIN_PLAN
    }
    truth_by_dll = {
        str(item.get("dll_name") or "").strip(): dict(item)
        for item in list(compiled_truth_manifest.get("dlls") or [])
    }

    per_run: list[dict[str, Any]] = []
    discovered_flow_steps: list[str] = []
    semantic_flow_steps: list[str] = []
    support_discovered_flow_steps: list[str] = []
    support_semantic_flow_steps: list[str] = []
    static_artifact_ok = True
    for record in run_records:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
        session_meta = _read_json(run_dir / "session" / "session-meta.json", {})
        stage_index = _read_json(run_dir / "session" / "stage-index.json", {})
        invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
        invocable_names = sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))
        dll_name = str(record.get("dll_name") or "").strip()
        expected_step = chain_by_dll.get(dll_name, {})
        support_only = bool(expected_step.get("support_only"))
        expected_for_dll = [str(expected_step.get("required_semantic_checkpoint") or "").strip()]
        expected_for_dll = [name for name in expected_for_dll if name]
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_match = all(name in invocable_names for name in expected_for_dll)
        semantic_checkpoint_match = all(_is_success_like_status(latest_status_map.get(name)) for name in expected_for_dll)

        if not invocables:
            static_artifact_ok = False
        if not session_meta or not stage_index:
            static_artifact_ok = False

        for function_name in expected_for_dll:
            discovered_target = support_discovered_flow_steps if support_only else discovered_flow_steps
            semantic_target = support_semantic_flow_steps if support_only else semantic_flow_steps
            if function_name in invocable_names and function_name not in discovered_target:
                discovered_target.append(function_name)
            if _is_success_like_status(latest_status_map.get(function_name)) and function_name not in semantic_target:
                semantic_target.append(function_name)

        additional_discovered = [
            name
            for name in invocable_names
            if name not in expected_for_dll and name in list(truth_by_dll.get(dll_name, {}).get("exports") or [])
        ]

        measurement_terminalization = dict(record.get("measurement_terminalization") or {})
        measurement_control_plane = dict(record.get("measurement_control_plane") or {})
        safe_to_compare = _record_safe_to_compare(record)
        per_run.append(
            {
                "dll_name": dll_name,
                "job_id": record.get("job_id"),
                "entry_surface": "upload",
                "binary_hash": record.get("binary_hash"),
                "expected_exports": expected_for_dll,
                "discovered_invocables": invocable_names,
                "additional_discovered_invocables": additional_discovered,
                "export_contract_match": export_match,
                "semantic_checkpoint_statuses": {
                    name: str(latest_status_map.get(name) or "") for name in expected_for_dll
                },
                "semantic_checkpoint_match": semantic_checkpoint_match,
                "run_valid": bool(record.get("valid_run", True)),
                "run_phase": str(record.get("phase") or ""),
                "macro_verdict_status": str(((record.get("verdict") or {}).get("status") if isinstance(record.get("verdict"), dict) else "") or ""),
                "job_status": str(((record.get("job_status_snapshot") or {}).get("status") if isinstance(record.get("job_status_snapshot"), dict) else "") or ""),
                "session_artifacts_present": bool(session_meta) and bool(stage_index),
                "authority_level": str(((record.get("run_authority") or {}).get("authority_level") if isinstance(record.get("run_authority"), dict) else "") or ""),
                "safe_to_steer_next_prompt": bool(((record.get("run_authority") or {}).get("safe_to_steer_next_prompt") if isinstance(record.get("run_authority"), dict) else False)),
                "safe_to_compare": bool(measurement_terminalization.get("safe_to_compare", True))
                if measurement_terminalization
                else bool(((record.get("run_authority") or {}).get("safe_to_steer_next_prompt") if isinstance(record.get("run_authority"), dict) else False)),
                "measurement_reason_code": str(measurement_terminalization.get("reason_code") or ""),
                "measurement_terminalization": measurement_terminalization,
                "failure_domain": str(record.get("failure_domain") or ""),
                "run_authority": dict(record.get("run_authority") or {}),
                "support_only": support_only,
            }
        )

    expected_symbol_flow = [
        str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_MEDIUM02_CHAIN_PLAN
        if not bool(step.get("support_only"))
    ]
    missing_flow = [name for name in expected_symbol_flow if name not in discovered_flow_steps]
    semantic_checkpoint_gap = [name for name in expected_symbol_flow if name not in semantic_flow_steps]
    compiled_ingest_success = static_artifact_ok and not missing_flow and all(
        item["export_contract_match"] for item in per_run
    )
    semantic_checkpoint_alignment_succeeded = not semantic_checkpoint_gap

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_MEDIUM02_CASE_ID,
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "compiled_fixture_root": str(compiled_spectrum_fixture_root()),
        "compiled_targets": compiled_target_names,
        "support_targets": support_target_names,
        "expected_active_modules": expected_active_modules,
        "expected_execution_flow": expected_flow,
        "expected_symbol_flow": expected_symbol_flow,
        "discovered_symbol_flow": discovered_flow_steps,
        "semantic_symbol_flow": semantic_flow_steps,
        "support_discovered_symbol_flow": support_discovered_flow_steps,
        "support_semantic_symbol_flow": support_semantic_flow_steps,
        "binary_ingest_proof_succeeded": compiled_ingest_success,
        "binary_embodiment_gap": [] if compiled_ingest_success else missing_flow or ["artifact_or_export_gap"],
        "semantic_checkpoint_alignment_succeeded": semantic_checkpoint_alignment_succeeded,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "per_run": per_run,
        "comparison_note": (
            "compiled binary ingest proof succeeded and medium-02 semantic checkpoints aligned"
            if compiled_ingest_success and semantic_checkpoint_alignment_succeeded
            else (
                "compiled binary ingest proof succeeded, but medium-02 semantic checkpoint alignment remains incomplete"
                if compiled_ingest_success
                else "compiled binary embodiment diverged from authored medium-02 semantics"
            )
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "authored_truth_manifest": str(SPECTRUM_AUTHORED_TRUTH_MANIFEST),
        "compiled_truth_manifest": str(SPECTRUM_COMPILED_TRUTH_MANIFEST),
        "package_manifest": str(SPECTRUM_COMPILED_PACKAGE_MANIFEST),
        "product_validity": "compiled_local_binary",
        "northstar_classification": "architecture-proof",
        "spectrum_source_classification": "architecture-proof",
        "spectrum_compiled_classification": "product-valid",
        "authored_suite_id": str(authored_truth_manifest.get("suite_id") or ""),
    }


def build_spectrum_compiled_hard01_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    compiled_truth_manifest: dict[str, Any],
    authored_truth_manifest: dict[str, Any],
    authored_hard_manifest: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_active_modules = list(authored_hard_manifest.get("active_modules") or [])
    expected_flow = list(authored_hard_manifest.get("execution_flow") or [])
    expected_shared_state = list(authored_hard_manifest.get("shared_state") or [])
    primary_blocker_family = str(authored_hard_manifest.get("primary_blocker_family") or "").strip()
    compiled_targets = ordered_spectrum_compiled_hard01_targets(package_manifest)
    compiled_target_names = [str(item.get("staged_name") or "").strip() for item in compiled_targets]

    chain_by_dll = {
        str(item["staged_name"]): dict(item) for item in SPECTRUM_COMPILED_HARD01_CHAIN_PLAN
    }
    truth_by_dll = {
        str(item.get("dll_name") or "").strip(): dict(item)
        for item in list(compiled_truth_manifest.get("dlls") or [])
    }

    per_run: list[dict[str, Any]] = []
    discovered_flow_steps: list[str] = []
    semantic_flow_steps: list[str] = []
    support_discovered_flow_steps: list[str] = []
    support_semantic_flow_steps: list[str] = []
    static_artifact_ok = True
    for record in run_records:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
        session_meta = _read_json(run_dir / "session" / "session-meta.json", {})
        stage_index = _read_json(run_dir / "session" / "stage-index.json", {})
        invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
        invocable_names = sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))
        dll_name = str(record.get("dll_name") or "").strip()
        expected_step = chain_by_dll.get(dll_name, {})
        support_only = bool(expected_step.get("support_only"))
        expected_for_dll = [str(expected_step.get("required_semantic_checkpoint") or "").strip()]
        expected_for_dll = [name for name in expected_for_dll if name]
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_match = all(name in invocable_names for name in expected_for_dll)
        semantic_checkpoint_match = all(
            _is_verified_semantic_checkpoint(record, name) for name in expected_for_dll
        )

        if not invocables:
            static_artifact_ok = False
        if not session_meta or not stage_index:
            static_artifact_ok = False

        for function_name in expected_for_dll:
            discovered_target = support_discovered_flow_steps if support_only else discovered_flow_steps
            semantic_target = support_semantic_flow_steps if support_only else semantic_flow_steps
            if function_name in invocable_names and function_name not in discovered_target:
                discovered_target.append(function_name)
            if _is_verified_semantic_checkpoint(record, function_name) and function_name not in semantic_target:
                semantic_target.append(function_name)

        additional_discovered = [
            name
            for name in invocable_names
            if name not in expected_for_dll and name in list(truth_by_dll.get(dll_name, {}).get("exports") or [])
        ]

        measurement_terminalization = dict(record.get("measurement_terminalization") or {})
        measurement_control_plane = dict(record.get("measurement_control_plane") or {})
        safe_to_compare = _record_safe_to_compare(record)
        per_run.append(
            {
                "dll_name": dll_name,
                "job_id": record.get("job_id"),
                "entry_surface": "upload",
                "binary_hash": record.get("binary_hash"),
                "expected_exports": expected_for_dll,
                "discovered_invocables": invocable_names,
                "additional_discovered_invocables": additional_discovered,
                "export_contract_match": export_match,
                "semantic_checkpoint_statuses": {
                    name: str(latest_status_map.get(name) or "") for name in expected_for_dll
                },
                "semantic_checkpoint_match": semantic_checkpoint_match,
                "run_valid": bool(record.get("valid_run", True)),
                "run_phase": str(record.get("phase") or ""),
                "macro_verdict_status": str(((record.get("verdict") or {}).get("status") if isinstance(record.get("verdict"), dict) else "") or ""),
                "job_status": str(((record.get("job_status_snapshot") or {}).get("status") if isinstance(record.get("job_status_snapshot"), dict) else "") or ""),
                "session_artifacts_present": bool(session_meta) and bool(stage_index),
                "authority_level": str(((record.get("run_authority") or {}).get("authority_level") if isinstance(record.get("run_authority"), dict) else "") or ""),
                "safe_to_steer_next_prompt": bool(((record.get("run_authority") or {}).get("safe_to_steer_next_prompt") if isinstance(record.get("run_authority"), dict) else False)),
                "safe_to_compare": safe_to_compare,
                "control_plane_safe_to_compare": (not measurement_control_plane)
                or bool(measurement_control_plane.get("safe_to_compare")),
                "control_plane_light": str(measurement_control_plane.get("light") or ""),
                "control_plane_reason_code": str(measurement_control_plane.get("reason_code") or ""),
                "measurement_control_plane": measurement_control_plane,
                "measurement_reason_code": str(measurement_terminalization.get("reason_code") or ""),
                "measurement_terminalization": measurement_terminalization,
                "failure_domain": str(record.get("failure_domain") or ""),
                "run_authority": dict(record.get("run_authority") or {}),
                "support_only": support_only,
            }
        )

    expected_symbol_flow = [
        str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_HARD01_CHAIN_PLAN
        if not bool(step.get("support_only"))
    ]
    missing_flow = [name for name in expected_symbol_flow if name not in discovered_flow_steps]
    semantic_checkpoint_gap = [name for name in expected_symbol_flow if name not in semantic_flow_steps]
    compiled_ingest_success = static_artifact_ok and not missing_flow and all(
        item["export_contract_match"] and item["control_plane_safe_to_compare"] for item in per_run
    )
    semantic_checkpoint_alignment_succeeded = not semantic_checkpoint_gap
    branch_trust_observer = _branch_trust_observer_from_hard01_run_records(run_records)
    branch_invalidation_authority = dict(branch_trust_observer.get("branch_invalidation_authority") or {})

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_HARD01_CASE_ID,
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "compiled_fixture_root": str(compiled_spectrum_fixture_root()),
        "compiled_targets": compiled_target_names,
        "support_targets": [
            str(item.get("target_name") or "").strip()
            for item in compiled_targets
            if bool(item.get("support_only"))
        ],
        "expected_active_modules": expected_active_modules,
        "expected_execution_flow": expected_flow,
        "expected_symbol_flow": expected_symbol_flow,
        "expected_shared_state": expected_shared_state,
        "expected_primary_blocker_family": primary_blocker_family,
        "discovered_symbol_flow": discovered_flow_steps,
        "semantic_symbol_flow": semantic_flow_steps,
        "support_discovered_symbol_flow": support_discovered_flow_steps,
        "support_semantic_symbol_flow": support_semantic_flow_steps,
        "binary_ingest_proof_succeeded": compiled_ingest_success,
        "binary_embodiment_gap": [] if compiled_ingest_success else missing_flow or ["artifact_or_export_gap"],
        "semantic_checkpoint_alignment_succeeded": semantic_checkpoint_alignment_succeeded,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "branch_trust_observer": branch_trust_observer,
        "branch_invalidation_authority": branch_invalidation_authority,
        "per_run": per_run,
        "comparison_note": (
            "compiled binary ingest proof succeeded and hard-01 semantic checkpoints aligned with explicit branch-trust provenance"
            if compiled_ingest_success
            and semantic_checkpoint_alignment_succeeded
            and str(branch_trust_observer.get("observer_status") or "").strip() == "pass"
            else (
                "compiled binary ingest proof succeeded, but hard-01 branch-trust provenance remains incomplete"
                if compiled_ingest_success
                and str(branch_trust_observer.get("observer_status") or "").strip() != "pass"
                else (
                    "compiled binary ingest proof succeeded, but hard-01 semantic checkpoint alignment remains incomplete"
                    if compiled_ingest_success
                    else "compiled binary embodiment diverged from authored hard-01 semantics"
                )
            )
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "authored_truth_manifest": str(SPECTRUM_AUTHORED_TRUTH_MANIFEST),
        "compiled_truth_manifest": str(SPECTRUM_COMPILED_TRUTH_MANIFEST),
        "package_manifest": str(SPECTRUM_COMPILED_PACKAGE_MANIFEST),
        "product_validity": "compiled_local_binary",
        "northstar_classification": "architecture-proof",
        "spectrum_source_classification": "architecture-proof",
        "spectrum_compiled_classification": "product-valid",
        "authored_suite_id": str(authored_truth_manifest.get("suite_id") or ""),
        "expected_current_failure_mode": str(authored_hard_manifest.get("expected_current_failure_mode") or ""),
        "missing_system_candidate": str(authored_hard_manifest.get("missing_system_candidate") or ""),
        "wrong_split": str(authored_hard_manifest.get("wrong_split") or ""),
        "right_split": str(authored_hard_manifest.get("right_split") or ""),
    }


def build_spectrum_compiled_hard02_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    compiled_truth_manifest: dict[str, Any],
    authored_truth_manifest: dict[str, Any],
    authored_hard_manifest: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_active_modules = list(authored_hard_manifest.get("active_modules") or [])
    expected_flow = list(authored_hard_manifest.get("execution_flow") or [])
    expected_shared_state = list(authored_hard_manifest.get("shared_state") or [])
    primary_blocker_family = str(authored_hard_manifest.get("primary_blocker_family") or "").strip()
    compiled_targets = ordered_spectrum_compiled_hard02_targets(package_manifest)
    compiled_target_names = [str(item.get("staged_name") or "").strip() for item in compiled_targets]

    chain_by_dll = {
        str(item["staged_name"]): dict(item) for item in SPECTRUM_COMPILED_HARD02_CHAIN_PLAN
    }
    truth_by_dll = {
        str(item.get("dll_name") or "").strip(): dict(item)
        for item in list(compiled_truth_manifest.get("dlls") or [])
    }

    per_run: list[dict[str, Any]] = []
    discovered_flow_steps: list[str] = []
    semantic_flow_steps: list[str] = []
    support_discovered_flow_steps: list[str] = []
    support_semantic_flow_steps: list[str] = []
    static_artifact_ok = True
    for record in run_records:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
        session_meta = _read_json(run_dir / "session" / "session-meta.json", {})
        stage_index = _read_json(run_dir / "session" / "stage-index.json", {})
        invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
        invocable_names = sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))
        dll_name = str(record.get("dll_name") or "").strip()
        expected_step = chain_by_dll.get(dll_name, {})
        support_only = bool(expected_step.get("support_only"))
        expected_for_dll = [str(expected_step.get("required_semantic_checkpoint") or "").strip()]
        expected_for_dll = [name for name in expected_for_dll if name]
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_match = all(name in invocable_names for name in expected_for_dll)
        semantic_checkpoint_match = all(
            _is_verified_semantic_checkpoint(record, name) for name in expected_for_dll
        )

        if not invocables:
            static_artifact_ok = False
        if not session_meta or not stage_index:
            static_artifact_ok = False

        for function_name in expected_for_dll:
            discovered_target = support_discovered_flow_steps if support_only else discovered_flow_steps
            semantic_target = support_semantic_flow_steps if support_only else semantic_flow_steps
            if function_name in invocable_names and function_name not in discovered_target:
                discovered_target.append(function_name)
            if _is_verified_semantic_checkpoint(record, function_name) and function_name not in semantic_target:
                semantic_target.append(function_name)

        additional_discovered = [
            name
            for name in invocable_names
            if name not in expected_for_dll and name in list(truth_by_dll.get(dll_name, {}).get("exports") or [])
        ]

        measurement_terminalization = dict(record.get("measurement_terminalization") or {})
        measurement_control_plane = dict(record.get("measurement_control_plane") or {})
        safe_to_compare = _record_safe_to_compare(record)
        per_run.append(
            {
                "dll_name": dll_name,
                "job_id": record.get("job_id"),
                "entry_surface": "upload",
                "binary_hash": record.get("binary_hash"),
                "expected_exports": expected_for_dll,
                "discovered_invocables": invocable_names,
                "additional_discovered_invocables": additional_discovered,
                "export_contract_match": export_match,
                "semantic_checkpoint_statuses": {
                    name: str(latest_status_map.get(name) or "") for name in expected_for_dll
                },
                "semantic_checkpoint_match": semantic_checkpoint_match,
                "run_valid": bool(record.get("valid_run", True)),
                "run_phase": str(record.get("phase") or ""),
                "macro_verdict_status": str(((record.get("verdict") or {}).get("status") if isinstance(record.get("verdict"), dict) else "") or ""),
                "job_status": str(((record.get("job_status_snapshot") or {}).get("status") if isinstance(record.get("job_status_snapshot"), dict) else "") or ""),
                "session_artifacts_present": bool(session_meta) and bool(stage_index),
                "authority_level": str(((record.get("run_authority") or {}).get("authority_level") if isinstance(record.get("run_authority"), dict) else "") or ""),
                "safe_to_steer_next_prompt": bool(((record.get("run_authority") or {}).get("safe_to_steer_next_prompt") if isinstance(record.get("run_authority"), dict) else False)),
                "safe_to_compare": safe_to_compare,
                "control_plane_safe_to_compare": (not measurement_control_plane)
                or bool(measurement_control_plane.get("safe_to_compare")),
                "control_plane_light": str(measurement_control_plane.get("light") or ""),
                "control_plane_reason_code": str(measurement_control_plane.get("reason_code") or ""),
                "measurement_control_plane": measurement_control_plane,
                "measurement_reason_code": str(measurement_terminalization.get("reason_code") or ""),
                "measurement_terminalization": measurement_terminalization,
                "failure_domain": str(record.get("failure_domain") or ""),
                "run_authority": dict(record.get("run_authority") or {}),
                "support_only": support_only,
            }
        )

    expected_symbol_flow = [
        str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_HARD02_CHAIN_PLAN
        if not bool(step.get("support_only"))
    ]
    missing_flow = [name for name in expected_symbol_flow if name not in discovered_flow_steps]
    semantic_checkpoint_gap = [name for name in expected_symbol_flow if name not in semantic_flow_steps]
    compiled_ingest_success = static_artifact_ok and not missing_flow and all(
        item["export_contract_match"] and item["control_plane_safe_to_compare"] for item in per_run
    )
    semantic_checkpoint_alignment_succeeded = not semantic_checkpoint_gap

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_HARD02_CASE_ID,
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "compiled_fixture_root": str(compiled_spectrum_fixture_root()),
        "compiled_targets": compiled_target_names,
        "support_targets": [
            str(item.get("target_name") or "").strip()
            for item in compiled_targets
            if bool(item.get("support_only"))
        ],
        "expected_active_modules": expected_active_modules,
        "expected_execution_flow": expected_flow,
        "expected_symbol_flow": expected_symbol_flow,
        "expected_shared_state": expected_shared_state,
        "expected_primary_blocker_family": primary_blocker_family,
        "discovered_symbol_flow": discovered_flow_steps,
        "semantic_symbol_flow": semantic_flow_steps,
        "support_discovered_symbol_flow": support_discovered_flow_steps,
        "support_semantic_symbol_flow": support_semantic_flow_steps,
        "binary_ingest_proof_succeeded": compiled_ingest_success,
        "binary_embodiment_gap": [] if compiled_ingest_success else missing_flow or ["artifact_or_export_gap"],
        "semantic_checkpoint_alignment_succeeded": semantic_checkpoint_alignment_succeeded,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "per_run": per_run,
        "comparison_note": (
            "compiled binary ingest proof succeeded and hard-02 semantic checkpoints aligned"
            if compiled_ingest_success and semantic_checkpoint_alignment_succeeded
            else (
                "compiled binary ingest proof succeeded, but hard-02 semantic checkpoint alignment remains incomplete"
                if compiled_ingest_success
                else "compiled binary embodiment diverged from authored hard-02 semantics"
            )
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "authored_truth_manifest": str(SPECTRUM_AUTHORED_TRUTH_MANIFEST),
        "compiled_truth_manifest": str(SPECTRUM_COMPILED_TRUTH_MANIFEST),
        "package_manifest": str(SPECTRUM_COMPILED_PACKAGE_MANIFEST),
        "product_validity": "compiled_local_binary",
        "northstar_classification": "architecture-proof",
        "spectrum_source_classification": "architecture-proof",
        "spectrum_compiled_classification": "product-valid",
        "authored_suite_id": str(authored_truth_manifest.get("suite_id") or ""),
        "expected_current_failure_mode": str(authored_hard_manifest.get("expected_current_failure_mode") or ""),
        "missing_system_candidate": str(authored_hard_manifest.get("missing_system_candidate") or ""),
        "wrong_split": str(authored_hard_manifest.get("wrong_split") or ""),
        "right_split": str(authored_hard_manifest.get("right_split") or ""),
    }


def build_spectrum_compiled_hard03_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    compiled_truth_manifest: dict[str, Any],
    authored_truth_manifest: dict[str, Any],
    authored_hard_manifest: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_active_modules = list(authored_hard_manifest.get("active_modules") or [])
    expected_flow = list(authored_hard_manifest.get("execution_flow") or [])
    expected_shared_state = list(authored_hard_manifest.get("shared_state") or [])
    primary_blocker_family = str(authored_hard_manifest.get("primary_blocker_family") or "").strip()
    compiled_targets = ordered_spectrum_compiled_hard03_targets(package_manifest)
    compiled_target_names = [str(item.get("staged_name") or "").strip() for item in compiled_targets]
    chain_by_dll = {
        str(item["staged_name"]): dict(item) for item in SPECTRUM_COMPILED_HARD03_CHAIN_PLAN
    }
    truth_by_dll = {
        str(item.get("dll_name") or "").strip(): dict(item)
        for item in list(compiled_truth_manifest.get("dlls") or [])
    }

    per_run: list[dict[str, Any]] = []
    discovered_flow_steps: list[str] = []
    semantic_flow_steps: list[str] = []
    support_discovered_flow_steps: list[str] = []
    support_semantic_flow_steps: list[str] = []
    static_artifact_ok = True
    for record in run_records:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
        session_meta = _read_json(run_dir / "session" / "session-meta.json", {})
        stage_index = _read_json(run_dir / "session" / "stage-index.json", {})
        invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
        invocable_names = sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))
        dll_name = str(record.get("dll_name") or "").strip()
        expected_step = chain_by_dll.get(dll_name, {})
        support_only = bool(expected_step.get("support_only"))
        expected_for_dll = [str(expected_step.get("required_semantic_checkpoint") or "").strip()]
        expected_for_dll = [name for name in expected_for_dll if name]
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_match = all(name in invocable_names for name in expected_for_dll)
        semantic_checkpoint_match = all(
            _is_verified_semantic_checkpoint(record, name) for name in expected_for_dll
        )

        if not invocables or not session_meta or not stage_index:
            static_artifact_ok = False

        for function_name in expected_for_dll:
            discovered_target = support_discovered_flow_steps if support_only else discovered_flow_steps
            semantic_target = support_semantic_flow_steps if support_only else semantic_flow_steps
            if function_name in invocable_names and function_name not in discovered_target:
                discovered_target.append(function_name)
            if _is_verified_semantic_checkpoint(record, function_name) and function_name not in semantic_target:
                semantic_target.append(function_name)

        additional_discovered = [
            name
            for name in invocable_names
            if name not in expected_for_dll and name in list(truth_by_dll.get(dll_name, {}).get("exports") or [])
        ]
        measurement_terminalization = dict(record.get("measurement_terminalization") or {})
        measurement_control_plane = dict(record.get("measurement_control_plane") or {})
        safe_to_compare = _record_safe_to_compare(record)
        per_run.append(
            {
                "dll_name": dll_name,
                "job_id": record.get("job_id"),
                "entry_surface": "upload",
                "binary_hash": record.get("binary_hash"),
                "expected_exports": expected_for_dll,
                "discovered_invocables": invocable_names,
                "additional_discovered_invocables": additional_discovered,
                "export_contract_match": export_match,
                "semantic_checkpoint_statuses": {
                    name: str(latest_status_map.get(name) or "") for name in expected_for_dll
                },
                "semantic_checkpoint_match": semantic_checkpoint_match,
                "run_valid": bool(record.get("valid_run", True)),
                "run_phase": str(record.get("phase") or ""),
                "macro_verdict_status": str(((record.get("verdict") or {}).get("status") if isinstance(record.get("verdict"), dict) else "") or ""),
                "job_status": str(((record.get("job_status_snapshot") or {}).get("status") if isinstance(record.get("job_status_snapshot"), dict) else "") or ""),
                "session_artifacts_present": bool(session_meta) and bool(stage_index),
                "authority_level": str(((record.get("run_authority") or {}).get("authority_level") if isinstance(record.get("run_authority"), dict) else "") or ""),
                "safe_to_steer_next_prompt": bool(((record.get("run_authority") or {}).get("safe_to_steer_next_prompt") if isinstance(record.get("run_authority"), dict) else False)),
                "safe_to_compare": safe_to_compare,
                "control_plane_safe_to_compare": (not measurement_control_plane)
                or bool(measurement_control_plane.get("safe_to_compare")),
                "control_plane_light": str(measurement_control_plane.get("light") or ""),
                "control_plane_reason_code": str(measurement_control_plane.get("reason_code") or ""),
                "measurement_control_plane": measurement_control_plane,
                "measurement_reason_code": str(measurement_terminalization.get("reason_code") or ""),
                "measurement_terminalization": measurement_terminalization,
                "failure_domain": str(record.get("failure_domain") or ""),
                "run_authority": dict(record.get("run_authority") or {}),
                "support_only": support_only,
            }
        )

    expected_symbol_flow = [
        str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_HARD03_CHAIN_PLAN
        if not bool(step.get("support_only"))
    ]
    missing_flow = [name for name in expected_symbol_flow if name not in discovered_flow_steps]
    semantic_checkpoint_gap = [name for name in expected_symbol_flow if name not in semantic_flow_steps]
    compiled_ingest_success = static_artifact_ok and not missing_flow and all(
        item["export_contract_match"] and item["control_plane_safe_to_compare"] for item in per_run
    )
    semantic_checkpoint_alignment_succeeded = not semantic_checkpoint_gap

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_HARD03_CASE_ID,
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "compiled_fixture_root": str(compiled_spectrum_fixture_root()),
        "compiled_targets": compiled_target_names,
        "support_targets": [
            str(item.get("target_name") or "").strip()
            for item in compiled_targets
            if bool(item.get("support_only"))
        ],
        "expected_active_modules": expected_active_modules,
        "expected_execution_flow": expected_flow,
        "expected_symbol_flow": expected_symbol_flow,
        "expected_shared_state": expected_shared_state,
        "expected_primary_blocker_family": primary_blocker_family,
        "discovered_symbol_flow": discovered_flow_steps,
        "semantic_symbol_flow": semantic_flow_steps,
        "support_discovered_symbol_flow": support_discovered_flow_steps,
        "support_semantic_symbol_flow": support_semantic_flow_steps,
        "binary_ingest_proof_succeeded": compiled_ingest_success,
        "binary_embodiment_gap": [] if compiled_ingest_success else missing_flow or ["artifact_or_export_gap"],
        "semantic_checkpoint_alignment_succeeded": semantic_checkpoint_alignment_succeeded,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "per_run": per_run,
        "comparison_note": (
            "compiled binary ingest proof succeeded and hard-03 semantic checkpoints aligned"
            if compiled_ingest_success and semantic_checkpoint_alignment_succeeded
            else (
                "compiled binary ingest proof succeeded, but hard-03 semantic checkpoint alignment remains incomplete"
                if compiled_ingest_success
                else "compiled binary embodiment diverged from authored hard-03 semantics"
            )
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "authored_truth_manifest": str(SPECTRUM_AUTHORED_TRUTH_MANIFEST),
        "compiled_truth_manifest": str(SPECTRUM_COMPILED_TRUTH_MANIFEST),
        "package_manifest": str(SPECTRUM_COMPILED_PACKAGE_MANIFEST),
        "product_validity": "compiled_local_binary",
        "northstar_classification": "architecture-proof",
        "spectrum_source_classification": "architecture-proof",
        "spectrum_compiled_classification": "product-valid",
        "authored_suite_id": str(authored_truth_manifest.get("suite_id") or ""),
        "expected_current_failure_mode": str(authored_hard_manifest.get("expected_current_failure_mode") or ""),
        "missing_system_candidate": str(authored_hard_manifest.get("missing_system_candidate") or ""),
        "wrong_split": str(authored_hard_manifest.get("wrong_split") or ""),
        "right_split": str(authored_hard_manifest.get("right_split") or ""),
    }


def build_spectrum_compiled_medium01_continuation_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    compiled_truth_manifest: dict[str, Any],
    authored_truth_manifest: dict[str, Any],
    authored_medium_manifest: dict[str, Any],
    continuation_packet: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_active_modules = list(authored_medium_manifest.get("active_modules") or [])
    expected_flow = list(authored_medium_manifest.get("execution_flow") or [])
    compiled_targets = ordered_spectrum_compiled_medium01_targets(package_manifest)
    target_by_name = {
        str(item.get("target_name") or "").strip(): str(item.get("staged_name") or "").strip()
        for item in compiled_targets
        if str(item.get("target_name") or "").strip()
    }
    retry_scope_targets = [str(item) for item in list(continuation_packet.get("retry_scope_targets") or []) if str(item).strip()]
    compiled_target_names = [target_by_name[name] for name in retry_scope_targets if name in target_by_name]

    chain_by_dll = {
        str(item["staged_name"]): dict(item) for item in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    }
    truth_by_dll = {
        str(item.get("dll_name") or "").strip(): dict(item)
        for item in list(compiled_truth_manifest.get("dlls") or [])
    }

    trusted_predecessor_targets = [str(item) for item in list(continuation_packet.get("trusted_predecessor_targets") or []) if str(item).strip()]
    trusted_predecessor_checkpoints = {
        str(step["target_name"]): str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
        if str(step["target_name"]) in trusted_predecessor_targets
    }

    per_run: list[dict[str, Any]] = []
    discovered_flow_steps: list[str] = list(dict.fromkeys(trusted_predecessor_checkpoints.values()))
    semantic_flow_steps: list[str] = [
        str(item) for item in list(continuation_packet.get("semantic_symbol_flow") or []) if str(item).strip()
    ]
    static_artifact_ok = True

    for record in run_records:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
        session_meta = _read_json(run_dir / "session" / "session-meta.json", {})
        stage_index = _read_json(run_dir / "session" / "stage-index.json", {})
        invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
        invocable_names = sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))
        dll_name = str(record.get("dll_name") or "").strip()
        expected_step = chain_by_dll.get(dll_name, {})
        expected_for_dll = [str(expected_step.get("required_semantic_checkpoint") or "").strip()]
        expected_for_dll = [name for name in expected_for_dll if name]
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_match = all(name in invocable_names for name in expected_for_dll)
        semantic_checkpoint_match = all(_is_success_like_status(latest_status_map.get(name)) for name in expected_for_dll)

        if not invocables:
            static_artifact_ok = False
        if not session_meta or not stage_index:
            static_artifact_ok = False

        for function_name in expected_for_dll:
            if function_name in invocable_names and function_name not in discovered_flow_steps:
                discovered_flow_steps.append(function_name)
            if _is_success_like_status(latest_status_map.get(function_name)) and function_name not in semantic_flow_steps:
                semantic_flow_steps.append(function_name)

        additional_discovered = [
            name
            for name in invocable_names
            if name not in expected_for_dll and name in list(truth_by_dll.get(dll_name, {}).get("exports") or [])
        ]

        per_run.append(
            {
                "dll_name": dll_name,
                "job_id": record.get("job_id"),
                "entry_surface": "upload",
                "binary_hash": record.get("binary_hash"),
                "expected_exports": expected_for_dll,
                "discovered_invocables": invocable_names,
                "additional_discovered_invocables": additional_discovered,
                "export_contract_match": export_match,
                "semantic_checkpoint_statuses": {
                    name: str(latest_status_map.get(name) or "") for name in expected_for_dll
                },
                "semantic_checkpoint_match": semantic_checkpoint_match,
                "run_valid": bool(record.get("valid_run", True)),
                "run_phase": str(record.get("phase") or ""),
                "macro_verdict_status": str(((record.get("verdict") or {}).get("status") if isinstance(record.get("verdict"), dict) else "") or ""),
                "job_status": str(((record.get("job_status_snapshot") or {}).get("status") if isinstance(record.get("job_status_snapshot"), dict) else "") or ""),
                "session_artifacts_present": bool(session_meta) and bool(stage_index),
            }
        )

    expected_symbol_flow = [
        str(step["required_semantic_checkpoint"])
        for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    ]
    missing_flow = [
        name
        for name in [
            str(step["required_semantic_checkpoint"])
            for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
            if str(step["target_name"]) in retry_scope_targets
        ]
        if name not in discovered_flow_steps
    ]
    semantic_checkpoint_gap = [name for name in expected_symbol_flow if name not in semantic_flow_steps]
    compiled_ingest_success = static_artifact_ok and not missing_flow and all(
        item["export_contract_match"] for item in per_run
    )
    semantic_checkpoint_alignment_succeeded = not semantic_checkpoint_gap

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "compiled_fixture_root": str(compiled_spectrum_fixture_root()),
        "compiled_targets": compiled_target_names,
        "trusted_predecessor_targets": trusted_predecessor_targets,
        "retry_scope_targets": retry_scope_targets,
        "expected_active_modules": expected_active_modules,
        "expected_execution_flow": expected_flow,
        "expected_symbol_flow": expected_symbol_flow,
        "discovered_symbol_flow": discovered_flow_steps,
        "semantic_symbol_flow": semantic_flow_steps,
        "binary_ingest_proof_succeeded": compiled_ingest_success,
        "binary_embodiment_gap": [] if compiled_ingest_success else missing_flow or ["artifact_or_export_gap"],
        "semantic_checkpoint_alignment_succeeded": semantic_checkpoint_alignment_succeeded,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "per_run": per_run,
        "comparison_note": (
            "compiled medium-01 continuation preserved binary ingest and narrowed the semantic gap"
            if compiled_ingest_success and len(semantic_checkpoint_gap) < len(list(continuation_packet.get("semantic_checkpoint_gap") or []))
            else (
                "compiled medium-01 continuation preserved binary ingest, but semantic checkpoint alignment remains incomplete"
                if compiled_ingest_success
                else "compiled medium-01 continuation regressed at the binary embodiment layer"
            )
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "authored_truth_manifest": str(SPECTRUM_AUTHORED_TRUTH_MANIFEST),
        "compiled_truth_manifest": str(SPECTRUM_COMPILED_TRUTH_MANIFEST),
        "package_manifest": str(SPECTRUM_COMPILED_PACKAGE_MANIFEST),
        "product_validity": "compiled_local_binary",
        "northstar_classification": "architecture-proof",
        "spectrum_source_classification": "architecture-proof",
        "spectrum_compiled_classification": "product-valid",
        "authored_suite_id": str(authored_truth_manifest.get("suite_id") or ""),
        "continuation_id": str(continuation_packet.get("continuation_id") or ""),
    }
