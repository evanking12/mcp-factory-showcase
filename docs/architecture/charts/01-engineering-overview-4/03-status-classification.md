# Status And Classification

Primary code anchor:

- `api/pipeline/core/finding_status.py`

```mermaid
flowchart TD
    A["Probe result arrives<br/>return_value plus sentinel meaning"] --> B{"return_value == 0?"}
    B -- "yes" --> VS["verified_success"]
    B -- "no" --> C["Resolve sentinel meaning from explicit meaning or sentinel table"]
    C --> D{"Meaning matches functional precondition pattern?"}
    D -- "yes" --> FP["functional_precondition_unmet"]
    D -- "no" --> F["failure"]

    U["Legacy or mixed-epoch status text"] --> N["normalize_status"]
    N --> VS
    N --> FP
    N --> IS["inferred_success"]
    N --> F
    N --> UNK["unknown"]
```

Canonical status order:

```mermaid
flowchart LR
    VS["verified_success"] --> FP["functional_precondition_unmet"] --> IS["inferred_success"] --> F["failure"] --> U["unknown"]
```

Interpretation:

- Runtime success is the strongest direct claim.
- Procedural success is not automatically reusable truth; semantically implausible
  working calls can be demoted before they become seed-eligible.
- Functional-precondition failures are treated as a stronger, more informative result than generic failure.
- Normalization exists so older capture formats remain comparable.
- Campaign attribution now also carries a package-carryover audit lane for
  regressed functions, so local-green/package-red mismatches can be upgraded
  from a blocker family into the first broken handoff and first broken
  invariant when local proof artifacts exist.
