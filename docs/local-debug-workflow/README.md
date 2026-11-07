# Local Debug Workflow

> Specialist workflow only.
> Do not treat this file as the default operator path.
> The canonical operator front door is [SETUP.md](../../SETUP.md).

Use this workflow when you want to run the chat + invocation loop locally with no remote services, no containers, and no bridge server.

## Inputs

You can use:

- a Ghidra JSON with top-level `tools`
- an `invocables_map.json` captured from an existing local pipeline job

## Flow

1. capture or prepare the invocable input
2. point the runner at the target DLL and JSON payload
3. execute the local debug loop

Example:

```powershell
python scripts/runs/run_local.py --dll "C:/path/contoso_cs.dll" --json "C:/path/invocables_map.json"
```

## Artifact Sources

| Artifact | Expected Shape | Source |
|---|---|---|
| Pipeline invocables map | `"invocables"` | Local artifact root `{job_id}/invocables_map.json` |
| Ghidra tool export | `"tools"` | Local discovery output |

## Notes

- local artifact storage is required for job-state-backed reuse
- the standalone local debug runner itself needs no cloud services
