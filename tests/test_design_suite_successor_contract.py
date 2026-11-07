from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.design_suite_successor_contract import (
    ATLAS_SUCCESSOR_SUITE_ID,
    ATLAS_SUCCESSOR_SUITE_NAME,
    DEFAULT_SUCCESSOR_SUITE_CONTRACT,
    DEFAULT_SUCCESSOR_SUITE_FIRST_SLICE,
)


ROOT = Path(__file__).resolve().parent.parent


def test_successor_suite_contract_defaults_lock_atlas_first_harder_family() -> None:
    contract = DEFAULT_SUCCESSOR_SUITE_CONTRACT

    assert contract.suite_id == ATLAS_SUCCESSOR_SUITE_ID
    assert contract.suite_name == ATLAS_SUCCESSOR_SUITE_NAME
    assert contract.first_harder_pressure_family == "mutual_pressure_blocker"
    assert contract.first_bounded_slice == ("batch", "identity", "ledger", "reconcile")
    assert contract.expected_observed_contract_present is True
    assert contract.compare_ready is False
    assert contract.promotion_ready is False


def test_successor_suite_first_slice_defaults_stay_bounded() -> None:
    first_slice = DEFAULT_SUCCESSOR_SUITE_FIRST_SLICE

    assert first_slice.active_modules == ("batch", "identity", "ledger", "reconcile")
    assert first_slice.deferred_modules == ("settlement", "notifications")
    assert first_slice.inherits_reusable_campaign_seam is True
    assert first_slice.compare_ready is False
    assert first_slice.promotion_ready is False


def test_successor_suite_contract_fixture_matches_code_defaults() -> None:
    contract_path = ROOT / "tests" / "fixtures" / "design_suite" / "atlas_reconciliation_suite" / "successor-suite-contract.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))

    assert payload["suite_id"] == DEFAULT_SUCCESSOR_SUITE_CONTRACT.suite_id
    assert payload["suite_name"] == DEFAULT_SUCCESSOR_SUITE_CONTRACT.suite_name
    assert payload["first_harder_pressure_family"] == DEFAULT_SUCCESSOR_SUITE_CONTRACT.first_harder_pressure_family
    assert tuple(payload["first_bounded_slice"]) == DEFAULT_SUCCESSOR_SUITE_CONTRACT.first_bounded_slice
