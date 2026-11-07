# S-00 Systems

## Depends On

| System | Use |
| --- | --- |
| Intake and discovery | Provides job status, binary path or upload blob, and `ctx.invocables`. |
| Ghidra bridge | Provides decompiled C, parameter surfaces, call graph extras, and data types when available. |
| Local artifact storage | Persists S-00 artifacts under `{job_id}/`. |
| Checkpointing | Records S-00 completion and resumes around completed setup work. |
| Prior-run inheritance | Allows vocab and sentinel reuse when a prior job is supplied. |
| Change-admission and sticky-doc governance | Keeps artifact and handoff changes explicit. |
| Sentinel calibration implementation | Supplies current baseline-truth behavior behind the S-00-owned setup baseline boundary. |
| Vocab implementation | Supplies current vocab and prior-hints behavior behind the S-00-owned setup baseline boundary. |
| Static analysis implementation | Supplies current static extraction behavior behind the S-00-owned static evidence boundary. |
| Shared handoff builder | Supplies normalized packet assembly while S-00 owns the admission/handoff boundary. |

## Does Not Own

| System | Boundary |
| --- | --- |
| Runtime proof | S-00 emits static/setup priors, not semantic truth. |
| Unlock behavior | S-01 owns write-mode unlock decisions and probing. |
| Probe curriculum | S-02 owns function-level probing order and runtime calls. |
| Cross-DLL orchestration | This stage currently produces a per-job packet, not a cross-DLL admission layer. |

## System Notes

Ghidra output is treated as structural prior. Runtime proof and downstream
verification can override or narrow static evidence.
