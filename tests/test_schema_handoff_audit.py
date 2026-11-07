from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import collector


_HARNESS_PATH = Path(__file__).resolve().parent.parent / "scripts" / "harness.py"
_SPEC = importlib.util.spec_from_file_location("harness_test_schema_module", _HARNESS_PATH)
assert _SPEC and _SPEC.loader
harness = importlib.util.module_from_spec(_SPEC)
sys.modules["harness_test_schema_module"] = harness
_SPEC.loader.exec_module(harness)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _schema(function_name: str, param_names: list[str]) -> dict:
    return {
        "job_id": "j1",
        "mcp_version": "1.0",
        "component": "contoso_cs",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": function_name,
                    "description": "desc",
                    "parameters": {
                        "type": "object",
                        "properties": {name: {"type": "string"} for name in param_names},
                        "required": list(param_names),
                    },
                },
            }
        ],
    }


def test_schema_handoff_audit_detects_drop_to_zero(tmp_path: Path) -> None:
    session = tmp_path / "session"
    _write_json(session / "stage-00-setup" / "schema.json", _schema("CS_UnlockAccount", ["customer_id", "code"]))
    _write_json(session / "stage-01-probe-loop" / "schema-after.json", _schema("CS_UnlockAccount", []))

    audit = collector._build_schema_handoff_audit(session)  # noqa: SLF001
    assert int((audit.get("summary") or {}).get("drop_to_zero_count") or 0) == 1
    assert int((audit.get("summary") or {}).get("regression_count") or 0) == 1
    assert audit.get("drop_to_zero")


def test_verify_fails_on_schema_handoff_drop_to_zero(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    _write_json(session / "session-meta.json", {"job_id": "j1", "component": "contoso_cs"})
    _write_json(session / "stage-index.json", {"version": "1.0", "stages": []})
    _write_json(session / "transition-index.json", {"version": "1.0", "transitions": [{"id": "T-01"}]})
    _write_json(session / "cohesion-report.json", {"version": "1.0", "gates": {"hard_fail": False}})
    _write_json(session / "schema-handoff-audit.json", {"summary": {"drop_to_zero_count": 1}})

    code = harness.main(["verify", "--session-dir", str(session), "--mode", "strict"])
    assert code == 1
    report = json.loads((session / "human" / "verify-report.json").read_text(encoding="utf-8"))
    assert int(report.get("schema_handoff_drop_to_zero") or 0) == 1


def test_verify_fails_on_schema_handoff_regression(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    _write_json(session / "session-meta.json", {"job_id": "j1", "component": "contoso_cs"})
    _write_json(session / "stage-index.json", {"version": "1.0", "stages": []})
    _write_json(session / "transition-index.json", {"version": "1.0", "transitions": [{"id": "T-01"}]})
    _write_json(session / "cohesion-report.json", {"version": "1.0", "gates": {"hard_fail": False}})
    _write_json(session / "schema-handoff-audit.json", {"summary": {"drop_to_zero_count": 0, "regression_count": 1}})

    code = harness.main(["verify", "--session-dir", str(session), "--mode", "strict"])
    assert code == 1
    report = json.loads((session / "human" / "verify-report.json").read_text(encoding="utf-8"))
    assert int(report.get("schema_handoff_regressions") or 0) == 1


def test_schema_handoff_audit_ignores_floor_gated_skipped_snapshots(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    _write_json(
        session / "stage-index.json",
        {
            "version": "1.0",
            "stages": [
                {"id": "S-04", "checks": {}, "skip_reason": "floor_broadening_blocked"},
                {"id": "S-05", "checks": {}, "skip_reason": "floor_broadening_blocked"},
                {"id": "S-06", "checks": {"answer_gaps_triggered": False}, "skip_reason": "floor_broadening_blocked"},
            ],
        },
    )
    _write_json(session / "stage-00-setup" / "schema.json", _schema("CS_UnlockAccount", ["customer_id", "code"]))
    _write_json(session / "stage-01-probe-loop" / "schema-after.json", _schema("CS_UnlockAccount", ["customer_id", "code"]))
    _write_json(session / "evidence" / "stage-05-backfill" / "schema-post-backfill.json", {})
    _write_json(session / "evidence" / "stage-07-finalize" / "schema-final.json", _schema("CS_UnlockAccount", ["customer_id", "code"]))

    audit = collector._build_schema_handoff_audit(session)  # noqa: SLF001

    assert int((audit.get("summary") or {}).get("drop_to_zero_count") or 0) == 0
    assert int((audit.get("summary") or {}).get("regression_count") or 0) == 0
    snapshots = list(audit.get("snapshots") or [])
    assert not any(row.get("path") == "stage-02-synthesis/schema-after.json" for row in snapshots)
    assert not any(row.get("path") == "evidence/stage-05-backfill/schema-post-backfill.json" for row in snapshots)


def test_schema_handoff_audit_ignores_synthetic_helper_tool_loss(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    _write_json(
        session / "stage-00-setup" / "schema.json",
        {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "CS_UnlockAccount",
                        "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "record_finding",
                        "parameters": {"type": "object", "properties": {"status": {"type": "string"}}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "enrich_invocable",
                        "parameters": {"type": "object", "properties": {"function": {"type": "string"}}},
                    },
                },
            ]
        },
    )
    _write_json(
        session / "evidence" / "stage-07-finalize" / "schema-final.json",
        _schema("CS_UnlockAccount", ["customer_id"]),
    )

    audit = collector._build_schema_handoff_audit(session)  # noqa: SLF001

    assert int((audit.get("summary") or {}).get("regression_count") or 0) == 0
    assert int((audit.get("summary") or {}).get("silent_function_loss_count") or 0) == 0
