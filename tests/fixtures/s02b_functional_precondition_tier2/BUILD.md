# S-02B Functional Precondition Tier 2 Fixture

This fixture is a medium-pressure compiled DLL for the
`S-02B invocation_execution` functional-precondition breakpoint.

It keeps behavior deterministic and stateful. Pressure comes from a simple
blocked-before-init / allowed-after-init sequence with write-like exports and
a distractor read export. The blocked return is a known not-initialized
sentinel, which lets S-02B preserve the observation without claiming final
semantics.

The fixture is not committed as a binary. Build it with:

```powershell
.\build.ps1 -OutputRoot .tmp\s02b-functional-precondition-tier2
```

Expected output:

```text
.tmp\s02b-functional-precondition-tier2\bin\s02b_functional_precondition_tier2.dll
```
