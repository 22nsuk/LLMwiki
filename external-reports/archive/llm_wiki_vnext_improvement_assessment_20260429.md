# LLM Wiki vNext Improvement Assessment Report

- 작성일: 2026-04-29 (Asia/Seoul)
- 출력 파일명: `llm_wiki_vnext_improvement_assessment_20260429.md`
- 검토 입력물:
  - `llm_wiki_vnext_unified_review_report_20260428.md`
  - `llm_wiki_vnext_integrated_followup_status_report_20260429.md`
  - 실제 산출물 ZIP: `LLM Wiki vNext(54).zip`
- 검토 방식: 두 리뷰 전문 재검토 + 실제 ZIP 내 코드/리포트/Makefile/테스트 존재 여부 및 핵심 수치 재대조
- 최종 판정: `progressed_but_still_not_release_ready`

---

## 1. 보고서 목적

본 문서는 두 개의 리뷰 문서를 각각 독립된 근거 문서로 다시 검토한 뒤, 그 결론을 실제 ZIP 내부 파일과 대조하여 **무엇이 이미 해결되었는지**, **무엇이 아직 남아 있는지**, **기존 리뷰 서술 중 무엇을 더 정교하게 고쳐 써야 하는지**, **지금 시점에서 가장 실무적으로 유효한 개선 우선순위가 무엇인지**를 재정리한 개선 보고서다.

이번 보고서는 단순 요약이 아니라 다음 네 가지를 분리해서 다룬다.

1. 두 리뷰 문서 간 공통 합의
2. 두 리뷰 문서 간 강조점 차이
3. 실제 ZIP 내부 파일로 재확인된 사실
4. 기존 리뷰를 한 단계 더 발전시키기 위한 구조적 개선안

---

## 2. 입력 문서별 성격과 역할

### 2.1 `llm_wiki_vnext_unified_review_report_20260428.md`

이 문서는 세 개의 선행 리뷰를 하나로 통합한 보고서다. 즉, 이번 작업에서 검토 대상인 “두 리뷰” 중 첫 번째 문서는 사실상 **3건의 기존 리뷰를 흡수한 메타 리뷰** 역할을 한다. 이 문서의 강점은 다음과 같다.

- 동일 체크포인트를 전제로 한 리뷰 간 합의 구조가 분명하다.
- 해결/미해결/신규 개선안이 분리되어 있다.
- `missing_schema 13건`, `ops_reports 7건`, `stable debt 71/155` 같은 세부 debt 목록이 풍부하다.
- 후속 우선순위를 P0/P1/P2 관점으로 정리해 둔 점이 실무적으로 유용하다.

한계도 있다.

- 리뷰가 참조한 기준 ZIP과 현재 ZIP이 다르다는 사실을 잘 설명하지만, 독자가 실제로 무엇이 “현 시점에 재현된 사실”이고 무엇이 “기준 리뷰에서 가져온 사실”인지 한 번 더 분리해서 읽어야 한다.
- live 재생성 값과 checked-in 저장값을 동시에 다루는 부분은 정확하지만, 보고서만 빠르게 읽는 독자에게는 “현재 저장본 수치”와 “live 재생성 수치”가 섞여 보일 수 있다.

### 2.2 `llm_wiki_vnext_integrated_followup_status_report_20260429.md`

이 문서는 위 통합 문서를 바탕으로 논점을 더 압축하고, 현재 ZIP 기준의 상태 메시지를 더 명료하게 재배치한 후속 상태 보고서다. 장점은 다음과 같다.

- 실제 실무자가 바로 읽기 좋은 P0/P1/P2 구조가 잘 잡혀 있다.
- “이미 전진한 항목”과 “release-ready를 아직 막는 항목”의 분리가 더 선명하다.
- `generated_artifact_index`, `fast-smoke`, `raw registry`, `learning readiness` 네 개의 핵심 축을 초반에 바로 드러내 읽기성이 좋다.

한계도 분명하다.

- 선행 통합 보고서의 내용을 대폭 재사용하고 있어서, 독립 문서로는 좋지만 중복이 꽤 크다.
- 일부 표현은 “현재 ZIP에서 재확인된 사실”과 “선행 보고서의 결론을 계승한 사실”이 같은 강도로 보인다.
- evidence source의 실제 파일 경로를 더 구체적으로 써 주면 후속 검증성이 높아진다.

### 2.3 두 문서의 관계 정리

두 문서는 서로 충돌하지 않는다. 오히려 관계는 아래처럼 보는 것이 정확하다.

- 첫 번째 문서: **리뷰 통합과 근거 축적 중심**
- 두 번째 문서: **운영 관점의 상태 재정리와 실행 우선순위 중심**

따라서 이번 개선 보고서는 둘 중 하나를 폐기하기보다, **첫 번째의 근거 밀도**와 **두 번째의 전달 효율**을 결합하는 방향이 가장 적절하다고 판단한다.

---

## 3. 실제 ZIP 기준 재검증 요약

실제 ZIP 파일(`LLM Wiki vNext(54).zip`)에서 직접 다시 확인한 값은 아래와 같다.

| 항목 | 실제 확인 결과 | 판정 |
|---|---|---|
| ZIP SHA-256 | `bf3b4433aeec89c7aa54d200c34bcfe8aac8d9735e443822bc87cc02b8657a6f` | 두 리뷰와 일치 |
| ZIP entries / files / dirs | 1,667 / 1,585 / 82 | 두 리뷰와 일치 |
| CRC 검사 | `zipfile.testzip() == None` | 무결성 이상 없음 |
| `ops/reports/generated-artifact-index.json` 존재 | 예 | 존재 재확인 |
| `ops/reports/release-smoke-report.json` 존재 | 예 | 존재 재확인 |
| `ops/reports/review-archive-report.json` 존재 | 예 | 존재 재확인 |
| `tests/test_makefile_static_gates.py` 존재 | 예 | 존재 재확인 |
| `tests/test_release_smoke.py` 존재 | 예 | 존재 재확인 |
| `ops/scripts/raw_registry_runtime.py` 존재 | 예 | 존재 재확인 |
| `ops/scripts/path_portability_runtime.py` 존재 | 예 | 존재 재확인 |

핵심적으로, 두 리뷰가 제시한 “현재 ZIP은 과거 기준 리뷰보다 한 단계 더 전진해 있다”는 큰 결론은 실제 파일 레벨에서도 유지된다.

---

## 4. 실제 파일로 확인된 ‘해결 또는 상당 부분 해소’ 항목

### 4.1 Generated artifact index의 inventory count drift는 실제로 해소되어 있다

실제 `ops/reports/generated-artifact-index.json`의 summary를 확인한 결과, 아래 수치가 저장되어 있었다.

| key | 저장값 |
|---|---:|
| `ops_reports_root_file_count` | 20 |
| `task_improvement_observation_count` | 30 |
| `external_reports_root_file_count` | 20 |
| `external_reports_archive_file_count` | 19 |
| `run_directory_count` | 11 |
| `run_archive_directory_count` | 1 |
| `canonical_report_count` | 31 |
| `archive_candidate_count` | 20 |

이는 두 리뷰가 공통으로 말한 “count drift는 해소됐다”는 판단과 부합한다. 즉, **inventory count 기준으로는 이미 복구된 상태**라고 봐도 무방하다.

다만 `generated_at`은 `2026-04-28T12:17:16Z`이고, `release-smoke-report.json`의 `generated_at`은 `2026-04-28T14:06:41Z`여서, 두 리뷰가 지적한 것처럼 **count는 맞더라도 fingerprint freshness는 다시 stale일 가능성**이 높다. 이 부분은 “해결”이 아니라 “부분 해결”로 두는 것이 정확하다.

### 4.2 `make fast-smoke`의 stale selector 이슈는 코드상으로는 해소되어 있다

실제 파일 확인 결과는 다음과 같다.

- Makefile에는 `fast-smoke:` target이 존재한다.
- Makefile에는 `release-smoke-fast:` target이 존재한다.
- Makefile에는 `release-smoke-full:` target은 없다.
- Makefile에는 현재 selector 이름인 `test_build_smoke_commands_match_release_gate_profiles`가 반영돼 있다.
- 과거 stale selector 이름인 `test_build_smoke_commands_matches_release_gate_contract`는 더 이상 기준 이름으로 남아 있지 않다.
- `tests/test_release_smoke.py`에는 `def test_build_smoke_commands_match_release_gate_profiles(...)`가 존재한다.
- `tests/test_makefile_static_gates.py`에는 `test_fast_smoke_selectors_collect_via_supported_pytest_entrypoint`가 존재한다.

정리하면, **stale node-id 자체는 실제 파일 기준으로 고쳐져 있다.** 따라서 이 항목은 더 이상 “현재 tree의 코드 결함”이라기보다 “full runtime 완주 증적이 아직 부족한 항목”으로 재분류하는 것이 맞다.

### 4.3 Release-smoke full report는 실제 저장본으로 확인된다

실제 `ops/reports/release-smoke-report.json` 확인 결과:

| key | 값 |
|---|---|
| `status` | `pass` |
| `profile` | `full` |
| `generated_at` | `2026-04-28T14:06:41Z` |
| `source_command` | `python -m ops.scripts.release_smoke --vault . --profile full` |

즉, 두 리뷰가 반복해서 언급한 “full profile 저장 report는 존재하며 최신화되어 있다”는 판단은 실제 파일에서 재확인된다.

### 4.4 Review archive canonicalization은 실제 산출물로 존재한다

실제 `ops/reports/review-archive-report.json` 확인 결과:

| key | 값 |
|---|---|
| `status` | `pass` |
| `generated_at` | `2026-04-28T03:41:42Z` |
| `packed_file_count` | 387 |

이 역시 두 리뷰의 공통 판단과 일치한다.

### 4.5 Raw registry 대응 코드는 실제 파일에 존재한다

실제 파일에서 다음을 확인했다.

- `ops/scripts/raw_registry_runtime.py` 존재
- `ops/scripts/path_portability_runtime.py` 존재
- `tests/test_raw_registry_preflight.py` 존재
- `tests/test_raw_registry_runtime.py` 존재

즉, raw registry 관련 보완이 문서상 선언만이 아니라 **코드/테스트 파일 존재 수준에서는 실체가 있다**는 점이 재확인된다.

---

## 5. 실제 파일로 확인된 ‘여전히 남아 있는 항목’

### 5.1 Stable artifact contract debt는 실제 저장 리포트에서도 그대로 크다

실제 `ops/reports/artifact-freshness-report.json`의 저장값은 아래와 같다.

| key | 값 |
|---|---:|
| `stable_contract_debt_artifact_count` | 71 |
| `stable_contract_debt_issue_count` | 155 |
| `mtime_sensitive_attention_artifact_count` | 34 |
| `mtime_sensitive_attention_issue_count` | 34 |
| `stale_artifact_count` | 34 |
| `missing_schema_count` | 13 |
| `unknown_currentness_artifact_count` | 71 |
| `missing_artifact_envelope_count` | 71 |

즉, 두 리뷰가 공통으로 강조한 핵심 blocker인 stable debt는 실제 저장본 기준으로도 그대로 남아 있다. 이 항목은 해석 여지가 거의 없다. **아직 크고, release-ready를 막는 주요 축이다.**

### 5.2 Learning readiness는 실제로도 `learning_uncertain`이다

관련 지표는 `ops/reports/learning-readiness-report.json`이 아니라 실제로는 `ops/reports/auto-improve-readiness.json` 안의 `learning_readiness` 블록에서 확인되었다. 이 점은 후속 보고서에서 더 명확히 써 줄 필요가 있다.

실제 확인값:

| key | 값 |
|---|---|
| `execution_readiness.status` | `pass` |
| `learning_readiness.status` | `learning_uncertain` |
| `learning_readiness.likely_to_learn` | `false` |
| `attempts_considered` | 7 |
| `min_attempts_considered` | 10 |
| `session_calibration_status` | `no_session_context` |
| `telemetry_coverage_ratio` | 0.0 |
| `rework_count` | 5 |
| `defect_escape_pair_count` | 3 |
| `hold_moving_average` | 0.2857 |
| `discard_moving_average` | 0.1429 |

따라서 learning readiness는 문서상 주장뿐 아니라 실제 저장 evidence에서도 미해결이다.

### 5.3 Fast/full profile evidence split은 아직 완결되지 않았다

실제 파일 확인 결과:

| 항목 | 실제 상태 |
|---|---|
| `ops/reports/release-smoke-report-fast.json` | 없음 |
| `ops/reports/release-smoke-report.json` | 있음 (`full`) |
| Makefile `release-smoke-fast` | 있음 |
| Makefile `release-smoke-full` | 없음 |

즉, 코드와 Makefile은 fast/full 분리를 향해 움직였지만, **증적 산출물 보관 정책과 타깃 명명 대칭성은 아직 닫히지 않았다.**

### 5.4 Raw registry canonical artifact는 아직 없다

실제 파일 확인 결과 `ops/reports/raw-registry-preflight-report.json`은 존재하지 않았다. 따라서 두 리뷰가 제안한 “cross-environment matrix의 canonical artifact화”는 아직 구현 전 단계로 보는 것이 맞다.

### 5.5 Test execution summary artifact도 아직 없다

실제 파일 확인 결과 `ops/reports/test-execution-summary.json`은 존재하지 않았다. 즉, timeout / fail / interrupt / partial-pass를 한 artifact로 구조화하는 개선안도 아직 미실행 상태다.

### 5.6 Bare pytest UX 혼선은 여전히 남아 있다

실제 재확인 결과:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --collect-only -q`는 통과했다.
- 반면 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest --collect-only -q`는 실패했고, 출력에는 `ModuleNotFoundError: No module named 'ops'`가 포함됐다.

즉, 두 리뷰가 지적한 “공식 entrypoint는 명시됐지만 plain pytest 사용자는 여전히 혼란을 겪는다”는 문제는 실제로도 그대로 남아 있다.

---

## 6. 두 리뷰를 실제 파일과 대조했을 때 드러나는 핵심 해석

### 6.1 두 리뷰의 기본 결론은 옳다

가장 중요한 결론부터 말하면, 두 리뷰의 기본 판정인 아래 문장은 유지된다.

> 많이 전진했지만 아직 release-ready는 아니다.

이 결론은 실제 ZIP 기준으로도 유효하다. 이유는 간단하다.

- 해소된 항목은 주로 **selector drift**, **count drift**, **stored report presence**, **raw registry acute mismatch 완화** 쪽이다.
- 남은 항목은 **artifact contract debt**, **learning readiness**, **profile evidence split**, **cross-environment canonical evidence**, **guided failure UX**처럼 release discipline의 핵심 영역이다.

즉, 해결된 항목보다 남은 항목의 성격이 더 무겁다.

### 6.2 다만 “이미 해결된 것”과 “부분 해결된 것”의 경계는 더 선명하게 써야 한다

기존 두 리뷰는 전반적으로 정확하지만, 실무적인 closeout 관점에서는 아래처럼 다시 구분하는 편이 더 좋다.

#### 완전 해결에 가까운 항목

- stale fast-smoke selector 제거
- generated artifact index의 inventory count drift 해소
- review archive canonicalization 저장 산출물 존재
- release-smoke full profile 저장 report 존재
- raw registry 관련 코드/테스트 반영

#### 부분 해결 또는 증적 미완성 항목

- generated artifact index fingerprint freshness
- raw registry cross-environment closure
- `make fast-smoke` full runtime pass evidence
- stable vs mtime-sensitive gate semantics의 운영 정책

#### 아직 미해결인 항목

- stable artifact contract debt
- learning readiness
- fast/full smoke evidence split
- bare pytest guided failure
- raw registry canonical artifact
- test execution summary artifact
- `release-smoke-full` alias

### 6.3 이번 실제 파일 대조에서 가장 유의미한 추가 포인트

이번 대조에서 가장 의미 있는 추가 포인트는 다음 세 가지다.

1. **learning evidence의 실제 위치가 `auto-improve-readiness.json` 안이라는 점**
   - 후속 보고서에는 이 실제 evidence 경로를 명시하는 편이 낫다.

2. **artifact freshness 저장값(34)과 live 재생성 가능값(91)을 강하게 구분해야 한다는 점**
   - 현 저장본만 읽는 독자는 34만 보게 된다.
   - live 재생성 근거를 쓸 때는 반드시 “재생성 기준”임을 붙여야 한다.

3. **fast/full split은 코드 구조보다 운영 증적 관리가 더 뒤처져 있다는 점**
   - 이미 코드 상수와 타깃 일부는 있지만, 저장 artifact 정책이 이를 따라오지 못하고 있다.

---

## 7. 개선 권고안

### 7.1 최우선 개선안 (즉시 반영 권장)

#### A. Generated artifact index를 “마지막 writer”로 고정

현재 상태에서 가장 실무적으로 먼저 닫아야 할 것은 `generated-artifact-index.json`의 최종 freshness다.

권고:

- release-smoke 갱신 뒤에 generated index를 반드시 마지막에 생성
- CI에서 `regenerated == stored`를 강제
- count mismatch뿐 아니라 `input_fingerprints`, `source_tree_fingerprint` mismatch도 fail 처리

#### B. Stable debt의 safe tranche부터 먼저 줄이기

현재 큰 blocker는 stable debt다. 하지만 71건 전체를 한 번에 다루기보다 아래 순서가 현실적이다.

1. `missing_schema 13건` 중 safe-to-backfill 10건 우선 정리
2. `ops_reports` owner 7건 중 safe subset 우선 정리
3. 이후 mtime-sensitive / sensitive 항목 분리 처리

#### C. Learning readiness evidence를 별도 closeout 패키지로 정리

이 항목은 다른 blocker와 달리 “문서 정리”만으로 닫히지 않는다. 따라서 명시적으로 하나의 closeout run이 필요하다.

완료 기준 권고:

- `attempts_considered >= 10`
- `session_calibration_status != no_session_context`
- `telemetry_coverage_ratio > 0`
- `likely_to_learn == true` 또는 named blocker 확정

### 7.2 단기 구조 개선안

#### D. Fast/full smoke 증적 정책 완결

권고:

- `release-smoke-report-fast.json`와 `release-smoke-report-full.json`를 분리 보관하거나,
- fast report를 아예 비저장 ephemeral artifact로 선언
- 어느 쪽이든 README / Makefile / test guard가 같은 정책을 말하도록 정렬
- `release-smoke-full:` alias 추가

#### E. Raw registry matrix artifact 도입

권고 파일:

- `ops/reports/raw-registry-preflight-report.json`

권장 최소 필드:

- `extraction_tool`
- `locale`
- `entry_count`
- `error_count`
- `warning_count`
- `path_alias_match_count`
- `content_hash_fallback_count`
- `unsupported_environment`

#### F. Test execution summary artifact 도입

권고 파일:

- `ops/reports/test-execution-summary.json`

필요 이유:

- 현재처럼 full runtime이 timeout이나 환경 cap에 걸릴 때, “실패”와 “미완주”를 분리할 수 있다.
- selector-level pass, collect-only pass, full runtime inconclusive를 동시에 기록할 수 있다.

### 7.3 보고서 자체 품질 개선안

#### G. “stored 값”과 “live regenerated 값”을 시각적으로 분리

다음 표기 규칙을 권장한다.

- `stored:` checked-in artifact 값
- `live:` 재생성 값
- 둘이 다를 경우 `drift:` 항목 별도 표기

이 구분이 분명해지면 artifact freshness 서술의 해석 오류가 크게 줄어든다.

#### H. 실제 evidence file path를 각 주장 옆에 병기

예시:

- learning readiness → `ops/reports/auto-improve-readiness.json`
- stable debt → `ops/reports/artifact-freshness-report.json`
- archive parity → `ops/reports/review-archive-report.json`
- full smoke evidence → `ops/reports/release-smoke-report.json`

#### I. “해결”, “부분 해결”, “증적 미완성”, “미해결”을 별도 태그로 사용

현재 리뷰들은 대체로 정확하지만, 운영 closeout에서는 이 네 상태가 다르다.

권장 태그:

- `resolved`
- `partially_resolved`
- `evidence_incomplete`
- `unresolved`

이렇게 나누면 fast-smoke나 raw registry처럼 “문제 자체는 줄었지만 증적 체계가 아직 불완전한 항목”을 더 정확하게 표현할 수 있다.

#### J. 실제 확인 시점과 확인 범위를 더 명시

이번처럼 ZIP SHA가 달라질 수 있는 프로젝트에서는 보고서마다 최소한 아래 메타데이터를 고정하는 것이 좋다.

- `review_basis.zip_sha256`
- `review_basis.entry_count`
- `review_basis.file_count`
- `verified_artifacts`
- `not_reverified_items`

---

## 8. 지금 시점의 권장 실행 순서

### Phase 1 — release blocker 직접 축소

1. `generated-artifact-index.json` final refresh + guard 고정
2. stable debt safe tranche 축소 (`missing_schema 10` + safe ops_reports subset)
3. learning readiness closeout run 수행
4. `release-smoke-full` alias 및 smoke evidence split 정책 확정

### Phase 2 — 증적 체계 보강

5. `raw-registry-preflight-report.json` 도입
6. `test-execution-summary.json` 도입
7. bare pytest guided failure 도입

### Phase 3 — 보고서 체계 개선

8. stored/live/drift 3분법 도입
9. evidence path 병기
10. `resolved / partially_resolved / evidence_incomplete / unresolved` 상태 태그 표준화

---

## 9. 최종 종합 판정

```text
current_snapshot_status            = progressed_but_still_not_release_ready
zip_sha256                         = bf3b4433aeec89c7aa54d200c34bcfe8aac8d9735e443822bc87cc02b8657a6f
inventory_count_drift              = resolved
generated_index_fingerprint        = partially_resolved_but_still_suspect
fast_smoke_selector_drift          = resolved
fast_smoke_full_runtime_evidence   = incomplete
raw_registry_acute_mismatch        = weakened_in_current_environment
raw_registry_cross_env_evidence    = incomplete
stable_artifact_contract_debt      = unresolved
learning_readiness                 = unresolved
release_smoke_full_report          = resolved
release_smoke_fast_report_storage  = unresolved
release_smoke_full_alias           = unresolved
test_execution_summary             = unresolved
bare_pytest_guided_failure         = unresolved
overall_release_confidence         = not_release_ready
```

한 줄로 요약하면 다음과 같다.

**두 리뷰의 큰 결론은 타당하며, 실제 ZIP 기준으로도 “상당히 전진했지만 아직 release-ready는 아닌 상태”가 맞다. 다만 현재 시점의 가장 중요한 개선 포인트는 더 이상 selector drift나 단순 count drift가 아니라, stable artifact debt·learning readiness·증적 artifact 체계의 완결성 쪽에 있다.**

---

## 10. 최종 권고

현재 단계에서 가장 효과가 큰 한 가지 조합은 아래다.

1. `generated-artifact-index.json` freshness 닫기
2. `missing_schema`와 `ops_reports` safe tranche 줄이기
3. learning readiness closeout run으로 `learning_uncertain`를 정면 해결하기

이 세 가지가 닫히기 전에는 보고서가 아무리 좋아져도 release-ready 판정은 바뀌지 않는다. 반대로 이 세 가지가 먼저 닫히면, 나머지 `fast/full profile evidence split`, `raw registry matrix artifact`, `test execution summary`, `bare pytest guided failure`는 비교적 예측 가능하게 후속 정리할 수 있다.
