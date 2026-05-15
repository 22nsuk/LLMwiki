# LLMwiki 두 통합 리뷰 실제 파일 대조 기반 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-04 (Asia/Seoul) |
| 작성 언어 | 한국어 |
| 검토 대상 리뷰 1 | `llmwiki_integrated_review_report_20260504.md` |
| 검토 대상 리뷰 1 SHA-256 | `62977ba534207857feba662e8e9245e28b408c04687e49fb8093eb1eee16f2e3` |
| 검토 대상 리뷰 1 분량 | 904 lines |
| 검토 대상 리뷰 2 | `llmwiki_post_review_integrated_report_20260504.md` |
| 검토 대상 리뷰 2 SHA-256 | `e007c4b1ea64a2487378aa9ff9c365735b6a38deef237cc71d5463c01ffdf287` |
| 검토 대상 리뷰 2 분량 | 906 lines |
| 기존 후속 보고서 | `llmwiki_post_review_work_status_report_20260504.md` |
| 기존 후속 보고서 SHA-256 | `6b26de95ff836984aab7b422136410edc881bbacf2c3fddafa6604adf22ba6dd` |
| 기준 리뷰 | `external-reports/llmwiki_review_test_structure_improvement_report_20260504.md` |
| 기준 리뷰 SHA-256 | `ada802e0d44239bcf282b0b1ab2285fca1a10deeeb10239b1f019b693a8415af` |
| 기준 리뷰 분량 | 613 lines / 35,485 bytes |
| 실제 대조 ZIP | `LLMwiki(12).zip` |
| 실제 ZIP SHA-256 | `470475533932575a0e42dc5e770b005290ee94e5775f9faa7707fc4f196cf209` |
| 실제 ZIP entry 수 | 1,829 |
| 실제 추출 경로 | `/mnt/data/llmwiki_fresh` |
| 본 보고서 목적 | 두 통합 리뷰를 기준 리뷰·기존 후속 보고서·실제 ZIP 파일과 대조하여 확정 판정, 상충 정정, 잔여 작업, 신규 개선안을 재정리 |

---

## 1. 최종 판정 요약

두 통합 리뷰의 핵심 결론은 실제 `LLMwiki(12).zip`과 대체로 일치한다. 현재 패키지는 기준 리뷰 이후 self-check, batch manifest, test summary 대표성, operator summary, external report manifest, accepted-risk vocabulary, test lane 분리 등 주요 구조 개선을 상당 부분 반영했다. 그러나 현재 상태는 여전히 **sealed clean release**가 아니라 **sealed conditional package / conditional release evidence**다.

다만 두 리뷰에서 그대로 가져오면 안 되는 정정 사항이 있다. **현재 업로드된 실제 ZIP은 `LLMwiki(12).zip` 하나이며, 이 스냅샷에서는 `make release-closeout-batch-manifest-verify PYTHON=python3`가 통과했다.** 따라서 `source_tree_fingerprint` 불일치로 verify가 실패한다는 주장은 이 파일에서 재현된 결함이 아니라, 두 리뷰 중 일부가 언급한 `LLMwiki(13).zip` 또는 별도 작업본의 회귀 위험으로 분리해야 한다.

### 1.1 실제 파일 기준 상태표

| 축 | 실제 파일 기준 판정 | 근거 |
| --- | --- | --- |
| ZIP 식별 | 확정 | SHA `470475533932575a…`, entry 1,829 |
| 기준 리뷰 존재 | 확정 | `ada802e0d44239bc…`, 613 lines |
| batch artifact digest sealing | 통과 | manifest artifacts 10/10 존재 및 digest 일치, `release-closeout-batch-manifest-verify` 통과 |
| batch manifest semantic status | conditional/fail 혼재 | `status=fail`, `semantic_release_status=conditional_pass`, `sealed_release_status=sealed_conditional_pass` |
| release authority | conditional | `release_authority_status=conditional_pass` |
| clean lane | 실패 | cohort `fail`, ledger `fail` |
| machine release | 차단 | closeout `machine_release_allowed=False`, ledger `blocked` |
| learning readiness | 미해소 | revalidation `due`, status `attention` |
| full-suite evidence | 미생성 | `ops/reports/test-execution-summary-full.json` 없음, shards 디렉터리 비어 있음 |
| subprocess lane | 실패 재현 | `make test-subprocess`에서 non-hermetic subprocess test 1 failed, 1 passed |
| recursive tmp hygiene | 미해소 | top-level `tmp/*.json` 0건이나 nested tmp 파일 7건 포함 |
| accepted-risk count semantics | 미정렬 | closeout 3, cohort/ledger/lane clean-blocking 2, operator clean-blocking 3 |
| external report provenance | 부분 개선 | root 보고서 5건 추적, archive 47건 제외, basis ZIP은 현재 ZIP과 다름 |

---

## 2. 검토 입력과 실제 파일 인벤토리

### 2.1 검토한 리뷰 문서

| 문서 | 역할 | 분량 | SHA-256 앞 16자 | 실제 판단 |
| --- | --- | ---: | --- | --- |
| `llmwiki_integrated_review_report_20260504.md` | 새 통합 리뷰 A | 904 lines | `62977ba534207857` | 세 보고서의 공통 합의와 고유 발견을 폭넓게 통합. ZIP 12/13 차이를 비교적 명확히 분리함 |
| `llmwiki_post_review_integrated_report_20260504.md` | 새 통합 리뷰 B | 906 lines | `e007c4b1ea64a248` | 실행 결과와 P0 잔여 작업을 더 직접적으로 요약. 단, 일부 source fingerprint 실패를 현재 ZIP 일반 상태처럼 표현할 위험이 있음 |
| `llmwiki_post_review_work_status_report_20260504.md` | 기존 후속 보고서 | 847 lines | `6b26de95ff836984` | ZIP 12 기준 실제 실행 로그 중심. 현재 실제 ZIP과 가장 직접적으로 맞닿음 |
| `external-reports/llmwiki_review_test_structure_improvement_report_20260504.md` | 기준 리뷰 | 613 lines | `ada802e0d44239bc` | P0/P1 기준선. 현재 개선 반영 여부를 판정하는 원점 |

### 2.2 ZIP 최상위 엔트리 분포

| 최상위 경로 | ZIP 엔트리 수 |
| --- | ---: |
| `raw` | 448 |
| `ops` | 437 |
| `wiki` | 418 |
| `runs` | 185 |
| `tests` | 153 |
| `system` | 74 |
| `external-reports` | 55 |
| `.codex` | 12 |
| `tmp` | 9 |
| `.obsidian` | 6 |
| `tools` | 6 |
| `.github` | 4 |
| `.ouroboros` | 2 |
| `.vscode` | 2 |
| `.gitattributes` | 1 |
| `.gitignore` | 1 |
| `.ouroboros_eval_artifact.md` | 1 |
| `AGENTS.local.md` | 1 |
| `AGENTS.md` | 1 |
| `ARCHITECTURE.md` | 1 |


### 2.3 테스트와 gate 구조

| 항목 | 값 |
| --- | ---: |
| `tests/test_*.py` 파일 수 | 135 |
| AST 기준 test 함수 수 | 893 |
| Makefile target 수 | 145 |
| CI matrix tier 수 | 9 |

확인된 pytest marker:

- `slow: expensive deterministic runtime tests that are excluded from the default fast tier.`
- `integration: end-to-end or live-runtime contract tests in the standard integration tier.`
- `integration_heavy: heavier live generation tests that run separately and are not implied by plain integration.`
- `public: public-surface contract tests; root-tree callers use make test-public, exported-tree callers use make public-check.`
- `report_contract: report, schema, template, and generated artifact contract tests.`
- `artifact_finalization: checked-in generated artifact self-checks that run after producer closeout refresh.`
- `release_sealing: release-builder sealing, batch manifest, and final artifact immutability checks.`
- `subprocess: tests that exercise real subprocess, interpreter startup, timeout, or OS command behavior.`

확인된 핵심 Makefile target:

- `static`: 존재
- `test-fast`: 존재
- `test-report-contract`: 존재
- `test-artifact-finalization`: 존재
- `test-release-sealing`: 존재
- `test-subprocess`: 존재
- `test-execution-summary-full`: 존재
- `release-builder-full`: 존재
- `release-closeout-batch-manifest-verify`: 존재
- `operator-release-summary`: 존재
- `external-report-reference-manifest`: 존재
- `release-provenance-clean`: 존재

CI workflow matrix tier: `fast`, `report-contract`, `artifact-finalization`, `release-sealing`, `subprocess`, `slow`, `integration`, `integration-heavy`, `public`


---

## 3. 두 통합 리뷰의 공통 결론과 실제 파일 대조

### 3.1 공통 결론 중 실제 파일과 일치하는 항목

| 항목 | 리뷰 결론 | 실제 파일 대조 결과 | 확정 판정 |
| --- | --- | --- | --- |
| Self-check watch path validator | 반영 완료 | `status.result=pass`, `missing_required_watch_paths=[]`, `batch_manifest_component_count=10` | 완료 |
| `test-execution-summary` 대표성 명시 | 반영 완료 | `suite_scope=report_contract_summary`, `represents_full_suite=False`, `full_suite_evidence.status=not_represented` | 완료, 단 full-suite artifact는 별도 미완료 |
| Operator one-page summary | 반영 완료 | `status=attention`, `semantic=conditional_pass`, `sealed=sealed_conditional_pass`, summary `semantic=conditional_pass; sealed=sealed_conditional_pass; full_suite=not_run; learning_revalidation=due` | 완료 |
| External report manifest | 반영 완료 | `summary.report_count=5`, `archive_included=False` | 구조 완료, provenance 분리 미완 |
| top-level tmp JSON | 해소 | top-level `tmp/*.json` 0건 | 해소 |
| recursive tmp hygiene | 미해소 | recursive `tmp` 파일 7건 | 미완료 |
| command runtime hermetic 구조 | 반영 | `tests/test_command_runtime.py`는 14 passed, `test-subprocess`는 실패 | 구조 반영, 운영 안정성 미완 |
| clean lane | 실패 | clean lane `fail`, failed conditions `zero_accepted_risk_family, strict_cohort_pass, release_closeout_clean` | 미완료 |
| learning readiness | due | `revalidation.status=due` | 미완료 |
| full-suite evidence | missing/not_run | `test-execution-summary-full.json` 없음 | 미완료 |
| accepted-risk count reconcile | 불일치 | closeout 3 / cohort clean-blocking 2 / operator clean-blocking 3 | 미완료 |

### 3.2 두 통합 리뷰에서 정정해야 할 표현

| 쟁점 | 리뷰 표현 | 실제 ZIP 기준 재판정 | 보고서 반영 방식 |
| --- | --- | --- | --- |
| `source_tree_fingerprint` verify 실패 | 일부 리뷰는 현재 상태의 핵심 P0처럼 기술 | `LLMwiki(12).zip` fresh extract에서 `make release-closeout-batch-manifest-verify PYTHON=python3` 통과 | 현재 ZIP 결함이 아니라 ZIP 13 또는 별도 작업본에서 관찰된 회귀 위험으로 분리 |
| `full_suite_status` field 위치 | 일부 서술은 top-level field처럼 간주 | 실제 operator summary에서는 `test_evidence.full_suite_status=not_run`, `source_load_status.full_test_summary=missing`; 한 줄 summary에도 `full_suite=not_run` | report schema에서 top-level alias를 추가하거나 문서에서 nested path를 정확히 써야 함 |
| `learning_readiness` release fields | 일부 요약은 revalidation artifact top-level에 `machine_release_allowed`가 있는 것처럼 읽힘 | 실제 값은 `learning-readiness-signoff-revalidation.json.closeout.machine_release_allowed=False`에 위치 | path를 `closeout.machine_release_allowed`로 표준화 |
| selected pytest pass claim | 기존 보고서는 여러 test 파일 pass를 기록 | 현재 환경에서 `tests/test_release_evidence_closeout_self_check.py`는 CLI test 지점에서 hang/timeout이 관찰됨. 직접 CLI는 성공 | pass claim은 이전 실행 증거로 남기되, 현 환경에서는 subprocess/pytest startup 계층 이슈를 별도 리스크로 기록 |
| `status=fail` 해석 | batch manifest가 실패처럼 보이거나 sealed pass처럼 보이는 양쪽 오해 가능 | artifact digest sealing은 pass, semantic/source-tree/clean-lane status는 fail/conditional | status namespace 분리를 P0로 유지 |

---

## 4. 기준 리뷰 P0/P1 항목별 실제 반영 판정

### 4.1 P0 항목

| 기준 리뷰 항목 | 실제 파일 기준 판정 | 실제 근거 | 남은 조치 |
| --- | --- | --- | --- |
| P0-1 Release package 봉인 무결성 복구 | 조건부 완료 | batch manifest artifact 10개 모두 digest 일치, verify 통과. 단 `status=fail`, source-tree coherence fail 계층 존재 | artifact sealing과 clean/source-tree sealing을 별도 status로 분리 |
| P0-2 Self-check watch path validator | 완료 | component count 10, missing path 0, watch path가 `batch_manifest.release_authority_status`로 수정 | package-level watch 추가는 P1/P2 |
| P0-3 `test-execution-summary` 대표성 | 구조 완료 / 증거 미완 | `represents_full_suite=false`, `suite_scope=report_contract_summary`, `full_suite_evidence.status=not_represented` | full-suite summary 생성 |
| P0-4 `command_runtime` hermetic subprocess | 구조 완료 / non-hermetic 미완 | command runtime unit 14 passed, subprocess lane 1 failed/1 passed | timeout race hardening, non-hermetic diagnostic 격리 |
| P0-5 accepted-risk vocabulary 단일화 | 부분 완료 | schema와 field vocabulary 추가, 그러나 count 집합 불일치 | reconciliation fixture/test 추가 |
| P0-6 Learning readiness lifecycle | 미완료 | `learning_uncertain`, `revalidation.status=due`, clean lane blocker 유지 | outcome/routing/auto-improve evidence 재생성 또는 signoff 정책 재정의 |
| P0-7 clean pass와 digest mismatch 공존 invariant | 부분 완료 | machine release는 차단되지만 `status=pass/fail/conditional/sealed`가 여러 artifact에서 혼재 | multi-axis status namespace와 dashboard consistency test |
| P0-8 Check command write-free mode | 부분 완료 | top-level tmp JSON은 없음. 그러나 `release-provenance-clean` 실행 중 canonical check chain이 장시간/timeout 문제를 보임 | check target write scope를 machine-readable하게 검증 |
| P0-9 full-suite/release-builder evidence | 미완료 | `test-execution-summary-full.json` 없음, shards 0건 | shard/aggregate artifact 표준화 및 CI publish |

### 4.2 P1 항목

| 기준 리뷰 항목 | 실제 파일 기준 판정 | 실제 근거 | 남은 조치 |
| --- | --- | --- | --- |
| P1-1 Operator one-page summary | 완료 | `ops/reports/operator-release-summary.json` 존재, semantic/sealed/learning/full-suite 요약 제공 | 빈 reason field 금지 및 canonical dashboard diff 추가 |
| P1-2 External report reference manifest | 구조 완료 / provenance 미완 | root external report 5건 참조, archive 제외, basis ZIP이 현재 ZIP과 다름 | basis ZIP/current ZIP/two-layer manifest 분리 |
| P1-3 release/review package mode 분리 | 부분 완료 | `release_package_mode=local_workspace`; recursive tmp 포함 | `release`, `review-full`, `local-workspace`별 package policy 도입 |
| P1-4 대형 test 파일 분해 | 미완료 | marker/lane은 늘었으나 대형 test 파일 자체 분해 증거는 제한적 | slow/subprocess/integration-heavy 별 fixture split 및 ownership 매핑 |

---

## 5. 실제 generated artifacts 상세 대조

### 5.1 Batch manifest와 artifact digest

| field | 값 |
| --- | --- |
| `status` | `fail` |
| `batch_integrity_status` | `pass` |
| `release_authority_status` | `conditional_pass` |
| `semantic_release_status` | `conditional_pass` |
| `sealed_release_status` | `sealed_conditional_pass` |
| `summary.artifact_count` | `10` |
| `summary.present_count` | `10` |
| `summary.current_count` | `10` |
| `downstream_input_digest_mismatch.status` | `match` |
| `downstream_input_digest_mismatch.mismatch_count` | `0` |
| `source_tree_fingerprint` | `b2a04af8646f57ea6bc5f997526a985317a7a1aff944654404a51b852de62214` |
| `finality.is_final` | `True` |

Artifact digest 재계산 결과:

| artifact | required | expected SHA 앞 16자 | actual SHA 앞 16자 | 일치 |
| --- | ---: | --- | --- | --- |
| `ops/reports/release-smoke-report.json` | True | `25a77a2f9d2d7176` | `25a77a2f9d2d7176` | O |
| `ops/reports/generated-artifact-index.json` | True | `e2866bbe92a0352f` | `e2866bbe92a0352f` | O |
| `ops/reports/artifact-freshness-report.json` | True | `8cbefcb243877d09` | `8cbefcb243877d09` | O |
| `ops/reports/test-execution-summary.json` | True | `431ecd89abac3bc0` | `431ecd89abac3bc0` | O |
| `ops/reports/release-closeout-summary.json` | True | `b9777b2bad6d70c8` | `b9777b2bad6d70c8` | O |
| `ops/reports/learning-readiness-signoff-revalidation.json` | True | `d21fdba8adda236f` | `d21fdba8adda236f` | O |
| `ops/reports/release-evidence-cohort.json` | True | `0ca1b27bc4975897` | `0ca1b27bc4975897` | O |
| `ops/reports/release-evidence-dashboard.json` | True | `c1593f1a7250701c` | `c1593f1a7250701c` | O |
| `ops/reports/release-lane-summary.json` | True | `178d40d0cfaa0e98` | `178d40d0cfaa0e98` | O |
| `ops/reports/release-clean-blocker-ledger.json` | True | `c1d391132c61a8e1` | `c1d391132c61a8e1` | O |


**판정:** 현재 actual ZIP 기준 artifact content sealing은 닫혀 있다. 그러나 이 사실은 clean release readiness를 뜻하지 않는다. batch manifest 자체가 `status=fail`이고 `integrity_layers.source_tree_coherence_integrity=fail`로 표시되므로, artifact digest pass와 clean/source-tree pass를 같은 status로 읽으면 안 된다.

### 5.2 Release closeout summary

| field | 값 |
| --- | --- |
| `status` | `pass` |
| `release_readiness_state` | `conditional_pass` |
| `checked_in_release_ready` | `True` |
| `live_rerun_release_ready` | `False` |
| `conditional_release_ready` | `True` |
| `clean_release_ready` | `False` |
| `machine_release_allowed` | `False` |
| `operator_release_allowed` | `True` |
| `summary.accepted_risk_family_count` | `3` |
| `summary.release_blocking_risk_count` | `1` |
| `summary.advisory_risk_count` | `2` |
| `clean_lane_blocking_risk_family_count` | `2` |
| `downstream_input_digest_mismatch.status` | `mismatch` |
| `downstream_input_digest_mismatch.mismatch_count` | `4` |
| mismatch input names | `release_smoke, test_summary, artifact_freshness, generated_index` |

**판정:** 두 리뷰가 지적한 downstream mismatch 4건은 실제 파일에서 확인된다. 다만 batch manifest의 downstream mismatch는 0건이므로, closeout summary와 batch manifest가 서로 다른 snapshot phase를 표현하고 있다. 이 계층 차이는 반드시 schema/status로 드러나야 한다.

### 5.3 Clean lane, accepted risk, learning readiness

| artifact | field | 값 |
| --- | --- | --- |
| `release-evidence-cohort.json` | `status` | `attention` |
| `release-evidence-cohort.json` | `summary.accepted_risk_family_count` | `2` |
| `release-evidence-cohort.json` | `clean_lane_contract.status` | `fail` |
| `release-evidence-cohort.json` | `clean_lane_contract.clean_lane_blocking_family_count` | `2` |
| `release-evidence-cohort.json` | `clean_lane_contract.failed_conditions` | `zero_accepted_risk_family, strict_cohort_pass, release_closeout_clean` |
| `release-clean-blocker-ledger.json` | `summary.blocker_count` | `3` |
| `release-clean-blocker-ledger.json` | `summary.clean_lane_status` | `fail` |
| `release-clean-blocker-ledger.json` | `summary.machine_release_status` | `blocked` |
| `release-lane-summary.json` | `lane_summary.clean_lane_status` | `fail` |
| `release-lane-summary.json` | `lane_summary.conditional_lane_status` | `pass` |
| `operator-release-summary.json` | `accepted_risk.operator_accepted_risk_family_count` | `3` |
| `operator-release-summary.json` | `accepted_risk.clean_lane_blocking_accepted_risk_family_count` | `3` |

Learning readiness:

| field | 값 |
| --- | --- |
| `status` | `attention` |
| `learning_readiness.status` | `learning_uncertain` |
| `learning_readiness.likely_to_learn` | `False` |
| `learning_readiness.blocker_present` | `True` |
| `revalidation.status` | `due` |
| `revalidation.clean_closeout_required` | `False` |
| `closeout.release_readiness_state` | `conditional_pass` |
| `closeout.machine_release_allowed` | `False` |
| `closeout.operator_release_allowed` | `True` |

**판정:** accepted risk count는 field 이름이 통일됐지만 aggregation source가 통일되지 않았다. clean lane을 닫으려면 먼저 어떤 field가 `dashboard attention`, `operator accepted risk`, `release blocking risk`, `clean-lane blocking risk` 중 어느 집합을 세는지 producer 간 합의해야 한다.

### 5.4 Test evidence

| field | 값 |
| --- | --- |
| `suite` | `report-contract-summary` |
| `suite_scope` | `report_contract_summary` |
| `represents_full_suite` | `False` |
| `counts.passed` | `123` |
| `counts.failed` | `0` |
| `full_suite_evidence.status` | `not_represented` |
| AST 기준 test 함수 수 | `893` |
| `ops/reports/test-execution-summary-full.json` | `없음` |
| `ops/reports/test-execution-summary-shards/` | `존재하나 비어 있음` |

**판정:** test summary의 정직성은 크게 개선됐다. 그러나 123개 pass는 full suite가 아니며, AST 기준 893개 test 함수의 full release-builder evidence는 아직 존재하지 않는다.

### 5.5 Operator summary

| field | 값 |
| --- | --- |
| `status` | `attention` |
| `semantic_release_status` | `conditional_pass` |
| `sealed_release_status` | `sealed_conditional_pass` |
| `release_package_mode` | `local_workspace` |
| `tmp_json_policy_status` | `clean` |
| `source_load_status.full_test_summary` | `missing` |
| `test_evidence.full_suite_status` | `not_run` |
| `test_evidence.full_suite_summary_load_status` | `missing` |
| `test_evidence.full_suite_reason` | `''` |
| `learning_readiness.revalidation_status` | `due` |
| `learning_readiness.release_effect.operator_summary` | `''` |
| `operator_summary` | `semantic=conditional_pass; sealed=sealed_conditional_pass; full_suite=not_run; learning_revalidation=due` |

**판정:** operator summary는 필요한 압축 정보를 제공하지만, `full_suite_reason`과 `learning_readiness.release_effect.operator_summary`가 빈 문자열이다. operator-facing artifact에서는 빈 reason을 허용하지 않는 편이 낫다.

### 5.6 External report reference manifest

| field | 값 |
| --- | --- |
| `basis_zip.name` | `LLMwiki.zip` |
| `basis_zip.sha256` | `0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93` |
| `basis_zip.entry_count` | `1819` |
| 현재 ZIP SHA-256 | `470475533932575a0e42dc5e770b005290ee94e5775f9faa7707fc4f196cf209` |
| 현재 ZIP entry count | `1829` |
| `summary.report_count` | `5` |
| `summary.archive_included` | `False` |
| archive file count | `47` |

Root external report references:

| file | lines | SHA 앞 16자 |
| --- | ---: | --- |
| `integrated_improvement_report_v3.md` | 599 | `9a2fdf8861f544fe` |
| `llmwiki_consolidated_improvement_execution_report_20260503.md` | 328 | `aa0f19a65c748da6` |
| `llmwiki_dual_review_crosscheck_improvement_report_20260503.md` | 603 | `541044dadf77dfbc` |
| `llmwiki_integrated_reviews_crosscheck_improvement_report_20260503.md` | 594 | `fdcaa591a30ae9c4` |
| `llmwiki_review_test_structure_improvement_report_20260504.md` | 613 | `ada802e0d44239bc` |


**판정:** external manifest는 기준 리뷰의 P1 요구를 충족하는 출발점이다. 하지만 현재 ZIP과 basis ZIP이 다르므로, `review_basis_zip`과 `current_distribution_zip`을 분리해야 한다. 또한 archive 47건의 exclusion이 정책적으로 허용되는지 manifest에서 이유를 제공해야 한다.

### 5.7 Recursive tmp hygiene

| 범위 | 결과 |
| --- | ---: |
| top-level `tmp/*.json` | 0 |
| recursive `tmp/**` file | 7 |

현재 recursive tmp 파일:

- `tmp/_patch_vocab_refs.py`
- `tmp/codex-plan-review/archive-execution-manifest.json`
- `tmp/codex-plan-review/artifact-freshness-report.json`
- `tmp/codex-plan-review/current-raw-registry-evidence-bundle.json`
- `tmp/codex-plan-review/current-release-evidence-cohort-strict.json`
- `tmp/codex-plan-review/raw-registry-cross-environment-matrix.json`
- `tmp/codex-plan-review/release-closeout-summary.json`


**판정:** 두 통합 리뷰의 지적처럼 top-level tmp JSON만 보는 정책은 충분하지 않다. release package mode에서는 `tmp/**` 전체를 제외하거나 recursive violation으로 처리해야 한다. `tmp/codex-plan-review`가 review package evidence라면 `review-full` package mode에서만 허용해야 한다.

---

## 6. 실행 검증 내역

이번 대조에서 실제 수행한 명령과 결과는 다음과 같다.

| 명령 | 결과 | 해석 |
| --- | --- | --- |
| `sha256sum LLMwiki(12).zip` | `470475533932575a0e42dc5e770b005290ee94e5775f9faa7707fc4f196cf209` | ZIP 식별 확정 |
| ZIP extract | 1,829 entries | 실제 파일 대조 완료 |
| AST test inventory | 135 files / 893 functions | full-suite 기준 규모 확인 |
| `python3 -m ruff check ops/scripts tests tools` | pass | 정적 lint 통과 |
| `python3 -m mypy @ops/mypy-allowlist.txt` | pass, 177 source files | allowlist mypy 통과 |
| `make release-closeout-batch-manifest-verify PYTHON=python3` | pass | 현재 ZIP 12에서는 batch manifest verify 실패 재현 안 됨 |
| batch manifest artifact digest 독립 재계산 | 10/10 match | required artifact content sealing 확인 |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_command_runtime.py -q` | 14 passed | fake/backend 중심 command runtime unit 통과 |
| `make test-subprocess PYTHON=python3` | 1 failed, 1 passed | non-hermetic real subprocess timeout false positive 재현 |
| `python3 -m ops.scripts.release_evidence_closeout_self_check --vault . --out tmp/self_check_test.json` | exit 0 | self-check CLI 직접 실행은 성공 |
| `tests/test_release_evidence_closeout_self_check.py -vv -s` | `test_main_cli_entry` 이후 timeout/hang 관찰 | pytest CLI/subprocess 계층의 불안정성 추가 신호 |
| `make release-provenance-clean PYTHON=python3` | ruff/mypy 후 artifact freshness 단계에서 timeout | clean release gate 전체 완료 증거 없음 |

### 6.1 Subprocess failure 재현 로그 핵심

`make test-subprocess PYTHON=python3` 결과:

```text
FAILED tests/test_command_runtime_subprocess.py::test_run_with_timeout_executes_real_subprocess
assert -15 == 0
TimedProcessResult(... timed_out=True, termination_reason='timeout', phase_observed='drain_after_signal', stdout_received=True, stderr_received=True, launch_latency_seconds=0.1009...)
1 failed, 1 passed
```

이 실패는 단순한 테스트 flaky가 아니라 성공 가능성이 있는 subprocess를 timeout/SIGTERM으로 전환할 수 있다는 의미다. 특히 `stdout_received=True`인데 `stdout=''`로 남는 결과는 capture/drain 단계의 race condition 가능성을 시사한다.

---

## 7. 두 통합 리뷰 간 차이와 통합 판정

### 7.1 차이점 요약

| 차이 | 리뷰 A 경향 | 리뷰 B 경향 | 실제 파일 기준 결론 |
| --- | --- | --- | --- |
| ZIP 12/13 구분 | ZIP 버전 의존성을 명시 | 동일 체크포인트처럼 요약하는 구간 존재 | 현재 실제 ZIP은 12. ZIP 13 결론은 회귀 위험으로만 반영 |
| source fingerprint drift | 13번 ZIP 고유 발견으로 상세 설명 | P0 잔여 작업으로 직접 반영 | 실제 ZIP 12에서는 verify pass. 다만 pristine workspace gate는 필요 |
| downstream mismatch | 고유 발견으로 분석 | P0-R9로 반영 | 실제 closeout summary에서 4건 확인 |
| execution 검증 | 세 보고서 보완 관계 강조 | 동적 검증 결과 표 중심 | 실제 재검증은 static/mypy/batch verify/command unit pass, subprocess fail |
| 개선안 수 | 18개로 더 폭넓음 | 15개로 압축 | 중복을 12개 실행 항목으로 재정렬 권장 |

### 7.2 통합 판정의 원칙

1. **현재 actual ZIP에서 재현되는 결함**과 **다른 스냅샷에서 보고된 회귀 위험**을 구분한다.
2. `pass`, `fail`, `attention`, `conditional_pass`, `sealed_conditional_pass`를 단일 status 축으로 합치지 않는다.
3. clean release를 막는 항목은 operator-facing 개선보다 우선한다.
4. schema 추가와 실제 producer semantics 정렬을 별도 완료 조건으로 둔다.
5. full-suite evidence가 없으면 release confidence는 conditional 이상으로 승격하지 않는다.

---

## 8. 확정 잔여 작업

### P0-A. Clean lane을 실제 pass로 닫기

현재 clean lane은 실패다. `release-evidence-cohort.clean_lane_contract.status=fail`, `release-clean-blocker-ledger.summary.clean_lane_status=fail`, `machine_release_allowed=False`가 동시에 확인된다. 실패 조건은 `zero_accepted_risk_family, strict_cohort_pass, release_closeout_clean`이다.

필요 작업:

- accepted risk family 중 clean lane blocking 집합을 0으로 만들거나, conditional lane 전용으로 이동한다.
- `release_closeout_clean` 실패를 생성하는 producer chain을 역추적해 blocker별 closure action을 출력한다.
- clean lane gate는 `operator_release_allowed=True`와 무관하게 machine release를 차단해야 한다.

### P0-B. Learning readiness revalidation due 해소

현재 `learning_readiness.status=learning_uncertain`, `likely_to_learn=False`, `blocker_present=True`, `revalidation.status=due`다. clean lane을 닫으려면 learning signals를 재생성하거나, signoff 정책이 clean release에 미치는 영향을 재정의해야 한다.

필요 작업:

- `auto-improve-readiness`, `outcome-metrics`, `routing-provenance-aggregate` 관련 산출물을 최신화한다.
- signoff가 conditional operator release에는 허용되더라도 clean/machine release에는 허용되지 않는다는 점을 schema에 명시한다.
- revalidation due/expired/active 상태별 release effect를 별도 field로 고정한다.

### P0-C. Full-suite evidence 생성

현재 `test-execution-summary.json`은 targeted report-contract summary이며, full-suite를 대표하지 않는다. `test-execution-summary-full.json`이 없고 shard artifact도 없다.

필요 작업:

- `test-execution-summary-full`을 실제 실행해 canonical full artifact를 생성한다.
- 장시간 실행이면 shard summary를 생성하고 aggregate artifact를 authoritative evidence로 삼는다.
- operator summary는 `full_suite_reason`을 빈 문자열로 두지 말고, missing/not_run의 정확한 이유를 기록한다.

### P0-D. Subprocess timeout false positive 수정

현재 non-hermetic subprocess lane은 실패한다. 단순히 hermetic path가 통과한다는 사실만으로 닫으면 안 된다.

필요 작업:

- `TimeoutExpired` 직후 signal 전송 전 짧은 no-signal grace drain을 수행한다.
- stdout/stderr 수신 여부와 process poll 상태를 재확인한 뒤 timeout 확정한다.
- `termination_reason`을 `startup_timeout`, `execution_timeout`, `timeout_after_output`, `signal_race_recovered` 등으로 세분화한다.
- non-hermetic subprocess lane은 release blocking이 아니라 environment diagnostic으로 둘지 정책 결정한다.

### P0-E. Accepted-risk count reconciliation

현재 count 집합이 맞지 않는다.

| field | 값 |
| --- | ---: |
| closeout `summary.accepted_risk_family_count` | 3 |
| closeout `summary.release_blocking_risk_count` | 1 |
| closeout `summary.advisory_risk_count` | 2 |
| closeout `clean_lane_blocking_risk_family_count` | 2 |
| cohort `clean_lane_contract.clean_lane_blocking_family_count` | 2 |
| lane `lane_summary.clean_lane_blocking_family_count` | 2 |
| ledger `summary.clean_lane_blocking_family_count` | 2 |
| operator `accepted_risk.clean_lane_blocking_accepted_risk_family_count` | 3 |

필요 작업:

- 각 count field에 `source_artifact`, `source_path`, `aggregation_rule`, `included_scopes`, `excluded_scopes`를 붙인다.
- same fixture를 closeout/cohort/lane/ledger/operator producer에 넣어 reconciliation test를 만든다.
- dashboard attention count와 clean-lane blocking count를 분리한다.

### P0-F. Closeout downstream input digest mismatch 해소

`release-closeout-summary.json`에는 downstream mismatch 4건이 있다. 반면 batch manifest는 mismatch 0건이다.

필요 작업:

- closeout summary에 `snapshot_phase=pre_finalization|post_finalization|sealed_snapshot`을 추가한다.
- finalizer 이후 산출물을 input으로 보는 경우 `informational_after_writer` 정책을 명시한다.
- release closeout summary와 batch manifest가 같은 digest semantics를 쓰지 않는다면 field 이름을 다르게 한다.

### P0-G. Recursive tmp/package hygiene 강화

현재 top-level tmp JSON은 0건이지만 recursive tmp 파일 7건이 포함되어 있다. release package라면 부적절하다.

필요 작업:

- `release` package mode에서는 `tmp/**` 전체를 제외하거나 fail 처리한다.
- `review-full` mode에서만 `tmp/codex-plan-review/**` 허용한다.
- `tmp/_patch_vocab_refs.py`는 삭제하거나 정식 migration script로 승격한다.

### P0-H. Status namespace 분리

현재 `status=pass`, `status=fail`, `attention`, `conditional_pass`, `sealed_conditional_pass`가 서로 다른 의미로 사용된다.

필요 작업:

- `artifact_generation_status`
- `artifact_digest_sealing_status`
- `source_tree_rebuild_status`
- `semantic_release_status`
- `clean_lane_status`
- `machine_release_status`
- `operator_release_status`

위 field를 별도 namespace로 분리하고 top-level `status`는 deprecated 또는 summary-only로 낮춘다.

### P0-I. Actual ZIP vs reported ZIP provenance 분리

현재 external manifest는 basis ZIP을 `LLMwiki.zip` SHA `0a547950…`, entry 1,819로 기록하지만, 실제 ZIP은 SHA `470475533932575a…`, entry 1,829다.

필요 작업:

- `review_basis_zip`과 `current_distribution_zip`을 별도 객체로 둔다.
- 기준 리뷰가 분석한 ZIP, 현재 배포 ZIP, 후속 리뷰 ZIP을 각각 기록한다.
- archive 제외 시 `archive_exclusion_policy`와 `excluded_file_count`를 추가한다.

### P0-J. Source tree fingerprint 회귀 방지 gate

현재 ZIP 12에서는 verify pass가 재현됐다. 그러나 두 리뷰 중 하나가 ZIP 13 또는 별도 작업본에서 source fingerprint drift를 기록했으므로 회귀 방지 gate는 여전히 필요하다.

필요 작업:

- pristine workspace에서 batch manifest regenerate 후 byte-for-byte diff를 수행하는 독립 target을 추가한다.
- 실패 시 expected/current fingerprint뿐 아니라 변경된 input family, source file set, generated artifact ordering을 출력한다.
- 이 gate의 실패를 artifact digest mismatch와 다른 class로 분류한다.

---

## 9. 신규 개선 방안 재정렬

두 리뷰가 제안한 개선안을 실제 파일 기준으로 중복 제거해 실행 순서로 재배열하면 다음과 같다.

### 9.1 즉시 처리 P0

| 순번 | 개선안 | 목적 | 완료 조건 |
| --- | --- | --- | --- |
| 1 | Subprocess timeout race hardening | 테스트/검증 신뢰성 복구 | `make test-subprocess` pass 또는 non-hermetic diagnostic 전환 |
| 2 | Full-suite shard/aggregate artifact 생성 | release confidence 확보 | `test-execution-summary-full.json` 또는 aggregate artifact 존재, operator summary가 읽음 |
| 3 | Learning readiness revalidation closure | clean lane blocker 해소 | `revalidation.status=active/pass` 또는 clean lane effect 명확화 |
| 4 | Accepted-risk reconciliation test | count semantics 정렬 | closeout/cohort/lane/ledger/operator count 관계 test pass |
| 5 | Closeout downstream snapshot phase 명시 | digest mismatch 혼동 제거 | mismatch 0 또는 `snapshot_phase`/policy로 설명 |
| 6 | Recursive tmp package policy | release package hygiene | release mode에서 `tmp/**` 포함 0건 또는 허용 사유 명시 |
| 7 | Status namespace split | operator/machine 해석 오류 차단 | 각 status axis가 schema-required로 분리됨 |

### 9.2 단기 P1

| 순번 | 개선안 | 목적 | 완료 조건 |
| --- | --- | --- | --- |
| 1 | External manifest two-layer 구조 | basis/current provenance 혼동 방지 | review basis와 current distribution ZIP을 별도 기록 |
| 2 | Operator summary reason non-empty | 운영자 판단 가능성 향상 | missing/not_run/due 상태의 reason이 빈 문자열이 아님 |
| 3 | Pristine workspace verify target | ZIP 13형 회귀 방지 | clean extract에서 regenerate/diff 결과 artifact 생성 |
| 4 | Batch verify diagnostic artifact | 실패 분석 시간 단축 | diff_reason, changed_fingerprints, suspected_inputs 제공 |
| 5 | Post-review delta manifest | 리뷰 간 변경 추적 | baseline/current added/modified/removed machine-readable 생성 |

### 9.3 중기 P2

| 순번 | 개선안 | 목적 |
| --- | --- | --- |
| 1 | 대형 test 파일 분해 | lane별 ownership과 실패 localization 개선 |
| 2 | CI artifact upload 표준화 | local evidence와 CI evidence 연결 |
| 3 | release/review/local package modes | 배포 ZIP과 리뷰 ZIP의 목적별 구성 분리 |
| 4 | self-check package-level 확대 | source tree, tmp hygiene, full-suite, provenance까지 감시 |
| 5 | clean release dashboard 단일화 | operator summary/dashboard/closeout 간 불일치 자동 감지 |

---

## 10. Definition of Done 재정의

현재 상태를 `sealed clean release`로 승격하려면 다음 조건을 모두 만족해야 한다.

1. `release-closeout-batch-manifest-verify`가 fresh/pristine workspace에서 pass한다.
2. required artifact digest 10/10 match가 유지된다.
3. `release-closeout-summary.clean_release_ready=true`와 `machine_release_allowed=true`가 된다.
4. `release-evidence-cohort.clean_lane_contract.status=pass`가 된다.
5. `release-clean-blocker-ledger.summary.blocker_count=0` 또는 machine release blocking blocker가 0이 된다.
6. `learning-readiness-signoff-revalidation.revalidation.status`가 due가 아니거나, clean release 영향이 명확히 pass/accepted policy로 봉인된다.
7. `test-execution-summary-full.json` 또는 shard aggregate full-suite artifact가 존재한다.
8. `test-execution-summary.json.represents_full_suite=false`인 상태에서는 이를 full-suite 근거로 사용하지 않는다.
9. `make test-subprocess`가 pass하거나 non-hermetic subprocess lane이 명시적으로 diagnostic-only로 격리된다.
10. accepted-risk count field 간 포함관계가 reconciliation test로 고정된다.
11. release package mode에서 `tmp/**`가 없거나 허용된 review evidence로 분류된다.
12. external report manifest가 기준 ZIP과 현재 ZIP을 동시에, 별도 필드로 기록한다.
13. operator summary의 missing/due/not_run reason field가 빈 문자열이 아니다.
14. top-level `status` 대신 axis-specific status가 machine-readable로 제공된다.

---

## 11. 최종 권고

현재 실제 파일 기준으로 가장 정확한 명명은 다음이다.

> **`artifact-digest-sealed conditional package with clean-lane blockers and incomplete full-suite evidence`**

즉, artifact digest sealing은 상당히 개선됐고 현재 ZIP 12에서는 batch manifest verify가 통과한다. 그러나 clean lane, machine release, full-suite evidence, learning readiness, subprocess stability, accepted-risk reconciliation, recursive tmp hygiene는 아직 닫히지 않았다.

작업 순서는 다음이 가장 효율적이다.

1. subprocess timeout false positive를 먼저 고쳐 검증 인프라를 안정화한다.
2. full-suite/shard evidence를 생성해 release confidence 공백을 닫는다.
3. learning readiness due와 accepted-risk count reconciliation을 처리해 clean lane blocker를 줄인다.
4. closeout snapshot phase와 status namespace를 정리해 operator/machine 판단 혼동을 없앤다.
5. package mode별 tmp/provenance policy를 정리해 release ZIP과 review ZIP의 목적을 분리한다.
6. pristine workspace verify와 post-review delta manifest로 이후 리뷰 사이클의 회귀 탐지를 자동화한다.

---

## 부록 A. 실제 대조 파일 목록

### A.1 확인한 핵심 JSON artifact

| 파일 | 존재 | SHA 앞 16자 |
| --- | --- | --- |
| `ops/reports/release-closeout-batch-manifest.json` | O | `a06e016cc5f8b5f6` |
| `ops/reports/release-closeout-summary.json` | O | `b9777b2bad6d70c8` |
| `ops/reports/release-evidence-cohort.json` | O | `0ca1b27bc4975897` |
| `ops/reports/release-evidence-dashboard.json` | O | `c1593f1a7250701c` |
| `ops/reports/release-lane-summary.json` | O | `178d40d0cfaa0e98` |
| `ops/reports/release-clean-blocker-ledger.json` | O | `c1d391132c61a8e1` |
| `ops/reports/operator-release-summary.json` | O | `0989d6bca6d27c4b` |
| `ops/reports/learning-readiness-signoff-revalidation.json` | O | `d21fdba8adda236f` |
| `ops/reports/test-execution-summary.json` | O | `431ecd89abac3bc0` |
| `ops/reports/release-evidence-closeout-self-check.json` | O | `22c4d73e8a26bee5` |
| `external-reports/report-reference-manifest.json` | O | `1b9ce7569ab1c84b` |


### A.2 주의가 필요한 실제 대조 한계

- 현재 대화에 실제 파일로 존재하는 ZIP은 `LLMwiki(12).zip`이다.
- 두 통합 리뷰가 언급한 `LLMwiki(13).zip`은 현재 파일 시스템에서 직접 대조하지 못했다.
- 따라서 `source_tree_fingerprint` 불일치 실패는 현재 ZIP 12의 직접 결함이 아니라 별도 스냅샷 회귀 위험으로 보고서에 반영했다.
- 일부 pytest 기반 CLI test는 현 실행 환경에서 hang/timeout을 보였으므로, 이전 보고서의 pass 로그와 이번 직접 실행 로그를 함께 보아야 한다.
