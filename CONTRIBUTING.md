# Contributing

This repository is maintained as a public-safe code/ops mirror. Contributions
should improve reproducible runtime behavior without importing private corpus
contents.

## Scope

Common public contribution surfaces:

- `docs/`
- `ops/`
- `tests/`
- `tools/`
- `mk/`
- `.codex/agents/`
- `.github/`
- root public documents and development configuration

Excluded from public contribution scope:

- `raw/`
- `wiki/`
- `system/`
- `runs/`
- `external-reports/`
- private inventory files and generated private reports

## Development

Start with:

```bash
make dev-install
make static
make test-public
```

Use [docs/development.md](./docs/development.md) to choose the closeout gate for
your change type.

## Change Rules

- Keep one PR focused on one purpose.
- Update docs, tests, schema, and policy together when a contract changes.
- Prefer Make targets in user-facing docs; use `llm-wiki-*` only for lifecycle
  policy public CLIs.
- Do not copy private corpus content, raw inventory, live run artifacts, or external report bodies into public surfaces.
- Run `make sync-public-policy` when adding a public file, public prefix, or durable generated report exception.
- Review `.codex/agents/` changes together with role intent, rung selection, and routing contracts.
- Record third-party material and license obligations in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) when needed.

## Pull Requests

Include:

- the reason for the change;
- the touched surface;
- the validation commands and current result;
- any remaining risk or intentionally skipped gate.

## Commit Governance

Commits should stay scoped to one runtime, policy, or documentation purpose. If
a change touches generated artifacts, the PR summary must name the Make target
or script that refreshed them. Release authority, public-boundary, and
subagent-routing changes should keep source, tests, docs, and generated evidence
together unless the split is explicitly justified in the PR.

## Security

Do not file public issues for sensitive security reports. Follow
[SECURITY.md](./SECURITY.md).
