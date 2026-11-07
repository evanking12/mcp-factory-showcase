from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FULL_FLOW = ROOT / "api" / "pipeline" / "core" / "FULL_FLOW.md"
S02_FLOW = ROOT / "api" / "pipeline" / "s02_probe" / "FLOW.md"
S03_FLOW = ROOT / "api" / "pipeline" / "s03_reconcile" / "FLOW.md"
S06_FLOW = ROOT / "api" / "pipeline" / "s06_gaps" / "FLOW.md"
S07_FLOW = ROOT / "api" / "pipeline" / "s07_finalize" / "FLOW.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_tokens(text: str, tokens: list[str]) -> None:
    for token in tokens:
        assert token in text, f"missing token '{token}'"


def test_full_flow_contains_locked_nxm_and_taxonomy_nodes() -> None:
    text = _read(FULL_FLOW)
    _assert_tokens(
        text,
        [
            "Shared Findings Pool",
            "Variant Merger",
            "functional_precondition_unmet",
            "S-04 Refresh",
            "emit_contract_artifacts",
        ],
    )


def test_s02_flow_parity_tokens() -> None:
    text = _read(S02_FLOW)
    _assert_tokens(
        text,
        [
            "M > 1?",
            "Shared Findings Pool",
            "Variant Merger",
            "verified_success > functional_precondition_unmet > inferred_success > failure > unknown",
        ],
    )


def test_s03_s06_s07_flow_parity_tokens() -> None:
    s03 = _read(S03_FLOW)
    s06 = _read(S06_FLOW)
    s07 = _read(S07_FLOW)

    _assert_tokens(s03, ["verified_success", "Per-function business-logic labels"])
    _assert_tokens(s06, ["functional_precondition_unmet", "S-04 Refresh"])
    _assert_tokens(s07, ["emit_contract_artifacts", "discovered_rate", "verified_rate"])
