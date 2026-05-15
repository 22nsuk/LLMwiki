from __future__ import annotations

import json

from .improvement_observations_runtime import IMPROVEMENT_OBSERVATIONS_FILENAME
from .mechanism_run_common_runtime import timestamp
from .mechanism_run_ledger_runtime import run_rel
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    PLANNING_VALIDATION_SCHEMA_PATH,
    PROMOTION_REPORT_SCHEMA_PATH,
    PROPOSAL_SNAPSHOT_SCHEMA_PATH,
    RUN_LEDGER_SCHEMA_PATH,
    SEED_SCHEMA_PATH,
)


PLANNING_VALIDATION_SCHEMA = PLANNING_VALIDATION_SCHEMA_PATH
PROMOTION_REPORT_SCHEMA = PROMOTION_REPORT_SCHEMA_PATH
PROPOSAL_SNAPSHOT_SCHEMA = PROPOSAL_SNAPSHOT_SCHEMA_PATH
RUN_LEDGER_SCHEMA = RUN_LEDGER_SCHEMA_PATH
SEED_SCHEMA = SEED_SCHEMA_PATH


def default_log_summary(
    run_id: str,
    primary_targets: list[str],
    proposal: dict | None,
) -> str:
    if proposal is not None:
        return f"Execute proposal {proposal['proposal_id']} on {proposal['primary_targets'][0]}"
    return f"Mechanism experiment {run_id} on {primary_targets[0]}"


def yaml_quoted(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def proposal_snapshot(
    run_id: str,
    *,
    proposal: dict,
    source_report: str,
    context: RuntimeContext | None = None,
) -> dict:
    return {
        "$schema": PROPOSAL_SNAPSHOT_SCHEMA,
        "run_id": run_id,
        "source_report": source_report,
        "captured_at": timestamp(context),
        "proposal": proposal,
    }


def starter_seed_text(
    run_id: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
    *,
    proposal: dict | None,
    seed_state: str,
) -> str:
    supporting_block = "\n".join(f"- `{target}`" for target in supporting_targets) or "- none"
    test_block = "\n".join(f"- `{test}`" for test in test_files) or "- none declared yet"
    evidence_page_paths = [
        "ops/reports/mechanism-review-candidates.json",
        "ops/reports/mutation-proposals.json",
    ]
    if proposal is not None:
        evidence_page_paths.append(run_rel(run_id, "proposal-snapshot.json"))
    evidence_pages = "\n".join(f'    - "{page}"' for page in evidence_page_paths)
    request_summary = (
        proposal["single_mechanism_scope"]
        if proposal is not None
        else "Run one scoped system_mechanism experiment and capture baseline/candidate artifacts."
    )
    primary_goals = [
        "Change one mechanism only and keep repo health green.",
        "Record baseline/candidate eval, lint, mechanism assessment, and promotion artifacts under one run id.",
        "Capture any follow-up automation or repo hygiene improvement in improvement-observations.json before the run closes.",
    ]
    if proposal is not None:
        primary_goals.append(proposal["expected_binary_signal"])
    goals_block = "\n".join(f"    - {yaml_quoted(goal)}" for goal in primary_goals)
    allowed_next = (
        '    - "SEED_FROZEN"\n    - "BLOCKED"'
        if seed_state == "SEED_DRAFT"
        else '    - "PLAN_DRAFT"\n    - "BLOCKED"'
    )
    notes = (
        f"Primary target: {primary_targets[0]}. Supporting targets:\\n{supporting_block}"
        f"\\nFocused tests:\\n{test_block}"
        f"\\nFollow-up surface: {run_rel(run_id, IMPROVEMENT_OBSERVATIONS_FILENAME)}"
    )
    if proposal is not None:
        notes += (
            f"\\nProposal id: {proposal['proposal_id']}."
            f"\\nFailure mode: {proposal['failure_mode']}."
            f"\\nWhy now: {proposal['why_now']}"
        )
    return f"""$schema: "{SEED_SCHEMA}"
run_id: {run_id}
mode: improvement

request:
  summary: {yaml_quoted(request_summary)}
  requester: maintainer-agent
  source_pages:
{evidence_pages}

state:
  current: {seed_state}
  allowed_next:
{allowed_next}

goals:
  primary:
{goals_block}
  non_goals:
    - "Do not mix unrelated content edits into the same run."
    - "Do not broaden the experiment beyond one primary mechanism target."

constraints:
  hard:
    - "One mechanism per experiment."
    - "Never edit raw/."
    - "Keep run-local artifacts under runs/<run-id>/."
  soft:
    - "Prefer one primary target and at most two supporting targets."
    - "Prefer structural change over prompt-only change."

success_criteria:
  - id: SC-001
    text: "Baseline and candidate mechanism assessment artifacts are both captured for the same run."
    trace:
      - "runs/{run_id}/baseline-mechanism-assessment.json"
      - "runs/{run_id}/candidate-mechanism-assessment.json"
  - id: SC-002
    text: "Repo health check is recorded before promotion evaluation."
    trace:
      - "runs/{run_id}/run-ledger.json"
  - id: SC-003
    text: "Promotion decision is written to promotion-report.json with explicit artifact inputs."
    trace:
      - "runs/{run_id}/promotion-report.json"
  - id: SC-004
    text: "Reusable follow-up improvements are captured in improvement-observations.json before the run closes."
    trace:
      - "runs/{run_id}/improvement-observations.json"

assumptions:
  open:
    - "Mutation command should only touch the frozen primary/supporting target set."
  frozen:
    - "Promotion success is read from promotion-report.json decision, not from shell exit code alone."

evidence:
  wiki_pages:
    - "system/system-index.md"
    - "system/system-log.md"
  raw_sources: []

signoff:
  status: pending
  by: ""
  ts: ""

notes: {yaml_quoted(notes)}
"""


def starter_plan_text(
    run_id: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    *,
    proposal: dict | None,
) -> str:
    supporting_text = ", ".join(f"`{target}`" for target in supporting_targets) if supporting_targets else "`none`"
    why_this = (
        proposal["why_now"]
        if proposal is not None
        else "Replace with the local failure mode this run is trying to reduce."
    )
    hypothesis = (
        proposal["change_hypothesis"]
        if proposal is not None
        else "Replace with why this target is narrow enough for a one-mechanism experiment."
    )
    expected_signal = (
        proposal["expected_binary_signal"]
        if proposal is not None
        else "Replace with the exact promotion or non-regression signal you expect to observe."
    )
    explicit_boundary = (
        proposal["single_mechanism_scope"]
        if proposal is not None
        else "Do not broaden the run beyond one primary mechanism."
    )
    return f"""# {run_id}

## Chosen target
- Primary target: `{primary_targets[0]}`
- Supporting targets: {supporting_text}

## Why this is the right first mechanism
- {why_this}
- {hypothesis}

## Expected binary signal
- {expected_signal}

## Suggested baseline capture order
1. `baseline-lint.json`
2. `baseline-eval.json`
3. `baseline-mechanism-assessment.json`

## Suggested candidate capture order
1. run the scoped mutation command
2. rerun repo health gate
3. `candidate-lint.json`
4. `candidate-eval.json`
5. `candidate-mechanism-assessment.json`
6. `promotion-report.json`

## Follow-up capture
- Before closing the run, append any reusable automation or repo hygiene follow-up to `runs/{run_id}/{IMPROVEMENT_OBSERVATIONS_FILENAME}`.

## Explicit boundary
- {explicit_boundary}
"""


def starter_open_questions(test_files: list[str], *, proposal: dict | None) -> str:
    test_text = ", ".join(f"`{path}`" for path in test_files) if test_files else "`none declared yet`"
    proposal_question = (
        f"5. Proposal `{proposal['proposal_id']}`에서 실제로 freeze할 focused tests와 mutation command는 무엇인가?\n"
        if proposal is not None
        else ""
    )
    return f"""# Open Questions

1. Which one mechanism is actually in scope for this run?
2. Which focused tests or commands will justify non-regression? Current seed: {test_text}
3. What signoff or append-only logging step remains after promotion evaluation?
4. What reusable automation or repo hygiene follow-up should be recorded in `improvement-observations.json` if this run surfaces one?
{proposal_question}"""


def initial_planning_validation(
    run_id: str,
    primary_targets: list[str],
    test_files: list[str],
    *,
    proposal: dict | None,
) -> dict:
    checks = [
        {
            "id": "single_mechanism_scope",
            "status": "PASS",
            "detail": f"Primary target is frozen to {primary_targets[0]} and supporting targets stay explicit.",
            "required_artifacts": ["seed.yaml"],
        },
        {
            "id": "baseline_artifacts_planned",
            "status": "PASS",
            "detail": "Baseline eval, lint, and mechanism assessment paths are fixed under this run directory.",
            "required_artifacts": ["seed.yaml", "run-ledger.json"],
        },
        {
            "id": "candidate_artifacts_planned",
            "status": "PASS",
            "detail": "Candidate eval, lint, mechanism assessment, changed-files manifest, and promotion-report paths are fixed under the same run id.",
            "required_artifacts": ["run-ledger.json", "promotion-report.json", "changed-files-manifest.json"],
        },
        {
            "id": "target_tests_declared",
            "status": "PASS" if test_files else "WARN",
            "detail": (
                "Focused test files are frozen before mutation starts."
                if test_files
                else "Declare focused tests before mutation starts."
            ),
            "required_artifacts": ["seed.yaml"],
        },
        {
            "id": "improvement_observations_ready",
            "status": "PASS",
            "detail": "A run-local observation file is ready for automation follow-ups discovered during execution.",
            "required_artifacts": [IMPROVEMENT_OBSERVATIONS_FILENAME],
        },
        {
            "id": "signoff_or_log_plan_present",
            "status": "PASS",
            "detail": "Promotion report and run-ledger already point to signoff and append-only log surfaces.",
            "required_artifacts": ["run-ledger.json", "promotion-report.json"],
        },
    ]
    if proposal is not None:
        checks.append(
            {
                "id": "proposal_snapshot_captured",
                "status": "PASS",
                "detail": f"Selected proposal {proposal['proposal_id']} is frozen under this run directory for stable provenance.",
                "required_artifacts": ["proposal-snapshot.json", "seed.yaml"],
            }
        )
    return {
        "$schema": PLANNING_VALIDATION_SCHEMA,
        "run_id": run_id,
        "status": "WARN",
        "summary": (
            f"Mechanism run {run_id} is scaffolded around {primary_targets[0]}, "
            "but baseline/candidate capture and promotion evaluation have not run yet."
        ),
        "checks": checks,
        "open_questions": [],
        "signoff": {
            "required": True,
            "status": "pending",
            "by": "",
            "ts": "",
        },
        "next_action": "Capture baseline lint/eval/mechanism artifacts, run the mutation command, then evaluate promotion.",
    }


def initial_run_ledger(
    run_id: str,
    *,
    include_proposal_snapshot: bool,
    context: RuntimeContext | None = None,
) -> dict:
    created_artifacts = [
        "seed.yaml",
        "planning-validation.json",
        "run-ledger.json",
        IMPROVEMENT_OBSERVATIONS_FILENAME,
        "promotion-report.json",
        "plan.md",
        "open-questions.md",
        "baseline-eval.json",
        "candidate-eval.json",
        "baseline-lint.json",
        "candidate-lint.json",
        "baseline-mechanism-assessment.json",
        "candidate-mechanism-assessment.json",
        "changed-files-manifest.json",
    ]
    if include_proposal_snapshot:
        created_artifacts.insert(4, "proposal-snapshot.json")
    return {
        "$schema": RUN_LEDGER_SCHEMA,
        "run_id": run_id,
        "status": "draft",
        "events": [
            {
                "ts": timestamp(context),
                "type": "created",
                "summary": "Initialized mechanism experiment artifacts from the mechanism-run starter bundle.",
                "artifacts": created_artifacts,
                "decision": "",
            }
        ],
    }


def placeholder_promotion_report(
    run_id: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    log_summary: str,
) -> dict:
    return {
        "$schema": PROMOTION_REPORT_SCHEMA,
        "run_id": run_id,
        "mode": "report_only",
        "artifact_class": "system_mechanism",
        "decision": "HOLD",
        "summary": log_summary,
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "checks": [
            {
                "id": "mechanism_scope_frozen",
                "status": "WARN",
                "detail": "Replace with actual gate results after baseline/candidate artifacts are generated.",
            }
        ],
        "signoff": {
            "required": True,
            "status": "pending",
            "by": "",
            "ts": "",
        },
        "log": {
            "required": True,
            "page": "system/system-log.md",
            "summary": log_summary,
            "status": "pending",
            "entry_ref": "",
        },
        "history": {"status": "active", "reason": "", "by": "", "ts": ""},
        "next_action": "Run promotion evaluation after baseline/candidate artifacts are generated.",
        "inputs": {
            "baseline_eval_report": run_rel(run_id, "baseline-eval.json"),
            "candidate_eval_report": run_rel(run_id, "candidate-eval.json"),
            "baseline_lint_report": run_rel(run_id, "baseline-lint.json"),
            "candidate_lint_report": run_rel(run_id, "candidate-lint.json"),
            "baseline_mechanism_report": run_rel(run_id, "baseline-mechanism-assessment.json"),
            "candidate_mechanism_report": run_rel(run_id, "candidate-mechanism-assessment.json"),
            "changed_files_manifest": run_rel(run_id, "changed-files-manifest.json"),
            "run_ledger": run_rel(run_id, "run-ledger.json"),
        },
    }
