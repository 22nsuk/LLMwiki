from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from tests.minimal_vault_seed_core import seed_minimal_vault as _seed_minimal_vault
from tests.minimal_vault_seed_smoke import (
    seed_doc_audit_smoke_vault as _seed_doc_audit_smoke_vault,
    seed_eval_coverage_smoke_vault as _seed_eval_coverage_smoke_vault,
    seed_open_question_smoke_vault as _seed_open_question_smoke_vault,
    seed_registry_review_smoke_vault as _seed_registry_review_smoke_vault,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
MINIMAL_VAULT_CREATED = "2026-04-15"
SCHEMA_PATHS = {
    "wiki-maintainer-policy.schema.json": REPO_ROOT / "ops" / "schemas" / "wiki-maintainer-policy.schema.json",
    "seed.schema.json": REPO_ROOT / "ops" / "schemas" / "seed.schema.json",
    "planning-validation.schema.json": REPO_ROOT / "ops" / "schemas" / "planning-validation.schema.json",
    "planning-gate-validation-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "planning-gate-validation-report.schema.json",
    "run-ledger.schema.json": REPO_ROOT / "ops" / "schemas" / "run-ledger.schema.json",
    "improvement-observations.schema.json": REPO_ROOT / "ops" / "schemas" / "improvement-observations.schema.json",
    "changed-files-manifest.schema.json": REPO_ROOT / "ops" / "schemas" / "changed-files-manifest.schema.json",
    "candidate-changed-files-snapshot.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "candidate-changed-files-snapshot.schema.json",
    "clean-fixture-regeneration-guard.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "clean-fixture-regeneration-guard.schema.json",
    "shadow-apply-report.schema.json": REPO_ROOT / "ops" / "schemas" / "shadow-apply-report.schema.json",
    "rollback-rehearsal-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "rollback-rehearsal-report.schema.json",
    "behavior-delta.schema.json": REPO_ROOT / "ops" / "schemas" / "behavior-delta.schema.json",
    "promotion-report.schema.json": REPO_ROOT / "ops" / "schemas" / "promotion-report.schema.json",
    "proposal-snapshot.schema.json": REPO_ROOT / "ops" / "schemas" / "proposal-snapshot.schema.json",
    "mechanism-assessment-report.schema.json": REPO_ROOT / "ops" / "schemas" / "mechanism-assessment-report.schema.json",
    "eval-report.schema.json": REPO_ROOT / "ops" / "schemas" / "eval-report.schema.json",
    "wiki-eval-coverage-report.schema.json": REPO_ROOT / "ops" / "schemas" / "wiki-eval-coverage-report.schema.json",
    "lint-report.schema.json": REPO_ROOT / "ops" / "schemas" / "lint-report.schema.json",
    "wiki-lint-review-classification.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "wiki-lint-review-classification.schema.json",
    "wiki-manifest.schema.json": REPO_ROOT / "ops" / "schemas" / "wiki-manifest.schema.json",
    "warning-budget-report.schema.json": REPO_ROOT / "ops" / "schemas" / "warning-budget-report.schema.json",
    "structural-complexity-budget-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "structural-complexity-budget-report.schema.json",
    "mutation-proposals.schema.json": REPO_ROOT / "ops" / "schemas" / "mutation-proposals.schema.json",
    "wiki-stage2-eval-report.schema.json": REPO_ROOT / "ops" / "schemas" / "wiki-stage2-eval-report.schema.json",
    "mechanism-review-candidates.schema.json": REPO_ROOT / "ops" / "schemas" / "mechanism-review-candidates.schema.json",
    "subagent-routing-report.schema.json": REPO_ROOT / "ops" / "schemas" / "subagent-routing-report.schema.json",
    "proposal-scope.schema.json": REPO_ROOT / "ops" / "schemas" / "proposal-scope.schema.json",
    "executor-report.schema.json": REPO_ROOT / "ops" / "schemas" / "executor-report.schema.json",
    "command-log-summary.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "command-log-summary.schema.json",
    "command-log-summary-backfill.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "command-log-summary-backfill.schema.json",
    "auto-improve-session.schema.json": REPO_ROOT / "ops" / "schemas" / "auto-improve-session.schema.json",
    "auto-improve-readiness-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "auto-improve-readiness-report.schema.json",
    "codex-goal-contract.schema.json": REPO_ROOT / "ops" / "schemas" / "codex-goal-contract.schema.json",
    "goal-run-status.schema.json": REPO_ROOT / "ops" / "schemas" / "goal-run-status.schema.json",
    "goal-runtime-clean-transient.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "goal-runtime-clean-transient.schema.json",
    "goal-runtime-fixed-point-check.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "goal-runtime-fixed-point-check.schema.json",
    "goal-runtime-quarantine-preflight.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "goal-runtime-quarantine-preflight.schema.json",
    "goal-runtime-run-admission.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "goal-runtime-run-admission.schema.json",
    "goal-runtime-closeout-plan.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "goal-runtime-closeout-plan.schema.json",
    "goal-resume-metadata.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "goal-resume-metadata.schema.json",
    "remediation-backlog.schema.json": REPO_ROOT / "ops" / "schemas" / "remediation-backlog.schema.json",
    "self-improvement-negative-lessons.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "self-improvement-negative-lessons.schema.json",
    "run-telemetry.schema.json": REPO_ROOT / "ops" / "schemas" / "run-telemetry.schema.json",
    "run-artifact-fingerprint.schema.json": REPO_ROOT / "ops" / "schemas" / "run-artifact-fingerprint.schema.json",
    "same-session-repair-context.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "same-session-repair-context.schema.json",
    "timeout-failure.schema.json": REPO_ROOT / "ops" / "schemas" / "timeout-failure.schema.json",
    "promotion-decision-trends.schema.json": REPO_ROOT / "ops" / "schemas" / "promotion-decision-trends.schema.json",
    "routing-provenance-aggregate.schema.json": REPO_ROOT / "ops" / "schemas" / "routing-provenance-aggregate.schema.json",
    "outcome-metrics.schema.json": REPO_ROOT / "ops" / "schemas" / "outcome-metrics.schema.json",
    "supply-chain-provenance.schema.json": REPO_ROOT / "ops" / "schemas" / "supply-chain-provenance.schema.json",
    "supply-chain-gate-report.schema.json": REPO_ROOT / "ops" / "schemas" / "supply-chain-gate-report.schema.json",
    "sbom-export-mapping.schema.json": REPO_ROOT / "ops" / "schemas" / "sbom-export-mapping.schema.json",
    "sbom-readiness-gate-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "sbom-readiness-gate-report.schema.json",
    "security-advisories.schema.json": REPO_ROOT / "ops" / "schemas" / "security-advisories.schema.json",
    "supply-chain-artifact-model.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "supply-chain-artifact-model.schema.json",
    "spdx-sbom-draft.schema.json": REPO_ROOT / "ops" / "schemas" / "spdx-sbom-draft.schema.json",
    "supply-chain-benchmark.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "supply-chain-benchmark.schema.json",
    "in-toto-statement.schema.json": REPO_ROOT / "ops" / "schemas" / "in-toto-statement.schema.json",
    "sigstore-bundle-verification.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "sigstore-bundle-verification.schema.json",
    "github-governance-live-drift.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "github-governance-live-drift.schema.json",
    "cyclonedx-1.6.schema.json": REPO_ROOT / "ops" / "schemas" / "cyclonedx-1.6.schema.json",
    "openvex-draft.schema.json": REPO_ROOT / "ops" / "schemas" / "openvex-draft.schema.json",
    "generated-artifact-index.schema.json": REPO_ROOT / "ops" / "schemas" / "generated-artifact-index.schema.json",
    "generated-artifact-convergence.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "generated-artifact-convergence.schema.json",
    "archive-execution-manifest.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "archive-execution-manifest.schema.json",
    "artifact-envelope.schema.json": REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json",
    "artifact-freshness-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "artifact-freshness-report.schema.json",
    "artifact-relocation-audit.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "artifact-relocation-audit.schema.json",
    "bootstrap-preflight-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "bootstrap-preflight-report.schema.json",
    "release-closeout-summary.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-closeout-summary.schema.json",
    "release-closeout-sealed-rehearsal-check.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-closeout-sealed-rehearsal-check.schema.json",
    "release-run-ready-plan.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-run-ready-plan.schema.json",
    "release-risk-taxonomy.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-risk-taxonomy.schema.json",
    "release-risk-taxonomy-matrix.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-risk-taxonomy-matrix.schema.json",
    "release-clean-lane-evidence-review.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-clean-lane-evidence-review.schema.json",
    "release-evidence-cohort.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-evidence-cohort.schema.json",
    "release-live-artifact-attestation.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-live-artifact-attestation.schema.json",
    "release-post-seal-attestation.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-post-seal-attestation.schema.json",
    "public-check-summary.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "public-check-summary.schema.json",
    "release-evidence-dashboard.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "release-evidence-dashboard.schema.json",
    "learning-readiness-signoff.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-readiness-signoff.schema.json",
    "learning-readiness-signoff-revalidation.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-readiness-signoff-revalidation.schema.json",
    "learning-claim-unlock-review.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-claim-unlock-review.schema.json",
    "learning-claim-evidence-bundle.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-claim-evidence-bundle.schema.json",
    "learning-confirmed-evidence-cohort.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-confirmed-evidence-cohort.schema.json",
    "learning-confirmed-legacy-reconstruction.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-confirmed-legacy-reconstruction.schema.json",
    "learning-delta-scoreboard.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-delta-scoreboard.schema.json",
    "remediation-backlog-status-overrides.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "remediation-backlog-status-overrides.schema.json",
    "learning-claim-activation-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "learning-claim-activation-report.schema.json",
    "session-synopsis.schema.json": REPO_ROOT / "ops" / "schemas" / "session-synopsis.schema.json",
    "raw-registry-preflight-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-registry-preflight-report.schema.json",
    "raw-registry-export.schema.json": REPO_ROOT / "ops" / "schemas" / "raw-registry-export.schema.json",
    "raw-registry-preflight-reproducibility.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-registry-preflight-reproducibility.schema.json",
    "raw-registry-cross-environment-matrix.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-registry-cross-environment-matrix.schema.json",
    "raw-registry-cross-environment-evidence-bundle.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-registry-cross-environment-evidence-bundle.schema.json",
    "test-execution-summary.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "test-execution-summary.schema.json",
    "codex-goal-prompt.schema.json": REPO_ROOT / "ops" / "schemas" / "codex-goal-prompt.schema.json",
    "goal-runtime-certificate.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "goal-runtime-certificate.schema.json",
    "goal-worktree-guard.schema.json": REPO_ROOT / "ops" / "schemas" / "goal-worktree-guard.schema.json",
    "test-deselection-policy.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "test-deselection-policy.schema.json",
    "make-target-inventory.schema.json": REPO_ROOT / "ops" / "schemas" / "make-target-inventory.schema.json",
    "workflow-dependency-planner.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "workflow-dependency-planner.schema.json",
    "manual-mutate-defect-registry.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "manual-mutate-defect-registry.schema.json",
    "defect-escape-closures.schema.json": REPO_ROOT / "ops" / "schemas" / "defect-escape-closures.schema.json",
    "rework-closures.schema.json": REPO_ROOT / "ops" / "schemas" / "rework-closures.schema.json",
    "raw-markdown-normalization-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-markdown-normalization-report.schema.json",
    "raw-intake-absorption-matrix.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-intake-absorption-matrix.schema.json",
    "raw-intake-promotion-profile-bundle.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-intake-promotion-profile-bundle.schema.json",
    "raw-intake-promotion-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-intake-promotion-report.schema.json",
    "raw-intake-route-proposal-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-intake-route-proposal-report.schema.json",
    "raw-intake-source-quality-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-intake-source-quality-report.schema.json",
    "raw-intake-seed-source-hints-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-intake-seed-source-hints-report.schema.json",
    "raw-intake-final-tree-validation-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "raw-intake-final-tree-validation-report.schema.json",
    "source-slug-curation-manifest.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "source-slug-curation-manifest.schema.json",
    "source-slug-curation-validation-report.schema.json": REPO_ROOT
    / "ops"
    / "schemas"
    / "source-slug-curation-validation-report.schema.json",
}


@lru_cache(maxsize=1)
def _live_policy_from_file(path: str, mtime_ns: int, size: int) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def clear_live_policy_cache() -> None:
    _live_policy_from_file.cache_clear()


def live_policy() -> dict[str, Any]:
    stat = POLICY_PATH.stat()
    return _live_policy_from_file(POLICY_PATH.as_posix(), stat.st_mtime_ns, stat.st_size)


def live_registry_shard_pages() -> list[str]:
    policy = live_policy()
    return list(policy["registry_contract"]["raw_registry_shard_pages"])


def live_registry_wiki_family_shard_pages() -> list[str]:
    return [
        path
        for path in live_registry_shard_pages()
        if path.startswith("system/system-raw-registry/wiki/")
        and path != "system/system-raw-registry/wiki.md"
    ]


def live_registry_child_shard_pages(relative_path: str) -> list[str]:
    parent_stem = Path(relative_path).with_suffix("").as_posix()
    child_prefix = f"{parent_stem}-"
    return [
        path
        for path in live_registry_wiki_family_shard_pages()
        if path.startswith(child_prefix) and path != relative_path
    ]


def registry_family_shard_required_sections(relative_path: str) -> list[str]:
    policy = live_policy()
    special_pages = policy["page_shape"]["special_page_required_sections"]
    return list(
        special_pages.get(
            relative_path,
            ["Summary", "Registered raw sources", "Related pages", "Source trace"],
        )
    )


def system_wikilink(relative_path: str) -> str:
    if relative_path.startswith("system/"):
        relative_path = relative_path[len("system/") :]
    if relative_path.endswith(".md"):
        relative_path = relative_path[:-3]
    return relative_path


def bullet_wikilinks(relative_paths: Sequence[str]) -> str:
    items = [f"- [[{system_wikilink(path)}]]" for path in relative_paths]
    return "\n".join(items)


def _registry_family_shard_section(
    heading: str,
    relative_path: str,
    source_trace_ref: str,
) -> str:
    stem = Path(relative_path).stem
    if relative_path.startswith("system/system-raw-registry/system-"):
        parent_router = "system-raw-registry/system"
        related_index = "system-index"
    else:
        parent_router = "system-raw-registry/wiki"
        related_index = "index"

    if heading == "Summary":
        child_count = len(live_registry_child_shard_pages(relative_path))
        return "\n".join(
            [
                f"- parent corpus router: [[{parent_router}]]",
                f"- topic family: `{stem}`",
                "- registered entries: `0`",
                f"- child registry shards: `{child_count}`",
            ]
        )
    if heading == "Registered raw sources":
        return "- none currently"
    if heading == "Directly listed raw sources":
        return "- none currently"
    if heading in {"Child registry shards", "Family shards", "Second-order shards"}:
        child_links = bullet_wikilinks(live_registry_child_shard_pages(relative_path))
        return child_links or "- none currently"
    if heading == "Compaction notes":
        return "- no compaction needed for the minimal vault fixture shard."
    if heading == "Related pages":
        return "\n".join(
            [
                "- [[system-raw-registry]]",
                f"- [[{parent_router}]]",
                f"- [[{related_index}]]",
            ]
        )
    if heading == "Source trace":
        return f"- `{source_trace_ref}`"
    return "- not represented in the minimal vault fixture."


def build_registry_family_shard_page(relative_path: str, source_trace_ref: str) -> str:
    stem = Path(relative_path).stem
    pretty_stem = " ".join(part.upper() if len(part) <= 3 else part.title() for part in stem.split("-"))
    sections = "\n\n".join(
        f"## {heading}\n{_registry_family_shard_section(heading, relative_path, source_trace_ref)}"
        for heading in registry_family_shard_required_sections(relative_path)
    )
    return f"""---
title: "Wiki Raw Registry Family Shard {pretty_stem}"
page_type: "registry-shard"
corpus: "system"
special_role: "raw-registry-shard"
aliases:
  - "{stem}"
  - "{system_wikilink(relative_path)}"
tags:
  - "corpus/system"
  - "type/registry-shard"
---

# {system_wikilink(relative_path)}

{sections}
"""


def _ensure_created_frontmatter(root: Path) -> None:
    for corpus_dir in (root / "wiki", root / "system"):
        if not corpus_dir.exists():
            continue
        for path in sorted(corpus_dir.rglob("*.md")):
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines or lines[0].strip() != "---":
                continue
            end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
            if end is None:
                continue
            if any(line.split(":", 1)[0].strip() == "created" for line in lines[1:end]):
                continue
            insert_at = end
            for index in range(1, end):
                if lines[index].split(":", 1)[0].strip() == "corpus":
                    insert_at = index + 1
                    break
            lines.insert(insert_at, f'created: "{MINIMAL_VAULT_CREATED}"')
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def seed_minimal_vault(
    root: Path,
    source_trace_ref: str = "raw/fake.pdf",
    *,
    schema_names: Sequence[str] | None = None,
) -> None:
    _seed_minimal_vault(root, source_trace_ref, schema_names=schema_names)


def seed_open_question_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    _seed_open_question_smoke_vault(root, source_trace_ref)


def seed_doc_audit_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    _seed_doc_audit_smoke_vault(root, source_trace_ref)


def seed_registry_review_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    _seed_registry_review_smoke_vault(root, source_trace_ref)


def seed_eval_coverage_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    _seed_eval_coverage_smoke_vault(root, source_trace_ref)


def seed_subagent_profiles(root: Path, roles: Sequence[str]) -> None:
    agents_dir = root / ".codex" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for role in roles:
        (agents_dir / f"{role}.toml").write_text(
            "\n".join(
                [
                    f'name = "{role}"',
                    f'description = "Test fixture profile for {role}."',
                    'developer_instructions = """Stay within the assigned role and bounded scope."""',
                    "",
                ]
            ),
            encoding="utf-8",
        )


def seed_planning_artifacts(root: Path, run_id: str, artifact_dir: str | Path = "artifacts") -> None:
    artifact_dir = Path(artifact_dir)
    if not artifact_dir.is_absolute():
        artifact_dir = root / artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "seed.yaml").write_text(
        f"""$schema: "ops/schemas/seed.schema.json"
run_id: {run_id}
mode: planning
request:
  summary: "Validate writer output paths"
  requester: human
  source_pages:
    - "wiki/source--fake.md"
state:
  current: REQUEST_IN
  allowed_next:
    - INTERVIEW
goals:
  primary:
    - "Keep output paths vault-relative"
  non_goals:
    - "None"
constraints:
  hard:
    - "No raw edits"
  soft:
    - "Keep it simple"
success_criteria:
  - id: SC-001
    text: "Artifacts validate"
    trace:
      - "wiki/source--fake.md"
assumptions:
  open:
    - "None"
  frozen:
    - "Vault exists"
evidence:
  wiki_pages:
    - "wiki/source--fake.md"
  raw_sources:
    - "raw/fake.pdf"
signoff:
  status: pending
  by: ""
  ts: ""
notes: ""
""",
        encoding="utf-8",
    )
    (artifact_dir / "planning-validation.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/planning-validation.schema.json",
                "run_id": run_id,
                "status": "PASS",
                "summary": "Artifacts align.",
                "checks": [
                    {
                        "id": "seed_present",
                        "status": "PASS",
                        "detail": "seed exists",
                        "required_artifacts": ["seed.yaml"],
                    }
                ],
                "open_questions": [],
                "signoff": {
                    "required": False,
                    "status": "not_required",
                    "by": "",
                    "ts": "",
                },
                "next_action": "Proceed",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "run-ledger.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": run_id,
                "status": "draft",
                "events": [
                    {
                        "ts": "2026-04-14T00:00:00Z",
                        "type": "created",
                        "summary": "Initialized artifacts.",
                        "artifacts": [
                            "seed.yaml",
                            "planning-validation.json",
                            "run-ledger.json",
                        ],
                        "decision": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def mutate_policy(vault: Path, mutator: Callable[[dict[str, Any]], None]) -> None:
    policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    mutator(policy)
    policy_path.write_text(
        yaml.safe_dump(policy, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def set_policy_value(vault: Path, path: Sequence[str], value: Any) -> None:
    def apply(policy: dict[str, Any]) -> None:
        target: Any = policy
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    mutate_policy(vault, apply)


def summary_count(page: Path, label: str) -> int:
    pattern = re.compile(rf"^(- {re.escape(label)}:\s*`?)(\d+)(`?\s*)$")
    for line in page.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return int(match.group(2))
    raise AssertionError(f"summary label not found: {label}")


def set_summary_count(page: Path, label: str, value: int) -> None:
    pattern = re.compile(rf"^(- {re.escape(label)}:\s*`?)(\d+)(`?\s*)$")
    lines = page.read_text(encoding="utf-8").splitlines()
    replaced = False
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        lines[idx] = f"{match.group(1)}{value}{match.group(3)}"
        replaced = True
        break
    if not replaced:
        raise AssertionError(f"summary label not found: {label}")
    page.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_registry_entry_scalar_field(
    page: Path,
    registry_id: str,
    field_name: str,
    value: str,
    *,
    after_field: str | None = None,
) -> None:
    lines = page.read_text(encoding="utf-8").splitlines()
    heading = f"#### {registry_id}"
    try:
        start = lines.index(heading)
    except ValueError as exc:
        raise AssertionError(f"registry entry not found: {registry_id}") from exc

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("#### "):
            end = idx
            break

    field_prefix = f"- {field_name}:"
    new_line = f"- {field_name}: {value}"
    for idx in range(start + 1, end):
        if lines[idx].startswith(field_prefix):
            lines[idx] = new_line
            page.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    insert_at = end
    if after_field is not None:
        after_prefix = f"- {after_field}:"
        for idx in range(start + 1, end):
            if lines[idx].startswith(after_prefix):
                insert_at = idx + 1
                break
        else:
            raise AssertionError(f"registry field not found: {after_field}")
    else:
        while insert_at > start + 1 and lines[insert_at - 1] == "":
            insert_at -= 1

    lines.insert(insert_at, new_line)
    page.write_text("\n".join(lines) + "\n", encoding="utf-8")
