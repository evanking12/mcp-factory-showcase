from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8", errors="ignore")


def test_runner_uses_storage_public_interface() -> None:
    source = _read("api/pipeline/runner.py")
    assert "from api.infra.storage import (" not in source
    assert "from api.infra.storage_api import (" in source


def test_services_use_public_interfaces() -> None:
    chat_source = _read("api/services/chat.py")
    discovery_source = _read("api/services/discovery.py")

    assert "from api.services.executor import _execute_tool" not in chat_source
    assert "from api.services.executor_api import execute_tool as _execute_tool" in chat_source
    assert "from api.infra.storage_api import (" in chat_source
    assert "from api.infra.storage_api import (" in discovery_source
