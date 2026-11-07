# GhidraMCP Static Comparison Program

## Question

This note is not asking:

- "is GhidraMCP good?"

It is asking:

- across authored `contoso` fixtures and one bounded `spectrum` slice, what
  static artifacts does GhidraMCP recover better than current `S-00`, and
  which of those are strong enough to justify the first `S-00` split?

Current `S-00` is the control. GhidraMCP is one candidate static evidence
surface, not the new architecture.

## Two Investigation Tracks

### 1. Empirical track

For each target, capture the same bounded packet:

- methods / exports
- imports
- strings
- bounded decompile snippets for key functions
- xrefs / call-relationship hints
- datatype / enum surfaces if available
- warnings / ambiguity signals if available

Then compare that against what current `S-00` already emits or can emit.

### 2. Design and source track

Read the GhidraMCP source to extract design principles, not to copy the whole
project.

Questions to answer:

- what surfaces are first-class tools
- what is keyed by function name vs address
- what is query-shaped vs artifact-shaped
- what is interactive convenience vs automation-ready
- what can be serialized cleanly
- what principles belong in `static_surface_extraction`
- what principles belong in `static_prior_shaping`
- what is only analyst ergonomics

Keep source-reading conclusions separate from empirical comparison results.

## Current S-00

`S-00` is directionally right but too compressed.

Today it mixes:

- sentinel calibration
- vocab seeding
- static analysis

The doctrinal flow also expects:

- FLOSS recovery
- direction reclassification
- call graph construction
- Ghidra data type extraction

What `S-00` already gets right:

- shared pre-probe context exists
- early error-code language is seeded
- static evidence is treated as prior, not truth
- some Ghidra-derived surfaces already exist, such as `call_graph.json` and
  `ghidra_data_types.json`

What is still weak:

- runtime calibration and static foundation are blended together
- extraction and shaping are blended together
- Ghidra-derived evidence often arrives late through `invocables` and
  `_ghidra_extras` instead of one owned static packet
- ambiguity, prerequisite hints, and frontier-shaping priors are not yet
  first-class outputs

The likely split target remains:

1. `setup_and_contract_baseline`
2. `static_surface_extraction`
3. `static_prior_shaping`

## What GhidraMCP Exposes

The live GhidraMCP path and the local bridge script expose a real static tool
surface, not just a nicer chat loop.

Observed or bridge-defined surfaces:

- methods / function listing
- classes / namespaces
- imports / exports
- strings
- data labels
- segments
- decompile by name
- decompile by address
- xrefs to / from / by function
- current address / current function lookup
- rename function / variable / data
- comment / prototype / local type updates

The live comparison value is strongest when these surfaces become durable
artifacts rather than one-off analyst interactions.

## Normalized Comparison Harness

Each target should produce one normalized packet with these sections:

- `target_metadata`
  - family
  - DLL path
  - fixture role
- `current_s00_packet`
  - what current `S-00` emits or can emit
  - presence or absence of `static_analysis.json`, `call_graph.json`,
    `ghidra_data_types.json`, decompile-derived surfaces, and ambiguity
    handling
- `ghidra_mcp_packet`
  - methods / exports
  - imports
  - strings
  - bounded decompile snippets for key functions
  - xrefs / call-relationship hints
  - datatype / enum surfaces if available
  - warnings / ambiguity signals if available
- `delta_assessment`
  - callable-surface gain
  - graph / prerequisite gain
  - datatype gain
  - ambiguity-labeling gain
  - no real improvement
- `verdict`
  - `adoptable_artifact_win`
  - `interesting_but_convenience_only`
  - `unsafe_or_overclaim_prone`
  - `no_material_improvement`
- `headlessability`
  - `already_headlessable`
  - `serializable_but_not_headless_yet`
  - `interactive_only`

## Fixture Ladder

Do not open all authored suites by hand. Use this ladder:

1. `contoso_legacy/contoso_cs.dll`
   - establish the schema and control packet
2. remaining `contoso/*`
   - one representative DLL per family first
3. one bounded `spectrum` slice
   - `tests/fixtures/spectrum_transaction_release_settlement_suite/bin/spectrum_session_bootstrap.dll`
4. only then broaden within `spectrum`

The point of the ladder is to distinguish:

- what survives on easy authored fixtures
- what survives once dependencies are more entangled
- what breaks down before broad suite coverage

## Campaign Legality

This work can be a real dynamic campaign.

The GUI dependency does not disqualify it, but it changes the law:

- the first tranche is explicitly `GUI-assisted`
- the parent thread owns the live GhidraMCP session
- subagents only analyze captured packets
- broader rollout is blocked until the campaign records a `headlessability`
  verdict

Constraints:

- do not let multiple agents poke the same live Ghidra session
- do not treat interactive-only wins as product wins
- do not treat static evidence as runtime truth
- do not decide architecture from one impressive decompile

## Stop Gate

The comparison program should stop when either:

1. at least two durable artifact wins survive the `contoso` ladder and one
   bounded `spectrum` slice and are strong enough to justify the first `S-00`
   split contract
2. the result is convenience-only, GUI-only, or overclaim-prone and therefore
   not campaign-worthy for rollout

Success is not "GhidraMCP looked useful." Success is:

- specific artifact classes survived the ladder
- they improve static foundation quality over current `S-00`
- they are at least serializable enough to be campaign-legal inputs to a future
  `static_surface_extraction` stage

## Claim Ceiling

This comparison program may prove only:

- static prior improvement
- better static artifact extraction
- better ambiguity preservation
- stronger prerequisite or frontier hints
- whether those gains are strong enough to justify the first `S-00` split
  contract

It may not prove:

- runtime truth
- unlock correctness
- semantic correctness
- broader pipeline success
- full `S-00` replacement

Any stronger claim requires separate runtime corroboration.

## What Counts As A Real Win

Only promote findings that can become first-class artifacts such as:

- `surface_inventory.json`
- `static_ambiguity_map.json`
- `candidate_prerequisite_graph.json`
- `static_role_hints.json`
- `probe_plan_seed.json`
- `static_frontier_ranking.json`
- bounded `decompile_snippets.json`

If a finding cannot become a durable artifact, it is probably convenience, not
architecture.
