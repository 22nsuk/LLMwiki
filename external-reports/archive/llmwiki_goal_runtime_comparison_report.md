# LLMwiki `goal/5day-auto-improve-runtime` 비교 검토 보고서

작성일: 2026-05-19 KST
대상 압축본: `/mnt/data/LLMwiki(3).zip`
대상 GitHub 브랜치: `22nsuk/LLMwiki`, `goal/5day-auto-improve-runtime`
브랜치 HEAD: `26deafb32ec595929c6394ec5f62e3e470de5c3d`
기준 main/base: `6c3ca7c46c6369ad043d78da5114c84173a14973`
보고서 파일명: `llmwiki_goal_runtime_comparison_report.md`

---

## 1. 결론 요약

압축본은 “브랜치 HEAD의 깨끗한 소스 스냅샷”이 아니라, `.git`까지 포함된 `main` 체크아웃 위에 장기 auto-improve 관련 변경 일부가 얹힌 dirty worktree이다. 압축본 내부의 Git ref에는 `goal/5day-auto-improve-runtime` 브랜치가 존재하고 HEAD SHA도 GitHub 브랜치와 일치하지만, 실제 파일 트리는 브랜치 HEAD와 동일하지 않다.

가장 중요한 차이는 다음 세 가지다.

1. **브랜치 HEAD는 장기 런의 승격 안전성을 크게 강화했다.** run-local hot state, explicit snapshot publish, fixed-point check, transient cleanup, clean fixture regeneration guard, remediation backlog, negative lesson ledger, profile ladder 검증이 추가되었다.
2. **압축본은 브랜치의 최신 안전장치 14개 파일이 빠져 있고, 240개 공통 파일이 브랜치와 다르다.** 특히 `goal_runtime_fixed_point_check`, `goal_runtime_clean_transient`, `clean_fixture_regeneration_guard` 계열이 압축본에 없다. 이는 “장기 런이 성공했다고 주장할 수 있는가”를 판단하는 핵심 anti-slop 장치의 누락이다.
3. **현재 브랜치 자체도 즉시 5일 런을 승격할 상태는 아니다.** clean branch preflight는 통과하지만, checked-in readiness는 `recent_log_overlap` 때문에 runnable proposal이 0개이고 `can_execute_trial=false`, `can_promote_result=false`이다. 이는 실패가 아니라 바람직한 중단 신호다. 장기 자동 개선은 “아무 변경이나 계속 시도”가 아니라 “학습 가능하고 승격 가능한 queue가 있을 때만 진행”해야 한다.

따라서 장기 최적 관점의 권고는 명확하다. **압축본의 local trial/report 상태를 그대로 이어가기보다, GitHub 브랜치 HEAD를 canonical source로 삼고 압축본의 로컬 산출물은 선별 백필 또는 폐기해야 한다.** 특히 브랜치에서 추가된 fixed-point/cleanup/fixture guard 계열을 먼저 도입한 뒤, queue unblock 또는 chronology expiry를 통해 runnable proposal을 회복해야 한다.

---

## 2. 비교 방법 및 전제

### 2.1 압축 해제 방식

초기 단순 unzip은 한글 파일명 일부를 잘못 복원하여 대량 삭제처럼 보이는 오판을 만들었다. 최종 비교는 Python `zipfile.ZipFile(..., metadata_encoding='cp949')`로 다시 풀어 수행했다.

정상 해제 결과:

| 항목 | 값 |
|---|---:|
| zip 내 파일 엔트리 | 6,106 |
| 누락 파일 | 0 |
| 압축 해제 후 비 `.git` 파일 | 2,085 |
| 압축 해제 디렉터리 크기 | 약 440MB |

이 점은 중요하다. 이 저장소는 한글 파일명과 raw/web snapshot이 많기 때문에 파일명 인코딩을 잘못 해석하면 Git status가 왜곡된다. 본 보고서의 결론은 CP949 보정 후 상태를 기준으로 한다.

### 2.2 GitHub 브랜치 확인

GitHub connector로 `22nsuk/LLMwiki` 저장소가 private repo이고 `goal/5day-auto-improve-runtime` 브랜치가 존재함을 확인했다. GitHub compare 기준 브랜치는 `main` 대비 37 commits ahead, 0 behind였다. zip 내부 `.git`의 `origin/goal/5day-auto-improve-runtime` ref도 동일한 HEAD `26deafb32ec595929c6394ec5f62e3e470de5c3d`를 가리켰다.

브랜치의 마지막 커밋 메시지는 다음 요지다.

> Automate goal runtime observation closure. Add fixed-point, transient cleanup, clean fixture regeneration, and usage-limit backoff guards for the goal auto-improve runtime. Refresh generated reports and tests so current observations close with verified evidence.

즉 이 브랜치는 단순 기능 추가 브랜치가 아니라, 장기 goal runtime의 “증거 닫힘”, “관측성”, “반복 실패 학습”, “승격 금지 조건”을 강화하는 브랜치다.

---

## 3. 정량 비교

### 3.1 압축본 worktree 상태

압축본은 현재 `main` 브랜치에 체크아웃되어 있으며 HEAD는 `6c3ca7c46c6369ad043d78da5114c84173a14973`이다. 다만 worktree는 clean하지 않다.

| 상태 | 개수 |
|---|---:|
| modified tracked files | 80 |
| untracked files | 35 |
| deleted files | 0 |
| dirty status entries 총합 | 115 |

압축본의 `tmp/goal-worktree-guard.json` 결과도 이를 확인한다.

| 항목 | 압축본 |
|---|---|
| detected_mode | `git_worktree` |
| branch | `main` |
| head_sha | `6c3ca7c46c6369ad043d78da5114c84173a14973` |
| dirty_entry_count | 115 |
| can_execute_goal_runtime | true |
| can_promote_result | false |
| promotion_blockers | `git_worktree_dirty` |

해석: 압축본은 실행 실험은 가능하지만, 그 결과를 승격 가능한 canonical evidence로 취급하면 안 된다.

### 3.2 GitHub 브랜치 HEAD 상태

로컬 clean checkout으로 재구성한 브랜치 HEAD는 다음 상태였다.

| 항목 | 브랜치 HEAD |
|---|---|
| branch | `goal/5day-auto-improve-runtime` |
| head_sha | `26deafb32ec595929c6394ec5f62e3e470de5c3d` |
| Git status | clean |
| goal worktree guard status | pass |
| can_execute_goal_runtime | true |
| can_promote_result | true, worktree guard 단독 기준 |

단, worktree guard가 clean이어도 auto-improve readiness는 별도 문제다. 브랜치의 checked-in readiness는 runnable queue가 없어서 trial/promotion 모두 막는다.

### 3.3 압축본 파일 트리 vs 브랜치 HEAD 파일 트리

`.git` 제외 후 CP949 보정 압축본과 clean branch checkout을 비교했다.

| 비교 항목 | 개수 |
|---|---:|
| 압축본 비 `.git` 파일 | 2,085 |
| 브랜치 HEAD 파일 | 2,079 |
| 양쪽 동일 파일 | 1,825 |
| 양쪽 공통이나 내용 다른 파일 | 240 |
| 압축본에만 있는 파일 | 20 |
| 브랜치에만 있는 파일 | 14 |

압축본에만 있는 20개 파일의 성격:

| 범주 | 예시 | 판단 |
|---|---|---|
| IDE/local state | `.obsidian/*`, `.vscode/settings.json`, `.serena/*` | canonical source 아님. public/source package에서 제외 권고 |
| 로컬 trial 산출물 | `runs/goal-auto-improve-trial/*`, `ops/reports/auto-improve-sessions/auto-improve-trial.json` | forensic evidence로만 취급. 브랜치의 run-local state 모델과 맞춰 재분류 필요 |
| 외부 보고서 | `external-reports/llmwiki_code_change_implementation_report_20260516.md`, `external-reports/llmwiki_long_run_integrated_improvement_plan_20260519.md` | 참고 보고서로 archive/manifest 편입 여부 판단 필요 |
| 임시/평가 파일 | `.ouroboros/*`, `.ouroboros_eval_artifact.md` | canonical source 아님 |
| prompt/report artifact | `ops/reports/codex-goal-prompt.json` | 브랜치에서는 prompt snapshot 정책이 달라짐. 추적 여부 재판정 필요 |

브랜치에만 있는 14개 파일:

```text
ops/reports/task-improvement-observations/task-20260518-goal-runtime-reconciliation/improvement-observations.json
ops/schemas/clean-fixture-regeneration-guard.schema.json
ops/schemas/goal-resume-metadata.schema.json
ops/schemas/goal-runtime-clean-transient.schema.json
ops/schemas/goal-runtime-fixed-point-check.schema.json
ops/scripts/mechanism/current_target_path_runtime.py
ops/scripts/mechanism/goal_runtime_clean_transient.py
ops/scripts/mechanism/goal_runtime_fixed_point_check.py
ops/scripts/public/clean_fixture_regeneration_guard.py
tests/test_clean_fixture_regeneration_guard.py
tests/test_goal_auto_improve_runtime.py
tests/test_goal_runtime_clean_transient.py
tests/test_goal_runtime_fixed_point_check.py
tests/workflow_static_helpers.py
```

이 14개는 단순 누락이 아니다. 장기 런의 anti-slop 폐쇄성을 보장하는 최신 안전장치와 그 테스트다. 압축본을 장기 런 출발점으로 쓰려면 이 누락부터 해소해야 한다.

---

## 4. 브랜치의 핵심 개선 내용

### 4.1 run-local hot state와 tracked snapshot 분리

압축본의 goal runtime은 상당 부분 이미 장기 런 구조를 포함하지만, 브랜치 HEAD는 hot state와 tracked canonical snapshot을 더 명확히 분리한다.

브랜치의 핵심 정책:

- active 상태는 기본적으로 `runs/goal-$(GOAL_RUN_ID)/state/` 아래에 쓴다.
- `ops/reports/goal-run-status.json`은 active hot state가 아니라 명시 publish 뒤의 tracked snapshot이다.
- heartbeat/status/resume 갱신이 tracked `ops/reports/`를 계속 dirty하게 만들지 않도록 한다.
- `goal-runtime-publish-snapshot`이 run-local contract/status를 tracked snapshot으로 승격한다.
- run-local evidence는 `goal-run-status.json`, `status.md`, `audit-log.jsonl`, `resume-metadata.json`, `checkpoint-command-events.jsonl`로 나뉜다.

장기 최적 관점에서 이 변화는 매우 중요하다. 5일 런에서 매 heartbeat마다 tracked report가 바뀌면 Git worktree가 상시 dirty 상태가 되고, dirty worktree guard와 promotion guard가 충돌한다. 브랜치는 이 문제를 run-local state로 분리해 해결한다.

### 4.2 fixed-point check 추가

브랜치에 새로 추가된 `ops/scripts/mechanism/goal_runtime_fixed_point_check.py`는 다음 5개 보고서의 의미적 정합성을 확인한다.

- `ops/reports/codex-goal-contract.json`
- `ops/reports/goal-run-status.json`
- `ops/reports/auto-improve-readiness.json`
- `ops/reports/session-synopsis.json`
- `ops/reports/remediation-backlog.json`

검사하는 핵심 불변식은 다음과 같다.

- goal contract와 goal-run-status의 `contract_id` 일치
- contract runtime profile과 status run profile 일치
- promotion blockers의 contract/status 동기화
- session synopsis의 active goal과 current status의 run id/profile/status 일치
- readiness promotion blockers, session blockers, remediation backlog active blockers의 정합성

실행 결과, clean branch에서 fixed-point check는 통과했다.

| 검사 | 결과 |
|---|---:|
| report_count | 5 |
| check_count | 16 |
| failed_check_count | 0 |
| status | pass |

압축본에는 이 check 자체가 없다. 이 누락은 장기 런이 “각 artifact는 존재하지만 서로 다른 사실을 말하는” 전형적 slop 상태로 빠질 위험을 키운다.

### 4.3 transient cleanup 추가

브랜치의 `goal_runtime_clean_transient.py`는 장기 런의 오래된 흔적을 제거하되, active run state는 보호한다.

제거 후보:

- legacy tracked goal markdown/status/resume/audit surface
- stale legacy runtime event logs
- stale `tmp/source-package-*` extraction tree
- current status가 참조하지 않는 stale `runs/goal-*` tree
- completed run의 transient stdout copy

보호 대상:

- `ops/reports/codex-goal-contract.json`
- `ops/reports/codex-goal-prompt.json`
- `ops/reports/goal-run-status.json`
- `ops/reports/goal-profile-verification.json`
- current status가 참조하는 `runs/goal-<id>` tree와 그 state files

clean branch에서 report-only cleanup은 제거 후보 0개, status pass였다. 압축본에는 이 기능이 없고, 실제로 local-only trial 파일이 남아 있다. 따라서 압축본은 장기 런 재개 전 cleanup/reconcile이 필요하다.

### 4.4 clean fixture regeneration guard 추가

브랜치에 추가된 `clean_fixture_regeneration_guard.py`는 `ops/reports/`가 dirty인 live report 상태에서 public fixture나 script output surface를 커밋용으로 재생성하지 못하게 막는다.

clean branch에서는 pass였다.

| 항목 | 값 |
|---|---:|
| dirty_ops_report_count | 0 |
| dirty_public_surface_count | 0 |
| status | pass |

반대로 `make auto-improve-readiness`를 실행해 report들이 dirty해진 상태에서는 guard가 fail했다. 이 동작은 의도적으로 바람직하다. live report 상태를 fixture truth로 오인하는 것을 막기 때문이다.

### 4.5 remediation backlog와 negative lessons

브랜치는 반복 실패를 단순 로그가 아니라 durable blocker로 승격한다.

- `ops/reports/self-improvement-negative-lessons.json`: 반복되는 실패 패턴, 금지 반복 패턴을 독립 ledger로 보존
- `ops/reports/remediation-backlog.json`: 반복 negative lesson과 active blocker를 backlog item으로 승격
- `ops/policies/remediation-backlog-status-overrides.json`: evidence가 있는 항목만 closed/deferred 처리
- auto-improve session runtime은 open `blocks_repeat` backlog item을 실행 전 stop 조건으로 읽음

장기 최적 관점에서 이는 “실패했지만 또 같은 프롬프트로 시도하는” slop loop를 막는 핵심 장치다.

### 4.6 proposal budget 후 maintenance loop

브랜치는 proposal budget이 소진된 뒤 단순 heartbeat padding으로 시간을 채우지 않는다. `GOAL_MAINTAIN_UNTIL_BUDGET=1`이면 남은 wall-clock budget 동안 다음을 반복 갱신한다.

- mechanism review
- mutation proposal
- readiness
- session report

즉 30분/6시간/2일/5일 profile은 “프로세스가 오래 살아 있었다”가 아니라 “주기적으로 의미 있는 maintenance evidence를 남겼다”로 검증된다.

---

## 5. anti-slop 관점 평가

이 저장소에서 slop은 단순히 문장이 장황한 문제가 아니다. 다음 상태들이 slop이다.

- 파일은 있지만 현재 source와 생성 command가 맞지 않는 상태
- artifact끼리 서로 다른 blocker/run/profile을 말하는 상태
- dirty ZIP/local worktree에서 나온 결과를 promotable evidence로 오인하는 상태
- `DISCARD` 또는 blocked outcome을 successful improvement처럼 취급하는 상태
- 5일 sustained claim을 elapsed wall-clock만으로 주장하는 상태
- fake backend 또는 stale report로 learning claim을 닫는 상태
- report regeneration이 fixture truth를 오염시키는 상태

브랜치는 이 중 상당수를 구조적으로 방어한다.

| slop 위험 | 브랜치의 방어 | 압축본 상태 |
|---|---|---|
| dirty worktree 결과 승격 | `goal_worktree_guard`, `can_promote_result=false` | 동작함. 압축본은 dirty라 promotion 차단됨 |
| artifact 간 의미 불일치 | `goal_runtime_fixed_point_check` | 누락 |
| stale transient 누적 | `goal_runtime_clean_transient` | 누락. local trial artifacts 존재 |
| fixture 오염 | `clean_fixture_regeneration_guard` | 누락 |
| 반복 실패 재시도 | negative lessons + remediation backlog | 일부 파일은 있으나 브랜치 최신 정합성과 다름 |
| heartbeat padding | maintenance cycle evidence 요구 | 압축본 README/Make target은 브랜치보다 구버전 |
| 5일 claim 남발 | profile ladder + verification apply gate | 일부 포함, 최신 branch 강화분 누락 |

판정: **브랜치 HEAD는 anti-slop 방향이 맞고, 압축본은 그 중간 상태다.** 압축본을 그대로 사용하면 “있는 것처럼 보이는 안전장치”와 “실제 최신 브랜치의 안전장치”가 섞여 오판 가능성이 크다.

---

## 6. 자가 개선 구조 평가

### 6.1 현재 자가 개선 pipeline의 강점

브랜치가 갖춘 강점은 다음과 같다.

1. **bounded scope**: auto-improve 대상이 `ops/**`, `tests/**`, run artifact, append-only `system/system-log.md`로 제한된다.
2. **proposal queue pressure 가시화**: `mutation-proposals.json`이 runnable/blocked proposal을 분리하고 blocked reason count를 남긴다.
3. **learning readiness와 execution readiness 분리**: 실행 가능하더라도 학습 가능성이 낮으면 promotion을 막을 수 있다.
4. **profile ladder**: 30m trial → 6h ramp → 2d candidate → 5d sustained로 증거 요구 수준이 상승한다.
5. **operator-facing snapshot**: live state와 checked-in canonical snapshot을 분리해 장기 run의 Git 오염을 줄인다.
6. **remediation backlog**: 같은 실패를 반복하지 않도록 실행 전 blocker로 승격한다.

### 6.2 현재 브랜치의 즉시 실행 상태

브랜치의 checked-in readiness는 다음 상태다.

| 항목 | 값 |
|---|---|
| `can_execute_trial` | false |
| `can_promote_result` | false |
| runnable proposal count | 0 |
| blocked proposal count | 2 |
| blocked reason | `recent_log_overlap` |
| next action | proposal queue blocker 해소 후 readiness 재실행 |

이 상태에서 장기 런을 강제로 시작하면 좋은 자동 개선이 아니라 chronology guard를 우회한 noisy run이 된다. 장기 최적 관점에서는 “멈춤”이 맞다.

### 6.3 압축본 readiness와 브랜치 readiness의 의미 차이

압축본의 `auto-improve-readiness.json`은 `can_execute_trial=true`, `can_promote_result=false`에 가까운 구상태를 담고 있다. 반면 브랜치 HEAD는 runnable proposal이 없어 `can_execute_trial=false`다.

이 차이는 단순 report timestamp 차이가 아니라 정책 차이다. 브랜치는 최근 chronology overlap이 있는 proposal을 queue에서 제외하고, runnable queue가 0이면 trial도 보류한다. 압축본은 이 강화된 queue gating/fixed-point closure를 아직 완전히 반영하지 않는다.

---

## 7. 테스트 및 검증 결과

### 7.1 의존성 설치 시도

프로젝트 선언 환경:

- Python: `>=3.12`
- runtime deps: `PyYAML>=6.0,<7`, `jsonschema>=4.23,<5`
- dev deps: `pytest>=8.3,<9`, `pytest-xdist>=3.6,<4`, `ruff>=0.15,<1`, `mypy>=1.20,<2`, `types-PyYAML>=6.0,<7`

실행 환경:

- Python 3.11.8
- pytest 8.2.2
- PyYAML 6.0.3
- jsonschema 4.26.0
- ruff 없음
- mypy 없음

가상환경 생성 후 `requirements-dev.txt` 설치를 시도했지만, container의 DNS/network 제한으로 PyPI 접근이 실패했다.

대표 로그:

```text
Temporary failure in name resolution
ERROR: Could not find a version that satisfies the requirement PyYAML<7,>=6.0
ERROR: No matching distribution found for PyYAML<7,>=6.0
```

따라서 ruff/mypy/full declared Python 3.12 lane은 이 환경에서 완료하지 못했다. 대신 현재 사용 가능한 system Python/pytest로 goal runtime 관련 targeted tests를 실행했다.

### 7.2 테스트 import 격리 문제

처음 targeted pytest를 실행할 때 `tests.minimal_vault_runtime` import가 실패했다. 원인은 외부 site-packages의 `tests` package가 repository의 `tests/` namespace를 가린 것이다. 임시로 `tests/__init__.py`를 생성해 local tests package를 우선시키자 테스트가 진행됐다.

이는 CI가 깨진다는 뜻은 아니지만, hermetic하지 않은 실행 환경에서는 재현성을 해칠 수 있다. 장기 최적 관점에서는 다음 중 하나를 권고한다.

- `tests/__init__.py`를 정식 추가한다.
- pytest import mode와 pythonpath를 명시한다.
- 모든 long-run validation은 project `.venv`/Python 3.12에서만 실행하도록 강제한다.

### 7.3 브랜치 HEAD targeted test 결과

clean branch checkout 기준 주요 goal runtime 테스트 결과:

| 테스트 파일 | 결과 |
|---|---:|
| `tests/test_auto_improve_readiness_release_authority_runtime.py` | 2 passed |
| `tests/test_clean_fixture_regeneration_guard.py` | 4 passed |
| `tests/test_codex_goal_client.py` | 14 passed |
| `tests/test_codex_goal_contract.py` | 6 passed |
| `tests/test_codex_goal_prompt.py` | 2 passed |
| `tests/test_command_runtime_heartbeat.py` | 2 passed |
| `tests/test_goal_auto_improve_runtime.py` | 2 passed |
| `tests/test_goal_run_status.py` | 12 passed |
| `tests/test_goal_runtime_clean_transient.py` | 4 passed |
| `tests/test_goal_runtime_fixed_point_check.py` | 4 passed |
| `tests/test_goal_runtime_runner.py` | 4 passed |
| `tests/test_goal_worktree_guard.py` | 5 passed |

추가 관찰:

- `tests/test_goal_profile_verification.py`는 파일 전체 실행에서 9개 테스트 통과 후 마지막 테스트에서 장시간 정지했다.
- 동일 마지막 테스트 `test_higher_profile_requires_repeated_time_budget_session`은 단독 실행 시 21.03초에 pass했다.

판정: 기능 자체가 깨졌다고 단정할 수는 없지만, profile verification 테스트에는 order-dependent performance/isolation 문제가 있다. 5일 런 검증을 담당하는 영역이므로 P1로 개선해야 한다.

### 7.4 압축본 available goal tests 결과

압축본에는 브랜치 최신 테스트 5개가 빠져 있으므로 동일 test matrix를 실행할 수 없다. 존재하는 테스트만 실행했다.

| 테스트 파일 | 결과 |
|---|---:|
| `tests/test_auto_improve_readiness_release_authority_runtime.py` | 2 passed |
| `tests/test_codex_goal_client.py` | 13 passed |
| `tests/test_codex_goal_contract.py` | 6 passed |
| `tests/test_codex_goal_prompt.py` | 2 passed |
| `tests/test_command_runtime_heartbeat.py` | 2 passed |
| `tests/test_goal_profile_verification.py` | 7 passed |
| `tests/test_goal_run_status.py` | 11 passed |
| `tests/test_goal_runtime_runner.py` | 3 passed |
| `tests/test_goal_worktree_guard.py` | 5 passed |

압축본의 테스트 통과는 “압축본이 브랜치와 동등하다”는 뜻이 아니다. 브랜치의 가장 중요한 신규 guard 테스트들이 아예 존재하지 않기 때문이다.

---

## 8. 주요 리스크 레지스터

### P0-1. 압축본을 canonical branch로 오인할 위험

- 증거: 압축본은 `main` HEAD 위 dirty worktree이며, branch HEAD와 240개 공통 파일이 다르고 14개 branch-only 파일이 없다.
- 영향: 장기 런 결과를 승격 가능한 evidence로 오판할 수 있다.
- 조치: GitHub branch HEAD를 canonical source로 삼고, 압축본 local artifacts는 별도 forensic input으로 분리한다.
- acceptance: `git status --porcelain` clean, branch HEAD `26deafb...`, `goal_worktree_guard.status=pass`, `can_promote_result=true`가 worktree guard 수준에서 성립.

### P0-2. fixed-point/cleanup/fixture guard 누락

- 증거: 압축본에는 `goal_runtime_fixed_point_check.py`, `goal_runtime_clean_transient.py`, `clean_fixture_regeneration_guard.py` 및 schema/tests가 없다.
- 영향: artifact 간 semantic drift, stale transient, public fixture 오염이 재발 가능하다.
- 조치: branch-only 14개 파일을 반드시 반영하거나 압축본 기반 작업을 폐기한다.
- acceptance: `goal-runtime-fixed-point-check`, `goal-runtime-clean-transient`, `clean-fixture-regeneration-guard`가 모두 pass.

### P0-3. runnable proposal queue 없음

- 증거: 브랜치 readiness는 `runnable_proposal_count=0`, `blocked_reason=recent_log_overlap`, `can_execute_trial=false`.
- 영향: 5일 런을 강행하면 chronology guard를 우회한 noisy run이 된다.
- 조치: recent log overlap window가 자연 만료되도록 기다리거나, branch가 의도한 queue-unblock target을 별도 수동 bounded run으로 닫는다.
- acceptance: `make auto-improve-readiness` 후 `execution_readiness.can_run=true`, `queue.runnable_proposal_count>=1`.

### P0-4. declared environment 미충족

- 증거: 프로젝트는 Python `>=3.12`와 ruff/mypy dev deps를 요구하지만 현재 환경은 Python 3.11.8이고 network 제한으로 deps 설치가 실패했다.
- 영향: full CI equivalence를 주장할 수 없다.
- 조치: Python 3.12 hermetic venv 또는 CI runner에서 `make check-serial`, `make public-check-serial`, targeted goal tests 재실행.
- acceptance: ruff/mypy/source-package/report-contract lanes 모두 pass.

### P1-1. tests namespace shadowing

- 증거: 외부 `site-packages/tests`가 repo `tests/`를 가려 import failure 발생.
- 영향: non-hermetic operator machine에서 validation이 흔들린다.
- 조치: `tests/__init__.py` 추가 또는 pytest config/import mode 명시.
- acceptance: 임시 shim 없이 targeted pytest가 pass.

### P1-2. profile verification order-dependent/performance 문제

- 증거: `test_goal_profile_verification.py` 전체 실행은 마지막 test에서 장시간 정지했지만, 해당 test 단독 실행은 21.03초 pass.
- 영향: 5일 ladder 검증 lane이 flaky/slow해질 수 있다.
- 조치: 6h ramp fixture를 72회 status write 대신 compact audit fixture로 줄이고, fixture cleanup과 deterministic clock 상태를 test마다 reset한다.
- acceptance: profile verification 전체 파일이 30초 이하로 pass, `--durations`에서 장기 단일 테스트 없음.

### P1-3. generated report churn

- 증거: `make auto-improve-readiness`는 여러 `ops/reports/*`를 갱신한다. 이후 clean fixture guard가 fail하여 dirty report state를 정확히 감지했다.
- 영향: operator가 live report 상태를 commit fixture로 착각할 수 있다.
- 조치: run-local hot state 원칙을 더 확장하고, commit-intent regeneration과 live-observation regeneration target을 명확히 분리한다.
- acceptance: 장기 런 중 tracked report dirty count가 bounded이고, snapshot publish 외에는 canonical reports가 바뀌지 않음.

---

## 9. 장기 최적화 로드맵

### 9.1 0~48시간: 안전한 기준점 복구

1. **브랜치 HEAD를 canonical checkout으로 고정**
   - `goal/5day-auto-improve-runtime` clean checkout에서 시작한다.
   - 압축본의 dirty main 상태를 승격 근거로 사용하지 않는다.

2. **압축본 local-only 파일 분류**
   - `.obsidian`, `.vscode`, `.serena`, `.ouroboros`는 source package에서 제외한다.
   - `runs/goal-auto-improve-trial/*`는 forensic archive로 옮기거나 branch run-local schema에 맞춰 backfill한다.
   - `external-reports/*20260516/20260519*`는 reference manifest에 편입할지 별도 결정한다.

3. **branch-only 14개 파일 반영 확인**
   - 특히 fixed-point, transient cleanup, fixture guard 세트를 누락 없이 유지한다.

4. **preflight matrix**
   - `make auto-improve-goal-preflight`
   - `make goal-runtime-clean-transient`
   - `make goal-runtime-fixed-point-check`
   - `make clean-fixture-regeneration-guard`
   - `make auto-improve-readiness`

5. **runnable queue 회복 전 장기 런 금지**
   - `recent_log_overlap` blocker가 있는 동안 `auto-improve-goal-run`을 시작하지 않는다.

### 9.2 1~2주: 장기 런 검증 비용 절감

1. **profile verification 테스트 최적화**
   - 6h/2d/5d elapsed simulation을 compact evidence fixture로 대체한다.
   - audit cadence 테스트는 property-style synthetic timestamps로 검증한다.

2. **status writer와 profile verifier의 public contract 명확화**
   - “파일 존재”가 아니라 “producer, run_id, profile, observed_at, command heartbeat, checkpoint event”의 교차검증을 contract로 문서화한다.

3. **queue unblock을 별도 mechanism family로 관리**
   - `recent_log_overlap`가 모든 proposal을 막을 때 fallback proposal이 chronology guard를 약화하지 않도록 target rotation만 허용한다.

4. **report churn budget 도입**
   - long-run 중 tracked report dirty count가 일정 기준을 넘으면 자동으로 snapshot publish를 보류한다.

### 9.3 1~2개월: 5일 sustained run 운영화

1. **5d sustained profile의 최소 증거 정의를 더 엄격히 분리**
   - elapsed time
   - maintenance cycle count
   - successful improvement count
   - post-success follow-up count
   - backoff/resume event coverage
   - fixed-point pass history
   - clean transient pass history
   - no-open-remediation-backlog proof

2. **content-addressed evidence snapshot**
   - canonical report의 `generated_at` churn보다 source/input digest 중심으로 currentness를 판단한다.

3. **operator dashboard 최소화**
   - 장기 런 중 사람이 볼 핵심만 `status.md`에 남긴다.
   - 상세 evidence는 JSONL/audit bundle로 둔다.

4. **slop-resistant success taxonomy**
   - `PROMOTE`, `HOLD`, `DISCARD`, `BLOCKED`, `USAGE_LIMITED`, `NO_RUNNABLE_QUEUE`, `REMEDIATION_REQUIRED`를 같은 success/failure 축에 섞지 않는다.
   - 특히 `DISCARD`는 improvement가 아니라 blocking outcome이라는 브랜치 정책을 유지한다.

---

## 10. 구체적 실행 권고

### 10.1 압축본 처리 방침

압축본은 “원본 저장소를 그대로 압축한 현장 스냅샷”으로서 가치는 있다. 그러나 source of truth로 쓰면 안 된다.

권장 처리:

1. 압축본은 `forensic/original-zip-20260519` 같은 read-only archive로 보관한다.
2. source 작업은 clean GitHub branch checkout에서 수행한다.
3. 압축본에만 있는 local artifacts는 다음 기준으로 분류한다.
   - 재현 가능한 run evidence: branch schema에 맞춰 archive/backfill
   - operator note/report: `external-reports/archive` 및 manifest 편입 검토
   - IDE/local config: ignore/exclude
   - stale transient: cleanup 대상

### 10.2 merge/reconcile 순서

권장 순서:

1. clean branch checkout 확보
2. branch-only safety files 존재 확인
3. 압축본 local-only 파일 중 source로 편입할 항목만 patch로 선별
4. `goal-runtime-clean-transient` report-only 실행
5. `goal-runtime-fixed-point-check` 실행
6. `clean-fixture-regeneration-guard` 실행
7. `auto-improve-readiness` 실행
8. runnable queue가 없으면 run 보류
9. runnable queue가 있으면 30m trial부터 재시작
10. 30m trial pass 후에만 `GOAL_PROFILE_VERIFICATION_APPLY=1` 검토

### 10.3 절대 피해야 할 패턴

- dirty 압축본에서 바로 5일 run 시작
- `can_execute_trial=true`인 오래된 readiness만 보고 run 시작
- `can_promote_result=false`를 “나중에 사람이 보면 됨”으로 무시
- `DISCARD`를 successful improvement로 계산
- generated report를 갱신한 직후 fixture도 같이 재생성
- runtime event log가 있다고 profile verification을 통과 처리
- fake backend/silent backend를 sustained claim에 사용

---

## 11. 최종 판정

브랜치 `goal/5day-auto-improve-runtime`은 방향이 좋다. 특히 다음 개선은 장기 자동 개선 시스템에서 필수에 가깝다.

- run-local hot state와 tracked snapshot 분리
- fixed-point semantic alignment check
- transient cleanup
- clean fixture regeneration guard
- remediation backlog
- negative lessons
- usage-limit backoff
- profile ladder verification
- queue runnable/blocked 분리

반면 압축본은 이 브랜치의 중간 산물과 local trial 상태가 섞인 dirty snapshot이다. 압축본은 분석 자료로는 유용하지만, 장기 auto-improve runtime의 기준 상태로 쓰기에는 부적합하다.

**최종 권고:** GitHub branch HEAD를 기준으로 clean checkout을 만들고, 압축본은 forensic archive로 보존한다. 그 후 runnable proposal queue를 회복하기 전까지 장기 auto-improve run은 보류한다. 5일 sustained claim은 `goal-runtime-fixed-point-check`, `goal-runtime-clean-transient`, `clean-fixture-regeneration-guard`, `goal-profile-verification`, `auto-improve-readiness`가 모두 같은 run/profile/blocker 상태를 가리킬 때만 허용해야 한다.

---

## 부록 A. 재현 명령 요약

```bash
# CP949 보정 압축 해제
python - <<'PY'
from pathlib import Path
import zipfile
zip_path = Path('/mnt/data/LLMwiki(3).zip')
out = Path('/mnt/data/llmwiki_zip_repo_cp949')
out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path, metadata_encoding='cp949') as z:
    z.extractall(out)
PY

# 압축본 상태 확인
cd /mnt/data/llmwiki_zip_repo_cp949
git status --porcelain=v1 | cut -c1-2 | sort | uniq -c
git rev-parse HEAD
git rev-parse origin/goal/5day-auto-improve-runtime

# clean branch checkout
GIT_CONFIG_GLOBAL=/dev/null git clone --no-hardlinks /mnt/data/llmwiki_zip_repo_cp949 /mnt/data/llmwiki_goal_git_repo
cd /mnt/data/llmwiki_goal_git_repo
git checkout goal/5day-auto-improve-runtime

# goal preflight
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 make auto-improve-goal-preflight

# branch fixed-point / cleanup / fixture guard
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m ops.scripts.goal_runtime_fixed_point_check --vault . --out tmp/goal-runtime-fixed-point-check-review.json
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m ops.scripts.goal_runtime_clean_transient --vault . --out tmp/goal-runtime-clean-transient-review.json
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m ops.scripts.clean_fixture_regeneration_guard --vault . --out tmp/clean-fixture-regeneration-guard-clean-review.json
```

## 부록 B. 검증 한계

- 현재 실행 환경은 Python 3.11.8이고 프로젝트 선언은 Python `>=3.12`이다.
- container DNS/network 제한으로 `requirements-dev.txt` 설치가 실패했다.
- ruff/mypy/full CI lane은 이 환경에서 완료하지 못했다.
- pytest는 system pytest 8.2.2로 targeted goal tests만 수행했다.
- `tests/__init__.py` 임시 shim을 사용해 외부 `site-packages/tests` shadowing을 회피했다.
- 이 한계 때문에 본 보고서는 “브랜치 구조와 targeted runtime 검증 기반의 정밀 리뷰”이지, “전체 CI green 인증서”가 아니다.
