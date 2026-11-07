# Multi-Agent Operating Design

## Purpose

Use multiple agents to reduce context rebuild, note burden, and triage delay
around one trusted live lane.

This layer exists to exploit the stronger substrate now available:

- machine-readable cluster checkpoints
- `convergence_summary.json`
- carryover audit surfaces
- `cross_dll_contracts` in campaign truth and attribution

It does not parallelize live execution.

## Hard Guardrails

- one live executor only
- analysis agents may read and summarize, but may not launch live runs
- roles must stay narrow and artifact-driven
- reusable roles become skills only when governance inventory rules are met
- campaign-specific roles remain prompts or runbooks

## Role Layout

### 1. Executor

Reads:

- the latest strategy digest
- the active cluster-owner digest
- carryover audit digest when package truth is involved

May touch:

- code
- notes
- bounded run surfaces

Outputs:

- the only live run decision
- the bounded patch or rerun result
- final tranche closeout

Must never do:

- delegate live execution to side agents
- allow multiple concurrent live reruns on the same lane

### 2. Cluster Owners

Instances:

- pricing owner
- workflow owner
- config/reporting owner

Reads:

- cluster checkpoint rows
- `convergence_summary.json`
- focused proof notes

May touch:

- cluster-local notes only when explicitly asked

Outputs:

- current seam
- latest trusted proof jobs
- first broken invariant
- next bounded local move

Must never do:

- launch runs
- widen scope from one cluster to package scale on their own

### 3. Carryover Auditor

Reads:

- campaign attribution report
- carryover audits
- local green vs package red proof notes

May touch:

- carryover note surfaces only when explicitly asked

Outputs:

- strongest carryover signal
- first broken handoff
- next audit question

Must never do:

- claim package recovery from local-only evidence
- mutate execution state

### 4. Strategy / Triage

Reads:

- cluster-owner digests
- carryover digest
- latest oracle or comparison surface

May touch:

- decision notes only

Outputs:

- one next action class:
  - rerun
  - investigate
  - fix
  - stop
  - architecture work

Must never do:

- code
- live runs

### 5. Artifact Curator

Reads:

- the latest prompt notes
- weakness register
- current operating design

May touch:

- handoff notes
- curated artifact indexes

Outputs:

- minimum handoff set
- what to ignore
- concise tranche closeout support

Must never do:

- re-triage technical direction
- duplicate the executor or strategy role

## Skills Vs Prompts

Keep as reusable skills:

- `triage-next-step`
  because it already has a distinct trigger, output, and decision boundary
- `run-artifact-curator`
  because artifact curation is reusable across campaigns and is already
  decision-distinct

Keep as prompts or runbooks for now:

- executor
  because this is the main operator lane, not a reusable sidecar skill
- pricing / workflow / config-reporting cluster owners
  because the ownership boundary is campaign- and frontier-specific
- carryover auditor
  because the role is now distinct enough to name, but still too tied to the
  current package frontier to promote into governance inventory yet

Do not add a new skill until:

- the same role trigger recurs across multiple campaigns
- the output stays stable
- the do-not-use boundary is explicit

## One Real Operating Cycle

Cycle date:

- April 6, 2026

Cycle goal:

- choose the next bounded operator handoff after prompt 05 and prompt 06
  without reopening every raw artifact in one thread

Role instantiation:

- executor: main thread
- pricing cluster owner: sidecar digest
- carryover auditor: sidecar digest
- artifact curator: sidecar digest
- strategy / triage: main-thread synthesis from those digests

Sidecar outputs:

- pricing owner reduced the pricing state question to a 4-file digest centered
  on job `920b7ae6`
- carryover auditor reduced the package persistence question to a 3-file digest
  centered on `carryover_audits` and the handoff
  `PR_ApproveRuleWindow -> PR_GetQuoteState`
- artifact curator reduced the next-operator handoff to a 4-item required set
  and explicitly excluded raw campaign JSON and full validation logs

Measured effect:

- raw source files distributed across sidecar questions: `12`
- digest outputs the executor had to consume: `3`
- context-rebuild reduction at the executor boundary: `75%`
- live execution parallelized: `no`

Why this counts:

- the executor reached a bounded next-state picture by reading three short role
  digests instead of reopening a dozen raw artifacts across three question
  classes
- the proof is about less context rebuild and less note burden, not faster live
  runtime

Proof artifact:

- `sessions/campaigns/blocker_harvest/20260405-111636/prompt-07-operating-cycle.json`

## Launch Sequence

1. Executor reads the latest prompt note and weakness register.
2. Executor instantiates only the sidecars needed for the current question.
3. Sidecars read machine-readable artifacts first.
4. Strategy chooses exactly one next action class.
5. Executor alone performs the live move if one is justified.
6. Artifact curator updates the handoff set and weakness register.

## Residual Boundaries

- this is an external coordination model, not an internal multi-executor
  pipeline
- it depends on the cluster checkpoint, convergence, carryover, and cross-DLL
  contract surfaces remaining machine-readable
- it should be judged by lower context rebuild and cleaner decisions, not by
  agent count
