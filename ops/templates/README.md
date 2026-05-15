# ops/templates/

이 디렉터리는 planning bundle과 improvement run에서 재사용할 **canonical blank template**를 둔다.

원칙:
- template는 `ops/`에 둔다.
- 실제 실행 artifact는 `runs/<run-id>/`에 둔다.
- template는 contract sample이지, live state를 담는 곳이 아니다.

starter bundle:
- `./`
  - generic planning / handoff starter
  - `seed.yaml`
  - `planning-validation.json`
  - `run-ledger.json`
  - `promotion-report.json`
  - `plan.md`
  - `open-questions.md`
- `improvement-observations.json`
  - standalone repo maintenance task follow-up sample
- `mechanism-run/`
  - `system_mechanism` experiment starter
  - `seed.yaml`
  - `planning-validation.json`
  - `run-ledger.json`
  - `promotion-report.json`
  - `improvement-observations.json`
  - `plan.md`
  - `open-questions.md`

권장 사용:
1. 먼저 `make dev-install`로 `.venv` 기반 개발 환경을 만든다.
  - `uv`가 있으면 이 target이 `.venv`를 생성/갱신하고 dependency와 editable install `-e .`를 함께 설치한다.
  - `uv`가 없어도 `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements-dev.txt`, `.venv/bin/python -m pip install -e .` fallback으로 같은 경로를 맞춘다.
2. `runs/<run-id>/` 디렉터리를 만든다.
3. 목적에 맞는 starter bundle을 복사한다.
   - planning / handoff면 `ops/templates/`
   - mechanism experiment면 `ops/templates/mechanism-run/`
   - run과 무관한 standalone maintenance task follow-up만 필요하면 `ops/templates/improvement-observations.json`
   - mechanism experiment를 scaffold부터 promotion/finalization 직전까지 한 번에 묶고 싶다면 `.venv/bin/python -m ops.scripts.run_mechanism_experiment ...` wrapper를 쓸 수 있다.
   - generated proposal을 실제 starter로 얼리고 싶다면 `.venv/bin/python -m ops.scripts.run_mechanism_experiment --vault . --run-id <run-id> --proposal-id <proposal-id> --scaffold-only`로 `proposal-snapshot.json`과 `improvement-observations.json`을 포함한 run-local starter를 먼저 만들 수 있다.
   - standalone observation artifact를 빠르게 만들고 싶다면 `.venv/bin/python -m ops.scripts.improvement_observations --vault . --task-id <task-id>`를 사용한다.
4. run 진행에 따라 내용을 채우고 갱신한다.
5. 사람용 chronology는 `system/system-log.md`, 기계용 상태 전이는 `runs/<run-id>/run-ledger.json`에 남긴다.
6. 구조 점검은 `.venv/bin/python -m ops.scripts.planning_gate_validate --vault . --artifact-dir runs/<run-id>`로 한다.
7. mechanism experiment는 baseline/candidate eval·lnt·mechanism assessment artifact와 changed-files/behavior-delta artifact를 같은 run 디렉터리에 함께 둔다.
8. promotion event는 `runs/<run-id>/promotion-report.json`으로 별도 기록하고, behavior-delta가 있으면 `inputs.behavior_delta`로 연결한다.
9. mechanism experiment에서 reusable automation이나 repo hygiene follow-up이 보이면 `runs/<run-id>/improvement-observations.json`에 먼저 남긴다.
10. mechanism experiment finalization은 `.venv/bin/python -m ops.scripts.finalize_run --vault . --run-id <run-id>`로 닫는 편이 좋다.

메모:
- root starter의 `promotion-report.json`은 generic page / planning 예시로 남긴다.
- root `improvement-observations.json`은 run과 무관한 standalone maintenance task용 canonical sample이다.
- `mechanism-run/promotion-report.json`은 `artifact_class: system_mechanism` 경로를 바로 시작할 수 있는 canonical sample이다.
- `mechanism-run/improvement-observations.json`은 run을 닫을 때 follow-up automation/backlog를 기록하는 schema-backed sample이다.
- `plan.md`와 `open-questions.md`는 schema gate 대상은 아니지만, 첫 run 생성 시 실제로 반복해서 필요했던 decision surface라 starter bundle에 포함한다.
- `run-ledger.json` starter timestamp는 placeholder가 아니라 schema-valid UTC 예시값으로 둔다. 실제 run에서는 append-style event를 추가하며 갱신한다.
