# LLM Wiki vNext 통합 리뷰 재검토 및 개선 보고서

- 파일명: `unified_current_audit_improvement_report.md`
- 작성일: 2026-04-25
- 작성 언어: 한국어
- 검토 대상 ZIP: `LLM Wiki vNext(39).zip`
- 새로 검토한 리뷰: `llm_wiki_vnext_unified_audit_report_20260425.md`
- 함께 대조한 기존 리뷰/보고서:
  - `llm_wiki_vnext_39_audit_improvement_report_20260425.md`
  - `llm_wiki_v36_cross_audit_improvement_report_20260425.md`
  - 이전 재출력본 `report.md` / `llm_wiki_vnext_39_audit_report_redelivered_20260425.md`
- 검토 방식: 업로드된 새 통합 리뷰의 주장 전체를 항목별로 분해하고, 기존 v39 보고서·v36 참고 리뷰·현재 ZIP 파일 식별값·이전 직접 검증 결과와 교차 대조했다.
- 중요한 한계: 이번 재검토 중 POSIX locale `unzip` 실제 해제는 부분 진행 후 장시간 지연되어 완료 판정을 새로 주장하지 않는다. 또한 전체 `make check`, 전체 pytest, ruff, mypy, release-smoke 완주도 이번 턴에서 새로 완료 주장하지 않는다. 기존 보고서와 새 통합 리뷰가 제시한 실행 결과는 “리뷰 근거”로 구분해 반영했다.

---

## 1. 최종 결론

새 통합 리뷰의 핵심 결론은 전반적으로 타당하다. 특히 현재 아카이브가 v36 참고 리뷰의 대상과 다른 artifact라는 점, v39 계열에서 일부 개선이 있었지만 auto-improve loop는 여전히 실행 가능한 proposal을 만들지 못한다는 점, generated artifact evidence chain과 run/report schema 부채가 서로 연결되어 있다는 점은 기존 v39 보고서와 현재 파일 상태가 모두 같은 방향을 가리킨다.

다만 새 통합 리뷰는 세부적으로 두 가지를 조정해 읽어야 한다.

첫째, ZIP portability는 “항상 실패하는 현재 결함”이 아니라 **환경 의존적 release portability defect**로 분류하는 것이 정확하다. UTF-8 환경의 Python `zipfile` 및 일반 `unzip` 경로에서는 통과가 확인되었고, POSIX locale 또는 escape-expanded filename 환경에서 실패 가능성이 실증 또는 강하게 추정된다. 따라서 우선순위는 P0 운영 중단 결함이라기보다 P1 release gate hardening에 가깝다. 단, 실제 배포 대상이 다양한 OS/locale을 포함한다면 release-blocker로 격상해야 한다.

둘째, auto-improve 병목은 v36의 `runs_considered=0` 단계에서 현재는 `runs_considered=2` 단계로 이동했다. 따라서 현재의 복구 기준은 단순히 “run을 읽는다”가 아니라 **`candidates_emitted > 0` 및 `proposals_emitted > 0`을 만드는 것**이어야 한다. 새 통합 리뷰가 이 기준을 상향 조정한 것은 타당하다.

현재 가장 중요한 개선 우선순위는 다음과 같다.

1. `structural_complexity_budget_runtime.py`의 strict preview import order I001 즉시 수정.
2. local schema validation error 13개와 핵심 run artifact의 `$schema` 누락을 우선 backfill.
3. `mechanism-review-candidates.json`의 `candidates_emitted=0` 원인을 machine-readable blocker로 분해.
4. `mutation-proposals.json`이 `proposals_emitted=0 / blocked_proposals=0`으로 조용히 끝나지 않게 fallback seed와 blocked reason을 기록.
5. artifact freshness report를 숫자 요약이 아니라 `top_debt`, `owner_surface`, `recommended_next_action`을 가진 실제 작업 큐로 개선.
6. ZIP release gate에 UTF-8 unzip, POSIX/escape-expanded filename budget, path budget, public/full archive class manifest를 추가.

---

## 2. 검토 대상 및 동일성 확인

### 2.1 현재 ZIP 식별

| 항목 | 값 |
|---|---:|
| 파일명 | `LLM Wiki vNext(39).zip` |
| 크기 | 191,151,960 bytes |
| SHA-256 | `c62b67c3354b9229025e0a91b03b2a1fdb2fb60bfdb9525b1045a10e45ac12ba` |
| 기존 v36 ZIP 크기 | 190,999,399 bytes |
| 기존 v36 ZIP SHA-256 | `f18f7ac4eb32c2952ce8e668cd70ad9150572b3dc24320d6362d2b2cb86ea33c` |

현재 ZIP은 v36 참고 리뷰의 대상과 다른 artifact다. 따라서 v36 리뷰는 “이전 결함의 기준선”으로만 사용해야 하고, 현재 판단은 v39 계열 ZIP 기준으로 내려야 한다.

### 2.2 새 통합 리뷰의 동일 아카이브 판단

새 통합 리뷰는 리뷰 A/B/C가 각각 `vNext(39).zip`, `vNext(40).zip`, `vNext.zip`처럼 다른 파일명을 사용했지만, 크기와 SHA-256이 동일하므로 같은 아카이브를 독립 검토한 것이라고 판단했다. 이 판단은 타당하다. 파일명 변동보다 SHA-256과 byte size가 더 강한 동일성 근거다.

### 2.3 현재 검토에서 확정 가능한 사실

| 항목 | 판정 |
|---|---|
| 현재 ZIP은 v36과 다름 | 확정 |
| 새 통합 리뷰가 대상으로 삼은 v39/v40/vNext.zip은 동일 SHA로 묶임 | 리뷰 근거상 수용 |
| 현재 ZIP의 정적 구조는 기존 v39 보고서와 일치 | 수용 |
| 현재 ZIP의 POSIX locale unzip 실패 여부 | 이번 턴에서는 완료 재현 못 함, 단 escape-expanded filename risk는 수용 |

---

## 3. 새 통합 리뷰의 핵심 주장별 대조

| 새 통합 리뷰 주장 | 기존 v39 보고서와 대조 | 현재 파일/검증 상태 | 판정 |
|---|---|---|---|
| 세 리뷰는 동일 SHA의 같은 아카이브를 검토했다 | 기존 v39 보고서의 SHA와 일치 | 현재 ZIP도 같은 byte size로 확인 | 수용 |
| v36 참고 리뷰 대상과 현재 ZIP은 다르다 | 기존 v39 보고서와 동일 | 크기/SHA가 다름 | 수용 |
| Python 276개 `py_compile` 오류 0 | 기존 v39 보고서와 동일 | 이전 직접 검증 결과와 일치 | 수용 |
| JSON 213개 parse 오류 0 | 기존 v39 보고서와 동일 | 이전 직접 검증 결과와 일치 | 수용 |
| local schema validation 13개 실패 | 기존 v39 보고서와 동일 | 기존 직접 검증 결과와 일치 | 수용 |
| generated artifact 144개 중 129개 envelope/currentness debt | 기존 v39 보고서와 동일 | `artifact-freshness-report.json` 기반 | 수용 |
| `runs_considered=2`, `runs_skipped=5` | 기존 v39 보고서와 동일 | `mechanism-review-candidates.json` 기반 | 수용 |
| `candidates_emitted=0`, `proposals_emitted=0`, `can_run=false` | 기존 v39 보고서와 동일 | generated reports 기반 | 수용 |
| strict preview I001 1건 | 기존 v39 보고서와 동일 | 해당 import 순서 문제 확인 | 수용 |
| POSIX locale unzip 실패 | 기존 v39 보고서는 직접 재현 안 함 | 이번 턴도 완료 재현 못 함 | 부분 수용: portability defect/risk로 반영 |
| `.pyc` 286개 포함 | 기존 v39 보고서에는 약함 | 새 통합 리뷰의 추가 발견 | 수용, release hygiene 항목 추가 |
| public export 384개, private prefix leak 0 | 기존 v39 보고서와 동일 | 이전 직접 실행 결과와 일치 | 수용 |
| freshness stale count가 mtime에 민감 | 기존 v39 보고서에는 미흡 | 새 통합 리뷰의 보완 통찰 | 수용, gate 설계에 반영 |

---

## 4. 현재 상태 요약

### 4.1 저장소는 “정적 위생은 양호하지만 운영 루프가 막힌 상태”

현재 저장소는 기본 정적 품질이 낮은 코드베이스는 아니다. Python 문법 오류와 JSON parse 오류는 발견되지 않았다. public export도 private prefix leak 없이 정상 결과를 낸다. 그러나 self-improving system으로서 중요한 generated artifact, run history, proposal queue, readiness 판단은 아직 닫힌 루프로 작동하지 않는다.

이 상태를 한 문장으로 표현하면 다음과 같다.

> 코드는 대체로 읽히고 파싱되지만, 시스템이 자기 산출물의 최신성·스키마·근거를 신뢰하지 못해 다음 개선 후보를 안정적으로 생성하지 못한다.

### 4.2 auto-improve 병목 사슬

현재 병목은 다음 순서로 연결된다.

```text
run artifact의 $schema / required field 누락
  ↓
mechanism review에서 runs_skipped=5, runs_considered=2
  ↓
candidates_emitted=0
  ↓
mutation_proposals에서 source_candidates_read=0, proposals_emitted=0
  ↓
auto_improve_readiness에서 can_run=false, runnable_proposal_count=0
  ↓
자동 개선 실행 불가
```

v36 대비 개선된 점은 `runs_considered=0`에서 `runs_considered=2`로 올라온 것이다. 그러나 실행 가능한 제안 생성까지는 아직 도달하지 못했다. 따라서 현재 수용 기준은 `runs_considered > 0`이 아니라 `candidates_emitted > 0`으로 올려야 한다.

### 4.3 generated artifact debt의 의미

`artifact-freshness-report.json`의 핵심 수치는 다음과 같다.

| 필드 | 값 |
|---|---:|
| `artifact_count` | 144 |
| `json_artifact_count` | 144 |
| `scanned_text_artifact_count` | 170 |
| `stale_artifact_count` | 55 |
| `unknown_currentness_artifact_count` | 129 |
| `missing_schema_count` | 39 |
| `missing_artifact_envelope_count` | 129 |
| `missing_generated_at` | 59 |
| `generated_at_older_than_file_mtime` | 55 |

이 수치는 단순 문서 누락 문제가 아니다. auto-improve runtime은 generated artifact를 다음 단계 입력으로 사용한다. 그러므로 envelope/currentness/schema가 없는 artifact는 자동 개선 판단의 입력 신뢰도를 떨어뜨린다.

---

## 5. 새 통합 리뷰에서 특히 유의미한 추가 통찰

### 5.1 POSIX locale ZIP portability

새 통합 리뷰는 리뷰 B의 관측을 통해 POSIX locale에서 `unzip`이 한글 파일명을 `#UXXXX` 형태로 escape하면서 filename component가 팽창하고, 이로 인해 `File name too long`이 발생할 수 있음을 제시했다.

현재 정리:

| 환경/검증 | 결과 |
|---|---|
| Python `zipfile` | 통과로 보고됨 |
| 일반 UTF-8 `unzip` | 통과로 보고됨 |
| POSIX locale `unzip` | 리뷰 B에서 실패 재현, 이번 턴에서는 완료 재현 못 함 |
| 원본 최대 component | 173 UTF-8 bytes |
| escape-expanded 최대 component | 약 317 bytes로 보고됨 |

이 항목은 “ZIP이 깨졌다”가 아니라 “locale과 unzip 구현에 따라 release archive가 해제 실패할 수 있다”로 이해해야 한다. 따라서 release-smoke가 UTF-8 happy path만 보면 부족하다.

### 5.2 freshness의 mtime 민감도

새 통합 리뷰는 압축 해제 후 filesystem mtime이 바뀌면서 stale count가 55에서 85로 증가할 수 있다고 지적했다. 이는 중요한 설계 신호다. freshness 판정은 file mtime에 과도하게 의존하면 release archive 재해제 환경에 따라 흔들린다.

권장 원칙:

1. `generated_at`과 `input_fingerprints`를 primary signal로 둔다.
2. `file_mtime`은 보조 signal로 낮춘다.
3. archive 재검증 시 `mtime_sensitive` 또는 `archive_rehydrated` 플래그를 기록한다.
4. stale count를 “실제 stale”과 “archive mtime artifact”로 분리한다.

### 5.3 `.pyc` 파일 포함

새 통합 리뷰는 `.pyc` 286개가 release archive에 포함되어 있음을 지적했다. 이 항목은 즉시 기능 장애를 일으키는 P0는 아니지만 release hygiene과 reproducibility 측면에서 정리해야 한다.

권장 정책:

- full internal vault archive라면 `.pyc` 포함 여부를 명시한다.
- public/release archive라면 `.pyc`, `.pytest_cache`, `.obsidian`, `.vscode`, `.codex` 등 개발 환경 산출물을 기본 제외한다.
- 제외하지 않는 경우 manifest에 “의도적으로 포함됨”을 기록한다.

### 5.4 proposal lifecycle ledger

새 통합 리뷰는 `improvement_id`, `source_run_id`, `evidence_artifact_ids`, `decision`, `negative_memory_key` 등 proposal lifecycle ledger를 강조했다. 이는 단순 편의 기능이 아니라 self-improvement loop의 중복 제안과 실패 반복을 막는 핵심 장치다.

권장 추가 필드:

| 필드 | 목적 |
|---|---|
| `improvement_id` | 제안-실행-결과 연결 |
| `source_run_id` | 어떤 run evidence에서 나온 제안인지 추적 |
| `evidence_artifact_ids` | 근거 artifact 목록 |
| `decision` | accepted/rejected/blocked/deferred 상태 |
| `negative_memory_key` | 같은 실패 제안 반복 방지 |
| `expected_debt_reduction` | debt 감소 예상치 |
| `actual_debt_delta` | 실행 후 실제 debt 변화 |

---

## 6. 우선순위 재정렬

### P0 — 즉시 처리

| ID | 항목 | 이유 | 완료 기준 |
|---|---|---|---|
| P0-1 | strict preview I001 수정 | 수정 비용이 극히 낮고 CI noise 제거 효과가 큼 | `ruff check --select I` error 0 |
| P0-2 | local schema validation error 13개 제거 | auto-improve input 신뢰도와 직접 연결 | local schema validation error 0 |
| P0-3 | 핵심 run artifact `$schema`/envelope backfill | `runs_skipped=5`의 직접 원인 | `runs_skipped` 감소, `runs_considered` 증가 |
| P0-4 | no-candidate blocker 기록 | 현재 병목인 `candidates_emitted=0` 원인 불명 | `candidate_blockers[]` 또는 동등 필드 생성 |
| P0-5 | mutation proposal empty-state 제거 | `proposals_emitted=0 / blocked_proposals=0`은 actionability가 없음 | proposal 또는 blocked reason 1개 이상 |

### P1 — 단기 구조 개선

| ID | 항목 | 이유 | 완료 기준 |
|---|---|---|---|
| P1-1 | artifact freshness top debt report | 숫자 요약을 작업 큐로 전환 | top 10 debt list stable output |
| P1-2 | canonical report truthfulness writer | 보고서/다운로드 artifact 신뢰도 강화 | exists/size/sha256/schema status 자동 기록 |
| P1-3 | ZIP portability gate | POSIX/escape-expanded filename defect 대응 | UTF-8 + POSIX/escape budget smoke |
| P1-4 | fast-smoke target | feedback loop 단축 | 30~120초 목표 target 추가 |
| P1-5 | long-running gate telemetry | hang/장시간 실행 구분 | phase, last item, stdout/stderr tail 기록 |
| P1-6 | optional JSON diagnostics 전파 | silent `{}` fallback 방지 | provenance-heavy caller wrapper 제거 |
| P1-7 | proposal lifecycle ledger | 실패 반복 방지 | `improvement_id` 기반 lifecycle report |

### P2/P3 — 중장기 정리

| ID | 항목 | 이유 |
|---|---|---|
| P2-1 | `auto_improve_readiness_runtime.py` 분해 | 1,257 LOC, branch complexity 과다 |
| P2-2 | `mutation_proposal_runtime.py` 분해 | scoring/fallback/report 책임 혼재 |
| P2-3 | output path policy 가시화 | `repo_report`, `external_export`, `public_export` 등 class 명확화 필요 |
| P2-4 | policy exact enumeration 축소 | YAML 1,667행 규모의 path enumeration drift 방지 |
| P2-5 | public/full archive class 분리 | full vault와 public export 경계 명확화 |
| P3-1 | root 0-byte placeholder 정리 | provenance hygiene |
| P3-2 | `review/` 빈 디렉터리 정리 | workspace 의도 명시 또는 삭제 |
| P3-3 | `.pyc`/cache/dev hidden dir release 정책 | reproducibility 및 배포 청결성 |

---

## 7. 권장 PR 실행 순서

### PR-1: Strict Preview Import Order 수정

- 대상: `ops/scripts/structural_complexity_budget_runtime.py`
- 변경: `from dataclasses import dataclass`를 `from json import JSONDecodeError`보다 앞으로 이동
- 예상 diff:

```python
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any
```

- 검증:
  - `python -m py_compile ops/scripts/structural_complexity_budget_runtime.py`
  - `python -m ruff check --select I ops/scripts/structural_complexity_budget_runtime.py`
- 위험도: 낮음

### PR-2: Schema Validation Error 13개 제거

- 대상:
  - `ops/reports/openvex-draft.json`
  - `runs/*/*mechanism-assessment.json`
  - `runs/*/run-telemetry.json`
- 작업:
  - `artifact_context`, `advisory_count`, `artifact_set_id`, `security_advisories_ref`, `spdx_ref` 보강
  - `risk_flag_evidence`, `target_profiles`, `dimension_evidence` 보강
  - `launch_succeeded`, `signal_sent`, `final_state_observed`, `stdout_received`, `stderr_received` 보강
- 주의: 실제 확인값과 `legacy_unknown` 값을 반드시 구분
- 완료 기준: local schema validation error 0

### PR-3: 핵심 Run Eval/Lint Artifact Backfill

- 대상:
  - `baseline-eval.json`
  - `candidate-eval.json`
  - `baseline-lint.json`
  - `candidate-lint.json`
- 작업:
  - `$schema` 추가
  - artifact envelope 추가
  - `generated_at`, `producer`, `source_command`, `input_fingerprints`, `currentness` 추가
- 완료 기준:
  - `runs_skipped` 감소
  - `$schema` 누락으로 skip되는 run 감소

### PR-4: Mechanism Review Candidate Blocker 도입

- 대상: mechanism review runtime
- 작업:
  - `candidates_emitted=0`의 원인을 `insufficient_history`, `threshold_not_met`, `schema_gap`, `missing_metric`, `deduped`, `policy_blocked` 등으로 분류
  - report에 `candidate_blockers[]` 출력
- 완료 기준: candidate가 0이어도 다음 action이 한 줄로 결정 가능

### PR-5: Mutation Proposal Fallback Seed 복구

- 대상: `mutation_proposal_runtime.py`
- 작업:
  - source candidate 0일 때 fallback family가 seed되지 않는 이유 기록
  - fallback도 불가능하면 `blocked_proposals`에 blocker로 기록
- 완료 기준: `proposals_emitted=0`과 `blocked_proposals=0`이 동시에 발생하지 않음

### PR-6: Artifact Freshness를 Work Queue로 전환

- 대상: `artifact_freshness_runtime.py`, schema
- 작업:
  - `top_debt`
  - `owner_surface`
  - `recommended_next_action`
  - `safe_to_backfill`
  - `mtime_sensitive`
  - `artifact_role`
- 완료 기준: report만 보고 다음 10개 수정 파일을 결정 가능

### PR-7: Canonical Report Truthfulness Writer

- 대상: report writer 공통층
- 작업:
  - schema validation 후 atomic write
  - 파일 재읽기 후 `exists`, `size_bytes`, `sha256` 기록
  - evidence manifest 자동 생성
- 완료 기준: canonical report-producing CLI가 동일 writer를 사용

### PR-8: ZIP Portability Release Gate

- 대상: release archive script
- 작업:
  - Python `zipfile` smoke
  - UTF-8 `unzip` smoke
  - POSIX locale `unzip` smoke 또는 escape-expanded filename budget 검사
  - max path/component/top offenders 기록
- 완료 기준: 환경 의존적 filename failure를 release 전에 감지

### PR-9: Fast Smoke Target

- 대상: Makefile, pytest markers
- 포함:
  - artifact IO
  - output path policy
  - optional JSON diagnostic
  - report schema sample
  - strict preview smoke
  - public export leak smoke
  - minimal run artifact validation
- 제외:
  - full wiki lint/eval
  - full release smoke
  - 외부 Python subprocess 의존 heavy test
- 완료 기준: 일반 개발 환경 30~120초

### PR-10: Runtime Surface 첫 분해

- 대상: `auto_improve_readiness_runtime.py`
- 분리:
  - evidence collector
  - blocker evaluator
  - queue diagnostics
  - recommendation renderer
  - report writer
- 완료 기준: public API compatibility 유지, behavior unchanged

---

## 8. 통합 Acceptance Criteria

| # | 기준 |
|---:|---|
| AC-01 | strict preview I001은 allowlist 확장 없이 코드 수정으로 제거한다. |
| AC-02 | local schema validation error는 0이거나 명시적 legacy allowlist로 분리된다. |
| AC-03 | touched generated JSON은 `$schema`와 artifact envelope를 가진다. |
| AC-04 | backfill 값은 확인값, `legacy_unknown`, `not_available`을 구분한다. |
| AC-05 | `mechanism-review-candidates`는 `candidates_emitted=0`일 때 machine-readable blocker를 출력한다. |
| AC-06 | `mutation-proposals`는 `proposals_emitted=0 / blocked_proposals=0`으로 조용히 종료하지 않는다. |
| AC-07 | auto-improve 복구의 1차 기준은 `candidates_emitted > 0`이다. |
| AC-08 | 2차 기준은 `proposals_emitted > 0`, 3차 기준은 `runnable_proposal_count > 0`이다. |
| AC-09 | `artifact-freshness-report`는 `top_debt`와 `recommended_next_action`을 제공한다. |
| AC-10 | freshness 판정은 `generated_at`/`input_fingerprints`와 mtime 신호를 분리한다. |
| AC-11 | canonical report 제공 전 `exists`, `size_bytes`, `sha256`, `schema_validation_status`가 기록된다. |
| AC-12 | release ZIP은 Python zipfile과 UTF-8 unzip에서 통과해야 한다. |
| AC-13 | POSIX locale unzip 또는 escape-expanded filename budget 검사를 release gate에 포함한다. |
| AC-14 | full vault archive와 public export archive는 `artifact_class`가 다르게 표시된다. |
| AC-15 | public export는 `raw/`, `wiki/`, `system/`, `runs/`, `external-reports/` leak check를 hard fail로 수행한다. |
| AC-16 | `make fast-smoke`는 30~120초 목표로 핵심 계약만 검증한다. |
| AC-17 | long-running gate는 phase, current item, elapsed seconds를 주기 출력한다. |
| AC-18 | timeout report는 `returncode`, `timed_out`, `signal_sent`, `stdout_tail`, `stderr_tail`을 포함한다. |
| AC-19 | optional JSON input은 `missing`, `decode_error`, `type_error`, `read_error`를 구분한다. |
| AC-20 | proposal lifecycle은 `improvement_id`로 source evidence, decision, outcome을 연결한다. |
| AC-21 | `.pyc`, `.pytest_cache`, `.obsidian`, `.vscode`, `.codex` 포함 여부는 archive class별 정책으로 결정한다. |
| AC-22 | runtime 분해 PR은 behavior change와 cleanup을 섞지 않는다. |
| AC-23 | output path class는 CLI help/report에 노출한다. |
| AC-24 | root 0-byte placeholder는 의도 문서화 또는 제거 중 하나로 처리한다. |
| AC-25 | `review/` 빈 디렉터리는 목적 문서화 또는 삭제한다. |

---

## 9. 새 통합 리뷰에 대한 세부 평가

### 9.1 강점

새 통합 리뷰는 기존 v39 보고서보다 다음 점에서 더 완성도가 높다.

1. 서로 다른 파일명으로 지칭된 리뷰 A/B/C가 동일 SHA의 같은 아카이브를 봤다는 점을 명확히 정리했다.
2. v36 대비 병목이 `runs_considered=0`에서 `candidates_emitted=0`으로 이동했다는 구조적 변화를 정확히 반영했다.
3. POSIX locale unzip failure를 단순 파일명 길이 문제가 아니라 escape-expanded filename 문제로 설명했다.
4. artifact freshness의 mtime 민감도를 별도 설계 이슈로 분리했다.
5. proposal lifecycle ledger와 negative memory를 self-improvement loop의 반복 실패 방지 장치로 제안했다.
6. `.pyc` 포함과 숨김 개발 디렉터리 포함 여부를 release archive hygiene 문제로 끌어올렸다.

### 9.2 보정이 필요한 부분

1. POSIX locale unzip 실패는 실제 배포 환경에서 중요하지만, 모든 환경에서 재현되는 defect로 과장하면 안 된다. release gate 항목으로 관리하되, 배포 대상 환경이 POSIX/non-UTF-8을 포함하면 release-blocker로 격상한다.
2. `stale_artifact_count`는 mtime 민감도가 있으므로 절대 수치만으로 품질 회귀를 판정하면 안 된다. fingerprint 기반 currentness와 분리해야 한다.
3. 리뷰 B가 확인한 기본 ruff/mypy 통과는 유용하지만, 다른 실행 환경에서는 재현되지 않았으므로 보고서에는 “리뷰 B 환경에서 확인”으로 구분해야 한다.
4. `.pyc` 포함은 release hygiene 문제이지, auto-improve loop를 직접 막는 핵심 P0는 아니다.

---

## 10. 최종 실행 로드맵

### Phase 1: 즉시 수정

- PR-1 strict preview import order 수정
- PR-2 local schema validation error 13개 제거
- PR-3 핵심 run eval/lint `$schema` backfill

목표: CI noise 제거, schema debt의 가장 위험한 부분 축소, mechanism review skip 감소.

### Phase 2: auto-improve queue 복구

- PR-4 no-candidate diagnostic
- PR-5 mutation proposal fallback seed
- proposal lifecycle ledger 최소 버전 도입

목표: `candidates_emitted=0`, `proposals_emitted=0`, `can_run=false`의 원인이 보고서에서 기계적으로 설명되게 만들기.

### Phase 3: artifact/release 운영성 강화

- PR-6 artifact freshness top debt
- PR-7 canonical report truthfulness writer
- PR-8 ZIP portability gate
- PR-9 fast-smoke target
- long-running gate telemetry

목표: 사람이 보고서 숫자를 해석하는 상태에서, 시스템이 다음 조치와 release 위험을 자동으로 드러내는 상태로 전환.

### Phase 4: 구조 개선

- `auto_improve_readiness_runtime.py` 분해
- `mutation_proposal_runtime.py` 분해
- output path policy class 가시화
- public/full archive class 분리
- root placeholder, review dir, `.pyc`/cache 정책 정리

목표: 장기 유지보수성과 release reproducibility 개선.

---

## 11. 검증 한계

이번 보고서는 새 통합 리뷰, 기존 v39 보고서, v36 참고 리뷰, 현재 ZIP 식별값을 대조해 작성했다. 다만 다음 검증은 이번 턴에서 새로 완료 주장하지 않는다.

1. `make check` 전체 완주
2. `make release-smoke` 전체 완주
3. 전체 pytest 완주
4. `ruff`/`mypy` 재실행 완료
5. POSIX locale `unzip` 전체 해제 완료
6. raw PDF 전체 의미론적 검토 또는 OCR
7. private corpus 본문 의미론적 검토

이 제한은 결론의 핵심을 약화하지 않는다. auto-improve loop의 병목, generated artifact debt, schema validation error, strict preview import order, release portability risk는 서로 독립적인 리뷰와 기존 검증 결과가 같은 방향을 가리키기 때문이다.

---

## 12. 최종 권고

지금 해야 할 일은 대규모 리팩터링이 아니다. 가장 먼저 작은 PR로 strict preview noise를 제거하고, schema validation error와 run artifact `$schema` 누락을 줄여 mechanism review가 더 많은 run을 읽도록 만들어야 한다. 그 다음 `candidates_emitted=0`의 원인을 machine-readable blocker로 드러내고, mutation proposal이 empty/empty 상태로 끝나지 않도록 fallback seed와 blocked reason을 복구해야 한다.

ZIP portability는 현재 모든 환경에서 실패하는 결함은 아니지만 release artifact로서는 충분히 중요한 리스크다. release gate에 POSIX/escape-expanded filename budget을 추가하고, 장기적으로 raw/web snapshot 파일명은 `slug + short hash` 방식으로 줄이며 원제목은 manifest/frontmatter에 보존하는 방향이 바람직하다.

한 줄로 정리하면 다음과 같다.

> 현재 v39 계열은 정적 코드 품질보다 generated evidence chain, schema-valid run history, candidate/proposal queue, release portability gate가 더 중요한 병목이다. 이 네 축을 먼저 복구해야 self-improving wiki라는 시스템 목표가 실제 운영 루프로 이어진다.
