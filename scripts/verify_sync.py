from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.handoff_contract import STAGE_CONTRACTS  # noqa: E402

BANNED_IDENTIFIERS = ("_cur", "_wucurrent", "_gap_current")
LEGACY_BANNED_IDENTIFIER_ALLOWLIST = frozenset(
    {
        "api/pipeline/runner.py",
        "api/pipeline/s01_unlock/unlock_helpers.py",
        "api/pipeline/s02_probe/probe_loop.py",
        "api/pipeline/s05_enrichment/verify.py",
        "api/pipeline/s06_gaps/__init__.py",
        "api/pipeline/s06_gaps/gap_resolution.py",
        "api/pipeline/s07_finalize/harmonize.py",
    }
)
INLINE_STATUS_RANK_TOKENS = (
    '"verified_success": 5',
    '"functional_precondition_unmet": 4',
    '"inferred_success": 3',
    '"failure": 2',
    '"unknown": 1',
)
FUNCTIONAL_REGEX_FRAGMENT = "insufficient|not enough|balance|points|quota|limit|depleted"


@dataclass
class Issue:
    tier: str
    code: str
    message: str
    where: str
    fix: str


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _iter_python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for root in paths:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if ".venv" in path.parts:
                continue
            yield path


def _stage_prefixes_from_contract() -> set[str]:
    prefixes: set[str] = set()
    for stage in STAGE_CONTRACTS:
        stage_id = stage.id
        if not stage_id.startswith("S-"):
            continue
        num = stage_id[2:4]
        if not num.isdigit():
            continue
        if stage_id.endswith("R"):
            # S-04R is a refresh stage, not a separate package directory.
            continue
        prefixes.add(f"s{num}")
    return prefixes


def _runtime_stage_dirs() -> set[str]:
    out: set[str] = set()
    for path in (REPO_ROOT / "api" / "pipeline").glob("s[0-9][0-9]_*"):
        if path.is_dir():
            out.add(path.name)
    return out


def _runner_stage_import_dirs() -> set[str]:
    text = _read(REPO_ROOT / "api" / "pipeline" / "runner.py")
    matches = re.findall(r"from\s+api\.pipeline\.(s[0-9][0-9]_[a-z0-9_]+)\s+import\s+run_s[0-9][0-9]", text)
    return set(matches)


def _find_inline_status_rank_literals(path: Path) -> list[Issue]:
    text = _read(path)
    if not text:
        return []
    try:
        where = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except Exception:
        where = str(path)
    if all(token in text for token in INLINE_STATUS_RANK_TOKENS):
        return [
            Issue(
                tier="A",
                code="duplicate-status-rank",
                message="Local status-rank dict duplicates canonical SSOT.",
                where=where,
                fix="Import STATUS_ORDER from api.pipeline.core.finding_status and remove local rank dict.",
            )
        ]
    return []


def _check_tier_a() -> list[Issue]:
    issues: list[Issue] = []

    contract_prefixes = _stage_prefixes_from_contract()
    stage_dirs = _runtime_stage_dirs()
    stage_prefixes = {name.split("_", 1)[0] for name in stage_dirs}

    missing_stage_dirs = sorted(contract_prefixes - stage_prefixes)
    for prefix in missing_stage_dirs:
        issues.append(
            Issue(
                tier="A",
                code="missing-stage-dir",
                message=f"No runtime stage directory found for contract stage prefix '{prefix}'.",
                where="api/pipeline",
                fix=f"Add directory '{prefix}_*' or remove/update the corresponding stage in handoff_contract.py.",
            )
        )

    extra_stage_dirs = sorted(stage_prefixes - contract_prefixes)
    for prefix in extra_stage_dirs:
        issues.append(
            Issue(
                tier="A",
                code="orphan-stage-dir",
                message=f"Runtime stage directory prefix '{prefix}' has no contract stage.",
                where="api/pipeline",
                fix=f"Add matching stage to handoff_contract.py or remove orphan '{prefix}_*' directory.",
            )
        )

    runner_dirs = _runner_stage_import_dirs()
    missing_runner_imports = sorted(stage_dirs - runner_dirs)
    for name in missing_runner_imports:
        issues.append(
            Issue(
                tier="A",
                code="runner-import-missing",
                message=f"Stage package '{name}' is not imported in runner dispatch.",
                where="api/pipeline/runner.py",
                fix=f"Add 'from api.pipeline.{name} import run_sNN' and include it in execution flow.",
            )
        )

    extra_runner_imports = sorted(runner_dirs - stage_dirs)
    for name in extra_runner_imports:
        issues.append(
            Issue(
                tier="A",
                code="runner-import-orphan",
                message=f"Runner imports '{name}' but no matching stage package directory exists.",
                where="api/pipeline/runner.py",
                fix=f"Remove import for '{name}' or add missing package directory.",
            )
        )

    for py in _iter_python_files((REPO_ROOT / "api", REPO_ROOT / "scripts")):
        text = _read(py)
        rel = str(py.relative_to(REPO_ROOT)).replace("\\", "/")
        if rel in LEGACY_BANNED_IDENTIFIER_ALLOWLIST or rel == "scripts/verify_sync.py":
            continue
        for token in BANNED_IDENTIFIERS:
            if re.search(rf"\b{re.escape(token)}\b", text):
                issues.append(
                    Issue(
                        tier="A",
                        code="banned-identifier",
                        message=f"Banned identifier '{token}' found.",
                        where=rel,
                        fix=f"Rename '{token}' to a descriptive, non-abbreviated variable name.",
                    )
                )
        if py not in {
            REPO_ROOT / "api" / "pipeline" / "core" / "finding_status.py",
            REPO_ROOT / "scripts" / "verify_sync.py",
        }:
            issues.extend(_find_inline_status_rank_literals(py))

    for required_path in (
        REPO_ROOT / "scripts" / "harness_lib" / "collector.py",
        REPO_ROOT / "api" / "pipeline" / "core" / "helpers.py",
    ):
        text = _read(required_path)
        if "api.pipeline.core.finding_status" not in text:
            issues.append(
                Issue(
                    tier="A",
                    code="ssot-import-missing",
                    message="Canonical finding_status import missing in critical module.",
                    where=str(required_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                    fix="Import canonical status constants/helpers from api.pipeline.core.finding_status.",
                )
            )

    return issues


def _check_tier_c() -> list[Issue]:
    """Validate that recent ledger rows contain cross-DLL correlation fields."""
    issues: list[Issue] = []
    ledger_path = REPO_ROOT / "sessions" / "ledger" / "run_ledger.jsonl"
    if not ledger_path.exists():
        issues.append(
            Issue(
                tier="C",
                code="ledger-missing",
                message="Run ledger file not found.",
                where="sessions/ledger/run_ledger.jsonl",
                fix="Run at least one pipeline session with collector to generate the ledger.",
            )
        )
        return issues

    import json
    rows: list[dict] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass

    if not rows:
        issues.append(
            Issue(
                tier="C",
                code="ledger-empty",
                message="Run ledger has no valid rows.",
                where="sessions/ledger/run_ledger.jsonl",
                fix="Run a pipeline session to populate the ledger.",
            )
        )
        return issues

    recent = rows[-min(5, len(rows)):]
    missing_entity_ns = sum(1 for r in recent if "entity_namespace" not in r)
    missing_fn_deps = sum(1 for r in recent if "function_dependencies_declared" not in r)

    if missing_entity_ns > 0:
        issues.append(
            Issue(
                tier="C",
                code="ledger-missing-entity-namespace",
                message=f"{missing_entity_ns}/{len(recent)} recent ledger rows lack 'entity_namespace' field.",
                where="sessions/ledger/run_ledger.jsonl",
                fix="Upgrade collector.py and re-run sessions to populate entity_namespace.",
            )
        )
    if missing_fn_deps > 0:
        issues.append(
            Issue(
                tier="C",
                code="ledger-missing-function-deps",
                message=f"{missing_fn_deps}/{len(recent)} recent ledger rows lack 'function_dependencies_declared' field.",
                where="sessions/ledger/run_ledger.jsonl",
                fix="Upgrade collector.py and re-run sessions to populate function_dependencies_declared.",
            )
        )

    crucial_fields = [
        ("analysis_entrypoint", "Analysis entrypoint (analyze-path vs upload)"),
        ("binary_origin", "Binary origin (repo_fixture, temp_upload, etc.)"),
        ("seeding_mode", "Seeding mode (none, same_dll_prior, cross_dll_prior, mixed)"),
    ]
    for field_name, description in crucial_fields:
        missing = sum(1 for r in recent if field_name not in r)
        if missing > 0:
            issues.append(
                Issue(
                    tier="C",
                    code=f"ledger-missing-{field_name.replace('_', '-')}",
                    message=f"{missing}/{len(recent)} recent rows lack '{field_name}': {description}.",
                    where="sessions/ledger/run_ledger.jsonl",
                    fix=f"Upgrade collector.py and re-run sessions to populate {field_name}.",
                )
            )
    return issues


def _check_tier_b() -> list[Issue]:
    issues: list[Issue] = []
    parity_targets = (
        REPO_ROOT / "api" / "pipeline" / "s02_probe" / "probe_loop.py",
        REPO_ROOT / "api" / "pipeline" / "s06_gaps" / "gap_resolution.py",
        REPO_ROOT / "api" / "infra" / "storage.py",
        REPO_ROOT / "api" / "pipeline" / "core" / "helpers.py",
    )
    for path in parity_targets:
        text = _read(path)
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        if "is_functional_precondition_text" not in text and "classify_finding_status(" not in text:
            issues.append(
                Issue(
                    tier="B",
                    code="classification-ssot-missing",
                    message="Classification path does not reference shared functional classification helpers.",
                    where=rel,
                    fix="Import is_functional_precondition_text/classify_finding_status from finding_status module.",
                )
            )
        if FUNCTIONAL_REGEX_FRAGMENT in text:
            issues.append(
                Issue(
                    tier="B",
                    code="inline-functional-regex",
                    message="Inline functional classification regex detected.",
                    where=rel,
                    fix="Use shared FUNCTIONAL_CLASSIFICATION_PATTERN/is_functional_precondition_text instead of inline regex.",
                )
            )

    full_flow = _read(REPO_ROOT / "api" / "pipeline" / "core" / "FULL_FLOW.md")
    for stage in STAGE_CONTRACTS:
        if stage.id.lower() not in full_flow.lower():
            issues.append(
                Issue(
                    tier="B",
                    code="doc-stage-missing",
                    message=f"Stage id '{stage.id}' not found in FULL_FLOW.md narrative.",
                    where="api/pipeline/core/FULL_FLOW.md",
                    fix=f"Add/update stage '{stage.id}' in FULL_FLOW.md or generate section from contract.",
                )
            )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify contract/code/doc sync invariants.")
    parser.add_argument("--tier", choices=("A", "B", "C", "all"), default="all")
    args = parser.parse_args(argv)

    issues: list[Issue] = []
    if args.tier in {"A", "all"}:
        issues.extend(_check_tier_a())
    if args.tier in {"B", "all"}:
        issues.extend(_check_tier_b())
    if args.tier in {"C", "all"}:
        issues.extend(_check_tier_c())

    if not issues:
        print("verify_sync: PASS")
        return 0

    print(f"verify_sync: FAIL ({len(issues)} issue(s))")
    for issue in issues:
        print(f"- [Tier {issue.tier}] {issue.code}")
        print(f"  what: {issue.message}")
        print(f"  where: {issue.where}")
        print(f"  fix: {issue.fix}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
