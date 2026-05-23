# codebase-memory-mcp Sidecar

`codebase-memory-mcp` is an optional public-safe code structure index. It helps
with graph-first/file-verified exploration, but it is not a dependency, release
gate, promotion authority, canonical evidence source, or assistant-specific
workflow requirement.

## Standard Flow

```bash
make cbm-index-public
make cbm-schema-public
make cbm-architecture-public
```

If the binary is not on `PATH`, pass it explicitly:

```bash
make cbm-index-public CBM_BIN=/path/to/codebase-memory-mcp
```

## Boundary

The index source is the public-safe CBM export, not the full vault root. The
export excludes:

- `raw/`
- `wiki/`
- `system/`
- `runs/`
- `external-reports/`
- `ops/reports/`
- `.codebase-memory`

The CBM export writes `CBM-EXPORT-MANIFEST.json` and root `.cbmignore`. Those
files describe the sidecar index boundary, not release evidence.

## How To Use Results

- Use graph output to find likely owners, dependencies, and test candidates.
- Confirm all conclusions with live file reads.
- Close changes with Make/Pytest gates, not graph output.
- Keep `rg`, direct file reads, and ordinary editor workflows available even
  when CBM is installed.

## Operational Rules

- Re-run `make cbm-index-public` after repo edits before trusting graph output;
  CBM does not watch the working tree.
- Treat snippet and search paths under `CBM_PUBLIC_OUT` as cache export paths.
  Map them back to the same relative path in the repo before editing.
- Treat `CALLS`, `WRITES`, `CONFIGURES`, `SEMANTICALLY_RELATED`, and other graph
  edges as candidate links, not proof.
- If graph output conflicts with live repo files, the live files and tests win.
