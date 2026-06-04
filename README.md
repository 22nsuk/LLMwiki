# LLMwiki Code/Ops Runtime

LLMwiki is a persistent LLM wiki workspace with a self-improving maintainer
runtime. This repository is the code/ops surface: policy, Make workflows,
schemas, tests, public export tooling, and agent operating contracts live here.

The private canonical vault can also contain `raw/`, `wiki/`, `system/`,
`runs/`, and `external-reports/`. Those surfaces are intentionally excluded
from the public mirror unless a document says otherwise.

## Start Here

1. Read [docs/README.md](./docs/README.md) for the documentation map.
2. Read [ARCHITECTURE.md](./ARCHITECTURE.md) for the current system model.
3. Run the public-safe developer loop:

```bash
make help
make dev-install
make static
make test-public
```

4. For a broader local check, use:

```bash
make test
make check
```

For a full developer regression, use `make test-all`. For release-grade
full-suite evidence, use the current-or-refresh evidence lane described in
[docs/development.md](./docs/development.md#supported-test-entrypoints). Bare
`pytest` is not a supported entrypoint.

## Documentation Map

- [docs/development.md](./docs/development.md): setup, test lanes, CI tier map, and change-type gates.
- [docs/repository-surfaces.md](./docs/repository-surfaces.md): full-vault, public export, and release source ZIP comparison.
- [docs/public-mirror.md](./docs/public-mirror.md): public/private boundary, export policy, and durable report exceptions.
- [docs/ops-runtime.md](./docs/ops-runtime.md): `mk/`, `ops/scripts/`, schemas, templates, and report surfaces.
- [docs/release.md](./docs/release.md): release evidence, source packages, sealing, and SBOM/provenance lanes.
- [docs/self-improvement-runtime.md](./docs/self-improvement-runtime.md): mechanism review, mutation proposal, goal runtime, and promotion.
- [docs/codebase-memory-mcp.md](./docs/codebase-memory-mcp.md): optional public-safe codebase-memory-mcp sidecar.
- [ops/README.md](./ops/README.md): compact ops subsystem index.
- [.codex/agents/README.md](./.codex/agents/README.md): project-scoped subagent role surface.

## Public Mirror

The public mirror tracks the code/ops runtime without private corpus contents;
the release source ZIP is a separate replay surface. See
[docs/repository-surfaces.md](./docs/repository-surfaces.md) for the comparison
and [ops/scripts/public/public_surface_policy.py](./ops/scripts/public/public_surface_policy.py)
for the public membership policy.

When public boundaries change, run:

```bash
make sync-public-policy
make test-public
```

Use `make public-export` to materialize the mirror and `make public-check` to
verify the exported tree.

## Common Workflows

Use `make help` for the compact operator index of setup, source checks,
report-contract, public mirror, mechanism, and release entrypoints. Detailed
selection guidance remains in [docs/development.md](./docs/development.md).

| Work type | First check | Closeout check |
| --- | --- | --- |
| docs-only public change | `make test-public` | `make sync-public-policy-check` if boundaries changed |
| ops script or test change | `make static` | `make test` or a focused pytest target |
| schema or report contract change | `make test-report-contract-core` | `make test-artifact-finalization` after regenerating artifacts |
| public export change | `make sync-public-policy` | `make public-check` |
| release evidence change | `make release-check` | `make release-check-all-surfaces` when public/export surfaces changed |

Full-vault work that mutates `raw/`, `wiki/`, `system/`, `runs/`, or
`external-reports/` also needs [AGENTS.local.md](./AGENTS.local.md).

## Optional codebase-memory-mcp

For code/ops 구조 탐색, a verified operator-local `codebase-memory-mcp` binary
can index the public-safe export:

```bash
make cbm-index-public
make cbm-schema-public
make cbm-architecture-public
```

This is a graph-first/file-verified hinting workflow. It is not canonical
evidence, not a release gate, and not a dependency. 기존 `rg` / file read workflow
continues to be supported. See [docs/codebase-memory-mcp.md](./docs/codebase-memory-mcp.md).

## License

The public surface is distributed under [Apache License 2.0](./LICENSE).
Third-party notices are kept in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
