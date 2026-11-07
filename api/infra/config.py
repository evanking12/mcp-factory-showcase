"""Shared local-first runtime configuration for MCP Factory."""

from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"

# The repo is local-first only. Non-local storage backends are no longer
# supported, so stale env values cannot steer runtime behavior.
STORAGE_BACKEND = "local"

# Direct OpenAI is the only supported model-provider path in this repo.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "")
OPENAI_EXPLORE_MODEL = os.getenv("OPENAI_EXPLORE_MODEL", "gpt-4o-mini")

# Maximum number of tool definitions sent in a single OpenAI API call.
# When total tools <= OPENAI_MAX_TOOLS the full set is sent with no filtering.
OPENAI_MAX_TOOLS = int(os.getenv("OPENAI_MAX_TOOLS", "60"))

# Windows GUI bridge (optional).
GUI_BRIDGE_URL = os.getenv("GUI_BRIDGE_URL", "").rstrip("/")
GUI_BRIDGE_SECRET = os.getenv("GUI_BRIDGE_SECRET", "")

# Pipeline API key guard (optional).
PIPELINE_API_KEY = os.getenv("PIPELINE_API_KEY", "")

# Storage layout.
UPLOAD_CONTAINER = "uploads"
ARTIFACT_CONTAINER = "artifacts"
ANALYSIS_QUEUE = "analysis-jobs"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DISCOVERY_DIR = _REPO_ROOT / "src" / "discovery"
LOCAL_DATA_ROOT = Path(
    os.getenv("MCP_LOCAL_DATA_ROOT", str(_REPO_ROOT / "local-data"))
).resolve()
SRC_DISCOVERY_DIR = Path(
    os.getenv("SRC_DISCOVERY_DIR", str(_DEFAULT_DISCOVERY_DIR))
).resolve()

# Generation module (P1: MCP SDK server emit).
_GEN_DIR = Path(__file__).parent.parent / "src" / "generation"
if str(_GEN_DIR) not in sys.path:
    sys.path.insert(0, str(_GEN_DIR))

# Allowed base paths for /api/analyze-path.
_SAFE_PATH_PREFIXES: tuple[Path, ...] = (
    Path(tempfile.gettempdir()),
    Path("/app"),
    Path("C:/"),
    Path("D:/"),
)
