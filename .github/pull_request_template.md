## Summary
- 

## Review
- [ ] Reviewer confirms the changed source, tests, docs, schemas, and generated artifacts line up with the stated runtime contract.
- [ ] Reviewer checks that any retained fallback, compatibility path, or operator-only lane has an explicit reason and revisit condition.

## Validation
- Operator index: `make help`; lane-selection details: `docs/development.md`
- [ ] `make static`
- [ ] Focused `.venv/bin/python -m pytest tests/...` selector or the Make lane that matches the change intent
- [ ] `make sync-derived` when tracked derived projections or public surface rules change
- [ ] `make public-check` when export or private-boundary behavior changes

## Boundary Check
- [ ] No private corpus, live run artifact, local path, or temp workspace detail was copied into public fixtures/docs
- [ ] Tracked source-derived projections affected by this change were refreshed through `make sync-derived`
