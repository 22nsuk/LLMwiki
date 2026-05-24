# Release Workflow

Release work is evidence-driven. Converge targets update local-only reports;
check targets verify that already-generated evidence is current.
Release authority is staged so each manifest answers one question:
`build/release/release-run-manifest.json` says whether the current commit is
runnable, `build/release/release-sealed-run-manifest.json` says whether the
source ZIP and sidecars are sealed evidence, and
`build/release/release-auto-promotion-ready-manifest.json` says whether the
result can be promoted without operator intervention.

## Common Targets

- `make release-check`: check-only release gate for the current tree.
- `make release-check-all-surfaces`: release check plus public policy and public export checks.
- `make release-run-ready`: one command to verify the current committed tree,
  emit canonical report-contract and full-suite test summaries, run public check,
  refresh/reuse current full release-smoke evidence, run package build and
  source-package smoke, then write the runnable release-run manifest.
- `make release-run-ready-check`: revalidate the existing manifest against the
  current HEAD, source fingerprint, source ZIP, and source-package smoke report.
- `make release-sealed-run-ready-plan`: inspect runnable authority evidence and
  write the cost-aware action plan for sealing without rerunning stage 1.
- `make release-sealed-run-ready`: build sealed sidecars, including the sealed
  operator summary diagnostic, write the operator-free sealed post-seal
  attestation, run the sealed rehearsal check, and write the sealed-run
  manifest. It requires current passing runnable evidence and does not rerun the
  runnable stage. The operator summary is generated for Stage 3 reuse, but it is
  not part of the sealed-run authority sidecar set.
- `make release-sealed-run-ready-check`: revalidate existing sealed evidence
  without rerunning tests or rebuilding the package.
- `make release-auto-promotion-ready-plan`: inspect preflight, runnable,
  preseal, sealed, operator, and auto-improve evidence and write the cost-aware
  action plan for the promotion verdict.
- `make release-auto-promotion-preflight`: refresh cheap unattended-promotion
  blockers before spending full run-ready cycles. It refresh-checks fast smoke
  and run-local goal evidence, refreshes the selected report-contract summary
  for changed test fingerprints, then runs artifact freshness and checks
  remediation, learning revalidation, and auto-improve readiness without
  building or sealing release artifacts.
- `make release-auto-promotion-preseal`: refresh clean closeout, strict
  same-fingerprint cohort, remediation, learning, and auto-improve diagnostics
  after run-ready and before sealing. It refreshes cheap cohort inputs such as
  bootstrap, registry, fast smoke, run-local goal evidence, generated index,
  artifact freshness, and external report references, but it only checks
  run-ready's full release-smoke and full-suite evidence for currentness instead
  of rerunning them.
- `make release-auto-promotion-operator-summary`: manual fallback to refresh the
  cheap build-local operator diagnostics used by the promotion verdict when
  sealed sidecars are already current.
- `make release-auto-promotion-ready`: low-cost promotion check that reads the
  current runnable and sealed manifests, reuses the sealed operator summary
  diagnostic, and decides unattended promotion. It never cascades into the lower
  runnable or sealing stages.
- `make release-auto-promotion-ready-check`: revalidate the existing
  auto-promotion manifest inputs without recomputing expensive evidence.
- `make release-converge`: mutating evidence convergence for release reports.
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

1. Commit the source tree you want to verify. Release tooling no longer commits
   or pushes automatically.
2. If unattended promotion is the intended outcome, run
   `make release-auto-promotion-preflight` before the expensive runnable stage.
3. Run `make release-run-ready`.
4. If unattended promotion is the intended outcome, run
   `make release-auto-promotion-preseal` before sealing.
5. Run `make release-sealed-run-ready` when you need source ZIP and sidecar
   evidence sealed for release review. Its planner requires a current passing
   run-ready manifest and reports the minimal next action if that evidence is
   missing, stale, or failing.
6. Run `make release-auto-promotion-ready` when unattended promotion must be
   evaluated. Its planner reuses current passing preflight, run, preseal, and
   sealed authority evidence, reports minimal next actions for missing or stale
   lower evidence, and then reuses the sealed operator summary diagnostic before
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
they must be cleared before unattended promotion is allowed.

## Evidence Boundaries

- `build/release/release-run-manifest.json` is runnable-only authority. It binds
  the current HEAD, source fingerprint, source ZIP, source-package smoke report,
  and executed steps. Remote branch sync is recorded as diagnostic context, but
  it is not a run-ready blocker because this stage answers whether the current
  local commit is runnable.
- `build/release/release-sealed-run-manifest.json` is sealed package authority.
  It binds the run manifest, source ZIP digest, post-seal attestation, and
  sealed rehearsal check. Batch/external sidecar legacy statuses are not treated
  as auto-promotion verdicts.
- `build/release/operator-release-summary.json` is generated during sealed-run
  readiness for Stage 3 reuse. It remains diagnostic input and is not included in
  `release-sealed-run-manifest.json` as sealed package authority.
- `build/release/release-auto-promotion-ready-manifest.json` is unattended
  promotion authority. Operator summary and learning diagnostics are read here,
  not exposed as `payload_status` inside the run manifest.
- `build/release/release-auto-promotion-preflight.json` and
  `build/release/release-auto-promotion-preseal.json` are diagnostic bridges for
  auto-promotion intent. They keep Stage 3-only blockers visible before the
  expensive run-ready and sealing stages, but they are not standalone release
  authority. Preflight catches learning, remediation, and auto-improve blockers
  before run-ready; preseal additionally requires clean closeout, no
  clean-lane-blocking accepted-risk family, gate-attention clean,
  source-tree-coherence pass, and a strict same-fingerprint evidence cohort
  before sealing. Advisory lifecycle backlog can remain visible at preseal
  without forcing another run-ready cycle.
- `build/release/release-*-plan.json` files are execution plans, not release
  authority. They decide which evidence can be reused and which minimal Make
  target should run next; the authority verdict still belongs to the staged
  manifests.
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
  check instead of rerunning the full suite. `release-check` does not rerun the
  unit subset after this full-suite evidence is current.
- `ops/reports/public-check-summary.json` proves the exported public tree contract.
  `public-check-all-check` reuses this report only when the same
  `source_tree_fingerprint` still matches.
- `ops/reports/release-closeout-finality-attestation.json` is diagnostic only;
  release authority is the staged `release-run`, `release-sealed-run`, and
  `release-auto-promotion-ready` manifests under `build/release/`.
- `ops/reports/` and `ops/operator/` are preserved locally and ignored by Git.
  If older branches still track entries under those paths, remove them from the
  index with `git rm --cached` while leaving the local files on disk.
- `external-reports/` remains private local-only input. Root reports must be
  reflected in lifecycle summaries before release; the reference manifest and
  archived reports are retained outside Git/source-release authority.
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
