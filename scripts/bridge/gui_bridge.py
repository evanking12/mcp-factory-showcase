"""
gui_bridge.py â€” Windows-only analysis bridge
=============================================
Runs on any Windows machine with
pywinauto + pywin32 installed).  Exposes a small FastAPI HTTP server that
the managed local pipeline can call to perform analysers that require Windows:

  â€¢ GUI  (pywinauto UIA tree walk)
  â€¢ COM / Type Library  (pythoncom / pywin32)
  â€¢ CLI  (run Windows EXEs for --help output)
  â€¢ Registry scan  (winreg HKLM App Paths / Uninstall / COM CLSIDs)

Authentication: every request must carry  X-Bridge-Key: <BRIDGE_SECRET>
(set the BRIDGE_SECRET env var before starting this server).

Usage (on Windows):
    set BRIDGE_SECRET=<a long random string>
    python scripts/bridge/gui_bridge.py          # listens on 0.0.0.0:8090

The pipeline reads GUI_BRIDGE_URL (e.g. http://127.0.0.1:8090) and
GUI_BRIDGE_SECRET from its environment and calls
POST /analyze with:
    {
      "path":   "C:\\Windows\\System32\\calc.exe",   # or uploaded temp path
      "hints":  "calculator",
      "types":  ["gui", "com", "cli", "registry"]    # optional filter
    }

Returns standard discovery JSON  { "invocables": [...] }.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import ctypes
import hashlib
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from api.infra.local_lane_admission import (
    build_bridge_local_lane_admission,
    canonical_runtime_base_url,
)
from api.infra.service_identity import TRUST_CONTRACT_VERSION, build_bridge_identity, git_identity

# â”€â”€ ensure the discovery package is importable â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_ROOT = Path(__file__).resolve().parent.parent.parent
_DISCOVERY = _ROOT / "src" / "discovery"
for _p in [str(_ROOT), str(_DISCOVERY)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gui_bridge")

# â”€â”€ Analysis result cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Key: resolved absolute exe path (lowercased); value: (timestamp, result_dict).
# A warm cache hit skips re-launching the same binary on repeated uploads,
# which matters most for UWP stubs that require a full cold-start window wait.
_ANALYSIS_CACHE: dict[str, tuple[float, dict]] = {}
_ANALYSIS_CACHE_TTL = float("inf")  # indefinite â€” same binary never re-analyzed

# â”€â”€ Active analysis cancellation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Only one analysis runs at a time.  When a new /analyze request arrives,
# the current one is signalled to abort via kill_event and its launched
# process is killed so pywinauto unblocks from COM/UIA waits immediately.
# _run_analysis_sync checks kill_event between phases and returns early.
_active_kill_event: "threading.Event | None" = None
_active_target_stem: "str | None" = None
_active_lock = threading.Lock()


def _kill_processes_by_stem(stem: str) -> None:
    """Kill any running process whose name contains *stem* (case-insensitive)."""
    try:
        import psutil
        for proc in psutil.process_iter(["name", "pid"]):
            pname = (proc.info["name"] or "").lower()
            if stem in pname or pname.startswith(stem):
                try:
                    proc.kill()
                    logger.info("Killed lingering process %s (pid=%d)",
                                proc.info["name"], proc.info["pid"])
                except Exception:
                    pass
    except Exception:
        pass

# â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BRIDGE_SECRET = os.getenv("BRIDGE_SECRET", "")
if not BRIDGE_SECRET:
    logger.warning(
        "BRIDGE_SECRET env var is not set â€” "
        "the bridge will reject ALL requests.  "
        "Set it before starting the server."
    )

app = FastAPI(title="MCP Factory GUI Bridge", version="1.0.0")
_BRIDGE_PROCESS_STARTED_AT = time.time()
_BRIDGE_PROCESS_GIT_SHA, _BRIDGE_PROCESS_DIRTY = git_identity(_ROOT)
_BRIDGE_CAPABILITIES = (
    "analyze",
    "execute",
    "flush_dll_cache",
    "flush_analysis_cache",
)


def _bridge_identity_payload() -> dict[str, Any]:
    return build_bridge_identity(
        service_version=app.version,
        process_started_at=_BRIDGE_PROCESS_STARTED_AT,
        source_paths=(Path(__file__),),
        config_payload={
            "bridge_port": str(os.getenv("BRIDGE_PORT", "8090")).strip(),
            "bridge_secret_configured": bool(BRIDGE_SECRET),
            "python_executable": sys.executable,
        },
        capabilities=_BRIDGE_CAPABILITIES,
        git_sha=_BRIDGE_PROCESS_GIT_SHA,
        dirty=_BRIDGE_PROCESS_DIRTY,
    )


def _bridge_readiness_payload() -> dict[str, Any]:
    ready = bool(BRIDGE_SECRET)
    blocking_reasons = [] if ready else ["bridge_secret_missing"]
    return {
        "component": "bridge",
        "ready": ready,
        "checked_at": time.time(),
        "contract_version": TRUST_CONTRACT_VERSION,
        "capabilities": list(_BRIDGE_CAPABILITIES),
        "blocking_reason": "" if ready else blocking_reasons[0],
        "blocking_reasons": blocking_reasons,
    }


def _bridge_local_lane_admission_payload() -> dict[str, Any]:
    return build_bridge_local_lane_admission(
        identity_payload=_bridge_identity_payload(),
        readiness_payload=_bridge_readiness_payload(),
        process_started_at=_BRIDGE_PROCESS_STARTED_AT,
        source_paths=(
            Path(__file__),
            _ROOT / "api" / "infra" / "local_lane_admission.py",
        ),
        configured_base_url=canonical_runtime_base_url("bridge"),
        secret_configured=bool(BRIDGE_SECRET),
    )


def _bridge_health_payload() -> dict[str, Any]:
    admission_payload = _bridge_local_lane_admission_payload()
    healthy = bool(admission_payload.get("admitted"))
    blocking_reasons = list(admission_payload.get("blocking_reasons") or [])
    return {
        "component": "bridge",
        "status": "ok" if healthy else "blocked",
        "healthy": healthy,
        "checked_at": time.time(),
        "contract_version": TRUST_CONTRACT_VERSION,
        "runtime_mode": "strict_local",
        "configured_base_url": canonical_runtime_base_url("bridge"),
        "blocking_reason": "" if healthy else (blocking_reasons[0] if blocking_reasons else "local_lane_not_admitted"),
        "blocking_reasons": blocking_reasons,
        "diagnostics": {
            "alive": "/alive",
            "identity": "/identity",
            "readiness": "/readiness",
            "local_lane_admission": "/local-lane-admission",
        },
    }


def _check_auth(x_bridge_key: str) -> None:
    """Constant-time secret comparison â€” raises 401 on mismatch."""
    if not BRIDGE_SECRET or not secrets.compare_digest(x_bridge_key, BRIDGE_SECRET):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Bridge-Key")


# â”€â”€ Request / response models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class AnalyzeRequest(BaseModel):
    path: str
    hints: str = ""
    types: list[str] = [
        "gui", "com", "cli", "registry",
        "dotnet", "rpc",
        "sql", "wsdl", "idl", "js", "script", "openapi", "jndi",
        "ghidra",
    ]  # base64-encoded binary content (optional): lets the bridge analyze an
    # uploaded file whose Linux temp path doesn't exist on the Windows VM.
    content: str | None = None


class ExecuteRequest(BaseModel):
    invocable: dict
    args: dict = {}


# â”€â”€ Lazy analyzer imports (all Windows-only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _import_gui():
    from gui_analyzer import analyze_gui  # type: ignore
    return analyze_gui

def _import_com():
    from com_scan import scan_com_registry, com_objects_to_invocables  # type: ignore
    return scan_com_registry, com_objects_to_invocables

def _import_tlb():
    from tlb_analyzer import scan_type_library  # type: ignore
    return scan_type_library

def _import_cli():
    from cli_analyzer import analyze_cli  # type: ignore
    return analyze_cli

def _import_registry():
    from registry_analyzer import analyze_registry  # type: ignore
    return analyze_registry

def _import_dotnet():
    from dotnet_analyzer import get_dotnet_methods  # type: ignore
    return get_dotnet_methods

def _import_rpc():
    from rpc_analyzer import analyze_rpc, rpc_to_invocables  # type: ignore
    return analyze_rpc, rpc_to_invocables

def _import_sql():
    from sql_analyzer import analyze_sql  # type: ignore
    return analyze_sql

def _import_wsdl():
    from wsdl_analyzer import analyze_wsdl  # type: ignore
    return analyze_wsdl

def _import_idl():
    from idl_analyzer import analyze_idl  # type: ignore
    return analyze_idl

def _import_js():
    from js_analyzer import analyze_js  # type: ignore
    return analyze_js

def _import_script():
    from script_analyzer import analyze_script  # type: ignore
    return analyze_script

def _import_openapi():
    from openapi_analyzer import analyze_openapi  # type: ignore
    return analyze_openapi

def _import_jndi():
    from jndi_analyzer import analyze_jndi  # type: ignore
    return analyze_jndi

def _import_ghidra():
    from ghidra_analyzer import analyze_with_ghidra  # type: ignore
    return analyze_with_ghidra


def _inv_to_dict(inv: Any) -> dict:
    """Convert an Invocable dataclass (or dict) to a plain JSON-safe dict.

    Uses to_dict() when available so parameters is always a list
    (not the raw Optional[str] dataclass field) and all fields are
    in the canonical pipeline format.  Stringifies non-serializable
    values (Path objects, etc.) to prevent JSONResponse failures.
    """
    if isinstance(inv, dict):
        d = inv
    elif hasattr(inv, "to_dict"):
        d = inv.to_dict()
    else:
        d = {k: v for k, v in vars(inv).items() if not k.startswith("_")}

    # Recursively ensure everything is JSON-serializable
    return _make_serializable(d)


def _make_serializable(obj: Any) -> Any:
    """Recursively coerce Path / non-primitive objects to strings."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


# How long (seconds) to allow the GUI analyzer before giving up.
# pywinauto can hang for 90+ s on UWP stubs (e.g. calc.exe on Server 2022).
# Raised to 60 s to give Win11 UWP apps enough time to expose their UIA tree.
GUI_ANALYZE_TIMEOUT = 60


def _run_analysis_sync(target: Path, requested: set, hints: str,
                       kill_event: threading.Event,
                       progress: dict | None = None) -> dict:
    """Synchronous analysis worker â€” runs in a thread pool executor.

    Keeping all blocking I/O (pywinauto, COM, subprocess) in a plain function
    avoids stalling the uvicorn async event loop.

    kill_event is checked between each analysis phase.  When set (because a
    newer upload arrived), the function returns whatever partial results it has
    collected so far, freeing the thread immediately.
    """
    invocables: list[dict] = []
    errors: dict[str, str] = {}
    if progress is not None:
        progress.update({
            "worker_started": True,
            "current_phase": "start",
            "target_path": str(target),
            "requested_types": sorted(requested),
        })

    def _aborted() -> bool:
        if kill_event.is_set():
            logger.info("Analysis of %s superseded by newer request â€” stopping early",
                        target.name)
            errors["aborted"] = "superseded by newer upload"
            if progress is not None:
                progress["current_phase"] = "aborted"
            return True
        return False

    # â”€â”€ GUI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "gui" in requested and target.suffix.lower() == ".exe":
        try:
            if progress is not None:
                progress["current_phase"] = "gui_running"
            analyze_gui_fn = _import_gui()
            # Enforce a hard time-box: pywinauto retries can add up to 90+ s on
            # headless Server 2022 where UWP windows never appear.
            # NOTE: do NOT use `with ThreadPoolExecutor(â€¦) as pool` here â€”
            # shutdown(wait=True) blocks even after TimeoutError fires.
            # shutdown(wait=False) lets the hanging thread die in the background.
            _gui_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            _gui_future = _gui_pool.submit(analyze_gui_fn, target, 20)
            try:
                gui_results = _gui_future.result(timeout=GUI_ANALYZE_TIMEOUT)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "GUI analysis timed out after %ds for %s â€” killing process",
                    GUI_ANALYZE_TIMEOUT, target.name,
                )
                _kill_processes_by_stem(target.stem.lower())
                errors["gui"] = f"timed out after {GUI_ANALYZE_TIMEOUT}s"
                gui_results = []
            finally:
                _gui_pool.shutdown(wait=False)
            invocables.extend(_inv_to_dict(i) for i in gui_results)
            logger.info("GUI: %d invocables from %s", len(gui_results), target.name)
            if progress is not None:
                progress["current_phase"] = "gui_complete"
        except Exception as exc:
            logger.warning("GUI analysis failed: %s", exc)
            errors["gui"] = str(exc)
            if progress is not None:
                progress["current_phase"] = "gui_error"

    # â”€â”€ COM / Type Library â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "com" in requested:
        try:
            if progress is not None:
                progress["current_phase"] = "com_running"
            scan_type_library = _import_tlb()
            tlb_results = scan_type_library(target)
            for entry in tlb_results:
                for method in entry.get("methods", []):
                    execution: dict = {
                        "method":           "com_invoke",
                        "dll_path":         str(target),
                        "interface":        entry.get("name", ""),
                        "interface_guid":   entry.get("guid", ""),
                        "member":           method.get("name", ""),
                        # All CoClass CLSIDs in this TLB â€” tried in order at
                        # execute time until one exposes the method.
                        "coclass_candidates": entry.get("coclass_candidates", []),
                    }
                    invocables.append({
                        "name":        method.get("name", "unknown"),
                        "source_type": "com",
                        "signature":   method.get("signature", method.get("name", "")),
                        "confidence":  "high",
                        "dll_path":    str(target),
                        "doc_comment": method.get("doc", ""),
                        "parameters":  method.get("parameters", []),
                        "return_type": method.get("return_type", ""),
                        "execution":   execution,
                    })
            logger.info("COM/TLB: %d methods from %s", len(tlb_results), target.name)
            if progress is not None:
                progress["current_phase"] = "com_complete"
        except Exception as exc:
            logger.warning("COM/TLB analysis failed: %s", exc)
            errors["com"] = str(exc)
            if progress is not None:
                progress["current_phase"] = "com_error"

    # â”€â”€ CLI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "cli" in requested and target.suffix.lower() == ".exe":
        try:
            analyze_cli = _import_cli()
            results = analyze_cli(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("CLI: %d invocables from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("CLI analysis failed: %s", exc)
            errors["cli"] = str(exc)

    # â”€â”€ Registry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "registry" in requested:
        try:
            analyze_registry = _import_registry()
            # Always filter by the target's stem (e.g. "contoso_cs") so we only
            # return registry/COM entries that are actually related to this binary.
            # Using user-supplied hints as the filter is wrong â€” free-text like
            # "customer service COM DLL" would match every COM class entry.
            results = analyze_registry(hints=target.stem)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("Registry: %d invocables", len(results))
        except Exception as exc:
            logger.warning("Registry analysis failed: %s", exc)
            errors["registry"] = str(exc)

    # â”€â”€ .NET reflection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "dotnet" in requested and target.suffix.lower() in (".dll", ".exe"):
        try:
            get_dotnet_methods = _import_dotnet()
            results = get_dotnet_methods(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info(".NET: %d methods from %s", len(results), target.name)
        except Exception as exc:
            logger.warning(".NET analysis failed: %s", exc)
            errors["dotnet"] = str(exc)

    # â”€â”€ RPC interface detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "rpc" in requested and target.suffix.lower() in (".dll", ".exe"):
        try:
            analyze_rpc, rpc_to_invocables = _import_rpc()
            rpc_result = analyze_rpc(target)
            results = rpc_to_invocables(rpc_result, target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("RPC: %d interfaces from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("RPC analysis failed: %s", exc)
            errors["rpc"] = str(exc)

    # â”€â”€ SQL source files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "sql" in requested and target.suffix.lower() == ".sql":
        try:
            analyze_sql = _import_sql()
            results = analyze_sql(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("SQL: %d objects from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("SQL analysis failed: %s", exc)
            errors["sql"] = str(exc)

    # â”€â”€ WSDL / SOAP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "wsdl" in requested and target.suffix.lower() in (".wsdl", ".xml"):
        try:
            analyze_wsdl = _import_wsdl()
            results = analyze_wsdl(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("WSDL: %d operations from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("WSDL analysis failed: %s", exc)
            errors["wsdl"] = str(exc)

    # â”€â”€ CORBA IDL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "idl" in requested and target.suffix.lower() == ".idl":
        try:
            analyze_idl = _import_idl()
            results = analyze_idl(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("IDL: %d methods from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("IDL analysis failed: %s", exc)
            errors["idl"] = str(exc)

    # â”€â”€ JavaScript / TypeScript â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "js" in requested and target.suffix.lower() in (".js", ".ts", ".mjs", ".cjs"):
        try:
            analyze_js = _import_js()
            results = analyze_js(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("JS/TS: %d functions from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("JS/TS analysis failed: %s", exc)
            errors["js"] = str(exc)

    # â”€â”€ Scripts (Python, PowerShell, Batch, VBS, Shell, Ruby, PHP) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _SCRIPT_EXTS = (".py", ".ps1", ".bat", ".cmd", ".vbs", ".sh", ".bash", ".rb", ".php")
    if not _aborted() and "script" in requested and target.suffix.lower() in _SCRIPT_EXTS:
        try:
            analyze_script = _import_script()
            results = analyze_script(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("Script: %d invocables from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("Script analysis failed: %s", exc)
            errors["script"] = str(exc)

    # â”€â”€ OpenAPI / Swagger / JSON-RPC descriptors â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not _aborted() and "openapi" in requested and target.suffix.lower() in (".yaml", ".yml", ".json"):
        try:
            analyze_openapi = _import_openapi()
            results = analyze_openapi(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("OpenAPI: %d operations from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("OpenAPI analysis failed: %s", exc)
            errors["openapi"] = str(exc)

    # â”€â”€ JNDI bindings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _JNDI_EXTS = (".properties", ".jndi", ".xml")
    if not _aborted() and "jndi" in requested and target.suffix.lower() in _JNDI_EXTS:
        try:
            analyze_jndi = _import_jndi()
            results = analyze_jndi(target)
            invocables.extend(_inv_to_dict(i) for i in results)
            logger.info("JNDI: %d bindings from %s", len(results), target.name)
        except Exception as exc:
            logger.warning("JNDI analysis failed: %s", exc)
            errors["jndi"] = str(exc)

    # â”€â”€ Ghidra final fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Only run Ghidra when every other analyzer path yielded zero invocables.
    _PE_EXTS = (".dll", ".exe")
    if (not _aborted()
            and "ghidra" in requested
            and target.suffix.lower() in _PE_EXTS
            and len(invocables) == 0):
        try:
            logger.info("Ghidra fallback triggered for %s (all other analyzers returned 0)", target.name)
            if progress is not None:
                progress["current_phase"] = "ghidra_running"
                progress["ghidra_entered"] = True
                progress["ghidra_entered_at"] = time.time()
            analyze_with_ghidra = _import_ghidra()
            ghidra_results = analyze_with_ghidra(target, timeout_s=600, exported_only=True)
            invocables.extend(ghidra_results)
            logger.info("Ghidra: %d functions recovered from %s",
                        len(ghidra_results), target.name)
            if progress is not None:
                progress["current_phase"] = "ghidra_complete"
                progress["ghidra_exited"] = True
                progress["ghidra_exited_at"] = time.time()
        except Exception as exc:
            logger.warning("Ghidra analysis failed: %s", exc)
            errors["ghidra"] = str(exc)
            if progress is not None:
                progress["current_phase"] = "ghidra_error"
                progress["ghidra_error"] = str(exc)

    # De-duplicate by name
    seen: set[str] = set()
    unique: list[dict] = []
    for inv in invocables:
        name = inv.get("name", "")
        if name and name not in seen:
            seen.add(name)
            unique.append(inv)

    if progress is not None:
        progress["worker_completed"] = True
        progress["current_phase"] = "complete"
        progress["result_invocable_count"] = len(unique)
        progress["errors"] = dict(errors)
    return {
        "invocables": unique,
        "count":      len(unique),
        "errors":     errors,
        "source":     str(target),
    }


# â”€â”€ Main endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.post("/analyze")
async def analyze(
    body: AnalyzeRequest,
    x_bridge_key: str = Header(default=""),
):
    _check_auth(x_bridge_key)

    # Flush any cached DLL handles so the file can be overwritten on disk.
    _flush_dll_cache()

    tmp_dir: Path | None = None

    _UPLOAD_DIR = Path(r"C:\mcp-factory\uploads")
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if body.content:
        # The pipeline sent base64-encoded file bytes â€” decode to a persistent file.
        # This handles uploaded binaries whose Linux temp path doesn't exist on Windows.
        try:
            import shutil
            filename = Path(body.path).name
            target = _UPLOAD_DIR / filename
            # Decode first â€” a binascii.Error here means genuinely corrupt content.
            _decoded = base64.b64decode(body.content)
            target = _persistent_upload_path(_UPLOAD_DIR, filename, _decoded)
            try:
                if target.exists():
                    logger.info(
                        "Reusing decoded uploaded binary at %s (%d bytes)",
                        target, target.stat().st_size,
                    )
                else:
                    target.write_bytes(_decoded)
                    logger.info(
                        "Decoded uploaded binary to %s (%d bytes)",
                        target, target.stat().st_size,
                    )
            except OSError as _write_err:
                # The file may be locked because a previous /execute call loaded it
                # via ctypes.LoadLibrary and the handle wasn't released yet.
                # If the file already exists on disk (same binary, different session),
                # continue analysis with the existing copy rather than aborting.
                if target.exists():
                    logger.warning(
                        "Could not overwrite %s (%s) â€” file is locked by a loaded DLL; "
                        "reusing existing on-disk copy for analysis.",
                        target.name, _write_err,
                    )
                else:
                    raise  # truly missing upload â€” propagate as 500
            # Prefer the real system-path binary for GUI analysis â€” persistent copies
            # of UWP/MSIX stubs (e.g. calc.exe) can't trigger package activation
            # from arbitrary directories.  Search system paths directly by
            # filename instead of using _resolve_exe_path(), which short-circuits
            # when the persistent file itself already exists on disk.
            _sys_paths = [
                Path(r"C:\Windows\System32") / target.name,
                Path(r"C:\Windows") / target.name,
                Path(r"C:\Windows\SysWOW64") / target.name,
                Path(r"C:\Program Files") / target.name,
                Path(r"C:\Program Files (x86)") / target.name,
                # Microsoft Office DLLs â€” check all Office versions
                Path(r"C:\Program Files\Microsoft Office\root\Office16") / target.name,
                Path(r"C:\Program Files\Microsoft Office\root\Office15") / target.name,
                Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16") / target.name,
                Path(r"C:\Program Files (x86)\Microsoft Office\Office16") / target.name,
                Path(r"C:\Program Files (x86)\Microsoft Office\Office15") / target.name,
            ]
            for _sys_candidate in _sys_paths:
                if _sys_candidate.exists() and _sys_candidate.resolve() != target.resolve():
                    logger.info("Using system path %s for analysis instead of upload copy", _sys_candidate)
                    target = _sys_candidate
                    break
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not decode content: {exc}")
    else:
        target = Path(body.path)
        if not target.exists():
            # The path comes from the local pipeline process (e.g. /tmp/mcp_xyz/calc.exe).
            # It won't exist here â€” try to resolve the filename against Windows system paths.
            filename = Path(body.path).name
            system_candidates = [
                Path(r"C:\Windows\System32") / filename,
                Path(r"C:\Windows") / filename,
                Path(r"C:\Windows\SysWOW64") / filename,
                Path(r"C:\Program Files") / filename,
                Path(r"C:\Program Files (x86)") / filename,
            ]
            for candidate in system_candidates:
                if candidate.exists():
                    logger.info("Resolved '%s' â†’ '%s' via system path fallback", body.path, candidate)
                    target = candidate
                    break
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Path not found: {body.path} (also searched system paths for '{filename}')",
                )

    requested = set(body.types)

    # â”€â”€ Cache lookup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # When the request includes base64 content (a fresh upload), skip the cache
    # so code changes to the analyzer are always picked up on re-upload.
    _cache_key = str(target).lower()
    if not body.content:
        _cached = _ANALYSIS_CACHE.get(_cache_key)
        if _cached:
            _ts, _res = _cached
            if time.time() - _ts < _ANALYSIS_CACHE_TTL:
                logger.info("Cache hit for %s (%d invocables)", target.name, _res["count"])
                async def _cached_gen():
                    yield (json.dumps(_res) + "\n").encode()
                return StreamingResponse(_cached_gen(), media_type="application/x-ndjson")
    else:
        _ANALYSIS_CACHE.pop(_cache_key, None)
        logger.info("Fresh upload detected â€” cleared analysis cache for %s", target.name)

    # â”€â”€ Cancel any in-progress analysis and start fresh â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # If another upload is being analysed right now, signal it to stop and kill
    # whatever process it launched.  This frees COM/UIA locks immediately so
    # the new analysis can start without queuing behind a stuck pywinauto thread.
    global _active_kill_event, _active_target_stem
    kill_event = threading.Event()
    with _active_lock:
        if _active_kill_event is not None and not _active_kill_event.is_set():
            prev_stem = _active_target_stem or ""
            logger.info("New upload (%s) â€” aborting in-progress analysis of %s",
                        target.name, prev_stem or "unknown")
            _active_kill_event.set()
            if prev_stem:
                _kill_processes_by_stem(prev_stem)
        _active_kill_event = kill_event
        _active_target_stem = target.stem.lower()

    async def _generate():
        global _active_kill_event, _active_target_stem
        loop = asyncio.get_running_loop()
        bridge_progress: dict = {}
        heartbeat_count = 0
        future = loop.run_in_executor(
            None,  # default ThreadPoolExecutor
            _run_analysis_sync,
            target,
            requested,
            body.hints,
            kill_event,
            bridge_progress,
        )
        try:
            # Send a keepalive heartbeat every 15 s while the analysis runs.
            # Avoids idle HTTP timeouts on long analyses.
            # Using future.done() + asyncio.sleep avoids asyncio.wait_for /
            # asyncio.shield edge cases that can silently abort the generator.
            while not future.done():
                await asyncio.sleep(15)
                if not future.done():
                    heartbeat_count += 1
                    heartbeat = {
                        "status": "running",
                        "phase": bridge_progress.get("current_phase", "unknown"),
                        "worker_started": bool(bridge_progress.get("worker_started")),
                        "target_path": bridge_progress.get("target_path", str(target)),
                        "requested_types": bridge_progress.get("requested_types", sorted(requested)),
                        "ghidra_entered": bool(bridge_progress.get("ghidra_entered")),
                        "ghidra_exited": bool(bridge_progress.get("ghidra_exited")),
                        "worker_completed": bool(bridge_progress.get("worker_completed")),
                        "heartbeat_count": heartbeat_count,
                    }
                    yield (json.dumps(heartbeat) + "\n").encode()
            result = future.result()  # non-blocking: future is already done
        except Exception as exc:
            logger.error("Bridge analysis raised in generator: %s", exc)
            yield (json.dumps({"invocables": [], "count": 0, "errors": {"generator": str(exc)}}) + "\n").encode()
            return
        finally:
            # Release the global slot so the next request doesn't see a stale event.
            with _active_lock:
                if _active_kill_event is kill_event:
                    _active_kill_event = None
                    _active_target_stem = None
            # NOTE: uploaded binaries are now kept in C:\mcp-factory\uploads\
            # (not a temp dir) so they remain accessible for /execute calls.
            # tmp_dir is always None post-refactor; this guard is kept for safety.
            if tmp_dir is not None:
                try:
                    import shutil
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

        # Only cache results with more than 1 invocable â€” a count of 1 almost always
        # means the GUI analysis failed (cold-start) and only the CLI stub came back.
        # Skipping the cache forces a fresh retry on the next request.
        if result.get("count", 0) > 1:
            _ANALYSIS_CACHE[_cache_key] = (time.time(), result)
        else:
            logger.info(
                "Skipping cache for %s â€” only %d invocable(s) found (likely cold-start failure)",
                target.name, result.get("count", 0),
            )
        yield (json.dumps(result) + "\n").encode()

    return StreamingResponse(_generate(), media_type="application/x-ndjson")


# â”€â”€ Execution helpers (mirror of api/main.py â€” runs on Windows) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _resolve_exe_path(path: str) -> str:
    """Resolve a possibly-Linux temp path to a real Windows executable path."""
    p = Path(path)
    if p.exists():
        return str(p)
    filename = p.name
    candidates = [
        Path(r"C:\Windows\System32") / filename,
        Path(r"C:\Windows") / filename,
        Path(r"C:\Windows\SysWOW64") / filename,
        Path(r"C:\Program Files") / filename,
        Path(r"C:\Program Files (x86)") / filename,
    ]
    # Missing DLL temp paths must not silently degrade to a same-named legacy
    # upload copy. That can make analysis truthful while /execute loads a
    # different stale artifact.
    if p.suffix.lower() != ".dll":
        candidates.insert(0, Path(r"C:\mcp-factory\uploads") / filename)
    for candidate in candidates:
        if candidate.exists():
            logger.info("Resolved '%s' â†’ '%s'", path, candidate)
            return str(candidate)
    return path  # let the caller surface a natural error


def _execute_cli_bridge(execution: dict, name: str, args: dict) -> str:
    target = (
        execution.get("executable_path")
        or execution.get("target_path")
        or execution.get("dll_path", "")
    )
    if not target:
        return f"CLI error: no executable path configured for '{name}'"
    target = _resolve_exe_path(target)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # If the exe stem matches the invocable name, treat it as a launch invocable.
    # Check if it's already running first â€” avoids stacking duplicate windows.
    if Path(target).stem.lower() == name.lower():
        try:
            _running_app = _connect_app(target)
            return f"{Path(target).name} is already running â€” reusing existing window."
        except Exception:
            pass
        try:
            # Use shell `start ""` for MSIX/UWP stubs (e.g. calc.exe on Win10+)
            # which exit immediately when called via direct Popen. `start`
            # triggers proper COM/Shell activation and is safe for classic EXEs too.
            # Never use CREATE_NO_WINDOW here â€” it suppresses MSIX activation.
            subprocess.Popen(f'start "" "{target}"', shell=True)
            return f"Launched {Path(target).name}"
        except Exception as exc:
            return f"CLI error: {exc}"
    cmd = [target, name] + [str(v) for v in args.values()]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=no_window,
        )
        return r.stdout or r.stderr or f"exit_code={r.returncode}"
    except Exception as exc:
        return f"CLI error: {exc}"


def _connect_app(exe_path: str, title_re: str = ""):
    """Connect to a running app window generically â€” no hardcoding.

    Strategy (in order):
    1. Enumerate all open Desktop windows and find the one whose title or
       owning process name contains the exe stem. Works for UWP apps whose
       real process (e.g. CalculatorApp.exe) differs from the launcher
       (calc.exe), as well as classic Win32 apps.
    2. Fall back to pywinauto connect(path=...) for classic apps.
    3. If an explicit title_re was supplied, try that too.
    """
    import psutil  # type: ignore
    from pywinauto import Desktop  # type: ignore
    from pywinauto.application import Application  # type: ignore

    exe_stem = Path(exe_path).stem.lower()  # e.g. "calc", "notepad"

    # Walk all visible top-level windows
    best_handle = None
    for w in Desktop(backend="uia").windows():
        try:
            title = (w.window_text() or "").lower()
            pid   = w.element_info.process_id
            try:
                proc_name = (psutil.Process(pid).name() or "").lower()
            except Exception:
                proc_name = ""
            if exe_stem in title or exe_stem in proc_name:
                best_handle = w.handle
                break
        except Exception:
            continue

    if best_handle:
        return Application(backend="uia").connect(handle=best_handle)

    # Fallback: classic Win32 connect by path
    if title_re:
        try:
            return Application(backend="uia").connect(title_re=title_re, timeout=3)
        except Exception:
            pass
    return Application(backend="uia").connect(path=exe_path, timeout=5)


def _read_display(app) -> str:
    """Try to read the current display value from the top window."""
    def _clean(t: str) -> str:
        # UWP Calculator prefixes values with accessibility text e.g. "Display is 8"
        import re
        t = re.sub(r"^(?:Display is|Result is|Expression is)\s*", "", t, flags=re.IGNORECASE)
        return t.strip()

    try:
        win = app.top_window()
        # Try common automation IDs for calculator/display controls
        for aid in ("CalculatorResults", "Display", "Result", "output", "NormalOutput"):
            try:
                t = win.child_window(auto_id=aid).window_text().strip()
                if t:
                    return _clean(t)
            except Exception:
                pass
        # Prefer a Text descendant that contains a digit (the numeric display)
        for ctrl in win.descendants(control_type="Text"):
            try:
                t = ctrl.window_text().strip()
                if t and any(c.isdigit() for c in t):
                    return _clean(t)
            except Exception:
                pass
        # Last resort: first non-empty Text descendant
        for ctrl in win.descendants(control_type="Text"):
            try:
                t = ctrl.window_text().strip()
                if t:
                    return _clean(t)
            except Exception:
                pass
    except Exception:
        pass
    return ""


def _execute_gui_bridge(execution: dict, name: str, args: dict) -> str:
    try:
        from pywinauto.application import Application  # type: ignore
    except ImportError:
        return "pywinauto is not installed on the bridge VM."
    exe_path    = _resolve_exe_path(execution.get("exe_path", ""))
    action_type = execution.get("action_type", "launch")
    if action_type in ("launch", "open_app") or not exe_path:
        try:
            # Use shell `start ""` so MSIX/UWP stubs get proper COM/Explorer
            # activation instead of a direct Popen (which exits immediately for
            # UWP stubs and is silently dropped in Session 0).
            subprocess.Popen(f'start "" "{exe_path}"', shell=True)
            # Poll for a visible window so callers get a meaningful error when
            # running in Session 0 (where the window never materialises).
            deadline = time.time() + 6
            window_found = False
            while time.time() < deadline:
                time.sleep(0.5)
                try:
                    _connect_app(exe_path)
                    window_found = True
                    break
                except Exception:
                    pass
            if not window_found:
                # Check whether the bridge itself is in a Session 0 (no desktop).
                try:
                    import ctypes
                    _sid = ctypes.windll.kernel32.WTSGetActiveConsoleSessionId()
                    _process_session = ctypes.c_ulong(0)
                    ctypes.windll.kernel32.ProcessIdToSessionId(
                        os.getpid(), ctypes.byref(_process_session))
                    if _process_session.value == 0:
                        return (
                            f"GUI launch error: bridge is running in Session 0 "
                            f"(SYSTEM service) â€” GUI windows cannot appear on the desktop. "
                            f"Restart gui_bridge.py as an interactive user: "
                            f"run install-bridge-service.ps1 on the VM."
                        )
                except Exception:
                    pass
                return (
                    f"Launched {Path(exe_path).name} but no window appeared within 6 s "
                    f"(possible Session 0 isolation or UWP activation failure)."
                )
            return f"Launched {Path(exe_path).name}"
        except Exception as exc:
            return f"GUI launch error: {exc}"
    if action_type == "close_app":
        try:
            app = _connect_app(exe_path)
            app.kill()
            return "App closed."
        except Exception as exc:
            return f"GUI close error: {exc}"
    if action_type == "menu_click":
        menu_path = args.get("menu_path") or execution.get("menu_path", "")
        try:
            app = _connect_app(exe_path)
            app.top_window().set_focus()
            app.top_window().menu_select(menu_path)
            return f"Menu '{menu_path}' selected."
        except Exception as exc:
            return f"GUI menu error: {exc}"
    if action_type == "button_click":
        button = args.get("button") or execution.get("button_name") or execution.get("button", "")
        try:
            app = _connect_app(exe_path)
            win = app.top_window()
            win.set_focus()
            # Try child_window by title first, fall back to bracket notation
            try:
                btn = win.child_window(title=button, control_type="Button")
                btn.click()
            except Exception:
                win[button].click()
            import time; time.sleep(0.3)
            display = _read_display(app)
            result = f"Clicked '{button}'."
            if display:
                result += f" Display shows: {display}"
            return result
        except Exception as exc:
            return f"GUI button error: {exc}"
    return f"GUI action '{action_type}' dispatched for '{Path(exe_path).name}'."


# â”€â”€ COM CLSID candidate cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_COM_CLSID_CACHE: dict[str, list[str]] = {}  # dll_name_lower â†’ [clsid, ...]
_MAX_COM_CANDIDATES = 25  # cap per-DLL to avoid iterating all 10 k+ CLSIDs


def _get_com_candidates(dll_lc: str) -> list[str]:
    """Return CLSIDs (strings) whose InprocServer32 DLL name matches dll_lc.

    Results are cached after the first call so subsequent tool invocations
    on the same DLL are instant.
    """
    if dll_lc in _COM_CLSID_CACHE:
        return _COM_CLSID_CACHE[dll_lc]
    import winreg
    found: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "CLSID") as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                if len(found) >= _MAX_COM_CANDIDATES:
                    break
                try:
                    clsid = winreg.EnumKey(root, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(root, f"{clsid}\\InprocServer32") as sk:
                        srv, _ = winreg.QueryValueEx(sk, "")
                    if dll_lc in srv.lower():
                        found.append(clsid)
                except OSError:
                    pass
    except OSError:
        pass
    _COM_CLSID_CACHE[dll_lc] = found
    return found


def _com_call_with_auto_dismiss(fn, arg_values: list, dialog_timeout: float = 20.0):
    """Call a COM method in a daemon thread.

    If the call doesn't return within 2 s (i.e. it opened a blocking modal
    dialog), use pywinauto to find the dialog window and click its primary
    accept button (OK / Select Folder / Open / Yes).  This lets the bridge
    serve users who have no direct access to the VM desktop.

    Returns the COM call's return value, or raises the exception it raised.
    """
    import threading

    result_box: list = [None]
    error_box:  list = [None]
    done_event = threading.Event()

    def _run():
        try:
            result_box[0] = fn(*arg_values) if arg_values else fn()
        except Exception as exc:
            error_box[0] = exc
        finally:
            done_event.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    # Fast path: method returned before a dialog could open
    if done_event.wait(timeout=2.0):
        if error_box[0] is not None:
            raise error_box[0]
        return result_box[0]

    # Slow path: assume a modal dialog is open â€” try to dismiss it
    logger.info("COM call is blocking â€” attempting auto-dismiss of modal dialog")
    _auto_dismiss_com_dialog(timeout=dialog_timeout)

    # Wait for the COM thread to finish after the dialog is gone
    done_event.wait(timeout=5.0)
    if error_box[0] is not None:
        raise error_box[0]
    return result_box[0]


def _auto_dismiss_com_dialog(timeout: float = 20.0) -> str | None:
    """Poll the desktop for a modal dialog and click its primary accept button.

    Uses win32gui directly (EnumWindows + EnumChildWindows) so it works
    regardless of pywinauto backend quirks.  Recognises common accept-button
    labels for BrowseForFolder, file-open pickers, message boxes, etc.
    Returns a description of what was clicked, or None if nothing was found.
    """
    import time as _time
    import win32gui
    import win32con

    _OK_LABELS = {"OK", "Select Folder", "Open", "Accept", "Yes", "Select", "Choose"}
    _clicked: list = []

    def _try_click_ok(dialog_hwnd: int, dialog_title: str) -> bool:
        """Return True if an accept button was found and clicked."""
        result: list = [False]

        def _enum_children(child_hwnd, _param):
            if result[0]:
                return  # already clicked
            try:
                cls  = win32gui.GetClassName(child_hwnd)
                text = win32gui.GetWindowText(child_hwnd)
                if cls == "Button" and text in _OK_LABELS:
                    if win32gui.IsWindowVisible(child_hwnd) and win32gui.IsWindowEnabled(child_hwnd):
                        # BM_CLICK is the most reliable way to press a button
                        # without needing to move the mouse cursor.
                        win32gui.SendMessage(child_hwnd, win32con.BM_CLICK, 0, 0)
                        logger.info(
                            "Auto-dismissed dialog '%s' via button '%s'",
                            dialog_title, text,
                        )
                        _clicked.append(f"dialog '{dialog_title}' dismissed via '{text}'")
                        result[0] = True
            except Exception:
                pass

        try:
            win32gui.EnumChildWindows(dialog_hwnd, _enum_children, None)
        except Exception:
            pass
        return result[0]

    deadline = _time.monotonic() + timeout

    while _time.monotonic() < deadline:
        _time.sleep(0.3)

        top_windows: list[tuple[int, str]] = []

        def _enum_top(hwnd, _param):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    top_windows.append((hwnd, win32gui.GetWindowText(hwnd)))
            except Exception:
                pass

        try:
            win32gui.EnumWindows(_enum_top, None)
        except Exception:
            continue

        for hwnd, title in top_windows:
            if _try_click_ok(hwnd, title):
                return _clicked[-1]

    logger.warning("Auto-dismiss: no clickable dialog found within %.0f s", timeout)
    return None


def _execute_com_bridge(inv: dict, execution: dict, args: dict) -> str:
    """Invoke a COM method on an object hosted in the target DLL.

    Accepts both method="com_invoke" (legacy) and method="com_dispatch" (schema).
    Resolution priority:
      1. If execution has a 'clsid', dispatch it directly.
      2. Otherwise scan the registry for CoClasses whose InprocServer32 matches
         the dll_path, then try each one.
    """
    import win32com.client  # pywin32 â€“ installed alongside pythoncom

    # Schema uses 'function_name'; legacy invocables use 'member'.
    member = (
        execution.get("member")
        or execution.get("function_name")
        or inv.get("name", "")
    )

    if not member:
        return "COM invoke error: no member/method specified in execution config"

    # Shell special-folder name â†’ SHSpecialFolderID constant.
    # IShellDispatch.NameSpace (and similar) accept an integer VARIANT for
    # well-known folders; the model often supplies a friendly name instead.
    _SHELL_FOLDER_CONSTANTS: dict[str, int] = {
        "desktop": 0, "internet": 1, "programs": 2, "controls": 3,
        "printers": 4, "personal": 5, "my documents": 5, "favorites": 6,
        "startup": 7, "recent": 8, "sendto": 9, "bitbucket": 10,
        "recycle bin": 10, "startmenu": 11, "start menu": 11,
        "mydocuments": 5, "mymusic": 13, "my music": 13,
        "myvideo": 14, "my video": 14, "desktopdirectory": 16,
        "drives": 17, "my computer": 17, "mycomputer": 17, "network": 18,
        "nethood": 19, "fonts": 20, "templates": 21, "appdata": 26,
        "printhood": 27, "localappdata": 28, "windows": 36, "system": 37,
        "programfiles": 38, "program files": 38, "mypictures": 39,
        "my pictures": 39, "profile": 40, "systemx86": 41,
        "programfilesx86": 42, "commonfiles": 43, "commonprograms": 46,
        "commonstartmenu": 47, "commondesktop": 48, "commonappdata": 35,
        "commontemplates": 45, "commondocuments": 46, "downloads": 374,
    }

    def _coerce_com_arg(v: object) -> object:
        """Coerce a model-supplied string to int/float for COM VARIANT args."""
        if not isinstance(v, str):
            return v
        lv = v.strip().lower()
        if lv in _SHELL_FOLDER_CONSTANTS:
            return _SHELL_FOLDER_CONSTANTS[lv]
        try:
            return int(v)
        except (ValueError, TypeError):
            pass
        try:
            return float(v)
        except (ValueError, TypeError):
            pass
        return v

    arg_values  = [_coerce_com_arg(v) for v in args.values()]
    errors_seen: list[str] = []

    # Build candidate list in priority order:
    #   1. direct clsid (explicitly stored, most precise)
    #   2. coclass_candidates from TLB analysis (stored at analyze time)
    #   3. lazy TLB scan from the DLL right now (catches stale invocables that
    #      pre-date the coclass_candidates fix â€” no re-upload required)
    #   4. registry scan by DLL name (last resort)
    direct_clsid   = execution.get("clsid") or inv.get("clsid")
    tlb_candidates = execution.get("coclass_candidates") or []
    dll_path = _resolve_exe_path(execution.get("dll_path", ""))
    dll_lc   = Path(dll_path).name.lower() if dll_path else ""

    # Lazy TLB scan: if no stored candidates, load the DLL's type library now
    lazy_tlb_candidates: list = []
    if not tlb_candidates and dll_path and Path(dll_path).exists():
        try:
            import pythoncom as _pc
            _tlb = _pc.LoadTypeLib(dll_path)
            for _i in range(_tlb.GetTypeInfoCount()):
                try:
                    _ti   = _tlb.GetTypeInfo(_i)
                    _attr = _ti.GetTypeAttr()
                    if _attr.typekind == 5:  # TKIND_COCLASS
                        lazy_tlb_candidates.append(str(_attr.iid))
                except Exception:
                    pass
            logger.info("COM lazy TLB scan of '%s': %d CoClass candidates",
                        dll_lc, len(lazy_tlb_candidates))
        except Exception as _e:
            logger.debug("COM lazy TLB scan failed for '%s': %s", dll_lc, _e)

    # Deduplicated ordered candidate list
    seen: set = set()
    ordered_candidates: list = []
    for c in ([direct_clsid] if direct_clsid else []) + tlb_candidates + lazy_tlb_candidates:
        if c and c not in seen:
            seen.add(c)
            ordered_candidates.append(c)

    source = "stored TLB" if tlb_candidates else ("lazy TLB" if lazy_tlb_candidates else "registry")
    # Only fall back to registry scan if TLB (stored or lazy) gave us nothing
    if not ordered_candidates and dll_lc:
        ordered_candidates = _get_com_candidates(dll_lc)
        source = "registry"

    logger.info("COM dispatch '%s' on '%s': %d candidates from %s",
                member, dll_lc, len(ordered_candidates), source)

    if not ordered_candidates:
        return (
            f"COM invoke error: no CoClass candidates for '{dll_lc}' "
            f"and no CLSID/TLB data in execution config. Cannot dispatch '{member}'."
        )

    method_found_on: str | None = None  # tracks first CLSID where member exists
    call_errors: list[str] = []

    for clsid in ordered_candidates:
        try:
            obj = win32com.client.Dispatch(clsid)
        except Exception as ex:
            errors_seen.append(f"{clsid}: Dispatch failed: {ex}")
            continue

        fn = getattr(obj, member, None)
        if fn is None:
            continue

        # Member exists on this object â€” record it even if the call fails
        if method_found_on is None:
            method_found_on = clsid

        try:
            result = _com_call_with_auto_dismiss(fn, arg_values)
            return f"Returned: {result}"
        except Exception as call_ex:
            call_str = str(call_ex)
            call_errors.append(f"{clsid}: {call_str}")
            # "Invalid number of parameters" â€” try as a property (no-call)
            if "parameter" in call_str.lower() or "argument" in call_str.lower():
                try:
                    prop = getattr(obj, member)
                    if not callable(prop):
                        return f"Returned: {prop}"
                except Exception:
                    pass

    if method_found_on:
        # Method WAS found but every call attempt failed â€” likely missing required args
        _raw_hint = (
            execution.get("parameters")
            or inv.get("parameters")
            or []
        )
        # Normalise: list of dicts â†’ list of names; list of strings â†’ keep as-is
        if _raw_hint and isinstance(_raw_hint[0], dict):
            param_hint = [p.get("name", str(p)) for p in _raw_hint]
        else:
            param_hint = list(_raw_hint)
        hint = f" Expected parameters: {param_hint}" if param_hint else \
               " Provide required arguments (e.g. a folder path for Open)."
        return (
            f"COM method '{member}' found on {method_found_on} but call failed. "
            f"Errors: {'; '.join(call_errors[:3])}.{hint}"
        )

    return (
        f"COM invoke error: none of {len(ordered_candidates)} CoClass candidate(s) "
        f"for '{dll_lc}' expose '{member}'. "
        f"Errors: {'; '.join(errors_seen[:3])}"
    )


def _execute_script_bridge(execution: dict, name: str, args: dict) -> str:
    """Execute a script-based invocable (Python, PowerShell, Node, Ruby, PHP, etc.).

    Builds the appropriate interpreter command from the execution metadata
    produced by schema.Invocable._get_execution_metadata() and runs it as a
    subprocess.  Supports every method the schema defines for JIT languages.
    """
    method      = execution.get("method", "")
    script_path = (
        execution.get("script_path")
        or execution.get("module_path")
        or execution.get("example", "")  # fallback: parse from example
    )
    func_name   = execution.get("function_name", "") or execution.get("method_name", "")
    arg_values  = list(args.values())

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # If the stored path is a Linux /tmp path that doesn't exist on this Windows
    # host, materialise the embedded script_content into a local temp file.
    _tmp_path: "str | None" = None
    script_content = execution.get("script_content")
    if script_path and not Path(script_path).exists() and script_content:
        suffix = Path(script_path).suffix or ".tmp"
        fd, _tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as _f:
                _f.write(script_content)
            script_path = _tmp_path
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            _tmp_path = None

    try:
        if method == "python_subprocess":
            # python -c "import importlib.util; spec=...; m.func(args)"
            arg_repr = ", ".join(repr(v) for v in arg_values)
            code = (
                f"import importlib.util, sys; "
                f"spec=importlib.util.spec_from_file_location('m', r'{script_path}'); "
                f"m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                f"print(m.{func_name}({arg_repr}))"
            ) if func_name else (
                f"exec(open(r'{script_path}').read())"
            )
            cmd = ["python", "-c", code]

        elif method in ("node", "ts-node"):
            interp = "ts-node" if method == "ts-node" else "node"
            if func_name:
                arg_repr = ", ".join(repr(v) for v in arg_values)
                code = f"const m=require('{script_path}'); console.log(m.{func_name}({arg_repr}))"
                cmd = [interp, "-e", code]
            else:
                cmd = [interp, script_path]

        elif method == "powershell":
            if func_name:
                arg_str = " ".join(f'"{v}"' for v in arg_values)
                cmd = [
                    "powershell", "-NoProfile", "-NonInteractive",
                    "-Command",
                    f". '{script_path}'; {func_name} {arg_str}",
                ]
            else:
                cmd = ["powershell", "-NoProfile", "-NonInteractive", "-File", script_path]

        elif method == "cmd_call":
            label = execution.get("label", func_name)
            arg_str = " ".join(str(v) for v in arg_values)
            cmd = ["cmd", "/c", f'call "{script_path}" :{label} {arg_str}'.strip()]

        elif method in ("bash",):
            if func_name:
                arg_str = " ".join(f'"{v}"' for v in arg_values)
                cmd = ["bash", "-c", f'source "{script_path}"; {func_name} {arg_str}']
            else:
                cmd = ["bash", script_path] + [str(v) for v in arg_values]

        elif method == "ruby":
            if func_name:
                arg_repr = ", ".join(repr(v) for v in arg_values)
                cmd = ["ruby", "-r", script_path, "-e", f"puts {func_name}({arg_repr})"]
            else:
                cmd = ["ruby", script_path] + [str(v) for v in arg_values]

        elif method == "php":
            if func_name:
                arg_repr = ", ".join(f'"{v}"' for v in arg_values)
                cmd = ["php", "-r", f"require '{script_path}'; echo {func_name}({arg_repr});"]
            else:
                cmd = ["php", script_path] + [str(v) for v in arg_values]

        elif method == "cscript":
            cmd = ["cscript", "//nologo", script_path] + [str(v) for v in arg_values]

        elif method == "cmd":
            cmd = ["cmd", "/c", script_path] + [str(v) for v in arg_values]

        else:
            return f"Script error: unsupported method '{method}'"

        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=no_window,
        )
        return r.stdout or r.stderr or f"exit_code={r.returncode}"

    except FileNotFoundError as exc:
        return f"Script error: interpreter not found â€” {exc}"
    except subprocess.TimeoutExpired:
        return "Script error: timed out after 30 s"
    except Exception as exc:
        return f"Script error: {exc}"
    finally:
        if _tmp_path:
            try:
                os.unlink(_tmp_path)
            except OSError:
                pass


def _execute_dotnet_bridge(execution: dict, name: str, args: dict) -> str:
    """Invoke a .NET method on this Windows VM via PowerShell reflection."""
    assembly  = execution.get("assembly_path", "")
    type_name = execution.get("type_name", "")
    func      = execution.get("function_name", name)
    is_static = execution.get("is_static", False)

    if not assembly:
        return ".NET error: no assembly_path in execution config"

    # Build argument list for PowerShell
    ps_args = ", ".join(f'"{v}"' for v in args.values()) if args else ""

    if is_static:
        invoke_expr = f'[{type_name}]::{func}({ps_args})'
        ps_script   = (
            f"$asm = [System.Reflection.Assembly]::LoadFile('{assembly}'); "
            f"$result = {invoke_expr}; "
            f"Write-Output $result"
        )
    else:
        ps_script = (
            f"$asm = [System.Reflection.Assembly]::LoadFile('{assembly}'); "
            f"$obj = [Activator]::CreateInstance($asm.GetType('{type_name}')); "
            f"$result = $obj.{func}({ps_args}); "
            f"Write-Output $result"
        )

    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.stdout.strip() or r.stderr.strip() or f"exit_code={r.returncode}"
    except subprocess.TimeoutExpired:
        return ".NET error: timed out after 30 s"
    except Exception as exc:
        return f".NET error: {exc}"


def _execute_http_bridge(execution: dict, name: str, args: dict) -> str:
    """Dispatch HTTP-based invocables: OpenAPI, JSON-RPC, SOAP.

    Requires a 'base_url' key in the execution dict (populated at chat time
    from the user-provided server URL), or falls back to a localhost default.
    """
    import json as _json
    method = execution.get("method", "")

    try:
        import httpx as _httpx
    except ImportError:
        return "HTTP error: httpx not installed on the bridge VM"

    base_url = execution.get("base_url", "http://localhost")

    try:
        if method == "http_request":
            http_method = execution.get("http_method", "get").upper()
            path        = execution.get("path", "/")
            url         = base_url.rstrip("/") + "/" + path.lstrip("/")
            resp = _httpx.request(http_method, url, json=args or None, timeout=15)
            return resp.text or f"HTTP {resp.status_code}"

        elif method == "jsonrpc":
            url     = base_url.rstrip("/")
            payload = {"jsonrpc": "2.0", "method": name, "params": list(args.values()), "id": 1}
            resp    = _httpx.post(url, json=payload, timeout=15)
            data    = resp.json()
            if "error" in data:
                return f"JSON-RPC error: {data['error']}"
            return _json.dumps(data.get("result"), indent=2)

        elif method == "soap":
            url    = base_url.rstrip("/")
            action = execution.get("action", name)
            params_xml = "".join(
                f"<{k}>{v}</{k}>" for k, v in args.items()
            )
            body = (
                '<?xml version="1.0"?>'
                '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"'
                ' xmlns:tns="urn:service">'
                f'<soapenv:Body><tns:{action}>{params_xml}</tns:{action}></soapenv:Body>'
                '</soapenv:Envelope>'
            )
            resp = _httpx.post(
                url,
                content=body.encode(),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": f'"{action}"',
                },
                timeout=15,
            )
            return resp.text

        else:
            return f"HTTP error: unsupported method '{method}'"

    except Exception as exc:
        return f"HTTP error: {exc}"


def _execute_sql_bridge(execution: dict, name: str, args: dict) -> str:
    """Execute a SQL object (procedure, function, view, table) via sqlite3 subprocess.

    For source .sql files the connection_required flag is always True, but
    MCP Factory does not currently manage a live DB connection string.
    This dispatcher handles SQLite (.db / .sqlite) targets directly; for
    SQL Server / PostgreSQL it returns the parameterized statement so the
    user can run it manually.
    """
    source_file = execution.get("source_file", "")
    statement   = execution.get("statement", "")
    obj_type    = execution.get("object_type", "")

    # If source file is a SQLite DB, run directly
    db_exts = {".db", ".sqlite", ".sqlite3"}
    if source_file and Path(source_file).suffix.lower() in db_exts:
        try:
            r = subprocess.run(
                ["sqlite3", source_file, statement],
                capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return r.stdout or r.stderr or f"exit_code={r.returncode}"
        except FileNotFoundError:
            pass  # sqlite3 CLI not in PATH, fall through to informational
        except Exception as exc:
            return f"SQL error: {exc}"

    # Non-SQLite: return the parameterized statement for the user to execute
    param_hints = "; ".join(f"{k}={v}" for k, v in args.items())
    note = f"  -- params: {param_hints}" if param_hints else ""
    return (
        f"-- {obj_type.upper()} '{name}' discovered in {Path(source_file).name if source_file else 'unknown'}\n"
        f"-- Execute against your target database:\n"
        f"{statement}{note}"
    )


_DLL_CACHE: dict[str, "ctypes.WinDLL | ctypes.CDLL"] = {}
_DLL_CACHE_LOCK = threading.Lock()
_DLL_CACHE_GENERATION = 0
_DLL_RUNTIME_COPY_DIR = Path(r"C:\mcp-factory\runtime-dlls")
_DLL_DIR_HANDLES: dict[str, Any] = {}
_DLL_ACTIVE_RUNTIME_DIR: str | None = None
_BRIDGE_BREADCRUMB_PATH = _ROOT / "sessions" / "bridge-execute-breadcrumbs.jsonl"
_BRIDGE_BREADCRUMB_LOCK = threading.Lock()
_DLL_EXECUTE_WORKER_PATH = Path(__file__).with_name("dll_execute_worker.py")
_DLL_EXECUTE_TIMEOUT_SECONDS = 60


def _summarize_execute_args(args: dict) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in (args or {}).items():
        if isinstance(value, (int, float, bool)) or value is None:
            summary[key] = value
            continue
        if isinstance(value, bytes):
            summary[key] = f"<bytes:{len(value)}>"
            continue
        text = str(value)
        if len(text) > 80:
            text = text[:77] + "..."
        summary[key] = text
    return summary


def _write_execute_breadcrumb(event: dict[str, Any]) -> None:
    payload = {"ts": time.time(), **(event or {})}
    try:
        _BRIDGE_BREADCRUMB_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        with _BRIDGE_BREADCRUMB_LOCK:
            with _BRIDGE_BREADCRUMB_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
    except Exception as exc:
        logger.warning("Failed to write execute breadcrumb: %s", exc)


def _persistent_upload_path(upload_dir: Path, original_name: str, content: bytes) -> Path:
    """Return a stable content-addressed upload path for bridge-side binaries."""
    source = Path(original_name or "upload.bin")
    stem = source.stem or "upload"
    safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem).strip("._")
    if not safe_stem:
        safe_stem = "upload"
    suffix = source.suffix or ".bin"
    digest = hashlib.sha256(content).hexdigest()[:16]
    return upload_dir / f"{safe_stem}-{digest}{suffix}"


def _runtime_execution_copy_path(runtime_dir: Path, original_path: str, generation: int) -> Path:
    """Return the per-generation runtime DLL copy path used for execution.

    The bridge intentionally keeps one loaded DLL handle alive during a
    pipeline session so state can accumulate within that run. A cache flush
    should therefore force the next run onto a fresh on-disk copy so Windows
    cannot silently reuse a still-live module handle for the same path.
    """
    source = Path(original_path or "upload.dll")
    stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in source.stem).strip("._")
    if not stem:
        stem = "upload"
    suffix = source.suffix or ".dll"
    digest = hashlib.sha256(str(source).lower().encode("utf-8")).hexdigest()[:12]
    return runtime_dir / f"{stem}-{digest}-g{int(generation)}{suffix}"


def _copy_runtime_sibling_dlls(source: Path, runtime_dir: Path) -> list[Path]:
    """Copy sibling DLL dependencies next to the runtime execution copy.

    Interwoven fixtures and some real-world legacy DLLs rely on sibling DLLs
    being discoverable via the Windows loader. When the bridge executes a fresh
    generation-scoped copy, copy those sibling DLLs into the same generation
    directory so runtime behavior still matches the source fixture layout.
    """
    copied: list[Path] = []
    if source.suffix.lower() != ".dll" or not source.exists():
        return copied
    try:
        source_resolved = source.resolve()
    except Exception:
        source_resolved = source
    for candidate in sorted(source.parent.glob("*.dll")):
        try:
            if candidate.resolve() == source_resolved:
                continue
        except Exception:
            if candidate == source:
                continue
        destination = runtime_dir / candidate.name
        if not destination.exists():
            shutil.copyfile(candidate, destination)
        copied.append(destination)
    return copied


def _activate_runtime_dll_directory(runtime_dir: Path) -> None:
    """Make a generation runtime directory visible to plain LoadLibrary calls.

    Some DLLs load sibling dependencies explicitly via LoadLibraryA("name.dll"),
    which does not automatically search the loaded module's directory. Activate
    the generation directory on the bridge process so those sibling lookups can
    resolve during execution.
    """
    global _DLL_ACTIVE_RUNTIME_DIR
    runtime_dir_str = str(runtime_dir)
    runtime_key = runtime_dir_str.lower()
    if _DLL_ACTIVE_RUNTIME_DIR == runtime_key:
        return

    try:
        result = ctypes.windll.kernel32.SetDllDirectoryW(runtime_dir_str)
        if result:
            _DLL_ACTIVE_RUNTIME_DIR = runtime_key
        else:
            logger.warning("SetDllDirectoryW failed for %s", runtime_dir_str)
    except Exception as exc:
        logger.warning("SetDllDirectoryW failed for %s: %s", runtime_dir_str, exc)

    add_dir = getattr(os, "add_dll_directory", None)
    if callable(add_dir) and runtime_key not in _DLL_DIR_HANDLES:
        try:
            _DLL_DIR_HANDLES[runtime_key] = add_dir(runtime_dir_str)
        except Exception as exc:
            logger.warning("add_dll_directory failed for %s: %s", runtime_dir_str, exc)


def _get_cached_dll(dll_path: str, calling_convention: str = "") -> "ctypes.WinDLL | ctypes.CDLL":
    """Return a cached DLL handle, loading it on first access.

    Keeps the DLL loaded across /execute calls so in-memory state (customer
    records, lock flags, earned points) persists across a pipeline session.
    The cache is cleared when /analyze is called, which needs to overwrite
    the DLL file on disk.
    """
    import ctypes
    with _DLL_CACHE_LOCK:
        global _DLL_CACHE_GENERATION
        cache_key = f"{dll_path}|g={_DLL_CACHE_GENERATION}"
        lib = _DLL_CACHE.get(cache_key)
        if lib is not None:
            return lib
        _cc = calling_convention.lower()
        runtime_path = dll_path
        try:
            source = Path(dll_path)
            if source.suffix.lower() == ".dll" and source.exists():
                generation_dir = _DLL_RUNTIME_COPY_DIR / f"g{int(_DLL_CACHE_GENERATION)}"
                generation_dir.mkdir(parents=True, exist_ok=True)
                runtime_copy = _runtime_execution_copy_path(
                    generation_dir,
                    dll_path,
                    _DLL_CACHE_GENERATION,
                )
                if not runtime_copy.exists():
                    shutil.copyfile(source, runtime_copy)
                _copy_runtime_sibling_dlls(source, generation_dir)
                _activate_runtime_dll_directory(generation_dir)
                runtime_path = str(runtime_copy)
        except Exception as exc:
            logger.warning("Runtime DLL copy fallback for %s failed: %s", dll_path, exc)
        if _cc in ("cdecl", "__cdecl", "c"):
            lib = ctypes.CDLL(runtime_path)
        else:
            lib = ctypes.WinDLL(runtime_path)
        _DLL_CACHE[cache_key] = lib
        logger.info(
            "DLL loaded and cached: source=%s runtime=%s (generation=%s convention=%s)",
            dll_path,
            runtime_path,
            _DLL_CACHE_GENERATION,
            _cc or "stdcall",
        )
        return lib


def _flush_dll_cache() -> None:
    """Unload all cached DLLs. Called before /analyze overwrites DLL files."""
    with _DLL_CACHE_LOCK:
        global _DLL_CACHE_GENERATION, _DLL_ACTIVE_RUNTIME_DIR
        for path, lib in list(_DLL_CACHE.items()):
            try:
                ctypes.windll.kernel32.FreeLibrary(lib._handle)
                logger.info("DLL cache: unloaded %s", path)
            except Exception:
                pass
        _DLL_CACHE.clear()
        for runtime_key, handle in list(_DLL_DIR_HANDLES.items()):
            try:
                close = getattr(handle, "close", None)
                if callable(close):
                    close()
            except Exception:
                logger.warning("Failed to close runtime DLL directory handle for %s", runtime_key)
        _DLL_DIR_HANDLES.clear()
        try:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass
        _DLL_ACTIVE_RUNTIME_DIR = None
        _DLL_CACHE_GENERATION += 1


def _bridge_param_argtype(param: dict) -> Any:
    """Return the ctypes argtype for one discovered parameter."""
    import ctypes
    import re

    raw = f"{param.get('type', '')} {param.get('resolved_type', '')}".lower()
    raw = " ".join(raw.replace("*", " * ").split())

    def _has_type_token(raw_text: str, token: str) -> bool:
        return bool(re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", raw_text))

    def _scalar_ptr_target(raw_text: str) -> Any | None:
        if any(_has_type_token(raw_text, tok) for tok in ("uint *", "uint32_t *", "dword *", "unsigned long *", "ulong *", "undefined4 *")):
            return ctypes.c_uint
        if any(_has_type_token(raw_text, tok) for tok in ("int *", "int32_t *", "long *")):
            return ctypes.c_int
        if _has_type_token(raw_text, "float *"):
            return ctypes.c_float
        if _has_type_token(raw_text, "double *"):
            return ctypes.c_double
        if any(_has_type_token(raw_text, tok) for tok in ("short *", "int16_t *")):
            return ctypes.c_short
        if any(_has_type_token(raw_text, tok) for tok in ("word *", "ushort *", "undefined2 *")):
            return ctypes.c_ushort
        if _has_type_token(raw_text, "bool *"):
            return ctypes.c_bool
        if _has_type_token(raw_text, "undefined8 *"):
            return ctypes.c_ulonglong
        return None

    if any(_has_type_token(raw, tok) for tok in ("lpcwstr", "lpwstr", "wchar_t *")):
        return ctypes.c_wchar_p
    if any(_has_type_token(raw, tok) for tok in ("lpcstr", "pcstr", "lpstr", "char *", "byte *", "uchar *")):
        return ctypes.c_char_p
    scalar_ptr_target = _scalar_ptr_target(raw)
    if scalar_ptr_target is not None:
        return ctypes.POINTER(scalar_ptr_target)
    if any(_has_type_token(raw, tok) for tok in ("undefined *", "lpvoid", "void *")):
        return ctypes.c_void_p
    if any(_has_type_token(raw, tok) for tok in ("uint32_t", "uint", "dword", "unsigned long", "ulong")):
        return ctypes.c_uint
    if any(_has_type_token(raw, tok) for tok in ("ushort", "word")):
        return ctypes.c_ushort
    if any(_has_type_token(raw, tok) for tok in ("int32_t", "int", "long")):
        return ctypes.c_int
    if _has_type_token(raw, "bool"):
        return ctypes.c_bool
    if _has_type_token(raw, "double"):
        return ctypes.c_double
    if _has_type_token(raw, "float"):
        return ctypes.c_float
    return ctypes.c_void_p


def _bridge_pointer_return_type(type_str: str) -> bool:
    raw = str(type_str or "").lower().replace("const ", "").strip()
    if not raw:
        return False
    if "*" in raw:
        return True
    return raw in {"handle", "hmodule", "hinstance", "hwnd", "lpvoid", "void *", "pointer"}


def _bridge_restype_for_return(type_str: str) -> Any:
    raw = str(type_str or "").strip().lower()
    if _bridge_pointer_return_type(raw):
        return ctypes.c_void_p
    return {
        "void": None,
        "bool": ctypes.c_bool,
        "int": ctypes.c_int,
        "unsigned": ctypes.c_uint,
        "unsigned int": ctypes.c_uint,
        "long": ctypes.c_long,
        "unsigned long": ctypes.c_ulong,
        "size_t": ctypes.c_size_t,
        "float": ctypes.c_float,
        "double": ctypes.c_double,
        "char*": ctypes.c_char_p,
        "const char*": ctypes.c_char_p,
        "wchar_t*": ctypes.c_wchar_p,
        "const wchar_t*": ctypes.c_wchar_p,
        "dword": ctypes.c_ulong,
        "word": ctypes.c_ushort,
        "ushort": ctypes.c_ushort,
        "short": ctypes.c_short,
        "byte": ctypes.c_ubyte,
        "uint32_t": ctypes.c_uint,
        "int32_t": ctypes.c_int,
        "undefined4": ctypes.c_int,
        "undefined": ctypes.c_int,
        "undefined8": ctypes.c_longlong,
        "hresult": ctypes.c_long,
        "handle": ctypes.c_void_p,
        "lpvoid": ctypes.c_void_p,
    }.get(raw, ctypes.c_int)


def _bridge_coerce_scalar_value(ctype_obj: Any, value: Any) -> Any:
    if ctype_obj in {ctypes.c_float, ctypes.c_double}:
        return float(value)
    return int(value)


def _bridge_pointer_input_payload(param: dict, value: Any) -> tuple[Any, Any, Any] | None:
    raw = str(param.get("resolved_type") or param.get("type") or "").lower().replace("const ", "").strip()
    if "*" not in raw:
        return None
    base = raw.rstrip("*").strip()
    if isinstance(value, (bytes, bytearray)):
        payload = ctypes.create_string_buffer(bytes(value))
        return payload, ctypes.c_void_p, payload
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes, bytearray)):
        return None
    scalar_ctype = None
    if "double" in base:
        scalar_ctype = ctypes.c_double
    elif "float" in base:
        scalar_ctype = ctypes.c_float
    elif any(tok in base for tok in ("short", "int16")):
        scalar_ctype = ctypes.c_short
    elif any(tok in base for tok in ("ushort", "word", "undefined2")):
        scalar_ctype = ctypes.c_ushort
    elif any(tok in base for tok in ("byte", "uchar")):
        scalar_ctype = ctypes.c_ubyte
    elif any(tok in base for tok in ("uint", "dword", "ulong", "unsigned")):
        scalar_ctype = ctypes.c_uint
    elif any(tok in base for tok in ("int", "long", "undefined4")):
        scalar_ctype = ctypes.c_int
    if scalar_ctype is None:
        return None
    try:
        coerced = [float(v) if scalar_ctype in {ctypes.c_float, ctypes.c_double} else int(v) for v in value]
    except (TypeError, ValueError):
        return None
    if not coerced:
        return None
    array_type = scalar_ctype * len(coerced)
    payload = array_type(*coerced)
    return payload, ctypes.POINTER(scalar_ctype), payload


def _bridge_struct_base_name(param: dict) -> str:
    raw = str(param.get("resolved_type") or param.get("type") or "")
    raw = raw.replace("const ", "").strip().rstrip("*").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if any(tok in lower for tok in ("void", "char", "wchar", "lpcstr", "lpstr", "lpcwstr", "lpwstr")):
        return ""
    return raw


def _bridge_lookup_struct_definition(inv: dict, param: dict) -> dict | None:
    base_name = _bridge_struct_base_name(param)
    if not base_name:
        return None
    extras = inv.get("_ghidra_extras") or {}
    for item in extras.get("data_types") or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "struct" and str(item.get("name") or "") == base_name:
            fields = item.get("fields") or []
            if isinstance(fields, list) and fields:
                return item
    return None


def _bridge_struct_field_ctype(field_type: str) -> Any | None:
    raw = str(field_type or "").lower().replace("const ", "").strip()
    if raw.startswith("char[") and raw.endswith("]"):
        try:
            return ctypes.c_char * int(raw[5:-1])
        except ValueError:
            return None
    if raw.startswith("wchar_t[") and raw.endswith("]"):
        try:
            return ctypes.c_wchar * int(raw[8:-1])
        except ValueError:
            return None
    if any(tok in raw for tok in ("dword", "uint32_t", "uint", "unsigned long", "ulong")):
        return ctypes.c_uint
    if "word" in raw or "ushort" in raw:
        return ctypes.c_ushort
    if any(tok in raw for tok in ("int32_t", "int", "long")):
        return ctypes.c_int
    if "bool" in raw:
        return ctypes.c_bool
    if "byte" in raw or "uchar" in raw:
        return ctypes.c_ubyte
    return None


def _bridge_build_flat_struct_class(struct_def: dict) -> Any | None:
    fields_spec: list[tuple[str, Any]] = []
    for field in struct_def.get("fields") or []:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("name") or "")
        field_ctype = _bridge_struct_field_ctype(str(field.get("type") or ""))
        if not field_name or field_ctype is None:
            return None
        fields_spec.append((field_name, field_ctype))
    if not fields_spec:
        return None
    struct_name = str(struct_def.get("name") or "BridgeStruct")
    return type(f"_Bridge_{struct_name}", (ctypes.Structure,), {"_fields_": fields_spec})


def _bridge_build_flat_struct_instance(struct_def: dict, values: dict[str, Any]) -> Any | None:
    struct_cls = _bridge_build_flat_struct_class(struct_def)
    if struct_cls is None:
        return None
    instance = struct_cls()
    for field in struct_def.get("fields") or []:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("name") or "")
        if field_name not in values:
            continue
        raw_type = str(field.get("type") or "").lower().replace("const ", "").strip()
        raw_value = values.get(field_name)
        if raw_type.startswith("char[") and raw_type.endswith("]"):
            size = getattr(type(instance), field_name).size
            data = str(raw_value or "").encode("utf-8", errors="ignore")[: max(size - 1, 0)]
            setattr(instance, field_name, data)
            continue
        if raw_type.startswith("wchar_t[") and raw_type.endswith("]"):
            size = getattr(type(instance), field_name).size
            setattr(instance, field_name, str(raw_value or "")[: max(size - 1, 0)])
            continue
        try:
            setattr(instance, field_name, int(raw_value))
        except (TypeError, ValueError):
            setattr(instance, field_name, 0)
    return instance


def _bridge_struct_to_dict(struct_instance: Any, struct_def: dict) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in struct_def.get("fields") or []:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("name") or "")
        raw_type = str(field.get("type") or "").lower().replace("const ", "").strip()
        if not field_name:
            continue
        value = getattr(struct_instance, field_name)
        if raw_type.startswith("char["):
            if isinstance(value, (bytes, bytearray)):
                result[field_name] = bytes(value).split(b"\x00", 1)[0].decode(errors="replace")
            else:
                result[field_name] = str(value)
            continue
        if raw_type.startswith("wchar_t["):
            result[field_name] = str(value).split("\x00", 1)[0]
            continue
        result[field_name] = int(value) if isinstance(value, (int, bool)) else value
    return result


_BRIDGE_SIZE_PARAM_TYPES = {
    "dword", "int", "uint", "unsigned int", "size_t",
    "long", "unsigned long", "uint32_t",
}


def _looks_like_bridge_output_buffer_param(
    params: list[dict[str, Any]],
    idx: int,
) -> bool:
    """Return True when a pointer slot clearly looks like an output buffer."""
    if idx < 0 or idx >= len(params):
        return False
    param = params[idx] or {}
    pname = str(param.get("name", "")).lower()
    ptype = str(param.get("type", "")).lower()
    if "*" not in ptype or "const " in ptype:
        return False

    explicit_name = (
        pname.startswith("pout") or
        pname.startswith("out") or
        "outbuf" in pname or
        "output" in pname or
        "errortext" in pname
    )
    if not explicit_name:
        return False

    if idx + 1 >= len(params):
        return False
    next_param = params[idx + 1] or {}
    next_name = str(next_param.get("name", "")).lower()
    next_type = str(next_param.get("type", "")).lower().replace("const ", "").strip(" *")
    return (
        next_type in _BRIDGE_SIZE_PARAM_TYPES or
        any(tok in next_name for tok in ("len", "size", "cch", "buflen", "capacity"))
    )


def _bridge_output_label(raw_name: str, seen_counts: dict[str, int]) -> str:
    """Return a stable, unique output label for bridge result text."""
    base = str(raw_name or "output_buffer").strip() or "output_buffer"
    seen_counts[base] = int(seen_counts.get(base, 0)) + 1
    if seen_counts[base] == 1:
        return base
    return f"{base}__{seen_counts[base]}"


def _execute_dll_bridge(inv: dict, execution: dict, args: dict) -> str:
    """Call a native DLL function via ctypes on this Windows VM."""
    import ctypes

    _ARGTYPE = {
        "int": ctypes.c_int,
        "short": ctypes.c_short,
        "ushort": ctypes.c_ushort,
        "uint": ctypes.c_uint,
        "unsigned": ctypes.c_uint,
        "unsigned int": ctypes.c_uint,
        "long": ctypes.c_long,
        "ulong": ctypes.c_ulong,
        "unsigned long": ctypes.c_ulong,
        "size_t": ctypes.c_size_t,
        "float": ctypes.c_float,
        "double": ctypes.c_double,
        "bool": ctypes.c_bool,
        "string": ctypes.c_char_p,
        "str": ctypes.c_char_p,
        "char*": ctypes.c_char_p,
        "const char*": ctypes.c_char_p,
        "wchar_t*": ctypes.c_wchar_p,
        "const wchar_t*": ctypes.c_wchar_p,
        # Win32 / Ghidra-decompiler type names
        "dword": ctypes.c_ulong,
        "word": ctypes.c_ushort,
        "byte": ctypes.c_ubyte,
        "uint32_t": ctypes.c_uint,
        "int32_t": ctypes.c_int,
        "undefined4": ctypes.c_int,
    }

    dll_path  = _resolve_exe_path(execution.get("dll_path", ""))
    func_name = execution.get("function_name", "")
    call_id = str(inv.get("_bridge_call_id") or "")
    if not dll_path or not func_name:
        return "DLL call error: missing dll_path or function_name in execution config"

    ret_str = (inv.get("return_type") or "unknown").strip().lower()
    restype = _bridge_restype_for_return(ret_str)

    params = list(inv.get("parameters") or [])
    if not params:
        # signature is a plain C prototype string, e.g.:
        # "int __stdcall CS_Foo(undefined8 param1, undefined8 param2)"
        # Parse the parameter list from it as a last resort.
        sig_str = inv.get("signature", "")
        if isinstance(sig_str, str) and "(" in sig_str:
            import re as _re
            m = _re.search(r'\(([^)]*)\)', sig_str)
            inner = m.group(1).strip() if m else ""
            if inner and inner.lower() != "void":
                for chunk in inner.split(","):
                    tokens = chunk.strip().split()
                    if len(tokens) >= 2:
                        raw_type = " ".join(tokens[:-1]).lower().strip("*").rstrip()
                        pname    = tokens[-1].lstrip("*")
                        params.append({"name": pname, "type": raw_type})

    # Wide-string output buffer functions: only allocate a buffer when the
    # function name ends with W AND a path/dir/name suffix.  Avoids wrongly
    # passing buffer args to zero-arg functions like GetCurrentProcessId.
    _BUFFER_SUFFIXES = (
        "directoryw", "pathw", "filenamew", "namew", "pathnamew",
        "longpathw", "shortpathw", "folderw", "volumew",
    )

    lib = None
    try:
        _cc = execution.get("calling_convention", "")
        lib = _get_cached_dll(dll_path, _cc)
        fn  = getattr(lib, func_name)
        fn.restype = restype

        c_args = []
        actual_argtypes = []
        buf    = None  # legacy: wchar buffer for W-suffix no-param functions
        out_str_bufs:   list[tuple[str, Any]] = []  # (name, c_char_p | create_string_buffer)
        out_str_alive:  list[Any] = []              # backing buffers kept alive for GC
        out_wchar_bufs: list[tuple[str, Any]] = []  # (name, create_unicode_buffer)
        out_scalars:    list[tuple[str, Any]] = []  # (name, ctypes scalar)
        out_structs:    list[tuple[str, Any, dict]] = []
        in_structs:     list[Any] = []
        in_payloads:    list[Any] = []
        output_label_counts: dict[str, int] = {}

        # Scalar ctypes used to allocate DWORD* / int* output parameters
        _SCALAR_PTR_MAP = {
            "dword": ctypes.c_uint,          "unsigned long": ctypes.c_uint,
            "ulong": ctypes.c_uint,          "uint":          ctypes.c_uint,
            "uint32_t": ctypes.c_uint,       "int":           ctypes.c_int,
            "int32_t": ctypes.c_int,         "long":          ctypes.c_int,
            "word": ctypes.c_ushort,         "byte":          ctypes.c_ubyte,
            "bool": ctypes.c_bool,
            # Ghidra "undefined*" types â€” specific sizes â†’ typed scalar slots
            "undefined": ctypes.c_uint,
            "undefined2": ctypes.c_ushort,
            "undefined4": ctypes.c_uint,
            "undefined8": ctypes.c_ulonglong,
        }
        # undefined4* / undefined8* are always output scalars; bare undefined* is a byte buffer.
        # Treat val=="" the same as val=None for these types so the LLM's blank exploratory
        # probes ("param_2": "") correctly allocate an output slot rather than a 1-byte char ptr.
        _ALWAYS_OUT_SCALAR_BASES = frozenset({"undefined2", "undefined4", "undefined8"})
        _ALWAYS_OUT_BUF_BASES    = frozenset({"undefined"})
        # Type names that represent a buffer-length argument following a char* out-buf
        if params:
            skip_indices: set[int] = set()
            for idx, p in enumerate(params):
                if idx in skip_indices:
                    continue
                pname     = p.get("name", f"param_{idx}")
                ptype_raw = p.get("type", "string")
                ptype_lc  = ptype_raw.lower()
                ptype_base = ptype_lc.replace("const ", "").strip().rstrip(" *")
                val       = args.get(pname)
                direction = p.get("direction", "")
                struct_def = _bridge_lookup_struct_definition(inv, p)

                is_ptr        = "*" in ptype_lc
                is_const_ptr  = is_ptr and "const " in ptype_lc
                # Only treat a pointer as an output buffer when no value was
                # supplied.  If the LLM passed a value (e.g. customer_id="1042"),
                # honour it as an input regardless of the direction heuristic â€”
                # Ghidra often marks non-const pointers as "out" even when they
                # are actually input strings (e.g. byte * for a customer-ID arg).
                # Treat val=="" the same as val=None for undefined-typed pointer params.
                # The LLM passes "" for unknown pointer args; for output-only types that
                # is semantically "allocate for me", not "pass a 1-byte string pointer".
                # Ghidra undefined*/undefined4*/undefined8* are ALWAYS output slots â€”
                # the model should never pass data values for these types.
                explicit_out_buffer = _looks_like_bridge_output_buffer_param(params, idx)
                _val_is_blank = (
                    val is None or
                    (str(direction).lower() == "out" and isinstance(val, str) and val == "") or
                    ptype_base in (_ALWAYS_OUT_SCALAR_BASES | _ALWAYS_OUT_BUF_BASES)
                )
                is_out_ptr    = is_ptr and not is_const_ptr and (_val_is_blank or explicit_out_buffer)
                is_char_out   = is_out_ptr and (
                    ("char" in ptype_base and "wchar" not in ptype_base) or
                    ptype_base in ("byte", "uchar") or
                    ptype_base in _ALWAYS_OUT_BUF_BASES   # undefined* â†’ byte buffer
                )
                is_wchar_out  = is_out_ptr and "wchar" in ptype_base
                is_scalar_out = is_out_ptr and not is_char_out and not is_wchar_out
                is_input_struct = is_ptr and isinstance(val, dict) and struct_def is not None
                is_output_struct = is_out_ptr and struct_def is not None and not is_char_out and not is_wchar_out

                if is_input_struct:
                    struct_instance = _bridge_build_flat_struct_instance(struct_def, val)
                    if struct_instance is None:
                        return f"DLL call error: unsupported input struct for {pname}"
                    in_structs.append(struct_instance)
                    c_args.append(ctypes.byref(struct_instance))
                    actual_argtypes.append(ctypes.c_void_p)

                elif is_output_struct:
                    struct_cls = _bridge_build_flat_struct_class(struct_def)
                    if struct_cls is None:
                        return f"DLL call error: unsupported output struct for {pname}"
                    struct_instance = struct_cls()
                    c_args.append(ctypes.byref(struct_instance))
                    actual_argtypes.append(ctypes.c_void_p)
                    out_structs.append((
                        _bridge_output_label(pname, output_label_counts),
                        struct_instance,
                        struct_def,
                    ))

                elif is_char_out:
                    # ANSI char* output buffer â€” auto-detect the following size param
                    buf_size = 4096
                    if idx + 1 < len(params):
                        np      = params[idx + 1]
                        np_name = np.get("name", "")
                        np_type = np.get("type", "").lower().replace("const ", "").strip(" *")
                        np_val  = args.get(np_name)
                        if np_val is not None:
                            try:
                                buf_size = max(64, int(np_val))
                            except (ValueError, TypeError):
                                pass
                        elif np_type in _BRIDGE_SIZE_PARAM_TYPES:
                            # Auto-supply the buffer length; skip that param in the loop
                            skip_indices.add(idx + 1)
                    # For Ghidra "undefined*" out params: enforce minimum 4096-byte
                    # buffer and always auto-supply the following size arg.  Passing
                    # size=0 causes the DLL to refuse (returns null-arg error).
                    if ptype_base in _ALWAYS_OUT_BUF_BASES:
                        buf_size = max(4096, buf_size)
                        if idx + 1 < len(params):
                            _np_type = params[idx + 1].get("type", "").lower() \
                                .replace("const ", "").strip(" *")
                            if _np_type in _BRIDGE_SIZE_PARAM_TYPES and (idx + 1) not in skip_indices:
                                skip_indices.add(idx + 1)
                    sbuf = ctypes.create_string_buffer(buf_size)
                    c_args.append(sbuf)
                    actual_argtypes.append(_bridge_param_argtype(p))
                    if (idx + 1) in skip_indices:
                        c_args.append(ctypes.c_uint(buf_size))
                        actual_argtypes.append(ctypes.c_uint)
                    out_str_bufs.append((_bridge_output_label(pname, output_label_counts), sbuf))

                elif is_wchar_out:
                    # Wide wchar_t* output buffer
                    buf_size = 4096
                    if idx + 1 < len(params):
                        np      = params[idx + 1]
                        np_name = np.get("name", "")
                        np_type = np.get("type", "").lower().replace("const ", "").strip(" *")
                        np_val  = args.get(np_name)
                        if np_val is not None:
                            try:
                                buf_size = max(64, int(np_val))
                            except (ValueError, TypeError):
                                pass
                        elif np_type in _BRIDGE_SIZE_PARAM_TYPES:
                            skip_indices.add(idx + 1)
                    wbuf = ctypes.create_unicode_buffer(buf_size)
                    c_args.append(wbuf)
                    actual_argtypes.append(_bridge_param_argtype(p))
                    if (idx + 1) in skip_indices:
                        c_args.append(ctypes.c_uint(buf_size))
                        actual_argtypes.append(ctypes.c_uint)
                    out_wchar_bufs.append((_bridge_output_label(pname, output_label_counts), wbuf))

                elif is_scalar_out:
                    # DWORD*, int*, LONG* etc. â€” allocate a typed scalar and pass byref
                    s_ctype = _SCALAR_PTR_MAP.get(ptype_base, ctypes.c_ulong)
                    scalar  = s_ctype(0)
                    c_args.append(ctypes.byref(scalar))
                    actual_argtypes.append(_bridge_param_argtype(p))
                    out_scalars.append((_bridge_output_label(pname, output_label_counts), scalar))

                elif val is not None:
                    # Normal input parameter.
                    # Pointer-typed params (byte*, undefined*, BYTE*, etc.) have two
                    # valid encodings depending on what the DLL actually expects:
                    #
                    #   String / opaque pointer  â†’ c_char_p(str(val).encode())
                    #     RCX = address of heap bytes, e.g. b"1042\x00"
                    #
                    #   Raw integer in pointer slot â†’ c_int64(int(val))
                    #     RCX = 1042  (the DLL treats the register value as an ID,
                    #     not as a memory address to dereference)
                    #
                    # The LLM signals which to use by the JSON value type:
                    #   {"param_1": "1042"} â†’ string â†’ c_char_p  (default / first try)
                    #   {"param_1": 1042}   â†’ integer â†’ c_int64  (retry / probe)
                    #
                    # This lets the probe-and-learn loop try both encodings without
                    # any DLL-specific knowledge baked in here.
                    if is_ptr:
                        payload = _bridge_pointer_input_payload(p, val)
                        if payload is not None:
                            payload_arg, payload_argtype, payload_keepalive = payload
                            in_payloads.append(payload_keepalive)
                            c_args.append(payload_arg)
                            actual_argtypes.append(payload_argtype)
                        elif isinstance(val, int):
                            # LLM explicitly passed an integer â€” put raw value in register
                            c_args.append(int(val))
                            actual_argtypes.append(ctypes.c_void_p)
                        else:
                            c_args.append(str(val).encode())
                            actual_argtypes.append(_bridge_param_argtype(p))
                    else:
                        atype = _ARGTYPE.get(ptype_base, ctypes.c_char_p)
                        if atype == ctypes.c_char_p:
                            c_args.append(str(val).encode())
                            actual_argtypes.append(_bridge_param_argtype(p))
                        elif atype == ctypes.c_wchar_p:
                            c_args.append(str(val))
                            actual_argtypes.append(_bridge_param_argtype(p))
                        else:
                            try:
                                c_args.append(_bridge_coerce_scalar_value(atype, val))
                            except (ValueError, TypeError):
                                c_args.append(0)
                            actual_argtypes.append(_bridge_param_argtype(p))
                # else: no value, not an output pointer â€” optional / unknown param, skip

        elif not params:
            # No declared params â€” allocate a wchar output buffer only for
            # well-known wide-string output functions (name ends with W + keyword).
            fn_lower = func_name.lower()
            if any(fn_lower.endswith(sfx) for sfx in _BUFFER_SUFFIXES):
                buf = ctypes.create_unicode_buffer(32767)
                c_args = [buf, ctypes.c_uint(32767)]
                actual_argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
                fn.restype = ctypes.c_uint

        if actual_argtypes:
            fn.argtypes = actual_argtypes
        _write_execute_breadcrumb({
            "event": "native_call_enter",
            "call_id": call_id,
            "tool": inv.get("name", ""),
            "dll_path": dll_path,
            "function_name": func_name,
            "arg_count": len(c_args),
            "arg_keys": [p.get("name", f"param_{idx}") for idx, p in enumerate(params)],
            "args": _summarize_execute_args(args),
            "return_type": ret_str,
        })
        result = fn(*c_args)
        _write_execute_breadcrumb({
            "event": "native_call_exit",
            "call_id": call_id,
            "tool": inv.get("name", ""),
            "function_name": func_name,
            "result_type": type(result).__name__,
            "result_preview": str(result)[:120],
        })

        # Collect output buffer / out-param values into the response.
        output_parts: list[str] = []
        for label, sbuf in out_str_bufs:
            txt = sbuf.value
            if isinstance(txt, bytes):
                txt = txt.decode(errors="replace")
            if txt:
                output_parts.append(f"{label}={txt!r}")
        for label, wbuf in out_wchar_bufs:
            txt = wbuf.value
            if txt:
                output_parts.append(f"{label}={txt!r}")
        # Sentinels defined here so we can use them for both return-value and scalar annotation
        _SENTINEL_VALUES = frozenset({
            0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFC, 0xFFFFFFFB,
        })
        for sc_name, scalar in out_scalars:
            sv = scalar.value
            # Flag values >= 2^31 that aren't known sentinels â€” likely packed data,
            # float bits, or a wrong Ghidra type inference for this output slot.
            if (isinstance(sv, int) and sv >= 0x80000000
                    and sv not in _SENTINEL_VALUES):
                output_parts.append(
                    f"{sc_name}={sv} (large uint \u2014 may be packed/float data or wrong buffer type)"
                )
            else:
                output_parts.append(f"{sc_name}={sv}")
        for struct_name, struct_instance, struct_def in out_structs:
            output_parts.append(
                f"{struct_name}={json.dumps(_bridge_struct_to_dict(struct_instance, struct_def))}"
            )
        if buf is not None:
            output_parts.append(f"output_buffer={buf.value!r}")

        _SENTINEL_NOTES: dict[int, str] = {
            0xFFFFFFFF: "sentinel: not found/invalid",
            0xFFFFFFFE: "sentinel: null argument",
            0xFFFFFFFD: "sentinel: not initialized",
            0xFFFFFFFC: "sentinel: account locked",
            0xFFFFFFFB: "sentinel: write denied",
        }
        _pointer_return = restype == ctypes.c_void_p
        _result_int = int(result) if isinstance(result, int) else 0
        _r32 = (_result_int & 0xFFFFFFFF) if isinstance(result, int) else 0
        _note = _SENTINEL_NOTES.get(_r32, "")
        if _pointer_return and result not in (None, 0):
            _ret_tag = f"Returned: {_result_int} (pointer=0x{int(result):X})" + (f" ({_note})" if _note else "")
        else:
            _ret_tag = f"Returned: {result}" + (f" ({_note})" if _note else "")

        if restype == ctypes.c_char_p and isinstance(result, bytes):
            return f"Returned: {result.decode(errors='replace')}"
        if restype == ctypes.c_wchar_p and isinstance(result, str):
            return f"Returned: {result}"
        if output_parts:
            return _ret_tag + "\n" + "\n".join(output_parts)
        return _ret_tag
    except Exception as exc:
        _write_execute_breadcrumb({
            "event": "native_call_error",
            "call_id": call_id,
            "tool": inv.get("name", ""),
            "function_name": func_name,
            "error": str(exc),
            "error_class": type(exc).__name__,
        })
        return f"DLL call error: {exc}"


def _execute_dll_bridge_isolated(inv: dict, execution: dict, args: dict) -> str:
    """Execute one DLL call in a worker process so bridge crashes stay contained."""
    call_id = str(inv.get("_bridge_call_id") or "")
    payload = {
        "inv": inv,
        "execution": execution,
        "args": args,
    }
    with tempfile.TemporaryDirectory(prefix="bridge-dll-exec-") as temp_dir:
        temp_root = Path(temp_dir)
        input_path = temp_root / "request.json"
        output_path = temp_root / "response.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(_DLL_EXECUTE_WORKER_PATH),
                    str(input_path),
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=_DLL_EXECUTE_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                cwd=str(_ROOT),
            )
        except subprocess.TimeoutExpired:
            message = (
                f"bridge worker timed out after {_DLL_EXECUTE_TIMEOUT_SECONDS}s "
                f"for {execution.get('function_name') or inv.get('name') or 'dll_import'}"
            )
            _write_execute_breadcrumb({
                "event": "native_call_error",
                "call_id": call_id,
                "tool": inv.get("name", ""),
                "function_name": execution.get("function_name", ""),
                "error": message,
                "error_class": "BridgeWorkerTimeout",
            })
            return f"DLL call error: {message}"
        except Exception as exc:
            _write_execute_breadcrumb({
                "event": "native_call_error",
                "call_id": call_id,
                "tool": inv.get("name", ""),
                "function_name": execution.get("function_name", ""),
                "error": str(exc),
                "error_class": type(exc).__name__,
            })
            return f"DLL call error: bridge worker launch failed: {exc}"

        if not output_path.exists():
            message = (
                "bridge worker crashed before returning a result "
                f"(exit_code={completed.returncode})"
            )
            _write_execute_breadcrumb({
                "event": "native_call_error",
                "call_id": call_id,
                "tool": inv.get("name", ""),
                "function_name": execution.get("function_name", ""),
                "error": message,
                "error_class": "BridgeWorkerCrash",
            })
            return f"DLL call error: {message}"

        try:
            worker_result = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as exc:
            message = f"bridge worker returned unreadable JSON: {exc}"
            _write_execute_breadcrumb({
                "event": "native_call_error",
                "call_id": call_id,
                "tool": inv.get("name", ""),
                "function_name": execution.get("function_name", ""),
                "error": message,
                "error_class": type(exc).__name__,
            })
            return f"DLL call error: {message}"

        if worker_result.get("status") != "ok":
            message = str(worker_result.get("error") or "bridge worker failed")
            _write_execute_breadcrumb({
                "event": "native_call_error",
                "call_id": call_id,
                "tool": inv.get("name", ""),
                "function_name": execution.get("function_name", ""),
                "error": message,
                "error_class": "BridgeWorkerError",
            })
            return f"DLL call error: {message}"

        result = worker_result.get("result")
        if isinstance(result, str):
            return result
        return str(result)


@app.post("/execute")
async def execute(
    body: ExecuteRequest,
    x_bridge_key: str = Header(default=""),
):
    """Execute a single tool call on this Windows VM and return the result."""
    _check_auth(x_bridge_key)
    call_id = secrets.token_hex(6)
    inv       = dict(body.invocable or {})
    inv["_bridge_call_id"] = call_id
    args      = body.args
    name      = inv.get("name", "")
    execution = inv.get("execution") or inv.get("mcp", {}).get("execution", {})
    method    = execution.get("method", "")
    _write_execute_breadcrumb({
        "event": "execute_enter",
        "call_id": call_id,
        "tool": name,
        "method": method,
        "arg_keys": sorted((args or {}).keys()),
        "args": _summarize_execute_args(args or {}),
    })
    logger.info("Execute: tool=%s method=%s args=%s execution=%s", name, method, args, execution)
    params = list((inv.get("parameters") or []))
    logger.info("Execute: declared params=%s", [p.get("name") for p in params])
    loop = asyncio.get_running_loop()
    if method == "gui_action":
        result = await loop.run_in_executor(None, _execute_gui_bridge, execution, name, args)
    elif method == "dll_import":
        result = await loop.run_in_executor(None, _execute_dll_bridge, inv, execution, args)
    elif method in ("com_invoke", "com_dispatch"):
        # COM calls may block indefinitely when they open a modal dialog
        # (e.g. BrowseForFolder).  Wrap in a Future with a 60 s timeout so
        # the HTTP handler always returns rather than hanging the event loop.
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _execute_com_bridge, inv, execution, args),
                timeout=60,
            )
        except asyncio.TimeoutError:
            result = (
                f"COM call '{name}' timed out after 60 s â€” the method likely opened "
                "a blocking modal dialog (e.g. a folder/file picker). "
                "The dialog may still be visible on the desktop."
            )
    elif method == "dotnet_reflection":
        result = await loop.run_in_executor(None, _execute_dotnet_bridge, execution, name, args)
    elif method in ("python_subprocess", "node", "ts-node", "powershell",
                    "cmd_call", "bash", "ruby", "php", "cscript", "cmd"):
        result = await loop.run_in_executor(None, _execute_script_bridge, execution, name, args)
    elif method in ("http_request", "jsonrpc", "soap"):
        result = await loop.run_in_executor(None, _execute_http_bridge, execution, name, args)
    elif method == "sql_exec":
        result = await loop.run_in_executor(None, _execute_sql_bridge, execution, name, args)
    elif method == "rpc_call":
        # RPC invocables require a running RPC server â€” execution not supported on bridge.
        # Discovery-only: the model can describe the interface but cannot invoke remotely.
        iface = execution.get("interface_uuid") or execution.get("endpoint") or name
        result = f"RPC interface '{iface}' discovered. Remote invocation requires a live RPC endpoint; describe the interface parameters instead."
    elif method in ("corba_iiop",):
        # CORBA requires an ORB (omniORB, JacORB) â€” not available on this Windows bridge.
        iface = execution.get("interface") or name
        result = f"CORBA interface '{iface}' discovered. Invocation requires a CORBA ORB over IIOP; describe the interface operations instead."
    elif method in ("jndi_lookup",):
        # JNDI requires a running Java naming provider â€” not available on this Windows bridge.
        lookup = execution.get("lookup_name") or name
        result = f"JNDI binding '{lookup}' discovered. Invocation requires a running JNDI provider (LDAP/RMI/IIOP); describe the binding instead."
    else:  # cli / subprocess / anything else
        result = await loop.run_in_executor(None, _execute_cli_bridge, execution, name, args)
    _write_execute_breadcrumb({
        "event": "execute_exit",
        "call_id": call_id,
        "tool": name,
        "method": method,
        "result_preview": str(result)[:120],
    })
    return JSONResponse({"result": result})


@app.post("/flush-dll-cache")
async def flush_dll_cache(x_bridge_key: str = Header(default="")):
    """Unload all cached DLLs so state resets for the next pipeline run."""
    _check_auth(x_bridge_key)
    _flush_dll_cache()
    return {"status": "flushed", "note": "All cached DLLs unloaded; next call will reload fresh."}


@app.post("/flush-analysis-cache")
async def flush_analysis_cache(x_bridge_key: str = Header(default="")):
    """Clear the Ghidra/analysis result cache so the next /analyze re-runs from scratch."""
    _check_auth(x_bridge_key)
    count = len(_ANALYSIS_CACHE)
    _ANALYSIS_CACHE.clear()
    return {"status": "flushed", "entries_cleared": count}


@app.post("/flush-all")
async def flush_all(x_bridge_key: str = Header(default="")):
    """Clear both analysis and DLL caches â€” full reset."""
    _check_auth(x_bridge_key)
    analysis_count = len(_ANALYSIS_CACHE)
    _ANALYSIS_CACHE.clear()
    _flush_dll_cache()
    return {"status": "flushed", "analysis_entries_cleared": analysis_count, "dll_cache": "cleared"}


@app.get("/alive")
async def alive():
    return {"status": "alive", "component": "bridge", "contract_version": TRUST_CONTRACT_VERSION}


@app.get("/health")
async def health():
    payload = _bridge_health_payload()
    return JSONResponse(status_code=200 if payload["healthy"] else 503, content=payload)


@app.get("/identity")
async def identity(x_bridge_key: str = Header(default="")):
    _check_auth(x_bridge_key)
    return JSONResponse(_bridge_identity_payload())


@app.get("/readiness")
async def readiness(x_bridge_key: str = Header(default="")):
    _check_auth(x_bridge_key)
    return JSONResponse(_bridge_readiness_payload())


@app.get("/local-lane-admission")
async def local_lane_admission(x_bridge_key: str = Header(default="")):
    _check_auth(x_bridge_key)
    return JSONResponse(_bridge_local_lane_admission_payload())


@app.get("/debug_session")
async def debug_session(x_bridge_key: str = Header(default="")):
    """Return the bridge process's Windows session info and visible desktop windows.

    GET http://<vm>:8090/debug_session  (with X-Bridge-Key header)

    Use this to confirm:
      - session_id == 1 (interactive desktop, not Session 0 SYSTEM)
      - visible windows include expected apps
    """
    _check_auth(x_bridge_key)
    import ctypes

    info: dict = {}

    # Session ID of the bridge process itself
    try:
        sid = ctypes.c_ulong(0)
        ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid))
        info["bridge_session_id"] = sid.value
        info["is_session_0"] = sid.value == 0
    except Exception as exc:
        info["bridge_session_id"] = f"error: {exc}"

    # Active console session (the one attached to the physical/RDP display)
    try:
        info["active_console_session"] = ctypes.windll.kernel32.WTSGetActiveConsoleSessionId()
    except Exception as exc:
        info["active_console_session"] = f"error: {exc}"

    # Enumerate visible top-level windows in this session
    try:
        import win32gui  # type: ignore
        windows = []
        def _cb(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    t = win32gui.GetWindowText(hwnd)
                    if t:
                        windows.append(t)
            except Exception:
                pass
        win32gui.EnumWindows(_cb, None)
        info["visible_windows"] = windows[:40]
        info["visible_window_count"] = len(windows)
    except Exception as exc:
        info["visible_windows"] = f"win32gui error: {exc}"

    # Quick check: is CalculatorApp.exe (the real calc process) running?
    try:
        import psutil  # type: ignore
        calc_procs = [p.name() for p in psutil.process_iter(["name"])
                      if "calc" in (p.info["name"] or "").lower()]
        info["calc_processes"] = calc_procs
    except Exception as exc:
        info["calc_processes"] = f"psutil error: {exc}"

    return JSONResponse(info)


@app.get("/debug_uia")
async def debug_uia(
    stem: str = "calc",
    x_bridge_key: str = Header(default=""),
):
    """Dump UIA Text/Edit descendants of the first window matching 'stem'."""
    _check_auth(x_bridge_key)
    import asyncio
    loop = asyncio.get_running_loop()

    def _dump():
        import psutil
        from pywinauto import Desktop
        from pywinauto.application import Application
        result = {"windows": [], "descendants": []}
        for w in Desktop(backend="uia").windows():
            try:
                title = (w.window_text() or "").lower()
                pid   = w.element_info.process_id
                pname = (psutil.Process(pid).name() or "").lower()
                if stem.lower() in title or stem.lower() in pname:
                    result["windows"].append({
                        "title": w.window_text(),
                        "pid": pid,
                        "process": psutil.Process(pid).name(),
                        "handle": w.handle,
                    })
                    app = Application(backend="uia").connect(handle=w.handle)
                    win = app.top_window()
                    for ctrl in win.descendants(control_type="Text"):
                        try:
                            result["descendants"].append({
                                "type": "Text",
                                "auto_id": ctrl.element_info.automation_id,
                                "text": ctrl.window_text(),
                            })
                        except Exception:
                            pass
                    for ctrl in win.descendants(control_type="Edit"):
                        try:
                            result["descendants"].append({
                                "type": "Edit",
                                "auto_id": ctrl.element_info.automation_id,
                                "text": ctrl.window_text(),
                            })
                        except Exception:
                            pass
                    break
            except Exception:
                continue
        return result

    data = await loop.run_in_executor(None, _dump)
    return JSONResponse(data)


# â”€â”€ Entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    port = int(os.getenv("BRIDGE_PORT", "8090"))
    logger.info("Starting GUI bridge on 0.0.0.0:%d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)

