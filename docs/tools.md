# Tools

The `tools/` directory contains public-safe helper scripts that are still
invoked as file-path tools rather than `python -m ops.scripts...` modules. They
are part of the public mirror surface, but their supported entrypoints are the
Make targets below.

Use Make targets for routine work so cache paths, target surfaces, and guard
defaults stay aligned with CI. Direct script invocation is mainly for focused
debugging or the script's `--help` output.

| Tool | Primary Make target | Purpose |
| --- | --- | --- |
| `tools/ruff_strict_preview.py` | `make ruff-strict-preview` | Runs selected Ruff preview rules on `ops/scripts tests tools` by default and reports candidate debt without failing the command. |
| `tools/strict_preview_audit.py` | `make strict-preview-audit` | Writes a JSON audit that combines Ruff preview-rule debt and stricter mypy preview checks across the configured target surface. |
| `tools/regenerate_report_schema_samples.py` | `make report-schema-samples-check` / `make report-schema-samples-regenerate` | Checks or regenerates schema sample fixtures used by report-contract tests. |

## Strict Preview Tools

`make ruff-strict-preview` is the quick, non-blocking Ruff preview scan. Its
defaults come from `mk/static.mk`:

- `RUFF_STRICT_PREVIEW_TARGETS`, defaulting to `ops/scripts tests tools`
- `RUFF_STRICT_PREVIEW_RULES`, currently `PTH201`
- `RUFF_CACHE_DIR`, under `tmp/tool-cache/ruff/<platform>`

`make strict-preview-audit` is the durable audit lane. It writes
`tmp/strict-preview-audit.json` by default and combines the same Ruff preview
surface with stricter mypy flags from `MYPY_STRICT_PREVIEW_FLAGS`.

Use the audit target when a change needs evidence that preview debt was
measured, and use the Ruff-only target when iterating on candidate rule cleanup.

## Report Schema Samples

`make report-schema-samples-check` runs the schema sample generator in check
mode and fails if checked-in fixtures are stale. `make
report-schema-samples-regenerate` first runs the clean fixture regeneration
guard, then rewrites the sample fixtures.

Run these targets when changing report schemas, schema-backed report producers,
or fixture generation rules. After regeneration, run the relevant
report-contract tests, normally `make test-report-contract-core` for the public
core lane.
