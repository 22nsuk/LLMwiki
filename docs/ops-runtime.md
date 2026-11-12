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

Command deadlines include output collection after the leader exits. A live
descendant holding stdout or stderr does not turn a timeout into success. The
POSIX backend signals the process group and escalates after the grace period;
every subsequent drain is bounded. If a writer remains outside the backend's
termination scope, the result records `output_drain_timeout`, partial output,
and a nonzero return code. Genuine completion races with output already at EOF
remain successful. Timeout handling may use up to two configured grace periods
after the execution deadline to terminate and collect output.

Unexpected errors after launch, including heartbeat/status-write failures and
interruption, abort the backend-owned process scope and perform a bounded reap
before propagating the error. This also covers failures while registering a
goal command's child identity. On POSIX the abort kills the process group even
when its leader has exited or closed output. SIGINT and SIGTERM use this same
abort path before forwarding the interruption to the previous signal handler;
output EOF alone cannot mark signal cleanup complete. Normal completion and timeout-race
handling retain their existing behavior. If termination or reaping cannot be
confirmed, `ProcessCleanupError` preserves the original failure as its cause;
the goal runner retains both locks for operator inspection instead of admitting
another writer.

Before launching a goal command, the workspace lock records
`child_registration_pending`. Successful PID/PGID registration clears it;
confirmed cleanup removes the lock normally. If registration and cleanup both
fail, a later runner, `make goal-runtime-lock-check`, and artifact
retention cleanup keep blocking even after the original runner exits. Lock
status reports `unresolved` when no recorded owner remains; `stop` refuses to
signal an unknown child. An operator must verify that the command and its
descendants have stopped before removing this lock. Resolve such a lock before
running an older runtime that does not recognize this field. Existing locks
without the field and registered children retain their PID/PGID-based stale
recovery behavior.

Mechanism repository-health checks, worker repository-health preflight, and
candidate dependency probes require Linux with Bubblewrap installed at
`/usr/bin/bwrap` and working user, PID, and network namespaces. On Debian/Ubuntu,
install it with `sudo apt-get install bubblewrap`. Ubuntu hosts with AppArmor
user-namespace restrictions also need the packaged Bubblewrap profile loaded:

```bash
sudo apt-get install --yes bubblewrap apparmor-profiles
bwrap_profile=/etc/apparmor.d/bwrap-userns-restrict
if [ ! -f "$bwrap_profile" ]; then
  bwrap_profile=/usr/share/apparmor/extra-profiles/bwrap-userns-restrict
fi
test -f "$bwrap_profile" && sudo apparmor_parser -r "$bwrap_profile"
```

Installing Bubblewrap alone does not load this profile and can leave network
namespace setup failing with `Failed RTM_NEWADDR: Operation not permitted`.
The profile is under `/etc/apparmor.d/` on newer Ubuntu images; older packages
place it under `/usr/share/apparmor/extra-profiles/`. Setup must fail if neither
packaged profile exists or the parser rejects it.
The shared CI setup action loads the profile and runs the production sandbox
launcher with dependency imports before the test lanes start. Unsupported hosts
or failed sandbox setup block validation; they never run the candidate on the host.
Goal-runtime bootstrap preflight uses the same bounded sandbox probe after its
Python, dependency, and Codex checks pass. Missing Bubblewrap, unusable namespaces,
or sandbox import failures produce a failed preflight with a `sandbox` diagnostic;
developer-only bootstrap checks do not require candidate execution support.

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

Update an existing item through the canonical writer instead of editing its
generated envelope by hand. Use
`python -m ops.scripts.mechanism.improvement_observations --task-id <task-id>
--update-observation-id <observation-id>` with at least one of `--status`,
`--suggested-followup`, or repeatable `--resolution-evidence`; the equivalent
`--run-id` form owns run observations. The command preserves the original
capture time and untouched observations while refreshing envelope fingerprints.

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

## Reusing Knowledge And Recording Maintenance Cost

For full-vault queries, start with the appropriate corpus router and reuse the
existing concept, synthesis, or query page when its evidence and scope cover the
question. Preserve source attribution, evaluation conditions, and uncertainty
in the answer. Reopen raw evidence when the page omits the needed support,
conflicts with another source, appears stale, or makes a stronger claim than its
citation supports. A structural quality pass does not establish factual accuracy.

Update pages when new evidence or a demonstrated mismatch changes their content.
A review may correctly end with `no_op`; record the reason and the review effort
without manufacturing an edit. When a correction changes a shared claim, follow
it into the relevant concept/synthesis, router, and registry note, then complete
the local supplement's log and final validation steps. Review a bounded source
batch against raw evidence instead of padding summaries to satisfy a heuristic.

At the next genuinely new source intake, start a private copy of the
[knowledge reuse cost record](../ops/templates/knowledge-reuse-cost-record.md)
before source discovery or drafting. Carry that record into later sessions so
initial construction, review, updates, reuse, and recovery remain attributable
to the same source. Completed examples reused for development are familiar
cases, not fresh holdout evidence. The blank template is public; populated
records and their source/answer snapshots belong under a private run or task
report directory. This is a manual diagnostic record, not a promotion artifact
or an automatically enforced runtime gate.

Compare answers only after checking the same source-grounded acceptance criteria.
Keep original answers and charge repair and re-review to the appropriate attempt.
Record failed attempts, no-op review, shared preparation, and orchestration
separately. Preserve unknown construction cost, tokens, cache usage, billing, and
natural error frequency as unknown; text bytes are not token or price estimates.
Do not infer whole-life savings from query latency alone. Label sums of task
durations separately from campaign wall time and human/CPU time, avoid counting
nested intervals twice, and identify any allocations of shared cost. Synthetic
recovery drills do not estimate natural error rates, and warm-session recovery
does not establish fresh-session recovery cost.

## Raw Intake And Registry Maintenance

All three intake modes (`raw-intake-source-quality`, `raw-intake-route-proposal`,
and `raw-intake-absorption-closeout`) validate the complete matrix before reading
raw/source/target files. The installed `raw-intake-absorption-matrix` schema owns
admission; the input's schema declaration or a vault-local schema cannot relax it.
Malformed JSON, duplicate JSON keys, nonstandard numeric constants, invalid
root/row types, missing fields and unknown fields are rejected without dropping
rows. Registry IDs must be nonempty, whitespace-free and unique. `source_count`
must equal the row count, and `action_counts`, `confidence_counts`, `target_counts`
must exactly tally the trimmed row values (no unused zero-count keys).

A legitimate empty batch still supplies the full schema-required envelope,
`source_count: 0`, `matrix: []`, and three empty count maps. Its pass means no work
was requested, with zero per-source results. An absent matrix is never an empty
batch. Regenerate old matrices with placeholder count maps before reuse.

Library callers receive `IntakeMatrixError` on admission failure. Both CLIs return
exit code 2 and an stderr diagnostic even without `--fail-on-fail`; they do not
write a report or overwrite a previous output. Callers must honor this exit code
and must not interpret a retained old report as the result of the failed command.
Valid matrices retain the existing per-source report and exit-code contracts.
Older successful reports do not establish that this admission check was run;
regenerate them with the current producer before reuse.

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

`make raw-intake-source-quality` and `make raw-intake-absorption-closeout`
require each matrix raw path to resolve to a readable regular file inside the
vault. Missing paths/files, directories, unreadable files, and paths outside the
vault block admission even for reviewed source-only seeds. Present binary raw
is accepted without a textual lead check. Route proposal reports apply the same
raw availability check; source pages may still be awaiting generation, and
unavailable identity metadata remains marked as skipped.

Source quality selects the first cleaned paragraph meeting
`--min-raw-lead-chars` (default 80), so a shorter photo caption or introduction
does not hide a later qualifying paragraph. It does not concatenate separate
short paragraphs to satisfy the minimum. If none qualifies, it retains the
first non-empty cleaned paragraph's length and hash with status `insufficient`;
the existing review/fail rules still apply. Empty or navigation-only captures
remain hard failures. `ok` means only that the cleaned length meets the minimum,
not that the text has been verified as article evidence: long captions and
unrecognized boilerplate still need source review. The report excerpt limit is
at least the configured minimum, including values above 700 characters.

The report shape is unchanged. Older reports remain readable, but regenerate
them before using the new paragraph-selection and short-text diagnostics;
historical `ok` alone did not imply the configured length threshold was met.

Markdown capture review runs through the existing normalization report, wiki
lint and intake source-quality report. `raw_markdown_normalize` adds
`raw_capture_*` codes to `manual_review_reasons`; `make lint` lists them as
`raw_snapshot_capture_review` review candidates, including raw files without a
source page. A capture review candidate is classified as `documentation_candidate` with
`refactor_candidate: false` and action `review_source_capture_preserve_raw`.
Source quality adds the same codes to `issues`. An otherwise valid,
reviewed intake remains `review` / `attention` while a signal is present; route
approval does not clear it. Existing empty/unavailable raw hard failures remain.

The shared, read-only detector recognizes missing body text, explicit automatic
summary blocks without article prose, article-like text after a copyright
boundary or a second distinct top-level title, and disjoint title vocabulary.
It compares declared titles with the first H1, article prose and human-readable
filenames. Slugs/IDs without spaces, short titles and cross-script translations
are excluded from the corresponding title comparisons. Recognized navigation,
recommendations, comments and code fences are excluded from analysis. Binary
and HTML intake inputs do not receive this Markdown capture review.

These are lexical review signals, not semantic contradiction detection, URL
verification or proof of a complete article. Paraphrases, shared vocabulary,
unrecognized captions/UI, multilingual text and unexpected page layouts can
produce false positives or missed cases. The detector never edits raw or
repairs titles; `--write` still performs only the normalizer's existing permitted
metadata/noise cleanup, and skips duplicate-preface removal for flagged captures
so the suspect article prefix remains reviewable. Review the original source, preserve historical captures
and register recovered bodies separately. A clear result means no recognized
signal. Old report shapes remain readable; regenerate reports before relying on
the new checks. Capture review does not change route/absorption authority.

Both report producers bind the complete raw and source-page file sets in
`input_fingerprints.raw_files` and `input_fingerprints.source_pages`. Each digest
covers sorted unique matrix paths, availability states, and full-file SHA-256
hashes from the same reads used by the checks. Raw tail edits, source body edits,
deletion/restoration, and changes to the referenced file set affect these
digests. Reordering matrix rows leaves the file-set digests unchanged; the
separate matrix byte fingerprint still changes. These digests are separate from
the public `source_tree_fingerprint` and do not expose private file contents.
Regenerate older reports before relying on corpus content identity: reports
without these keys remain readable historical evidence but cannot establish it.

Route report version 2 separates review from reflection:

- `route_proposal` checks assignment review and input identity. Its
  `route_status` can pass while `closeout_status` and `absorption_audit.status`
  remain `not_checked`; it does not count any completed closeout.
- `absorption_closeout` retains those checks and requires a readable source page
  with a raw-path binding. For `refresh_existing_synthesis` and
  `create_new_synthesis_family`, the concrete concept/synthesis target must be a
  readable file and contain a visible wikilink back to that source. Plain source
  names, routing metadata, HTML comments and code examples do not count as links.
  Closeout parses CommonMark blocks and inline tokens (with Markdown tables),
  retaining the existing wikilink target, anchor and alias syntax. Fenced and
  indented code are excluded inside lists and nested blockquotes as well as at
  the document root. Escaped brackets, HTML tokens, image alt text and link
  destinations do not create wikilink evidence; visible prose links after a code
  block still count. The source-body check uses the same parsed prose boundary.
- `target` can identify a unique flat page stem or a vault-relative `wiki/` or
  `system/` page path. When it is a proposed family label, add the reviewed
  `target_page` binding to the matrix; the gate does not guess a page from a
  topic label. Qualified links disambiguate identical stems across corpora.
  Missing, ambiguous, unreadable, non-file and outside-vault targets fail.
- `update_existing_source` requires the target to be the source page itself;
  a self-link is unnecessary. `keep_source_only_seed` requires the retained
  source but reports absorption as `not_applicable`. `discard_from_active_routes`
  also reports `not_applicable`: this approves a disposition, not proof of
  deletion. Neither disposition contributes to `absorption_pass_count`.

Closeout also binds `input_fingerprints.target_pages` (sorted path, availability,
full-byte SHA-256) and `absorption_page_paths` (the page-name set used to resolve
stems). Target edits, removal/restoration or newly ambiguous names invalidate
that evidence. These checks read the files without changing corpus pages.
Version 1 route reports remain schema-readable historical records, but their
`closeout_status: pass` established only route review; regenerate them with
`--mode absorption_closeout` before relying on completion. Consumers of version
2 must use `route_status` for proposal readiness and `closeout_status` plus the
absorption audit for reflection. A structural pass establishes current file and
linkage presence, not a before/after textual change, faithful claim integration
or semantic correctness; those still require source-backed review.

Source-trace eval report version 2 similarly separates declaration from
verification. Backticked external URLs are `external_unverified`, `exists: null`,
and `verification_status: not_checked` in every distribution profile. They are
reported separately from missing local paths and do not fail a check whose
`assurance_scope` is `local_path_existence_only`. No URL fetch or claim check is
performed. A local `present` result checks existence only. Regenerate version 1
reports before using these distinctions; a previous URL `present` result is not
evidence that it was ever retrieved or verified.

## Compatibility Surface

Some lifecycle-policy flat module paths such as
`python -m ops.scripts.release_smoke` continue to work through compatibility
routing. New docs should prefer Make targets or canonical package paths such as
`ops.scripts.release.release_smoke`; use `llm-wiki-*` only for lifecycle policy
public CLIs.
