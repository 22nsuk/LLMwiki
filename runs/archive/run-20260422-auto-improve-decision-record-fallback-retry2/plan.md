# run-20260422-auto-improve-decision-record-fallback-retry2

## Chosen target
- Primary target: `ops/scripts/auto_improve_iteration_persistence_runtime.py`
- Supporting targets: `ops/schemas/run-telemetry.schema.json`

## Why this is the right first mechanism
- Replace with the local failure mode this run is trying to reduce.
- Replace with why this target is narrow enough for a one-mechanism experiment.

## Expected binary signal
- Replace with the exact promotion or non-regression signal you expect to observe.

## Suggested baseline capture order
1. `baseline-lint.json`
2. `baseline-eval.json`
3. `baseline-mechanism-assessment.json`

## Suggested candidate capture order
1. run the scoped mutation command
2. rerun repo health gate
3. `candidate-lint.json`
4. `candidate-eval.json`
5. `candidate-mechanism-assessment.json`
6. `promotion-report.json`

## Follow-up capture
- Before closing the run, append any reusable automation or repo hygiene follow-up to `runs/run-20260422-auto-improve-decision-record-fallback-retry2/improvement-observations.json`.

## Explicit boundary
- Do not broaden the run beyond one primary mechanism.
