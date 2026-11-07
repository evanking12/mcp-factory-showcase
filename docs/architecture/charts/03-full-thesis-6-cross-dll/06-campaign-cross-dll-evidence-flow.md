# Campaign And Cross-DLL Evidence Flow

Primary code anchors:

- `api/pipeline/core/campaign_stages.py`
- `api/pipeline/core/checkpoint.py`
- `api/pipeline/core/types.py`

```mermaid
flowchart TD
    PRE["S-pre campaign planner"] --> PLAN["execution order plus per-DLL context slices"]

    subgraph DLLRuns["Per-DLL explore runs"]
        D1["DLL A run"]
        D2["DLL B run"]
        D3["DLL C run"]
    end

    PLAN --> D1
    PLAN --> D2
    PLAN --> D3

    D1 --> OUT1["findings, invocables, vocab, evidence candidates"]
    D2 --> OUT2["findings, invocables, vocab, evidence candidates"]
    D3 --> OUT3["findings, invocables, vocab, evidence candidates"]

    OUT1 --> POST["S-post consolidation into EvidenceGraph"]
    OUT2 --> POST
    OUT3 --> POST

    POST --> GRAPH["cross-DLL edges, entity overlap, re-probe recommendations"]
    GRAPH --> BASE["curated ten-DLL baseline contract"]
    BASE --> ATTR["baseline-aware campaign attribution report"]
    GRAPH --> ATTR
    ATTR --> NEXT["next campaign iteration or targeted replay"]
    NEXT --> PLAN
```

Interpretation:

- Cross-DLL novelty lives in shared evidence becoming controlled future context.
- Campaign orchestration is not just batch execution; it is graph-backed learning across DLL boundaries.
- The attribution report is the architect-facing layer that turns campaign artifacts into next-system and regression decisions.
- Once the suite has a curated benchmark control, the attribution layer should compare against that contract first and only use ledger fallback when the curated baseline is absent.
- The attribution layer must mark explicit surface mismatches as `incomparable` instead of flattening them into false "flat" or false regression judgments.
- Clean-control decisions and historical-wave decisions are related but not identical: stronger repaired anchors may remove old apparent gains from the current control surface without invalidating the historical implementation lesson.
