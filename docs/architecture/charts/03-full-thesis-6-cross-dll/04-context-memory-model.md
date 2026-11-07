# Context And Memory Model

```mermaid
flowchart TD
    R["ExploreRuntime"] --> C["ExploreContext"]
    P["prior job"] --> C
    Q["checkpoint"] --> C
    C --> M["runtime artifact materializer"]
    M --> E["evidence candidates, findings, and reusable artifacts"]
    E --> F["final artifacts"]
    F --> P
```

Current first-wave result:

- reusable runtime artifacts are helping some producer-consumer chains
- routing is still not reliable enough to treat this as a complete Tier 1 win
