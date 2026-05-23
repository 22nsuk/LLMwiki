# Release Workflow

Release work is evidence-driven. Converge targets update durable reports;
check targets verify that already-generated evidence is current.

## Common Targets

- `make release-check`: check-only release gate for the current tree.
- `make release-check-all-surfaces`: release check plus public policy and public export checks.
- `make release-converge`: mutating evidence convergence for release reports.
- `make release-converge-all-surfaces`: convergence plus public policy/export refresh.
- `make release-source-ready`: source-ready commit and post-commit convergence flow.
- `make release-evidence-converge`: authoritative clean release evidence convergence.
- `make release-evidence-closeout-sealed`: materialized source ZIP plus sealed release evidence.
- `make release-smoke-fast`: developer/package precheck이며 canonical release evidence로 쓰지 않는다.
- `make release-smoke`: canonical release evidence는 이 full 단일 report인 `ops/reports/release-smoke-report.json`이다.

## Evidence Boundaries

- `ops/reports/release-smoke-report.json` is the canonical full release smoke report.
- `ops/reports/public-check-summary.json` proves the exported public tree contract.
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
