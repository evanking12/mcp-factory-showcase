"""S-04 checkpoint hooks.

READS:
  - All findings from prior stages

WRITES:
  - api_reference.md hash (for cache invalidation)
  - synthesis_complete flag

STAGE GATE:
  is_stage_complete("s04_synthesis") -> skip synthesis (reuse cached api_reference.md)
  Only invalidated if findings changed since checkpoint.
"""
CHECKPOINT_STAGE_NAME = "s04_synthesis"

READS_FROM_CHECKPOINT = [
    "findings",
]

WRITES_TO_CHECKPOINT = [
    "synthesis_complete",
]

STAGE_COMPLETE_METADATA = {}
