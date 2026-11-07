from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import capture


def test_should_skip_snapshot_defaults_to_blob_only_for_localhost(monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_CAPTURE_BLOB_ONLY", raising=False)
    assert capture._should_skip_snapshot("http://127.0.0.1:8201") is True  # noqa: SLF001
    assert capture._should_skip_snapshot("http://localhost:8201") is True  # noqa: SLF001
    assert capture._should_skip_snapshot("https://example.com") is False  # noqa: SLF001


def test_should_skip_snapshot_honors_env_override(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_CAPTURE_BLOB_ONLY", "0")
    assert capture._should_skip_snapshot("http://127.0.0.1:8201") is False  # noqa: SLF001
    monkeypatch.setenv("HARNESS_CAPTURE_BLOB_ONLY", "1")
    assert capture._should_skip_snapshot("https://example.com") is True  # noqa: SLF001
