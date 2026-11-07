"""api.pipeline -- Stage-based exploration pipeline package.

Public API (single entry point for external consumers):
    from api.pipeline.runner import _explore_worker
    from api.pipeline.types import ExploreContext, ExploreRuntime
"""

__all__ = ["_explore_worker"]


def __getattr__(name: str):
    if name == "_explore_worker":
        from api.pipeline.runner import _explore_worker
        return _explore_worker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
