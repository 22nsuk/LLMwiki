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
- `ops/policies/wiki-maintainer-policy.local.yaml` and its atomic-write staging files

## Local Corpus Settings

Keep the tracked `ops/policies/wiki-maintainer-policy.yaml` public-safe.
Full vaults can store their corpus-specific additions in the ignored
`ops/policies/wiki-maintainer-policy.local.yaml`. The default policy loader
automatically applies this file, including when the default policy path is
passed explicitly. A different explicit policy path remains self-contained.

The local file uses `schema_version: 1` and an `overrides` mapping, validated by
`ops/schemas/local-corpus-policy.schema.json`. Only special-page section rules,
special-page frontmatter rules, raw-registry shard pages, and shard-to-corpus
assignments can be overridden. Mappings merge recursively, `null` removes a
mapping entry, and lists replace the corresponding public list. The complete
effective policy still passes the normal schema and safety checks. Unrelated
public runtime and routing updates continue to apply.

`make raw-registry-shard-policy-sync-write` writes these differences to the
local file without rewriting the tracked default policy. With an explicit
custom `--policy` destination, the CLI continues to write that destination.
For an existing locally edited policy, retain its loaded policy object, restore
the public base, and use `write_local_corpus_policy(vault, effective_policy)`
to produce the local overlay; it rejects changes outside the four corpus
surfaces. Verify `load_policy(vault)` equals the retained effective policy.

Canonical report input fingerprints include `local_corpus_policy` whenever the
default policy has a local overlay. The `policy` fingerprint binds both files,
and cached test summaries and collection manifests are invalidated when the
overlay is created, changed, or removed. Derived test summaries preserve the
parent's policy fingerprints, including the base policy binding when no overlay
exists, so they follow the same invalidation lifecycle as direct summaries.
Test aggregates and reused summaries retain the overlay dependencies of their
input evidence, including `missing` for an overlay that was absent. This binding
survives nested aggregation and subset derivation even with a custom output
policy; evidence composed entirely from independent custom policies stays
independent. Subset derivation treats legacy omitted absence and explicit
`missing` as the same input state, while preserving collection dependencies.
An unreadable or invalid policy referenced by cached test evidence makes the
cache unusable. `--reuse-if-current` executes with the requested valid policy;
`--reuse-only` fails without running tests or writing replacement evidence.
The shared artifact freshness scan also marks policy-bound live canonical reports stale
when the overlay is created, changed, or removed, including reports generated
before overlays were supported. It records
`input_fingerprint_mismatch:local_corpus_policy` and requires the report owner
to regenerate the evidence. Explicit custom policies stay independent of the
default overlay; archived reports and historical run snapshots retain their
existing lifecycle treatment. Release closeout routes policy mismatches in
release-owned reports through its existing freshness review gate. Closeout and
external-report lifecycle readers reject a cached freshness aggregate whose
local policy inputs have changed until it is regenerated. Freshness aggregates
always record the scanned vault's `local_corpus_policy` fingerprint, using
`missing` when the overlay is absent, even with an explicit custom scan policy:
the scan also evaluates default-policy reports. Older custom-policy aggregates
without this binding require regeneration; direct custom-policy reports retain
their independence from the default overlay. Environment-only
diagnostics without effective-policy inputs remain independent of the overlay.
Public source fingerprints, Git tracking, public exports, wheels, and sdists
exclude the local file.
Full and sparse candidate workspaces retain the overlay whenever they copy the
default policy, so local validation uses the same effective corpus settings.
Tests and examples must use synthetic corpus names; never copy an operator's local inventory into
public fixtures or documentation.

The full-vault root `.gitignore` applies the same ownership boundary within
`.agents/`: operator-local siblings are ignored while `.agents/skills/**`
remains trackable. This keeps local agent state out of dirty-worktree planning
without deleting repository-owned workflow skills.

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

Each summary keeps two boundary claims separate. `public_export` and
`summary.export_git_metadata_absence_status` describe only the materialized
bundle, including whether its output directory contains `.git` metadata.
`source_history_scan` independently inspects paths reachable from all source
repository refs plus `HEAD` using the canonical public-surface exclusion policy.
Git replacement-object semantics are disabled for both traversal and object-size
resolution, so a local `refs/replace/*` entry cannot mask the original history.
Ambient Git variables that can redirect the repository, refs, object store,
shallow boundary, graft file, or namespace are removed from scanner subprocesses.
The raw traversal forces `--ignore-submodules=none`, so repository or global
diff configuration cannot hide an excluded gitlink path.
Refs that peel directly to trees are expanded with `git ls-tree`, covering
path-bearing objects that `git log --all` silently ignores.
An active legacy `.git/info/grafts` file makes the evaluation
`insufficient_history` rather than allowing a pass, because Git still applies
grafted ancestry even when replacement objects are disabled.
Its counts cover distinct reachable leaf-object/path pairs, including every
alias of a shared object, while `violation_bytes` counts each violating leaf
object once.
Its `evaluation_status` (`evaluated`, `insufficient_history`, or
`not_requested`) is distinct from its predicate `status` (`pass`, `fail`, or
`unknown`); a shallow or incomplete repository can never establish a pass.
Summary reuse recomputes a full history-state fingerprint over the sorted
object/path records and evaluation outcome; matching ref tips alone cannot keep
a cached pass current after reachable objects become unavailable.
The scan is diagnostic for public-check execution status but is the only
history predicate used by external-report lifecycle reconciliation. Lifecycle
promotion also recomputes the current history scan and requires its full-pass
fingerprint to match the stored predicate; stale embedded pass fields are not
release evidence.

History remediation is not a public-check writer action. Rewriting refs requires
separate human approval after sensitivity classification, backups, and an
impact plan covering branches, tags, pull-request refs, forks, force-push, and
fresh-clone cutover. Completion requires a full-ref scan and a fresh clone to
both report zero forbidden history paths; do not weaken or skip the scanner to
manufacture that result.

General lane-selection guidance lives in [development.md](development.md).
