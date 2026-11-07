"""Compatibility wrapper for the S-00 static evidence boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s00_setup.static_evidence import run_static_evidence


def run_static_surface_extraction(ctx: Any) -> None:
    """Preserve the older seam name while routing through static evidence."""
    run_static_evidence(ctx)
