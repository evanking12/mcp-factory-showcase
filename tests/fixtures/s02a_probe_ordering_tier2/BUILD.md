# S-02A Probe Ordering Tier 2 Fixture

This fixture is a medium-pressure compiled DLL for the
`S-02A probe_ordering` ordering-quality breakpoint.

It intentionally keeps callable behavior simple and deterministic. Pressure
comes from init-like, read-like, write-like, and distractor exported names that
should be ordered into a useful probe plan before execution begins.

The fixture is not committed as a binary. Build it with:

```powershell
.\build.ps1 -OutputRoot .tmp\s02a-probe-ordering-tier2
```

Expected output:

```text
.tmp\s02a-probe-ordering-tier2\bin\s02a_probe_ordering_tier2.dll
```

