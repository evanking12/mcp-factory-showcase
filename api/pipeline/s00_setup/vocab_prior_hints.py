"""S-00 owned vocabulary and prior-hints seeding seam."""

from __future__ import annotations

from typing import Any

from api.pipeline.s00_setup.vocab_seed import _run_phase_0_vocab_seed


def run_vocab_prior_hints(ctx: Any) -> None:
    """Run the current vocab/prior-hints implementation through an owned seam."""
    _run_phase_0_vocab_seed(ctx)
