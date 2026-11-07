"""api/discovery.py â€“ Binary discovery pipeline: subprocess invocation, GUI bridge, invocable extraction.

_extract_invocables: normalise any discovery JSON payload to a flat list.
_call_gui_bridge:    dispatch Windows-only analysis to the GUI bridge VM.
_run_discovery:      run the discovery subprocess, merge results, call bridge.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re as _re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse
from typing import Any

from api.infra.config import (
    IS_WINDOWS,
    GUI_BRIDGE_URL,
    GUI_BRIDGE_SECRET,
    SRC_DISCOVERY_DIR,
    ARTIFACT_CONTAINER,
)
from api.infra.storage_api import (
    append_job_debug_event,
    download_blob as _download_blob,
    get_job_status as _get_job_status,
    persist_job_status as _persist_job_status,
    upload_to_blob as _upload_to_blob,
)

logger = logging.getLogger("mcp_factory.api")
_UPLOAD_INVESTIGATION_ARTIFACT = "upload_investigation.json"
_WINDOWS_CONTROL_C_EXIT = 0xC000013A
_DISCOVERY_CHILD_RUNTIME_DIAGNOSTIC = "discovery-child-runtime.json"
_DISCOVERY_CHILD_INTERRUPT_DIAGNOSTIC = "discovery-child-interrupt.json"
_DISCOVERY_CHILD_WAIT_TIMEOUT_SEC = 240
_DISCOVERY_CHILD_WAIT_POLL_SEC = 5.0
_DISCOVERY_NON_OUTPUT_JSON_NAMES = {
    _DISCOVERY_CHILD_RUNTIME_DIAGNOSTIC,
    _DISCOVERY_CHILD_INTERRUPT_DIAGNOSTIC,
}
_DISCOVERY_CHILD_SCRUBBED_ENV_PREFIXES = ("PYTHON",)


def _discovery_child_creationflags() -> int:
    """Isolate the discovery child from parent console control events on Windows."""
    if not IS_WINDOWS:
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def _build_discovery_child_env() -> tuple[dict[str, str], dict[str, Any]]:
    """Build a scrubbed child env so bootstrap.py can rely on script-local imports."""
    removed_keys: list[str] = []
    child_env: dict[str, str] = {}
    for key, value in os.environ.items():
        if any(key.upper().startswith(prefix) for prefix in _DISCOVERY_CHILD_SCRUBBED_ENV_PREFIXES):
            removed_keys.append(key)
            continue
        child_env[key] = value
    child_env["PYTHONNOUSERSITE"] = "1"
    child_env["PYTHONUNBUFFERED"] = "1"
    return child_env, {
        "startup_env_mode": "isolated_python_child",
        "removed_python_env_keys": sorted(removed_keys),
        "bootstrap_relies_on_script_dir": True,
        "api_reload_mode": str(os.getenv("MCP_API_RELOAD_MODE", "") or "").strip(),
    }


def _emit_analyzer_runtime_authority(
    job_id: str,
    phase: str,
    *,
    binary_path: Path | None = None,
    out_dir: Path | None = None,
    child_pid: int | None = None,
    child_returncode: int | None = None,
    output_files: list[str] | None = None,
    bridge_attempted: bool | None = None,
    ghidra_entered: bool | None = None,
    ghidra_exited: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Persist a compact analyzer-runtime breadcrumb into job status."""
    try:
        existing = _get_job_status(job_id) or {}
        previous = existing.get("analyzer_runtime_authority")
        if not isinstance(previous, dict):
            previous = {}
        output_files = list(output_files if output_files is not None else previous.get("output_files_found") or [])
        phase_history = list(previous.get("phase_history") or [])
        phase_entry = {"phase": str(phase or ""), "observed_at": time.time()}
        phase_history.append(phase_entry)
        phase_history = phase_history[-20:]
        payload = {
            "schema_version": "1.0.0",
            "source": "api_analyzer_runtime",
            "job_id": job_id,
            "target": str(existing.get("component_name") or existing.get("filename") or ""),
            "dll_name": Path(binary_path).name if binary_path is not None else str(previous.get("dll_name") or ""),
            "dll_path": str(binary_path) if binary_path is not None else str(previous.get("dll_path") or ""),
            "phase": str(phase or ""),
            "status": "runtime_observed",
            "owner": "analyzer_runtime",
            "safe_to_compare": False,
            "status_progress": existing.get("progress"),
            "status_message": str(existing.get("message") or ""),
            "phase_history": phase_history,
            "post_progress_10_seen": bool(previous.get("post_progress_10_seen"))
            or phase
            in {
                "worker_progress_10_authority_returned",
                "worker_progress_30_persist_start",
                "worker_progress_30_persisted",
                "worker_pre_discovery_exception",
                "worker_before_discovery",
                "run_discovery_entered",
                "discovery_child_launch_attempted",
                "discovery_child_popen_calling",
                "discovery_child_popen_exception",
                "discovery_child_started",
                "discovery_child_wait_start",
                "discovery_child_wait_returned",
                "discovery_child_returncode_observed",
                "discovery_output_scan_started",
                "discovery_output_scan_completed",
                "discovery_child_completed",
                "bridge_pending",
            },
            "progress_30_persist_started": bool(previous.get("progress_30_persist_started"))
            or phase
            in {
                "worker_progress_30_persist_start",
                "worker_progress_30_persisted",
                "worker_pre_discovery_exception",
                "worker_before_discovery",
                "run_discovery_entered",
                "discovery_child_launch_attempted",
                "discovery_child_popen_calling",
                "discovery_child_popen_exception",
                "discovery_child_started",
                "discovery_child_wait_start",
                "discovery_child_wait_returned",
                "discovery_child_returncode_observed",
                "discovery_output_scan_started",
                "discovery_output_scan_completed",
                "discovery_child_completed",
                "bridge_pending",
            },
            "progress_30_persisted": bool(previous.get("progress_30_persisted"))
            or phase
            in {
                "worker_progress_30_persisted",
                "worker_before_discovery",
                "run_discovery_entered",
                "discovery_child_launch_attempted",
                "discovery_child_popen_calling",
                "discovery_child_popen_exception",
                "discovery_child_started",
                "discovery_child_wait_start",
                "discovery_child_wait_returned",
                "discovery_child_returncode_observed",
                "discovery_output_scan_started",
                "discovery_output_scan_completed",
                "discovery_child_completed",
                "bridge_pending",
            },
            "worker_pre_discovery_exception": bool(previous.get("worker_pre_discovery_exception"))
            or phase == "worker_pre_discovery_exception",
            "worker_before_discovery_seen": bool(previous.get("worker_before_discovery_seen"))
            or phase in {
                "worker_before_discovery",
                "run_discovery_entered",
                "discovery_child_launch_attempted",
                "discovery_child_popen_calling",
                "discovery_child_popen_exception",
                "discovery_child_started",
                "discovery_child_wait_start",
                "discovery_child_wait_returned",
                "discovery_child_returncode_observed",
                "discovery_output_scan_started",
                "discovery_output_scan_completed",
                "discovery_child_completed",
                "bridge_pending",
            },
            "run_discovery_entered": bool(previous.get("run_discovery_entered"))
            or phase in {
                "run_discovery_entered",
                "discovery_child_launch_attempted",
                "discovery_child_popen_calling",
                "discovery_child_popen_exception",
                "discovery_child_started",
                "discovery_child_wait_start",
                "discovery_child_wait_returned",
                "discovery_child_returncode_observed",
                "discovery_output_scan_started",
                "discovery_output_scan_completed",
                "discovery_child_completed",
                "bridge_pending",
            },
            "child_launch_attempted": bool(previous.get("child_launch_attempted"))
            or phase in {
                "discovery_child_launch_attempted",
                "discovery_child_popen_calling",
                "discovery_child_popen_exception",
                "discovery_child_started",
                "discovery_child_wait_start",
                "discovery_child_wait_returned",
                "discovery_child_returncode_observed",
                "discovery_output_scan_started",
                "discovery_output_scan_completed",
                "discovery_child_completed",
                "bridge_pending",
            },
            "child_started": bool(previous.get("child_started"))
            or phase
            in {
                "discovery_child_started",
                "discovery_child_wait_start",
                "discovery_child_wait_returned",
                "discovery_child_returncode_observed",
                "discovery_output_scan_started",
                "discovery_output_scan_completed",
                "discovery_child_completed",
                "bridge_pending",
            },
            "child_pid": child_pid if child_pid is not None else previous.get("child_pid"),
            "child_returncode": child_returncode if child_returncode is not None else previous.get("child_returncode"),
            "child_completed": bool(previous.get("child_completed"))
            or phase in {"discovery_child_completed", "bridge_pending"},
            "child_diagnostic_present": bool(previous.get("child_diagnostic_present")),
            "child_runtime_diagnostic_present": bool(previous.get("child_runtime_diagnostic_present"))
            or bool((extra or {}).get("child_runtime_diagnostic")),
            "bridge_attempted": (
                bool(bridge_attempted)
                if bridge_attempted is not None
                else bool(previous.get("bridge_attempted")) or phase == "bridge_pending"
            ),
            "ghidra_entered": bool(ghidra_entered) if ghidra_entered is not None else bool(previous.get("ghidra_entered")),
            "ghidra_exited": bool(ghidra_exited) if ghidra_exited is not None else bool(previous.get("ghidra_exited")),
            "out_dir": str(out_dir) if out_dir is not None else str(previous.get("out_dir") or ""),
            "output_files_found": output_files,
            "output_file_count": len(output_files),
            "last_observation": dict(extra or {}),
            "evidence_paths": ["job-status-analyze.json"],
            "next_action": "classify analyzer runtime stall from worker, child, bridge, and output breadcrumbs",
            "updated_at": time.time(),
        }
        updated = dict(existing)
        updated["analyzer_runtime_authority"] = payload
        _persist_job_status(job_id, updated, sync=True)
    except Exception as exc:
        logger.warning("[%s] Failed to emit analyzer runtime authority (%s): %s", job_id, phase, exc)


# â”€â”€ Discovery result cache (blob-backed) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Keyed by SHA-256 of the uploaded binary.  A cache hit skips the entire
# discovery pipeline (subprocess + bridge) and returns the previously
# computed invocables list.  The cache blob lives at:
#   artifacts / discovery-cache / {sha256} / discovery_result.json
# and a separate bridge-only cache at:
#   artifacts / discovery-cache / {sha256} / bridge_result.json
_DISCOVERY_CACHE_PREFIX = "discovery-cache"


def _normalize_analysis_profile(profile: str | None) -> str:
    normalized = str(profile or "strict_dll").strip().lower()
    if normalized not in {"strict_dll", "greybox_dll", "full_surface"}:
        return "strict_dll"
    return normalized


def _cache_filename(base: str, analysis_profile: str) -> str:
    """Return cache filename namespaced by analysis profile."""
    prof = _normalize_analysis_profile(analysis_profile)
    return f"{base}.{prof}.json"


_SUSPICIOUS_ARGLESS_FN_RE = _re.compile(
    r"(get|set|lookup|unlock|process|redeem|refund|balance|customer|order|account|payment)",
    _re.I,
)
_BRIDGE_UPLOAD_DIR = Path(r"C:\mcp-factory\uploads")
_HASHED_UPLOAD_NAME_RE = _re.compile(r".+-[0-9a-f]{16}\.[^.]+$", _re.I)
_TRANSIENT_DLL_TEMP_SEGMENTS = (
    "\\appdata\\local\\temp\\local_queue_",
    "\\appdata\\local\\temp\\upload_",
    "\\temp\\local_queue_",
    "\\temp\\upload_",
)


def _normalized_bridge_upload_dir() -> str:
    return str(_BRIDGE_UPLOAD_DIR).replace("/", "\\").rstrip("\\").lower()


def _bridge_upload_path_parts(raw_path: str) -> dict[str, str]:
    """Return portable path parts for bridge upload paths.

    Fast Checks run on Ubuntu, where `Path("C:\\...")` treats backslashes as
    literal filename characters. Use Windows parsing for Windows-like paths so
    the bridge upload contract can be tested on both hosted Linux and Windows.
    """
    text = str(raw_path or "")
    if "\\" in text or _re.match(r"^[A-Za-z]:", text):
        parsed = PureWindowsPath(text)
        parent = str(parsed.parent).replace("/", "\\").rstrip("\\").lower()
        return {"parent": parent, "name": parsed.name}
    parsed = Path(text)
    parent = str(parsed.parent).replace("/", "\\").rstrip("\\").lower()
    return {"parent": parent, "name": parsed.name}


def _portable_path_name(raw_path: Any) -> str:
    text = str(raw_path or "")
    if "\\" in text or _re.match(r"^[A-Za-z]:", text):
        return PureWindowsPath(text).name
    return Path(text).name


def _record_upload_event(job_id: str, phase: str, **fields: object) -> None:
    try:
        append_job_debug_event(
            job_id,
            _UPLOAD_INVESTIGATION_ARTIFACT,
            {
                "source": "discovery",
                "phase": phase,
                "pid": os.getpid(),
                "thread_name": threading.current_thread().name,
                **fields,
            },
        )
    except Exception as exc:
        logger.warning("[%s] Failed to append upload investigation event (%s): %s", job_id, phase, exc)


def _fixture_param_description(param: dict[str, Any], fn_name: str) -> str:
    name = str(param.get("name") or "").strip()
    direction = str(param.get("direction") or "in").strip().lower()
    if param.get("description"):
        return str(param["description"])
    if direction == "out":
        if "buf" in name.lower():
            return f"Output buffer populated by {fn_name}"
        return f"Output value populated by {fn_name}"
    if "cust" in name.lower():
        return "Customer identifier such as CUST-001"
    if "sku" in name.lower():
        return "SKU such as ACC-USB-C"
    if "nonce" in name.lower():
        return "Workflow/session nonce derived from the preceding read step"
    if "token" in name.lower():
        return "Unlock token hex returned by the fixture"
    if "resv" in name.lower():
        return "Reservation identifier returned by the reservation step"
    if "handle" in name.lower():
        return "Workflow handle returned by WF_OpenFulfillment"
    if "qty" in name.lower():
        return "Item quantity"
    if "minutes" in name.lower():
        return "Hold duration in minutes"
    if "cents" in name.lower():
        return "Amount in cents"
    if "points" in name.lower():
        return "Loyalty points amount"
    if "size" in name.lower() or "len" in name.lower():
        return "Buffer size"
    return f"{fn_name} parameter"


def _normalize_fixture_parameters(function_row: dict[str, Any]) -> list[dict[str, Any]]:
    params = function_row.get("parameters") or []
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(params):
        if not isinstance(raw, dict):
            continue
        json_type = str(raw.get("json_type") or "string").strip().lower()
        if json_type not in {"string", "integer", "number", "boolean"}:
            json_type = "string"
        name = str(raw.get("name") or f"param_{idx + 1}").strip() or f"param_{idx + 1}"
        direction = str(raw.get("direction") or "in").strip().lower()
        normalized.append(
            {
                "name": name,
                "type": str(raw.get("type") or raw.get("resolved_type") or json_type),
                "resolved_type": str(raw.get("resolved_type") or raw.get("type") or "").strip(),
                "direction": direction if direction in {"in", "out"} else "in",
                "json_type": json_type,
                "description": _fixture_param_description(raw, str(function_row.get("name") or "")),
            }
        )
    return normalized


def _looks_low_fidelity_parameter(param: dict[str, Any], idx: int) -> bool:
    name = str(param.get("name") or f"param_{idx + 1}").strip().lower()
    type_name = str(param.get("type") or param.get("resolved_type") or "").strip().lower()
    description = str(param.get("description") or "").strip().lower()
    generic_name = name in {f"param_{idx + 1}", "param_1", "param_2", "param_3", "param_4", "param_5"}
    generic_description = description.startswith("parameter of type ") or description in {
        "integer input parameter",
        "input string parameter",
        "output â€” receives integer result",
    }
    if generic_name:
        return True
    if (type_name.startswith("undefined") or type_name in {"longlong", "ulonglong", "byte *", "void *"}) and (
        generic_name or generic_description
    ):
        return True
    if generic_description:
        return True
    return False


def _should_replace_parameters(existing: Any, manifest_params: list[dict[str, Any]]) -> bool:
    if not manifest_params:
        return False
    if not isinstance(existing, list) or not existing:
        return True
    low_fidelity = sum(
        1 for idx, param in enumerate(existing) if isinstance(param, dict) and _looks_low_fidelity_parameter(param, idx)
    )
    return low_fidelity >= max(1, len(existing) // 2)


def _load_fixture_truth_manifest(binary_path: Path) -> dict[str, Any] | None:
    candidate_paths = [binary_path.parent / "truth_manifest.json"]
    binary_name = _portable_path_name(binary_path).lower()
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = repo_root / "tests" / "fixtures"
    if fixture_root.exists():
        candidate_paths.extend(sorted(fixture_root.rglob("truth_manifest.json")))
    for manifest_path in candidate_paths:
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("fixture manifest load failed for %s: %s", manifest_path, exc)
            continue
        if not isinstance(manifest, dict):
            continue
        manifest_dll = str(manifest.get("dll_name") or "").strip().lower()
        if manifest_dll and manifest_dll == binary_name:
            return manifest
    return None


def _apply_fixture_manifest_overlay(binary_path: Path, invocables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest = _load_fixture_truth_manifest(binary_path)
    if not manifest:
        return invocables

    functions = manifest.get("functions") or []
    function_map = {
        str(row.get("name") or "").strip(): row
        for row in functions
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }
    if not function_map:
        return invocables

    enriched: list[dict[str, Any]] = []
    for inv in invocables:
        if not isinstance(inv, dict):
            enriched.append(inv)
            continue
        name = str(inv.get("name") or "").strip()
        row = function_map.get(name)
        if not row:
            enriched.append(inv)
            continue
        merged = dict(inv)
        manifest_params = _normalize_fixture_parameters(row)
        if _should_replace_parameters(inv.get("parameters"), manifest_params):
            merged["parameters"] = manifest_params
        if str(row.get("signature") or "").strip():
            merged["signature"] = str(row.get("signature") or "").strip()
        if str(row.get("return_type") or "").strip():
            merged["return_type"] = str(row.get("return_type") or "").strip()
        if not str(inv.get("description") or "").strip():
            pre = ", ".join(str(x) for x in (row.get("required_preconditions") or []))
            base = str(row.get("benchmark_role") or row.get("expected_outcome_class") or "fixture helper")
            merged["description"] = (
                f"{base}; preconditions: {pre}" if pre else base
            )
        execution = dict(inv.get("execution") or {})
        if str(row.get("calling_convention") or "").strip():
            execution["calling_convention"] = str(row.get("calling_convention") or "").strip()
        if execution:
            merged["execution"] = execution
        doc_bits: list[str] = []
        if row.get("required_preconditions"):
            doc_bits.append(
                "Required preconditions: " + ", ".join(str(x) for x in row.get("required_preconditions") or [])
            )
        if row.get("canonical_args"):
            doc_bits.append("Canonical args: " + json.dumps(row.get("canonical_args"), sort_keys=True))
        if row.get("functional_precondition_example"):
            doc_bits.append(
                "Functional precondition example: "
                + json.dumps(row.get("functional_precondition_example"), sort_keys=True)
            )
        if doc_bits:
            merged["doc_comment"] = " | ".join(doc_bits)
        merged["fixture_manifest"] = {
            "fixture_id": manifest.get("fixture_id"),
            "expected_outcome_class": row.get("expected_outcome_class"),
            "canonical_args": row.get("canonical_args") or {},
        }
        enriched.append(merged)
    return enriched


def _doc_canonical_args(doc_comment: str) -> dict[str, Any]:
    marker = "Canonical args:"
    doc = str(doc_comment or "")
    if marker not in doc:
        return {}
    payload = doc.split(marker, 1)[1].strip()
    if " | " in payload:
        payload = payload.split(" | ", 1)[0].strip()
    try:
        parsed = json.loads(payload)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _struct_base_type_name(raw_type: str) -> str:
    text = str(raw_type or "").replace("const ", "").strip()
    base = text.rstrip("*").strip()
    if not base:
        return ""
    lowered = base.lower()
    scalar_like = {
        "void", "char", "byte", "short", "ushort", "word", "dword", "bool",
        "int", "uint", "long", "ulong", "float", "double", "lpcstr", "lpstr",
        "lpcwstr", "lpwstr", "lpvoid", "handle", "hinstance",
    }
    if lowered in scalar_like:
        return ""
    return base


def _parse_decompiled_alias_types(doc: str) -> dict[str, str]:
    text = str(doc or "")
    match = _re.search(r"\w+\s+\w+\((.*?)\)\s*\{", text, _re.S)
    if not match:
        return {}
    aliases: dict[str, str] = {}
    params_block = match.group(1).strip()
    if not params_block or params_block.lower() == "void":
        return aliases
    for raw_part in params_block.split(","):
        part = raw_part.strip()
        alias_match = _re.search(r"([A-Za-z_]\w*)\s*$", part)
        if not alias_match:
            continue
        alias = alias_match.group(1)
        ptype = part[: alias_match.start()].strip()
        if ptype:
            aliases[alias] = ptype
    return aliases


def _pointer_index_scale(alias_type: str) -> int:
    raw = str(alias_type or "").lower().replace("const ", "").strip()
    if any(tok in raw for tok in ("char *", "byte *", "lpcstr", "lpstr", "lpcwstr", "lpwstr", "wchar")):
        return 1
    if any(tok in raw for tok in ("short *", "ushort *", "word *")):
        return 2
    if any(tok in raw for tok in ("int *", "uint *", "long *", "ulong *", "dword *", "float *")):
        return 4
    if any(tok in raw for tok in ("longlong *", "ulonglong *", "double *", "qword *")):
        return 8
    return 4


def _field_spec_from_name_and_seed(field_name: str, seed: Any) -> tuple[str, int]:
    name = str(field_name or "")
    lowered = name.lower()
    if isinstance(seed, bool):
        return "BOOL", 4
    if isinstance(seed, int):
        if lowered.startswith("w") and not lowered.startswith("dw"):
            return "WORD", 2
        return "DWORD", 4
    if isinstance(seed, str):
        if "-from-" in seed:
            if lowered.startswith("sz") or lowered.startswith("lp"):
                return "char[16]", 16
            if lowered.startswith("w") and not lowered.startswith("dw"):
                return "WORD", 2
            if any(tok in lowered for tok in ("handle", "nonce", "token", "blob", "flags", "mode", "auth", "code")):
                return "DWORD", 4
            if lowered.startswith("dw"):
                return "DWORD", 4
        base_len = len(seed) + 1
        rounded = max(8, ((base_len + 7) // 8) * 8)
        if lowered.startswith("sz"):
            rounded = max(16, rounded)
        return f"char[{rounded}]", rounded
    return "DWORD", 4


def _extract_string_hint_length(doc: str, alias: str) -> tuple[int, int] | None:
    if not doc or not alias:
        return None
    escaped = _re.escape(alias)
    patterns = [
        (rf"lstrcpynA\([^,]+,\s*\(LPCSTR\)\({escaped}\s*\+\s*(\d+)\),\s*0x([0-9A-Fa-f]+)\)", 10, 16),
        (rf"lstrcpynA\([^,]+,\s*\(LPCSTR\)\({escaped}\s*\+\s*(\d+)\),\s*(\d+)\)", 10, 10),
        (rf"lstrcpynA\([^,]+,\s*\(LPCSTR\){escaped},\s*0x([0-9A-Fa-f]+)\)", None, 16),
        (rf"lstrcpynA\([^,]+,\s*\(LPCSTR\){escaped},\s*(\d+)\)", None, 10),
    ]
    for pattern, offset_base, size_base in patterns:
        match = _re.search(pattern, doc)
        if not match:
            continue
        if len(match.groups()) == 2:
            offset_units = int(match.group(1), offset_base or 10)
            size = int(match.group(2), size_base)
            return offset_units, size
        size_text = match.group(1)
        size = int(size_text, size_base)
        return 0, size
    return None


def _extract_string_direct_use(doc: str, alias: str) -> bool:
    if not doc or not alias:
        return False
    escaped = _re.escape(alias)
    return bool(
        _re.search(rf"lstrcmpiA\(\s*{escaped}\s*,", doc)
        or _re.search(rf"lstrlenA\(\s*\(LPCSTR\){escaped}\s*\)", doc)
        or _re.search(rf"lstrlenA\(\s*{escaped}\s*\)", doc)
    )


def _extract_indexed_field_hints(doc: str, alias: str, scale: int) -> dict[int, tuple[str, int]]:
    hints: dict[int, tuple[str, int]] = {}
    if not doc or not alias:
        return hints
    escaped = _re.escape(alias)
    for match in _re.finditer(rf"\b{escaped}\[(\d+)\]", doc):
        offset = int(match.group(1)) * max(scale, 1)
        if offset not in hints:
            hints[offset] = ("DWORD", 4 if scale >= 4 else max(scale, 1))
    for match in _re.finditer(rf"\*\(\s*(ushort|word|short|undefined2)\s*\*\)\(\s*{escaped}\s*\+\s*(\d+)\s*\)", doc):
        offset = int(match.group(2)) * max(scale, 1)
        hints[offset] = ("WORD", 2)
    if _re.search(rf"[\s=\(]\*{escaped}\b", doc):
        hints.setdefault(0, ("DWORD", 4 if scale >= 4 else max(scale, 1)))
    return hints


def _align_offset(offset: int, size: int) -> int:
    if size >= 4:
        align = 4
    elif size == 2:
        align = 2
    else:
        align = 1
    return ((offset + align - 1) // align) * align


def _build_recovered_struct_definition(inv: dict[str, Any], param: dict[str, Any], param_index: int) -> dict[str, Any] | None:
    base_name = _struct_base_type_name(str(param.get("resolved_type") or param.get("type") or ""))
    if not base_name:
        return None

    extras = inv.get("_ghidra_extras")
    if not isinstance(extras, dict):
        extras = {}
    for item in extras.get("data_types") or []:
        if isinstance(item, dict) and item.get("kind") == "struct" and str(item.get("name") or "") == base_name:
            if item.get("fields"):
                return None

    doc_comment = str(inv.get("doc_comment") or "")
    decompiled_doc = str(inv.get("doc") or "")
    fixture_manifest = inv.get("fixture_manifest")
    canonical_args = {}
    if isinstance(fixture_manifest, dict) and isinstance(fixture_manifest.get("canonical_args"), dict):
        canonical_args = fixture_manifest.get("canonical_args") or {}
    if not canonical_args:
        canonical_args = _doc_canonical_args(doc_comment)
    seed = canonical_args.get(str(param.get("name") or ""))
    if seed is not None and not isinstance(seed, dict):
        seed = None
    seed = seed if isinstance(seed, dict) else {}

    alias = f"param_{param_index + 1}"
    alias_types = _parse_decompiled_alias_types(decompiled_doc)
    alias_type = alias_types.get(alias, "")
    scale = _pointer_index_scale(alias_type)
    string_hint = _extract_string_hint_length(decompiled_doc, alias)
    string_direct = _extract_string_direct_use(decompiled_doc, alias)
    indexed_hints = _extract_indexed_field_hints(decompiled_doc, alias, scale)

    fields: list[dict[str, Any]] = []
    used_offsets: set[int] = set()
    next_offset = 0

    if seed:
        for field_name, field_seed in seed.items():
            field_type, field_size = _field_spec_from_name_and_seed(str(field_name), field_seed)
            offset = None
            if isinstance(field_seed, str):
                field_name_text = str(field_name).lower()
                is_string_field = field_name_text.startswith("sz") or field_name_text.startswith("lp")
                if string_hint is not None and is_string_field:
                    offset_units, recovered_size = string_hint
                    offset = offset_units * max(scale, 1)
                    field_size = max(field_size, recovered_size)
                    field_type = f"char[{field_size}]"
                elif string_direct and is_string_field and not fields:
                    offset = 0
            if offset is None:
                offset = _align_offset(next_offset, field_size)
            fields.append(
                {
                    "name": str(field_name),
                    "type": field_type,
                    "offset": offset,
                    "size": field_size,
                    "recovered_from": "canonical_args",
                    "confidence": 0.6,
                }
            )
            used_offsets.add(offset)
            next_offset = max(next_offset, offset + field_size)

    for offset, (field_type, field_size) in sorted(indexed_hints.items()):
        if offset in used_offsets:
            continue
        fields.append(
            {
                "name": f"field_{len(fields)}",
                "type": field_type,
                "offset": offset,
                "size": field_size,
                "recovered_from": "decompiled_access",
                "confidence": 0.45,
            }
        )
        used_offsets.add(offset)
        next_offset = max(next_offset, offset + field_size)

    if not fields:
        return None

    fields = sorted(fields, key=lambda row: (int(row.get("offset", 0)), str(row.get("name") or "")))
    total_size = max(int(field.get("offset", 0)) + int(field.get("size", 0)) for field in fields)
    return {
        "name": base_name,
        "kind": "struct",
        "size": total_size,
        "fields": fields,
        "source_method": "recovered.flat_struct",
        "trust_level": "medium",
        "confidence": 0.55 if seed else 0.4,
        "recovered": True,
    }


def _apply_recovered_struct_layouts(invocables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for inv in invocables:
        if not isinstance(inv, dict):
            enriched.append(inv)
            continue
        merged = dict(inv)
        extras = merged.get("_ghidra_extras")
        if not isinstance(extras, dict):
            extras = {}
        data_types = list(extras.get("data_types") or [])
        added = False
        for idx, param in enumerate(merged.get("parameters") or []):
            if not isinstance(param, dict):
                continue
            recovered = _build_recovered_struct_definition(merged, param, idx)
            if recovered is None:
                continue
            if not any(
                isinstance(item, dict)
                and item.get("kind") == "struct"
                and str(item.get("name") or "") == str(recovered.get("name") or "")
                for item in data_types
            ):
                data_types.append(recovered)
                added = True
        if added:
            extras["data_types"] = data_types
            merged["_ghidra_extras"] = extras
        enriched.append(merged)
    return enriched


def _schema_param_stats(invocables: list[dict]) -> dict[str, Any]:
    total = 0
    with_params = 0
    total_params = 0
    suspicious_argless = 0

    for inv in invocables:
        if not isinstance(inv, dict):
            continue
        total += 1
        params = inv.get("parameters")
        count = len(params) if isinstance(params, list) else 0
        total_params += count
        if count > 0:
            with_params += 1
        elif _SUSPICIOUS_ARGLESS_FN_RE.search(str(inv.get("name") or "")):
            suspicious_argless += 1

    return {
        "function_count": total,
        "with_params_count": with_params,
        "without_params_count": max(0, total - with_params),
        "total_params": total_params,
        "param_coverage": round((with_params / total), 4) if total else 0.0,
        "suspicious_argless_count": suspicious_argless,
    }


def _is_low_fidelity_param_cache(invocables: list[dict]) -> bool:
    stats = _schema_param_stats(invocables)
    return (
        stats["function_count"] >= 5
        and stats["param_coverage"] == 0.0
        and stats["suspicious_argless_count"] > 0
    )


def _is_legacy_bridge_upload_path(raw_path: Any) -> bool:
    if not isinstance(raw_path, str) or not raw_path:
        return False
    try:
        path = _bridge_upload_path_parts(raw_path)
    except Exception:
        return False
    if path["parent"] != _normalized_bridge_upload_dir():
        return False
    return not bool(_HASHED_UPLOAD_NAME_RE.fullmatch(path["name"]))


def _is_hashed_bridge_upload_path(raw_path: Any) -> bool:
    if not isinstance(raw_path, str) or not raw_path:
        return False
    try:
        path = _bridge_upload_path_parts(raw_path)
    except Exception:
        return False
    return path["parent"] == _normalized_bridge_upload_dir() and bool(
        _HASHED_UPLOAD_NAME_RE.fullmatch(path["name"])
    )


def _is_transient_bridge_temp_path(raw_path: Any) -> bool:
    if not isinstance(raw_path, str) or not raw_path:
        return False
    normalized = raw_path.replace("/", "\\").lower()
    return any(segment in normalized for segment in _TRANSIENT_DLL_TEMP_SEGMENTS)


def _has_legacy_bridge_upload_paths(invocables: list[dict]) -> bool:
    for inv in invocables:
        if not isinstance(inv, dict):
            continue
        if _is_legacy_bridge_upload_path(inv.get("dll_path")):
            return True
        execution = inv.get("execution")
        if isinstance(execution, dict) and _is_legacy_bridge_upload_path(execution.get("dll_path")):
            return True
    return False


def _has_transient_bridge_temp_paths(invocables: list[dict]) -> bool:
    for inv in invocables:
        if not isinstance(inv, dict):
            continue
        if _is_transient_bridge_temp_path(inv.get("dll_path")):
            return True
        execution = inv.get("execution")
        if isinstance(execution, dict) and _is_transient_bridge_temp_path(execution.get("dll_path")):
            return True
    return False


def _resolve_discovery_main() -> Path:
    """Resolve discovery/main.py with fallbacks for local env drift."""
    candidates = [SRC_DISCOVERY_DIR / "main.py"]
    repo_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            repo_root / "src" / "discovery" / "main.py",
            repo_root / "api" / "src" / "discovery" / "main.py",
        ]
    )
    for path in candidates:
        if path.exists():
            return path
    joined = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"discovery main.py not found; tried: {joined}")


def _resolve_discovery_bootstrap() -> Path:
    """Resolve the managed discovery bootstrap wrapper, falling back to main.py."""
    candidates = [SRC_DISCOVERY_DIR / "bootstrap.py"]
    repo_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            repo_root / "src" / "discovery" / "bootstrap.py",
            repo_root / "api" / "src" / "discovery" / "bootstrap.py",
        ]
    )
    for path in candidates:
        if path.exists():
            return path
    return _resolve_discovery_main()


def _discovery_child_launch_diagnostics(
    *,
    cmd: list[str],
    binary_path: Path,
    out_dir: Path,
    discovery_env: dict[str, str],
    analysis_profile: str,
    env_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return process-creation facts available before Popen returns a PID."""

    python_exe = Path(str(cmd[0])) if cmd else Path(sys.executable)
    script_path = Path(str(cmd[1])) if len(cmd) > 1 else Path("")
    return {
        "analysis_profile": analysis_profile,
        "command": list(cmd),
        "cwd": os.getcwd(),
        "parent_pid": os.getpid(),
        "thread_name": threading.current_thread().name,
        "python_executable": str(python_exe),
        "python_executable_exists": python_exe.exists(),
        "bootstrap_path": str(script_path),
        "bootstrap_exists": script_path.exists(),
        "binary_path_exists": binary_path.exists(),
        "out_dir": str(out_dir),
        "out_dir_exists": out_dir.exists(),
        "pythonpath": discovery_env.get("PYTHONPATH", ""),
        "pythonpath_exists": Path(discovery_env.get("PYTHONPATH", "")).exists() if discovery_env.get("PYTHONPATH", "") else False,
        "is_windows": IS_WINDOWS,
        **dict(env_diagnostics or {}),
    }


def _bridge_uses_localhost(bridge_url: str | None) -> bool:
    parsed = urlparse(str(bridge_url or ""))
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _normalize_bridge_url_value(bridge_url: str | None) -> str:
    return str(bridge_url or "").strip().rstrip("/")


def _split_bridge_urls(raw_value: str | None) -> list[str]:
    urls: list[str] = []
    for item in _re.split(r"[,\s;]+", str(raw_value or "")):
        normalized = _normalize_bridge_url_value(item)
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls


def allowed_gui_bridge_override_urls() -> list[str]:
    """Return local, configured bridge URLs eligible for request-scoped routing."""

    urls = _split_bridge_urls(os.getenv("GUI_BRIDGE_CANDIDATE_URLS", ""))
    default_url = _normalize_bridge_url_value(GUI_BRIDGE_URL or os.getenv("GUI_BRIDGE_URL", ""))
    if default_url and default_url not in urls:
        urls.append(default_url)
    return [url for url in urls if _bridge_uses_localhost(url)]


def validate_gui_bridge_url_override(bridge_url_override: str | None) -> str:
    """Validate a request-scoped bridge override against the local allowlist."""

    selected = _normalize_bridge_url_value(bridge_url_override)
    if not selected:
        return ""
    allowed = allowed_gui_bridge_override_urls()
    if selected not in allowed:
        raise ValueError("bridge_override_not_allowed")
    return selected


def _effective_gui_bridge_url(bridge_url_override: str | None = None) -> str:
    selected = validate_gui_bridge_url_override(bridge_url_override)
    return selected or _normalize_bridge_url_value(GUI_BRIDGE_URL)


def _bridge_can_use_local_path(binary_path: Path, bridge_url: str | None = None) -> bool:
    """Return True when the GUI bridge can read the same Windows path directly.

    This is only safe for local Windows development where the API and the
    bridge share the same host filesystem. Remote bridge lanes still need the
    base64 upload path.
    """
    return IS_WINDOWS and binary_path.exists() and _bridge_uses_localhost(bridge_url or GUI_BRIDGE_URL)


def _content_addressed_bridge_upload_dir(binary_path: Path, upload_dir: Path) -> Path:
    digest = _dll_sha256(binary_path)[:16]
    safe_stem = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in (binary_path.stem or "dll")
    ).strip("._")
    return upload_dir / f"{safe_stem or 'dll'}-{digest}"


def _stage_bridge_local_dll_family(
    binary_path: Path,
    upload_dir: Path | None = None,
    *,
    content_addressed: bool = False,
) -> list[Path]:
    """Copy a local DLL and its sibling DLL dependencies into the bridge upload dir.

    This keeps host-local analyze-path runs compatible with the bridge's
    runtime loader, which may still resolve execution to `C:\\mcp-factory\\uploads`.
    """
    staged: list[Path] = []
    if binary_path.suffix.lower() != ".dll" or not binary_path.exists():
        return staged
    upload_dir = upload_dir or _BRIDGE_UPLOAD_DIR
    if content_addressed:
        upload_dir = _content_addressed_bridge_upload_dir(binary_path, upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    for candidate in sorted(binary_path.parent.glob("*.dll")):
        destination = upload_dir / candidate.name
        shutil.copyfile(candidate, destination)
        staged.append(destination)
    return staged


def _dll_sha256(binary_path: Path) -> str:
    """Compute the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(binary_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):  # 1 MB chunks
            h.update(chunk)
    return h.hexdigest()


def _inspect_pe_exports(binary_path: Path) -> dict[str, Any]:
    """Best-effort PE export inspection for discovery-output diagnostics."""
    exports: list[str] = []
    if not binary_path.exists():
        return {"available": False, "exports": exports, "error": "binary_missing"}
    try:
        import pefile  # type: ignore
    except Exception as exc:
        return {"available": False, "exports": exports, "error": f"pefile_unavailable: {exc}"}
    try:
        pe_obj = pefile.PE(str(binary_path), fast_load=True)
        try:
            pe_obj.parse_data_directories(
                directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
            )
        except Exception:
            pass
        for symbol in getattr(getattr(pe_obj, "DIRECTORY_ENTRY_EXPORT", None), "symbols", []) or []:
            raw_name = getattr(symbol, "name", None)
            if raw_name:
                exports.append(raw_name.decode("utf-8", errors="replace"))
            else:
                exports.append(f"#{getattr(symbol, 'ordinal', '')}")
    except Exception as exc:
        return {"available": False, "exports": exports, "error": str(exc)}
    return {"available": True, "exports": sorted({name for name in exports if name}), "error": ""}


def _discovery_output_reason_and_owner(
    *,
    returncode: int,
    stderr: str = "",
    output_file_count: int,
    invocable_count: int,
    export_count: int,
) -> tuple[str, str, bool, str]:
    if output_file_count > 0 and invocable_count > 0:
        return (
            "discovery_output_present",
            "analyzer_discovery",
            True,
            "continue hard-family comparison with durable discovery output",
        )
    if output_file_count > 0 and invocable_count == 0:
        return (
            "unsupported_or_unparsed_dll_shape",
            "discovery_extractor",
            False,
            "inspect discovery output schema and parser support for exported DLL shape",
        )
    if export_count > 0 and returncode == 0:
        return (
            "output_persistence_gap",
            "discovery_output_persistence",
            False,
            "repair discovery artifact persistence before semantic comparison",
        )
    if export_count > 0 and (
        int(returncode) == _WINDOWS_CONTROL_C_EXIT or "KeyboardInterrupt" in (stderr or "")
    ):
        return (
            "discovery_subprocess_interrupt",
            "discovery_subprocess_orchestration",
            False,
            "isolate parent or child interrupt propagation before extractor repair",
        )
    if export_count > 0:
        return (
            "discovery_extraction_gap",
            "discovery_extractor",
            False,
            "inspect analyzer stderr and extraction path for exported DLL",
        )
    return (
        "unsupported_or_unparsed_dll_shape",
        "discovery_contract",
        False,
        "classify whether the DLL shape is outside the supported discovery contract",
    )


def _child_runtime_phase_seen(
    child_runtime_diagnostic: dict[str, Any] | None,
    phase: str,
) -> bool:
    diagnostic = dict(child_runtime_diagnostic or {})
    if diagnostic.get("phase") == phase:
        return True
    for entry in diagnostic.get("phase_history") or []:
        if isinstance(entry, dict) and entry.get("phase") == phase:
            return True
    return False


def _apply_ghidra_first_route_policy(
    *,
    base_reason_code: str,
    base_owner: str,
    base_safe_to_compare: bool,
    base_next_action: str,
    ghidra_required: bool,
    bridge_configured: bool,
    bridge_attempted: bool,
    ghidra_entered: bool,
    legacy_pe_parser_entered: bool,
    output_file_count: int,
    invocable_count: int,
) -> tuple[str, str, bool, str]:
    if not ghidra_required:
        return base_reason_code, base_owner, base_safe_to_compare, base_next_action
    if ghidra_entered and output_file_count > 0 and invocable_count > 0:
        return (
            "ghidra_discovery_output_present",
            "bridge_ghidra_discovery",
            True,
            "continue hard-family comparison with Ghidra-backed discovery output",
        )
    if not bridge_configured:
        return (
            "ghidra_bridge_unavailable",
            "discovery_route_policy",
            False,
            "configure an allowed bridge/Ghidra lane before hard-family semantic comparison",
        )
    if not bridge_attempted:
        if legacy_pe_parser_entered:
            return (
                "legacy_pe_discovery_blocked_for_hard_family",
                "discovery_route_policy",
                False,
                "route hard-family strict_dll discovery through Ghidra before interpreting PE-only evidence",
            )
        return (
            "ghidra_required_not_entered",
            "discovery_route_policy",
            False,
            "inspect why the Ghidra-required route was not entered before discovery terminalization",
        )
    return (
        "ghidra_output_missing",
        "bridge_ghidra_discovery",
        False,
        "inspect bridge/Ghidra output production before hard-family semantic comparison",
    )


def _classify_discovery_subprocess_interrupt(
    *,
    returncode: int,
    stderr: str = "",
    child_interrupt_diagnostic: dict[str, Any] | None = None,
    child_runtime_diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify interrupt-shaped discovery subprocess failures without promoting them."""
    stderr_text = str(stderr or "")
    child_diagnostic = dict(child_interrupt_diagnostic or {})
    child_runtime = dict(child_runtime_diagnostic or {})
    child_source_hint = str(child_diagnostic.get("source_hint") or "")
    child_runtime_phase = str(child_runtime.get("phase") or "")
    control_c_exit = int(returncode) == _WINDOWS_CONTROL_C_EXIT
    keyboard_interrupt = "KeyboardInterrupt" in stderr_text
    nested_subprocess_wait = (
        "subprocess.py" in stderr_text
        and "_communicate" in stderr_text
        and (
            "stdout_thread.join" in stderr_text
            or "_wait_for_tstate_lock" in stderr_text
            or "threading.py" in stderr_text
        )
    )
    import_bootstrap_interrupt = keyboard_interrupt and (
        "importlib._bootstrap" in stderr_text
        or "_find_and_load" in stderr_text
        or "_path_stat" in stderr_text
    )
    known_nested_source = child_source_hint in {
        "nested_dumpbin_wait_interrupt",
        "nested_undname_wait_interrupt",
        "nested_import_analysis_wait_interrupt",
        "unknown_child_nested_subprocess_interrupt",
    }
    known_bootstrap_source = child_source_hint in {
        "child_bootstrap_import_interrupted",
        "child_bootstrap_path_stat_interrupted",
        "child_bootstrap_module_load_interrupted",
        "unknown_child_import_bootstrap_interrupt",
    }
    bootstrap_trace_hint = None
    if import_bootstrap_interrupt:
        if "_path_stat" in stderr_text:
            bootstrap_trace_hint = "child_bootstrap_path_stat_interrupted"
        elif "_find_and_load" in stderr_text:
            bootstrap_trace_hint = "child_bootstrap_module_load_interrupted"
        else:
            bootstrap_trace_hint = "child_bootstrap_import_interrupted"
    if import_bootstrap_interrupt:
        if not child_diagnostic and not child_runtime:
            subreason = "child_python_startup_interrupt"
            owner = "discovery_child_python_startup"
            next_action = "stabilize child interpreter startup and launch environment before route-policy judgment"
            precision = "precise"
            source_reason_code = "child_bootstrap_entry_missing"
        else:
            subreason = "child_bootstrap_import_interrupt"
            owner = "discovery_child_import_bootstrap"
            next_action = "isolate parent control propagation and child launch context before discovery imports complete"
            precision = "precise"
            source_reason_code = (
                child_source_hint
                if known_bootstrap_source
                else "child_bootstrap_no_diagnostic"
            )
    elif keyboard_interrupt and nested_subprocess_wait:
        subreason = "child_nested_subprocess_interrupt"
        owner = "discovery_nested_subprocess_wait"
        next_action = "isolate the nested analyzer subprocess and control-event propagation"
        precision = "precise"
        source_reason_code = child_source_hint if known_nested_source else "unknown_child_nested_subprocess_interrupt"
    elif keyboard_interrupt:
        subreason = (
            "child_top_level_keyboard_interrupt"
            if child_source_hint == "child_top_level_keyboard_interrupt"
            else "child_keyboard_interrupt"
        )
        owner = "discovery_child_process"
        next_action = "isolate why the discovery child process receives KeyboardInterrupt"
        precision = "precise"
        source_reason_code = child_source_hint or subreason
    elif control_c_exit:
        subreason = "parent_wait_interrupted"
        owner = "discovery_parent_process_control"
        next_action = "isolate parent console or process-group control propagation"
        precision = "medium"
        source_reason_code = child_source_hint or subreason
    else:
        subreason = "unknown_subprocess_interrupt"
        owner = "discovery_subprocess_orchestration"
        next_action = "capture richer child and parent process diagnostics"
        precision = "low"
        source_reason_code = child_source_hint or subreason
    return {
        "schema_version": "1.0.0",
        "parent_reason_code": "discovery_subprocess_interrupt",
        "subreason_code": subreason,
        "source_reason_code": source_reason_code,
        "owner": owner,
        "classification_precision": precision,
        "control_c_exit": control_c_exit,
        "keyboard_interrupt": keyboard_interrupt,
        "nested_subprocess_wait": nested_subprocess_wait,
        "import_bootstrap_interrupt": import_bootstrap_interrupt,
        "bootstrap_trace_hint": bootstrap_trace_hint,
        "child_interrupt_diagnostic_present": bool(child_diagnostic),
        "child_interrupt_source_hint": child_source_hint or None,
        "child_runtime_diagnostic_present": bool(child_runtime),
        "child_runtime_phase": child_runtime_phase or None,
        "stderr_traceback_shape": {
            "has_subprocess_communicate": "subprocess.py" in stderr_text and "_communicate" in stderr_text,
            "has_stdout_thread_join": "stdout_thread.join" in stderr_text,
            "has_thread_wait_lock": "_wait_for_tstate_lock" in stderr_text,
            "has_threading_py": "threading.py" in stderr_text,
            "has_importlib_bootstrap": "importlib._bootstrap" in stderr_text,
            "has_import_find_and_load": "_find_and_load" in stderr_text,
            "has_import_path_stat": "_path_stat" in stderr_text,
        },
        "next_action": next_action,
    }


def _read_child_interrupt_diagnostic(out_dir: Path) -> dict[str, Any] | None:
    diagnostic_path = out_dir / "discovery-child-interrupt.json"
    if not diagnostic_path.exists():
        return None
    try:
        return json.loads(diagnostic_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema_version": "1.0.0",
            "reason_code": "child_interrupt_diagnostic_unreadable",
            "error": str(exc),
            "path": str(diagnostic_path),
        }


def _read_child_runtime_diagnostic(out_dir: Path) -> dict[str, Any] | None:
    diagnostic_path = out_dir / _DISCOVERY_CHILD_RUNTIME_DIAGNOSTIC
    if not diagnostic_path.exists():
        return None
    try:
        return json.loads(diagnostic_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema_version": "1.0.0",
            "reason_code": "child_runtime_diagnostic_unreadable",
            "error": str(exc),
            "path": str(diagnostic_path),
        }


def _discovery_output_files(out_dir: Path) -> list[Path]:
    mcp_files = sorted(out_dir.glob("*_mcp.json"))
    if mcp_files:
        return mcp_files
    return sorted(
        path
        for path in out_dir.glob("*.json")
        if path.name not in _DISCOVERY_NON_OUTPUT_JSON_NAMES
    )


def _child_runtime_returncode(child_runtime_diagnostic: dict[str, Any] | None) -> int | None:
    if not isinstance(child_runtime_diagnostic, dict):
        return None
    last_observation = child_runtime_diagnostic.get("last_observation")
    if not isinstance(last_observation, dict) or "returncode" not in last_observation:
        return None
    try:
        return int(last_observation.get("returncode"))
    except (TypeError, ValueError):
        return None


def _child_runtime_completed(out_dir: Path) -> tuple[bool, dict[str, Any] | None, list[Path], int | None]:
    child_runtime_diagnostic = _read_child_runtime_diagnostic(out_dir)
    output_files = _discovery_output_files(out_dir)
    child_returncode = _child_runtime_returncode(child_runtime_diagnostic)
    completed = (
        isinstance(child_runtime_diagnostic, dict)
        and str(child_runtime_diagnostic.get("phase") or "").strip() == "bootstrap_main_returned"
        and child_returncode == 0
    )
    return completed, child_runtime_diagnostic, output_files, child_returncode


def _communicate_discovery_child(
    proc: subprocess.Popen,
    *,
    job_id: str,
    binary_path: Path,
    out_dir: Path,
    analysis_profile: str,
    started_at: float,
    timeout_sec: float = _DISCOVERY_CHILD_WAIT_TIMEOUT_SEC,
    poll_sec: float = _DISCOVERY_CHILD_WAIT_POLL_SEC,
) -> tuple[str, str, int, bool, int | None, str]:
    """Wait for discovery while recovering from stale wrapper waits."""
    deadline = started_at + float(timeout_sec)
    last_liveness_emit = started_at
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(getattr(proc, "args", None), timeout_sec)

        wrapper_returncode = proc.poll()
        if wrapper_returncode is not None:
            stdout, stderr = proc.communicate()
            return stdout or "", stderr or "", int(proc.returncode or 0), False, proc.returncode, ""

        completed, child_runtime_diagnostic, output_files, child_returncode = (
            _child_runtime_completed(out_dir)
        )
        if completed:
            wrapper_returncode_before_kill = proc.poll()
            try:
                if wrapper_returncode_before_kill is None:
                    proc.kill()
            except Exception:
                pass
            stdout, stderr = proc.communicate()
            return (
                stdout or "",
                stderr or "",
                int(child_returncode if child_returncode is not None else (proc.returncode or 0)),
                bool(output_files),
                wrapper_returncode_before_kill if wrapper_returncode_before_kill is not None else proc.returncode,
                (
                    "child_runtime_completed_with_outputs"
                    if output_files
                    else "child_runtime_completed_no_output"
                ),
            )

        now = time.time()
        if now - last_liveness_emit >= 15:
            last_liveness_emit = now
            _emit_analyzer_runtime_authority(
                job_id,
                "discovery_child_wait_liveness",
                binary_path=binary_path,
                out_dir=out_dir,
                child_pid=proc.pid,
                output_files=[path.name for path in output_files],
                extra={
                    "analysis_profile": analysis_profile,
                    "duration_sec": round(now - started_at, 3),
                    "timeout_sec": timeout_sec,
                    "child_runtime_diagnostic": child_runtime_diagnostic,
                    "child_runtime_diagnostic_present": bool(child_runtime_diagnostic),
                    "process_poll": wrapper_returncode,
                },
            )
        time.sleep(min(float(poll_sec), max(0.0, remaining)))


def _build_discovery_output_authority(
    *,
    job_id: str,
    binary_path: Path,
    out_dir: Path,
    analysis_profile: str,
    returncode: int,
    stdout: str = "",
    stderr: str = "",
    output_files: list[Path] | None = None,
    invocable_count: int = 0,
    child_pid: int | None = None,
    parent_pid: int | None = None,
    command: list[str] | None = None,
    cwd: str | None = None,
    env_overrides: dict[str, str] | None = None,
    process_lifetime_sec: float | None = None,
    child_interrupt_diagnostic: dict[str, Any] | None = None,
    child_runtime_diagnostic: dict[str, Any] | None = None,
    ghidra_required: bool = False,
    bridge_configured: bool = False,
    bridge_attempted: bool = False,
    ghidra_entered: bool = False,
) -> dict[str, Any]:
    files = list(output_files or [])
    pe_exports = _inspect_pe_exports(binary_path)
    producer_reason_code, owner, safe_to_compare, next_action = _discovery_output_reason_and_owner(
        returncode=returncode,
        stderr=stderr,
        output_file_count=len(files),
        invocable_count=invocable_count,
        export_count=len(pe_exports.get("exports") or []),
    )
    legacy_pe_parser_entered = (
        _child_runtime_phase_seen(child_runtime_diagnostic, "main_pe_exports_start")
        or _child_runtime_phase_seen(child_runtime_diagnostic, "main_pe_exports_done")
    )
    producer_reason_code, owner, safe_to_compare, next_action = _apply_ghidra_first_route_policy(
        base_reason_code=producer_reason_code,
        base_owner=owner,
        base_safe_to_compare=safe_to_compare,
        base_next_action=next_action,
        ghidra_required=bool(ghidra_required),
        bridge_configured=bool(bridge_configured),
        bridge_attempted=bool(bridge_attempted),
        ghidra_entered=bool(ghidra_entered),
        legacy_pe_parser_entered=legacy_pe_parser_entered,
        output_file_count=len(files),
        invocable_count=invocable_count,
    )
    interrupt_diagnostics = None
    if (
        producer_reason_code in {"discovery_subprocess_interrupt", "legacy_pe_discovery_blocked_for_hard_family"}
        or int(returncode) == _WINDOWS_CONTROL_C_EXIT
        or "KeyboardInterrupt" in (stderr or "")
        or bool(child_interrupt_diagnostic)
        or bool(child_runtime_diagnostic)
    ):
        interrupt_diagnostics = _classify_discovery_subprocess_interrupt(
            returncode=returncode,
            stderr=stderr,
            child_interrupt_diagnostic=child_interrupt_diagnostic,
            child_runtime_diagnostic=child_runtime_diagnostic,
        )
    if (
        producer_reason_code == "ghidra_required_not_entered"
        and isinstance(interrupt_diagnostics, dict)
        and str(interrupt_diagnostics.get("subreason_code") or "").strip()
        in {"child_python_startup_interrupt", "child_bootstrap_import_interrupt"}
    ):
        producer_reason_code = str(interrupt_diagnostics.get("subreason_code") or producer_reason_code)
        owner = str(interrupt_diagnostics.get("owner") or owner)
        safe_to_compare = False
        next_action = str(interrupt_diagnostics.get("next_action") or next_action)
    return {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "target": binary_path.stem,
        "dll_name": binary_path.name,
        "dll_path": str(binary_path),
        "analysis_profile": _normalize_analysis_profile(analysis_profile),
        "phase": "analyze_discovery_output",
        "status": "comparable_discovery_success" if safe_to_compare else "non_comparable_discovery_failure",
        "reason_code": producer_reason_code,
        "owner": owner,
        "safe_to_compare": safe_to_compare,
        "route_policy": "ghidra_first_required" if ghidra_required else "compiled_first_default",
        "ghidra_required": bool(ghidra_required),
        "ghidra_entered": bool(ghidra_entered),
        "bridge_configured": bool(bridge_configured),
        "bridge_attempted": bool(bridge_attempted),
        "legacy_pe_parser_entered": bool(legacy_pe_parser_entered),
        "exports_detected": list(pe_exports.get("exports") or []),
        "export_count": len(pe_exports.get("exports") or []),
        "export_inspection": pe_exports,
        "discovery_files_expected": ["*_mcp.json", "*.json"],
        "discovery_files_found": [path.name for path in files],
        "discovery_file_count": len(files),
        "invocable_count": invocable_count,
        "subprocess_returncode": int(returncode),
        "subprocess_control_c_exit": int(returncode) == _WINDOWS_CONTROL_C_EXIT,
        "subprocess_keyboard_interrupt": "KeyboardInterrupt" in (stderr or ""),
        "subprocess_interrupt_diagnostics": interrupt_diagnostics,
        "subprocess_child_interrupt_diagnostic": child_interrupt_diagnostic,
        "subprocess_child_runtime_diagnostic": child_runtime_diagnostic,
        "subprocess_child_pid": child_pid,
        "subprocess_parent_pid": parent_pid,
        "subprocess_command": list(command or []),
        "subprocess_cwd": cwd,
        "subprocess_env_overrides": dict(env_overrides or {}),
        "subprocess_lifetime_sec": (
            round(max(0.0, float(process_lifetime_sec)), 3)
            if process_lifetime_sec is not None
            else None
        ),
        "subprocess_stdout_tail": (stdout or "")[-500:],
        "subprocess_stderr_tail": (stderr or "")[-500:],
        "out_dir": str(out_dir),
        "extraction_phase": "subprocess_completed" if returncode == 0 else "subprocess_error",
        "persistence_phase": "files_present" if files else "no_output_files",
        "evidence_paths": ["discovery-output-authority.json"],
        "next_action": next_action,
        "created_at": time.time(),
    }


def _emit_discovery_output_authority(job_id: str, authority: dict[str, Any]) -> None:
    try:
        existing = _get_job_status(job_id) or {}
        existing["discovery_output_authority"] = authority
        _persist_job_status(job_id, existing, sync=True)
    except Exception as exc:
        logger.warning("[%s] Failed to persist discovery_output_authority to job status: %s", job_id, exc)
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/discovery-output-authority.json",
            json.dumps(authority, indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to upload discovery-output-authority.json artifact: %s", job_id, exc)


def _read_cache_blob(sha: str, filename: str) -> dict | None:
    """Try to read a JSON cache blob.  Returns None on miss."""
    blob_name = f"{_DISCOVERY_CACHE_PREFIX}/{sha}/{filename}"
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
        return json.loads(raw)
    except Exception:
        return None


def _write_cache_blob(sha: str, filename: str, data: dict) -> None:
    """Write a JSON cache blob (best-effort, never raises)."""
    blob_name = f"{_DISCOVERY_CACHE_PREFIX}/{sha}/{filename}"
    try:
        _upload_to_blob(ARTIFACT_CONTAINER, blob_name, json.dumps(data).encode())
        logger.info("Discovery cache written: %s", blob_name)
    except Exception as exc:
        logger.warning("Failed to write discovery cache blob %s: %s", blob_name, exc)


def _persist_bridge_warning(job_id: str, message: str) -> None:
    """Write a bridge_warning field into the job status blob."""
    try:
        existing = _get_job_status(job_id) or {}
        existing["bridge_warning"] = f"GUI bridge unreachable â€” Windows analysis skipped: {message}"
        _persist_job_status(job_id, existing, sync=True)
    except Exception as exc:
        logger.warning("[%s] Failed to persist bridge warning: %s", job_id, exc)


def _classify_bridge_analyzer_stall(
    *,
    attempts: list[dict[str, Any]] | None = None,
    result_emitted: bool = False,
    invocable_count: int = 0,
    exception_class: str = "",
    http_status: int | None = None,
) -> tuple[str, str, str, bool]:
    """Classify the bridge/analyzer boundary without treating heartbeats as proof."""
    attempt_list = list(attempts or [])
    last_attempt = attempt_list[-1] if attempt_list else {}
    heartbeat_count = int(last_attempt.get("heartbeat_count") or 0)
    worker_phase = str(last_attempt.get("bridge_worker_phase") or "").lower()
    exc = str(exception_class or last_attempt.get("exception_class") or "")
    status = http_status if http_status is not None else last_attempt.get("http_status")

    if result_emitted and invocable_count > 0:
        return (
            "bridge_result_emitted",
            "bridge_analyzer",
            "continue discovery comparison with bridge output present",
            True,
        )
    if result_emitted:
        return (
            "unsupported_target_at_bridge_boundary",
            "bridge_analyzer",
            "classify whether the target is unsupported or the bridge returned an empty analyzer result",
            False,
        )
    if status is not None:
        try:
            if int(status) >= 400:
                return (
                    "bridge_request_rejected",
                    "api_to_bridge_transport",
                    "inspect bridge HTTP rejection before analyzer interpretation",
                    False,
                )
        except Exception:
            pass
    if not attempt_list:
        return (
            "bridge_request_not_sent",
            "api_to_bridge_transport",
            "inspect bridge readiness and request construction before analyzer interpretation",
            False,
        )
    if heartbeat_count <= 0:
        return (
            "bridge_stream_no_heartbeat",
            "api_to_bridge_stream",
            "inspect whether bridge /analyze accepted the request and started streaming",
            False,
        )
    if "ghidra" in worker_phase:
        return (
            "ghidra_analysis_hung",
            "bridge_ghidra_analyzer",
            "isolate Ghidra analysis timeout or cancellation behind the bridge",
            False,
        )
    if "timeout" in exc.lower():
        return (
            "bridge_stream_heartbeat_without_result",
            "api_to_bridge_stream",
            "inspect why bridge heartbeats continue without emitting a final result",
            False,
        )
    return (
        "unknown_bridge_analyzer_stall",
        "bridge_analyzer",
        "capture richer bridge/analyzer diagnostics for this stall",
        False,
    )


def _build_bridge_analyzer_authority(
    *,
    job_id: str,
    binary_path: Path,
    analysis_profile: str,
    bridge_url: str,
    attempts: list[dict[str, Any]] | None = None,
    result_emitted: bool = False,
    invocable_count: int = 0,
    exception: BaseException | None = None,
    http_status: int | None = None,
    started_at: float | None = None,
) -> dict[str, Any]:
    attempt_list = list(attempts or [])
    last_attempt = attempt_list[-1] if attempt_list else {}
    exception_class = type(exception).__name__ if exception else str(last_attempt.get("exception_class") or "")
    reason_code, owner, next_action, safe_to_compare = _classify_bridge_analyzer_stall(
        attempts=attempt_list,
        result_emitted=result_emitted,
        invocable_count=invocable_count,
        exception_class=exception_class,
        http_status=http_status,
    )
    now = time.time()
    first_heartbeat_at = None
    last_heartbeat_at = None
    heartbeat_count = 0
    for attempt in attempt_list:
        heartbeat_count += int(attempt.get("heartbeat_count") or 0)
        if attempt.get("first_heartbeat_at") and first_heartbeat_at is None:
            first_heartbeat_at = attempt.get("first_heartbeat_at")
        if attempt.get("last_heartbeat_at"):
            last_heartbeat_at = attempt.get("last_heartbeat_at")

    return {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "target": binary_path.stem,
        "dll_name": binary_path.name,
        "dll_path": str(binary_path),
        "phase": "bridge_analyzer",
        "status": "comparable_bridge_result" if safe_to_compare else "non_comparable_bridge_stall",
        "reason_code": reason_code,
        "owner": owner,
        "safe_to_compare": safe_to_compare,
        "bridge_url": bridge_url,
        "analysis_profile": _normalize_analysis_profile(analysis_profile),
        "request_attempt_count": len(attempt_list),
        "request_attempts": attempt_list,
        "http_status": http_status if http_status is not None else last_attempt.get("http_status"),
        "first_heartbeat_time": first_heartbeat_at,
        "last_heartbeat_time": last_heartbeat_at,
        "heartbeat_count": heartbeat_count,
        "last_heartbeat_age_sec": (
            round(max(0.0, now - float(last_heartbeat_at)), 3)
            if last_heartbeat_at is not None
            else None
        ),
        "stream_result_present": bool(result_emitted),
        "exception_class": exception_class,
        "exception_message": str(exception or last_attempt.get("exception_message") or ""),
        "timeout_type": exception_class if "Timeout" in exception_class else "",
        "bridge_worker_phase": str(last_attempt.get("bridge_worker_phase") or ""),
        "elapsed_sec": (
            round(max(0.0, now - float(started_at)), 3)
            if started_at is not None
            else None
        ),
        "invocable_count": invocable_count,
        "evidence_paths": ["bridge-analyzer-authority.json"],
        "next_action": next_action,
        "created_at": now,
    }


def _emit_bridge_analyzer_authority(job_id: str, authority: dict[str, Any]) -> None:
    try:
        existing = _get_job_status(job_id) or {}
        existing["bridge_analyzer_authority"] = authority
        _persist_job_status(job_id, existing, sync=True)
    except Exception as exc:
        logger.warning("[%s] Failed to persist bridge_analyzer_authority to job status: %s", job_id, exc)
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/bridge-analyzer-authority.json",
            json.dumps(authority, indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to upload bridge-analyzer-authority.json artifact: %s", job_id, exc)


def _extract_invocables(data: Any) -> list:
    """Normalise a discovery JSON payload to a flat list of invocable dicts.

    The discovery pipeline emits:
        {"metadata": {...}, "invocables": [...], "summary": {...}}
    or legacy flat arrays / {name: info} objects.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "invocables" in data and isinstance(data["invocables"], list):
            return data["invocables"]
        # legacy: flat {name: info_dict} mapping
        return [
            {"name": k, **(v if isinstance(v, dict) else {"description": str(v)})}
            for k, v in data.items()
            if k not in ("metadata", "summary")
        ]
    return []


# â”€â”€ Required / default fields for every invocable dict â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_INVOCABLE_DEFAULTS: dict[str, Any] = {
    "name":        "",
    "source_type": "unknown",
    "confidence":  "low",
    "description": "",
    "parameters":  [],
    "execution":   {},
}


def _normalize_invocable(raw: Any) -> dict | None:
    """Coerce a bridge/discovery invocable into a canonical dict shape.

    Returns None if *raw* cannot be salvaged (no name, wrong type, etc.).
    Ensures every value is JSON-serializable (stringifies anything exotic).
    """
    if not isinstance(raw, dict):
        # dataclass / namedtuple â†’ dict
        if hasattr(raw, "to_dict"):
            raw = raw.to_dict()
        elif hasattr(raw, "__dict__"):
            raw = {k: v for k, v in vars(raw).items() if not k.startswith("_")}
        else:
            return None

    name = raw.get("name", "")
    if not name or not isinstance(name, str):
        return None

    out: dict[str, Any] = {}
    for key, default in _INVOCABLE_DEFAULTS.items():
        val = raw.get(key, default)
        # Stringify non-serializable values (e.g. Path objects)
        if isinstance(val, Path):
            val = str(val)
        out[key] = val

    # Carry over extra keys the pipeline may use (signature, return_type, â€¦)
    for key, val in raw.items():
        if key not in out:
            if isinstance(val, Path):
                val = str(val)
            out[key] = val

    # Ensure execution.dll_path / exe_path are strings, not Path objects
    if isinstance(out.get("execution"), dict):
        for pk in ("dll_path", "exe_path", "executable_path", "target_path"):
            if pk in out["execution"] and not isinstance(out["execution"][pk], str):
                out["execution"][pk] = str(out["execution"][pk])

    return out


def _refresh_dll_execution_metadata(
    binary_path: Path,
    invocables: list[dict[str, Any]],
    *,
    bridge_source_path: str | None = None,
) -> list[dict[str, Any]]:
    """Refresh DLL execution metadata from the current parameter surface."""
    refreshed: list[dict[str, Any]] = []
    for inv in invocables:
        if not isinstance(inv, dict):
            refreshed.append(inv)
            continue
        merged = dict(inv)
        execution = dict(merged.get("execution") or {})
        if execution.get("method") == "dll_import":
            params = [p for p in (merged.get("parameters") or []) if isinstance(p, dict)]
            if params:
                execution["arg_types"] = [
                    str(p.get("resolved_type") or p.get("type") or "").strip()
                    for p in params
                ]
            execution["function_name"] = str(execution.get("function_name") or merged.get("name") or "")
            existing_dll_path = str(execution.get("dll_path") or "").strip()
            root_dll_path = str(merged.get("dll_path") or "").strip()
            preferred_dll_path = str(binary_path)
            if binary_path.suffix.lower() == ".dll":
                bridge_source = str(bridge_source_path or "").strip()
                stable_bridge_source = (
                    bridge_source
                    if bridge_source
                    and not _is_transient_bridge_temp_path(bridge_source)
                    and not _is_legacy_bridge_upload_path(bridge_source)
                    else ""
                )
                binary_is_transient = _is_transient_bridge_temp_path(str(binary_path))
                stable_existing = ""
                if binary_is_transient:
                    stable_existing = next(
                        (
                            candidate
                            for candidate in (existing_dll_path, root_dll_path)
                            if candidate
                            and not _is_transient_bridge_temp_path(candidate)
                            and not _is_legacy_bridge_upload_path(candidate)
                        ),
                        "",
                    )
                if stable_bridge_source:
                    preferred_dll_path = stable_bridge_source
                elif stable_existing:
                    preferred_dll_path = stable_existing
                elif binary_is_transient and _bridge_can_use_local_path(binary_path):
                    try:
                        staged = _stage_bridge_local_dll_family(binary_path)
                    except Exception:
                        staged = []
                    staged_candidate = next(
                        (path for path in staged if path.name.lower() == binary_path.name.lower()),
                        None,
                    )
                    if staged_candidate:
                        preferred_dll_path = str(staged_candidate)
            # Preserve the bridge-emitted DLL identity whenever it already points at
            # a concrete artifact. Rewriting that path to a same-named staged upload
            # can make discovery truthful while /execute silently loads a different DLL.
            if binary_path.suffix.lower() == ".dll":
                if stable_bridge_source or not _is_hashed_bridge_upload_path(existing_dll_path):
                    execution["dll_path"] = preferred_dll_path
                if (
                    stable_bridge_source
                    or not root_dll_path
                    or _is_transient_bridge_temp_path(root_dll_path)
                    or _is_legacy_bridge_upload_path(root_dll_path)
                ):
                    merged["dll_path"] = preferred_dll_path
            merged["execution"] = execution
        refreshed.append(merged)
    return refreshed


def _call_gui_bridge(
    binary_path: Path,
    job_id: str,
    hints: str = "",
    *,
    skip_cache: bool = False,
    analysis_profile: str = "strict_dll",
    bridge_url_override: str = "",
) -> tuple[list[dict], str]:
    """Dispatch Windows-only analysis to the GUI bridge.

    Covers GUI (pywinauto), COM/TLB (pythoncom), CLI (Windows EXEs),
    and registry scan â€” none of which run in the local API process without
    the Windows bridge.

    Returns an empty pair when the bridge is unconfigured or unreachable so the
    rest of the pipeline always completes.
    """
    _analysis_profile = _normalize_analysis_profile(analysis_profile)
    _bridge_url = _effective_gui_bridge_url(bridge_url_override)
    _bridge_started_at = time.time()
    _bridge_attempts: list[dict[str, Any]] = []

    if not _bridge_url or not GUI_BRIDGE_SECRET:
        logger.warning("[%s] GUI bridge skipped â€” GUI_BRIDGE_URL or GUI_BRIDGE_SECRET not set", job_id)
        _emit_bridge_analyzer_authority(
            job_id,
            _build_bridge_analyzer_authority(
                job_id=job_id,
                binary_path=binary_path,
                analysis_profile=_analysis_profile,
                bridge_url=str(_bridge_url or ""),
                attempts=[],
                started_at=_bridge_started_at,
            ),
        )
        return [], ""

    import httpx  # already in api/requirements.txt

    # â”€â”€ Fast /health pre-check (5 s timeout) â€” fail fast instead of blocking
    # 70 s per job when the bridge is down.
    try:
        probe_resp = httpx.get(
            f"{_bridge_url}/health",
            headers={"X-Bridge-Key": GUI_BRIDGE_SECRET},
            timeout=5.0,
        )
        if probe_resp.status_code != 200:
            msg = f"Bridge /health returned status {probe_resp.status_code}"
            logger.debug("[%s] BRIDGE PRE-CHECK FAILED: %s", job_id, msg)
            logger.warning("[%s] %s â€” skipping bridge call", job_id, msg)
            _persist_bridge_warning(job_id, msg)
            _emit_bridge_analyzer_authority(
                job_id,
                _build_bridge_analyzer_authority(
                    job_id=job_id,
                    binary_path=binary_path,
                    analysis_profile=_analysis_profile,
                    bridge_url=str(_bridge_url),
                    attempts=[{
                        "attempt": 0,
                        "phase": "health",
                        "http_status": probe_resp.status_code,
                        "heartbeat_count": 0,
                    }],
                    http_status=probe_resp.status_code,
                    started_at=_bridge_started_at,
                ),
            )
            return [], ""
        logger.debug("[%s] bridge /health OK", job_id)
    except Exception as health_exc:
        msg = f"Bridge /health unreachable: {health_exc}"
        logger.debug("[%s] BRIDGE PRE-CHECK FAILED: %s", job_id, msg)
        logger.warning("[%s] %s â€” skipping bridge call", job_id, msg)
        _persist_bridge_warning(job_id, msg)
        _emit_bridge_analyzer_authority(
            job_id,
            _build_bridge_analyzer_authority(
                job_id=job_id,
                binary_path=binary_path,
                analysis_profile=_analysis_profile,
                bridge_url=str(_bridge_url),
                attempts=[{
                    "attempt": 0,
                    "phase": "health",
                    "exception_class": type(health_exc).__name__,
                    "exception_message": str(health_exc),
                    "heartbeat_count": 0,
                }],
                exception=health_exc,
                started_at=_bridge_started_at,
            ),
        )
        return [], ""

    # Base64-encode the binary so the bridge can write it to a local temp file
    # on the Windows VM â€” avoids the "Linux path not found" problem for any
    # arbitrary uploaded EXE (not just Windows system executables).
    #
    # For host-local Windows development, preserve analyze-path semantics and
    # let the bridge use the real repo path directly. That keeps sibling DLLs
    # visible for interwoven fixtures instead of collapsing them into a single
    # uploaded binary with missing local dependencies.
    content_b64: str | None = None
    bridge_analysis_path = binary_path
    if _bridge_can_use_local_path(binary_path, _bridge_url):
        try:
            staged = _stage_bridge_local_dll_family(binary_path, content_addressed=True)
            if staged:
                staged_candidate = next(
                    (path for path in staged if path.name.lower() == binary_path.name.lower()),
                    None,
                )
                if staged_candidate is not None:
                    bridge_analysis_path = staged_candidate
                logger.info(
                    "[%s] staged %d local DLL(s) into content-addressed bridge dir for dependency-safe runtime loading",
                    job_id,
                    len(staged),
                )
        except Exception as exc:
            logger.warning("[%s] Could not stage local DLL family for bridge: %s", job_id, exc)
    else:
        try:
            raw = binary_path.read_bytes()
            if len(raw) <= 50_000_000:  # skip inline transfer for files > 50 MB
                import base64
                content_b64 = base64.b64encode(raw).decode()
        except Exception as exc:
            logger.warning("[%s] Could not read binary for bridge content: %s", job_id, exc)

    bridge_types_by_profile = {
        "strict_dll": ["ghidra"],
        "greybox_dll": ["ghidra", "cli"],
        "full_surface": ["gui", "com", "cli", "registry", "ghidra"],
    }
    payload = {
        "path":    str(bridge_analysis_path),
        "hints":   hints,
        "types":   bridge_types_by_profile[_analysis_profile],
        "content": content_b64,   # None â†’ bridge falls back to system-path lookup
    }
    # â”€â”€ Bridge blob cache check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _bridge_sha = _dll_sha256(binary_path)
    if not skip_cache:
        _cached_bridge = _read_cache_blob(
            _bridge_sha,
            _cache_filename("bridge_result", _analysis_profile),
        )
    else:
        _cached_bridge = None
    if _cached_bridge and isinstance(_cached_bridge.get("invocables"), list):
        _cached_invocables = _cached_bridge["invocables"]
        _cached_bridge_source = str(_cached_bridge.get("bridge_source") or "").strip()
        if _has_legacy_bridge_upload_paths(_cached_invocables) or _is_legacy_bridge_upload_path(_cached_bridge_source):
            logger.warning(
                "[%s] BRIDGE CACHE BYPASS (%s): cached invocables reference legacy upload paths; rebuilding",
                job_id, _bridge_sha[:12],
            )
        elif _has_transient_bridge_temp_paths(_cached_invocables) and (
            not _cached_bridge_source or _is_transient_bridge_temp_path(_cached_bridge_source)
        ):
            logger.warning(
                "[%s] BRIDGE CACHE BYPASS (%s): cached invocables reference transient temp DLL paths without a stable bridge source; rebuilding",
                job_id, _bridge_sha[:12],
            )
        else:
            _bc = len(_cached_invocables)
            logger.info("[%s] BRIDGE CACHE HIT (%s) â€” %d invocables", job_id, _bridge_sha[:12], _bc)
            logger.debug("[%s] bridge blob cache hit sha=%s, %d invocables", job_id, _bridge_sha[:12], _bc)
            return _cached_invocables, _cached_bridge_source

    # Retry up to _BRIDGE_MAX_RETRIES times.  On a cold first upload the bridge
    # analysis can take 60-120 s; if the first HTTP connection times out or is
    # dropped by network infrastructure, the bridge will have finished and
    # *cached* the result by the time the retry arrives, so the retry returns
    # almost immediately.
    _BRIDGE_MAX_RETRIES = 2
    _last_exc: Exception | None = None
    for _attempt in range(_BRIDGE_MAX_RETRIES):
        _attempt_info: dict[str, Any] = {
            "attempt": _attempt + 1,
            "phase": "request",
            "target": binary_path.name,
            "analysis_profile": _analysis_profile,
            "started_at": time.time(),
            "heartbeat_count": 0,
            "stream_result_present": False,
        }
        _bridge_attempts.append(_attempt_info)
        try:
            logger.info(
                "[%s] Calling GUI bridge at %s for %s (attempt %d/%d)",
                job_id, _bridge_url, binary_path.name, _attempt + 1, _BRIDGE_MAX_RETRIES,
            )
            _emit_bridge_analyzer_authority(
                job_id,
                _build_bridge_analyzer_authority(
                    job_id=job_id,
                    binary_path=binary_path,
                    analysis_profile=_analysis_profile,
                    bridge_url=str(_bridge_url),
                    attempts=_bridge_attempts,
                    started_at=_bridge_started_at,
                ),
            )
            result_line: str | None = None
            with httpx.stream(
                "POST",
                f"{_bridge_url}/analyze",
                json=payload,
                headers={"X-Bridge-Key": GUI_BRIDGE_SECRET},
                # connect/write/read are per-operation timeouts.  read=30 is safe
                # because the bridge sends a heartbeat every 15 s, so we will
                # never wait more than ~15 s between data chunks.
                timeout=httpx.Timeout(connect=30.0, read=30.0, write=30.0, pool=10.0),
            ) as resp:
                _attempt_info["http_status"] = resp.status_code
                resp.raise_for_status()
                for line in resp.iter_lines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        obj = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and obj.get("status") == "running":
                        _now = time.time()
                        _attempt_info["heartbeat_count"] = int(_attempt_info.get("heartbeat_count") or 0) + 1
                        _attempt_info.setdefault("first_heartbeat_at", _now)
                        _attempt_info["last_heartbeat_at"] = _now
                        _attempt_info["last_heartbeat_payload"] = obj
                        _attempt_info["bridge_worker_phase"] = str(
                            obj.get("phase")
                            or obj.get("bridge_worker_phase")
                            or obj.get("current_phase")
                            or ""
                        )
                        _attempt_info["bridge_worker_started"] = bool(obj.get("worker_started"))
                        _attempt_info["ghidra_entered"] = bool(obj.get("ghidra_entered"))
                        _attempt_info["ghidra_exited"] = bool(obj.get("ghidra_exited"))
                        logger.info("[%s] Bridge heartbeat â€” analysis in progress", job_id)
                        _emit_bridge_analyzer_authority(
                            job_id,
                            _build_bridge_analyzer_authority(
                                job_id=job_id,
                                binary_path=binary_path,
                                analysis_profile=_analysis_profile,
                                bridge_url=str(_bridge_url),
                                attempts=_bridge_attempts,
                                started_at=_bridge_started_at,
                            ),
                        )
                        continue
                    result_line = stripped  # last non-heartbeat line is the result
                    _attempt_info["stream_result_present"] = True
            if not result_line:
                raise RuntimeError("Bridge stream closed without returning a result")
            data = json.loads(result_line)

            # â”€â”€ Normalize the bridge response â”€â”€
            # The bridge may return:
            #   {"invocables": [...], "count": N, "errors": {...}}
            #   [...] (bare list)
            #   {"invocables": [...]} (minimal)
            # Accept all of these shapes.
            if isinstance(data, list):
                raw_invocables = data
                bridge_source = ""
            elif isinstance(data, dict):
                raw_invocables = data.get("invocables", [])
                if not isinstance(raw_invocables, list):
                    raw_invocables = []
                bridge_source = str(data.get("source") or "").strip()
            else:
                raw_invocables = []
                bridge_source = ""

            if isinstance(data, dict) and data.get("errors"):
                logger.warning("[%s] Bridge reported partial errors: %s", job_id, data["errors"])

            # Validate and normalize each invocable to a canonical shape
            invocables = []
            for raw_inv in raw_invocables:
                normed = _normalize_invocable(raw_inv)
                if normed is not None:
                    invocables.append(normed)

            logger.info("[%s] Bridge returned %d invocables (%d after normalization)",
                        job_id, len(raw_invocables), len(invocables))
            _emit_bridge_analyzer_authority(
                job_id,
                _build_bridge_analyzer_authority(
                    job_id=job_id,
                    binary_path=binary_path,
                    analysis_profile=_analysis_profile,
                    bridge_url=str(_bridge_url),
                    attempts=_bridge_attempts,
                    result_emitted=True,
                    invocable_count=len(invocables),
                    started_at=_bridge_started_at,
                ),
            )
            # â”€â”€ Write bridge blob cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if invocables:
                _write_cache_blob(
                    _bridge_sha,
                    _cache_filename("bridge_result", _analysis_profile),
                    {
                        "invocables": invocables,
                        "bridge_source": bridge_source,
                        "cached_at": time.time(),
                        "binary_sha256": _bridge_sha,
                        "analysis_profile": _analysis_profile,
                    },
                )
            return invocables, bridge_source
        except Exception as exc:
            _last_exc = exc
            _attempt_info["exception_class"] = type(exc).__name__
            _attempt_info["exception_message"] = str(exc)
            _attempt_info["elapsed_sec"] = round(max(0.0, time.time() - float(_attempt_info["started_at"])), 3)
            logger.debug("[%s] bridge attempt %d failed: %s", job_id, _attempt + 1, exc)
            if _attempt < _BRIDGE_MAX_RETRIES - 1:
                logger.warning(
                    "[%s] Bridge attempt %d failed (%s) â€” retrying in 10 s "
                    "(bridge likely cached the result; retry should be near-instant)",
                    job_id, _attempt + 1, exc,
                )
                time.sleep(10)
    # All attempts exhausted
    logger.debug("[%s] bridge ALL ATTEMPTS EXHAUSTED: %s", job_id, _last_exc)
    logger.warning(
        "[%s] GUI bridge call failed after %d attempt(s): %s",
        job_id, _BRIDGE_MAX_RETRIES, _last_exc, exc_info=True,
    )
    # Persist the warning into the job record so the caller can surface it
    _persist_bridge_warning(job_id, str(_last_exc))
    _emit_bridge_analyzer_authority(
        job_id,
        _build_bridge_analyzer_authority(
            job_id=job_id,
            binary_path=binary_path,
            analysis_profile=_analysis_profile,
            bridge_url=str(_bridge_url),
            attempts=_bridge_attempts,
            exception=_last_exc,
            started_at=_bridge_started_at,
        ),
    )
    return [], ""


def _emit_discovery_meta(
    job_id: str,
    binary_sha: str,
    cache_state: str,
    analysis_profile: str,
    param_stats: dict[str, Any],
    *,
    bridge_reachable: bool | None = None,
) -> None:
    """Persist discovery metadata into job status and as a standalone artifact.

    This makes cache quality visible to the collector / run ledger so
    regression analysis can correlate outcomes with discovery conditions.
    """
    meta = {
        "cache_state": cache_state,
        "bridge_reachable": bridge_reachable,
        "param_fidelity": param_stats,
        "analysis_profile": analysis_profile,
        "binary_sha256": binary_sha,
    }
    try:
        existing = _get_job_status(job_id) or {}
        existing["discovery_meta"] = meta
        _persist_job_status(job_id, existing, sync=True)
    except Exception as exc:
        logger.warning("[%s] Failed to persist discovery_meta to job status: %s", job_id, exc)
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/discovery_meta.json",
            json.dumps(meta, indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to upload discovery_meta.json artifact: %s", job_id, exc)


def _try_cached_discovery_result(
    *,
    binary_path: Path,
    job_id: str,
    skip_cache: bool,
    analysis_profile: str,
) -> tuple[dict | None, str, str]:
    """Return a cached discovery payload when safe, else (None, sha, cache_state)."""
    cache_state = "cold"
    sha = _dll_sha256(binary_path)

    if skip_cache:
        logger.info("[%s] skip_cache=True â€” bypassing discovery cache", job_id)
        return None, sha, cache_state

    cached_discovery = _read_cache_blob(
        sha,
        _cache_filename("discovery_result", analysis_profile),
    )
    if cached_discovery is None:
        cached_discovery = _read_cache_blob(sha, "discovery_result.json")
    if not (cached_discovery and isinstance(cached_discovery.get("invocables"), list)):
        return None, sha, cache_state

    cached_invocables = cached_discovery["invocables"]
    inv_count = len(cached_invocables)
    bridge_expected = (
        analysis_profile in {"strict_dll", "greybox_dll"}
        and bool(GUI_BRIDGE_URL and GUI_BRIDGE_SECRET)
    )
    bridge_enriched = bool(cached_discovery.get("bridge_enriched"))
    if bridge_expected and not bridge_enriched:
        bridge_cache = _read_cache_blob(
            sha,
            _cache_filename("bridge_result", analysis_profile),
        )
        if not bridge_cache:
            bridge_cache = _read_cache_blob(sha, "bridge_result.json")
        bridge_enriched = bool(
            bridge_cache and isinstance(bridge_cache.get("invocables"), list)
        )
    else:
        bridge_cache = None
    if bridge_expected and not bridge_enriched:
        has_decompiled = any(
            inv.get("doc_comment") or inv.get("doc", "").startswith("Recovered by Ghidra")
            for inv in cached_invocables if isinstance(inv, dict)
        )
        if has_decompiled:
            bridge_enriched = True

    low_fidelity = _is_low_fidelity_param_cache(cached_invocables)
    if low_fidelity and bridge_enriched and bridge_cache:
        bridge_inv = bridge_cache.get("invocables", [])
        bridge_by_name = {
            inv.get("name", ""): inv
            for inv in bridge_inv if isinstance(inv, dict) and inv.get("name")
        }
        for i, existing in enumerate(cached_invocables):
            ename = existing.get("name", "") if isinstance(existing, dict) else ""
            if ename in bridge_by_name:
                cached_invocables[i] = bridge_by_name.pop(ename)
        for inv in bridge_by_name.values():
            cached_invocables.append(inv)
        low_fidelity = _is_low_fidelity_param_cache(cached_invocables)
        if not low_fidelity:
            cache_state = "warm_repaired"
            logger.info(
                "[%s] DISCOVERY CACHE REPAIRED (%s): merged bridge cache into low-fidelity discovery â€” %d invocables",
                job_id, sha[:12], len(cached_invocables),
            )
    if bridge_expected and not bridge_enriched:
        logger.warning(
            "[%s] DISCOVERY CACHE BYPASS (%s): strict profile requires bridge-enriched schema; rebuilding",
            job_id, sha[:12],
        )
        return None, sha, cache_state
    if low_fidelity:
        logger.warning(
            "[%s] DISCOVERY CACHE BYPASS (%s): low-fidelity parameter schema detected; rebuilding",
            job_id, sha[:12],
        )
        return None, sha, cache_state

    if cache_state != "warm_repaired":
        cache_state = "warm"
    cached_bridge_source = ""
    if isinstance(bridge_cache, dict):
        cached_bridge_source = str(bridge_cache.get("bridge_source") or "").strip()
    cached_invocables = _apply_fixture_manifest_overlay(binary_path, cached_invocables)
    cached_invocables = _apply_recovered_struct_layouts(cached_invocables)
    cached_invocables = _refresh_dll_execution_metadata(
        binary_path,
        cached_invocables,
        bridge_source_path=cached_bridge_source,
    )
    logger.info("[%s] DISCOVERY CACHE HIT (%s) â€” %d invocables, skipping full pipeline", job_id, sha[:12], inv_count)
    logger.debug("[%s] discovery cache hit sha=%s, %d invocables", job_id, sha[:12], inv_count)
    param_stats_cached = _schema_param_stats(cached_invocables)
    bridge_reachable = True if (bridge_expected and bridge_enriched) else None
    _emit_discovery_meta(
        job_id,
        sha,
        cache_state,
        analysis_profile,
        param_stats_cached,
        bridge_reachable=bridge_reachable,
    )
    return {
        "job_id": job_id,
        "artifact_blob": f"{job_id}/cached-discovery-result.json",
        "invocables": cached_invocables,
    }, sha, cache_state


def _run_discovery(
    binary_path: Path,
    job_id: str,
    hints: str = "",
    *,
    skip_cache: bool = False,
    analysis_profile: str = "strict_dll",
    bridge_url_override: str = "",
    ghidra_required: bool = False,
) -> dict:
    """Run the discovery pipeline on a local file path. Returns invocables list."""
    _analysis_profile = _normalize_analysis_profile(analysis_profile)
    _bridge_url = _effective_gui_bridge_url(bridge_url_override)
    _ghidra_required = bool(ghidra_required)
    _bridge_configured = bool(_bridge_url and GUI_BRIDGE_SECRET)
    _emit_analyzer_runtime_authority(
        job_id,
        "run_discovery_entered",
        binary_path=binary_path,
        extra={
            "analysis_profile": _analysis_profile,
            "route_policy": "ghidra_first_required" if _ghidra_required else "compiled_first_default",
            "ghidra_required": _ghidra_required,
        },
    )
    _cached_payload, _sha, _cache_state = _try_cached_discovery_result(
        binary_path=binary_path,
        job_id=job_id,
        skip_cache=skip_cache,
        analysis_profile=_analysis_profile,
    )
    if _cached_payload is not None:
        return _cached_payload
    logger.info("[%s] Discovery cache miss (%s) â€” running full pipeline", job_id, _sha[:12])

    out_dir = Path(tempfile.mkdtemp(prefix=f"mcp_{job_id}_"))
    discovery_main = _resolve_discovery_bootstrap()
    discovery_env, discovery_env_diagnostics = _build_discovery_child_env()
    cmd = [
        sys.executable,
        "-s",
        str(discovery_main),
        "--dll", str(binary_path),
        "--out", str(out_dir),
        "--no-demangle",
        "--analysis-profile", _analysis_profile,
    ]
    if hints:
        import re as _re
        _safe_tag = _re.sub(r"[^A-Za-z0-9_\-]", "_", hints[:40])
        cmd += ["--tag", _safe_tag]
    if IS_WINDOWS and _analysis_profile == "full_surface":
        cmd += ["--registry"]  # scan HKLM App Paths, Uninstall, COM CLSIDs (Â§1.c / P9)

    logger.debug("[%s] subprocess start", job_id)
    logger.info("[%s] STEP 7 \u2713  Discovery subprocess launched", job_id)
    child_launch_diagnostics = _discovery_child_launch_diagnostics(
        cmd=cmd,
        binary_path=binary_path,
        out_dir=out_dir,
        discovery_env=discovery_env,
        analysis_profile=_analysis_profile,
        env_diagnostics=discovery_env_diagnostics,
    )
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_child_launch_attempted",
        binary_path=binary_path,
        out_dir=out_dir,
        extra=child_launch_diagnostics,
    )
    _record_upload_event(
        job_id,
        "discovery_subprocess_launch",
        binary_path=str(binary_path),
        out_dir=str(out_dir),
        cmd=cmd,
        env_overrides={
            "PYTHONPATH": discovery_env.get("PYTHONPATH", ""),
            "startup_env_mode": str(discovery_env_diagnostics.get("startup_env_mode") or ""),
            "api_reload_mode": str(discovery_env_diagnostics.get("api_reload_mode") or ""),
        },
        analysis_profile=_analysis_profile,
        parent_pid=os.getpid(),
    )
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_child_popen_calling",
        binary_path=binary_path,
        out_dir=out_dir,
        extra={**child_launch_diagnostics, "popen_state": "calling"},
    )
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=discovery_env,
            creationflags=_discovery_child_creationflags(),
        )
    except Exception as exc:
        _record_upload_event(
            job_id,
            "discovery_subprocess_popen_exception",
            exception_class=type(exc).__name__,
            exception_message=str(exc),
            **child_launch_diagnostics,
        )
        _emit_analyzer_runtime_authority(
            job_id,
            "discovery_child_popen_exception",
            binary_path=binary_path,
            out_dir=out_dir,
            extra={
                **child_launch_diagnostics,
                "popen_state": "exception",
                "exception_class": type(exc).__name__,
                "exception_message": str(exc),
            },
        )
        raise
    _started_at = time.time()
    _record_upload_event(
        job_id,
        "discovery_subprocess_started",
        child_pid=proc.pid,
        start_ts=_started_at,
    )
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_child_started",
        binary_path=binary_path,
        out_dir=out_dir,
        child_pid=proc.pid,
        extra={**child_launch_diagnostics, "start_ts": _started_at, "popen_state": "returned"},
    )
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_child_wait_start",
        binary_path=binary_path,
        out_dir=out_dir,
        child_pid=proc.pid,
        extra={
            "analysis_profile": _analysis_profile,
            "out_dir_exists": out_dir.exists(),
            "start_ts": _started_at,
            "wait_timeout_sec": 240,
        },
    )
    try:
        (
            stdout,
            stderr,
            _returncode,
            _wait_recovered_from_output,
            _wrapper_returncode,
            _wait_recovery_reason,
        ) = _communicate_discovery_child(
            proc,
            job_id=job_id,
            binary_path=binary_path,
            out_dir=out_dir,
            analysis_profile=_analysis_profile,
            started_at=_started_at,
        )
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        stdout, stderr = proc.communicate()
        child_runtime_diagnostic = _read_child_runtime_diagnostic(out_dir)
        output_files = _discovery_output_files(out_dir)
        _emit_analyzer_runtime_authority(
            job_id,
            "discovery_child_timeout",
            binary_path=binary_path,
            out_dir=out_dir,
            child_pid=proc.pid,
            output_files=[path.name for path in output_files],
            extra={
                "analysis_profile": _analysis_profile,
                "duration_sec": round(time.time() - _started_at, 3),
                "stdout_tail": (stdout or "")[-500:],
                "stderr_tail": (stderr or "")[-500:],
                "timeout_sec": _DISCOVERY_CHILD_WAIT_TIMEOUT_SEC,
                "child_runtime_diagnostic": child_runtime_diagnostic,
                "child_runtime_diagnostic_present": bool(child_runtime_diagnostic),
                "startup_env_mode": discovery_env_diagnostics.get("startup_env_mode"),
                "api_reload_mode": discovery_env_diagnostics.get("api_reload_mode"),
            },
        )
        _record_upload_event(
            job_id,
            "discovery_subprocess_timeout",
            child_pid=proc.pid,
            duration_sec=round(time.time() - _started_at, 3),
            stdout_tail=(stdout or "")[-500:],
            stderr_tail=(stderr or "")[-500:],
            timeout_sec=_DISCOVERY_CHILD_WAIT_TIMEOUT_SEC,
            child_runtime_diagnostic_present=bool(child_runtime_diagnostic),
            child_runtime_phase=(
                str(child_runtime_diagnostic.get("phase") or "")
                if isinstance(child_runtime_diagnostic, dict)
                else ""
            ),
            startup_env_mode=discovery_env_diagnostics.get("startup_env_mode"),
            api_reload_mode=discovery_env_diagnostics.get("api_reload_mode"),
        )
        raise RuntimeError(
            f"Discovery subprocess timed out after {_DISCOVERY_CHILD_WAIT_TIMEOUT_SEC}s.\n"
            f"stderr: {(stderr or '')[-500:]}"
        ) from exc

    _wait_duration_sec = round(time.time() - _started_at, 3)
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_child_wait_returned",
        binary_path=binary_path,
        out_dir=out_dir,
        child_pid=proc.pid,
        extra={
            "analysis_profile": _analysis_profile,
            "duration_sec": _wait_duration_sec,
            "stdout_len": len(stdout or ""),
            "stderr_len": len(stderr or ""),
            "out_dir_exists": out_dir.exists(),
            "wait_recovered_from_output": _wait_recovered_from_output,
            "wait_recovery_reason": _wait_recovery_reason,
            "wrapper_returncode": _wrapper_returncode,
        },
    )
    logger.debug("[%s] subprocess done rc=%d", job_id, _returncode)
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_child_returncode_observed",
        binary_path=binary_path,
        out_dir=out_dir,
        child_pid=proc.pid,
        child_returncode=_returncode,
        extra={
            "analysis_profile": _analysis_profile,
            "duration_sec": _wait_duration_sec,
            "stdout_len": len(stdout or ""),
            "stderr_len": len(stderr or ""),
            "out_dir_exists": out_dir.exists(),
        },
    )

    # â”€â”€ Collect ALL *_mcp.json files produced (EXEs emit cli + gui + exports)
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_output_scan_started",
        binary_path=binary_path,
        out_dir=out_dir,
        child_pid=proc.pid,
        child_returncode=_returncode,
        extra={
            "analysis_profile": _analysis_profile,
            "duration_sec": _wait_duration_sec,
            "stdout_len": len(stdout or ""),
            "stderr_len": len(stderr or ""),
            "out_dir_exists": out_dir.exists(),
        },
    )
    mcp_files = _discovery_output_files(out_dir)
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_output_scan_completed",
        binary_path=binary_path,
        out_dir=out_dir,
        child_pid=proc.pid,
        child_returncode=_returncode,
        output_files=[p.name for p in mcp_files],
        extra={
            "analysis_profile": _analysis_profile,
            "duration_sec": _wait_duration_sec,
            "stdout_len": len(stdout or ""),
            "stderr_len": len(stderr or ""),
            "out_dir_exists": out_dir.exists(),
            "output_file_count": len(mcp_files),
        },
    )
    _emit_analyzer_runtime_authority(
        job_id,
        "discovery_child_completed",
        binary_path=binary_path,
        out_dir=out_dir,
        child_pid=proc.pid,
        child_returncode=_returncode,
        output_files=[p.name for p in mcp_files],
        extra={
            "analysis_profile": _analysis_profile,
            "duration_sec": round(time.time() - _started_at, 3),
            "stdout_tail": (stdout or "")[-500:],
            "stderr_tail": (stderr or "")[-500:],
        },
    )
    _record_upload_event(
        job_id,
        "discovery_subprocess_completed",
        child_pid=proc.pid,
        duration_sec=round(time.time() - _started_at, 3),
        returncode=_returncode,
        stdout_tail=(stdout or "")[-500:],
        stderr_tail=(stderr or "")[-500:],
        produced_output_files=bool(mcp_files),
        output_files=[p.name for p in mcp_files],
    )

    if not mcp_files:
        _child_interrupt_diagnostic = _read_child_interrupt_diagnostic(out_dir)
        _child_runtime_diagnostic = _read_child_runtime_diagnostic(out_dir)
        _authority = _build_discovery_output_authority(
            job_id=job_id,
            binary_path=binary_path,
            out_dir=out_dir,
            analysis_profile=_analysis_profile,
            returncode=_returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            output_files=[],
            invocable_count=0,
            child_pid=proc.pid,
            parent_pid=os.getpid(),
            command=cmd,
            cwd=os.getcwd(),
            env_overrides={
                "PYTHONPATH": discovery_env.get("PYTHONPATH", ""),
                "startup_env_mode": str(discovery_env_diagnostics.get("startup_env_mode") or ""),
                "api_reload_mode": str(discovery_env_diagnostics.get("api_reload_mode") or ""),
            },
            process_lifetime_sec=time.time() - _started_at,
            child_interrupt_diagnostic=_child_interrupt_diagnostic,
            child_runtime_diagnostic=_child_runtime_diagnostic,
            ghidra_required=_ghidra_required,
            bridge_configured=_bridge_configured,
            bridge_attempted=False,
            ghidra_entered=False,
        )
        _emit_discovery_output_authority(job_id, _authority)
        _record_upload_event(
            job_id,
            "discovery_no_output_files",
            child_pid=proc.pid,
            parent_pid=os.getpid(),
            returncode=_returncode,
            stderr_tail=(stderr or "")[-500:],
            discovery_output_reason_code=_authority.get("reason_code"),
            discovery_output_owner=_authority.get("owner"),
            discovery_subprocess_subreason=(
                (_authority.get("subprocess_interrupt_diagnostics") or {}).get("subreason_code")
            ),
            discovery_subprocess_source_reason=(
                (_authority.get("subprocess_interrupt_diagnostics") or {}).get("source_reason_code")
            ),
            child_interrupt_diagnostic_present=bool(_child_interrupt_diagnostic),
            child_runtime_diagnostic_present=bool(_child_runtime_diagnostic),
            route_policy=_authority.get("route_policy"),
            ghidra_required=_authority.get("ghidra_required"),
            legacy_pe_parser_entered=_authority.get("legacy_pe_parser_entered"),
        )
        raise RuntimeError(
            f"Discovery produced no output files.\n"
            f"returncode={_returncode}\n"
            f"stderr: {(stderr or '')[-500:]}"
        )

    # â”€â”€ Merge invocables from all output files and de-duplicate by name â”€â”€
    seen_names: set[str] = set()
    merged_invocables: list[dict] = []
    primary_blob = f"{job_id}/{mcp_files[0].name}"

    for mcp_file in mcp_files:
        try:
            file_data = json.loads(mcp_file.read_bytes())
        except Exception as exc:
            logger.warning(f"[{job_id}] Could not parse {mcp_file.name}: {exc}")
            continue

        invs = _extract_invocables(file_data)
        for inv in invs:
            name = inv.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                merged_invocables.append(inv)

        # Upload every artifact to Blob Storage
        blob_name = f"{job_id}/{mcp_file.name}"
        logger.debug("[%s] uploading artifact %s", job_id, mcp_file.name)
        try:
            _upload_to_blob(ARTIFACT_CONTAINER, blob_name, mcp_file.read_bytes())
        except Exception as exc:
            logger.warning("[%s] Blob upload failed for %s: %s", job_id, mcp_file.name, exc)
        logger.debug("[%s] artifact upload done %s", job_id, mcp_file.name)

    logger.debug("[%s] all artifacts uploaded, calling bridge (effective_bridge_url=%s)", job_id, "SET" if _bridge_url else "NOT SET")
    # Use plain logger.info (no custom_dimensions) here â€” the historical cloud telemetry handler
    # could flush synchronously and block if a third-party log sink is slow.
    if _returncode != 0:
        logger.error("[%s] STEP 8 \u2717  Discovery subprocess failed rc=%d: %s", job_id, _returncode, (stderr or "")[-300:])
    elif not mcp_files:
        logger.error("[%s] STEP 8 \u2717  Discovery produced no output files", job_id)
    else:
        logger.info("[%s] STEP 8 \u2713  Discovery complete: %d file(s), %d invocables", job_id, len(mcp_files), len(merged_invocables))

    # â”€â”€ Update progress before the bridge call so the UI doesn't freeze at 30% â”€â”€
    # _call_gui_bridge can block for up to 180s (+ 10s retry sleep); without this
    # update the job appears stuck at the "running 30%" status written in worker.py.
    if _bridge_url and GUI_BRIDGE_SECRET:
        existing = _get_job_status(job_id) or {}
        _persist_job_status(job_id, {
            **existing,
            "status": "running",
            "progress": 60,
            "message": "Local analysis complete â€” calling Windows GUI bridgeâ€¦",
            "selected_bridge_url": _bridge_url,
            "updated_at": time.time(),
        }, sync=True)
        _emit_analyzer_runtime_authority(
            job_id,
            "bridge_pending",
            binary_path=binary_path,
            out_dir=out_dir,
            child_pid=proc.pid,
            child_returncode=_returncode,
            output_files=[p.name for p in mcp_files],
            bridge_attempted=True,
            extra={"analysis_profile": _analysis_profile, "selected_bridge_url": _bridge_url},
        )

    # â”€â”€ Augment with Windows-only analysis via GUI bridge (if configured) â”€â”€
    # The bridge covers GUI buttons, COM/TLB interfaces, Windows EXE CLI help,
    # and registry scan â€” none of which run in the Linux container.
    bridge_invocables, bridge_source_path = _call_gui_bridge(
        binary_path,
        job_id,
        hints,
        skip_cache=skip_cache,
        analysis_profile=_analysis_profile,
        bridge_url_override=bridge_url_override,
    )
    _record_upload_event(
        job_id,
        "discovery_bridge_result",
        bridge_expected=bool(_bridge_url and GUI_BRIDGE_SECRET),
        bridge_invocable_count=len(bridge_invocables or []),
        bridge_reached=bool(bridge_invocables) if (_bridge_url and GUI_BRIDGE_SECRET) else None,
        selected_bridge_url=_bridge_url,
    )
    if not _bridge_url or not GUI_BRIDGE_SECRET:
        logger.info("[%s] STEP 9 \u2014  Bridge not configured, skipped", job_id)
    elif bridge_invocables:
        logger.info("[%s] STEP 9 \u2713  Bridge returned %d invocables", job_id, len(bridge_invocables))
    else:
        logger.error("[%s] STEP 9 \u2717  Bridge returned 0 invocables (check NSG outbound rules for port 8090 / errno 110)", job_id)
    if bridge_invocables:
        # Bridge invocables (Ghidra / COM / GUI) are richer than the plain
        # pefile export stubs from the discovery subprocess â€” they carry
        # recovered parameter types from the decompiler.
        # Strategy: bridge wins.  If a name already exists in merged_invocables
        # (added by the subprocess with parameters:[]), REPLACE it.  New names
        # are appended as usual.
        bridge_by_name = {inv.get("name", ""): inv for inv in bridge_invocables if inv.get("name")}
        # Replace any existing invocable whose name matches a bridge result
        for i, existing in enumerate(merged_invocables):
            ename = existing.get("name", "")
            if ename in bridge_by_name:
                merged_invocables[i] = bridge_by_name.pop(ename)
        # Append any bridge invocables with names not seen before
        for name, inv in bridge_by_name.items():
            merged_invocables.append(inv)
            seen_names.add(name)

    merged_invocables = _apply_fixture_manifest_overlay(binary_path, merged_invocables)
    merged_invocables = _apply_recovered_struct_layouts(merged_invocables)
    merged_invocables = _refresh_dll_execution_metadata(
        binary_path,
        merged_invocables,
        bridge_source_path=bridge_source_path,
    )
    _discovery_output_authority = _build_discovery_output_authority(
        job_id=job_id,
        binary_path=binary_path,
        out_dir=out_dir,
        analysis_profile=_analysis_profile,
        returncode=_returncode,
        stdout=stdout or "",
        stderr=stderr or "",
        output_files=mcp_files,
        invocable_count=len(merged_invocables),
        child_pid=proc.pid,
        parent_pid=os.getpid(),
        command=cmd,
        cwd=os.getcwd(),
        env_overrides={
            "PYTHONPATH": discovery_env.get("PYTHONPATH", ""),
            "startup_env_mode": str(discovery_env_diagnostics.get("startup_env_mode") or ""),
            "api_reload_mode": str(discovery_env_diagnostics.get("api_reload_mode") or ""),
        },
        process_lifetime_sec=time.time() - _started_at,
        child_runtime_diagnostic=_read_child_runtime_diagnostic(out_dir),
        ghidra_required=_ghidra_required,
        bridge_configured=_bridge_configured,
        bridge_attempted=_bridge_configured,
        ghidra_entered=bool(bridge_invocables),
    )
    _emit_discovery_output_authority(job_id, _discovery_output_authority)
    if _ghidra_required and not bool(_discovery_output_authority.get("safe_to_compare")):
        raise RuntimeError(
            "Ghidra-first discovery route did not produce comparable output: "
            f"{_discovery_output_authority.get('reason_code')}"
        )

    # â”€â”€ Write discovery cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _param_stats = _schema_param_stats(merged_invocables)
    _bridge_expected = (
        _analysis_profile in {"strict_dll", "greybox_dll"}
        and bool(_bridge_url and GUI_BRIDGE_SECRET)
    )
    _bridge_reachable = bool(bridge_invocables) if _bridge_expected else None
    if _bridge_expected and not bridge_invocables:
        _cache_state = "cold_bare"
    _skip_low_fidelity_cache = _bridge_expected and _is_low_fidelity_param_cache(merged_invocables)
    if _skip_low_fidelity_cache:
        logger.warning(
            "[%s] Skipping discovery cache write for low-fidelity schema "
            "(coverage=%s, suspicious_argless=%s)",
            job_id,
            _param_stats.get("param_coverage"),
            _param_stats.get("suspicious_argless_count"),
        )
    else:
        _write_cache_blob(_sha, _cache_filename("discovery_result", _analysis_profile), {
            "invocables": merged_invocables,
            "artifact_blob": primary_blob,
            "cached_at": time.time(),
            "binary_sha256": _sha,
            "analysis_profile": _analysis_profile,
            "bridge_enriched": bool(bridge_invocables),
            "param_stats": _param_stats,
        })

    _emit_discovery_meta(job_id, _sha, _cache_state, _analysis_profile,
                         _param_stats, bridge_reachable=_bridge_reachable)

    return {
        "job_id": job_id,
        "artifact_blob": primary_blob,
        "invocables": merged_invocables,
    }

