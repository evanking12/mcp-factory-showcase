"""S-06 checkpoint hooks.

READS:
  - All accumulated context from S-00 through S-05

WRITES:
  - Gap resolution outcomes per function
  - MC-6 decisions
  - winning_init_sequence: updated if MC-6 discovers new sequence
  - write_unlock_block: updated if MC-6 cracks write-unlock

STAGE GATE:
  is_stage_complete("s06_gaps") -> skip gap resolution + MC-6
"""
CHECKPOINT_STAGE_NAME = "s06_gaps"

READS_FROM_CHECKPOINT = [
    "all_prior_context",
]

WRITES_TO_CHECKPOINT = [
    "gap_resolution_outcomes",
    "mc6_decisions",
    "winning_init_sequence",
    "write_unlock_block",
]

STAGE_COMPLETE_METADATA = {}
