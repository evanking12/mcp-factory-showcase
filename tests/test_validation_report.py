from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import validation_report


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_emit_validation_report_verified_match(tmp_path: Path, monkeypatch) -> None:
    session_dir = tmp_path / "session"
    stage_dir = session_dir / "stage-05-finalization"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        stage_dir / "findings.json",
        [
            {
                "function": "CS_GetVersion",
                "status": "success",
                "working_call": {},
            }
        ],
    )
    _write_json(
        stage_dir / "invocables_map.json",
        {
            "CS_GetVersion": {
                "name": "CS_GetVersion",
                "parameters": [],
                "execution": {"method": "dll_import"},
            }
        },
    )
    (stage_dir / "behavioral_spec.py").write_text(
        "class ExampleWrapper:\n"
        "    def get_version(self):\n"
        "        return 131841\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validation_report,
        "_run_direct",
        lambda inv, args: ("Returned: 131841", ""),
    )

    payload = validation_report.emit_validation_report(session_dir)
    summary = payload["summary"]
    assert summary["checked"] == 1
    assert summary["verified_1to1"] == 1
    assert (session_dir / "validation-report.json").exists()
    assert (session_dir / "human" / "validation-report.md").exists()


def test_emit_validation_report_wrapper_missing_method(tmp_path: Path, monkeypatch) -> None:
    session_dir = tmp_path / "session"
    stage_dir = session_dir / "stage-05-finalization"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        stage_dir / "findings.json",
        [
            {
                "function": "CS_Initialize",
                "status": "success",
                "working_call": {},
            }
        ],
    )
    _write_json(
        stage_dir / "invocables_map.json",
        {
            "CS_Initialize": {
                "name": "CS_Initialize",
                "parameters": [],
                "execution": {"method": "dll_import"},
            }
        },
    )
    (stage_dir / "behavioral_spec.py").write_text(
        "class EmptyWrapper:\n"
        "    pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validation_report,
        "_run_direct",
        lambda inv, args: ("Returned: 0", ""),
    )

    payload = validation_report.emit_validation_report(session_dir)
    summary = payload["summary"]
    assert summary["checked"] == 1
    assert summary["wrapper_error"] == 1
    assert payload["entries"][0]["status"] == "wrapper_error"


def test_emit_validation_report_placeholder_wrapper_method_counts_as_incomplete_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_dir = tmp_path / "session"
    stage_dir = session_dir / "stage-05-finalization"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        stage_dir / "findings.json",
        [
            {
                "function": "SP_PrepareReleasePreview",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {
                    "reservation_handle": "sp-resv-ORD-001-64",
                    "operator_token": "sp-operator-ORD-001-session",
                    "out_preview_ticket": "sp-preview-ORD-001-64-gate",
                    "out_len": 256,
                },
            }
        ],
    )
    _write_json(
        stage_dir / "invocables_map.json",
        {
            "SP_PrepareReleasePreview": {
                "name": "SP_PrepareReleasePreview",
                "parameters": [
                    {"name": "reservation_handle", "direction": "in"},
                    {"name": "operator_token", "direction": "in"},
                    {"name": "out_preview_ticket", "direction": "out"},
                    {"name": "out_len", "direction": "in"},
                ],
                "execution": {"method": "dll_import"},
            }
        },
    )
    (stage_dir / "behavioral_spec.py").write_text(
        "class ExampleWrapper:\n"
        "    def SP_PrepareReleasePreview(self, reservation_handle, operator_token, out_preview_ticket, out_len):\n"
        "        pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validation_report,
        "_run_direct",
        lambda inv, args: ("Returned: 0", ""),
    )

    payload = validation_report.emit_validation_report(session_dir)
    summary = payload["summary"]
    assert summary["checked"] == 1
    assert summary["wrapper_unavailable"] == 1
    assert summary["mismatch"] == 0
    assert payload["entries"][0]["status"] == "wrapper_unavailable"
    assert payload["entries"][0]["wrapper_error"].startswith("wrapper_method_placeholder:")


def test_emit_validation_report_void_return_wrapper_is_not_treated_as_placeholder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_dir = tmp_path / "session"
    stage_dir = session_dir / "stage-05-finalization"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        stage_dir / "findings.json",
        [
            {
                "function": "SP_PrepareReleasePreview",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {
                    "reservation_handle": "sp-resv-ORD-001-64",
                    "operator_token": "sp-operator-ORD-001-session",
                    "out_preview_ticket": "sp-preview-ORD-001-64-gate",
                    "out_len": 256,
                },
            }
        ],
    )
    _write_json(
        stage_dir / "invocables_map.json",
        {
            "SP_PrepareReleasePreview": {
                "name": "SP_PrepareReleasePreview",
                "parameters": [
                    {"name": "reservation_handle", "direction": "in"},
                    {"name": "operator_token", "direction": "in"},
                    {"name": "out_preview_ticket", "direction": "out"},
                    {"name": "out_len", "direction": "in"},
                ],
                "execution": {"method": "dll_import"},
            }
        },
    )
    (stage_dir / "behavioral_spec.py").write_text(
        "class ExampleWrapper:\n"
        "    def SP_PrepareReleasePreview(self, reservation_handle, operator_token, out_preview_ticket, out_len):\n"
        "        self.last_preview_ticket = out_preview_ticket\n"
        "        return None\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validation_report,
        "_run_direct",
        lambda inv, args: ("Returned: 0", ""),
    )

    payload = validation_report.emit_validation_report(session_dir)
    assert payload["entries"][0]["status"] != "wrapper_unavailable"
    assert not str(payload["entries"][0].get("wrapper_error") or "").startswith("wrapper_method_placeholder:")


def test_emit_validation_report_wrapper_ignores_extra_param_keys_for_zero_arg_wrapper(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_dir = tmp_path / "session"
    stage_dir = session_dir / "stage-05-finalization"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        stage_dir / "findings.json",
        [
            {
                "function": "SP_OpenOperatorSession",
                "status": "partial",
                "status_canonical": "inferred_success",
                "working_call": {"param_1": 0, "param_2": "", "param_3": 64},
            }
        ],
    )
    _write_json(
        stage_dir / "invocables_map.json",
        {
            "SP_OpenOperatorSession": {
                "name": "SP_OpenOperatorSession",
                "parameters": [
                    {"name": "param_1"},
                    {"name": "param_2"},
                    {"name": "param_3"},
                ],
                "execution": {"method": "dll_import"},
            }
        },
    )
    (stage_dir / "behavioral_spec.py").write_text(
        "class ExampleWrapper:\n"
        "    def SP_OpenOperatorSession(self):\n"
        "        return 0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validation_report,
        "_run_direct",
        lambda inv, args: ("Returned: 0", ""),
    )

    payload = validation_report.emit_validation_report(session_dir)
    assert payload["summary"]["wrapper_error"] == 0
    assert payload["entries"][0]["status"] == "verified_1to1"


def test_emit_validation_report_wrapper_trims_to_signature_when_args_exceed_method_arity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_dir = tmp_path / "session"
    stage_dir = session_dir / "stage-05-finalization"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        stage_dir / "findings.json",
        [
            {
                "function": "SP_IssueReleaseHold",
                "status": "partial",
                "status_canonical": "inferred_success",
                "working_call": {
                    "param_1": "sess-1",
                    "param_2": "ord-1",
                    "param_3": "",
                    "param_5": 64,
                    "param_7": 64,
                },
            }
        ],
    )
    _write_json(
        stage_dir / "invocables_map.json",
        {
            "SP_IssueReleaseHold": {
                "name": "SP_IssueReleaseHold",
                "parameters": [
                    {"name": "param_1"},
                    {"name": "param_2"},
                    {"name": "param_3"},
                    {"name": "param_5"},
                    {"name": "param_7"},
                ],
                "execution": {"method": "dll_import"},
            }
        },
    )
    (stage_dir / "behavioral_spec.py").write_text(
        "class ExampleWrapper:\n"
        "    def SP_IssueReleaseHold(self, lpszCustId, dwHoldMinutes):\n"
        "        return 0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validation_report,
        "_run_direct",
        lambda inv, args: ("Returned: 0", ""),
    )

    payload = validation_report.emit_validation_report(session_dir)
    assert payload["summary"]["wrapper_error"] == 0
    assert payload["entries"][0]["status"] == "verified_1to1"


def test_emit_validation_report_ignores_output_only_buffer_args_for_projected_wrapper_signature(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_dir = tmp_path / "session"
    stage_dir = session_dir / "stage-05-finalization"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        stage_dir / "findings.json",
        [
            {
                "function": "SP_RecordReleaseReceipt",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {
                    "param_1": "sp-commit-0",
                    "param_2": "sp-operator-0-session",
                    "output_buffer": "sp-audit-receipt-0-ok",
                    "param_4": 64,
                },
            }
        ],
    )
    _write_json(
        stage_dir / "invocables_map.json",
        {
            "SP_RecordReleaseReceipt": {
                "name": "SP_RecordReleaseReceipt",
                "parameters": [
                    {"name": "param_1", "direction": "in"},
                    {"name": "param_2", "direction": "in"},
                    {"name": "output_buffer", "direction": "out"},
                    {"name": "param_4", "direction": "in"},
                ],
                "execution": {"method": "dll_import"},
            }
        },
    )
    (stage_dir / "behavioral_spec.py").write_text(
        "class ExampleWrapper:\n"
        "    @staticmethod\n"
        "    def SP_RecordReleaseReceipt(param_1, param_2, param_4):\n"
        "        return 0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validation_report,
        "_run_direct",
        lambda inv, args: ("Returned: 0", ""),
    )

    payload = validation_report.emit_validation_report(session_dir)
    assert payload["summary"]["wrapper_error"] == 0
    assert payload["entries"][0]["status"] == "verified_1to1"
