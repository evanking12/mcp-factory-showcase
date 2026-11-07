# MCP Factory â€” Setup Guide

> Last updated: April 7, 2026

---

> Canonical `operator_start_here` runbook for MCP Factory.
> Manual per-process commands below are implementation escape hatches, not
> peer-authoritative startup surfaces.

## What Is This Project?

**MCP Factory** is a Windows-focused reverse-engineering automation tool built as a Microsoft-sponsored USF Senior Design capstone project. In plain terms:

- You hand it a Windows binary â€” a DLL, EXE, COM object, CLI tool, or GUI app â€” that has **no documentation**.
- It automatically **discovers** every callable entry point (exported functions, COM interfaces, CLI flags, GUI controls, etc.).
- It feeds those entry points to an **LLM-driven probe engine** (GPT-4o / GPT-4o-mini) that experimentally calls each function, reads what comes back, and figures out what the parameters mean.
- It then **generates a standards-compliant MCP (Model Context Protocol) server** â€” a small Python server that any AI agent (VS Code Copilot, custom GPTs, Claude, etc.) can connect to and call those functions as tools.

**Concrete example:** A legacy bank DLL called `contoso_cs.dll` ships with zero documentation. MCP Factory discovers 13 exported functions, probes them, learns that `CS_Initialize()` must be called first and returns a status code, that `CS_GetAccountBalance(account_id)` returns a balance as a double, etc. â€” then generates a working MCP server. Your AI agent can now call `CS_GetAccountBalance` through natural language.

### Architecture at a glance

```
Windows binary
      â”‚
      â–¼
[Discovery]      â€” 22+ analyzers: PE exports, COM, CLI, GUI, SQL,
                   scripting, RPC, .NET, PDB, Ghidra decompilation
      â”‚
      â–¼
[Explore Engine] â€” LLM (GPT-4o-mini) probes each function:
                   tries inputs, reads outputs, learns semantics
      â”‚
      â–¼
[Schema Synthesis] â€” enriches names, types, descriptions
      â”‚
      â–¼
[MCP Generation] â€” emits OpenAI function-calling schema + server.py
      â”‚
      â–¼
Generated MCP Server (stdio or HTTP)
  â”œâ”€â”€ VS Code Copilot connects natively
  â”œâ”€â”€ Chat UI at /api/chat with live tool execution
  â””â”€â”€ Any MCP-compatible agent works
```

### Two deployment modes

| Mode                                    | When to use                            | Requires                                                  |
| --------------------------------------- | -------------------------------------- | --------------------------------------------------------- |
| **Local CLI** (`mcp_factory.py`)        | Quick analysis of a single binary      | Python, OpenAI key                                        |
| **Local Web Stack** (API + UI + Bridge) | Full UI, job history, iterative tuning | Python, OpenAI key, local storage mode                    |


This guide focuses on getting the **local web stack** running. The CLI mode is a subset.

---

## Prerequisites

### Required on all setups

| Requirement          | Version                         | Notes                                                                                                                                                |
| -------------------- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Windows 10 or 11** | Any                             | The GUI/COM/registry analyzers require Windows. The pipeline API can run on Linux (Docker) but the bridge must be on Windows for full functionality. |
| **Python**           | 3.10+ recommended (3.8 minimum) | The `pyproject.toml` says `>=3.8` but 3.10â€“3.11 match the Docker image and avoid edge-case `match` statement / type-alias issues.                    |
| **Git**              | Any recent                      | For cloning and CI/CD                                                                                                                                |
| **OpenAI API key**   | â€”                               | `sk-...` key from https://platform.openai.com/api-keys. The explore engine calls `gpt-4o-mini` by default (~$0.03 per 13-function DLL run).          |

### Required for GUI/DLL analysis (the bridge)

| Requirement                    | Notes                                                                                                                                                                            |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Visual C++ Redistributable** | Required to load many DLLs via ctypes. Get it from https://aka.ms/vs/17/release/vc_redist.x64.exe                                                                                |
| **pywin32**                    | Installed automatically on Windows via `requirements.txt`. If the install fails, run `pip install pywin32` then `python Scripts/pywin32_postinstall.py -install` from your venv. |
| **pywinauto**                  | Installed automatically. Required only for GUI (UIA) analysis of EXEs.                                                                                                           |

### Optional (for cloud features)

| Requirement        | Notes                                                                                                                            |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------- |

| **Docker Desktop** | Only needed if you want to run the containers locally.                                                                           |
| **.NET 8 SDK**     | Only needed for `.NET Aspire` local orchestration (`dotnet run` in `aspire/AppHost`).                                            |
| **Ghidra**         | Only needed for decompilation-based discovery (`GHIDRA_HOME` env var). Optional â€” the pipeline falls back gracefully without it. |

---

## Installation

### Automated setup (recommended)

The repo ships with two scripts that handle everything:

| Script      | Purpose                                                                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `setup.ps1` | **One-time setup** â€” creates `.venv`, installs all deps, scaffolds `.env`, validates imports. Asks to launch at the end.                 |
| `start.ps1` | **Any-time launcher** â€” loads `.env`, opens each service in its own labelled window, waits for the API to be ready, and opens the dashboard unless `-NoBrowser` is set. |

```powershell
# 1. Clone (skip if you already have the repo)
git clone "REPOSITORY_URL"
cd mcp-factory

# 2. Allow scripts to run in this session (no permanent policy change)
Set-ExecutionPolicy -Scope Process Bypass

# 3. Run one-time setup â€” follow the prompts for your OpenAI key
.\setup.ps1
```

`setup.ps1` will:

1. Find Python 3.8+ on your PATH
2. Create `.venv`
3. `pip install -r requirements.txt` + `pip install -r api/requirements.txt`
4. Run the `pywin32` post-install step (if needed)
5. Scaffold `.env` â€” prompts you for your OpenAI key and storage preference
6. Create the `local-data/` directory
7. Validate critical imports, including the templating dependency used by the UI and dashboard
8. Optionally call `start.ps1` immediately

To start services on any subsequent run, use the canonical managed local lane
command:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -LaneOnly -ForceRestartApi -ForceRestartBridge
```

To validate the bounded local proving lane from a clean managed setup:

```powershell
.\runtime\validate-local-lane.ps1
```

Runtime ownership map:

- `docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md`
- Use that registry when old cloud-era notes or scripts disagree with the strict local operator path.

`start.ps1` opens up to five separate, labelled PowerShell windows:

- **Bridge :8090** â€” GUI/DLL/COM execution via ctypes and pywinauto
- **API :8201** â€” FastAPI pipeline (discovery, explore, generate)
- **UI :8080** â€” web upload wizard, chat, session viewer
- **Dashboard :8081** â€” pipeline monitor
- **API Monitor** â€” long-lived lane ownership / freshness monitor for the managed API process

Then waits up to 15 seconds for the API to be healthy and opens http://localhost:8081 in your browser unless `-NoBrowser` is set.

**Optional flags for non-default cases:**

```powershell
.\start.ps1 -NoBridge    # skip the bridge (no DLL/GUI execution)
.\start.ps1 -NoBrowser   # don't auto-open the dashboard
.\start.ps1 -NoReload    # disable uvicorn --reload
.\start.ps1 -ApiOnly     # API only, no UI or bridge
.\start.ps1 -BridgeOnly  # bridge only, no API, UI, or dashboard
.\start.ps1 -ForceRestartApi
.\start.ps1 -ForceRestartBridge
```

First-class runtime homes:

```powershell
.\runtime\api\start.ps1 -ForceRestart
.\runtime\bridge\start.ps1 -ForceRestart
.\runtime\api\check.ps1
.\runtime\bridge\check.ps1
.\runtime\runners\proving-lane-canary\run.ps1
```

---

### Manual setup (if you prefer)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r api/requirements.txt
```

Then copy `.env.example` to `.env` and fill in at minimum:

```dotenv
OPENAI_API_KEY=sk-proj-...
MCP_STORAGE_BACKEND=local
GUI_BRIDGE_URL=http://127.0.0.1:8090
GUI_BRIDGE_SECRET=local-debug
```

> **Important:** The bridge secret (`GUI_BRIDGE_SECRET` / `BRIDGE_SECRET`) must match on both the API side and the bridge server side. `local-debug` is fine for local development.

> **Local-first rule:** day-to-day setup and proving should use the managed local lane. If old notes disagree, use the local runtime contract and [LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md](docs/architecture/runtime/LOCAL-RUNTIME-OWNERSHIP-REGISTRY.md).

---

## Running the Local Web Stack

The canonical way is:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -LaneOnly -ForceRestartApi -ForceRestartBridge
```

This opens the same service windows described above and auto-opens
http://localhost:8081 once the API is healthy unless `-NoBrowser` is set. See
the [Installation](#installation) section for non-default flags.

### What each service does

| Service        | Port | Command (manual equivalent, non-default)                                                            |
| -------------- | ---- | ---------------------------------------------------------------------------------------------------- |
| GUI/DLL Bridge | 8090 | `$env:BRIDGE_SECRET="local-debug"; python scripts/bridge/gui_bridge.py`                               |
| Pipeline API   | 8201 | `uvicorn api.routes.main:app --host 0.0.0.0 --port 8201 --reload`                                     |
| Web UI         | 8080 | `$env:PIPELINE_URL="http://127.0.0.1:8201"; uvicorn ui.main:app --host 0.0.0.0 --port 8080 --reload` |
| Dashboard      | 8081 | `$env:PIPELINE_URL="http://127.0.0.1:8201"; uvicorn dashboard.main:app --host 0.0.0.0 --port 8081 --reload` |

The bridge is a Windows-only server that:

- Loads DLL functions via `ctypes`
- Walks GUI (UIA) trees with `pywinauto`
- Scans COM / registry

> **The bridge secret must match.** The API sends `X-Bridge-Key: <GUI_BRIDGE_SECRET>`; the bridge validates it against `BRIDGE_SECRET`. `start.ps1` handles this mapping automatically.

---

## Quick Sanity Check

Once all services are running via the canonical startup command or a manual
escape hatch, run a smoke test from your main terminal:

```powershell
.venv\Scripts\Activate.ps1
python scripts/mcp_smoke_test.py
```

This checks the local runtime and then exercises a small fixture path. Treat
`.\runtime\validate-local-lane.ps1` as the authoritative bounded lane gate;
this smoke test is additive.

---

## Running the CLI (no web stack needed)

For a quick single-binary analysis without starting any servers:

```powershell
.venv\Scripts\Activate.ps1

# Discover, select, generate, serve â€” all in one command
python mcp_factory.py --target C:\Windows\System32\notepad.exe --description "text editor"
```

This will:

1. Run the discovery pipeline on `notepad.exe`
2. Show an interactive TUI to select which functions to include
3. Generate an MCP server in `generated/notepad/`
4. Launch it on port 5000 and open your browser

You'll be prompted for your OpenAI API key on first run if the `.env` doesn't have one.

### Pre-built servers (no analysis needed)

The repo ships with pre-built servers for `notepad` and `calc`:

```powershell
python mcp_factory.py --serve notepad
# Open http://localhost:5000 and try:
# "Open a new file and type hello world"
```

---

## VS Code Copilot Integration

The `.vscode/mcp.json` is already configured to connect Copilot to the notepad MCP server:

```json
{
  "servers": {
    "notepad": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["${workspaceFolder}/generated/notepad/mcp_stdio.py"]
    }
  }
}
```

1. Open this repo in VS Code
2. Open Copilot Chat (`Ctrl+Alt+I`)
3. Type: `#mcp-notepad open a new file and type hello world`

Copilot will call `file_new` and `type_text` through the MCP stdio protocol â€” Notepad opens and text appears.

> To use a different generated server, add another entry to `.vscode/mcp.json` pointing to its `mcp_stdio.py`.

---

## Running Tests

The AGENTS.md specifies this as the canonical test command:

```powershell
python scripts/harness.py test -- tests/ -v --tb=short --ignore=tests/test_mcp_stdio.py
```

`test_mcp_stdio.py` is ignored because it requires a live MCP server process.

For a quick unit-only run (no API, no bridge):

```powershell
pytest tests/ -v --tb=short --ignore=tests/test_mcp_stdio.py -k "not integration"
```

After changing stage logic or stage package layout, run the tier A sync check:

```powershell
python scripts/verify_sync.py --tier A
```

If you've changed classification or finding-status paths, also run tier B:

```powershell
python scripts/verify_sync.py --tier B
```

---

## Environment Variables Reference

All configuration is read from environment variables (or your `.env` file). The authoritative source is [api/infra/config.py](api/infra/config.py).

### Required for any LLM functionality

| Variable               | Default                                  | Description                                                         |
| ---------------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| `OPENAI_API_KEY`       | _(none)_                                 | Your `sk-...` key. Required.                                        |
| `OPENAI_MODEL`         | `gpt-4o`                                 | Model for interactive chat.                                         |
| `OPENAI_CHAT_MODEL`    | _(empty â€” falls back to `OPENAI_MODEL`)_ | Override for chat only, e.g. `gpt-4o-mini`.                         |
| `OPENAI_EXPLORE_MODEL` | `gpt-4o-mini`                            | Model for the LLM probe loop. Mini is ~15x cheaper and good enough. |

### Storage

| Variable                | Default           | Description                                                                                                      |
| ----------------------- | ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| `MCP_STORAGE_BACKEND`   | `local`           | Canonical local storage mode. Use `local` for normal development and proving. |
| `MCP_LOCAL_DATA_ROOT`   | `./local-data`    | Where local-mode artifacts are stored.                                                                           |


### GUI Bridge

| Variable            | Default   | Description                                                                                                   |
| ------------------- | --------- | ------------------------------------------------------------------------------------------------------------- |
| `GUI_BRIDGE_URL`    | _(empty)_ | URL of the bridge server, e.g. `http://127.0.0.1:8090`. Without this, DLL/GUI tool execution calls will fail. |
| `GUI_BRIDGE_SECRET` | _(empty)_ | Shared secret. Must match `BRIDGE_SECRET` on the bridge process.                                              |

### Explore engine tuning

| Variable                        | Default               | Description                                                                    |
| ------------------------------- | --------------------- | ------------------------------------------------------------------------------ |
| `EXPLORE_CAP_PROFILE`           | _(none)_              | `dev` (fast), `stabilize` (balanced), `deploy` (deepest).                      |
| `EXPLORE_MAX_ROUNDS`            | _(profile-dependent)_ | Hard cap on LLM probe rounds per function.                                     |
| `EXPLORE_MAX_TOOL_CALLS`        | _(profile-dependent)_ | Hard cap on tool calls per round.                                              |
| `EXPLORE_MAX_FUNCTIONS`         | _(profile-dependent)_ | Max functions to probe in one job.                                             |
| `EXPLORE_ENABLE_GAP_RESOLUTION` | `1`                   | Set to `0` to skip the post-discovery gap-fill pass. Faster for dev iteration. |

### Security / access

| Variable           | Default          | Description                                                                                 |
| ------------------ | ---------------- | ------------------------------------------------------------------------------------------- |
| `PIPELINE_API_KEY` | _(empty = open)_ | If set, all API requests must include `X-Pipeline-Key: <value>`. Leave empty for local dev. |
| `UI_API_KEY`       | _(empty = open)_ | Same for the UI container.                                                                  |

---

## Local Storage Mode

By default (`MCP_STORAGE_BACKEND=local`), the API stores all job artifacts under `local-data/`:

```
local-data/
  jobs/
    <job-id>/
      status.json
      invocables_map.json
      findings.json
      ...
```

No cloud account needed. This is the recommended mode for local development and testing.

> If local artifact writes fail, double-check that `MCP_STORAGE_BACKEND=local` is set and that `local-data/` is writable.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'api'`

The project expects to be run from the repo root. Make sure you're in the project root directory and that your virtual environment is active:

```powershell
cd "C:\path\to\mcp-factory"
.venv\Scripts\Activate.ps1
uvicorn api.routes.main:app ...
```

### `ModuleNotFoundError: No module named 'win32api'` (pywin32)

Run the pywin32 post-install script:

```powershell
python .venv\Scripts\pywin32_postinstall.py -install
```

Then restart your terminal and re-activate the venv.

### `401 Unauthorized` from the bridge

The `GUI_BRIDGE_SECRET` environment variable on the API side doesn't match the `BRIDGE_SECRET` on the bridge side. Make sure both are set to the same string (e.g. `local-debug`).

### `Connection refused` on port 8090

The bridge isn't running. Start it in Terminal 3 (see above). If you don't need GUI/DLL analysis, you can leave the bridge stopped â€” pure discovery (PE headers, strings, Ghidra JSON) still works.

### Access violations when calling DLL functions

Most DLL functions that accept output buffer pointers (`byte *`, `undefined4 *`, etc.) will crash with an access violation because the bridge passes string literals into pointer registers instead of pre-allocated ctypes buffers. This is a known limitation documented in [docs/local-debug-workflow/README.md](docs/local-debug-workflow/README.md). The `CS_Initialize` and `CS_GetVersion` functions work fine; the rest of `contoso_cs.dll` hit this issue.

### PowerShell execution policy blocks scripts

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### `uvicorn` not found

Make sure your venv is activated: `.venv\Scripts\Activate.ps1`. Then `pip install uvicorn[standard]`.

### The UI says "Pipeline unreachable"

The UI proxies all `/api/*` calls to `PIPELINE_URL` (default: `http://127.0.0.1:8201` for local dev). If you need to override it manually, set it to `http://127.0.0.1:8201`:

```powershell
$env:PIPELINE_URL = "http://127.0.0.1:8201"
uvicorn ui.main:app --port 8080 --reload
```

---

## Full Workflow: Analyzing a DLL

Here's what the full pipeline looks like end-to-end using the web UI:

1. **Start the local stack** (API on 8201, UI on 8080, dashboard on 8081, and bridge on 8090 when needed) as described above.
2. **Open** http://localhost:8080 for the upload/chat UI or http://localhost:8081 for the dashboard review surface.
3. **Upload** â€” drag `tests/fixtures/contoso_legacy/contoso_cs.dll` onto the upload zone, or paste a path to any DLL/EXE on your machine.
4. **Discover** â€” the API runs all 22+ analyzers. PE exports are found immediately; Ghidra decompilation (if installed) gives richer type info.
5. **Select** â€” a table shows every discovered function with a confidence level (HIGH/MEDIUM/LOW). Toggle off anything you don't want in the final server.
6. **Generate** â€” emits `schema.json` and `server.py` (MCP stdio server).
7. **Chat** â€” the chat pane lets you call the generated tools live. Tool calls, arguments, and results are shown inline.

Alternatively, via CLI:

```powershell
# Full pipeline from the command line
python mcp_factory.py --target tests\fixtures\contoso_legacy\contoso_cs.dll --description "legacy customer service DLL"
```

---

## Project Layout (what actually matters)

```
mcp-factory/
â”œâ”€â”€ mcp_factory.py              # Single-command CLI entry point
â”œâ”€â”€ .env.example                # Template for secrets â€” copy to .env
â”œâ”€â”€ requirements.txt            # Root deps (discovery, tests, CLI)
â”œâ”€â”€ api/
â”‚   â”œâ”€â”€ requirements.txt        # API deps (FastAPI, OpenAI)
â”‚   â”œâ”€â”€ routes/main.py          # FastAPI app â€” all HTTP endpoints
â”‚   â”œâ”€â”€ infra/
â”‚   â”‚   â”œâ”€â”€ config.py           # All env var reads â€” single source of truth
â”‚   â”‚   â”œâ”€â”€ storage.py          # Local artifact storage layer
â”‚   â”‚   â”œâ”€â”€ worker.py           # Background job queue worker
â”‚   â”‚   â””â”€â”€ telemetry.py        # OpenAI client + local telemetry hooks
â”‚   â”œâ”€â”€ pipeline/               # 8-stage explore pipeline (s00 through s07)
â”‚   â”‚   â””â”€â”€ core/               # Contracts, status taxonomy, compatibility
â”‚   â””â”€â”€ services/
â”‚       â”œâ”€â”€ executor.py         # Dispatches tool calls (DLL/CLI/GUI/bridge)
â”‚       â”œâ”€â”€ chat.py             # Agentic SSE chat loop
â”‚       â””â”€â”€ generate.py         # MCP schema + server generation
â”œâ”€â”€ ui/
â”‚   â””â”€â”€ main.py                 # Web UI (FastAPI, proxies to API)
â”œâ”€â”€ src/
â”‚   â”œâ”€â”€ discovery/              # 22+ source-type analyzers
â”‚   â”‚   â”œâ”€â”€ exports.py          # PE export table (pefile)
â”‚   â”‚   â”œâ”€â”€ gui_analyzer.py     # UIA tree walk (pywinauto)
â”‚   â”‚   â”œâ”€â”€ com_scan.py         # COM CLSID scan
â”‚   â”‚   â”œâ”€â”€ ghidra_analyzer.py  # Ghidra decompilation bridge
â”‚   â”‚   â””â”€â”€ ...                 # cli, dotnet, pdb, sql, script, etc.
â”‚   â””â”€â”€ generation/
â”‚       â””â”€â”€ section4_generate_server.py  # MCP server template emitter
â”œâ”€â”€ scripts/
â”‚   â”œâ”€â”€ bridge/
â”‚   â”‚   â””â”€â”€ gui_bridge.py       # Windows bridge server (DLL/GUI/COM calls)
â”‚   â”œâ”€â”€ harness.py              # Test harness runner
â”‚   â”œâ”€â”€ verify_sync.py          # Stage/contract sync checker (tier A/B)
â”‚   â””â”€â”€ mcp_smoke_test.py       # Quick connectivity smoke test
â”œâ”€â”€ tests/
â”‚   â””â”€â”€ fixtures/contoso_legacy/ # contoso_cs.dll â€” the demo target DLL
â”œâ”€â”€ generated/                  # Pre-built MCP servers (notepad, calc)
â”œâ”€â”€ local-data/                 # Local job artifact storage (auto-created)
â””â”€â”€ .vscode/mcp.json            # VS Code Copilot MCP configuration
```

---

## Cost Reference

Everything uses pay-per-token pricing. Rough estimates:

| Operation                    | Model       | Approx. cost |
| ---------------------------- | ----------- | ------------ |
| Single chat message          | gpt-4o-mini | ~$0.002      |
| Full 13-function DLL explore | gpt-4o-mini | ~$0.03       |
| Full 13-function DLL explore | gpt-4o      | ~$0.50       |

Set `OPENAI_EXPLORE_MODEL=gpt-4o-mini` and `OPENAI_CHAT_MODEL=gpt-4o-mini` during development. Switch the explore model to `gpt-4o` only for final quality validation runs.

---

## What the Original README Doesn't Tell You

The existing README is written from the perspective of someone who already knows the system. Here are the gaps:

1. **`MCP_STORAGE_BACKEND=local` is already in `.env.example`** â€” if the local lane is behaving oddly, confirm it is still present in your active `.env` and shell session.
2. **The bridge is a separate runtime system**, not a library import. Start it via `.\runtime\bridge\start.ps1` or the combined launcher. Without it, the `/execute` endpoint returns 503.
3. **`pywin32` needs a post-install step** on some systems. If you get `win32api` import errors, see the troubleshooting section above.
4. **The `.env` file must be loaded into the shell before starting uvicorn** â€” uvicorn doesn't auto-load `.env`. The `python-dotenv` package is used inside the app, but only after startup. Set vars in your shell session first using the `Get-Content` snippet above, or use `dotenv run` if you install it.
5. **The local UI and dashboard should point at the stable API on `8201`**. If you launch them manually, set `PIPELINE_URL=http://127.0.0.1:8201` so uploads and dashboard review use the same trusted lane.
6. **The generated notepad/calc servers in `generated/` require their own `.env`** with an OpenAI key. `mcp_factory.py` handles this automatically, but if you copy a generated server somewhere else, create a `.env` next to `mcp_stdio.py`.

---

## Contact / Issues

- GitHub Issues: the Issues tab of this repository
- Team: Evan King (lead), Layalie AbuOleim, Caden Spokas, Thinh Nguyen
- Sponsor: Microsoft (USF CSE Senior Design Capstone, Spring 2026)


