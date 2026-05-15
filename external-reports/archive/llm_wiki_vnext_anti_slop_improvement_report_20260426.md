# LLM Wiki vNext Anti-Slop Improvement Report

- 작성일: 2026-04-26
- 작성 언어: 한국어
- 출력 파일명: `llm_wiki_vnext_anti_slop_improvement_report.md`
- 검토 대상 ZIP: `LLM Wiki vNext(42).zip`
- 실제 검토 기준 SHA-256: `6f2c8f491b759bdc413455a020d770979deb0566bfc6d8444f72129ba709f0f6`
- 대조한 기존 리뷰: `unified_current_audit_improvement_report(1).md`
- 정밀 검토한 세 리뷰:
  1. `llm_wiki_vnext_integrated_review_report.md`
  2. `llm_wiki_vnext_post_review_unified_report.md`
  3. `integrated_post_review_audit_report.md.md`

---

## 1. 목적과 판단 원칙

이번 문서는 세 리뷰의 좋은 문장을 최대한 많이 합치는 문서가 아니다. 반대로 다음 원칙으로 재판정한 문서다.

1. **세 리뷰가 공통으로 주장한 내용이라도 실제 ZIP과 현재 산출물로 다시 확인되지 않으면 우선순위를 낮춘다.**
2. **좋아 보이는 개선안이라도 현재 병목을 직접 줄이지 않으면 후순위로 내린다.**
3. **정책, 진단, 보고서 표면이 좋아진 것과 실제 운영 루프가 복구된 것을 구분한다.**

이 문서의 핵심 질문은 하나다.

> 지금 시점에서 무엇을 먼저 고쳐야 auto-improve queue가 다시 열리는가?

---

## 2. 검토 대상과 동일성 판정

### 2.1 세 리뷰와 실제 ZIP은 같은 체크포인트를 본다

세 리뷰는 파일명 표기가 조금씩 다르지만 모두 동일 SHA-256의 같은 아카이브를 대상으로 삼는다.

| 항목 | 값 |
|---|---:|
| ZIP 파일명 | `LLM Wiki vNext(42).zip` |
| ZIP 크기 | 273,066,366 bytes |
| ZIP SHA-256 | `6f2c8f491b759bdc413455a020d770979deb0566bfc6d8444f72129ba709f0f6` |
| ZIP entry 수 | 11,552 |

### 2.2 기존 리뷰는 다른 세대 아카이브 기준선이다

기존 리뷰 `unified_current_audit_improvement_report(1).md`는 v39 계열 아카이브 기준이다. 즉 직접 비교 대상이라기보다 **이전 우선순위 기준선**으로 써야 한다.

이 구분은 중요하다. 이유는 다음과 같다.

- v39 기준에서 P0였던 항목 중 일부는 이미 해결되었다.
- 따라서 기존 리뷰의 우선순위를 그대로 재사용하면 과잉 수정과 우선순위 왜곡이 생긴다.

---

## 3. 실제 파일 기준 재검증 결과

아래 항목은 세 리뷰의 주장과 별개로, 현재 해제본 `llm_wiki_vnext_42`에서 직접 다시 확인한 결과다.

### 3.1 정적 위생은 양호하다

직접 실행 결과:

| 검증 | 결과 |
|---|---|
| 비-venv Python `py_compile` | 276개 오류 0 |
| 비-venv JSON parse | 215개 오류 0 |
| `python3 -m ruff check ops/scripts tests tools` | 통과 |
| `python3 tools/ruff_strict_preview.py` | 통과 |
| `python3 -m mypy @ops/mypy-allowlist.txt` | 통과 (`154 source files`) |
| strict-preview mypy | 통과 (`10 source files`) |

따라서 현재 코드는 “문법/타입/기본 lint가 무너진 저장소”가 아니다. 이 점은 세 리뷰의 공통 결론과도 맞는다.

### 3.2 운영 루프 병목은 현재도 그대로 재현된다

직접 재실행 결과:

| 명령 | 결과 |
|---|---|
| `python3 -m ops.scripts.mechanism_review --vault .` | exit 0 |
| `python3 -m ops.scripts.mutation_proposal --vault .` | exit 0 |
| `python3 -m ops.scripts.auto_improve_readiness --vault . --out ...` | exit 1 |

재생성 후 핵심 상태:

| 산출물 | 핵심 수치 |
|---|---|
| `mechanism-review-candidates.json` | `runs_discovered=7`, `runs_considered=2`, `runs_skipped=5`, `candidates_emitted=0` |
| `mutation-proposals.json` | `source_candidates_read=0`, `proposals_emitted=0`, `blocked_proposals=0` |
| `auto-improve-readiness.json` | `can_run=false`, `runnable_proposal_count=0` |

즉, **세 리뷰의 핵심 진단은 현재 해제본에서도 그대로 재현된다.**

### 3.3 release-smoke 완주성은 아직 확인되지 않았고 partial report 보장도 불충분하다

`release_smoke`를 별도로 제한 시간과 함께 실행했을 때 완료되지 않았고, 즉시 활용 가능한 partial report도 확인되지 않았다. 이 항목은 세 리뷰가 “미완료”로 남긴 한계를 실제로 다시 드러낸다.

따라서 다음 문장은 현재 시점에서도 유지된다.

> release-smoke는 계약과 테스트는 추가됐지만, 장시간 실행 실패 시 운영자가 바로 읽을 수 있는 부분 보고서를 안정적으로 남기는 수준까지는 확인되지 않았다.

### 3.4 ZIP portability는 실제 환경 의존 리스크이지 보편 실패는 아니다

직접 구조 분석 결과:

| 항목 | 값 |
|---|---:|
| 비ASCII 파일명 entry | 340 |
| bit 11(UTF-8 flag) 사용 | 2 |
| Unicode Path extra field(`0x7075`) 사용 | 340 |
| 최대 UTF-8 component 길이 | 173 bytes |
| 최대 UTF-8 path 길이 | 191 bytes |
| 최대 POSIX escape-expanded component | 317 bytes |
| 최대 POSIX escape-expanded path | 335 bytes |
| 255 bytes 초과 component offender | 6개 |

상위 offender는 모두 `raw/web-snapshots/` 아래 긴 한국어 제목 파일이다.

이 항목은 다음처럼 읽어야 정확하다.

- Python `zipfile`/일반 UTF-8 경로에서는 큰 문제가 드러나지 않는다.
- 그러나 POSIX `C` locale 계열 unzip 경로에서는 filename escape expansion 때문에 해제 실패 가능성이 높다.
- 따라서 이는 **보편적 무결성 결함**이라기보다 **release portability defect**다.

기존 리뷰보다 이 분류가 더 정확하다.

## 4. 기존 리뷰 대비 현재 판정

기존 리뷰의 주요 권고를 현재 시점에서 다시 판정하면 다음과 같다.

| 기존 권고 | 현재 판정 | 이유 |
|---|---|---|
| strict preview I001 수정 | 완료 | 실제 strict-preview ruff 통과 |
| local schema validation error 제거 | 부분 완료 | OpenVEX 1건은 해소됐지만 invalid debt가 남음 |
| 핵심 run artifact `$schema` backfill | 미완료 | skipped run 5개가 여전히 핵심 병목 |
| no-candidate blocker 기록 | 완료 | `candidate_blockers` 존재 |
| mutation proposal empty-state 제거 | 미완료에 가까운 부분 완료 | 진단은 생겼지만 summary는 아직 `0/0` |
| artifact freshness work queue화 | 완료 | `top_debt`, `owner_surface`, `recommended_next_action` 존재 |
| canonical report truthfulness writer | 부분 완료 | 일부 강화 흔적은 있으나 전체 rollout 불충분 |
| ZIP portability gate | 부분 완료 | 코드/테스트 계약은 생겼지만 현재 artifact는 여전히 C locale risk 보유 |
| fast-smoke target | 진전 확인 | 타깃과 테스트 강화 흔적은 있으나 wall-clock 완주를 새로 확인하지 못함 |
| proposal lifecycle ledger | 미완료 | queue가 비어 있어 실효성 이전에 구조 자체도 미완성 |

핵심은 이것이다.

> 기존 리뷰의 즉시 항목 중 “관측 가능성 개선”은 상당수 반영됐지만, “실행 가능한 다음 action 생성”은 아직 반영되지 않았다.

---

## 5. 세 리뷰에서 수용할 것과 낮출 것을 구분한 최종 판단

### 5.1 그대로 수용해야 하는 핵심 판단

#### A. auto-improve loop는 아직 복구되지 않았다

이건 세 리뷰와 실제 재실행 결과가 모두 일치한다.

병목 사슬:

legacy run artifact schema debt
  ↓
runs_skipped=5
  ↓
candidates_emitted=0
  ↓
source_candidates_read=0
  ↓
proposals_emitted=0
  ↓
can_run=false

#### B. 진단 계층은 분명히 좋아졌다

현재는 최소한 다음이 가능하다.

- candidate가 왜 0인지 기계적으로 읽을 수 있다.
- mutation queue가 왜 비었는지 설명할 수 있다.
- freshness debt가 어느 surface에 몰려 있는지 볼 수 있다.

이 변화는 중요하지만, **운영 복구와 동일시하면 안 된다.**

#### C. release artifact hygiene와 portability는 실제 리스크다

이건 cosmetic issue가 아니다. 현재 아카이브는 배포 artifact와 개발 snapshot이 섞여 있고, 일부 환경에서는 unzip 자체가 깨질 가능성이 있다.

### 5.2 좋은 제안이지만 지금은 낮춰야 하는 항목

#### A. 대규모 runtime 분해

`auto_improve_readiness_runtime.py` 분해, `mutation_proposal_runtime.py` 분해는 장기적으로 맞다. 하지만 지금 queue가 비어 있는 핵심 원인은 복잡도 자체보다 **schema debt와 candidate seed 부재**다. 지금 당장 1순위는 아니다.

#### B. proposal lifecycle ledger

`improvement_id`, `source_run_id`, `negative_memory_key`는 좋은 방향이다. 하지만 proposal이 0건인 상황에서 ledger를 먼저 넓히면 운영 가치보다 schema surface만 커질 가능성이 높다.

#### C. supply-chain family 전체 envelope rollout

장기적으로 필요하지만, 지금 self-improve loop를 막는 직접 원인은 아니다. release hygiene와 run artifact debt보다 우선할 이유가 없다.

#### D. archive candidate 자동 archival flow

정리성에는 유익하지만, queue 복구보다 앞설 수는 없다.

---

## 6. 현시점 우선순위 재정렬

### P0 — 지금 바로 막고 있는 병목

#### P0-1. legacy run artifact schema backfill

가장 중요한 항목이다.

현재 skip되는 대표 run:

- `run-20260422-auto-improve-decision-record-fallback-retry3-linux-tmp`
- `run-20260422-auto-improve-decision-record-fallback-retry2`
- `run-20260422-auto-improve-decision-record-fallback`
- `run-20260415-mechanism-planning-gate-second-clean`
- `run-20260414-mechanism-planning-gate`

공통 원인:

- `baseline-eval.json`의 `$schema` 누락

이 항목을 먼저 줄이지 않으면 candidate가 계속 0에 머무를 가능성이 높다.

**완료 기준**

1. `$schema` 누락으로 skip되는 run 0개
2. `runs_considered`가 2에서 유의미하게 증가
3. `runs_skipped` 감소

#### P0-2. candidate 0을 proposal seed로 연결하는 bridge 추가

현재는 blocker를 설명할 뿐, 그 blocker를 다음 작업 큐로 연결하지 못한다. 따라서 `candidate_blockers`가 존재해도 proposal queue는 비어 있다.

여기서 필요한 것은 예쁜 진단이 아니라 다음 중 하나다.

- bootstrap/shadow candidate 생성
- blocked proposal 생성
- candidate-to-proposal bridge report 생성

즉 **0 candidates → 0 proposals**를 운영적으로 끝내야 한다.

**완료 기준**

1. `proposals_emitted > 0` 또는
2. `blocked_proposals > 0`과 함께 machine-readable proposal blocker 존재

#### P0-3. schema validation 실패 12건 제거

이건 cosmetic이 아니다. mechanism review의 신뢰할 수 있는 evidence chain과 직접 연결된다.

우선 대상:

- `baseline/candidate-mechanism-assessment.json` 계열
- `run-telemetry.json`의 timeout metadata 누락 필드

**완료 기준**

- local schema validation failure 0

### P1 — 운영 복구를 지지하는 단기 작업

#### P1-1. release-smoke partial report 보장

현재 장기 실행 실패 시 바로 읽을 수 있는 부분 report를 신뢰하기 어렵다. 운영성 측면에서 중요하지만, queue 자체를 막는 직접 원인은 아니므로 P1이 적절하다.

#### P1-2. raw/web-snapshot filename canonicalization

현재 portability offender가 명확히 식별되었으므로, 긴 원문 제목을 slug + short hash 파일명으로 바꾸고 원제목은 frontmatter로 옮기는 것이 맞다.

#### P1-3. artifact freshness `top_debt[]`의 파일 단위 정규화

지금도 report는 좋아졌지만, 다음 10개 파일을 바로 고르기엔 아직 추상적이다. `path`, `owner_surface`, `recommended_action`, `expected_debt_reduction`까지 내려와야 진짜 작업 큐다.

#### P1-4. session rollup evidence 추가

현재 `attempts_considered=7`, `session_reports_considered=0`은 outcome calibration을 약하게 만든다. 다만 schema debt를 줄이기 전에는 효과가 제한적일 수 있어 P1이 적절하다.

### P2 — 좋아 보이지만 지금은 뒤로 미뤄야 할 작업

- runtime 대규모 분해
- proposal lifecycle ledger full rollout
- supply-chain family envelope 전면 확장
- archive candidate 자동 archival flow
- truthfulness writer의 광범위한 공통층 통합

이 항목들은 모두 맞는 방향이지만, **queue가 비어 있는 지금 당장 가장 값비싼 문제**는 아니다.

---

## 7. 권장 실행 순서

### PR-1: Legacy Run Artifact Backfill

대상:

- `runs/*/baseline-eval.json`
- `runs/*/candidate-eval.json`
- `runs/*/baseline-lint.json`
- `runs/*/candidate-lint.json`
- `runs/*/run-telemetry.json`
- `runs/*/*mechanism-assessment.json`

원칙:

- 확인 가능한 값과 `legacy_unknown`를 분리
- migration context와 원본 해시 기록
- schema validation까지 한 번에 수행

### PR-2: Mutation Proposal Blocked Ledger / Bridge

목표:

- `proposals_emitted=0 / blocked_proposals=0` 동시 상태 제거
- candidate blocker를 proposal seed 또는 blocked proposal로 승격

권장 추가 필드:

- `candidate_blocker_count`
- `proposal_seed_blockers`
- `proposal_blockers`
- `fallback_seed_attempted`
- `fallback_seed_result`

### PR-3: Schema Validation 12건 제거

목표:

- invalid artifact debt를 즉시 줄이고 mechanism review 입력 신뢰도 개선

### PR-4: Filename Canonicalization + POSIX Budget Gate

목표:

- `raw/web-snapshots/` long title 파일명을 canonical form으로 정리
- escape-expanded component 255 bytes 초과를 사전 차단

### PR-5: release-smoke partial report / heartbeat

목표:

- timeout/interrupt에도 phase, elapsed, stdout/stderr tail을 남김

---

## 8. 최소 Acceptance Criteria

이 프로젝트는 항목을 많이 닫는 것보다, 현재 병목이 실제로 줄었는지로 합격 여부를 판단해야 한다. 최소 기준은 아래 8개면 충분하다.

| ID | 기준 |
|---:|---|
| AC-01 | `$schema` 누락으로 skip되는 run이 0개다. |
| AC-02 | local schema validation failure가 0이다. |
| AC-03 | `mechanism-review-candidates.summary.candidates_emitted > 0` 또는 bootstrap/shadow candidate가 machine-readable하게 생성된다. |
| AC-04 | `mutation-proposals`는 `proposals_emitted=0 / blocked_proposals=0`으로 종료하지 않는다. |
| AC-05 | `auto-improve-readiness`가 `can_run=false`일 때도 next action이 proposal blocker 단위로 즉시 읽힌다. |
| AC-06 | `LC_ALL=C` 경로를 포함한 portability gate가 long filename offender를 사전에 잡는다. |
| AC-07 | `release-smoke`가 중단되어도 partial report를 남긴다. |

---

## 9. 최종 판단

세 리뷰는 전체적으로 수준이 높다. 특히 다음 세 가지는 모두 수용할 가치가 있다.

1. 현재 저장소가 “코드가 무너진 저장소”가 아니라 “운영 루프가 막힌 저장소”라는 진단
2. 관측 가능성 계층이 실제로 개선되었다는 평가
3. portability와 packaging hygiene를 무시하면 안 된다는 경고

그러나 anti-slop 기준으로 우선순위를 다시 매기면 결론은 더 단순해진다.

> 지금 가장 중요한 것은 멋진 보고서 구조를 더 넓히는 일이 아니라, legacy run artifact schema debt를 줄여 `candidates_emitted > 0`과 `proposals_emitted > 0`을 만드는 것이다.

즉, 현시점 1순위는 아래 세 줄로 요약된다.

1. **run artifact backfill**
2. **schema validation 12건 제거**
3. **candidate blocker를 proposal blocker/seed로 연결**

그 다음에야 portability hardening, freshness 정교화, lifecycle ledger, runtime decomposition이 의미를 가진다.

이 순서를 바꾸면 문서는 더 예뻐질 수 있어도 시스템은 여전히 멈춰 있을 가능성이 높다.


