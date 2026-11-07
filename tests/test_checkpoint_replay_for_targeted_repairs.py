from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "regression" / "replay_session_closeout.py"
SPEC = importlib.util.spec_from_file_location("replay_session_closeout_test_module", SCRIPT_PATH)
assert SPEC and SPEC.loader
replay_module = importlib.util.module_from_spec(SPEC)
sys.modules["replay_session_closeout_test_module"] = replay_module
SPEC.loader.exec_module(replay_module)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _schema(function_name: str, param_names: list[str]) -> dict:
    return {
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
        ]
    }


def _write_minimal_session(session: Path, *, regression: bool = False) -> None:
    _write_json(
        session / "session-meta.json",
        {
            "job_id": "j1",
            "component": "spectrum_transaction_release_settlement_suite",
            "analysis_profile": "strict_dll",
            "contract_version": "1.0",
        },
    )
    _write_json(session / "stage-index.json", {"version": "1.0", "stages": []})
    _write_json(session / "transition-index.json", {"version": "1.0", "transitions": []})
    _write_json(session / "cohesion-report.json", {"version": "1.0", "gates": {"hard_fail": False}})
    _write_json(
        session / "stage-05-finalization" / "findings.json",
        [{"function": "SP_RecordReleaseReceipt", "status": "verified_success"}],
    )
    _write_json(
        session / "stage-05-finalization" / "invocables_map.json",
        {
            "SP_RecordReleaseReceipt": {
                "parameters": [{"name": "release_id", "type": "string"}],
            }
        },
    )
    _write_json(
        session / "stage-00-setup" / "schema.json",
        _schema("SP_RecordReleaseReceipt", ["release_id"]),
    )
    final_params = [] if regression else ["release_id"]
    _write_json(
        session / "evidence" / "stage-07-finalize" / "schema-final.json",
        _schema("SP_RecordReleaseReceipt", final_params),
    )


def _write_duplicate_required_collision_session(session: Path) -> None:
    _write_minimal_session(session)
    _write_json(
        session / "stage-00-setup" / "schema.json",
        _schema(
            "SP_RecordReleaseReceipt",
            ["param_1", "param_2", "param_3", "param_4"],
        ),
    )
    collapsed = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "SP_RecordReleaseReceipt",
                    "description": "Records a release receipt.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "receipt_id": {"type": "string"},
                            "operator_session_token": {"type": "string"},
                            "receipt_buffer_len": {"type": "integer"},
                        },
                        "required": [
                            "receipt_id",
                            "operator_session_token",
                            "receipt_id",
                            "receipt_buffer_len",
                        ],
                    },
                },
            }
        ]
    }
    _write_json(session / "evidence" / "stage-05-backfill" / "schema-post-backfill.json", collapsed)
    _write_json(session / "evidence" / "stage-07-finalize" / "schema-final.json", collapsed)


def _hash_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def test_missing_source_fails_closed(tmp_path: Path) -> None:
    result = replay_module.replay_session_closeout(
        source_session_dir=tmp_path / "missing",
        output_root=tmp_path / "out",
        mode="strict",
    )

    assert result["blocking_signal"] == "source_session_missing"
    assert result["claim_ceiling"] == "checkpoint_replay_only"
    assert result["product_green_claimed"] is False
    assert (tmp_path / "out" / "checkpoint-replay-result.json").exists()


def _write_green_closeout(session_dir: Path) -> None:
    _write_json(
        session_dir / "schema-handoff-audit.json",
        {"summary": {"regression_count": 0, "drop_to_zero_count": 0, "silent_function_loss_count": 0}},
    )
    _write_json(
        session_dir / "transition-contract-audit.json",
        {"summary": {"valid": True, "fail_count": 0}},
    )
    _write_json(
        session_dir / "run-validity.json",
        {"valid": True, "reasons": [], "gate_results": {"schema_handoff_consistent": True}},
    )


def test_replay_does_not_mutate_source(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source-session"
    _write_minimal_session(source)
    before_hashes = _hash_tree(source)

    def fake_collect(session_dir: Path, **_: object) -> int:
        _write_green_closeout(Path(session_dir))
        return 0

    monkeypatch.setattr(replay_module.collector, "collect_session", fake_collect)

    result = replay_module.replay_session_closeout(
        source_session_dir=source,
        output_root=tmp_path / "out",
        mode="strict",
    )

    assert result["blocking_signal"] == "checkpoint_replay_green"
    assert _hash_tree(source) == before_hashes
    assert (tmp_path / "out" / "replayed-session" / "run-validity.json").exists()


def test_valid_closeout_replay_emits_green_without_product_claim(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source-session"
    _write_minimal_session(source)

    def fake_collect(session_dir: Path, **_: object) -> int:
        _write_green_closeout(Path(session_dir))
        return 0

    monkeypatch.setattr(replay_module.collector, "collect_session", fake_collect)

    result = replay_module.replay_session_closeout(
        source_session_dir=source,
        output_root=tmp_path / "out",
        mode="strict",
        component="spectrum_transaction_release_settlement_suite",
    )

    assert result["blocking_signal"] == "checkpoint_replay_green"
    assert result["collect_exit_code"] == 0
    assert result["safe_to_compare"] is True
    assert result["product_green_claimed"] is False
    assert result["after"]["run_validity"]["valid"] is True
    assert result["authority_deltas"]["schema_handoff_regression_count_after"] == 0


def test_schema_handoff_regression_remains_blocked(tmp_path: Path) -> None:
    source = tmp_path / "source-session"
    _write_minimal_session(source, regression=True)

    result = replay_module.replay_session_closeout(
        source_session_dir=source,
        output_root=tmp_path / "out",
        mode="strict",
    )

    assert result["blocking_signal"] == "schema_handoff_regression_persists"
    assert result["safe_to_compare"] is False
    assert result["after"]["run_validity"]["valid"] is False
    assert result["after"]["schema_handoff"]["regression_count"] > 0


def test_duplicate_required_collision_replay_preserves_slots(tmp_path: Path) -> None:
    source = tmp_path / "source-session"
    _write_duplicate_required_collision_session(source)

    result = replay_module.replay_session_closeout(
        source_session_dir=source,
        output_root=tmp_path / "out",
        mode="strict",
    )

    assert result["product_green_claimed"] is False
    assert result["after"]["schema_handoff"]["regression_count"] == 0
    assert result["schema_replay_normalization"]

    replayed_schema = json.loads(
        (
            tmp_path
            / "out"
            / "replayed-session"
            / "evidence"
            / "stage-07-finalize"
            / "schema-final.json"
        ).read_text(encoding="utf-8")
    )
    params = replayed_schema["tools"][0]["function"]["parameters"]
    assert list(params["properties"]) == [
        "receipt_id",
        "operator_session_token",
        "receipt_buffer_len",
        "receipt_id_2",
    ]
    assert params["required"] == [
        "receipt_id",
        "operator_session_token",
        "receipt_id_2",
        "receipt_buffer_len",
    ]


def test_invalid_source_contract_fails_before_claiming_replay_green(tmp_path: Path) -> None:
    source = tmp_path / "source-session"
    source.mkdir(parents=True)
    _write_json(source / "session-meta.json", {"job_id": "j1"})

    result = replay_module.replay_session_closeout(
        source_session_dir=source,
        output_root=tmp_path / "out",
        mode="strict",
    )

    assert result["blocking_signal"] == "source_session_contract_invalid"
    assert result["collect_exit_code"] is None
    assert result["safe_to_compare"] is False
    assert result["product_green_claimed"] is False
