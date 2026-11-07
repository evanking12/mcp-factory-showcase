from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.pipeline.core.spectrum_compiled_ingest import SPECTRUM_COMPILED_HARD03_CHAIN_PLAN
from api.pipeline.core.spectrum_compiled_ingest import _branch_invalidation_authority_from_records
from api.pipeline.core.spectrum_compiled_ingest import _pick_finding
from api.pipeline.core.spectrum_compiled_ingest import build_spectrum_compiled_hard03_report
from api.pipeline.core.spectrum_compiled_ingest import ordered_spectrum_compiled_hard03_targets
from scripts.runs.run_spectrum_compiled_easy01 import (
    SPECTRUM_COMPILED_CASE_ID,
    SPECTRUM_COMPILED_SUITE_ID,
    run_spectrum_compiled_easy01,
)
from scripts.runs.run_spectrum_compiled_easy01_product import (
    SPECTRUM_COMPILED_EASY01_PRODUCT_CASE_ID,
    run_spectrum_compiled_easy01_product,
)
from scripts.runs.run_spectrum_compiled_medium01 import (
    SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
    run_spectrum_compiled_medium01,
)
from scripts.runs.run_spectrum_compiled_medium01_product import (
    SPECTRUM_COMPILED_MEDIUM01_PRODUCT_CASE_ID,
    run_spectrum_compiled_medium01_product,
)
from scripts.runs.run_spectrum_compiled_medium02 import (
    SPECTRUM_COMPILED_MEDIUM02_CASE_ID,
    run_spectrum_compiled_medium02,
)
from scripts.runs.run_spectrum_compiled_medium02_product import (
    SPECTRUM_COMPILED_MEDIUM02_PRODUCT_CASE_ID,
    run_spectrum_compiled_medium02_product,
)
from scripts.runs.run_spectrum_compiled_hard01 import (
    SPECTRUM_COMPILED_HARD01_CASE_ID,
    run_spectrum_compiled_hard01,
)
from scripts.runs.run_spectrum_compiled_hard01_product import (
    SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID,
    SPECTRUM_COMPILED_HARD01_PRODUCT_VARIANT_ID,
    run_spectrum_compiled_hard01_product,
)
from scripts.runs.run_spectrum_compiled_hard02 import (
    SPECTRUM_COMPILED_HARD02_CASE_ID,
    _promote_recovered_finalized_record,
    _recover_finalized_target_from_job_store,
    run_spectrum_compiled_hard02,
)
from scripts.runs.run_spectrum_compiled_hard03 import (
    SPECTRUM_COMPILED_HARD03_CASE_ID,
    run_spectrum_compiled_hard03,
)
from scripts.runs.run_spectrum_compiled_medium01_continuation import (
    run_spectrum_compiled_medium01_continuation,
)


@pytest.fixture(autouse=True)
def _stub_strict_local_preflight(monkeypatch) -> None:
    stub = {
        "admitted": True,
        "runtime_contract_id": "local_runtime_contract_v1",
        "api": {"admitted": True},
        "bridge": {"admitted": True},
    }
    for fn in (
        run_spectrum_compiled_medium01,
        run_spectrum_compiled_medium02,
        run_spectrum_compiled_hard01,
        run_spectrum_compiled_hard02,
        run_spectrum_compiled_hard03,
    ):
        monkeypatch.setitem(fn.__globals__, "ensure_strict_local_lane_preflight", lambda **kwargs: dict(stub))
    for fn in (
        run_spectrum_compiled_hard01,
        run_spectrum_compiled_hard02,
        run_spectrum_compiled_hard03,
    ):
        monkeypatch.setitem(fn.__globals__, "verify_api_identity_for_resolution", lambda api_url, api_key: (True, "api_ok:test"))
        monkeypatch.setitem(
            fn.__globals__,
            "fetch_api_readiness",
            lambda api_url, api_key: {"ready": True, "blocking_reasons": []},
        )
        monkeypatch.setitem(
            fn.__globals__,
            "fetch_bridge_readiness",
            lambda bridge_url, bridge_key: {"ready": True, "capabilities": ["analyze"], "blocking_reasons": []},
        )
        monkeypatch.setitem(
            fn.__globals__,
            "hard_family_bridge_stream_health_for_target",
            lambda target_name, analysis_profile: {
                "source": "test",
                "status": "coherent",
                "reason_code": "bridge_stream_health_coherent",
                "stream_health_known": True,
                "recent_signals": [],
            },
        )


def _package_manifest(tmp_path: Path) -> dict:
    fixture_bin = tmp_path / "fixture-bin"
    fixture_bin.mkdir(parents=True, exist_ok=True)
    targets = []
    for name, target_name in [
        ("spectrum_session_bootstrap.dll", "session_bootstrap"),
        ("spectrum_reservation_stage.dll", "reservation_stage"),
        ("spectrum_release_commit.dll", "release_commit"),
        ("spectrum_audit_trace.dll", "audit_trace"),
    ]:
        dll_path = fixture_bin / name
        dll_path.write_bytes(f"binary:{name}".encode("utf-8"))
        targets.append(
            {
                "staged_name": name,
                "source_path": str(dll_path),
                "target_name": target_name,
                "selection_reason": f"{target_name}_reason",
                "dependency_confidence": "high",
                "lane_id": "lane-1",
            }
        )
    return {
        "selected_runtime_targets": targets,
        "bundled_dlls": [{"staged_name": row["staged_name"], "source_path": row["source_path"]} for row in targets],
    }


def _authored_easy_manifest() -> dict:
    return {
        "case_id": "easy-01",
        "active_modules": [
            "session_bootstrap",
            "reservation_stage",
            "release_commit",
            "audit_trace",
        ],
        "execution_flow": [
            {"module": "session_bootstrap", "function": "open_operator_session"},
            {"module": "reservation_stage", "function": "issue_release_hold"},
            {"module": "release_commit", "function": "commit_release"},
            {"module": "audit_trace", "function": "record_release_receipt"},
        ],
    }


def _medium_package_manifest(tmp_path: Path) -> dict:
    fixture_bin = tmp_path / "fixture-bin-medium"
    fixture_bin.mkdir(parents=True, exist_ok=True)
    selected_targets = []
    bundled_dlls = []
    for name, target_name in [
        ("spectrum_session_bootstrap.dll", "session_bootstrap"),
        ("spectrum_reservation_stage.dll", "reservation_stage"),
        ("spectrum_dispatch_preview.dll", "dispatch_preview"),
        ("spectrum_fee_quote.dll", "fee_quote"),
        ("spectrum_settlement_reconcile.dll", "settlement_reconcile"),
    ]:
        dll_path = fixture_bin / name
        dll_path.write_bytes(f"binary:{name}".encode("utf-8"))
        row = {
            "staged_name": name,
            "source_path": str(dll_path),
            "target_name": target_name,
            "selection_reason": f"{target_name}_reason",
            "dependency_confidence": "high",
            "lane_id": "lane-1",
        }
        bundled_dlls.append({"staged_name": name, "source_path": str(dll_path)})
        if target_name in {"session_bootstrap", "reservation_stage"}:
            selected_targets.append(row)
        else:
            bundled_dlls[-1]["target_name"] = target_name
    return {
        "selected_runtime_targets": selected_targets,
        "bundled_dlls": bundled_dlls,
    }


def _authored_medium_manifest() -> dict:
    return {
        "case_id": "medium-01",
        "active_modules": [
            "session_bootstrap",
            "reservation_stage",
            "dispatch_preview",
            "fee_quote",
            "settlement_reconcile",
        ],
        "execution_flow": [
            "session_bootstrap.open_operator_session",
            "reservation_stage.issue_release_hold",
            "dispatch_preview.prepare_release_preview",
            "fee_quote.stage_release_fee_quote",
            "settlement_reconcile.verify_reserved_release",
        ],
    }


def _patch_easy01_runner_dependencies(monkeypatch, manifest: dict) -> None:
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_RecordReleaseReceipt"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_easy_manifest",
        _authored_easy_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.ApiClient", FakeClient)


def _patch_medium01_runner_dependencies(monkeypatch, manifest: dict) -> None:
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_VerifyReservedRelease"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_medium01_manifest",
        _authored_medium_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.emit_spectrum_medium01_semantic_continuation",
        lambda **kwargs: None,
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.ApiClient", FakeClient)


def _medium02_package_manifest(tmp_path: Path) -> dict:
    fixture_bin = tmp_path / "fixture-bin-medium02"
    fixture_bin.mkdir(parents=True, exist_ok=True)
    selected_targets = []
    bundled_dlls = []
    for name, target_name in [
        ("spectrum_session_bootstrap.dll", "session_bootstrap"),
        ("spectrum_reservation_stage.dll", "reservation_stage"),
        ("spectrum_dispatch_preview.dll", "dispatch_preview"),
        ("spectrum_fee_quote.dll", "fee_quote"),
        ("spectrum_attestation_stage.dll", "attestation_stage"),
        ("spectrum_invoice_sync.dll", "invoice_sync"),
        ("spectrum_entitlement_sync.dll", "entitlement_sync"),
        ("spectrum_settlement_reconcile.dll", "settlement_reconcile"),
    ]:
        dll_path = fixture_bin / name
        dll_path.write_bytes(f"binary:{name}".encode("utf-8"))
        row = {
            "staged_name": name,
            "source_path": str(dll_path),
            "target_name": target_name,
            "selection_reason": f"{target_name}_reason",
            "dependency_confidence": "high",
            "lane_id": "lane-1",
        }
        bundled_dlls.append({"staged_name": name, "source_path": str(dll_path)})
        if target_name in {"session_bootstrap", "reservation_stage"}:
            selected_targets.append(row)
        else:
            bundled_dlls[-1]["target_name"] = target_name
    return {
        "selected_runtime_targets": selected_targets,
        "bundled_dlls": bundled_dlls,
    }


def _authored_medium02_manifest() -> dict:
    return {
        "case_id": "medium-02",
        "active_modules": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "invoice_sync",
            "entitlement_sync",
            "settlement_reconcile",
        ],
        "execution_flow": [
            "session_bootstrap.open_operator_session",
            "reservation_stage.issue_release_hold",
            "attestation_stage.emit_release_attestation",
            "invoice_sync.stage_release_invoice",
            "entitlement_sync.stage_customer_entitlement_update",
            "settlement_reconcile.confirm_attested_release",
        ],
    }


def _hard01_package_manifest(tmp_path: Path) -> dict:
    fixture_bin = tmp_path / "fixture-bin-hard01"
    fixture_bin.mkdir(parents=True, exist_ok=True)
    bundled_dlls = []
    for name, target_name in [
        ("spectrum_session_bootstrap.dll", "session_bootstrap"),
        ("spectrum_reservation_stage.dll", "reservation_stage"),
        ("spectrum_dispatch_preview.dll", "dispatch_preview"),
        ("spectrum_fee_quote.dll", "fee_quote"),
        ("spectrum_attestation_stage.dll", "attestation_stage"),
        ("spectrum_release_commit.dll", "release_commit"),
        ("spectrum_replay_branch.dll", "replay_branch"),
        ("spectrum_settlement_reconcile.dll", "settlement_reconcile"),
        ("spectrum_audit_trace.dll", "audit_trace"),
    ]:
        dll_path = fixture_bin / name
        dll_path.write_bytes(f"binary:{name}".encode("utf-8"))
        bundled_dlls.append(
            {
                "staged_name": name,
                "source_path": str(dll_path),
                "target_name": target_name,
            }
        )
    return {
        "selected_runtime_targets": [
            {
                "staged_name": "spectrum_session_bootstrap.dll",
                "source_path": str(fixture_bin / "spectrum_session_bootstrap.dll"),
                "target_name": "session_bootstrap",
                "selection_reason": "session_bootstrap_reason",
                "dependency_confidence": "high",
                "lane_id": "lane-1",
            },
            {
                "staged_name": "spectrum_reservation_stage.dll",
                "source_path": str(fixture_bin / "spectrum_reservation_stage.dll"),
                "target_name": "reservation_stage",
                "selection_reason": "reservation_stage_reason",
                "dependency_confidence": "high",
                "lane_id": "lane-1",
            },
        ],
        "bundled_dlls": bundled_dlls,
    }


def _authored_hard01_manifest() -> dict:
    return {
        "case_id": "hard-01",
        "primary_blocker_family": "interwoven_lineage_ambiguity",
        "active_modules": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "release_commit",
            "replay_branch",
            "settlement_reconcile",
            "audit_trace",
        ],
        "execution_flow": [
            "session_bootstrap.open_operator_session",
            "reservation_stage.issue_release_hold",
            "attestation_stage.emit_release_attestation",
            "release_commit.commit_release",
            "replay_branch.replay_release_branch",
            "settlement_reconcile.select_trusted_branch",
            "audit_trace.invalidate_untrusted_branch",
        ],
        "shared_state": [
            "reservation_handle",
            "hold_token",
            "attestation_packet",
            "replay_attestation_packet",
        ],
        "expected_current_failure_mode": "locally plausible replay artifacts outrank late branch-truth too early",
        "missing_system_candidate": "branch-trust observer and replay provenance evidence",
        "wrong_split": "treat replay branches as independent clean lifecycle outputs",
        "right_split": "keep competing branches grouped with late branch-truth selection and audit invalidation",
    }


def test_branch_invalidation_authority_rejects_same_trusted_and_rejected_branch() -> None:
    authority = _branch_invalidation_authority_from_records(
        trusted_branch_id="primary",
        rejected_branch_ids=["primary"],
        candidate_branch_ids=["primary", "replay"],
        audit_row={"latest_status_map": {"SP_InvalidateUntrustedBranch": "verified_success"}},
        audit_finding={
            "status_canonical": "verified_success",
            "working_call": {
                "trusted_branch_id": "sp-branch-primary",
                "rejected_branch_id": "sp-branch-primary",
                "out_audit_token": "sp-audit-primary-branch-invalidated",
            },
        },
        late_invalidation_refs=["runs/09-audit_trace/findings.json"],
    )

    assert authority["authority_present"] is False
    assert authority["blocking_signal"] == "branch_invalidation_authority_missing"
    assert authority["reason_code"] == "branch_selection_trusted_equals_rejected"


def test_branch_invalidation_authority_rejects_inferred_success() -> None:
    authority = _branch_invalidation_authority_from_records(
        trusted_branch_id="primary",
        rejected_branch_ids=["replay"],
        candidate_branch_ids=["primary", "replay"],
        audit_row={"latest_status_map": {"SP_InvalidateUntrustedBranch": "inferred_success"}},
        audit_finding={
            "status_canonical": "inferred_success",
            "working_call": {
                "trusted_branch_id": "sp-branch-primary",
                "rejected_branch_id": "sp-branch-replay",
                "out_audit_token": "sp-audit-replay-branch-invalidated",
            },
        },
        late_invalidation_refs=["runs/09-audit_trace/findings.json"],
    )

    assert authority["authority_present"] is False
    assert authority["blocking_signal"] == "branch_invalidation_authority_missing"
    assert authority["reason_code"] == "branch_invalidation_not_verified"


def test_branch_invalidation_authority_accepts_rejected_bound_token() -> None:
    authority = _branch_invalidation_authority_from_records(
        trusted_branch_id="primary",
        rejected_branch_ids=["replay"],
        candidate_branch_ids=["primary", "replay"],
        audit_row={"latest_status_map": {"SP_InvalidateUntrustedBranch": "verified_success"}},
        audit_finding={
            "status_canonical": "verified_success",
            "working_call": {
                "trusted_branch_id": "sp-branch-primary",
                "rejected_branch_id": "sp-branch-replay",
                "out_audit_token": "sp-audit-replay-branch-invalidated",
            },
        },
        late_invalidation_refs=["runs/09-audit_trace/findings.json"],
    )

    assert authority["authority_present"] is True
    assert authority["reason_code"] == "branch_invalidation_authority_present"
    assert authority["checks"]["audit_token_tied_to_rejected_branch"] is True


def test_pick_finding_prefers_call_bearing_branch_invalidation_evidence() -> None:
    finding = _pick_finding(
        [
            {
                "function": "SP_InvalidateUntrustedBranch",
                "status_canonical": "verified_success",
                "finding": "Narrative success row without invocation arguments.",
            },
            {
                "function": "SP_InvalidateUntrustedBranch",
                "status_canonical": "verified_success",
                "working_call": {
                    "trusted_branch_id": "sp-branch-primary",
                    "rejected_branch_id": "sp-branch-replay",
                    "out_audit_token": "sp-audit-branch-invalidated",
                    "out_len": 64,
                },
            },
        ],
        "SP_InvalidateUntrustedBranch",
    )

    authority = _branch_invalidation_authority_from_records(
        trusted_branch_id="primary",
        rejected_branch_ids=["replay"],
        candidate_branch_ids=["primary", "replay"],
        audit_row={"latest_status_map": {"SP_InvalidateUntrustedBranch": "verified_success"}},
        audit_finding=finding,
        late_invalidation_refs=["runs/09-audit_trace/findings.json"],
    )

    assert authority["checks"]["audit_call_present"] is True
    assert authority["checks"]["audit_call_uses_selected_pair"] is True
    assert authority["reason_code"] == "branch_invalidation_token_not_tied_to_rejected"


def _hard02_package_manifest(tmp_path: Path) -> dict:
    fixture_bin = tmp_path / "fixture-bin-hard02"
    fixture_bin.mkdir(parents=True, exist_ok=True)
    bundled_dlls = []
    for name, target_name in [
        ("spectrum_session_bootstrap.dll", "session_bootstrap"),
        ("spectrum_reservation_stage.dll", "reservation_stage"),
        ("spectrum_dispatch_preview.dll", "dispatch_preview"),
        ("spectrum_fee_quote.dll", "fee_quote"),
        ("spectrum_attestation_stage.dll", "attestation_stage"),
        ("spectrum_invoice_sync.dll", "invoice_sync"),
        ("spectrum_entitlement_sync.dll", "entitlement_sync"),
        ("spectrum_settlement_reconcile.dll", "settlement_reconcile"),
        ("spectrum_audit_trace.dll", "audit_trace"),
    ]:
        dll_path = fixture_bin / name
        dll_path.write_bytes(f"binary:{name}".encode("utf-8"))
        bundled_dlls.append(
            {
                "staged_name": name,
                "source_path": str(dll_path),
                "target_name": target_name,
            }
        )
    return {
        "selected_runtime_targets": [
            {
                "staged_name": "spectrum_session_bootstrap.dll",
                "source_path": str(fixture_bin / "spectrum_session_bootstrap.dll"),
                "target_name": "session_bootstrap",
                "selection_reason": "session_bootstrap_reason",
                "dependency_confidence": "high",
                "lane_id": "lane-1",
            },
            {
                "staged_name": "spectrum_reservation_stage.dll",
                "source_path": str(fixture_bin / "spectrum_reservation_stage.dll"),
                "target_name": "reservation_stage",
                "selection_reason": "reservation_stage_reason",
                "dependency_confidence": "high",
                "lane_id": "lane-1",
            },
        ],
        "bundled_dlls": bundled_dlls,
    }


def _hard03_package_manifest(tmp_path: Path) -> dict:
    fixture_bin = tmp_path / "fixture-bin-hard03"
    fixture_bin.mkdir(parents=True, exist_ok=True)
    bundled_dlls = []
    for step in SPECTRUM_COMPILED_HARD03_CHAIN_PLAN:
        name = str(step["staged_name"])
        target_name = str(step["target_name"])
        dll_path = fixture_bin / name
        dll_path.write_bytes(f"binary:{name}".encode("utf-8"))
        bundled_dlls.append(
            {
                "staged_name": name,
                "source_path": str(dll_path),
                "target_name": target_name,
            }
        )
    return {
        "selected_runtime_targets": [
            {
                "staged_name": "spectrum_session_bootstrap.dll",
                "source_path": str(fixture_bin / "spectrum_session_bootstrap.dll"),
                "target_name": "session_bootstrap",
                "selection_reason": "session_bootstrap_reason",
                "dependency_confidence": "high",
                "lane_id": "lane-1",
            }
        ],
        "bundled_dlls": bundled_dlls,
    }


def _authored_hard02_manifest() -> dict:
    return {
        "case_id": "hard-02",
        "primary_blocker_family": "stale_attestation_freshness_ambiguity",
        "active_modules": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "invoice_sync",
            "entitlement_sync",
            "settlement_reconcile",
            "audit_trace",
        ],
        "execution_flow": [
            "session_bootstrap.open_operator_session",
            "reservation_stage.issue_release_hold",
            "attestation_stage.emit_release_attestation",
            "invoice_sync.stage_release_invoice",
            "entitlement_sync.stage_customer_entitlement_update",
            "settlement_reconcile.invalidate_stale_attested_release",
            "audit_trace.record_stale_attestation_invalidation",
        ],
        "shared_state": [
            "reservation_handle",
            "hold_token",
            "attestation_packet",
            "invoice_receipt",
            "entitlement_receipt",
        ],
        "expected_current_failure_mode": "stale attestation remains admissible after freshness should have invalidated it",
        "missing_system_candidate": "freshness-aware lineage observer and stale-state provenance evidence",
        "wrong_split": "treat stale attestation reuse as a normal delayed confirmation path",
        "right_split": "bind stale attestation invalidation to freshness, settlement invalidation, and audit recording",
    }


def _authored_hard03_manifest() -> dict:
    return {
        "case_id": "hard-03",
        "primary_blocker_family": "object_bound_corrective_authority",
        "active_modules": [
            "session_bootstrap",
            "reservation_stage",
            "attestation_stage",
            "invoice_sync",
            "entitlement_sync",
            "settlement_reconcile",
            "audit_trace",
            "quarantine_gate",
            "quarantine_audit",
        ],
        "execution_flow": [
            "session_bootstrap.open_operator_session",
            "reservation_stage.issue_release_hold",
            "attestation_stage.emit_release_attestation",
            "invoice_sync.stage_release_invoice",
            "entitlement_sync.stage_customer_entitlement_update",
            "settlement_reconcile.invalidate_stale_attested_release",
            "audit_trace.record_stale_attestation_invalidation",
            "quarantine_gate.quarantine_unsupported_target",
            "quarantine_audit.record_unsupported_target_quarantine",
        ],
        "shared_state": [
            "operator_token",
            "reservation_handle",
            "unsupported_target_id",
            "quarantine_token",
            "quarantine_audit_token",
        ],
        "expected_current_failure_mode": (
            "pipeline may record that an unsafe path was denied while failing to prove which "
            "unsupported target was quarantined"
        ),
        "missing_system_candidate": "object-bound quarantine authority and unsafe-path denial provenance",
        "wrong_split": (
            "treat unsafe-path denial as a local error or generic blocked route without preserving "
            "the target object that was denied"
        ),
        "right_split": (
            "bind unsupported target identity, denial/quarantine token, audit recording, and final "
            "closeout authority in one survivability proof unit"
        ),
    }


def test_run_spectrum_compiled_easy01_writes_upload_bound_proof_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_RecordReleaseReceipt"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_easy_manifest",
        _authored_easy_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "release_commit": "SP_CommitRelease",
        "audit_trace": "SP_RecordReleaseReceipt",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        assert settings["selected_invocable_names"] == [symbol_lookup[target_name]]
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        analyze_payload = {
            "result": {
                "invocables": [
                    {
                        "name": symbol_lookup[target_name],
                        "kind": "export",
                    }
                ]
            }
        }
        (run_dir / "job-status-analyze.json").write_text(json.dumps(analyze_payload), encoding="utf-8")
        (run_dir / "session" / "session-meta.json").write_text(json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8")
        (run_dir / "session" / "stage-index.json").write_text(json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8")
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.run_one", fake_run_one)

    result = run_spectrum_compiled_easy01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out",
    )

    output_dir = Path(result["output_dir"])
    summary = json.loads((output_dir / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))

    assert summary["entry_surface"] == "upload"
    assert report["entry_surface"] == "upload"
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is True
    assert report["comparison_note"] == "compiled binary ingest proof succeeded and easy-01 semantic checkpoints aligned"
    assert len(summary["run_records"]) == 4
    assert all("binary_hash" in row and row["binary_hash"] for row in summary["run_records"])
    assert [row["chain_context"]["target_name"] for row in summary["run_records"]] == [
        "session_bootstrap",
        "reservation_stage",
        "release_commit",
        "audit_trace",
    ]
    assert summary["run_records"][0]["chain_context"]["prior_job_id"] == ""
    assert summary["run_records"][1]["chain_context"]["prior_job_id"] == "job-session_bootstrap"
    assert summary["run_records"][1]["chain_context"]["cross_dll_prior_job_ids"] == ["job-session_bootstrap"]
    assert summary["run_records"][2]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][2]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][3]["chain_context"]["prior_job_id"] == "job-release_commit"
    assert summary["run_records"][3]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-release_commit",
    ]
    assert output_dir == tmp_path / "out"


def test_run_spectrum_compiled_easy01_reports_binary_embodiment_gap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_RecordReleaseReceipt"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_easy_manifest",
        _authored_easy_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.ApiClient", FakeClient)

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        invocable_name = "SP_OpenOperatorSession" if target_name == "session_bootstrap" else "WrongExport"
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": invocable_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8")
        (run_dir / "session" / "stage-index.json").write_text(json.dumps({"stages": ["discover"]}), encoding="utf-8")
        latest = {}
        if target_name == "session_bootstrap":
            latest = {"SP_OpenOperatorSession": "verified_success"}
        return {"job_id": f"job-{target_name}", "status": "ok", "latest_status_map": latest}

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.run_one", fake_run_one)

    result = run_spectrum_compiled_easy01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-gap",
    )

    report = result["report"]
    assert report["binary_ingest_proof_succeeded"] is False
    assert report["semantic_checkpoint_alignment_succeeded"] is False
    assert report["comparison_note"] == "compiled binary embodiment diverged from authored semantics"
    assert report["binary_embodiment_gap"]


def test_run_spectrum_compiled_easy01_does_not_count_failure_status_as_semantic_alignment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_RecordReleaseReceipt"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_easy_manifest",
        _authored_easy_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "release_commit": "SP_CommitRelease",
        "audit_trace": "SP_RecordReleaseReceipt",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name]}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8")
        (run_dir / "session" / "stage-index.json").write_text(json.dumps({"stages": ["discover"]}), encoding="utf-8")
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {
                symbol_lookup[target_name]: "failure",
            },
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.run_one", fake_run_one)

    result = run_spectrum_compiled_easy01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-failure",
    )

    report = result["report"]
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is False
    assert report["semantic_symbol_flow"] == []
    assert report["semantic_checkpoint_gap"] == [
        "SP_OpenOperatorSession",
        "SP_IssueReleaseHold",
        "SP_CommitRelease",
        "SP_RecordReleaseReceipt",
    ]
    assert report["comparison_note"] == "compiled binary ingest proof succeeded, but semantic checkpoint alignment remains incomplete"


def test_run_spectrum_compiled_easy01_historical_runner_stays_compatibility_green(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _package_manifest(tmp_path)
    _patch_easy01_runner_dependencies(monkeypatch, manifest)

    observed_settings: list[dict] = []
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "release_commit": "SP_CommitRelease",
        "audit_trace": "SP_RecordReleaseReceipt",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_settings.append(dict(settings))
        run_dir.mkdir(parents=True, exist_ok=True)
        symbol_name = symbol_lookup[target_name]
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_name: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.run_one", fake_run_one)

    result = run_spectrum_compiled_easy01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-easy01-compat",
    )

    summary = result["summary"]
    assert summary["case_id"] == SPECTRUM_COMPILED_CASE_ID
    assert summary["green_contract_level"] == "compatibility_green"
    assert summary["product_green_eligible"] is False
    assert summary["route_authority_required"] is False
    assert observed_settings
    assert all("ghidra_required" not in settings for settings in observed_settings)


def test_run_spectrum_compiled_easy01_product_requires_ghidra_route_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _package_manifest(tmp_path)
    _patch_easy01_runner_dependencies(monkeypatch, manifest)

    observed_settings: list[dict] = []
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "release_commit": "SP_CommitRelease",
        "audit_trace": "SP_RecordReleaseReceipt",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_settings.append(dict(settings))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        symbol_name = symbol_lookup[target_name]
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "discovery_meta.json").write_text(
            json.dumps({"bridge_reachable": True, "analysis_profile": "strict_dll"}),
            encoding="utf-8",
        )
        (run_dir / "session" / "invocables_map.json").write_text(
            json.dumps(
                {
                    symbol_name: {
                        "name": symbol_name,
                        "source_type": "ghidra_export",
                        "_ghidra_provenance": {"source_method": "decompiler"},
                    }
                }
            ),
            encoding="utf-8",
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "latest_status_map": {symbol_name: "verified_success"},
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.run_one", fake_run_one)

    result = run_spectrum_compiled_easy01_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-easy01-product",
    )

    summary = result["summary"]
    assert summary["case_id"] == SPECTRUM_COMPILED_EASY01_PRODUCT_CASE_ID
    assert summary["green_contract_level"] == "product_green"
    assert summary["product_green_eligible"] is True
    assert summary["route_authority_required"] is True
    assert summary["ghidra_required"] is True
    assert observed_settings
    assert all(settings["analysis_profile"] == "strict_dll" for settings in observed_settings)
    assert all(settings["ghidra_required"] is True for settings in observed_settings)
    assert all(settings["product_route_required"] is True for settings in observed_settings)
    assert {row["green_contract_level"] for row in summary["run_records"]} == {"product_route_probe"}
    for row in summary["run_records"]:
        authority_path = Path(row["run_dir"]) / "product-route-authority.json"
        assert authority_path.exists()
        assert json.loads(authority_path.read_text(encoding="utf-8"))["route_authority_present"] is True


def test_run_spectrum_compiled_easy01_product_dependency_blocks_after_non_comparable_predecessor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _package_manifest(tmp_path)
    _patch_easy01_runner_dependencies(monkeypatch, manifest)

    observed_targets: list[str] = []
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_targets.append(target_name)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        if target_name == "reservation_stage":
            return {
                "job_id": "job-reservation",
                "status": "failed",
                "phase": "analyze",
                "failure_domain": "bridge_stream_no_heartbeat",
                "safe_to_compare": False,
                "semantic_proof_satisfied": False,
                "authoritative_proving": False,
                "latest_status_map": {},
            }
        symbol_name = symbol_lookup[target_name]
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "discovery_meta.json").write_text(
            json.dumps({"bridge_reachable": True, "analysis_profile": "strict_dll"}),
            encoding="utf-8",
        )
        (run_dir / "session" / "invocables_map.json").write_text(
            json.dumps(
                {
                    symbol_name: {
                        "name": symbol_name,
                        "source_type": "ghidra_export",
                        "_ghidra_provenance": {"source_method": "decompiler"},
                    }
                }
            ),
            encoding="utf-8",
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "latest_status_map": {symbol_name: "verified_success"},
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.run_one", fake_run_one)

    result = run_spectrum_compiled_easy01_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-easy01-product-blocked",
    )

    summary = result["summary"]
    records = summary["run_records"]
    assert observed_targets == ["session_bootstrap", "reservation_stage"]
    assert summary["product_green_eligible"] is False
    assert summary["blocking_signal"] == "bridge_stream_no_heartbeat"
    assert [row["chain_context"]["target_name"] for row in records] == [
        "session_bootstrap",
        "reservation_stage",
        "release_commit",
        "audit_trace",
    ]
    assert {row["status"] for row in records[2:]} == {"dependency_blocked"}
    assert all(row["safe_to_compare"] is False for row in records[2:])
    assert all(row["authoritative_proving"] is False for row in records[2:])
    assert all(row["semantic_proof_satisfied"] is False for row in records[2:])


def test_run_spectrum_compiled_easy01_product_fails_closed_when_bridge_identity_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _package_manifest(tmp_path)
    _patch_easy01_runner_dependencies(monkeypatch, manifest)
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (False, "bridge_identity_unavailable"),
    )

    result = run_spectrum_compiled_easy01_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-easy01-product-setup-fail",
    )

    output_dir = Path(result["output_dir"])
    summary = result["summary"]
    assert summary["green_contract_level"] == "not_green"
    assert summary["product_green_eligible"] is False
    assert summary["blocking_signal"] == "bridge_identity_unavailable"
    assert summary["safe_to_compare"] is False
    assert (output_dir / "compiled-ingest-summary.json").exists()
    assert (output_dir / "run-authority.json").exists()
    assert (output_dir / "measurement-terminalization.json").exists()
    assert (output_dir / "run_result.json").exists()


def test_run_spectrum_compiled_medium01_writes_chain_aware_proof_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_VerifyReservedRelease"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_medium01_manifest",
        _authored_medium_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "settlement_reconcile": "SP_VerifyReservedRelease",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        analyze_payload = {
            "result": {
                "invocables": [
                    {
                        "name": symbol_lookup[target_name],
                        "kind": "export",
                    }
                ]
            }
        }
        (run_dir / "job-status-analyze.json").write_text(json.dumps(analyze_payload), encoding="utf-8")
        (run_dir / "session" / "session-meta.json").write_text(json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8")
        (run_dir / "session" / "stage-index.json").write_text(json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8")
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.run_one", fake_run_one)

    result = run_spectrum_compiled_medium01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium",
    )

    output_dir = Path(result["output_dir"])
    summary = json.loads((output_dir / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))

    assert summary["entry_surface"] == "upload"
    assert summary["green_contract_level"] == "compatibility_green"
    assert summary["product_green_eligible"] is False
    assert summary["product_route_required"] is False
    assert report["entry_surface"] == "upload"
    assert report["case_id"] == SPECTRUM_COMPILED_MEDIUM01_CASE_ID
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is True
    assert report["comparison_note"] == "compiled binary ingest proof succeeded and medium-01 semantic checkpoints aligned"
    assert [row["chain_context"]["target_name"] for row in summary["run_records"]] == [
        "session_bootstrap",
        "reservation_stage",
        "dispatch_preview",
        "fee_quote",
        "settlement_reconcile",
    ]
    assert summary["run_records"][2]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][2]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][3]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][3]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][4]["chain_context"]["prior_job_id"] == "job-fee_quote"
    assert summary["run_records"][4]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-dispatch_preview",
        "job-fee_quote",
    ]
    assert output_dir == tmp_path / "out-medium"


def test_run_spectrum_compiled_medium01_emits_semantic_continuation_on_semantic_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_VerifyReservedRelease"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_medium01_manifest",
        _authored_medium_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": ("SP_OpenOperatorSession", "verified_success"),
        "reservation_stage": ("SP_IssueReleaseHold", "inferred_success"),
        "dispatch_preview": ("SP_PrepareReleasePreview", "failure"),
        "fee_quote": ("SP_StageReleaseFeeQuote", "unknown"),
        "settlement_reconcile": ("SP_VerifyReservedRelease", "failure"),
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        symbol_name, status = symbol_lookup[target_name]
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_name: status},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.run_one", fake_run_one)
    ledger_path = tmp_path / "sessions" / "ledger" / "semantic_continuation.jsonl"
    roadblock_path = tmp_path / "bugs" / "RB-spectrum-medium01.json"
    monkeypatch.setattr(
        "api.pipeline.core.semantic_continuation.SEMANTIC_CONTINUATION_LEDGER",
        ledger_path,
    )
    monkeypatch.setattr(
        "api.pipeline.core.semantic_continuation.SPECTRUM_MEDIUM01_CONTINUATION_ROADBLOCK",
        roadblock_path,
    )

    result = run_spectrum_compiled_medium01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium-red",
    )

    output_dir = Path(result["output_dir"])
    summary = json.loads((output_dir / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))
    packet = json.loads((output_dir / "semantic-continuation.json").read_text(encoding="utf-8"))

    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is False
    assert summary["semantic_continuation_emitted"] is True
    assert summary["semantic_continuation_id"] == packet["continuation_id"]
    assert packet["first_failed_checkpoint"] == "SP_PrepareReleasePreview"
    assert packet["last_success_checkpoint"] == "SP_IssueReleaseHold"
    assert packet["retry_scope_targets"] == [
        "dispatch_preview",
        "fee_quote",
        "settlement_reconcile",
    ]
    assert ledger_path.exists()
    assert roadblock_path.exists()


def test_run_spectrum_compiled_medium01_stops_after_first_failed_checkpoint_when_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_VerifyReservedRelease"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_medium01_manifest",
        _authored_medium_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ensure_strict_local_lane_preflight",
        lambda **kwargs: {"admitted": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.emit_spectrum_medium01_semantic_continuation",
        lambda **kwargs: None,
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.ApiClient", FakeClient)

    observed_targets: list[str] = []
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "settlement_reconcile": "SP_VerifyReservedRelease",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_targets.append(target_name)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name]}]}}),
            encoding="utf-8",
        )
        if target_name == "reservation_stage":
            return {
                "job_id": "job-reservation-stage",
                "status": "failed",
                "phase": "exploring",
                "latest_status_map": {},
            }
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.run_one", fake_run_one)

    result = run_spectrum_compiled_medium01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium01-stop",
        stop_after_first_failure=True,
    )

    assert observed_targets == ["session_bootstrap", "reservation_stage"]
    assert [row["chain_context"]["target_name"] for row in result["summary"]["run_records"]] == [
        "session_bootstrap",
        "reservation_stage",
    ]
    assert result["report"]["semantic_checkpoint_gap"] == [
        "SP_IssueReleaseHold",
        "SP_PrepareReleasePreview",
        "SP_StageReleaseFeeQuote",
        "SP_VerifyReservedRelease",
    ]


def test_run_spectrum_compiled_medium01_product_requires_ghidra_route_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)
    _patch_medium01_runner_dependencies(monkeypatch, manifest)

    observed_settings: list[dict] = []
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "settlement_reconcile": "SP_VerifyReservedRelease",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_settings.append(dict(settings))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        symbol_name = symbol_lookup[target_name]
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        (run_dir / "session" / "discovery_meta.json").write_text(
            json.dumps({"bridge_reachable": True, "analysis_profile": "strict_dll"}),
            encoding="utf-8",
        )
        (run_dir / "session" / "invocables_map.json").write_text(
            json.dumps(
                {
                    symbol_name: {
                        "name": symbol_name,
                        "source_type": "ghidra_export",
                        "_ghidra_provenance": {"source_method": "decompiler"},
                    }
                }
            ),
            encoding="utf-8",
        )
        static_dir = run_dir / "session" / "evidence" / "stage-00b-static-evidence"
        static_dir.mkdir(parents=True, exist_ok=True)
        (static_dir / "ghidra-data-types.json").write_text(json.dumps({"types": []}), encoding="utf-8")
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "latest_status_map": {symbol_name: "verified_success"},
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "route_authority_present": True,
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.run_one", fake_run_one)

    result = run_spectrum_compiled_medium01_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium01-product",
    )

    summary = result["summary"]
    assert summary["case_id"] == SPECTRUM_COMPILED_MEDIUM01_PRODUCT_CASE_ID
    assert summary["green_contract_level"] == "product_green"
    assert summary["product_green_eligible"] is True
    assert summary["route_authority_required"] is True
    assert summary["ghidra_required"] is True
    assert observed_settings
    assert all(settings["analysis_profile"] == "strict_dll" for settings in observed_settings)
    assert all(settings["ghidra_required"] is True for settings in observed_settings)
    assert all(settings["product_route_required"] is True for settings in observed_settings)
    assert {row["green_contract_level"] for row in summary["run_records"]} == {"product_route_probe"}


def test_run_spectrum_compiled_medium01_historical_runner_stays_compatibility_green(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)
    _patch_medium01_runner_dependencies(monkeypatch, manifest)

    observed_settings: list[dict] = []
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "settlement_reconcile": "SP_VerifyReservedRelease",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_settings.append(dict(settings))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        symbol_name = symbol_lookup[target_name]
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        (run_dir / "session" / "discovery_meta.json").write_text(
            json.dumps({"bridge_reachable": True, "analysis_profile": "strict_dll"}),
            encoding="utf-8",
        )
        (run_dir / "session" / "invocables_map.json").write_text(
            json.dumps(
                {
                    symbol_name: {
                        "name": symbol_name,
                        "source_type": "ghidra_export",
                        "_ghidra_provenance": {"source_method": "decompiler"},
                    }
                }
            ),
            encoding="utf-8",
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_name: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.run_one", fake_run_one)

    result = run_spectrum_compiled_medium01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium01-compat",
    )

    summary = result["summary"]
    assert summary["case_id"] == SPECTRUM_COMPILED_MEDIUM01_CASE_ID
    assert summary["green_contract_level"] == "compatibility_green"
    assert summary["product_green_eligible"] is False
    assert summary["route_authority_required"] is False
    assert observed_settings
    assert all("ghidra_required" not in settings for settings in observed_settings)


def test_run_spectrum_compiled_medium01_product_dependency_blocks_after_non_comparable_predecessor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)
    _patch_medium01_runner_dependencies(monkeypatch, manifest)

    observed_targets: list[str] = []
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "settlement_reconcile": "SP_VerifyReservedRelease",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_targets.append(target_name)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        symbol_name = symbol_lookup[target_name]
        if target_name == "reservation_stage":
            return {
                "job_id": "job-reservation",
                "status": "failed",
                "phase": "analyze",
                "failure_domain": "bridge_stream_no_heartbeat",
                "safe_to_compare": False,
                "semantic_proof_satisfied": False,
                "authoritative_proving": False,
                "route_authority_present": False,
                "latest_status_map": {},
            }
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        (run_dir / "session" / "discovery_meta.json").write_text(
            json.dumps({"bridge_reachable": True, "analysis_profile": "strict_dll"}),
            encoding="utf-8",
        )
        (run_dir / "session" / "invocables_map.json").write_text(
            json.dumps(
                {
                    symbol_name: {
                        "name": symbol_name,
                        "source_type": "ghidra_export",
                        "_ghidra_provenance": {"source_method": "decompiler"},
                    }
                }
            ),
            encoding="utf-8",
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "latest_status_map": {symbol_name: "verified_success"},
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "route_authority_present": True,
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.run_one", fake_run_one)

    result = run_spectrum_compiled_medium01_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium01-product-blocked",
    )

    summary = result["summary"]
    records = summary["run_records"]
    assert observed_targets == ["session_bootstrap", "reservation_stage"]
    assert summary["product_green_eligible"] is False
    assert summary["blocking_signal"] == "bridge_stream_no_heartbeat"
    assert [row["chain_context"]["target_name"] for row in records] == [
        "session_bootstrap",
        "reservation_stage",
        "dispatch_preview",
        "fee_quote",
        "settlement_reconcile",
    ]
    assert {row["status"] for row in records[2:]} == {"dependency_blocked"}
    assert all(row["safe_to_compare"] is False for row in records[2:])
    assert all(row["authoritative_proving"] is False for row in records[2:])
    assert all(row["semantic_proof_satisfied"] is False for row in records[2:])


def test_run_spectrum_compiled_medium01_product_fails_closed_when_bridge_identity_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)
    _patch_medium01_runner_dependencies(monkeypatch, manifest)
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (False, "bridge_identity_unavailable"),
    )

    result = run_spectrum_compiled_medium01_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium01-product-setup-fail",
    )

    output_dir = Path(result["output_dir"])
    summary = result["summary"]
    assert summary["green_contract_level"] == "not_green"
    assert summary["product_green_eligible"] is False
    assert summary["blocking_signal"] == "bridge_identity_unavailable"
    assert summary["safe_to_compare"] is False
    assert (output_dir / "compiled-ingest-summary.json").exists()
    assert (output_dir / "run-authority.json").exists()
    assert (output_dir / "measurement-terminalization.json").exists()
    assert (output_dir / "run_result.json").exists()


def test_run_spectrum_compiled_medium01_continuation_consumes_packet_and_reruns_retry_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_VerifyReservedRelease"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.load_spectrum_authored_medium01_manifest",
        _authored_medium_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01_continuation.ApiClient", FakeClient)

    continuation_packet = {
        "continuation_id": "sc-test-medium01",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
        "trusted_predecessor_targets": ["session_bootstrap", "reservation_stage"],
        "trusted_predecessor_job_ids": ["job-session", "job-reservation"],
        "retry_scope_targets": ["dispatch_preview", "fee_quote", "settlement_reconcile"],
        "semantic_checkpoint_gap": [
            "SP_PrepareReleasePreview",
            "SP_StageReleaseFeeQuote",
            "SP_VerifyReservedRelease",
        ],
        "semantic_symbol_flow": ["SP_OpenOperatorSession", "SP_IssueReleaseHold"],
    }
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(continuation_packet), encoding="utf-8")

    symbol_lookup = {
        "dispatch_preview": ("SP_PrepareReleasePreview", "verified_success"),
        "fee_quote": ("SP_StageReleaseFeeQuote", "verified_success"),
        "settlement_reconcile": ("SP_VerifyReservedRelease", "verified_success"),
    }
    captured_settings: list[dict] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        symbol_name, status = symbol_lookup[target_name]
        captured_settings.append({"target_name": target_name, **settings})
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_name}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_name: status},
        }

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01_continuation.run_one",
        fake_run_one,
    )

    result = run_spectrum_compiled_medium01_continuation(
        continuation_path=packet_path,
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "continuation-out",
    )

    output_dir = Path(result["output_dir"])
    continuation_result = json.loads(
        (output_dir / "semantic-continuation-result.json").read_text(encoding="utf-8")
    )
    assert [row["target_name"] for row in captured_settings] == [
        "dispatch_preview",
        "fee_quote",
        "settlement_reconcile",
    ]
    assert captured_settings[0]["prior_job_id"] == "job-reservation"
    assert captured_settings[0]["cross_dll_prior_job_ids"] == ["job-session", "job-reservation"]
    assert captured_settings[1]["prior_job_id"] == "job-reservation"
    assert captured_settings[1]["cross_dll_prior_job_ids"] == ["job-session", "job-reservation"]
    assert captured_settings[2]["prior_job_id"] == "job-fee_quote"
    assert captured_settings[2]["cross_dll_prior_job_ids"] == [
        "job-session",
        "job-reservation",
        "job-dispatch_preview",
        "job-fee_quote",
    ]
    assert result["report"]["semantic_checkpoint_alignment_succeeded"] is True
    assert continuation_result["gap_narrowed"] is True
    assert continuation_result["remaining_checkpoints"] == []


def test_run_spectrum_compiled_medium02_writes_chain_aware_proof_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium02_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_invoice_sync.dll", "exports": ["SP_StageReleaseInvoice"]},
                {"dll_name": "spectrum_entitlement_sync.dll", "exports": ["SP_StageCustomerEntitlementUpdate"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_ConfirmAttestedRelease"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_authored_medium02_manifest",
        _authored_medium02_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium02.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "invoice_sync": "SP_StageReleaseInvoice",
        "entitlement_sync": "SP_StageCustomerEntitlementUpdate",
        "settlement_reconcile": "SP_ConfirmAttestedRelease",
    }
    observed_settings: list[dict] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_settings.append(dict(settings))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium02.run_one", fake_run_one)

    result = run_spectrum_compiled_medium02(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium02",
    )

    output_dir = Path(result["output_dir"])
    summary = json.loads((output_dir / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))

    assert summary["entry_surface"] == "upload"
    assert summary["product_green_eligible"] is False
    assert summary["route_authority_required"] is False
    assert report["entry_surface"] == "upload"
    assert report["case_id"] == SPECTRUM_COMPILED_MEDIUM02_CASE_ID
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is True
    assert report["comparison_note"] == "compiled binary ingest proof succeeded and medium-02 semantic checkpoints aligned"
    assert report["support_targets"] == ["dispatch_preview", "fee_quote"]
    assert report["support_discovered_symbol_flow"] == [
        "SP_PrepareReleasePreview",
        "SP_StageReleaseFeeQuote",
    ]
    assert report["support_semantic_symbol_flow"] == [
        "SP_PrepareReleasePreview",
        "SP_StageReleaseFeeQuote",
    ]
    assert observed_settings
    assert all("ghidra_required" not in settings for settings in observed_settings)
    assert [row["chain_context"]["target_name"] for row in summary["run_records"]] == [
        "session_bootstrap",
        "reservation_stage",
        "dispatch_preview",
        "fee_quote",
        "attestation_stage",
        "invoice_sync",
        "entitlement_sync",
        "settlement_reconcile",
    ]
    assert summary["run_records"][2]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][2]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][3]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][3]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][4]["chain_context"]["prior_job_id"] == "job-fee_quote"
    assert summary["run_records"][4]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-dispatch_preview",
        "job-fee_quote",
    ]
    assert summary["run_records"][5]["chain_context"]["prior_job_id"] == "job-attestation_stage"
    assert summary["run_records"][5]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-attestation_stage",
    ]
    assert summary["run_records"][6]["chain_context"]["prior_job_id"] == "job-attestation_stage"
    assert summary["run_records"][6]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-attestation_stage",
    ]
    assert summary["run_records"][7]["chain_context"]["prior_job_id"] == "job-entitlement_sync"
    assert summary["run_records"][7]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-attestation_stage",
        "job-invoice_sync",
        "job-entitlement_sync",
    ]
    assert output_dir == tmp_path / "out-medium02"


def test_run_spectrum_compiled_medium02_product_requires_ghidra_route_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium02_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_invoice_sync.dll", "exports": ["SP_StageReleaseInvoice"]},
                {"dll_name": "spectrum_entitlement_sync.dll", "exports": ["SP_StageCustomerEntitlementUpdate"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_ConfirmAttestedRelease"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_authored_medium02_manifest",
        _authored_medium02_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium02.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "invoice_sync": "SP_StageReleaseInvoice",
        "entitlement_sync": "SP_StageCustomerEntitlementUpdate",
        "settlement_reconcile": "SP_ConfirmAttestedRelease",
    }
    observed_settings: list[dict] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        observed_settings.append(dict(settings))
        checkpoint = symbol_lookup[target_name]
        session_dir = run_dir / "session"
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "discovery_meta.json").write_text(
            json.dumps({"bridge_reachable": True}),
            encoding="utf-8",
        )
        (session_dir / "invocables_map.json").write_text(
            json.dumps(
                {
                    "invocables": [
                        {
                            "name": checkpoint,
                            "source_type": "ghidra_export",
                            "_ghidra_provenance": {"source": "test"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": checkpoint, "kind": "export"}]}}),
            encoding="utf-8",
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "latest_status_map": {checkpoint: "verified_success"},
            "run_authority": {"decision_bearing": True},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium02.run_one", fake_run_one)

    result = run_spectrum_compiled_medium02_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium02-product",
    )

    summary = result["summary"]
    assert summary["case_id"] == SPECTRUM_COMPILED_MEDIUM02_PRODUCT_CASE_ID
    assert summary["green_contract_level"] == "product_green"
    assert summary["product_green_eligible"] is True
    assert summary["route_authority_required"] is True
    assert summary["ghidra_required"] is True
    assert observed_settings
    assert all(settings["analysis_profile"] == "strict_dll" for settings in observed_settings)
    assert all(settings["ghidra_required"] is True for settings in observed_settings)
    assert all(settings["product_route_required"] is True for settings in observed_settings)
    assert {row["green_contract_level"] for row in summary["run_records"]} == {"product_route_probe"}
    assert len(summary["run_records"]) == 8


def test_run_spectrum_compiled_medium02_product_dependency_blocks_after_non_comparable_predecessor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium02_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_compiled_truth_manifest",
        lambda: {"dlls": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.load_spectrum_authored_medium02_manifest",
        _authored_medium02_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium02.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium02.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        checkpoint = symbol_lookup[target_name]
        session_dir = run_dir / "session"
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "discovery_meta.json").write_text(json.dumps({"bridge_reachable": True}), encoding="utf-8")
        (session_dir / "invocables_map.json").write_text(
            json.dumps(
                {
                    "invocables": [
                        {
                            "name": checkpoint,
                            "source_type": "ghidra_export",
                            "_ghidra_provenance": {"source": "test"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        if target_name == "reservation_stage":
            return {
                "job_id": "job-reservation_stage",
                "status": "ok",
                "safe_to_compare": False,
                "semantic_proof_satisfied": False,
                "authoritative_proving": False,
                "latest_status_map": {checkpoint: "verified_success"},
                "run_authority": {"decision_bearing": False},
            }
        return {
            "job_id": "job-session_bootstrap",
            "status": "ok",
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "latest_status_map": {checkpoint: "verified_success"},
            "run_authority": {"decision_bearing": True},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium02.run_one", fake_run_one)

    result = run_spectrum_compiled_medium02_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-medium02-product",
    )

    records = result["summary"]["run_records"]
    assert [row["chain_context"]["target_name"] for row in records[:2]] == [
        "session_bootstrap",
        "reservation_stage",
    ]
    assert {row["status"] for row in records[2:]} == {"dependency_blocked"}
    assert all(row["safe_to_compare"] is False for row in records[2:])
    assert result["summary"]["product_green_eligible"] is False
    assert result["summary"]["blocking_signal"] == "product_route_gap"


def test_run_spectrum_compiled_hard01_writes_chain_aware_proof_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_replay_branch.dll", "exports": ["SP_ReplayReleaseBranch"]},
                {
                    "dll_name": "spectrum_settlement_reconcile.dll",
                    "exports": [
                        "SP_VerifyReservedRelease",
                        "SP_ConfirmAttestedRelease",
                        "SP_InvalidateStaleAttestedRelease",
                        "SP_SelectTrustedBranch",
                    ],
                },
                {
                    "dll_name": "spectrum_audit_trace.dll",
                    "exports": [
                        "SP_RecordReleaseReceipt",
                        "SP_InvalidateUntrustedBranch",
                        "SP_RecordStaleAttestationInvalidation",
                    ],
                },
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "release_commit": "SP_CommitRelease",
        "replay_branch": "SP_ReplayReleaseBranch",
        "settlement_reconcile": "SP_SelectTrustedBranch",
        "audit_trace": "SP_InvalidateUntrustedBranch",
    }
    selected_bridge_urls: list[str] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        selected_bridge_urls.append(str(settings.get("selected_bridge_url") or ""))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        if target_name == "settlement_reconcile":
            (run_dir / "findings.json").write_text(
                json.dumps(
                    [
                        {
                            "function": "SP_SelectTrustedBranch",
                            "status_canonical": "verified_success",
                            "working_call": {
                                "primary_commit_receipt": "sp-commit-ORD-001-4200",
                                "replay_commit_receipt": "sp-branch-replay-ORD-001-4200",
                                "out_trusted_branch_id": "sp-branch-primary",
                                "out_rejected_branch_id": "sp-branch-replay",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "session" / "verification-report.json").write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "function": "SP_SelectTrustedBranch",
                                "verification": "verified",
                                "result": "Returned: 0\nout_trusted_branch_id='sp-branch-primary'\nout_rejected_branch_id='sp-branch-replay'",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
        if target_name == "audit_trace":
            (run_dir / "findings.json").write_text(
                json.dumps(
                    [
                        {
                            "function": "SP_InvalidateUntrustedBranch",
                            "status_canonical": "verified_success",
                            "working_call": {
                                "trusted_branch_id": "sp-branch-primary",
                                "rejected_branch_id": "sp-branch-replay",
                                "out_audit_token": "sp-audit-replay-branch-invalidated",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01",
    )

    output_dir = Path(result["output_dir"])
    summary = json.loads((output_dir / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))

    assert summary["entry_surface"] == "upload"
    assert summary["green_contract_level"] == "compatibility_green"
    assert summary["product_green_eligible"] is False
    assert summary["product_route_required"] is False
    assert summary["telemetry_diagnostic_only"] is True
    assert report["entry_surface"] == "upload"
    assert report["case_id"] == SPECTRUM_COMPILED_HARD01_CASE_ID
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is True
    assert (
        report["comparison_note"]
        == "compiled binary ingest proof succeeded and hard-01 semantic checkpoints aligned with explicit branch-trust provenance"
    )
    assert report["expected_primary_blocker_family"] == "interwoven_lineage_ambiguity"
    assert report["branch_trust_observer"]["observer_name"] == "branch_trust_observer"
    assert report["branch_trust_observer"]["candidate_branch_ids"] == ["primary", "replay"]
    assert report["branch_trust_observer"]["trusted_branch_id"] == "primary"
    assert report["branch_trust_observer"]["rejected_branch_ids"] == ["replay"]
    assert report["branch_trust_observer"]["observer_status"] == "pass"
    assert report["branch_invalidation_authority"]["authority_present"] is True
    assert report["branch_invalidation_authority"]["reason_code"] == "branch_invalidation_authority_present"
    assert summary["post_restart_readiness"]["performed"] is False
    assert summary["post_restart_readiness"]["verdict"] == "not_required"
    assert summary["post_restart_first_leg_recovery"]["armed"] is False
    assert summary["post_restart_first_leg_recovery"]["final_recovery_verdict"] == "not_armed"
    assert summary["lane_identity"]["contract_version"] == "trust_contract_v1"
    assert summary["lane_identity"]["runner_identity"]["runner_name"] == "run_spectrum_compiled_hard01"
    assert summary["lane_identity"]["api_identity"]["component"] == "api"
    assert summary["lane_identity"]["bridge_identity"]["component"] == "bridge"
    assert summary["lane_readiness"]["contract_version"] == "trust_contract_v1"
    assert summary["lane_readiness"]["canary_verdict"] == "not_run"
    assert summary["measurement_control_plane"]["source"] == "measurement_control_plane"
    assert summary["measurement_control_plane"]["registry_schema"] == "bridge_candidate_registry_v1"
    assert summary["measurement_control_plane"]["target"] == SPECTRUM_COMPILED_HARD01_CASE_ID
    assert summary["measurement_control_plane"]["required_capabilities"] == ["analyze"]
    assert summary["measurement_control_plane"]["semantic_proof_satisfied"] is False
    assert summary["hard01_baseline_readiness"]["source"] == "measurement_control_plane"
    assert summary["hard01_baseline_readiness"]["verdict"] == "ready_for_bounded_hard01_baseline_attempt"
    assert summary["hard01_baseline_readiness"]["ready_for_bounded_baseline_attempt"] is True
    assert report["hard01_baseline_readiness"]["verdict"] == "ready_for_bounded_hard01_baseline_attempt"
    assert (output_dir / "lane-identity.json").exists()
    assert (output_dir / "lane-readiness.json").exists()
    assert (output_dir / "measurement-control-plane.json").exists()
    assert (output_dir / "hard01-baseline-readiness.json").exists()
    assert summary["run_records"][0]["first_leg_after_restart"] is False
    assert summary["run_records"][0]["auto_recovery_triggered"] is False
    assert all(row["measurement_control_plane"]["source"] == "measurement_control_plane" for row in summary["run_records"])
    assert all(row["measurement_control_plane"]["semantic_proof_satisfied"] is False for row in summary["run_records"])
    assert set(selected_bridge_urls) == {"http://bridge.test"}
    assert all(row["explore_settings"]["selected_bridge_url"] == "http://bridge.test" for row in summary["run_records"])
    assert (output_dir / "runs" / "01-session_bootstrap" / "measurement-control-plane.json").exists()
    assert report["support_targets"] == ["dispatch_preview", "fee_quote"]
    assert report["support_discovered_symbol_flow"] == [
        "SP_PrepareReleasePreview",
        "SP_StageReleaseFeeQuote",
    ]
    assert report["support_semantic_symbol_flow"] == [
        "SP_PrepareReleasePreview",
        "SP_StageReleaseFeeQuote",
    ]
    assert report["expected_shared_state"] == [
        "reservation_handle",
        "hold_token",
        "attestation_packet",
        "replay_attestation_packet",
    ]
    assert [row["chain_context"]["target_name"] for row in summary["run_records"]] == [
        "session_bootstrap",
        "reservation_stage",
        "dispatch_preview",
        "fee_quote",
        "attestation_stage",
        "release_commit",
        "replay_branch",
        "settlement_reconcile",
        "audit_trace",
    ]
    assert summary["run_records"][2]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][2]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][3]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][3]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][4]["chain_context"]["prior_job_id"] == "job-fee_quote"
    assert summary["run_records"][4]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-dispatch_preview",
        "job-fee_quote",
    ]
    assert summary["run_records"][5]["chain_context"]["prior_job_id"] == "job-reservation_stage"
    assert summary["run_records"][5]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert summary["run_records"][6]["chain_context"]["prior_job_id"] == "job-release_commit"
    assert summary["run_records"][6]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-release_commit",
    ]
    assert summary["run_records"][7]["chain_context"]["prior_job_id"] == "job-replay_branch"
    assert summary["run_records"][7]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-attestation_stage",
        "job-release_commit",
        "job-replay_branch",
    ]
    assert summary["run_records"][8]["chain_context"]["prior_job_id"] == "job-settlement_reconcile"
    assert summary["run_records"][8]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-attestation_stage",
        "job-release_commit",
        "job-replay_branch",
        "job-settlement_reconcile",
    ]
    assert output_dir == tmp_path / "out-hard01"


def test_run_spectrum_compiled_hard01_product_threads_product_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_hard01(**kwargs):
        observed.update(kwargs)
        return {
            "output_dir": str(tmp_path / "out-hard01-product"),
            "summary": {
                "case_id": SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID,
                "green_contract_level": "product_green",
                "product_green_eligible": False,
                "blocking_signal": "product_route_gap",
            },
            "report": {},
        }

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01_product.run_spectrum_compiled_hard01",
        fake_hard01,
    )

    result = run_spectrum_compiled_hard01_product(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-product",
        stop_after_first_failure=True,
    )

    assert result["summary"]["case_id"] == SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID
    assert observed["product_route_required"] is True
    assert observed["case_id"] == SPECTRUM_COMPILED_HARD01_PRODUCT_CASE_ID
    assert observed["variant_id"] == SPECTRUM_COMPILED_HARD01_PRODUCT_VARIANT_ID
    assert observed["stop_after_first_failure"] is True


def test_run_spectrum_compiled_hard01_routes_selected_configured_bridge(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)
    selected_target = manifest["selected_runtime_targets"][0]

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {"dlls": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ordered_spectrum_compiled_hard01_targets",
        lambda _manifest: [selected_target],
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.build_spectrum_compiled_hard01_report",
        lambda **kwargs: {
            "binary_ingest_proof_succeeded": False,
            "semantic_checkpoint_alignment_succeeded": False,
            "run_records": kwargs["run_records"],
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.write_enterprise_survivability_summary",
        lambda **kwargs: {"run_count": len(kwargs["run_records"])},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, f"bridge_ok:{bridge_url}"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_strict_local_lane_preflight",
        lambda **kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: {
            "freshness_verdict": "fresh",
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_bridge_freshness",
        lambda repo_root, bridge_url, bridge_key, campaign_log=None: {
            "freshness_verdict": "fresh",
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_runner_identity",
        lambda **kwargs: {
            "component": "runner",
            "runner_name": "run_spectrum_compiled_hard01",
            "runner_git_sha": "same-sha",
            "runner_dirty": False,
            "contract_version": "trust_contract_v1",
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_api_identity",
        lambda api_url, api_key, api_msg: {
            "component": "api",
            "git_sha": "same-sha",
            "dirty": False,
            "contract_version": "trust_contract_v1",
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: {
            "component": "bridge",
            "git_sha": "same-sha",
            "dirty": False,
            "contract_version": "trust_contract_v1",
            "capabilities": ["analyze"],
            "bridge_url": bridge_url,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.build_lane_readiness_packet",
        lambda **kwargs: {
            "ready": True,
            "lane_comparable": True,
            "blocking_reasons": [],
            "contract_version": "trust_contract_v1",
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True, "blocking_reasons": []},
    )

    def fake_bridge_readiness(bridge_url: str, bridge_key: str) -> dict:
        if bridge_url.endswith(":8091"):
            return {"ready": False, "capabilities": [], "blocking_reasons": ["bridge_down"]}
        return {"ready": True, "capabilities": ["analyze"], "blocking_reasons": []}

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.fetch_bridge_readiness",
        fake_bridge_readiness,
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    selected_urls: list[str] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        **kwargs,
    ):
        selected_urls.append(str(settings.get("selected_bridge_url") or ""))
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {"SP_OpenOperatorSession": "verified_success"},
            "valid_run": True,
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)
    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://127.0.0.1:8091",
        bridge_urls="http://127.0.0.1:8091,http://127.0.0.1:8092",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-multi-bridge",
    )

    summary = result["summary"]
    record = summary["run_records"][0]

    assert selected_urls == ["http://127.0.0.1:8092"]
    assert record["explore_settings"]["selected_bridge_url"] == "http://127.0.0.1:8092"
    assert record["measurement_control_plane"]["selected_candidate_id"] == "configured-bridge-2"
    assert record["measurement_control_plane"]["selected_bridge"]["url"] == "http://127.0.0.1:8092"


def test_run_spectrum_compiled_hard01_quarantined_target_fails_closed_without_run_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {"dlls": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.build_spectrum_compiled_hard01_report",
        lambda **kwargs: {
            "binary_ingest_proof_succeeded": False,
            "semantic_checkpoint_alignment_succeeded": False,
            "run_records": kwargs["run_records"],
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.write_enterprise_survivability_summary",
        lambda **kwargs: {"run_count": len(kwargs["run_records"])},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, f"bridge_ok:{bridge_url}"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: {
            "freshness_verdict": "fresh",
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_bridge_freshness",
        lambda repo_root, bridge_url, bridge_key, campaign_log=None: {
            "freshness_verdict": "fresh",
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_runner_identity",
        lambda **kwargs: {
            "component": "runner",
            "runner_name": "run_spectrum_compiled_hard01",
            "runner_git_sha": "same-sha",
            "runner_dirty": False,
            "contract_version": "trust_contract_v1",
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_api_identity",
        lambda api_url, api_key, api_msg: {
            "component": "api",
            "git_sha": "same-sha",
            "dirty": False,
            "contract_version": "trust_contract_v1",
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: {
            "component": "bridge",
            "git_sha": "same-sha",
            "dirty": False,
            "contract_version": "trust_contract_v1",
            "capabilities": ["analyze"],
            "bridge_url": bridge_url,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.build_lane_readiness_packet",
        lambda **kwargs: {
            "ready": True,
            "lane_comparable": True,
            "blocking_reasons": [],
            "contract_version": "trust_contract_v1",
        },
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    called_targets: list[str] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        **kwargs,
    ):
        called_targets.append(target_name)
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "latest_status_map": {"SP_OpenOperatorSession": "verified_success"},
            "valid_run": True,
            "authoritative_proving": True,
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)
    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    quarantine_registry = json.dumps(
        [
            {
                "bridge_url": "http://127.0.0.1:8090",
                "target": "reservation_stage",
                "analysis_profile": "strict_dll",
                "state": "active",
                "reason_code": "bridge_recent_no_heartbeat_stall",
                "observed_at": "2026-04-22T00:00:00+00:00",
                "next_action": "route around reservation_stage on this bridge",
            }
        ]
    )

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://127.0.0.1:8090",
        bridge_key="bridge-secret",
        bridge_quarantine_registry=quarantine_registry,
        output_root=tmp_path / "out-hard01-quarantine",
    )

    records = result["summary"]["run_records"]
    assert called_targets == ["session_bootstrap"]
    assert [row["chain_context"]["target_name"] for row in records] == [
        "session_bootstrap",
        "reservation_stage",
    ]
    assert records[0]["measurement_control_plane"]["light"] == "green"
    assert records[1]["measurement_control_plane"]["light"] == "quarantined"
    assert records[1]["measurement_control_plane"]["selection_reason"] == "no_non_quarantined_bridge_available"
    assert records[1]["phase"] == "control_plane_admission"
    assert records[1]["authoritative_proving"] is False
    assert records[1]["run_authority"]["authority_level"] == "non_authoritative"
    assert records[1]["measurement_terminalization"]["reason_code"] == "bridge_lane_quarantined"
    assert records[1]["dependent_chain_policy"] == "stop_dependent_chain_on_non_comparable_target"


def test_run_spectrum_compiled_hard01_does_not_count_functional_precondition_as_semantic_alignment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_replay_branch.dll", "exports": ["SP_ReplayReleaseBranch"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_SelectTrustedBranch"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_InvalidateUntrustedBranch"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "release_commit": "SP_CommitRelease",
        "replay_branch": "SP_ReplayReleaseBranch",
        "settlement_reconcile": "SP_SelectTrustedBranch",
        "audit_trace": "SP_InvalidateUntrustedBranch",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        status = "verified_success"
        if target_name == "audit_trace":
            status = "functional_precondition_unmet"
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "latest_status_map": {symbol_lookup[target_name]: status},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-functional",
    )

    report = result["report"]
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is False
    assert report["semantic_checkpoint_gap"] == ["SP_InvalidateUntrustedBranch"]
    assert report["per_run"][-1]["semantic_checkpoint_match"] is False
    assert report["branch_trust_observer"]["observer_status"] == "warn"
    assert report["branch_invalidation_authority"]["authority_present"] is False
    assert report["branch_invalidation_authority"]["blocking_signal"] == "branch_invalidation_authority_missing"
    assert report["branch_invalidation_authority"]["reason_code"] in {
        "branch_invalidation_call_missing",
        "branch_invalidation_not_verified",
    }


def test_run_spectrum_compiled_hard01_prefers_verified_branch_trust_output_over_findings_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_replay_branch.dll", "exports": ["SP_ReplayReleaseBranch"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_SelectTrustedBranch"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_InvalidateUntrustedBranch"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    freshness = {
        "freshness_verdict": "fresh",
        "restart_required": False,
        "restart_performed": False,
        "api_process": {"pid": 111},
    }
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: freshness,
    )
    freshness = {
        "freshness_verdict": "fresh",
        "restart_required": False,
        "restart_performed": False,
        "api_process": {"pid": 111},
    }
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: freshness,
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "release_commit": "SP_CommitRelease",
        "replay_branch": "SP_ReplayReleaseBranch",
        "settlement_reconcile": "SP_SelectTrustedBranch",
        "audit_trace": "SP_InvalidateUntrustedBranch",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        if target_name == "settlement_reconcile":
            (run_dir / "findings.json").write_text(
                json.dumps(
                    [
                        {
                            "function": "SP_SelectTrustedBranch",
                            "working_call": {
                                "primary_commit_receipt": "sp-commit-GDG-SM-RED",
                                "replay_commit_receipt": "sp-branch-replay-ACC-USB-C",
                                "out_trusted_branch_id": "CUST-001",
                                "out_rejected_branch_id": "CUST-004",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "session" / "verification-report.json").write_text(
                json.dumps(
                    {
                        "verified_count": 1,
                        "entries": [
                            {
                                "function": "SP_SelectTrustedBranch",
                                "verification": "verified",
                                "result": "Returned: 0\nout_trusted_branch_id='sp-branch-primary'\nout_rejected_branch_id='sp-branch-replay'",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        record = {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }
        if target_name == "replay_branch":
            record["latest_status_map"] = {symbol_lookup[target_name]: "failure"}
        if target_name == "audit_trace":
            record["valid_run"] = False
        return record

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-branch-trust-observer",
    )

    observer = result["report"]["branch_trust_observer"]
    assert observer["trusted_branch_id"] == "primary"
    assert observer["rejected_branch_ids"] == ["replay"]
    assert observer["observer_status"] == "warn"
    assert "before replay provenance was semantically resolved" in observer["decision_reason"]


def test_run_spectrum_compiled_hard01_does_not_count_nonterminal_verified_status_as_semantic_alignment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_replay_branch.dll", "exports": ["SP_ReplayReleaseBranch"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_SelectTrustedBranch"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_InvalidateUntrustedBranch"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "release_commit": "SP_CommitRelease",
        "replay_branch": "SP_ReplayReleaseBranch",
        "settlement_reconcile": "SP_SelectTrustedBranch",
        "audit_trace": "SP_InvalidateUntrustedBranch",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        record = {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }
        if target_name == "attestation_stage":
            record["phase"] = "awaiting_clarification"
            record["verdict"] = {}
            record["job_status_snapshot"] = {"status": "running"}
        return record

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-nonterminal",
    )

    report = result["report"]
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is False
    assert report["semantic_checkpoint_gap"] == ["SP_EmitReleaseAttestation"]
    assert report["per_run"][4]["semantic_checkpoint_match"] is False


def test_run_spectrum_compiled_hard01_does_not_promote_invalid_release_commit_as_trusted_predecessor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_replay_branch.dll", "exports": ["SP_ReplayReleaseBranch"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_SelectTrustedBranch"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_InvalidateUntrustedBranch"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "release_commit": "SP_CommitRelease",
        "replay_branch": "SP_ReplayReleaseBranch",
        "settlement_reconcile": "SP_SelectTrustedBranch",
        "audit_trace": "SP_InvalidateUntrustedBranch",
    }
    captured_settings: dict[str, dict[str, Any]] = {}

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        captured_settings[target_name] = dict(settings)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        record = {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }
        if target_name == "release_commit":
            record["valid_run"] = False
        return record

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-predecessor-gate",
    )

    assert captured_settings["replay_branch"]["prior_job_id"] == ""
    assert captured_settings["replay_branch"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
    ]
    assert captured_settings["settlement_reconcile"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-attestation_stage",
        "job-replay_branch",
    ]


def test_run_spectrum_compiled_hard01_passes_comparable_lane_readiness_to_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)
    same_sha = "same-sha"

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_replay_branch.dll", "exports": ["SP_ReplayReleaseBranch"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_SelectTrustedBranch"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_InvalidateUntrustedBranch"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: {
            "freshness_verdict": "fresh",
            "restart_required": False,
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_bridge_freshness",
        lambda repo_root, bridge_url, bridge_key, campaign_log=None: {
            "freshness_verdict": "fresh",
            "restart_required": False,
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_runner_identity",
        lambda **kwargs: {
            "component": "runner",
            "runner_name": "run_spectrum_compiled_hard01",
            "runner_git_sha": same_sha,
            "runner_dirty": False,
            "contract_version": "trust_contract_v1",
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_api_identity",
        lambda api_url, api_key, api_msg: {
            "component": "api",
            "role": "pipeline_control_plane",
            "contract_version": "trust_contract_v1",
            "pipeline_schema_version": "handoff_contract_v1.0.0",
            "status_schema_version": "job_status_v1",
            "git_sha": same_sha,
            "dirty": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: {
            "component": "bridge",
            "role": "execution_bridge",
            "contract_version": "trust_contract_v1",
            "capabilities": ["analyze", "execute", "flush_dll_cache"],
            "git_sha": same_sha,
            "dirty": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True, "blocking_reasons": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True, "capabilities": ["analyze"], "blocking_reasons": []},
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "release_commit": "SP_CommitRelease",
        "replay_branch": "SP_ReplayReleaseBranch",
        "settlement_reconcile": "SP_SelectTrustedBranch",
        "audit_trace": "SP_InvalidateUntrustedBranch",
    }
    observed_readiness: list[dict] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
        lane_readiness=None,
    ):
        observed_readiness.append(dict(lane_readiness or {}))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "authoritative_proving": True,
            "failure_domain": "",
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-comparable-lane",
    )

    assert observed_readiness
    assert all(item["ready"] is True for item in observed_readiness)
    assert all(item["lane_comparable"] is True for item in observed_readiness)
    assert result["summary"]["lane_identity"]["comparable"] is True
    assert result["summary"]["lane_readiness"]["ready"] is True
    assert result["summary"]["measurement_control_plane"]["semantic_proof_satisfied"] is False
    assert result["summary"]["measurement_control_plane"]["registry_schema"] == "bridge_candidate_registry_v1"
    assert result["summary"]["measurement_control_plane"]["reason_code"] == "green_lane_admitted"
    assert result["summary"]["measurement_control_plane"]["light"] == "green"
    assert result["summary"]["run_records"][0]["measurement_control_plane"]["semantic_proof_satisfied"] is False
    assert result["summary"]["run_records"][0]["measurement_control_plane"]["registry_schema"] == "bridge_candidate_registry_v1"
    assert result["summary"]["run_records"][0]["measurement_control_plane"]["reason_code"] == "green_lane_admitted"
    reservation_record = next(
        row for row in result["summary"]["run_records"] if row["chain_context"]["target_name"] == "reservation_stage"
    )
    assert reservation_record["measurement_control_plane"]["reason_code"] == "green_lane_admitted"
    assert reservation_record["measurement_control_plane"]["light"] == "green"
    assert reservation_record["measurement_control_plane"]["selected_candidate_id"] == "configured-local-bridge"
    assert result["summary"]["run_records"][0]["run_authority"]["authority_level"] == "decision_bearing"


def test_run_spectrum_compiled_hard01_uses_current_run_authority_over_stale_bridge_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True, "blocking_reasons": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True, "capabilities": ["analyze"], "blocking_reasons": []},
    )

    def bridge_health(target_name, analysis_profile):
        if target_name == "reservation_stage":
            return {
                "source": "test",
                "status": "recent_stall",
                "reason_code": "bridge_recent_no_heartbeat_stall",
                "stream_health_known": True,
                "recent_signals": ["bridge_stream_no_heartbeat"],
            }
        return {
            "source": "test",
            "status": "coherent",
            "reason_code": "bridge_stream_health_coherent",
            "stream_health_known": True,
            "recent_signals": [],
        }

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.hard_family_bridge_stream_health_for_target",
        bridge_health,
    )
    trace_path = tmp_path / "hard01-trace.jsonl"
    monkeypatch.setenv("MCP_FACTORY_PRODUCT_TRACE_ID", "trace-hard01-test")
    monkeypatch.setenv("MCP_FACTORY_PRODUCT_TRACE_PATH", str(trace_path))

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    observed_targets: list[str] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
        lane_readiness=None,
    ):
        observed_targets.append(target_name)
        required_symbol = str(settings.get("required_semantic_checkpoint") or target_name)
        run_dir.mkdir(parents=True, exist_ok=True)
        session_dir = run_dir / "session"
        static_dir = session_dir / "evidence" / "stage-00b-static-evidence"
        static_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": required_symbol, "kind": "export"}]}}),
            encoding="utf-8",
        )
        (session_dir / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (session_dir / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        (session_dir / "discovery_meta.json").write_text(
            json.dumps({"bridge_reachable": True, "analysis_profile": "strict_dll"}),
            encoding="utf-8",
        )
        (session_dir / "invocables_map.json").write_text(
            json.dumps({required_symbol: {"name": required_symbol, "source_type": "ghidra_export"}}),
            encoding="utf-8",
        )
        (static_dir / "ghidra-data-types.json").write_text(json.dumps({"types": []}), encoding="utf-8")
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "authoritative_proving": True,
            "failure_domain": "",
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "safe_to_compare": True,
            "job_terminalization": {
                "terminal": True,
                "terminalization_kind": "done",
                "kind": "done",
            },
            "latest_status_map": {required_symbol: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-yellow",
        product_route_required=True,
    )

    assert observed_targets[:2] == ["session_bootstrap", "reservation_stage"]
    reservation_record = next(
        row for row in result["summary"]["run_records"] if row["chain_context"]["target_name"] == "reservation_stage"
    )
    assert reservation_record["measurement_control_plane"]["light"] == "green"
    assert reservation_record["measurement_control_plane"]["registry_schema"] == "bridge_candidate_registry_v1"
    assert reservation_record["measurement_control_plane"]["selected_candidate_id"] == "configured-local-bridge"
    assert reservation_record["run_authority"]["authority_level"] == "decision_bearing"
    assert reservation_record["authoritative_proving"] is True
    assert "measurement_terminalization" not in reservation_record
    assert result["report"]["binary_ingest_proof_succeeded"] is True
    assert result["report"]["semantic_checkpoint_alignment_succeeded"] is True
    trace_events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    control_plane_events = [event for event in trace_events if event["span_name"] == "hard01.control_plane"]
    assert any(
        event["attributes"]["target"] == "reservation_stage"
        and event["attributes"]["phase"] == "pre_run"
        and event["attributes"]["reason_code"] == "bridge_recent_no_heartbeat_stall"
        and event["attributes"]["current_run_evidence"] is False
        for event in control_plane_events
    )
    assert any(
        event["attributes"]["target"] == "reservation_stage"
        and event["attributes"]["phase"] == "post_run"
        and event["attributes"]["reason_code"] == "green_lane_admitted"
        and event["attributes"]["current_run_evidence"] is True
        for event in control_plane_events
    )


def test_run_spectrum_compiled_hard01_retries_first_leg_once_after_restart_stall(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard01_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_release_commit.dll", "exports": ["SP_CommitRelease"]},
                {"dll_name": "spectrum_replay_branch.dll", "exports": ["SP_ReplayReleaseBranch"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_SelectTrustedBranch"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_InvalidateUntrustedBranch"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        _authored_hard01_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )

    freshness = {
        "freshness_verdict": "restart_required_code_newer",
        "restart_required": True,
        "restart_performed": True,
        "api_process": {"pid": 111},
    }
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: freshness,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.run_post_restart_readiness_probe",
        lambda *args, **kwargs: {
            "performed": True,
            "ready": True,
            "verdict": "ready",
            "authoritative_or_not": True,
        },
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.ApiClient", FakeClient)

    relaunch_calls: list[str] = []
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.relaunch_local_api_lane",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: relaunch_calls.append(api_url) or {
            "restart_performed": True
        },
    )

    call_counts: dict[str, int] = {}
    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "release_commit": "SP_CommitRelease",
        "replay_branch": "SP_ReplayReleaseBranch",
        "settlement_reconcile": "SP_SelectTrustedBranch",
        "audit_trace": "SP_InvalidateUntrustedBranch",
    }
    selected_bridge_urls: list[str] = []

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        call_counts[target_name] = call_counts.get(target_name, 0) + 1
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}-{call_counts[target_name]}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        if target_name == "session_bootstrap" and call_counts[target_name] == 1:
            return {
                "job_id": "job-session_bootstrap-1",
                "status": "failed",
                "phase": "awaiting_clarification",
                "authoritative_proving": False,
                "failure_domain": "pipeline",
                "run_authority": {
                    "authority_level": "non_authoritative",
                    "authoritative_proving": False,
                    "failure_domain": "pipeline",
                    "safe_to_steer_next_prompt": False,
                },
                "runner_terminalization": {"kind": "quasi_terminal_clarify_stall"},
                "latest_status_map": {},
            }
        return {
            "job_id": f"job-{target_name}-{call_counts[target_name]}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "authoritative_proving": True,
            "failure_domain": "",
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard01.run_one", fake_run_one)

    result = run_spectrum_compiled_hard01(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard01-retry",
    )

    summary = result["summary"]
    assert summary["post_restart_readiness"]["performed"] is True
    assert summary["post_restart_first_leg_recovery"]["auto_recovery_triggered"] is True
    assert summary["post_restart_first_leg_recovery"]["auto_recovery_attempts"] == 1
    assert summary["post_restart_first_leg_recovery"]["final_recovery_verdict"] == "recovered"
    assert summary["run_records"][0]["first_leg_after_restart"] is True
    assert summary["run_records"][0]["auto_recovery_triggered"] is True
    assert summary["run_records"][0]["run_authority"]["authority_level"] == "decision_bearing"
    assert len(summary["run_records"][0]["post_restart_attempts"]) == 2
    assert call_counts["session_bootstrap"] == 2
    assert relaunch_calls == ["http://api.test"]


def test_run_spectrum_compiled_hard02_writes_chain_aware_proof_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _hard02_package_manifest(tmp_path)

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.load_spectrum_compiled_truth_manifest",
        lambda: {
            "dlls": [
                {"dll_name": "spectrum_session_bootstrap.dll", "exports": ["SP_OpenOperatorSession"]},
                {"dll_name": "spectrum_reservation_stage.dll", "exports": ["SP_IssueReleaseHold"]},
                {"dll_name": "spectrum_dispatch_preview.dll", "exports": ["SP_PrepareReleasePreview"]},
                {"dll_name": "spectrum_fee_quote.dll", "exports": ["SP_StageReleaseFeeQuote"]},
                {"dll_name": "spectrum_attestation_stage.dll", "exports": ["SP_EmitReleaseAttestation"]},
                {"dll_name": "spectrum_invoice_sync.dll", "exports": ["SP_StageReleaseInvoice"]},
                {"dll_name": "spectrum_entitlement_sync.dll", "exports": ["SP_StageCustomerEntitlementUpdate"]},
                {"dll_name": "spectrum_settlement_reconcile.dll", "exports": ["SP_InvalidateStaleAttestedRelease"]},
                {"dll_name": "spectrum_audit_trace.dll", "exports": ["SP_RecordStaleAttestationInvalidation"]},
            ]
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": SPECTRUM_COMPILED_SUITE_ID},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.load_spectrum_authored_hard02_manifest",
        _authored_hard02_manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    freshness = {
        "freshness_verdict": "fresh",
        "restart_required": False,
        "restart_performed": False,
        "api_process": {"pid": 222},
    }
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: freshness,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True, "capabilities": ["analyze"]},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.hard_family_bridge_stream_health_for_target",
        lambda target_name, analysis_profile: (
            {
                "source": "test",
                "status": "unproven",
                "reason_code": "bridge_stream_health_unproven",
                "stream_health_known": False,
                "recent_signals": [],
            }
            if target_name == "dispatch_preview"
            else {
                "source": "test",
                "status": "coherent",
                "reason_code": "bridge_stream_health_coherent",
                "stream_health_known": True,
                "recent_signals": [],
            }
        ),
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard02.ApiClient", FakeClient)

    symbol_lookup = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
        "dispatch_preview": "SP_PrepareReleasePreview",
        "fee_quote": "SP_StageReleaseFeeQuote",
        "attestation_stage": "SP_EmitReleaseAttestation",
        "invoice_sync": "SP_StageReleaseInvoice",
        "entitlement_sync": "SP_StageCustomerEntitlementUpdate",
        "settlement_reconcile": "SP_InvalidateStaleAttestedRelease",
        "audit_trace": "SP_RecordStaleAttestationInvalidation",
    }

    def fake_run_one(
        client,
        repo_root,
        run_dir,
        api_url,
        api_key,
        target_name,
        dll_path,
        variant_name,
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        snapshot_profile,
        heartbeat_path,
        campaign_log=None,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": symbol_lookup[target_name], "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target_name}"}), encoding="utf-8"
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}), encoding="utf-8"
        )
        return {
            "job_id": f"job-{target_name}",
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "verdict": {"status": "done"},
            "job_status_snapshot": {"status": "done"},
            "failure_domain": "",
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "latest_status_map": {symbol_lookup[target_name]: "verified_success"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_hard02.run_one", fake_run_one)

    result = run_spectrum_compiled_hard02(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-hard02",
    )

    output_dir = Path(result["output_dir"])
    summary = json.loads((output_dir / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))

    assert summary["case_id"] == SPECTRUM_COMPILED_HARD02_CASE_ID
    assert summary["api_freshness"] == freshness
    assert summary["post_restart_readiness"]["performed"] is False
    assert summary["post_restart_first_leg_recovery"]["armed"] is False
    assert summary["lane_identity"]["runner_identity"]["runner_name"] == "run_spectrum_compiled_hard02"
    assert summary["lane_identity"]["api_identity"]["component"] == "api"
    assert summary["lane_identity"]["bridge_identity"]["component"] == "bridge"
    assert summary["lane_readiness"]["ready"] is True
    assert summary["measurement_control_plane"]["source"] == "measurement_control_plane"
    assert summary["measurement_control_plane"]["registry_schema"] == "bridge_candidate_registry_v1"
    assert summary["measurement_control_plane"]["target"] == SPECTRUM_COMPILED_HARD02_CASE_ID
    assert summary["measurement_control_plane"]["required_capabilities"] == ["analyze"]
    assert summary["measurement_control_plane"]["reason_code"] == "green_lane_admitted"
    assert summary["measurement_control_plane"]["light"] == "green"
    assert summary["measurement_control_plane"]["semantic_proof_satisfied"] is False
    assert summary["run_records"][0]["run_authority"]["authority_level"] == "decision_bearing"
    assert all(row["measurement_control_plane"]["source"] == "measurement_control_plane" for row in summary["run_records"])
    assert all(row["measurement_control_plane"]["semantic_proof_satisfied"] is False for row in summary["run_records"])
    reservation_record = next(
        row for row in summary["run_records"] if row["chain_context"]["target_name"] == "reservation_stage"
    )
    assert reservation_record["measurement_control_plane"]["reason_code"] == "green_lane_admitted"
    assert reservation_record["measurement_control_plane"]["light"] == "green"
    assert reservation_record["measurement_control_plane"]["selected_candidate_id"] == "configured-local-bridge"
    dispatch_record = next(
        row for row in summary["run_records"] if row["chain_context"]["target_name"] == "dispatch_preview"
    )
    assert dispatch_record["pre_run_measurement_control_plane"]["reason_code"] == "bridge_stream_health_unproven"
    assert dispatch_record["current_run_bridge_stream_health"]["reason_code"] == "bridge_stream_health_coherent"
    assert dispatch_record["measurement_control_plane"]["reason_code"] == "green_lane_admitted"
    assert dispatch_record["measurement_control_plane"]["light"] == "green"
    assert dispatch_record["measurement_control_plane"]["pre_run_control_plane"]["reason_code"] == "bridge_stream_health_unproven"
    assert "measurement_terminalization" not in dispatch_record
    assert (output_dir / "lane-identity.json").exists()
    assert (output_dir / "lane-readiness.json").exists()
    assert (output_dir / "measurement-control-plane.json").exists()
    assert (output_dir / "runs" / "01-session_bootstrap" / "measurement-control-plane.json").exists()
    assert report["case_id"] == SPECTRUM_COMPILED_HARD02_CASE_ID
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is True
    assert report["per_run"][0]["run_authority"]["authority_level"] == "decision_bearing"
    assert report["expected_symbol_flow"] == [
        "SP_OpenOperatorSession",
        "SP_IssueReleaseHold",
        "SP_EmitReleaseAttestation",
        "SP_StageReleaseInvoice",
        "SP_StageCustomerEntitlementUpdate",
        "SP_InvalidateStaleAttestedRelease",
        "SP_RecordStaleAttestationInvalidation",
    ]
    assert report["support_targets"] == ["dispatch_preview", "fee_quote"]
    assert report["expected_current_failure_mode"] == (
        "stale attestation remains admissible after freshness should have invalidated it"
    )
    assert report["missing_system_candidate"] == (
        "freshness-aware lineage observer and stale-state provenance evidence"
    )
    assert summary["run_records"][0]["chain_context"]["prior_job_id"] == ""
    assert summary["run_records"][4]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-dispatch_preview",
        "job-fee_quote",
    ]
    assert summary["run_records"][7]["chain_context"]["cross_dll_prior_job_ids"] == [
        "job-session_bootstrap",
        "job-reservation_stage",
        "job-attestation_stage",
        "job-invoice_sync",
        "job-entitlement_sync",
    ]
    assert summary["run_records"][5]["chain_context"]["prior_job_id"] == "job-attestation_stage"
    assert summary["run_records"][8]["chain_context"]["prior_job_id"] == "job-settlement_reconcile"


def test_spectrum_compiled_hard03_chain_adds_unsupported_target_quarantine() -> None:
    assert [step["target_name"] for step in SPECTRUM_COMPILED_HARD03_CHAIN_PLAN][-2:] == [
        "quarantine_gate",
        "quarantine_audit",
    ]
    assert [step["required_semantic_checkpoint"] for step in SPECTRUM_COMPILED_HARD03_CHAIN_PLAN][-2:] == [
        "SP_QuarantineUnsupportedTarget",
        "SP_RecordUnsupportedTargetQuarantine",
    ]
    assert SPECTRUM_COMPILED_HARD03_CASE_ID == "hard-03"


def test_spectrum_compiled_hard03_report_tracks_quarantine_authority_flow(tmp_path: Path) -> None:
    manifest = _hard03_package_manifest(tmp_path)
    compiled_targets = ordered_spectrum_compiled_hard03_targets(manifest)
    truth_manifest = {"dlls": []}
    run_records = []
    for index, target in enumerate(compiled_targets, start=1):
        run_dir = tmp_path / "runs" / f"{index:02d}-{target['target_name']}"
        (run_dir / "session").mkdir(parents=True, exist_ok=True)
        function_name = str(target["required_semantic_checkpoint"])
        (run_dir / "job-status-analyze.json").write_text(
            json.dumps({"result": {"invocables": [{"name": function_name, "kind": "export"}]}}),
            encoding="utf-8",
        )
        (run_dir / "session" / "session-meta.json").write_text(
            json.dumps({"job_id": f"job-{target['target_name']}"}),
            encoding="utf-8",
        )
        (run_dir / "session" / "stage-index.json").write_text(
            json.dumps({"stages": ["discover", "explore"]}),
            encoding="utf-8",
        )
        truth_manifest["dlls"].append(
            {"dll_name": target["staged_name"], "exports": [function_name]}
        )
        run_records.append(
            {
                "run_dir": str(run_dir),
                "dll_name": target["staged_name"],
                "job_id": f"job-{target['target_name']}",
                "binary_hash": "abc",
                "valid_run": True,
                "phase": "done",
                "verdict": {"status": "done"},
                "job_status_snapshot": {"status": "done"},
                "latest_status_map": {function_name: "verified_success"},
                "run_authority": {
                    "authority_level": "decision_bearing",
                    "authoritative_proving": True,
                    "safe_to_steer_next_prompt": True,
                },
                "measurement_control_plane": {"safe_to_compare": True, "light": "green"},
            }
        )

    report = build_spectrum_compiled_hard03_report(
        output_dir=tmp_path,
        package_manifest=manifest,
        compiled_truth_manifest=truth_manifest,
        authored_truth_manifest={"suite_id": SPECTRUM_COMPILED_SUITE_ID},
        authored_hard_manifest=_authored_hard03_manifest(),
        run_records=run_records,
    )

    assert report["case_id"] == SPECTRUM_COMPILED_HARD03_CASE_ID
    assert report["expected_primary_blocker_family"] == "object_bound_corrective_authority"
    assert report["binary_ingest_proof_succeeded"] is True
    assert report["semantic_checkpoint_alignment_succeeded"] is True
    assert report["expected_symbol_flow"][-2:] == [
        "SP_QuarantineUnsupportedTarget",
        "SP_RecordUnsupportedTargetQuarantine",
    ]


def test_hard02_runner_recovers_finalized_s07_artifacts_from_job_store(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setitem(_recover_finalized_target_from_job_store.__globals__, "REPO_ROOT", tmp_path)
    job_dir = tmp_path / "local-data" / "artifacts" / "job-session"
    (job_dir / "checkpoints").mkdir(parents=True)
    (job_dir / "findings.json").write_text(
        json.dumps(
            [
                {
                    "function": "SP_OpenOperatorSession",
                    "status_canonical": "verified_success",
                    "working_call": {
                        "operator_id": "easy01-operator",
                        "out_operator_token": "sp-operator-easy01-operator-session",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "checkpoints" / "s07_finalize.json").write_text(
        json.dumps({"completed": True}),
        encoding="utf-8",
    )

    run_dir = tmp_path / "run"
    recovery = _recover_finalized_target_from_job_store(
        run_dir=run_dir,
        job_id="job-session",
        required_semantic_checkpoint="SP_OpenOperatorSession",
    )

    assert recovery["decision_bearing_recovery"] is True
    assert recovery["required_checkpoint_status_canonical"] == "verified_success"
    assert (run_dir / "findings.json").exists()


def test_hard02_runner_promotes_recovered_record_without_product_semantic_reinterpretation(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    record = {
        "job_id": "job-session",
        "status": "failed",
        "phase": "exploring",
        "measurement_terminalization": {"reason_code": "runner_observed_nonterminal_timeout"},
    }
    control_plane = {
        "light": "yellow",
        "status": "diagnostic_only",
        "reason_code": "runner_observed_nonterminal_timeout",
        "blocking_reasons": ["runner_observed_nonterminal_timeout"],
        "safe_to_compare": False,
    }

    promoted = _promote_recovered_finalized_record(
        run_dir=run_dir,
        record=record,
        control_plane=control_plane,
        recovery={
            "decision_bearing_recovery": True,
            "source": "local_job_artifact_store",
            "s07_finalize_completed": True,
            "required_checkpoint_status_canonical": "verified_success",
        },
    )

    assert promoted["status"] == "ok"
    assert promoted["phase"] == "done"
    assert promoted["authoritative_proving"] is True
    assert promoted["terminalization_recovered"] is True
    assert "measurement_terminalization" not in promoted
    assert promoted["measurement_control_plane"]["reason_code"] == "current_run_s07_finalize_recovered"
    assert (run_dir / "run-authority.json").exists()


def test_run_spectrum_compiled_hard01_falls_back_to_repo_env_for_bridge_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MCP_FACTORY_API_KEY", "")
    monkeypatch.setenv("GUI_BRIDGE_URL", "")
    monkeypatch.setenv("GUI_BRIDGE_SECRET", "")
    monkeypatch.setenv("BRIDGE_SECRET", "")
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_spectrum_compiled_package_built",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_compiled_truth_manifest",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_truth_manifest",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.load_spectrum_authored_hard01_manifest",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.resolve_api_url",
        lambda api_url, api_key, verify_identity=None: ("http://api.test", "api_ok:test", "explicit"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: {"freshness_verdict": "fresh", "restart_performed": False},
    )
    captured: dict[str, str] = {}

    def fake_load_repo_env(name: str) -> str:
        mapping = {
            "PIPELINE_API_KEY": "api-from-env",
            "GUI_BRIDGE_URL": "http://bridge.from.env",
            "GUI_BRIDGE_SECRET": "bridge-secret-from-env",
            "BRIDGE_SECRET": "bridge-secret-from-env",
        }
        return mapping.get(name, "")

    def fake_bridge_freshness(repo_root, bridge_url, bridge_key, campaign_log=None):
        captured["bridge_url"] = bridge_url
        captured["bridge_key"] = bridge_key
        raise RuntimeError("stop_after_bridge_freshness")

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01._load_repo_env_value",
        fake_load_repo_env,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard01.ensure_local_bridge_freshness",
        fake_bridge_freshness,
    )

    with pytest.raises(RuntimeError, match="stop_after_bridge_freshness"):
        run_spectrum_compiled_hard01()

    assert captured == {
        "bridge_url": "http://bridge.from.env",
        "bridge_key": "bridge-secret-from-env",
    }


def test_run_spectrum_compiled_hard02_falls_back_to_repo_env_for_bridge_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MCP_FACTORY_API_KEY", "")
    monkeypatch.setenv("GUI_BRIDGE_URL", "")
    monkeypatch.setenv("GUI_BRIDGE_SECRET", "")
    monkeypatch.setenv("BRIDGE_SECRET", "")
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.ensure_spectrum_compiled_package_built",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.load_spectrum_compiled_truth_manifest",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.load_spectrum_authored_truth_manifest",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.load_spectrum_authored_hard02_manifest",
        lambda: {},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.resolve_api_url",
        lambda api_url, api_key, verify_identity=None: ("http://api.test", "api_ok:test", "explicit"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, **kwargs: {"freshness_verdict": "fresh", "restart_performed": False},
    )
    captured: dict[str, str] = {}

    def fake_load_repo_env(name: str) -> str:
        mapping = {
            "PIPELINE_API_KEY": "api-from-env",
            "GUI_BRIDGE_URL": "http://bridge.from.env",
            "GUI_BRIDGE_SECRET": "bridge-secret-from-env",
            "BRIDGE_SECRET": "bridge-secret-from-env",
        }
        return mapping.get(name, "")

    def fake_bridge_freshness(repo_root, bridge_url, bridge_key, campaign_log=None):
        captured["bridge_url"] = bridge_url
        captured["bridge_key"] = bridge_key
        raise RuntimeError("stop_after_bridge_freshness")

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02._load_repo_env_value",
        fake_load_repo_env,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_hard02.ensure_local_bridge_freshness",
        fake_bridge_freshness,
    )

    with pytest.raises(RuntimeError, match="stop_after_bridge_freshness"):
        run_spectrum_compiled_hard02()

    assert captured == {
        "bridge_url": "http://bridge.from.env",
        "bridge_key": "bridge-secret-from-env",
    }
