"""S-00 setup orchestration over owned setup seams."""

from __future__ import annotations

from api.pipeline.s00_setup.baseline_truth import run_baseline_truth  # noqa: F401
from api.pipeline.s00_setup.calibration import (  # noqa: F401
    _calibrate_sentinels,
    _name_sentinel_candidates,
    _parse_hint_error_codes,
)
from api.pipeline.s00_setup.admission_handoff import run_admission_handoff
from api.pipeline.s00_setup.s01_handoff_packet import build_s01_handoff_packet  # noqa: F401
from api.pipeline.s00_setup.setup_baseline import run_setup_baseline
from api.pipeline.s00_setup.static_analysis import _run_phase_0_static  # noqa: F401
from api.pipeline.s00_setup.static_evidence import run_static_evidence
from api.pipeline.s00_setup.static_surface_extraction import run_static_surface_extraction  # noqa: F401
from api.pipeline.s00_setup.vocab_prior_hints import run_vocab_prior_hints  # noqa: F401
from api.pipeline.s00_setup.vocab_seed import _run_phase_0_vocab_seed  # noqa: F401
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s00_setup import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s00_setup import context as _stage_context  # noqa: F401
from api.pipeline.s00_setup import session_artifacts as _session_artifacts  # noqa: F401

_run_phase_05_calibrate = run_baseline_truth


def run_s00(ctx) -> None:
    """Run the S-00 parent stage through setup baseline only."""
    run_setup_baseline(ctx)
