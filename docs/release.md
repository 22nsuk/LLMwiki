# Release Workflow

Release work is evidence-driven. Converge targets update durable reports;
check targets verify that already-generated evidence is current.

## Common Targets

- `make release-check`: check-only release gate for the current tree.
- `make release-check-all-surfaces`: release check plus public policy and public export checks.
- `make release-converge`: mutating evidence convergence for release reports.
- `make release-converge-all-surfaces`: convergence plus public policy/export refresh.
- `make release-source-ready`: source-ready commit flow. Mutating convergence happens
  in `release-source-ready-prepare` before the commit; `release-source-ready-post-verify`
  is write-free and only fails if the already-generated check evidence is stale or
  failing. Operator release summary is tracked evidence and is refreshed during
  the prepare convergence flow.
- `make release-sealed-dirty-recovery`: narrow recovery lane for the case where
  sealed verification exposes dirty generated canonical evidence only. It refuses
  non-generated/source changes, rechecks all surfaces, then reruns sealed closeout.
- `make release-evidence-converge`: authoritative clean release evidence convergence.
- `make release-evidence-closeout-sealed`: check-only sealed packaging lane for an
  already source-ready tree. It must not run mutating tracked evidence convergence.
- `make release-smoke-fast`: developer/package precheck이며 canonical release evidence로 쓰지 않는다.
- `make release-smoke`: canonical release evidence는 이 full 단일 report인 `ops/reports/release-smoke-report.json`이다.

## Recommended Order

1. Run `make release-source-ready` to converge tracked evidence, create the
   source-ready commit, and run write-free post-verify checks.
2. Run `make release-evidence-closeout-sealed` from the clean source-ready tree.
   This materializes `build/release/LLMwiki-source.zip`, writes local post-seal
   attestation under `build/release/`, and verifies the sealed rehearsal check
   against the already tracked source-ready evidence.
3. If sealed verification reports only generated canonical evidence drift, run
   `make release-sealed-dirty-recovery`. If it reports source or other
   non-generated drift, fix that writer boundary explicitly.

## Evidence Boundaries

- `ops/reports/release-smoke-report.json` is the canonical full release smoke report.
- `ops/reports/test-execution-summary.json` and
  `ops/reports/test-execution-summary-full.json` are reused by check lanes only
  when their `source_tree_fingerprint` still matches the current tree. Stale
  evidence fails fast; explicit refresh targets rerun tests. `release-check`
  does not rerun the unit subset after this full-suite evidence is current.
- `ops/reports/public-check-summary.json` proves the exported public tree contract.
  `public-check-all-check` reuses this report only when the same
  `source_tree_fingerprint` still matches.
- `ops/reports/release-closeout-finality-attestation.json` binds final closeout digests.
- `external-reports/` remains private local-only input. Root reports must be
  reflected in lifecycle summaries before release; the reference manifest and
  archived reports are retained outside Git/source-release authority.
- `build/release/` holds materialized distribution ZIPs and sidecar audit evidence.
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
