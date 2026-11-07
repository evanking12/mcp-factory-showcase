from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.design_suite_real_campaign_contract import (
    DEFAULT_DESIGN_SUITE_REAL_CAMPAIGN_CONTRACT,
)


ROOT = Path(__file__).resolve().parent.parent


def test_real_campaign_contract_defaults_remain_generic_and_non_compare() -> None:
    contract = DEFAULT_DESIGN_SUITE_REAL_CAMPAIGN_CONTRACT

    assert contract.owner_module == "api/pipeline/core/design_suite_real_campaign_runtime.py"
    assert contract.entry_runner == "scripts/runs/run_design_suite_real_campaign.py"
    assert contract.compare_ready is False
    assert contract.promotion_ready is False
    assert "audits/design-suite-campaign-attribution-review.json" in contract.inherited_artifacts


def test_real_campaign_contract_doc_matches_code_defaults() -> None:
    path = ROOT / "docs" / "architecture" / "engineScaling" / "engineScaling_DesignSuite" / "design-suite-real-campaign-contract.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["owner_module"] == DEFAULT_DESIGN_SUITE_REAL_CAMPAIGN_CONTRACT.owner_module
    assert payload["entry_runner"] == DEFAULT_DESIGN_SUITE_REAL_CAMPAIGN_CONTRACT.entry_runner
    assert payload["compare_ready"] is False
    assert payload["promotion_ready"] is False
