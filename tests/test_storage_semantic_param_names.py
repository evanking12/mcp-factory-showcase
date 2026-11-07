from __future__ import annotations

import json

from api.infra import storage


def _seed_invocable(job_id: str) -> None:
    storage._JOB_INVOCABLE_MAPS[job_id] = {
        "SP_RecordReleaseReceipt": {
            "name": "SP_RecordReleaseReceipt",
            "description": "Records a release receipt for a transaction.",
            "parameters": [
                {"name": "param_1", "type": "char *", "description": "Parameter 1"},
                {"name": "param_2", "type": "char *", "description": "Parameter 2"},
                {"name": "param_3", "type": "char *", "description": "Parameter 3"},
                {"name": "param_4", "type": "uint", "description": "Parameter 4"},
            ],
        }
    }


def test_patch_invocable_derives_semantic_param_names_from_descriptions(monkeypatch) -> None:
    job_id = "job-semantic-param-names"
    _seed_invocable(job_id)

    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda *args, **kwargs: json.dumps({"component": "test-component"}).encode("utf-8"),
    )

    import api.services.generate as generate

    monkeypatch.setattr(generate, "run_generate", lambda *args, **kwargs: {"ok": True})

    try:
        result = storage._patch_invocable(
            job_id,
            "SP_RecordReleaseReceipt",
            {
                "parameters": [
                    {
                        "name": "param_1",
                        "description": "Identifier for the commit, expected to be a string representing the commit ID.",
                    },
                    {
                        "name": "param_2",
                        "description": "Session identifier for the operator, expected to be a string representing the operator session ID.",
                    },
                    {
                        "name": "param_3",
                        "description": "Receipt identifier for the recorded release, expected to be a string representing the receipt ID.",
                    },
                    {
                        "name": "param_4",
                        "description": "Length of the receipt buffer, expected to be an integer indicating the size of the buffer.",
                    },
                ]
            },
        )
        params = storage._JOB_INVOCABLE_MAPS[job_id]["SP_RecordReleaseReceipt"]["parameters"]
        names = [param["name"] for param in params]

        assert names == [
            "commit_id",
            "operator_session_id",
            "receipt_id",
            "receipt_buffer_len",
        ]
        assert "no param renames" not in result
    finally:
        storage._JOB_INVOCABLE_MAPS.pop(job_id, None)


def test_patch_invocable_derives_names_from_audit_trace_backfill_descriptions(monkeypatch) -> None:
    job_id = "job-audit-trace-semantic-param-names"
    _seed_invocable(job_id)

    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda *args, **kwargs: json.dumps({"component": "test-component"}).encode("utf-8"),
    )

    import api.services.generate as generate

    monkeypatch.setattr(generate, "run_generate", lambda *args, **kwargs: {"ok": True})

    try:
        storage._patch_invocable(
            job_id,
            "SP_RecordReleaseReceipt",
            {
                "parameters": [
                    {
                        "name": "param_1",
                        "description": 'Commit identifier (must start with "sp-commit-"). Example: "sp-commit-GDG-SM-RED".',
                    },
                    {
                        "name": "param_2",
                        "description": 'Session token for the operator (must start with "sp-operator-"). Example: "sp-operator-easy01-operator-session".',
                    },
                    {
                        "name": "param_3",
                        "description": "Output buffer - receives result data (omit from call; auto-allocated)",
                    },
                    {
                        "name": "param_4",
                        "description": "Length of the receipt identifier. Example: 64.",
                    },
                ]
            },
        )
        params = storage._JOB_INVOCABLE_MAPS[job_id]["SP_RecordReleaseReceipt"]["parameters"]
        names = [param["name"] for param in params]

        assert names == [
            "commit_id",
            "operator_session_token",
            "param_3",
            "receipt_id_len",
        ]
    finally:
        storage._JOB_INVOCABLE_MAPS.pop(job_id, None)


def test_patch_invocable_avoids_duplicate_semantic_param_names(monkeypatch) -> None:
    job_id = "job-audit-trace-duplicate-semantic-param-names"
    _seed_invocable(job_id)

    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda *args, **kwargs: json.dumps({"component": "test-component"}).encode("utf-8"),
    )

    import api.services.generate as generate

    monkeypatch.setattr(generate, "run_generate", lambda *args, **kwargs: {"ok": True})

    try:
        storage._patch_invocable(
            job_id,
            "SP_RecordReleaseReceipt",
            {
                "parameters": [
                    {
                        "name": "param_1",
                        "description": "Receipt identifier for the release.",
                    },
                    {
                        "name": "param_2",
                        "description": "Session token for the operator.",
                    },
                    {
                        "name": "param_3",
                        "description": "Receipt identifier for the recorded release.",
                    },
                    {
                        "name": "param_4",
                        "description": "Length of the receipt identifier. Example: 64.",
                    },
                ]
            },
        )
        params = storage._JOB_INVOCABLE_MAPS[job_id]["SP_RecordReleaseReceipt"]["parameters"]
        names = [param["name"] for param in params]

        assert len(names) == 4
        assert len(set(names)) == 4
        assert names[0] == "receipt_id"
        assert names[2] == "param_3"
    finally:
        storage._JOB_INVOCABLE_MAPS.pop(job_id, None)


def test_run_generate_preserves_unique_schema_properties_for_duplicate_param_names(monkeypatch) -> None:
    from api.services import generate

    uploaded: dict[str, dict] = {}
    registered: dict[str, list[dict]] = {}

    def _fake_upload(_container, blob_name, payload):
        if blob_name.endswith("mcp_schema.json"):
            uploaded["schema"] = json.loads(payload.decode("utf-8"))
        return "ok"

    def _fake_register(job_id, selected):
        registered[job_id] = selected

    monkeypatch.setattr(generate, "_upload_to_blob", _fake_upload)
    monkeypatch.setattr(generate, "_register_invocables", _fake_register)

    result = generate.run_generate(
        {
            "job_id": "job-duplicate-schema-param-names",
            "selected": [
                {
                    "name": "SP_RecordReleaseReceipt",
                    "description": "Records a release receipt.",
                    "parameters": [
                        {"name": "receipt_id", "type": "char *"},
                        {"name": "operator_session_token", "type": "char *"},
                        {"name": "receipt_id", "type": "char *"},
                        {"name": "receipt_buffer_len", "type": "uint"},
                    ],
                }
            ],
        }
    )

    schema = uploaded["schema"]
    params = schema["tools"][0]["function"]["parameters"]
    assert result["job_id"] == "job-duplicate-schema-param-names"
    assert list(params["properties"]) == [
        "receipt_id",
        "operator_session_token",
        "receipt_id_2",
        "receipt_buffer_len",
    ]
    assert params["required"] == [
        "receipt_id",
        "operator_session_token",
        "receipt_id_2",
        "receipt_buffer_len",
    ]
    registered_names = [
        param["name"]
        for param in registered["job-duplicate-schema-param-names"][0]["parameters"]
    ]
    assert registered_names == [
        "receipt_id",
        "operator_session_token",
        "receipt_id_2",
        "receipt_buffer_len",
    ]


def test_patch_invocable_keeps_generic_names_when_descriptions_lack_specific_semantics(monkeypatch) -> None:
    job_id = "job-generic-param-names"
    _seed_invocable(job_id)

    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda *args, **kwargs: json.dumps({"component": "test-component"}).encode("utf-8"),
    )

    import api.services.generate as generate

    monkeypatch.setattr(generate, "run_generate", lambda *args, **kwargs: {"ok": True})

    try:
        storage._patch_invocable(
            job_id,
            "SP_RecordReleaseReceipt",
            {
                "parameters": [
                    {"name": "param_1", "description": "Input string parameter."},
                    {"name": "param_2", "description": "Output buffer."},
                    {"name": "param_3", "description": "Parameter 3"},
                    {"name": "param_4", "description": "Integer parameter."},
                ]
            },
        )
        params = storage._JOB_INVOCABLE_MAPS[job_id]["SP_RecordReleaseReceipt"]["parameters"]

        assert [param["name"] for param in params] == [
            "param_1",
            "param_2",
            "param_3",
            "param_4",
        ]
    finally:
        storage._JOB_INVOCABLE_MAPS.pop(job_id, None)
