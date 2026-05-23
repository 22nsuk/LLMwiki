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
  run full pytest, public check, package build, and source-package smoke, then
  write the runnable release-run manifest.
- `make release-run-ready-check`: revalidate the existing manifest against the
  current HEAD, source fingerprint, source ZIP, and source-package smoke report.
- `make release-run-ready-ensure`: try `release-run-ready-check` first, then run
  `release-run-ready` only when runnable evidence is missing, stale, or failing.
- `make release-sealed-run-ready`: build sealed sidecars, write the operator-free
  sealed post-seal attestation, run the sealed rehearsal check, and write the
  sealed-run manifest. It uses `release-run-ready-ensure` so already-current
  runnable evidence is reused.
- `make release-sealed-run-ready-check`: revalidate existing sealed evidence
  without rerunning tests or rebuilding the package.
- `make release-sealed-run-ready-ensure`: try `release-sealed-run-ready-check`
  first, then run `release-sealed-run-ready` only when sealed evidence is
  missing, stale, or failing.
- `make release-auto-promotion-ready`: low-cost promotion check that reads the
  sealed manifest, refreshes cheap learning/auto-improve diagnostics, reads the
  operator summary, and decides unattended promotion. It uses
  `release-sealed-run-ready-ensure` so the top stage can be run as one command.
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
- `make release-smoke`: canonical release evidence는 이 full 단일 report인 `ops/reports/release-smoke-report.json`이다.

## Recommended Order

1. Commit the source tree you want to verify. Release tooling no longer commits
   or pushes automatically.
2. Run `make release-run-ready`.
3. Run `make release-sealed-run-ready` when you need source ZIP and sidecar
   evidence sealed for release review. It will reuse a current run-ready
   manifest when one already exists.
4. Run `make release-auto-promotion-ready` when unattended promotion must be
   evaluated. It will ensure sealed evidence first, then refresh only the cheap
   diagnostic inputs needed for the auto-promotion verdict.

`release-auto-promotion-ready` intentionally avoids rerunning full pytest or
rebuilding the package when current lower-stage evidence already passes. Check
targets may still rewrite their `build/release/` diagnostic manifests while
they re-evaluate currentness; they are check-first reuse paths, not immutable
read-only probes.

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
- `build/release/release-auto-promotion-ready-manifest.json` is unattended
  promotion authority. Operator summary and learning diagnostics are read here,
  not exposed as `payload_status` inside the run manifest.
- `ops/reports/release-smoke-report.json` is local diagnostic evidence and is
  not a final release authority.
- `ops/reports/test-execution-summary.json` and
  `ops/reports/test-execution-summary-full.json` are reused by check lanes only
  when their `source_tree_fingerprint` still matches the current tree. Stale
  evidence fails fast; explicit refresh targets rerun tests. `release-check`
  does not rerun the unit subset after this full-suite evidence is current.
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
