"""S-02 session artifacts."""

STAGE_ARTIFACTS = {
    "prerequisite_state_machine.json": {
        "description": "S-02A probe-ordering plan with prerequisite roles, edges, and execution layers",
        "format": '{"roles": [...], "edges": [...], "layers": [...]}',
        "produced_by": "_run_phase_2_curriculum_order",
        "consumed_by": ["S-02B invocation execution", "config frontier audit", "session-snapshot"],
    },
    "explore_probe_log.json": {
        "description": "Per-call trace of every DLL invocation during probing",
        "format": '[{"function": "...", "args": {...}, "result_excerpt": "...", "classification": {...}}, ...]',
        "produced_by": "_explore_one / _run_phase_3_probe_loop / S-02B invocation execution",
        "consumed_by": ["S-03 reconciliation", "S-07 harmonization", "session-snapshot"],
    },
    "explore_config.json": {
        "description": "Cap profile and runtime settings used for this run",
        "format": '{"mode": "...", "cap_profile": "...", "max_rounds_per_function": N, ...}',
        "produced_by": "_explore_worker",
        "consumed_by": ["session-snapshot (metadata)"],
    },
    "mcp_schema_t0.json": {
        "description": "Pre-enrichment schema snapshot (baseline for diffing)",
        "format": "Full MCP schema JSON",
        "produced_by": "_explore_worker",
        "consumed_by": ["session-snapshot (before/after comparison)"],
    },
}

FUTURE_RUNTIME_ALIASES = {
    "evidence/stage-02a-probe-ordering/prerequisite-state-machine.json": "prerequisite_state_machine.json",
    "evidence/stage-02b-invocation-execution/stage-context.txt": "model_context_phase_01_probe_loop.txt",
    "evidence/stage-02b-invocation-execution/probe-user-message-sample.txt": "probe_user_message_sample.txt",
    "evidence/stage-02c-evidence-capture/probe-log.json": "explore_probe_log.json",
    "evidence/stage-02c-evidence-capture/findings.json": "findings.json",
}
