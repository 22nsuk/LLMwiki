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
| `ops/scripts/mechanism/mutation_proposal_runtime.py` | `build_report()` already calls `_load_mutation_report_inputs()`, `_assemble_mutation_proposals()`, `_assemble_mutation_diagnostics()`, `_mutation_report_payload()`, then validates. | Move `_MutationReportInputs`, `_load_mutation_report_inputs()`, report/session/log readers, and policy override handling into a mutation proposal input helper. | Move candidate-to-proposal mapping, bootstrap proposal creation, next-run repair selection, queue pressure, and recent-log-overlap decisions into pure decision helpers. | Move `_mutation_report_payload()` and envelope/text-input assembly into a renderer helper. | Move `_report_status()`, `_empty_queue_blockers()`, source evidence gap gating, and dedupe/recent-overlap unblock rules into named promotion-rule helpers. | Preserve `build_report()` and CLI import surface; extract loader first because the current façade boundary is already explicit near the bottom of the file. |
| `ops/scripts/mechanism/auto_improve_runtime.py` | `run_auto_improve_session()` coordinates request coercion, session start, loop state, iteration execution, completion, and maintenance. | Move request/session loading, goal contract snapshot loading, existing session loading, and readiness/report refresh wrappers into loader helpers. | Move stop-reason evaluation, repeated blocker detection, queue action planning, maintenance cycle metadata, and budget/timeout decisions into pure decision helpers. | Move session report writing payload assembly and maintenance action plan payload assembly behind renderer helpers while preserving existing schema paths. | Move learning preflight authorization, quarantine/pre-promotion failure policy, maintenance resume eligibility, and promotion/stop conditions into promotion-rule helpers. | Extract stop/maintenance decision helpers before touching execution plumbing; they are already mostly pure and have focused tests. |
| `ops/scripts/release/release_evidence_dashboard.py` | `build_report()` loads dashboard reports, derives signals, gates, status counts, then calls `_render_dashboard_report()`. | Keep `_load_dashboard_reports()` as the seed and move report loading plus fingerprint/currentness input gathering into a dashboard input helper. | Move component gates, learning guard summaries, finalizer duration decisions, status counts, and dashboard status classification into decision helpers. | Move `_render_dashboard_report()`, inputs payload, summary payload, and budget signal assembly into a renderer helper. | Move advisory lifecycle, signoff revalidation, closeout decision gate, and learning-claim blocking rules into promotion-rule helpers. | Extract renderer after adding byte-identical report tests; the current render function is already a clean boundary. |
| `ops/scripts/release/release_closeout_summary.py` | `build_report()` already calls `_load_closeout_sources()`, `_prepare_closeout_state()`, and `_render_closeout_report()` through existing source/risk/render helper modules. | Continue moving source specs, source loading, learning signoff loading, previous closeout loading, and dependency reproducibility input preparation into `release_closeout_source_runtime.py` or a closeout input helper. | Move component evaluation, source-tree coherence, live make check, readiness state, and downstream digest mismatch decisions into closeout decision helpers. | Keep report assembly in `release_closeout_render_runtime.py`; move remaining envelope/file-input assembly there only after schema samples and closeout tests are pinned. | Keep accepted-risk finalization, taxonomy coverage, signoff application, and clean-lane blocking decisions in `release_closeout_risk_runtime.py` or smaller promotion-rule helpers. | Finish the partially-complete split by moving the remaining envelope/input glue out of the large module while keeping `build_report()` as the stable façade. |

### Completed First-Split Moves

The first extraction pass intentionally moved only seams that were already
pure or already sat at a stable report assembly boundary.

| Hotspot | Extracted helper | Boundary | Contract guard |
| --- | --- | --- | --- |
| `ops/scripts/mechanism/mutation_proposal_runtime.py` | `ops/scripts/mechanism/mutation_proposal_promotion_runtime.py` | Promotion rule: source-evidence gaps, empty-queue blockers, blocked count, report status. | Focused helper tests plus the façade golden digest. |
| `ops/scripts/mechanism/auto_improve_runtime.py` | `ops/scripts/mechanism/auto_improve_maintenance_decision_runtime.py` | Decision/promotion rule: maintenance queue action and cycle metadata. | Focused helper tests plus selected auto-improve session tests. |
| `ops/scripts/release/release_evidence_dashboard.py` | `ops/scripts/release/release_evidence_dashboard_render_runtime.py` | Renderer: dashboard input payloads, summary payloads, budget signals, accepted-risk delta rendering. | Dashboard focused report-contract test plus façade golden digest. |
| `ops/scripts/release/release_closeout_summary.py` | `ops/scripts/release/release_closeout_envelope_runtime.py` | Renderer/input glue: closeout envelope constants and file-input source identity assembly. | Closeout focused report-contract tests plus façade golden digest. |

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

| Item | Status | Reason | Revisit condition |
| --- | --- | --- | --- |
| `ops/scripts/release/release_evidence_planner.py::build_plan()` | Explicitly defer | The remaining budget trigger is `parameter_count` only: the public keyword façade carries explicit release evidence path overrides exposed through `parse_args()`/`main()` and is imported directly by tests. Moving the body behind a private request object would not remove the AST-level parameter count, while collapsing the signature into a public request object would violate the current façade-preservation rule. | Revisit only as an intentional release planner API migration with compatibility tests, docs, and Make/CLI review. |

## Entry Documents

- Repository overview: [../README.md](../README.md)
- Architecture: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Ops runtime map: [../docs/ops-runtime.md](../docs/ops-runtime.md)
- Self-improvement loop: [../docs/self-improvement-runtime.md](../docs/self-improvement-runtime.md)
- Development checks: [../docs/development.md](../docs/development.md)
