# Public Mirror

The public mirror is a self-contained code/ops view of the repository. It must
be useful without private corpus files, live run directories, or external
review material.

For a side-by-side comparison of the full local vault, public export, and
release source ZIP, see [repository-surfaces.md](repository-surfaces.md). This
document owns the public mirror/export lane only.

## Included Surface

The source of truth is `ops/scripts/public/public_surface_policy.py`.
The public mirror `.gitignore` is generated into
`ops/templates/public-mirror.gitignore`; the repository root `.gitignore` is
full-vault hygiene only and must not be treated as public export policy.

The public mirror includes:

- `docs/`
- `ops/`, excluding private inventory files and generated evidence reports
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
- `ops/operator/`
- `ops/reports/`
- `tmp/`
- private inventory files such as `ops/manifest.json` and `ops/raw-registry.json`

`external-reports/` is excluded as a whole. In the full local vault, root
external reports are active local-only intake, while
`external-reports/report-reference-manifest.json` and
`external-reports/archive/` are local-only retained evidence rather than a
Git/public source of truth. The public mirror only receives sanitized,
schema-backed summaries such as the external report action matrix.

## Generated Evidence

`ops/reports/` and `ops/operator/` are generated evidence surfaces, not public
source. They are excluded from public export as whole directories and ignored in
the full-vault root `.gitignore` the same way `external-reports/` is. Existing
local evidence should be preserved on disk, but any tracked entries under these
surfaces should be removed from the index with `git rm --cached`.

If a generated report needs to influence public behavior, promote the rule,
schema, fixture, or test that produces the behavior. Do not add a durable report
allowlist exception back into the public mirror.

## Commands

```bash
make help
make sync-public-policy
make public-export
make public-check
```

Use `make help` for the compact operator index and
`make sync-public-policy-check` in check-only contexts. These targets sync or
check `ops/templates/public-mirror.gitignore`, not the full-vault root
`.gitignore`. Use `make public-check-all` when the exported tree should run all
tests rather than only the public marker tier. General lane-selection guidance
lives in [development.md](development.md).

## CBM Export

`make cbm-export-public` builds a separate public-safe export for
codebase-memory-mcp indexing. It prunes generated evidence directories such as
`ops/reports/` and `ops/operator/` entirely and writes `CBM-EXPORT-MANIFEST.json`
plus a root `.cbmignore`. It is intentionally separate from release evidence
and public-check authority.
