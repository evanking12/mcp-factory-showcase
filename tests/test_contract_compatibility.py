from __future__ import annotations

from api.pipeline.core.compatibility import is_capture_compatible
from api.pipeline.core.handoff_contract import AUDITOR_VERSION, CONTRACT_VERSION


def test_compatibility_accepts_current_pair() -> None:
    assert is_capture_compatible(AUDITOR_VERSION, CONTRACT_VERSION)


def test_compatibility_is_tolerant_for_legacy_missing_versions() -> None:
    assert is_capture_compatible("", CONTRACT_VERSION)
    assert is_capture_compatible(AUDITOR_VERSION, "")


def test_compatibility_rejects_unknown_contract_version() -> None:
    assert not is_capture_compatible(AUDITOR_VERSION, "9.9.9")

