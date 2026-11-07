# Agent Evaluation Loop

## Purpose

This document explains how to build, test, critique, and refine an agentic
ecosystem for MCP Factory.

It treats agents as product components, not as magical general helpers.

The goal is to answer:

- how to define an agent role
- how to test whether the role is actually useful
- how to refine the role after observing failures
- how to dynamically decide which agents the ecosystem needs next

This is the operating model for turning one human plus a disciplined AI
ecosystem into a coherent product team.

## Core Thesis

AI agents work best when they have:

- specialized roles
- explicit tasks
- bounded ownership
- defined inputs
- defined outputs
- measurable evaluation criteria
- clear disallowed behaviors

They work worst when they are treated as:

- vague autonomous helpers
- substitutes for product intent
- broad omniscient workers with no boundary

So the ecosystem should be built the same way the product is built:

- contract first
- evaluated in practice
- refined from evidence

## The Core Loop

The correct loop for a new agent or bot is:

1. define the role
2. define the task boundary
3. define the expected output
4. run the agent on a bounded real or synthetic task
5. inspect what it got right
6. inspect what it got wrong
7. refine the role contract
8. rerun
9. decide whether the agent is trustworthy enough for real workflow use

This is the same principle as the dynamic prompt loop:

- do one bounded thing
- inspect evidence
- refine from the result

## Program-Level Success vs Local Prompt Success

For this ecosystem, these are not the same:

- local prompt success
  - one prompt family produced its contracts, evaluations, and refinements
- program success
  - the ecosystem can now be handed to the user as an implementation-ready
    package

The ecosystem program is not complete merely because:

- Prompt 01 calibrated `review + gate`
- Prompt 02 calibrated `run/evidence`
- Prompt 03 calibrated `product/observability`

It is complete only when those calibrated role families are synthesized into
one implementation-ready package that tells the user exactly what to stand up.

## Final Deliverable Requirement

The final required deliverable for the ecosystem program is an
implementation-ready ecosystem package.

Recommended canonical artifact:

- `docs/architecture/agentic_ecosystem/AGENTIC-ECOSYSTEM-IMPLEMENTATION-PACK.md`

That package should include:

- role hierarchy
- useful specialist roles discovered
- role family grouping
- role contracts
- evaluation outcomes
- keep / refine / split / merge / retire decisions
- recommended `skill` vs `agent` vs `prompt-only` routing for each role
- recommended model and reasoning effort
- recommended sandbox mode or write boundary
- expected context inputs
- expected output contracts
- repo locations for setup
- rollout order
- parent-thread dispatch law
- context-management rules

Without that package, the program is still exploratory rather than
implementation-ready.

## Treat Every Agent As A Product Component

For each agent, define:

- purpose
- owned inputs
- owned outputs
- GM-consumable top-block output
- what it should never do
- what success looks like
- what failure looks like
- what evidence it must cite
- how its work will be reviewed

This prevents role drift.

Without this, the ecosystem becomes:

- noisy
- hard to trust
- difficult to review
- expensive to operate

## Example Role Contract Shape

For any agent, the minimum useful role contract should answer:

- `name`
- `purpose`
- `GM-consumable output`
  - every specialist response starts with the YAML block defined in
    `role_contracts/GM-CONSUMABLE-SPECIALIST-OUTPUT.md`
- `trigger`
- `do_use_when`
- `do_not_use_when`
- `required_inputs`
- `required_output_shape`
- `disallowed_behaviors`
- `evaluation_criteria`
- `close_conditions`

This applies to:

- subagents
- code review bots
- verification bots
- handoff bots
- observability bots
- architecture drift bots

## How To Evaluate A Subagent

When evaluating a subagent role:

1. write the role contract
2. give it one bounded task
3. include exact files or artifacts
4. require a specific output shape
5. compare the result against what a strong human reviewer would want

Record:

- prompt used
- task input
- output produced
- what it got right
- what it missed
- what it overclaimed
- whether the role is too broad or too weak
- what should change next

That record should live in a durable artifact, not only in conversation memory.

Recommended homes:

- `docs/architecture/agentic_ecosystem/agent_evals/`
- or `sessions/agent_evals/`

Canonical repo-tracked surfaces for this ecosystem now include:

- prompt-chain home:
  - `docs/architecture/agentic_ecosystem/prompts/`
- role-contract template:
  - `docs/architecture/agentic_ecosystem/role_contracts/`
- evaluation schema:
  - `docs/architecture/agentic_ecosystem/agent_evals/`
- lifecycle governance:
  - `docs/architecture/agentic_ecosystem/AGENT-LIFECYCLE-GOVERNANCE.md`
- lifecycle registry:
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
- dynamic campaign template:
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
- scoped cleanup workflow template:
  - `docs/architecture/agentic_ecosystem/prompts/templates/SCOPED-REPO-CLEANUP-PROMPT-TEMPLATE.md`

## How The Main Thread Should Use A Subagent

The main thread should:

- define the subgoal
- define the evidence boundary
- define the output shape
- spawn the agent
- inspect the result
- critique the role itself, not only the answer
- refine the role contract if needed

That means the main thread is not only asking:

- did the subagent answer the question

It is also asking:

- is this agent good at this kind of question at all
- is the prompt too broad
- is the output shape wrong
- should this role remain a subagent, a skill, a custom agent, or a parent
  responsibility

## Workflow-Level Orchestration Skills

Not every reusable ecosystem component should become a specialist reviewer or
auditor.

Some reusable components should be workflow-level orchestration skills that:

- choose one bounded surface
- dispatch existing specialist roles beneath them
- enforce one-cycle stop gates
- standardize output shape across repeated cleanup or review work

The scoped cleanup workflow is the canonical example:

- skill:
  - `.agents/skills/scoped-repo-cleanup/SKILL.md`
- prompt template:
  - `docs/architecture/agentic_ecosystem/prompts/templates/SCOPED-REPO-CLEANUP-PROMPT-TEMPLATE.md`

That workflow does not replace:

- `repo-hygiene-auditor`
- `run-artifact-curator`
- `code_review_bot`
- `verification_gate_bot`

It orchestrates them under the GM model for one ownership surface at a time.

## Dynamic Campaign Workflow Quality

Dynamic campaigns should evaluate workflow quality explicitly, not leave it as
an inference from product progress alone.

For every executed tranche, the GM must authoritatively score:

- `gm_control_quality`
- `context_pressure_result`
- `delegation_effectiveness`
- `operator_reviewability`

Each field must include:

- `score`
- `evidence`
- `strongest_risk`
- `next_correction`

Use this fixed score scale:

- `0 = failed_or_unsafe`
- `1 = weak`
- `2 = acceptable`
- `3 = strong`

`context_pressure_result` must explicitly say whether any branch-shaping fact
lived only in chat or transient thread memory before durable writeback caught
up.

Taskforce rule:

- the GM is always the authoritative scorer
- `campaign-output-ledger` preserves the relevant workflow deltas while the
  tranche is live
- `campaign-reviewer` owns prompt-close review, campaign review summary, and
  morning principles review
- `proving-authority-reviewer` owns rerun-authority review before proving
  evidence may steer the next branch
- review topology stays star-shaped under the GM:
  - no recursive reviewer delegation
  - no reviewer-owned branch choice
  - no reviewer-owned code changes

Required review checkpoints:

- prompt close:
  - `campaign-reviewer`
  - non-blocking unless pause, handoff, compaction, or overnight close is the
    active gate
- rerun or proving close:
  - `proving-authority-reviewer`
  - blocking before blocker rerank or next-prompt choice from that run
- overnight or morning close:
  - `campaign-reviewer`
  - blocking before campaign pause or handoff

Campaign-level synthesis should also judge:

- dispatch discipline quality
- branch mutation quality
- evidence-to-decision quality
- stop-gate quality
- campaign economics

Campaign economics should at minimum count:

- executed tranches
- code-bearing tranches
- reruns or proving commands
- blocker reranks
- prompt displacements

Dispatch-accountability rule:

- every executed tranche should leave durable evidence of:
  - roles considered
  - roles dispatched
  - why materially fitting roles were not dispatched
- role usefulness should be judged not only by output quality, but also by:
  - trigger fit
  - dispatch frequency when applicable
  - skip quality when not dispatched
  - whether dispatch accountability improved reviewability

## Code Review Bot Example

Yes, the same loop should be used for a code review bot.

### Step 1: Start With A Default Review Assumption

A good default review assumption is:

- correctness
- regressions
- missing tests
- boundary violations

### Step 2: Run It On Real Changes

Use real repo diffs, not only invented examples.

Ask:

- did it find real bugs
- was it too noisy
- did it focus on style instead of risk
- did it miss important boundary issues
- did it cite the right files and lines

### Step 3: Tighten It To The Repo

For this repo, a strong review bot should eventually understand:

- contract-first change discipline
- execution-lane trust
- underscore-boundary restrictions
- UI truth sync requirements
- evidence and regression discipline
- system ownership boundaries

### Step 4: Refine And Rerun

The goal is not to guess the perfect review agent up front.

The goal is to evolve one from:

- generic reviewer

to:

- MCP Factory reviewer

## The Principles At Play

The main principles you are talking about are:

- contract-first agent design
- evaluation-driven refinement
- closed-loop improvement
- explicit ownership
- measurable outputs
- observability for agents
- calibration before trust
- prompt engineering as systems design
- productizing the ecosystem instead of improvising it

Also:

- dogfooding
- harnessing
- reviewability
- trust gating

## Do People Commonly Use This Tactic

Yes, good teams do, even if they do not always describe it clearly.

The mature pattern is:

- define role
- test role on bounded tasks
- inspect misses and overclaims
- refine prompt and constraints
- rerun
- only then rely on the agent in a production workflow

What many teams do instead is:

- write one clever prompt
- call it a reviewer or debugger
- then tolerate unstable results

That is weaker than the evaluation loop described here.

## How To Dynamically Change What Agents The System Needs

This is one of the most important parts of the ecosystem.

The ecosystem should not keep a fixed list of agents forever.

It should evolve from the findings.

### Rule

Create, refine, merge, or retire agent roles based on recurring work patterns
and recurring failure patterns.

### Add A New Agent Role When

All of these are becoming true:

- a task recurs across multiple cycles
- the task has a stable trigger
- the task has a distinct output shape
- the task has a clear boundary
- giving it to a specialist would reduce noise or improve review quality

Examples:

- repeated need to audit lane trust
- repeated need to check UI truth drift
- repeated need to format structured handoffs
- repeated need to review cross-system contract changes

### Refine An Existing Agent When

The role is directionally right, but:

- too noisy
- too broad
- too vague
- too optimistic
- too weak at citing evidence
- not specific enough to the repo

Refinement levers:

- sharpen trigger
- narrow scope
- improve output format
- add repo-specific doctrine
- add explicit do-not-do rules
- add examples of real failure modes

### Split An Agent When

One role is doing two distinct jobs badly.

Examples:

- one “reviewer” both checks correctness and formats handoffs poorly
- one “auditor” both checks lane trust and evaluates suite coverage

Those should become separate roles if:

- triggers differ
- outputs differ
- expertise differs

### Merge Agents When

Two roles are not actually distinct.

Merge if:

- they have the same trigger
- they produce nearly the same output
- the split adds confusion rather than specialization

### Retire An Agent When

- the task is no longer recurring
- the role was replaced by a stronger one
- the role is too broad to evaluate honestly
- the role is better handled by the parent thread

## What To Record After Each Agent Evaluation

Every evaluation should ideally leave behind:

- the role tested
- the task given
- the output produced
- the quality assessment
- the strongest miss
- the strongest overclaim
- the next refinement
- the decision:
  - keep
  - refine
  - split
  - merge
  - retire

This is how the ecosystem becomes measurable instead of mystical.

## Dynamic Prompt-Chain Rule For This Ecosystem

The prompt chain should behave like this:

1. calibrate one role family
2. record the role contracts and evaluation artifacts
3. refine the family
4. generate the next prompt from evidence
5. continue into the next role family
6. synthesize the resulting role families into the implementation-ready
   ecosystem package

Stopping after a role-family calibration is only valid if:

- the program was explicitly scoped to that one family, or
- a stop condition fired

Otherwise, the chain must continue.

## Specialized Roles Worth Considering

Below is a non-exhaustive set of specialized roles that may be useful over
time.

### Review And Gate Roles

- code review bot
- verification gate bot
- regression risk bot
- public boundary auditor
- architecture drift auditor

### Run And Evidence Roles

- run auditor
- ledger auditor
- compare-run auditor
- attribution auditor
- roadblock classifier

### Product And Observability Roles

- UI truth auditor
- coverage surface summarizer
- dashboard contract checker
- operator wording reviewer

### Delivery And Coordination Roles

- handoff formatter
- release checkpoint summarizer
- branch readiness reviewer
- prompt-chain construction auditor

### Suite And Architecture Roles

- proving-suite evaluator
- blocker-family coverage evaluator
- system ownership drift evaluator
- capability progression reviewer

## How The Ecosystem Should Refine Itself While The User Is Away

Yes, if configured and authorized properly, the ecosystem should be able to:

- trace each role
- test the role on bounded work
- critique the role
- refine the role
- preserve those findings in repo-tracked form

The parent thread should remain the decision-maker.

That means the parent can:

- give a subagent a bounded role
- inspect how well it performed
- decide whether the role contract is good enough
- refine it
- rerun the evaluation
- decide whether to keep using that agent

This is how the ecosystem itself becomes a product.

## How AI Agents Work Best

AI agents work best when:

- the role is narrow
- the task is explicit
- the inputs are sufficient
- the outputs are structured
- the boundary is enforced
- evaluation is frequent
- trust is earned, not assumed

The path to that state is refinement:

1. start broad enough to be useful
2. test on real work
3. identify misses and drift
4. narrow or split the role
5. add repo-specific law
6. retest

That is how you get from:

- general helper

to:

- trustworthy specialist

## Operating Conclusion

The ecosystem should be built with the same mindset as the main product:

- explicit roles
- explicit contracts
- evidence-driven refinement
- trustworthy outputs
- real observability

If built that way, one human plus the ecosystem can operate far above what a
solo improvised workflow could sustain.

## Ecosystem Hierarchy And Role Depth

Yes, the ecosystem should generally have a hierarchy.

The healthiest default shape is:

- one main orchestrator thread
- several mid-level specialist roles
- several narrow evaluators, auditors, and workers beneath them

For this repo, the main orchestrator should remain:

- the main Codex thread

That parent thread acts as:

- general manager of the active information
- sole branch selector
- final synthesis layer
- prompt-chain owner
- conflict resolver between specialist findings

Everything else should become more specialized as the role gets closer to a
single recurring task.

This does not mean the system needs dozens of agents immediately.

It means the structure should support:

- broad synthesis at the top
- narrower roles beneath it
- explicit handoff between layers

## How Many Agentic Roles Are Plausible

Quite a lot are plausible, but not all should exist at once.

The right answer is:

- many potential roles
- few active trusted roles at first
- more only when recurring work proves the need

Immediate role families that make sense for this project:

### Orchestration Layer

- main execution/orchestrator agent
- dynamic prompt-chain manager
- branch and stop-gate selector

### Review And Gate Layer

- code review bot
- verification gate bot
- regression risk bot
- public-boundary reviewer
- architecture drift reviewer

### Run And Evidence Layer

- run auditor
- ledger auditor
- compare-run auditor
- campaign attribution auditor
- roadblock classifier

### Product And Observability Layer

- UI truth auditor
- dashboard contract checker
- coverage summarizer
- operator wording reviewer

### Delivery Layer

- handoff formatter
- release checkpoint summarizer
- branch readiness reviewer
- prompt-chain construction reviewer

### Suite And Architecture Layer

- proving-suite evaluator
- blocker-family coverage evaluator
- system ownership evaluator
- capability progression evaluator

### Narrow Worker Layer

- route fix worker
- probe-loop fix worker
- validation/wrapper worker
- dashboard presentation worker
- doc sync worker

That is already well over a dozen plausible roles.

But the ecosystem should not start by activating all of them.

## Specialized Subsections Vs Distinct Roles

Some roles should remain subsections of a broader role at first.

Example:

- one code review bot may initially cover:
  - correctness
  - regressions
  - boundary violations
  - missing tests

Later, if the outputs diverge enough, that can split into:

- correctness reviewer
- regression reviewer
- boundary reviewer
- test adequacy reviewer

So yes, many roles begin as specialized subsections inside a broader role.

The split should happen only when:

- the trigger differs
- the output differs
- the evaluation criteria differ
- the broader role is becoming noisy or vague

## The Correct Hierarchy For This Repo

Yes, the intended direction is:

- one general manager of active truth
- more and more specific specialists beneath it

That manager should:

- hold the wider goal
- hold the stop gate
- hold the dominant blocker
- route work to specialists
- integrate findings
- decide what gets recorded in the next prompt or handoff

The specialists should:

- not own product intent
- not own branch choice
- not own the final synthesis
- own only their bounded role

## Skills Vs Agents Vs Prompt Artifacts

This ecosystem should use three layers distinctly.

### Skills

Skills should encode:

- recurring execution law
- decision criteria
- repo-specific discipline

Use a skill when the same reasoning pattern will recur across many tasks.

Examples:

- subagent orchestration
- roadblock handling
- UI sync auditing
- ledger auditing

### Agents

Agents should encode:

- role
- scope
- output contract

Use an agent when the task is role-shaped and can be repeated under a stable
specialty.

Examples:

- code review agent
- verification gate agent
- run auditor agent

### Prompt Artifacts

Prompt artifacts should encode:

- current bounded objective
- current evidence
- current branch
- next-prompt construction

Use prompt artifacts when the work is campaign-shaped or architecture-shaped
and must evolve from live findings.

Examples:

- dynamic prompt chains
- architecture execution tranches
- proving-suite readiness gates

## How To Route Work Between Them

The general rule is:

- stable recurring law -> skill
- stable specialist role -> agent
- current evolving tranche -> prompt artifact

If a role needs recurring repo doctrine and bounded execution:

- use both a skill and an agent

If a current tranche keeps recurring across many prompts:

- extract its stable part into a skill or specialist agent

## Context Window Management

This is one of the most important practical issues.

The ecosystem works best when context is stratified.

### Parent Thread Context

The parent thread should hold only:

- wider goal
- minimum floor
- current horizon
- stop gate
- dominant blocker
- active system boundaries
- latest proving results
- next-prompt construction state

The parent should not keep every raw artifact or every code path in active
memory.

### Specialist Context

Each specialist should receive only:

- the exact role it owns
- the exact question it must answer
- the exact files or artifacts it needs
- the required output shape
- the disallowed drift

This keeps specialist threads sharper and cheaper.

### Durable Context Surfaces

The ecosystem should offload long-lived context into:

- skills
- system docs
- prompt artifacts
- construction notes
- run artifacts
- handoff records

That is how the parent thread avoids carrying the whole repo in working memory.

### Integration Rule

Subagents should return:

- conclusion
- evidence
- uncertainty
- smallest safe next move

The parent then compresses that into:

- next decision
- next prompt
- or recorded doctrine

This is how context gets summarized instead of endlessly accumulated.

## How To Manage My Context Versus Subagent Context

The right pattern is:

- I keep the strategic and cross-system context
- they keep the local specialized context

I should pass down:

- only what they need to answer their bounded question

They should pass back:

- only what I need to choose the next branch

That prevents context pollution and keeps the main thread useful for long
programs.

## Dynamic Role Refinement

As the ecosystem matures, I should continually ask:

- is this recurring enough to deserve a specialist
- is this specialist too broad
- should this role split
- should this move into a skill
- should this become a prompt template instead
- should this role retire because the parent thread or another role now covers
  it better

This means the ecosystem should evolve from evidence exactly the same way the
product evolves from evidence.

## Practical Rule

Start with:

- one strong parent orchestrator
- a small number of high-value specialist roles

Then refine toward:

- more specialized roles
- sharper prompts
- stronger skills
- cleaner handoffs
- smaller context windows per specialist

The target is not maximal complexity.

The target is:

- maximal clarity per role
- minimal ambiguity per task
