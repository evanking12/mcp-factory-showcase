# S-03 Systems

## Depends On

| System | Use |
| --- | --- |
| Probe evidence | Compares LLM labels against actual call results. |
| Finding status taxonomy | Normalizes and repairs status semantics. |
| Micro-coordinator decisions | Captures write-failure analysis. |
| Artifact storage | Persists MC and sentinel catalog evidence. |

## Does Not Own

| System | Boundary |
| --- | --- |
| Function probing | S-02 owns raw runtime probing. |
| Narrative synthesis | S-04 owns human-readable API documentation. |
| Final closure | S-07 owns final harmonization and done/clarification state. |

## System Notes

S-03 is a truth-repair stage. It can correct contradictions but should not
invent behavior that is not supported by probe evidence.
