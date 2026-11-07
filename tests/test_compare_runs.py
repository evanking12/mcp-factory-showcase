from __future__ import annotations

import json
from pathlib import Path

from codex.scripts.compare_runs import compare


def test_compare_reads_function_field_and_detects_flaky(tmp_path: Path) -> None:
    run1 = tmp_path / "run1" / "findings.json"
    run1.parent.mkdir(parents=True, exist_ok=True)
    run1.write_text(
        json.dumps(
            [
                {"function": "CS_GetVersion", "status_canonical": "verified_success", "working_call": {}},
                {"function": "CS_RedeemLoyaltyPoints", "status_canonical": "failure"},
            ]
        ),
        encoding="utf-8",
    )

    run2 = tmp_path / "run2" / "findings.json"
    run2.parent.mkdir(parents=True, exist_ok=True)
    run2.write_text(
        json.dumps(
            [
                {"function": "CS_GetVersion", "status_canonical": "verified_success", "working_call": {}},
                {"function": "CS_RedeemLoyaltyPoints", "status_canonical": "functional_precondition_unmet"},
            ]
        ),
        encoding="utf-8",
    )

    result = compare([run1, run2])

    assert result["total_functions"] == 2
    assert result["upgrades"] == ["CS_RedeemLoyaltyPoints"]
    assert result["flaky"] == ["CS_RedeemLoyaltyPoints"]
    assert result["summary_per_run"][0]["verified_success"] == 1
    assert result["summary_per_run"][1]["discovered"] == 2
