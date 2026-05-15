# LLM Wiki vNext Dual Integrated Review Cross-check Improvement Report

- **작성일:** 2026-04-30 (Asia/Seoul)
- **작성 언어:** 한국어
- **파일명:** `llm_wiki_vnext_dual_integrated_review_crosscheck_improvement_report_20260430.md`
- **검토 대상 신규 리뷰 1:** `llm_wiki_vnext_integrated_review_report_20260430.md`
- **검토 대상 신규 리뷰 2:** `LLM Wiki vNext 통합 후속 검토 보고서_20260430.md`
- **대조한 기존 후속 감사 보고서:** `llm_wiki_vnext_post_review_followup_audit_report_20260430.md`
- **대조한 기준 리뷰:** `external-reports/llm_wiki_vnext_two_review_crosscheck_improvement_report_20260429.md`
- **대조한 실제 ZIP:** `LLM Wiki vNext(61).zip`
- **최종 판정:** **`not_release_ready_but_evidence_system_materially_progressed`**

---

## 0. 결론 요약

두 신규 통합 리뷰를 전문 기준으로 확인하고, 기존 후속 감사 보고서 및 실제 ZIP 파일 상태와 다시 대조한 결론은 다음과 같다.

현재 저장소는 2026-04-29 기준 리뷰 이후 **release evidence 체계가 실질적으로 성숙**했다. 특히 `release-evidence-closeout` target, source-tree coherence 표면화, accepted-risk metadata, learning-readiness signoff schema, structured deselection policy, archive execution manifest, raw registry cross-environment matrix, CycloneDX offline schema alias가 실제 파일로 확인된다.

그러나 현재 ZIP은 여전히 **release-ready가 아니다.** 직접 원인은 변하지 않았다. 체크인된 `ops/reports/release-closeout-summary.json`은 `status=fail`, `release_ready=false`, `blocker_count=1`이고, hard blocker는 `learning_blocked_by_review_required`다. 이 blocker를 닫는 실제 `ops/reports/learning-readiness-signoff.json`은 존재하지 않는다.

이번 재대조에서 추가로 명확해진 점은 세 가지다.

1. 두 신규 리뷰는 본질적으로 서로 충돌하지 않는다. 두 번째 리뷰가 첫 번째 리뷰보다 훨씬 상세하며, 첫 번째 리뷰의 내용을 대부분 포함·확장한다.
2. 기존 후속 감사 보고서와도 핵심 판정은 일치한다. 다만 두 신규 리뷰는 `raw registry replay drift`, tranche 계획, 46개 변경 파일 appendix, no-schema JSON 목록을 더 체계적으로 부각한다.
3. 실제 파일 재실행에서는 `raw_registry_cross_environment_matrix` drift가 현재 추출 경로에서는 재현되지 않았다. 반면 `artifact_freshness_runtime`의 mtime 민감성은 재현되었고, 체크인 report의 `mtime_sensitive_attention_artifact_count=38`이 추출 파일시스템 재실행 시 `90`으로 증가했다. 따라서 `raw registry replay drift`는 환경민감 위험으로 유지하고, artifact freshness에는 ZIP-aware mtime mode가 더 시급하다.

---

## 1. 입력 리뷰 전문 검토 결과

### 1.1 신규 리뷰 1: `llm_wiki_vnext_integrated_review_report_20260430.md`

| 항목 | 값 |
|---|---:|
| bytes | 43,211 |
| lines | 577 |
| heading count | 53 |
| SHA-256 | `1470ecdc33e0829123161b6f2faf033d8b5a0d7cd33c16ff2fea02d77163248f` |

이 리뷰는 3개의 후속 리뷰를 하나의 통합 판정으로 압축한 문서다. 핵심 구조는 다음과 같다.

- Executive Summary에서 `materially_progressed_after_20260429_review_but_still_not_release_ready`를 명시한다.
- 기준 리뷰 이후 반영된 작업분을 `release closeout orchestration`, source-tree coherence, learning signoff plumbing, test execution summary, archive manifest, artifact freshness queue, raw registry matrix, CycloneDX offline validation으로 정리한다.
- 지정 리뷰 권고별 현재 상태 매트릭스를 제공한다.
- 직접 검증 결과와 신규 개선 방안을 비교적 압축적으로 제시한다.

**판정:** 신규 리뷰 1은 결론과 핵심 근거가 정확하다. 다만 독자가 실제 조치 순서를 잡기에는 리뷰 2보다 세부 수치와 appendix가 적다. 따라서 “상위 통합 요약본”으로 보는 것이 적절하다.

### 1.2 신규 리뷰 2: `LLM Wiki vNext 통합 후속 검토 보고서_20260430.md`

| 항목 | 값 |
|---|---:|
| bytes | 59,216 |
| lines | 990 |
| heading count | 67 |
| SHA-256 | `5d012e7114d69b96a2c753c62a5353877eb5b608e39cfb04c109193d2013b37e` |

이 리뷰는 신규 리뷰 1보다 훨씬 상세한 후속 통합 보고서다. 특히 다음 항목이 더 강하다.

- ZIP 인벤토리와 기준 리뷰 파일 지표를 별도 표로 명시한다.
- 기준 리뷰 이후 46개 변경 파일을 전체 목록으로 보존한다.
- Release closeout component별 `generated_at`, fingerprint prefix, 해석을 제공한다.
- 리뷰 A/B/C별 고유 발견을 분리한다.
- 직접 검증 결과 차이, 특히 raw registry matrix 재실행 결과 차이를 별도 설명한다.
- Tranche 1~4의 실행 계획으로 남은 작업을 단계화한다.

**판정:** 신규 리뷰 2는 신규 리뷰 1의 실질적 superset에 가깝다. 보고서 구조와 실행 계획이 더 정교하므로 실제 개선 작업의 기준 문서로는 신규 리뷰 2를 우선 삼는 것이 맞다. 신규 리뷰 1은 결론 요약과 독립적 재확인 자료로 활용하면 된다.

### 1.3 두 신규 리뷰 간 정합성

| 검토 축 | 신규 리뷰 1 | 신규 리뷰 2 | 대조 판정 |
|---|---|---|---|
| 최종 상태 | materially progressed, not release-ready | materially progressed, not release-ready | **일치** |
| 핵심 blocker | `learning_blocked_by_review_required` | `learning_blocked_by_review_required` | **일치** |
| signoff artifact | schema/path만 존재, 실제 JSON 부재 | schema/path만 존재, 실제 JSON 부재 | **일치** |
| source-tree coherence | attention/accepted risk | attention/accepted risk, 6 fingerprints | **일치** |
| archive manifest | 구현, dry-run, applied=0 | 구현, dry-run, applied=0 | **일치** |
| raw registry matrix | 구현됐으나 replay drift 위험 | 구현됐으나 환경민감 drift 위험 상세화 | **일치, 리뷰 2가 더 상세** |
| artifact freshness | debt queue 존재, backlog 잔존 | debt queue 존재, mtime 민감성 강조 | **일치, 리뷰 2가 더 상세** |
| action plan | tranche 중심 | tranche + appendix 중심 | **상호 보완** |

---

## 2. 기존 리뷰 및 기준 리뷰와의 대조

### 2.1 기존 후속 감사 보고서와의 대조

기존 후속 감사 보고서 `llm_wiki_vnext_post_review_followup_audit_report_20260430.md`는 763 lines, SHA-256 `3de73d18e431f6cdd3b5b1654cc566e7851fe6ff49044f1f6b40233ab955fa0c`이며, 이전 작업에서 생성된 후속 감사 기준선이다.

| 항목 | 기존 후속 감사 보고서 | 두 신규 리뷰 | 현 대조 결과 |
|---|---|---|---|
| 최종 판정 | not release-ready, materially progressed | not release-ready, materially progressed | **유지** |
| 직접 blocker | learning blocker 1건 | learning blocker 1건 | **유지** |
| targeted tests | 최소 45건 직접 OK로 보고 | 리뷰 B 기여로 재인용 | **대체로 유지. 본 재검증은 일부 장시간 테스트 timeout으로 제한** |
| ruff/mypy | 통과 | 리뷰 B가 통과 근거로 제시 | **직접 재확인: 둘 다 통과** |
| raw registry matrix | pass 중심 | 리뷰 A drift 발견 포함 | **drift 위험은 신규로 강화된 쟁점** |
| artifact freshness mtime | 추출 환경 mtime skew 언급 | 리뷰 B/C가 상세화 | **직접 재현: mtime count 증가** |
| 실행 계획 | P0/P1/P2 중심 | Tranche 1~4로 재구성 | **신규 리뷰 2가 운영 계획으로 더 적합** |

### 2.2 기준 리뷰(`20260429`)와의 대조

기준 리뷰 파일은 ZIP 내부의 `external-reports/llm_wiki_vnext_two_review_crosscheck_improvement_report_20260429.md`다.

| 항목 | 값 |
|---|---:|
| bytes | 36,288 |
| lines | 639 |
| ZIP timestamp | `2026-04-29 21:21:30` |
| SHA-256 | `b984cd700ce96114743edb6e3312e39c480366c346fcc0b6f374b15dfbc0f55e` |

기준 리뷰 이후 실제 ZIP metadata상 46개 파일이 변경되었다. 따라서 현재 ZIP은 기준 리뷰 당시와 같은 스냅샷이 아니라, 기준 리뷰 권고 일부가 반영된 후속 스냅샷이다.

---

## 3. 실제 ZIP 및 파일 상태 재검증

### 3.1 ZIP 무결성 및 인벤토리

| 항목 | 값 |
|---|---:|
| ZIP SHA-256 | `3cfbcaa58a1be229457b68be8cf9fd7abdd6dbfc4d9a5936858ddf09f6e638ed` |
| entries | 1,705 |
| files | 1,621 |
| dirs | 84 |
| compressed bytes | 190,936,115 |
| uncompressed bytes | 241,291,315 |
| `zipfile.testzip()` | `None` |

확장자 상위 분포는 `.md` 949, `.py` 291, `.json` 249, `.pdf` 62, `.txt` 28이며, top-level 파일 분포는 `raw` 446, `wiki` 417, `ops` 320, `runs` 156, `tests` 129, `system` 71, `external-reports` 42다. 이는 두 신규 리뷰의 인벤토리 수치와 일치한다.

### 3.2 기준 리뷰 이후 변경 파일 46건

기준 리뷰 timestamp 이후 변경된 파일은 정확히 46건이다. 분포는 `tests` 11, `ops/reports` 10, `ops/schemas` 7, `ops/scripts` 6, `ops root/other` 4, root docs/config 3, runs templates 2, `.github` 1, `.obsidian` 1, `ops/policies` 1로 정리된다.

상세 목록은 [Appendix A](#appendix-a--기준-리뷰-이후-변경-파일-46건)에 보존했다.

---

## 4. Release Closeout 현재 상태

### 4.1 핵심 상태

| 항목 | 값 |
|---|---:|
| `profile` | `base` |
| `status` | `fail` |
| `release_ready` | `False` |
| `component_count` | 6 |
| `ready_component_count` | 5 |
| `blocker_count` | 1 |
| `accepted_risk_count` | 3 |
| `source_tree_coherence_status` | `attention` |

**판정:** 두 신규 리뷰의 핵심 결론은 실제 파일과 일치한다. 현재 closeout은 `fail`이며 release-ready가 아니다.

### 4.2 Component 상태

| component | ready | source_status | generated_at | fingerprint prefix | currentness |
|---|---:|---|---|---|---|
| `release_smoke` | True | `pass` | `2026-04-28T16:55:02Z` | `8e47ee468ebb` | `current` |
| `test_summary` | True | `pass` | `2026-04-29T15:33:57Z` | `c43250cae328` | `current` |
| `raw_registry` | True | `pass` | `2026-04-29T14:57:03Z` | `dc38a5cada27` | `current` |
| `artifact_freshness` | True | `attention` | `2026-04-29T15:34:50Z` | `3a817c254b4d` | `current` |
| `generated_index` | True | `attention` | `2026-04-29T15:34:20Z` | `61a3ffcb0809` | `current` |
| `auto_improve_readiness` | False | `unknown` | `2026-04-29T08:00:17Z` | `598185ee58fc` | `current` |

핵심 해석은 다음과 같다.

- 6개 component 중 5개는 ready다.
- `auto_improve_readiness`만 ready=false이며, 이 component가 hard blocker의 원천이다.
- `release_smoke`는 pass이지만 `generated_at=2026-04-28T16:55:02Z`라 기준 리뷰 이후 46개 변경보다 오래된 evidence다.
- 6개 component fingerprint가 모두 다르므로, strict same-cohort evidence는 아직 아니다.

### 4.3 Hard blocker

| 항목 | 값 |
|---|---|
| source | `auto_improve_readiness` |
| code | `learning_blocked_by_review_required` |
| severity | `blocker` |
| gate_effect | `review_required` |

`ops/reports/learning-readiness-signoff.json`은 존재하지 않는다. 따라서 signoff schema와 closeout 변환 경로가 구현되어 있어도 blocker는 현재 닫히지 않는다.

`auto-improve-readiness.json`의 learning metrics는 다음과 같다.

| metric | 현재 값 | 해석 |
|---|---:|---|
| `attempts_considered` | 7 | 최소 10 미달 |
| `session_calibration_status` | `no_session_context` | 세션 맥락 부족 |
| `telemetry_coverage_ratio` | 0.0 | telemetry-backed learning evidence 없음 |
| `rework_count` | 5 | threshold 초과 |
| `hold_moving_average` | 0.2857 | threshold 초과 |
| `discard_moving_average` | 0.1429 | threshold 이내 또는 상대적 양호 |
| `defect_escape_pair_count` | 3 | threshold 초과 |

### 4.4 Accepted risks

| code | source | severity | gate_effect | expires_at | owner |
|---|---|---|---|---|---|
| `artifact_freshness_attention` | `artifact_freshness` | `warn` | `accepted_risk` | `2026-05-06T16:43:18Z` | `runtime-maintainer` |
| `generated_index_archive_advisory` | `generated_index` | `warn` | `accepted_risk` | `2026-05-06T16:43:18Z` | `runtime-maintainer` |
| `source_tree_coherence_attention` | `source_tree_coherence` | `warn` | `accepted_risk` | `2026-05-06T16:43:18Z` | `runtime-maintainer` |

세 accepted risk는 hard blocker가 아니라 advisory/attention debt를 임시 수락하는 장치다. 모두 2026-05-06 만료 조건을 가지므로, 만료 전 재검증 또는 실제 debt cleanup이 필요하다.

---

## 5. 주요 개선 작업의 실제 반영 상태

### 5.1 Release evidence closeout target

`Makefile`의 dry-run 결과는 다음 순서를 실제로 강제한다.

```text
release-smoke-full
→ registry-preflight
→ test-execution-summary
→ generated-artifact-index
→ archive-execution-manifest-report
→ artifact-freshness
→ release-closeout-summary
```

**판정:** 기준 리뷰의 `strict release evidence closeout target` 권고는 구현 완료로 본다. 단, 이 target의 최신 전체 실행 결과가 release-ready로 닫힌 것은 아니다.

### 5.2 Learning readiness signoff plumbing

| 구성 요소 | 실제 상태 |
|---|---|
| `ops/schemas/learning-readiness-signoff.schema.json` | 존재 |
| `ops/scripts/release_closeout_summary.py`의 signoff 변환 경로 | 존재 |
| 관련 테스트 | 존재 |
| `ops/reports/learning-readiness-signoff.json` | **부재** |

**판정:** 구현은 진행됐지만 운영 evidence가 없으므로 P0는 미완이다.

### 5.3 Test execution summary 및 structured deselection

| 항목 | 값 |
|---|---:|
| `status` | `pass` |
| passed | 197 |
| failed | 0 |
| errors | 0 |
| deselected tests | 3 |
| Python version recorded | `3.14.3` |
| pytest version recorded | `8.4.2` |
| plugin autoload policy | `disabled` |
| interpreter path class | `repo_virtualenv` |

**판정:** test deselection semantics는 실제로 machine-readable evidence로 승격됐다. 다만 체크인 summary의 Python은 3.14.3이고, 본 재검증 환경은 Python 3.13.5다. 이는 테스트 실패 사유는 아니지만 reproducibility metadata 관점에서는 계속 기록해야 한다.

### 5.4 Artifact freshness

체크인된 `artifact-freshness-report.json` summary는 다음과 같다.

| metric | checked-in 값 |
|---|---:|
| artifact_count | 163 |
| stale_artifact_count | 38 |
| missing_schema_count | 0 |
| missing_artifact_envelope_count | 32 |
| unknown_currentness_artifact_count | 32 |
| stable_contract_debt_artifact_count | 32 |
| stable_contract_debt_issue_count | 64 |
| mtime_sensitive_attention_artifact_count | 38 |
| mtime_sensitive_attention_issue_count | 38 |
| safe_to_backfill_artifact_count | 125 |

Debt queue는 다음과 같다.

| queue | items | issues |
|---|---:|---:|
| `runs_historical_archive` | 29 | 58 |
| `ops_reports_producer_refresh` | 3 | 6 |
| `mtime_sensitive_regeneration` | 38 | 38 |

본 재실행에서 `artifact_freshness_runtime --out tmp/validation/artifact-freshness-report.json`은 다음처럼 달라졌다.

| metric | checked-in | 추출 파일시스템 재실행 |
|---|---:|---:|
| stale_artifact_count | 38 | 89 |
| mtime_sensitive_attention_artifact_count | 38 | 90 |
| safe_to_backfill_artifact_count | 125 | 73 |

**판정:** 두 신규 리뷰가 지적한 mtime 민감성은 실제로 재현된다. release ZIP 검증은 파일시스템 mtime이 아니라 ZIP metadata 또는 embedded currentness를 기준으로 하는 mode가 필요하다.

### 5.5 Generated artifact index 및 archive execution manifest

| 항목 | generated index | archive manifest |
|---|---:|---:|
| status | `attention` | `attention` |
| canonical_report_count | 36 | - |
| archive_candidate_count | 24 | 24 |
| planned_move_count | - | 24 |
| applied_move_count | - | 0 |
| rollback_available_count | - | 0 |

Archive manifest move surface 분포는 다음과 같다.

| surface | count |
|---|---:|
| `ops_reports` | 3 |
| `external_reports` | 20 |
| `runs` | 1 |

**판정:** manifest는 구현됐고 dry-run evidence도 존재한다. 그러나 실제 archive cleanup은 아직 적용되지 않았다.

### 5.6 Raw registry preflight / reproducibility / cross-environment matrix

| 항목 | 값 |
|---|---:|
| preflight status | `pass` |
| entry_count | 446 |
| error_count | 0 |
| warning_count | 0 |
| path_alias_match_count | 0 |
| content_hash_fallback_count | 0 |
| matrix status | `pass` |
| matrix rows | 5 |

Matrix rows:

| profile | evidence_mode | status | check_count |
|---|---|---:|---:|
| `linux-c-utf8` | `live_preflight_and_ci_workflow` | `pass` | 5 |
| `windows-utf8` | `ci_workflow` | `pass` | 3 |
| `macos-utf8` | `ci_workflow` | `pass` | 3 |
| `path-separator-fixture` | `fixture` | `pass` | 2 |
| `locale-utf8-fixture` | `fixture` | `pass` | 2 |

본 재실행에서는 `raw_registry_preflight`와 `raw_registry_cross_environment_matrix`가 모두 pass였고, `path_alias_match_count`도 0으로 유지됐다. 따라서 리뷰 A가 보고한 `0 → 332` drift는 현재 추출 경로에서는 재현되지 않았다.

그러나 `semantic_compare_fields`에는 `stats.path_alias_match_count`가 포함되어 있다. 이 값은 metric semantics상 “canonical storage_path가 없지만 manual/exported/deterministic alias가 존재하는 entry 수”이므로, 추출 경로·alias fixture·환경에 민감할 수 있다. 따라서 리뷰 A의 발견은 “현재 항상 재현되는 실패”라기보다 “현재 matrix policy가 환경민감 통계를 strict semantic field로 취급할 위험”으로 해석하는 것이 정확하다.

### 5.7 CycloneDX offline validation

`ops/scripts/schema_constants_runtime.py`에는 `CYCLONEDX_16_SCHEMA_URI → CYCLONEDX_16_SCHEMA_PATH` alias가 존재하고, 본 schema validation에서도 CycloneDX HTTP schema URI 1건이 local alias로 성공 검증됐다.

**판정:** offline validation 정책은 구현 완료에 가깝다. 남은 것은 외부 검증 도구와 내부 local alias 정책 간의 문서화다.

### 5.8 Manual mutate defect registry 및 writer output boundary

| 항목 | 상태 |
|---|---|
| manual mutate registry status | `pass` |
| registered defects | 2 |
| fixed defects | 2 |
| covered regressions | 2 |
| unresolved/uncovered | 0 |

writer output boundary는 `/tmp` 등 vault 밖 출력 경로를 거부하는 테스트와 실제 runtime error로 확인된다. 본 재실행에서도 `/tmp/...`를 output path로 지정한 raw registry command는 `repo output path must stay under vault`로 거부됐다. 이 동작은 의도된 보안·재현성 경계로 보인다.

---

## 6. 직접 검증 결과

### 6.1 정적 분석

| 명령 | 결과 |
|---|---|
| `python3 --version` | Python 3.13.5 |
| `python3 -m ruff check ops/scripts tests tools` | `All checks passed!` |
| `python3 -m mypy @ops/mypy-allowlist.txt` | `Success: no issues found in 161 source files` |

### 6.2 변경 Python 파일 문법 검증

기준 리뷰 이후 변경된 `.py` 파일 17건에 대해 `python3 -m py_compile`을 실행했다.

| 항목 | 값 |
|---|---:|
| changed `.py` files | 17 |
| py_compile returncode | 0 |
| errors | 0 |

### 6.3 JSON schema validation

`tmp`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `__pycache__`를 제외하고 JSON 파일을 스캔했다.

| 항목 | 값 |
|---|---:|
| JSON files scanned | 249 |
| parse errors | 0 |
| local schema refs, CycloneDX alias 포함 | 171 |
| local schema validation pass | 171 |
| local schema validation fail | 0 |
| external/draft/non-local schema refs | 66 |
| no `$schema` JSON | 12 |
| CycloneDX HTTP URI local alias validated | 1 |

No-schema JSON 목록은 [Appendix B](#appendix-b--schema-없는-json-12건)에 보존했다.

### 6.4 Targeted tests

본 세션에서 모든 장시간 suite를 끝까지 재생성하지는 못했다. `unittest` 통합 실행은 40개 `ok` 이후 timeout이 발생했고, 일부 `pytest` 파일 단위 실행도 장시간 cleanup/collection 구간에서 timeout이 발생했다. 따라서 여기서는 **직접 완료된 결과**와 **체크인 evidence**를 분리한다.

직접 완료된 안정 테스트 그룹:

| 테스트 그룹 | 결과 |
|---|---|
| `tests.test_archive_execution_manifest` | 2 tests OK |
| `tests.test_raw_registry_cross_environment_matrix` | 3 tests OK |
| `tests.test_cyclonedx_sbom` | 3 tests OK |
| `tests.test_makefile_static_gates` | 25 tests OK |
| `tests.test_ci_workflow_static` | 4 tests OK |
| selected `tests/test_release_closeout_summary.py` 개별 pytest | 최소 4개 추가 OK 확인 |

체크인된 `ops/reports/test-execution-summary.json`은 `197 passed / 0 failed / 0 errors / 3 deselected`를 기록한다. 본 보고서에서는 이를 “체크인 evidence”로만 취급하고, 현 세션의 full live pass로 주장하지 않는다.

### 6.5 Runtime command checks

| 명령 | 결과 |
|---|---|
| `archive_execution_manifest --mode dry_run --out tmp/validation/...` | `attention`, 24 planned, 0 applied |
| `release_closeout_summary --no-fail --out tmp/validation/...` | `fail`, `release_ready=false`, blocker 1 |
| `raw_registry_preflight --out tmp/validation/...` | `pass`, 446 entries, alias count 0 |
| `raw_registry_cross_environment_matrix --out tmp/validation/...` | `pass`, 5 rows |
| `artifact_freshness_runtime --out tmp/validation/...` | `attention`, mtime-sensitive 90로 증가 |

---

## 7. 두 신규 리뷰에 대한 감사 판정

### 7.1 유지해야 할 결론

두 신규 리뷰의 다음 결론은 실제 파일과 대조해도 유지된다.

1. 기준 리뷰 이후 작업은 단순 문서 수정이 아니라 script/schema/report/test/CI/Makefile 전반의 실질 구현이다.
2. release-ready는 아니다.
3. hard blocker는 `learning_blocked_by_review_required` 하나다.
4. signoff schema는 있으나 실제 signoff artifact가 없다.
5. source-tree coherence는 strict pass가 아니라 accepted risk다.
6. archive manifest는 dry-run 계획까지이며 실제 적용은 없다.
7. artifact freshness debt는 큐로 표면화됐지만 backlog는 남아 있다.
8. raw registry cross-env matrix는 생겼지만, release-grade replay evidence로 보강해야 한다.

### 7.2 보정해야 할 표현

| 원문 취지 | 보정 판정 |
|---|---|
| raw registry replay drift가 확인됐다는 표현 | 맞다. 다만 본 재실행에서는 재현되지 않았다. “항상 실패”가 아니라 “환경민감 strict semantic field 위험”으로 표현하는 것이 더 정확하다. |
| schema validation 수치 170/172 차이 | 실제 검증 scope와 CycloneDX alias 포함 여부에 따라 달라질 수 있다. 본 재검증 기준은 249 JSON, 171 local pass, 0 fail이다. 결론상 모순은 없다. |
| targeted tests 45건 직접 실행 OK | 기존 리뷰 B의 기록으로는 유지 가능하다. 본 재검증에서는 일부 장시간 test file이 timeout되어 full 재확인은 하지 못했다. |
| release evidence closeout target 완료 | target 구현은 완료다. 그러나 target의 최신 full 실행 evidence가 release-ready로 닫힌 것은 아니다. |
| artifact freshness checked-in 수치 | checked-in 수치 38은 맞다. 추출 재실행에서는 90으로 증가하므로 ZIP-aware mtime mode 필요성이 더 강해진다. |

---

## 8. 개선 방안 — 우선순위별 실행 계획

### P0. Release-ready 직접 차단 해소

#### P0.1 `learning_blocked_by_review_required`를 닫는다

선택지는 두 가지다.

**경로 A — 실제 learning evidence 보강**

- `attempts_considered >= 10` 달성
- `telemetry_coverage_ratio > 0` 달성
- `session_calibration_status != no_session_context` 달성
- `hold_moving_average < 0.25` 달성
- `rework_count <= 1` 달성
- `defect_escape_pair_count <= 1` 달성
- 최종적으로 `learning_readiness.likely_to_learn=true` 만들기

**경로 B — operator signoff로 accepted risk 전환**

`ops/reports/learning-readiness-signoff.json`을 schema에 맞게 생성한다. 최소 필드는 다음과 같다.

```json
{
  "linked_blocker_id": "learning_blocked_by_review_required",
  "accepted_by": "<operator>",
  "accepted_at": "<UTC timestamp>",
  "expires_at": "<UTC timestamp>",
  "risk_owner": "runtime-maintainer",
  "revalidation_condition": "rerun release evidence closeout before the next release",
  "rollback_trigger": "learning telemetry regresses or auto-improve queue blocks"
}
```

권장 개선은 `make learning-readiness-signoff-template` 또는 `ops/templates/learning-readiness-signoff.json`을 추가해 operator가 수동 JSON을 실수 없이 만들 수 있게 하는 것이다.

#### P0.2 최신 full release evidence chain을 재실행한다

현재 `release_smoke` evidence는 기준 리뷰 이후 변경 파일보다 오래됐다. `make release-evidence-closeout`을 원본 working tree에서 끝까지 실행하고, 결과로 생성된 component들이 동일 cohort 또는 명시적으로 허용된 cohort policy 아래 묶여야 한다.

#### P0.3 source-tree coherence 정책을 확정한다

현재 policy는 `allowed_divergence_with_fingerprints`다. release 기준으로 아래 둘 중 하나를 결정해야 한다.

| 선택지 | 장점 | 단점 |
|---|---|---|
| `strict_same_fingerprint` | release evidence 신뢰도가 가장 높음 | 일부 장시간 report 재생성 비용 증가 |
| `allowed_divergence_with_explicit_risk` | 현실적 운영 가능 | accepted risk 관리·만료·근거 문서화 필요 |

### P1. Evidence portability와 archive/currentness cleanup

#### P1.1 artifact freshness를 ZIP-aware로 만든다

추출 파일시스템 mtime은 release evidence로 불안정하다. 다음 mode를 추가한다.

```bash
python -m ops.scripts.artifact_freshness_runtime   --vault .   --zip-metadata /path/to/release.zip   --mtime-source zip_info
```

또는 currentness envelope를 우선시하고 filesystem mtime은 advisory로 낮춘다.

#### P1.2 archive manifest에 apply/rollback lifecycle을 추가한다

현재는 `dry_run`과 `applied` mode 일부가 있으나 release 운영 관점에서는 다음 3단계가 명확해야 한다.

1. `dry_run`: planned moves 생성
2. `apply`: digest before/after, actual move, rollback path 기록
3. `rollback`: applied manifest 기반 복구

24개 archive candidate는 apply하거나 defer reason/expiry를 붙여야 한다.

#### P1.3 raw registry matrix에서 environment-dependent semantic field를 분리한다

`stats.path_alias_match_count`는 strict semantic compare field에서 분리하는 것이 안전하다.

권장 구조:

```json
{
  "strict_semantic_fields": [
    "artifact_kind",
    "status",
    "stats.entry_count",
    "stats.error_count",
    "stats.warning_count"
  ],
  "environment_dependent_semantic_fields": [
    "stats.path_alias_match_count",
    "environment_fingerprint",
    "path_alias_resolution_mode"
  ]
}
```

#### P1.4 cross-env CI artifact digest collector를 추가한다

현재 Windows/macOS는 CI workflow declaration 중심이다. release-grade evidence로 올리려면 CI가 OS별 matrix report를 업로드하고, collector가 digest bundle을 생성해야 한다.

권장 신규 파일:

`ops/reports/raw-registry-cross-environment-evidence-bundle.json`

필수 필드:

- profile
- runner OS
- generated_at
- report path
- report SHA-256
- semantic compare status
- uploaded artifact name

### P2. Package/review boundary와 reproducibility 정리

#### P2.1 public/release archive와 review snapshot include policy를 분리한다

현재 ZIP에는 `.obsidian`, `.vscode`, placeholder run templates가 포함된다. review snapshot에서는 허용될 수 있지만 public/release package에서는 별도 exclude policy가 필요하다.

#### P2.2 clean ZIP bootstrap contract를 강화한다

체크인 test summary는 `.venv/bin/python` 기준이다. ZIP에는 `.venv`가 없으므로 다음을 명확히 해야 한다.

- clean checkout에서 dependency 설치 명령
- supported Python version range
- plugin autoload disable policy
- long-running suite shard 실행법
- report-contract-summary 재현 절차

#### P2.3 schema zero-count guard를 CI hard gate로 고정한다

현재 `missing_schema_count=0`, schema validation fail 0은 좋은 상태다. 이 상태가 회귀하지 않도록 CI에서 local-schema-backed JSON validation을 hard gate로 유지해야 한다.

---

## 9. 권장 실행 순서

### Tranche 1 — release blocker closeout

1. `ops/templates/learning-readiness-signoff.json` 또는 generator target 추가
2. 실제 learning evidence를 보강할지 operator signoff를 사용할지 결정
3. `ops/reports/learning-readiness-signoff.json` 생성 또는 learning metrics 개선
4. `make release-evidence-closeout` 재실행
5. `release-closeout-summary.json`의 `release_ready=true` 여부 확인

### Tranche 2 — cohort consistency hardening

1. `source_tree_coherence.policy`를 strict 또는 accepted-risk mode로 문서화
2. evidence chain run id 또는 cohort id 추가
3. component별 `generated_at`, report mtime, source fingerprint skew를 blocker/accepted-risk로 일관 처리
4. `release-evidence-closeout-run.json` 단일 manifest 추가

### Tranche 3 — artifact/archive debt cleanup

1. archive planned move 24건 처리
2. `ops_reports_producer_refresh` 3건을 우선 backfill
3. historical run artifact 29건 archive 또는 noncanonical 분류
4. artifact freshness rerun에서 stable debt와 mtime debt 감소 확인

### Tranche 4 — portability and package release

1. ZIP-aware artifact freshness mode 구현
2. raw registry cross-env evidence bundle 추가
3. report-contract pytest shard summary 추가
4. public/release archive exclude policy 적용
5. `provenance` 또는 `sbom` profile을 release 기준으로 선택

---

## 10. 종합 판정

두 신규 리뷰는 모두 신뢰할 수 있으며, 특히 신규 리뷰 2는 실제 개선 작업을 진행하기 위한 운영 계획으로 충분히 상세하다. 기존 후속 감사 보고서와도 본질적 충돌은 없다. 실제 ZIP 파일 대조 결과도 다음 결론을 지지한다.

> **LLM Wiki vNext는 기준 리뷰 이후 evidence system이 명확히 진전됐지만, 현재 release-ready는 아니다. 즉시 닫아야 할 P0는 learning readiness blocker이며, 그 다음은 최신 ordered release evidence rerun, source-tree cohort policy 확정, artifact freshness mtime portability, archive candidate 처리, raw registry replay semantics 정리다.**

---

## Appendix A — 기준 리뷰 이후 변경 파일 46건

| timestamp | path | bytes |
|---|---|---:|
| 2026-04-29 23:43:08 | `.github/workflows/ci.yml` | 7,196 |
| 2026-04-29 23:48:10 | `.obsidian/workspace.json` | 8,362 |
| 2026-04-30 00:15:48 | `Makefile` | 22,962 |
| 2026-04-29 23:41:52 | `ops/direct-script-entrypoints.txt` | 1,922 |
| 2026-04-29 23:56:44 | `ops/manifest.json` | 279,469 |
| 2026-04-29 23:42:12 | `ops/mypy-allowlist.txt` | 6,662 |
| 2026-04-29 22:48:36 | `ops/policies/report-contract-deselections.json` | 1,727 |
| 2026-04-30 00:18:26 | `ops/README.md` | 70,915 |
| 2026-04-30 00:34:24 | `ops/reports/archive-execution-manifest.json` | 18,411 |
| 2026-04-30 00:34:52 | `ops/reports/artifact-freshness-report.json` | 224,422 |
| 2026-04-30 00:34:22 | `ops/reports/generated-artifact-index.json` | 31,636 |
| 2026-04-30 00:34:18 | `ops/reports/manual-mutate-defect-registry.json` | 4,241 |
| 2026-04-29 23:57:08 | `ops/reports/raw-registry-cross-environment-matrix.json` | 22,403 |
| 2026-04-29 23:57:04 | `ops/reports/raw-registry-preflight-report.json` | 5,208 |
| 2026-04-29 23:57:08 | `ops/reports/raw-registry-preflight-reproducibility.json` | 19,100 |
| 2026-04-30 00:34:52 | `ops/reports/release-closeout-summary.json` | 12,876 |
| 2026-04-29 22:39:34 | `ops/reports/task-improvement-observations/task-20260429-release-closeout-summary/improvement-observations.json` | 5,226 |
| 2026-04-30 00:33:58 | `ops/reports/test-execution-summary.json` | 11,294 |
| 2026-04-29 22:50:50 | `ops/schemas/archive-execution-manifest.schema.json` | 5,098 |
| 2026-04-29 22:55:24 | `ops/schemas/artifact-freshness-report.schema.json` | 17,887 |
| 2026-04-29 21:54:16 | `ops/schemas/learning-readiness-signoff.schema.json` | 3,351 |
| 2026-04-29 23:41:38 | `ops/schemas/raw-registry-cross-environment-matrix.schema.json` | 7,837 |
| 2026-04-30 00:15:10 | `ops/schemas/release-closeout-summary.schema.json` | 12,136 |
| 2026-04-29 22:48:36 | `ops/schemas/test-deselection-policy.schema.json` | 1,321 |
| 2026-04-30 00:16:26 | `ops/schemas/test-execution-summary.schema.json` | 8,190 |
| 2026-04-29 22:51:40 | `ops/scripts/archive_execution_manifest.py` | 8,858 |
| 2026-04-29 22:55:00 | `ops/scripts/artifact_freshness_runtime.py` | 46,673 |
| 2026-04-29 23:55:56 | `ops/scripts/raw_registry_cross_environment_matrix.py` | 18,108 |
| 2026-04-30 00:15:00 | `ops/scripts/release_closeout_summary.py` | 33,240 |
| 2026-04-29 23:39:04 | `ops/scripts/schema_constants_runtime.py` | 7,107 |
| 2026-04-30 00:27:26 | `ops/scripts/test_execution_summary.py` | 20,277 |
| 2026-04-29 23:41:46 | `pyproject.toml` | 4,725 |
| 2026-04-30 00:17:58 | `README.md` | 50,405 |
| 2026-04-30 00:33:58 | `runs/run-YYYYMMDD-mechanism-slug/runtime-events.jsonl` | 29,293 |
| 2026-04-30 00:33:58 | `runs/run-YYYYMMDD-slug/runtime-events.jsonl` | 28,936 |
| 2026-04-29 23:42:24 | `tests/minimal_vault_runtime.py` | 18,040 |
| 2026-04-29 22:57:28 | `tests/test_archive_execution_manifest.py` | 3,868 |
| 2026-04-29 22:55:40 | `tests/test_artifact_freshness_runtime.py` | 30,063 |
| 2026-04-29 23:43:42 | `tests/test_ci_workflow_static.py` | 3,882 |
| 2026-04-30 00:17:18 | `tests/test_cyclonedx_sbom.py` | 8,094 |
| 2026-04-30 00:16:48 | `tests/test_generated_report_contracts.py` | 57,264 |
| 2026-04-30 00:15:56 | `tests/test_makefile_static_gates.py` | 32,391 |
| 2026-04-29 23:45:46 | `tests/test_raw_registry_cross_environment_matrix.py` | 5,032 |
| 2026-04-30 00:15:40 | `tests/test_release_closeout_summary.py` | 22,193 |
| 2026-04-30 00:16:38 | `tests/test_test_execution_summary.py` | 15,233 |
| 2026-04-29 23:42:20 | `tests/test_writer_output_paths.py` | 20,639 |

---

## Appendix B — schema 없는 JSON 12건

| path |
|---|
| `.obsidian/app.json` |
| `.obsidian/appearance.json` |
| `.obsidian/core-plugins.json` |
| `.obsidian/graph.json` |
| `.obsidian/workspace.json` |
| `.vscode/settings.json` |
| `ops/manifest.json` |
| `ops/raw-registry.json` |
| `tests/fixtures/report_schema_samples.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/concept-continuity-integration-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/registration/source-english-summary-reregistration-2026-04-22.json` |
| `ops/schemas/wiki-maintainer-policy.schema.json` |

---

## Appendix C — 신규 리뷰 1 heading inventory

| line | heading |
|---:|---|
| 1 | # LLM Wiki vNext 통합 리뷰 보고서 (Integrated Review Report) |
| 16 | ## 1. 핵심 결론 (Executive Summary) |
| 35 | ## 2. 검토 대상 및 방법 |
| 37 | ### 2.1 검토 대상 |
| 51 | ### 2.2 세 리뷰의 공통 검증 방법 |
| 62 | ### 2.3 각 리뷰의 고유한 검증 기여 |
| 72 | ## 3. 기준 리뷰 이후 반영된 작업분 |
| 74 | ### 3.1 Release closeout orchestration 고도화 |
| 84 | ### 3.2 Source-tree coherence와 accepted risk metadata 반영 |
| 92 | ### 3.3 Learning readiness signoff plumbing 추가 |
| 98 | ### 3.4 Test execution summary의 구조화 심화 |
| 109 | ### 3.5 Archive execution manifest 도입 |
| 115 | ### 3.6 Artifact freshness debt queue화 |
| 126 | ### 3.7 Raw registry cross-environment matrix 구현 |
| 137 | ### 3.8 CycloneDX offline validation 정책이 코드 수준으로 닫힘 |
| 145 | ### 3.9 기준 리뷰에 없던 추가 강화 작업 |
| 154 | ## 4. 지정 리뷰 권고별 현재 상태 매트릭스 |
| 173 | ## 5. 현재 Release Closeout 상세 |
| 175 | ### 5.1 Component 상태 |
| 186 | ### 5.2 Blocker |
| 206 | ### 5.3 Accepted risks |
| 218 | ## 6. Artifact / Archive / Raw Registry 상태 |
| 220 | ### 6.1 Artifact freshness summary |
| 244 | ### 6.2 Generated artifact index와 archive manifest |
| 259 | ### 6.3 Raw registry reproducibility / cross-environment matrix |
| 275 | ## 7. 직접 검증 결과 (세 리뷰 통합) |
| 277 | ### 7.1 Schema validation |
| 291 | ### 7.2 Static / typecheck |
| 298 | ### 7.3 Changed Python 문법 검증 |
| 302 | ### 7.4 Targeted tests |
| 318 | ### 7.5 Runtime command checks |
| 331 | ## 8. 새로 식별된 개선 방안 (세 리뷰 공통/고유 제안 통합) |
| 333 | ### 8.1 Raw registry replay drift (신규 발견) |
| 349 | ### 8.2 Evidence chain freshness skew guard |
| 353 | ### 8.3 Learning signoff file generator 또는 template |
| 357 | ### 8.4 "추출 ZIP replay" 전용 evidence profile 추가 |
| 366 | ### 8.5 Archive execution을 `dry_run`, `apply`, `rollback` 3모드로 완성 |
| 376 | ### 8.6 Cross-env matrix report를 CI artifact digest collector와 연결 |
| 386 | ### 8.7 Mtime currentness를 ZIP-aware로 전환 |
| 399 | ### 8.8 Closeout profile을 release type별로 고정 |
| 411 | ### 8.9 Auto-improve readiness freshness를 closeout에서 더 엄격히 보기 |
| 415 | ### 8.10 No-schema allowlist |
| 421 | ## 9. 남아 있는 작업분 |
| 437 | ## 10. 권장 실행 순서 |
| 439 | ### Tranche 1 — release-ready 직접 수렴 |
| 447 | ### Tranche 2 — evidence cohort consistency |
| 455 | ### Tranche 3 — artifact/archive debt cleanup |
| 462 | ### Tranche 4 — reproducibility and public package |
| 472 | ## 11. 종합 판정 |
| 492 | ## Appendix A. 지정 리뷰 이후 변경된 46개 파일 전체 목록 |
| 545 | ## Appendix B. 현재 closeout blocker 원문 요약 |
| 560 | ## Appendix C. 증거 우선 원칙 |
| 571 | ## Appendix D. 세 리뷰의 고유한 기여 요약 |

---

## Appendix D — 신규 리뷰 2 heading inventory

| line | heading |
|---:|---|
| 1 | # LLM Wiki vNext 통합 후속 검토 보고서 |
| 11 | ## 통합 대상 리뷰 일람 |
| 23 | ## 목차 |
| 46 | ## 1. 핵심 결론 요약 |
| 52 | ### 1.1 세 리뷰의 최종 판정 비교 |
| 62 | ## 2. ZIP 무결성 및 인벤토리 |
| 64 | ### 2.1 현재 검토 대상 ZIP 공통 지표 |
| 82 | ### 2.2 확장자별 파일 분포 (리뷰 C 기준) |
| 100 | ### 2.3 Top-level 디렉토리 파일 분포 |
| 115 | ### 2.4 기준 리뷰 파일 지표 |
| 127 | ## 3. 기준 리뷰 이후 변경 파일 46건 전체 분석 |
| 131 | ### 3.1 변경 영역별 분류 |
| 146 | ### 3.2 타임스탬프 흐름으로 본 작업 순서 |
| 152 | ## 4. 현재 Release Closeout 상태 — 상세 수치 기록 |
| 154 | ### 4.1 `ops/reports/release-closeout-summary.json` 핵심 지표 |
| 170 | ### 4.2 Component별 상태 (세 리뷰 공통 확인) |
| 185 | ### 4.3 Hard Blocker 상세 |
| 195 | ### 4.4 Accepted Risks 상세 (3건) |
| 207 | ## 5. 기준 리뷰 권고 대비 현재 이행 상태 매트릭스 |
| 228 | ## 6. 완료 또는 상당 부분 완료된 작업분 — 영역별 상세 |
| 230 | ### 6.1 Release Evidence Closeout Orchestration 고도화 |
| 258 | ### 6.2 Source-Tree Coherence와 Accepted Risk Metadata 반영 |
| 271 | ### 6.3 Learning Readiness Signoff Plumbing 추가 |
| 284 | ### 6.4 Test Execution Summary 구조화 심화 |
| 301 | ### 6.5 Archive Execution Manifest 도입 |
| 314 | ### 6.6 Raw Registry Cross-Environment Matrix 구현 |
| 326 | ### 6.7 Artifact Freshness Debt Queue 표면화 |
| 338 | ### 6.8 CycloneDX Offline Validation 정책 코드 수준으로 완성 |
| 351 | ### 6.9 기준 리뷰에 없던 추가 강화 작업 |
| 364 | ## 7. 여전히 남아 있는 작업분 — 항목별 상세 |
| 366 | ### 7.1 [P0] Learning Readiness Blocker — 직접적 release 차단 항목 |
| 413 | ### 7.2 [P0] 최신 변경 이후 Full Release Evidence Chain 재실행 |
| 427 | ### 7.3 [P0] Source-Tree Coherence 정책 확정 |
| 438 | ### 7.4 [P1] Artifact Freshness Debt 잔존 |
| 456 | ### 7.5 [P1] Archive Execution Manifest — 계획만 있고 적용 없음 |
| 470 | ### 7.6 [P1] Raw Registry Cross-Environment Evidence — CI 선언 증거 중심 |
| 474 | ### 7.7 [P1] Clean ZIP Bootstrap 재현성 |
| 478 | ### 7.8 [P2] Supply-Chain/SBOM Profile 정책화 |
| 484 | ## 8. 리뷰별 고유 발견 및 기여 |
| 488 | ### 8.1 리뷰 A의 고유 발견: Raw Registry Replay Drift |
| 515 | ### 8.2 리뷰 B의 고유 기여: 가장 광범위한 직접 실행 검증 |
| 562 | ### 8.3 리뷰 C의 고유 기여: 체계적 섹션-항목 대조 방법론 |
| 597 | ## 9. 세 리뷰에서 공통으로 제안된 개선 방안 |
| 601 | ### 9.1 Learning Readiness 해소 경로 즉시 결정 |
| 605 | ### 9.2 최신 변경 이후 Full Release Evidence Chain 재실행 |
| 609 | ### 9.3 Source-Tree Coherence 정책을 명시적으로 문서화 |
| 613 | ### 9.4 Archive Manifest를 Dry-Run에서 실제 적용으로 승격 |
| 617 | ### 9.5 Raw Registry Cross-Environment Per-Platform Artifact 보존 |
| 623 | ## 10. 리뷰 고유 신규 개선 제안 — 통합 목록 |
| 625 | ### 10.1 리뷰 A 고유 제안 |
| 653 | ### 10.2 리뷰 B 고유 제안 |
| 727 | ### 10.3 리뷰 C 고유 제안 |
| 751 | ## 11. 직접 검증 결과 비교 |
| 770 | ## 12. 권장 실행 순서 — 통합 Tranche 계획 |
| 774 | ### Tranche 1 — Release-Ready 직접 수렴 (P0) |
| 786 | ### Tranche 2 — Evidence Cohort Consistency (P0/P1) |
| 796 | ### Tranche 3 — Artifact/Archive Debt Cleanup (P1) |
| 806 | ### Tranche 4 — Reproducibility, Cross-Platform, Public Package (P1/P2) |
| 819 | ## 13. 종합 판정 |
| 823 | ### 13.1 작업분 인정 여부 |
| 835 | ### 13.2 Release-Ready 여부 |
| 849 | ### 13.3 한 문장 최종 총평 |
| 855 | ## Appendix A — 변경 파일 46건 전체 목록 |
| 910 | ## Appendix B — Release Closeout Component 상세 |
| 923 | ## Appendix C — Learning Readiness Signal 전체 목록 |
| 947 | ## Appendix D — Artifact Freshness Debt Queue 상세 |
| 965 | ## Appendix E — Raw Registry Cross-Environment Matrix 행 목록 |
