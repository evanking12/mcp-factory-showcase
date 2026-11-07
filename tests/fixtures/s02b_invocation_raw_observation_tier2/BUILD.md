# S-02B Raw Observation Tier 2 Fixture

This fixture is a medium-pressure compiled DLL for the
`S-02B invocation_execution` raw-observation breakpoint.

It intentionally keeps callable behavior simple and deterministic. Pressure
comes from multiple exported statuses and one typed argument-bearing call, not
from lane failure, model behavior, or cross-DLL dependencies.

The fixture is not committed as a binary. Build it with:

```powershell
.\build.ps1 -OutputRoot .tmp\s02b-invocation-tier2
```

Expected output:

```text
.tmp\s02b-invocation-tier2\bin\s02b_invocation_raw_observation_tier2.dll
```
