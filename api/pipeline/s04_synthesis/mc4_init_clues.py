"""api.pipeline.s04_synthesis.mc4_init_clues -- MC-4: post-synthesis coordinator."""

from __future__ import annotations

import logging
import re as _re

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _download_blob
from api.pipeline.core.helpers import _persist_mc_decision
from api.pipeline.s01_unlock.unlock_helpers import (
    _build_write_args_from_vocab,
    _targeted_unlock_attempt,
)

logger = logging.getLogger("mcp_factory.api")


def _mc4_post_synthesis(ctx) -> None:
    """Parse synthesis doc for init sequence clues the LLM may have inferred."""
    if ctx.unlock_result.get("unlocked"):
        return

    decision = {"trigger": "mc4-post-synthesis", "analysis": {}, "action": None, "result": None}

    try:
        api_ref = ""
        try:
            raw = _download_blob(ARTIFACT_CONTAINER, f"{ctx.job_id}/api_reference.md")
            api_ref = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        except Exception:
            decision["analysis"]["api_reference"] = "unavailable"
            _persist_mc_decision(ctx, "mc4-post-synthesis", decision)
            return

        decision["analysis"]["api_ref_length"] = len(api_ref)

        init_mode_matches = _re.findall(
            r"(?:CS_Initialize|init\w*)\s*\(\s*(?:mode\s*=\s*|param_1\s*=\s*)?(\d+)\s*\)",
            api_ref, _re.I,
        )
        prose_matches = _re.findall(
            r"mode\s+(\d+)\s+(?:for|enables?|activates?|unlocks?|allows?)\s+(?:write|payment|transaction)",
            api_ref, _re.I,
        )
        all_suggested_modes = list(dict.fromkeys(
            [int(m) for m in init_mode_matches + prose_matches]
        ))

        if all_suggested_modes:
            decision["analysis"]["suggested_modes"] = all_suggested_modes
            decision["analysis"]["source"] = "synthesis document mentioned specific init modes"
            decision["action"] = "try_synthesis_suggested_modes"

            init_names = [inv["name"] for inv in ctx.invocables
                          if _re.search(r"init(ializ)?", inv["name"], _re.I)]
            init_seqs = []
            for mode in all_suggested_modes:
                for init_fn in init_names:
                    init_seqs.append({"fn": init_fn, "args": {"param_1": mode}})

            write_args = _build_write_args_from_vocab(ctx)
            if _targeted_unlock_attempt(ctx, init_seqs, write_args, "mc4-post-synthesis"):
                decision["result"] = f"UNLOCKED via synthesis-suggested mode {all_suggested_modes}"
            else:
                decision["result"] = f"tried modes {all_suggested_modes} from synthesis -- still blocked"
        else:
            dep_patterns = _re.findall(
                r"(?:must|should|need to|requires?)\s+(?:call|invoke)\s+(\w+)\s+(?:before|first|prior)",
                api_ref, _re.I,
            )
            if dep_patterns:
                decision["analysis"]["dependencies"] = dep_patterns
                decision["action"] = "noted_dependencies"
                decision["result"] = f"synthesis mentions dependencies: {dep_patterns} -- logged for MC-5/MC-6"
            else:
                decision["analysis"]["init_clues"] = "none found"
                decision["action"] = "no_action"
                decision["result"] = "synthesis doc has no actionable init sequence hints"

    except Exception as exc:
        decision["result"] = f"error: {exc}"
        logger.debug("[%s] mc4-post-synthesis failed: %s", ctx.job_id, exc)

    _persist_mc_decision(ctx, "mc4-post-synthesis", decision)
