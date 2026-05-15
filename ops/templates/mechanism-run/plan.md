# run-YYYYMMDD-mechanism-slug

## Chosen target
- Primary target: `ops/scripts/<primary-target>.py`
- Supporting targets: replace with zero to two concrete paths

## Why this is the right first mechanism
- Replace with the local failure mode this run is trying to reduce.
- Replace with why this target is narrow enough for a one-mechanism experiment.

## Expected binary signal
- Replace with the exact promotion or non-regression signal you expect to observe.

## Suggested baseline capture order
1. freeze at least one target-focused regression test file
2. `baseline-lint.json`
3. `baseline-eval.json`
4. `baseline-mechanism-assessment.json`

## Suggested candidate capture order
1. implement one narrow mechanism change
2. rerun `make check`
3. `candidate-lint.json`
4. `candidate-eval.json`
5. `candidate-mechanism-assessment.json`
6. `changed-files-manifest.json`
7. `behavior-delta.json`
8. `promotion-report.json`

## Explicit boundary
- Do not broaden the run beyond one primary mechanism.
