from __future__ import annotations

import asyncio


def test_report_route_uses_public_invocables_map(monkeypatch) -> None:
    import api.routes.routes_session as routes_session

    uploaded: list[tuple[str, str]] = []

    monkeypatch.setattr(
        routes_session,
        "get_invocables_map",
        lambda job_id: {
            "WF_GenerateReport": {
                "name": "WF_GenerateReport",
                "description": "Generate the operator report",
                "parameters": [],
            }
        },
    )
    monkeypatch.setattr(routes_session, "_load_findings", lambda job_id: [])
    monkeypatch.setattr(
        routes_session,
        "_upload_to_blob",
        lambda container, blob_name, data: uploaded.append((container, blob_name)),
    )

    response = asyncio.run(routes_session.get_report("job-6"))
    body = response.body.decode("utf-8")

    assert "WF_GenerateReport" in body
    assert uploaded == [(routes_session.ARTIFACT_CONTAINER, "job-6/report.md")]
