"""S-00 owned setup baseline boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s00_setup.baseline_truth import run_baseline_truth
from api.pipeline.s00_setup.status import emit_s00_substage_status
from api.pipeline.s00_setup.vocab_prior_hints import run_vocab_prior_hints


def run_setup_baseline(ctx: Any) -> None:
    """Establish sentinel/vocab baseline before static evidence is interpreted."""
    emit_s00_substage_status(
        ctx,
        "s00_setup_baseline",
        "S-00A: Establishing setup baseline...",
        state="start",
    )
    try:
        run_baseline_truth(ctx)
        run_vocab_prior_hints(ctx)
    except Exception:
        emit_s00_substage_status(
            ctx,
            "s00_setup_baseline",
            "S-00A: Setup baseline failed.",
            state="fail",
        )
        raise
    emit_s00_substage_status(
        ctx,
        "s00_setup_baseline",
        "S-00A: Setup baseline complete.",
        state="done",
    )
