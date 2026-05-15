# LLM Wiki vNext 두 통합 리뷰 교차대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-03 (Asia/Seoul) |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_dual_review_crosscheck_improvement_report_20260503.md` |
| 신규 검토 대상 1 | `llmwiki_integrated_review_report_20260503.md` |
| 신규 검토 대상 2 | `LLM Wiki vNext 통합 리뷰 보고서.md` |
| 기존 기준 리뷰 | `external-reports/llm_wiki_vnext_review_reconciliation_improvement_report_20260502.md` |
| 기존 비교 리뷰 | `external-reports/llmwiki_integrated_reviews_crosscheck_improvement_report_20260503.md` |
| 실제 대조 ZIP | `LLMwiki(3).zip` |
| 실제 ZIP SHA-256 | `ac6289d58f95422819b760db745f73cc970dbc94fb8735188958927048fc3898` |
| 최종 판정 | **두 신규 리뷰의 큰 결론은 실제 파일과 대체로 부합한다. 다만 둘 다 독립 증거라기보다 동일한 후속 리뷰 묶음을 재편집한 통합 문서군에 가깝고, 현재 실제 상태는 여전히 `conditional_pass`이며 clean release / machine release는 불가하다.** |

---

## 1. 목적과 판정 기준

본 보고서는 새로 제공된 두 개의 통합 리뷰 문서를 누락 없이 읽고, 기존 리뷰들과 실제 ZIP 내부 파일 상태를 다시 맞대조하여 다음 네 가지를 분리해 정리하는 데 목적이 있다.

1. 두 신규 리뷰가 공통으로 정확하게 포착한 사실
2. 두 신규 리뷰 중 한쪽만 상대적으로 더 잘 포착한 사실
3. 실제 파일과 맞지 않거나 보정이 필요한 표현
4. 기준 리뷰 이후 완료된 작업, 남은 작업, 이번 대조에서 다시 강화된 개선 방안

판정의 우선순위는 다음과 같이 두었다.

- **최우선**: 실제 ZIP 내부 파일, Makefile, `pyproject.toml`, `ops/reports/*.json`, `ops/script-output-surfaces.json`, `tmp/*.json`, 실제 재실행 결과
- **그다음**: 기준 리뷰와 기존 비교 리뷰
- **마지막**: 두 신규 리뷰의 서술 방식과 해석

즉, 문서의 문장 자체보다 현재 ZIP이 실제로 무엇을 말하는지가 최종 판정의 기준이다.

---

## 2. 검토한 문서와 실제 파일 범위

### 2.1 직접 검토한 신규 리뷰 2건

#### A. `llmwiki_integrated_review_report_20260503.md`
- 구조가 더 길고 세부적이다.
- 완료 작업, 현재 release evidence 상태, fingerprint 계열 혼재, blocker 세분화, 개선 방안 통합, DoD, 우선순위 계획까지 포함한다.
- 사실상 **세 후속 리뷰(Delta / Followup / Audit)를 자세히 다시 합성한 버전**이다.

#### B. `LLM Wiki vNext 통합 리뷰 보고서.md`
- Executive Summary 중심으로 더 읽기 쉽게 재구성되어 있다.
- 문서 성격상 A보다 짧고, 핵심 메시지와 우선순위 전달에는 유리하다.
- 다만 세부 근거의 깊이는 A보다 얕고, 일부 편집 품질 문제도 있다.

### 2.2 기존 리뷰

이번 대조에서 참고한 기존 리뷰는 최소 다음 두 갈래다.

1. **기준 리뷰**: `external-reports/llm_wiki_vnext_review_reconciliation_improvement_report_20260502.md`
   - 2026-05-02 시점의 기준선 역할
   - 당시 P0 성격의 문제들(Ruff/import fallback, closeout lineage, batch manifest finalizer 편입, accepted risk clean lane, test summary 대표성 부족 등)을 정리한 문서

2. **기존 비교 리뷰**: `external-reports/llmwiki_integrated_reviews_crosscheck_improvement_report_20260503.md`
   - 이름상 현재 요청과 가장 가까운 선행 문서이나, 실제로는 **현재 ZIP과 다른 체크포인트**를 보고 있다.
   - 이 문서가 기록한 ZIP SHA는 `19966884918dcba3082fceb71f8edb4916f285a143e2a361ddd9270526820144`이고, 현재 업로드 ZIP SHA는 `ac6289d58f95422819b760db745f73cc970dbc94fb8735188958927048fc3898`이다.
   - 따라서 이 문서는 **참고용 과거 비교 보고서**로는 유효하지만, 현재 ZIP의 직접 증거로 사용하면 안 된다.

### 2.3 실제 ZIP에서 직접 확인한 핵심 파일

- `Makefile`
- `pyproject.toml`
- `ops/script-output-surfaces.json`
- `ops/script-module-surfaces.json`
- `ops/reports/release-closeout-summary.json`
- `ops/reports/release-evidence-cohort.json`
- `ops/reports/release-evidence-dashboard.json`
- `ops/reports/release-closeout-batch-manifest.json`
- `ops/reports/release-lane-summary.json`
- `ops/reports/generated-artifact-index.json`
- `ops/reports/auto-improve-readiness.json`
- `ops/reports/learning-readiness-signoff.json`
- `ops/reports/learning-readiness-signoff-revalidation.json`
- `ops/reports/artifact-freshness-report.json`
- `tmp/*.json`
- `tests/test_script_module_surface_contract.py`

---

## 3. 실제 ZIP 상태 재확인

### 3.1 ZIP 인벤토리

실제 `LLMwiki(3).zip`에서 확인한 값은 다음과 같다.

| 항목 | 실제 확인값 |
| --- | ---: |
| ZIP SHA-256 | `ac6289d58f95422819b760db745f73cc970dbc94fb8735188958927048fc3898` |
| 전체 엔트리 | 1,802 |
| 일반 파일 | 1,708 |
| 디렉터리 | 94 |
| 비압축 총량 | 243,134,691 bytes |
| 압축 총량 | 191,274,175 bytes |
| ZIP timestamp 범위 | `2026-04-12 16:03:06` ~ `2026-05-03 13:07:54` |

이 값은 두 신규 리뷰의 핵심 숫자와 대체로 일치한다. 반면 기존 비교 리뷰(`external-reports/llmwiki_integrated_reviews_crosscheck_improvement_report_20260503.md`)가 전제한 ZIP은 다른 체크포인트이므로 숫자가 다르다.

### 3.2 Release authority 핵심 값

`ops/reports/release-closeout-summary.json`의 실제 값은 다음과 같다.

| 필드 | 값 |
| --- | --- |
| `generated_at` | `2026-05-03T03:00:31Z` |
| `status` | `pass` |
| `source_tree_fingerprint` | `1dd874641849806760d30df46ae700ebf21298f08c603ff5c451044193ecd2e2` |
| `release_readiness_state` | `conditional_pass` |
| `clean_release_ready` | `false` |
| `conditional_release_ready` | `true` |
| `machine_release_allowed` | `false` |
| `operator_release_allowed` | `true` |
| `requires_accepted_risk_review` | `true` |

즉 현재 상태는 두 신규 리뷰가 공통으로 말한 것처럼 **clean release 불가, machine release 불가, operator-mediated conditional release만 가능**이다.

### 3.3 Release evidence cohort: checked-in과 live check의 차이

체크인된 `ops/reports/release-evidence-cohort.json`은 03:00:31Z 시점에 생성되어 `source_tree_fingerprint=1dd874...`를 기록한다. 그러나 실제 재실행 결과는 아래와 같이 실패한다.

#### 실제 재실행 명령

```bash
make release-evidence-cohort-check
```

#### 실제 재실행 결과 핵심

| 필드 | 값 |
| --- | --- |
| `status` | `fail` |
| `source_tree_fingerprint` | `6104207594dd4514c438ca78659649024436350b1c786b3586437ccf66fd1132` |
| `summary.strict_same_fingerprint` | `false` |
| `summary.component_fingerprint_count` | `2` |
| `cohort.fingerprints` | `1dd874...`, `e61d9d...` |
| `clean_lane_contract.status` | `fail` |
| `clean_lane_contract.failed_conditions` | `zero_accepted_risk_family`, `strict_cohort_pass`, `release_closeout_clean` |

이 점에서 두 신규 리뷰의 핵심 진단은 맞다. 다만 실제 live check JSON에서는 일부 값이 top-level이 아니라 `summary` 또는 `cohort` 아래에 있으므로, 기술 문서 작성 시 필드 경로를 더 정확히 써 주는 편이 좋다.

### 3.4 Batch manifest 실제 상태

`ops/reports/release-closeout-batch-manifest.json`의 실제 값은 다음과 같다.

| 필드 | 값 |
| --- | --- |
| `generated_at` | `2026-05-03T04:05:22Z` |
| `status` | `fail` |
| `source_tree_fingerprint` | `e61d9d8e0b4c22b576872dbdf9493653c2f2e5a48c5ceb320ee6a77d6d9e5e72` |
| `batch_integrity_status` | `pass` |
| `release_authority_status` | `conditional_pass` |
| `finality.is_final` | `true` |

실제 `--check` 재실행 결과는 실패한다.

```bash
python -m ops.scripts.release_closeout_batch_manifest --vault . --check
```

실제 오류:

```text
batch manifest check failed: content differs from ops/reports/release-closeout-batch-manifest.json
```

### 3.5 Batch manifest digest 대조 결과

직접 `digest`를 다시 계산해 확인한 결과, batch manifest가 열거한 8개 required artifact 중 **현재 파일 digest와 일치하는 것은 6개**, 불일치하는 것은 2개였다.

| artifact path | 현재 digest 일치 여부 | 관찰 |
| --- | :---: | --- |
| `ops/reports/release-smoke-report.json` | ❌ | batch에 기록된 내용과 현재 파일이 다름 |
| `ops/reports/generated-artifact-index.json` | ❌ | batch에 기록된 내용과 현재 파일이 다름 |
| `ops/reports/artifact-freshness-report.json` | ✅ | 일치 |
| `ops/reports/test-execution-summary.json` | ✅ | 일치 |
| `ops/reports/release-closeout-summary.json` | ✅ | 일치 |
| `ops/reports/learning-readiness-signoff-revalidation.json` | ✅ | 일치 |
| `ops/reports/release-evidence-cohort.json` | ✅ | 일치 |
| `ops/reports/release-evidence-dashboard.json` | ✅ | 일치 |

즉 두 신규 리뷰가 공통으로 지적한 “batch finality와 실제 현재 파일 간 괴리”는 실제로 확인된다. 다만 보다 정밀하게 표현하면 **8개 전체가 어긋난 것이 아니라 2개만 어긋난다**.

### 3.6 Console script registry drift 실제 확인

직접 테스트와 정적 계산으로 확인한 결과는 다음과 같다.

- `pyproject.toml`의 `[project.scripts]` 개수: **52**
- `ops/script-output-surfaces.json`에서 `direct_fallback_eligible=true`이면서 실제 파일 본문에 `direct script fallback` 마커가 있는 direct wrapper expected set: **53**
- 누락된 command: **`llm-wiki-release-lane-summary`**
- 기대 target: **`ops.scripts.release_lane_summary:main`**

실제 실패 재현:

```bash
python -m pytest tests/test_script_module_surface_contract.py -q
```

핵심 실패 원인:
- `expected 53` vs `actual 52`
- `missing_in_actual = ['llm-wiki-release-lane-summary']`

이 항목은 두 신규 리뷰가 공통으로 정확하게 잡았다.

### 3.7 tmp 후보 파일과 Makefile verify 충돌

실제 ZIP에는 다음 파일이 포함되어 있다.

- `tmp/generated-artifact-index.candidate.json`
- `tmp/script-output-surfaces.candidate.json`

그리고 실제 재실행 결과:

```bash
make release-closeout-batch-manifest-verify
```

오류:

```text
tmp/*.json present; diagnostic workspace not clean
```

즉 두 신규 리뷰가 강조한 “release verification clean-room과 diagnostic scratch가 섞여 있다”는 문제는 실제 파일과 완전히 일치한다.

### 3.8 Learning readiness 실제 값

`ops/reports/auto-improve-readiness.json`의 실제 학습 관련 값은 다음과 같다.

| 필드 | 값 |
| --- | --- |
| `learning_readiness.status` | `learning_uncertain` |
| `learning_readiness.likely_to_learn` | `false` |
| `can_execute_trial` | `true` |
| `can_promote_result` | `false` |
| `metrics.attempts_considered` | `7` |
| `metrics.min_attempts_considered` | `10` |
| `metrics.telemetry_coverage_ratio` | `0.0` |
| `metrics.rework_count` | `2` |
| `metrics.hold_moving_average` | `0.2857` |
| `metrics.defect_escape_pair_count` | `1` |

따라서 “learning readiness는 signoff artifact가 추가되었지만 실제 promotion 가능 상태는 아니다”라는 두 신규 리뷰의 핵심 결론도 맞다.

---

## 4. 두 신규 리뷰의 공통 강점

### 4.1 최종 판정은 실제와 부합한다

두 문서 모두 결론적으로 현재 스냅샷을 `conditional_pass`로 보며, clean release 및 machine release는 불가하다고 정리한다. 이것은 실제 release-closeout-summary 값과 일치한다.

### 4.2 완료된 작업과 남은 작업을 구분하려는 시도가 적절하다

두 문서는 모두 다음과 같은 패턴을 취한다.

- 기준 리뷰의 P0 전부가 그대로 남은 것은 아니다.
- Ruff/import fallback, batch manifest finalizer 편입, release lane summary artifact 도입, signoff/revalidation 도입 등은 **실제로 진전이 있었다**.
- 그러나 그 진전이 clean release로 이어진 것은 아니며, lineage/fingerprint/registry/accepted-risk/learning 측면의 핵심 blocker는 남아 있다.

이 분류 방식은 실제 ZIP 상태와 잘 맞는다.

### 4.3 다중 fingerprint 계열 문제를 정확히 짚었다

실제 파일을 보면 최소 두 개의 canonical fingerprint 계열이 공존한다.

- 03:00대 artifact들의 `1dd874...`
- 04:05~04:06대 artifact들의 `e61d9d...`

그리고 live check 결과는 현재 소스 트리 fingerprint를 `61042075...`로 본다. 따라서 두 리뷰가 “단일 봉인 상태가 아니다”라고 본 것은 타당하다.

### 4.4 단순 lint/pass 관점이 아니라 release governance 관점으로 읽었다

두 문서는 단순히 테스트 몇 개가 통과했는지 여부보다,

- finality
- lineage
- authority snapshot
- accepted risk semantics
- batch integrity
- clean lane / conditional lane 분리

같은 운영 관점의 문제를 전면에 둔다. 이 접근은 실제 repo의 핵심 리스크를 더 잘 반영한다.

---

## 5. 두 신규 리뷰의 차이와 상대 평가

### 5.1 A 문서가 더 강한 점

`llmwiki_integrated_review_report_20260503.md`는 다음 측면에서 더 강하다.

1. **완료분과 미완료분의 분리**가 더 명시적이다.
2. `release-closeout-summary`, `cohort`, `dashboard`, `batch manifest`, `generated-artifact-index`를 각각 따로 풀어 쓴다.
3. blocker가 더 세분화되어 있어 실행 계획으로 곧바로 이어지기 쉽다.
4. 개선 방안이 Delta / Followup / Audit 출처별로 더 촘촘하게 정리되어 있다.
5. DoD와 우선순위 계획이 구조적으로 정리되어 있어 운영 문서로 재사용하기 좋다.

실제 개선 보고서의 바탕 문서로는 A가 더 적합하다.

### 5.2 B 문서가 더 강한 점

`LLM Wiki vNext 통합 리뷰 보고서.md`는 다음 측면에서 강점이 있다.

1. Executive Summary가 좋아서 의사결정자에게 빠르게 전달하기 쉽다.
2. 세 리뷰의 방법론 차이와 고유 기여를 설명하는 문단이 읽기 쉽다.
3. 핵심 판단과 우선순위를 더 응축해서 전달한다.
4. “문서의 역할 차이”를 강조해 독자가 각 리뷰를 어떤 시선으로 읽어야 하는지 이해하기 쉽다.

요약본이나 briefing 문서로는 B의 구성력이 좋다.

### 5.3 둘 다 가진 한계

두 문서는 모두 내용상 매우 가까운 계열이며, 동일한 세 후속 리뷰 묶음(Delta / Followup / Audit)을 다시 통합한 결과다. 따라서 **둘을 서로 독립적인 신규 증거 2건으로 세면 안 된다**.

보다 정확한 평가는 다음과 같다.

- 둘은 **동일 문제공간을 같은 근거층으로 재구성한 2개의 편집 버전**이다.
- 따라서 “A도 이렇게 말하고 B도 이렇게 말한다”는 사실만으로 신뢰도가 두 배가 되지는 않는다.
- 진짜 판단 근거는 결국 실제 ZIP 내부 파일과 재실행 결과다.

---

## 6. 실제 파일과 맞지 않거나 보정이 필요한 부분

### 6.1 기존 비교 리뷰는 현재 ZIP의 직접 증거가 아니다

`external-reports/llmwiki_integrated_reviews_crosscheck_improvement_report_20260503.md`는 이름상 매우 유사하지만 다른 ZIP 체크포인트를 전제로 한다.

- 그 문서의 ZIP SHA: `19966884...`
- 현재 ZIP SHA: `ac6289d5...`

따라서 이 문서는 **현재 요청에 대한 참고 문헌**으로는 사용할 수 있으나, 현재 업로드 ZIP의 숫자나 currentness를 직접 대표하는 문서로 쓰면 안 된다.

### 6.2 B 문서의 편집 품질 이슈

`LLM Wiki vNext 통합 리뷰 보고서.md`에는 제목부 판정 문구에 `조걸부 통과`처럼 보이는 오탈자가 있다. 의미는 `conditional_pass` 설명이므로 결론 자체는 이해되지만, 최종 보고서로 재배포하기에는 편집 품질 보정이 필요하다.

### 6.3 live cohort check 필드 경로는 더 정확하게 써야 한다

두 문서 모두 큰 의미는 맞지만, 실제 live check JSON에서는 다음 값들이 top-level이 아니라 nested path에 있다.

- `summary.strict_same_fingerprint`
- `summary.component_fingerprint_count`
- `cohort.fingerprints`

후속 보고서에서는 이 점을 분명히 적는 편이 좋다.

### 6.4 batch manifest digest mismatch는 “2건”으로 한정해서 쓰는 편이 더 정확하다

두 문서 모두 핵심 문제를 정확히 잡았지만, 후속 산출물에서는 “batch가 봉인한 required artifact 전체가 뒤틀렸다”로 일반화하지 말고 다음처럼 쓰는 것이 가장 정확하다.

- required artifact 8개 중 6개는 일치
- `release-smoke-report.json`, `generated-artifact-index.json` 2개만 불일치

이렇게 쓰면 실제 조치 범위도 더 분명해진다.

### 6.5 Learning readiness 값은 nested metrics 기준으로 써야 한다

일부 서술은 `can_execute_trial`, `can_promote_result`, `attempts_considered`, `telemetry_coverage_ratio` 등을 top-level처럼 읽히게 만들 수 있다. 실제로는 `auto-improve-readiness.json` 내부 구조상 다음처럼 층위가 나뉜다.

- `can_execute_trial`, `can_promote_result`: top-level
- `learning_readiness.metrics.*`: 세부 수치

기술 보고서에서는 이 구분을 보존하는 것이 좋다.

---

## 7. 기준 리뷰 대비 실제로 완료된 작업

기준 리뷰(2026-05-02)가 제기한 문제 중 현재 ZIP에서 **실제로 진전이 확인되는 항목**은 다음과 같다.

### 7.1 Ruff / import fallback 정리

- `release_closeout_batch_manifest.py`의 unused import 문제는 현재 주요 결론상 해소된 것으로 보인다.
- 두 신규 리뷰 모두 이를 완료 작업으로 잡고 있으며, 현재 상태와 충돌하지 않는다.

### 7.2 Batch manifest의 closeout finalizer 편입

Makefile에서 `release-evidence-closeout` 말미에 아래 흐름이 존재한다.

```text
report-contract-finalization
→ release-closeout-batch-manifest-promote
→ release-closeout-batch-manifest-verify
```

즉 batch manifest를 closeout 마지막 canonical 단계로 넣으려는 구조적 조치는 실제로 반영되어 있다.

### 7.3 Release lane summary artifact 도입

현재 실제 repo에는 다음이 존재한다.

- `ops/scripts/release_lane_summary.py`
- `ops/reports/release-lane-summary.json`
- `ops/schemas/release-lane-summary.schema.json`
- `tests/test_release_lane_summary.py`
- `ops/policies/release-lane-definitions.json`

즉 vocabulary 정리 방향 자체는 구현되었다.

### 7.4 Learning readiness signoff / revalidation 도입

- `ops/reports/learning-readiness-signoff.json`
- `ops/reports/learning-readiness-signoff-revalidation.json`

둘 다 실제로 존재한다. 다만 이것은 **학습 readiness 해결**이 아니라 **학습 blocker를 operator-reviewed risk로 감싸는 장치 도입**으로 이해해야 한다.

### 7.5 Artifact freshness 계층 안정화

`ops/reports/artifact-freshness-report.json`은 현재 `status=pass`다. 즉 freshness 계층은 기준 리뷰 시점보다 정리된 것으로 보인다.

---

## 8. 현재 남아 있는 핵심 작업분

### 8.1 P0 — 현재 clean release를 직접 막는 항목

#### P0-1. `llm-wiki-release-lane-summary` 엔트리포인트 추가 또는 역할 재정의

현재 상태:
- expected direct wrapper 53
- actual project scripts 52
- missing command: `llm-wiki-release-lane-summary`

권고:
- 우선안: `pyproject.toml`에 `llm-wiki-release-lane-summary = "ops.scripts.release_lane_summary:main"` 추가
- 대안: 해당 스크립트를 direct wrapper가 아닌 pure module writer로 재분류

#### P0-2. closeout chain을 단일 frozen fingerprint window로 다시 생성

현재 상태:
- 03:00대 core artifact는 `1dd874...`
- 04:05~04:06대 artifact는 `e61d9d...`
- live check는 현재 tree를 `61042075...`로 계산

권고:
- closeout 시작 시점의 frozen fingerprint를 1회 계산
- smoke / index / dashboard / cohort / closeout-summary / batch manifest를 그 한 윈도우 안에서만 재생성
- 그 이후 canonical write 금지

#### P0-3. batch manifest를 다시 생성하고 `--check`를 통과시킬 것

현재 상태:
- `batch_integrity_status=pass`
- `release_authority_status=conditional_pass`
- 그러나 `--check`는 fail
- current digest mismatch 2건 존재

권고:
- `release-smoke-report.json`, `generated-artifact-index.json` 생성 순서를 closeout의 frozen 단계 안으로 넣고 batch를 다시 봉인
- `batch_creation_integrity_status`와 `current_file_digest_status`를 분리하는 schema 보강도 같이 진행

#### P0-4. `tmp/*.json`를 release verification clean-room에서 분리

현재 상태:
- ZIP 안에 candidate tmp JSON이 포함되어 있음
- verify target은 tmp가 없어야 한다고 가정함

권고:
- `release-evidence` export 모드에서는 tmp 후보 파일 제외
- 또는 verify target이 export mode를 인지하여 diagnostic ZIP과 release ZIP을 다르게 처리

#### P0-5. accepted risk를 clean lane과 conditional lane에서 명확히 분리

현재 상태:
- `conditional_pass`는 유지 가능
- 그러나 clean lane은 accepted risk family 2건 때문에 구조적으로 막힘

권고:
- clean lane: accepted risk family 0만 허용
- conditional lane: operator-reviewed accepted risk만 허용
- batch / dashboard / lane summary / closeout summary가 같은 vocabulary를 사용하도록 맞춤

### 8.2 P1 — 단기 안정화

#### P1-1. Batch manifest `status` 의미 분리

현재는 다음이 동시에 존재한다.

- `status=fail`
- `batch_integrity_status=pass`
- `release_authority_status=conditional_pass`

이 조합은 operator에게 해석 부담을 준다. 최소한 아래처럼 분리하는 것이 좋다.

- `batch_integrity_status`
- `release_authority_status`
- `machine_release_allowed`
- `operator_release_allowed`
- `legacy_status` 또는 `status` 재정의

#### P1-2. script registry의 단일 source of truth 확정

현재 서로 drift 가능성이 있는 지점:
- `pyproject.toml [project.scripts]`
- `ops/script-output-surfaces.json`
- `ops/script-module-surfaces.json`
- 실제 `ops/scripts/*.py`

권고:
- source of truth를 한 곳으로 정하고 나머지는 생성물로 취급
- pre-commit/CI에서 자동 비교

#### P1-3. long-running suite 분리

문서상 지적처럼 다음 suite는 느리거나 불안정하다.

- `test_writer_output_paths.py`
- `test_generated_report_contracts.py`
- `test_release_closeout_batch_manifest.py`

권고:
- `fast_contract`
- `regeneration`
- `release_finalization`

같은 lane으로 나눠, release blocking test와 forensic test를 분리

#### P1-4. system log finalization barrier

`system/system-log.md`가 release source fingerprint에 영향을 주는 구조라면,

- report regeneration 전에 append를 끝내거나
- release-source 제외 후 별도 audit fingerprint를 관리해야 한다.

### 8.3 P2 — 중기 구조 개선

#### P2-1. report provenance guard

보고서 안에 ZIP SHA와 인벤토리를 적는다면, export 시점에 현재 ZIP과 자동 대조해야 한다. 현재처럼 오래된 비교 보고서가 새 ZIP 안에 남아 있으면 근거 오인이 생긴다.

#### P2-2. external report reference manifest

현재 repo는 외부 리뷰 문서가 많고, 어떤 문서가 어떤 ZIP 체크포인트를 본 것인지 분리 관리가 필요하다.

#### P2-3. release package mode 분리

- `release-evidence`
- `review-full`
- `local-vault-full`

같이 용도를 명확히 나누면 tmp/diagnostic/archival artifact가 릴리스 판단을 오염시키는 문제를 줄일 수 있다.

---

## 9. 두 신규 리뷰를 통합해 채택할 권장 결론

### 9.1 채택할 것

두 신규 리뷰에서 다음 결론은 채택해도 된다.

1. 현재 상태는 `conditional_pass`다.
2. clean release와 machine release는 아직 불가하다.
3. 기준 리뷰 이후 상당한 진전이 실제로 있었다.
4. 하지만 lineage/fingerprint/finality/registry/accepted-risk/learning 측면의 핵심 문제는 아직 남아 있다.
5. `llm-wiki-release-lane-summary` 누락과 batch manifest live check 실패는 즉시 해결해야 할 실무 항목이다.

### 9.2 보정해서 채택할 것

다음은 방향은 맞지만 표현을 보정하는 것이 좋다.

1. **fingerprint 관련 필드 경로**: live check JSON에서 일부 값은 nested path 기준으로 써야 한다.
2. **batch mismatch 범위**: “전체 drift”보다 “현재 확인된 required artifact 8개 중 2개 mismatch”로 쓰는 편이 정확하다.
3. **learning metrics 층위**: top-level vs nested metrics를 구분해서 써야 한다.
4. **기존 비교 리뷰 활용 방식**: 현재 ZIP의 직접 증거가 아니라 과거 체크포인트 문서라는 점을 명시해야 한다.

### 9.3 버릴 것

다음 해석은 버리거나 약화해야 한다.

1. 두 신규 리뷰를 서로 독립적인 신규 증거 2건으로 세는 해석
2. 기존 비교 리뷰(`external-reports/llmwiki_integrated_reviews_crosscheck_improvement_report_20260503.md`)를 현재 ZIP의 direct evidence로 간주하는 해석
3. “이미 clean release 직전”이라는 낙관적 표현

---

## 10. 최종 결론

이번 대조의 결론은 명확하다.

- 새로 제공된 두 통합 리뷰는 **핵심 결론 면에서는 실제 ZIP과 대체로 잘 맞는다.**
- 특히 `conditional_pass 유지`, `clean/machine release 불가`, `다중 fingerprint 계열 공존`, `batch manifest live check 실패`, `release_lane_summary 엔트리포인트 누락`, `tmp candidate로 인한 verify 실패`, `learning readiness 미해결`은 실제 파일과 재실행 결과가 모두 뒷받침한다.
- 다만 두 문서는 **같은 세 후속 리뷰 묶음을 다른 방식으로 재편집한 문서군**으로 보는 편이 더 정확하며, 서로를 독립된 새로운 증거로 간주하면 안 된다.
- 또한 기존 비교 리뷰는 현재 ZIP이 아닌 이전 체크포인트를 본 문서이므로, 현재 상태 판단에는 직접 증거가 아니라 참고자료로만 취급해야 한다.

최종적으로 현재 repo는 다음 한 문장으로 정리하는 것이 가장 정확하다.

> **이 ZIP은 기준 리뷰 이후 여러 핵심 조치를 반영해 `conditional_pass` 상태까지는 올라왔지만, closeout lineage를 단일 frozen fingerprint window로 다시 봉인하고, batch manifest 및 script registry drift를 정리하기 전까지는 clean release 및 machine release로 승격될 수 없다.**

---

## 11. 바로 실행할 최소 작업 5개

1. `pyproject.toml`에 `llm-wiki-release-lane-summary` entrypoint 추가 또는 `release_lane_summary.py`를 pure module writer로 재분류
2. `tmp/*.json`를 release package에서 제외하거나 verify target을 export mode aware하게 수정
3. `release-smoke-report.json`과 `generated-artifact-index.json`까지 포함한 closeout chain을 단일 frozen fingerprint로 재생성
4. `release_closeout_batch_manifest --check`와 `make release-evidence-cohort-check`를 모두 통과하는 새 canonical batch 재봉인
5. accepted risk vocabulary와 batch manifest status semantics를 통일해 clean lane / conditional lane 해석을 혼동 없게 정리

