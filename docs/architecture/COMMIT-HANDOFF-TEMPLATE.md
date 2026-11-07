# Commit Handoff Template

Use this template for non-trivial commits in MCP Factory.

Commit messages are AI-searchable evidence packets. Future Codex runs should
be able to search commit history by signal, family, invariant, proof surface,
claim ceiling, and next action without reconstructing context from chat.

All fields should remain present. If a field does not apply, use:

- `n/a`
- `none`

## Template

```text
<area>: <verb> <signal/family/outcome>

Summary:
- ...
- ...

Why:
- ...
- ...

Campaign:
- <campaign_slug | prompt_slug | not_applicable>

Signal:
- <canonical_signal_key | blocker_key | not_applicable>

Family:
- <breakpoint/survivability/measurement/governance/product family>

Classification:
- <local_bug | family_blocker | missing_system | not_applicable>

Invariant:
- <shared property protected or improved>

Tier impact:
- <current tier -> target/held/lifted | not_applicable>

Proof surface:
- <unit | checkpoint | target-local | compiled suite | cross-suite | governance tests | none>

Proof result:
- <short result>

Suites run:
- <none | Hard03 target-local | Hard02 full | Medium02 anchor | ...>

Rerun policy:
- <why full rerun was required, skipped, or deferred>

Writeback:
- <posture/signal map/tier matrix/campaign closeout/docs/etc>

Next:
- <next campaign/proof/checkpoint | none>

Claim ceiling:
- <strongest legal claim>

Risk:
- <known residual risk>

Systems touched:
- execution_system
- reasoning_system

Contracts touched:
- ...
- ...

Prompt / workflow context:
- ...
- ...

Evidence / artifacts:
- ...
- ...

Validation:
- python scripts\verify_sync.py --tier A
- n/a

Regression posture:
- tier ...
- baseline ...
- gate run or still unproven ...
- proof surface ...
- suites run ...
- claim ceiling ...

Lane:
- 8201 -> 8090

Behavior change:
- ...
- ...

Known residual risk:
- ...
- ...

Follow-up / next checkpoint:
- ...
- ...
```

## Compressed Template

For small commits, keep the body shorter, but do not omit the searchable
minimum: `Signal:`, `Family:`, `Proof surface:`, `Claim ceiling:`, and `Next:`.

```text
<area>: <verb> <signal/family/outcome>

Campaign: <campaign_slug | not_applicable>
Signal: <canonical_signal_key | not_applicable>
Family: <family>
Classification: <local_bug | family_blocker | missing_system | not_applicable>
Invariant: <shared property>
Proof surface: <proof surface>
Proof result: <short result>
Suites run: <none | suite names>
Rerun policy: <short reason>
Writeback: <surfaces touched>
Next: <next campaign/proof | none>
Claim ceiling: <strongest legal claim>
Risk: <known residual risk>
```

## Examples

Governance-only:

```text
governance: codify searchable commit evidence packets

Campaign: commit_message_evidence_packet_contract_v1
Signal: not_applicable
Family: governance / commit history searchability
Classification: missing_system
Invariant: non-trivial commits carry searchable proof, claim ceiling, and next-step metadata
Tier impact: governance contract held
Proof surface: governance tests
Proof result: stage sticky docs pass; verify_sync PASS
Suites run: none
Rerun policy: docs/governance-only; no runtime proof
Writeback: AGENTS.md; COMMIT-HANDOFF-TEMPLATE; sticky-doc tests
Next: hard03_child_wrapper_wait_return_authority_v1
Claim ceiling: commit-message governance only
Risk: historical commits remain pre-contract and less searchable
```

Runtime/proof:

```text
hard03: classify child wrapper wait return

Campaign: hard03_child_wrapper_wait_return_authority_v1
Signal: child_wrapper_wait_return_missing
Family: measurement fabric / analyzer runtime boundedness
Classification: family_blocker
Invariant: parent/child terminalization emits wait-return, returncode, output-scan, or confirmed hang authority
Tier impact: Tier 3 held; lower signal sharpened
Proof surface: target-local
Proof result: analyzer_timeout sharpened to child_wrapper_wait_return_missing
Suites run: Hard03 reservation_stage target-local only
Rerun policy: full Hard03 deferred until seam repair
Writeback: posture updated; signal map current; tier matrix updated
Next: hard03_child_wrapper_wait_return_repair_v1
Claim ceiling: Hard03 analyzer-runtime classification only
Risk: parent wait may still race suite-level stuck timeout
```

## Notes

- Prefer canonical system names:
  - `execution_system`
  - `reasoning_system`
  - `evidence_system`
  - `operator_system`
  - `governance_system`
  - `verification_system`
- `Validation:` must list checks actually run.
- `Regression posture:` should separate implementation work from what
  non-regression proof actually exists; include proof surface, suites run, and
  claim ceiling when they govern the claim.
- `Evidence / artifacts:` should point to the most relevant docs, evals, runs,
  compare reports, or implementation-pack artifacts.
- `Behavior change:` should describe what is now different in product or
  workflow terms, not just which files changed.
- `Known residual risk:` should be blunt; it exists to accelerate review, not
  to make the change sound complete.
- `Known residual risk:` remains valid and should align with `Risk:`.
- `Follow-up / next checkpoint:` remains valid and should align with `Next:`.
