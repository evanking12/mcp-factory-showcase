from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_manifest() -> dict:
    path = ROOT / "tests" / "fixtures" / "design_suite" / "atlas_reconciliation_suite" / "truth_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_atlas_successor_fixture_has_manifest_contract_and_first_slice() -> None:
    fixture_dir = ROOT / "tests" / "fixtures" / "design_suite" / "atlas_reconciliation_suite"
    manifest = _load_manifest()

    assert manifest["suite_id"] == "atlas_reconciliation_suite"
    assert (fixture_dir / "successor-suite-contract.json").exists()
    assert (fixture_dir / "successor-suite-first-slice.json").exists()
    assert (fixture_dir / "atlas-expected-observed-report.json").exists()
    assert tuple(manifest["active_modules"]) == ("batch", "identity", "ledger", "reconcile")
    assert [item["module"] for item in manifest["deferred_modules"]] == ["settlement", "notifications"]
    assert manifest["preferred_expansion_order"] == ["settlement", "notifications"]
    assert manifest["execution_inputs"] == {
        "tenant_id": "tenant-001",
        "party_id": "party-001",
        "amount_cents": 7300,
    }


def test_atlas_successor_manifest_declares_mutual_pressure_family() -> None:
    manifest = _load_manifest()
    family = manifest["blocker_families"][0]
    relationships = {item["family"]: item for item in manifest["expected_relationships"]["producer_consumers"]}

    assert family["family_id"] == "mutual_pressure_blocker"
    assert set(family["provisional_subjects"]) == {"identity.bind_party", "ledger.stage_transfer"}
    assert family["confirmation_sites"] == ["reconcile.confirm_alignment"]
    assert "batch_open_to_identity_bind" in relationships
    assert "batch_open_to_ledger_stage" in relationships
    assert "identity_bind_to_reconcile_confirm" in relationships
    assert "ledger_stage_to_reconcile_confirm" in relationships
    assert manifest["shared_state_carriers"][0]["carrier_id"] == "batch_window"
