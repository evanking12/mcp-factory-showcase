"""S-07 checkpoint hooks.

READS:
  - Final findings after all resolution phases
  - vocab for description synthesis

WRITES:
  - behavioral_spec.py present flag
  - harmonization_complete flag
  - This is the TERMINAL checkpoint -- pipeline is fully complete.

STAGE GATE:
  is_stage_complete("s07_finalize") -> pipeline already completed for this checkpoint
"""
CHECKPOINT_STAGE_NAME = "s07_finalize"

READS_FROM_CHECKPOINT = [
    "findings",
    "vocab",
]

WRITES_TO_CHECKPOINT = [
    "behavioral_spec_present",
    "harmonization_complete",
]

STAGE_COMPLETE_METADATA = {}
