# LLMwiki Code/Ops Runtime

LLMwiki is a persistent LLM wiki workspace with a self-improving maintainer
runtime. This repository is the public-safe code/ops surface for that workspace:
it packages the Make workflows, Python ops package, policies, schemas, tests,
release/public-export tooling, supply-chain artifact generators, and scoped
agent operating contracts that keep the private canonical vault reproducible.

The repository is intentionally **not** a public dump of the private knowledge
corpus. A full local vault may also contain `raw/`, `wiki/`, `system/`, `runs/`,
`external-reports/`, `ops/operator/`, and generated `ops/reports/` evidence.
Those surfaces stay private or generated unless a policy-backed document says
otherwise.

## What This Runtime Provides

- **Persistent wiki maintenance contracts**: source intake, registry checks,
  wiki/system corpus hygiene, lint/eval surfaces, and source-trace rules.
- **Schema-backed ops automation**: reusable Python runtime modules under
  `ops/scripts/*`, JSON Schema contracts, templates, artifact writers, and Make
  targets that make reports reproducible instead of hand-edited.
- **Self-improvement loop**: mechanism review, mutation proposals, goal-runtime
  admission/closeout, promotion gates, readiness evidence, and bounded runtime
  experiments.
- **Public mirror and release replay**: policy-generated public exports,
  corpus-free public checks, release run-ready manifests, source ZIP smoke,
  sealing, and promotion readiness lanes.
- **Supply-chain evidence**: provenance, SBOM, advisory, OpenVEX, in-toto, and
  Sigstore-oriented report generators wired through Make.
- **Agent operating surface**: `AGENTS.md`, `AGENTS.local.md`, and
  `.codex/agents/` describe the public-safe and full-vault roles agents may use.

## Surface Model

| Surface | Purpose | Main authority | Typical verification |
| --- | --- | --- | --- |
| Full local vault | Private operator workspace and canonical corpus operation. | `AGENTS.md` plus `AGENTS.local.md` | Task-specific gates such as `make check` or `make release-check` |
| Public mirror/export | Corpus-free code/ops runtime for review, CI, and optional CBM indexing. | `ops/scripts/public/public_surface_policy.py` | `make public-check` or `make public-check-all` |
| Release source ZIP | Normalized replay package for release smoke, sealing, and provenance sidecars. | Staged manifests under `build/release/` | `make release-run-ready-check`, `make release-sealed-run-ready-check`, `make release-auto-promotion-ready-check` |

See [docs/repository-surfaces.md](./docs/repository-surfaces.md) for the full
comparison and [docs/public-mirror.md](./docs/public-mirror.md) for the public
boundary contract.

## Start Here

Requirements: Python 3.12 or newer, `make`, and preferably `uv` for locked
third-party dependency replay.

```bash
make help
make dev-install
make bootstrap-preflight
make static
make test-public
```

For broader local validation:

```bash
make test
make check
```

For a full developer regression, use `make test-all`. For release-grade
full-suite evidence, use the current-or-refresh evidence lane described in
[docs/development.md](./docs/development.md#supported-test-entrypoints). Bare
`pytest` is not a supported entrypoint. Use Make targets or focused
`.venv/bin/python -m pytest tests/...` selectors.

## Primary Operator Entrypoints

Use `make help` for the compact, current command index. The main families are:

| Family | Representative targets |
| --- | --- |
| Setup/status | `make dev-install`, `make status`, `make bootstrap-preflight` |
| Source checks | `make static`, `make ruff-strict-preview`, `make mypy-strict-preview`, `make strict-preview-audit` |
| Tests/report contracts | `make test`, `make test-all`, `make test-report-contract-core`, `make test-report-contract-all` |
| Public mirror | `make sync-public-policy`, `make public-check`, `make public-check-all` |
| Mechanism/goal runtime | `make auto-improve-readiness`, `make goal-runtime-run-admission`, `make release-auto-promotion-ready` |
| Release | `make changed-path-minimum-plan`, `make release-run-ready`, `make release-post-commit-finalize`, `make release-sealed-run-ready` |
| Review handoff | `make review-archive-clean`, `make review-archive` |
| Supply chain | `make supply-chain-check`, `make cyclonedx-sbom`, `make spdx-sbom`, `make openvex-draft`, `make in-toto-statement`, `make sigstore-bundle` |

## Common Workflows

| Work type | First check | Closeout check |
| --- | --- | --- |
| Public docs/root docs change | `make static` | `make public-check` |
| Ops script or test change | `make static` | `make test` or a focused pytest selector |
| Schema, policy, or report-contract change | `make static` | `make test-report-contract-core` |
| Public export boundary change | `make sync-public-policy` | `make public-check` or `make public-check-all` |
| Release evidence or package behavior change | `make release-run-ready-check` | `make release-run-ready`; add `make release-sealed-run-ready` when sealing is required |
| Source review handoff | `make static` | `make review-archive-clean` |
| Supply-chain artifact change | `make supply-chain-check` | The owning SBOM/provenance target plus relevant release checks |

Full-vault work that reads or mutates `raw/`, `wiki/`, `system/`, `runs/`, or
`external-reports/` also needs [AGENTS.local.md](./AGENTS.local.md). Public docs,
tests, and fixtures must not assume those private surfaces exist.

## Repository Layout

- `ops/`: control layer for policies, schemas, templates, runtime scripts, and
  generated report contracts.
- `ops/scripts/`: domain packages for `core`, `eval`, `registry`, `mechanism`,
  `release`, `learning`, `supply_chain`, `public`, and `test` automation.
- `mk/`: Make target families for setup, static checks, tests, artifacts,
  registry, mechanism, release, public mirror, and supply-chain lanes.
- `tests/`: pytest contract suite for public-safe runtime behavior and generated
  artifact rules.
- `docs/`: public workflow and architecture documentation.
- `.github/`: CI, release, dependency, and governance surfaces.
- `.codex/agents/`: project-scoped subagent role surface.

Canonical imports use the domain package paths, for example
`ops.scripts.release.release_status_surface`. The package still keeps flat
`ops.scripts.<name>` compatibility aliases for existing Make/script callers.

## Documentation Map

- [docs/README.md](./docs/README.md): documentation hub and first reading path.
- [ARCHITECTURE.md](./ARCHITECTURE.md): current system model and boundaries.
- [docs/development.md](./docs/development.md): setup, test lanes, CI tier map,
  and change-type gates.
- [docs/repository-surfaces.md](./docs/repository-surfaces.md): full-vault,
  public export, and release source ZIP comparison.
- [docs/public-mirror.md](./docs/public-mirror.md): public/private boundary,
  export policy, and durable report exceptions.
- [docs/ops-runtime.md](./docs/ops-runtime.md): `mk/`, `ops/scripts/`, schemas,
  templates, and report surfaces.
- [docs/release.md](./docs/release.md): release evidence, source packages,
  sealing, and SBOM/provenance lanes.
- [docs/self-improvement-runtime.md](./docs/self-improvement-runtime.md):
  mechanism review, mutation proposal, goal runtime, and promotion.
- [docs/codebase-memory-mcp.md](./docs/codebase-memory-mcp.md): optional
  public-safe codebase-memory-mcp sidecar.
- [ops/README.md](./ops/README.md): compact ops subsystem index.
- [.codex/agents/README.md](./.codex/agents/README.md): project-scoped subagent
  role surface.

## Python Package And CLI Surface

The project package is `llm-wiki-vnext` and requires Python 3.12+. Runtime
third-party dependencies are intentionally small: `PyYAML` and `jsonschema`.
Developer tooling is locked through `uv.lock` and installed by `make dev-install`.

Installed console scripts include:

```bash
llm-wiki-status
llm-wiki-finalize-run
llm-wiki-improvement-observations
llm-wiki-planning-gate-validate
llm-wiki-run-mechanism-experiment
```

## Optional codebase-memory-mcp

For code/ops structure exploration (`code/ops 구조 탐색`), a verified operator-local
`codebase-memory-mcp` binary can index a public-safe export:

```bash
make cbm-smoke-public
make cbm-index-public
make cbm-schema-public
make cbm-architecture-public
make cbm-search-public CBM_SEARCH_PATTERN=release_run_ready
```

This is a graph-first/file-verified hinting workflow. It is not canonical
evidence, not a release gate, and not a dependency. 기존 `rg` / file read workflow
remains supported alongside direct file reads.

## License

The public surface is distributed under [Apache License 2.0](./LICENSE).
Third-party notices are kept in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
