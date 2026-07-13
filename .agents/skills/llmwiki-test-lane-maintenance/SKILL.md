---
name: llmwiki-test-lane-maintenance
description: Maintain LLMwiki pytest lanes, changed-path minimums, Make selector variables, CI and release workflow routing, workflow-dependency planner checks, and Makefile static-gate test splits. Use when work changes ops/test-lane-registry.json, mk/test.mk, .github/workflows/ci.yml, .github/workflows/release.yml, tests/workflow_static_helpers.py, test-lane contract tests, or related public projections.
---

# LLMwiki Test Lane Maintenance

Keep the registry, Make targets, workflows, planner behavior, documentation, and tests aligned whenever a test lane or its routing contract changes.

## Read the Authorities

Read the following before editing:

1. `AGENTS.md` and any applicable local supplement.
2. `docs/development.md` for the public testing contract.
3. `ops/test-lane-registry.json` and its schema for canonical lane and changed-path data.
4. The owning Make, workflow, helper, and test files named by the requested change.

Treat the registry as the selector authority. Discover current selectors and commands from it; do not copy a complete selector inventory into this skill.

## Maintain the Contract

1. Classify the change: selector pack, Make target, CI or release routing, changed-path minimum, workflow dependency, static-gate split, or test-cost governance.
2. Map every affected owner before editing. A lane change commonly spans the registry, generated Make projection, workflow routing, planner expectations, documentation, and focused contract tests.
3. Edit canonical sources first. Never hand-edit generated selector projections as if they were authoritative.
4. Update directly affected tests and documentation in the same change. Preserve public/private boundaries and deterministic behavior.
5. Remove superseded selectors, commands, or assertions when the new contract makes them obsolete.

## Validate Proportionally

Run the narrowest relevant checks first, using `.venv/bin/python -m pytest` for focused pytest files.

- Run `make sync-derived` after changing source-derived projections or public prefixes. Use `make sync-derived-check` only for check-only validation.
- Run `make changed-path-minimum-test` to execute the registry-selected minimum for the task. When the worktree already contains unrelated changes, pass a task-owned changed-files manifest through `WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST`; the whole dirty diff is not evidence of the current task scope. Treat the selected lane as a minimum, not as final release proof.
- Run `make workflow-dependency-planner-check` when changed-path or dependency-planning semantics change.
- Run `make test-report-contract-core` when lane or report-contract semantics change.
- Run `make public-check` when the public boundary or export behavior changes.
- Finish with the broader repository gates required by `AGENTS.md` and the task scope.

If a validation command is absent or renamed, inspect the registry and Makefiles instead of guessing or preserving a stale command here.

## Guardrails

- Keep selector discovery registry-backed and schema-validated.
- Keep CI and release routing thin; avoid duplicating lane definitions in workflow YAML.
- Record exact focused pytest commands in duration estimates when the changed-path planner needs to schedule them.
- Preserve cost-aware split boundaries and explain any deliberate coverage reduction.
- Do not rely on private corpus or live run artifacts for public lane tests.
- Keep generated artifacts reproducible and free of local absolute paths.

## Done Criteria

The change is complete only when canonical registry data, generated projections, Make/workflow routing, planner output, focused tests, and public documentation agree, and the selected validation gates pass.
