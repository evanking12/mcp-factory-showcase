from __future__ import annotations

from api.pipeline.core.spectrum_efficiency_activation import (
    SPECTRUM_EFFICIENCY_CASE_ID,
    SPECTRUM_EFFICIENCY_SUITE_ID,
    build_activation_plan,
    load_spectrum_efficiency_benchmark_protocol,
    load_spectrum_efficiency_package_manifest,
    load_spectrum_efficiency_truth_manifest,
    ordered_spectrum_efficiency_false_positive_targets,
    ordered_spectrum_efficiency_pass_one_targets,
    ordered_spectrum_efficiency_pass_two_targets,
)


def test_efficiency_activation_protocol_shapes_are_stable() -> None:
    manifest = load_spectrum_efficiency_package_manifest()
    truth_manifest = load_spectrum_efficiency_truth_manifest()
    protocol = load_spectrum_efficiency_benchmark_protocol()

    assert protocol["suite_id"] == SPECTRUM_EFFICIENCY_SUITE_ID
    assert protocol["case_id"] == SPECTRUM_EFFICIENCY_CASE_ID
    assert len(protocol["required_metrics_fields"]) == 6
    assert len(truth_manifest["dlls"]) == 10
    assert all(len(dll["exports"]) == 3 for dll in truth_manifest["dlls"])
    assert sum(len(dll["exports"]) for dll in truth_manifest["dlls"]) == 30

    pass_one = ordered_spectrum_efficiency_pass_one_targets(manifest, protocol)
    pass_two = ordered_spectrum_efficiency_pass_two_targets(manifest, protocol)
    false_positive = ordered_spectrum_efficiency_false_positive_targets(manifest, protocol)

    assert [item["target_name"] for item in pass_one] == [
        "session_bootstrap",
        "reservation_stage",
        "dispatch_preview",
        "fee_quote",
    ]
    assert [item["target_name"] for item in pass_two] == [
        "attestation_stage",
        "invoice_sync",
        "entitlement_sync",
        "settlement_reconcile",
    ]
    assert [item["target_name"] for item in false_positive] == [
        "audit_trace",
        "replay_branch",
    ]


def test_activation_plan_records_explicit_deferment() -> None:
    protocol = load_spectrum_efficiency_benchmark_protocol()
    manifest = load_spectrum_efficiency_package_manifest()
    pass_one_targets = ordered_spectrum_efficiency_pass_one_targets(manifest, protocol)

    plan = build_activation_plan(protocol=protocol, phase="pass_one", targets=pass_one_targets)

    assert plan["active_floor"] == "Floor 2: Selective Deepening"
    assert len(plan["chosen_frontier"]) == 4
    assert plan["deferred_surfaces"] == [
        "attestation_stage",
        "invoice_sync",
        "entitlement_sync",
        "settlement_reconcile",
    ]
