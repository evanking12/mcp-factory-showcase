from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.decomposition_contract import (
    DECOMPOSITION_CONTRACT_SCHEMA_VERSION,
    DEFAULT_DECOMPOSITION_RETENTION_POLICY,
)


SHARD_INVENTORY_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class ShardConfidencePlaceholder:
    status: str = "bounded_placeholder"
    score: float = 0.0
    reason: str = "intake_inventory_only"

    def __post_init__(self) -> None:
        normalized_status = str(self.status or "").strip().lower()
        if normalized_status not in {"bounded_placeholder", "tentative", "high_confidence"}:
            raise ValueError("unsupported shard confidence placeholder status")
        if self.score < 0:
            raise ValueError("confidence score must be non-negative")
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "reason", str(self.reason or "").strip() or "intake_inventory_only")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShardInventoryArtifact:
    shard_id: str
    package_id: str
    graph_epoch: str
    dll_entries: tuple[dict[str, Any], ...]
    dll_count: int
    intake_mode: str
    observer_summary_id: str
    contradiction_summary_id: str
    confidence_placeholder: ShardConfidencePlaceholder
    retention_class: str = "canonical"
    schema_version: str = SHARD_INVENTORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.shard_id or "").strip():
            raise ValueError("shard_id must be non-empty")
        if not str(self.package_id or "").strip():
            raise ValueError("package_id must be non-empty")
        if self.dll_count < 0:
            raise ValueError("dll_count must be non-negative")
        if str(self.intake_mode or "").strip() != "intake_only":
            raise ValueError("ShardInventoryArtifact only supports intake_only mode in Prompt 02")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence_placeholder"] = self.confidence_placeholder.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ShardInventoryArtifact":
        dll_entries = payload.get("dll_entries")
        if dll_entries is None:
            dll_entries = payload.get("dlls") or []
        confidence_payload = dict(payload.get("confidence_placeholder") or {})
        return cls(
            shard_id=payload.get("shard_id", ""),
            package_id=payload.get("package_id", ""),
            graph_epoch=payload.get("graph_epoch", ""),
            dll_entries=tuple(dll_entries or ()),
            dll_count=int(payload.get("dll_count") or len(dll_entries or [])),
            intake_mode=payload.get("intake_mode", "intake_only"),
            observer_summary_id=payload.get("observer_summary_id", ""),
            contradiction_summary_id=payload.get("contradiction_summary_id", ""),
            confidence_placeholder=ShardConfidencePlaceholder(
                status=confidence_payload.get("status", "bounded_placeholder"),
                score=float(confidence_payload.get("score", 0.0) or 0.0),
                reason=confidence_payload.get("reason", "intake_inventory_only"),
            ),
            retention_class=payload.get("retention_class", "canonical"),
            schema_version=payload.get("schema_version", SHARD_INVENTORY_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class ShardContradictionSummary:
    shard_id: str
    contradiction_state: str = "none"
    contradiction_count: int = 0
    contradictions: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    retention_class: str = "canonical"
    schema_version: str = SHARD_INVENTORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.shard_id or "").strip():
            raise ValueError("shard_id must be non-empty")
        if self.contradiction_count < 0:
            raise ValueError("contradiction_count must be non-negative")
        object.__setattr__(self, "contradiction_state", str(self.contradiction_state or "").strip() or "none")
        object.__setattr__(
            self,
            "warnings",
            tuple(str(warning or "").strip() for warning in tuple(self.warnings or ()) if str(warning or "").strip()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ShardContradictionSummary":
        contradictions = payload.get("contradictions")
        if contradictions is None:
            contradictions = payload.get("items") or []
        return cls(
            shard_id=payload.get("shard_id", ""),
            contradiction_state=payload.get("contradiction_state", "none"),
            contradiction_count=int(payload.get("contradiction_count") or len(contradictions or [])),
            contradictions=tuple(contradictions or ()),
            warnings=tuple(payload.get("warnings") or ()),
            retention_class=payload.get("retention_class", "canonical"),
            schema_version=payload.get("schema_version", SHARD_INVENTORY_SCHEMA_VERSION),
        )


def emit_shard_inventory_artifacts(shard_plan: dict[str, Any]) -> dict[str, Any]:
    shards = list(shard_plan.get("shards") or [])
    inventory_rows: list[dict[str, Any]] = []
    contradiction_rows: list[dict[str, Any]] = []
    observer_rows: list[dict[str, Any]] = []

    for shard in shards:
        if not isinstance(shard, dict):
            continue
        lifecycle = dict(shard.get("lifecycle") or {})
        shard_id = str(lifecycle.get("id") or "").strip()
        package_id = str(shard.get("package_id") or shard_plan.get("package_id") or "").strip()
        graph_epoch = str(shard.get("graph_epoch") or shard_plan.get("graph_epoch") or "").strip()
        dll_ids = list(shard.get("dll_ids") or [])
        dll_filenames = list(shard.get("dll_filenames") or [])
        job_ids = list(shard.get("job_ids") or [])
        dll_entries = tuple(
            {
                "dll_id": str(dll_ids[index] if index < len(dll_ids) else "").strip(),
                "filename": str(dll_filenames[index] if index < len(dll_filenames) else "").strip(),
                "job_id": str(job_ids[index] if index < len(job_ids) else "").strip(),
            }
            for index in range(max(len(dll_ids), len(dll_filenames), len(job_ids)))
            if any(
                str(value or "").strip()
                for value in (
                    dll_ids[index] if index < len(dll_ids) else "",
                    dll_filenames[index] if index < len(dll_filenames) else "",
                    job_ids[index] if index < len(job_ids) else "",
                )
            )
        )
        observer_summary_id = f"{shard_id}::observer"
        contradiction_summary_id = f"{shard_id}::contradictions"
        inventory_rows.append(
            ShardInventoryArtifact(
                shard_id=shard_id,
                package_id=package_id,
                graph_epoch=graph_epoch,
                dll_entries=dll_entries,
                dll_count=int(shard.get("shard_economics", {}).get("actual_shard_width") or len(dll_entries)),
                intake_mode=str(shard.get("intake_mode") or "intake_only"),
                observer_summary_id=observer_summary_id,
                contradiction_summary_id=contradiction_summary_id,
                confidence_placeholder=ShardConfidencePlaceholder(),
                retention_class=DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("shard_summary"),
            ).to_dict()
        )
        contradiction_rows.append(
            ShardContradictionSummary(
                shard_id=shard_id,
                contradiction_state=str(lifecycle.get("contradiction_state") or "none"),
                contradiction_count=0,
                contradictions=(),
                warnings=(),
                retention_class=DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("shard_summary"),
            ).to_dict()
        )
        observer = dict(shard.get("observer_summary") or {})
        observer["observer_summary_id"] = observer_summary_id
        observer["schema_version"] = DECOMPOSITION_CONTRACT_SCHEMA_VERSION
        observer_rows.append(observer)

    return {
        "schema_version": SHARD_INVENTORY_SCHEMA_VERSION,
        "package_id": str(shard_plan.get("package_id") or "").strip(),
        "graph_epoch": str(shard_plan.get("graph_epoch") or "").strip(),
        "shard_inventory_artifacts": inventory_rows,
        "shard_contradiction_summaries": contradiction_rows,
        "shard_observer_summaries": observer_rows,
    }
