#!/usr/bin/env python3
"""Stdlib-only bootstrap wrapper for managed discovery child diagnostics."""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Callable


DIAGNOSTIC_NAME = "discovery-child-interrupt.json"
RUNTIME_DIAGNOSTIC_NAME = "discovery-child-runtime.json"
_RUNTIME_PHASE_HISTORY: list[dict] = []


def _out_dir_from_argv(argv: list[str]) -> Path | None:
    for index, value in enumerate(argv):
        if value == "--out" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--out="):
            return Path(value.split("=", 1)[1])
    return None


def _bootstrap_source_hint(traceback_text: str) -> str:
    text = traceback_text.lower()
    if "_path_stat" in text:
        return "child_bootstrap_path_stat_interrupted"
    if "_find_and_load" in text or "importlib._bootstrap" in text:
        return "child_bootstrap_module_load_interrupted"
    return "child_bootstrap_import_interrupted"


def _write_bootstrap_interrupt_diagnostic(
    exc: BaseException,
    argv: list[str],
    *,
    phase: str,
    startup_ts: float,
) -> None:
    out_dir = _out_dir_from_argv(argv)
    if out_dir is None:
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        frames = traceback.extract_tb(exc.__traceback__)
        payload = {
            "schema_version": "1.0.0",
            "reason_code": "child_keyboard_interrupt",
            "source_hint": _bootstrap_source_hint(traceback_text),
            "bootstrap_phase": phase,
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "cwd": os.getcwd(),
            "argv": list(argv),
            "python_executable": sys.executable,
            "pythonpath": os.environ.get("PYTHONPATH", ""),
            "startup_ts": startup_ts,
            "diagnostic_ts": time.time(),
            "traceback_tail": traceback_text[-2000:],
            "stack_frames": [
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in frames[-8:]
            ],
        }
        (out_dir / DIAGNOSTIC_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Diagnostics must never become a second failure source for discovery.
        return


def _write_runtime_phase(
    argv: list[str],
    phase: str,
    *,
    startup_ts: float,
    details: dict | None = None,
) -> None:
    out_dir = _out_dir_from_argv(argv)
    if out_dir is None:
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / RUNTIME_DIAGNOSTIC_NAME
        entry = {"phase": phase, "observed_at": time.time()}
        _RUNTIME_PHASE_HISTORY.append(entry)
        payload = {
            "schema_version": "1.0.0",
            "source": "discovery_child_bootstrap",
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "cwd": os.getcwd(),
            "argv": list(argv),
            "python_executable": sys.executable,
            "pythonpath": os.environ.get("PYTHONPATH", ""),
            "startup_ts": startup_ts,
            "phase": phase,
            "phase_history": _RUNTIME_PHASE_HISTORY[-40:],
            "last_observation": dict(details or {}),
            "updated_at": time.time(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except BaseException:
        # Runtime diagnostics must never become a second failure source.
        return


def run(
    argv: list[str] | None = None,
    *,
    importer: Callable[[str], ModuleType] | None = None,
) -> int:
    """Import discovery main under a guard, then delegate with original argv."""
    global _RUNTIME_PHASE_HISTORY
    active_argv = list(sys.argv if argv is None else argv)
    previous_argv = sys.argv
    startup_ts = time.time()
    importer = importer or importlib.import_module
    _RUNTIME_PHASE_HISTORY = []
    sys.argv = active_argv
    try:
        _write_runtime_phase(active_argv, "bootstrap_import_start", startup_ts=startup_ts)
        discovery_main = importer("main")
        _write_runtime_phase(active_argv, "bootstrap_import_success", startup_ts=startup_ts)
        _write_runtime_phase(active_argv, "bootstrap_main_calling", startup_ts=startup_ts)
        result = int(discovery_main.main() or 0)
        _write_runtime_phase(
            active_argv,
            "bootstrap_main_returned",
            startup_ts=startup_ts,
            details={"returncode": result},
        )
        return result
    except KeyboardInterrupt as exc:
        _write_bootstrap_interrupt_diagnostic(
            exc,
            active_argv,
            phase="bootstrap_import_or_main",
            startup_ts=startup_ts,
        )
        raise
    except BaseException as exc:
        _write_runtime_phase(
            active_argv,
            "bootstrap_main_error",
            startup_ts=startup_ts,
            details={"exception_class": type(exc).__name__, "exception_message": str(exc)},
        )
        raise
    finally:
        sys.argv = previous_argv


if __name__ == "__main__":
    sys.exit(run())
