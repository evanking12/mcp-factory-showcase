# Proving-Lane Canary Runtime

Canonical start path:

```powershell
.\runtime\runners\proving-lane-canary\run.ps1
```

Config surface:
- Root `.env` for API key and bridge secret resolution
- Canonical local contract: [runtime/local-runtime-contract.json](../../local-runtime-contract.json)
- Implementation entrypoint: [scripts/runs/run_proving_lane_canary.py](../../../scripts/runs/run_proving_lane_canary.py)

Identity and readiness contract consumed:
- API: `http://127.0.0.1:8201`
- Bridge: `http://127.0.0.1:8090`
- The runner consumes those contracts plus strict local admission; it does not rediscover a local lane ad hoc.

Authoritative output packets:
- `lane-identity.json`
- `lane-readiness.json`
- `analyze-only-canary.json`
- `bridge-execution-canary.json`
- `lane-trust-packet.json`

Failure boundary:
- Missing packets or `canary_verdict != passed` means the bounded local lane-trust floor is not trusted enough to steer compiled-suite or stage-split runs.

Smallest honest trust claim:
- A passed canary proves the managed local lane identity/readiness contract, a deterministic analyze-only DLL submission, and bounded bridge execution. It does not prove broader generate/explore maturity or session-capture durability.
