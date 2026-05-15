# LLM Wiki vNext 두 통합 리뷰 대조 개선 보고서

- **작성일**: 2026-04-28 (Asia/Seoul)
- **출력 파일명**: `llm_wiki_vnext_two_review_crosscheck_improvement_report_20260428.md`
- **직접 검토한 신규 리뷰 2건**
  1. `llm_wiki_vnext_integrated_post_review_report_20260428.md`
  2. `llm_wiki_vnext_triple_review_integrated_report_20260428.md`
- **대조한 기존 리뷰 및 산출물**
  - 이전 생성 보고서: `llm_wiki_vnext_post_review_current_state_report_20260428.md`
  - ZIP 내부 기준 외부 리뷰: `external-reports/llm_wiki_vnext_integrated_audit_report_20260428.md`
  - ZIP 내부 기준 외부 리뷰: `external-reports/llm_wiki_vnext_dual_review_improvement_report_20260428.md`
  - 실제 아카이브: `LLM Wiki vNext.zip`
- **대상 ZIP SHA-256**: `b33fed4266d8c25ca0acd2d4bbd84603cddad5ec1c54fbfdef644a2dad3465e5`
- **최종 판정**: `progressed_after_reviews_but_not_release_ready`
- **핵심 결론**: 두 신규 리뷰의 주요 결론은 실제 ZIP 및 저장 산출물과 대부분 일치한다. 단, 이번 대조에서 `generated-artifact-index.json` drift가 외부 리뷰 2건 누락에만 한정되지 않고 `task_improvement_observation_count`까지 포함하는 더 넓은 inventory drift임을 추가 확인했다. 또한 `make fast-smoke` stale node id 실패는 현재 파일에서도 그대로 재현된다.

---

## 1. 검토 방식과 한계

본 보고서는 두 신규 리뷰를 전문 기준으로 읽고, 기존 리뷰에서 제시한 핵심 판단과 실제 프로젝트 파일을 다시 대조했다. 실제 파일 검증은 ZIP 무결성, 저장된 JSON report, Makefile/test selector, external-reports inventory, generated artifact index, artifact freshness, auto-improve readiness, release-smoke 저장본을 중심으로 수행했다.

| 검증 | 결과 | 소요 | 해석 |
|---|---:|---:|---|
| ZIP CRC 검사 (`zipfile.testzip`) | pass | — | 손상 entry 없음 |
| Python 안전 추출 | pass | — | path traversal 없음, 1,583개 파일 추출 |
| `raw_registry_preflight` on clean UTF-8 extraction | pass | 9.59s | 446 entries, errors 0, warnings 0 |
| `make registry-preflight` on existing extraction | pass | 8.41s | UTF-8 추출 환경에서는 raw registry pass 재확인 |
| `make fast-smoke` | fail | 8.38s | stale pytest node id로 즉시 실패 |
| `generated_artifact_index` live regeneration on clean extraction | pass | 2.41s | 저장본 summary와 실제 inventory 간 drift 확인 |
| `artifact_freshness_runtime` live regeneration on clean extraction | pass | 16.19s | stable debt는 동일, mtime-sensitive 수치는 live에서 증가 |

`make release-smoke-fast`는 재확인 시도 중 현재 도구 실행 환경의 자동 60초 interrupt에 걸려 새 증적으로 채택하지 않았다. 따라서 본 보고서에서는 두 신규 리뷰가 기록한 `make release-smoke-fast` pass 및 ZIP 내부 저장된 `release-smoke-report.json`을 별도 증거로만 취급한다. 사용자가 요청한 "timeout 제한 없이" 조건은 현재 런타임에서 완전히 보장할 수 없었다.

---

## 2. 신규 리뷰 2건의 성격 비교

두 신규 리뷰는 모두 리뷰-A/B/C 세 건을 통합하는 문서이며, 최종 방향은 사실상 같다. 차이는 강조점과 세부 전개 방식이다.

| 항목 | `integrated_post_review_report` | `triple_review_integrated_report` | 대조 판정 |
|---|---|---|---|
| 문서 목적 | 세 리뷰의 합의·쟁점·신규 발견·통합 권장 행동을 장문으로 정리 | 동일한 세 리뷰를 더 압축된 실행 보고서 형식으로 통합 | 상호 보완 |
| 구조 | 목차 포함 12개 대단원, PR-1~PR-8 실행 순서 상세 | 9개 대단원, 상태 라벨과 우선순위 압축 | 첫 번째는 감사 추적에 강하고 두 번째는 실행 지시가 선명함 |
| raw registry 해석 | C-locale fail / UTF-8 pass를 추출 로케일 분기로 설명 | 동일하게 extraction environment dependent로 정리 | 일치 |
| artifact debt | `71/71/13`, owner 분포와 issue 유형 상세 | `71/71/13`, 남은 ops_reports 7건과 missing schema 13건 정리 | 일치 |
| learning readiness | `learning_uncertain`, evidence 부족 강조 | 동일, acceptance criteria 명시 | 일치 |
| 신규 결함 | `make fast-smoke`, generated-artifact-index drift | 동일 두 항목을 P0/P1 우선순위로 배치 | 일치 |
| 개선 방안 | raw canonicalizer, current-tree fingerprint, test summary, profile split 등 종합 | 동일 개선안을 P0/P1/P1.5/P2로 재정렬 | 일치 |

### 2.1 누락 여부 점검

첫 번째 문서는 기준 리뷰 재정리, 세 리뷰 공통 합의, raw registry/bare pytest/gate 재현성 쟁점, 리뷰별 고유 발견, 기준 리뷰 재판정, P0/P1/P2 잔여 과제, PR-1~PR-8 실행 순서, 수치 부록을 포함한다. 두 번째 문서는 공통 판단과 불일치 해석, 검증 환경과 실행 결과 교차표, 기준 리뷰 이후 반영 작업, 현재 남은 작업, 기준 리뷰 재판정, 신규 개선 방안 14개, 권장 우선순위, 리뷰별 기여와 한계, 최종 상태 라벨을 포함한다.

따라서 두 신규 리뷰 자체는 큰 누락 없이 작성되어 있다. 다만 실제 파일 대조 결과, 두 문서 모두 `generated-artifact-index` drift의 폭을 "external-reports 18 vs 16" 중심으로 설명했고, **task-improvement observation directory 30 vs 저장본 24** drift까지는 명시하지 않았다. 이 항목은 본 보고서에서 새로 보강한다.

---

## 3. 실제 ZIP 및 파일 구조 대조

| 항목 | 실제 값 |
|---|---:|
| SHA-256 | `b33fed4266d8c25ca0acd2d4bbd84603cddad5ec1c54fbfdef644a2dad3465e5` |
| ZIP size | 191,236,219 bytes |
| ZIP entries | 1,665 |
| files | 1,583 |
| directories | 82 |
| uncompressed bytes | 240,559,534 |
| non-ASCII entry count | 334 |
| max UTF-8 path component bytes | 167 |
| CRC check | `None` = 오류 없음 |

두 신규 리뷰가 전제한 SHA와 실제 업로드 ZIP SHA는 일치한다. 파일 수 1,583개, non-ASCII entry 334건도 신규 리뷰의 수치와 일치한다. 이는 raw registry의 C-locale/UTF-8 분기 해석을 뒷받침한다. non-ASCII entry가 334건으로 많기 때문에, 경로 인코딩·추출 로케일·파일 시스템 호환성은 release packaging 계약의 일부로 다뤄야 한다.

### 3.1 실제 inventory와 저장 index 비교

| 항목 | 실제 파일 시스템 | 저장된 `generated-artifact-index.json` | live 재생성 결과 | 판정 |
|---|---:|---:|---:|---|
| `ops_reports_root_file_count` | 20 | 20 | 20 | 일치 |
| `task_improvement_observation_count` | 30 | 24 | 30 | **저장본 stale** |
| `external_reports_root_file_count` | 18 | 16 | 18 | **저장본 stale** |
| `external_reports_archive_file_count` | 19 기준 | 19 | 19 | 일치 |
| `run_directory_count` | 11 | 11 | 11 | 일치 |
| `run_archive_directory_count` | 1 | 1 | 1 | 일치 |
| `canonical_report_count` | script 산출 | 30 | 29 | 정책 재분류 필요 |
| `archive_candidate_count` | script 산출 | 17 | 20 | 정책 재분류 필요 |

신규 리뷰 2건은 `external-reports` root 파일 수가 실제 18개인데 저장 index가 16개라고 지적했다. 이번 실제 파일 대조에서는 이 지적이 맞을 뿐 아니라, `ops/reports/task-improvement-observations/` 역시 실제 30개 directory인데 저장 index는 24개로 남아 있음을 추가 확인했다. 즉 generated index drift는 **외부 리뷰 파일 self-include 문제만이 아니라 2026-04-28 후속 task observation 6건까지 반영하지 못한 inventory freshness 문제**다.

| 대상 파일 | 실제 ZIP 존재 | 저장 index 포함 | live index 포함 |
|---|---:|---:|---:|
| `external-reports/llm_wiki_vnext_integrated_audit_report_20260428.md` | 예 | 아니오 | 예 |
| `external-reports/llm_wiki_vnext_dual_review_improvement_report_20260428.md` | 예 | 아니오 | 예 |

**개선 포인트**: generated index guard는 `external_reports_root_file_count`만 비교하면 부족하다. task observation count, canonical/archive candidate 분류, 기준 리뷰 파일 포함 여부까지 함께 검사해야 한다.

---

## 4. 핵심 상태 재판정

### 4.1 Release readiness

두 신규 리뷰와 실제 파일 대조를 종합하면 release-ready가 아니다. 이유는 네 가지다.

1. stable artifact debt가 여전히 `71/71/13`이다.
2. learning readiness가 `learning_uncertain`이며 실제 learning evidence가 부족하다.
3. raw registry는 UTF-8 추출본에서는 pass지만 C-locale 추출 환경에서 fail이 보고되어 환경 독립성이 없다.
4. `make fast-smoke`가 stale pytest node id로 실패한다.

### 4.2 Raw registry

직접 재실행한 clean UTF-8 추출본의 `raw_registry_preflight` 결과는 pass였다.

```text
status=pass
entry_count=446
error_count=0
warning_count=0
```

| 관점 | 판정 |
|---|---|
| UTF-8/Python 안전 추출본 | pass |
| C-locale/escaped filename 추출본 | 기존 리뷰 A/B 기준 fail 46 errors / 46 warnings |
| repository 구조적 리스크 | 남아 있음 |
| release blocker 여부 | "모든 환경에서 즉시 blocker"는 아니지만, release archive 환경 독립성 관점에서는 P0에 가깝다 |

**개선 방향**: registry `storage_path`를 특정 추출 도구의 파일명 렌더링에 묶어두지 말고, canonical path + display path + path_aliases bridge를 분리한다. C-locale failure 3~5건을 축약 fixture로 고정해 "UTF-8에서만 통과하는" 회귀를 막는다.

### 4.3 Artifact freshness와 stable debt

| 지표 | ZIP 저장본 | clean live 재생성 | 판정 |
|---|---:|---:|---|
| `artifact_count` | 155 | 155 | 일치 |
| `missing_artifact_envelope_count` | 71 | 71 | 일치 |
| `unknown_currentness_artifact_count` | 71 | 71 | 일치 |
| `missing_schema_count` | 13 | 13 | 일치 |
| `stable_contract_debt_artifact_count` | 71 | 71 | 일치 |
| `stable_contract_debt_issue_count` | 155 | 155 | 일치 |
| `stale_artifact_count` | 34 | 91 | live에서 증가 |
| `mtime_sensitive_artifact_count` | 34 | 91 | live에서 증가 |
| `safe_to_backfill_artifact_count` | 121 | 64 | live에서 감소 |

stable debt 수치 `71/71/13`은 저장본과 live 재생성 모두에서 동일하다. 반면 stale/mtime-sensitive 계열은 실행 시점에 따라 `34`에서 `91`로 바뀐다. 따라서 두 신규 리뷰의 "stable-only required gate, mtime-sensitive advisory 분리" 제안은 실제 파일 대조로도 타당하다.

| 이슈 | 건수 | owner 분포 | 처리 방향 |
|---|---:|---|---|
| `missing_artifact_envelope` | 71 | `{'ops_reports': 7, 'runs': 64}` | envelope backfill / archive classification |
| `unknown_currentness` | 71 | ops_reports/runs | currentness metadata backfill |
| `missing_schema` | 13 | runs 13 | safe 10건 우선, sensitive 3건은 재생성/legacy 결정 |
| `missing_generated_at` | 27 | runs 27 | generated_at backfill 또는 legacy noncanonical |
| `generated_at_older_than_file_mtime` | 34 | ops_reports/runs | advisory 또는 current-tree fingerprint와 결합 |

`missing_schema` 13건 중 safe static tranche는 10건, history/mtime-sensitive tranche는 3건이다. 두 신규 리뷰의 "safe 10건 먼저 닫고 3건은 별도 판단" 제안은 실제 artifact record와 일치한다.

### 4.4 Learning readiness

| 항목 | 현재 값 | 목표/해석 |
|---|---:|---|
| `execution_readiness.status` | `pass` | 실행 queue는 열림 |
| `learning_readiness.status` | `learning_uncertain` | 아직 confirmed/ready 아님 |
| `likely_to_learn` | `false` | 실제 learning confidence 미달 |
| `attempts_considered` | 7 | 최소 10 미달 |
| `session_reports_considered` | 1 | 낮음 |
| `session_calibration_status` | `no_session_context` | 세션 context 부재 |
| `telemetry_coverage_ratio` | 0.0 | telemetry-backed evidence 없음 |
| `rework_count` | 5 | 높음 |
| `hold_moving_average` | 0.2857 | 주의 |
| `defect_escape_pair_count` | 3 | 높음 |

learning evidence hardening은 관측/계약 강화이지 readiness 해결이 아니다. acceptance criteria는 attempts ≥ 10, session context 존재, telemetry coverage > 0, rework/defect escape 감소로 잡아야 한다.

### 4.5 Release-smoke와 fast-smoke

| 항목 | 값 |
|---|---|
| `release-smoke status` | `pass` |
| `release-smoke profile` | `full` |
| `release-smoke generated_at` | `2026-04-28T05:04:20Z` |
| `release-smoke source_command` | `python -m ops.scripts.release_smoke --vault . --profile full` |
| `release-smoke source_tree_fingerprint` | `aff47b8cdb158a48a198ecbdc7746ccaafdc44e747aa2a4ec4aaddde6313867b` |

저장본 full release-smoke는 pass이며 command path sanitization도 적용되어 있다. 하지만 live full rerun 증적은 아직 충분하지 않고, fast/full profile report가 하나의 파일을 공유하기 때문에 마지막 실행 profile을 덮어쓸 위험이 있다.

| 항목 | 값 |
|---|---|
| Makefile stale selector 존재 | `True` |
| 실제 test 함수 존재 | `True` |
| stale selector | `tests/test_release_smoke.py::ReleaseSmokeTest::test_build_smoke_commands_matches_release_gate_contract` |
| 실제 함수 | `tests/test_release_smoke.py::ReleaseSmokeTest::test_build_smoke_commands_match_release_gate_profiles` |
| 직접 실행 결과 | `make fast-smoke` rc=2, pytest error: not found |

이는 두 신규 리뷰가 지적한 신규 회귀가 현재 파일과 정확히 일치함을 의미한다. 이 결함은 raw registry보다 먼저 고쳐도 안전한 단일 파일 수준의 빠른 복구 대상이다.

### 4.6 Review archive

| 항목 | 값 |
|---|---|
| `status` | `pass` |
| `packed_file_count` | 387 |
| `generated_at` | `2026-04-28T03:41:42Z` |
| `source_tree_fingerprint` | `fe34bb3fc876ba5b3be6e650b36de00505721019139277e97749cf9e85bcc713` |

review archive canonicalization은 두 신규 리뷰의 판단처럼 완료된 후속 작업으로 보는 것이 타당하다. 단, generated index drift가 남아 있어 review archive와 generated index 사이의 provenance chain은 아직 완전히 닫히지 않았다.

---

## 5. 기존 리뷰 판단과의 대조

| 기존 판단 | 현재 대조 결과 |
|---|---|
| 이전 기준선 대비 실질 진전 | 유지. 후속 작업이 코드·테스트·문서·CI에 반영됨 |
| stable artifact debt `79/79/17` | 수치 업데이트 필요. 현재는 `71/71/13` |
| raw registry 46 mismatch P0 | 조건부 유지. C-locale에서는 재현된 것으로 보이나 UTF-8 clean extraction에서는 pass |
| learning readiness 미해결 | 유지. `learning_uncertain` |
| release-smoke full만 존재 | 폐기. fast/full profile 구조는 도입됨 |
| pytest 진입점 정리 필요 | 부분 완료. bare pytest unsupported contract는 명시됐으나 `make fast-smoke` selector는 stale |
| 현재 ZIP에서는 raw registry failure 미재현 | UTF-8 clean extraction 기준 유지 |
| raw registry는 복구보다 재현 프로토콜 고정이 먼저 | 유지. 단, C-locale real-failure fixture가 추가로 필요 |
| generated-artifact-index external report drift | 유지, 단 drift 범위가 task observation count까지 확장됨 |
| full unit/release rerun 증적 부족 | 유지. release-smoke-fast 재시도는 도구 자동 interrupt로 미확정 |

---

## 6. 남은 작업과 개선 방안

### P0 — 즉시 복구 / release confidence 차단

| ID | 작업 | 근거 | 완료 기준 |
|---|---|---|---|
| P0-1 | `make fast-smoke` stale node id 수정 | 현재 Makefile의 selector가 실제 테스트 함수명과 불일치 | `make fast-smoke` pass, static gate가 node id 실존성 검증 |
| P0-2 | generated-artifact-index 재생성 및 drift guard | external reports 18 vs 16, task observations 30 vs 24 | index summary가 실제 inventory와 일치, 두 기준 리뷰가 canonical/archive 정책에 따라 포함 |
| P0-3 | raw registry extraction matrix 고정 | UTF-8 pass / C-locale fail 발산 | UTF-8, Info-ZIP, C-locale 등 지원 환경 matrix에서 모두 pass 또는 명시적 unsupported fail |
| P0-4 | raw path canonicalizer + alias migrator | Unicode/escaped path mismatch 가능성 | `storage_path`, `display_path`, `path_aliases` 분리. 46건 실데이터 mismatch fixture 포함 |
| P0-5 | current-tree report freshness gate | 저장 report가 이후 tree 변경을 대표하지 못할 수 있음 | checked-in report의 source_tree_fingerprint가 현 tree와 불일치하면 stale로 분류 |

### P1 — 단기 필수

| ID | 작업 | 근거 | 완료 기준 |
|---|---|---|---|
| P1-1 | stable debt safe tranche 처리 | `71/71/13` 잔존 | missing_schema ≤ 3, missing envelope < 50 |
| P1-2 | ops_reports 7건 envelope/currentness 처리 | `ops/reports` canonical surface debt | ops_reports missing envelope 0 |
| P1-3 | learning readiness evidence 확보 | `learning_uncertain`, attempts 7, telemetry 0.0 | attempts ≥ 10, session context 연결, telemetry coverage > 0 |
| P1-4 | release-smoke profile별 report 분리 | 단일 report 덮어쓰기 위험 | `release-smoke-report-fast.json`, `release-smoke-report-full.json` 동시 보존 |
| P1-5 | raw registry preflight canonical artifact 추가 | 현재 stdout 중심 | `ops/reports/raw-registry-preflight-report.json` 생성 및 schema-backed |
| P1-6 | test execution summary artifact 도입 | timeout/interrupt/fail 구분 부족 | command, duration, rc, phase, termination_reason, collected_count 기록 |
| P1-7 | bare pytest unsupported UX 개선 | `ModuleNotFoundError`가 원인 설명 부족 | helper message 또는 README top-level 안내, guard test |

### P2 — 중기 구조 개선

| ID | 작업 | 근거 | 완료 기준 |
|---|---|---|---|
| P2-1 | archive hygiene gate | `.venv`, cache, egg-info 등 archive 혼입 방지 | release archive preflight가 ephemeral files 차단 |
| P2-2 | path budget monitor | non-ASCII 334건, max component 167 bytes | 200/240/255 byte threshold warning |
| P2-3 | review self-inclusion 정책 명문화 | 외부 리뷰가 checkpoint 내부에 포함되는 기준 불명확 | manifest에 inclusion policy와 index regeneration trigger 기록 |
| P2-4 | run log placeholder 정책 | 0-byte placeholder 15건 관리 | retention policy 또는 ignore rule 명문화 |
| P2-5 | release-smoke-full alias | fast/full naming 대칭성 부족 | Makefile/README/CI 용어 통일 |
| P2-6 | mtime-sensitive KPI 분리 UI | live regeneration에서 stale count가 실행 시점에 민감 | stable debt required, mtime-sensitive advisory로 분리 표시 |

---

## 7. 권장 실행 순서

1. **PR-1: `make fast-smoke` 복구** — stale selector를 현재 test node id로 변경하고 FAST_SMOKE_TESTS collect-only 검증을 추가한다.
2. **PR-2: generated artifact index 재생성 및 guard** — 실제 18 external reports, 30 task observations, canonical/archive membership을 반영한다.
3. **PR-3: raw registry environment matrix** — UTF-8 safe extraction, Info-ZIP UTF-8, C-locale escape extraction을 분리 실행하고 결과 artifact를 저장한다.
4. **PR-4: raw path canonicalizer / alias migration** — 실데이터 failure fixture를 고정하고 `storage_path`, `display_path`, `path_aliases`를 분리한다.
5. **PR-5: artifact debt safe tranche** — missing schema safe 10건과 ops_reports 7건을 먼저 처리한다.
6. **PR-6: learning readiness closure** — operator-approved bounded auto-improve run으로 attempts/session/telemetry evidence를 확보한다.
7. **PR-7: release-smoke report split 및 full rerun** — fast/full report를 별도 파일로 저장하고 latest tree fingerprint로 검증한다.
8. **PR-8: test-execution-summary 및 archive hygiene** — timeout/interruption/partial report를 구조화하고 cache/venv 혼입을 방지한다.

---

## 8. 새로 보강한 개선 포인트

### 8.1 generated index drift 범위 확대

기존 신규 리뷰들은 external reports 18 vs 16을 중심으로 drift를 설명했다. 실제 파일 대조에서는 `task_improvement_observation_count`도 30 vs 24로 어긋난다. 따라서 재생성 guard는 root inventory count, canonical/archive membership, source_tree_fingerprint, input_fingerprints 최신성을 함께 봐야 한다.

### 8.2 stored vs live artifact freshness 판정 언어 개선

`stable_contract_debt_*`는 저장본과 live가 일치하지만, `stale_artifact_count`와 `mtime_sensitive_artifact_count`는 live 재생성에서 34 → 91로 바뀐다. 보고서 UI는 이를 "악화"로만 표시하면 안 되며, `stored_snapshot_metric`과 `live_regeneration_metric`을 분리해야 한다.

### 8.3 release-smoke-fast 검증 증적의 runtime cap 명시

현재 대화 런타임에서는 60초 자동 interrupt가 발생했다. 따라서 장시간 gate는 "실패", "timeout", "tool-interrupted", "not-run"을 분리해야 한다. 이 요구는 test-execution-summary artifact의 필요성을 강화한다.

### 8.4 Makefile selector drift 방지 방식 구체화

단순히 Makefile 문자열을 검사하는 static test는 부족하다. `FAST_SMOKE_TESTS` 전체를 parse해 `python -m pytest --collect-only -q <node ids>`가 성공하는지 검증해야 한다. 이 테스트는 release-smoke test rename과 Makefile drift를 즉시 잡는다.

---

## 9. 최종 종합 판정

```text
snapshot_status                         = progressed_after_reviews_but_not_release_ready
zip_integrity_status                    = pass
raw_registry_status                     = pass_on_utf8_extract / fail_reported_on_c_locale_extract
artifact_contract_status                = improved_but_open_71_71_13
learning_readiness_status               = learning_uncertain
release_smoke_full_stored               = pass_sanitized
release_smoke_fast_live_in_this_run      = inconclusive_due_runtime_interrupt
make_fast_smoke_status                  = fail_stale_pytest_nodeid
generated_artifact_index_status         = stale_inventory_drift
generated_artifact_index_drift_scope     = external_reports_and_task_observations
overall_release_confidence              = not_release_ready
recommended_next_action                 = fix_fast_smoke -> refresh_index_guard -> raw_registry_matrix -> artifact_debt_tranche -> learning_evidence
```

**최종 한 줄 요약**: 두 신규 리뷰의 결론은 실제 파일 대조와 대부분 일치하며, 현재 스냅샷은 기준 리뷰 이후 확실히 진전됐지만 release-ready는 아니다. 즉시 처리할 작업은 `make fast-smoke` 복구와 `generated-artifact-index` 재생성/guard이며, 이번 대조에서 generated index drift가 외부 리뷰 누락뿐 아니라 task improvement observation count까지 포함하는 더 넓은 inventory freshness 문제임을 새로 확인했다.
