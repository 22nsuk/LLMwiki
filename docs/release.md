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
  state, not from a stale release-run manifest sidecar.
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
  source-fingerprint, revision, and lane-specific semantics.
- `make release-run-ready-plan-check`: check-only form of the planner that fails
  when existing evidence is not reusable.
- `make release-run-ready-check`: revalidate the existing manifest against the
  current HEAD, source fingerprint, source ZIP, and source-package smoke report.
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
- `make release-auto-promotion-safe-cleanup`: normalize safe generated
  evidence before preseal. It removes stale goal-runtime transients, cleans tmp
  JSON candidates, backfills schema-backed historical run artifacts, refreshes
  generated-artifact index and artifact freshness, refreshes external report
  reference diagnostics, and rewrites the closeout summary from those current
  inputs.
- `make generated-artifact-retention-clean`: dry-run a retention-aware cleanup
  of regenerated local residue. Pass `GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY=1`
  only when you intentionally want to remove allowlisted ignored residue such as
  source-package extracts and local tool caches; current release authority,
  private corpus roots, and run provenance are retained.
- `make release-auto-promotion-preseal`: refresh clean closeout, strict
  same-fingerprint cohort, remediation, learning, and auto-improve diagnostics
  after run-ready and before sealing. It refreshes cheap cohort inputs such as
  bootstrap, registry, fast smoke, generated index, artifact freshness, and
  external report references through the safe cleanup lane, then refreshes
  auto-improve readiness after those sealed-batch inputs settle so strict
  cohort checks do not read stale release-gate blockers. It only checks
  run-ready's full release-smoke and full-suite
  evidence for currentness instead of rerunning them. It removes any older final
  ready manifest before writing new preseal evidence.
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
  is current before report-contract summaries or release smoke can read it.
- `make release-converge-all-surfaces`: convergence plus public policy/export refresh.
- `make release-source-ready`: source-ready commit flow. Mutating convergence happens
  in `release-source-ready-prepare` before the commit; `release-source-ready-post-verify`
  is write-free and only fails if the already-generated check evidence is stale or
  failing. Operator release summary is local-only evidence and is refreshed
  during the prepare convergence flow.
- `make release-evidence-converge`: authoritative clean release evidence convergence.
- `make release-evidence-closeout-sealed`: check-only sealed packaging lane for an
  already source-ready tree. It must not run mutating source/evidence convergence;
  zip-bound sealed evidence is written as sidecars under `build/release/`.
- `make release-smoke-fast`: developer/package precheck이며 canonical release evidence로 쓰지 않는다.
  Preflight, preseal, and goal-run admission may refresh it to keep archive
  schema/currentness diagnostics cheap before expensive release evidence is
  attempted.
- `make release-smoke`: canonical release evidence는 이 full 단일 report인 `ops/reports/release-smoke-report.json`이다.
  Source-package smoke runs registry and wiki lint checks in release-archive
  profile because public source ZIPs intentionally omit `raw/`, `wiki/`, and
  `system/`; missing private corpus surfaces must not become release-smoke
  blockers. Public-code review candidates, including Python function-budget
  candidates, remain visible in the smoke diagnostics.

## Recommended Order

1. Before committing a changed source tree, run `make release-converge-preflight`
   or the full `make release-source-ready` flow. This keeps
   `ops/script-output-surfaces.json` current in the same source commit instead
   of requiring a follow-up generated-artifact commit. Release run/seal tooling
   still does not push automatically.
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
   `make release-auto-promotion-safe-cleanup`; run the safe cleanup target
   directly only when you need to settle safe generated evidence before retrying
   preseal.
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
vocabulary: `none`, `advisory`, `blocks_promotion`, `blocks_execution`, or
`operator_review_required`. Use `advisory` for visible debt that does not block
the next step, `blocks_promotion` for evidence that allows bounded repair but
cannot be promoted, `blocks_execution` for evidence that prevents starting a
run, and `operator_review_required` when a human signoff or explicit
authorization is the gate. Legacy values such as `active`, `review_required`,
`shadow`, and `accepted_risk` are compatibility inputs only and must not be
emitted by new reports.

Currentness is also objective. Reuse or operator-facing `current` should come
from the live HEAD/source-fingerprint/domain checks owned by the relevant lane,
not from a report's self-declared `current` field alone.

## Remote Governance

Remote-visible release governance is recorded in
`.github/release-governance.yml`. That file is the public-safe checklist for
branch protection/ruleset configuration: direct pushes to `main` are forbidden,
pull requests and required status checks are required, force-pushes and branch
deletions are disabled, and the required CI matrix mirrors the `CI` workflow
tiers for Python 3.12, 3.13, and 3.14. Singleton checks include Windows release
smoke, raw-registry cross-environment evidence, supply-chain, CodeQL, and
dependency review.

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

Recommended closeout sequence:

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
   If its planner reports operator accepted-risk or gate-attention counts, rerun
   `make release-auto-promotion-preseal` and then `make release-sealed-run-ready`
   so the sealed operator summary is regenerated from current source evidence.

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
  package/test semantics.
- `ops/reports/release-smoke-report.json` is local diagnostic evidence and is
  not a final release authority. `release-run-ready` refreshes or reuses the
  current full smoke report; preseal uses the current-check lane and fails fast
  if that evidence is missing or stale.
- `ops/reports/test-execution-summary.json` and
  `ops/reports/test-execution-summary-full.json` are reused by check lanes only
  when their `source_tree_fingerprint` still matches the current tree. Stale
  evidence fails fast; explicit refresh targets rerun tests. `release-run-ready`
  emits the canonical full-suite summary while it runs the test stage, so
  preseal and auto-promotion checks should reuse that evidence by currentness
  check instead of rerunning the full suite. Self-declared currentness is only a
  diagnostic hint; HEAD/source-fingerprint/domain-currentness checks are the
  authority. `release-check` does not rerun the unit subset after this full-suite
  evidence is current.
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
  `script-output-surfaces` alone does not invalidate this summary because
  `ops/script-output-surfaces.json` is outside the public export fingerprint
  authority; broader reruns come from downstream generated-artifact and
  finality repair bundles, not from `public-check-summary-current-check`
  itself.
- `ops/reports/release-closeout-finality-attestation.json` is diagnostic only;
  release authority is the staged `release-run`, `release-sealed-run`, and
  `release-auto-promotion-ready` manifests under `build/release/`.
- `ops/reports/` and `ops/operator/` are preserved locally and ignored by Git.
  If older branches still track entries under those paths, remove them from the
  index with `git rm --cached` while leaving the local files on disk.
- `external-reports/` remains private local-only input. Root reports must be
  reflected in lifecycle summaries before release; the reference manifest and
  archived reports are retained outside Git/source-release authority.
  `ops/reports/external-report-action-matrix.json` separates action lifecycle
  as `resolved`, `historically_true`, `superseded`, or `currently_valid`.
  Historical claims such as an older "46/46 stale" report count must not be
  rendered as current state; the current revalidated operator count is
  `5 stale / 47 total` with `3` priority stale reports until those reports are
  regenerated or excluded from the canonical set. Excluded stale canonical
  reports need an explicit non-canonical marker, and preserved stale payloads
  need a preservation reason.
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

Canonical dependency evidence is `pyproject.toml` plus `uv.lock`, replayed in
CI through `uv lock --check` and a frozen `uv export` locked-requirements
install. Root `requirements.txt` and `requirements-dev.txt` are retired from the
source and public-export surfaces; if an older report or fixture still mentions
them, treat them only as optional compatibility/provenance inputs.
