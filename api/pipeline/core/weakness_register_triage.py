from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_NAME = "weakness-register-triage.json"


REPO_ROOT = Path(__file__).resolve().parents[3]
WEAKNESS_REGISTER_PATH = REPO_ROOT / ".agents" / "ARCHITECTURAL-WEAKNESSES.md"


ACTIVE_IDS = {
    "2-expected-vs-observed-seam-checks-are-not-yet-formal-runtime-surfaces",
    "3-rerun-discipline-still-depends-too-much-on-agent-judgment",
    "8-narrow-live-reruns-can-still-be-ambiguous-when-they-reuse-stale-terminal-jobs",
    "11-contradiction-tracking-is-still-weaker-than-the-new-floor-to-ceiling-loop-controller",
    "12-cross-dll-contracts-are-only-explicit-for-shared-runtime-entity-continuity",
    "24-floor-aware-collection-is-now-mostly-fixed-but-comparable-run-policy-still-needs-an-explicit-package-floor-validity-rule",
    "25-batch-b-floor-to-ceiling-package-mode-is-planner-ready-but-the-live-frontier-seam-is-still-blocked-by-red-structured-preflight-regressions",
    "30-the-decomposition-layer-is-now-coherent-on-bounded-contoso-proofs-but-still-under-stressed-relative-to-enterprise-package-ambiguity",
    "31-the-first-decomposition-native-reduced-batch-b-run-proves-the-runtime-bridge-works-but-slice-attribution-still-collapses-and-active-frontier-ledger-validity-is-not-yet-collector-complete",
    "34-major-new-layers-can-still-be-locally-coherent-while-staying-globally-under-explained-or-overlap-ambiguous",
}

SUPERSEDED_IDS = {
    "1a-autonomous-prompt-chains-can-still-stop-too-early-when-the-wider-goal-is-technically-true-but-too-narrow",
    "5-prompt-memory-is-still-carrying-too-much-repo-critical-behavior",
    "9-rollout-prompts-can-undershoot-the-intended-integration-horizon-if-tranche-size-is-not-stated-explicitly",
    "12-the-weakness-register-needs-closure-and-supersession-discipline-not-just-append-only-growth",
    "29-complex-architecture-prompts-can-still-miss-implementation-critical-bases-unless-a-prompt-sufficiency-gate-is-enforced-in-governance",
    "32-interwoven-expansion-is-now-strategically-clear-but-it-still-lacks-canonical-artifact-and-observer-contracts-strong-enough-to-keep-contoso-derived-methodology-generic",
    "33-the-repo-now-has-a-bounded-non-contoso-proving-family-but-it-is-still-architecture-proof-only-and-not-yet-a-runtime-bearing-transfer-surface",
}

STALE_IDS = {
    "1-systems-are-not-yet-first-class-contracted-like-stages",
    "4-broader-capability-is-outpacing-coordination",
    "6-automation-agents-would-still-be-premature-without-contract-observers",
    "7-first-rollout-scope-can-overfit-to-the-active-campaign-if-schema-adoption-is-too-narrow",
    "10-campaign-polling-can-be-ambiguous-between-true-lifecycle-stall-and-legitimate-long-tail-execution",
    "11-package-level-blocker-families-are-clearer-than-per-function-regression-causes",
    "13-scale-planning-still-under-specifies-run-economics-and-evidence-compression-discipline",
    "14-the-engine-does-not-yet-have-first-class-seeded-reuse-and-cluster-level-checkpoint-discipline",
    "15-historical-checkpoints-can-lag-newly-introduced-semantic-checkpoint-layers",
    "16-bounded-reruns-can-still-lose-real-consumer-coverage-if-prerequisite-rebuild-spends-the-full-tool-budget",
    "17-package-mode-can-still-drop-locally-green-functions-when-direct-target-persistence-lags-successful-prereq-replay",
    "18-the-engine-does-not-yet-measure-convergence-rate-across-successive-passes-on-the-same-target-surface",
    "19-upstream-poison-can-spread-when-low-quality-or-misclassified-successes-are-reused-as-authoritative-truth",
    "20-the-foundational-pass-still-aims-too-broadly-which-wastes-time-on-low-context-write-targets-before-enough-state-truth-exists",
    "21-cross-dll-dependency-handling-is-still-stronger-at-attribution-and-reuse-than-at-first-class-architectural-modeling",
    "22-the-priority-stack-does-not-yet-have-an-explicit-integrity-gate-for-its-most-foundational-layers",
    "23-floor-to-ceiling-mode-can-still-collapse-into-a-single-ordinary-run-when-preservation-never-becomes-trustable",
    "26-direct-target-truth-preservation-is-stronger-but-live-package-proof-is-still-needed-to-prove-the-carryover-seam-is-fully-repaired",
    "27-package-frontier-proofs-can-be-honest-and-valid-without-automatically-becoming-overlap-comparable",
    "28-the-boa-constrictor-decomposition-layer-is-now-well-scoped-conceptually-but-still-lacks-common-rails-for-identity-economics-and-observer-law",
}


NEXT_PROMPT = {
    "id": "23",
    "filename": "23-package-floor-live-validity-and-replay-gate.md",
    "title": "Package-Floor Live Validity And Replay Gate",
    "why_now": (
        "The top active weakness cluster is no longer design-suite proving or repo-only "
        "cleanup. It is the live package-floor validity seam: comparable-run policy, "
        "stale narrow reruns, and red structured preflight regressions are still blocking "
        "trustworthy expensive package claims."
    ),
}


TOP_ACTIVE_SHORTLIST = [
    {
        "id": "25-batch-b-floor-to-ceiling-package-mode-is-planner-ready-but-the-live-frontier-seam-is-still-blocked-by-red-structured-preflight-regressions",
        "rank": 1,
        "cluster": "live_frontier_validity",
        "why_now": "The planner is ready, but the live prerequisite replay seam is still red on the exact path needed for the next expensive Batch B claim.",
    },
    {
        "id": "24-floor-aware-collection-is-now-mostly-fixed-but-comparable-run-policy-still-needs-an-explicit-package-floor-validity-rule",
        "rank": 2,
        "cluster": "package_floor_policy",
        "why_now": "The capture layer is mostly repaired, but promotion/comparison policy is still under-specified for narrow package-floor evidence.",
    },
    {
        "id": "8-narrow-live-reruns-can-still-be-ambiguous-when-they-reuse-stale-terminal-jobs",
        "rank": 3,
        "cluster": "replay_freshness",
        "why_now": "Observer-backed reruns are still vulnerable to stale job reuse and entry-surface ambiguity.",
    },
    {
        "id": "31-the-first-decomposition-native-reduced-batch-b-run-proves-the-runtime-bridge-works-but-slice-attribution-still-collapses-and-active-frontier-ledger-validity-is-not-yet-collector-complete",
        "rank": 4,
        "cluster": "decomposition_runtime_validity",
        "why_now": "The runtime bridge now works, but the live reduced run still collapses slice attribution and strict ledger completeness.",
    },
    {
        "id": "34-major-new-layers-can-still-be-locally-coherent-while-staying-globally-under-explained-or-overlap-ambiguous",
        "rank": 5,
        "cluster": "repo_legibility",
        "why_now": "The repo can now hide real cost in stale wrappers, archive drift, and duplicated concept homes even while the architecture passes tests.",
    },
]


SURFACE_FINDINGS = [
    {
        "path": "docs/architecture/oldstuff/",
        "status": "clarify",
        "recommendation": "retain as explicit archive home after verification",
        "rationale": "The current worktree suggests an archive move is underway, but the canonical archive boundary is not yet committed or documented as complete.",
    },
    {
        "path": "docs/architecture/engineScaling/engineScaling_General/",
        "status": "clarify",
        "recommendation": "verify and either adopt as canonical general-horizon home or retire in favor of existing engineScaling roots",
        "rationale": "A second general engine-scaling home appears in the worktree, which risks duplicate concept ownership until one path is declared canonical.",
    },
    {
        "path": "docs/architecture/*.md (root legacy set)",
        "status": "retire_after_verification",
        "recommendation": "retire only after archive/home migration is committed and linked from canonical docs",
        "rationale": "The worktree shows many root architecture docs being removed while likely archive replacements exist; this is an obvious supersession seam but not yet safely closed.",
    },
    {
        "path": "scripts/runs/run_northstar_campaign.py + scripts/runs/run_atlas_campaign.py",
        "status": "narrow",
        "recommendation": "keep as thin suite wrappers over the generic real-campaign owner",
        "rationale": "They are no longer the campaign owner, but still provide honest suite entrypoints and should remain visibly thin rather than disappear immediately.",
    },
    {
        "path": "ui/main.py + dashboard/main.py",
        "status": "clarify",
        "recommendation": "document the two-surface UI boundary and avoid overlapping operator responsibilities",
        "rationale": "Both are active UI surfaces, but one is the main app and one is the pipeline dashboard; that boundary is currently easy for humans to blur.",
    },
]


@dataclass(frozen=True)
class WeaknessEntry:
    identifier: str
    title: str
    body: str


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def parse_weakness_entries(markdown_text: str) -> list[WeaknessEntry]:
    parts = re.split(r"(?m)^###\s+", markdown_text)
    entries: list[WeaknessEntry] = []
    for part in parts[1:]:
        if "\n" not in part:
            continue
        title, body = part.split("\n", 1)
        title = title.strip()
        entries.append(
            WeaknessEntry(
                identifier=_slugify(title),
                title=title,
                body=body.strip(),
            )
        )
    return entries


def classify_weakness_entry(entry: WeaknessEntry) -> dict[str, Any]:
    if entry.identifier in ACTIVE_IDS:
        status = "active"
        rationale = "Still decision-bearing for the next implementation branch or current operator efficiency."
    elif entry.identifier in SUPERSEDED_IDS:
        status = "superseded"
        rationale = "Narrower governance or later implementation work now covers this weakness more directly."
    elif entry.identifier in STALE_IDS:
        status = "stale"
        rationale = "Still real historically, but no longer the strongest current blocker and should not steer the next branch by default."
    else:
        status = "stale"
        rationale = "Unmapped entries default to stale during this first reduction pass rather than silently staying active."
    return {
        "id": entry.identifier,
        "title": entry.title,
        "status": status,
        "rationale": rationale,
    }


def build_weakness_register_triage(
    *,
    register_text: str,
    worktree_status_lines: list[str] | None = None,
) -> dict[str, Any]:
    entries = parse_weakness_entries(register_text)
    classified = [classify_weakness_entry(entry) for entry in entries]
    by_id = {item["id"]: item for item in classified}

    shortlist: list[dict[str, Any]] = []
    for item in TOP_ACTIVE_SHORTLIST:
        classified_item = dict(by_id[item["id"]])
        classified_item.update(item)
        shortlist.append(classified_item)

    status_counts = {
        "active": sum(1 for item in classified if item["status"] == "active"),
        "stale": sum(1 for item in classified if item["status"] == "stale"),
        "superseded": sum(1 for item in classified if item["status"] == "superseded"),
    }

    duplicate_or_overlapping_surfaces = [
        {
            "concept": "general engine-scaling horizon docs",
            "paths": [
                "docs/architecture/engineScaling/",
                "docs/architecture/engineScaling/engineScaling_General/",
            ],
            "recommendation": "pick one canonical home and archive or link the other",
        },
        {
            "concept": "UI operator surfaces",
            "paths": [
                "ui/main.py",
                "dashboard/main.py",
            ],
            "recommendation": "clarify owner responsibilities so the dashboard does not quietly duplicate the main UI",
        },
        {
            "concept": "real campaign ownership",
            "paths": [
                "api/pipeline/core/design_suite_real_campaign_runtime.py",
                "scripts/runs/run_northstar_campaign.py",
                "scripts/runs/run_atlas_campaign.py",
            ],
            "recommendation": "keep only the generic owner as decision-bearing and maintain suite wrappers as thin entrypoints",
        },
    ]

    return {
        "artifact_type": ARTIFACT_NAME,
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_register": str(WEAKNESS_REGISTER_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "entry_counts": {
            "total": len(entries),
            **status_counts,
        },
        "entry_statuses": classified,
        "top_active_shortlist": shortlist,
        "deprecated_or_orphaned_surfaces": SURFACE_FINDINGS,
        "duplicate_or_overlapping_surfaces": duplicate_or_overlapping_surfaces,
        "worktree_signals": list(worktree_status_lines or []),
        "next_prompt": NEXT_PROMPT,
        "evaluation": {
            "what_this_prompt_proved": (
                "The register can be reduced into a smaller active set and the repo's "
                "most obvious stale or duplicate surfaces can be named without another large architecture buildout."
            ),
            "what_remains_unproven": (
                "The top active weakness cluster still needs a real implementation prompt and live proof; "
                "this triage only clarifies priorities."
            ),
            "what_changed_in_the_architecture": (
                "The weakness register is now intended to steer the next branch from a machine-readable triage artifact, "
                "not only from free-form review."
            ),
            "is_the_planned_next_prompt_still_correct": False,
            "replacement_next_prompt": NEXT_PROMPT,
        },
    }


def write_weakness_register_triage(output_dir: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(output_dir) / ARTIFACT_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination

