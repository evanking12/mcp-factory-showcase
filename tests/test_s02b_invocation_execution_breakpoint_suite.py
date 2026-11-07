from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from api.infra import storage
from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.s02_probe import invocation_execution
from api.pipeline.s02_probe import probe_loop
from api.pipeline.s02_probe import status as s02_status
from api.services import executor


REPO_ROOT = Path(__file__).resolve().parents[1]
TIER1_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s02b_invocation_raw_observation_tier1"
TIER1_BUILD_SCRIPT = TIER1_FIXTURE_ROOT / "build.ps1"
TIER2_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s02b_invocation_raw_observation_tier2"
TIER2_BUILD_SCRIPT = TIER2_FIXTURE_ROOT / "build.ps1"
ARG_TIER2_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s02b_argument_construction_tier2"
ARG_TIER2_BUILD_SCRIPT = ARG_TIER2_FIXTURE_ROOT / "build.ps1"
PRECONDITION_TIER2_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s02b_functional_precondition_tier2"
PRECONDITION_TIER2_BUILD_SCRIPT = PRECONDITION_TIER2_FIXTURE_ROOT / "build.ps1"


def _has_msvc_toolchain() -> bool:
    if sys.platform != "win32":
        return False
    script = (
        "$vswhere = Join-Path ${env:ProgramFiles(x86)} "
        "'Microsoft Visual Studio\\Installer\\vswhere.exe'; "
        "$install = ''; "
        "if (Test-Path $vswhere) { "
        "$install = & $vswhere -latest -products * "
        "-requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 "
        "-property installationPath 2>$null "
        "}; "
        "$cl = Get-Command cl.exe -ErrorAction SilentlyContinue; "
        "if ($install -or $cl) { exit 0 } else { exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@pytest.fixture(scope="module")
def raw_observation_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build_fixture_dll(
        tmp_path_factory=tmp_path_factory,
        temp_name="s02b-raw-observation-tier1",
        build_script=TIER1_BUILD_SCRIPT,
        dll_name="s02b_invocation_raw_observation_tier1.dll",
    )


@pytest.fixture(scope="module")
def raw_observation_tier2_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build_fixture_dll(
        tmp_path_factory=tmp_path_factory,
        temp_name="s02b-raw-observation-tier2",
        build_script=TIER2_BUILD_SCRIPT,
        dll_name="s02b_invocation_raw_observation_tier2.dll",
    )


@pytest.fixture(scope="module")
def argument_construction_tier2_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build_fixture_dll(
        tmp_path_factory=tmp_path_factory,
        temp_name="s02b-argument-construction-tier2",
        build_script=ARG_TIER2_BUILD_SCRIPT,
        dll_name="s02b_argument_construction_tier2.dll",
    )


@pytest.fixture(scope="module")
def functional_precondition_tier2_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build_fixture_dll(
        tmp_path_factory=tmp_path_factory,
        temp_name="s02b-functional-precondition-tier2",
        build_script=PRECONDITION_TIER2_BUILD_SCRIPT,
        dll_name="s02b_functional_precondition_tier2.dll",
    )


def _build_fixture_dll(
    *,
    tmp_path_factory: pytest.TempPathFactory,
    temp_name: str,
    build_script: Path,
    dll_name: str,
) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp(temp_name)
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(build_script),
            "-OutputRoot",
            str(output_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    dll_path = output_root / "bin" / dll_name
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


def _invocable(
    name: str,
    dll_path: Path,
    *,
    parameters: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "return_type": "int",
        "parameters": parameters or [],
        "execution": {
            "method": "dll_import",
            "dll_path": str(dll_path),
            "function_name": name,
        },
    }


def _ctx_for_invocables(
    *,
    job_id: str,
    invocables: list[dict[str, object]],
    max_tool_calls: int,
) -> ExploreContext:
    runtime = ExploreRuntime(
        max_rounds=0,
        max_tool_calls=max_tool_calls,
        min_direct_probes=1,
        skip_documented=False,
        deterministic_fallback_enabled=True,
        concurrency=1,
    )
    ctx = ExploreContext(
        job_id=job_id,
        runtime=runtime,
        client=object(),
        model="no-model",
        invocables=invocables,
        inv_map={str(inv["name"]): inv for inv in invocables},
        tool_schemas=[],
        total=len(invocables),
    )
    ctx.vocab = {}
    ctx.sentinels = {}
    ctx.unlock_result = {"unlocked": False, "sequence": []}
    return ctx


def _ctx(dll_path: Path) -> ExploreContext:
    invocables = [
        _invocable("S02B_StatusOk", dll_path),
        _invocable("S02B_StateCounter", dll_path),
    ]
    return _ctx_for_invocables(
        job_id="job-s02b-raw-observation-tier1",
        invocables=invocables,
        max_tool_calls=2,
    )


def _install_quiet_storage(monkeypatch: pytest.MonkeyPatch, probe_log: list[dict[str, object]]) -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []

    monkeypatch.setattr(s02_status, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(s02_status, "_persist_job_status", lambda _job_id, payload: statuses.append(dict(payload)))
    monkeypatch.setattr(s02_status, "_set_explore_status", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(storage, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(probe_loop, "_download_blob", lambda *_args, **_kwargs: b"[]")
    monkeypatch.setattr(probe_loop, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_save_stage_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_append_transcript", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_append_executor_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_patch_invocable", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_patch_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_save_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(probe_loop, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(probe_loop, "_update_vocabulary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_generate_hypothesis", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(
        probe_loop,
        "_append_explore_probe_log",
        lambda _job_id, rows: probe_log.extend(dict(row) for row in rows),
    )
    return statuses


def test_s02b_tier1_preserves_raw_observations_from_compiled_invocations(
    monkeypatch: pytest.MonkeyPatch,
    raw_observation_dll: Path,
) -> None:
    """Tier 1 anchor: S-02B preserves raw DLL observations without model or lane claims."""
    probe_log: list[dict[str, object]] = []
    statuses = _install_quiet_storage(monkeypatch, probe_log)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    ctx = _ctx(raw_observation_dll)

    invocation_execution.run_invocation_execution(ctx)

    substage_states = [
        row.get("s02_substage_status", {}).get("s02_invocation_execution", {}).get("state")
        for row in statuses
    ]
    assert substage_states == ["start", "done"]
    assert "S02B_StatusOk" in ctx.already_explored
    assert "S02B_StateCounter" in ctx.already_explored

    observations = {
        (str(row.get("function")), str(row.get("phase"))): row
        for row in probe_log
        if row.get("phase") == "deterministic_fallback"
    }
    status_ok = observations[("S02B_StatusOk", "deterministic_fallback")]
    state_counter = observations[("S02B_StateCounter", "deterministic_fallback")]

    assert status_ok["args"] == {}
    assert state_counter["args"] == {}
    assert status_ok["tool"] == "S02B_StatusOk"
    assert state_counter["tool"] == "S02B_StateCounter"
    assert "Returned: 0" in str(status_ok["result_excerpt"])
    assert "Returned: 1" in str(state_counter["result_excerpt"])

    status_trace = status_ok["trace"]
    counter_trace = state_counter["trace"]
    assert isinstance(status_trace, dict)
    assert isinstance(counter_trace, dict)
    assert status_trace["backend"] == "dll"
    assert counter_trace["backend"] == "dll"
    assert status_trace["function_name"] == "S02B_StatusOk"
    assert counter_trace["function_name"] == "S02B_StateCounter"
    assert status_trace["raw_result"] == 0
    assert counter_trace["raw_result"] == 1


def test_s02b_tier2_preserves_medium_raw_observation_pressure(
    monkeypatch: pytest.MonkeyPatch,
    raw_observation_tier2_dll: Path,
) -> None:
    """Tier 2 anchor: S-02B preserves multiple compiled raw observations under medium pressure."""
    probe_log: list[dict[str, object]] = []
    statuses = _install_quiet_storage(monkeypatch, probe_log)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    invocables = [
        _invocable("S02B_T2_StatusOk", raw_observation_tier2_dll),
        _invocable("S02B_T2_StatusBlocked", raw_observation_tier2_dll),
        _invocable("S02B_T2_StatusWarning", raw_observation_tier2_dll),
        _invocable("S02B_T2_StateCounter", raw_observation_tier2_dll),
        _invocable(
            "S02B_T2_EchoInt",
            raw_observation_tier2_dll,
            parameters=[
                {
                    "name": "value",
                    "type": "int",
                    "json_type": "integer",
                    "description": "integer probe value",
                    "direction": "in",
                }
            ],
        ),
    ]
    ctx = _ctx_for_invocables(
        job_id="job-s02b-raw-observation-tier2",
        invocables=invocables,
        max_tool_calls=len(invocables),
    )

    invocation_execution.run_invocation_execution(ctx)

    substage_states = [
        row.get("s02_substage_status", {}).get("s02_invocation_execution", {}).get("state")
        for row in statuses
    ]
    assert substage_states == ["start", "done"]
    for invocable in invocables:
        assert invocable["name"] in ctx.already_explored

    observations = {
        str(row.get("function")): row
        for row in probe_log
        if row.get("phase") == "deterministic_fallback"
    }
    assert set(observations) == {str(invocable["name"]) for invocable in invocables}

    expected_raw_results = {
        "S02B_T2_StatusOk": 0,
        "S02B_T2_StatusBlocked": -5,
        "S02B_T2_StatusWarning": 7,
        "S02B_T2_StateCounter": 1,
    }
    for function_name, raw_result in expected_raw_results.items():
        row = observations[function_name]
        trace = row["trace"]
        assert row["tool"] == function_name
        assert row["args"] == {}
        assert isinstance(trace, dict)
        assert trace["backend"] == "dll"
        assert trace["function_name"] == function_name
        assert trace["raw_result"] == raw_result
        assert trace["c_args_count"] == 0
        assert f"Returned: {raw_result}" in str(row["result_excerpt"])
        assert "classification" in row

    echo_row = observations["S02B_T2_EchoInt"]
    echo_trace = echo_row["trace"]
    assert isinstance(echo_trace, dict)
    assert echo_trace["backend"] == "dll"
    assert echo_trace["function_name"] == "S02B_T2_EchoInt"
    assert echo_trace["c_args_count"] == 1
    echo_args = echo_row["args"]
    assert isinstance(echo_args, dict)
    assert set(echo_args) == {"value"}
    echo_value = echo_args["value"]
    assert isinstance(echo_value, int)
    expected_echo_result = echo_value + 100
    assert echo_trace["raw_result"] == expected_echo_result
    assert f"Returned: {expected_echo_result}" in str(echo_row["result_excerpt"])
    assert "value" in echo_row.get("arg_sources", {})
    assert "classification" in echo_row


def test_s02b_tier2_constructs_usable_typed_arguments_under_medium_pressure(
    monkeypatch: pytest.MonkeyPatch,
    argument_construction_tier2_dll: Path,
) -> None:
    """Tier 2 anchor: S-02B constructs typed arguments, not only preserves results."""
    probe_log: list[dict[str, object]] = []
    statuses = _install_quiet_storage(monkeypatch, probe_log)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    invocables = [
        _invocable(
            "S02B_ARG_T2_Quantity",
            argument_construction_tier2_dll,
            parameters=[
                {
                    "name": "quantity",
                    "type": "int",
                    "json_type": "integer",
                    "description": "quantity to apply",
                    "direction": "in",
                }
            ],
        ),
        _invocable(
            "S02B_ARG_T2_AmountCents",
            argument_construction_tier2_dll,
            parameters=[
                {
                    "name": "amount_cents",
                    "type": "int",
                    "json_type": "integer",
                    "description": "amount in cents",
                    "direction": "in",
                }
            ],
        ),
        _invocable(
            "S02B_ARG_T2_ModeFlag",
            argument_construction_tier2_dll,
            parameters=[
                {
                    "name": "mode_flag",
                    "type": "int",
                    "json_type": "integer",
                    "description": "mode flag",
                    "direction": "in",
                }
            ],
        ),
        _invocable(
            "S02B_ARG_T2_QuantityAmount",
            argument_construction_tier2_dll,
            parameters=[
                {
                    "name": "quantity",
                    "type": "int",
                    "json_type": "integer",
                    "description": "quantity to apply",
                    "direction": "in",
                },
                {
                    "name": "amount_cents",
                    "type": "int",
                    "json_type": "integer",
                    "description": "amount in cents",
                    "direction": "in",
                },
            ],
        ),
    ]
    ctx = _ctx_for_invocables(
        job_id="job-s02b-argument-construction-tier2",
        invocables=invocables,
        max_tool_calls=len(invocables),
    )

    invocation_execution.run_invocation_execution(ctx)

    substage_states = [
        row.get("s02_substage_status", {}).get("s02_invocation_execution", {}).get("state")
        for row in statuses
    ]
    assert substage_states == ["start", "done"]

    observations = {
        str(row.get("function")): row
        for row in probe_log
        if row.get("phase") == "deterministic_fallback"
    }
    assert set(observations) == {str(invocable["name"]) for invocable in invocables}

    quantity_args = observations["S02B_ARG_T2_Quantity"]["args"]
    amount_args = observations["S02B_ARG_T2_AmountCents"]["args"]
    mode_args = observations["S02B_ARG_T2_ModeFlag"]["args"]
    combined_args = observations["S02B_ARG_T2_QuantityAmount"]["args"]
    assert quantity_args == {"quantity": 1}
    assert amount_args == {"amount_cents": 2500}
    assert mode_args == {"mode_flag": 1}
    assert combined_args == {"quantity": 1, "amount_cents": 2500}

    expected_results = {
        "S02B_ARG_T2_Quantity": 1,
        "S02B_ARG_T2_AmountCents": 2500,
        "S02B_ARG_T2_ModeFlag": 1,
        "S02B_ARG_T2_QuantityAmount": 12500,
    }
    for function_name, expected_result in expected_results.items():
        row = observations[function_name]
        trace = row["trace"]
        assert isinstance(trace, dict)
        assert row["tool"] == function_name
        assert trace["backend"] == "dll"
        assert trace["function_name"] == function_name
        assert trace["raw_result"] == expected_result
        assert f"Returned: {expected_result}" in str(row["result_excerpt"])
        assert "classification" in row
        assert row.get("arg_sources")

    assert observations["S02B_ARG_T2_QuantityAmount"]["trace"]["c_args_count"] == 2
    assert set(observations["S02B_ARG_T2_QuantityAmount"]["arg_sources"]) == {
        "quantity",
        "amount_cents",
    }


def test_s02b_tier2_records_functional_preconditions_without_final_semantic_overclaim(
    monkeypatch: pytest.MonkeyPatch,
    functional_precondition_tier2_dll: Path,
) -> None:
    """Tier 2 anchor: S-02B preserves blocked-before-init and allowed-after-init facts."""
    probe_log: list[dict[str, object]] = []
    statuses = _install_quiet_storage(monkeypatch, probe_log)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    invocables = [
        _invocable(
            "S02B_PRE_T2_CommitBeforeInit",
            functional_precondition_tier2_dll,
            parameters=[
                {
                    "name": "amount_cents",
                    "type": "int",
                    "json_type": "integer",
                    "description": "amount in cents",
                    "direction": "in",
                }
            ],
        ),
        _invocable("S02B_PRE_T2_InitSession", functional_precondition_tier2_dll),
        _invocable(
            "S02B_PRE_T2_CommitAfterInit",
            functional_precondition_tier2_dll,
            parameters=[
                {
                    "name": "amount_cents",
                    "type": "int",
                    "json_type": "integer",
                    "description": "amount in cents",
                    "direction": "in",
                }
            ],
        ),
        _invocable("S02B_PRE_T2_ReadStatus", functional_precondition_tier2_dll),
    ]
    ctx = _ctx_for_invocables(
        job_id="job-s02b-functional-precondition-tier2",
        invocables=invocables,
        max_tool_calls=len(invocables),
    )

    invocation_execution.run_invocation_execution(ctx)

    substage_states = [
        row.get("s02_substage_status", {}).get("s02_invocation_execution", {}).get("state")
        for row in statuses
    ]
    assert substage_states == ["start", "done"]

    observations = {
        str(row.get("function")): row
        for row in probe_log
        if row.get("phase") == "deterministic_fallback"
    }
    assert set(observations) == {str(invocable["name"]) for invocable in invocables}

    before = observations["S02B_PRE_T2_CommitBeforeInit"]
    init = observations["S02B_PRE_T2_InitSession"]
    after = observations["S02B_PRE_T2_CommitAfterInit"]
    read_status = observations["S02B_PRE_T2_ReadStatus"]

    before_trace = before["trace"]
    init_trace = init["trace"]
    after_trace = after["trace"]
    read_trace = read_status["trace"]
    assert isinstance(before_trace, dict)
    assert isinstance(init_trace, dict)
    assert isinstance(after_trace, dict)
    assert isinstance(read_trace, dict)

    before_args = before["args"]
    after_args = after["args"]
    assert isinstance(before_args, dict)
    assert isinstance(after_args, dict)
    assert set(before_args) == {"amount_cents"}
    assert set(after_args) == {"amount_cents"}
    assert isinstance(before_args["amount_cents"], int)
    assert isinstance(after_args["amount_cents"], int)
    assert before_args["amount_cents"] > 0
    assert after_args["amount_cents"] > 0
    assert init["args"] == {}
    assert read_status["args"] == {}

    assert before_trace["raw_result"] == -3
    assert "Returned: -3" in str(before["result_excerpt"])
    assert before["classification"]["signed"] == -3
    assert before["classification"]["meaning"] == "not initialized"
    assert before["classification"]["source"] == "deterministic.default_sentinel"

    assert init_trace["raw_result"] == 0
    assert "Returned: 0" in str(init["result_excerpt"])
    assert init["classification"]["signed"] == 0

    assert after_trace["raw_result"] == 0
    assert "Returned: 0" in str(after["result_excerpt"])
    assert after["classification"]["signed"] == 0

    assert read_trace["raw_result"] == 7
    assert "Returned: 7" in str(read_status["result_excerpt"])
    assert read_status["classification"]["signed"] == 7
    assert read_status["classification"]["format_guess"] == "custom_positive_status_or_data"

    for row in (before, init, after, read_status):
        trace = row["trace"]
        assert isinstance(trace, dict)
        assert trace["backend"] == "dll"
        assert trace["function_name"] == row["function"]
        assert row["policy"] is None
        assert row.get("arg_sources") is not None
