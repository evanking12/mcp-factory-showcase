# Truth, Replay, Checkpoints, And Compounding

```mermaid
flowchart TD
    A["cold run"] --> B["audited artifacts"]
    B --> C["checkpoint"]
    B --> D["ledger row"]
    B --> M["materialized runtime artifacts"]
    C --> E["replay-backed run"]
    D --> E
    M --> E
    E --> F["compare and decide"]
    F --> G["promote only when claims stay truthful"]
```

Current first-wave result:

- compounding improved some same-DLL state reuse,
- but the transport surface stayed flat and payments exposed a regression,
- so promotion should remain conservative.
