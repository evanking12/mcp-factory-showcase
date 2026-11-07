from __future__ import annotations

from dataclasses import dataclass

# Contract epoch/version metadata for strict artifact auditing.
CONTRACT_VERSION = "1.0.0"
AUDITOR_VERSION = "1.0.0"
CONTRACT_EPOCH = 1


@dataclass(frozen=True)
class ArtifactRequirement:
    canonical_path: str
    blob_candidates: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class StageContract:
    id: str
    name: str
    required_inputs: tuple[ArtifactRequirement, ...]
    required_outputs: tuple[ArtifactRequirement, ...]
    required_context: tuple[ArtifactRequirement, ...] = ()
    required_reasoning: tuple[ArtifactRequirement, ...] = ()
    optional_when: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransitionContract:
    id: str
    name: str
    principle: str
    severity: str
    producer_stage: str
    consumer_stage: str
    producer_evidence: tuple[str, ...]
    consumer_evidence: tuple[str, ...]
    effect_evidence: tuple[str, ...]


@dataclass(frozen=True)
class SchemaHandoffSnapshot:
    canonical_path: str
    aliases: tuple[str, ...]
    owner_stage_ids: tuple[str, ...] = ()


def _req(canonical_path: str, *blob_candidates: str, description: str = "") -> ArtifactRequirement:
    candidates = tuple(x for x in blob_candidates if str(x).strip())
    return ArtifactRequirement(
        canonical_path=canonical_path,
        blob_candidates=candidates or (canonical_path,),
        description=description,
    )


def _optional(*conditions: str) -> tuple[str, ...]:
    return tuple(str(condition or "").strip() for condition in conditions if str(condition or "").strip())


def stage_optional_skip_reasons(
    stage: StageContract,
    *,
    gap_triggered: bool,
    floor_broadening_blocked: bool,
) -> tuple[str, ...]:
    allowed: list[str] = []
    for condition in stage.optional_when:
        if condition == "gap_not_triggered" and not gap_triggered:
            allowed.append(condition)
        elif condition == "floor_broadening_blocked" and floor_broadening_blocked:
            allowed.append(condition)
    return tuple(allowed)


def stage_skip_reason_is_allowed(
    stage: StageContract,
    skip_reason: str,
    *,
    gap_triggered: bool,
    floor_broadening_blocked: bool,
) -> bool:
    reason = str(skip_reason or "").strip()
    if not reason:
        return False
    reason_key = reason.split(":", 1)[0]
    return reason_key in stage_optional_skip_reasons(
        stage,
        gap_triggered=gap_triggered,
        floor_broadening_blocked=floor_broadening_blocked,
    )


STAGE_CONTRACTS: tuple[StageContract, ...] = (
    StageContract(
        id="S-00",
        name="setup",
        required_inputs=(),
        required_outputs=(
            _req(
                "evidence/stage-00-setup/schema-t0.json",
                "mcp_schema_t0.json",
                "stage-00-setup/schema.json",
                "evidence/stage-00-setup/schema-t0.json",
                description="Initial schema snapshot (t0).",
            ),
            _req(
                "evidence/stage-00-setup/invocables-map.json",
                "invocables_map.json",
                "stage-05-finalization/invocables_map.json",
                "evidence/stage-00-setup/invocables-map.json",
                description="Invocable map at setup boundary.",
            ),
            _req(
                "evidence/stage-00-setup/stage-checks.json",
                "explore_config.json",
                "stage-00-setup/explore_config.json",
                "evidence/stage-00-setup/stage-checks.json",
                description="Setup config/checkpoint evidence.",
            ),
        ),
    ),
    StageContract(
        id="S-01",
        name="write-unlock",
        required_inputs=(
            _req(
                "evidence/stage-00-setup/invocables-map.json",
                "invocables_map.json",
                "stage-05-finalization/invocables_map.json",
                "evidence/stage-00-setup/invocables-map.json",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-01-pre-probe/vocab.json",
                "vocab.json",
                "stage-05-finalization/vocab.json",
                "evidence/stage-01-pre-probe/vocab.json",
            ),
            _req(
                "evidence/stage-01-pre-probe/static-analysis.json",
                "static_analysis.json",
                "stage-00-setup/static_analysis.json",
                "evidence/stage-01-pre-probe/static-analysis.json",
            ),
            _req(
                "evidence/stage-01-pre-probe/sentinel-calibration.json",
                "sentinel_calibration.json",
                "stage-00-setup/sentinel_calibration.json",
                "evidence/stage-01-pre-probe/sentinel-calibration.json",
            ),
            _req(
                "evidence/stage-01-pre-probe/write-unlock-probe.json",
                "write_unlock_probe.json",
                "stage-00-setup/write-unlock-probe.json",
                "evidence/stage-01-pre-probe/write-unlock-probe.json",
            ),
        ),
    ),
    StageContract(
        id="S-02",
        name="probe-loop",
        required_inputs=(
            _req(
                "evidence/stage-01-pre-probe/vocab.json",
                "vocab.json",
                "stage-05-finalization/vocab.json",
                "evidence/stage-01-pre-probe/vocab.json",
            ),
            _req(
                "evidence/stage-01-pre-probe/static-analysis.json",
                "static_analysis.json",
                "stage-00-setup/static_analysis.json",
                "evidence/stage-01-pre-probe/static-analysis.json",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-02-probe-loop/probe-log.json",
                "explore_probe_log.json",
                "stage-01-probe-loop/explore_probe_log.json",
                "evidence/stage-02-probe-loop/probe-log.json",
            ),
            _req(
                "evidence/stage-02-probe-loop/findings.json",
                "findings.json",
                "stage-02-synthesis/findings.json",
                "evidence/stage-02-probe-loop/findings.json",
            ),
        ),
        required_context=(
            _req(
                "diagnostics/chat-model-context.txt",
                "model_context_phase_01_probe_loop.txt",
                "diagnostics/chat-model-context.txt",
            ),
            _req(
                "diagnostics/chat-system-context-turn0.txt",
                "chat_system_context_turn0.txt",
                "diagnostics/chat-system-context.txt",
                "diagnostics/chat-system-context-turn0.txt",
            ),
        ),
        required_reasoning=(
            _req(
                "evidence/stage-02-probe-loop/probe-round-reasoning.json",
                "evidence/stage-02-probe-loop/probe-round-reasoning.json",
            ),
            _req(
                "evidence/stage-02-probe-loop/probe-stop-reasons.json",
                "evidence/stage-02-probe-loop/probe-stop-reasons.json",
            ),
            _req(
                "evidence/stage-02-probe-loop/probe-strategy-summary.json",
                "evidence/stage-02-probe-loop/probe-strategy-summary.json",
            ),
        ),
    ),
    StageContract(
        id="S-03",
        name="reconcile",
        required_inputs=(
            _req(
                "evidence/stage-02-probe-loop/findings.json",
                "findings.json",
                "stage-02-synthesis/findings.json",
                "evidence/stage-02-probe-loop/findings.json",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-03-post-probe/sentinel-catalog.json",
                "sentinel_catalog.json",
                "stage-05-finalization/sentinel_catalog.json",
                "evidence/stage-03-post-probe/sentinel-catalog.json",
            ),
            _req(
                "evidence/mc-decisions/mc3-post-reconcile.json",
                "mc-decisions/mc3-post-reconcile.json",
                "evidence/mc-decisions/mc3-post-reconcile.json",
            ),
        ),
    ),
    StageContract(
        id="S-04",
        name="synthesis",
        required_inputs=(
            _req(
                "evidence/stage-02-probe-loop/findings.json",
                "findings.json",
                "stage-02-synthesis/findings.json",
                "evidence/stage-02-probe-loop/findings.json",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-04-synthesis/api-reference.md",
                "api_reference.md",
                "stage-02-synthesis/api_reference.md",
                "evidence/stage-04-synthesis/api-reference.md",
            ),
            _req(
                "evidence/stage-04-synthesis/synthesis-input-snapshot.json",
                "evidence/stage-04-synthesis/synthesis-input-snapshot.json",
            ),
            _req(
                "evidence/stage-04-synthesis/synthesis-coverage-check.json",
                "evidence/stage-04-synthesis/synthesis-coverage-check.json",
            ),
            _req(
                "evidence/mc-decisions/mc4-post-synthesis.json",
                "mc-decisions/mc4-post-synthesis.json",
                "evidence/mc-decisions/mc4-post-synthesis.json",
            ),
        ),
        required_context=(
            _req(
                "evidence/stage-04-synthesis/stage-context.txt",
                "model_context_phase_06_synthesis.txt",
                "stage-02-synthesis/model_context.txt",
                "evidence/stage-04-synthesis/stage-context.txt",
            ),
        ),
        optional_when=_optional("floor_broadening_blocked"),
    ),
    StageContract(
        id="S-05",
        name="enrichment",
        required_inputs=(
            _req(
                "evidence/stage-04-synthesis/api-reference.md",
                "api_reference.md",
                "stage-02-synthesis/api_reference.md",
                "evidence/stage-04-synthesis/api-reference.md",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-05-backfill/backfill-report.json",
                "backfill_result.json",
                "evidence/stage-05-backfill/backfill-report.json",
            ),
            _req(
                "evidence/stage-05-backfill/schema-post-backfill.json",
                "mcp_schema_post_discovery.json",
                "stage-02-synthesis/schema-after.json",
                "evidence/stage-05-backfill/schema-post-backfill.json",
            ),
            _req(
                "evidence/mc-decisions/mc5-post-verification.json",
                "mc-decisions/mc5-post-verification.json",
                "evidence/mc-decisions/mc5-post-verification.json",
            ),
            _req(
                "evidence/mc-decisions/verification-report.json",
                "verification-report.json",
                "mc-decisions/verification-report.json",
                "evidence/mc-decisions/verification-report.json",
            ),
        ),
        optional_when=_optional("floor_broadening_blocked"),
    ),
    StageContract(
        id="S-06",
        name="gap-resolution",
        required_inputs=(
            _req(
                "evidence/stage-05-backfill/schema-post-backfill.json",
                "mcp_schema_post_discovery.json",
                "stage-02-synthesis/schema-after.json",
                "evidence/stage-05-backfill/schema-post-backfill.json",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-06-gap-resolution/gap-resolution-log.json",
                "gap_resolution_log.json",
                "stage-03-gap-resolution/gap_resolution_log.json",
                "evidence/stage-06-gap-resolution/gap-resolution-log.json",
            ),
            _req(
                "evidence/stage-06-gap-resolution/schema-pre-mini-session.json",
                "mcp_schema_pre_mini_session.json",
                "stage-03-gap-resolution/mini-schema-before.json",
                "evidence/stage-06-gap-resolution/schema-pre-mini-session.json",
            ),
            _req(
                "evidence/stage-06-gap-resolution/schema-post-mini-session.json",
                "mcp_schema_post_mini_session.json",
                "stage-03-gap-resolution/mini-schema-after.json",
                "evidence/stage-06-gap-resolution/schema-post-mini-session.json",
            ),
            _req(
                "evidence/mc-decisions/mc6-post-gap-resolution.json",
                "mc-decisions/mc6-post-gap-resolution.json",
                "evidence/mc-decisions/mc6-post-gap-resolution.json",
            ),
        ),
        optional_when=_optional("gap_not_triggered", "floor_broadening_blocked"),
    ),
    StageContract(
        id="S-04R",
        name="synthesis-refresh",
        required_inputs=(
            _req(
                "evidence/stage-06-gap-resolution/schema-post-mini-session.json",
                "mcp_schema_post_mini_session.json",
                "stage-03-gap-resolution/mini-schema-after.json",
                "evidence/stage-06-gap-resolution/schema-post-mini-session.json",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-04-synthesis/api-reference.md",
                "api_reference.md",
                "stage-02-synthesis/api_reference.md",
                "evidence/stage-04-synthesis/api-reference.md",
            ),
        ),
        optional_when=_optional("gap_not_triggered", "floor_broadening_blocked"),
    ),
    StageContract(
        id="S-07",
        name="finalize",
        required_inputs=(
            _req(
                "evidence/stage-04-synthesis/api-reference.md",
                "api_reference.md",
                "stage-02-synthesis/api_reference.md",
                "evidence/stage-04-synthesis/api-reference.md",
            ),
        ),
        required_outputs=(
            _req(
                "evidence/stage-07-finalize/behavioral-spec.py",
                "behavioral_spec.py",
                "stage-05-finalization/behavioral_spec.py",
                "evidence/stage-07-finalize/behavioral-spec.py",
            ),
            _req(
                "evidence/stage-07-finalize/schema-final.json",
                "mcp_schema.json",
                "evidence/stage-07-finalize/schema-final.json",
            ),
            _req(
                "checkpoints/s07_finalize.json",
                "checkpoints/s07_finalize.json",
            ),
        ),
    ),
)


STAGE_CONTRACT_BY_ID = {stage.id: stage for stage in STAGE_CONTRACTS}
STAGE_ORDER = tuple(stage.id for stage in STAGE_CONTRACTS)


TRANSITION_CONTRACTS: tuple[TransitionContract, ...] = (
    TransitionContract("T-01", "hints_to_vocab", "Hints become ID vocab for probing.", "medium", "S-01", "S-02", ("evidence/stage-01-pre-probe/hints.txt",), ("evidence/stage-01-pre-probe/vocab.json",), ("evidence/stage-02-probe-loop/stage-context.txt",)),
    TransitionContract("T-02", "hint_error_codes_to_sentinels", "Hinted error codes are merged into calibrated sentinel map.", "high", "S-01", "S-01", ("evidence/stage-01-pre-probe/hints.txt",), ("evidence/stage-01-pre-probe/sentinel-calibration.json",), ("evidence/stage-01-pre-probe/vocab.json",)),
    TransitionContract("T-03", "vocab_to_probe_prompt", "Vocab propagates into probe prompt/context.", "medium", "S-01", "S-02", ("evidence/stage-01-pre-probe/vocab.json",), ("evidence/stage-02-probe-loop/stage-context.txt",), ("evidence/stage-02-probe-loop/probe-log.json",)),
    TransitionContract("T-04", "static_analysis_to_probe_prompt", "Static analysis hints appear in probe execution context.", "medium", "S-01", "S-02", ("evidence/stage-01-pre-probe/static-analysis.json",), ("evidence/stage-02-probe-loop/probe-user-message-sample.txt",), ("evidence/stage-02-probe-loop/probe-log.json",)),
    TransitionContract("T-05", "static_ids_to_fallback_args", "Static IDs are reused in deterministic fallback args.", "low", "S-01", "S-02", ("evidence/stage-01-pre-probe/static-analysis.json",), ("evidence/stage-02-probe-loop/probe-log.json",), ("evidence/stage-02-probe-loop/findings.json",)),
    TransitionContract("T-06", "probe_findings_to_synthesis", "Probe findings are represented in synthesis output.", "high", "S-02", "S-04", ("evidence/stage-02-probe-loop/findings.json",), ("evidence/stage-04-synthesis/api-reference.md",), ("evidence/stage-04-synthesis/stage-context.txt",)),
    TransitionContract("T-07", "synthesis_to_backfill_patches", "Synthesis drives schema backfill patches.", "medium", "S-04", "S-05", ("evidence/stage-04-synthesis/api-reference.md",), ("evidence/stage-05-backfill/backfill-report.json",), ("evidence/stage-05-backfill/schema-post-backfill.json",)),
    TransitionContract("T-08", "enrich_call_to_schema", "Explicit enrich calls mutate schema semantics.", "high", "S-02", "S-05", ("evidence/stage-02-probe-loop/probe-log.json",), ("evidence/stage-00-setup/invocables-map.json",), ("evidence/stage-05-backfill/schema-post-backfill.json",)),
    TransitionContract("T-09", "auto_enrich_to_schema", "Auto-enrichment contributes semantic schema updates.", "medium", "S-02", "S-05", ("evidence/stage-02-probe-loop/probe-log.json",), ("evidence/stage-00-setup/invocables-map.json",), ("evidence/stage-05-backfill/schema-post-backfill.json",)),
    TransitionContract("T-10", "vocab_to_param_names", "Vocabulary influences semantic parameter naming.", "medium", "S-01", "S-05", ("evidence/stage-01-pre-probe/vocab.json",), ("evidence/stage-00-setup/invocables-map.json",), ("evidence/stage-05-backfill/schema-post-backfill.json",)),
    TransitionContract("T-11", "enriched_knowledge_to_synthesis_input", "Findings + vocab are reflected in synthesis input/context.", "high", "S-02", "S-04", ("evidence/stage-02-probe-loop/findings.json", "evidence/stage-01-pre-probe/vocab.json"), ("evidence/stage-04-synthesis/stage-context.txt",), ("evidence/stage-04-synthesis/api-reference.md",)),
    TransitionContract("T-12", "gap_answers_to_mini_session_context", "Answered gaps propagate into mini-session context.", "medium", "S-06", "S-06", ("evidence/stage-01-pre-probe/vocab.json",), ("evidence/stage-06-gap-resolution/mini-session-transcript.txt",), ("evidence/stage-06-gap-resolution/gap-resolution-log.json",)),
    TransitionContract("T-13", "mini_session_to_schema_evolution", "Mini-session exploration changes schema evolution.", "high", "S-06", "S-06", ("evidence/stage-06-gap-resolution/mini-session-transcript.txt",), ("evidence/stage-06-gap-resolution/schema-pre-mini-session.json",), ("evidence/stage-06-gap-resolution/schema-post-mini-session.json",)),
    TransitionContract("T-14", "findings_to_chat_prompt", "Findings are injected into chat prompt context.", "high", "S-02", "S-07", ("evidence/stage-02-probe-loop/findings.json",), ("diagnostics/chat-system-context-turn0.txt",), ("diagnostics/executor-trace.json",)),
    TransitionContract("T-15", "vocab_to_chat_prompt", "Vocabulary blocks are injected into chat prompt context.", "medium", "S-01", "S-07", ("evidence/stage-01-pre-probe/vocab.json",), ("diagnostics/chat-system-context-turn0.txt",), ("diagnostics/executor-trace.json",)),
    TransitionContract("T-16", "schema_evolution_present", "Schema evolution exists from t0 to final output.", "high", "S-00", "S-07", ("evidence/stage-00-setup/schema-t0.json",), ("evidence/stage-07-finalize/schema-evolution.json",), ("evidence/stage-07-finalize/schema-final.json",)),
    TransitionContract("T-17", "sentinel_calibration_outcome", "Sentinel calibration yields DLL-specific outcome signal.", "low", "S-01", "S-02", ("evidence/stage-01-pre-probe/sentinel-calibration.json",), ("evidence/stage-02-probe-loop/stage-context.txt",), ("evidence/stage-02-probe-loop/probe-log.json",)),
    TransitionContract("T-18", "write_unlock_probe_outcome", "Write unlock probe outcome is recorded and consumed.", "low", "S-01", "S-02", ("evidence/stage-01-pre-probe/write-unlock-probe.json",), ("evidence/stage-02-probe-loop/probe-log.json",), ("evidence/stage-02-probe-loop/probe-log.json",)),
    TransitionContract("T-19", "mc_coordinator_decisions", "MC decisions are persisted as reasoning artifacts.", "medium", "S-02", "S-06", ("evidence/mc-decisions/mc3-post-reconcile.json", "evidence/mc-decisions/mc4-post-synthesis.json"), ("evidence/mc-decisions/mc5-post-verification.json", "evidence/mc-decisions/mc6-post-gap-resolution.json"), ("evidence/stage-02-probe-loop/findings.json",)),
    TransitionContract("T-20", "enrichment_verification_outcome", "Enrichment verification result is captured and traceable.", "high", "S-05", "S-06", ("evidence/stage-05-backfill/backfill-report.json", "evidence/stage-02-probe-loop/findings.json"), ("evidence/mc-decisions/verification-report.json",), ("evidence/stage-02-probe-loop/findings.json",)),
    TransitionContract("T-21", "winning_init_sequence_persistence", "Winning init sequence is persisted for replay.", "medium", "S-02", "S-07", ("evidence/mc-decisions/mc6-post-gap-resolution.json",), ("evidence/mc-decisions/winning-init-sequence.json",), ("evidence/stage-02-probe-loop/findings.json",)),
)

TRANSITION_CONTRACT_BY_ID = {t.id: t for t in TRANSITION_CONTRACTS}
TRANSITION_ORDER = tuple(t.id for t in TRANSITION_CONTRACTS)
TRANSITION_SEVERITY = {t.id: t.severity for t in TRANSITION_CONTRACTS}


SCHEMA_HANDOFF_SNAPSHOTS: tuple[SchemaHandoffSnapshot, ...] = (
    SchemaHandoffSnapshot(
        canonical_path="stage-00-setup/schema.json",
        aliases=("evidence/stage-00-setup/schema-t0.json",),
        owner_stage_ids=("S-00",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-01-probe-loop/schema-before.json",
        aliases=("stage-00-setup/schema.json", "evidence/stage-00-setup/schema-t0.json"),
        owner_stage_ids=("S-02",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-01-probe-loop/schema-after.json",
        aliases=(),
        owner_stage_ids=("S-02",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-02-synthesis/schema-before.json",
        aliases=("stage-01-probe-loop/schema-after.json",),
        owner_stage_ids=("S-04",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-02-synthesis/schema-after.json",
        aliases=("evidence/stage-05-backfill/schema-post-backfill.json",),
        owner_stage_ids=("S-05",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-03-gap-resolution/schema-before.json",
        aliases=("stage-02-synthesis/schema-after.json",),
        owner_stage_ids=("S-06",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-03-gap-resolution/schema-after.json",
        aliases=(),
        owner_stage_ids=("S-06",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-04-clarification/schema-before.json",
        aliases=("stage-03-gap-resolution/schema-after.json",),
        owner_stage_ids=(),
    ),
    SchemaHandoffSnapshot(
        canonical_path="stage-04-clarification/schema-after.json",
        aliases=(),
        owner_stage_ids=(),
    ),
    SchemaHandoffSnapshot(
        canonical_path="evidence/stage-05-backfill/schema-post-backfill.json",
        aliases=("stage-02-synthesis/schema-after.json",),
        owner_stage_ids=("S-05",),
    ),
    SchemaHandoffSnapshot(
        canonical_path="evidence/stage-07-finalize/schema-final.json",
        aliases=("stage-05-finalization/invocables_map.json",),
        owner_stage_ids=("S-07",),
    ),
)


REQUIRED_CONTRACT_FILES: tuple[str, ...] = (
    "session-meta.json",
    "stage-index.json",
    "transition-index.json",
    "cohesion-report.json",
)


FORWARD_GAP_KPI_ARTIFACTS: tuple[str, ...] = (
    "llm_usage.json",
    "stage_events.json",
    "queue_metrics.json",
    "variant_contributions.json",
)


def strict_required_stage_evidence() -> tuple[str, ...]:
    out: list[str] = []
    for stage in STAGE_CONTRACTS:
        for req in stage.required_outputs:
            out.append(req.canonical_path)
        for req in stage.required_reasoning:
            out.append(req.canonical_path)
    return tuple(dict.fromkeys(out))


def strict_required_context_evidence() -> tuple[str, ...]:
    out: list[str] = []
    for stage in STAGE_CONTRACTS:
        for req in stage.required_context:
            out.append(req.canonical_path)
    return tuple(dict.fromkeys(out))
