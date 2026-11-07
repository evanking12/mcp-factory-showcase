from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_start_ps1_uses_venv_python_module_for_api_uvicorn() -> None:
    text = (REPO_ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "$EscVenvPy  = $VenvPy -replace" in text
    assert "& '$EscVenvPy' -m uvicorn api.routes.main:app --host 0.0.0.0 --port $apiPort $reloadArg" in text
    assert "& '$escUvicorn' api.routes.main:app --host 0.0.0.0 --port $apiPort $reloadArg" not in text
