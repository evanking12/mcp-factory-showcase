# S-07 Live Contract

## Guarantees Today

- Runs final harmonization and behavioral spec generation where possible.
- Emits or refreshes final vocab/description and contract artifacts where available.
- Sets closure state based on remaining clarification questions and run status.
- Treats component-description synthesis as optional: S-07 uses deterministic
  description text by default, and opt-in model synthesis must fail closed
  without blocking final close.
- Treats contract artifact emission as asynchronous best-effort: S-07 records
  `s07_emit_contract_artifacts`, but slow supplemental contract emission must
  not block terminal worker verdict persistence.
- Treats macro-verdict evaluation and persistence as bounded close-path work:
  the worker records `s07_macro_verdict_evaluate` and
  `s07_macro_verdict_persist`, and a slow macro verdict must degrade to an
  explicit fallback rather than freeze terminal close.
- Treats worker-close progress breadcrumbs as nonblocking diagnostics. Final
  terminal status persistence remains synchronous, but intermediate close
  status messages must not block the worker close path.

## Semantic Obligation

S-07 must produce coherent operator-facing closure over the evidence produced so
far. It reports trusted, inferred, open, and unsupported surfaces; it does not
make missing upstream proof true.

## Handoff Rule

S-07 hands off operator-facing closure: what is trusted, what remains open, and
what artifacts support that conclusion.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Final artifacts or final status surfaces are emitted, or supplemental contract artifacts / macro-verdict persistence are deferred while worker close continues. |
| Stay | Required prior-stage outputs are missing and closure would be misleading. |
| Fail | Finalization cannot persist final status, corrupts contract artifacts, or hides close-path timeout evidence. |

## Compatibility Notes

Finalization is not proof that every function is semantically known. It is the
run closure surface over the evidence produced so far.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-07 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
