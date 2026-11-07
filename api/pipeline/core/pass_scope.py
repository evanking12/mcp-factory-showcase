from __future__ import annotations

import re
from typing import Any

from api.pipeline.core.helpers import _INIT_RE

_FOUNDATION_READ_RE = re.compile(
    r"(?:^|_)(get|read|list|query|fetch|status|state|echo|describe|inspect|peek|diagnostic)",
    re.I,
)
_SETUP_RE = re.compile(
    r"(?:^|_)(init|initialize|open|begin|setup|connect|bind|prepare|start|license|auth|load)",
    re.I,
)
_WRITE_RE = re.compile(
    r"(?:^|_)(write|set|put|update|delete|remove|free|close|commit|seal|submit|approve|cancel|sync|process)",
    re.I,
)
_ARTIFACT_RE = re.compile(
    r"(nonce|ticket|quote|report|reservation|handle|workflow|token|state|artifact)",
    re.I,
)


def normalize_pass_scope_profile(pass_index: int, pass_scope_profile: str | None) -> str:
    profile = str(pass_scope_profile or "").strip().lower()
    if profile in {"foundation", "later_pass"}:
        return profile
    return "foundation" if int(pass_index or 1) <= 1 else "later_pass"


def describe_pass_scope_bucket(
    inv: dict[str, Any],
    *,
    pass_index: int,
    pass_scope_profile: str | None,
) -> tuple[int, str]:
    profile = normalize_pass_scope_profile(pass_index, pass_scope_profile)
    if profile != "foundation":
        return (50, "later_pass_default")

    fn_name = str(inv.get("name") or "")
    fn_lower = fn_name.lower()
    prereq_count = len(list(inv.get("_required_preconditions") or []))
    sequence_role = str(inv.get("_sequence_role") or "").strip().lower()
    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    has_output_param = any(
        str(p.get("direction") or "").strip().lower() in {"out", "inout", "output"}
        or str(p.get("name") or "").lower().startswith(("pout", "out"))
        for p in params
    )

    if _INIT_RE.search(fn_name) or (_SETUP_RE.search(fn_lower) and not _WRITE_RE.search(fn_lower)):
        return (0, "foundation_setup")
    if has_output_param and not _WRITE_RE.search(fn_lower):
        return (10, "foundation_producer")
    if _FOUNDATION_READ_RE.search(fn_lower):
        return (20, "foundation_read_surface")
    if sequence_role == "state_consumer" and not _WRITE_RE.search(fn_lower):
        return (25, "foundation_state_reader")
    if _ARTIFACT_RE.search(fn_lower) and prereq_count <= 1 and not _WRITE_RE.search(fn_lower):
        return (30, "foundation_state_shape")
    if prereq_count >= 2 and sequence_role in {"lifecycle_transition", "gate"}:
        return (85, "deferred_deep_state_consumer")
    if _WRITE_RE.search(fn_lower):
        return (90, "deferred_write_or_irreversible")
    return (40, "foundation_default")
