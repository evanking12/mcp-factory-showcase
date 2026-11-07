from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ui.main import app


def test_ui_includes_lab_panel_and_run_review_surfaces() -> None:
    root = Path(__file__).resolve().parent.parent / "ui"
    server_src = (root / "main.py").read_text(encoding="utf-8")
    template_src = (root / "templates" / "index.html").read_text(encoding="utf-8")
    app_src = (root / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="lab-status-panel"' in template_src
    assert 'id="run-review"' in template_src
    assert '@app.get("/api/lab/status")' in server_src
    assert '@app.get("/api/jobs/{job_id}/verdict")' in server_src
    assert '@app.get("/api/campaigns/{campaign_id}")' in server_src
    assert '@app.get("/api/campaigns/{campaign_id}/session-snapshot")' in server_src
    assert 'id="graph-expand-btn"' in template_src
    assert 'id="campaign-expand-btn"' in template_src
    assert 'id="preview-modal"' in template_src
    assert 'id="graph-modal"' in template_src
    assert 'id="campaign-modal"' in template_src
    assert 'id="campaign-dll-actions"' in template_src
    assert 'id="campaign-drilldown-view"' in template_src
    assert 'id="campaign-reuse-view"' in template_src
    assert '"featured": _build_featured_showcase_payload()' in server_src
    assert app_src.count("await _refreshLabStatus();") >= 3


def test_ui_root_renders_index_template() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "MCP Factory" in response.text


def test_local_data_readme_points_humans_to_sessions_first() -> None:
    src = (Path(__file__).resolve().parent.parent / "local-data" / "README.md").read_text(encoding="utf-8")

    assert "machine-oriented runtime storage" in src
    assert "sessions/README.md" in src
    assert "summary.json" in src
