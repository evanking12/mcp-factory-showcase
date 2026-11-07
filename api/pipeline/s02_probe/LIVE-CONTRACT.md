# S-02 Live Contract

## Guarantees Today

- Runs three runtime-visible probe boundaries while preserving `s02_probe` as
  the compatibility parent:
  - `s02_probe_ordering`
  - `s02_invocation_execution`
  - `s02_evidence_capture`
- Probes selected functions with accumulated setup, vocab, sentinel, and unlock context.
- Emits probe logs that later stages can inspect without relying on chat memory.
- Preserves the distinction between observed calls and inferred semantics.

## Semantic Obligation

S-02 must produce concrete runtime observations from real calls. It can expose
behavior evidence and working-call candidates, but it must not synthesize final
semantic truth by itself.

## Handoff Rule

S-02 hands off runtime observations and working-call candidates. It must not
claim synthesis-level semantic truth by itself.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Probe logs and findings exist for attempted functions. |
| Stay | Required context or executor readiness is too weak to produce useful observations. |
| Fail | Runtime probing cannot execute or probe evidence cannot be persisted. |

## Compatibility Notes

S-02 still receives legacy context through `ExploreContext`; packetized upstream
input is currently introduced at the S-00 to S-01 seam only. `s02_probe`
remains the compatibility parent for full-stage checkpoint/resume behavior.
The split checkpoints add attribution only and do not remove legacy artifact
paths.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-02 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
