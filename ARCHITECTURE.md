# LLMwiki Architecture

This is the public-safe architecture overview for the current code/ops runtime.
It describes boundaries and control flow without exposing private corpus
contents, raw inventory, live run artifacts, or external review material.

## Purpose

LLMwiki combines two loops:

- a maintainer loop that turns curated raw sources into persistent wiki/system
  knowledge;
- a meta-maintainer loop that improves the maintainer runtime with policy,
  tests, schema-backed reports, and bounded experiments.

The public mirror shares the runtime and its tests. The private vault keeps the
actual corpus and operator evidence.

## Layers

| Layer | Surface | Public mirror status | Role |
| --- | --- | --- | --- |
| Raw | `raw/` | excluded | canonical source snapshots |
| Knowledge corpus | `wiki/`, `system/` | excluded | maintained content and system knowledge |
| Run artifacts | `runs/` | excluded | planning, promotion, and goal-run evidence |
| Ops control layer | `ops/`, `mk/`, `tests/`, `tools/` | included | policy, schema, scripts, Make, and tests |
| Docs and agents | `docs/`, root docs, `.codex/agents/` | included | public operating contract and role surface |
| CI/export | `.github/`, root config | included | reproducible public validation |

## Runtime Loops

### Public Development

`make dev-install`, `make static`, `make test-public`, and `make public-check`
prove that the public code/ops mirror is usable without private corpus state.

### Corpus Maintenance

Full-vault sessions may read or mutate `raw/`, `wiki/`, `system/`, and `runs/`.
Those rules are local-only and live in `AGENTS.local.md`.

### Self-Improvement

Mechanism review, mutation proposal, goal runtime, promotion gate, and release
evidence form the bounded meta-maintainer loop. See
[docs/self-improvement-runtime.md](./docs/self-improvement-runtime.md).

### Release And Export

Release evidence is generated under policy-approved paths and checked by Make
targets. Public export is generated from the source policy rather than
hand-maintained file lists. See [docs/public-mirror.md](./docs/public-mirror.md)
and [docs/release.md](./docs/release.md). For the operator-facing comparison
between the full local vault, public export, and release source ZIP, see
[docs/repository-surfaces.md](./docs/repository-surfaces.md).

## Source Of Truth Map

| Question | Authority |
| --- | --- |
| What is public? | `ops/scripts/public/public_surface_policy.py` |
| How do I run checks? | `Makefile`, `mk/*.mk`, `docs/development.md` |
| What do test lanes mean? | `ops/test-lane-registry.json` |
| What does a report contain? | `ops/schemas/*.json` |
| How are scripts organized? | `docs/ops-runtime.md` |
| What may agents do? | `AGENTS.md` and `AGENTS.local.md` |

## Surface Boundaries

The short rule is: public mirror membership comes from
`ops/scripts/public/public_surface_policy.py`; private corpus and local evidence
remain outside public source; release source ZIP authority comes from staged
manifests under `build/release/`. The full comparison lives in
[docs/repository-surfaces.md](./docs/repository-surfaces.md).

Representative public roots remain visible here for quick orientation:

- `docs/`
- `.github/`

Generated report exceptions are explicit and policy-backed. If a new durable
public report is needed, update policy, `.gitignore`, export tests, and docs in
the same change.
