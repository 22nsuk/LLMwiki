# LLM Wiki vNext Two-Review Crosscheck Improvement Report

- **작성일:** 2026-04-30 (Asia/Seoul)
- **파일명:** `two_review_crosscheck_improvement_report_20260430.md`
- **작성 언어:** 한국어
- **검토 대상 ZIP:** `LLM Wiki vNext.zip`
- **검토 대상 ZIP SHA-256:** `80c926e39ad013cc0b62ba8943f76dba9e1d4912710c0e47dada36d25fb382bf`
- **ZIP 엔트리:** 파일 `1656`개, 디렉터리 `89`개, 총 `1745`개
- **기준 리뷰:** `external-reports/integrated_improvement_crosscheck_report_20260430_kr.md`
- **기존 대조 보고서:** `post_crosscheck_followup_status_report_20260430.md`
- **이번에 추가 대조한 리뷰 2건:**
  1. `llm_wiki_vnext_integrated_post_review_report_20260430.md`
  2. `LLM Wiki vNext 통합 리뷰 보고서_20260430.md`

---

## 0. 최종 판정

두 신규 리뷰는 기존 대조 보고서 및 실제 ZIP의 checked-in 파일과 **핵심 결론에서 일치**한다. 현재 ZIP은 기준 리뷰 당시의 `materially_advanced_but_not_release_ready` 상태에서 확실히 진전되어, checked-in release evidence 기준으로는 `release_ready=true`에 도달했다. 그러나 이 상태는 무조건적 또는 clean release-ready가 아니라 다음 조건 위에 서 있다.

1. `learning-readiness-signoff.json`의 **시한부 accepted risk**에 의존한다.
2. `release-evidence-cohort.json`은 존재하지만 `strict_same_fingerprint=false`이고 `status=attention`이다.
3. `artifact-freshness-report.json`은 `stale=0`, `mtime_sensitive=0`까지 개선되었지만 stable contract debt 32건이 남아 `status=attention`이다.
4. checked-in artifact와 fresh/live rerun 결과를 구분하는 evidence model이 아직 충분히 선명하지 않다.
5. clean environment에서 전체 closeout chain이 end-to-end로 재현된 증거는 아직 부족하다.

따라서 가장 정확한 현재 판정은 다음과 같다.

> **조건부 release-ready / signoff_release_ready.**  
> checked-in JSON evidence와 스키마 계약은 상당히 강해졌지만, strict-clean release-ready로 승격하려면 signoff 의존 축소, strict cohort 달성 또는 정책 waiver 명문화, freshness debt backfill, live reproducibility 확증이 필요하다.

---

## 1. 검토 범위와 수행한 확인

### 1.1 직접 읽고 대조한 문서

| 구분 | 파일 | bytes | lines | SHA-256 |
|---|---:|---:|---:|---|
| new_review_long | `llm_wiki_vnext_integrated_post_review_report_20260430.md` | 54,471 | 1,004 | `49297b722efe0f5e0f686ab083046ff7b437fa9f4d00885003dc5362b1945385` |
| new_review_short | `LLM Wiki vNext 통합 리뷰 보고서_20260430.md` | 25,126 | 490 | `cf2353cc302b70a7ea0f639926fb1d9d0ae4f5493fb4747bd390cec4af0d04ad` |
| existing_review | `post_crosscheck_followup_status_report_20260430.md` | 44,055 | 696 | `19472bd195e3c93242df47b1699cc063f02de1f3cc1a3ddff02bb93be6ed2781` |
| baseline_crosscheck | `integrated_improvement_crosscheck_report_20260430_kr.md` | 31,119 | 726 | `72d5d4254d61c84c87aa1ac7d70bd2c6626399a269e619984b5bdfc2f26f6fdd` |

### 1.2 실제 ZIP 구조 확인

현재 ZIP은 `80c926...` SHA를 가지며, 루트에는 `AGENTS.md`, `AGENTS.local.md`, `Makefile`, `README.md`, `ops/`, `tests/`, `runs/`, `tmp/`, `external-reports/`, `wiki/`, `system/`, `raw/` 등이 포함되어 있다. full local vault supplement가 존재하므로, 실제 파일 대조에서는 public mirror 규칙과 local supplement가 모두 관련된다.

주요 파일 확장자 분포는 다음과 같다.

| 확장자 | 파일 수 |
|---|---:|
| `.md` | 951 |
| `.py` | 299 |
| `.json` | 274 |
| `.pdf` | 62 |
| `.txt` | 28 |
| `.pyc` | 18 |
| `.yaml` | 13 |
| `.toml` | 10 |
| `.jsonl` | 8 |
| `<no_ext>` | 5 |
| `.docx` | 2 |
| `.yml` | 2 |

### 1.3 스키마 검증

현재 ZIP에서 핵심 JSON report 18개를 각 파일의 `$schema`가 가리키는 로컬 스키마로 검증했다. 결과는 전원 `pass`다. 이는 두 신규 리뷰와 기존 대조 보고서의 “checked-in evidence는 구조적으로 self-consistent하다”는 주장과 일치한다.

| report | schema | 검증 결과 |
|---|---|---|
| `ops/reports/bootstrap-preflight-report.json` | `ops/schemas/bootstrap-preflight-report.schema.json` | pass |
| `ops/reports/learning-readiness-signoff.json` | `ops/schemas/learning-readiness-signoff.schema.json` | pass |
| `ops/reports/release-evidence-cohort.json` | `ops/schemas/release-evidence-cohort.schema.json` | pass |
| `tmp/release-evidence-cohort.candidate.json` | `ops/schemas/release-evidence-cohort.schema.json` | pass |
| `ops/reports/release-closeout-summary.json` | `ops/schemas/release-closeout-summary.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-evidence-bundle.json` | `ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json` | pass |
| `tmp/raw-registry-cross-environment-evidence-bundle-check.json` | `ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json` | pass |
| `ops/reports/artifact-freshness-report.json` | `ops/schemas/artifact-freshness-report.schema.json` | pass |
| `ops/reports/archive-execution-manifest.json` | `ops/schemas/archive-execution-manifest.schema.json` | pass |
| `ops/reports/test-execution-summary.json` | `ops/schemas/test-execution-summary.schema.json` | pass |
| `ops/reports/test-execution-summary-shards/report-contract-summary.json` | `ops/schemas/test-execution-summary.schema.json` | pass |
| `ops/reports/generated-artifact-index.json` | `ops/schemas/generated-artifact-index.schema.json` | pass |
| `ops/reports/manual-mutate-defect-registry.json` | `ops/schemas/manual-mutate-defect-registry.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix-linux-c-utf8.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix-windows-utf8.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix-macos-utf8.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/review-archive-report.json` | `ops/schemas/review-archive-report.schema.json` | pass |

### 1.4 live 명령 재확인

검토 중 현재 런타임에서 제한적으로 live rerun도 시도했다.

| 명령 | 결과 | 해석 |
|---|---|---|
| `python3 -m ops.scripts.bootstrap_preflight --dev --json` | exit 1, `status=fail`, dev dependency `mypy`, `ruff` missing | checked-in `bootstrap-preflight-report.json`은 pass지만, 현재 검토 컨테이너는 release-builder/dev 환경이 아니다. 이 결과는 “checked-in pass와 live 환경 상태를 분리해야 한다”는 리뷰들의 지적을 강화한다. |
| `make release-evidence-cohort-check` | exit 2, `tmp/release-evidence-cohort-check.json` 생성, strict policy 기준 `status=fail`, `strict_same_fingerprint=false` | canonical cohort는 allowed-risk attention이고, strict diagnostic은 실패한다. 이번 추출/검토 환경에서는 `modified_after_generated_at_count=9`로 산출되었는데, canonical report의 3과 다르므로 mtime 기반 strict check는 추출 환경과 command side effect에 민감하다. |
| `make raw-registry-cross-environment-evidence-bundle` | 현재 도구 런타임의 자동 인터럽트로 미완주 | 이 검토에서는 raw registry live 재현성에 대한 새 pass/fail 결론을 추가로 내리지 않았다. checked-in bundle은 schema-valid pass 상태다. |

---

## 2. 두 신규 리뷰의 성격과 상호 관계

### 2.1 신규 리뷰 1: `llm_wiki_vnext_integrated_post_review_report_20260430.md`

이 문서는 두 신규 리뷰 중 더 큰 통합 보고서이며, 보고서 내부에서 4개 하위 리뷰를 동등한 1차 자료로 취급한다고 명시한다. 구조상 다음을 모두 포함한다.

- 기준 리뷰의 `materially_advanced_but_not_release_ready` 판정 재확인
- 현재 ZIP의 파일 수, 확장자 분포, 변경 파일 분포
- 핵심 JSON report 상태판
- 기준 리뷰 이후 완료된 P0/P1/P2 항목
- 남은 작업 전수 분석
- 새 개선안 IM-01~IM-14
- 후속 실행 Tranche A~E
- Appendix 기반 수치 비교와 변경 파일 타임라인
- 리뷰 A~D의 고유 발견 요약

**대조 판정:** 실제 파일과 대체로 정합하다. 특히 canonical artifact 4종 존재, closeout pass, archive applied, freshness mtime 개선, raw registry bundle pass, test summary shard/aggregate 존재, accepted risk 3건, stable contract debt 32건은 실제 JSON과 일치한다.

**주의할 점:** 이 문서는 리뷰 D의 live rerun 실패를 별도 절에서 잘 분리해 설명하지만, 일부 요약 문장에서는 live reproducibility gap이 모든 리뷰의 공통 직접 실행 결과처럼 읽힐 수 있다. 실제로는 리뷰 D가 정량화했고, 기존 리뷰는 checked-in/schema 중심 검증이었다. 따라서 “모두 동의한 잔여 리스크”와 “모두 직접 재실행한 결과”를 엄격히 구분해야 한다.

### 2.2 신규 리뷰 2: `LLM Wiki vNext 통합 리뷰 보고서_20260430.md`

이 문서는 신규 리뷰 1보다 짧은 요약형 통합 보고서다. 핵심 결론, 완료 항목, 잔여 과제, 새 개선안, 권장 실행 순서를 압축해 제공한다.

**대조 판정:** 주요 결론은 신규 리뷰 1, 기존 대조 보고서, 실제 JSON과 일치한다. 특히 “조건부/정책적 release-ready이지만 clean release-ready는 아니다”라는 문장은 현재 상태를 가장 짧게 잘 표현한다.

**주의할 점:** 짧은 보고서는 누락 없이 쓰기에는 압축도가 높다. JSON schema 검증 목록, 변경 파일 전체 타임라인, live rerun 한계, accepted risk 세부, freshness debt queue, actual command rerun의 환경 민감도 등은 신규 리뷰 1 또는 기존 대조 보고서에 비해 생략되어 있다. 따라서 운영 근거 문서로는 신규 리뷰 1과 기존 대조 보고서를 함께 참조해야 한다.

### 2.3 기존 대조 보고서와의 관계

기존 `post_crosscheck_followup_status_report_20260430.md`는 실제 ZIP inventory와 17개 JSON schema validation, 변경 파일 55건 분석을 중심으로 작성되어 있다. 신규 리뷰 1은 이 내용을 흡수해 더 넓은 통합 관점으로 확장했고, 신규 리뷰 2는 이를 다시 압축한 executive review에 가깝다.

정리하면 관계는 다음과 같다.

| 문서 | 역할 | 장점 | 한계 |
|---|---|---|---|
| 기존 대조 보고서 | ZIP과 baseline의 직접 대조 | SHA, 파일 수, schema validation, 변경 파일 55건이 가장 구체적 | live rerun은 거의 사용하지 않음 |
| 신규 리뷰 1 | 4개 리뷰 전원 통합 사후 리뷰 | 가장 완전한 통합 구조, 개선안과 로드맵 풍부 | 일부 요약에서 “공통 지적”과 “직접 재실행 증거”가 섞여 읽힐 수 있음 |
| 신규 리뷰 2 | 축약형 통합 리뷰 | 결론과 우선순위를 빠르게 파악하기 좋음 | 근거와 예외 조건이 압축되어 단독 운영 문서로는 부족 |

---

## 3. 기준 리뷰 및 실제 파일과의 핵심 대조

### 3.1 기준 리뷰의 fail 상태에서 현재 pass 상태로 이동한 축

기준 리뷰의 핵심 blocker는 다음 네 부재/실패 축이었다.

1. `learning-readiness-signoff.json` 부재
2. `release-evidence-cohort.json` 부재 또는 strict 재실행 실패
3. `raw-registry-cross-environment-evidence-bundle.json` 부재 및 per-profile evidence 부재
4. `bootstrap-preflight-report.json` canonical report 부재

현재 실제 파일에서는 네 artifact가 모두 존재한다. 또한 `release-closeout-summary.json`은 `status=pass`, `release_ready=true`다. 다만 release-ready 판정은 accepted risk 3건을 포함하므로 clean pass로 해석하면 안 된다.

### 3.2 현재 checked-in 핵심 report 상태

| artifact | 확인 축 | 실제 값 |
|---|---|---|
| `release-closeout-summary.json` | status / release_ready / summary | `pass / True / component=7, ready=6, blocker=0, accepted_risk=3, source_tree=attention` |
| `learning-readiness-signoff.json` | linked_blocker / expiry / owner | `learning_blocked_by_review_required / 2026-05-07T06:02:10Z / runtime-maintainer` |
| `release-evidence-cohort.json` | status / policy / summary | `attention / allowed_divergence_with_explicit_risk / component=9, loaded=9, strict=False, modified_after=3, risk=2` |
| `raw-registry-cross-environment-evidence-bundle.json` | status / summary | `pass / expected=3, valid=3, missing=0, failed=0, diagnostic=1` |
| `bootstrap-preflight-report.json` | checked-in status / deps | `pass / dependency=5, missing=0, missing_packages=[]` |
| `archive-execution-manifest.json` | mode / summary | `applied / candidate=27, applied=27, rollback=27` |
| `artifact-freshness-report.json` | status / mtime / debt | `attention / mtime_source=embedded_currentness, stale=0, mtime_sensitive=0, envelope_missing=32, stable_debt=32, issue=64` |
| `test-execution-summary.json` | status / counts / deselected | `pass / passed=231, failed=0, errors=0, warnings=0, deselected=3, duration_ms=496442` |
| `generated-artifact-index.json` | status / summary | `pass / canonical=42, archive_candidate=0, task_obs=34, external_archive=42` |
| `manual-mutate-defect-registry.json` | status / defects | `pass / registered=2, fixed=2, unresolved_or_uncovered=0` |
| `review-archive-report.json` | status / archive | `pass / archive_path=tmp/llm-wiki-vnext-review.zip, packed_file_count=387, generated_at=2026-04-28T03:41:42Z` |

### 3.3 release closeout accepted risk 3건

`release-closeout-summary.json`의 `release_ready=true`는 risk-free가 아니라 다음 accepted risk 3건 위에 서 있다.

| code | source | severity | gate_effect | expires_at | owner |
|---|---|---|---|---|---|
| `artifact_freshness_attention` | artifact_freshness | warn | accepted_risk | 2026-05-07T07:38:36Z | runtime-maintainer |
| `source_tree_coherence_attention` | source_tree_coherence | warn | accepted_risk | 2026-05-07T07:38:36Z | runtime-maintainer |
| `learning_blocked_by_review_required` | auto_improve_readiness | warn | accepted_risk | 2026-05-07T06:02:10Z | runtime-maintainer |

### 3.4 release evidence cohort risk 2건

`release-evidence-cohort.json`은 `status=attention`이며, strict cohort를 통과한 증거가 아니다.

| code | severity | gate_effect | expires_at | message |
|---|---|---|---|---|
| `cohort_not_strict_same_fingerprint` | warn | accepted_by_cohort_policy | 2026-05-07T07:38:38Z | release evidence components have more than one source_tree_fingerprint. |
| `cohort_modified_after_generated_at` | warn | accepted_by_cohort_policy | 2026-05-07T07:38:38Z | release evidence component files were modified after their embedded generated_at timestamps: archive_execution_manifest, artifact_freshness, release_closeout_summary |

### 3.5 artifact freshness debt 상위 항목

`artifact-freshness-report.json`은 mtime 기반 false-positive를 줄였지만, artifact envelope/currentness debt를 별도 축으로 드러낸다.

| path | owner_surface | issues | recommended_next_action | safe_to_backfill |
|---|---|---|---|---|
| `ops/reports/auto-improve-sessions/auto-improve-20260428-readiness-preflight.json` | ops_reports | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `ops/reports/sbom-export-mapping.json` | ops_reports | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `ops/reports/supply-chain-provenance.json` | ops_reports | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `runs/archive/run-20260415-mechanism-planning-gate-second-retry/baseline-mechanism-assessment.json` | runs | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `runs/archive/run-20260415-mechanism-planning-gate-second-retry/candidate-mechanism-assessment.json` | runs | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `runs/archive/run-20260422-auto-improve-decision-record-fallback/baseline-mechanism-assessment.json` | runs | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `runs/run-20260414-mechanism-planning-gate/baseline-mechanism-assessment.json` | runs | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `runs/run-20260414-mechanism-planning-gate/candidate-mechanism-assessment.json` | runs | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `runs/run-20260415-mechanism-planning-gate-second-clean/baseline-mechanism-assessment.json` | runs | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |
| `runs/run-20260415-mechanism-planning-gate-second-clean/candidate-mechanism-assessment.json` | runs | missing_artifact_envelope, unknown_currentness | backfill_artifact_envelope | True |

### 3.6 test deselection 3건

신규 리뷰들이 “deselection lifecycle 관리”를 잔여 과제로 둔 것은 타당하다. 다만 실제 파일에는 이미 `ops/policies/report-contract-deselections.json`이 존재하고, 각 deselected test는 policy ref를 갖는다. 남은 작업은 “정책 파일 최초 생성”이 아니라 **budget, expiry, 증가 시 gate effect, refresh 후 pass 확인**을 추가하는 것이다.

| nodeid | release_blocking | expected_to_pass_after_refresh | policy_ref |
|---|---:|---:|---|
| `tests/test_generated_report_contracts.py::test_checked_in_artifact_freshness_report_keeps_stable_debt_axes_explicit` | False | True | ops/policies/report-contract-deselections.json#artifact_freshness_self_reference |
| `tests/test_generated_report_contracts.py::test_checked_in_test_execution_summary_is_schema_backed_and_debt_free` | False | True | ops/policies/report-contract-deselections.json#test_execution_summary_self_reference |
| `tests/test_generated_report_contracts.py::test_checked_in_generated_artifact_index_matches_live_inventory_and_fingerprints` | False | True | ops/policies/report-contract-deselections.json#generated_artifact_index_self_reference |

---

## 4. 신규 리뷰 주장별 정합성 판정

| 주장 | 신규 리뷰 1 | 신규 리뷰 2 | 실제 파일 대조 | 판정 |
|---|---|---|---|---|
| 현재 ZIP SHA가 `80c926...`이다 | 명시 | 일부 축약 | ZIP SHA 직접 계산 일치 | 정합 |
| 기준 리뷰 상태는 `materially_advanced_but_not_release_ready`였다 | 명시 | 명시 | baseline 문서 내용과 일치 | 정합 |
| canonical artifact 4종이 모두 생성되었다 | 명시 | 명시 | 4개 파일 모두 존재, schema pass | 정합 |
| closeout이 fail → pass로 이동했다 | 명시 | 명시 | `status=pass`, `release_ready=true` | 정합 |
| learning blocker는 metric 개선이 아니라 signoff로 처리되었다 | 명시 | 명시 | signoff notes와 closeout accepted risk 일치 | 정합 |
| archive lifecycle은 applied 27 / rollback 27이다 | 명시 | 명시 | archive summary 일치 | 정합 |
| freshness는 stale 0 / mtime_sensitive 0이지만 debt 32가 남았다 | 명시 | 명시 | freshness summary 일치 | 정합 |
| raw registry per-profile bundle은 checked-in pass다 | 명시 | 명시 | bundle summary 3/3 valid, pass | 정합 |
| strict same-fingerprint cohort는 아직 아니다 | 명시 | 명시 | canonical strict false, diagnostic strict fail | 정합 |
| live reproducibility gap이 있다 | 명시 | 명시 | bootstrap live fail 및 cohort strict fail을 현재도 확인; raw registry는 이번 검토 미완주 | 정합하되 출처/환경 구분 필요 |
| public surface policy가 코드화되었다 | 명시 | 언급 | `ops/scripts/public_surface_policy.py` 존재 | 정합 |
| review archive report는 387 files를 담는다 | 명시 | 부분 언급 | `review-archive-report.json`의 `packed_file_count=387` | 정합하되 generated_at은 2026-04-28 |
| test deselection 3건 관리는 필요하다 | 명시 | 명시 | 3건 존재, policy ref 존재 | 정합하되 남은 작업은 budget/expiry 중심 |
| rollback rehearsal 미완료 | 명시 | 명시 | 별도 rollback rehearsal pass artifact는 확인되지 않음 | 정합 |

---

## 5. 보정·주의가 필요한 표현

두 신규 리뷰의 핵심 결론은 유지하되, 다음 표현은 개선 보고서 또는 운영 문서에서 더 엄밀히 써야 한다.

### 5.1 “v65/v66/v67”보다 SHA 중심 표기가 안전하다

신규 리뷰 2는 문서별로 v65/v66/v67 라벨을 쓴다. 그러나 현재 실제로 대조 가능한 artifact는 동일 ZIP SHA `80c926e39ad013cc0b62ba8943f76dba9e1d4912710c0e47dada36d25fb382bf`다. 운영 문서에서는 버전 라벨보다 SHA와 report `generated_at`을 주 키로 삼아야 한다.

### 5.2 “4개 리뷰 전원 확인”과 “4개 리뷰 전원 live 실행”은 다르다

네 리뷰가 공통으로 동의한 결론과 네 리뷰가 직접 같은 명령을 실행했다는 뜻은 다르다. 신규 리뷰 1은 이 차이를 비교적 잘 설명하지만, 요약 문장에서는 혼동될 수 있다. live rerun gap은 특히 리뷰 D와 이번 제한 검증에서 강하게 확인된 축이고, 기존 대조 보고서는 checked-in/schema 검증 중심이었다.

### 5.3 strict cohort의 `modified_after_generated_at_count`는 환경 민감하다

canonical report는 `modified_after_generated_at_count=3`이다. 이번 추출 환경에서 `make release-evidence-cohort-check`를 strict mode로 실행하자 `modified_after_generated_at_count=9`가 되었다. ZIP 추출 mtime, command-generated diagnostic, stdout/stderr wrapper side effect가 수치에 영향을 줄 수 있으므로, strict 검증은 release builder에서 controlled checkout 또는 ZIP metadata-aware mode로 수행해야 한다.

### 5.4 bootstrap checked-in pass와 current runtime fail을 동시에 기록해야 한다

`ops/reports/bootstrap-preflight-report.json`은 checked-in 기준 `pass`이고 missing dependency 0이다. 그러나 이번 런타임에서 `python3 -m ops.scripts.bootstrap_preflight --dev --json`은 `mypy`, `ruff` missing으로 fail했다. 이는 repository가 반드시 실패한다는 뜻이 아니라, 검토 환경이 dev/release-builder로 준비되지 않았음을 의미한다.

### 5.5 raw registry live failure는 이번 검토에서 새로 확정하지 않았다

기존 리뷰 D는 raw registry linux profile live failure를 지적했다. 이번 검토에서는 `make raw-registry-cross-environment-evidence-bundle`을 시도했으나 도구 런타임의 자동 인터럽트로 미완주했다. 따라서 이 보고서는 raw registry live failure를 “기존 리뷰 D에서 보고된 재현성 gap”으로 유지하되, 이번 검토에서 독립 재확정했다고 쓰지는 않는다.

### 5.6 review archive report는 존재하지만 최신 post-review artifact는 아니다

`ops/reports/review-archive-report.json`은 `packed_file_count=387`로 존재한다. 다만 `generated_at=2026-04-28T03:41:42Z`이므로 2026-04-30 post-review 작업까지 반영한 최신 review snapshot 증거로 쓰려면 재생성이 필요하다.

### 5.7 test deselection 정책은 이미 존재한다

신규 리뷰들이 제안한 deselection lifecycle 관리는 유효하지만, 실제 파일에는 `ops/policies/report-contract-deselections.json`이 이미 존재한다. 후속 작업은 “정책 생성”보다 다음에 집중해야 한다.

- 만료일 또는 재검증 기한 추가
- deselection 증가 budget 추가
- release closeout에서 deselection count 증가 시 attention/fail 승격
- refresh 후 expected-to-pass가 실제로 닫혔는지 별도 증거 생성

---

## 6. 남아 있는 작업 통합 목록

### 6.1 P0 — 조건부 release-ready를 clean release-ready로 올리기 위한 작업

#### P0-1. learning readiness signoff 의존 축소

현재 signoff는 `2026-05-07T06:02:10Z`에 만료된다. signoff는 blocker를 운영적으로 닫지만, learning metrics가 개선되었다는 증거는 아니다.

필요 작업:

1. signoff 만료 전 `make release-evidence-closeout` 재실행
2. `auto-improve-readiness.json`의 signal 6개를 개별 개선 대상으로 분해
3. operator renewal이 필요한 경우 새 signoff artifact 생성
4. 장기적으로 signoff 없이 `learning_blocked_by_review_required`가 닫히는 상태 달성

#### P0-2. strict source-tree cohort 달성 또는 waiver 명문화

현재 canonical cohort는 `allowed_divergence_with_explicit_risk` 정책으로 attention 상태다.

필요 작업:

1. 동일 source tree에서 closeout chain 전체 연속 재생성
2. affected component의 mtime drift 정리
3. `strict_same_fingerprint=true`, `modified_after_generated_at_count=0` 달성 확인
4. strict pass가 불가능하면 divergence 허용 조건, owner, expiry, rollback trigger를 release policy에 명시

#### P0-3. checked-in vs live rerun 이중 판정 도입

현재 보고서들은 checked-in pass와 live rerun fail/미완주를 함께 다룬다. 이를 사람이 읽고 구분하는 수준에서 끝내지 말고 JSON field로 모델링해야 한다.

권장 필드:

```json
{
  "checked_in_state": "pass",
  "live_rerun_state": "fail_or_not_run",
  "authoritative_for_release": "checked_in_until_clean_rebuild",
  "last_full_rebuild_verified_at": null,
  "rerun_required_before_release": true
}
```

### 6.2 P1 — evidence chain 완성도 향상

#### P1-1. artifact freshness debt 32건 backfill

현재 debt queue는 크게 `runs_historical_archive` 29건과 `ops_reports_producer_refresh` 3건으로 나뉜다.

필요 작업:

1. `safe_to_backfill=true` artifact에 envelope/currentness metadata 추가
2. historical run artifact는 archive/exemption policy로 분류
3. producer-refresh 대상 3건은 generator를 갱신해 향후 자동으로 envelope를 쓰게 함
4. 완료 후 `artifact-freshness-report.json`이 `status=pass`로 전환되는지 확인

#### P1-2. raw registry atomic promotion

현재 checked-in bundle은 pass지만, live profile rerun gap과 canonical path 오염 위험이 계속 지적된다.

필요 작업:

1. 모든 profile matrix를 먼저 `tmp/raw-registry-cross-env/`에 생성
2. schema validation과 bundle validation을 통과할 때만 `ops/reports/`로 atomic promote
3. 실패 시 기존 canonical pass artifact 보존
4. promote 전후 SHA-256과 source_tree_fingerprint 기록

#### P1-3. release evidence dashboard 도입

현재 정보가 여러 report에 분산되어 있다. 단일 dashboard artifact를 두면 운영 판단이 쉬워진다.

권장 dashboard 축:

| Gate | Checked-in | Strict/live | Risk | Owner | Expiry | Next action |
|---|---|---|---|---|---|---|
| closeout | pass | not fully rebuilt | accepted risk 3 | runtime-maintainer | 2026-05-07 | revalidate |
| cohort | attention | strict fail | fingerprint/mtime | runtime-maintainer | 2026-05-07 | repair cohort |
| freshness | attention | not rerun as pass | metadata debt 32 | ops owner | before clean release | backfill |
| raw registry | pass | live gap reported | profile reproducibility | registry owner | immediate | atomic promotion |
| bootstrap | checked-in pass | current runtime fail | environment | release builder | immediate | dev install / env class |

### 6.3 P2 — 운영 경계와 재현성 품질

#### P2-1. release source / review snapshot / public docs profile 분리

현재 ZIP에는 `.obsidian/`, `.vscode/`, `tmp/`, `runs/`, `external-reports/`, `wiki/`, `system/`, `raw/`가 함께 들어 있다. 이는 full local review snapshot으로는 자연스럽지만 release source와 public docs에는 과하다.

필요 작업:

1. profile 3종 정의: `release_source`, `review_snapshot`, `public_docs`
2. profile별 include/exclude manifest 생성
3. 각 profile artifact SHA-256 기록
4. CI에서 profile별 boundary check 실행

#### P2-2. rollback rehearsal evidence 생성

archive apply는 완료되었지만 실제 rollback rehearsal pass artifact는 확인되지 않는다.

필요 작업:

1. rollback dry-run diagnostic report 생성
2. 최소 1개 archived candidate 복원 fixture test
3. rollback SLA와 retention 기간 문서화

#### P2-3. bootstrap environment class 추가

bootstrap report에는 `environment_class`가 없다. checked-in pass와 review container fail을 분리하려면 환경 유형을 report에 기록해야 한다.

권장 값:

- `release_builder`
- `developer_cleanroom`
- `review_container`
- `ci`

함께 기록할 필드:

- `dependency_source`
- `install_attempted`
- `install_result`
- `venv_path`
- `python_executable`
- `offline_or_network_restricted`

#### P2-4. review archive 최신화

`review-archive-report.json`은 존재하지만 2026-04-28 생성 artifact다. 2026-04-30 이후 post-review 상태를 review archive로 배포하려면 재생성하고 SHA를 남겨야 한다.

---

## 7. 새로 식별한 추가 개선안

두 신규 리뷰가 이미 제안한 IM/N/I 시리즈에 더해, 이번 실제 파일 대조 과정에서 다음 개선안을 추가한다.

### ADD-01. report compiler에 “claim provenance” 표준 추가

통합 보고서가 하위 리뷰의 주장을 합칠 때, 각 claim마다 다음 provenance를 붙인다.

- `checked_in_json_confirmed`
- `schema_validated`
- `live_rerun_confirmed`
- `review_reported_only`
- `inferred_from_file_inventory`
- `not_reverified_due_environment`

이를 적용하면 “4개 리뷰 전원 동의”와 “4개 리뷰 전원 직접 실행” 혼동을 줄일 수 있다.

### ADD-02. strict cohort check에 ZIP metadata-aware mode 추가

ZIP으로 전달된 review snapshot은 추출 과정에서 filesystem mtime이 바뀔 수 있다. `release-evidence-cohort-check`에 `--zip-metadata` 또는 `--mtime-source embedded_currentness` mode를 추가해, review snapshot에서는 추출 mtime이 아닌 embedded metadata/manifest를 기준으로 strict 진단할 수 있게 한다.

### ADD-03. live rerun command는 기본적으로 noncanonical output을 강제

`*-check` target은 이미 tmp output을 많이 사용하지만, raw registry profile matrix처럼 canonical path에 직접 쓸 수 있는 경로가 남아 있다. review container에서 live rerun을 할 때는 `REVIEW_DIAGNOSTIC_OUT_DIR=tmp/review-diagnostics/<timestamp>/` 같은 일괄 override를 지원하는 것이 안전하다.

### ADD-04. review archive report freshness gate 추가

`review-archive-report.json`처럼 존재하지만 오래된 artifact는 “존재함”과 “현재 release snapshot을 대표함”을 분리해야 한다. `generated_artifact_index` 또는 dashboard에서 `representative_of_current_zip=false` 같은 축을 추가한다.

### ADD-05. deselection policy에 budget과 expiry를 추가

현재 policy file에는 reason과 policy_ref가 있다. 여기에 다음을 추가한다.

- `expires_at`
- `max_allowed_deselected_count`
- `owner`
- `revalidation_command`
- `gate_effect_when_expired`
- `gate_effect_when_count_increases`

### ADD-06. learning readiness signal별 owner와 최소 evidence contract 추가

6개 signal을 하나의 blocker reason 문자열로만 다루면 개선 추적이 어렵다. 각 signal에 owner, required evidence, minimum sample size, next evaluation command를 붙인다.

### ADD-07. generated report의 “source_command realism” 검증

일부 report의 `source_command`는 canonical generation command를 설명하지만, 실제 검토 환경에서는 동일 명령이 다르게 동작할 수 있다. report마다 `source_command_verified_in_environment` 또는 `reproduction_last_verified_at`을 별도 field로 두면 혼동을 줄일 수 있다.

### ADD-08. raw registry live rerun에 progress/heartbeat 추가

이번 검토에서 raw registry bundle rerun은 도구 자동 인터럽트로 미완주했다. long-running command는 heartbeat, phase progress, partial diagnostic artifact를 남겨야 review container에서도 “어디까지 진행했는지”를 알 수 있다.

### ADD-09. version labels를 immutable evidence identifier로 치환

문서에서 v65/v66/v67을 계속 쓰려면 각 label과 ZIP SHA, source timestamp, report file path의 mapping table이 필요하다. 그렇지 않으면 report 간 비교는 SHA와 `generated_at` 중심으로 통일하는 것이 안전하다.

### ADD-10. release closeout summary에 component count 설명 추가

closeout summary는 component 7개, evidence cohort는 component 9개다. 이는 오류라기보다 감사 범위 차이다. README와 closeout summary에 “closeout component model”과 “cohort ordered-chain model”의 차이를 명시해야 한다.

---

## 8. 권장 후속 실행 순서

### Tranche A — release 직전 필수 재검증

1. clean release-builder 환경 준비
2. `make dev-install`
3. `make bootstrap-preflight`
4. `make release-evidence-closeout`
5. `make release-evidence-cohort-check`
6. strict pass가 아니면 divergence policy와 accepted risk expiry를 갱신

### Tranche B — signoff dependency 제거

1. `auto-improve-readiness.json`의 6개 learning signal별 defect ticket 작성
2. 최소 sample size와 telemetry coverage를 확보
3. high rework / defect escape proxy를 줄이는 구체 메커니즘 개선
4. signoff 없이 closeout pass 가능한 상태로 전환

### Tranche C — artifact freshness pass 전환

1. debt queue 32건 export
2. runs historical archive 29건은 archive/exemption 또는 envelope backfill
3. ops report producer refresh 3건은 generator 수정
4. `artifact-freshness-report.json` 재생성
5. `stable_contract_debt_artifact_count=0` 또는 explicit nonblocking debt policy 달성

### Tranche D — reproducibility hardening

1. raw registry atomic temp generation 도입
2. bootstrap environment class 추가
3. strict cohort ZIP metadata-aware mode 추가
4. review live rerun output directory 일괄 격리
5. dashboard artifact 생성

### Tranche E — packaging boundary 확정

1. `release_source`, `review_snapshot`, `public_docs` profile 문서화
2. profile별 manifest와 SHA 생성
3. `review-archive-report.json` 최신화
4. public surface CI check와 full vault review check 분리

---

## 9. 결론

두 신규 리뷰는 기존 대조 보고서와 실제 파일을 기준으로 보았을 때 **핵심 사실관계가 맞고, 서로 보완적**이다. 신규 리뷰 1은 세부 근거와 개선안이 가장 완전하고, 신규 리뷰 2는 의사결정용 요약으로 적합하다. 실제 ZIP의 checked-in JSON evidence는 schema-valid하며, 기준 리뷰 이후 핵심 artifact가 생성되고 closeout이 `release_ready=true`로 이동한 것은 사실이다.

다만 남은 작업 역시 두 리뷰가 말한 것보다 작지 않다. 현재 상태는 “release-ready”라는 단어만 떼어내면 과대평가될 수 있다. 정확한 운영 표현은 **`signoff_release_ready` 또는 `release_ready_with_accepted_risk`**다. clean release-ready로 승격하려면 signoff 만료 전 재검증, strict cohort repair, freshness debt backfill, live rebuild reproducibility, packaging boundary 정리가 필요하다.

---

## Appendix A. 실제 파일 기반 세부 확인값

### A.1 Makefile target 존재 여부

| target | 상태 |
|---|---|
| `learning-readiness-signoff` | 부재 |
| `learning-readiness-signoff-check` | 부재 |
| `learning-readiness-signoff-template` | 부재 |
| `release-evidence-cohort` | 부재 |
| `release-evidence-cohort-check` | 부재 |
| `raw-registry-cross-environment-profile-matrices` | 부재 |
| `raw-registry-cross-environment-evidence-bundle` | 부재 |
| `raw-registry-cross-environment-evidence-bundle-check` | 부재 |
| `artifact-freshness` | 부재 |
| `artifact-freshness-check` | 부재 |
| `archive-execution-manifest-apply` | 부재 |
| `archive-execution-manifest-defer` | 부재 |
| `archive-execution-manifest-rollback` | 부재 |
| `test-execution-summary` | 부재 |
| `test-execution-summary-aggregate` | 부재 |
| `release-evidence-closeout` | 부재 |
| `bootstrap-preflight` | 부재 |

### A.2 report schema validation 전체 결과

| report | schema | 결과 |
|---|---|---|
| `ops/reports/bootstrap-preflight-report.json` | `ops/schemas/bootstrap-preflight-report.schema.json` | pass |
| `ops/reports/learning-readiness-signoff.json` | `ops/schemas/learning-readiness-signoff.schema.json` | pass |
| `ops/reports/release-evidence-cohort.json` | `ops/schemas/release-evidence-cohort.schema.json` | pass |
| `tmp/release-evidence-cohort.candidate.json` | `ops/schemas/release-evidence-cohort.schema.json` | pass |
| `ops/reports/release-closeout-summary.json` | `ops/schemas/release-closeout-summary.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-evidence-bundle.json` | `ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json` | pass |
| `tmp/raw-registry-cross-environment-evidence-bundle-check.json` | `ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json` | pass |
| `ops/reports/artifact-freshness-report.json` | `ops/schemas/artifact-freshness-report.schema.json` | pass |
| `ops/reports/archive-execution-manifest.json` | `ops/schemas/archive-execution-manifest.schema.json` | pass |
| `ops/reports/test-execution-summary.json` | `ops/schemas/test-execution-summary.schema.json` | pass |
| `ops/reports/test-execution-summary-shards/report-contract-summary.json` | `ops/schemas/test-execution-summary.schema.json` | pass |
| `ops/reports/generated-artifact-index.json` | `ops/schemas/generated-artifact-index.schema.json` | pass |
| `ops/reports/manual-mutate-defect-registry.json` | `ops/schemas/manual-mutate-defect-registry.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix-linux-c-utf8.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix-windows-utf8.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/raw-registry-cross-environment-matrix-macos-utf8.json` | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | pass |
| `ops/reports/review-archive-report.json` | `ops/schemas/review-archive-report.schema.json` | pass |

### A.3 현재 실행 검증 한계

- 현재 런타임은 dev dependency가 완비된 release-builder가 아니다.
- `bootstrap_preflight --dev`는 `mypy`, `ruff` missing으로 fail했다.
- `release-evidence-cohort-check` strict diagnostic은 fail했고, 이번 추출 환경에서는 mtime drift count가 canonical report보다 크게 산출되었다.
- `raw-registry-cross-environment-evidence-bundle` live rerun은 도구 자동 인터럽트로 미완주하여 새 결론으로 사용하지 않았다.
- 따라서 이 보고서의 authoritative 판정은 checked-in JSON + schema validation + 제한 live diagnostic의 조합이다.
