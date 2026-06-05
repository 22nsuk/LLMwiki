# ops/

`ops/` is the control layer for the LLMwiki maintainer runtime. It holds policy,
schema, templates, scripts, generated report contracts, and public/export
tooling.

## Layout

- `policies/`: runtime policy and governance inputs.
- `schemas/`: JSON Schema contracts for reports, templates, and runtime artifacts.
- `scripts/`: Python runtime packages organized by domain.
- `templates/`: reusable starter templates and sidecar templates.
- `reports/`: generated evidence, ignored by default except policy-approved durable files.
- `test-lane-registry.json`: authority for persistent pytest lanes, derived packs, CI routing, and documentation boundaries.

See [../docs/ops-runtime.md](../docs/ops-runtime.md) for the full runtime map.

## Script Packages

- `core`: shared artifact, path, policy, schema, command, and workflow helpers.
- `eval`: lint, eval, warning, complexity, and documentation audit helpers.
- `registry`: raw registry export, preflight, normalization, and intake.
- `mechanism`: mechanism review, mutation proposal, goal runtime, and experiments.
- `release`: release evidence, external report lifecycle, sealing, and summaries.
- `learning`: learning claim, readiness signoff, remediation, and lesson surfaces.
- `supply_chain`: provenance, SBOM, advisory, OpenVEX, in-toto, and Sigstore.
- `public`: public export, public check, and CBM public export.
- `test`: test execution summary and lane registry runtime.

## Primary Make Families

```bash
make help
make dev-install
make static
make test-public
make test-report-contract-core
make sync-public-policy
make public-check
make release-check
make auto-improve-readiness
```

`make help` is the compact operator index. Detailed usage lives in:

- [../docs/development.md](../docs/development.md)
- [../docs/repository-surfaces.md](../docs/repository-surfaces.md)
- [../docs/public-mirror.md](../docs/public-mirror.md)
- [../docs/release.md](../docs/release.md)
- [../docs/self-improvement-runtime.md](../docs/self-improvement-runtime.md)

## Optional codebase-memory-mcp quickstart

```bash
make cbm-smoke-public
make cbm-index-public
make cbm-schema-public
make cbm-architecture-public
make cbm-search-public CBM_SEARCH_PATTERN=release_run_ready
```

Set `CBM_BIN=/path/to/codebase-memory-mcp` when the binary is not on `PATH`.
This graph-first/file-verified sidecar is optional and never canonical evidence.
See [../docs/codebase-memory-mcp.md](../docs/codebase-memory-mcp.md).

## Generated Artifact Rule

Durable schema-backed reports must be written through the shared artifact
helpers, validated, and promoted intentionally. Scratch checks and candidate
files stay under `tmp/`; release packages and audit sidecars stay under
`build/`.

## Operating Principles

- Policy and schema changes need matching runtime and tests.
- Generated private artifacts are not source of truth.
- Public-safe code must run without `raw/`, `wiki/`, `system/`, `runs/`, or `external-reports/`.
- Public boundary changes require `make sync-public-policy`.
- Prefer canonical package paths and Make targets over flat compatibility module names in new documentation.
