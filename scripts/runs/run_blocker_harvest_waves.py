from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.infra.config import GUI_BRIDGE_SECRET, GUI_BRIDGE_URL, PIPELINE_API_KEY  # noqa: E402
from runtime.runtime_contract import local_api_base_url, local_bridge_base_url  # noqa: E402
from scripts.ops.nightly_groundtruth import verify_api_identity, verify_bridge_identity  # noqa: E402


def _load_repo_env_value(name: str) -> str:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip()
    return ""


DEFAULT_API_URL = (os.getenv("MCP_FACTORY_API_URL") or local_api_base_url()).rstrip("/")
DEFAULT_BRIDGE_URL = os.getenv(
    "GUI_BRIDGE_URL",
    _load_repo_env_value("GUI_BRIDGE_URL") or GUI_BRIDGE_URL or local_bridge_base_url(),
).rstrip("/")
DEFAULT_API_KEY = os.getenv("MCP_FACTORY_API_KEY", _load_repo_env_value("PIPELINE_API_KEY") or PIPELINE_API_KEY or "")
DEFAULT_BRIDGE_KEY = os.getenv(
    "BRIDGE_SECRET",
    os.getenv("GUI_BRIDGE_SECRET", _load_repo_env_value("BRIDGE_SECRET") or _load_repo_env_value("GUI_BRIDGE_SECRET") or GUI_BRIDGE_SECRET or ""),
)
TERMINAL_CAMPAIGN_PHASES = {"done", "partial_failure", "cancelled_partial"}
FIXTURE_BUILD_SCRIPT = REPO_ROOT / "tests" / "fixtures" / "contoso_business_suite" / "build-package.ps1"
FIXTURE_MANIFESTS = [
    REPO_ROOT / "tests" / "fixtures" / "contoso_business_suite" / "package_manifest.json",
    REPO_ROOT / "tests" / "fixtures" / "contoso_business_suite" / "package_manifest_batch_a.json",
    REPO_ROOT / "tests" / "fixtures" / "contoso_business_suite" / "package_manifest_batch_b.json",
    REPO_ROOT / "tests" / "fixtures" / "contoso_business_suite" / "package_manifest_batch_c.json",
]
EXTERNAL_PACKAGE_DIRS = [
    REPO_ROOT / ".tmp" / "canary_inspect" / "kyocera",
    REPO_ROOT / ".tmp" / "canary_inspect" / "canon",
    REPO_ROOT / ".tmp" / "demo_batch" / "MultiCommander_win32__15_8_0_3135__exe",
]
SKIP_DLL_TOKENS = ("resource", "mui", "lang", "helper", "setup", "uninst", "update", "crash")
PREFER_CORE_TOKENS = ("driver", "client", "core", "gateway", "bridge", "tool", "vendor")
PREFER_EXTENSION_TOKENS = ("plugin", "ext", "addin", "shell", "hook")
CONTROL_SLICE_FAMILY_PRIORITY = (
    "opaque handle routing",
    "sequencing/state machine",
    "discovery opacity",
    "state",
)
FAMILY_TO_SYSTEM = {
    "opaque handle routing": "generalized runtime artifact materializer",
    "sequencing/state machine": "prerequisite and state-machine classifier",
    "discovery opacity": "discovery opacity augmenter",
}
WAVE_BASELINE_PREDECESSOR = {
    "wave-2-batch-a": "wave-1",
    "wave-2-batch-b": "wave-2-batch-a",
    "wave-2-batch-c": "wave-2-batch-b",
}


@dataclass(frozen=True)
class WaveSpec:
    wave_id: str
    label: str
    kind: str
    manifest_path: Path | None = None
    package_dir: Path | None = None


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def slugify(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")


def powershell_file(script_path: Path, *args: str, timeout_sec: int = 1800) -> subprocess.CompletedProcess[str]:
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path), *args]
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


def api_headers(api_key: str) -> dict[str, str]:
    return {"X-Pipeline-Key": api_key} if api_key else {}


def bridge_headers(bridge_key: str) -> dict[str, str]:
    return {"X-Bridge-Key": bridge_key} if bridge_key else {}


def verify_bridge_execute_identity(bridge_url: str, bridge_key: str) -> tuple[bool, str]:
    invocable = {
        "name": "bridge_execute_identity",
        "execution": {
            "method": "powershell",
            "script_path": r"C:\__bridge_execute_identity__.ps1",
            "script_content": "Write-Output 'bridge_execute_ok'",
        },
    }
    try:
        resp = requests.post(
            f"{bridge_url}/execute",
            headers=bridge_headers(bridge_key),
            json={"invocable": invocable, "args": {}},
            timeout=30,
        )
        resp.raise_for_status()
        result = str(resp.json().get("result", "")).strip()
        if "bridge_execute_ok" not in result:
            return False, f"unexpected_execute_result:{result[:120]}"
        return True, result
    except Exception as exc:
        return False, f"bridge_execute_failed:{exc}"


def wait_for_lane_health(
    api_url: str,
    api_key: str,
    bridge_url: str,
    bridge_key: str,
    *,
    timeout_sec: int = 90,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        api_ok, api_msg = verify_api_identity(api_url, api_key)
        bridge_ok, bridge_msg = verify_bridge_identity(bridge_url, bridge_key)
        execute_ok, execute_msg = verify_bridge_execute_identity(bridge_url, bridge_key)
        lab_status: dict[str, Any] = {}
        try:
            lab_resp = requests.get(
                f"{api_url}/api/lab/status",
                headers=api_headers(api_key),
                timeout=20,
            )
            if lab_resp.status_code == 200:
                lab_status = lab_resp.json()
        except Exception as exc:
            lab_status = {"status": "error", "detail": str(exc)}
        last = {
            "api_ok": api_ok,
            "api_message": api_msg,
            "bridge_ok": bridge_ok,
            "bridge_message": bridge_msg,
            "execute_ok": execute_ok,
            "execute_message": execute_msg,
            "lab_status": lab_status,
            "checked_at": utc_iso(),
        }
        if api_ok and bridge_ok and execute_ok and str(lab_status.get("status") or "") in {"ok", "valid"}:
            return last
        time.sleep(2)
    return last


def manifest_stage_root(manifest: dict[str, Any]) -> Path:
    return (REPO_ROOT / str(manifest.get("stage_root") or "")).resolve()


def build_fixture_package(manifest_path: Path, wave_dir: Path) -> tuple[dict[str, Any], Path, Path]:
    proc = powershell_file(FIXTURE_BUILD_SCRIPT, "-ManifestPath", str(manifest_path))
    build_report = {
        "manifest_path": str(manifest_path),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "built_at": utc_iso(),
    }
    write_json(wave_dir / "fixture-build.json", build_report)
    if proc.returncode != 0:
        raise RuntimeError(f"fixture build failed for {manifest_path.name}")
    manifest = read_json(manifest_path, {})
    stage_root = manifest_stage_root(manifest)
    campaign_request_path = stage_root / "campaign-request.json"
    attach_plan_path = stage_root / "attach-plan.json"
    if not campaign_request_path.exists() or not attach_plan_path.exists():
        raise RuntimeError(f"fixture build did not produce campaign files under {stage_root}")
    return manifest, campaign_request_path, attach_plan_path


def discover_dlls(package_dir: Path) -> list[Path]:
    if not package_dir.exists():
        return []
    return sorted(path for path in package_dir.iterdir() if path.is_file() and path.suffix.lower() == ".dll")


def choose_external_targets(dll_paths: list[Path], limit: int = 3) -> list[Path]:
    if not dll_paths:
        return []
    scored: list[tuple[int, Path]] = []
    for dll_path in dll_paths:
        stem = dll_path.stem.lower()
        score = 0
        if any(token in stem for token in SKIP_DLL_TOKENS):
            score -= 3
        if any(token in stem for token in PREFER_CORE_TOKENS):
            score += 4
        if any(token in stem for token in PREFER_EXTENSION_TOKENS):
            score += 2
        if "icon" in stem:
            score -= 2
        if "dll" in stem:
            score += 1
        scored.append((score, dll_path))
    scored.sort(key=lambda item: (-item[0], item[1].name.lower()))

    chosen: list[Path] = []
    extension_candidate: Path | None = None
    for _score, path in scored:
        stem = path.stem.lower()
        if extension_candidate is None and any(token in stem for token in PREFER_EXTENSION_TOKENS):
            extension_candidate = path
        if path not in chosen and not any(token in stem for token in SKIP_DLL_TOKENS):
            chosen.append(path)
        if len(chosen) >= limit:
            break
    if extension_candidate and extension_candidate not in chosen and len(chosen) < limit:
        chosen.append(extension_candidate)
    if not chosen:
        chosen = [scored[0][1]]
    return chosen[:limit]


def infer_selection_reason(filename: str) -> str:
    lower = filename.lower()
    if any(token in lower for token in PREFER_EXTENSION_TOKENS):
        return "extension_plugin_canary"
    if any(token in lower for token in ("driver", "client", "core")):
        return "vendor_core_canary"
    if "icon" in lower:
        return "dependency_noise_canary"
    return "sibling_dependency_canary"


def build_external_manifest(package_dir: Path) -> dict[str, Any]:
    dll_paths = discover_dlls(package_dir)
    selected = choose_external_targets(dll_paths)
    package_slug = slugify(package_dir.name or package_dir.parent.name)
    return {
        "package_id": f"external-{package_slug}",
        "package_label": package_dir.name,
        "package_purpose": "External software blocker-harvest canary package.",
        "doc_visibility": "unknown_external",
        "dependency_context": "local_extracted_package",
        "operator_notes": "Curated automatically from an already-local extracted package for blocker-family harvesting.",
        "package_context": {
            "package_shape": "extracted_folder",
            "curated_runtime_subset": True,
            "proving_goal": "external_blocker_harvest",
            "selection_rule": "core_plus_dependency_plus_extension_when_available",
        },
        "selected_runtime_targets": [
            {
                "staged_name": path.name,
                "staged_path": str(path),
                "selection_reason": infer_selection_reason(path.name),
                "dependency_confidence": "unknown",
                "lane_id": "lane-1",
            }
            for path in selected
        ],
        "deferred_dlls": [path.name for path in dll_paths if path not in selected],
    }


def write_external_inputs(manifest: dict[str, Any], wave_dir: Path) -> tuple[Path, Path]:
    stage_root = wave_dir / "generated-package"
    stage_root.mkdir(parents=True, exist_ok=True)
    campaign_request = {
        "package_id": manifest["package_id"],
        "package_label": manifest["package_label"],
        "package_context": manifest["package_context"],
        "package_purpose": manifest["package_purpose"],
        "doc_visibility": manifest["doc_visibility"],
        "dependency_context": manifest["dependency_context"],
        "operator_notes": manifest["operator_notes"],
        "analysis_profile": "strict_dll",
        "max_dlls": len(manifest["selected_runtime_targets"]),
    }
    campaign_request_path = stage_root / "campaign-request.json"
    attach_plan_path = stage_root / "attach-plan.json"
    write_json(campaign_request_path, campaign_request)
    write_json(attach_plan_path, manifest["selected_runtime_targets"])
    write_json(stage_root / "external-manifest.json", manifest)
    return campaign_request_path, attach_plan_path


def create_campaign(session: requests.Session, api_url: str, payload: dict[str, Any], api_key: str) -> str:
    resp = session.post(
        f"{api_url}/api/campaigns",
        headers=api_headers(api_key),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return str(resp.json()["campaign_id"])


def attach_campaign_dll(
    session: requests.Session,
    api_url: str,
    api_key: str,
    campaign_id: str,
    attach_entry: dict[str, Any],
) -> dict[str, Any]:
    staged_path = REPO_ROOT / str(attach_entry["staged_path"])
    with staged_path.open("rb") as fh:
        files = {"file": (staged_path.name, fh, "application/octet-stream")}
        data = {
            "hints": f"Blocker-harvest package attach for {staged_path.name}",
            "selection_reason": str(attach_entry.get("selection_reason") or ""),
            "dependency_confidence": str(attach_entry.get("dependency_confidence") or ""),
            "lane_id": str(attach_entry.get("lane_id") or "lane-1"),
        }
        resp = session.post(
            f"{api_url}/api/campaigns/{campaign_id}/attach",
            headers=api_headers(api_key),
            files=files,
            data=data,
            timeout=300,
        )
    resp.raise_for_status()
    return resp.json()


def finalize_campaign_discovery(session: requests.Session, api_url: str, api_key: str, campaign_id: str) -> dict[str, Any]:
    resp = session.post(
        f"{api_url}/api/campaigns/{campaign_id}/finalize-discovery",
        headers=api_headers(api_key),
        timeout=900,
    )
    resp.raise_for_status()
    return resp.json()


def start_campaign_explore(session: requests.Session, api_url: str, api_key: str, campaign_id: str) -> dict[str, Any]:
    body = {
        "explore_settings": {
            "mode": "normal",
            "analysis_profile": "strict_dll",
            "lane_id": "lane-1",
            "parallel_runs": 1,
        }
    }
    resp = session.post(
        f"{api_url}/api/campaigns/{campaign_id}/explore",
        headers=api_headers(api_key),
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def poll_campaign(session: requests.Session, api_url: str, api_key: str, campaign_id: str, wave_dir: Path) -> dict[str, Any]:
    poll_path = wave_dir / "campaign-poll.json"
    last_error_path = wave_dir / "campaign-poll-errors.json"
    transient_errors: list[dict[str, Any]] = []
    while True:
        try:
            resp = session.get(
                f"{api_url}/api/campaigns/{campaign_id}",
                headers=api_headers(api_key),
                timeout=60,
            )
            resp.raise_for_status()
            payload = resp.json()
            write_json(poll_path, payload)
            phase = str(payload.get("phase") or "").lower()
            if phase in TERMINAL_CAMPAIGN_PHASES:
                if transient_errors:
                    write_json(last_error_path, transient_errors)
                return payload
        except requests.RequestException as exc:
            transient_errors.append({"checked_at": utc_iso(), "error": str(exc)})
            write_json(last_error_path, transient_errors[-20:])
        time.sleep(5)


def download_snapshot(session: requests.Session, api_url: str, api_key: str, campaign_id: str, wave_dir: Path) -> Path:
    resp = session.get(
        f"{api_url}/api/campaigns/{campaign_id}/session-snapshot",
        headers=api_headers(api_key),
        timeout=300,
    )
    resp.raise_for_status()
    zip_path = wave_dir / f"campaign-{campaign_id}.zip"
    zip_path.write_bytes(resp.content)
    extract_dir = wave_dir / "snapshot"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    return extract_dir


def _aggregate_secondary_families(classifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in classifications:
        for family in list(row.get("secondary_blocker_families") or []):
            if family:
                counter[str(family)] += 1
    return [{"family": family, "count": count} for family, count in counter.most_common()]


def _candidate_next_systems(classifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in classifications:
        system = str(row.get("candidate_next_system") or "").strip()
        if system:
            counter[system] += 1
    return [{"system": system, "count": count} for system, count in counter.most_common()]


def choose_control_slice_primary_family(dominant_families: list[dict[str, Any]]) -> str:
    families = [str(item.get("family") or "") for item in dominant_families if str(item.get("family") or "")]
    if not families:
        return ""
    by_priority = {family: idx for idx, family in enumerate(CONTROL_SLICE_FAMILY_PRIORITY)}
    return min(families, key=lambda family: (by_priority.get(family, len(CONTROL_SLICE_FAMILY_PRIORITY)), family))


def load_previous_wave_summary(summary_path: Path | None) -> dict[str, Any] | None:
    if not summary_path:
        return None
    payload = read_json(summary_path, {})
    return payload if isinstance(payload, dict) and payload else None


def _summary_is_trusted(summary: dict[str, Any] | None) -> bool:
    if not isinstance(summary, dict) or not summary:
        return False
    if str(summary.get("lane_gate_status") or "") != "trusted":
        return False
    if not bool(summary.get("package_summary_legible")):
        return False
    if int(summary.get("ledger_missing_count") or 0) != 0:
        return False
    if int(summary.get("runtime_path_mismatch_count") or 0) != 0:
        return False
    return True


def find_latest_trusted_wave_summary(wave_id: str, *, exclude_root: Path | None = None) -> dict[str, Any] | None:
    sessions_root = REPO_ROOT / "sessions" / "campaigns" / "blocker_harvest"
    if not sessions_root.exists():
        return None
    candidates = sorted(
        sessions_root.glob(f"*/{wave_id}/wave-summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if exclude_root and exclude_root in path.parents:
            continue
        summary = load_previous_wave_summary(path)
        if _summary_is_trusted(summary):
            summary["_summary_path"] = str(path)
            return summary
    return None


def build_wave_expansion_baseline_contract(
    *,
    wave_id: str,
    previous_summary: dict[str, Any] | None,
    runtime_targets: list[str],
) -> dict[str, Any]:
    if not previous_summary or not runtime_targets:
        return {}
    previous_targets = sorted(str(item) for item in list(previous_summary.get("runtime_targets") or []) if str(item))
    overlap_dll_set = sorted(set(previous_targets) & set(runtime_targets))
    if not overlap_dll_set:
        return {}
    previous_per_dll = list(((previous_summary.get("attribution_summary") or {}).get("per_dll") or []))
    baseline_graph_epoch = str(
        ((previous_summary.get("cohesion_summary") or {}).get("graph_epoch"))
        or ((previous_summary.get("attribution_summary") or {}).get("per_dll") or [{}])[0].get("graph_epoch")
        or ""
    ).strip()
    baseline_seeding_mode = str(
        ((previous_summary.get("cohesion_summary") or {}).get("seeding_mode"))
        or ((previous_summary.get("cohesion_summary") or {}).get("attribution_mode_counts") and "cross_dll_prior")
        or ""
    ).strip()
    entries: list[dict[str, Any]] = []
    for row in previous_per_dll:
        filename = str(row.get("filename") or "").strip()
        if filename not in overlap_dll_set:
            continue
        entries.append(
            {
                "component": str(row.get("component") or "").strip(),
                "dll_id": str(row.get("dll_id") or "").strip(),
                "filename": filename,
                "baseline_job_id": str(row.get("job_id") or "").strip(),
                "source_type": "wave_expansion_overlap_baseline",
                "provisional": False,
                "note": f"trusted overlap baseline from {previous_summary.get('wave_id')}",
                "baseline_verified_count": int(row.get("verified_count") or 0),
                "baseline_total_functions": int(row.get("total_functions") or 0),
                "analysis_entrypoint": str(row.get("analysis_entrypoint") or "").strip(),
                "binary_origin": str(row.get("binary_origin") or "").strip(),
                "analysis_profile": str(row.get("analysis_profile") or "").strip(),
                "cache_state": str(row.get("cache_state") or "").strip(),
                "seeding_mode": baseline_seeding_mode,
                "graph_epoch": str(row.get("graph_epoch") or baseline_graph_epoch or "").strip(),
                "lane_id": str(row.get("lane_id") or "").strip(),
            }
        )
    if not entries:
        return {}
    return {
        "schema_version": "1.0.0",
        "source_wave_id": str(previous_summary.get("wave_id") or ""),
        "source_campaign_id": str(previous_summary.get("campaign_id") or ""),
        "source_summary_path": str(previous_summary.get("_summary_path") or ""),
        "baseline_graph_epoch": baseline_graph_epoch,
        "baseline_seeding_mode": baseline_seeding_mode,
        "baseline_package_dll_set": previous_targets,
        "overlap_dll_set": overlap_dll_set,
        "no_baseline_required_dlls": sorted(set(runtime_targets) - set(overlap_dll_set)),
        "dll_entries": entries,
    }


def summarize_wave_result(
    *,
    wave_id: str,
    campaign_id: str,
    extract_dir: Path,
    runtime_targets: list[str],
    previous_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    truth = read_json(extract_dir / "campaign" / "campaign-truth.json", {}) or read_json(extract_dir / "campaign-truth.json", {})
    cohesion = read_json(extract_dir / "audits" / "campaign-cohesion-report.json", {})
    attribution = read_json(extract_dir / "audits" / "campaign-attribution-report.json", {})
    lane_gate = dict(truth.get("lane_gate") or {})

    lane_reports: list[dict[str, Any]] = []
    blocker_rows: list[dict[str, Any]] = []
    for dll_dir in sorted((extract_dir / "dlls").glob("*")) if (extract_dir / "dlls").exists() else []:
        lane_report = read_json(dll_dir / "lane-trust.json", {})
        blocker = read_json(dll_dir / "blocker-classification.json", {})
        if lane_report:
            lane_reports.append(lane_report)
        if blocker:
            blocker_rows.append(blocker)

    trustworthy_count = sum(1 for row in lane_reports if row.get("trustworthy_for_architecture") is True)
    runtime_path_mismatch_count = sum(1 for row in lane_reports if row.get("runtime_path_trust") == "mismatch")
    ledger_missing_count = sum(1 for row in lane_reports if "ledger_row_missing" in list(row.get("reasons") or []))
    per_dll_truth = list(truth.get("per_dll") or [])
    classified_count = 0
    for idx, row in enumerate(blocker_rows):
        primary = str(row.get("primary_blocker_family") or "").strip()
        truth_row = per_dll_truth[idx] if idx < len(per_dll_truth) else {}
        fully_verified = int(truth_row.get("verified_count") or 0) >= int(truth_row.get("total_functions") or 0) > 0
        if primary or fully_verified:
            classified_count += 1
    package_summary_legible = bool(truth.get("per_dll")) and classified_count > 0
    dominant = list(((truth.get("blocker_harvest_summary") or {}).get("dominant_blocker_families") or []))
    secondary = _aggregate_secondary_families(blocker_rows)
    next_systems = _candidate_next_systems(blocker_rows)
    current_primary_families = [str(item.get("family") or "") for item in dominant if str(item.get("family") or "")]
    previous_primary_families = [
        str(item.get("family") or "")
        for item in list((previous_summary or {}).get("dominant_blocker_families") or [])
        if str(item.get("family") or "")
    ]
    new_primary_families = [family for family in current_primary_families if family not in previous_primary_families]
    stable_primary_families = [family for family in current_primary_families if family in previous_primary_families]
    measured_dlls = len(list(truth.get("per_dll") or []))
    blocker_classified_ratio = (classified_count / measured_dlls) if measured_dlls else 0.0
    total_verified = int(cohesion.get("total_verified") or 0)
    total_functions = int(cohesion.get("total_functions") or 0)
    previous_cohesion = dict((previous_summary or {}).get("cohesion_summary") or {})
    previous_total_verified = int((previous_summary or {}).get("total_verified") or previous_cohesion.get("total_verified") or 0)
    previous_total_functions = int((previous_summary or {}).get("total_functions") or previous_cohesion.get("total_functions") or 0)
    overlap_dll_count = int(
        attribution.get("overlap_dll_count")
        or truth.get("overlap_dll_count")
        or 0
    )
    overlap_baseline_comparable = bool(
        attribution.get("overlap_baseline_comparable")
        if "overlap_baseline_comparable" in attribution
        else truth.get("overlap_baseline_comparable")
    )
    overlap_verified_delta = int(attribution.get("overlap_verified_delta") or 0)
    overlap_regression_summary = list(attribution.get("overlap_regression_summary") or [])
    package_internal_truth_ready = bool(
        attribution.get("package_internal_truth_ready")
        if "package_internal_truth_ready" in attribution
        else truth.get("package_internal_truth_ready")
    )
    package_wide_comparable = bool(
        attribution.get("package_wide_comparable")
        if "package_wide_comparable" in attribution
        else truth.get("package_wide_comparable")
    )
    package_floor_evidence_class = str(
        attribution.get("package_floor_evidence_class")
        or truth.get("package_floor_evidence_class")
        or ""
    )
    baseline_contract_present = bool(
        attribution.get("baseline_contract_present")
        or truth.get("baseline_contract_present")
    )
    verified_delta = overlap_verified_delta if baseline_contract_present else (total_verified - previous_total_verified if previous_summary else 0)
    family_shifted = bool(previous_summary) and current_primary_families != previous_primary_families
    control_slice_reproved_after_system = bool(previous_summary) and (verified_delta > 0 or family_shifted)

    return {
        "wave_id": wave_id,
        "campaign_id": campaign_id,
        "package_id": str(truth.get("package_id") or ""),
        "package_label": str(truth.get("package_label") or ""),
        "runtime_targets": runtime_targets,
        "phase": str(truth.get("phase") or ""),
        "dll_count": int(truth.get("dll_count") or measured_dlls),
        "measured_dlls": measured_dlls,
        "lane_gate_status": str(lane_gate.get("trust_status") or ""),
        "lane_gate": lane_gate,
        "lane_trust_summary": dict(((truth.get("blocker_harvest_summary") or {}).get("lane_trust_summary") or {})),
        "dominant_blocker_families": dominant,
        "secondary_blocker_families": secondary,
        "architecture_relevance_summary": dict(((truth.get("blocker_harvest_summary") or {}).get("architecture_relevance_summary") or {})),
        "candidate_next_systems": next_systems,
        "trustworthy_for_architecture_count": trustworthy_count,
        "blocker_classified_count": classified_count,
        "blocker_classified_ratio": blocker_classified_ratio,
        "package_summary_legible": package_summary_legible,
        "package_internal_truth_ready": package_internal_truth_ready,
        "baseline_contract_present": baseline_contract_present,
        "overlap_baseline_comparable": overlap_baseline_comparable,
        "overlap_dll_count": overlap_dll_count,
        "overlap_verified_delta": overlap_verified_delta,
        "overlap_regression_summary": overlap_regression_summary,
        "package_wide_comparable": package_wide_comparable,
        "package_floor_evidence_class": package_floor_evidence_class,
        "runtime_path_mismatch_count": runtime_path_mismatch_count,
        "ledger_missing_count": ledger_missing_count,
        "hidden_variable_warnings": list(truth.get("hidden_variable_warnings") or []),
        "total_verified": total_verified,
        "total_functions": total_functions,
        "verified_rate": float(cohesion.get("verified_rate") or 0.0),
        "previous_total_verified": previous_total_verified,
        "previous_total_functions": previous_total_functions,
        "verified_delta": verified_delta,
        "control_slice_reproved_after_system": control_slice_reproved_after_system,
        "cohesion_summary": cohesion,
        "attribution_summary": attribution,
        "new_primary_families": new_primary_families,
        "stable_primary_families": stable_primary_families,
    }


def compare_wave_summaries(previous_summary: dict[str, Any], current_summary: dict[str, Any]) -> dict[str, Any]:
    prev_primary = [str(item.get("family") or "") for item in list(previous_summary.get("dominant_blocker_families") or []) if str(item.get("family") or "")]
    curr_primary = [str(item.get("family") or "") for item in list(current_summary.get("dominant_blocker_families") or []) if str(item.get("family") or "")]
    prev_targets = set(str(item) for item in list(previous_summary.get("runtime_targets") or []))
    curr_targets = set(str(item) for item in list(current_summary.get("runtime_targets") or []))
    return {
        "previous_wave_id": previous_summary.get("wave_id"),
        "current_wave_id": current_summary.get("wave_id"),
        "added_runtime_targets": sorted(curr_targets - prev_targets),
        "removed_runtime_targets": sorted(prev_targets - curr_targets),
        "new_primary_families": [family for family in curr_primary if family not in prev_primary],
        "stable_primary_families": [family for family in curr_primary if family in prev_primary],
        "lane_gate_changed": previous_summary.get("lane_gate_status") != current_summary.get("lane_gate_status"),
        "lane_trust_summary_changed": previous_summary.get("lane_trust_summary") != current_summary.get("lane_trust_summary"),
        "package_floor_evidence_class": str(current_summary.get("package_floor_evidence_class") or ""),
        "overlap_baseline_comparable": bool(current_summary.get("overlap_baseline_comparable")),
        "overlap_verified_delta": int(current_summary.get("overlap_verified_delta") or 0),
        "overlap_regression_count": len(list(current_summary.get("overlap_regression_summary") or [])),
        "package_worth_deeper_runtime_spend": bool(current_summary.get("package_summary_legible")) and current_summary.get("runtime_path_mismatch_count", 0) == 0,
    }


def decide_wave_verdict(
    *,
    summary: dict[str, Any],
    previous_summary: dict[str, Any] | None,
    no_signal_streak: int,
) -> tuple[dict[str, Any], int]:
    dominant_families = [str(item.get("family") or "") for item in list(summary.get("dominant_blocker_families") or []) if str(item.get("family") or "")]
    measurement_dominated = bool(dominant_families) and all(
        family in {"measurement", "discovery opacity"} for family in dominant_families
    )
    new_signal = bool(summary.get("new_primary_families"))
    next_no_signal_streak = 0 if new_signal else (no_signal_streak + (1 if previous_summary else 0))

    stop_reasons: list[str] = []
    verdict = "expand"
    if not bool(summary.get("package_internal_truth_ready", True)):
        verdict = "harden trust/measurement"
        stop_reasons.append("package_internal_truth_not_ready")
    elif summary.get("lane_gate_status") == "blocked":
        verdict = "stop and roadblock"
        stop_reasons.append("lane_gate_blocked")
    elif bool(summary.get("baseline_contract_present")) and not bool(summary.get("overlap_baseline_comparable")):
        verdict = "stop and roadblock"
        stop_reasons.append("overlap_baseline_not_comparable")
    elif list(summary.get("overlap_regression_summary") or []):
        verdict = "stop and roadblock"
        stop_reasons.append("overlap_regressions_remain")
    elif summary.get("runtime_path_mismatch_count", 0) > 0:
        verdict = "stop and roadblock"
        stop_reasons.append("runtime_path_mismatch")
    elif summary.get("ledger_missing_count", 0) > 0:
        verdict = "harden trust/measurement"
        stop_reasons.append("ledger_row_missing")
    elif measurement_dominated:
        verdict = "harden trust/measurement"
        stop_reasons.append("measurement_or_discovery_dominated")
    elif not summary.get("package_summary_legible"):
        verdict = "refine package curation"
        stop_reasons.append("package_summary_not_legible")
    elif previous_summary is None:
        measured_dlls = max(1, int(summary.get("measured_dlls") or 0))
        if summary.get("trustworthy_for_architecture_count", 0) < min(3, measured_dlls):
            verdict = "harden trust/measurement"
            stop_reasons.append("insufficient_trusted_dlls")
        elif float(summary.get("blocker_classified_ratio") or 0.0) < 0.8:
            verdict = "refine package curation"
            stop_reasons.append("insufficient_blocker_classification")
    elif next_no_signal_streak >= 2:
        verdict = "stop and roadblock"
        stop_reasons.append("two_consecutive_no_signal_rounds")

    architecture_signal = "unchanged"
    if summary.get("new_primary_families"):
        architecture_signal = "strengthens"
    elif previous_summary and summary.get("stable_primary_families"):
        architecture_signal = "leaves_unchanged"

    return {
        "verdict": verdict,
        "stop_reasons": stop_reasons,
        "architecture_signal": architecture_signal,
    }, next_no_signal_streak


def render_summary_markdown(summary: dict[str, Any], comparison: dict[str, Any] | None, verdict: dict[str, Any]) -> str:
    dominant = ", ".join(f"{item['family']} ({item['dll_count']})" for item in list(summary.get("dominant_blocker_families") or [])) or "none"
    secondary = ", ".join(f"{item['family']} ({item['count']})" for item in list(summary.get("secondary_blocker_families") or [])) or "none"
    lane_trust = ", ".join(f"{k}={v}" for k, v in dict(summary.get("lane_trust_summary") or {}).items()) or "none"
    next_systems = ", ".join(f"{item['system']} ({item['count']})" for item in list(summary.get("candidate_next_systems") or [])) or "none"
    lines = [
        f"# {summary['wave_id']} summary",
        "",
        f"- package: `{summary.get('package_id')}`",
        f"- runtime targets: {', '.join(summary.get('runtime_targets') or [])}",
        f"- lane gate: `{summary.get('lane_gate_status')}`",
        f"- lane trust summary: {lane_trust}",
        f"- dominant blocker families: {dominant}",
        f"- secondary blocker families: {secondary}",
        f"- candidate next systems: {next_systems}",
        f"- trustworthy DLLs: {summary.get('trustworthy_for_architecture_count')}/{summary.get('measured_dlls')}",
        f"- blocker classification ratio: {float(summary.get('blocker_classified_ratio') or 0.0):.2%}",
        f"- package summary legible: `{bool(summary.get('package_summary_legible'))}`",
        f"- package internal truth ready: `{bool(summary.get('package_internal_truth_ready'))}`",
        f"- overlap baseline comparable: `{bool(summary.get('overlap_baseline_comparable'))}`",
        f"- package wide comparable: `{bool(summary.get('package_wide_comparable'))}`",
        f"- architecture signal: `{verdict.get('architecture_signal')}`",
        f"- next-step verdict: `{verdict.get('verdict')}`",
    ]
    if summary.get("baseline_contract_present"):
        lines.extend(
            [
                f"- overlap DLL count: {int(summary.get('overlap_dll_count') or 0)}",
                f"- overlap verified delta: {int(summary.get('overlap_verified_delta') or 0)}",
                f"- overlap regressions: {len(list(summary.get('overlap_regression_summary') or []))}",
            ]
        )
    if comparison:
        lines.extend(
            [
                "",
                "## Comparison",
                f"- added runtime targets: {', '.join(comparison.get('added_runtime_targets') or []) or 'none'}",
                f"- new primary families: {', '.join(comparison.get('new_primary_families') or []) or 'none'}",
                f"- stable primary families: {', '.join(comparison.get('stable_primary_families') or []) or 'none'}",
                f"- overlap baseline comparable: `{bool(comparison.get('overlap_baseline_comparable'))}`",
                f"- overlap verified delta: {int(comparison.get('overlap_verified_delta') or 0)}",
                f"- package worth deeper runtime spend: `{bool(comparison.get('package_worth_deeper_runtime_spend'))}`",
            ]
        )
    if verdict.get("stop_reasons"):
        lines.extend(["", "## Stop reasons"] + [f"- {reason}" for reason in list(verdict.get("stop_reasons") or [])])
    return "\n".join(lines) + "\n"


def build_control_slice_decision(summary: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    dominant = list(summary.get("dominant_blocker_families") or [])
    secondary = list(summary.get("secondary_blocker_families") or [])
    next_systems = list(summary.get("candidate_next_systems") or [])
    selected_family = choose_control_slice_primary_family(dominant)
    architect_summary = dict((summary.get("attribution_summary") or {}).get("architect_summary") or {})
    selected_system = str(architect_summary.get("leading_candidate_system") or "")
    aligned_system = FAMILY_TO_SYSTEM.get(selected_family, "")
    if aligned_system:
        selected_system = aligned_system
    elif not selected_system:
        selected_system = str((next_systems[0] or {}).get("system") or "") if next_systems else ""
    bounded_tranche_required = bool(selected_family or selected_system)
    control_slice_reproved = bool(summary.get("control_slice_reproved_after_system"))
    next_step_verdict = str(verdict.get("verdict") or "")
    if not control_slice_reproved and bounded_tranche_required:
        next_step_verdict = "build bounded system"
    return {
        "schema_version": "1.0.0",
        "wave_id": str(summary.get("wave_id") or ""),
        "campaign_id": str(summary.get("campaign_id") or ""),
        "package_id": str(summary.get("package_id") or ""),
        "package_label": str(summary.get("package_label") or ""),
        "dominant_blocker_family": selected_family,
        "secondary_blocker_families": [str(item.get("family") or "") for item in secondary if str(item.get("family") or "")],
        "candidate_next_system": selected_system,
        "lane_gate_status": str(summary.get("lane_gate_status") or ""),
        "trustworthy_for_architecture_count": int(summary.get("trustworthy_for_architecture_count") or 0),
        "measured_dlls": int(summary.get("measured_dlls") or 0),
        "blocker_classified_ratio": float(summary.get("blocker_classified_ratio") or 0.0),
        "strength_vs_suite_ranking": str(verdict.get("architecture_signal") or "unchanged"),
        "bounded_tranche_required": bounded_tranche_required,
        "wave_2_allowed": control_slice_reproved and verdict.get("verdict") == "expand",
        "next_step_verdict": next_step_verdict,
        "stop_reasons": list(verdict.get("stop_reasons") or []),
    }


def render_expansion_decision_note(
    *,
    summary: dict[str, Any],
    comparison: dict[str, Any] | None,
    verdict: dict[str, Any],
) -> str:
    attribution = dict(summary.get("attribution_summary") or {})
    dominant = ", ".join(f"{item['family']} ({item['dll_count']})" for item in list(summary.get("dominant_blocker_families") or [])) or "none"
    overlap_regressions = list(summary.get("overlap_regression_summary") or [])
    no_baseline_required = list((attribution.get("no_baseline_required_dlls") or []))
    lines = [
        "## Expansion Wave Decision Note",
        "",
        f"- package id: `{summary.get('package_id')}`",
        f"- campaign id: `{summary.get('campaign_id')}`",
        f"- trust summary: lane gate `{summary.get('lane_gate_status')}`, ledger missing `{int(summary.get('ledger_missing_count') or 0)}`, runtime path mismatches `{int(summary.get('runtime_path_mismatch_count') or 0)}`",
        f"- verified totals: `{int(summary.get('total_verified') or 0)}/{int(summary.get('total_functions') or 0)}`",
        f"- dominant blocker families: {dominant}",
        f"- package internal truth ready: `{bool(summary.get('package_internal_truth_ready'))}`",
        f"- overlap baseline comparable: `{bool(summary.get('overlap_baseline_comparable'))}`",
        f"- package wide comparable: `{bool(summary.get('package_wide_comparable'))}`",
        f"- overlap dll count: `{int(summary.get('overlap_dll_count') or 0)}`",
        f"- overlap verified delta: `{int(summary.get('overlap_verified_delta') or 0)}`",
        f"- no-baseline-required dlls: {', '.join(no_baseline_required) or 'none'}",
    ]
    if comparison:
        lines.extend(
            [
                "",
                "## Comparison",
                f"- added runtime targets: {', '.join(comparison.get('added_runtime_targets') or []) or 'none'}",
                f"- new primary families: {', '.join(comparison.get('new_primary_families') or []) or 'none'}",
                f"- stable primary families: {', '.join(comparison.get('stable_primary_families') or []) or 'none'}",
            ]
        )
    lines.extend(["", "## Overlap regressions"])
    if overlap_regressions:
        lines.extend(
            [
                f"- {row.get('dll')}/{row.get('function')}: {row.get('old_status')} -> {row.get('new_status')}"
                for row in overlap_regressions
            ]
        )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Verdict",
            f"`{verdict.get('verdict')}`",
        ]
    )
    if verdict.get("stop_reasons"):
        lines.extend(["", "## Stop reasons"] + [f"- {reason}" for reason in list(verdict.get("stop_reasons") or [])])
    return "\n".join(lines) + "\n"


def write_roadblock(summary: dict[str, Any], verdict: dict[str, Any], output_dir: Path) -> Path:
    roadblock_id = f"RB-2026-04-03-{summary['wave_id']}-blocker-harvest-stop"
    stop_reasons = set(verdict.get("stop_reasons", []))
    roadblock_class = "plateau"
    if stop_reasons & {"lane_gate_blocked", "runtime_path_mismatch", "ledger_row_missing", "overlap_baseline_not_comparable", "package_internal_truth_not_ready"}:
        roadblock_class = "measurement"
    payload = {
        "id": roadblock_id,
        "title": f"Blocker-harvest stopped at {summary['wave_id']}",
        "class": roadblock_class,
        "layer": "campaign_orchestration",
        "symptom": f"Wave {summary['wave_id']} ended with verdict '{verdict['verdict']}'",
        "smallest_reproducer": {
            "wave_id": summary["wave_id"],
            "campaign_id": summary.get("campaign_id"),
            "package_id": summary.get("package_id"),
            "lane_gate_status": summary.get("lane_gate_status"),
        },
        "trust_impact": "Campaign interpretation is not trustworthy enough to continue automatically.",
        "allowed_next_actions": [
            "harden lane trust and measurement",
            "refine package curation",
            "rerun the blocked wave only after fixing the stop cause"
        ],
        "disallowed_next_actions": [
            "continue to later waves without fixing trust or measurement",
            "treat the blocker as an architecture gap without trustworthy lane evidence"
        ],
        "exit_criteria": [
            "lane gate not blocked",
            "runtime path trust mismatches resolved",
            "ledger row presence restored if missing"
        ],
        "next_move": verdict["verdict"],
    }
    path = REPO_ROOT / "bugs" / f"{roadblock_id}.json"
    write_json(path, payload)
    write_json(output_dir / "roadblock.json", payload)
    return path


def run_campaign_from_inputs(
    *,
    api_url: str,
    api_key: str,
    campaign_request_path: Path,
    attach_plan_path: Path,
    wave_dir: Path,
    baseline_contract: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], Path]:
    session = requests.Session()
    campaign_request = read_json(campaign_request_path, {})
    if baseline_contract:
        campaign_request["baseline_contract"] = dict(baseline_contract)
    attach_plan = read_json(attach_plan_path, [])
    campaign_id = create_campaign(session, api_url, campaign_request, api_key)
    write_json(wave_dir / "campaign-created.json", {"campaign_id": campaign_id, "request": campaign_request})

    attach_results: list[dict[str, Any]] = []
    for entry in attach_plan:
        attach_results.append(attach_campaign_dll(session, api_url, api_key, campaign_id, entry))
    write_json(wave_dir / "attach-results.json", attach_results)

    finalize_payload = finalize_campaign_discovery(session, api_url, api_key, campaign_id)
    write_json(wave_dir / "finalize-discovery.json", finalize_payload)

    explore_payload = start_campaign_explore(session, api_url, api_key, campaign_id)
    write_json(wave_dir / "explore-start.json", explore_payload)

    final_status = poll_campaign(session, api_url, api_key, campaign_id, wave_dir)
    snapshot_dir = download_snapshot(session, api_url, api_key, campaign_id, wave_dir)
    return campaign_id, final_status, snapshot_dir


def wave_specs() -> list[WaveSpec]:
    specs = [
        WaveSpec("wave-1", "Contoso 4-DLL proof", "fixture", manifest_path=FIXTURE_MANIFESTS[0]),
        WaveSpec("wave-2-batch-a", "Contoso batch A", "fixture", manifest_path=FIXTURE_MANIFESTS[1]),
        WaveSpec("wave-2-batch-b", "Contoso batch B", "fixture", manifest_path=FIXTURE_MANIFESTS[2]),
        WaveSpec("wave-2-batch-c", "Contoso batch C full package", "fixture", manifest_path=FIXTURE_MANIFESTS[3]),
    ]
    for package_dir in EXTERNAL_PACKAGE_DIRS:
        specs.append(
            WaveSpec(
                f"wave-3-{slugify(package_dir.name)}",
                f"External package {package_dir.name}",
                "external",
                package_dir=package_dir,
            )
        )
    return specs


def execute_wave(
    spec: WaveSpec,
    *,
    api_url: str,
    api_key: str,
    wave_dir: Path,
    baseline_summary: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if spec.kind == "fixture":
        manifest, campaign_request_path, attach_plan_path = build_fixture_package(spec.manifest_path or Path(), wave_dir)
        runtime_targets = [str(item.get("staged_name") or "") for item in list(manifest.get("selected_runtime_targets") or [])]
        write_json(wave_dir / "package-manifest.json", manifest)
    else:
        manifest = build_external_manifest(spec.package_dir or Path())
        campaign_request_path, attach_plan_path = write_external_inputs(manifest, wave_dir)
        runtime_targets = [str(item.get("staged_name") or "") for item in list(manifest.get("selected_runtime_targets") or [])]

    baseline_contract = build_wave_expansion_baseline_contract(
        wave_id=spec.wave_id,
        previous_summary=baseline_summary,
        runtime_targets=runtime_targets,
    )
    if baseline_summary:
        write_json(wave_dir / "baseline-summary.json", baseline_summary)
    if baseline_contract:
        write_json(wave_dir / "baseline-contract.json", baseline_contract)

    campaign_id, final_status, snapshot_dir = run_campaign_from_inputs(
        api_url=api_url,
        api_key=api_key,
        campaign_request_path=campaign_request_path,
        attach_plan_path=attach_plan_path,
        wave_dir=wave_dir,
        baseline_contract=baseline_contract,
    )
    write_json(wave_dir / "campaign-final-status.json", final_status)
    summary = summarize_wave_result(
        wave_id=spec.wave_id,
        campaign_id=campaign_id,
        extract_dir=snapshot_dir,
        runtime_targets=runtime_targets,
        previous_summary=None,
    )
    return manifest, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run autonomous blocker-harvest campaign waves.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--bridge-key", default=DEFAULT_BRIDGE_KEY)
    parser.add_argument("--output-root", default="")
    parser.add_argument("--start-wave", default="wave-1")
    parser.add_argument("--stop-after-wave", default="")
    parser.add_argument("--control-slice-baseline-summary", default="")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_root = Path(args.output_root) if args.output_root else (REPO_ROOT / "sessions" / "campaigns" / "blocker_harvest" / timestamp)
    output_root.mkdir(parents=True, exist_ok=True)

    restart_proc = powershell_file(REPO_ROOT / "sessions" / "restart_local_services.ps1", timeout_sec=180)
    write_json(
        output_root / "wave-0" / "restart-local-services.json",
        {
            "returncode": restart_proc.returncode,
            "stdout": restart_proc.stdout[-4000:],
            "stderr": restart_proc.stderr[-4000:],
            "completed_at": utc_iso(),
        },
    )
    if restart_proc.returncode != 0:
        raise RuntimeError("local lane restart failed")

    lane_health = wait_for_lane_health(args.api_url, args.api_key, args.bridge_url, args.bridge_key)
    write_json(output_root / "wave-0" / "lane-health.json", lane_health)
    if not (lane_health.get("api_ok") and lane_health.get("bridge_ok") and lane_health.get("execute_ok")):
        raise RuntimeError(f"lane health failed: {lane_health}")

    specs = wave_specs()
    start_index = next((idx for idx, spec in enumerate(specs) if spec.wave_id == args.start_wave), 0)
    stop_after = str(args.stop_after_wave or "").strip()
    previous_summary: dict[str, Any] | None = None
    baseline_summary = load_previous_wave_summary(Path(args.control_slice_baseline_summary) if args.control_slice_baseline_summary else None)
    no_signal_streak = 0
    campaign_index: list[dict[str, Any]] = []

    for spec in specs[start_index:]:
        wave_dir = output_root / spec.wave_id
        wave_dir.mkdir(parents=True, exist_ok=True)
        baseline_for_wave = previous_summary
        expected_predecessor = WAVE_BASELINE_PREDECESSOR.get(spec.wave_id, "")
        if expected_predecessor and (
            not baseline_for_wave or str(baseline_for_wave.get("wave_id") or "") != expected_predecessor
        ):
            baseline_for_wave = find_latest_trusted_wave_summary(expected_predecessor, exclude_root=output_root)

        manifest, summary = execute_wave(
            spec,
            api_url=args.api_url,
            api_key=args.api_key,
            wave_dir=wave_dir,
            baseline_summary=baseline_for_wave,
        )
        comparison_summary = baseline_for_wave or previous_summary
        if spec.wave_id == "wave-1" and comparison_summary is None and baseline_summary:
            comparison_summary = baseline_summary
            write_json(wave_dir / "control-slice-baseline-summary.json", baseline_summary)
        if comparison_summary:
            summary = summarize_wave_result(
                wave_id=summary["wave_id"],
                campaign_id=summary["campaign_id"],
                extract_dir=wave_dir / "snapshot",
                runtime_targets=summary["runtime_targets"],
                previous_summary=comparison_summary,
            )
        comparison = compare_wave_summaries(comparison_summary, summary) if comparison_summary else None
        verdict, no_signal_streak = decide_wave_verdict(
            summary=summary,
            previous_summary=comparison_summary,
            no_signal_streak=no_signal_streak,
        )
        write_json(wave_dir / "package-manifest-used.json", manifest)
        write_json(wave_dir / "wave-summary.json", summary)
        if comparison:
            write_json(wave_dir / "wave-comparison.json", comparison)
        write_json(wave_dir / "next-step-verdict.json", verdict)
        if spec.wave_id == "wave-1":
            write_json(wave_dir / "control-slice-decision.json", build_control_slice_decision(summary, verdict))
        elif summary.get("baseline_contract_present"):
            write_text(wave_dir / f"{spec.wave_id}-decision-note.md", render_expansion_decision_note(summary=summary, comparison=comparison, verdict=verdict))
            if spec.wave_id == "wave-2-batch-b":
                write_text(wave_dir / "batch-b-decision-note.md", render_expansion_decision_note(summary=summary, comparison=comparison, verdict=verdict))
        write_text(wave_dir / "wave-summary.md", render_summary_markdown(summary, comparison, verdict))
        campaign_index.append(
            {
                "wave_id": spec.wave_id,
                "campaign_id": summary["campaign_id"],
                "package_id": summary.get("package_id"),
                "runtime_targets": summary.get("runtime_targets"),
                "verdict": verdict.get("verdict"),
            }
        )
        write_json(output_root / "campaign-index.json", campaign_index)

        if verdict["verdict"] == "stop and roadblock":
            roadblock_path = write_roadblock(summary, verdict, wave_dir)
            write_json(output_root / "stop-state.json", {"wave_id": spec.wave_id, "roadblock_path": str(roadblock_path)})
            break
        previous_summary = summary
        if stop_after and spec.wave_id == stop_after:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
