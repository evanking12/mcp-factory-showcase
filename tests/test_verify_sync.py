from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFY_SYNC = REPO_ROOT / "scripts" / "verify_sync.py"


def _load_verify_sync_module():
    spec = importlib.util.spec_from_file_location("verify_sync_module", VERIFY_SYNC)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_sync_module"] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def test_verify_sync_tier_a_passes_on_current_repo() -> None:
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SYNC), "--tier", "A"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_verify_sync_detects_duplicate_status_rank(tmp_path: Path) -> None:
    mod = _load_verify_sync_module()
    bad = tmp_path / "bad_module.py"
    bad.write_text(
        "\n".join(
            [
                "RANK = {",
                '  "verified_success": 5,',
                '  "functional_precondition_unmet": 4,',
                '  "inferred_success": 3,',
                '  "failure": 2,',
                '  "unknown": 1,',
                "}",
            ]
        ),
        encoding="utf-8",
    )
    issues = mod._find_inline_status_rank_literals(bad)
    assert len(issues) == 1
    assert issues[0].code == "duplicate-status-rank"
