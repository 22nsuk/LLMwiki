# Release Workflow

Release work is evidence-driven. Converge targets update local-only reports;
check targets verify that already-generated evidence is current.
The run-ready release authority is `build/release/release-run-manifest.json`.
`ops/reports/` remains diagnostic/local evidence and does not decide final
sealed/run-ready status.

## Common Targets

- `make release-check`: check-only release gate for the current tree.
- `make release-check-all-surfaces`: release check plus public policy and public export checks.
- `make release-run-ready`: one command to verify the current committed tree,
  run the current test/public/package/smoke/seal sequence, and write the
  authoritative release-run manifest.
- `make release-run-ready-check`: revalidate the existing manifest against the
  current HEAD, source fingerprint, source ZIP, smoke report, and sidecars.
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
3. Run `make release-run-ready-check` if you need a readback verification of the
   manifest after another process inspects or transfers the build directory.

The command fixes the sequence to preflight, current tests, public check,
source package build, clean-extract smoke, sealed sidecars, and manifest check.
Each step records the starting source fingerprint and must finish with the same
fingerprint. Full pytest, public check, and package build are each run at most
once in this graph.

## Evidence Boundaries

- `build/release/release-run-manifest.json` is the final authority for a
  run-ready release. It binds the current HEAD, source fingerprint, source ZIP,
  source-package smoke report, and sealed sidecars.
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
  final release authority is the release-run manifest plus the source ZIP digest.
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
