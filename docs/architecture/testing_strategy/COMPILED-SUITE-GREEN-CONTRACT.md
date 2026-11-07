# Compiled Suite Green Contract

## Purpose

This contract prevents compiled-suite `green` language from overstating what a
run proved.

The product route for compiled enterprise suites is:

```text
compiled/no-source input -> Ghidra-backed analysis -> durable discovery evidence -> semantic/product result
```

Historical green runs remain useful, but they must be labeled by the strongest
contract they actually satisfied. A `Medium01` or hard-family run name is a
pressure descriptor, not a proof-quality label.

## Benchmark Question

When a compiled suite reports success, can the repo say exactly whether that
success was compatibility, measurement, route, semantic, or product green?

## Green Levels

| Level | Meaning | Minimum proof | Claim ceiling |
| --- | --- | --- | --- |
| `compatibility_green` | The runner/regression path worked under its historical contract. | suite completed its configured checks without violating its stated contract | regression compatibility only |
| `measurement_green` | The measurement fabric closed honestly. | comparable successes and durable non-comparable packets are preserved with dependency policy | measurement diagnosability only |
| `route_green` | The intended analysis route was entered and proved. | required route authority exists, such as Ghidra-backed authority for compiled enterprise suites | route authority only |
| `semantic_green` | Stage or checkpoint semantics passed with decision-bearing evidence. | semantic proof is satisfied by comparable, decision-bearing evidence | semantic suite scope only |
| `product_green` | The compiled/no-source product route succeeded. | Ghidra-backed route authority, durable discovery output, and semantic/product evidence all exist | compiled enterprise product route only |

## Fixture Shape

- `compatibility_green` fixtures may use historical runner contracts and do not
  imply Ghidra-backed product proof.
- `measurement_green` fixtures may include non-comparable targets if the run
  closes with durable authority packets and honest dependency blocking.
- `route_green` compiled enterprise fixtures must prove the intended analyzer
  route was entered. PE-only structural metadata is preflight evidence, not
  product discovery proof.
- `product_green` fixtures must start from compiled/no-source inputs and
  produce Ghidra-backed discovery plus decision-bearing semantic/product output.

## Required Outputs

Compiled-suite summaries, baseline docs, and campaign closeouts must preserve:

- `green_contract_level`
- route authority evidence, when claimed
- `safe_to_compare`
- `semantic_proof_satisfied`
- `authoritative_proving`
- decision-bearing status
- claim ceiling
- evidence paths

These fields are governed by the Decision-Bearing Provenance Principle in
`AGENTS.md`: product-relevant choices must be emitted as structured evidence
that downstream stages can depend on, and missing authority must fail closed
with a canonical blocker.

If a current artifact cannot emit `green_contract_level` yet, its docs must
state the implied level explicitly and must not call it product green.

## Acceptance Criteria

- A compiled enterprise suite cannot be `product_green` without Ghidra-backed
  route authority.
- PE-only discovery or legacy structural metadata cannot satisfy route-green or
  product-green claims for compiled enterprise suites that require Ghidra.
- Yellow, red, quarantined, or non-comparable records cannot satisfy semantic
  green or product green.
- Historical `Medium01` green evidence is preserved as compatibility or
  regression green unless the run also proves Ghidra-backed route authority.
- Hard-family classification evidence remains baseline data until semantic or
  product green is separately proven.

## Constraints

- This contract does not change suite scheduling, fixtures, bridge behavior,
  Ghidra behavior, or stage semantics by itself.
- This contract does not delete historical baselines.
- This contract does not promote hard02 or any stage tier.
- This contract exists because green label drift is a governance failure even
  when the underlying instrumentation work is useful.

## Runner Boundary

For compiled enterprise proving, the runner is allowed to be a proof harness
but not a product brain.

Allowed harness duties:

- target ordering and dependency policy
- bounded budgets and stop-after-first-failure behavior
- artifact collection and durable fail-closed closeout
- comparability, authority, and blocking-signal reporting

Disallowed duties:

- hidden binary knowledge or fixture-only hints
- route bypasses the real product path would not receive
- converting missing route or product evidence into success by interpretation
- analysis work that belongs inside API, bridge, Ghidra, or discovery runtime

If a compiled-suite proof depends on runner-only intelligence that the real
compiled/no-source product route would not have, the run may still be useful as
compatibility or measurement evidence but it cannot support `route_green` or
`product_green`.

## Assumptions And Defaults

- Compiled enterprise product proof requires Ghidra-backed evidence unless a
  future architecture decision explicitly changes that route.
- `strict_dll` may remain compiled-first while still requiring Ghidra-backed
  comparable discovery for product-green claims.
- Medium/hard names describe fixture pressure and suite size. They do not
  determine green level.

## Current Truth Sources

This document defines green levels and claim ceilings. It does not own mutable
baseline, gate, anchor, or active-blocker truth.

Current product proving truth is contract-backed:

| Current fact | Authoritative source |
| --- | --- |
| Active defended product baselines | `configs/regression/baseline_registry.json` |
| Product gate suite membership and required product-green fields | `configs/regression/gate_v1.json` |
| Local proving anchor, active pressure target, active blocker signal, and required external check name | `configs/regression/product_proving_posture.json` |
| Canonical hard-family signal keys | `docs/architecture/testing_strategy/HARD-FAMILY-FAILURE-SIGNAL-MAP.md` |

## Questions This Suite Can Answer

- What kind of green did a compiled-suite run actually earn?
- Did the run prove Ghidra-backed route authority or only compatibility?
- Can a historical baseline be preserved without overstating product proof?
- Which evidence fields are mandatory before product-green language is legal?

## Questions This Suite Cannot Answer

- It cannot make Ghidra or the bridge work.
- It cannot prove hard02 or broader hard-family product maturity.
- It cannot prove S-00 through S-07 stage tiers.
- It cannot replace a live compiled/no-source product-route proof.

## Historical Notes

Historical compatibility baselines remain useful, but they are not the active
product-green source once a surface is promoted in `baseline_registry.json`.

Campaign prose may explain how a baseline was earned. It must not become the
source of truth for whether that baseline is currently active.
