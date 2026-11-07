from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.cluster_checkpoint import CLUSTER_CHECKPOINTS_BY_ID
from api.pipeline.core.interwoven_artifacts import (
    DEFAULT_INTERWOVEN_ARTIFACT_PLACEMENT,
    INTERWOVEN_CANONICAL_ARTIFACTS,
    INTERWOVEN_SUMMARY_ONLY_ARTIFACTS,
    InterwovenProducerConsumerReport,
    InterwovenSharedStateReport,
)
from api.pipeline.core.prerequisite_state_groups import PREREQUISITE_STATE_GROUPS_BY_ID


ROOT = Path(__file__).resolve().parent.parent


def _load_manifest(fixture_name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / fixture_name / "truth_manifest.json").read_text(encoding="utf-8"))


def test_producer_consumer_report_round_trips_for_config_to_reporting_seam() -> None:
    config = _load_manifest("contoso_config")
    reporting = _load_manifest("contoso_reporting")

    assert PREREQUISITE_STATE_GROUPS_BY_ID["config_licensed_ticket_bootstrap"].group_id == "config_licensed_ticket_bootstrap"
    assert CLUSTER_CHECKPOINTS_BY_ID["config_approval_license"].cluster_id == "config_approval_license"
    assert CLUSTER_CHECKPOINTS_BY_ID["reporting_preview_render_export"].cluster_id == "reporting_preview_render_export"
    assert any(item["name"] == "CFG_ApproveLicensedCall" for item in config["functions"])
    assert any(item["name"] == "RP_ExportLedger" for item in reporting["functions"])

    report = InterwovenProducerConsumerReport(
        family="config_ticket_nonce_to_reporting_export",
        producer_id="config_approval_license:CFG_ApproveLicensedCall",
        producer_kind="producer",
        consumer_id="reporting_preview_render_export:RP_ExportLedger",
        consumer_kind="consumer",
        state_tokens=("ticket", "nonce"),
        evidence_edges=(
            "CFG_ApproveLicensedCall->RP_PrepareReservationReport",
            "CFG_GetLicenseNonce->RP_ExportLedger",
        ),
        dependency_mode="shared_state_mediated",
        confidence=0.84,
        contradiction_state="none",
    )

    restored = InterwovenProducerConsumerReport.from_dict(report.to_dict())

    assert restored == report
    assert restored.state_tokens == ("ticket", "nonce")
    assert restored.observer_verdict == ""


def test_shared_state_report_round_trips_for_events_mask_reuse() -> None:
    events = _load_manifest("contoso_events")
    assert any(item["name"] == "EV_ReplayMask" for item in events["functions"])

    report = InterwovenSharedStateReport(
        carrier_id="events_session_mask",
        carrier_kind="shared_state_carrier",
        state_tokens=("dwEventSession", "dwEventMask"),
        downstream_consumers=("EV_RegisterMask", "EV_ReplayMask"),
        exporting_seams=("EV_OpenEventSession",),
        importing_seams=("EV_RegisterMask", "EV_ReplayMask"),
        staleness_risk="low",
        confidence=0.81,
        contradiction_state="none",
    )

    restored = InterwovenSharedStateReport.from_dict(report.to_dict())

    assert restored == report
    assert restored.downstream_consumers == ("EV_RegisterMask", "EV_ReplayMask")


def test_interwoven_artifact_defaults_keep_prompt00_session_scoped() -> None:
    assert set(INTERWOVEN_CANONICAL_ARTIFACTS) == {
        "interwoven-producer-consumer-report.json",
        "interwoven-shared-state-report.json",
        "interwoven-staged-chain-report.json",
    }
    assert INTERWOVEN_SUMMARY_ONLY_ARTIFACTS == ("interwoven-observer-summary.json",)
    assert DEFAULT_INTERWOVEN_ARTIFACT_PLACEMENT["canonical_scope"] == "session_only"
    assert DEFAULT_INTERWOVEN_ARTIFACT_PLACEMENT["campaign_projection"] is False
    assert DEFAULT_INTERWOVEN_ARTIFACT_PLACEMENT["ledger_projection"] is False
    assert DEFAULT_INTERWOVEN_ARTIFACT_PLACEMENT["collector_projection"] is False
