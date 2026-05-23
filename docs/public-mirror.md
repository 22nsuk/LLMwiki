# Public Mirror

The public mirror is a self-contained code/ops view of the repository. It must
be useful without private corpus files, live run directories, or external
review material.

## Included Surface

The source of truth is `ops/scripts/public/public_surface_policy.py`.

The public mirror includes:

- `docs/`
- `ops/`, excluding private inventory files and most generated reports
- `tests/`
- `tools/`
- `mk/`
- `.codex/agents/`
- `.github/`
- root public documents and development configuration

The public mirror excludes:

- `raw/`
- `wiki/`
- `system/`
- `runs/`
- `external-reports/`
- `tmp/`
- private inventory files such as `ops/manifest.json` and `ops/raw-registry.json`

`external-reports/` is excluded as a whole. In the full local vault, root
external reports are active local-only intake, while
`external-reports/report-reference-manifest.json` and
`external-reports/archive/` are local-only retained evidence rather than a
Git/public source of truth. The public mirror only receives sanitized,
schema-backed summaries such as the external report action matrix.

## Durable Report Exceptions

`ops/reports/` is generally generated evidence and is ignored by default. A
small allowlist of durable public evidence is kept in policy when the report is
needed for source-layout or workflow-order contracts.

Current durable exceptions are:

- `ops/reports/goal-worktree-guard.json`
- `ops/reports/release-workflow-order-guard.json`
- `ops/reports/workflow-dependency-planner.json`

Changing this allowlist requires updating the policy, `.gitignore`, export
tests, and public-check expectations together.

## Commands

```bash
make sync-public-policy
make public-export
make public-check
```

Use `make sync-public-policy-check` in check-only contexts. Use
`make public-check-all` when the exported tree should run all tests rather than
only the public marker tier.

## CBM Export

`make cbm-export-public` builds a separate public-safe export for
codebase-memory-mcp indexing. It prunes `ops/reports/` entirely and writes
`CBM-EXPORT-MANIFEST.json` plus a root `.cbmignore`. It is intentionally
separate from release evidence and public-check authority.
