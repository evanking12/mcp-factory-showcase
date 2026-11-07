from pathlib import Path

from codex.scripts import run_targeted


def test_run_targeted_uses_analyze_path_for_local_dll(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "sample.dll"
    dll_path.write_bytes(b"dll")
    calls: list[tuple[str, str]] = []

    def fake_api(base: str, method: str, path: str, body: dict | None = None) -> dict:
        calls.append((method, path))
        if path == "/api/analyze-path":
            return {"job_id": "job-123"}
        if path == "/api/jobs/job-123/explore":
            return {"ok": True}
        if path == "/api/findings/job-123":
            return {"findings": []}
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(run_targeted, "_api", fake_api)
    monkeypatch.setattr(run_targeted, "_poll_job", lambda *args, **kwargs: {"explore_phase": "done"})
    monkeypatch.setattr(run_targeted, "_poll_analysis_job", lambda *args, **kwargs: {"status": "done"})

    result = run_targeted.run_targeted(
        ["CP_ProcessPurchase"],
        "test hypothesis",
        prior_job_id="prior-1",
        api_url="http://localhost:8201",
        dll_path=str(dll_path),
    )

    assert result["job_id"] == "job-123"
    assert calls[0] == ("POST", "/api/analyze-path")
