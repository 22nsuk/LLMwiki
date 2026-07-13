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
Because the generated public mirror template opens allowlisted prefixes after a
deny-by-default rule, it re-ignores policy-excluded segments, nested local
environments, bytecode, cache, coverage, editor, and OS state inside those
prefixes. Do not mirror that generated block back into the repository root
`.gitignore` without a separate full-vault Git hygiene contract change.

The public mirror includes:

- `docs/`
- `ops/`, excluding private inventory files and generated evidence reports
- `tests/`
- `tools/`
- `mk/`
- `.agents/skills/`
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
make sync-derived
make public-export
make public-check
```

Use `make help` for the compact operator index and
`make sync-derived-check` in check-only contexts. The aggregate includes public
policy template sync; use `make sync-public-policy` or
`make sync-public-policy-check` only when debugging that public-specific slice.
These public policy targets sync or check `ops/templates/public-mirror.gitignore`,
not the full-vault root `.gitignore`. Use `make public-check-all` when the
exported tree should run all tests rather than only the public marker tier. The
default and selectorless lanes retain independent canonical summaries at
`ops/reports/public-check-summary.json` and
`ops/reports/public-check-summary-full.json`, respectively, so one checkpoint
cannot replace the other's evidence.
General lane-selection guidance lives in [development.md](development.md).
