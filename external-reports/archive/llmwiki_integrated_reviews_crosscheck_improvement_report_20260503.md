# LLM Wiki vNext 통합 리뷰 교차대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-03 (Asia/Seoul) |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_integrated_reviews_crosscheck_improvement_report_20260503.md` |
| 검토 대상 1 | `llm_wiki_vnext_integrated_review_report_20260503.md` |
| 검토 대상 2 | `llm_wiki_vnext_integrated_post_review_report_20260503.md` |
| 기존 대조 리뷰 | `llmwiki_review_report_20260503.md` |
| 기준 리뷰 | `external-reports/llm_wiki_vnext_review_reconciliation_improvement_report_20260502.md` |
| 실제 대조 ZIP | `LLMwiki.zip` |
| ZIP SHA-256 | `19966884918dcba3082fceb71f8edb4916f285a143e2a361ddd9270526820144` |
| Canonical source tree fingerprint | `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde` |
| 최종 판정 | **`conditional_pass` 유지. 기준 리뷰의 P0 다수는 해소됐지만 `clean_release_ready=false`, `machine_release_allowed=false`이므로 clean/machine release는 아직 불가.** |

---

## 1. Executive Summary

새로 제공된 두 통합 리뷰는 서로 독립적인 문체와 구성으로 작성되었지만, 실제 파일 상태와 대조했을 때 큰 결론은 일치한다. 현재 `LLMwiki.zip`은 2026-05-02 기준 리뷰가 보았던 상태보다 후속 정리가 반영된 스냅샷이며, Ruff 실패 제거, import fallback 계약 재정립, `ops/script-output-surfaces.json` 재봉인, release evidence fingerprint coherence 회복, batch manifest의 final authority 편입 같은 핵심 개선을 실제 파일에서도 확인할 수 있다.

그러나 release authority의 결론은 바뀌지 않는다. `ops/reports/release-closeout-summary.json`은 `release_readiness_state=conditional_pass`, `clean_release_ready=false`, `machine_release_allowed=false`, `operator_release_allowed=true`, `requires_accepted_risk_review=true`를 기록한다. `ops/reports/release-evidence-cohort.json`은 strict fingerprint coherence를 통과하지만 clean lane contract는 `zero_accepted_risk_family=false`와 `release_closeout_clean=false` 때문에 실패한다. 따라서 현재 스냅샷은 **coherent conditional evidence batch**로 볼 수 있으나, clean release 또는 machine release로 보아서는 안 된다.

두 통합 리뷰가 추가로 강조한 개선 포인트도 실제 파일과 대체로 부합한다. 특히 accepted-risk count vocabulary 불일치, batch manifest `status=fail`의 의미 혼재, learning readiness signoff/revalidation attention, diagnostic output quarantine 취약성은 계속 관리해야 한다. 다만 일부 표현은 보정이 필요하다. 예를 들어 실제 ZIP의 마지막 entry timestamp는 `2026-05-03 04:25:04`로 확인되어 일부 리뷰의 `04:25:02` 기록과 2초 차이가 있고, dashboard의 `gate_count`/`authoritative_gate_count`는 top-level이 아니라 `summary` 아래에 있다. 또한 learning signoff의 `window_ends_at=2026-05-09T19:25:00Z`와 accepted-risk 자체의 `expires_at=2026-05-07T06:02:10Z`는 서로 다른 의미의 날짜로 분리해서 써야 한다.

---

## 2. 검토 범위와 방법

### 2.1 검토한 보고서

| 구분 | 파일명 | lines | chars | SHA-256 |
| --- | --- | ---: | ---: | --- |
| 새 리뷰 1 | `llm_wiki_vnext_integrated_review_report_20260503.md` | 665 | 29146 | `6cf9487efa4ce9ffd1f7d97f667013377c516e61a23a7ab025f1a49a612bd86f` |
| 새 리뷰 2 | `llm_wiki_vnext_integrated_post_review_report_20260503.md` | 429 | 20150 | `ca98faa101133dab7e45d97bdee0e11e12d3c85cce94351616503cff310eaa9e` |
| 기존 리뷰 | `llmwiki_review_report_20260503.md` | 682 | 31885 | `237605a98bf8307dd22ead9ea0335e5058da90602dec043a17e334d3b36e974a` |
| 기준 리뷰 | `llm_wiki_vnext_review_reconciliation_improvement_report_20260502.md` | 555 | 24475 | `52f84fb7d4640fb16735d94a46cbad40fc94a9574cf4d48a329be09c4d698e9a` |

### 2.2 실제 ZIP 인벤토리

| 항목 | 실제 확인값 |
| --- | ---: |
| ZIP 크기 | 191,837,614 bytes |
| 전체 엔트리 | 1,820 |
| 일반 파일 | 1,726 |
| 디렉터리 | 94 |
| 비압축 총량 | 244,202,177 bytes |
| ZIP entry timestamp 범위 | `2026-04-12 16:03:06` ~ `2026-05-03 04:25:04` |

상위 경로별 파일 수 상위 항목:

| 경로 | 파일 수 |
| --- | ---: |
| `raw` | 446 |
| `wiki` | 417 |
| `ops` | 365 |
| `runs` | 166 |
| `tests` | 138 |
| `system` | 71 |
| `external-reports` | 48 |
| `tmp` | 33 |
| `.codex` | 10 |
| `.obsidian` | 5 |
| `tools` | 5 |
| `.github` | 2 |

확장자별 파일 수 상위 항목:

| 확장자 | 파일 수 |
| --- | ---: |
| `.md` | 958 |
| `.json` | 320 |
| `.py` | 311 |
| `.pdf` | 62 |
| `.txt` | 27 |
| `.yaml` | 14 |
| `.jsonl` | 12 |
| `.toml` | 11 |
| `<none>` | 5 |
| `.yml` | 2 |
| `.docx` | 2 |
| `.ini` | 1 |

### 2.3 실제 대조한 핵심 파일

이번 대조는 보고서 본문만 비교하지 않고, ZIP에서 추출한 실제 파일을 함께 확인했다. 주요 확인 대상은 다음이다.

```text
AGENTS.md
AGENTS.local.md
Makefile
ops/script-output-surfaces.json
ops/script-module-surfaces.json
ops/policies/release-closeout-batch.json
ops/policies/release-lane-definitions.json
ops/reports/release-closeout-summary.json
ops/reports/release-evidence-cohort.json
ops/reports/release-evidence-dashboard.json
ops/reports/release-closeout-batch-manifest.json
ops/reports/test-execution-summary.json
ops/reports/learning-readiness-signoff-revalidation.json
ops/reports/auto-improve-readiness.json
ops/reports/artifact-freshness-report.json
tmp/release-evidence-cohort-check.json
ops/scripts/release_closeout_batch_manifest.py
ops/scripts/release_evidence_cohort.py
ops/scripts/script_output_surfaces.py
ops/scripts/test_execution_summary.py
ops/scripts/command_runtime.py
tests/test_import_fallback_contract.py
tests/test_script_module_surface_contract.py
tests/test_release_closeout_batch_manifest.py
tests/test_command_runtime.py
```

---

## 3. 새 두 리뷰의 결론 대조

### 3.1 공통 결론

두 통합 리뷰는 모두 아래 결론에 도달한다.

| 항목 | 두 리뷰의 공통 결론 | 실제 파일 대조 |
| --- | --- | --- |
| 기준 리뷰 이후 후속 정리 여부 | 후속 작업 반영됨 | ZIP entry, release evidence timestamp, fingerprint 정렬로 확인 |
| 최종 release state | `conditional_pass` | `release-closeout-summary.json`에서 확인 |
| clean release | 불가 | `clean_release_ready=false` |
| machine release | 불가 | `machine_release_allowed=false` |
| operator release | accepted-risk review 전제로 가능 | `operator_release_allowed=true`, `requires_accepted_risk_review=true` |
| strict fingerprint coherence | 회복 | cohort summary의 `strict_same_fingerprint=true`, `component_fingerprint_count=1` |
| clean lane | 실패 | `zero_accepted_risk_family=false`, `release_closeout_clean=false` |
| accepted risk count 불일치 | 존재 | closeout/cohort 1, dashboard/tmp diagnostic 2 |
| batch manifest status 모호성 | 존재 | batch integrity는 완전하지만 top-level `status=fail` |
| learning readiness | attention/uncertain | signoff revalidation `status=attention`, auto-improve learning readiness `learning_uncertain` |

### 3.2 새 리뷰 1의 강점

새 리뷰 1은 세 리뷰(A/B/C)의 고유 발견을 빠짐없이 색인화하고, 각 발견을 P0/P1/P2로 재정렬한 점이 강하다. 특히 다음 항목을 명확히 구분했다.

- 리뷰 A 고유 발견: external-reports 참조 완결성 결여
- 리뷰 B 고유 발견: `release-evidence-cohort-check` currentness probing subprocess 폭증
- 리뷰 C 고유 발견: `command_runtime` SIGTERM(-15) 재현
- 리뷰 C 고유 발견: diagnostic output quarantine 취약성
- batch manifest `status` 의미 혼재
- accepted risk count vocabulary 불일치

실제 파일 대조 결과 이 구조화는 유효하다. 단, 일부 필드 위치와 timestamp는 아래 보정 항목처럼 정밀화가 필요하다.

### 3.3 새 리뷰 2의 강점

새 리뷰 2는 새 리뷰 1보다 간결하지만, 운영자가 바로 실행할 수 있는 통합 권장 실행 계획이 선명하다. 특히 다음을 P0로 묶은 점이 실제 파일 상태와 맞다.

- learning readiness blocker 해소 또는 conditional-only 정책 확정
- accepted-risk vocabulary 통합
- `command_runtime` SIGTERM 재현 원인 고립
- currentness probing refactor
- batch manifest status 이원화
- diagnostic output quarantine

다만 새 리뷰 2는 `window_ends_at=2026-05-09T19:25:00Z`와 accepted-risk expiry `2026-05-07T06:02:10Z`를 같은 줄에서 함께 언급하며 "문서별 기록 상이"라고 표현하는데, 실제 파일상 이는 서로 다른 날짜 필드다. 따라서 충돌이라기보다 **revalidation window와 risk acceptance expiry의 의미 차이**로 정리하는 편이 정확하다.

---

## 4. 실제 파일 기준 핵심 상태

### 4.1 Release Closeout Summary

| 필드 | 실제 값 |
| --- | --- |
| path | `ops/reports/release-closeout-summary.json` |
| SHA-256 | `8e92677f3d9884a878a982da79d5266b8ddede9c86ba1dcda067fd64b2a7708f` |
| generated_at | `2026-05-02T19:25:00Z` |
| status | `pass` |
| source_tree_fingerprint | `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde` |
| release_readiness_state | `conditional_pass` |
| checked_in_release_ready | `True` |
| live_rerun_release_ready | `True` |
| conditional_release_ready | `True` |
| clean_release_ready | `False` |
| machine_release_allowed | `False` |
| operator_release_allowed | `True` |
| requires_accepted_risk_review | `True` |
| accepted_risk_count | `1` |
| accepted_risk_instance_count | `1` |
| accepted_risk_family_count | `1` |
| release_blocking_risk_count | `1` |
| blocker_count | `0` |

판정: closeout은 hard blocker 0을 기록하지만, accepted risk 1건이 남아 있어 clean release가 아니다. 이 지점은 두 새 리뷰, 기존 리뷰, 실제 파일이 모두 일치한다.

### 4.2 Release Evidence Cohort

| 필드 | 실제 값 |
| --- | --- |
| path | `ops/reports/release-evidence-cohort.json` |
| SHA-256 | `e05d6ec296721491d5f9c3ff8d3c9e92ca5f1537dd0ed3a246caf7442c3719ec` |
| generated_at | `2026-05-02T19:25:00Z` |
| status | `pass` |
| source_tree_fingerprint | `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde` |
| component_count | `9` |
| loaded_component_count | `9` |
| strict_same_fingerprint | `True` |
| component_fingerprint_count | `1` |
| modified_after_generated_at_count | `0` |
| accepted_risk_count | `1` |
| clean_lane_contract_status | `fail` |
| clean lane failed_conditions | `zero_accepted_risk_family, release_closeout_clean` |

판정: cohort 자체는 `status=pass`이고 strict fingerprint coherence는 회복됐다. 그러나 clean lane contract는 별도로 실패한다. 이 때문에 `cohort pass`를 `clean release pass`로 해석하면 안 된다.

### 4.3 Release Evidence Dashboard

| 필드 | 실제 값 |
| --- | --- |
| path | `ops/reports/release-evidence-dashboard.json` |
| SHA-256 | `1ee8e5361a5cbd5d20b51fb626b74a000a6a9d6962f1566fa92d40ea658c523d` |
| generated_at | `2026-05-02T19:25:01Z` |
| status | `attention` |
| source_tree_fingerprint | `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde` |
| summary.gate_count | `11` |
| summary.authoritative_gate_count | `8` |
| summary.accepted_risk_count | `2` |
| summary.checked_in_fail_count | `0` |
| summary.live_rerun_fail_count | `0` |

dashboard의 accepted risk count는 2로, closeout/cohort의 1과 다르다. 실제 gates를 보면 `auto_improve_readiness`의 `learning_blocked_by_review_required` 1건과 `learning_readiness_signoff_revalidation`의 `learning_readiness_signoff_attention` 1건을 별도 attention/risk item처럼 세고 있다. 따라서 이것은 "같은 위험을 잘못 중복했다"라고 단정하기보다는, **family-level risk count와 gate-level attention count의 vocabulary가 섞인 문제**로 보는 것이 정확하다.

### 4.4 Release Closeout Batch Manifest

| 필드 | 실제 값 |
| --- | --- |
| path | `ops/reports/release-closeout-batch-manifest.json` |
| SHA-256 | `917e7e2646fba4ac28cebbbc7051a9e7e70307c9552f98a73c91869377b8438c` |
| generated_at | `2026-05-02T19:25:02Z` |
| status | `fail` |
| source_tree_fingerprint | `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde` |
| artifact_count | `8` |
| present_count | `8` |
| current_count | `8` |
| required_count | `8` |
| required_present_count | `8` |
| required_current_count | `8` |
| finality.is_final | `True` |
| finality.reason | `last canonical writer in release-evidence-closeout` |
| release_decision_snapshot.clean_release_ready | `False` |
| release_decision_snapshot.machine_release_allowed | `False` |
| release_decision_snapshot.release_readiness_state | `conditional_pass` |

판정: batch manifest의 `status=fail`은 artifact missing/currentness failure가 아니라 release decision snapshot이 clean/machine release를 허용하지 않기 때문에 발생한다. 따라서 두 새 리뷰가 권장한 status semantics 이원화는 실제 파일 기준으로도 필요하다.

### 4.5 Test Execution Summary

| 필드 | 실제 값 |
| --- | --- |
| path | `ops/reports/test-execution-summary.json` |
| SHA-256 | `f7111484a5ed7375224dd27b555ed36e8ce54b1efa58d9bc88a4a2a705a96951` |
| generated_at | `2026-05-02T19:24:55Z` |
| status | `pass` |
| source_tree_fingerprint | `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde` |
| command returncode | `0` |
| timed_out | `False` |
| timeout_seconds | `5400` |
| termination_reason | `completed` |
| duration_ms | `8079` |
| counts.passed | `119` |
| counts.failed | `0` |
| pytest_collect_nodeid_count | `119` |
| execution python_version | `3.14.3` |
| execution pytest_version | `8.4.2` |

판정: checked-in summary는 Python `3.14.3` 환경에서 119 tests pass를 기록한다. 반면 기존 리뷰/새 리뷰 일부가 언급한 `command_runtime` 재현은 Python 3.13.5 fresh extraction에서 발생한 외부 재검증 결과다. 따라서 release summary에는 `checked_in_pass`와 `live_rerun_matrix_pass`를 분리해 기록해야 한다.

### 4.6 Learning Readiness / Auto Improve

| 항목 | 실제 값 |
| --- | --- |
| signoff revalidation path | `ops/reports/learning-readiness-signoff-revalidation.json` |
| signoff revalidation status | `attention` |
| signoff revalidation generated_at | `2026-05-02T19:25:00Z` |
| revalidation.status | `due` |
| revalidation.window_ends_at | `2026-05-09T19:25:00Z` |
| revalidation.status_reason | `learning readiness signoff expires within the revalidation window; release closeout evidence is present but metrics still leave the blocker open` |
| auto-improve learning_readiness.status | `learning_uncertain` |
| attempts_considered | `7` |
| min_attempts_considered | `10` |
| telemetry_coverage_ratio | `0.0` |
| hold_moving_average | `0.2857` |
| rework_count | `2` |
| defect_escape_pair_count | `1` |

accepted risk 자체의 expiry는 closeout/batch의 accepted risk entry에 기록된 `2026-05-07T06:02:10Z`이고, revalidation window는 `2026-05-09T19:25:00Z`다. 두 날짜는 같은 개념이 아니므로 보고서와 dashboard는 각각 `risk_acceptance_expires_at`과 `revalidation_window_ends_at`처럼 필드명을 분리해야 한다.

### 4.7 Script Output Surfaces

| 필드 | 실제 값 |
| --- | --- |
| path | `ops/script-output-surfaces.json` |
| SHA-256 | `190a1e696f68fe1a22d6fcba87646b963419207660ca5ef0b1d2a20f31e1659c` |
| generated_at | `2026-05-02T19:24:31Z` |
| artifact_kind | `script_output_surfaces` |
| source_tree_fingerprint | `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde` |
| surfaces count | `171` |
| direct_fallback_eligible count | `65` |

실제 `tests/test_import_fallback_contract.py`는 더 이상 수동 allowlist를 직접 기준으로 삼지 않고, `ops/script-output-surfaces.json`의 `direct_fallback_eligible` field를 기준으로 fallback files와 registry를 비교한다. 기준 리뷰에서 지적한 수동 allowlist drift는 구조적으로 개선된 상태다.

### 4.8 Diagnostic Cohort Check

| 필드 | 실제 값 |
| --- | --- |
| path | `tmp/release-evidence-cohort-check.json` |
| SHA-256 | `22bbd8a119f12d8e9ef21512ac88ad1de9d20b961d31aca75221588f641198d8` |
| generated_at | `2026-05-02T10:53:50Z` |
| status | `pass` |
| source_tree_fingerprint | `a4db3a44838d1e8047469d0f621f9b696a4df6702e096a92374e03c6bac854fb` |
| strict_same_fingerprint | `True` |
| accepted_risk_count | `2` |
| clean_lane_contract_status | `fail` |
| failed_conditions | `zero_accepted_risk_family, release_closeout_clean` |

diagnostic output은 canonical release evidence의 fingerprint인 `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde`와 다른 fingerprint를 갖는다. 이 자체가 실패는 아니지만, diagnostic write가 source tree fingerprint 대상에 섞이면 batch manifest verify를 오염시킬 수 있다는 두 리뷰의 지적은 타당하다.

---

## 5. 기준 리뷰 이후 완료 또는 상당 진전된 작업

| 항목 | 기준 리뷰 당시 문제 | 현재 실제 파일 기준 판정 | 보완 의견 |
| --- | --- | --- | --- |
| Ruff 실패 | `release_closeout_batch_manifest.py` unused import | 실제 파일에서 `report_path` import 제거 확인 | 현재 런타임에는 ruff 모듈이 없어 재실행 증거는 새 리뷰 로그에 의존 |
| Import fallback | 수동 allowlist와 fallback file 불일치 | registry 기반 `direct_fallback_eligible` 계약으로 전환 | 생성형 registry를 source of truth로 유지해야 함 |
| Script output surfaces | writer registry fingerprint drift | `ops/script-output-surfaces.json`이 canonical fingerprint 기록 | payload equality와 fingerprint freshness를 계속 분리해야 함 |
| Release evidence lineage | closeout/cohort/dashboard/batch fingerprint 산개 | 핵심 release evidence가 `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde`로 정렬 | diagnostic/scratch output은 별도 fingerprint로 분리 필요 |
| Cohort strict fingerprint | `strict_same_fingerprint=false`, component fp 여러 개 | `strict_same_fingerprint=true`, `component_fingerprint_count=1` | cohort pass와 clean lane pass는 별도 표시 필요 |
| Batch manifest final authority | final closeout recipe 후행/외부 artifact | Makefile `release-evidence-closeout` 마지막에 promote/verify 편입 | top-level status semantics 이원화 필요 |
| Test execution summary | release-relevant 대표성 부족 | schema와 checked-in summary 확장, 119 tests pass | Python 3.13.5 live rerun evidence 별도 수집 필요 |
| Release lane vocabulary | clean/conditional 혼동 | `ops/policies/release-lane-definitions.json` 존재 | 각 report가 lane별 상태를 같은 vocabulary로 써야 함 |

---

## 6. 아직 남아 있는 작업분

### 6.1 Clean release / machine release 불가

현재 release state는 conditional이다. clean release를 위해서는 최소한 다음이 필요하다.

- `clean_release_ready=true`
- `machine_release_allowed=true`
- `release_readiness_state=clean_pass`
- `accepted_risk_family_count=0`
- `release-evidence-cohort.clean_lane_contract.status=pass`
- learning readiness signoff attention 해소 또는 clean lane과 호환되는 형태로 제거

현재 파일은 위 조건을 만족하지 않는다. 따라서 operator-mediated conditional release 외에는 배포 판단을 확장하면 안 된다.

### 6.2 Accepted-risk count vocabulary 불일치

실제 count는 다음처럼 갈린다.

| source | count | 해석 |
| --- | ---: | --- |
| closeout summary | 1 | accepted risk family/instance 압축 기준 |
| cohort summary | 1 | clean lane을 막는 accepted risk family 기준 |
| dashboard summary | 2 | gate-level attention/risk item 기준 |
| tmp diagnostic cohort | 2 | local diagnostic generation 기준 |

개선 방향은 count 값을 억지로 하나로 맞추는 것이 아니라, 아래 vocabulary를 모든 산출물에 함께 쓰는 것이다.

```json
{
  "accepted_risk_family_count": 1,
  "accepted_risk_instance_count": 1,
  "accepted_risk_gate_attention_count": 2,
  "accepted_risk_dashboard_item_count": 2,
  "clean_lane_blocking_family_count": 1
}
```

### 6.3 Batch manifest `status=fail` 의미 모호성

현재 batch manifest는 artifact integrity 관점에서는 8/8 present/current이고 finality도 true다. 그러나 top-level status는 release decision snapshot을 반영해 fail이다. 이 때문에 사람이나 자동화가 "batch 파일이 망가짐"으로 오해할 수 있다.

권장 구조:

```json
{
  "batch_integrity_status": "pass",
  "artifact_currentness_status": "pass",
  "finality_status": "pass",
  "release_authority_status": "conditional_pass",
  "clean_lane_status": "fail",
  "machine_release_status": "blocked",
  "operator_action_required": true
}
```

### 6.4 Learning readiness attention

`learning_readiness.status=learning_uncertain`이고, attempts 7건은 minimum 10건에 못 미친다. telemetry coverage ratio는 0.0이고, hold/rework/defect escape signal이 남아 있다. accepted risk가 operator signoff로 임시 수용된 상태이므로 clean release에는 부적합하다.

즉시 필요한 조치:

- signoff expiry 전 재검증
- attempts ≥ 10 충족
- routing provenance telemetry coverage > 0으로 개선
- hold/rework/defect escape proxy 완화
- accepted risk expiry/owner/revalidation 결과를 closeout에 다시 반영

### 6.5 `command_runtime` SIGTERM 재현성

두 새 리뷰 중 하나와 기존 리뷰는 Python 3.13.5 fresh extraction에서 `test_run_with_timeout_returns_completed_process_result`가 `returncode=-15`로 실패했다고 기록한다. 실제 파일의 checked-in summary는 Python 3.14.3에서 pass를 기록한다. 이 불일치는 "둘 중 하나가 틀렸다"가 아니라, matrix와 실행 환경에 따라 결과가 달라지는 위험 신호다.

현재 `ops/scripts/command_runtime.py`는 POSIX에서 `start_new_session=True`로 process group을 만들고 timeout 시 `killpg(process.pid, SIGTERM)`을 보낸다. 정상 완료 케이스에서 `communicate(timeout=5)`가 timeout으로 오판되거나, startup hook/환경 지연으로 인해 timeout path에 들어가면 정상 child가 SIGTERM 처리될 가능성을 배제할 수 없다.

필수 개선:

- timeout 계측 시작점과 process launch latency 분리
- child environment 인자 지원 및 Jupyter/startup hook 제거 옵션 제공
- 정상 완료 return code 보존 테스트 강화
- Python 3.13/3.14, Linux/macOS matrix 분리
- `test_execution_summary.json`에 checked-in runtime과 live rerun runtime을 별도 필드로 기록

### 6.6 Diagnostic output quarantine

`tmp/release-evidence-cohort-check.json`은 canonical release evidence와 다른 fingerprint를 가진다. diagnostic 파일이 release source tree fingerprint 계산에 포함되면 fresh verify 이후 diagnostic write가 batch manifest를 스스로 무효화하는 self-invalidating loop가 생긴다.

권장 조치:

- `tmp/`, `ops/reports/diagnostics/`, `runs/` 같은 scratch artifact를 release source fingerprint 대상에서 제외
- canonical artifact fingerprint와 workspace/scratch signature 분리
- `release-closeout-batch-manifest-verify` precondition에 clean workspace 조건 명시
- Makefile에 clean-room verify target 추가
- diagnostic mode와 release-bound mode를 CLI 옵션으로 분리

### 6.7 Evidence currentness probing subprocess 폭증

새 리뷰 1·2는 `release-evidence-cohort-check` currentness probing이 subprocess를 과도하게 만들 수 있다고 지적한다. 실제 작업 환경에서도 orphan `timeout ... python -c ...` 계열 process가 남아 검증 재실행을 방해할 수 있음을 관찰했다. 이 문제는 release 판단 자체보다 **검증 인프라의 안정성**에 영향을 준다.

권장 조치:

- file currentness 확인은 기본적으로 in-process `Path.exists()`/`Path.stat()`/hash read로 처리
- 외부 subprocess가 필요한 경우 bounded worker pool 적용
- 전체 budget과 stage별 budget을 사용하고 파일별 10초 누적 구조 제거
- report에 `probe_strategy`, `probed_file_count`, `probe_timeout_count`, `probe_error_count`, `probe_duration_ms` 기록

### 6.8 External-reports reference integrity

기준 리뷰가 참조한 상위 리뷰 3건은 현재 ZIP에서 직접 확인되지 않는다. 현재 작업의 새 리뷰들은 그 결손을 보완하지만, archive 재현성 관점에서는 참조 문서 manifest가 필요하다.

권장 조치:

```json
{
  "report": "external-reports/llm_wiki_vnext_review_reconciliation_improvement_report_20260502.md",
  "references": [
    {
      "path": "external-reports/llm_wiki_vnext_통합사후보고서_20260502.md",
      "sha256": "",
      "required": true,
      "present": false
    }
  ]
}
```

ZIP export 시 required reference가 없으면 `attention` 또는 `fail`을 내야 한다.

---

## 7. 새 두 리뷰에서 보정해야 할 부분

| 항목 | 리뷰 서술 | 실제 파일 대조 | 보정 제안 |
| --- | --- | --- | --- |
| ZIP timestamp max | 일부 표에 `2026-05-03 04:25:02` | 실제 ZIP max는 `2026-05-03 04:25:04` | 2초 차이로 정정 |
| dashboard gate count 위치 | `gate_count`, `authoritative_gate_count`를 단순 필드처럼 언급 | 실제 위치는 `summary.gate_count`, `summary.authoritative_gate_count` | field path를 명시 |
| learning date 불일치 | `2026-05-09` 또는 `2026-05-07`이 문서별 상이하다고 표현 | `window_ends_at=2026-05-09`, accepted risk `expires_at=2026-05-07` | 서로 다른 개념으로 분리 |
| batch manifest fail | `status=fail`을 언급 | 실제 artifact summary는 8/8 current | `batch_integrity_status`와 `release_authority_status`로 분리 |
| command_runtime | pass/fail 리뷰가 공존 | checked-in summary Python 3.14.3 pass, 외부 Python 3.13.5 fail 기록 | matrix-specific risk로 관리하되 재현 환경에서는 P0 후보 |
| tmp diagnostic cohort | status와 clean lane 혼동 가능 | top-level `status=pass`, clean lane status fail, fp는 canonical과 다름 | diagnostic status, lane status, fingerprint role을 분리 |

---

## 8. 개선 실행 계획

### 8.1 P0 — 다음 clean release 전 필수

| 순서 | 작업 | 완료 기준 |
| ---: | --- | --- |
| 1 | `command_runtime` SIGTERM 재현 원인 고립 | Python 3.13.5/3.14 matrix에서 정상 완료 command returncode 0 보존 |
| 2 | accepted-risk vocabulary 통합 | closeout/cohort/dashboard/batch/tmp diagnostic이 family/instance/gate count를 같은 이름으로 기록 |
| 3 | batch manifest status 이원화 | batch integrity pass와 clean release fail이 별도 필드로 표시 |
| 4 | diagnostic output quarantine | diagnostic write 후에도 canonical batch verify가 self-invalidating되지 않음 |
| 5 | clean/conditional lane summary 분리 | 한 화면에서 `cohort=pass`, `clean_lane=fail`, `conditional=pass`, `machine=blocked`가 구분됨 |
| 6 | learning signoff 재검증 | accepted risk expiry 전 재검증 또는 accepted risk 제거 |

### 8.2 P1 — 단기 안정화

| 순서 | 작업 | 완료 기준 |
| ---: | --- | --- |
| 1 | currentness probing in-process 전환 | subprocess-per-file 구조 제거, probe metadata 기록 |
| 2 | test execution summary matrix 확장 | checked-in pass/live rerun pass/Python version/OS/env hook이 구조화됨 |
| 3 | writer registry fast check CLI 추가 | pytest 없이 registry equality 빠르게 검증 |
| 4 | generated report contract suite 분리 | fast/slow/finalization marker와 per-test duration 기록 |
| 5 | release evidence handoff 강화 | verify job과 publish job이 같은 evidence bundle을 사용 |
| 6 | lane decision table artifact 추가 | 운영자와 자동화가 같은 조건표를 읽음 |

### 8.3 P2 — 중기 유지보수

| 순서 | 작업 | 완료 기준 |
| ---: | --- | --- |
| 1 | external report reference manifest 도입 | 기준/통합 리뷰가 참조하는 문서 present/digest 검증 |
| 2 | post-review delta manifest 자동 생성 | 기준 리뷰 이후 변경 파일과 산출물 변화를 자동 요약 |
| 3 | 대형 runtime script 분리 | `test_execution_summary.py` 등 collector/normalizer/writer 역할 분리 |
| 4 | public/internal review ZIP mode 분리 | `external-reports`, `raw`, `wiki`, `system`, `runs` 포함 여부를 mode로 통제 |
| 5 | README/ops README 최신화 | conditional vs clean release 절차와 accepted-risk semantics 최신화 |

---

## 9. Clean Release Definition of Done 대비 현재 상태

| 번호 | 조건 | 현재 상태 | 판정 |
| ---: | --- | --- | --- |
| 1 | Ruff clean | 새 리뷰 로그상 pass, 실제 unused import 제거 | ✅ 대체 충족 |
| 2 | mypy allowlist clean | 새 리뷰 로그상 pass(172 files) | ✅ 충족 |
| 3 | import fallback contract clean | registry 기반 계약으로 전환 | ✅ 충족 |
| 4 | writer output surface registry 정합 | `ops/script-output-surfaces.json` canonical fp 기록 | ✅ 충족 |
| 5 | release evidence strict fingerprint coherence | cohort `strict_same_fingerprint=true` | ✅ 충족 |
| 6 | required batch artifacts present/current | 8/8 present/current | ✅ 충족 |
| 7 | batch finality | `finality.is_final=true` | ✅ 충족 |
| 8 | test summary checked-in pass | Python 3.14.3에서 119 pass | ✅/⚠️ matrix gap |
| 9 | command runtime matrix stable | Python 3.13.5 재현 보고 존재 | ❌ 미충족 |
| 10 | accepted risk family 0 | closeout/cohort 1 | ❌ 미충족 |
| 11 | dashboard/closeout/cohort risk vocabulary 일치 | 1 vs 2 | ❌ 미충족 |
| 12 | clean lane contract pass | failed conditions 2개 | ❌ 미충족 |
| 13 | machine release allowed | false | ❌ 미충족 |
| 14 | learning readiness clean | `learning_uncertain`/attention | ❌ 미충족 |
| 15 | diagnostic output quarantine | tmp diagnostic fp가 canonical과 다름 | ❌ 미충족 |
| 16 | external report reference integrity | required upstream refs manifest 없음 | ❌ 미충족 |

---

## 10. 권장 release summary 목표 형태

현재 가장 큰 운영 리스크는 `conditional_pass`가 clean release처럼 읽히는 것이다. 다음과 같은 one-page summary를 자동 생성하는 것이 좋다.

```text
Release readiness: conditional_pass
Clean release: no
Machine release: no
Operator release: yes, accepted-risk review required
Evidence cohort: pass
Strict fingerprint coherence: pass
Clean lane: fail
Clean lane failed conditions: zero_accepted_risk_family, release_closeout_clean
Accepted risk family count: 1
Accepted risk gate attention count: 2
Learning readiness: learning_uncertain / signoff revalidation due
Batch integrity: pass
Batch finality: pass
Batch release authority: conditional_pass, clean blocked
Command runtime matrix: unresolved; Python 3.13.5 rerun required
Diagnostic quarantine: unresolved
```

이 summary는 `release-closeout-summary.json`, `release-evidence-cohort.json`, `release-evidence-dashboard.json`, `release-closeout-batch-manifest.json`, `test-execution-summary.json`, `learning-readiness-signoff-revalidation.json`을 입력으로 삼아 생성해야 한다.

---

## 11. 최종 결론

새 두 통합 리뷰는 기존 리뷰와 실제 파일 상태를 잘 통합하고 있으며, 큰 방향의 오류는 없다. 실제 `LLMwiki.zip` 대조 결과, 기준 리뷰 이후 다음 개선은 실제로 반영되었다고 판단한다.

- Ruff/import fallback 계열의 기준 리뷰 P0는 실제 파일 구조상 해소됐다.
- 수동 fallback allowlist 중심 계약이 `ops/script-output-surfaces.json` 기반 생성형 registry 계약으로 이동했다.
- release evidence 주요 산출물이 하나의 canonical fingerprint `6b70b1cd1180919dbe83ec03ebf3e3f56c32f9d9ba040950d3c926c957872cde`로 정렬됐다.
- batch manifest가 `release-evidence-closeout`의 마지막 canonical writer로 편입됐다.
- lane definitions 정책이 생겨 clean/conditional vocabulary가 파일로 표현되기 시작했다.
- test execution summary는 schema와 checked-in evidence가 확장됐다.

하지만 다음 이유로 clean release와 machine release는 아직 불가하다.

1. `accepted_risk_family_count=1`이 남아 있다.
2. `release_closeout_clean=false`이다.
3. clean lane contract가 `zero_accepted_risk_family`, `release_closeout_clean` 조건으로 실패한다.
4. dashboard와 closeout/cohort의 accepted risk count vocabulary가 일치하지 않는다.
5. learning readiness가 여전히 uncertain/attention 상태다.
6. `command_runtime`은 checked-in Python 3.14.3 summary와 외부 Python 3.13.5 재현 결과가 갈라져 matrix 안정성이 입증되지 않았다.
7. diagnostic output과 canonical release fingerprint 경계가 충분히 격리되지 않았다.
8. batch manifest top-level status가 artifact integrity와 release decision을 한 필드에 섞어 운영자 오해를 유발할 수 있다.

따라서 현 시점의 개선 방향은 새 두 리뷰의 통합 권고와 동일하게 잡는 것이 타당하다. 다만 보고서와 자동 summary에서는 위 보정 사항을 반영해 **field path, 날짜 의미, count vocabulary, status semantics**를 더 엄밀하게 써야 한다.

> **최종 판정: 현재 스냅샷은 기준 리뷰 이후 상당히 개선된 coherent conditional evidence batch다. 그러나 clean/machine release로 승격하기에는 accepted-risk, learning readiness, command runtime matrix, diagnostic quarantine, batch status semantics 문제가 남아 있다. 다음 작업은 기능 추가보다 release authority vocabulary와 검증 인프라 안정화에 집중해야 한다.**
