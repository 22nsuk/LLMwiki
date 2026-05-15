# run-20260415-mechanism-planning-gate-second-clean

## Chosen target
- Primary target: `ops/scripts/planning_gate_validate.py`
- Supporting targets: `ops/scripts/planning_gate_validate_runtime.py`

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

## Explicit boundary
- Do not broaden the run beyond one primary mechanism.
