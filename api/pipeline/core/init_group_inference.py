from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


INIT_GROUP_INFERENCE_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class InitializationGroupObserverResult:
    observer_name: str
    object_id: str
    status: str
    exported_state_explicit: bool
    downstream_consumers_explicit: bool
    bounded_group: bool
    contradiction_state: str
    warnings: tuple[str, ...] = ()
    schema_version: str = INIT_GROUP_INFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if str(self.observer_name or "").strip() != "initialization_group_plausibility":
            raise ValueError("observer_name must be initialization_group_plausibility")
        normalized_status = str(self.status or "").strip().lower()
        if normalized_status not in {"pass", "warn", "fail"}:
            raise ValueError("observer status must be pass, warn, or fail")
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "contradiction_state", str(self.contradiction_state or "").strip() or "none")
        object.__setattr__(
            self,
            "warnings",
            tuple(str(warning or "").strip() for warning in tuple(self.warnings or ()) if str(warning or "").strip()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_initialization_groups(
    merge_output: dict[str, Any],
    *,
    max_member_dlls: int = 4,
) -> dict[str, Any]:
    package_id = str(merge_output.get("package_id") or "").strip()
    graph_epoch = str(merge_output.get("graph_epoch") or "").strip()
    rows = [
        dict(row)
        for row in list(merge_output.get("candidate_initialization_groups") or [])
        if isinstance(row, dict)
    ]
    artifacts: list[dict[str, Any]] = []
    observers: list[dict[str, Any]] = []
    oversized_group_count = 0
    cross_dll_group_count = 0

    for row in rows:
        lifecycle = dict(row.get("lifecycle") or {})
        details = dict(row.get("details") or {})
        member_dlls = tuple(
            str(member or "").strip()
            for member in list(row.get("member_dlls") or [])
            if str(member or "").strip()
        )
        if len(member_dlls) > 1:
            cross_dll_group_count += 1
        bounded_group = 0 < len(member_dlls) <= max_member_dlls
        if not bounded_group:
            oversized_group_count += 1
        exported_state_artifacts = tuple(
            str(member or "").strip()
            for member in list(details.get("exported_state_artifacts") or [])
            if str(member or "").strip()
        )
        likely_downstream_consumers = tuple(
            str(member or "").strip()
            for member in list(details.get("likely_downstream_consumers") or [])
            if str(member or "").strip()
        )
        contradiction_state = str(lifecycle.get("contradiction_state") or "none").strip() or "none"
        status = "pass"
        warnings: list[str] = []
        if contradiction_state in {"contradicted", "blocked"}:
            status = "fail"
            warnings.append("contradiction_state_blocks_group")
        elif not bounded_group:
            status = "fail"
            warnings.append("oversized_group")
        elif not exported_state_artifacts or not likely_downstream_consumers:
            status = "warn"
            warnings.append("incomplete_init_group_evidence")
        observer = InitializationGroupObserverResult(
            observer_name="initialization_group_plausibility",
            object_id=str(lifecycle.get("id") or "").strip(),
            status=status,
            exported_state_explicit=bool(exported_state_artifacts),
            downstream_consumers_explicit=bool(likely_downstream_consumers),
            bounded_group=bounded_group,
            contradiction_state=contradiction_state,
            warnings=tuple(warnings),
        ).to_dict()
        observers.append(observer)
        artifact = {
            "group_id": str(lifecycle.get("id") or "").strip(),
            "package_id": package_id,
            "graph_epoch": graph_epoch,
            "member_functions": tuple(
                str(member or "").strip()
                for member in list(details.get("member_functions") or [])
                if str(member or "").strip()
            ),
            "member_dlls": member_dlls,
            "exported_state_artifacts": exported_state_artifacts,
            "likely_downstream_consumers": likely_downstream_consumers,
            "confidence": row.get("confidence_score", 0.0),
            "contradiction_state": contradiction_state if bounded_group else "blocked",
            "observer_summary": observer,
            "schema_version": INIT_GROUP_INFERENCE_SCHEMA_VERSION,
        }
        artifacts.append(artifact)

    return {
        "schema_version": INIT_GROUP_INFERENCE_SCHEMA_VERSION,
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "initialization_groups": artifacts,
        "init_group_observer_summaries": observers,
        "cross_dll_group_count": cross_dll_group_count,
        "oversized_group_count": oversized_group_count,
    }
