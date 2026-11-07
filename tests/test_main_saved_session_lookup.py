from __future__ import annotations

import json


def test_find_saved_session_dir_discovers_late_written_session(tmp_path, monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_SESSIONS_ROOT", tmp_path)
    main._SAVED_SESSION_DIR_CACHE.clear()

    assert main._find_saved_session_dir("job-lookup") is None

    session_dir = tmp_path / "saved-session"
    session_dir.mkdir()
    (session_dir / "kpi_run.json").write_text(
        json.dumps({"job_id": "job-lookup"}),
        encoding="utf-8",
    )

    assert main._find_saved_session_dir("job-lookup") == session_dir


def test_find_saved_session_dir_discovers_late_written_session_meta_fallback(tmp_path, monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_SESSIONS_ROOT", tmp_path)
    main._SAVED_SESSION_DIR_CACHE.clear()

    assert main._find_saved_session_dir("job-meta") is None

    session_dir = tmp_path / "saved-meta-session"
    session_dir.mkdir()
    (session_dir / "session-meta.json").write_text(
        json.dumps({"job_id": "job-meta"}),
        encoding="utf-8",
    )

    assert main._find_saved_session_dir("job-meta") == session_dir


def test_find_saved_session_dir_reuses_positive_cache(tmp_path, monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_SESSIONS_ROOT", tmp_path)
    main._SAVED_SESSION_DIR_CACHE.clear()

    session_dir = tmp_path / "cached-session"
    session_dir.mkdir()
    kpi_path = session_dir / "kpi_run.json"
    kpi_path.write_text(json.dumps({"job_id": "job-cache"}), encoding="utf-8")

    read_calls = 0

    def _counting_read(path):
        nonlocal read_calls
        read_calls += 1
        return json.loads(path.read_text(encoding="utf-8"))

    monkeypatch.setattr(main, "_read_json_if_exists", _counting_read)

    assert main._find_saved_session_dir("job-cache") == session_dir
    first_read_calls = read_calls
    assert first_read_calls >= 1

    assert main._find_saved_session_dir("job-cache") == session_dir
    assert read_calls == first_read_calls
