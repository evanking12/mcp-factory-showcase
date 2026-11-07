from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from api.pipeline.core.decomposition_contract import (
    DecompositionLifecycle,
    ShardEconomics,
    build_decomposition_object_id,
    build_shard_validity_observer,
)
from api.pipeline.core.types import Campaign


PACKAGE_INTAKE_SHARD_SCHEMA_VERSION = "1.0.0"


def _normalize_package_input(package_input: Campaign | dict[str, Any]) -> dict[str, Any]:
    if isinstance(package_input, Campaign):
        payload = package_input.to_dict()
    else:
        payload = dict(package_input or {})
    payload["dll_entries"] = list(payload.get("dll_entries") or [])
    return payload


def _normalize_shard_entries(raw_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in list(raw_entries or []):
        if not isinstance(row, dict):
            continue
        dll_id = str(row.get("dll_id") or row.get("id") or "").strip()
        filename = str(row.get("filename") or "").strip()
        job_id = str(row.get("job_id") or "").strip()
        if not dll_id and not filename:
            continue
        normalized.append(
            {
                "dll_id": dll_id,
                "filename": filename,
                "job_id": job_id,
                "component": str(row.get("component") or row.get("component_name") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "estimated_runtime_minutes": float(
                    row.get("estimated_runtime_minutes")
                    or row.get("runtime_weight_minutes")
                    or 0.0
                ),
            }
        )
    return sorted(
        normalized,
        key=lambda row: (
            row.get("filename", ""),
            row.get("dll_id", ""),
            row.get("job_id", ""),
        ),
    )


@dataclass(frozen=True)
class PackageIntakeShard:
    lifecycle: DecompositionLifecycle
    shard_ordinal: int
    dll_ids: tuple[str, ...]
    dll_filenames: tuple[str, ...]
    job_ids: tuple[str, ...]
    package_id: str
    package_label: str = ""
    graph_epoch: str = ""
    intake_mode: str = "intake_only"
    split_strategy: str = "requested_width"
    shard_economics: ShardEconomics = field(default_factory=ShardEconomics)
    observer_summary: dict[str, Any] = field(default_factory=dict)
    package_context_recorded: bool = False
    baseline_contract_present: bool = False
    schema_version: str = PACKAGE_INTAKE_SHARD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.intake_mode != "intake_only":
            raise ValueError("PackageIntakeShard is Phase 1 intake_only only")
        if not self.dll_ids and not self.dll_filenames:
            raise ValueError("PackageIntakeShard requires at least one DLL identifier")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lifecycle"] = self.lifecycle.to_dict()
        payload["shard_economics"] = self.shard_economics.to_dict()
        return payload


def build_package_intake_shards(
    package_input: Campaign | dict[str, Any],
    *,
    target_shard_width: int = 10,
    hard_split_threshold: int = 15,
    graph_epoch: str = "",
    intake_mode: str = "intake_only",
) -> dict[str, Any]:
    if intake_mode != "intake_only":
        raise ValueError("Phase 1 package intake shard runner only supports intake_only")

    payload = _normalize_package_input(package_input)
    package_id = str(payload.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("package_id must be non-empty")
    package_label = str(payload.get("package_label") or "").strip()
    effective_graph_epoch = str(graph_epoch or payload.get("graph_epoch") or "package-intake").strip()
    if not effective_graph_epoch:
        raise ValueError("graph_epoch must be non-empty")

    raw_entries = _normalize_shard_entries(payload.get("dll_entries") or [])
    package_context_recorded = "package_context" in payload
    baseline_contract_present = bool(payload.get("baseline_contract"))
    requested_width = max(1, int(target_shard_width or 1))
    threshold = max(1, int(hard_split_threshold or 1))
    effective_width = min(requested_width, threshold)
    split_strategy = "requested_width" if requested_width <= threshold else "hard_split_threshold"

    shards: list[PackageIntakeShard] = []
    for shard_ordinal, start in enumerate(range(0, len(raw_entries), effective_width)):
        shard_entries = raw_entries[start : start + effective_width]
        estimated_runtime_minutes = round(
            sum(float(entry.get("estimated_runtime_minutes") or 0.0) for entry in shard_entries),
            2,
        )
        lifecycle = DecompositionLifecycle(
            id=build_decomposition_object_id(
                "shard",
                package_id,
                graph_epoch=effective_graph_epoch,
                ordinal=shard_ordinal,
            ),
            object_type="shard",
            package_id=package_id,
            graph_epoch=effective_graph_epoch,
            source_ids=tuple(
                source_id
                for source_id in (
                    entry.get("job_id") or entry.get("dll_id") or entry.get("filename")
                    for entry in shard_entries
                )
                if source_id
            ),
            contradiction_state="none",
        )
        economics = ShardEconomics(
            target_shard_width=requested_width,
            actual_shard_width=len(shard_entries),
            target_runtime_budget_minutes=12,
            actual_runtime_minutes=estimated_runtime_minutes,
            hard_runtime_ceiling_minutes=20,
            hard_split_threshold=threshold,
            target_deep_follow_up_budget=0,
            actual_deep_follow_up_count=0,
            intake_mode=intake_mode,
            budget_breached=False,
        )
        budget_breached = economics.evaluate_budget_breached()
        observer_summary = build_shard_validity_observer(
            object_id=lifecycle.id,
            status="pass" if not budget_breached else "fail",
            capture_valid=True,
            runtime_budget_ok=economics.runtime_budget_ok,
            required_artifacts_present=True,
            hidden_variable_state_recorded=package_context_recorded or baseline_contract_present,
            reasons=(f"split_strategy={split_strategy}",),
            warnings=tuple(
                warning
                for warning in (
                    () if split_strategy == "requested_width" else ("auto_resplit_to_hard_threshold",)
                )
                + (() if economics.runtime_budget_ok else ("estimated_runtime_budget_breached",))
            ),
        )
        shards.append(
            PackageIntakeShard(
                lifecycle=lifecycle,
                shard_ordinal=shard_ordinal,
                dll_ids=tuple(entry.get("dll_id", "") for entry in shard_entries if entry.get("dll_id")),
                dll_filenames=tuple(
                    entry.get("filename", "") for entry in shard_entries if entry.get("filename")
                ),
                job_ids=tuple(entry.get("job_id", "") for entry in shard_entries if entry.get("job_id")),
                package_id=package_id,
                package_label=package_label,
                graph_epoch=effective_graph_epoch,
                intake_mode=intake_mode,
                split_strategy=split_strategy,
                shard_economics=ShardEconomics(
                    target_shard_width=economics.target_shard_width,
                    actual_shard_width=economics.actual_shard_width,
                    target_runtime_budget_minutes=economics.target_runtime_budget_minutes,
                    actual_runtime_minutes=economics.actual_runtime_minutes,
                    hard_runtime_ceiling_minutes=economics.hard_runtime_ceiling_minutes,
                    hard_split_threshold=economics.hard_split_threshold,
                    target_deep_follow_up_budget=economics.target_deep_follow_up_budget,
                    actual_deep_follow_up_count=economics.actual_deep_follow_up_count,
                    intake_mode=economics.intake_mode,
                    budget_breached=budget_breached,
                ),
                observer_summary=observer_summary,
                package_context_recorded=package_context_recorded,
                baseline_contract_present=baseline_contract_present,
            )
        )

    return {
        "schema_version": PACKAGE_INTAKE_SHARD_SCHEMA_VERSION,
        "package_id": package_id,
        "package_label": package_label,
        "graph_epoch": effective_graph_epoch,
        "intake_mode": intake_mode,
        "target_shard_width": requested_width,
        "effective_shard_width": effective_width,
        "hard_split_threshold": threshold,
        "split_strategy": split_strategy,
        "package_context_recorded": package_context_recorded,
        "baseline_contract_present": baseline_contract_present,
        "shard_count": len(shards),
        "budget_breach_count": sum(
            1 for shard in shards if shard.shard_economics.evaluate_budget_breached()
        ),
        "shards": [shard.to_dict() for shard in shards],
    }
