# Runtime Orientation

This file replaces the older decomposition note with a newcomer-friendly map of
the current maintainer runtime. It is not the full contract; it points to the
live owners and explains how the pieces fit together.

## Mental Model

The runtime has three cooperating layers:

1. Policy and schemas define allowed behavior and report shape.
2. Make targets orchestrate repeatable workflows.
3. Python packages implement bounded runtime steps and write schema-backed evidence.

Most work should start from a Make target, then follow the target to its script
package and schema.

## Main Runtime Areas

| Area | Package | Make file | What it owns |
| --- | --- | --- | --- |
| Shared runtime helpers | `ops/scripts/core/` | `mk/core.mk`, `mk/artifact.mk` | artifact IO, paths, policy, schemas, command execution, workflow planning |
| Eval and lint | `ops/scripts/eval/` | `mk/eval.mk`, `mk/test.mk` | wiki lint/eval, warning budget, complexity, doc audit |
| Registry | `ops/scripts/registry/` | `mk/registry.mk` | raw registry export, preflight, normalization, intake routing |
| Mechanism loop | `ops/scripts/mechanism/` | `mk/mechanism.mk` | mechanism review, mutation proposal, goal runtime, promotion experiments |
| Release | `ops/scripts/release/` | `mk/release.mk` | release evidence, external report lifecycle, sealing, closeout summaries |
| Learning | `ops/scripts/learning/` | `mk/release.mk` | learning claims, readiness signoff, remediation backlog, negative lessons |
| Public export | `ops/scripts/public/` | `mk/public.mk` | public mirror, public check, CBM public export |
| Supply chain | `ops/scripts/supply_chain/` | `mk/supply_chain.mk` | provenance, SBOM, advisory, OpenVEX, in-toto, Sigstore |

## How To Trace A Change

1. Identify the Make target that a user would run.
2. Read the recipe in `mk/*.mk`.
3. Follow the `python -m ops.scripts...` entrypoint to the canonical package.
4. Read the schema for any report the script writes.
5. Add or update tests near the runtime owner.
6. Close with the narrow Make/Pytest gate for that surface.

## Current Design Direction

- Keep orchestrators thin and move reusable state transitions into helper modules.
- Prefer schema-backed reports over prose-only evidence.
- Keep public export reproducible without private corpus state.
- Keep generated artifact promotion explicit: candidate under `tmp/`, validated durable report under policy-approved output.
- Keep compatibility aliases only as migration surfaces; new docs should teach current package paths.
- Keep authority axes explicit; do not collapse source-closeout, sealed-run, and diagnostic evidence into one synthetic status.
- Keep operator-facing currentness computed from live HEAD/fingerprint/domain checks, not from self-declared current fields alone.

## Responsibility Split Plan

The runtime-codehealth-hardening sprint uses the same façade shape that already
exists in `ops/scripts/mechanism/finalize_run.py`: the CLI module parses
arguments and maps known runtime exceptions to exit codes, while
`ops/scripts/mechanism/finalize_run_runtime.py` coordinates artifact loading,
state assembly, payload validation, and atomic writes through helper modules.
New hotspot work should move in that direction without changing public function
signatures or schema-backed report payloads.

Each hotspot is split along four boundaries:

| Boundary | Meaning | Extraction rule |
| --- | --- | --- |
| Loader | Read policy, reports, manifests, filesystem state, and injected runtime context. | Keep I/O here; return dataclasses or plain payloads that can be reused by tests. |
| Decision | Pure state transitions, ranking, gate decisions, and status classification. | No writes, no wall-clock calls, no schema output assembly. |
| Renderer | Assemble schema-backed reports from loaded inputs and decisions. | Use the injected `RuntimeContext` timestamp already carried by loader inputs. |
| Promotion rule | Decide whether an action may advance, stop, require operator review, or remain diagnostic. | Keep rules small, named, and testable with focused unit/property tests. |

### Planned Hotspot Splits

| Hotspot | Current façade | Loader extraction | Decision extraction | Renderer extraction | Promotion-rule extraction | First safe move |
| --- | --- | --- | --- | --- | --- | --- |
| `ops/scripts/mechanism/mutation_proposal_runtime.py` | `build_report()` calls the loader, proposal assembly, diagnostics assembly, report renderer, and validator in order. | Done: `ops/scripts/mechanism/mutation_proposal_loader_runtime.py` owns `MutationReportInputs`, policy overrides, current mechanism-review loading, optional report/session loading, and recent-log input selection. | Move candidate-to-proposal mapping, bootstrap proposal creation, next-run repair selection, queue pressure, and recent-log-overlap decisions into pure decision helpers. | Move `_mutation_report_payload()` and envelope/text-input assembly into a renderer helper. | Done for status/blocker rules in `ops/scripts/mechanism/mutation_proposal_promotion_runtime.py`; keep moving remaining dedupe/recent-overlap promotion decisions only with focused tests. | Next safe move: extract candidate-to-proposal decision helpers while preserving `build_report()` and CLI import surface. |
| `ops/scripts/mechanism/auto_improve_runtime.py` | `run_auto_improve_session()` coordinates request coercion, session start, loop state, iteration execution, completion, and maintenance. | Move request/session loading, goal contract snapshot loading, existing session loading, and readiness/report refresh wrappers into loader helpers. | Move stop-reason evaluation, repeated blocker detection, queue action planning, maintenance cycle metadata, and budget/timeout decisions into pure decision helpers. | Move session report writing payload assembly and maintenance action plan payload assembly behind renderer helpers while preserving existing schema paths. | Move learning preflight authorization, quarantine/pre-promotion failure policy, maintenance resume eligibility, and promotion/stop conditions into promotion-rule helpers. | Extract stop/maintenance decision helpers before touching execution plumbing; they are already mostly pure and have focused tests. |
| `ops/scripts/mechanism/auto_improve_readiness_runtime.py` readiness cluster | `build_readiness_report()` loads reports, derives queue state, assesses execution/learning/promotion readiness, and renders the readiness report. | Done for queue derivation ownership: `ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py` owns `ReadinessQueueState`, and the façade now carries that object instead of duplicating queue scalar fields. | Done for `_dict_field` leakage, queue payload ownership, and execution-readiness field ownership: readiness queue/release-authority/worktree-guard helpers share `ops/scripts/core/payload_field_runtime.py::dict_field()`, queue/check/fallback/remediation assembly lives behind `readiness_queue_payloads()`, and queue-derived execution reasons/next action live behind `readiness_execution_fields()`. | Keep top-level readiness report assembly in the façade until learning/promotion payload helpers are byte-pinned and source paths stay stable. | Keep admission independent: `goal_runtime_run_admission.py` must recompute runnable queue/currentness instead of trusting readiness' snapshot. | Next safe move: extract learning/promotion payload helpers that consume queue-derived fields without importing `goal_runtime_run_admission.py` or widening the report schema. |
| `ops/scripts/release/release_evidence_dashboard.py` | `build_report()` loads dashboard reports, derives signals, gates, status counts, then calls `_render_dashboard_report()`. | Keep `_load_dashboard_reports()` as the seed and move report loading plus fingerprint/currentness input gathering into a dashboard input helper. | Move component gates, learning guard summaries, finalizer duration decisions, status counts, and dashboard status classification into decision helpers. | Move `_render_dashboard_report()`, inputs payload, summary payload, and budget signal assembly into a renderer helper. | Move advisory lifecycle, signoff revalidation, closeout decision gate, and learning-claim blocking rules into promotion-rule helpers. | Extract renderer after adding byte-identical report tests; the current render function is already a clean boundary. |
| `ops/scripts/release/release_closeout_summary.py` | `build_report()` already calls `_load_closeout_sources()`, `_prepare_closeout_state()`, and `_render_closeout_report()` through existing source/risk/render helper modules. | Continue moving source specs, source loading, learning signoff loading, previous closeout loading, and dependency reproducibility input preparation into `release_closeout_source_runtime.py` or a closeout input helper. | Move component evaluation, source-tree coherence, live make check, readiness state, and downstream digest mismatch decisions into closeout decision helpers. | Keep report assembly in `release_closeout_render_runtime.py`; move remaining envelope/file-input assembly there only after schema samples and closeout tests are pinned. | Keep accepted-risk finalization, taxonomy coverage, signoff application, and clean-lane blocking decisions in `release_closeout_risk_runtime.py` or smaller promotion-rule helpers. | Finish the partially-complete split by moving the remaining envelope/input glue out of the large module while keeping `build_report()` as the stable façade. |

### Completed First-Split Moves

The first extraction pass intentionally moved only seams that were already
pure or already sat at a stable report assembly boundary.

| Hotspot | Extracted helper | Boundary | Contract guard |
| --- | --- | --- | --- |
| `ops/scripts/core/command_log_summary_backfill.py` | `_BackfillState` plus group collection, summary-reference repair, closure, fingerprint, raw-delete, and summary helpers. | Loader/decision/renderer: legacy command-log group handling and backfill report assembly while deleting the unused local reference accumulator. | Command-log summary backfill focused tests plus static checks. |
| `ops/scripts/core/command_runtime.py` | `RunWithTimeoutRequest`, `_RunWithTimeoutState`, and completed/timeout result helpers. | Loader/decision/renderer: timeout execution request coercion, process start state, communicate handling, timeout recovery, and result payload assembly are split while legacy `run_with_timeout(argv, cwd=..., timeout_seconds=...)` callers remain supported. | Command runtime, heartbeat, subprocess smoke tests plus static checks. |
| `ops/scripts/core/request_coercion_runtime.py` | `coerce_request_or_kwargs()`, first used by next-run decision and release-source-ready commit helpers. | Cross-cutting hygiene: pure request-object-or-legacy-kwargs coercion is shared without absorbing positional, dict, allowlist, or path-resolving compatibility contracts. | Request coercion helper tests plus next-run decision and release source ready commit focused tests. |
| `ops/scripts/core/payload_field_runtime.py` | `dict_field()` now serves readiness queue, release-authority, worktree-guard, and façade summary helpers. | Cross-cutting hygiene: nested dict payload access is shared inside the readiness cluster instead of importing private helpers across ownership boundaries. | Payload helper tests plus readiness queue/runtime focused tests and static checks. |
| `ops/scripts/core/codex_goal_client.py` | Section builder helpers in the same module. | Renderer: goal contract payload sections for guard, roots, budgets, execution policy, backend, stop conditions, evidence, and metadata. | `tests/test_codex_goal_client.py`, goal runtime certificate tests, and goal runtime runner tests. |
| `ops/scripts/mechanism/goal_runtime_certificate_report.py` | State/render helpers in the same module. | Loader/renderer: certificate update state, file-input collection, command observability, envelope assembly, and final report rendering. | Goal runtime certificate, admission, and status tests. |
| `ops/scripts/mechanism/mutation_proposal_runtime.py` | `ops/scripts/mechanism/mutation_proposal_loader_runtime.py` | Loader: report input dataclass, policy override handling, current mechanism-review validation, optional outcome/remediation/session report loading, and recent-log selection. | Focused build-report tests plus the façade golden digest. |
| `ops/scripts/mechanism/mutation_proposal_runtime.py` | `ops/scripts/mechanism/mutation_proposal_promotion_runtime.py` | Promotion rule: source-evidence gaps, empty-queue blockers, blocked count, report status. | Focused helper tests plus the façade golden digest. |
| `ops/scripts/mechanism/next_run_repair_queue_runtime.py` | `_NextRunRepairScope` and `_next_run_repair_scope()`. | Loader/decision: primary/supporting targets, test targets, source run identity, failure taxonomy, and evidence paths for repair proposals. | Next-run repair queue tests plus mutation proposal build/promotion tests. |
| `ops/scripts/mechanism/auto_improve_runtime.py` | `ops/scripts/mechanism/auto_improve_maintenance_decision_runtime.py` | Decision/promotion rule: maintenance queue action and cycle metadata. | Focused helper tests plus selected auto-improve session tests. |
| `ops/scripts/mechanism/auto_improve_readiness_runtime.py` | Existing `ReadinessQueueState` and `readiness_queue_payloads()` from `ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py` are now carried/used by `ReadinessInputs` and `render_readiness_report()`. | Loader/decision/renderer ownership: queue derivation, queue payload, fallback payload, check assembly, and remediation assembly stay in the queue runtime while the façade no longer unpacks and re-owns queue scalar fields. | Readiness runtime, readiness queue, queue selection, goal admission, next-run repair, schema sample, and static checks. |
| `ops/scripts/release/release_evidence_dashboard.py` | `ops/scripts/release/release_evidence_dashboard_render_runtime.py` | Renderer: dashboard input payloads, summary payloads, budget signals, accepted-risk delta rendering. | Dashboard focused report-contract test plus façade golden digest. |
| `ops/scripts/release/release_closeout_summary.py` | `ops/scripts/release/release_closeout_envelope_runtime.py` | Renderer/input glue: closeout envelope constants and file-input source identity assembly. | Closeout focused report-contract tests plus façade golden digest. |
| `ops/scripts/release/external_report_lifecycle_runtime.py` | Reason-detail resolver tables and helpers in the same module. | Decision: action-status reason mapping, prefix handling, and exact release auto-promotion reason IDs. | External report action matrix status/lifecycle/static tests. |
| `ops/scripts/release/external_report_release_verification_runtime.py` | Release verified reason-id helper sets in the same module. | Decision: verified action reason ID assembly while preserving reason order. | External report action matrix status/lifecycle/static tests. |
| `ops/scripts/release/release_source_ready_commit.py` | `RunCommitRequest`, `_RunCommitState`, and head/amend/dirty-path/stage/commit guard helpers. | Loader/decision/renderer: release-source-ready commit request coercion, snapshot/amend validation, dirty path policy, dry-run/no-change handling, and git side effects are separated while legacy CLI keyword calls remain supported. | Release source ready commit focused tests plus static checks. |
| `ops/scripts/release/release_status_surface.py` | `StatusSurfaceSignals` plus status-line builder helpers. | Renderer: release status signal coercion, lock/dependency detail rendering, and each public status line are split while legacy keyword callers remain supported. | Release status surface focused tests plus static checks. |
| `ops/scripts/release/release_workflow_order_guard.py` | `_WorkflowOrderInputs`, check assembly, envelope, summary, and target-recipe helpers. | Loader/renderer: Makefile invocation loading, planner report reuse, guard check assembly, and report payload rendering. | Release workflow order guard tests plus static checks. |
| `tests/test_release_workflow_order_guard.py` | Scenario recipe constants, Makefile template helper, and a thin `_write_makefile()` fixture method. | Test-lane cost/readability: workflow-order scenario inputs are table-like constants instead of a 200-line fixture method. | Release workflow order guard focused tests plus static checks. |
| `tests/test_makefile_auto_improve_goal_static_gates.py` | Purpose-specific goal admission, contract/status, lock/preflight, local evidence, closeout, and refresh recipe tests. | Test-lane cost/readability: auto-improve goal Makefile assertions are split by runtime phase instead of two large static gate methods. | Auto-improve goal Makefile focused tests plus static checks. |
| `tests/test_makefile_test_execution_summary_gates.py` | Phony target and assignment tables plus purpose-specific recipe tests. | Test-lane cost/readability: report-contract, currentness/preflight, and full-suite reuse assertions are split by scenario instead of one large Makefile static gate. | Test execution summary Makefile focused tests plus static checks. |
| `tests/test_external_report_action_matrix_status.py` | Goal-native fixture constants, report builders, and separate active/completed contract assertions. | Test-lane cost/readability: goal runtime external-report action evidence is prepared through named synthetic report builders instead of one long action-matrix scenario method. | External report action matrix status focused tests plus static checks. |
| `tests/test_run_mechanism_experiment.py` / `tests/run_mechanism_experiment_test_utils.py` | Raw-registry preflight convergence constants, fake callback builders, run helper, and artifact assertion helpers now live in the wrapper fixture utility. | Test-lane cost/readability: wrapper-driven generated artifact convergence is owned by the shared scenario harness while the test method stays focused on setup and assertions. | Run mechanism experiment focused tests plus static checks. |
| `ops/scripts/release/release_auto_promotion_ready.py` | `_ReadyCheckInputs` plus phase, goal-runtime, manifest-authority, operator, and auto-improve check helpers. | Decision/renderer: ready-check assembly is grouped by authority area before manifest rendering. | Release auto-promotion ready focused tests plus static checks. |
| `ops/scripts/mechanism/auto_improve_next_run_decision_runtime.py` | `NextRunDecisionRequest`, request coercion, executor-report path, evidence path, and decision-builder helpers. | Loader/decision: next-run decision inputs are carried by a typed request while legacy keyword callers remain supported by the facade. | Next-run decision tests, next-run repair queue tests, selected auto-improve iteration tests, and static checks. |
| `ops/scripts/test/test_execution_reuse_runtime.py` | `ReuseCurrentnessRequest`, command identity helpers, and diagnostics assembly helpers. | Loader/decision: reuse currentness diagnostics are request-shaped, with existing dictionary and legacy keyword call surfaces preserved. | Test execution summary focused tests plus static checks. |

No compatibility shim or duplicate implementation was kept for these moves:
the original blocks were deleted from the hotspot modules in the same change.

### Complexity Ratchet Ceiling

`system_refactor_policy.complexity_ratchet` stores the structural complexity
ratchet as policy, not as a report-schema extension. The contract is split into
two ledgers so the gate can block both new debt and resurfaced debt.

- `warn_targets`: active ceiling entries currently allowed to remain in `warn`.
- `resolved_targets`: former ceiling entries that returned to `pass` and must
  now fail immediately if they reappear as `warn`.

`complexity-budget-touched-check` stays a touched-surface gate. It still writes
the same touched complexity report, then applies policy-backed ratchet
regression logic when touched inputs are provided. This keeps the existing
structural complexity report schema unchanged while making new warn targets and
resurfaced debt actionable.

### Pre-Split Golden Baseline

`tests/test_runtime_hotspot_facade_golden_outputs.py` pins a slow, synthetic
baseline for the four first-split façades. It builds each output twice with a
fixed injected clock, validates the schema-backed payload, scans for local path
leaks, and compares canonical JSON bytes against frozen digests. The
auto-improve façade is intentionally captured as a normalized artifact bundle
because it writes several sidecars; raw file hashes that vary with in-memory
dict ordering are converted to canonical loaded-payload hashes before digesting.
Run this test before and after any extraction that touches the planned hotspot
files.

## Preservation And Delete-First Ledger

Use this ledger whenever a split keeps code that appears redundant or
temporary. If a preserved item is not listed here with a reason, the default is
to delete it during the extraction that made it unnecessary.

| Item | Status | Reason |
| --- | --- | --- |
| Existing public entrypoints such as `build_report()`, `write_report()`, `parse_args()`, and `main()` | Preserve | Tests, Make targets, compatibility aliases, and report-contract smoke tests import these names directly. They should become thin façades, not disappear during helper extraction. |
| Existing schema-backed report fields and envelope source paths | Preserve until an intentional contract update | Downstream report consumers depend on byte-identical field shape. Helper extraction can add helper source paths only with matching schema/sample/test/docs updates. |
| Large pure-ish helper blocks inside hotspot files | Temporary preserve | Planning alone does not prove dead code. Move them only with focused tests, then delete the original block in the same change. |

No dead or duplicate implementation is intentionally preserved by this plan.
Future extraction tasks must update this ledger before leaving any redundant
compatibility wrapper, shim, or unused helper behind.

### P2 Deferral Ledger

Use this ledger when a function-budget proposal is real but the only safe fix
would require an intentional public façade migration rather than a private
helper extraction.

No current P2 function-budget deferral is intentionally retained. New entries
must name the public façade contract, the verification that prevents immediate
removal, and the condition that makes the migration safe.

## Entry Documents

- Repository overview: [../README.md](../README.md)
- Architecture: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Ops runtime map: [../docs/ops-runtime.md](../docs/ops-runtime.md)
- Self-improvement loop: [../docs/self-improvement-runtime.md](../docs/self-improvement-runtime.md)
- Development checks: [../docs/development.md](../docs/development.md)
