from api.pipeline.core.design_suite_artifacts import (
    NorthstarFamilyBlockerReport,
    NorthstarProducerConsumerReport,
    NorthstarSharedStateReport,
)


def test_northstar_producer_consumer_report_round_trips_into_interwoven_shape() -> None:
    report = NorthstarProducerConsumerReport(
        family="session_bootstrap_to_inventory_reserve",
        blocker_family="bootstrap_family_blocker",
        producer_module="session",
        producer_step="bootstrap_session",
        consumer_module="inventory",
        consumer_step="reserve_item",
        state_tokens=("session_token", "customer_context"),
        evidence_edges=("session.bootstrap_session->inventory.reserve_item",),
        dependency_mode="shared_state_mediated",
        confidence=0.9,
    )

    interwoven = report.to_interwoven_report()

    assert interwoven.family == report.family
    assert interwoven.producer_id == "session.bootstrap_session"
    assert interwoven.consumer_id == "inventory.reserve_item"


def test_northstar_shared_state_report_round_trips_into_interwoven_shape() -> None:
    report = NorthstarSharedStateReport(
        carrier_id="session_token",
        carrier_kind="shared_state_carrier",
        state_tokens=("session_token", "sequence_nonce"),
        downstream_consumers=("inventory.reserve_item", "billing.authorize_charge"),
        exporting_seams=("session.bootstrap_session",),
        importing_seams=("inventory.reserve_item", "billing.authorize_charge"),
        staleness_risk="medium",
        confidence=0.83,
    )

    interwoven = report.to_interwoven_report()

    assert interwoven.carrier_id == "session_token"
    assert set(interwoven.downstream_consumers) == {"inventory.reserve_item", "billing.authorize_charge"}


def test_northstar_family_blocker_report_requires_bounded_explanation() -> None:
    report = NorthstarFamilyBlockerReport(
        blocker_family="bootstrap_family_blocker",
        subjects=("session.bootstrap_session", "inventory.reserve_item", "billing.authorize_charge"),
        upstream_requirements=("session.bootstrap_session",),
        shared_state_carriers=("session_token",),
        failure_or_pressure_sites=("inventory.reserve_item", "billing.authorize_charge"),
        contradiction_state="none",
        explanation="The bootstrap token gates more than one downstream family pressure site.",
        confidence=0.86,
    )

    payload = report.to_dict()

    assert payload["blocker_family"] == "bootstrap_family_blocker"
    assert "inventory.reserve_item" in payload["failure_or_pressure_sites"]
    assert payload["provisional_subjects"] == ()
    assert payload["confirmation_sites"] == ()


def test_northstar_family_blocker_report_tracks_late_confirmation_shape() -> None:
    report = NorthstarFamilyBlockerReport(
        blocker_family="late_confirmation_blocker",
        subjects=("inventory.reserve_item", "billing.authorize_charge", "audit.commit_receipt"),
        upstream_requirements=("inventory.reserve_item", "billing.authorize_charge"),
        shared_state_carriers=("session_token", "authorization_receipt", "reservation_id"),
        failure_or_pressure_sites=("inventory.reserve_item", "billing.authorize_charge"),
        contradiction_state="none",
        explanation="Upstream work remains provisional until audit confirms alignment.",
        confidence=0.86,
        provisional_subjects=("inventory.reserve_item", "billing.authorize_charge"),
        confirmation_sites=("audit.commit_receipt",),
    )

    payload = report.to_dict()

    assert payload["provisional_subjects"] == (
        "inventory.reserve_item",
        "billing.authorize_charge",
    )
    assert payload["confirmation_sites"] == ("audit.commit_receipt",)


def test_northstar_family_blocker_report_tracks_forked_state_shape() -> None:
    report = NorthstarFamilyBlockerReport(
        blocker_family="forked_state_blocker",
        subjects=("billing.authorize_charge", "audit.commit_receipt"),
        upstream_requirements=("billing.authorize_charge",),
        shared_state_carriers=("authorization_receipt_branch", "reservation_id"),
        failure_or_pressure_sites=("audit.commit_receipt",),
        contradiction_state="none",
        explanation="Billing emits two plausible authorization branches but only one may reach audit.",
        confidence=0.85,
        lineage_branches=("authorization_receipt_primary", "authorization_receipt_shadow"),
        accepted_branch="authorization_receipt_primary",
        rejected_branches=("authorization_receipt_shadow",),
    )

    payload = report.to_dict()

    assert payload["lineage_branches"] == (
        "authorization_receipt_primary",
        "authorization_receipt_shadow",
    )
    assert payload["accepted_branch"] == "authorization_receipt_primary"
    assert payload["rejected_branches"] == ("authorization_receipt_shadow",)
