# Open Questions

1. Should `planning_gate_validate.py` validate `promotion-report.json` whenever that file exists in the artifact directory, or only when the run clearly follows the mechanism-run starter layout?
2. Should run-id alignment be extended from `seed.yaml` / `planning-validation.json` / `run-ledger.json` to `promotion-report.json` as well?
3. Is a schema-only check enough for the first pass, or should the same run also add one narrow cross-check on `promotion-report.inputs.run_ledger` path consistency?
