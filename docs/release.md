# Release Workflow

Release work is evidence-driven. Converge targets update local-only reports;
check targets verify that already-generated evidence is current.
Release authority is staged so each manifest answers one question:
`build/release/release-run-manifest.json` says whether the current commit is
runnable, `build/release/release-sealed-run-manifest.json` says whether the
source ZIP and sidecars are sealed evidence, and
`build/release/release-auto-promotion-ready-manifest.json` says whether the
result can be promoted without operator intervention.

The release source ZIP is distinct from both the full local vault and the
public export. See [repository-surfaces.md](repository-surfaces.md) for the
surface comparison; this document owns release evidence and staged authority.

## Common Targets

- `make status` / `llm-wiki-status`: read-only operator status surface. It
  renders source closeout, sealed run, public summary, lockfile freshness,
  learning signoff, goal runtime certificate, and remote sync as one 7-line
  view without writing new authority evidence. Remote sync is read from live Git
  state, not from a stale release-run manifest sidecar. Lockfile freshness uses
  the canonical-index lock check, while the line detail also exposes ambient
  baseline lock-check status and the normalization step when those differ.
- `make release-check`: check-only release gate for the current tree.
- `make release-check-all-surfaces`: release check plus public policy and public export checks.
- `make release-run-ready`: one command to verify the current committed tree,
  emit canonical report-contract and full-suite test summaries, refresh/reuse
  current public-check evidence,
  refresh/reuse current full release-smoke evidence, refresh/reuse current
  source ZIP, source-package smoke, and clean-extract replay evidence, then
  write the runnable release-run manifest. It removes any older
  auto-promotion-ready manifest before refreshing runnable authority.
- `make release-run-ready-plan`: cheap read-only planner for the runnable stage.
  It records stale evidence causes and the minimal next target before a full
  run-ready refresh spends test/package cycles. It writes a local plan sidecar
  only; ignored evidence remains release-lane context, not public source. Reuse
  requires schema-valid evidence with matching producer, currentness,
  source-fingerprint, revision, and lane-specific semantics. Its stdout and
  JSON sidecar expose summary mode, duration-budget status, reason codes, and
  exact next targets; the runnable authority still belongs to
  `make release-run-ready`.
- `make release-run-ready-plan-check`: check-only form of the planner that fails
  when existing evidence is not reusable.
- `make release-run-ready-check`: revalidate the existing manifest against the
  current HEAD, source fingerprint, source ZIP, and source-package smoke report.
  Source-tree drift failures print the expected fingerprint, current
  fingerprint, changed-after-generated-at sample, and
  `minimal_remediation_target=release-run-ready`.
- `make release-sealed-run-ready-plan`: inspect runnable authority evidence and
  write the cost-aware action plan for sealing without rerunning stage 1. The
  planner requires both current passing run-ready evidence and current passing
  auto-promotion preseal evidence before it spends work on sealed sidecars.
- `make release-sealed-run-ready`: build sealed sidecars, including the sealed
  operator summary diagnostic, write the operator-free sealed post-seal
  attestation, run the sealed rehearsal check, and write the sealed-run
  manifest. It requires current passing runnable evidence and does not rerun the
  runnable stage. The operator summary is generated for Stage 3 reuse, but it is
  not part of the sealed-run authority sidecar set. Archived or preserved stale
  sidecars must also stay out of that active authority set and remain explicit
  non-authoritative evidence only. It also removes any older auto-promotion-ready
  manifest before refreshing sealed authority.
- `make release-sealed-run-ready-check`: revalidate existing sealed evidence
  without rerunning tests or rebuilding the package.
- `make release-auto-promotion-ready-plan`: inspect preflight, runnable,
  preseal, sealed, operator, auto-improve, goal-run status, and goal-runtime
  certificate evidence and write the cost-aware action plan for the promotion
  verdict.
- `make release-auto-promotion-goal-run-id-guard`: resolve the release
  goal-run binding and record final verification diagnostics. Explicit
  `GOAL_RUN_ID` values are accepted when they do not contradict current
  goal-run evidence; omitted values may still be inferred from matching current
  verified `goal-run-status` plus `goal-runtime-certificate` evidence. Missing
  or unverified certificate evidence is recorded as a final promotion blocker,
  not as a preflight bootstrap blocker. The Makefile default
  `auto-improve-trial` is only tolerated as an unselected input; it is blocked
  if it would become the effective release auto-promotion run id.
- `make release-auto-promotion-preflight`: refresh cheap unattended-promotion
  blockers before spending full run-ready cycles. It first runs the goal-run id
  guard, refreshes cheap generated prerequisites such as queue-input reports and
  the external-report action matrix, refresh-checks fast smoke, refreshes the
  selected report-contract summary for changed test fingerprints, then runs
  artifact freshness and checks remediation, learning revalidation, and
  auto-improve readiness without building release artifacts, sealing, or
  creating runtime-trial evidence. It removes any older final ready manifest
  before writing new preflight evidence.
- `make release-auto-promotion-safe-cleanup-cleanup-only`: normalize safe
  generated evidence before preseal. It removes stale goal-runtime transients,
  cleans tmp JSON candidates, backfills schema-backed historical run artifacts,
  and refreshes generated-artifact index plus artifact freshness without running
  fixed-point.
- `make release-auto-promotion-safe-cleanup-finalize`: run the optional
  ZIP-bound external-reference, batch-manifest, and fixed-point suffix. The
  legacy `make release-auto-promotion-safe-cleanup` target remains a wrapper for
  cleanup-only plus this explicit finalize step.
- `make generated-artifact-retention-clean`: dry-run a retention-aware cleanup
  of regenerated local residue. Pass `GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY=1`
  only when you intentionally want to remove allowlisted ignored residue such as
  source-package extracts and local tool caches; current release authority,
  private corpus roots, and run provenance are retained. Ignored run logs with
  missing, malformed, or path-incomplete fingerprint evidence are reported as
  `retention_blockers`; apply mode leaves them in place while deleting only
  candidates already classified as safe.
- `make command-log-summary-backfill`: prepare legacy run stdout/stderr for
  retention cleanup by writing schema-backed `command-log-summary.json` files
  and capped `*-trace.txt` streams, rewriting same-run executor/timeout/ledger
  references to those traces, refreshing run-artifact fingerprints, and then
  reporting retention status. Use `COMMAND_LOG_SUMMARY_BACKFILL_APPLY=1` with
  `COMMAND_LOG_SUMMARY_BACKFILL_ALL=1` or a specific
  `COMMAND_LOG_SUMMARY_BACKFILL_RUN_ID=<run-id>` to mutate evidence. Add
  `COMMAND_LOG_SUMMARY_BACKFILL_INCLUDE_RUN_COMMANDS=1` and
  `COMMAND_LOG_SUMMARY_BACKFILL_CLOSE_PROMOTED_UNREFERENCED=1` only when
  promoted finalized runs should be closed for retention. Raw deletion also
  requires `COMMAND_LOG_SUMMARY_BACKFILL_DELETE_RAW=1` plus
  `COMMAND_LOG_SUMMARY_BACKFILL_OPERATOR_CONFIRMATION=CONFIRM_COMMAND_LOG_RAW_DELETE`;
  it removes only non-empty raw command logs already classified
  `delete_allowed=true` by the retention report.
- `make release-auto-promotion-preseal`: refresh clean closeout, strict
  same-fingerprint cohort, remediation, learning, and auto-improve diagnostics
  after run-ready and before sealing. It refreshes cheap cohort inputs such as
  bootstrap, registry, fast smoke, generated index, artifact freshness, and
  external report references through the safe cleanup lane, then refreshes
  auto-improve readiness after those sealed-batch inputs settle so strict
  cohort checks do not read stale release-gate blockers. It only checks
  run-ready's full release-smoke and full-suite
  evidence for currentness instead of rerunning them. It removes any older final
  ready manifest before writing new preseal evidence, and writes a final
  fixed-point after its tracked report refreshes so finality remains terminal
  before sealing.
- `make release-auto-promotion-operator-summary`: manual fallback to refresh the
  cheap build-local operator diagnostics used by the promotion verdict when
  sealed sidecars are already current. It invalidates the final ready manifest
  because the operator diagnostic is a Stage 3 input.
- `make release-auto-promotion-ready`: low-cost promotion check that reads the
  current runnable and sealed manifests, reuses the sealed operator summary
  diagnostic, directly verifies current goal-run status plus goal-runtime
  certificate evidence, and decides unattended promotion. It never cascades into
  the lower runnable or sealing stages.
- `make release-auto-promotion-ready-check`: revalidate the existing
  auto-promotion manifest inputs without recomputing expensive evidence.
- `make release-converge`: mutating evidence convergence for release reports.
- `make release-converge-preflight`: first refreshes the narrow
  `generated-artifact-script-output` lane so `ops/script-output-surfaces.json`
  is current as a material output/fallback registry before report-contract
  summaries or release smoke can read it.
- `make release-converge-all-surfaces`: convergence plus public policy/export refresh.
- `make release-source-ready`: source-ready commit flow. Mutating convergence happens
  in `release-source-ready-prepare` before the commit; `release-post-commit-finalize`
  then checks revision-bound evidence for the new HEAD before
  `release-source-ready-post-verify` runs as a write-free check. Operator
  release summary is local-only evidence and is refreshed during the prepare
  convergence flow.
- `make release-post-commit-finalize`: official post-commit evidence suffix for
  source-ready commits. It runs check/current-only surfaces, writes the
  post-commit readback report, then leaves `release-closeout-finality-verify` as
  the final Make invocation. It fails if source fingerprint or source contract
  paths drift. Dirty tracked generated evidence is `attention` and points back to
  `release-source-ready-prepare`. It does not refresh full pytest evidence,
  staged authority manifests, report writer clusters, or action lifecycle
  cleanup. It also does not replace `release-run-ready`,
  `release-sealed-run-ready`, or `release-auto-promotion-ready` authority.
  When those staged authority sidecars, including the final
  auto-promotion-ready manifest, are stale or missing, the top-level
  post-commit status may still pass while `authority_readback.status=attention`
  names the owning authority target.
  `make head-aligned-evidence-converge` is a compatibility alias for this target.
- `make release-authority-settle`: explicit staged-authority writer lane for
  unattended promotion after release evidence is current. It first runs
  `release-finality-resettle-current-or-refresh`, which skips the expensive
  resettle when replay/current finality checks already pass, then runs
  preflight, run-ready, preseal, sealed-run-ready, and auto-promotion-ready
  manifests. On a clean ready pass, it refreshes the action matrix and
  generated artifact index, then runs the archive-candidate gate before
  post-commit readback or terminal finality. Archive candidates are local-only
  review-retention decisions, but moving them after finality changes tracked
  generated evidence and forces another fixed-point pass. If the gate reports
  candidates, run `make archive-execution-manifest-apply
  ARCHIVE_EXECUTION_OPERATOR_CONFIRMATION=CONFIRM_ARCHIVE_EXECUTION` when the
  move is appropriate, then rerun the authority lane from that pre-finality
  state. After the ready attempt, it runs a post-ready
  `current-or-refresh` finality tail: replay/current checks skip the ZIP-bound
  batch-manifest and fixed-point writers when they are already current, otherwise
  the tail promotes the batch manifest, rewrites fixed-point/finality,
  replay-verifies the same ZIP metadata, and then verifies finality so no
  tracked report writer runs after finality. If ready is blocked, this finality
  tail still runs and the original
  ready failure is returned. On a clean ready pass, check-only authority
  readback plus post-commit finalizer verification run before the same terminal
  finality tail.
  It does not regenerate long-tail report producers; run
  `make release-evidence-converge` or the owning evidence refresh target first
  when stale generated reports are the blocker.
- `make changed-path-minimum-plan`: advisory changed-path cost planner. It reads
  `ops/test-lane-registry.json` and an optional
  `WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST`, emits minimal suggested
  commands and deterministic duration-budget status, and always marks the final
  full release proof as still required through the registry-owned explicit
  checkpoint command, currently `make release-run-ready`.
- `make release-evidence-converge`: authoritative clean release evidence convergence.
- `make release-evidence-closeout-sealed`: check-only sealed packaging lane for an
  already source-ready tree. It must not run mutating source/evidence convergence;
  zip-bound sealed evidence is written as sidecars under `build/release/`.
- `make release-smoke-fast`: developer/package precheck, not canonical release
  evidence. Preflight, preseal, and goal-run admission may refresh it to keep
  archive schema/currentness diagnostics cheap before expensive release
  evidence is attempted.
- `make release-smoke`: canonical release evidence for the full smoke report at
  `ops/reports/release-smoke-report.json`.
  Source-package smoke runs registry and wiki lint checks in release-archive
  profile because public source ZIPs intentionally omit `raw/`, `wiki/`, and
  `system/`; missing private corpus surfaces must not become release-smoke
  blockers. Public-code review candidates, including Python function-budget
  candidates, remain visible in the smoke diagnostics.

## Recommended Order

1. Before committing a changed source tree, run `make changed-path-minimum-plan`
   when you want a cheap advisory lane, then run `make release-converge-preflight`
   or the full `make release-source-ready` flow. This keeps
   the `ops/script-output-surfaces.json` material output/fallback registry
   current in the same source commit instead of requiring a follow-up
   generated-artifact commit. Release run/seal tooling still does not push
   automatically.
2. If unattended promotion is the intended outcome, run
   `make release-auto-promotion-preflight` before the expensive runnable stage.
   You may pass `GOAL_RUN_ID=<goal-run-id>` explicitly, but if it is omitted the
   goal-run id guard can infer the effective id from current matching global
   run/certificate evidence. Missing verified runtime evidence is carried as a
   final promotion blocker; it does not stop this diagnostic bridge from
   proving cheaper release blockers.
3. Run `make release-run-ready-plan-check` when you want a cheap preflight that
   reports stale run-ready evidence and the minimal next target without
   refreshing local evidence. Run `make release-run-ready` from the committed
   tree when the planner is ready or when you intentionally want the runnable
   authority stage to refresh the required evidence.
4. If unattended promotion is the intended outcome, run
   `make release-auto-promotion-preseal` before sealing. As with preflight, an
   explicit `GOAL_RUN_ID=<goal-run-id>` is allowed but the guard can infer the
   effective id from verified global evidence. This includes
   `make release-auto-promotion-goal-run-id-guard` and
   `make release-auto-promotion-safe-cleanup-cleanup-only`; run the cleanup-only
   target directly when you need to settle safe generated evidence before
   retrying preseal.
5. Run `make release-sealed-run-ready` when you need source ZIP and sidecar
   evidence sealed for release review. Its planner requires a current passing
   run-ready manifest plus current passing auto-promotion preseal evidence, and
   reports the minimal next action if either authority is missing, stale, or
   failing.
6. Run `make release-auto-promotion-ready` when unattended promotion must be
   evaluated. Its planner reuses current passing preflight, run, preseal, and
   sealed authority evidence, reports minimal next actions for missing or stale
   lower evidence, and then reuses the sealed operator summary diagnostic and
   current verified goal-runtime certificate evidence before
   writing the auto-promotion authority manifest.

`release-auto-promotion-ready` intentionally avoids rerunning full pytest,
rebuilding the package, or resealing evidence when current lower-stage evidence
already passes. Learning and auto-improve reports under `ops/reports/` are
diagnostic inputs for the final manifest; if they are stale, the planner records
the preflight or preseal refresh target rather than mutating canonical
lower-stage evidence during stage 3 readback.
Auto-improve `release_gate` promotion blockers remain visible as diagnostics at
stage 3, but lower release authority is decided by current run/sealed manifests;
independent learning, remediation, worktree, and clean-release blockers still
block unattended promotion.
Operator diagnostics at stage 3 keep `accepted_risk`, `gate_attention`, and
`learning_claim` counts separate. All three groups are strict-zero checks for
unattended promotion, but gate attention and learning-claim blockers are not
reported as accepted risk. Advisory lifecycle accepted risks that are allowed to
remain visible at preseal still count as accepted-risk diagnostics at Stage 3;
they must be cleared before unattended promotion is allowed. The non-sealed
`external_report_strict_unavailable` advisory is cleared only by the sealed
batch path that binds a materialized current distribution ZIP; post-seal
attestation and sealed rehearsal still provide the strict provenance proof.

`status=attention` is a condition label, not a gate decision. Reports that can
affect execution or promotion must also emit `gate_effect` from the shared
vocabulary: `none`, `advisory`, `claim_blocker`, `operator_review_required`,
`blocks_promotion`, or `blocks_execution`. Use `advisory` for visible
debt that does not block the next step, `claim_blocker` for evidence that blocks
a specific claim or readiness assertion without becoming the release authority
itself, `operator_review_required` when a human signoff or explicit
authorization is the gate, `blocks_promotion` for evidence that allows bounded
repair but cannot be promoted, and `blocks_execution` for evidence that prevents
starting a run. Legacy values such as `active`, `review_required`, `shadow`, and
`accepted_risk` are compatibility inputs only and must not be emitted by new
reports.

Currentness is also objective. Reuse or operator-facing `current` should come
from the live HEAD/source-fingerprint/domain checks owned by the relevant lane,
not from a report's self-declared `current` field alone.
Artifact freshness gate effects describe the scanned artifact's own evidentiary
surface, not release promotion by themselves. A source revision or source tree
fingerprint mismatch on a canonical `ops/reports/` payload is a `claim_blocker`:
that report cannot support current claims until its owner refreshes it. Release
promotion authority is evaluated by the release closeout and staged authority
surfaces, which separately distinguish release-owned freshness attention from
non-release-owned operational drift.
After a source-ready commit, use `make release-post-commit-finalize` before
claiming release evidence is aligned for that HEAD. Use
`make release-authority-settle` only when staged release authority should be
rewritten for unattended promotion. `make release-check-finalized` is retained
only as a compatibility alias for `release-check`; it is not a mutating
finalization target.

## Remote Governance

Remote-visible release governance is recorded in
`.github/release-governance.yml`. That file is the public-safe checklist for
branch protection/ruleset configuration: direct pushes to `main` are forbidden,
pull requests and required status checks are required, force-pushes and branch
deletions are disabled, and the required CI matrix mirrors the `CI` workflow
after its matrix `exclude` entries. The fast tier keeps Python 3.12, 3.13, and
3.14 coverage; heavier CI tiers are required on Python 3.12 unless the workflow
and governance matrix are deliberately expanded together. Singleton checks
include Windows release smoke, raw-registry cross-environment evidence,
supply-chain, CodeQL, and dependency review.

Live GitHub drift evidence is an operator/full-vault lane, not a public CI or
release-promotion prerequisite. Create a sanitized JSON input with normalized
protected branch names, required check contexts, and branch-protection booleans,
then run:

```bash
make collaboration-governance GITHUB_GOVERNANCE_LIVE_INPUT=tmp/github-governance-live-input.json
make operator-evidence-closeout-current-or-refresh
```

The resulting `ops/reports/github-governance-live-drift.json` stores only
normalized counts, missing or mismatched required checks, input digest, status,
and redaction metadata. Do not retain raw ruleset dumps, tokens, actor payloads,
or private repository settings in that report. Use
`operator-evidence-closeout-current-or-refresh` after the operator evidence
writer so the default test-execution summary, generated index, artifact
freshness, the active matrix, and finality settle without rebuilding release
packages or rerunning release authority.
This lane uses stable JSONL artifact-freshness progress so long scans emit
heartbeat events without writing nondeterministic phase durations into the
canonical freshness report.

Working branches are pushed with `git push -u origin HEAD:<working-branch>`.
After push, attach the GitHub Actions workflow run and combined status check to
the pushed commit. Attachment service/configuration failures are recorded under
`remote_sync.workflow_attachment.workflow_attachment_error`; they do not rewrite
the push result or stop remote sync bookkeeping.

Release publication must leave remote-visible assets for the verified source
ZIP, evidence bundle, and release attestation. Offline verification replays the
staged authority checks with `make release-run-ready-check`,
`make release-sealed-run-ready-check`,
`make release-auto-promotion-ready-check`, and
`python -m ops.scripts.release.release_live_artifact_attestation verify`.

## Auto-Promotion Closeout Runbook

Use this runbook when the goal is to prove unattended release promotion for the
current committed tree. The runbook is a repository operating contract, not a
Codex skill: the Make targets, schemas, and manifests are the authority.

Before starting:

- Confirm the intended source tree is committed. Do not let release tooling
  commit or push implicitly.
- Do not run `make auto-improve-goal-run` as part of release closeout unless the
  operator explicitly requests a runtime trial. Release authority normally reads
  existing goal/runtime diagnostics; it does not create new mechanism runs.
  If `auto-improve-readiness` recommends `make auto-improve-goal-run` while you
  are in this release closeout runbook, treat that as a separate evidence
  production path, not as the next release target. The release-owned blocker is
  still missing or stale verified goal-run/certificate evidence.
- Treat `ops/reports/`, `ops/operator/`, `build/release/`, `runs/`, and `tmp/`
  as generated evidence surfaces. Refresh them through Make/script targets, not
  by hand editing JSON.

Remediation backlog may auto-close historical `goal_status_*` echo blockers
when current release authority evidence proves the owning gate is clean, such as
artifact freshness, release closeout summary, or strict release evidence cohort.
Do not close `goal_status_self_improvement_loop_certificate_incomplete` this
way. When current blocked certificate evidence exists, remediation backlog may
defer the duplicate goal-status echo to the release auto-promotion final
certificate gate, where it remains a live blocker until a completed goal-runtime
run produces a verified `goal-runtime-certificate`.

Recommended closeout sequence:

If artifact freshness points at stale generated report payloads, refresh the
owning evidence lane first: use `make release-evidence-converge` for broad
release evidence convergence, or a narrower owner target when the stale report
family is known. Use `make release-authority-settle` after that only when the
staged authority sidecars themselves should be rewritten for unattended
promotion.

`ops/reports/learning-readiness-signoff.json` is the active operator acceptance
source for the learning-readiness blocker. Keep it canonical while the
acceptance is live, but fix source revision/tree drift with
`make learning-readiness-signoff-refresh`; use `make learning-readiness-signoff`
only when the operator is renewing or replacing the acceptance decision.

1. Run `make release-auto-promotion-preflight GOAL_RUN_ID=<goal-run-id>` for
   cheap blockers when a run id is known, or omit `GOAL_RUN_ID` to let the
   binding resolver infer it from verified current evidence. Stop here if the
   goal-run binding is unsafe, learning revalidation, remediation backlog,
   worktree, auto-improve readiness, or fast smoke currentness fails. Missing
   verified runtime certificate evidence is carried forward as a final
   promotion blocker instead of forcing a runtime trial inside release closeout.
2. Run `make release-run-ready` only after preflight passes. This is the
   expensive runnable authority stage and is the owner of full-suite test
   evidence for the current fingerprint.
3. Run `make release-auto-promotion-preseal`. Stop here if the clean cohort,
   clean-lane-blocking accepted-risk family, gate attention, source-tree coherence, or
   same-fingerprint evidence cohort fails. Do not move failure diagnosis into
   Stage 3. Preseal runs the safe cleanup lane before accepted-risk and
   gate-attention evidence is evaluated.
4. Run `make release-sealed-run-ready` only after preseal passes. This creates
   the sealed package evidence and the sealed operator summary diagnostic for
   Stage 3 reuse.
5. Run `make release-auto-promotion-ready` as the final readback authority. It
   should reuse the current lower-stage evidence rather than rerunning tests,
   rebuilding the package, resealing, or creating runtime-trial evidence.
   If its planner reports release/clean-lane blocking accepted-risk counts or
   residual non-advisory gate attention, rerun `make release-auto-promotion-preseal`
   and then `make release-sealed-run-ready` so the sealed operator summary is
   regenerated from current source evidence.
   The `release-authority-settle` tail then first tries a ZIP-bound replay and
   finality current check. Only stale evidence triggers batch-manifest
   promotion, fixed-point rewrite, batch replay verification, and finality
   verification as the terminal report-writer suffix.

Completion is proven only by
`build/release/release-auto-promotion-ready-manifest.json` with:

- `status=pass`
- `auto_promotion_status=allowed`
- `unattended_promotion_allowed=true`
- empty `blockers`
- current `goal-run-status` and verified `goal-runtime-certificate` evidence for
  the same selected run id
- source revision and source tree fingerprint matching the intended commit

Release authority is decided by v2 status axes, not the legacy top-level
`status` field. Consumers must read `release_authority_status`,
`machine_release_allowed`, and `sealed_release_status` as the primary
authority. The top-level `status=pass` remains a strict clean plus sealed
compatibility alias for old readers only; `status=pass` without
`release_authority_status=clean_pass` and `machine_release_allowed=true`
means `conditional_pass` with machine release blocked.

Source closeout and sealed-run evidence are separate authority axes. A source
closeout that remains unsealed or otherwise diagnostic does not, by itself,
invalidate a current sealed-run verdict for the bound source ZIP. Consumers
should show both authorities as-is instead of collapsing them into a synthetic
"inconsistent state" warning.

If a lower stage fails, fix the owning lower-stage evidence first. Stage 3 should
not compensate for stale run-ready evidence, stale sealed evidence, mixed
fingerprints, accepted risk, gate attention, or learning blockers.

## Evidence Boundaries

- `build/release/release-run-manifest.json` is runnable-only authority. It binds
  the current HEAD, source fingerprint, source ZIP, source-package smoke report,
  and executed steps. Its `step_duration_summary` records total runtime,
  slowest step, and grouped duration comparisons for test/public/smoke/
  source-package lanes. Each step row also records `summary_mode=reused|executed`.
  Composite steps are conservative: if any subwork executes, the top-level step
  is recorded as `executed`. Remote branch sync is recorded as diagnostic context, but
  it is not a run-ready blocker because this stage answers whether the current
  local commit is runnable.
- `build/release/release-sealed-run-manifest.json` is sealed package authority.
  It binds the run manifest, source ZIP digest, post-seal attestation, and
  sealed rehearsal check. Batch/external sidecar legacy statuses are not treated
  as auto-promotion verdicts. Preserved stale sidecars belong in archived or
  otherwise non-authoritative evidence surfaces, not in the active sealed
  authority set. A sealed sidecar cleanup is not complete until every active
  authoritative `build/release/*.json` entry is HEAD-aligned; failed validation
  requires rerunning the whole cleanup attempt.
- `build/release/operator-release-summary.json` is generated during sealed-run
  readiness for Stage 3 reuse. It remains diagnostic input and is not included in
  `release-sealed-run-manifest.json` as sealed package authority.
- `build/release/release-auto-promotion-ready-manifest.json` is unattended
  promotion authority. Operator summary, learning diagnostics, goal-run status,
  and goal-runtime certificate evidence are read here, not exposed as
  `payload_status` inside the run manifest.
- `build/release/release-auto-promotion-preflight.json` and
  `build/release/release-auto-promotion-preseal.json` are diagnostic bridges for
  auto-promotion intent. They keep Stage 3-only blockers visible before the
  expensive run-ready and sealing stages, but they are not standalone release
  authority. Preflight catches learning, remediation, and auto-improve blockers
  before run-ready; preseal additionally requires clean closeout, no
  clean-lane-blocking accepted-risk family, gate-attention clean,
  source-tree-coherence pass, and a strict same-fingerprint evidence cohort
  before sealing. Goal-runtime certificate blockers are preserved as final
  promotion blockers for Stage 3 instead of blocking bootstrap diagnostics.
  Advisory lifecycle backlog can remain visible at preseal without forcing
  another run-ready cycle.
- `build/release/release-*-plan.json` files are execution plans, not release
  authority. They decide which evidence can be reused and which minimal Make
  target should run next; the authority verdict still belongs to the staged
  manifests.
- `build/release/release-run-ready-plan.json` is the runnable-stage diagnostic
  plan. It may mention stale `ops/reports/` or `build/release/` artifacts, but
  it does not promote or certify them; it points to the smallest refresh/check
  target that should run before spending the full run-ready cycle. A passing
  status field alone is insufficient for reuse; the planner also validates the
  report schema, producer, currentness envelope, source identity, and relevant
  package/test semantics. The plan also exposes `summary_mode`, exact
  `next_targets`, `reason_codes`, and `duration_summary` so expensive gate
  refreshes are visible before the authoritative `release-run-ready` writer is
  run.
- `ops/reports/release-smoke-report.json` is local diagnostic evidence and is
  not a final release authority. `release-run-ready` refreshes or reuses the
  current full smoke report; preseal uses the current-check lane and fails fast
  if that evidence is missing or stale. Release archive construction rejects
  included source files whose filesystem mtime is more than 60 seconds in the
  future before writing a temporary ZIP, so clock-skewed inputs do not become
  misleading package metadata.
- `ops/reports/test-execution-summary.json` and
  `ops/reports/test-execution-summary-full.json` are reused by check lanes only
  when their `source_tree_fingerprint` still matches the current tree. Stale
  evidence goes through the current-or-refresh path documented in
  `docs/development.md`: current check, aggregate metadata reuse, then explicit
  refresh only when needed. `release-run-ready` emits the canonical full-suite
  summary while it runs the test stage, so preseal and auto-promotion checks
  should reuse that evidence by currentness check instead of rerunning the full
  suite. Self-declared currentness is only a diagnostic hint;
  HEAD/source-fingerprint/domain-currentness checks are the authority.
  `release-check` does not rerun the unit subset after this full-suite evidence
  is current.
- `ops/reports/public-check-summary.json` proves the exported public tree contract.
  `public-check-summary-current-check`, `public-check-all-check`, and
  `release-run-ready` reuse this report only when the same
  `source_tree_fingerprint` still matches; stale evidence reruns the full public
  export check lane. Its inner `pytest_public` step runs
  `ops.scripts.test_execution_summary --suite public --reuse-if-current` inside
  the exported tree, reusing a temporary `test-execution-summary-public.json`
  cache instead of the repository canonical report path. After a refresh, the
  export-local summary is copied back into that cache and removed from the
  exported tree so the public surface stays clean. Refreshing
  `script-output-surfaces` alone does not invalidate this summary because the
  material output/fallback registry at `ops/script-output-surfaces.json` is
  outside the public export fingerprint authority; broader reruns come from
  downstream generated-artifact and finality repair bundles, not from
  `public-check-summary-current-check` itself.
- `ops/reports/release-closeout-finality-attestation.json` is diagnostic only;
  release authority is the staged `release-run`, `release-sealed-run`, and
  `release-auto-promotion-ready` manifests under `build/release/`. Artifact
  freshness excludes this finality-owned diagnostic so a terminal finality write
  does not create freshness debt; validate it with
  `make release-closeout-finality-verify`. After refreshing `artifact-freshness`,
  `external-report-action-matrix`, `generated-artifact-index`,
  `release-closeout-summary-report`, or another fixed-point tracked report,
  rerun `make release-finality-resettle-current-or-refresh` so current finality
  evidence is reused when possible, or the attestation is rewritten and verified
  after the last tracked writer when needed. The resettle lane refreshes
  `release-authority-sealed-preflight` before artifact freshness/finality scans
  so `ops/reports/release-closeout-sealed-rehearsal-check.json` is not left as a
  source-identity-only stale record after fixed-point attestation. Do not run
  `release-closeout-finality-attestation` directly after a freshness or summary
  refresh: finality verification reads the fixed-point digest map, so the
  durable repair is `make release-closeout-fixed-point` followed by terminal
  `make release-closeout-finality-verify`, or simply
  `make release-finality-resettle-current-or-refresh`.
  The action matrix is a generated-artifact-index input, so it must be refreshed
  inside the fixed-point/finality suffix before the attestation, not after it.
  Staged authority also refreshes the action matrix after
  `release-auto-promotion-ready` and before archive gating, so release-run and
  promotion truth-ladder statuses are reflected before terminal finality is
  considered current.
  `release-closeout-fixed-point` performs the final action-matrix readback after
  its post-promote artifact-freshness bootstrap and before it writes the
  attestation, so the matrix does not retain a pre-bootstrap freshness blocker.
  Any canonical report writer after the attestation can invalidate the finality
  digest map and should be treated as a reason to rerun the resettle lane.
  For staged authority settle, prefer `make release-authority-settle`; its
  terminal tail checks the effective distribution ZIP first and only rewrites
  the batch manifest, fixed point, replay verification, and finality evidence
  when current evidence cannot be reused.
- `ops/reports/` and `ops/operator/` are preserved locally and ignored by Git.
  If older branches still track entries under those paths, remove them from the
  index with `git rm --cached` while leaving the local files on disk.
- `external-reports/` remains private local-only input. Root reports must be
  reflected in lifecycle summaries before release; the reference manifest and
  archived reports are retained outside Git/source-release authority.
  `ops/reports/external-report-action-matrix.json` separates action lifecycle
  as `resolved`, `historically_true`, `superseded`, or `currently_valid`.
  It also summarizes currently valid actions by source-action availability,
  artifact-freshness backlog, and release/operator authority needs so the next
  lane is visible without reading every action row. Open or planned observations
  are not generated-only backlog: register them in
  `ops/observation-closeout-registry.json` before finality sealing, or update the
  registry and rerun the full resettle lane afterward. Finality-after generated
  observations are only appropriate for closed statuses with resolution evidence;
  do not mark an open follow-up `wontfix` merely to avoid the tracked registry
  update, and do not mutate tracked source while treating the existing finality
  attestation as current.
  Before a root report is moved to archive, require a per-report absorption
  check: matched action IDs, evidence status, lifecycle, unmatched
  recommendation count, and any operator-only rationale must be recorded in
  private/local evidence. Open task observations for archive reconciliation keep
  related broad actions `currently_valid`, so archive recommendations cannot rely
  only on active-report count or implemented totals. Generated-artifact index
  `reason` text is display-only for this decision; use structured
  `matched_action_ids`, `unresolved_action_ids`, `unresolved_action_count`,
  `superseded_by`, and matrix `status_reason_details` as the reconciliation
  evidence. Archive-reconciliation observations with `status: automated` keep
  their mapped actions partial until they include `resolution_evidence` entries
  such as `source:...`, `test:...`, `artifact:...`, `digest:...`, or `make:...`.
  Broad action themes such as hotspot refactor backlog, supply-chain external
  verification, governance, and source-package binding use action-specific
  completion predicates, so surface presence or backlog capture is not treated
  as full absorption.
  Historical claims such as an older stale report count must not be rendered as
  current state; use the regenerated action matrix and artifact-freshness
  summary for live counts. If current, source-bound artifact-freshness evidence
  is missing, stale, invalid, or source-mismatched, the action matrix reports
  `canonical_artifact_freshness_state.evidence_status` and leaves count fields
  unavailable instead of falling back to older fixed counts; refresh the
  `artifact-freshness` owner target to restore live counts. Excluded stale
  canonical reports need an explicit non-canonical marker, and preserved stale
  payloads need a preservation reason.
  When artifact freshness reports `stale_routing.classification:
  source_identity_only`, use `stale_routing.source_identity_owner_routes` to
  choose the narrow owner lane for each stale artifact group before paying for
  broad release evidence convergence. If the stale set is only source
  revision/tree fingerprint drift, start with
  `make freshness-source-identity-converge`; it refreshes freshness/index
  identity evidence and then uses the finality current-or-refresh wrapper
  without entering full-suite, release-run-ready, promotion authority, or goal
  publish lanes. Treat this as source-identity/finality readback debt, not as
  evidence payload freshness debt that automatically justifies broad release
  convergence. The top-level resettle target remains the safe post-commit
  fallback, while owner routes point to concrete Make targets such as
  `external-report-reference-manifest-settle`,
  `test-execution-summary-full-current-or-refresh`,
  `release-finality-resettle-current-or-refresh`,
  `GOAL_RUN_ID=<completed-run-id> make goal-runtime-publish-snapshot`,
  `supply-chain-artifacts-cached`, or
  `release-source-package-check`.
  Broad freshness refresh targets do not publish goal runtime status snapshots
  or rewrite canonical goal prompt/contract surfaces: canonical goal evidence is
  run evidence, not a generic currentness artifact, and must be refreshed
  through the goal-runtime lane with an explicit run ID.
  To avoid source-identity churn, use this order for real run convergence:

  1. Finish all source, code, documentation, policy, schema, fixture, and test
     edits.
  2. Validate the changed surface. If a CLI option, output path, or direct
     script writer surface changed, include `make script-output-surfaces-check`
     before committing; refresh `make script-output-surfaces` only when the
     check reports a stale material output/fallback registry.
  3. Commit the source-ready change before mutating canonical generated
     evidence.
  4. Run the narrow generated convergence lane that matches the blocker:
     `make generated-artifact-converge` for generated-artifact feedback, or
     `make freshness-source-identity-converge` for source revision/tree
     fingerprint resettle. Do not jump to broad release convergence unless the
     owner route still requires it.
  5. Run `make artifact-freshness-refresh-check`.
  6. When finality-tracked reports changed, run
     `make release-finality-resettle-current-or-refresh`.
  7. Run the release/operator authority lane only after freshness and finality
     are stable, for example `make release-run-ready` or
     `make release-authority-settle`.
     `release-authority-settle` first checks that the selected goal run is
     backed by verified completed-run evidence. If the goal certificate/status
     pair is stale, blocked, or only locally diagnostic, the lane stops before
     paying for full-suite, release package, or sealed-run evidence.
     `release-authority-settle` writes or refreshes the
     `release-auto-promotion-ready` manifest, then refreshes the action matrix,
     generated-artifact index, and archive execution manifest before terminal
     finality. This happens even when promotion readiness is blocked, so the
     active matrix reflects the newest blocker state and archive/source-action
     candidates stop the run before another finality seal.
  8. Finish with `make release-post-commit-finalize` so HEAD readback,
     script-output surface checking, artifact freshness checking, and terminal
     finality verification use the committed tree.

  If the final freshness pass does not change tracked source inputs,
  `release-run-ready-plan-check` should remain a reuse-only ready plan rather
  than opening another release evidence loop.
  After `release-closeout-finality-verify` passes, avoid mutating freshness,
  supply-chain, matrix, index, or archive reports directly. If one of those
  writers is required, treat finality as intentionally invalidated and finish
  with `make release-finality-resettle-current-or-refresh` as the terminal
  writer/check sequence. `make supply-chain-artifacts-cached` enforces this
  rule: when current finality already verifies, it fails unless
  `ALLOW_FINALITY_INVALIDATION=1` is set, and that bypass must be followed by
  `make release-finality-resettle-current-or-refresh`.
- `build/release/` holds materialized distribution ZIPs, sidecar audit evidence,
  and the release-run manifest.
- `tmp/` holds scratch checks and candidate files that must not become authority.

## Supply Chain

Supply-chain evidence is opt-in unless a release profile requires it:

```bash
make supply-chain-provenance
make supply-chain-check
make sbom-readiness-check
make openvex-draft-cached
```

CycloneDX, SPDX, OpenVEX, in-toto/SLSA, and Sigstore outputs share the
repo-native artifact model so dependency and public-export coverage can be
audited consistently.

`sigstore-bundle` defaults to local integrity evidence. That is useful for
readiness diagnostics, but it is not external bundle verification. To close the
external Sigstore evidence lane, provide an observed bundle reference:

```bash
make sigstore-bundle SIGSTORE_BUNDLE_REF=tmp/sigstore.bundle
make operator-evidence-closeout-current-or-refresh
```

`verified-external-bundle` requires a non-empty bundle reference, passing local
subject checks, a parseable Sigstore bundle JSON payload, and bundle structure
that carries verification material plus signed content. A placeholder file or a
bundle with failing checks remains non-pass as
`external-bundle-verification-failed`; leave the lane operator-pending until the
publish/release environment has produced an observed bundle.
The active matrix distinguishes local supply-chain artifact refresh from
external bundle verification: source-identity drift routes to the freshness
owner lane, while `supply_chain_external_verification` remains operator-pending
until `SIGSTORE_BUNDLE_REF=<bundle>` points at an observed bundle.

Canonical dependency evidence is `pyproject.toml` plus `uv.lock`, replayed with
the canonical-index `make uv-lock-check` gate and frozen `uv export`
locked-requirements installs in CI and `make dev-install`. `make dev-install`
uses `DEV_INSTALL_INDEX_URL` for local install replay; it defaults to the
canonical index but can be overridden without changing the `uv-lock-check`
authority. Root
`requirements.txt` and `requirements-dev.txt` are retired from the
source and public-export surfaces; if an older report or fixture still mentions
them, treat them only as optional compatibility/provenance inputs.
