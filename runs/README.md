# runs/

이 디렉터리는 실제 planning bundle과 meta-improvement run의 **live artifact workspace**다.

저장소 추적 정책:
- Git에는 기본적으로 `runs/README.md`만 남기고, 실제 run artifact는 로컬 workspace 산출물로 취급한다.
- 장기 보관이 정말 필요할 때만 run artifact를 별도 sanitize/export한 뒤 명시적으로 포함하는 편이 좋다.
- 기본 run artifact는 절대경로보다 repo-relative path를 우선 남기는 방향으로 유지한다.
- 기존 artifact를 공유 가능한 형태로 다시 정리하려면 `make sanitize-runs` 또는 `./.venv/bin/python -m ops.scripts.sanitize_run_artifacts --vault .`를 사용한다.

권장 구조:
- `runs/<run-id>/seed.yaml`
- `runs/<run-id>/planning-validation.json`
- `runs/<run-id>/run-ledger.json`
- `runs/<run-id>/promotion-report.json`
- `runs/<run-id>/plan.md`
- `runs/<run-id>/task-graph.json`
- `runs/<run-id>/open-questions.md`

`system_mechanism` experiment 권장 추가 artifact:
- `runs/<run-id>/baseline-eval.json`
- `runs/<run-id>/candidate-eval.json`
- `runs/<run-id>/baseline-lint.json`
- `runs/<run-id>/candidate-lint.json`
- `runs/<run-id>/baseline-mechanism-assessment.json`
- `runs/<run-id>/candidate-mechanism-assessment.json`

원칙:
- 새 run은 목적에 맞는 starter에서 시작한다.
  - planning / handoff는 `ops/templates/`
  - `system_mechanism` experiment는 `ops/templates/mechanism-run/`
- `run-ledger.json`은 상태 전이와 결정 이벤트를 append-style로 누적한다.
- `run-ledger.json`은 canonical event vocabulary(`created`, `seed_frozen`, `baseline_captured`, `mutation_applied`, `mutation_failed`, `candidate_captured`, `repo_health_checked`, `promotion_evaluated`, `history_status_updated`, `finalized`)와 UTC `YYYY-MM-DDTHH:MM:SSZ` timestamp를 사용한다.
- `plan.md`와 `open-questions.md`는 schema gate 대상은 아니지만, scope 결정과 후속 세션 handoff를 위해 starter와 함께 두는 편이 좋다.
- `system_mechanism` promotion을 할 때는 관련 event의 `artifacts`에 실제 primary target 경로를 repo-relative로 남기는 편이 좋다.
- `promotion-report.json`은 특정 wiki/system promotion event의 판정 결과를 남기는 canonical report다.
- `system_mechanism` promotion report의 `history.status`는 run lifecycle의 canonical source다. `active`만 mechanism review/mutation proposal active history에 포함되고, `archived`/`quarantined`는 advisory report의 `excluded_runs`로만 남는다.
- 사람용 장기 chronology는 `system/system-log.md`에 남기고, run-local 상태는 `runs/<run-id>/`에 남긴다.
- `mechanism_review.py`는 이 디렉터리의 promotion / assessment artifact를 읽어 advisory queue를 만들지만, queue 자체를 `system/system-log.md`에 자동 append하지 않는다.
- `mutation_proposal.py`는 mechanism review queue를 읽어 단일 mechanism scope proposal을 만들지만, proposal queue도 `system/system-log.md`에 자동 append하지 않는다.
- proposal에서 실제 run을 열기로 정했다면 `python -m ops.scripts.run_mechanism_experiment --vault . --run-id <run-id> --proposal-id <proposal-id> --scaffold-only`로 starter를 먼저 만들고, 선택된 proposal은 `runs/<run-id>/proposal-snapshot.json`으로 run-local에 freeze하는 편이 좋다.
- 구조 점검은 `python -m ops.scripts.planning_gate_validate --vault . --artifact-dir runs/<run-id>`로 한다.
- `planning_gate_validate`는 이제 starter bundle뿐 아니라 completed/finalized `system_mechanism` run도 phase-aware하게 검사한다.
  - completed/finalized mechanism run에서는 baseline/candidate eval·lnt·mechanism assessment, promotion-report, run-ledger locality, finalized log state까지 함께 본다.
- `python -m ops.scripts.finalize_run --vault . --run-id <run-id>`는 finalized mechanism run의 append-only log entry, promotion-report log state, run-ledger finalization, planning-validation refresh를 한 번에 마감하는 helper다.
- `python -m ops.scripts.run_mechanism_experiment --vault . --run-id <run-id> ... --mutation-command "<cmd>"`는 scaffold, baseline capture, mutation command, candidate capture, repo health command, promotion evaluation, 조건부 finalization을 한 번에 묶는 wrapper다.
  - full execution mode에서는 baseline/candidate mechanism assessment가 generic smoke가 아니라 실제 target-facing surface를 보도록 최소 1개 `--test-file`을 요구한다.
  - proposal-aware starter generation만 필요할 때는 `--proposal-id ... --scaffold-only`를 써서 `seed.yaml`, `plan.md`, `open-questions.md`, `proposal-snapshot.json`만 먼저 얼릴 수 있다.

메커니즘 실험 메모:
- 첫 실제 run에서는 `seed.yaml`의 scope와 `promotion-report.json`의 primary target을 먼저 좁히고 시작하는 편이 안전하다.
- baseline test set에는 최소 1개의 target-focused regression test를 포함하는 편이 좋다. 그렇지 않으면 test-count improvement가 generic smoke 증가로 과대 해석되기 쉽다.
- `promotion_gate.py`의 shell exit code는 report 생성 성공 여부를 말할 뿐이므로, 실험 결과는 반드시 `runs/<run-id>/promotion-report.json`의 `decision`으로 읽는다.
- `system/system-log.md`는 실험 후보 queue가 아니라 채택된 실험 chronology다. run이 끝나고 결과가 확정된 뒤에만 append한다.
- wrapper를 쓰더라도 `mutation_command`는 한 메커니즘만 바꾸도록 유지하는 편이 좋다. signoff가 pending이면 wrapper는 promotion report를 남기고 `HOLD`에서 멈추며, append-only log finalization은 수행하지 않는다.
- buggy run을 active history에서 빼야 할 때는 directory move를 기본값으로 쓰지 말고, 먼저 `./.venv/bin/python -m ops.scripts.set_mechanism_run_history --vault . --run-id <run-id> --status archived|quarantined --reason \"<reason>\" --by <actor>`로 lifecycle status를 갱신한다.
- physical move는 예외적인 장기 보관 정리일 뿐이며, 필요하더라도 `history.status`를 먼저 기록한 뒤에만 고려한다.
