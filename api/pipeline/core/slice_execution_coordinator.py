from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SLICE_EXECUTION_COORDINATOR_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class SliceExecutionObserverResult:
    observer_name: str
    execution_unit_id: str
    status: str
    serialized_lane_safe: bool
    slice_attribution_preserved: bool
    bounded_execution_unit: bool
    live_parallelism_enabled: bool
    warnings: tuple[str, ...] = ()
    schema_version: str = SLICE_EXECUTION_COORDINATOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if str(self.observer_name or "").strip() != "slice_execution_coordination":
            raise ValueError("observer_name must be slice_execution_coordination")
        normalized_status = str(self.status or "").strip().lower()
        if normalized_status not in {"pass", "warn", "fail"}:
            raise ValueError("observer status must be pass, warn, or fail")
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(
            self,
            "warnings",
            tuple(str(warning or "").strip() for warning in tuple(self.warnings or ()) if str(warning or "").strip()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_slice_execution_map(
    frontier_slice_plan: dict[str, Any],
    *,
    base_lane_id: str = "slice-lane-0",
    allow_live_parallelism: bool = False,
) -> dict[str, Any]:
    if allow_live_parallelism:
        raise ValueError("Prompt 07 does not permit unsafe live parallelism")

    package_id = str(frontier_slice_plan.get("package_id") or "").strip()
    graph_epoch = str(frontier_slice_plan.get("graph_epoch") or "").strip()
    slices = [
        dict(row)
        for row in list(frontier_slice_plan.get("frontier_slices") or [])
        if isinstance(row, dict)
    ]

    execution_units: list[dict[str, Any]] = []
    observers: list[dict[str, Any]] = []

    for slice_ordinal, slice_row in enumerate(slices):
        lifecycle = dict(slice_row.get("lifecycle") or {})
        slice_id = str(lifecycle.get("id") or slice_row.get("slice_id") or "").strip()
        active_dlls = tuple(
            str(name or "").strip()
            for name in list(slice_row.get("active_dlls") or [])
            if str(name or "").strip()
        )
        required_cluster_ids = tuple(
            str(name or "").strip()
            for name in list(slice_row.get("required_cluster_ids") or [])
            if str(name or "").strip()
        )
        required_initialization_group_ids = tuple(
            str(name or "").strip()
            for name in list(slice_row.get("required_initialization_group_ids") or [])
            if str(name or "").strip()
        )
        related_dependency_class_ids = tuple(
            str(name or "").strip()
            for name in list(slice_row.get("related_dependency_class_ids") or [])
            if str(name or "").strip()
        )
        protected_imported_truth_ids = tuple(
            str(name or "").strip()
            for name in list(slice_row.get("imported_lower_floor_dlls") or [])
            if str(name or "").strip()
        )

        for dll_ordinal, dll_name in enumerate(active_dlls):
            execution_unit_id = f"slice_exec::{slice_id}::{dll_ordinal}"
            warnings: list[str] = []
            bounded_execution_unit = bool(dll_name and slice_id and len(active_dlls) > 0)
            if len(active_dlls) > 1:
                warnings.append("multi_dll_slice_serialized")
            observer = SliceExecutionObserverResult(
                observer_name="slice_execution_coordination",
                execution_unit_id=execution_unit_id,
                status="pass" if bounded_execution_unit else "fail",
                serialized_lane_safe=True,
                slice_attribution_preserved=bool(slice_id),
                bounded_execution_unit=bounded_execution_unit,
                live_parallelism_enabled=False,
                warnings=tuple(warnings),
            ).to_dict()
            observers.append(observer)
            execution_units.append(
                {
                    "execution_unit_id": execution_unit_id,
                    "package_id": package_id,
                    "graph_epoch": graph_epoch,
                    "source_frontier_slice_id": slice_id,
                    "slice_label": str(slice_row.get("label") or slice_id).strip(),
                    "target_dll": dll_name,
                    "sequence_index": len(execution_units),
                    "lane_id": base_lane_id,
                    "serialized_lane_safe": True,
                    "parallel_intake_compatible": True,
                    "live_parallelism_enabled": False,
                    "required_cluster_ids": required_cluster_ids,
                    "required_initialization_group_ids": required_initialization_group_ids,
                    "related_dependency_class_ids": related_dependency_class_ids,
                    "protected_imported_truth_ids": protected_imported_truth_ids,
                    "interwoven_subject_ids": tuple(
                        str(name or "").strip()
                        for name in list(slice_row.get("interwoven_subject_ids") or [])
                        if str(name or "").strip()
                    ),
                    "interwoven_contradiction_summary": dict(slice_row.get("interwoven_contradiction_summary") or {}),
                    "interwoven_attribution_present": bool(slice_row.get("interwoven_attribution_present")),
                    "runtime_overrides": {
                        "lane_id": base_lane_id,
                        "variant_id": f"{slice_ordinal}:{dll_ordinal}",
                        "iteration_mode": "floor_to_ceiling",
                        "floor_scope": "package",
                        "prerequisite_state_group_ids": list(required_initialization_group_ids),
                        "interwoven_subject_ids": list(slice_row.get("interwoven_subject_ids") or []),
                        "interwoven_contradiction_summary": dict(
                            slice_row.get("interwoven_contradiction_summary") or {}
                        ),
                        "interwoven_attribution_present": bool(slice_row.get("interwoven_attribution_present")),
                    },
                    "observer_summary": observer,
                    "schema_version": SLICE_EXECUTION_COORDINATOR_SCHEMA_VERSION,
                }
            )

    return {
        "schema_version": SLICE_EXECUTION_COORDINATOR_SCHEMA_VERSION,
        "coordinator_type": "slice_execution",
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "base_lane_id": base_lane_id,
        "live_parallelism_enabled": False,
        "execution_units": execution_units,
        "execution_unit_count": len(execution_units),
        "coordinator_observer_summaries": observers,
    }
