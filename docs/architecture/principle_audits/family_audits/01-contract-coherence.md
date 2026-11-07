# Principle Family Audit: `contract_coherence`

- strongest_principle: `CC-04 system minimization before expansion`
- weakest_principle: `CC-02 explicit overlap resolution`
- recurring_failure_pattern: `the repo defines coherent surfaces, but overlap retirement and operator-meaning separation are not enforced tightly enough before new surfaces accrete`
- count_of_escalations: `1`

## `CC-01`: `contract-first coherence`

- principle_id: `CC-01`
- principle_name: `contract-first coherence`
- score_1_to_10: `8`
- why: `The repo states the goal explicitly in AGENTS.md ("keep contract-first coherence intact"), and the architecture guide reinforces contract-bearing, bounded changes, explicit evaluation, and self-review. The doctrine is consistent across governance surfaces, task registry, and architecture docs, so the principle is real and repeated rather than incidental.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/ARCHITECT-OPERATING-GUIDE.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `codex/tasks/governance_inventory.json`
- evidence_missing:
  - `No single enforcement surface mechanically checks contract-first alignment across every new task, prompt, and architecture artifact.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/ARCHITECT-OPERATING-GUIDE.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `codex/tasks/governance_inventory.json`
- main_failure_mode: `Coherence is well stated, but enforcement is distributed across human-readable guidance rather than centralized into one hard gate, so drift can still happen between doctrine and execution.`
- recommended_tightening: `Add a small contract-coherence checklist or validation step to canonical prompt/task surfaces so new systems must explicitly state scope, replacement behavior, and review-surface ownership before they are treated as execution-ready.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `CC-02`: `explicit overlap resolution`

- principle_id: `CC-02`
- principle_name: `explicit overlap resolution`
- score_1_to_10: `6`
- why: `This principle exists in the docs and is stated clearly, but the repo still accumulates overlapping campaign, review, and governance surfaces faster than the overlap state is retired or narrowed.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/ARCHITECT-OPERATING-GUIDE.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `codex/tasks/governance_inventory.json`
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
- evidence_missing:
  - `No canonical overlap registry records, per overlapping surface, whether the older surface is kept, narrowed, superseded, or retired after a gate.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/ARCHITECT-OPERATING-GUIDE.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `codex/tasks/governance_inventory.json`
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
- main_failure_mode: `Two or more surfaces continue to carry the same operator meaning until a later review or closeout explains the difference, which forces prompt archaeology instead of clean ownership transitions.`
- recommended_tightening: `Create a repo-tracked overlap-resolution note for every new decision-bearing surface and require it to say one of keep, narrow, supersede, or retire before the surface is treated as active.`
- escalate_to_gm: `yes`
- escalation_reason: `The principle score is below 7, and the repo’s current failure pattern is specifically overlap drift across campaign and review surfaces.`

## `CC-03`: `distinct truth surfaces`

- principle_id: `CC-03`
- principle_name: `distinct truth surfaces`
- score_1_to_10: `7`
- why: `The repo separates canonical surfaces, active prompts, compact tranche summaries, closeouts, and run truth. The remaining weakness is that authority boundaries are not always obvious enough to prevent archaeology when a blocker moves from one surface to another.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `codex/tasks/governance_inventory.json`
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
- evidence_missing:
  - `No single compact truth map makes cross-surface authority and precedence obvious at a glance for all campaign families.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `codex/tasks/governance_inventory.json`
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
- main_failure_mode: `Truth surfaces exist, but their authority boundaries are not always obvious enough to prevent archaeology.`
- recommended_tightening: `Add a canonical truth-surface precedence note to campaign and governance docs that states which surface is authoritative for blocker ranking, run authority, closeout meaning, and operator-visible verdicts.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `CC-04`: `system minimization before expansion`

- principle_id: `CC-04`
- principle_name: `system minimization before expansion`
- score_1_to_10: `8`
- why: `This is one of the strongest principles in the repo. The minimization doctrine requires distinct trigger, distinct output, clear boundary, local verifiability, and operator-burden reduction.`
- evidence_found:
  - `docs/architecture/SYSTEM-VETTING-AND-MINIMIZATION.md`
  - `AGENTS.md`
  - `codex/tasks/governance_inventory.json`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
- evidence_missing:
  - `The repo still contains many archived one-off prompts and overlapping campaign artifacts, so the minimization rule is not yet fully reflected in surface count or operator complexity.`
- repo_surfaces_reviewed:
  - `docs/architecture/SYSTEM-VETTING-AND-MINIMIZATION.md`
  - `AGENTS.md`
  - `codex/tasks/governance_inventory.json`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
- main_failure_mode: `The repo is good at requiring a reason to add a new system, but less good at pruning or collapsing surfaces once overlap has already accumulated.`
- recommended_tightening: `Pair the minimization rule with a retirement rule for stale or overlapping prompts/tasks so expansion pressure is matched by explicit contraction pressure.`
- escalate_to_gm: `no`
- escalation_reason: `none`
