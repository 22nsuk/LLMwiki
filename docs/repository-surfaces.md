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

Dependency source authority in this surface is `pyproject.toml` plus `uv.lock`.
Root `requirements.txt` and `requirements-dev.txt` are intentionally retired
and are not public-export inputs.

Use `docs/public-mirror.md` for public boundary details and commands. Use
`make sync-public-policy` when the public boundary changes, and use
`make public-export` or `make public-check` when you need materialized export
evidence.

CBM indexing uses a separate public-safe export built by `make cbm-index-public`
or the lower-level CBM targets. That export is a navigation aid, not release
authority.

For source review handoff, use `make review-archive-clean`. It clears local
Python caches and scratch candidate JSON before running the clean
`review-archive` profile, producing the review archive and schema-backed report
without turning local diagnostic evidence into release authority.

For full-vault reviewer orientation, use `make review-surface-manifest`.
`docs/REVIEW_SCOPE.md` is the tracked canonical inventory; the companion JSON at
`tmp/review-surface-manifest.json` is intentionally ephemeral and must not be
promoted to `ops/reports/`.

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

`build/release/` may contain both active authority artifacts and diagnostic or
archived evidence. Only the staged manifests and the current sidecar set they
bind are authority. Preserved stale sidecars should be archived or explicitly
marked non-authoritative instead of remaining in the active sealed lane.

Likewise, reports intentionally excluded from a canonical or authoritative set
should be marked non-canonical rather than left beside active authority inputs
without explanation.

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

## Report Bucket Model

Release and runtime report paths are classified into exactly one bucket:

- `checked_in_canonical_source_side`: top-level `ops/reports/*.json` reports
  that are treated as source-side canonical evidence until regenerated or
  explicitly excluded.
- `build_release_authoritative_sidecar`: active `build/release/*.json`
  sidecars that are bound by staged release authority. Plan, preflight,
  preseal, dry-run, and archived files are not in this bucket.
- `observational_diagnostic`: diagnostic, scratch, nested, operator, or plan
  reports such as `ops/operator/`, `tmp/`, nested `ops/reports/**`, and
  non-authoritative `build/release/*-plan.json` evidence.
- `archival_historical`: preserved historical evidence under archive/archival
  paths such as `ops/reports/archive/`, `build/release/archive/`, and
  `external-reports/archive/`.

The bucket assignment and the documentation compliance verdict are separate:
runtime classification must still produce a total partition if this section is
missing or incomplete, but promotion/signoff should treat missing bucket
documentation as a policy failure until the public-safe criteria are restored.
When moving a report out of an authoritative bucket, apply the delete-first
rule: remove the old canonical path and keep the payload only in its explicit
new bucket.
Stale canonical report resolution records one decision per stale report:
regenerate it into HEAD-aligned current evidence, or remove it from the
canonical set with an explicit excluded/non-canonical marker. If the stale
payload is preserved outside the canonical set, the record must include the
preservation reason.

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

## Remote Governance Surface

`.github/release-governance.yml` is part of the public mirror and records the
remote-visible branch protection, required status checks, release asset, and
attestation contract. It is configuration evidence for GitHub rulesets/branch
protection and should stay aligned with `.github/workflows/ci.yml`,
`.github/workflows/codeql.yml`, `.github/workflows/dependency-review.yml`, and
`.github/workflows/release.yml`.

The file is intentionally public-safe: it names check lanes, branch patterns,
release asset names, and offline verification commands, but it does not contain
tokens, repository secrets, private corpus paths, or local operator state.
