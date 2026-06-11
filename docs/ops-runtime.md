# Ops Runtime

The ops runtime is the repository control layer: policy, schema, reports,
Make orchestration, and helper scripts.

## Make Layout

- `mk/core.mk`: environment setup and bootstrap preflight.
- `mk/static.mk`: ruff and mypy gates.
- `mk/test.mk`: pytest lanes and report-contract packs.
- `mk/eval.mk`: lint, eval, warning, and complexity gates.
- `mk/artifact.mk`: generated artifact refresh and convergence helpers.
- `mk/registry.mk`: raw registry and manifest surfaces.
- `mk/mechanism.mk`: self-improvement, goal runtime, and mechanism workflows.
- `mk/release.mk`: shared release variables and compatibility entrypoints.
- `mk/release-authority.mk`: run-ready, sealed-run, and auto-promotion authority.
- `mk/release-evidence.mk`: release evidence, closeout, archive, and smoke lanes.
- `mk/release-learning.mk`: learning readiness, remediation, and session evidence.
- `mk/public.mk`: public export and codebase-memory-mcp sidecar targets.
- `mk/supply_chain.mk`: provenance, SBOM, OpenVEX, in-toto, and Sigstore surfaces.

## Script Layout

`ops/scripts/` is organized by runtime domain:

- `core/`: shared artifact, path, policy, schema, command, and workflow helpers.
- `eval/`: lint, eval, warning, complexity, and documentation audit helpers.
- `registry/`: raw registry export, preflight, normalization, and intake.
- `mechanism/`: mechanism review, mutation proposal, goal runtime, and experiments.
- `release/`: release evidence, external report lifecycle, sealing, and summaries.
- `learning/`: learning claim, readiness signoff, remediation, and lesson surfaces.
- `supply_chain/`: provenance, SBOM, advisory, OpenVEX, in-toto, and Sigstore.
- `public/`: public export, public check, and CBM public export.
- `test/`: test execution summary and lane registry runtime.

After editable install, lifecycle policy public CLIs are exposed as
`llm-wiki-*` console scripts from `pyproject.toml`. Make targets are the
preferred operator entrypoint for report generators and maintenance lanes.

## Generated Artifacts

Schema-backed JSON reports should use the shared artifact writer helpers and
include a canonical envelope. Candidate-to-promote writers should write under
`tmp/*.candidate.json` first, validate schema and producer metadata, then
promote to the durable path.

General rule:

- canonical evidence is written to local-only `ops/reports/` or `ops/operator/`
  paths and should not be tracked as public source; if stale evidence is kept
  for investigation, archive or mark it non-canonical instead of leaving it in
  the active authority set;
- check-only or advisory scratch output lives under `tmp/`;
- release packages, source-package extracts, and audit packs live under `build/`.

Operator-facing `current` or reusable-evidence decisions should come from the
objective lane checks that bind HEAD, source fingerprint, and domain-specific
currentness. Self-declared current fields are diagnostic metadata, not
authority by themselves.

## Compatibility Surface

Some flat module paths such as `python -m ops.scripts.release_smoke` continue to
work through compatibility routing. New docs should prefer Make targets or
canonical package paths such as `ops.scripts.release.release_smoke`; use
`llm-wiki-*` only for lifecycle policy public CLIs.
