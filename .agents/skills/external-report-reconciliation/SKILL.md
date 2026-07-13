---
name: external-report-reconciliation
description: Reconcile LLMwiki external reports, action-matrix status and lifecycle entries, remediation backlog items, improvement observations, and archive readiness against current repository evidence. Use for read-only audits of whether recommendations are implemented, partial, stale, superseded, awaiting release verification, operator-only, or ready for archive review.
---

# External Report Reconciliation

Use this file as the canonical reconciliation workflow. Keep role profiles and public docs as thin pointers; do not duplicate the procedure there.

## Respect the Boundary

Read `AGENTS.md` first. Read `AGENTS.local.md` before inspecting full-vault surfaces such as `external-reports/`, local action matrices, remediation backlogs, or improvement observations.

In a public mirror, assume private reports and generated evidence may be absent. Use public-safe schemas, producers, tests, Make contracts, and documentation without inventing corpus or report contents.

Keep reconciliation read-only unless the user explicitly requests an official refresh, archive, close, or implementation lane. Never copy private report prose into public docs, tests, or fixtures.

## Use Current Authorities

Treat these as generated evidence when present, not source or release authority:

- `external-reports/report-reference-manifest.json`
- `ops/reports/external-report-action-matrix.json`
- `ops/reports/generated-artifact-index.json`
- `ops/reports/artifact-freshness-report.json`
- `ops/reports/remediation-backlog.json`
- `ops/reports/task-improvement-observations/**/improvement-observations.json`

Read current schemas, runtime producers, and focused tests before using enum values or
recommending a lane. Read external-report lifecycle and action targets in
`mk/release-evidence.mk`, remediation-backlog targets in `mk/release-learning.mk`,
and artifact orchestration in `mk/artifact.mk`; treat `mk/release.mk` as their umbrella
variable and include surface. Release and promotion authority remains in staged
`build/release/*manifest.json` evidence and official release gates.

## Reconcile

1. Identify the reports, recommendations, dates, or action IDs in scope.
2. Check generated-evidence currentness before trusting conclusions. Inspect artifact status, report status, currentness, source revision and tree fingerprint, input fingerprints, canonical freshness state, active-root coverage, and reference-manifest alignment.
3. Report stale or incomplete generated evidence before interpreting its totals.
4. Read relevant improvement observations so closed work is not reopened.
5. Map each prose recommendation to current `ACTION_CATALOG` IDs, action-matrix items, backlog items, observations, and source/test evidence. Keep prose-only judgment separate from deterministic evidence.
6. Classify each item on independent axes:
   - action status: use the current matrix schema values;
   - action lifecycle: use the current schema/runtime values;
   - evidence condition: `current`, `stale`, `missing`, `binary_operator_review`, or `prose_only`;
   - archive implication: `archive_ready`, `keep_active`, `operator_only`, or `not_requested`.
7. For every report in scope, record its path and digest, report type, matched action IDs, unmatched recommendation or heading count, and any operator-only rationale. Use sanitized labels or digests instead of private verbatim text.
8. Keep binary or non-extractable reports operator-only unless an explicit extracted mapping exists.
9. Do not infer archive readiness from location, active report count, or broad implemented totals. Require complete per-report mapping or retain `keep_active`/`operator_only`.
10. Recommend the smallest official next lane from current status reasons, planner output, and Make ownership. Do not substitute reconciliation for release proof.

## Result Discipline

Keep action status, lifecycle, evidence condition, and archive implication visibly separate. Surface stale or missing evidence, the minimal next action, and residual risk. Follow any stricter output contract supplied by the invoking role or user.
