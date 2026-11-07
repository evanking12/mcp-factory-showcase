from __future__ import annotations

from typing import Any

from api.pipeline.core.finding_status import normalize_status


def target_scope_names(*sources: Any) -> list[str]:
    names: list[str] = []
    for source in sources:
        if source is None:
            continue
        if hasattr(source, "__dict__") and not isinstance(source, dict):
            source = vars(source)
        if not isinstance(source, dict):
            continue
        required = str(source.get("required_semantic_checkpoint") or "").strip()
        if required:
            names.append(required)
        for item in list(source.get("selected_invocable_names") or []):
            name = str(item or "").strip()
            if name:
                names.append(name)
    return list(dict.fromkeys(names))


def canonical_status_map(
    findings: list[dict[str, Any]],
    scope_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    scoped = [str(item).strip() for item in list(scope_names or []) if str(item).strip()]
    scope_set = set(scoped)
    status_map: dict[str, str] = {name: "unknown" for name in scoped}

    for row in findings:
        fn = str((row or {}).get("function") or "").strip()
        if not fn:
            continue
        if scope_set and fn not in scope_set:
            continue
        status_map[fn] = normalize_status((row or {}).get("status_canonical") or (row or {}).get("status"))

    if not scope_set:
        return status_map
    return {name: status_map.get(name, "unknown") for name in scoped}
