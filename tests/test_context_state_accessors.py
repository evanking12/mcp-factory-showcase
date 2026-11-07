from __future__ import annotations

from api.pipeline.core.types import ExploreContext, ExploreRuntime


def _ctx() -> ExploreContext:
    return ExploreContext(
        job_id="job-ctx",
        runtime=ExploreRuntime(),
        client=object(),
        model="gpt-test",
    )


def test_explored_counter_accessors() -> None:
    ctx = _ctx()
    assert ctx.explored_count() == 0
    assert ctx.increment_explored() == 1
    assert ctx.increment_explored(2) == 3
    assert ctx.explored_count() == 3


def test_mc_decision_accessors() -> None:
    ctx = _ctx()
    assert ctx.latest_mc_decision("mc3-post-reconcile") == {}
    ctx.persist_mc_decision("mc3-post-reconcile", {"action": "retry"})
    assert ctx.latest_mc_decision("mc3-post-reconcile") == {"action": "retry"}
