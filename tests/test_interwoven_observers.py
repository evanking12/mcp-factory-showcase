from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.interwoven_artifacts import (
    InterwovenProducerConsumerReport,
    InterwovenSharedStateReport,
)
from api.pipeline.core.interwoven_observers import (
    INTERWOVEN_OBSERVER_NAMES,
    build_interwoven_state_staleness_risk_observer,
    build_producer_consumer_plausibility_observer,
    build_shared_state_reuse_plausibility_observer,
)


ROOT = Path(__file__).resolve().parent.parent


def _manifest_path(fixture_name: str) -> str:
    return str(ROOT / "tests" / "fixtures" / fixture_name / "truth_manifest.json")


def test_producer_consumer_observer_passes_for_first_config_to_pricing_seam() -> None:
    report = InterwovenProducerConsumerReport(
        family="config_customer_ticket_nonce_to_pricing_quote",
        producer_id="config_approval_license:CFG_ApproveLicensedCall",
        producer_kind="producer",
        consumer_id="pricing_quote_lifecycle:PR_SealQuote",
        consumer_kind="consumer",
        state_tokens=("customer_id", "ticket", "nonce"),
        evidence_edges=(
            "CFG_ApproveLicensedCall->PR_BeginQuote",
            "CFG_GetLicenseNonce->PR_SealQuote",
        ),
        dependency_mode="shared_state_mediated",
        confidence=0.88,
        contradiction_state="none",
    )

    observer = build_producer_consumer_plausibility_observer(
        report,
        canonical_sources=(
            _manifest_path("contoso_config"),
            _manifest_path("contoso_pricing"),
        ),
    )

    assert observer["observer_name"] == "producer_consumer_plausibility"
    assert observer["verdict"] == "pass"
    assert "producer_consumer_edge_present" in observer["reasons"]


def test_shared_state_reuse_observer_passes_for_events_session_mask() -> None:
    report = InterwovenSharedStateReport(
        carrier_id="events_session_mask",
        carrier_kind="shared_state_carrier",
        state_tokens=("dwEventSession", "dwEventMask"),
        downstream_consumers=("EV_RegisterMask", "EV_ReplayMask"),
        exporting_seams=("EV_OpenEventSession",),
        importing_seams=("EV_RegisterMask", "EV_ReplayMask"),
        staleness_risk="low",
        confidence=0.79,
        contradiction_state="none",
    )

    observer = build_shared_state_reuse_plausibility_observer(
        report,
        canonical_sources=(_manifest_path("contoso_events"),),
    )

    assert observer["observer_name"] == "shared_state_reuse_plausibility"
    assert observer["verdict"] == "pass"
    assert "shared_state_reused_across_boundaries" in observer["reasons"]


def test_state_staleness_observer_fails_for_high_risk_interwoven_state() -> None:
    report = InterwovenSharedStateReport(
        carrier_id="events_session_mask",
        carrier_kind="shared_state_carrier",
        state_tokens=("dwEventSession", "dwEventMask"),
        downstream_consumers=("EV_RegisterMask", "EV_ReplayMask"),
        exporting_seams=("EV_OpenEventSession",),
        importing_seams=("EV_RegisterMask", "EV_ReplayMask"),
        staleness_risk="high",
        confidence=0.66,
        contradiction_state="none",
    )

    observer = build_interwoven_state_staleness_risk_observer(
        report,
        canonical_sources=(_manifest_path("contoso_events"), _manifest_path("contoso_interwoven")),
    )

    assert set(INTERWOVEN_OBSERVER_NAMES) == {
        "producer_consumer_plausibility",
        "shared_state_reuse_plausibility",
        "staged_chain_ordering_plausibility",
        "interwoven_state_staleness_risk",
    }
    assert observer["observer_name"] == "interwoven_state_staleness_risk"
    assert observer["verdict"] == "fail"
    assert "state_reuse_may_be_stale_or_forked" in observer["blocking_risks"]
