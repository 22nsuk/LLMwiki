# codebase-memory-mcp Sidecar

`codebase-memory-mcp` is an optional public-safe code structure index. It helps
with graph-first/file-verified exploration, but it is not a dependency, release
gate, promotion authority, canonical evidence source, or assistant-specific
workflow requirement.

## Standard Flow

First-run health check:

```bash
make cbm-smoke-public
```

Normal refresh and navigation:

```bash
make cbm-index-public
make cbm-schema-public
make cbm-architecture-public
make cbm-search-public CBM_SEARCH_PATTERN=release_run_ready
```

If the binary is not on `PATH`, pass it explicitly:

```bash
make cbm-index-public CBM_BIN=/path/to/codebase-memory-mcp
```

Do not run `codebase-memory-mcp install` as part of this repo contract. Agent
config and hook installation is operator-local setup; repository onboarding uses
a verified local binary or an explicit `CBM_BIN`.

For a first-run health check, prefer `make cbm-smoke-public`. It builds the
public-safe export, indexes it, prints schema and architecture summaries, and
runs one fixed `search_code` probe so the operator can see whether graph-backed
navigation is usable before relying on it. The export step prints a compact
summary; the full file list remains in `CBM-EXPORT-MANIFEST.json` under the
generated export.

## Boundary

The index source is the public-safe CBM export, not the full vault root. The
export excludes:

- `raw/`
- `wiki/`
- `system/`
- `runs/`
- `external-reports/`
- `ops/operator/`
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

## Better Default Use

Use CBM before broad grep when the question is about structure, ownership, or
impact. It is most useful at the beginning of these tasks:

CBM is a better starting point than `rg` when a new worker does not yet know
the owning file or exact token, because graph-backed search can surface scripts,
Make targets, docs, and tests together. When the exact string is already known,
prefer `rg` first; it is smaller, deterministic, and reads the live working tree
directly.

- mapping the owner of a release, runtime, schema, or public-export behavior
- finding adjacent tests and docs before changing an `ops/scripts` contract
- checking whether a proposed change crosses public/private/generated
  boundaries
- identifying likely callers, writers, or config consumers before editing
- comparing a changed source file against nearby policy/schema/test surfaces

Practical parent workflow:

1. Run `make cbm-smoke-public` when validating a fresh sidecar setup. For normal
   refreshes after source edits, `make cbm-index-public` is enough.
2. Start with `make cbm-schema-public` or `make cbm-architecture-public` for a
   repository-level map.
3. Use `make cbm-search-public CBM_SEARCH_PATTERN=<token>` or direct
   graph/search/trace output to choose the first files to inspect.
4. Read those repo files directly and verify every claim with `rg`, source
   reads, schema checks, tests, or Make targets.
5. When CBM points to `CBM_PUBLIC_OUT`, translate the path back to the same
   relative path in the live repo before editing.

Good task recipes:

- Release blocker triage: use CBM to map release scripts, manifest writers,
  Make targets, and tests; then validate with staged release manifests.
- Goal runtime triage: use CBM to find admission, readiness, certificate, and
  mutation-proposal owners; then inspect current run evidence directly.
- External report reconciliation: use CBM to locate action-matrix and backlog
  producers; then compare generated reports and current source evidence.
- Subagent role work: use CBM to map `.codex/agents`, routing policy, selector
  runtime, and tests before adding or renaming roles.

Do not use CBM as:

- release or promotion authority
- a replacement for `rg` when the exact token is already known
- proof that generated artifacts are current
- a reason to skip direct file reads, tests, or public-check gates

## Operational Rules

- Re-run `make cbm-index-public` after repo edits before trusting graph output;
  CBM does not watch the working tree.
- Treat snippet and search paths under `CBM_PUBLIC_OUT` as cache export paths.
  Map them back to the same relative path in the repo before editing.
- Treat `CALLS`, `WRITES`, `CONFIGURES`, `SEMANTICALLY_RELATED`, and other graph
  edges as candidate links, not proof.
- If graph output conflicts with live repo files, the live files and tests win.

Advanced direct CLI/MCP tools are optional. Use `make cbm-list-projects-public`
to confirm the project name, and `codebase-memory-mcp --help` for exact tool
names such as `search_graph`, `query_graph`, `trace_path`, and
`detect_changes`.
