# LLM Wiki vNext Dual Integrated Review Cross-check Improvement Report

- 작성일 2026-04-29 (AsiaSeoul)
- 산출 파일명 `llm_wiki_vnext_dual_integrated_review_crosscheck_improvement_report_20260429.md`
- 검토 대상 신규 리뷰
  1. `llm_wiki_vnext_integrated_assessment_report_20260429.md`
  2. `llm_wiki_vnext_integrated_post_assessment_report_20260429.md`
- 대조 기준
  - ZIP 내부 기존 기준 리뷰 `external-reportsllm_wiki_vnext_improvement_assessment_20260429.md`
  - 이전 후속 보고서 `llm_wiki_vnext_post_assessment_followup_report_20260429_v2.md`
  - 실제 ZIP `LLM Wiki vNext.zip`
- 실제 ZIP SHA-256 `8e0ce1e586b615d80549fb9315a1ed5a201ca9c380964ceb513381ae5b41bcda`
- ZIP inventory entries `1,674`, files `1,592`, dirs `82`
- CRC 검사 `zipfile.testzip() == None`
- 최종 판정 `materially_progressed_but_release_ready_blocked_by_evidence_semantics`

---

## 1. 보고서 목적

본 보고서는 새로 제공된 두 통합 리뷰 문서인 `llm_wiki_vnext_integrated_assessment_report_20260429.md`와 `llm_wiki_vnext_integrated_post_assessment_report_20260429.md`를 처음부터 끝까지 검토한 뒤, 다음 세 축과 대조해 개선 현황을 재정리한 문서다.

1. ZIP 내부 기존 기준 리뷰인 `external-reportsllm_wiki_vnext_improvement_assessment_20260429.md`
2. 이전 후속 보고서인 `llm_wiki_vnext_post_assessment_followup_report_20260429_v2.md`
3. 현재 업로드된 실제 `LLM Wiki vNext.zip` 내부 파일, schema, canonical report, Makefile target

두 신규 리뷰는 모두 동일한 현재 ZIP SHA-256 `8e0ce1e586b615d80549fb9315a1ed5a201ca9c380964ceb513381ae5b41bcda`를 대상으로 하며, 결론도 큰 방향에서 일치한다. 즉 현재 스냅샷은 기준 리뷰 이후 실질적으로 많이 개선되었지만, 아직 release-ready로 판정하기에는 핵심 증적·학습·freshness semantics가 부족하다.

---

## 2. 검토한 입력 자료

### 2.1 신규 리뷰 2건

 문서  성격  핵심 초점 
---------
 `llm_wiki_vnext_integrated_assessment_report_20260429.md`  세 후속 리뷰를 통합한 평가 보고서  리뷰 간 공통 확인, 고유 관찰, 상태 재분류, 권고사항 
 `llm_wiki_vnext_integrated_post_assessment_report_20260429.md`  통합 후속 평가 보고서  실제 반영 작업, 남은 작업, 새 개선 포인트, 우선순위 권고 

두 문서는 구조와 표현은 다르지만, 다음 판단에는 일치한다.

- raw registry canonical report는 현재 환경 기준으로 해소되었다.
- test execution summary artifact는 도입되었다.
- `release-smoke-full` alias는 추가되었다.
- stable artifact contract debt는 줄었지만 남아 있다.
- learning readiness는 여전히 핵심 blocker다.
- fastfull smoke evidence policy는 미완이다.
- raw registry cross-environment evidence는 미완이다.
- bare pytest guided failure는 문서화만 있고 UX 구현은 미완이다.
- 최종 상태는 아직 release-ready가 아니다.

### 2.2 실제 ZIP 및 기존 파일 대조

실제 `LLM Wiki vNext.zip`을 열어 다음을 재확인했다.

 항목  실제 확인값 
------
 ZIP SHA-256  `8e0ce1e586b615d80549fb9315a1ed5a201ca9c380964ceb513381ae5b41bcda` 
 entries  `1,674` 
 files  `1,592` 
 dirs  `82` 
 compressed bytes  `190,828,729` 
 uncompressed bytes  `240,759,751` 
 CRC 검사  `None`, 무결 
 기준 리뷰 존재  `external-reportsllm_wiki_vnext_improvement_assessment_20260429.md` 존재 
 이전 후속 보고서 존재  `mntdatallm_wiki_vnext_post_assessment_followup_report_20260429_v2.md` 존재 

---

## 3. 두 신규 리뷰의 결론 비교

### 3.1 최종 판정 문구 비교

 문서  최종 판정 
------
 `llm_wiki_vnext_integrated_assessment_report_20260429.md`  `progressed_materially_but_still_not_release_ready` 
 `llm_wiki_vnext_integrated_post_assessment_report_20260429.md`  `materially_improved_but_still_not_release_ready` 
 본 대조 보고서  `materially_progressed_but_release_ready_blocked_by_evidence_semantics` 

표현은 다르지만 의미는 같다. 현재 ZIP은 단순히 조금 나아진 상태가 아니라, 기준 리뷰에서 미해결로 남았던 몇몇 구체 항목을 실제로 닫았다. 그러나 남은 blocker가 대부분 release evidence semantics, learning readiness, freshnesscurrentness discipline에 있으므로 release-ready 판정은 아직 불가능하다.

### 3.2 두 리뷰가 공통으로 확인한 해소 항목

 항목  두 리뷰 공통 판정  실제 파일 대조 결과 
---------
 `raw-registry-preflight-report.json` 도입  resolved for current environment  확인됨 
 `test-execution-summary.json` 도입  resolved  확인됨 
 `release-smoke-full` alias  resolved  확인됨 
 release-smoke full report 갱신  resolvedrefreshed  확인됨 
 stable artifact debt 감소  materially reduced  확인됨 
 generated artifact index 재갱신  improved, still attention  확인됨 
 pytest entrypoint contract 문서화  contract clarified  리뷰 내용상 확인, bare pytest UX는 미완 
 schema validation 통과  pass  직접 재검증 6종 통과 

### 3.3 두 리뷰가 공통으로 확인한 미해결 항목

 항목  공통 판정  release 영향 
---------
 learning readiness  unresolved core blocker  높음 
 stable artifact contract debt  reduced but unresolved  높음 
 missing schema 13건  unresolved  중~높음 
 fastfull smoke evidence storage policy  unresolved  중 
 raw registry cross-environment evidence  incomplete  중~높음 
 bare pytest guided failure  unresolved  policy only  중 
 generated index `attention`  unresolved  중 
 mtime-sensitive freshness drift  newly emphasized  중~높음 
 release closeout 상위 집계 artifact 부재  newly identified  중 

---

## 4. 실제 파일 대조 결과

### 4.1 Canonical report 존재 여부

실제 ZIP 내부에서 다음 canonical report가 존재함을 확인했다.

 report  존재  상태 요약 
---------
 `opsreportsraw-registry-preflight-report.json`  yes  `status=pass` 
 `opsreportstest-execution-summary.json`  yes  `status=pass`, `158 passed` 
 `opsreportsrelease-smoke-report.json`  yes  `status=pass`, `profile=full` 
 `opsreportsgenerated-artifact-index.json`  yes  `status=attention` 
 `opsreportsartifact-freshness-report.json`  yes  `status=attention` 
 `opsreportsauto-improve-readiness.json`  yes  `learning_readiness.status=learning_uncertain` 

### 4.2 Schema validation 재검증

실제 ZIP에서 schema와 report를 추출해 JSON Schema validation을 수행했다. 결과는 다음과 같다.

 report  schema  validation 
---------
 `raw-registry-preflight-report.json`  `raw-registry-preflight-report.schema.json`  pass 
 `test-execution-summary.json`  `test-execution-summary.schema.json`  pass 
 `release-smoke-report.json`  `release-smoke-report.schema.json`  pass 
 `generated-artifact-index.json`  `generated-artifact-index.schema.json`  pass 
 `artifact-freshness-report.json`  `artifact-freshness-report.schema.json`  pass 
 `auto-improve-readiness.json`  `auto-improve-readiness.schema.json`  pass 

따라서 두 신규 리뷰의 “canonical report schema validation 통과” 주장은 실제 파일과 일치한다.

### 4.3 Makefile target wiring 재확인

실제 Makefile에서 다음 target을 확인했다.

 target  확인 결과 
------
 `release-smoke`  존재, full profile 실행 
 `release-smoke-full`  존재, `release-smoke` alias 
 `release-smoke-fast`  존재, fast profile 실행 
 `registry-preflight`  존재 
 `test-execution-summary`  존재 

dry-run 기준으로 `release-smoke-full`은 full profile, `release-smoke-fast`는 fast profile을 실행하도록 연결되어 있었다. 이 역시 두 신규 리뷰의 판단과 일치한다.

---

## 5. 기준 리뷰 대비 실제 개선 사항

### 5.1 Raw registry preflight canonical artifact 도입

기준 리뷰에서는 raw registry preflight 관련 코드·테스트는 있었지만 canonical report가 없다는 점이 blocker였다. 현재는 다음 구성요소가 모두 존재한다.

 구성요소  현재 상태 
------
 script  `opsscriptsraw_registry_preflight.py` 
 schema  `opsschemasraw-registry-preflight-report.schema.json` 
 report  `opsreportsraw-registry-preflight-report.json` 
 test  `teststest_raw_registry_preflight.py` 
 Makefile target  `registry-preflight` 
 console script  `llm-wiki-raw-registry-preflight` 

저장 report 주요 값

 key  value 
------
 `artifact_kind`  `raw_registry_preflight_report` 
 `status`  `pass` 
 `generated_at`  `2026-04-28T165819Z` 
 `locale`  `C.UTF-8` 
 `unsupported_environment`  `false` 
 `stats.entry_count`  `446` 
 `stats.error_count`  `0` 
 `stats.warning_count`  `0` 
 `stats.path_alias_match_count`  `0` 
 `stats.content_hash_fallback_count`  `0` 

재분류 `unresolved` → `resolved_for_current_environment`.

다만 신규 리뷰에서 지적한 대로 cross-environment evidence는 아직 없으며, storedlive 재생성 시 `path_alias_match_count`가 달라진다는 관찰이 있어 완전 해결로 보기는 어렵다.

### 5.2 Test execution summary artifact 도입

기준 리뷰에서는 test execution summary artifact가 없었다. 현재는 다음 파일군이 존재한다.

 구성요소  현재 상태 
------
 script  `opsscriptstest_execution_summary.py` 
 schema  `opsschemastest-execution-summary.schema.json` 
 report  `opsreportstest-execution-summary.json` 
 test  `teststest_test_execution_summary.py` 
 Makefile target  `test-execution-summary` 
 console script  `llm-wiki-test-execution-summary` 

저장 report 주요 값

 key  value 
------
 `artifact_kind`  `test_execution_summary` 
 `suite`  `report-contracts` 
 `status`  `pass` 
 `returncode`  `0` 
 `timed_out`  `false` 
 `timeout_seconds`  `5400` 
 `termination_reason`  `completed` 
 `duration_ms`  `247879` 
 `counts.passed`  `158` 
 `counts.failed`  `0` 
 `counts.errors`  `0` 
 `counts.skipped`  `0` 
 `counts.warnings`  `0` 

재분류 `unresolved` → `resolved_as_canonical_report_present`.

남은 보완점은 test target file fingerprint가 포함되지 않아, report 생성 이후 test file 변경을 artifact 자체로 감지하기 어렵다는 점이다.

### 5.3 `release-smoke-full` alias 추가

기준 리뷰에서 미해결이었던 `release-smoke-full` alias가 실제 Makefile에 추가되었다.

```make
release-smoke
	$(PYTHON) -m ops.scripts.release_smoke --vault $(VAULT) --profile full

release-smoke-full release-smoke

release-smoke-fast
	$(PYTHON) -m ops.scripts.release_smoke --vault $(VAULT) --profile fast
```

재분류 `unresolved` → `resolved`.

다만 fastfull report storage policy는 별도 문제로 남는다.

### 5.4 Release smoke full report 재생성

현재 `opsreportsrelease-smoke-report.json`은 full profile 기준 pass report다.

 key  value 
------
 `artifact_kind`  `release_smoke_report` 
 `profile`  `full` 
 `status`  `pass` 
 `generated_at`  `2026-04-28T165502Z` 
 `packed_file_count`  `1331` 

내부 command는 raw registry preflight, wiki lint, wiki eval, stage2 eval, planning gate validate를 포함하며, 신규 리뷰에 따르면 5개 command 모두 returncode 0이다.

### 5.5 Stable artifact contract debt 감소

기준 리뷰와 현재 report를 비교하면 다음과 같다.

 지표  기준 리뷰  현재  변화 
------------
 `stable_contract_debt_artifact_count`  71  47  -24 
 `stable_contract_debt_issue_count`  155  107  -48 
 `unknown_currentness_artifact_count`  71  47  -24 
 `missing_artifact_envelope_count`  71  47  -24 
 `stale_artifact_count`  34  33  -1 
 `missing_schema_count`  13  13  0 

재분류 `unresolved` → `materially_reduced_but_unresolved`.

감소 폭은 의미 있지만, 47개 artifact  107개 issue는 여전히 release blocker다. 특히 `missing_schema_count=13`이 줄지 않은 점은 다음 tranche의 명확한 작업 대상이다.

### 5.6 Generated artifact index 재갱신

현재 `generated-artifact-index.json`은 새 canonical report를 반영하고 있으며, 생성 순서도 주요 report 이후다.

 항목  현재 
------
 `ops_reports_root_file_count`  22 
 `external_reports_root_file_count`  21 
 `canonical_report_count`  30 
 `archive_candidate_count`  24 
 `status`  `attention` 

재분류 `partially resolved but suspect` → `improved_but_still_attention`.

index는 좋아졌지만 archive namespace 정리, dated report relocation, archived run top-level 잔존 문제가 남아 있다.

---

## 6. 두 신규 리뷰에서 추가로 식별된 개선 포인트

### 6.1 Raw registry storedlive stats 재현성 불일치

신규 리뷰들은 저장된 `raw-registry-preflight-report.json`과 live 재생성 결과 사이에 다음 차이가 있었다고 기록한다.

 지표  저장본  live 재생성 
---------
 `path_alias_match_count`  0  332 
 `content_hash_fallback_count`  0  0 
 `source_tree_fingerprint`  동일  동일 

이 관찰은 중요하다. canonical report가 존재하고 schema validation을 통과하더라도, 동일 source tree fingerprint에서 runtime 재생성 stats가 크게 달라진다면 해당 artifact의 environment sensitivity가 충분히 설명되지 않은 것이다.

개선 방안

- `path_alias_resolution_mode` 또는 `alias_policy_version`을 report에 추가한다.
- environment fingerprint에 OS, locale, extraction tool, path normalization mode를 포함한다.
- `path_alias_match_count`가 environment-sensitive metric인지 deterministic metric인지 명시한다.
- stored report와 live report의 diff를 별도 diagnostic artifact로 저장한다.

### 6.2 Mtime-sensitive freshness drift

신규 리뷰는 저장본과 live 재생성 사이에 mtime-sensitive freshness 수치가 크게 달라진다고 기록한다.

 지표  저장본  live 재생성 
---------
 `stale_artifact_count`  33  89 
 `mtime_sensitive_artifact_count`  33  89 
 `mtime_sensitive_attention_issue_count`  33  89 
 stable debt 수치  47107  47107 

이는 ZIP extraction 또는 packaging 과정에서 mtime이 재해석되며 freshness 판단이 흔들릴 수 있음을 의미한다.

개선 방안

- stored currentness와 live regenerated currentness를 report에서 분리한다.
- ZIP packaging timestamp normalization을 release package preflight에 포함한다.
- mtime-sensitive artifact는 content fingerprint 기반 currentness로 전환한다.
- legacy artifact에는 accepted-risk 또는 noncanonical marker를 부여한다.

### 6.3 Test execution summary의 target fingerprint 부재

현재 test execution summary는 suite, command, schema, policy 등은 fingerprint에 포함하지만 실제 test target file content fingerprint는 충분히 포함하지 않는다.

문제 시나리오

1. `test-execution-summary.json`이 생성된다.
2. 이후 `teststest_generated_report_contracts.py` 같은 test file이 변경된다.
3. report는 여전히 `158 passed`라고 말한다.
4. artifact 자체만으로 어떤 test file이 바뀌었는지 감지하기 어렵다.

개선 방안

- wrapped command의 pytest selector를 해석한다.
- 해당 test file들의 content hash를 `test_target_fingerprints`에 포함한다.
- `pytest --collect-only` node id hash를 optional field로 저장한다.
- test target fingerprint가 바뀌면 summary를 stale로 판정한다.

### 6.4 Generated index 이후 release-relevant file 변경 guard 부재

신규 리뷰는 generated index 이후에도 release-relevant file이 바뀔 수 있다는 문제를 지적한다.

대표 예

 파일  timestamp 
------
 `opsreportsgenerated-artifact-index.json`  2026-04-29 021030 
 `teststest_generated_report_contracts.py`  2026-04-29 021048 
 `.obsidianworkspace.json`  2026-04-29 021124 

`.obsidianworkspace.json`은 release surface가 아닐 가능성이 높지만, `teststest_generated_report_contracts.py`는 release-relevant test surface다.

개선 방안

- release surface allowlistdenylist를 명확히 한다.
- canonical evidence 생성 이후 release-relevant file mtime이 더 최신이면 preflight fail 처리한다.
- `.obsidian`, `.vscode`, local cache 등은 ignore allowlist에 넣는다.
- index freshness guard의 책임 범위를 `release_surface`, `local_full_vault_surface`, `developer_hidden_surface`로 분리한다.

### 6.5 Release closeout 상위 집계 artifact 부재

현재 release evidence는 여러 파일에 분산되어 있다.

- `opsreportsrelease-smoke-report.json`
- `opsreportstest-execution-summary.json`
- `opsreportsraw-registry-preflight-report.json`
- `opsreportsartifact-freshness-report.json`
- `opsreportsgenerated-artifact-index.json`
- `opsreportsauto-improve-readiness.json`

개선 방안

- `opsreportsrelease-closeout-summary.json`을 도입한다.
- 위 canonical report들의 status, generated_at, source_tree_fingerprint, blocking reason을 집계한다.
- release-ready 여부를 단일 field로 계산한다.
- accepted-risk와 unresolved-blocker를 분리한다.

### 6.6 Fastfull smoke report retention policy 미정

현재 target은 fastfull 모두 있지만 report는 full 단일 파일만 있다.

 항목  현재 
------
 `release-smoke-full`  존재 
 `release-smoke-fast`  존재 
 `release-smoke-report.json`  존재, full 
 `release-smoke-report-fast.json`  없음 
 `release-smoke-report-full.json`  없음 

선택지는 두 가지다.

 정책  설명  장점  단점 
------------
 정책 A  full만 canonical, fast는 local precheck  단순함  fast evidence 보존 없음 
 정책 B  fastfull 모두 canonical report 저장  증적 대칭성  artifact 수 증가 

현재 프로젝트의 anti-overengineering 원칙상 정책 A가 더 적합하다. 단, README와 schematest에 “fast는 ephemeral developer precheck이고 canonical release evidence는 full smoke report 하나”라고 명시해야 한다.

### 6.7 Learning readiness 별도 blocker ticket 필요

현재 `auto-improve-readiness.json`의 핵심 수치는 다음과 같다.

 key  value 
------
 `execution_readiness.status`  `pass` 
 `learning_readiness.status`  `learning_uncertain` 
 `learning_readiness.likely_to_learn`  `false` 
 `attempts_considered`  `7` 
 `min_attempts_considered`  `10` 
 `session_calibration_status`  `no_session_context` 
 `telemetry_coverage_ratio`  `0.0` 
 `rework_count`  `5` 
 `defect_escape_pair_count`  `3` 

이 항목은 이제 다른 report hygiene 문제에 묻히면 안 된다. raw registry와 test summary가 닫힌 뒤 남은 가장 질적인 blocker다.

개선 방안

- `learning_readiness`를 별도 release blocker로 ticket화한다.
- `attempts_considered = 10`을 최소 closeout 조건으로 둔다.
- `session_calibration_status != no_session_context`가 되도록 실제 session context를 확보한다.
- `telemetry_coverage_ratio  0`을 최소 조건으로 둔다.
- `likely_to_learn == true`가 아니면 named blocker와 operator signoff를 요구한다.

---

## 7. 남은 작업 우선순위

### P0. Release-ready 판정을 막는 직접 blocker

1. Learning readiness closeout
   - `learning_uncertain`을 해소하거나 accepted-risk로 명시해야 한다.
   - 현재 `likely_to_learn=false`, `telemetry_coverage_ratio=0.0`은 release-ready와 양립하기 어렵다.

2. Artifact freshness safe tranche 처리
   - `missing_artifact_envelope` 47건
   - `unknown_currentness` 47건
   - 이 중 safe-to-backfill 18건을 먼저 닫는다.

3. Missing schema 13건 처리
   - schema를 추가하거나 noncanonical JSON으로 명확히 제외한다.
   - 기준 리뷰 이후 전혀 줄지 않았으므로 우선순위가 높다.

4. Generated index `attention` 해소
   - dated report archive 이동
   - archived run top-level namespace 정리
   - why_blocked 구조화

### P1. Evidence semantics 강화

1. Test execution summary에 target file fingerprints 추가
2. Raw registry preflight에 environment matrix 또는 environment fingerprint 확장
3. Storedlive reproducibility diagnostic artifact 추가
4. Release-relevant file post-index modification guard 추가
5. Release closeout summary artifact 도입

### P2. Developer UX 및 packaging hygiene

1. Bare pytest guided failure 최소 구현
2. README troubleshooting 보강
3. Clock skew  mtime normalization preflight 추가
4. Fast smoke report retention policy 문서화
5. Generated artifact index classification delta 설명 추가

---

## 8. 상태 재분류표

 항목  기준 리뷰 판정  신규 리뷰 통합 판정  본 보고서 대조 판정 
------------
 inventory count drift  resolved  resolved  resolved 
 generated index freshness  partially resolved  suspect  improved, still attention  improved_but_blocked_by_attention 
 fast smoke selector drift  resolved  resolved  resolved 
 release-smoke full report  resolved  resolvedrefreshed  resolvedrefreshed 
 release-smoke-full alias  unresolved  resolved  resolved 
 release-smoke fast report storage  unresolved  unresolved  unresolved_policy_choice_needed 
 raw registry canonical artifact  unresolved  resolved for current env  resolved_for_current_environment 
 raw registry cross-env evidence  incomplete  incomplete  incomplete 
 raw registry stats reproducibility  not separately identified  newly flagged  blocker_candidate 
 test execution summary artifact  unresolved  resolved  resolved_with_target_fingerprint_gap 
 stable artifact contract debt  unresolved  materially reduced but unresolved  materially_reduced_but_unresolved 
 missing schema  unresolved  unresolved  unresolved_13_remaining 
 learning readiness  unresolved  unresolved core blocker  unresolved_core_blocker 
 bare pytest guided failure  unresolved  unresolved  policy only  unresolved_ux 
 mtime-sensitive freshness drift  not separately identified  newly emphasized  blocker_candidate 
 release closeout summary  absent  newly identified  recommended 
 final release confidence  not release ready  still not release ready  still_not_release_ready 

---

## 9. 권장 실행 계획

### 9.1 가장 작은 완결 단위

현재 상태에서 가장 작은 완결 단위는 “새 기능 추가”가 아니라 “이미 생긴 증적 체계의 release semantics를 닫는 것”이다. 다음 순서를 권장한다.

1. `artifact-freshness-report.json`의 safe-to-backfill tranche를 줄인다.
2. `missing_schema_count=13`을 schema 부여 또는 noncanonical exclusion으로 닫는다.
3. `test-execution-summary.json`에 test target fingerprints를 추가한다.
4. `raw-registry-preflight-report.json`에 environment matrix 또는 deterministicstored metric 구분을 추가한다.
5. `release-closeout-summary.json`을 도입해 scattered evidence를 단일 release gate로 묶는다.
6. learning readiness는 별도 blocker로 관리해 최소 증거 기준을 충족시킨다.

### 9.2 작업 순서 예시

 순서  작업  완료 기준 
---------
 1  artifact freshness safe tranche backfill  safe-to-backfill blocker 0 또는 named blocker만 남음 
 2  missing schema 13건 정리  schema 추가 또는 noncanonical exclusion 
 3  test summary target fingerprints 추가  test file 변경 시 summary stale 감지 
 4  release-relevant post-index guard 추가  index 이후 testsopsschema 변경 시 preflight fail 
 5  raw registry env matrix 추가  single-env limitation이 구조화됨 
 6  release closeout summary 추가  release-ready 계산이 단일 artifact로 가능 
 7  learning readiness closeout  `learning_uncertain` 해소 또는 accepted-risk signoff 

---

## 10. 최종 결론

두 신규 리뷰는 기존 후속 보고서보다 더 넓은 통합 관점과 더 깊은 실행 관찰을 제공한다. 실제 ZIP과 대조한 결과, 두 리뷰의 핵심 판단은 대부분 사실과 일치한다.

현재 ZIP은 기준 리뷰 이후 다음을 실제로 개선했다.

- `raw-registry-preflight-report.json` canonical artifact 도입
- `test-execution-summary.json` canonical artifact 도입
- `release-smoke-full` alias 추가
- release smoke full report 갱신
- generated artifact index 재갱신
- stable artifact debt 71155에서 47107로 감소
- schema validation 가능한 canonical report 체계 강화

그러나 아직 release-ready는 아니다. 남은 문제는 단순 누락 파일이 아니라 다음과 같은 release evidence semantics 문제다.

- `learning_readiness.status=learning_uncertain`
- `learning_readiness.likely_to_learn=false`
- `telemetry_coverage_ratio=0.0`
- stable debt 47 artifacts  107 issues 잔존
- missing schema 13건 잔존
- generated index `status=attention`
- raw registry cross-environment evidence 부재
- storedlive raw registry stats 불일치
- mtime-sensitive freshness drift
- fastfull report retention policy 미정
- test execution summary target fingerprint 부재
- release closeout 상위 집계 artifact 부재

따라서 최종 판정은 다음과 같다.

`LLM Wiki vNext`는 기준 리뷰 이후 실질적으로 진전되었고, 일부 명시적 unresolved 항목은 resolved로 재분류되어야 한다. 그러나 release-ready를 막는 병목은 이제 “파일이 있느냐”가 아니라 “그 파일들이 현재 release 상태를 재현 가능하고 환경 독립적으로 증명하느냐”로 이동했다. 다음 개선 라운드는 artifact freshness, learning readiness, storedlive reproducibility, release closeout aggregation을 중심으로 진행해야 한다.