from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.interwoven_runtime_projection import build_interwoven_runtime_projection


ROOT = Path(__file__).resolve().parent.parent


def _load_manifest(fixture_name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / fixture_name / "truth_manifest.json").read_text(encoding="utf-8"))


def test_interwoven_fixture_declares_real_prime_session_fanout_pattern() -> None:
    manifest = _load_manifest("contoso_interwoven")
    patterns = {
        str(row.get("pattern_id") or "").strip(): row
        for row in list(manifest.get("interwoven_patterns") or [])
        if isinstance(row, dict)
    }

    assert "prime_session_fanout" in patterns
    pattern = patterns["prime_session_fanout"]
    assert pattern["producer_function"] == "CI_PrimeSession"
    assert set(pattern["consumers"]) == {"CI_EarnThenRedeem", "CI_UnlockAndDebit"}
    assert "same-fixture fanout" in pattern["why_synthetic_insufficient"]


def test_interwoven_runtime_projection_handles_real_fixture_fanout_without_new_vocabulary() -> None:
    manifest = _load_manifest("contoso_interwoven")
    names = {row["name"] for row in manifest["functions"]}
    assert {"CI_PrimeSession", "CI_EarnThenRedeem", "CI_UnlockAndDebit"} <= names

    projection = build_interwoven_runtime_projection(
        {
            "producer_consumer_reports": [
                {
                    "family": "prime_session_to_earn_then_redeem",
                    "producer_id": "CI_PrimeSession",
                    "producer_kind": "producer",
                    "consumer_id": "CI_EarnThenRedeem",
                    "consumer_kind": "consumer",
                    "state_tokens": ("bound_customer", "expected_nonce", "primed_session"),
                    "evidence_edges": ("CI_PrimeSession->CI_EarnThenRedeem",),
                    "dependency_mode": "shared_state_mediated",
                    "confidence": 0.86,
                    "contradiction_state": "none",
                },
                {
                    "family": "prime_session_to_unlock_and_debit",
                    "producer_id": "CI_PrimeSession",
                    "producer_kind": "producer",
                    "consumer_id": "CI_UnlockAndDebit",
                    "consumer_kind": "consumer",
                    "state_tokens": ("primed_session", "unlock_token"),
                    "evidence_edges": ("CI_PrimeSession->CI_UnlockAndDebit",),
                    "dependency_mode": "shared_state_mediated",
                    "confidence": 0.82,
                    "contradiction_state": "none",
                },
            ],
            "shared_state_reports": [
                {
                    "carrier_id": "ci_prime_session_state",
                    "carrier_kind": "shared_state_carrier",
                    "state_tokens": ("bound_customer", "expected_nonce", "primed_session"),
                    "downstream_consumers": ("CI_EarnThenRedeem", "CI_UnlockAndDebit"),
                    "exporting_seams": ("CI_PrimeSession",),
                    "importing_seams": ("CI_EarnThenRedeem", "CI_UnlockAndDebit"),
                    "staleness_risk": "low",
                    "confidence": 0.83,
                    "contradiction_state": "none",
                }
            ],
            "subject_dll_hints": {
                "prime_session_to_earn_then_redeem": ["contoso_cs_interwoven.dll"],
                "prime_session_to_unlock_and_debit": ["contoso_cs_interwoven.dll"],
                "ci_prime_session_state": ["contoso_cs_interwoven.dll"],
            },
        }
    )

    assert projection["interwoven_artifact_presence"] is True
    assert set(projection["interwoven_subject_ids"]) == {
        "prime_session_to_earn_then_redeem",
        "prime_session_to_unlock_and_debit",
        "ci_prime_session_state",
    }
    assert projection["interwoven_contradiction_summary"]["none"] == 3
