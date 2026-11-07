from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_northstar_audit_rejects_shadow_authorization_branch() -> None:
    module = _load_module(
        "northstar_audit",
        ROOT / "tests" / "fixtures" / "design_suite" / "northstar_transaction_suite" / "src" / "audit.py",
    )

    with pytest.raises(ValueError, match="shadow authorization branch rejected"):
        module.commit_receipt("NST-cust-001", "AUTH-SHADOW-4999", "RSV-SKU-001")
