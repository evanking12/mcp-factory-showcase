"""S-03 session artifacts."""

STAGE_ARTIFACTS = {
    "mc-decisions/mc3-post-reconcile.json": {
        "description": "MC-3 write failure analysis decision",
        "format": '[{"trigger": "...", "analysis": {...}, "action": "...", "result": "..."}]',
        "produced_by": "_mc3_post_reconcile",
        "consumed_by": ["MC-6 (prior MC decisions as context)", "session-snapshot"],
    },
    "sentinel_catalog.json": {
        "description": "Promoted sentinel evidence catalog",
        "format": '{"codes": {...}, "promoted_count": N, "total_counts": N}',
        "produced_by": "_run_phase_5_sentinel_catalog",
        "consumed_by": ["session-snapshot"],
    },
}
