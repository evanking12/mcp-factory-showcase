"""S-02 checkpoint hooks.

READS:
  - Per-function entries: {fn_name: {status, working_call, ...}}
  - Functions with status="success" + working_call are SKIPPED (focus_functions)
  - already_explored: set of function names from prior findings

WRITES:
  - Per-function entries after probing completes
  - Updated sentinels (stage-boundary recalibration may discover new codes)
  - Updated unlock_result (stage-boundary re-probe may crack write-unlock)

STAGE GATE:
  is_stage_complete("s02_probe") -> legacy compatibility parent for full S-02
  is_stage_complete("s02_probe_ordering") -> skip S-02A ordering
  is_stage_complete("s02_invocation_execution") -> skip S-02B invocation execution
  is_stage_complete("s02_evidence_capture") -> skip S-02C evidence capture
  Per-function: should_skip_function(checkpoint, fn_name) -> skip individual function
"""
CHECKPOINT_STAGE_NAME = "s02_probe"
CHECKPOINT_SUBSTAGE_NAMES = [
    "s02_probe_ordering",
    "s02_invocation_execution",
    "s02_evidence_capture",
]

READS_FROM_CHECKPOINT = [
    "per_function_entries",
    "already_explored",
]

WRITES_TO_CHECKPOINT = [
    "per_function_entries",
    "sentinels",
    "unlock_result",
]

STAGE_COMPLETE_METADATA = {}
