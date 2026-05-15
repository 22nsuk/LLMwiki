# run-20260507-auto-improve-iteration-persistence-discard-path

## Chosen target
- Primary target: `ops/scripts/auto_improve_iteration_persistence_runtime.py`
- Supporting targets: `ops/schemas/run-telemetry.schema.json`

## Why this is the right first mechanism
- contract_regression_signals family에서 `repeated_discard_runs` 신호가 최근 2개 run 기준으로 누적돼 지금 한 번의 단일 mechanism 실험으로 국소화할 가치가 있다.
- If the next experiment around ops/scripts/auto_improve_iteration_persistence_runtime.py changes only one DISCARD-producing path and records explicit non-regression evidence, recent discard/rework pressure should drop without expanding the mechanism surface.

## Expected binary signal
- next finalized attempt for this target avoids DISCARD while candidate_eval non-regresses and promotion artifacts explain the terminal decision

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
- Before closing the run, append any reusable automation or repo hygiene follow-up to `runs/run-20260507-auto-improve-iteration-persistence-discard-path/improvement-observations.json`.

## Explicit boundary
- narrow the next mechanism experiment on ops/scripts/auto_improve_iteration_persistence_runtime.py to the DISCARD outcome path only
