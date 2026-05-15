# LLM Wiki vNext 개선 보고서

## 1. 작업 개요

이 보고서는 다음 네 가지 입력을 함께 검토해 재작성한 **개선 보고서**다.

1. 업로드된 리뷰 A: `LLM_Wiki_vNext_Anti_Slop_Integration_Report.md`
2. 업로드된 리뷰 B: `llm_wiki_vnext_integrated_review_report(1).md`
3. 이 대화에서 앞서 작성된 기존 리뷰(assistant 작성 기존 anti-slop/self-improvement 보고서)
4. 실제 저장소 파일 및 선택 재실행 결과 (`/mnt/data/review_workspace` 기준)

이번 보고서의 목적은 단순 요약이 아니다. 다음을 분리해서 정리했다.

- **두 리뷰가 공통으로 맞게 짚은 것**
- **기존 리뷰와 새 리뷰가 결합되며 더 강해진 주장**
- **실제 파일/재실행과 대조했을 때 보정이 필요한 주장**
- **즉시 수정 가능한 항목과 구조 개편이 필요한 항목**

핵심 결론부터 말하면, 두 업로드 리뷰의 큰 방향은 대체로 정확하다. 다만 실제 저장소와 다시 대조해 보니 몇몇 항목은 더 정밀하게 써야 한다. 특히 `writer_output_paths` 관련 문제는 리뷰들이 적은 것보다 **범위가 더 넓고**, `command_runtime` 관련 문제는 현재 시점에서 **결정적 재현 실패라기보다 병렬/환경 상호작용형 flake 후보**로 분류하는 편이 정확하다.

---

## 2. 실제로 다시 확인한 근거

이번 턴에서 실제로 다시 확인한 항목은 다음과 같다.

### 2.1 실제 파일 직접 대조

- `pyproject.toml`
- `ops/direct-script-entrypoints.txt`
- `ops/reports/release-closeout-summary.json`
- `ops/reports/release-evidence-cohort.json`
- `ops/reports/release-evidence-dashboard.json`
- `ops/reports/artifact-freshness-report.json`
- `ops/reports/auto-improve-readiness.json`
- `ops/reports/test-execution-summary.json`
- `tests/test_import_fallback_contract.py`
- `tests/test_script_module_surface_contract.py`
- `tests/test_generated_report_contracts.py`
- `tests/test_writer_output_paths.py`
- `ops/scripts/learning_readiness_signoff_revalidation.py`
- `ops/scripts/make_target_inventory.py`
- `ops/scripts/release_evidence_dashboard.py`

### 2.2 실제 재실행한 검증

이번 턴에서 재실행한 결과는 다음과 같다.

- `tests/test_import_fallback_contract.py -x` → **실패 재현**
- `tests/test_script_module_surface_contract.py -x` → **실패 재현**
- `tests/test_generated_report_contracts.py -x` → **실패 재현**
- `tests/test_writer_output_paths.py -x` → **실패 재현**
- `tests/test_command_runtime.py::CommandRuntimeTests::test_run_with_timeout_returns_completed_process_result` → **단독 pass**
- 동일 테스트 `-n 2` 실행 → **pass**

즉, 문서상으로 제기된 핵심 drift 문제는 실제로 다시 확인됐고, timeout/runtime 이슈는 현재 시점에서는 **“항상 깨지는 deterministic defect”로 단정하기보다 suite/worker 상호작용이 개입된 불안정성 후보**로 쓰는 편이 정확하다.

---

## 3. 두 업로드 리뷰가 정확하게 짚은 점

## 3.1 최상위 문제는 코드 조잡함보다 운영 계약 드리프트다

이 진단은 기존 리뷰와 두 업로드 리뷰가 모두 일치한다. 실제 파일을 다시 봐도 이 방향이 맞다.

현재 저장소는 다음 요소를 이미 갖추고 있다.

- schema-backed report
- currentness metadata
- release evidence cohort
- learning readiness signoff
- output path guard
- atomic write / rollback 계열 보호장치
- public/private boundary 의식

즉, 코어 런타임 자체가 무질서한 저장소는 아니다. 문제는 품질을 지키는 장치가 많아지면서 **장치끼리 서로 다른 진실을 가리키기 시작한 것**이다.

이건 기존 리뷰에서 말한 “sloppy governance”와 정확히 연결된다. 실제 재검증 결과도 그 해석을 지지한다.

## 3.2 `release_ready=true` 와 live gate 실패의 공존은 anti-slop 관점에서 최우선 문제다

실제 checked-in artifact를 다시 확인한 결과:

- `ops/reports/release-closeout-summary.json` → `status=pass`, `release_ready=true`
- `ops/reports/release-evidence-dashboard.json` → `status=attention`, `accepted_risk_count=6`
- `ops/reports/release-evidence-cohort.json` → `status=pass`

그리고 업로드 리뷰들이 인용한 핵심 진단은 모두 같은 방향이다.

- checked-in release evidence는 pass 성격을 유지하고 있음
- 그러나 live canonical gate(`make check`) 쪽에서 실패 4건이 보고됨
- 이 상태는 “릴리스 가능성”과 “실제 현재 상태”를 분리하지 못하게 만듦

이건 두 업로드 리뷰의 가장 강한 지적이었고, 그 우선순위 판단은 타당하다.

## 3.3 direct entrypoint / console script / generated artifact contract drift는 실제로 재현된다

실제 재실행으로 확인된 항목:

### A. direct script fallback allowlist 불일치

재현된 실패:

```text
FAILED tests/test_import_fallback_contract.py::ImportFallbackContractTests::test_direct_script_entrypoint_allowlist_matches_fallback_files
Items in the first set but not the second:
'ops/scripts/bootstrap_preflight.py'
```

즉, 업로드 리뷰들이 지적한 `bootstrap_preflight.py` allowlist 드리프트는 현재 저장소에서 그대로 재현된다.

### B. `pyproject.toml` console script 누락 2건

실제 비교 결과, 누락은 정확히 다음 2건이다.

```toml
llm-wiki-make-target-inventory = "ops.scripts.make_target_inventory:main"
llm-wiki-release-evidence-dashboard = "ops.scripts.release_evidence_dashboard:main"
```

업로드 리뷰들의 이 지적도 실제 상태와 일치한다.

### C. artifact freshness 테스트 의미 충돌

재현된 실패:

```text
FAILED tests/test_generated_report_contracts.py::test_checked_in_artifact_freshness_report_keeps_stable_debt_axes_explicit
assert None == 'backfill_artifact_envelope'
```

실제 `artifact-freshness-report.json` 요약값은 다음과 같다.

- `artifact_count = 180`
- `missing_artifact_envelope_count = 0`
- `stable_contract_debt_issue_count = 0`

즉, 보고서가 현재 debt 없음 상태를 가리키는데 테스트는 과거 debt 축이 `top_debt`에 남아 있길 기대하고 있다. 두 업로드 리뷰가 이걸 “과거 debt 존재를 요구하는 잘못된 테스트 semantics”로 읽은 건 정확하다.

---

## 4. 실제 파일과 대조했을 때 보정이 필요한 부분

여기부터가 이번 보고서의 핵심 추가 가치다. 두 업로드 리뷰의 큰 방향은 맞지만, 실제 파일과 재실행을 다시 맞춰 보니 몇몇 항목은 **더 정확하게** 써야 한다.

## 4.1 `writer_output_paths` 문제는 리뷰들이 적은 것보다 범위가 넓다

업로드 리뷰들은 주로 **extra 3건**만 강조했다.

- `ops/scripts/learning_readiness_signoff_revalidation.py`
- `ops/scripts/make_target_inventory.py`
- `ops/scripts/release_evidence_dashboard.py`

하지만 실제 AST 기반 비교를 다시 해보면 문제는 extra만이 아니다.

### output option 분류 실제 차이

#### extra

- `ops/scripts/learning_readiness_signoff_revalidation.py`
- `ops/scripts/make_target_inventory.py`
- `ops/scripts/release_evidence_dashboard.py`

#### missing

- `ops/scripts/raw_markdown_normalize.py`
- `ops/scripts/supply_chain_artifacts.py`

### repo output resolver 분류 실제 차이

#### extra

- `ops/scripts/learning_readiness_signoff_revalidation.py`
- `ops/scripts/make_target_inventory.py`
- `ops/scripts/raw_intake_promotion.py`
- `ops/scripts/release_evidence_dashboard.py`

#### missing

- `ops/scripts/raw_markdown_normalize.py`
- `ops/scripts/release_smoke.py`
- `ops/scripts/review_archive.py`
- `ops/scripts/source_slug_curation.py`

즉, 이 문제는 “새로 추가된 파일 3개를 allowlist에 넣으면 끝”이 아니다. 실제로는 다음 두 종류가 동시에 존재한다.

1. **새로 잡혔는데 registry/allowlist에 반영 안 된 surface**
2. **기존 registry/allowlist에 있으나 실제 AST surface와 어긋난 항목**

따라서 개선 방향도 더 정밀해야 한다.

- 단순 allowlist patch로 끝내면 재발한다.
- `ops/script-module-surfaces.json` 혹은 별도 writer registry를 **생성형 source of truth**로 승격해야 한다.
- 테스트는 “추가/삭제/클래스 변경”을 모두 설명형 diff로 출력해야 한다.

이 부분은 두 업로드 리뷰보다 이번 보고서가 더 엄밀하게 정리한 포인트다.

## 4.2 `command_runtime` 문제는 현재 시점에서 “결정적 버그”보다 “parallel-sensitive flake”로 쓰는 편이 정확하다

업로드 리뷰들은 대체로 다음 서사를 사용한다.

- `run_with_timeout()`이 환경에 따라 무한 대기할 수 있다.
- `communicate(timeout=...)` 의존이 위험하다.
- suite 전체를 멈출 수 있다.

이 방향 자체는 충분히 합리적이다. 특히 bounded drain, final timeout, integration lane 분리는 좋은 권고다.

다만 **현재 턴에서 다시 재실행한 범위 안에서는** 다음이 확인됐다.

- 해당 단일 테스트는 **serial pass**
- 동일 테스트를 `-n 2`로 돌려도 **pass**

즉, 지금 이 순간의 강한 표현은 이렇게 바꾸는 편이 맞다.

### 수정 전 진술

- timeout runtime이 현재 저장소에서 확정적으로 잘못 동작한다
- 해당 테스트 실패는 즉시 재현 가능한 deterministic defect다

### 수정 후 진술

- timeout/runtime 경로는 설계상 더 harden될 여지가 크다
- 업로드 리뷰가 제시한 bounded drain, monotonic deadline, lane 분리는 유효하다
- 하지만 현재 추가 재실행 범위에서는 실패를 고립 재현하지 못했으므로, **병렬 전체 스위트나 환경 anomaly와 결합될 때 드러나는 flake/interaction issue**로 분류하는 것이 더 정확하다

즉, 이 문제는 **우선순위는 높지만, 기술 서술은 한 단계 보수적으로 써야 한다.**

## 4.3 `test-execution-summary.json`은 업로드 리뷰들이 설명한 것보다 더 불안정한 표면이다

실제 파일을 다시 보면 `test-execution-summary.json`은 다음과 같은 특징을 가진다.

- `status = pass`
- `returncode = 0`
- `timed_out = false`
- `suite = report-contract-summary`
- `command` 안에 실제 deselect 4건이 박혀 있음
- 그러나 기대했던 `summary` 집계는 **없거나 비어 있음**
- `passed_count`, `failed_count`, `errors_count`, `deselected_count` 같은 count도 현재 파일에서는 **top-level에 `None`**

즉, 업로드 리뷰들이 이 파일을 “passed 116, failed 0, deselected 4” 식으로 읽은 부분은 당시 다른 실행 산출물이나 이전 상태에 기반한 설명일 수는 있어도, **현재 checked-in 파일 그대로의 표면과는 다르다.**

이건 작은 차이가 아니다. 왜냐하면 이 저장소의 핵심 문제 자체가 “checked-in evidence를 너무 믿으면 안 된다”이기 때문이다.

따라서 개선 보고서에서는 이 항목을 이렇게 정리하는 편이 정확하다.

- report-contract lane이 deselection을 사용하고 있다는 점은 분명하다
- 하지만 현재 checked-in `test-execution-summary.json`이 충분히 self-descriptive하지 않다
- 즉, **“실행 결과 요약 artifact가 실행 계약을 완전히 복원할 수 있어야 한다”는 요구를 아직 충족하지 못한다**

## 4.4 `auto-improve-readiness.json`은 summary형 artifact가 아니라 nested verdict artifact다

업로드 리뷰들은 이 파일을 대체로 잘 읽었지만, 구조를 더 명확히 적는 편이 좋다.

실제 파일은 다음처럼 읽는 것이 맞다.

- 최상위 `summary`에 중요한 값이 있는 구조가 아님
- 핵심은 `execution_readiness`와 `learning_readiness` 안에 중첩됨

실제 중요한 값:

- `execution_readiness.status = pass`
- `execution_readiness.can_run = true`
- `execution_readiness.runnable_proposal_count = 1`
- `learning_readiness.status = learning_uncertain`
- `learning_readiness.gate_effect = review_required`
- `learning_readiness.likely_to_learn = false`
- `attempts_considered = 6`
- `min_attempts_considered = 10`
- `telemetry_coverage_ratio = 0.5`
- `rework_count = 2`
- `defect_escape_pair_count = 1`

즉, “실행 가능”과 “승격 가능한 학습 상태”를 구분하는 저장소라는 업로드 리뷰의 요지는 맞지만, 실제 artifact surface를 보고 설계할 때는 `summary`가 아니라 **nested verdict contract**를 기준으로 삼아야 한다.

## 4.5 accepted risk 수치 자체도 artifact마다 다르므로 authoritative surface를 구분해야 한다

실제 checked-in 값:

- `release-closeout-summary.json` → `accepted_risk_count = 5`
- `release-evidence-dashboard.json` → `accepted_risk_count = 6`

즉, 같은 저장소 안에서도 accepted risk 숫자가 artifact마다 다르게 보인다.

이건 두 업로드 리뷰가 지적한 “truth ladder” 필요성을 더 강하게 뒷받침한다. 이 상태에서는 다음을 강제해야 한다.

1. 어떤 artifact가 **authoritative** 인가
2. 어떤 artifact는 **narrative or dashboard aggregation** 인가
3. 어떤 artifact는 **live rerun dependent** 인가

지금은 사람이 보고 “대충 비슷하다”고 넘기기 쉽지만, self-improvement 체계에서는 이런 미세한 표면 차이가 곧 오판의 원인이 된다.

---

## 5. 기존 리뷰와 두 업로드 리뷰를 합쳐 얻는 더 나은 해석

기존 리뷰는 주로 다음 축을 강조했다.

- governance drift
- single source of truth 부재
- generated artifact와 계약 테스트의 의미 불일치
- 대형 runtime / 대형 테스트의 복잡도 집중
- self-improvement는 실험으로 제한해야 한다는 원칙

두 업로드 리뷰는 여기에 다음을 더했다.

- live gate와 checked-in release evidence 불일치의 심각성
- truth ladder 개념
- 2-phase canonical promote 필요성
- writer/output surface 분류의 중요성
- concurrency/lock contract 필요성
- archive mode manifest 필요성

실제 파일과 다시 대조해 보면, 세 축을 이렇게 재정렬하는 것이 가장 정확하다.

### 축 1. 지금 당장 막아야 하는 것

- `release_ready=true` 와 live gate fail의 공존
- entrypoint / console script / writer surface drift
- artifact freshness test semantics mismatch

### 축 2. 구조를 바꿔야 재발이 멈추는 것

- 수동 allowlist / registry / pyproject 동시 유지
- canonical write와 self-reference report 구조
- checked-in evidence와 live execution result의 연결 약함

### 축 3. 자가 개선이 안전해지려면 추가로 필요한 것

- learning uncertainty 해소 전 promotion authority 차단
- mutation class를 더 작게 쪼개기
- timeout/runtime 경로의 bounded behavior 보장
- concurrency/lock contract

즉, **기존 리뷰는 방향을 잘 잡았고, 두 업로드 리뷰는 우선순위를 더 sharpen했다.** 다만 실제 파일 대조 결과를 반영하면 writer drift와 report surface 문제를 더 엄밀히 다뤄야 한다.

---

## 6. 통합 최종 진단

### 가장 중요한 한 문장

**현재 LLM Wiki vNext의 최우선 문제는 “코드가 엉성하다”가 아니라, “evidence 체계가 스스로의 진실 계층을 충분히 강제하지 못한다”는 점이다.**

이 문제는 다음 형태로 나타난다.

1. live gate와 checked-in report가 같은 결론을 보장하지 않는다.
2. CLI / allowlist / writer classification이 한 정의에서 생성되지 않는다.
3. generated artifact test가 현재 상태 검증과 과거 debt taxonomy 보존을 혼동한다.
4. self-improvement는 실행 가능하지만, promotion-safe 하지는 않다.

이 네 가지가 동시에 존재하면, 품질 체계가 많을수록 오히려 **“그럴듯한 pass”** 가 늘어난다.

---

## 7. 권장 개선안

## 7.1 P0 — 오늘 바로 닫아야 할 항목

### P0-1. `release_ready` 판정에 live canonical gate를 강제 입력으로 넣기

필수 변경:

- `release-closeout-summary` 생성 시 live `make check` 결과를 직접 참조
- live `make check` fail이면 `release_ready=false`
- accepted risk는 `release_ready=true`를 유지시키는 면죄부가 아니라 별도 상태로 분리

권장 필드:

- `release_ready`
- `clean_release_ready`
- `conditional_release_ready`
- `last_live_make_check_returncode`
- `last_live_make_check_generated_at`
- `last_live_make_check_log_path`

### P0-2. direct entrypoint / console script drift 즉시 복구

즉시 수정:

- `ops/direct-script-entrypoints.txt`에 `ops/scripts/bootstrap_preflight.py` 추가 또는 fallback 제거
- `pyproject.toml`에 누락된 2개 console script 추가

### P0-3. writer/output surface를 수동 allowlist에서 생성형 registry로 전환

즉시 patch해야 할 실제 불일치:

#### output option

- extra 3건
- missing 2건

#### resolver

- extra 4건
- missing 4건

즉, 지금은 단순히 3건 추가로 끝내지 말고, 테스트가 읽는 registry 자체를 새로 설계해야 한다.

### P0-4. `artifact_freshness` 테스트 semantics 수정

바꿔야 할 원칙:

- 현재 debt가 0이면 `top_debt`에 과거 debt axis가 없어도 정상
- debt taxonomy 보존은 별도 registry/policy에서 검증
- live report는 현재 debt만 표현

### P0-5. canonical write는 무조건 2-phase promote로 바꾸기

권장 흐름:

1. candidate artifact를 `tmp/diagnostics/...` 에 생성
2. schema / fingerprint / live gate / contract test 검증
3. 전부 pass한 경우에만 `ops/reports/...` 로 promote

이렇게 해야 self-reference test와 stale checked-in report 문제가 동시에 줄어든다.

## 7.2 P1 — 이번 주 안에 구조적으로 손봐야 할 항목

### P1-1. truth ladder를 코드와 schema에 반영

권장 순서:

1. 방금 끝난 live canonical gate
2. 같은 fingerprint의 generated artifact
3. structured accepted risk
4. historical checked-in report
5. 사람이 쓴 narrative review

상위 단계가 fail이면 하위 단계의 pass가 릴리즈 판정을 뒤집지 못하게 해야 한다.

### P1-2. timeout/runtime 하드닝 + 테스트 tier 분리

권장 조치:

- `communicate()` 마지막 drain에도 timeout 적용
- monotonic deadline 기반 bounded loop 추가
- process group / orphan diagnostic 분리
- real subprocess test는 serial integration lane으로 이동
- fake backend 기반 unit lane과 분리

중요한 점은, 이 항목을 “현재 단일 테스트가 항상 실패한다”로 쓰기보다 **“전체 suite 또는 특정 환경에서만 드러나는 상호작용형 불안정성까지 흡수하는 구조로 바꿔야 한다”** 로 쓰는 것이다.

### P1-3. `test-execution-summary`와 `release-evidence-dashboard`를 더 self-descriptive 하게 만들기

현재는 사람이 파일을 열어도 실제 어떤 lane이 어떤 deselect를 썼는지, 어떤 rerun이 authoritative인지 복원하기 어렵다. 이건 evidence artifact로서 약점이다.

추가 권장 필드:

- `passed_count`
- `failed_count`
- `errors_count`
- `deselected_count`
- `authoritative`
- `derived_from_live_gate`
- `checked_in_or_live`
- `promotion_source`

### P1-4. `auto-improve-readiness`를 promotion gate와 더 강하게 연결

현재 읽기:

- 실행 가능
- 학습 확실성은 부족
- review_required

따라서 다음을 명시해야 한다.

- `can_execute_trial`
- `can_promote_result`
- `promotion_blockers`
- `required_operator_signoff`
- `rollback_required_before_promotion`

## 7.3 P2 — 중기 구조 개선

### P2-1. 대형 runtime / 대형 test 분해

기존 리뷰가 지적한 복잡도 집중은 여전히 유효하다. 특히 다음 파일군은 계속 핵심 후보다.

- `auto_improve_readiness_runtime.py`
- `mutation_proposal_runtime.py`
- `artifact_freshness_runtime.py`
- `release_closeout_summary.py`
- `test_execution_summary.py`

분해 원칙:

- collector
- normalizer
- classifier/scorer
- report builder
- writer/envelope

### P2-2. 공통 artifact envelope/writer 도입

반복되는 다음 패턴을 공용화해야 한다.

- `PRODUCER`
- `SOURCE_COMMAND`
- `ARTIFACT_KIND`
- `generated_at`
- `currentness`
- `source_tree_fingerprint`
- `input_fingerprints`
- repo-relative output guard

### P2-3. archive mode / public-private packaging contract 명시

권장 mode:

- `full_vault_private_archive`
- `public_code_mirror`
- `release_source_package`
- `review_bundle`

각 archive root에 `ARCHIVE-MANIFEST.json` 추가를 권장한다.

---

## 8. 실제 수정 우선순위 제안

### 1순위

- live gate와 release-ready 불일치 제거
- direct entrypoint / console script drift 제거
- writer surface registry화
- artifact freshness test semantics 수정

### 2순위

- 2-phase canonical promote
- timeout/runtime bounded drain 설계 보강
- report artifact self-description 강화

### 3순위

- auto-improve promotion safety 강화
- complexity budget의 실제 merge gate화
- 대형 runtime/test 분해

---

## 9. Definition of Done

다음이 모두 참이 되어야 현재 저장소가 anti-slop / self-improvement 관점에서 한 단계 안정권으로 올라간다고 볼 수 있다.

1. `make check`가 clean pass한다.
2. `release-closeout-summary`와 live gate 결과가 같은 결론을 낸다.
3. `release_ready=true`가 fail한 live gate 위에 서는 경로가 없다.
4. `ops/direct-script-entrypoints.txt`와 실제 fallback marker가 일치한다.
5. `pyproject.toml` scripts와 direct wrapper 기대치가 일치한다.
6. writer output / resolver classification extra/missing count가 0이다.
7. `artifact_freshness` 테스트가 과거 debt 존재를 요구하지 않는다.
8. canonical report는 2-phase promote를 거친다.
9. `auto-improve-readiness`가 uncertain learning 상태에서 promotion authority를 열지 않는다.
10. `test-execution-summary`와 dashboard가 authoritative/live 여부를 스스로 설명할 수 있다.
11. timeout/runtime live-process 테스트가 unit lane과 integration lane으로 분리된다.
12. accepted risk가 clean pass와 같은 UI/필드로 표현되지 않는다.

---

## 10. 최종 결론

두 업로드 리뷰는 전체적으로 수준이 높고, 방향도 맞다. 특히 다음 세 가지를 최상위 위험으로 본 판단은 타당하다.

1. live gate와 checked-in release evidence의 불일치
2. 수동 유지되는 운영 계약 surface의 drift
3. learning uncertainty 상태에서의 과도한 self-improvement 낙관

다만 실제 저장소와 다시 대조한 결과, 이번 최종 보고서에서는 다음 두 가지 보정을 반드시 넣어야 한다.

### 첫째

`writer_output_paths` 문제는 리뷰들이 적은 것보다 더 넓다. extra만 있는 게 아니라 missing도 함께 존재한다. 따라서 단순 allowlist 추가가 아니라 registry 구조 재설계 문제다.

### 둘째

`command_runtime` 문제는 현재 시점에서 고립 재현까지는 확보되지 않았다. 그러므로 deterministic defect라고 쓰기보다, **suite/parallel/environment interaction까지 포함해 흡수해야 하는 불안정성 클래스**로 다루는 편이 정확하다.

이 두 보정을 반영하면, 기존 리뷰 + 두 업로드 리뷰 + 실제 파일 대조를 거친 최종 판단은 다음 한 줄로 정리된다.

> **이 저장소는 이미 성숙한 evidence-oriented ops runtime이지만, 이제 필요한 것은 기능 추가보다 “진실 계층을 강제하는 구조화”다.**

즉, 사람의 기억으로 여러 표면을 동시에 맞추는 구조를 제거하고, live gate → authoritative artifact → conditional decision 으로 이어지는 단일 진실 흐름을 코드로 강제해야 한다. 그 작업이 끝나야 self-improvement도 진짜 개선이 되고, 그 전까지는 bounded trial 이상을 맡기면 안 된다.

---

## 11. 외부 기준과의 정렬 포인트

이번 개선 방향은 공개 생태계의 일반 원칙과도 잘 맞는다.

- PyPA entry points / `pyproject.toml` metadata / console script 표면 정합성
- pytest fixture 재사용, integration tier 분리, flaky test 격리
- mypy strict의 점진적 확대와 per-module 관리
- Ruff의 좁은 기본 규칙에서 점진적으로 확대하는 방식
- JSON Schema의 modular structuring / `$ref` 기반 재사용
- SLSA / in-toto / Sigstore / CycloneDX / OpenVEX 계열의 provenance, attestation, SBOM/VEX 운영 원칙

즉, 지금 필요한 것은 새로운 원칙의 발명이 아니라, **이미 코드베이스 안에 있는 좋은 의도를 더 강한 구조로 연결하는 일**이다.
