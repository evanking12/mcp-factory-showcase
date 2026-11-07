from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DESIGN_SUITE_SUCCESSOR_BRANCH_DECISION_ARTIFACT = "design-suite-successor-branch-decision.json"


def build_successor_suite_branch_decision(
    readiness: Mapping[str, Any],
    *,
    suite_id: str,
    suite_name: str,
    real_campaign_runtime_reusable: bool,
    remaining_real_campaign_glue: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    readiness_payload = dict(readiness or {})
    readiness_green = bool(readiness_payload.get("ready_for_first_bounded_campaign"))
    glue = sorted({str(item or "").strip() for item in tuple(remaining_real_campaign_glue or ()) if str(item or "").strip()})
    compare_ready = False
    promotion_ready = False

    blocking_reasons: list[str] = []
    if not readiness_green:
        blocking_reasons.append("successor_suite_local_readiness_not_green")
    if not real_campaign_runtime_reusable:
        blocking_reasons.append("real_campaign_runtime_still_suite_specific")

    if not readiness_green:
        recommended_next_branch = "narrower repair prompt"
        why_now = (
            "The successor suite is not yet locally ready, so spending effort on "
            "real campaign admission or seam genericization would be premature."
        )
    elif not real_campaign_runtime_reusable:
        recommended_next_branch = "generic design-suite campaign seam tightening"
        why_now = (
            "Atlas is locally ready, but the real campaign path is still carried "
            "by Northstar-specific runner ownership. Genericizing that seam is the "
            "stronger blocker than admitting Atlas through another suite-specific wrapper."
        )
    else:
        recommended_next_branch = "successor real bounded campaign gate"
        why_now = (
            "The successor suite is locally ready and the real campaign seam is "
            "generic enough that a bounded Atlas campaign is now the strongest next proof."
        )

    return {
        "artifact_type": DESIGN_SUITE_SUCCESSOR_BRANCH_DECISION_ARTIFACT,
        "schema_version": "1.0.0",
        "suite_id": suite_id,
        "suite_name": suite_name,
        "local_campaign_ready": readiness_green,
        "real_campaign_runtime_reusable": real_campaign_runtime_reusable,
        "remaining_real_campaign_glue": glue,
        "compare_ready": compare_ready,
        "promotion_ready": promotion_ready,
        "recommended_next_branch": recommended_next_branch,
        "why_now": why_now,
        "blocking_reasons": blocking_reasons,
    }


def write_successor_suite_branch_decision(output_dir: str | Path, payload: Mapping[str, Any]) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / DESIGN_SUITE_SUCCESSOR_BRANCH_DECISION_ARTIFACT
    destination.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
    return destination
