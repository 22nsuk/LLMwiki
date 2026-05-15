# run-20260414-mechanism-planning-gate

## Chosen target
- Primary target: `ops/scripts/planning_gate_validate.py`
- Expected supporting targets:
  - `tests/test_run_templates.py`
  - one narrow planning-gate regression test if needed

## Why this is the recommended first run
- it closes a real operational gap in the new `system_mechanism` starter flow without requiring a broad new wrapper
- it uses an existing primary target, so baseline/candidate mechanism assessment is straightforward
- it improves the next run before trying to automate the full run lifecycle

## Alternatives reviewed and not chosen first
1. `run_mechanism_experiment.py`
This is valuable, but it would start from a brand-new primary script and widen the first run into orchestration design, artifact writing, and CLI ergonomics all at once.

2. `session_briefing.py`
This would help future sessions, but it does not directly reduce the current friction in starting and validating the first real mechanism run.

3. `promotion_gate.py` follow-up cleanup
The file was just modularized and already has stronger exit-code coverage. It is a valid later run, but not the highest leverage first baseline experiment.

## Working hypothesis
If `planning_gate_validate.py` understands mechanism-run promotion scaffolding more explicitly, then a maintainer can catch run setup mistakes before mutation starts, and future mechanism runs will have cleaner baseline/candidate artifact histories.

## Expected binary signal
- planning-gate validation gets stricter on mechanism-run scaffolding
- focused tests increase or become more specific
- repo health remains green

## Suggested baseline capture order
1. `python -m ops.scripts.wiki_lint --vault . --out runs/run-20260414-mechanism-planning-gate/baseline-lint.json`
2. `python -m ops.scripts.wiki_eval --vault . --require-max-score --out runs/run-20260414-mechanism-planning-gate/baseline-eval.json`
3. `python -m ops.scripts.mechanism_assess --vault . --primary-target ops/scripts/planning_gate_validate.py --test-file tests/test_run_templates.py --out runs/run-20260414-mechanism-planning-gate/baseline-mechanism-assessment.json`

## Suggested candidate capture order
1. implement the narrow planning-gate hardening change
2. rerun `make check`
3. capture `candidate-lint.json`
4. capture `candidate-eval.json`
5. capture `candidate-mechanism-assessment.json`
6. run `promotion_gate.py`

## Explicit boundary
- do not build a full experiment harness in this run
- do not change promotion semantics
- do not turn `planning_gate_validate.py` into a generic run orchestrator
