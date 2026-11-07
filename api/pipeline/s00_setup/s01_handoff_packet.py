"""Compatibility wrapper for the S-00 admission handoff packet producer."""

from __future__ import annotations

from typing import Any

from api.pipeline.s00_setup.admission_handoff import run_admission_handoff


def build_s01_handoff_packet(ctx: Any) -> dict[str, Any] | None:
    """Preserve the legacy producer name while routing through admission handoff."""
    return run_admission_handoff(ctx)
