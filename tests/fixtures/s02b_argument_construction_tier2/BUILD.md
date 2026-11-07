# S-02B Argument Construction Tier 2 Fixture

This fixture is a medium-pressure compiled DLL for the
`S-02B invocation_execution` argument-construction breakpoint.

It keeps behavior deterministic and simple. Pressure comes from multiple typed
integer parameters whose expected values are selected by S-02B from parameter
names and descriptions. The functions encode the received arguments in their
return values so the test can verify construction without claiming broader
lane or semantic correctness.

The fixture is not committed as a binary. Build it with:

```powershell
.\build.ps1 -OutputRoot .tmp\s02b-argument-construction-tier2
```

Expected output:

```text
.tmp\s02b-argument-construction-tier2\bin\s02b_argument_construction_tier2.dll
```

