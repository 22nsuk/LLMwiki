# Knowledge Reuse Cost Record

Copy this blank template into a private run or task report directory before a
new source intake begins. Keep the same record across sessions; append attempts
instead of replacing failures. This manual record is diagnostic evidence, not a
schema-backed promotion report. Do not publish filled records or private inputs.
See the [operating procedure](../../docs/ops-runtime.md#reusing-knowledge-and-recording-maintenance-cost).

## Scope Frozen Before Work

- Record ID / source identity: `unrecorded`
- Source snapshot path and SHA-256 / corpus revision: `unrecorded`
- Source discovery and capture included from the start: `unknown`
- Source and question novelty / prior exposure: `unknown`
- Question and source-grounded acceptance criteria: `unrecorded`
- Raw-only and wiki-first input sets / selection method: `unrecorded`
- Assigned model, reasoning settings, actual backend identity: `unknown`
- Session context, caches, concurrency and execution order: `unrecorded`
- Clock identity, timing start/end boundaries, exclusions: `unrecorded`
- Reviewer identity and blind/nonblind review method: `unrecorded`

## Attempt Ledger

Add a row for each attempt. Stage can be discovery/capture, initial construction,
review, update, reuse, repair, recovery, or shared setup/orchestration. Preserve
the original answer, source evidence, corrections and acceptance result in
linked private artifacts. Use a parent ID for nested work so aggregates do not
double-count it. Each process/session clock must be identified; do not subtract
timestamps from incompatible clocks.

| Attempt ID / parent | Stage / raw or wiki path | Session / clock | Start / end and elapsed seconds | Outcome / reason | Evidence references |
| --- | --- | --- | --- | --- | --- |
| unrecorded | unrecorded | unrecorded | unknown | not_started | unrecorded |

Distinguish completed, failed, incomplete, excluded-from-comparison and
not-started attempts. An exclusion needs a reason and still retains incurred
cost. For incomplete work, preserve any observed interval as a lower bound, not
as the final duration. A completed update review may be `no_op`; its review
effort is still part of the ledger. Work that has not occurred is not zero cost.
Record naturally occurring failures separately from injected faults, and identify
whether recovery had warm context or a fresh session.

## Usage And Unknowns

Record provider usage with units and a receipt/log reference per attempt where
available. Use `null` or `unknown` for unavailable values; never infer tokens from
characters/bytes or infer charges from elapsed time.

| Attempt ID | Input / output / reasoning / cached tokens | Billed amount / currency | Usage evidence or reason unknown |
| --- | --- | --- | --- |
| unrecorded | unknown | unknown | unrecorded |

- Initial construction cost captured completely: `unknown`
- Source discovery/capture, shared preparation and reviewer effort: `unknown`
- Unobserved queue time, retries or orchestration: `unknown`
- Natural error frequency and future update frequency: `unknown`

## Comparison And Closeout

- Source-grounded quality result for each original and repaired answer:
  `unrecorded`
- Comparable raw/wiki attempts and excluded attempts with reasons: `unrecorded`
- Per-stage totals and treatment of overlapping/shared intervals: `unrecorded`
- Campaign wall time versus sum of task elapsed time: `unknown`
- Any human/CPU-time measurements, units and collection method: `unknown`
- Conditional workload scenario and assumptions, if used: `unrecorded`
- Supported conclusion and unmeasured costs that limit it: `unrecorded`
- Page update or no-op decision and supporting source evidence: `unrecorded`
- Existing observation ID, remaining work and next real intake/reuse event:
  `unrecorded`

Include answer repair and re-review when comparing accepted answers. If any cost
component is unknown, label the sum as measured components only. Do not claim
whole-life savings or break-even from that subtotal. Reusing a known question
does not create an independent holdout. A planned future observation remains
pending until its real event occurs.
