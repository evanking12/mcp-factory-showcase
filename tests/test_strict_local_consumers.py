from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dashboard_and_tonight_config_pin_canonical_loopback_urls() -> None:
    dashboard_src = (REPO_ROOT / "dashboard" / "main.py").read_text(encoding="utf-8")
    tonight = json.loads((REPO_ROOT / "configs" / "harness" / "tonight.json").read_text(encoding="utf-8"))

    assert 'http://127.0.0.1:8201' in dashboard_src
    assert 'http://127.0.0.1:8090' in dashboard_src
    assert tonight["api"]["url"] == "http://127.0.0.1:8201"
    assert tonight["bridge"]["url"] == "http://127.0.0.1:8090"


def test_long_run_consumers_use_strict_local_preflight_and_runtime_defaults() -> None:
    hard01 = (REPO_ROOT / "scripts" / "runs" / "run_spectrum_compiled_hard01.py").read_text(encoding="utf-8")
    hard02 = (REPO_ROOT / "scripts" / "runs" / "run_spectrum_compiled_hard02.py").read_text(encoding="utf-8")
    medium01 = (REPO_ROOT / "scripts" / "runs" / "run_spectrum_compiled_medium01.py").read_text(encoding="utf-8")
    compare_phase1 = (REPO_ROOT / "scripts" / "stage_split_compare_phase1.py").read_text(encoding="utf-8")

    assert "ensure_strict_local_lane_preflight" in hard01
    assert "local_bridge_base_url()" in hard01
    assert '"http://localhost:8090"' not in hard01

    assert "ensure_strict_local_lane_preflight" in hard02
    assert "local_bridge_base_url()" in hard02
    assert '"http://localhost:8090"' not in hard02

    assert "ensure_strict_local_lane_preflight" in medium01
    assert "ensure_strict_local_lane_preflight" in compare_phase1
