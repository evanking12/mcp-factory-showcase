# Pipeline Coordinator Reference

> Explanatory mirror only.
> Use `api/pipeline/README.md` and `api/pipeline/sNN_*/` for live stage truth.
> Historical N x M variant notes now live under `docs/architecture/_archive/oldstuff/NXM-EXPANSION-ARCHITECTURE.md`.

## Architecture

The pipeline uses a two-tier coordinator system:

- **Macro Coordinator** -- runs ONCE at the end of the full pipeline (after S-07). Makes cross-run decisions: should we loop again? What strategy adjustments for the next iteration? In NxM mode, also produces variant configs for the next run.
- **Micro Coordinators (MC-3 through MC-6)** -- run WITHIN a single pipeline execution, after specific stages. Make intra-run tactical decisions, primarily around write-function unlock. In NxM mode, MCs run on the **merged** output from the Variant Merger (not per-variant).

```
DLL Upload
    |
    v
S-00: Setup (sentinel calibration, vocab, static analysis)
    |
S-01: Write-Unlock Probe (code reasoning on decompiled C)
    |
S-02: Probe Loop (per-function LLM agent)
    |
S-03: Reconciliation --> MC-3: Write Failure Classification
    |
S-04: Synthesis -------> MC-4: Init Sequence Clues
    |
S-05: Enrichment ------> MC-5: Read-to-Write Chaining
    |
S-06: Gap Resolution --> MC-6: Final Comprehensive Unlock
    |
S-07: Finalization
    |
    v
Macro Coordinator --> Verdict: done | loop_again | awaiting_clarification
```

---

## Macro Coordinator

**File:** `api/pipeline/core/macro_coordinator.py`

**When it runs:** After S-07 completes. Called by `runner.py` at the end of `_explore_worker`.

**Inputs:**
- All findings (from blob storage)
- Clarification questions from S-06
- Full ExploreContext with sentinels, vocab, unlock status

**Evaluates:**
- `verified_rate`: verified_success functions / total callable functions
- `discovered_rate`: (verified + functional_precondition_unmet + inferred) / total
- Whether unresolved functions are all write-type (suggests unlock focus)
- Whether clarification questions exist (suggests user input needed)
- Per-variant performance (in NxM mode): which variant config produced the best results

**Decisions:**

| Verdict | Condition | What happens |
|---------|-----------|-------------|
| `done` | verified_rate >= 100% | Pipeline complete, all functions verified |
| `done` | verified_rate >= 85%, no questions | High enough — remaining functions likely unprobeable |
| `done` | discovered_rate >= 95%, no questions | Nearly everything understood (some may be `functional_precondition_unmet`) |
| `awaiting_clarification` | Open questions from S-06 | UI shows questions, user answers feed next run |
| `loop_again` | verified_rate < 85%, no questions | Suggests strategy adjustments + variant configs for next iteration |

**Strategy adjustments (suggestions for next run):**

| Adjustment | When suggested | Effect |
|-----------|---------------|--------|
| `focus_functions` | <= 3 unresolved functions | Only re-probe those specific functions |
| `skip_to_stage` | Sentinels/unlock already solved | Jump to S-02, skip S-00/S-01 |
| `focus_write_unlock` | All failures are write-type | Extend init mode sweep range |
| `increase_budget` | Functions were close to succeeding | Bump max_rounds and max_tool_calls |
| `variant_configs` | NxM mode, loop_again | M variant configurations for next run (model, temp, context, curriculum) |

**Output:** `RunVerdict` dataclass saved to `{job_id}/macro_verdict.json` and `job_status.macro_verdict`.

---

## MC-3: Post-Reconcile Write Failure Classification

**File:** `api/pipeline/s03_reconcile/mc3_write_analysis.py`  
**Function:** `_mc3_post_reconcile(ctx)`  
**Runs after:** Phase 4 (reconciliation)  
**Skipped if:** Write-unlock already resolved

**What it does:**
1. Scans the probe log for write-function return codes
2. Classifies the failure pattern:
   - **Uniform sentinel** (all write fns return same error) -- init/auth problem. Triggers targeted init sweep across modes 0-64.
   - **Mixed sentinels** (different errors per function) -- per-function argument problems. Defers to later stages.
   - **Accidental success** (write fn returned 0 but was recorded as error) -- patches the finding to success.
   - **No write probes** (write fns were never called) -- triggers a full write-unlock re-probe.
3. If targeted sweep succeeds, calls `_mark_unlock_resolved` and updates `ctx.write_unlock_block`

**Decision artifact:** `{job_id}/mc-decisions/mc3-post-reconcile.json`

---

## MC-4: Post-Synthesis Init Sequence Clues

**File:** `api/pipeline/s04_synthesis/mc4_init_clues.py`  
**Function:** `_mc4_post_synthesis(ctx)`  
**Runs after:** Phase 6 (API reference synthesis)  
**Skipped if:** Write-unlock already resolved

**What it does:**
1. Downloads `api_reference.md` (the LLM-generated synthesis document)
2. Regex-parses for:
   - Explicit init mode mentions: `CS_Initialize(mode=2)`, `mode 1 enables write`
   - Dependency chain mentions: `must call X before Y`
3. If init modes found, tries them via `_targeted_unlock_attempt`
4. If dependency chains found, logs them for MC-5/MC-6

**Decision artifact:** `{job_id}/mc-decisions/mc4-post-synthesis.json`

---

## MC-5: Post-Verification Read-to-Write Chaining

**File:** `api/pipeline/s05_enrichment/mc5_chain_reads.py`  
**Function:** `_mc5_post_verification(ctx)`  
**Runs after:** Phase 7b (verification)  
**Skipped if:** Write-unlock already resolved

**What it does:**
1. Loads all findings, filters for verified read functions
2. Extracts concrete values from working_call arguments:
   - Customer IDs matching `^[A-Z]+-\d+` (e.g., CUST-001, ORD-001)
   - Numeric amounts in range 1-100000
3. Builds argument combinations: each extracted ID x each extracted amount
4. Tries these combinations on every write function via `_targeted_unlock_attempt`

**Key insight:** If `CS_GetAccountBalance("CUST-001")` verified, then "CUST-001" is a known-good customer ID. Chain it into `CS_ProcessPayment(customer_id="CUST-001", amount=100)`.

**Decision artifact:** `{job_id}/mc-decisions/mc5-post-verification.json`

---

## MC-6: Final Comprehensive Unlock

**File:** `api/pipeline/s06_gaps/mc6_final_unlock.py`  
**Function:** `_mc6_post_gap_resolution(ctx)`  
**Runs after:** Phase 8 (gap resolution)  
**Skipped if:** Write-unlock already resolved

**What it does (4 phases):**

### Phase A: LLM Code Reasoning
- Sends ALL invocable decompiled C code to the LLM
- Asks for unlock strategies (XOR checksums, magic values, call sequences)
- Executes each strategy the LLM proposes

### Phase B: Pattern-Based Unlock
- Runs `_analyze_decompiled_unlock_patterns` to find XOR checksum targets
- Generates XOR codes for each target
- Tries ID x XOR-code combinations on unlock functions

### Phase C: Dependency Chain Replay
- Tries function sequences from code analysis (call A, then call B)
- Tests write functions after each dependency chain

### Phase D: Brute-Force Fallback
- All known IDs x all known amounts x init modes 0-512
- The widest sweep in the pipeline — last resort

**Status classification:** When MC-6 fails to achieve return 0 but observes a meaningful business-logic sentinel (e.g., "insufficient balance", "not enough points"), it classifies the finding as `functional_precondition_unmet` rather than `failure`. This indicates the function works but has unmet runtime preconditions. Historical N x M context is archived at `docs/architecture/_archive/oldstuff/NXM-EXPANSION-ARCHITECTURE.md`.

**Context advantage:** MC-6 has the RICHEST context of any coordinator. It sees all prior MC decisions, all verification results, all findings, and all decompiled C. This is why autonomous unlock discovery typically succeeds here.

**Decision artifact:** `{job_id}/mc-decisions/mc6-post-gap-resolution.json`

---

## Shared Infrastructure

All micro coordinators use:
- `_persist_mc_decision(ctx, mc_id, decision)` from `core/helpers.py` — appends to decision artifact
- `_targeted_unlock_attempt(ctx, init_seqs, write_args, label)` from `s01_unlock/unlock_helpers.py` — runs init sequence + write test
- `_mark_unlock_resolved(ctx, trigger, notes)` from `s01_unlock/unlock_helpers.py` — marks ctx as unlocked, triggers re-probe

All coordinators mutate `ctx` in-place and return nothing. Side effects:
- `ctx.unlock_result` — updated if unlock succeeds
- `ctx.write_unlock_block` — updated with unlock status text for LLM prompts
- Findings patched in blob storage via `_patch_finding`
- Decision artifacts written to blob storage
