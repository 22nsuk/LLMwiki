# LLM Wiki vNext Two-Review Cross-check Improvement Report

- **작성일:** 2026-04-29 (Asia/Seoul)
- **산출 파일명:** `llm_wiki_vnext_two_review_crosscheck_improvement_report_20260429.md`
- **검토 요청:** 새로 제공된 두 리뷰를 누락 없이 검토한 뒤, 기존 리뷰와 실제 ZIP 파일을 대조하여 개선 보고서 작성
- **검토 대상 ZIP:** `/mnt/data/LLM Wiki vNext.zip`
- **ZIP SHA-256:** `ae41e1ce5d63e859b892678331f160472c4b258cc82008cef76088ba70125f17`
- **최종 판정:** **`not_release_ready_but_materially_progressed_after_baseline_and_prior_review`**
- **핵심 결론:** 두 신규 리뷰와 기존 개선 보고서는 큰 틀에서 서로 일치한다. 실제 파일 대조 결과도 대부분의 주요 주장을 확인한다. 다만 현재 ZIP은 `release-closeout-summary.json` 기준 `release_ready=false`이며, 최종 hard blocker는 여전히 `learning_readiness`다. 추가로, 이번 직접 검증에서는 closeout component 6개가 모두 서로 다른 `source_tree_fingerprint`를 갖는다는 점을 명확히 확인했으므로, 다음 라운드의 핵심 개선은 **learning evidence closeout + release evidence cohort consistency**로 수렴한다.

---

## 1. 검토 범위와 입력 문서

이번 보고서는 아래 네 문서를 모두 전문 기준으로 검토하고, 실제 추출 ZIP의 파일·JSON·스키마와 대조했다.

| 문서 | bytes | SHA-256(축약) | lines | heading 수 |
| --- | --- | --- | --- | --- |
| llm_wiki_vnext_post_crosscheck_improvement_report_20260429.md | 31134 | 2996d55be70bae66… | 469 | 40 |
| llm_wiki_vnext_integrated_review_report_20260429.md | 41874 | 6a4b9cd8da777646… | 778 | 62 |
| 후속점검보고서.md | 35215 | f7846fc4bb6d9459… | 657 | 41 |
| LLM Wiki vNext Dual Integrated Review Cross-check Improvement Report_20260429.md | 25859 | 57faf27efd5187ca… | 562 | 37 |


해석상 주의할 점은 다음과 같다.

1. 새로 제공된 `llm_wiki_vnext_integrated_review_report_20260429.md`와 `후속점검보고서.md`는 서로 다른 관점의 원천 리뷰라기보다, 동일 체크포인트와 동일 기준 리뷰를 대상으로 한 **2차 통합/후속 점검 보고서** 성격이 강하다.
2. 두 신규 리뷰 모두 내부적으로 세 후속 리뷰(`post_review_followup`, `post_crosscheck_improvement`, `post_crosscheck_followup`)를 통합 대상으로 언급한다.
3. 현재 세션에서 실제 파일로 확인 가능한 “기존 리뷰”는 이전 산출물인 `llm_wiki_vnext_post_crosscheck_improvement_report_20260429.md`이며, ZIP 내부 기준 리뷰는 `external-reports/LLM Wiki vNext Dual Integrated Review Cross-check Improvement Report_20260429.md`다.
4. 두 신규 리뷰가 참조하는 upstream 후속 보고서 중 일부는 현재 업로드 파일 또는 ZIP 내부 개별 파일로는 직접 존재하지 않았다. 따라서 해당 세부 내용은 두 신규 리뷰의 전문 서술을 근거로 통합하되, 실제 ZIP 파일로 확인 가능한 항목은 별도 “확인됨/보강됨/미확인”으로 구분했다.

---

## 2. 실제 ZIP 무결성 및 인벤토리 재확인

| 항목 | 값 |
|---|---:|
| SHA-256 | `ae41e1ce5d63e859b892678331f160472c4b258cc82008cef76088ba70125f17` |
| ZIP entries | 1693 |
| files | 1609 |
| dirs | 84 |
| compressed bytes | 190886221 |
| uncompressed bytes | 241027460 |
| `zipfile.testzip()` | `None` |

기준 리뷰 파일의 ZIP timestamp는 `2026-04-29 10:22:00`였고, 그 이후 변경된 파일은 실제 ZIP metadata 기준 **96건**이었다. 두 신규 리뷰와 기존 개선 보고서가 반복해서 언급한 “기준 리뷰 이후 96건 변경”은 이번 재검증에서도 그대로 확인됐다.

| 영역 | 기준 리뷰 ZIP timestamp 이후 변경 파일 수 |
| --- | --- |
| .obsidian | 1 |
| docs/makefile/README | 3 |
| ops root/other | 3 |
| ops/reports | 19 |
| ops/schemas | 18 |
| ops/scripts | 18 |
| runs | 17 |
| tests | 17 |


이 분포는 기준 리뷰 이후 변경이 단순 문서 보강이 아니라 `ops/reports`, `ops/schemas`, `ops/scripts`, `tests`, `runs` 전반에 걸쳐 이루어졌음을 보여 준다.

---

## 3. 두 신규 리뷰에 대한 전문 검토 요약

### 3.1 `llm_wiki_vnext_integrated_review_report_20260429.md`

이 문서는 세 후속 리뷰를 상호 교차 검토한 “통합 리뷰” 형식이다. 특징은 다음과 같다.

- 기준 리뷰 이후 반영된 작업을 세 리뷰의 공통 확인 항목과 고유 확인 항목으로 분리한다.
- ZIP SHA, inventory, 변경 파일 96건, 주요 JSON report 수치가 실제 파일과 일치한다.
- `release-closeout-summary.json`의 6개 component, blocker 1건, accepted risk 2건을 구체적으로 정리한다.
- `raw intake / raw markdown workflow`를 별도 개선 축으로 다룬다.
- `artifact_freshness` stored 값과 live 재생성 값의 drift, closeout과 freshness 간 생성 순서 문제, CycloneDX offline schema 문제처럼 기존 개선 보고서보다 더 세밀한 위험을 식별한다.
- schema validation 158건, in-process artifact 재생성 등 넓은 커버리지의 검증 결과를 인용한다.

이 리뷰는 가장 넓은 개선 항목 목록과 가장 세밀한 우선순위 분해를 제공한다. 실제 파일과 대조했을 때 큰 결론은 확인되며, 특히 raw intake와 closeout source-tree coherence에 대한 지적은 다음 작업 우선순위에 반영할 가치가 높다.

### 3.2 `후속점검보고서.md`

이 문서는 결론과 실행 순서를 더 압축적으로 정리한 후속 점검 보고서다. 특징은 다음과 같다.

- 동일 SHA 체크포인트를 대상으로 세 독립 후속 리뷰를 통합했다고 밝힌다.
- 결론은 `materially progressed after the referenced review, but still not release-ready`로, 통합 리뷰 및 기존 개선 보고서와 일치한다.
- focused unit test 11건, pytest 진입점 UX 직접 확인, canonical schema validation 10종, ZIP 무결성 등 검증 summary를 명확히 정리한다.
- 남은 작업을 `learning_readiness`, artifact freshness, generated index, evidence cohort consistency, raw registry cross-environment matrix, post-index modification guard로 압축한다.
- 개선 방안은 release closeout consistency gate, artifact debt remediation queue, archive execution manifest, learning signoff artifact, release-smoke refresh chain, accepted risk expiry 등 실행 가능한 단위로 정리되어 있다.

이 리뷰는 통합 리뷰보다 raw intake와 CycloneDX 관련 상세는 적지만, 실제 다음 작업을 착수하기 위한 실행 순서가 더 간결하다. 실제 파일 대조 결과와도 핵심 수치·판정이 맞다.

---

## 4. 기존 개선 보고서와 두 신규 리뷰의 정합성

세 문서는 결론상 거의 완전히 일치한다.

| 항목 | 기존 개선 보고서 | 신규 통합 리뷰 | 후속점검보고서 | 실제 파일 대조 |
|---|---|---|---|---|
| 최종 release-ready 여부 | 아님 | 아님 | 아님 | `release_ready=false` 확인 |
| 최종 hard blocker | `learning_readiness` | `learning_readiness` | `learning_readiness` | closeout blocker 1건 확인 |
| release closeout summary | 기준 리뷰 이후 도입 | 도입 확인 | 도입 확인 | script/schema/report/test/Makefile target 존재 |
| test target fingerprint | 도입 확인 | 도입 확인 | 도입 확인 | 18개 fingerprint 확인 |
| raw registry same-env reproducibility | pass/match | pass/match | pass/match | `diff_status=match` 확인 |
| missing schema | 13 → 0 | 13 → 0 | 13 → 0 | `missing_schema_count=0` 확인 |
| stable artifact debt | 47/107 → 32/64 | 47/107 → 32/64 | 47/107 → 32/64 | `32 artifacts / 64 issues` 확인 |
| generated index | attention 유지 | attention 유지 | attention 유지 | `archive_candidate_count=24` 확인 |
| artifact freshness | attention/accepted risk | attention/accepted risk | attention/accepted risk | closeout accepted risk 확인 |
| bare pytest UX | 구현됨 | 구현됨 | 구현됨 | 코드와 테스트 파일 존재 확인 |
| fast/full smoke policy | full canonical, fast precheck | 동일 | 동일 | README/Makefile/script 경로 확인 |
| supply-chain/SBOM | pass이나 closeout 미편입 | 동일 | 동일 | gate reports pass, closeout component 미포함 확인 |

차이는 결론 충돌이 아니라 **상세도와 검증 범위의 차이**다.

- 신규 통합 리뷰는 raw intake workflow, 158개 JSON validation, live 재생성 drift, freshness-closeout 생성 순환 문제, CycloneDX offline validation 문제를 더 많이 다룬다.
- 후속점검보고서는 실행 순서와 “가장 작은 완결 단위”를 더 명확히 압축한다.
- 기존 개선 보고서는 기준 리뷰 이후 실제 작업분과 남은 작업분을 최초로 재분류한 보고서로서, 두 신규 리뷰의 대부분 결론과 맞는다.

---

## 5. 실제 파일로 확인한 주요 현재 상태

### 5.1 Release closeout summary

`ops/reports/release-closeout-summary.json`의 현재 핵심 값은 다음과 같다.

| 항목 | 값 |
|---|---:|
| `status` | `fail` |
| `release_ready` | `False` |
| `component_count` | 6 |
| `ready_component_count` | 5 |
| `blocker_count` | 1 |
| `accepted_risk_count` | 2 |
| `generated_at` | `2026-04-29T11:05:28Z` |

| Closeout component | source_status | ready | blockers | accepted_risks | generated_at |
| --- | --- | --- | --- | --- | --- |
| release_smoke | pass | True | 0 | 0 | 2026-04-28T16:55:02Z |
| test_summary | pass | True | 0 | 0 | 2026-04-29T11:05:07Z |
| raw_registry | pass | True | 0 | 0 | 2026-04-29T07:59:43Z |
| artifact_freshness | attention | True | 0 | 1 | 2026-04-29T11:05:26Z |
| generated_index | attention | True | 0 | 1 | 2026-04-29T11:05:12Z |
| auto_improve_readiness | unknown | False | 1 | 0 | 2026-04-29T08:00:17Z |


확인된 hard blocker는 다음 1건이다.

| source | code | gate_effect | required_evidence |
|---|---|---|---|
| `auto_improve_readiness` | `learning_blocked_by_review_required` | `review_required` | `learning_readiness.likely_to_learn=true` 또는 해당 named blocker의 operator accepted risk 기록 |

accepted risk는 다음 2건이다.

1. `artifact_freshness_attention`
2. `generated_index_archive_advisory`

따라서 두 신규 리뷰의 “5개 component는 ready, 1개 learning blocker로 release-ready 실패” 판정은 실제 파일과 일치한다.

### 5.2 Closeout source-tree coherence 직접 확인

이번 대조에서 별도로 확인한 중요한 사실은 closeout이 읽는 6개 component의 `source_tree_fingerprint`가 전부 다르다는 점이다.

| Component | Path | Status | generated_at | source_tree_fingerprint |
| --- | --- | --- | --- | --- |
| release_smoke | ops/reports/release-smoke-report.json | pass | 2026-04-28T16:55:02Z | 8e47ee468ebb… |
| test_summary | ops/reports/test-execution-summary.json | pass | 2026-04-29T11:05:07Z | bf76a6593355… |
| raw_registry | ops/reports/raw-registry-preflight-report.json | pass | 2026-04-29T07:59:43Z | dc38a5cada27… |
| artifact_freshness | ops/reports/artifact-freshness-report.json | attention | 2026-04-29T11:05:26Z | b02009f77b76… |
| generated_index | ops/reports/generated-artifact-index.json | attention | 2026-04-29T11:05:12Z | 61a3ffcb0809… |
| auto_improve_readiness | ops/reports/auto-improve-readiness.json | current | 2026-04-29T08:00:17Z | 598185ee58fc… |


`release-closeout-summary.json` 자체도 `source_tree_fingerprint=3fed072313f61cb214b7e7c2300d4760b43f70fda3fb2563b6314ce798e28536`를 갖는다. 이 값도 component fingerprint들과 일치하지 않는다. 이것이 곧바로 오류라는 뜻은 아니지만, 두 신규 리뷰가 지적한 **evidence cohort consistency gate 부재**는 실제 파일 관찰로도 강하게 뒷받침된다. 현재 closeout은 component status를 집계하지만, “모든 증거가 동일한 release tree를 증명한다”는 점까지 strict하게 보장하지 않는다.

### 5.3 Learning readiness

`ops/reports/auto-improve-readiness.json`의 learning readiness는 다음 상태다.

| 항목 | 값 |
|---|---:|
| `status` | `learning_uncertain` |
| `gate_effect` | `review_required` |
| `can_run` | True |
| `likely_to_learn` | False |
| `attempts_considered` | 7 |
| `min_attempts_considered` | 10 |
| `session_reports_considered` | 1 |
| `session_calibration_status` | `no_session_context` |
| `telemetry_coverage_ratio` | 0.0 |
| `rework_count` | 5 |
| `hold_moving_average` | 0.2857 |
| `discard_moving_average` | 0.1429 |
| `defect_escape_pair_count` | 3 |

이 수치는 두 신규 리뷰와 기존 개선 보고서가 모두 제시한 결론을 뒷받침한다. 실행 readiness는 충분히 진전됐지만, release credit을 줄 수 있는 learning evidence가 부족하다.

### 5.4 Artifact freshness

현재 `ops/reports/artifact-freshness-report.json`의 summary는 다음과 같다.

| 지표 | 값 |
|---|---:|
| `artifact_count` | 161 |
| `json_artifact_count` | 161 |
| `scanned_text_artifact_count` | 199 |
| `stale_artifact_count` | 38 |
| `mtime_sensitive_artifact_count` | 39 |
| `unknown_currentness_artifact_count` | 32 |
| `missing_schema_count` | 0 |
| `missing_artifact_envelope_count` | 32 |
| `schema_invalid_artifact_count` | 0 |
| `schema_unavailable_artifact_count` | 0 |
| `stable_contract_debt_artifact_count` | 32 |
| `stable_contract_debt_issue_count` | 64 |

`top_debt`는 다음 세 항목으로 수렴한다.

| issue | count | owner surfaces | safe_to_backfill_count | mtime_sensitive_count | recommended_next_action |
| --- | --- | --- | --- | --- | --- |
| generated_at_older_than_file_mtime | 38 | {'ops_reports': 9, 'runs': 29} | 0 | 38 | regenerate_artifact_or_refresh_timestamp |
| missing_artifact_envelope | 32 | {'ops_reports': 3, 'runs': 29} | 0 | 32 | backfill_artifact_envelope |
| unknown_currentness | 32 | {'ops_reports': 3, 'runs': 29} | 0 | 32 | backfill_currentness_metadata |


핵심은 `missing_schema_count=0`이다. 기준 리뷰 당시 13건이던 schema 누락은 실제로 해소됐다. 동시에 남은 debt는 `safe_to_backfill_count=0`인 항목들이므로, 단순 bulk backfill이 아니라 archive/historical run policy와 producer-specific regeneration이 필요하다.

### 5.5 Generated artifact index

현재 `ops/reports/generated-artifact-index.json` summary는 다음과 같다.

| 지표 | 값 |
|---|---:|
| `status` | `attention` |
| `ops_reports_root_file_count` | 24 |
| `task_improvement_observation_count` | 32 |
| `external_reports_root_file_count` | 22 |
| `external_reports_archive_file_count` | 19 |
| `run_directory_count` | 11 |
| `run_archive_directory_count` | 1 |
| `canonical_report_count` | 33 |
| `archive_candidate_count` | 24 |

`why_blocked`는 세 가지다.

1. dated top-level ops report를 archive namespace로 이동해야 한다.
2. 오래된 root-level external report를 `external-reports/archive/`로 이동해야 한다.
3. `promotion-report.history.status=archived`인 run이 top-level `runs/` namespace에 남아 있다.

두 신규 리뷰의 “구조화는 개선됐으나 attention 유지” 판정은 실제 파일과 일치한다.

### 5.6 Test execution summary

현재 `ops/reports/test-execution-summary.json`의 핵심 값은 다음과 같다.

| 항목 | 값 |
|---|---:|
| `suite` | `report-contract-summary` |
| `status` | `pass` |
| `passed` | 177 |
| `failed` | 0 |
| `errors` | 0 |
| `timed_out` | False |
| `termination_reason` | `completed` |
| `duration_ms` | 300563 |
| `test_target_fingerprints` 수 | 18 |
| `pytest_collect_nodeid_digest.nodeid_count` | 177 |
| `pytest_collect_nodeid_digest.sha256` | `fa79bcd248183122038db202ff8a662480db94c4e864d5357efbc9398e920b4c` |

현재 command에는 3개의 `--deselect`가 포함되어 있다. 두 신규 리뷰가 제안한 “deselect 사유의 machine-readable 구조화”는 실제로 아직 남은 개선점이다. 지금은 command string 안에 deselect가 들어 있지만, 각각의 nodeid별 `reason`, `policy_ref`, `release_blocking` 같은 별도 구조 필드는 확인되지 않았다.

### 5.7 Raw registry preflight와 reproducibility

`ops/reports/raw-registry-preflight-report.json`은 다음 상태다.

| 항목 | 값 |
|---|---:|
| `status` | `pass` |
| `entry_count` | 446 |
| `error_count` | 0 |
| `warning_count` | 0 |
| `path_alias_match_count` | 0 |
| `content_hash_fallback_count` | 0 |
| `path_alias_resolution_mode` | `canonical_storage_path_then_manual_exported_environment_aliases_then_unique_content_sha256` |
| `alias_policy_version` | `raw_registry_alias_resolution_v1` |
| `environment_fingerprint.platform_system` | `Linux` |
| `environment_fingerprint.locale` | `C.UTF-8` |

`ops/reports/raw-registry-preflight-reproducibility.json`은 `status=pass`, `diff_status=match`, `comparisons=15`로 확인됐다. 따라서 same-environment stored/live reproducibility는 실제로 닫혔다. 그러나 OS/locale/extraction tool을 달리한 cross-environment matrix는 아직 evidence가 없다.

### 5.8 Supply-chain, SBOM, CycloneDX

실제 파일 상태는 다음과 같다.

| Artifact | status | generated_at | closeout component 포함 여부 |
|---|---|---|---|
| `ops/reports/supply-chain-gate-report.json` | `pass` | `2026-04-29T02:30:27Z` | 미포함 |
| `ops/reports/sbom-readiness-gate-report.json` | `pass` | `2026-04-29T02:30:29Z` | 미포함 |
| `ops/reports/cyclonedx-bom.json` | `$schema=http://cyclonedx.org/schema/bom-1.6.schema.json` | n/a | 미포함 |

두 신규 리뷰의 판단처럼 supply-chain/SBOM gate 자체는 pass 상태지만, release closeout의 strict component로는 아직 포함되지 않는다. 또한 CycloneDX BOM은 외부 HTTP schema를 참조하므로 offline complete validation을 요구하는 release audit에서는 vendored schema 또는 외부 schema policy가 필요하다.

### 5.9 Raw markdown / raw intake workflow

신규 통합 리뷰가 강조한 raw intake workflow는 실제 파일에서 확인된다.

| Artifact | 확인값 |
|---|---|
| `runs/run-20260415-raw-markdown-normalization/raw-markdown-normalization-report.json` | `file_count=111`, `changed_count=67`, `manual_review_count=1` |
| `raw-intake-absorption-matrix-2026-04-22.json` | `source_count=180`, `create_new_synthesis_family=104`, `refresh_existing_synthesis=64` |
| `raw-intake-promotion-profiles-2026-04-22.json` | `family_count=20`, `refresh_count=10` |
| `raw-intake-promotion-render-after-concept-integration-2026-04-22.json` | `status=pass`, `written_file_count=50` |
| `raw-registry-preflight-final-tree-2026-04-22.json` | `status=pass`, `entry_count=446`, `errors=0`, `warnings=0` |
| `wiki-lint-final-tree-2026-04-22.json` | `status=pass`, `errors=0`, `warnings=0` |

이 항목은 release-ready를 직접 막는 blocker는 아니지만, 기준 리뷰 이후 작업분의 실체를 보여 주는 중요한 운영 증거다.

---

## 6. 이번 직접 검증 결과

### 6.1 Canonical report-schema 10쌍 검증

다음 10개 report-schema 쌍은 이번에 직접 JSON Schema 검증을 수행했고 모두 통과했다.

| Report | Schema | 이번 직접 검증 | 현재 report status |
| --- | --- | --- | --- |
| ops/reports/raw-registry-preflight-report.json | ops/schemas/raw-registry-preflight-report.schema.json | pass | pass |
| ops/reports/raw-registry-preflight-reproducibility.json | ops/schemas/raw-registry-preflight-reproducibility.schema.json | pass | pass |
| ops/reports/test-execution-summary.json | ops/schemas/test-execution-summary.schema.json | pass | pass |
| ops/reports/release-smoke-report.json | ops/schemas/release-smoke-report.schema.json | pass | pass |
| ops/reports/generated-artifact-index.json | ops/schemas/generated-artifact-index.schema.json | pass | attention |
| ops/reports/artifact-freshness-report.json | ops/schemas/artifact-freshness-report.schema.json | pass | attention |
| ops/reports/auto-improve-readiness.json | ops/schemas/auto-improve-readiness-report.schema.json | pass | current |
| ops/reports/release-closeout-summary.json | ops/schemas/release-closeout-summary.schema.json | pass | fail |
| ops/reports/supply-chain-gate-report.json | ops/schemas/supply-chain-gate-report.schema.json | pass | pass |
| ops/reports/sbom-readiness-gate-report.json | ops/schemas/sbom-readiness-gate-report.schema.json | pass | pass |


### 6.2 전체 local-schema-backed JSON 검증

이번 재검증에서는 `*.json` 전체를 스캔하여 local `$schema`가 `ops/schemas/...`를 가리키는 JSON을 모두 검증했다.

| 항목 | 값 |
|---|---:|
| 전체 JSON 파일 수 | 242 |
| local `ops/schemas/...` `$schema` 보유 JSON | 167 |
| local schema validation pass | 167 |
| local schema validation fail/exception | 0 |
| 외부/draft schema 참조 JSON | 63 |
| `$schema` 없는 JSON | 12 |
| JSON parse errors | 0 |

두 신규 리뷰 중 하나가 언급한 “158개 내부 schema-backed JSON validation”은 해당 리뷰의 검증 범위 기준으로 해석하는 것이 안전하다. 이번 직접 스캔은 더 넓게 잡아 **167개 local-schema-backed JSON 전부 pass**를 확인했다. 이는 리뷰 결론과 충돌하지 않고, 오히려 schema coverage가 실제 파일 수준에서 더 넓게 확인된 보강 증거다.

### 6.3 실행 검증 한계

이번 세션에서 focused pytest와 `release_closeout_summary` CLI를 직접 재실행하려고 했으나, 현재 노트북 실행 계층에서 subprocess가 장시간 응답하지 않아 각각 60초 자동 인터럽트 또는 30초 timeout에 걸렸다. 따라서 이번 보고서에서는 해당 재실행을 pass/fail 증거로 사용하지 않았다.

사용한 확정 증거는 다음으로 제한했다.

- ZIP SHA 및 `zipfile.testzip()` 무결성
- 실제 추출 파일 존재 및 metadata
- 주요 JSON report 값 직접 파싱
- canonical 10개 report-schema 직접 검증
- local-schema-backed JSON 167개 직접 검증
- 체크인된 `test-execution-summary.json`의 177 passed / 18 fingerprints / collect digest 증적

---

## 7. 기준 리뷰 이후 반영된 작업분 재정리

### 7.1 완료 또는 사실상 완료로 재분류할 항목

| 항목 | 기준 리뷰 당시 | 현재 실제 파일 기준 |
|---|---|---|
| `release-closeout-summary` | 부재, 도입 권장 | script/schema/report/test/Makefile target 존재. report는 `status=fail`이지만 집계 artifact 자체는 구현됨 |
| test execution target fingerprints | 부재 | 18개 test target fingerprint와 177개 collect nodeid digest 존재 |
| raw registry stored/live reproducibility | 권고 또는 불일치 우려 | same-environment 기준 `diff_status=match` |
| raw registry metric semantics | 설명 부족 | `path_alias_resolution_mode`, `alias_policy_version`, `environment_fingerprint`, `metric_semantics` 존재 |
| artifact freshness missing schema | 13건 | 0건 |
| stable artifact debt | 47 artifacts / 107 issues | 32 artifacts / 64 issues |
| bare pytest guided failure | 문서화 위주, UX 미완 | `tests/conftest.py`, `tests/test_pytest_entrypoint_guidance.py`, README/ops README로 구현 근거 확인 |
| fast/full smoke policy | retention policy 불명확 | full canonical report와 fast developer precheck 경로 분리 확인 |
| supply-chain/SBOM gate | 기준 리뷰 핵심에는 부재 | gate report와 schema 존재, status pass |

### 7.2 부분 해소로 재분류할 항목

| 항목 | 해소된 부분 | 남은 부분 |
|---|---|---|
| artifact freshness | missing schema 0, stable debt 감소 | mtime-sensitive historical/archive debt 32 artifacts / 64 issues, attention 유지 |
| generated artifact index | archive reason과 candidate 구조화 | archive candidate 24건 실제 이동 미완, attention 유지 |
| raw registry reproducibility | Linux/C.UTF-8 same-env stored/live match | macOS/Windows/locale/extraction tool matrix 미완 |
| release evidence closeout | 단일 집계 view 도입 | source-tree coherence와 generation order strict gate 부재 |
| test summary | fingerprint와 collect digest 도입 | deselected tests의 구조화된 사유 부재 |
| supply-chain/SBOM | gate pass | release closeout strict component 편입 여부 미정 |

### 7.3 여전히 미완인 항목

1. `learning_readiness.likely_to_learn=false`에 따른 release blocker 해소
2. closeout component들의 source-tree fingerprint 정렬 또는 허용 divergence 정책
3. release smoke full evidence를 후속 변경 이후 다시 생성하는 strict chain
4. artifact freshness와 release closeout 간 순환/생성 순서 정책
5. generated index archive candidate 24건 정리
6. raw registry cross-environment matrix
7. post-index modification guard
8. accepted risk expiry와 owner/signoff 기록
9. CycloneDX offline schema validation
10. public/private boundary와 local workspace file inclusion policy

---

## 8. 새로 또는 더 강하게 식별된 개선 방안

### 8.1 P0 — Release-ready 수렴을 위한 필수 개선

#### 8.1.1 Learning readiness closeout

목표는 두 경로 중 하나다.

- **증거 해소 경로:** `attempts_considered >= 10`, `telemetry_coverage_ratio > 0`, `session_calibration_status != no_session_context`, `likely_to_learn=true`.
- **운영자 signoff 경로:** `learning_blocked_by_review_required`를 named accepted risk로 승인하고, 승인자·승인 시각·만료 조건·재검토 조건·rollback trigger를 별도 canonical artifact에 기록.

권장 artifact는 `ops/reports/learning-readiness-signoff.json`이다. 이 파일은 release closeout이 읽을 수 있어야 하며, closeout summary에 accepted risk로 반영되어야 한다.

#### 8.1.2 Release evidence cohort consistency gate

현재 component fingerprint 6개가 모두 다르므로, closeout에는 다음 구조가 필요하다.

```json
{
  "source_tree_coherence": {
    "status": "pass|attention|fail",
    "component_fingerprint_count": 0,
    "release_relevant_file_modified_after_component_count": 0,
    "policy": "strict_same_fingerprint|allowed_divergence_with_fingerprints",
    "components": []
  }
}
```

최소 acceptance criteria는 다음이다.

- 모든 release-blocking component가 동일 `source_tree_fingerprint`를 갖거나,
- 서로 다른 fingerprint를 허용하는 경우 각 divergence가 policy로 설명되고 accepted risk에 연결되어야 한다.
- closeout 시점 이후 release-relevant file modification이 있으면 fail 또는 attention으로 승격해야 한다.

#### 8.1.3 Release evidence closeout Makefile target

현재 `report-contract-closeout`은 유용하지만 release smoke full을 항상 다시 실행하는 strict release evidence chain은 아니다. 다음 target 계층을 별도로 둘 필요가 있다.

```make
release-evidence-closeout:
    make release-smoke-full
    make test-execution-summary
    make generated-artifact-index
    make artifact-freshness
    make release-closeout-summary
```

이 target은 report contract evidence와 release evidence를 분리하고, full smoke가 오래된 상태로 closeout에 섞이는 위험을 줄인다.

### 8.2 P1 — Evidence semantics 강화

#### 8.2.1 Accepted risk expiry

현재 accepted risk 2건은 closeout에 들어 있지만 만료 조건이 없다. 다음 필드를 도입해야 한다.

- `accepted_by`
- `accepted_at`
- `expires_at` 또는 `expires_on_next_release`
- `revalidation_condition`
- `maximum_allowed_count`
- `risk_owner`

#### 8.2.2 Artifact debt surface-specific queue

남은 debt는 일반 backfill이 아니라 owner surface별 큐로 나눠야 한다.

| Queue | 대상 | 종료 조건 |
|---|---|---|
| `runs_historical_archive_queue` | `runs/*` historical artifact | archive class 또는 currentness policy 확정 |
| `ops_reports_producer_refresh_queue` | `auto-improve-sessions`, `sbom-export-mapping`, `supply-chain-provenance` | producer가 artifact envelope/currentness를 직접 기록 |
| `mtime_sensitive_regeneration_queue` | mtime drift artifact | generated_at/file_mtime policy 확정 및 재생성 |

#### 8.2.3 Archive execution manifest

`generated-artifact-index.json`은 candidate를 잘 보여 주지만 실제 이동 실행 증거는 없다. `ops/reports/archive-execution-manifest.json`을 도입해 다음을 기록하는 것이 좋다.

- source path
- target archive path
- superseded-by 검토 결과
- dry-run/applied 상태
- operator confirmation
- rollback path

#### 8.2.4 Test deselection semantics

현재 command string의 `--deselect` 3건은 release evidence 해석에 중요하다. 다음 필드를 `test-execution-summary.json`에 추가해야 한다.

```json
{
  "deselected_tests": [
    {
      "nodeid": "...",
      "reason": "...",
      "policy_ref": "...",
      "release_blocking": false,
      "expected_to_pass_after_refresh": true
    }
  ]
}
```

#### 8.2.5 Raw registry cross-environment matrix

현재 same-env reproducibility는 pass다. 다음 matrix를 추가해야 한다.

- Linux + C.UTF-8 + Python zipfile extraction
- macOS default locale
- Windows path separator 및 Unicode normalization
- 다른 ZIP extraction tool
- manual alias fallback fixture
- content hash fallback fixture

### 8.3 P2 — 운영 hygiene와 packaging 강화

#### 8.3.1 CycloneDX offline schema policy

`ops/reports/cyclonedx-bom.json`은 외부 HTTP schema를 참조한다. offline release audit 요구가 있다면 CycloneDX 1.6 schema를 vendoring하거나, 외부 schema는 release-blocking validation 대상이 아니라는 정책을 명시해야 한다.

#### 8.3.2 Bootstrap reproducibility

체크인된 `test-execution-summary.json`의 command는 `.venv/bin/python`을 사용한다. ZIP에는 `.venv`가 없으므로 외부 재현자는 다음 정보가 필요하다.

- Python version
- pytest version
- dependency install command
- virtualenv 생성 절차
- plugin autoload policy
- supported entrypoint 목록

#### 8.3.3 Local workspace/public boundary

`.obsidian/workspace.json`, `.vscode`, placeholder run directory 등은 release archive와 review archive의 목적에 따라 include/exclude policy가 달라져야 한다. 현재 ZIP이 review snapshot이라면 허용될 수 있으나, public/release archive라면 더 강한 제외 정책이 필요하다.

#### 8.3.4 Schema zero-count 유지 guard

`missing_schema_count=0`은 큰 성과다. 새 JSON artifact가 schema 없이 추가되는 회귀를 막으려면 CI 또는 Makefile gate에서 다음을 요구해야 한다.

- 새 JSON artifact는 local schema 또는 명시적 noncanonical marker를 가져야 한다.
- schema가 필요 없는 JSON은 owner와 reason을 machine-readable하게 남긴다.
- `artifact_freshness`의 missing schema check를 release-blocking 또는 at least strict warning으로 운영한다.

---

## 9. 권장 실행 순서

### 9.1 Tranche 1 — Release-ready 직접 수렴

1. `learning_readiness`를 실제 evidence로 해소할지, operator signoff로 accepted risk 처리할지 결정한다.
2. 선택한 경로에 맞춰 `learning-readiness-signoff.json` 또는 learning telemetry evidence를 생성한다.
3. `release-evidence-closeout` target을 추가하거나 기존 closeout target을 엄격화한다.
4. full smoke → test summary → generated index → artifact freshness → release closeout 순서로 evidence를 재생성한다.
5. closeout에서 `release_ready=true`가 되거나, 남은 blocker가 명시적 accepted risk로만 남는지 확인한다.

### 9.2 Tranche 2 — Evidence cohort consistency

1. component별 `source_tree_fingerprint`를 closeout이 비교하게 한다.
2. fingerprint 불일치 정책을 `strict_same_fingerprint` 또는 `allowed_divergence_with_fingerprints` 중 하나로 명시한다.
3. release-relevant 파일이 component 생성 이후 수정되면 closeout이 attention/fail로 반응하게 한다.
4. `generated_at` skew 허용 범위와 예외 정책을 문서화한다.

### 9.3 Tranche 3 — Debt cleanup

1. generated index의 archive candidate 24건을 검토한다.
2. archive execution manifest를 dry-run으로 생성한다.
3. `runs/*` historical artifact를 archive/currentness class로 재분류한다.
4. `ops/reports/*` producer-specific artifact를 재생성하거나 envelope/currentness를 producer에서 직접 기록한다.
5. artifact freshness를 재실행해 stable debt 32/64가 줄었는지 확인한다.

### 9.4 Tranche 4 — Cross-environment와 supply-chain

1. raw registry reproducibility matrix를 macOS/Windows/locale variation으로 확장한다.
2. supply-chain/SBOM gate를 release closeout strict component로 편입할지 결정한다.
3. CycloneDX schema vendoring 또는 policy exception을 결정한다.
4. `.venv` 없는 ZIP 재현 절차와 dependency bootstrap을 README/ops README/report에 명시한다.

---

## 10. 종합 판정

### 10.1 두 신규 리뷰의 신뢰도 판정

| 리뷰 | 판정 | 이유 |
|---|---|---|
| `llm_wiki_vnext_integrated_review_report_20260429.md` | 신뢰 가능, 가장 넓은 coverage | 실제 파일 수치와 주요 결론이 일치하며, raw intake·live drift·CycloneDX·source-tree coherence 등 고유 발견이 유효함 |
| `후속점검보고서.md` | 신뢰 가능, 실행순서 정리에 강함 | 실제 파일 수치와 주요 결론이 일치하며, 다음 tranche와 최소 완결 단위를 명확히 제시함 |
| 기존 `post_crosscheck_improvement` 보고서 | 여전히 유효, 다만 일부 세부는 신규 리뷰가 보강 | 주요 판정은 두 신규 리뷰와 일치하며, 신규 리뷰가 더 넓은 검증과 추가 위험을 보완함 |

### 10.2 최종 상태

현재 ZIP은 기준 리뷰보다 훨씬 진전됐다. 특히 release evidence의 파일 존재, schema coverage, test summary fingerprint, raw registry reproducibility, release closeout aggregation은 실제 파일 기준으로 확인된다. 그러나 release-ready는 아니다.

현재 release-ready를 막는 직접 사유는 다음이다.

1. `learning_blocked_by_review_required` hard blocker 1건이 남아 있다.
2. closeout component 6개가 서로 다른 `source_tree_fingerprint`를 갖고, 이를 strict하게 판정하는 source-tree coherence gate가 없다.
3. `artifact_freshness`와 `generated_index`는 pass가 아니라 accepted risk다.
4. release smoke full evidence가 후속 변경 이후 strict chain으로 다시 닫혔다는 증거가 부족하다.
5. raw registry는 same-env reproducibility만 있고 cross-env matrix가 없다.

### 10.3 최종 한 문장 요약

> **두 신규 리뷰는 기존 개선 보고서와 충돌하지 않고, 실제 ZIP 파일 대조 결과도 핵심 결론을 확인한다. 저장소는 기준 리뷰 이후 실질적으로 진전됐지만, 현재 release-ready를 막는 마지막 본질적 병목은 `learning_readiness`이며, 다음 개선 라운드는 `learning evidence`, `source-tree coherence`, `release evidence refresh order`, `archive/currentness semantics`를 닫는 데 집중해야 한다.**

---

## Appendix A. 실제 확인한 주요 파일 존재 여부

| 파일 | 존재 여부 |
|---|---:|
| `ops/scripts/release_closeout_summary.py` | true |
| `ops/schemas/release-closeout-summary.schema.json` | true |
| `ops/reports/release-closeout-summary.json` | true |
| `tests/test_release_closeout_summary.py` | true |
| `tests/conftest.py` | true |
| `tests/test_pytest_entrypoint_guidance.py` | true |
| `ops/reports/raw-registry-preflight-reproducibility.json` | true |
| `ops/reports/test-execution-summary.json` | true |
| `ops/reports/supply-chain-gate-report.json` | true |
| `ops/reports/sbom-readiness-gate-report.json` | true |

## Appendix B. 이번 보고서 작성 중 적용한 증거 우선 원칙

- 문서 결론은 실제 ZIP 파일 값과 맞을 때 “확인됨”으로 분류했다.
- 문서가 인용한 upstream 보고서가 현재 파일로 직접 존재하지 않는 경우에는 “해당 신규 리뷰의 전문 서술”로만 취급했다.
- subprocess 기반 pytest/CLI 재실행은 현재 환경 제한으로 완료하지 못했으므로 pass 증거로 사용하지 않았다.
- 대신 schema validation, JSON parsing, ZIP CRC, checked-in report evidence를 확정 근거로 사용했다.
- path, count, status, fingerprint, generated_at처럼 기계적으로 확인 가능한 값은 실제 파일에서 다시 읽어 기록했다.
