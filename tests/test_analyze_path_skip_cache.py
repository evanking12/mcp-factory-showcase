from __future__ import annotations

from pathlib import Path


def test_analyze_path_forwards_skip_cache_to_worker() -> None:
    source = Path("api/routes/main.py").read_text(encoding="utf-8", errors="replace")

    assert 'skip_cache = _as_bool(body.get("skip_cache"), False)' in source
    assert '"skip_cache_requested": skip_cache' in source
    assert "_analyze_worker(job_id, target, hints, target.name, None, skip_cache)" in source
