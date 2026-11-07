"""S-01 session artifacts."""

STAGE_ARTIFACTS = {
    "write_unlock_probe.json": {
        "description": "Full write-unlock probe sequence and outcomes",
        "format": '{"outcome": "resolved|blocked|not_attempted", "unlocked": bool, ...}',
        "produced_by": "run_s01",
        "consumed_by": ["S-02 (write_unlock_block in prompts)", "S-03 MC-3"],
    },
    "winning_init_sequence.json": {
        "description": "The init sequence that activates write mode",
        "format": '{"sequence": [{"fn": "...", "args": {...}}], "write_fn_tested": "...", ...}',
        "produced_by": "run_s01 or MC-6",
        "consumed_by": ["S-01 (replay on warm start)", "S-05 verification"],
    },
    "code_reasoning_analysis.json": {
        "description": "LLM analysis of decompiled C for unlock patterns",
        "format": '{"unlock_functions": [...], "dependency_chains": [...]}',
        "produced_by": "_probe_write_unlock",
        "consumed_by": ["MC-6 (comprehensive code reasoning)"],
    },
}
