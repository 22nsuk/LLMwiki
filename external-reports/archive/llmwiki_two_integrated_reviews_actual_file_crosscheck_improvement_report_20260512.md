# LLMwiki 두 통합 리뷰·기존 리뷰·실제 압축본 교차검토 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-12 KST |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_two_integrated_reviews_actual_file_crosscheck_improvement_report_20260512.md` |
| 신규 검토 대상 리뷰 1 | `llmwiki_integrated_review_report_20260512.md` |
| 신규 검토 대상 리뷰 2 | `llmwiki_integrated_crosscheck_report_20260512.md` |
| 기존 리뷰 | `llmwiki_current_zip_vs_20260511_report_improvement_plan_20260512.md` |
| 실제 압축본 | `/mnt/data/LLMwiki(33).zip` |
| 실제 ZIP SHA-256 | `28eec5a7888eb3fe04786ef87c3211cf47a2059467084d973dbb1f0094e87c7d` |
| 최종 판정 | **두 신규 리뷰는 기존 리뷰와 실제 압축본의 핵심 상태를 대체로 정확하게 통합하고 있다. 다만 두 번째 교차검토 리뷰가 RO/RW 환경 구분, P0 세분화, Makefile basis default, auto-improve live guard를 더 보수적이고 실행 가능한 형태로 정리한다. 실제 파일 재검증 결과 현재 체크포인트는 과거 2026-05-11 보고서의 일부 P0를 해소했지만, artifact freshness/schema drift, 1,107→1,112 full-suite evidence drift, full pytest 4건 실패, 다중 fingerprint cohort, external-report lifecycle, auto-improve promotion gate 문제는 여전히 P0/P1로 처리해야 한다.** |

---

## 1. 검토 목적과 범위

본 보고서는 사용자가 추가로 제공한 두 개의 통합 리뷰를 누락 없이 검토하고, 다음 세 축과 다시 대조하여 현재 체크포인트의 권위 있는 개선 방향을 정리한다.

1. **신규 리뷰 1**: `llmwiki_integrated_review_report_20260512.md`
2. **신규 리뷰 2**: `llmwiki_integrated_crosscheck_report_20260512.md`
3. **기존 리뷰 및 실제 파일**: 직전 산출물 `llmwiki_current_zip_vs_20260511_report_improvement_plan_20260512.md`와 원본 저장소 스냅샷 ZIP `LLMwiki(33).zip`

압축본은 사용자 전제대로 저장소 원본 snapshot으로 취급했다. 따라서 원본 ZIP 안에 `tmp/`, `runs/`, `external-reports/`가 존재하는 것 자체는 release packaging 결함으로 보지 않았다. 대신 저장소가 생성하는 release distribution ZIP 경로인 `make release-distribution-zip`이 `tmp/`와 `external-reports/`를 배제하고 정상 산출물을 만드는지를 검증했다.

---

## 2. 요약 결론

### 2.1 두 신규 리뷰의 전체 신뢰도

두 신규 리뷰는 모두 다음 핵심 판단에서 기존 리뷰 및 실제 파일과 일치한다.

| 공통 판단 | 실제 파일 재검증 결과 | 판정 |
| --- | --- | --- |
| 현재 ZIP은 2026-05-11 기준 보고서의 ZIP과 다른 스냅샷이다. | SHA `28eec5a7...`, 2,082 entries, 1,964 files, 118 dirs | 일치 |
| `make static`은 통과한다. | ruff pass, mypy “no issues found in 207 source files” | 일치 |
| `make test-artifact-finalization`은 clean/RW 환경에서 통과한다. | 6 passed | 일치 |
| `make artifact-freshness-check`는 실패한다. | exit code 2, `status=fail`, schema invalid 2건 | 일치 |
| release distribution ZIP 생성 경로는 정상이다. | 1,497 files, smoke pass, `tmp/`·`external-reports/` 미포함 | 일치 |
| full collect-only는 1,112 tests다. | 1,112 collected | 일치 |
| full pytest는 4건 실패한다. | exit code 1, `FAILED` 4건 확인 | 일치 |
| 주요 release authority artifact는 `76190249...`와 `e5f8a33d...` cohort가 공존한다. | 실제 JSON artifact에서 확인 | 일치 |

### 2.2 더 권위 있게 채택할 리뷰

두 리뷰 모두 유효하지만, **실행 계획의 기준으로는 신규 리뷰 2(`llmwiki_integrated_crosscheck_report_20260512.md`)를 더 우선 채택**하는 것이 적절하다. 이유는 다음과 같다.

- RO(read-only) 추출 환경과 writable clone 환경의 차이를 명확히 분리했다.
- `artifact-freshness-check`를 실제로 실행한 리뷰와 실행하지 않은 리뷰를 더 정확히 구분했다.
- P0를 `artifact freshness`, full-suite evidence, full pytest, fingerprint lineage, external report lifecycle, closeout live regeneration, auto-improve live guard, Makefile basis default로 더 세밀하게 나눴다.
- 기존 리뷰에서 P1 guard로 둔 auto-improve promotion 문제를 release gate 관점에서 P0 guard로 격상해 더 안전하게 다룬다.
- Makefile의 낡은 external report basis default(`0a547950...`, entry count `1819`)를 별도 위험으로 분리했다.

신규 리뷰 1은 큰 틀에서 정확하지만, 일부 표현에서 “A/B/C 공통” 범위를 다소 넓게 기술하거나, 실행 환경 차이를 신규 리뷰 2만큼 명확히 분리하지 않는다. 이는 결론을 뒤집는 오류는 아니지만, 후속 작업 지시서로는 신규 리뷰 2의 구조가 더 안전하다.

---

## 3. 실제 ZIP inventory 재검증

### 3.1 ZIP identity

| 항목 | 실제 값 |
| --- | --- |
| 파일 | `/mnt/data/LLMwiki(33).zip` |
| SHA-256 | `28eec5a7888eb3fe04786ef87c3211cf47a2059467084d973dbb1f0094e87c7d` |
| 크기 | 192,798,186 bytes |
| 전체 entries | 2,082 |
| 파일 entries | 1,964 |
| 디렉터리 entries | 118 |
| uncompressed bytes | 251,584,627 |
| unsafe path | 0 |

두 신규 리뷰가 전제한 현재 ZIP identity는 실제 파일과 일치한다. 단, 신규 리뷰 1은 일부 표기에서 `/mnt/data/LLMwiki.zip`이라고 썼으나, 실제 업로드 파일명은 `/mnt/data/LLMwiki(33).zip`이다. SHA가 같으므로 내용상 결함은 아니며, 보고서 표기 정합성 문제로만 보면 된다.

### 3.2 prefix별 파일 수

| prefix | 파일 수 |
| --- | ---: |
| `ops/` | 482 |
| `raw/` | 446 |
| `wiki/` | 417 |
| `runs/` | 263 |
| `tests/` | 173 |
| `system/` | 71 |
| `external-reports/` | 64 |
| root files | 18 |
| `.codex/` | 10 |
| `tools/` | 6 |
| `.obsidian/` | 5 |
| `tmp/` | 5 |
| `.github/` | 2 |
| `.ouroboros/` | 1 |
| `.vscode/` | 1 |

### 3.3 확장자별 파일 수

| 확장자 | 파일 수 |
| --- | ---: |
| `.md` | 982 |
| `.json` | 440 |
| `.py` | 381 |
| `.pdf` | 62 |
| `.txt` | 43 |
| `.yaml` | 18 |
| `.jsonl` | 16 |
| `.toml` | 11 |
| `(none)` | 5 |
| `.yml` | 2 |
| `.docx` | 2 |
| `.ini` | 1 |
| `.lock` | 1 |

`tmp/` 파일이 5개로 줄고 `.json` 수가 440개로 줄어든 상태는 두 신규 리뷰와 기존 리뷰의 관측과 일치한다. 이는 과거 기준 보고서 이후 temporary artifact cleanup이 일부 진행되었음을 보여준다.

---

## 4. 실제 external-reports 상태

현재 원본 ZIP의 `external-reports/` root active 파일은 다음 2개다.

1. `external-reports/llmwiki_two_20260511_reviews_crosscheck_improvement_report_20260511.md`
2. `external-reports/report-reference-manifest.json`

archive 파일 수는 62개다. `ops/reports/generated-artifact-index.json`은 다음과 같이 판단한다.

| 항목 | 실제 값 |
| --- | ---: |
| `status` | `attention` |
| `external_reports_root_file_count` | 2 |
| `external_reports_archive_file_count` | 62 |
| `canonical_report_count` | 70 |
| `archive_candidate_count` | 1 |
| archive candidate | `external-reports/llmwiki_two_20260511_reviews_crosscheck_improvement_report_20260511.md` |
| archive reason | `All structured action themes from this external report are implemented in canonical evidence.` |

따라서 두 신규 리뷰가 지적한 “2026-05-11 보고서 자체가 archive candidate가 되었다”는 판단은 실제 파일과 일치한다. 후속 작업은 단순히 보고서를 추가하는 것이 아니라 active report set과 archive candidate rule을 정리하는 방향이어야 한다.

---

## 5. 주요 checked-in canonical artifact 상태

| artifact | checked-in 상태 | fingerprint | 실제 판정 |
| --- | --- | --- | --- |
| `ops/reports/release-closeout-summary.json` | `status=pass`, `clean_release_ready=True`, `machine_release_allowed=True`, `release_readiness_state=clean_pass` | `761902495e...` | checked-in만 보면 clean이나 schema 요구 필드 누락 및 live cohort 불일치 존재 |
| `ops/reports/release-closeout-batch-manifest.json` | `status=pass`, `sealed_release_status=sealed_clean_pass`, distribution package `materialized` | `761902495e...` | 과거 P0인 distribution binding 미완료는 해소 |
| `ops/reports/release-evidence-cohort.json` | `status=pass`, `strict_same_fingerprint=True`, `component_fingerprint_count=1` | `761902495e...` | strict cohort 자체는 해소됐지만 schema 요구 필드 누락 |
| `ops/reports/release-clean-blocker-ledger.json` | `status=attention`, `blocker_count=0`, `clean_lane_status=pass`, `machine_release_status=allowed`, `auto_improve_lane_status=blocked` | `761902495e...` | release clean 자체 차단이 아니라 auto-improve/learning guard 계열 attention |
| `ops/reports/external-report-action-matrix.json` | `status=pass`, `implemented_count=10`, `requires_release_run_verification_count=0` | `e5f8a33d...` | 과거 action matrix 미완료는 해소 |
| `ops/reports/generated-artifact-index.json` | `status=attention`, `archive_candidate_count=1` | `e5f8a33d...` | external report lifecycle 미정리 |
| `ops/reports/auto-improve-readiness.json` | `can_execute_trial=True`, `can_promote_result=True`, `promotion_blockers=[]` | `e5f8a33d...` | live freshness 실패와 충돌하므로 promotion gate 보강 필요 |
| `ops/reports/test-execution-summary-full.json` | `status=pass`, `counts.passed=1107`, `collect_nodeids=1107` | `761902495e...` | live collect-only 1,112와 불일치 |
| `ops/reports/artifact-freshness-report.json` | `status=pass` | `761902495e...` | checked-in은 pass이나 live check는 fail |
| `ops/reports/release-smoke-report.json` | `status=pass` | `e5f8a33d...` | e5f8 cohort에 속함 |

핵심은 checked-in artifact 내부에서 이미 `76190249...` 계열과 `e5f8a33d...` 계열이 공존한다는 점이다. 실제 live source tree fingerprint는 `e5f8a33d936bb742cc9679eae1fcca3eca92088782a83b2ed4cd3a37fb35b079`로 재계산되었다. 따라서 현재 상태는 “과거 P0 일부 해소”와 “현재 source tree 기준 재봉인 미완료”가 동시에 존재하는 상태다.

---

## 6. 직접 검증 결과

| 검증 | 명령 | 결과 | 의미 |
| --- | --- | --- | --- |
| 의존성 설치 | `uv venv .venv && uv pip install -e '.[dev]'` | 성공 | 테스트 실행 가능 환경 구성 |
| static | `make PYTHON=.venv/bin/python static` | exit 0 | ruff pass, mypy pass |
| artifact finalization | `make PYTHON=.venv/bin/python test-artifact-finalization` | exit 0, 6 passed | clean/RW 기준 통과 |
| artifact freshness check | `make PYTHON=.venv/bin/python artifact-freshness-check` | exit 2 | schema drift 및 operational attention 확인 |
| release distribution ZIP | `make PYTHON=.venv/bin/python release-distribution-zip` | exit 0 | release ZIP 생성 정상 |
| collect-only | `.venv/bin/python -m pytest -o addopts= --collect-only -q --capture=no` | exit 0, 1,112 collected | checked-in full summary 1,107과 불일치 |
| selected 4 failing tests | 4개 nodeid 직접 실행 | exit 1, 4 failed | 리뷰 C 및 두 신규 통합 리뷰의 실패 목록 재현 |
| full pytest | `.venv/bin/python -m pytest -q` | exit 1, `FAILED` 4건 | full-suite 실패 4건 재확인 |

### 6.1 artifact-freshness-check 상세

`tmp/artifact-freshness-report-check.json` 기준 주요 값은 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| `status` | `fail` |
| `artifact_count` | 291 |
| `json_artifact_count` | 291 |
| `scanned_text_artifact_count` | 351 |
| `stale_artifact_count` | 0 |
| `schema_invalid_artifact_count` | 2 |
| `stable_contract_debt_artifact_count` | 2 |
| `stable_contract_debt_issue_count` | 2 |
| `operational_attention_artifact_count` | 1 |
| `operational_attention_issue_count` | 2 |
| `recommended_next_action` | `regenerate_schema_invalid_artifacts` |

Top debt files는 다음과 같다.

| 파일 | issue | 권장 조치 |
| --- | --- | --- |
| `ops/reports/release-closeout-summary.json` | `schema_validation_failed` | `regenerate_artifact_from_current_schema` |
| `ops/reports/release-evidence-cohort.json` | `schema_validation_failed` | `regenerate_artifact_from_current_schema` |
| `ops/reports/test-execution-summary.json` | `test_target_fingerprint_mismatch:tests/test_generated_report_contracts.py`, `test_target_fingerprint_mismatch:tests/test_makefile_static_gates.py` | `regenerate_test_execution_summary` |

이 결과는 신규 리뷰 1, 신규 리뷰 2, 기존 리뷰의 핵심 P0 판정과 일치한다.

### 6.2 release distribution ZIP 검증

| 항목 | 실제 값 |
| --- | --- |
| 생성 파일 | `build/release/LLMwiki-source.zip` |
| SHA-256 | `1df2ad601bfa68925f5dc876952881990e103df2430ceb77be952d41f513f353` |
| 크기 | 190,232,097 bytes |
| entries/files | 1,497 |
| directory entries | 0 |
| root prefix | `LLMwiki` |
| `LLMwiki/tmp/` 포함 | false |
| `LLMwiki/external-reports/` 포함 | false |
| smoke status | pass |

따라서 압축 관련 문제는 원본 repository snapshot ZIP과 release distribution ZIP의 성격을 혼동하지 않는 한, 저장소 생성 경로 자체는 정상이다. 다만 checked-in batch manifest의 distribution ZIP SHA는 `1953daae...`이고 이번 재생성 SHA는 `1df2ad60...`이므로, release authority에서 byte-level ZIP identity를 요구할지 content manifest equality를 요구할지 정책을 분리해야 한다.

### 6.3 full pytest 실패 4건 재확인

full pytest는 exit code 1로 종료되었고, 로그에서 다음 4개 `FAILED` 항목이 확인되었다.

| 실패 테스트 | 실제 실패 원인 | 개선 방향 |
| --- | --- | --- |
| `tests/test_release_closeout_batch_manifest.py::ReleaseCloseoutBatchManifestTests::test_makefile_closeout_recipe_uses_fixed_point_finalizer` | Makefile의 `release-evidence-closeout` 마지막 recipe가 기대값 `$(MAKE) release-closeout-finality-verify`가 아니라 `$(MAKE) external-report-action-matrix` | closeout recipe의 권위 순서를 재정의하고 test 또는 Makefile을 정렬 |
| `tests/test_report_schema_sample_regeneration.py::ReportSchemaSampleRegenerationTests::test_direct_script_check_passes_for_current_fixture` | `tests/fixtures/report_schema_samples.json`이 stale. OpenVEX sample fingerprint가 fixture `314f1666...`에서 generated `929ec12c...`로 변경 | `tools/regenerate_report_schema_samples.py` 재생성 후 diff 검토 |
| `tests/test_report_schema_sample_regeneration.py::ReportSchemaSampleRegenerationTests::test_generated_openvex_sample_matches_frozen_fixture` | generated OpenVEX sample과 frozen fixture 불일치 | sample 재생성 또는 fingerprint input surface 안정화 |
| `tests/test_writer_output_paths.py::WriterOutputPathsTest::test_script_output_surface_registry_matches_current_ast_inventory` | `ops/script-output-surfaces.json`의 source_tree_fingerprint가 `76190249...`이나 live expected는 `e5f8a33d...`; `ops_scripts` input fingerprint도 `3e1f740...` → `12d7649...`로 변경 | `make script-output-surfaces` 재생성 및 writer classification diff 검토 |

이 네 건은 product runtime 로직 붕괴라기보다 generated fixture, Makefile contract, script output registry가 현재 source tree와 어긋난 currentness/contract failure다. 하지만 release gate 관점에서는 full-suite 실패이므로 P0로 유지해야 한다.

---

## 7. 두 신규 리뷰와 기존 리뷰의 대조

### 7.1 완전 일치 또는 실질 일치 항목

| 항목 | 기존 리뷰 | 신규 리뷰 1 | 신규 리뷰 2 | 실제 파일 판정 |
| --- | --- | --- | --- | --- |
| 현재 ZIP SHA/entries | `28eec5a7...`, 2,082 entries | 동일 | 동일 | 일치 |
| 기준 보고서 ZIP identity 폐기 | 폐기 | 폐기 | 폐기 | 일치 |
| batch manifest distribution binding | 해소, 회귀가드로 강등 | 해소 | 해소 | 실제 checked-in materialized |
| external action matrix | 10/10 implemented | 10/10 | 10/10 | 실제 pass |
| artifact-freshness-check | fail | fail | fail | 실제 exit 2 |
| full-suite count drift | 1,107 vs 1,112 | 동일 | 동일 | 실제 collect 1,112 |
| full pytest 4건 실패 | 기록 | 기록 | 기록 | 실제 full pytest exit 1, 4 FAILED |
| release ZIP 생성 | pass, 1,497 files | pass | pass | 실제 pass |
| external report lifecycle | archive candidate 정리 필요 | 정리 필요 | 정리 필요 | 실제 archive candidate 1 |

### 7.2 신규 리뷰 1의 보완/수정 포인트

신규 리뷰 1은 대체로 정확하지만 다음 사항은 후속 최종 보고서에서 보정하는 것이 좋다.

| 항목 | 신규 리뷰 1 표현 | 실제 대조 | 보정 제안 |
| --- | --- | --- | --- |
| ZIP 경로 | `/mnt/data/LLMwiki.zip` | 실제 파일명은 `/mnt/data/LLMwiki(33).zip` | SHA 기준으로 동일성을 명시하고 경로 표기 보정 |
| artifact-freshness 실행 주체 | 일부 표에서 A/B/C 공통처럼 표현 | 신규 리뷰 2는 A/C 직접 실패, B는 RO/RW finalization 중심으로 분리 | “실제 재검증에서 fail confirmed”로 통일하고, 리뷰별 실행 범위는 신규 리뷰 2 기준 채택 |
| P0 분해 | P0-1~P0-5 중심 | 실제로 Makefile basis default, RO/RW 환경, closeout live mismatch가 별도 관리 필요 | 신규 리뷰 2의 P0-6~P0-8 구조를 흡수 |
| auto-improve promotion | P0-4로 언급하나 기존 리뷰에서는 P1 guard 성격도 있음 | 실제 live freshness fail 상태에서 `can_promote_result=true` | release promotion gate에 직접 걸리는 P0 guard로 격상 |

### 7.3 신규 리뷰 2의 강점과 채택 지점

신규 리뷰 2는 다음 지점에서 기존 리뷰보다 더 실행 가능하다.

1. **RO/RW 환경 분리**: read-only 추출 실패와 writable clone 정상화를 구분해 “저장소 아키텍처 결함”과 “artifact refresh 누락”을 분리한다.
2. **P0 세분화**: artifact freshness, full-suite evidence, full pytest, fingerprint lineage, lifecycle, closeout live regeneration, promotion guard, Makefile basis default를 각각 독립 수락 기준으로 둔다.
3. **release ZIP identity 분리**: raw snapshot ZIP, checked-in distribution ZIP, 현재 rerun distribution ZIP을 같은 identity field로 섞지 말라고 명확히 지시한다.
4. **Makefile basis default 지적**: 외부 보고서 basis SHA `0a547950...`와 entry count `1819` 하드코딩이 현재 ZIP과 무관하므로, fail-fast 또는 auto-derive 정책이 필요하다고 본다.
5. **full runner 개선**: long-running full pytest의 heartbeat/JUnit/shard/xdist 권위 관계를 P1로 분리한다.

따라서 후속 개선 작업은 신규 리뷰 2를 기본 골격으로 삼고, 기존 리뷰와 신규 리뷰 1의 검증 로그·표현을 보조 근거로 합치는 방식이 가장 안전하다.

---

## 8. 최종 우선순위 개선 계획

### P0-1. `artifact-freshness-check` schema drift 2건 해소

**문제**: live `make artifact-freshness-check`가 exit 2로 실패한다. `release-closeout-summary.json`과 `release-evidence-cohort.json`이 현재 schema가 요구하는 `divergence_diagnostics` 필드를 포함하지 않는다.

**조치**:

1. `release-closeout-summary` producer가 `source_tree_coherence.divergence_diagnostics`를 항상 생성하도록 수정한다.
2. `release-evidence-cohort` producer가 `cohort.divergence_diagnostics`를 항상 생성하도록 수정한다.
3. schema validation `$ref` 경로가 clean extraction과 release builder 환경에서 모두 안정적으로 해석되는지 확인한다.
4. 두 artifact를 수기 편집이 아니라 producer 기반으로 재생성한다.
5. `make PYTHON=.venv/bin/python artifact-freshness-check`가 exit 0이 되는지 확인한다.

**수락 기준**:

- `schema_invalid_artifact_count=0`
- `stable_contract_debt_artifact_count=0`
- `operational_attention_artifact_count=0` 또는 명시적으로 accepted/advisory 분류
- `recommended_next_action=none`

### P0-2. 단일 live fingerprint lineage로 canonical artifact 재봉인

**문제**: checked-in artifact가 `76190249...`와 `e5f8a33d...` 계열로 나뉘어 있다. live source tree fingerprint는 `e5f8a33d936bb742cc9679eae1fcca3eca92088782a83b2ed4cd3a37fb35b079`다.

**조치**:

1. release builder 환경을 고정한다.
2. source tree를 더 변경하지 않은 상태에서 generated artifact refresh를 일괄 실행한다.
3. `release-closeout-summary`, `release-evidence-cohort`, `artifact-freshness-report`, `test-execution-summary`, `test-execution-summary-full`, `script-output-surfaces`, `generated-artifact-index`, `release-smoke-report`, `external-report-action-matrix`, `auto-improve-readiness`의 fingerprint cohort를 정렬한다.

**수락 기준**:

- 주요 release authority artifact가 단일 live fingerprint 계열로 수렴한다.
- checked-in pass와 live regeneration pass가 같은 의미를 갖는다.
- checked-in `clean_pass`가 live `conditional_pass`로 뒤집히지 않는다.

### P0-3. full-suite evidence를 1,112 node 기준으로 재봉인

**문제**: checked-in `test-execution-summary-full.json`은 1,107 passed/collected를 기록하지만, live collect-only는 1,112 tests다.

**조치**:

1. release-builder 환경에서 collect-only 1,112를 다시 확인한다.
2. 1,112 증가가 의도된 테스트 추가인지 확인한다.
3. Makefile expected node count 또는 관련 fixture를 1,112 기준으로 갱신한다.
4. full summary artifact를 재생성한다.
5. artifact freshness의 `test_target_fingerprint_mismatch`를 제거한다.

**수락 기준**:

- `test-execution-summary-full.json`의 collect count가 1,112로 갱신된다.
- full pytest가 0 failure로 통과한다.
- `artifact-freshness-check`가 full summary 관련 operational attention을 더 이상 보고하지 않는다.

### P0-4. full pytest 4건 실패 해소

**문제**: full pytest exit 1, 4 failed.

**조치 순서**:

1. Makefile `release-evidence-closeout` recipe의 마지막 단계가 `release-closeout-finality-verify`인지 `external-report-action-matrix`인지 권위 순서를 결정한다.
2. 결정한 순서에 맞게 Makefile 또는 테스트 기대값을 정렬한다.
3. `tools/regenerate_report_schema_samples.py`를 실행해 OpenVEX sample fixture를 갱신한다.
4. `make script-output-surfaces`로 `ops/script-output-surfaces.json`을 live AST inventory와 맞춘다.
5. 네 실패 테스트를 먼저 재실행한 뒤 full pytest를 재실행한다.

**수락 기준**:

- 위 4개 nodeid가 모두 pass
- full pytest exit 0
- full test execution summary가 이 결과를 canonical artifact로 반영

### P0-5. auto-improve promotion gate를 live currentness와 결합

**문제**: `auto-improve-readiness.json`은 `can_promote_result=true`, `promotion_blockers=[]`를 기록하지만, live `artifact-freshness-check`와 full pytest가 실패한다.

**조치**:

1. `can_execute_trial`과 `can_promote_result`를 분리한다.
2. promotion 허용 조건에 다음 gate를 포함한다.
   - `make artifact-freshness-check` exit 0
   - release closeout live regeneration pass
   - full pytest 또는 release-approved full summary pass
   - external report lifecycle clean
3. live currentness 실패 시 `can_promote_result=false`와 명시적 blocker를 기록한다.

**수락 기준**:

- 현재와 같은 freshness fail 상태에서는 promotion이 false다.
- next_action이 trial 가능성과 promotion 가능성을 혼동하지 않는다.
- auto-improve readiness가 checked-in stale pass만으로 promotion을 허용하지 않는다.

### P0-6. external report lifecycle 정리

**문제**: generated-artifact-index가 2026-05-11 보고서를 archive candidate로 판단한다.

**조치**:

1. 해당 보고서를 active root에 유지할지 archive로 이동할지 결정한다.
2. archive할 경우 `external-report-reference-manifest`, `external-report-action-matrix`, `generated-artifact-index`를 순서대로 재생성한다.
3. 새로 생성되는 본 보고서까지 active report로 편입한다면, 다시 lifecycle 기준을 적용한다.

**수락 기준**:

- `archive_candidate_count=0`
- active report set이 현재 release 판단에 필요한 최신 문서만 포함
- action matrix active/archive counts가 실제 파일 배치와 일치

### P0-7. Makefile external report basis default 제거 또는 자동 산출

**문제**: Makefile 기본값에 현재 ZIP과 무관한 basis가 남아 있다.

| 변수 | 현재 기본값 |
| --- | --- |
| `EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256` | `0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93` |
| `EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT` | `1819` |

**조치**:

1. 외부 보고서 basis 값은 명시 입력이 없으면 fail-fast하도록 변경하거나, 현재 지정된 ZIP에서 자동 계산한다.
2. `report-reference-manifest.json`이 stale basis를 재유입하지 않도록 test를 추가한다.
3. release distribution ZIP과 raw repository snapshot ZIP의 identity field를 분리한다.

**수락 기준**:

- 신규 외부 보고서 생성 시 오래된 `0a547950.../1819` basis가 자동으로 들어가지 않는다.
- basis zip path/name/sha/entry count가 하나의 provenance record로 일관되게 생성된다.

### P1-1. release ZIP byte identity 정책 명확화

현재 release ZIP 생성은 pass이고 manifest comparison도 pass다. 그러나 SHA는 checked-in `1953daae...`, 이번 rerun `1df2ad60...`, 다른 리뷰 환경 `4773c2c5...`처럼 여러 계열이 관측됐다.

**정책 결정**:

- release authority가 content manifest equality를 기준으로 삼는다면 현재 생성 경로는 정상이다.
- byte-for-byte reproducibility를 요구한다면 압축 라이브러리, file ordering, extra field, compression level, timestamp metadata까지 고정하고 별도 deterministic ZIP test를 추가해야 한다.

### P1-2. long-running full test runner 운영성 개선

이번 검증에서도 full pytest는 장시간 실행되며 대량 diff로 로그가 매우 길어졌다. release builder에서는 다음 개선이 필요하다.

- shard별 JUnit/XML 및 요약 JSON 생성
- heartbeat 출력
- 실패 nodeid를 별도 파일로 추출
- pytest-xdist 사용 여부와 authoritative full summary의 관계 문서화
- voluminous diff truncation 정책 도입

### P2-1. stale artifact 조기 감지 fast CI contract 추가

현재 문제는 대부분 stale generated artifact가 누적된 결과다. 다음 PR gate를 추가하는 것이 효과적이다.

- `report-schema-samples-check`
- `script-output-surfaces` currentness check
- `artifact-freshness-check` fast mode
- external report basis sanity check
- auto-improve promotion guard check

---

## 9. 권장 실행 순서

```bash
# 0. 의존성
uv venv .venv
uv pip install -e '.[dev]'

# 1. 현재 상태 재확인
make PYTHON=.venv/bin/python static
make PYTHON=.venv/bin/python artifact-freshness-check || true
.venv/bin/python -m pytest -o addopts= --collect-only -q --capture=no

# 2. schema drift producer 수정 후
make PYTHON=.venv/bin/python release-closeout-summary
make PYTHON=.venv/bin/python release-evidence-cohort
make PYTHON=.venv/bin/python artifact-freshness-check

# 3. stale fixture/registry 정렬
.venv/bin/python tools/regenerate_report_schema_samples.py
make PYTHON=.venv/bin/python script-output-surfaces
make PYTHON=.venv/bin/python test-execution-summary

# 4. full-suite evidence 재봉인
make PYTHON=.venv/bin/python test-execution-summary-full-refresh
.venv/bin/python -m pytest -q

# 5. external report lifecycle 및 release ZIP 정책 정리
make PYTHON=.venv/bin/python external-report-reference-manifest
make PYTHON=.venv/bin/python external-report-action-matrix
make PYTHON=.venv/bin/python generated-artifact-index
make PYTHON=.venv/bin/python release-distribution-zip

# 6. 최종 gate
make PYTHON=.venv/bin/python test-artifact-finalization
make PYTHON=.venv/bin/python artifact-freshness-check
make PYTHON=.venv/bin/python static
```

---

## 10. 최종 판정 매트릭스

| 영역 | 현재 판정 | 우선순위 | 근거 |
| --- | --- | --- | --- |
| 원본 ZIP identity | 기준 보고서 대비 변경됨 | 정보 갱신 | SHA/entry/file/tmp/archive count 변경 |
| release distribution ZIP 생성 | 정상 | 유지/문서화 | 1,497 files, smoke pass, `tmp/`·`external-reports/` 제외 |
| static quality gate | 통과 | 유지 | ruff/mypy pass |
| artifact finalization | 통과 | 유지 | 6 passed |
| batch manifest distribution binding | 해소 | 회귀가드 | checked-in materialized/sealed clean pass |
| external action matrix | 해소 | 회귀가드 | 10/10 implemented, 0 verification |
| artifact-freshness live check | 실패 | P0 | schema invalid 2건 + operational attention 1건 |
| release closeout/evidence schema | 불일치 | P0 | `divergence_diagnostics` 누락 |
| fingerprint lineage | 다중 cohort | P0 | `76190249...`와 `e5f8a33d...` 공존 |
| full-suite evidence | 미봉인 | P0 | checked-in 1,107 vs live 1,112 |
| full pytest | 실패 | P0 | exit 1, 4 FAILED |
| auto-improve readiness | 위험 | P0 guard | freshness/full pytest fail인데 promotion true |
| external report lifecycle | 미정리 | P0/P1 | archive candidate 1 |
| Makefile basis default | 낡음 | P0/P1 | `0a547950...`, `1819` 기본값 |
| release ZIP byte reproducibility | 정책 모호 | P1 | content pass이나 SHA 다계열 |

---

## 11. 결론

두 신규 리뷰는 기존 리뷰의 핵심 결론을 강화한다. 현재 압축본은 2026-05-11 기준 보고서가 지적했던 distribution binding, action matrix, 일부 clean-lane 관련 P0를 상당 부분 해소했다. 하지만 이 상태를 clean sealed release로 간주할 수는 없다. 실제 파일 기준으로 live freshness gate가 실패하고, full-suite node inventory가 1,107에서 1,112로 벌어져 있으며, full pytest 4건 실패가 재현되고, release authority artifact가 서로 다른 fingerprint cohort에 남아 있기 때문이다.

따라서 다음 작업의 목표는 새 기능 개발이 아니라 **현재 source tree fingerprint `e5f8a33d...` 기준으로 schema, freshness, closeout, evidence cohort, full test summary, script output registry, external report lifecycle, auto-improve promotion guard를 한 번에 재봉인**하는 것이다. 이 작업이 완료되어야 현재 체크포인트는 “과거 보고서 지적사항 일부 해결 상태”에서 “현재 파일 기준으로 검증 완료된 clean release evidence 상태”로 전환될 수 있다.

---

## Appendix A. 검증 로그 요약

### A.1 static

```text
make PYTHON=.venv/bin/python static
ruff: All checks passed!
mypy: Success: no issues found in 207 source files
exit code: 0
```

### A.2 artifact finalization

```text
make PYTHON=.venv/bin/python test-artifact-finalization
6 passed in 1.74s
exit code: 0
```

### A.3 artifact freshness check

```text
make PYTHON=.venv/bin/python artifact-freshness-check
exit code: 2
status: fail
schema_invalid_artifact_count: 2
stable_contract_debt_artifact_count: 2
operational_attention_artifact_count: 1
recommended_next_action: regenerate_schema_invalid_artifacts
```

### A.4 release distribution ZIP

```text
make PYTHON=.venv/bin/python release-distribution-zip
exit code: 0
zip: build/release/LLMwiki-source.zip
sha256: 1df2ad601bfa68925f5dc876952881990e103df2430ceb77be952d41f513f353
entries/files: 1497
has_tmp: false
has_external_reports: false
smoke status: pass
```

### A.5 collect-only

```text
.venv/bin/python -m pytest -o addopts= --collect-only -q --capture=no
1112 tests collected in 3.66s
exit code: 0
```

### A.6 full pytest

```text
.venv/bin/python -m pytest -q
exit code: 1
FAILED entries: 4

FAILED tests/test_release_closeout_batch_manifest.py::ReleaseCloseoutBatchManifestTests::test_makefile_closeout_recipe_uses_fixed_point_finalizer
FAILED tests/test_report_schema_sample_regeneration.py::ReportSchemaSampleRegenerationTests::test_direct_script_check_passes_for_current_fixture
FAILED tests/test_report_schema_sample_regeneration.py::ReportSchemaSampleRegenerationTests::test_generated_openvex_sample_matches_frozen_fixture
FAILED tests/test_writer_output_paths.py::WriterOutputPathsTest::test_script_output_surface_registry_matches_current_ast_inventory
```
