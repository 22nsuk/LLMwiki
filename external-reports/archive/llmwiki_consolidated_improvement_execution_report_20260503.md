# LLMwiki 개선을 위한 통합 실행 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-03 (Asia/Seoul) |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_consolidated_improvement_execution_report_20260503.md` |
| 통합 입력 문서 | `llmwiki_post_review_integrated_report_20260503.md`, `llmwiki_post_review_unified_report_20260503.md`, `llmwiki_post_review_audit_report_20260503_ko.md`, `llmwiki_dual_post_review_reconciliation_improvement_report_20260503.md` |
| 실증 기준 | `LLMwiki(9).zip` 내부 체크인 산출물과 설정 파일 |
| ZIP SHA-256 | `72c845256fe05bb9e1ebddb51e357d7321ef8f3780e639d71b40bb4d7f1c35df` |
| 최종 통합 판정 | **현재 스냅샷은 release governance 문서화와 산출물 체계가 상당히 정리되었으나, 상태는 여전히 `conditional_pass`이며 clean release / machine release는 불가하다. 다음 단계의 핵심은 “문서 추가”가 아니라 strict cohort 봉인, accepted risk 제거, closeout 검증 의미 분리, 운영 선언과 코드 구현 일치화다.** |

---

## 1. 이 보고서의 목적

이번 문서는 단순 비교표가 아니다. 업로드된 두 후속 통합 문서와 기존 분석 문서를 한데 묶어, **지금 실제로 파일과 릴리스 체계를 어떻게 개선해야 하는지**를 실행 관점에서 재정리한 통합 보고서다.

즉 목적은 다음 네 가지다.

1. 여러 문서에 흩어진 사실과 판단을 **하나의 실행 기준**으로 수렴시킨다.
2. 현재 ZIP이 실제로 말하는 상태를 기준으로 **문서 서술의 우선순위**를 다시 잡는다.
3. 기존 보고서들을 앞으로 어떻게 역할 분리할지 정한다.
4. 레포/산출물/문서 체계를 clean release 가능한 방향으로 개선하기 위한 **구체적 작업 순서**를 제시한다.

---

## 2. 통합에 사용한 입력과 우선순위

### 2.1 통합한 문서

이번 통합에는 최소 다음 네 문서를 반영했다.

1. `llmwiki_post_review_integrated_report_20260503.md`
2. `llmwiki_post_review_unified_report_20260503.md`
3. `llmwiki_post_review_audit_report_20260503_ko.md`
4. `llmwiki_dual_post_review_reconciliation_improvement_report_20260503.md`

### 2.2 최종 판정의 우선순위

문장보다 실물을 우선했다. 판정 우선순위는 다음과 같다.

1. **최우선**: `LLMwiki(9).zip` 내부 실제 파일  
   - `ops/reports/*.json`
   - `ops/script-output-surfaces.json`
   - `Makefile`
   - `pyproject.toml`
   - `system/system-log.md`
2. **다음**: 기존 분석 문서들이 공통으로 확인한 사실
3. **마지막**: 문서별 표현, 강조점, 해석 차이

이 원칙에 따라, 문서가 아무리 길고 정교해도 실제 체크인 상태와 어긋나는 부분은 보수적으로 정리했다.

---

## 3. 현재 상태의 단일 기준선

여러 문서를 통합한 뒤에도, 현재 상태를 판정하는 기준선은 아래 값들로 수렴한다.

### 3.1 Release authority 핵심 상태

#### `ops/reports/release-closeout-summary.json`

- `status=pass`
- `release_readiness_state=conditional_pass`
- `clean_release_ready=false`
- `machine_release_allowed=false`
- `operator_release_allowed=true`
- `requires_accepted_risk_review=true`
- `source_tree_fingerprint=8c9b5cc7c8ebf37d5aabe70f3cff75bc6fedd7ce2a9df6496c5a734bd9f8ac9a`

#### `ops/reports/release-evidence-cohort.json`

- `status=attention`
- `strict_same_fingerprint=false`
- `component_fingerprint_count=2`
- `accepted_risk_family_count=3`
- `clean_lane_contract.status=fail`
- `failed_conditions =`
  - `zero_accepted_risk_family`
  - `strict_cohort_pass`
  - `release_closeout_clean`

#### `ops/reports/release-lane-summary.json`

- `clean_lane_status=fail`
- `conditional_lane_status=pass`
- `machine_release_status=blocked`
- `operator_release_status=allowed`
- `release_authority_status=conditional_pass`

#### `ops/reports/release-closeout-batch-manifest.json`

- `status=fail`
- `batch_integrity_status=pass`
- `release_authority_status=conditional_pass`
- `finality.is_final=true`
- `summary.required_count=10`
- `summary.required_present_count=10`
- `summary.required_current_count=10`

### 3.2 Accepted risk family 3건

clean lane을 막는 accepted risk family는 현재 3건으로 정리된다.

1. `learning_blocked_by_review_required`
2. `generated_index_archive_advisory`
3. `source_tree_coherence_attention`

이 셋은 각각 성격이 다르지만, 지금 시점에서는 모두 clean lane 차단 요인이다.

### 3.3 Learning readiness 상태

현재 learning readiness는 구조적으로 “장치가 생겼다”와 “해결되었다”를 구분해야 한다.

- signoff 파일은 존재한다.
- revalidation 파일도 존재한다.
- 그러나 실제 상태는 여전히 `learning_uncertain`에 가깝다.
- `attempts_considered=7`, `min_attempts_considered=10`
- `telemetry_coverage_ratio=0.0`
- `likely_to_learn=false`

즉 **conditional lane에서 operator signoff로 임시 수용된 상태**이지, clean release 기준을 만족한 상태는 아니다.

### 3.4 테스트/정적 검증 측면에서 이미 안정화된 부분

기존 문서들이 공통으로 확인한 안정 구간은 유지해도 된다.

- Ruff 통과
- mypy 통과
- `test_release_lane_summary` 통과
- `test_release_closeout_batch_manifest` 통과
- `test_release_clean_blocker_ledger` 통과 확인
- `test_import_fallback_contract` 통과
- `test_script_module_surface_contract` 통과
- `test_command_runtime` 일부 핵심 경로 통과 확인
- `test-execution-summary.json` 기준 `119 passed, 0 failed`

이 구간은 “이미 해소된 정적/계약성 문제”로 분리해도 무방하다.

---

## 4. 여러 보고서를 통합한 뒤 남는 핵심 해석

이 절이 이번 문서의 핵심이다. 여러 보고서의 표현은 달라도, 실질적으로는 아래 네 문장으로 수렴한다.

### 4.1 문제의 중심은 artifact 부재에서 coherence/contract 문제로 이동했다

이전 기준 리뷰들이 크게 지적했던 항목 중 일부는 현재 실제로 해소되었다.

- `release-lane-summary` entrypoint 부재 해소
- `release_clean_blocker_ledger` 신설
- accepted-risk vocabulary 표면 보강
- closeout chain에 lane / blocker / batch finalizer 편입
- canonical artifact 일괄 재생성

따라서 지금의 중심 문제는 더 이상 “산출물이 없다”가 아니다.  
지금의 중심 문제는 다음 두 축이다.

1. **strict source-tree cohort를 하나로 봉인하지 못함**
2. **운영 문서가 말하는 계약과 실제 구현이 완전히 일치하지 않음**

### 4.2 batch manifest는 “깨져 있다”기보다 “의미가 섞여 있다”

여러 문서가 공통으로 다룬 중요한 포인트다.

현재 상태를 가장 정확하게 말하면 다음과 같다.

- artifact inventory 측면: **통과**
- required artifact currentness 측면: **통과**
- release authority 측면: **conditional**
- strict source-tree identicality 측면: **미해결**

그런데 top-level `status=fail`이 이 의미를 한 줄에 섞어 표현한다.  
그래서 operator는 “배치 자체가 깨졌나?”와 “clean release가 아직 안 되나?”를 구분하기 어렵다.

즉 이 문제는 단순 pass/fail 문제가 아니라, **검증 층위 분리 실패** 문제다.

### 4.3 `ops/script-output-surfaces.json` 문제는 payload 문제가 아니라 envelope 문제다

실행용 개선 계획에서 이 구분은 매우 중요하다.

현재 드러난 문제는 대체로 다음으로 요약할 수 있다.

- 표면 분류 payload 자체가 대규모로 틀린 것은 아니다.
- 문제는 checked-in envelope의 `source_tree_fingerprint`가 closeout 계열과 갈라져 있다는 점이다.
- 이 차이가 `component_fingerprint_count=2`를 만드는 한 원인 축이다.

즉 이 이슈를 “분류 로직 재설계”로 과잉 대응할 필요는 없다.  
우선순위는 **canonical refresh와 frozen closeout 재봉인**이다.

### 4.4 system log와 Makefile 불일치는 작아 보여도 운영상 치명적이다

`system/system-log.md`에는 `release-closeout-batch-manifest-verify` target에 clean-workspace precondition이 추가되었다고 적혀 있다.  
하지만 실제 `Makefile` target은 현재 단순히 Python check만 실행한다.

이 문제는 표면상 사소해 보여도, 실제로는 다음 리스크를 만든다.

- 운영자는 fail-fast guard가 있다고 믿는다.
- 하지만 실제 자동화는 그 guard를 강제하지 않는다.
- 결과적으로 문서상 보장과 코드상 보장이 분리된다.

이 항목은 문서 품질 문제가 아니라 **운영 계약 위반**에 가깝다.

---

## 5. 파일 개선을 위한 통합 실행 계획

이 절은 실제로 레포와 산출물을 개선하기 위한 실행 목록이다.

### 5.1 P0 — clean release 전 반드시 처리할 항목

#### 1) `ops/script-output-surfaces.json` canonical refresh
목표:
- checked-in `source_tree_fingerprint`를 current release source tree와 일치시킨다.
- payload drift 여부와 envelope drift 여부를 분리해 확인한다.

완료 기준:
- checked-in registry와 fresh generation이 payload / fingerprint / currentness 모두 일치
- `component_fingerprint_count` 감소의 직접 근거 확보

#### 2) frozen closeout window 재생성
목표:
- release evidence 전체를 하나의 frozen source tree fingerprint 아래 다시 봉인한다.

완료 기준:
- `strict_same_fingerprint=true`
- `component_fingerprint_count=1`
- `make release-evidence-cohort-check`가 clean lane 요구까지 포함해 통과 가능해지는 기반 마련

#### 3) batch manifest 검증 의미를 3계층으로 분리
현재 필요한 구분:

- artifact inventory integrity
- artifact content integrity
- source-tree coherence integrity

완료 기준:
- `release-closeout-batch-manifest.json` 또는 companion artifact에서 위 3층이 각각 독립 필드로 표현됨
- top-level `status` 오독 가능성 축소

#### 4) `system/system-log.md`와 `Makefile` 계약 일치화
선택지는 둘 중 하나다.

- 실제 Makefile에 clean-workspace precondition 구현
- 또는 system log의 해당 서술을 “planned / not yet enforced”로 정정

완료 기준:
- 문서 선언과 코드 동작이 1:1로 일치
- 가능하면 이를 확인하는 정적 contract test 추가

#### 5) archive candidate 2건 처리
현재 `generated-artifact-index.json`는 archive candidate 2건 때문에 advisory risk를 유지한다.

완료 기준:
- 두 파일을 `external-reports/archive/`로 이동하거나
- 정책적으로 root 유지가 정당하면 그 근거를 machine-readable하게 남김
- `generated_index_archive_advisory` 제거 또는 clean lane 비차단화

#### 6) learning readiness blocker 해소 또는 clean lane 모델 재정의
현재는 signoff 기반 조건부 허용 상태다.

완료 기준(둘 중 하나):
- 실제 learning closure 조건 충족
- 혹은 clean lane 정의를 재설계해 이 risk가 operator-only로 내려감

### 5.2 P1 — 구조 안정화 항목

#### 1) `accepted-risk-vocabulary.schema.json`를 실제 공통 `$ref`로 승격
지금은 파일이 생겼다는 수준에 가깝다.  
다음 단계는 여러 schema가 이 vocabulary를 공유하도록 강제하는 것이다.

완료 기준:
- closeout / dashboard / lane / batch manifest / blocker ledger가 공통 vocabulary fragment를 참조
- count와 명칭 drift 재발 방지

#### 2) closeout self-check artifact 추가
필요한 산출물 예시:
- `ops/reports/release-evidence-closeout-self-check.json`

포함할 내용:
- closeout 직후 batch verify 결과
- closeout 직후 cohort check 결과
- 당시 source tree fingerprint
- 당시 주요 upstream input digest

이 artifact가 있어야 “처음부터 틀렸는지”와 “나중에 drift했는지”를 구분할 수 있다.

#### 3) downstream input digest 검증 추가
현재 closeout summary가 어떤 upstream artifact를 읽었는지, 그 digest가 현재 checked-in 파일과 같은지까지 추적해야 한다.

완료 기준:
- consumer ↔ input digest mismatch를 machine-readable하게 보고
- closeout stale reference를 조기 탐지

#### 4) `system log` 선언 검증 테스트 추가
예시:
- `tests/test_system_log_release_contracts.py`

완료 기준:
- “added”, “enforced”, “fail-fast” 유형 선언이 실제 구현과 불일치할 경우 바로 실패

---

## 6. 가장 작은 안전한 다음 단계

실무적으로 바로 시작할 순서는 아래가 가장 안전하다.

1. `ops/script-output-surfaces.json` 재봉인
2. frozen closeout window 재실행
3. `release-evidence-cohort-check`와 batch manifest 검증을 read-only / mutable 모드로 분리
4. `system log` 선언과 Makefile 구현을 일치
5. archive candidate 2건 처리
6. long-form canonical report + operator summary 두 문서 체계로 정리

이 여섯 단계가 끝나야 현재 문서 체계도 함께 안정된다.

---

## 7. 최종 결론

이번 통합의 핵심은 단순하다.

> **지금 필요한 것은 strict cohort / accepted risk / closeout semantics / 운영 계약 일치 문제를 순서대로 닫는 것이다.**

즉 다음 회차의 목표는 아래여야 한다.

**release evidence를 실제로 더 clean하게 만든다.**
