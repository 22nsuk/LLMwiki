# Repository Surfaces

This is the quick comparison for the three repository shapes operators and
reviewers are most likely to confuse:

- the full local vault used for private operation;
- the public mirror/export used for source review and public checks;
- the release source ZIP used for package replay and release evidence.

Each surface has a different owner, command lane, and proof standard. Do not
use one surface as authority for another unless a schema-backed report or Make
target explicitly binds them.

## Surface Matrix

| Surface | Purpose | Includes | Excludes | Authority | Generate | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| Full local vault | Private operator workspace and canonical corpus operation. | Public code/ops plus local `raw/`, `wiki/`, `system/`, `runs/`, `external-reports/`, and generated evidence. | Nothing by default, but binary raw is read-only and generated evidence is not hand-edited source. | `AGENTS.md` plus `AGENTS.local.md` for local-only work. | Normal Git checkout plus local operator state. | Task-specific gates such as `make check`, `make release-check`, or the runbook target in use. |
| Public mirror/export | Corpus-free code/ops runtime for public review, tests, CI, and optional CBM indexing. | `docs/`, `ops/`, `tests/`, `tools/`, `mk/`, `.codex/agents/`, `.github/`, and root public documents/config. | `raw/`, `wiki/`, `system/`, `runs/`, `external-reports/`, `ops/operator/`, `ops/reports/`, `tmp/`, and private inventory files. | `ops/scripts/public/public_surface_policy.py`. | `make sync-public-policy` and `make public-export`. | `make sync-public-policy-check`, `make public-check`, or `make public-check-all`. |
| Release source ZIP | Normalized source package for release replay, package smoke, sealing, and provenance sidecars. | The policy-approved source package contents and release metadata needed for replay. | Private corpus, local active reports, scratch state, and generated evidence not intentionally packaged as sidecars. | Staged manifests under `build/release/`, especially run-ready, sealed-run-ready, and auto-promotion-ready manifests. | `make release-run-ready`, then `make release-sealed-run-ready` when sealing is required. | `make release-run-ready-check`, `make release-sealed-run-ready-check`, and `make release-auto-promotion-ready-check`. |

## Full Local Vault

The full local vault is the only surface where private corpus and operator
evidence may exist together. It may contain `raw/`, `wiki/`, `system/`,
`runs/`, `external-reports/`, `ops/reports/`, `ops/operator/`, `build/`, and
`tmp/`.

Use it for source intake, corpus maintenance, mechanism runs, external report
intake, and release evidence generation. When work directly touches local-only
surfaces, read `AGENTS.local.md` in addition to `AGENTS.md`.

Do not copy private corpus contents, active external report text, live run
payloads, or local inventory into public docs, tests, or fixtures. Public source
changes should encode the rule, schema, script, test, or sanitized summary that
future public users can reproduce without private state.

## Public Mirror And Export

The public mirror is the source-review shape. It must remain useful without
private corpus directories or generated evidence directories. The canonical
membership policy is `ops/scripts/public/public_surface_policy.py`; generated
ignore templates such as `ops/templates/public-mirror.gitignore` are derived
from that policy.

Use `docs/public-mirror.md` for public boundary details and commands. Use
`make sync-public-policy` when the public boundary changes, and use
`make public-export` or `make public-check` when you need materialized export
evidence.

CBM indexing uses a separate public-safe export built by `make cbm-index-public`
or the lower-level CBM targets. That export is a navigation aid, not release
authority.

## Release Source ZIP

The release source ZIP is not the full local vault and not merely a public
mirror copy. It is a normalized package replay surface bound to release
manifests and sidecar evidence.

The staged release authority lives under `build/release/`:

- `release-run-manifest.json` answers whether the current committed tree is
  runnable.
- `release-sealed-run-manifest.json` answers whether the source ZIP and
  sidecars are sealed evidence.
- `release-auto-promotion-ready-manifest.json` answers whether unattended
  promotion is allowed.

`ops/reports/` remains local diagnostic evidence unless a release stage binds a
specific report digest into the package or sidecar set. Source-package smoke
runs in a release-archive profile because a clean source ZIP intentionally does
not include private corpus surfaces.

## Artifact-Only Surfaces

These paths are evidence or scratch surfaces, not hand-maintained source:

- `ops/reports/`
- `ops/operator/`
- `build/release/`
- `runs/`
- `tmp/`

Refresh them through the owning Make target or schema-backed writer. If a
generated report exposes a rule that should become durable public behavior,
move the behavior into source, schema, policy, fixture, or test coverage instead
of committing the local report payload.

## Change Checklist

When a change affects repository boundaries, check the owner surface first:

- Public membership or export behavior: update
  `ops/scripts/public/public_surface_policy.py`, relevant public docs, and
  public export tests, then run `make sync-public-policy`.
- Release package or authority behavior: update the owning release script,
  schema, Make target, and tests, then use the staged release checks in
  `docs/release.md`.
- Full-vault local-only workflow: keep private details out of public fixtures,
  update local evidence through official targets, and apply `AGENTS.local.md`.
- Generated evidence behavior: update the producer and schema, regenerate via
  official targets, and avoid manual JSON edits.

For the broader runtime map, see `ARCHITECTURE.md`. For public export details,
see `docs/public-mirror.md`. For release runbooks, see `docs/release.md`.
