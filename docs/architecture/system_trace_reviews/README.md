# System Trace Reviews

This directory holds durable end-to-end trace reviews for bounded systems.

Each review should answer:

- what system was traced
- what broader goal it serves
- what code path and artifact path were expected
- what statuses or checkpoints should move
- what operator surfaces should reflect the system
- what tests cover the path
- what mismatches, missing links, or overclaims remain
- whether the strongest result is a:
  - `local_bug`
  - `family_blocker`
  - `missing_system`

Use one review artifact per traced system so the GM and future specialist roles
can compare traces over time without reconstructing them from chat memory.
