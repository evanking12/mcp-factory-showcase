from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_manifest() -> dict:
    path = ROOT / "tests" / "fixtures" / "design_suite" / "northstar_transaction_suite" / "truth_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_northstar_design_suite_fixture_has_manifest_and_source_family() -> None:
    fixture_dir = ROOT / "tests" / "fixtures" / "design_suite" / "northstar_transaction_suite"
    manifest = _load_manifest()

    assert manifest["suite_id"] == "northstar_transaction_suite"
    assert (fixture_dir / "northstar-expected-observed-report.json").exists()
    assert tuple(manifest["active_modules"]) == ("session", "inventory", "billing")
    assert [item["module"] for item in manifest["deferred_modules"]] == ["audit", "fulfillment", "notifications"]
    assert manifest["preferred_expansion_order"] == ["audit", "fulfillment", "notifications"]
    assert manifest["execution_inputs"] == {
        "customer_id": "cust-001",
        "sku": "SKU-001",
        "amount_cents": 4999,
    }
    for relative in manifest["module_sources"].values():
        assert (ROOT / relative).exists()


def test_northstar_first_slice_manifest_declares_bootstrap_and_shared_state_pressures() -> None:
    manifest = _load_manifest()
    families = {item["family_id"]: item for item in manifest["blocker_families"]}
    relationships = {item["family"]: item for item in manifest["expected_relationships"]["producer_consumers"]}

    assert "bootstrap_family_blocker" in families
    assert set(families["bootstrap_family_blocker"]["failure_or_pressure_sites"]) == {
        "inventory.reserve_item",
        "billing.authorize_charge",
    }
    assert "session_bootstrap_to_inventory_reserve" in relationships
    assert "session_bootstrap_to_billing_authorize" in relationships
    assert manifest["shared_state_carriers"][0]["carrier_id"] == "session_token"


def test_northstar_overlap_pressure_is_present_but_deferred_from_first_slice() -> None:
    manifest = _load_manifest()
    overlap = manifest["overlap_pressure"]

    assert overlap["module"] == "audit"
    assert overlap["family_group"]["family_id"] == "two_family_overlap_blocker"
    assert "notifications" == manifest["preferred_expansion_order"][-1]
    assert "audit.commit_receipt" in overlap["execution_rule"]
    assert "misgroup" in overlap["expected_misgroup_risk"]


def test_northstar_late_confirmation_pressure_is_present_but_bounded() -> None:
    manifest = _load_manifest()
    late_confirmation = manifest["late_confirmation_pressure"]

    assert late_confirmation["module"] == "audit"
    assert late_confirmation["family_group"]["family_id"] == "late_confirmation_blocker"
    assert late_confirmation["family_group"]["confirmation_sites"] == ["audit.commit_receipt"]
    assert "provisional" in late_confirmation["execution_rule"]
    assert set(late_confirmation["family_group"]["provisional_subjects"]) == {
        "inventory.reserve_item",
        "billing.authorize_charge",
    }


def test_northstar_forked_state_pressure_is_present_but_bounded() -> None:
    manifest = _load_manifest()
    forked_state = manifest["forked_state_pressure"]

    assert forked_state["module"] == "audit"
    assert forked_state["family_group"]["family_id"] == "forked_state_blocker"
    assert forked_state["family_group"]["accepted_branch"] == "authorization_receipt_primary"
    assert "authorization_receipt_shadow" in forked_state["execution_rule"]
    assert set(forked_state["family_group"]["rejected_branches"]) == {
        "authorization_receipt_shadow",
    }
