# Ops Runtime

The ops runtime is the repository control layer: policy, schema, reports,
Make orchestration, and helper scripts.

## Make Layout

- `mk/core.mk`: environment setup and bootstrap preflight.
- `mk/static.mk`: ruff and mypy gates.
- `mk/test.mk`: pytest lanes and report-contract packs.
- `mk/eval.mk`: lint, eval, warning, and complexity gates.
- `mk/artifact.mk`: generated artifact refresh and convergence helpers.
- `mk/registry.mk`: raw registry and manifest surfaces.
- `mk/mechanism.mk`: self-improvement, goal runtime, and mechanism workflows.
- `mk/release.mk`: shared release variables and compatibility entrypoints.
- `mk/release-authority.mk`: run-ready, sealed-run, and auto-promotion authority.
- `mk/release-evidence.mk`: release evidence, closeout, archive, and smoke lanes.
- `mk/release-learning.mk`: learning readiness, remediation, and session evidence.
- `mk/public.mk`: public export and public-check targets.
- `mk/supply_chain.mk`: provenance, SBOM, OpenVEX, in-toto, and Sigstore surfaces.

## Script Layout

`ops/scripts/` is organized by runtime domain:

- `core/`: shared artifact, path, policy, schema, command, and workflow helpers.
- `eval/`: lint, eval, warning, complexity, and documentation audit helpers.
- `registry/`: raw registry export, preflight, normalization, and intake.
- `mechanism/`: mechanism review, mutation proposal, goal runtime, and experiments.
- `release/`: release evidence, external report lifecycle, sealing, and summaries.
- `learning/`: learning claim, readiness signoff, remediation, and lesson surfaces.
- `supply_chain/`: provenance, SBOM, advisory, OpenVEX, in-toto, and Sigstore.
- `public/`: public export, public check, and public-surface helpers.
- `test/`: test execution summary and lane registry runtime.

After editable install, lifecycle policy public CLIs are exposed as
`llm-wiki-*` console scripts from `pyproject.toml`. Make targets are the
preferred operator entrypoint for report generators and maintenance lanes.

## Candidate Validation Isolation

Mechanism repository-health checks, worker repository-health preflight, and
candidate dependency probes require Linux with Bubblewrap installed at
`/usr/bin/bwrap` and working user, PID, and network namespaces. On Debian/Ubuntu,
install it with `sudo apt-get install bubblewrap`. Ubuntu hosts with AppArmor
user-namespace restrictions also need the packaged Bubblewrap profile loaded:

```bash
sudo apt-get install --yes bubblewrap apparmor-profiles
sudo apparmor_parser -r /usr/share/apparmor/extra-profiles/bwrap-userns-restrict
```

Installing Bubblewrap alone does not load this profile and can leave network
namespace setup failing with `Failed RTM_NEWADDR: Operation not permitted`.
The shared CI setup action loads the profile and runs the production sandbox
launcher with dependency imports before the test lanes start. Unsupported hosts
or failed sandbox setup block validation; they never run the candidate on the host.

The trusted parent launches the check in a fresh filesystem and network
namespace. Only the candidate workspace is writable on the host; `/tmp` and
shared memory are disposable, bounded mounts. System tools and the launcher's
Python runtime are read-only. The parent supplies a synthetic HOME and a fixed
environment without credentials, Python import overrides, or user tool config.
Network-dependent checks must use local fixtures and dependencies installed
before validation. Both default and explicit check commands use this boundary.
Full-copy preflight runs the candidate Makefile inside the sandbox, so it checks
candidate code without writing to the live checkout. Candidate descendants are
terminated when their validation command exits or times out.

Python mount sources are captured from the controller's runtime before candidate
execution. A candidate interpreter link cannot add host mounts. Requests that
resolve to the controller's base executable run through its original virtualenv
path, preserving installed dependencies and installer prefix aliases. Requests
for a different installation fail closed: start the controller in that Python
environment to use it for validation.

Workspace files must not contain external symlinks (except validated virtualenv
interpreter entrypoints), hard links, sockets, devices, or FIFOs. This is checked
before execution and before the host reads resulting diagnostics. Unsafe outputs
abort before host audit, log, or ledger writes, including failed validation.
Ordinary files and internal symlinks remain supported. Files already
copied into the candidate are visible there; keep secrets out of candidate inputs.
The authorized mutation controller retains its existing agent and artifact access.

Host diagnostics apply the same workspace checks before worker snapshots and
structural preflight. Function-budget policy prefixes and discovered Python files
must resolve inside the candidate vault, including file and directory symlinks.
An escaping path blocks diagnostics after both successful and failed checks;
contained paths, internal aliases, and missing optional prefixes remain supported.

## Generated Artifacts

Schema-backed JSON reports should use the shared artifact writer helpers and
include a canonical envelope. Candidate-to-promote writers should write under
`tmp/*.candidate.json` first, validate schema and producer metadata, then
promote to the durable path.

General rule:

- canonical evidence is written to local-only `ops/reports/` or `ops/operator/`
  paths and should not be tracked as public source; if stale evidence is kept
  for investigation, archive or mark it non-canonical instead of leaving it in
  the active authority set;
- check-only or advisory scratch output lives under `tmp/`;
- release packages, source-package extracts, and audit packs live under `build/`.

Tracked source-derived projections converge through `make sync-derived`, whose
membership is declared in `ops/policies/derived-surfaces.json` and projected
into `mk/derived-surfaces.generated.mk`. The write aggregate refreshes tracked
projections and selected operator-local diagnostics. Use
`make sync-derived-check` when a CI or review context must prove checkable
projections are current and validate inventory/operator metadata without
rewriting files. This is separate from `make generated-artifact-converge`, which
belongs to release/report finality evidence under generated report surfaces.

When adding or changing an ops script, treat the script source, `pyproject.toml`
console-script exposure, Make recipe references, and small override files as
the human-owned contract. Add or adjust source-derived projection membership in
`ops/policies/derived-surfaces.json`, then run `make sync-derived` so the
generated Make fragment and the declared projections converge from those
sources. New generic `ops/scripts/**/*.py` changes are also known to the workflow
dependency planner as runtime source changes. Their iterative minimum pairs
`make static` with any focused tests selected by changed test files or
owner-specific rules. Shared lane-contract changes and the final release
checkpoint still run their broader authoritative lanes.

Static Make/CI tests should keep structural invariants and wiring checks only.
Exact generated content belongs in the generator unit test or the
`make sync-derived` no-op convergence check. Protected release recipe roles and
ordering remain declarative in the release workflow order guard spec; its raw
Make recipe line snapshots are refreshed through `make sync-derived`.

Observation closeout uses the tracked
`ops/observation-closeout-registry.json` only for retained `open` or `planned`
follow-ups. Run `make observation-closeout-lint` before adding registry entries:
closed `automated` observations with resolution evidence stay in their
observation artifact, and `wontfix` observations must carry explicit resolution
evidence rather than being hidden by omission. Do not blanket-register a task's
observations; register only the unregistered open/planned items reported by the
lint.

For meta-maintenance tracks that reduce bookkeeping surfaces, declare a stop
condition once the duplicated owner has moved to a generator, manifest, or lint.
After that point, observe the next 20-30 commits for recurring companion edits
such as schema sample seeds, static gate mirrors, or sync manifest churn. If the
recurrence does not reappear, close the track and fold any remaining small seed
or literal reductions into the next real schema/runtime change instead of
opening another standalone cleanup phase.

Operator-facing `current` or reusable-evidence decisions should come from the
objective lane checks that bind HEAD, source fingerprint, and domain-specific
currentness. Self-declared current fields are diagnostic metadata, not
authority by themselves.

## Raw Intake And Registry Maintenance

Full-vault raw intake work should move through the reviewable surfaces in this
order:

1. Run the route proposal audit before writing or promoting pages.
2. Use the absorption matrix as the per-source decision trail.
3. Reflect approved source decisions in source, concept, and synthesis bodies,
   not only in placement metadata.
4. Check whether raw registry shards need a parent-router or second-order split.
5. Run `make raw-registry-shard-policy-sync-check` after shard edits; use
   `make raw-registry-shard-policy-sync-write` only when the check report shows
   policy surfaces that should be derived from existing shard pages.
6. Finish with `make lint`, `make stage2-eval`, and
   `make registry-preflight-check` for full-vault registry changes.

Synthesis and concept pages should read as reusable wiki knowledge, not intake
or routing memos. Keep route notes in maintenance sections, keep `Related pages`
focused on navigation rather than source inventories, and use an evidence map
only when it improves the analysis instead of duplicating `Evidence considered`
or `Source trace`.

## Compatibility Surface

Some lifecycle-policy flat module paths such as
`python -m ops.scripts.release_smoke` continue to work through compatibility
routing. New docs should prefer Make targets or canonical package paths such as
`ops.scripts.release.release_smoke`; use `llm-wiki-*` only for lifecycle policy
public CLIs.
