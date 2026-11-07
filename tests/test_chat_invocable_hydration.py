from __future__ import annotations


def test_hydrate_invocables_primes_cache_on_storage_fallback(monkeypatch) -> None:
    import api.services.chat as chat

    captured: list[tuple[str, dict[str, dict[str, object]]]] = []
    loaded = {"FnA": {"name": "FnA", "description": "from-storage"}}

    monkeypatch.setattr(chat, "_get_invocables_map", lambda job_id: dict(loaded))
    monkeypatch.setattr(
        chat,
        "_register_invocables",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("hydration fallback should not register or persist invocables")
        ),
    )
    monkeypatch.setattr(
        chat,
        "_prime_invocables_cache",
        lambda job_id, invocables_map: captured.append((job_id, dict(invocables_map))),
    )

    invocables, tools, inv_map = chat._hydrate_invocables_and_tools(
        job_id="job-1",
        invocables=[],
        tools=[],
    )

    assert invocables == [{"name": "FnA", "description": "from-storage"}]
    assert [tool["function"]["name"] for tool in tools] == ["FnA"]
    assert inv_map == loaded
    assert captured == [("job-1", loaded)]
