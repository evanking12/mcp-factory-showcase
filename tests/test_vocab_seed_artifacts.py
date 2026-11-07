from __future__ import annotations

import json
from types import SimpleNamespace

from api.pipeline.s00_setup import vocab_seed


def test_run_phase_0_vocab_seed_persists_pre_probe_vocab(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(vocab_seed, "_download_blob", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(
        vocab_seed,
        "_get_job_status",
        lambda _job_id: {
            "hints": "Use CUST-001 and code 0xFFFFFFFB",
            "use_cases": "contoso payments local replay control",
        },
    )
    monkeypatch.setattr(vocab_seed, "_parse_hint_error_codes", lambda _hints: {0xFFFFFFFB: "write denied"})
    monkeypatch.setattr(
        vocab_seed,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploaded.setdefault(blob_name, data),
    )

    ctx = SimpleNamespace(
        job_id="job-vocab",
        sentinels={},
        vocab={},
        use_cases_text="",
    )

    vocab_seed._run_phase_0_vocab_seed(ctx)  # noqa: SLF001

    assert "job-vocab/vocab.json" in uploaded
    payload = json.loads(uploaded["job-vocab/vocab.json"].decode("utf-8"))
    assert payload["id_formats"] == ["CUST-001"]
    assert payload["notes"] == "User description: Use CUST-001 and code 0xFFFFFFFB"
    assert payload["user_context"] == "contoso payments local replay control"
    assert payload["error_codes"]["0xFFFFFFFB"] == "write denied"
