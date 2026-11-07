# Contributing to MCP Factory

Normal development, proving, and validation should use the managed local lane on `http://127.0.0.1:8201` and `http://127.0.0.1:8090`.

## Development Setup

```powershell
git clone "REPOSITORY_URL"
cd mcp-factory
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r api/requirements.txt
```

Runtime checks:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -LaneOnly -ForceRestartApi -ForceRestartBridge
powershell -ExecutionPolicy Bypass -File .\runtime\validate-local-lane.ps1
```

## Workflow

- create a feature branch from `main`
- make bounded changes
- run the relevant local validation and proving commands
- update docs when operator behavior or contracts change

## Commit Guidance

Use clear reviewable commits:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation only
- `test:` tests
- `refactor:` structure change without intended behavior change
- `chore:` maintenance

## Testing

At minimum, run the checks that match the surfaces you touched. Common examples:

```powershell
python -m pytest tests/test_runtime_contract.py tests/test_lane_trust_contract_routes.py -q
python scripts/verify_sync.py --tier A
```

For proving work, prefer the managed local lane and the repo’s bounded proving scripts over ad hoc manual testing.

## Project Structure

```text
mcp-factory/
├── api/                    # FastAPI backend
├── ui/                     # FastAPI web UI
├── runtime/                # canonical runtime wrappers and checks
├── sessions/               # proving scripts, test data, run archives
├── scripts/                # automation and runner entrypoints
├── tests/                  # pytest tests
└── docs/                   # operator and architecture docs
```
