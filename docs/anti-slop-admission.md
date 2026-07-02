# Anti-slop admission

New gates, reports, schemas, and Make targets must pass a five-field admission
review before they become operator-facing or release-blocking surfaces.

## Five-field admission rule

Every proposed surface must declare:

1. **Purpose** — what operator or maintainer question it answers in one sentence.
2. **Evidence contract** — which inputs, schemas, and producer modules are canonical.
3. **Gate effect** — the strongest `gate_effect` the surface may emit; use
   `ops/scripts/core/gate_effect_vocabulary.py` (`none`, `advisory`,
   `claim_blocker`, `operator_review_required`, `blocks_promotion`,
   `blocks_execution`).
4. **Retirement trigger** — the observable condition that makes the surface
   obsolete or demotable to advisory/backlog.
5. **Replacement path** — the Make target, script module, or existing report
   that should subsume the surface if it is retired.

Surfaces that cannot name all five fields stay in backlog until the contract is
complete.

## Code enforcement

`make make-target-inventory` writes the diagnostic Make inventory report, and
`make make-target-inventory-check` runs the same live contract without rewriting
that diagnostic. Both run `ops/scripts/core/anti_slop_admission_runtime.py`
against `ops/make-target-inventory-operator.json` and `ops/script-lifecycle-policy.json`:

- Operator inventory entries require `purpose` and `replacement`; each `target`
  must exist in the Makefile inventory.
- Lifecycle modules require `rationale`; `replacement` is required except when
  `lifecycle` is `public_cli`.
- Runnable script surfaces discovered from pyproject scripts, Make
  `python -m ops.scripts...` calls, or direct fallback markers must resolve to
  an `ops/scripts` file and have a lifecycle policy entry.
- `removal_ready: true` requires `remove_after`; expired `remove_after` dates fail
  admission.
- Schemas reference `gate_effect_vocabulary` via `$ref` rather than inline enums.

Regression coverage: `tests/test_anti_slop_admission_runtime.py` and
`tests/test_make_target_inventory.py`.

## Retirement rule

Retire or demote a surface when any of the following is true:

- A replacement path has shipped and the old surface duplicates it without
  adding independent evidence.
- The gate effect stayed `advisory` or `none` across three consecutive
  refresh cycles while still requiring operator attention.
- The schema or report never gained a focused test in `tests/` and is not
  referenced by `ops/test-lane-registry.json`, `ops/script-lifecycle-policy.json`,
  or a documented Make entrypoint.

Demoted axes and reports must record a `retirement_condition` field in their
output until removal is safe.

## Related contracts

- Gate vocabulary: `ops/scripts/core/gate_effect_vocabulary.py`
- Script lifecycle intent: `ops/script-lifecycle-policy.json`
- Make target inventory: `make make-target-inventory`,
  `make make-target-inventory-check`, and
  `ops/make-target-inventory-operator.json`
- Lane registry and derived projection alignment: `ops/test-lane-registry.json`
  and `make sync-derived-check`
- Review scope manifest: `docs/REVIEW_SCOPE.md` is the tracked canonical
  reviewer inventory; `tmp/review-surface-manifest.json` is an intentionally
  ephemeral navigation aid from `make review-surface-manifest` and must not be
  promoted to `ops/reports/`.
