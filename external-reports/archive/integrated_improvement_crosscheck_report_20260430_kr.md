# LLM Wiki vNext 개선 보고서

- **작성일:** 2026-04-30 (Asia/Seoul)
- **작성 언어:** 한국어
- **파일명:** `integrated_improvement_crosscheck_report_20260430_kr.md`
- **검토 대상 ZIP:** `LLM Wiki vNext(64).zip`
- **검토 ZIP SHA-256:** `eef6544f6b4bc5ac0227fd8a552b575f94a2b1153c8cef94d16a53f765bb3aa8`
- **직접 대조한 업로드 리뷰:**
  1. `Post-Dual-Review Cross-check Follow-up Integrated Report_20260430.md`
  2. `integrated_review_report_20260430.md`
- **대조한 기존 리뷰:** `external-reports/llm_wiki_vnext_dual_integrated_review_crosscheck_improvement_report_20260430.md`
- **최종 종합 판정:** **`materially_advanced_but_not_release_ready`**

---

## 0. 결론 요약

두 개의 신규 리뷰는 핵심 판단에서 서로 충돌하지 않는다. 둘 다 같은 결론에 도달한다. 즉, **기준 리뷰 이후 evidence system 구현은 분명히 진전되었지만, 현재 ZIP은 아직 release-ready가 아니다.**

실제 ZIP과 재대조한 결과, 이 결론은 그대로 유지된다. 다만 이번 재검증을 통해 다음 사실이 더 명확해졌다.

1. **리뷰들의 공통 결론은 실제 파일 상태와 정합적이다.**
   - `ops/scripts/learning_readiness_signoff.py`, `ops/scripts/release_evidence_cohort.py`, `ops/scripts/bootstrap_preflight.py`, `ops/scripts/raw_registry_cross_environment_evidence_bundle.py` 등 신규 surface는 실제로 존재한다.
   - 그러나 `ops/reports/learning-readiness-signoff.json`, `ops/reports/release-evidence-cohort.json`, `ops/reports/raw-registry-cross-environment-evidence-bundle.json`, `ops/reports/bootstrap-preflight-report.json`은 **원본 ZIP 기준으로 존재하지 않는다.**

2. **현재 직접 blocker는 여전히 `learning_blocked_by_review_required` 하나다.**
   - `ops/reports/release-closeout-summary.json`은 실제로 `status=fail`, `release_ready=false`, `blocker_count=1`, `accepted_risk_count=3` 상태다.
   - blocker를 닫기 위한 signoff 경로는 구현되어 있지만, 실제 signoff artifact는 없다.

3. **리뷰들이 강조한 P0/P1 과제는 실제 재실행에서도 재현된다.**
   - `make release-evidence-cohort-check` 재실행 시 strict cohort는 실제로 **실패**했다.
   - `make raw-registry-cross-environment-evidence-bundle` 재실행 시 bundle 생성도 실제로 **실패**했다.
   - `python -m ops.scripts.bootstrap_preflight --dev --json`는 현재 검토 환경에서 **pass**였다.
   - `ruff check`와 `mypy`도 핵심 신규 스크립트 4개에 대해 **pass**였다.

4. **이번 재대조에서 새로 분명해진 운영상 문제는 “실패 rerun이 canonical path를 오염시킬 수 있다”는 점이다.**
   - `release-evidence-cohort-check`와 `raw-registry-cross-environment-evidence-bundle`는 실패해도 canonical 경로(`ops/reports/...`)에 결과를 써버린다.
   - 즉, 리뷰/진단 목적으로 재실행한 실패 artifact가 release evidence와 동일한 위치에 떨어질 수 있다.
   - 이는 기존 리뷰들이 강하게 시사했지만 명시적으로 분리하지 않았던 operational hazard다.

따라서 현재 상태를 가장 정확하게 표현하면 다음과 같다.

> **LLM Wiki vNext는 기준 리뷰 이후 evidence mechanism이 실제로 확장되었지만, 현재 상태는 “release-ready 전환”이 아니라 “남은 문제를 더 기계적으로 증명할 수 있게 된 상태”에 가깝다. 즉시 닫아야 할 P0는 learning readiness blocker 해소와 ordered release evidence cohort의 실제 완성이고, P1은 raw registry per-profile evidence 완성, artifact freshness canonical mode 확정, archive apply/defer 실행이다.**

---

## 1. 검토 범위와 방법

이번 보고서는 다음 네 축을 동시에 대조했다.

### 1.1 문서 대조 축

- 업로드 리뷰 1: `Post-Dual-Review Cross-check Follow-up Integrated Report_20260430.md`
- 업로드 리뷰 2: `integrated_review_report_20260430.md`
- 기존 리뷰: `external-reports/llm_wiki_vnext_dual_integrated_review_crosscheck_improvement_report_20260430.md`

### 1.2 실제 산출물 대조 축

압축 해제 후 다음을 직접 확인했다.

- ZIP 무결성 및 SHA-256
- 기준 시각 이후 변경 파일 수와 경로 분포
- 실제 존재/부재 report, script, schema, template
- `Makefile` target 실제 선언 상태
- 주요 checked-in JSON report 핵심 수치

### 1.3 재실행 검증 축

다음 명령을 실제로 수행했다.

```bash
python -m ops.scripts.bootstrap_preflight --dev --json
make release-evidence-cohort-check
make raw-registry-cross-environment-evidence-bundle
ruff check ops/scripts/learning_readiness_signoff.py \
          ops/scripts/release_evidence_cohort.py \
          ops/scripts/bootstrap_preflight.py \
          ops/scripts/raw_registry_cross_environment_evidence_bundle.py
mypy ops/scripts/learning_readiness_signoff.py \
     ops/scripts/release_evidence_cohort.py \
     ops/scripts/bootstrap_preflight.py \
     ops/scripts/raw_registry_cross_environment_evidence_bundle.py
```

### 1.4 검증 기준

검증은 “문서에 적힌 주장”이 아니라 아래 두 가지를 기준으로 판정했다.

1. **원본 ZIP 기준 상태**: 실제로 포함되어 있는가
2. **재실행 기준 상태**: 다시 돌리면 pass/fail이 어떻게 재현되는가

이 구분은 중요하다. 원본 ZIP에는 없지만, 재실행하면 fail artifact가 생성될 수 있기 때문이다.

---

## 2. 두 신규 리뷰의 성격과 상호 관계

### 2.1 `integrated_review_report_20260430.md`

이 문서는 세 리뷰를 하나의 구조화된 통합 보고서로 정리한 성격이 강하다. 강점은 다음과 같다.

- 기준 리뷰 이후 반영된 작업을 항목별로 정리한다.
- 미해결 항목을 P0/P1/P2로 구조화한다.
- 리뷰별 고유 발견과 개선안 ID(I-01~I-21)를 체계적으로 정리한다.
- 실행 계획을 tranche 형태로 제시한다.

즉, **설명력과 구조화 수준이 높고, 운영 의사결정 문서로 읽기 좋다.**

### 2.2 `Post-Dual-Review Cross-check Follow-up Integrated Report_20260430.md`

이 문서는 더 직접적이고 운용 중심적이다. 강점은 다음과 같다.

- ZIP SHA, 기준 리뷰 SHA, 검토 범위를 더 엄밀히 적는다.
- 실제 blocker를 10개 항목으로 분해해 severity와 함께 정리한다.
- report 존재/부재와 live 재실행 결과를 더 단단하게 묶는다.
- 수치와 단계별 우선순위를 운영 체크리스트에 가깝게 제시한다.

즉, **실무 follow-up과 release gate 관점에서는 이 문서가 더 바로 쓰기 좋다.**

### 2.3 두 리뷰의 관계에 대한 판정

두 문서는 중복이 많지만 관계는 경쟁적이지 않다.

- `integrated_review_report_20260430.md`는 **프레임을 정리하는 문서**다.
- `Post-Dual-Review Cross-check Follow-up Integrated Report_20260430.md`는 **실행 우선순위를 고정하는 문서**다.

따라서 둘을 함께 보면 오히려 해석 여지가 줄어든다. 이번 실제 ZIP 대조 결과도 이 상보성을 지지한다.

---

## 3. 기존 리뷰와의 대조

기존 리뷰 `external-reports/llm_wiki_vnext_dual_integrated_review_crosscheck_improvement_report_20260430.md`의 핵심 메시지는 다음으로 요약된다.

- evidence system은 실질적으로 진전되었다.
- 현재 ZIP은 release-ready가 아니다.
- P0는 learning readiness blocker 해소다.
- 그 다음 우선순위는 ordered release evidence rerun, source-tree cohort policy, artifact freshness portability, archive candidate 처리, raw registry replay semantics 정리다.

이번에 업로드된 두 신규 리뷰는 이 기존 리뷰의 방향을 뒤집지 않는다. 오히려 다음 방식으로 **구체화**한다.

| 축 | 기존 리뷰 | 신규 리뷰 2건 | 이번 실제 검증 판정 |
|---|---|---|---|
| 최종 판정 | not release-ready | release-ready still blocked | **동일** |
| learning blocker | P0 | P0 | **실제 closeout summary로 재확인** |
| signoff 경로 | 필요 | 구현됨, artifact 부재 | **실제 파일로 재확인** |
| strict cohort | attention 성격 | fail로 명시화 | **재실행 fail로 재현** |
| artifact freshness | portability 문제 | mode 정책 문제로 구체화 | **checked-in 수치로 재확인** |
| archive lifecycle | dry-run debt | applied 0로 구체화 | **실제 report로 재확인** |
| raw registry portability | 보강 필요 | per-profile evidence 부재로 구체화 | **재실행 fail로 재현** |
| package boundary | 정리 필요 | `.obsidian`, `tmp`, review output 포함으로 구체화 | **실제 ZIP로 재확인** |

요약하면, **신규 리뷰들은 기존 리뷰를 반박하지 않고 operationally executable한 형태로 세분화했다.**

---

## 4. 실제 ZIP 무결성 및 변경분 재확인

### 4.1 ZIP 무결성

직접 계산한 ZIP 메타데이터는 다음과 같다.

| 항목 | 값 |
|---|---|
| ZIP SHA-256 | `eef6544f6b4bc5ac0227fd8a552b575f94a2b1153c8cef94d16a53f765bb3aa8` |
| entries | 1,724 |
| files | 1,638 |
| dirs | 86 |
| compressed bytes | 190,993,894 |
| uncompressed bytes | 241,747,335 |

이는 업로드 리뷰들이 적은 `1,638 files / 86 dirs / 241,747,335 bytes / SHA-256 eef654...`와 정합적이다.

### 4.2 기준 리뷰 이후 변경 파일 수 재확인

업로드 follow-up 리뷰가 제시한 기준 시각 `2026-04-30 01:54:24` 이후 변경 파일 수는 실제로 **42개**였다.

상위 분포는 다음과 같다.

| 상위 경로 | 개수 |
|---|---:|
| `ops/` | 21 |
| `tests/` | 11 |
| `tmp/` | 4 |
| `runs/` | 2 |
| `.github/` | 1 |
| `.obsidian/` | 1 |
| 루트(`Makefile`, `README.md`) | 2 |

즉, 신규 리뷰들이 말한 “기준 리뷰 이후 의미 있는 후속 작업”은 실제 ZIP 메타데이터 상으로도 뒷받침된다.

### 4.3 변경 파일의 실제 성격

42개 변경 파일은 대체로 다음 다섯 묶음으로 분류된다.

1. **새 기능 surface**
   - `ops/scripts/learning_readiness_signoff.py`
   - `ops/scripts/release_evidence_cohort.py`
   - `ops/scripts/bootstrap_preflight.py`
   - `ops/scripts/raw_registry_cross_environment_evidence_bundle.py`
   - `ops/scripts/artifact_freshness_runtime.py`
   - `ops/scripts/archive_execution_manifest.py`

2. **schema/template 보강**
   - `ops/schemas/release-evidence-cohort.schema.json`
   - `ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json`
   - `ops/schemas/archive-execution-manifest.schema.json`
   - `ops/schemas/artifact-freshness-report.schema.json`
   - `ops/templates/learning-readiness-signoff.json`

3. **checked-in report 갱신**
   - `ops/reports/release-closeout-summary.json`
   - `ops/reports/test-execution-summary.json`
   - `ops/reports/generated-artifact-index.json`
   - `ops/reports/archive-execution-manifest.json`
   - `ops/reports/artifact-freshness-report.json`
   - `ops/reports/manual-mutate-defect-registry.json`

4. **static gate / CI / 문서 보강**
   - `Makefile`
   - `.github/workflows/ci.yml`
   - `README.md`
   - `ops/README.md`
   - `ops/mypy-allowlist.txt`

5. **test 확장**
   - `tests/test_learning_readiness_signoff.py`
   - `tests/test_release_evidence_cohort.py`
   - `tests/test_bootstrap_preflight.py`
   - `tests/test_raw_registry_cross_environment_evidence_bundle.py`
   - `tests/test_artifact_freshness_runtime.py`
   - `tests/test_generated_report_contracts.py`
   - `tests/test_makefile_static_gates.py`
   - 그 외 관련 회귀 테스트들

즉, 단순 문서 추가가 아니라 **코드·스키마·테스트·리포트·문서·CI가 묶여 움직인 변경**이라는 업로드 리뷰의 해석은 타당하다.

---

## 5. 업로드 리뷰들의 핵심 주장과 실제 파일 정합성

### 5.1 정합성이 확인된 주장

아래 항목은 두 신규 리뷰와 실제 ZIP이 **같은 결론**을 내리는 항목들이다.

| 주장 | 실제 파일 대조 결과 | 판정 |
|---|---|---|
| `learning_readiness_signoff` 경로가 구현되었다 | script/schema/template 존재, report 부재 | **정합** |
| `release_evidence_cohort` 경로가 구현되었다 | script/schema/test/Make target 존재, report 부재 | **정합** |
| `bootstrap_preflight`가 추가되었다 | script/test/Make target 존재 | **정합** |
| `raw_registry_cross_environment_evidence_bundle`가 추가되었다 | script/schema/test/Make target 존재, report 부재 | **정합** |
| release-ready는 아직 blocked다 | `release-closeout-summary.json` fail | **정합** |
| blocker는 learning readiness다 | blocker code 실제 일치 | **정합** |
| archive는 아직 dry-run이다 | `mode=dry_run`, `applied_move_count=0` | **정합** |
| artifact freshness는 attention이다 | 실제 report status=attention | **정합** |
| package boundary가 아직 섞여 있다 | `.obsidian`, `.vscode`, `tmp`, `external-reports` 실제 포함 | **정합** |

### 5.2 실제 수치로 재확인된 핵심 checked-in reports

#### 5.2.1 `ops/reports/release-closeout-summary.json`

실제 핵심 값:

- `status = fail`
- `release_ready = false`
- `blockers = 1`
- `accepted_risks = 3`
- `source_tree_coherence.status = attention`
- 첫 blocker code = `learning_blocked_by_review_required`

blocker 메시지에는 다음 learning signal 부족이 함께 걸려 있다.

- `outcome_metrics_attempt_history_below_minimum`
- `mechanism_review_session_context_missing`
- `loop_health_telemetry_coverage_missing`
- `recent_hold_moving_average`
- `high_rework`
- `defect_escape_proxy`

#### 5.2.2 `ops/reports/test-execution-summary.json`

실제 핵심 값:

- `status = pass`
- `counts.passed = 222`
- `counts.failed = 0`
- `counts.errors = 0`
- `counts.warnings = 0`
- `execution_environment.python_version = 3.14.3`
- `execution_environment.pytest_version = 8.4.2`

#### 5.2.3 `ops/reports/generated-artifact-index.json`

실제 핵심 값:

- `status = attention`
- `summary.canonical_report_count = 34`
- `summary.archive_candidate_count = 27`

#### 5.2.4 `ops/reports/archive-execution-manifest.json`

실제 핵심 값:

- `status = attention`
- `mode = dry_run`
- `summary.candidate_count = 27`
- `summary.planned_move_count = 27`
- `summary.applied_move_count = 0`
- `summary.rollback_available_count = 0`

#### 5.2.5 `ops/reports/artifact-freshness-report.json`

실제 핵심 값:

- `status = attention`
- `mtime_source = filesystem`
- `summary.artifact_count = 164`
- `summary.stale_artifact_count = 40`
- `summary.mtime_sensitive_artifact_count = 41`
- `summary.missing_artifact_envelope_count = 32`
- `summary.safe_to_backfill_artifact_count = 123`

#### 5.2.6 `ops/reports/raw-registry-cross-environment-matrix.json`

실제 핵심 값:

- `status = pass`
- `profile = linux-c-utf8`
- `matrix rows = 5`

#### 5.2.7 `ops/reports/manual-mutate-defect-registry.json`

실제 핵심 값:

- `status = pass`
- `registered_defect_count = 2`
- `fixed_defect_count = 2`
- `covered_regression_count = 2`
- `unresolved_or_uncovered_count = 0`

---

## 6. 원본 ZIP 기준으로 실제로 비어 있는 것들

업로드 리뷰들이 반복해서 지적한 “구현은 있으나 운영 artifact가 비어 있음”은 실제 ZIP에서 그대로 확인됐다.

### 6.1 부재가 재확인된 report artifacts

원본 ZIP 기준으로 아래 파일은 **존재하지 않았다.**

- `ops/reports/learning-readiness-signoff.json`
- `ops/reports/release-evidence-cohort.json`
- `ops/reports/raw-registry-cross-environment-evidence-bundle.json`
- `ops/reports/bootstrap-preflight-report.json`

이 부재는 매우 중요하다. 이유는 다음과 같다.

1. signoff 경로가 있어도 실제 signoff artifact가 없으면 blocker는 닫히지 않는다.
2. cohort 코드가 있어도 canonical cohort report가 없으면 release evidence chain은 완결되지 않는다.
3. bundle 코드가 있어도 운영 evidence bundle이 없으면 cross-environment portability는 여전히 선언 수준에 머문다.
4. bootstrap preflight가 pass여도 canonical report가 없으면 clean bootstrap evidence가 저장되지 않는다.

### 6.2 원본 ZIP에서 실제로 존재하는 대응 surface

반대로 아래 파일은 실제로 있었다.

- `ops/scripts/learning_readiness_signoff.py`
- `ops/schemas/learning-readiness-signoff.schema.json`
- `ops/templates/learning-readiness-signoff.json`
- `ops/scripts/release_evidence_cohort.py`
- `ops/schemas/release-evidence-cohort.schema.json`
- `ops/scripts/bootstrap_preflight.py`
- `ops/scripts/raw_registry_cross_environment_evidence_bundle.py`
- `ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json`

즉, 이번 ZIP은 “경로를 여는 작업”은 분명히 했지만 “운영 evidence를 채우는 작업”은 아직 덜 끝난 상태다.

---

## 7. 실제 재실행 검증 결과

이번 보고서는 문서 요약만 하지 않고 핵심 부분을 직접 재실행했다.

### 7.1 bootstrap preflight

실행 결과:

- `status = pass`
- `dependency_count = 5`
- `missing_dependency_count = 0`

해석:

- 업로드 리뷰들의 “live bootstrap preflight pass” 진술은 현재 검토 환경에서도 재현되었다.
- 다만 pass 결과가 **report artifact로 남지 않는 상태**이므로, release evidence chain 관점에서는 여전히 미완결이다.

### 7.2 strict release evidence cohort

`make release-evidence-cohort-check` 재실행 결과는 **실패**였다.

재현된 핵심 값:

- `status = fail`
- `profile = base`
- `cohort_policy = strict_same_fingerprint`
- `summary.component_count = 6`
- `summary.issue_count = 1`
- `summary.strict_same_fingerprint = false`
- `summary.component_fingerprint_count = 6`
- `summary.modified_after_generated_at_count = 6`
- `issue code = cohort_not_strict_same_fingerprint`

해석:

- 업로드 리뷰들이 말한 “strict mode에서 fail”은 실제로 재현된다.
- source-tree coherence는 설명적 attention이 아니라 **실제 fail artifact로 드러나는 문제**다.
- 더 중요한 점은 이 명령이 실패하면서도 canonical 위치인 `ops/reports/release-evidence-cohort.json`에 결과를 쓰려 한다는 것이다.

### 7.3 raw registry cross-environment evidence bundle

`make raw-registry-cross-environment-evidence-bundle` 재실행 결과는 **실패**였다.

재현된 핵심 값:

- `status = fail`
- `summary.expected_profile_count = 3`
- `summary.report_count = 0`
- `summary.valid_report_count = 0`
- `summary.missing_report_count = 3`
- `summary.invalid_report_count = 0`
- `summary.failed_report_count = 0`
- 기대 profile: `linux-c-utf8`, `windows-utf8`, `macos-utf8`

해석:

- 업로드 리뷰들이 말한 “per-profile report 3개 부재”는 실제로 재현된다.
- 현재 저장소에는 단일 `raw-registry-cross-environment-matrix.json`만 있고, bundle generator는 profile별 결과를 요구한다.
- 따라서 bundle surface는 구현됐지만 운영 evidence 계약은 아직 닫히지 않았다.

### 7.4 정적 품질 게이트

실행 결과:

- `ruff check` → **All checks passed**
- `mypy` → **Success: no issues found in 4 source files**

대상 스크립트:

- `ops/scripts/learning_readiness_signoff.py`
- `ops/scripts/release_evidence_cohort.py`
- `ops/scripts/bootstrap_preflight.py`
- `ops/scripts/raw_registry_cross_environment_evidence_bundle.py`

해석:

- 신규 기능 surface의 static quality는 양호하다.
- 즉, 문제는 “코드 품질 부족”보다 “운영 evidence chain이 아직 비어 있음”에 더 가깝다.

---

## 8. Makefile 및 운영 경로 재검토

### 8.1 실제로 존재하는 target

`Makefile`에는 다음 target들이 실제로 선언되어 있다.

- `release-evidence-closeout`
- `release-evidence-cohort`
- `release-evidence-cohort-check`
- `raw-registry-cross-environment-evidence-bundle`
- `bootstrap-preflight`

이는 신규 리뷰들의 주장과 일치한다.

### 8.2 실제로 없는 target

반면 아래와 같은 signoff 편의 target은 없다.

- `learning-readiness-signoff`
- `learning-readiness-signoff-check`
- `learning-readiness-signoff-template`

이 부재는 업로드 follow-up 리뷰가 지적한 UX gap과 일치한다.

### 8.3 closeout chain의 실제 순서

`release-evidence-closeout`는 현재 다음 순서다.

```make
release-evidence-closeout:
	$(MAKE) release-smoke-full
	$(MAKE) registry-preflight
	$(MAKE) test-execution-summary
	$(MAKE) generated-artifact-index
	$(MAKE) archive-execution-manifest-report
	$(MAKE) artifact-freshness
	$(MAKE) release-closeout-summary
	$(MAKE) release-evidence-cohort
```

여기서 주목할 점은 **`bootstrap-preflight`가 아직 closeout chain에 포함되어 있지 않다**는 것이다.

이 점은 이번 재검증에서도 중요한 개선 포인트로 유지된다.

---

## 9. 남아 있는 작업분 정리

### 9.1 P0 — 즉시 닫아야 할 항목

#### P0-1. learning readiness blocker 해소

현재 blocker를 닫는 경로는 둘 중 하나다.

- 경로 A: 실제 learning evidence를 개선하여 `likely_to_learn=true` 달성
- 경로 B: 실제 `ops/reports/learning-readiness-signoff.json` 생성

현재 상태는 **경로 B용 plumbing은 있으나 report artifact가 없음**이다.

#### P0-2. release evidence cohort를 실제 canonical evidence로 완성

현재는 code/test/Make target까지는 있으나 원본 ZIP에 `ops/reports/release-evidence-cohort.json`이 없다. strict check를 돌리면 fail artifact가 생길 뿐이다.

#### P0-3. strict cohort fail 처리 정책 확정

현재 strict mode 결과는 다음을 보여준다.

- 모든 component fingerprint가 다르다.
- 모든 component가 `modified_after_generated_at=true`다.

따라서 둘 중 하나를 결정해야 한다.

- strict single cohort로 다시 생성
- explicit risk로 유지하되 signoff에 owner/expiry/revalidation을 남김

### 9.2 P1 — evidence portability와 운영 증거 완성

#### P1-1. raw registry per-profile evidence 3종 생성

현재 bundle은 3개 profile report를 기대하지만 실제로는 단일 matrix만 존재한다. 이 gap을 닫아야 한다.

#### P1-2. artifact freshness canonical mode 정책 확정

현재 checked-in canonical report는 `filesystem` 모드다. 신규 리뷰들은 `zip_info`, `embedded_currentness`까지 포함한 정책 결정을 요구한다.

#### P1-3. archive 27건 apply/defer 실행

현재 `planned_move_count = 27`, `applied_move_count = 0`다. dry-run에서 멈춘 상태다.

#### P1-4. bootstrap preflight report 승격

pass/fail 여부가 일회성 CLI 결과가 아니라 canonical report로 남아야 한다.

### 9.3 P2 — 패키지/운영 UX 정리

#### P2-1. signoff Make UX 추가

현재는 script와 schema는 있으나 operator-friendly target이 없다.

#### P2-2. long-running summary shards 도입

신규 리뷰들이 지적했듯, 전체 report-contract-summary 또는 전체 pytest 계열은 실행 비용이 높다. shard + aggregate 구조가 적합하다.

---

## 10. 이번 재대조에서 새로 식별된 개선 방안

이 절은 업로드 리뷰들의 권고를 반복하지 않고, **이번 실제 재실행을 통해 추가로 명확해진 개선점**만 별도로 정리한다.

### N-01. 실패 진단용 rerun은 canonical output path를 직접 쓰지 않도록 분리해야 한다

현재 다음 명령은 실패해도 canonical path에 결과를 기록한다.

- `make release-evidence-cohort-check`
- `make raw-registry-cross-environment-evidence-bundle`

이 구조는 위험하다. 리뷰 목적의 fail artifact가 원본 evidence와 같은 위치에 생성되기 때문이다.

**개선안:**
- `--out`을 tmp diagnostics path로 기본 분기하거나
- `*-check` target은 canonical path에 쓰지 않도록 별도 output contract를 둔다.

### N-02. “원본 ZIP에 부재”와 “재실행 시 fail artifact 생성”을 문서에서 명시적으로 구분해야 한다

현재 리뷰를 읽는 사람이 가장 헷갈리기 쉬운 지점은 다음이다.

- 원본 ZIP 기준으로는 report가 없다.
- 그러나 검증 중 명령을 돌리면 fail report는 생성될 수 있다.

이 둘을 구분하지 않으면 “파일이 생겼으니 해결된 것”처럼 오독될 수 있다.

**개선안:**
- 모든 리뷰에서 `checked_in_state`와 `rerun_state`를 분리한 표준 표를 사용한다.

### N-03. bundle generator는 “단일 matrix 존재”와 “per-profile matrix 부재”를 더 친절하게 구분해서 보고해야 한다

현재 실패는 `missing_report_count=3`으로만 요약된다. 하지만 실제 저장소에는 `raw-registry-cross-environment-matrix.json` 하나가 있다.

**개선안:**
- diagnostics에 `fallback_candidate_detected=true`
- `single_matrix_present_but_profile_split_missing=true`
- 기대 profile별 매핑 힌트 출력

### N-04. `bootstrap-preflight`는 closeout chain에 들어가야 할 뿐 아니라, closeout summary의 component로 승격되어야 한다

지금은 pass 결과가 나와도 release evidence chain에는 저장되지 않는다.

**개선안:**
- `release-evidence-closeout` 최상단에 `bootstrap-preflight`
- `ops/reports/bootstrap-preflight-report.json` 생성
- `release-closeout-summary`에 component로 포함

### N-05. signoff template은 placeholder artifact가 아니라 “template artifact”임을 schema/retention에서 더 강하게 표현해야 한다

현재 template JSON에는 `artifact_status = current`, `retention_policy = canonical_report`가 들어 있다. 설명 주석은 template라 하지만 필드만 보면 canonical artifact처럼 보일 여지가 있다.

**개선안:**
- template 전용 `artifact_status = template_only`
- template 전용 `retention_policy = template`
- closeout에서 `source_revision = template` 즉시 reject

### N-06. source-tree coherence는 `modified_after_generated_at_count` 자체를 독립 blocker code로 분리하는 편이 좋다

현재 strict cohort fail에는 fingerprint mismatch와 `modified_after_generated_at`가 함께 들어 있다. 둘은 성격이 다르다.

- fingerprint mismatch: cohort 불일치
- modified_after_generated_at: 생성 시점/파일시스템 시점 불정합

**개선안:**
- blocker code 분리
- remediation 경로도 분리

### N-07. package profile 정의 시 `tmp/codex-plan-review`는 항상 non-release로 고정해야 한다

현재 tmp review outputs는 진단에는 유용하지만 release evidence와 혼동될 수 있다.

**개선안:**
- `review_snapshot` profile에만 포함
- `release_source`, `public_docs`에서는 항상 제외

---

## 11. 실행 우선순위 제안

### Tranche 1 — release blocker 직결 항목

1. `learning-readiness-signoff.json` 생성 또는 실제 learning metrics 개선
2. `release-evidence-cohort` strict fail 해소 또는 explicit risk 정책 고정
3. `release-evidence-closeout` 재실행 후 `release_ready` 재판정

### Tranche 2 — canonical evidence chain 완성

1. `bootstrap-preflight-report.json` 생성
2. `release-evidence-cohort.json` canonical artifact 체크인
3. `raw-registry-cross-environment-evidence-bundle.json` canonical artifact 체크인
4. `checked_in_state` / `rerun_state` 분리 보고 표준화

### Tranche 3 — portability와 lifecycle 정리

1. raw registry per-profile matrix 3종 생성
2. artifact freshness authoritative mode 확정
3. archive 27건 apply/defer 및 rollback 경로 명시

### Tranche 4 — package boundary 정리

1. review snapshot / release source / public docs profile 정의
2. `.obsidian`, `.vscode`, `tmp`, archived review outputs 정리
3. signoff Make UX 및 diagnostic output 분리

---

## 12. 최종 판정

이번 재대조의 최종 결론은 분명하다.

1. 업로드된 두 리뷰는 핵심 판정에서 일치하며, 실제 ZIP과도 정합적이다.
2. 기존 리뷰의 메시지는 여전히 유효하고, 두 신규 리뷰는 그것을 더 실행 가능한 수준으로 구체화한다.
3. 실제 ZIP은 코드·스키마·테스트·CI·문서 차원에서 눈에 띄게 진전되었지만, 운영 evidence chain은 아직 비어 있는 부분이 많다.
4. 현재 직접 blocker는 여전히 `learning_blocked_by_review_required`이며, signoff artifact 부재와 strict cohort fail이 release-ready 전환을 막고 있다.
5. raw registry bundle, bootstrap report, cohort report는 “경로는 있음 / 운영 artifact는 없음” 상태다.
6. archive lifecycle도 dry-run에 머물러 있어 cleanup이 끝난 상태가 아니다.

따라서 가장 정확한 한 줄 판정은 다음과 같다.

> **LLM Wiki vNext는 기준 리뷰 이후 evidence system이 실질적으로 성숙했지만, 현재 상태는 아직 release-ready가 아니다. 지금 필요한 것은 새 기능 추가보다, 이미 구현된 evidence surface를 canonical artifact와 운영 정책으로 끝까지 닫아 release gate를 실제로 통과시키는 것이다.**

---

## Appendix A. 이번 재검증에서 직접 확인한 핵심 사실 요약

| 항목 | 실제 결과 |
|---|---|
| ZIP SHA-256 | `eef6544f6b4bc5ac0227fd8a552b575f94a2b1153c8cef94d16a53f765bb3aa8` |
| files / dirs | `1638 / 86` |
| 기준 시각 이후 변경 파일 수 | `42` |
| `release-closeout-summary.json` | `fail`, `release_ready=false`, blocker 1 |
| `learning-readiness-signoff.json` | 원본 ZIP 기준 부재 |
| `release-evidence-cohort.json` | 원본 ZIP 기준 부재 |
| `raw-registry-cross-environment-evidence-bundle.json` | 원본 ZIP 기준 부재 |
| `bootstrap-preflight-report.json` | 원본 ZIP 기준 부재 |
| `bootstrap_preflight --dev` | pass |
| `release-evidence-cohort-check` | fail |
| `raw-registry-cross-environment-evidence-bundle` | fail |
| `ruff` | pass |
| `mypy` | pass |
| archive lifecycle | dry_run, planned 27, applied 0 |
| artifact freshness | attention, stale 40, mtime-sensitive 41, missing envelope 32 |

## Appendix B. 원본 ZIP 기준 부재/존재 매트릭스

| 경로 | 원본 ZIP 상태 | 의미 |
|---|---|---|
| `ops/scripts/learning_readiness_signoff.py` | 존재 | signoff generator 구현 |
| `ops/schemas/learning-readiness-signoff.schema.json` | 존재 | signoff contract 구현 |
| `ops/templates/learning-readiness-signoff.json` | 존재 | template 존재 |
| `ops/reports/learning-readiness-signoff.json` | 부재 | 실제 운영 signoff 없음 |
| `ops/scripts/release_evidence_cohort.py` | 존재 | cohort generator 구현 |
| `ops/schemas/release-evidence-cohort.schema.json` | 존재 | cohort contract 구현 |
| `ops/reports/release-evidence-cohort.json` | 부재 | canonical cohort artifact 없음 |
| `ops/scripts/bootstrap_preflight.py` | 존재 | bootstrap 진단 구현 |
| `ops/reports/bootstrap-preflight-report.json` | 부재 | canonical bootstrap evidence 없음 |
| `ops/scripts/raw_registry_cross_environment_evidence_bundle.py` | 존재 | bundle generator 구현 |
| `ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json` | 존재 | bundle contract 구현 |
| `ops/reports/raw-registry-cross-environment-evidence-bundle.json` | 부재 | canonical bundle artifact 없음 |

