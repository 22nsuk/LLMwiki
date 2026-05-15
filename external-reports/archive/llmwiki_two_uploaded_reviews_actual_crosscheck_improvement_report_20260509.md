# LLMwiki 두 신규 통합 리뷰-기존 리뷰-현재 압축본 실제 대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-09 KST |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_two_uploaded_reviews_actual_crosscheck_improvement_report_20260509.md` |
| 검토 대상 ZIP | `LLMwiki(27).zip` |
| 현재 ZIP SHA-256 | `e9d9f6821021da873075df271f16f6c06adfe9c10b6f53b2f0589d046a2d2f93` |
| 현재 ZIP 엔트리 | 2029개 (파일 1917개 + 디렉터리 112개) |
| 비교 대상 신규 리뷰 1 | `llmwiki_integrated_tri_review_report_20260509.md` |
| 비교 대상 신규 리뷰 2 | `llmwiki_integrated_review_report_20260509.md` |
| 기존 리뷰/직전 보고서 | `llmwiki_current_zip_actual_crosscheck_update_report_20260509.md` |
| 저장소 내부 기준 외부 보고서 | `external-reports/llmwiki_two_new_reviews_actual_crosscheck_improvement_report_20260509.md` |
| 작업 복사본 | `/mnt/data/llmwiki_two_reviews_deep_work` |

---

## 0. 최종 결론

두 신규 리뷰(`llmwiki_integrated_tri_review_report_20260509.md`, `llmwiki_integrated_review_report_20260509.md`)를 전체적으로 대조한 결과, 두 문서는 **핵심 진단에서 실질적으로 같은 결론**에 도달한다. 즉, 기존 보고서의 핵심 P0였던 `artifact-freshness-check` schema-invalid 6건은 현재 압축본에서 해소되었지만, 저장소는 여전히 release-ready가 아니다. 현재 최우선 blocker는 다음 네 묶음이다.

1. `ops/script-output-surfaces.json`의 `source_tree_fingerprint`가 현재 live AST inventory fingerprint와 불일치하여 `make check`가 실패한다.
2. `release-smoke-report`, `test-execution-summary`, `generated-artifact-index` 등 release/generated canonical artifacts가 서로 다른 source tree snapshot을 가리킨다.
3. `release-source-package-check`의 기본 `SOURCE_PACKAGE_EXTRACT_ROOT`가 release ZIP의 고정 archive root `LLMwiki`와 맞지 않아 기본값 검증이 실패한다. override 시 통과하므로 ZIP 생성 자체보다 checker default가 문제다.
4. `auto-improve-readiness.json`이 live gate failure와 stale canonical artifacts를 promotion blocker로 반영하지 못해 `can_promote_result=true`를 유지한다.

따라서 이번 보고서의 통합 판정은 다음과 같다.

> **현재 압축본은 artifact freshness schema 관점에서는 개선되었지만, release/promotion authority 관점에서는 아직 blocked 상태로 취급해야 한다. 조치는 단일 JSON 수정보다 “현재 source tree 기준 canonical artifact 재생성 + source package checker default root 수정 + live gate와 auto-improve/release authority 연결”을 하나의 자동화 루프로 닫는 방식이어야 한다.**

---

## 1. 입력 자료와 실제 확인 범위

### 1.1 검토한 리뷰/보고서

| 구분 | 파일 | SHA-256 |
| --- | --- | --- |
| 신규 리뷰 1 | `llmwiki_integrated_tri_review_report_20260509.md` | `c913b8965bb3bbedde9930b4a45ab8625e479e5f6131a9b7ab0e99de4ecd280f` |
| 신규 리뷰 2 | `llmwiki_integrated_review_report_20260509.md` | `8deeeefff2251a0fc38e053f36599cc33ad47416fe846f91a100b2f81a4a264d` |
| 기존 직전 리뷰 | `llmwiki_current_zip_actual_crosscheck_update_report_20260509.md` | `cfadd638edfe2997a9354b0d6ac9f74d3992dbb3ceb98c728e7fc2703089670e` |
| 저장소 내부 기준 보고서 | `external-reports/llmwiki_two_new_reviews_actual_crosscheck_improvement_report_20260509.md` | `998fd58f8c33f74a8480db6950714858063dd69539811185ba51823b3505cb46` |

### 1.2 현재 ZIP 구조

현재 업로드 ZIP은 두 신규 리뷰가 말한 것과 동일하게 `e9d9f682...`, 2,029 entries다. 기준 외부 보고서가 전제한 `6731aa87...`, 2,007 entries 및 저장소 manifest의 `0a547950...`, 1,819 entries와는 다르다. 즉 현재 ZIP에 대해서는 기존 보고서의 P0/P1을 그대로 재사용하지 말고 현재 artifact와 live command 결과로 재판정해야 한다.

| 항목 | 값 |
| --- | ---: |
| ZIP SHA-256 | `e9d9f6821021da873075df271f16f6c06adfe9c10b6f53b2f0589d046a2d2f93` |
| 전체 entries | 2029 |
| 파일 entries | 1917 |
| 디렉터리 entries | 112 |
| 비압축 크기 합계 | 250,593,654 bytes |
| 압축 크기 합계 | 192,052,466 bytes |

| prefix | 파일 수 |
| --- | --- |
| ops | 452 |
| raw | 446 |
| wiki | 417 |
| runs | 263 |
| tests | 164 |
| system | 71 |
| external-reports | 61 |
| <root> | 18 |
| .codex | 10 |
| tools | 6 |
| .obsidian | 5 |
| .github | 2 |
| .ouroboros | 1 |
| .vscode | 1 |

---

## 2. 이번 추가 검증에서 확인한 명령 결과

이번 작업에서는 현재 ZIP을 새 작업복사본으로 풀어 일부 명령을 직접 재실행했고, 장시간 전체 실행이 필요한 항목은 직전 동일 SHA 작업복사본의 완료 로그를 함께 사용했다. 동일 ZIP SHA와 동일 핵심 파일 fingerprint를 기준으로 하므로 기존 완료 로그는 현재 판정에 유효하다. 다만 이번 새 작업복사본에서 `selected_contracts` 및 `release-source-package-check` 기본값 전체 재실행은 도구 실행 제한으로 중단되었으므로, 해당 항목은 직전 전체 로그와 checked-in JSON/소스 대조를 근거로 판정했다.

| 검증 | rc | 메모 |
| --- | --- | --- |
| make static | 0 |  |
| make artifact-freshness-check | 0 |  |
| python -m pytest --collect-only -q | 0 | 151개 테스트 파일, 1050 tests collected |
| make release-distribution-zip | 0 | LLMwiki root, 1468 entries, sha256 bc988f2d1e52… |
| make check | 2 | 1 failed, 740 passed in 322.43s (0:05:22) (동일 SHA 기준 이전 전체 로그 재사용) |
| selected contract 68개 | 1 | 3 failed, 65 passed in 19.19s (동일 SHA 기준 이전 전체 로그 재사용) |
| make release-source-package-check 기본값 | 2 | 동일 SHA 기준 이전 전체 로그: extract-root mismatch 계열 실패 |
| make release-source-package-check SOURCE_PACKAGE_EXTRACT_ROOT=…/LLMwiki | 0 | current-fingerprint report 46096f5bd375…, nodeid_count=980, 975 passed, 5 skipped, 70 deselected i |

### 2.1 직접 재확인된 통과 항목

- `make static`: ruff/mypy 통과.
- `make artifact-freshness-check`: 통과.
- `pytest --collect-only -q`: 1050 tests collected.
- `make release-distribution-zip`: 통과. 생성 ZIP은 `LLMwiki` root 하나만 갖고, 1468 entries, SHA-256 `bc988f2d1e52e34923915e59cf19b5885e5d816bce32e9a58419edd2434538fd`이다.

### 2.2 동일 SHA 완료 로그로 재확인된 실패 항목

- `make check`: `1 failed, 740 passed in 322.43s (0:05:22)`, rc=2. 실패 테스트는 `tests/test_writer_output_paths.py::WriterOutputPathsTest::test_script_output_surface_registry_matches_current_ast_inventory`다.
- selected contract 68개: `3 failed, 65 passed in 19.19s`, rc=1. 하드 실패 3건은 확정이며, 두 신규 리뷰 중 하나가 지적한 `generated-artifact-index` 실패는 환경/상태 차이에 따라 4번째 잠재 실패로 보수적으로 취급한다.
- `release-source-package-check` 기본값: rc=2. `SOURCE_PACKAGE_EXTRACT_ROOT` 기본값이 작업 디렉터리 basename을 기대하는 구조이므로 archive root `LLMwiki`와 불일치한다.
- `release-source-package-check` override: rc=0. `current-fingerprint report 46096f5bd375…, nodeid_count=980, 975 passed, 5 skipped, 70 deselected i`. 이는 source ZIP payload 자체보다 checker default root가 문제임을 확인한다.

---

## 3. 두 신규 리뷰와 기존 리뷰의 관계

### 3.1 신규 리뷰 1: tri-review synthesis

신규 리뷰 1은 세 개의 이전 리뷰를 종합하는 형태이며, 특히 다음 강점이 있다.

- 기준 보고서 ZIP(`6731...`)과 현재 ZIP(`e9d9...`)의 식별자 차이를 명확히 분리한다.
- `artifact-freshness-check` schema-invalid 6건 해소와 `make check` 실패 지점 이동을 정확히 설명한다.
- `release-source-package-check` default fail / override pass를 P0로 끌어올린다.
- `auto-improve-readiness.json`의 `can_promote_result=true`를 promotion safety 문제로 다룬다.

보완점은 `fingerprint island`를 세 개 핵심 군집으로 요약했지만, 전체 `ops/reports/*.json` 스캔 기준으로는 raw-registry cross-environment 계열의 별도 fingerprint 군집도 존재한다는 점이다. 이 군집이 release-blocking인지 historical/cross-env evidence인지 정책적으로 분류해야 한다.

### 3.2 신규 리뷰 2: 현재 압축본 세 리뷰 통합 보고서

신규 리뷰 2는 실행 방법론과 리뷰 간 관점 차이를 더 명확하게 정리한다. 특히 다음 항목이 유용하다.

- selected contract 실패 수량을 3건과 4건 사이의 불확실성으로 보수 처리한다.
- path encoding 항목에서 “clean extract에서는 보존되지만 escaped storage path는 실제 존재한다”는 중간 결론을 제시한다.
- source-package default root 문제를 `Makefile` 기본값과 `release_archive_root_name` 정책 불일치로 구체화한다.
- P0/P1/P2 실행 순서를 자동화 런으로 옮기기 쉬운 형태로 정리한다.

보완점은 `make check`와 selected contract의 실제 실패 원인이 모두 “schema-invalid”가 아니라 “currentness/fingerprint chain drift”임을 최상위 메시지에서 더 강하게 분리해야 한다는 점이다.

### 3.3 기존 직전 리뷰와의 대조

직전 보고서(`llmwiki_current_zip_actual_crosscheck_update_report_20260509.md`)는 현재 ZIP의 실제 대조 결과를 이미 잘 포착했다. 두 신규 리뷰는 이를 더 상위 통합 보고서 형태로 재정리한 것이며, 핵심 판정은 대부분 일치한다.

| 항목 | 직전 리뷰 | 신규 리뷰 1 | 신규 리뷰 2 | 이번 판정 |
| --- | --- | --- | --- | --- |
| 현재 ZIP SHA/엔트리 | `e9d9...`, 2,029 | 동일 | 동일 | 동일 확인 |
| artifact freshness schema-invalid 6건 | 해소 | 해소 | 해소 | 해소 확정 |
| `make check` | 실패, writer output surface drift | 실패 | 실패 | P0 유지 |
| selected contracts | 3건 실패 중심 | 3~4건 실패 | 3~4건 실패 | 최소 3건 확정, 4번째 보수 추적 |
| source package default | 실패 / override pass | 실패 / override pass | 실패 / override pass | P0 유지 |
| auto-improve | 과낙관 | 과낙관 | 과낙관 | P0 유지 |
| path encoding | portability/provenance 보강 | alias/provenance 관리 | escaped path 실재 + clean extract 보존 | P1 유지 |

---

## 4. 현재 실제 파일 기준 핵심 판정

### 4.1 artifact freshness: 기존 P0는 닫힘

현재 checked-in `ops/reports/artifact-freshness-report.json` 및 새 `make artifact-freshness-check` 실행 모두 pass다.

| 필드 | 값 |
| --- | --- |
| status | `pass` |
| source_tree_fingerprint | `46096f5bd375efbb154b4de3e030962e56066dcfed546954d5bc8ad606bdfd0d` |
| generated_at | `2026-05-09T13:57:37Z` |
| 새 실행 rc | `0` |

두 신규 리뷰가 “schema-invalid 6건은 해소됨”으로 판정한 것은 실제 파일과 일치한다. 따라서 더 이상 `learning-claim-*` 6개 schema-invalid를 현재 P0로 유지하면 안 된다. 회귀 방지 대상으로만 남겨야 한다.

### 4.2 `make check`: 현재 P0의 직접 실패

`make check` 실패 원인은 `artifact-freshness-check`가 아니라 writer/generated contract drift다.

| 항목 | 값 |
| --- | --- |
| 실패 테스트 | `tests/test_writer_output_paths.py::WriterOutputPathsTest::test_script_output_surface_registry_matches_current_ast_inventory` |
| checked-in artifact | `ops/script-output-surfaces.json` |
| checked-in fingerprint | `cbc4850169b47e327db2bba41b0136b44e98327727ea187c44d1f730d1993998` |
| 현재 expected fingerprint | `46096f5bd375efbb154b4de3e030962e56066dcfed546954d5bc8ad606bdfd0d` |
| surfaces count | `196` |
| 성격 | surface 목록 오류가 아니라 envelope/currentness fingerprint drift |

개선은 `ops/script-output-surfaces.json`을 현재 source tree 기준 생성 target으로 재생성한 뒤 `make check`를 다시 통과시키는 순서가 맞다. JSON fingerprint만 수동으로 바꾸는 방식은 금지해야 한다.

### 4.3 selected contract: 최소 3건 실패, 4번째는 보수 추적

직전 전체 로그에서는 65 passed / 3 failed가 확인된다. 신규 리뷰 2는 64 passed / 4 failed 실행을 함께 반영했다. 따라서 운영적으로는 다음과 같이 처리해야 한다.

| 구분 | 테스트 | 상태 |
| --- | --- | --- |
| 확정 실패 | `test_checked_in_test_execution_summary_is_schema_backed_and_debt_free` | test target fingerprint mismatch |
| 확정 실패 | `test_checked_in_release_smoke_report_matches_live_envelope_fingerprints` | release-smoke stale fingerprint |
| 확정 실패 | `test_script_output_surface_registry_matches_current_ast_inventory` | script-output-surfaces stale fingerprint |
| 잠재/환경차 실패 | `test_checked_in_generated_artifact_index_matches_live_inventory_and_fingerprints` | generated-artifact-index stale 또는 family/path normalization drift |

selected contract를 68 passed로 만들기 전까지 release promotion은 차단해야 한다.

### 4.4 fingerprint islands: 핵심 release cluster는 세 군집, 광역 스캔은 네 군집

두 신규 리뷰는 핵심 release/generated artifact 관점에서 `46096f5b...`, `8c0d018c...`, `cbc48501...` 세 군집을 지적했다. 이번 전체 JSON 스캔에서는 raw-registry cross-environment 계열의 `45684aa3...` 군집도 별도로 관찰된다.

| fingerprint | artifact 수 | 대표 경로 |
| --- | --- | --- |
| 8c0d018ce4f1… | 24 | ops/reports/archive-execution-manifest.json, ops/reports/auto-improve-readiness.json, ops/reports/bootstrap-preflight-report.json, ops/reports/learning-claim-evidence-bundle.json, ops/reports/learning-claim-unlock-review.json, ops/reports/learning-confirmed-evidence-cohort.json … |
| 46096f5bd375… | 12 | ops/reports/artifact-freshness-report.json, ops/reports/defect-escape-closures.json, ops/reports/generated-artifact-index.json, ops/reports/manual-mutate-defect-registry.json, ops/reports/release-clean-blocker-ledger.json, ops/reports/release-closeout-batch-manifest.json … |
| 45684aa37911… | 4 | ops/reports/raw-registry-cross-environment-evidence-bundle.json, ops/reports/raw-registry-cross-environment-matrix-linux-c-utf8.json, ops/reports/raw-registry-cross-environment-matrix-macos-utf8.json, ops/reports/raw-registry-cross-environment-matrix-windows-utf8.json |
| 0650f21ee3f8… | 1 | ops/reports/openvex-draft.json |
| 07ec0b96606f… | 1 | ops/reports/release-closeout-fixed-point.json |
| 1dd874641849… | 1 | ops/reports/learning-readiness-signoff.json |
| 3b6450998d83… | 1 | ops/reports/promotion-decision-trends.json |
| 48171812f317… | 1 | ops/reports/structural-complexity-budget.json |
| 7ecf5dac85fe… | 1 | ops/reports/release-closeout-fixed-point-cost-trend.json |
| 8fcb3e3be389… | 1 | ops/reports/release-closeout-finality-attestation.json |
| 9c1d76dc7f64… | 1 | ops/reports/supply-chain-gate-report.json |
| ad91b944712a… | 1 | ops/reports/review-archive-report.json |
| be98e44ad2ca… | 1 | ops/reports/operator-release-summary.json |
| cbc4850169b4… | 1 | ops/script-output-surfaces.json |
| e2e6715a121d… | 1 | ops/reports/sbom-readiness-gate-report.json |
| e42cbf9a4630… | 1 | ops/reports/release-smoke-report-fast.json |

판정은 다음과 같다.

- P0: release/promotion authority에 직접 들어가는 artifacts가 서로 다른 fingerprint를 가리키는 문제는 즉시 차단해야 한다.
- P1: cross-environment evidence처럼 의도적으로 다른 환경 snapshot을 보존하는 artifact가 있다면 `historical`, `cross_env`, `non_release_blocking` 등 scope를 schema에 명시해야 한다.
- 금지: 단순히 여러 fingerprint가 있다는 이유만으로 모두 pass 처리하거나, 반대로 모든 historical/cross-env artifact를 무조건 blocking 처리하는 것. 필요한 것은 fingerprint island의 **정책적 분류와 release authority 연결**이다.

### 4.5 release authority: 보수화되었지만 truth ladder가 닫히지 않음

| artifact | 핵심 상태 |
| --- | --- |
| `release-closeout-summary.json` | `status=pass`, `clean_release_ready=False`, `source_tree_coherence.status=attention` |
| `release-evidence-dashboard.json` | `status=attention`, fp=`46096f5bd375...` |
| `release-closeout-batch-manifest.json` | `status=fail`, `machine_release_status=blocked`, `release_authority_status=conditional_pass` |
| `auto-improve-readiness.json` | `can_execute_trial=True`, `can_promote_result=True`, fp=`8c0d018ce4f1...` |

release authority가 과거처럼 완전한 clean pass를 주장하지는 않는다. 그러나 live `make check` 실패와 selected contract failure가 `auto-improve-readiness.json`의 `can_promote_result=false` 및 concrete `promotion_blockers[]`로 직접 연결되지 않는 문제가 남아 있다.

### 4.6 source package: ZIP 생성 정상, checker default가 P0

`make release-distribution-zip`으로 생성한 source ZIP은 정상이다.

| 항목 | 값 |
| --- | --- |
| source ZIP | `build/release/LLMwiki-source.zip` |
| SHA-256 | `bc988f2d1e52e34923915e59cf19b5885e5d816bce32e9a58419edd2434538fd` |
| size | 190,131,612 bytes |
| entries | 1468 |
| root prefixes | `LLMwiki` |

반면 `Makefile` 기본값은 다음 구조다.

```makefile
SOURCE_PACKAGE_EXTRACT_ROOT ?= $(SOURCE_PACKAGE_CHECK_ROOT)/extract/$(notdir $(abspath $(VAULT)))
```

현재 release ZIP 내부 root는 policy 기반 `LLMwiki`이다. 작업 디렉터리명이 `llmwiki_contract_work`, `llmwiki_two_reviews_deep_work`처럼 달라질 수 있으므로 기본값은 mismatch를 일으킨다. 두 신규 리뷰의 P0 판정이 맞다.

추가로, checked-in `ops/reports/source-package-clean-extract.json`은 `status=pass`지만 fingerprint `8c0d018ce4f1...`에 묶인 historical artifact다. override로 재생성된 동일 SHA 작업복사본의 최신 source-package report는 `current-fingerprint report 46096f5bd375…, nodeid_count=980, 975 passed, 5 skipped, 70 deselected i`였으므로, checked-in artifact를 release-current evidence로 사용하려면 재생성과 승격이 필요하다.

### 4.7 full-suite evidence: 1,039 vs 1,050 drift 유지

| 기준 | 값 |
| --- | ---: |
| checked-in `test-execution-summary-full.json` passed count | 1039 |
| checked-in nodeid_count | 1039 |
| 현재 fresh collect count | 1050 |
| Makefile expected count | 1,029 |

두 신규 리뷰가 말한 3중 drift(1,029 / 1,039 / 1,050)는 실제 파일과 일치한다. full-suite evidence는 P0 이후 현재 tree 기준으로 재생성해야 한다.

### 4.8 report-reference manifest: stale basis ZIP 유지

| 필드 | 값 |
| --- | --- |
| basis_zip | `{'name': 'LLMwiki.zip', 'sha256': '0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93', 'entry_count': 1819, 'source': 'reported'}` |
| current_distribution_zip | `{'name': '', 'sha256': '', 'entry_count': None, 'source': 'unspecified'}` |
| source_tree_fingerprint | `8c0d018ce4f15ddb443087e90d4a501817b65775b3b740d2beab51a6281f30d1` |

현재 manifest의 basis ZIP은 현재 업로드 ZIP도, repo-generated source ZIP도 아니다. sealed closeout에서는 computed distribution ZIP을 주입해 authoritative 값으로 재생성해야 한다.

---

## 5. 두 신규 리뷰 중 채택/보정할 사항

### 5.1 그대로 채택할 사항

| 항목 | 채택 이유 |
| --- | --- |
| schema-invalid 6건 해소 | 새 `artifact-freshness-check` 실행과 JSON 모두 pass다. |
| `make check` 실패 원인이 writer/generated contract drift로 이동 | 완료 로그와 `ops/script-output-surfaces.json` fingerprint가 일치한다. |
| selected contract 3~4건 실패 | 완료 로그상 3건 확정, 신규 리뷰 2의 4번째 지적은 보수 추적 가치가 있다. |
| source package default fail / override pass | Makefile 기본값과 script extract check 구조가 이를 설명한다. |
| auto-improve 과낙관 | `can_promote_result=true`, blockers empty 계열이 현재 failure와 충돌한다. |
| release ZIP root `LLMwiki` 정상 | 새 `make release-distribution-zip`로 재확인했다. |
| path encoding은 blocker가 아니라 provenance/normalization P1 | clean extract 보존과 escaped storage path 실재가 동시에 맞다. |

### 5.2 보정할 사항

| 항목 | 보정 판정 |
| --- | --- |
| selected contract 실패 수 | “3 또는 4”가 아니라 운영상 “최소 3 확정, 4번째 generated-artifact-index는 재실행 환경에서 반드시 확인할 잠재 P0”로 표현한다. |
| source-package checked-in pass | pass 자체는 사실이나 stale fingerprint에 묶여 release-current evidence가 아니다. override 재생성 결과와 차이가 있으므로 current chain 재생성이 필요하다. |
| fingerprint island | 핵심 release cluster는 세 군집이지만 전체 ops/reports 스캔에는 raw-registry cross-env 계열 별도 fingerprint도 있다. scope 분류를 추가해야 한다. |
| release authority status | `status=pass`와 `clean_release_ready=false`가 함께 존재하므로 top-level pass를 release-ready로 읽지 않도록 machine verdict vocabulary를 분리해야 한다. |
| 압축 관련 결론 | ZIP 생성 자체는 정상이다. 압축 관련 조치는 archive 생성보다 source-package checker default와 self-description 소비 로직에 집중한다. |

---

## 6. 개선 우선순위

### P0 — release/promotion blocker

| 번호 | 개선 항목 | 상세 조치 | 완료 기준 |
| --- | --- | --- | --- |
| P0-1 | `ops/script-output-surfaces.json` currentness 복구 | `make script-output-surfaces` 또는 해당 생성 스크립트로 재생성 후 승격 | `make check`의 writer output surface 테스트 통과 |
| P0-2 | selected contract 실패 해소 | test summary, release smoke, generated artifact index, script-output-surfaces를 동일 source snapshot에서 재생성 | selected contract 68 passed |
| P0-3 | source package checker default root 수정 | Makefile default를 policy/self-description archive root 기반으로 변경 | override 없이 `make release-source-package-check` 통과 |
| P0-4 | auto-improve promotion safety 보수화 | live fail/not-run, selected contract fail, stale artifact, source-package fail을 `promotion_blockers[]`로 기록 | fail/not-run 상태에서 `can_promote_result=false` |
| P0-5 | release dashboard truth ladder 연결 | `live_make_check` 또는 동등 release gate를 authoritative input으로 추가 | `make check` fail/not-run이면 machine release blocked |
| P0-6 | stale canonical artifact batch refresh | release-smoke, source-package-clean-extract, report-reference-manifest, test summaries, dashboard/closeout를 같은 chain에서 재생성 | release cluster fingerprint 정책 위반 없음 |

### P1 — release evidence completeness

| 번호 | 개선 항목 | 상세 조치 | 완료 기준 |
| --- | --- | --- | --- |
| P1-1 | full-suite evidence refresh | full collect/run summary를 현재 1,050 test tree 기준으로 재생성 | Makefile expected / checked-in summary / fresh collect 일치 |
| P1-2 | distribution ZIP 주입 | external manifest strict와 closeout batch manifest에 `build/release/LLMwiki-source.zip` 주입 | `distribution_package.status=bound/pass` 계열 |
| P1-3 | report-reference stale basis 제거 | reported default보다 computed current distribution ZIP 우선 | current_distribution_zip source가 computed |
| P1-4 | fingerprint island scope 분류 | historical/cross-env/current release artifact 구분 | release blocker와 non-blocking historical evidence 분리 |
| P1-5 | path alias/provenance normalization | `storage_path`, `display_path`, `canonical_reference_path`, `content_sha256` 기준 family 안정화 | escaped path가 index family drift를 만들지 않음 |
| P1-6 | release verdict vocabulary 정리 | `status=pass`와 `machine_release_ready` 분리 | 외부 소비자가 top-level status만으로 release 가능 오판하지 않음 |

### P2 — 유지보수성

| 번호 | 개선 항목 | 상세 조치 |
| --- | --- | --- |
| P2-1 | `vault_name` naming 잔재 정리 | archive helper parameter를 `archive_root_name`으로 정리 |
| P2-2 | 테스트 실패 메시지 개선 | surface mismatch / fingerprint mismatch / schema error를 구분 출력 |
| P2-3 | wiki_lint review candidate 정리 | P0/P1 이후 93건 후보 단계 정리 |
| P2-4 | platform path smoke 분리 | C locale/Info-ZIP path diagnostics를 warning과 blocker로 분리 |

---

## 7. 권장 자동화 실행 플랜

1. 기준선 고정: ZIP SHA/엔트리, 두 신규 리뷰, 기존 리뷰, 저장소 내부 기준 보고서, 현재 JSON artifact 값을 모두 기록한다.
2. P0 직접 실패 닫기: `ops/script-output-surfaces.json` 재생성 → `make static` → `make artifact-freshness-check` → `make check`.
3. stale generated artifacts 재생성: test-execution-summary, full summary, release-smoke, generated-artifact-index, source-package-clean-extract, report-reference-manifest를 현재 fingerprint chain에서 재생성한다.
4. source package 기본값 수정: `SOURCE_PACKAGE_EXTRACT_ROOT`가 policy/self-description archive root를 사용하도록 Makefile/script/test를 고친다.
5. promotion truth ladder 보수화: live gate fail/not-run, selected contract fail, source package fail, fingerprint island를 release dashboard와 auto-improve blockers에 연결한다.
6. sealed release evidence 재생성: distribution ZIP 주입, external manifest strict, release closeout sealed, lane summary, blocker ledger를 갱신한다.
7. DoD 반복 검증: 모든 P0/P1 조건이 통과할 때까지 같은 루프를 반복하고 최종 로그와 증거를 남긴다.

---

## 8. Codex용 자연어 goal prompt

아래 프롬프트는 Codex 자동화 런에 그대로 입력할 수 있도록 작성했다.

```text
너는 LLMwiki 저장소의 자동 개선 에이전트다. 현재 저장소 루트에서 사람의 추가 개입을 요구하지 말고, 실패 원인을 직접 조사하고 수정하고 검증하는 루프를 계속 실행하라. 목표는 현재 ZIP 기준 P0/P1 release-readiness 결함을 모두 닫는 것이다. 우선 `python -m venv .venv` 또는 사용 가능한 가상환경을 구성하고 `pip install -e '.[dev]'`를 완료한 뒤, `make static`, `make artifact-freshness-check`, `make check`, selected contract suite, `make release-distribution-zip`, `make release-source-package-check`, full-suite collect/run evidence, sealed closeout evidence를 반복 실행한다.

1차 목표는 `ops/script-output-surfaces.json`의 `source_tree_fingerprint` drift를 현재 source tree 기준으로 재생성하여 `make check`를 통과시키는 것이다. 단순 JSON 수동 편집으로 숫자만 맞추지 말고 저장소가 제공하는 생성 스크립트와 Makefile target을 사용하라. 2차 목표는 `ops/reports/test-execution-summary.json`, `ops/reports/test-execution-summary-full.json`, `ops/reports/release-smoke-report.json`, `ops/reports/generated-artifact-index.json`, `external-reports/report-reference-manifest.json`, `ops/reports/source-package-clean-extract.json`, release closeout/dashboard/lane artifacts를 같은 source tree fingerprint chain에서 재생성하여 selected contract 68개가 전부 통과하게 만드는 것이다. 3차 목표는 `SOURCE_PACKAGE_EXTRACT_ROOT` 기본값이 작업 디렉터리 basename이 아니라 `ops/policies/wiki-maintainer-policy.yaml`의 `release_packaging.archive_root_name` 또는 source ZIP 내부 `release-archive-self-description.json`의 archive root를 따르도록 Makefile/script/test를 수정하여 `make release-source-package-check`가 override 없이 통과하게 만드는 것이다.

promotion safety도 반드시 닫아라. live `make check`, selected contract failure, stale canonical artifact, source package check fail/not-run, fingerprint island가 하나라도 있으면 `auto-improve-readiness.json`의 `can_promote_result`가 false가 되고 `promotion_blockers`에 구체적인 blocker가 기록되도록 구현하라. release dashboard/closeout/lane summary는 live gate fail 또는 not-run을 clean release blocker로 반영해야 하며, `status=pass`와 `clean_release_ready=false`가 소비자를 혼동시키지 않도록 machine verdict 필드를 명확히 하라.

반복 루프의 Definition of Done은 다음과 같다: `make static` pass, `make artifact-freshness-check` pass 및 schema_invalid 0 유지, `make check` pass, selected contract 68개 pass, `make release-source-package-check` 기본값 pass, `pytest --collect-only -q` count와 checked-in full-suite summary 일치, repo-generated `build/release/LLMwiki-source.zip` root가 `LLMwiki`이고 smoke manifest comparison pass, release closeout batch manifest가 distribution ZIP bound 상태, external report reference manifest가 current distribution ZIP을 computed 값으로 기록, source package clean extract가 현재 fingerprint에서 pass, auto-improve가 fail/not-run 상태에서 promotion을 금지하고 모든 blocker를 기록, release 관련 canonical artifacts가 의도된 단일 current fingerprint policy로 수렴하는 것이다. 실패가 나오면 로그를 읽고 원인을 분류한 뒤 수정하고 같은 검증을 다시 실행하라. 모든 변경은 최소 범위로 수행하고, 매 반복마다 실행 명령·rc·핵심 로그·수정 파일·남은 blocker를 `ops/reports` 또는 명확한 요약 파일에 기록하라. 완료 후 최종 산출물로 변경 요약, 검증 명령 전체 목록, 통과 증거, 남은 known risk가 있으면 그 근거와 blocker 상태를 한국어로 작성하라.
```

---

## 9. 최종 Definition of Done

| # | 완료 조건 | 우선순위 |
| ---: | --- | --- |
| 1 | `make static` 통과 | P0 |
| 2 | `make artifact-freshness-check` 통과 및 `schema_invalid_artifact_count=0` 유지 | P0 |
| 3 | `make check` 통과 | P0 |
| 4 | selected contract 68개 전부 통과 | P0 |
| 5 | `ops/script-output-surfaces.json`이 live AST inventory와 fingerprint까지 일치 | P0 |
| 6 | `make release-source-package-check`가 override 없이 통과 | P0 |
| 7 | `auto-improve-readiness.json`이 fail/not-run 상태에서 `can_promote_result=false`를 표시 | P0 |
| 8 | release dashboard/closeout/lane summary가 live gate fail/not-run을 machine blocker로 반영 | P0 |
| 9 | full-suite collect/run summary가 현재 1,050 test tree와 일치 | P1 |
| 10 | source package clean extract가 현재 fingerprint chain에서 pass | P1 |
| 11 | `build/release/LLMwiki-source.zip` root가 `LLMwiki`이고 smoke manifest comparison pass | P0 |
| 12 | closeout batch manifest가 distribution ZIP을 bound 상태로 포함 | P1 |
| 13 | external report reference manifest가 current distribution ZIP을 computed 값으로 기록 | P1 |
| 14 | release-current canonical artifacts가 의도된 단일 fingerprint policy로 수렴 | P1 |
| 15 | historical/cross-env fingerprint islands가 명시적 scope로 분류되어 release authority가 오판하지 않음 | P1 |

---

## 10. 최종 권고

두 신규 리뷰는 대체로 정확하며, 직전 리뷰 및 실제 파일과도 핵심 진단이 일치한다. 다만 현재 조치의 초점은 더 이상 `artifact-freshness-check` schema-invalid 6건이 아니다. 현재의 핵심은 **currentness/fingerprint chain, source package default root, promotion truth ladder**다.

따라서 Codex 자동화 런은 단일 artifact를 손으로 고치는 방식이 아니라 다음 폐루프를 반복해야 한다.

```bash
make script-output-surfaces
make static
make artifact-freshness-check
make check
python -m pytest -q -o addopts= \
  tests/test_generated_report_contracts.py \
  tests/test_writer_output_paths.py \
  tests/test_import_fallback_contract.py \
  tests/test_script_module_surface_contract.py
make release-distribution-zip
make release-source-package-check
make external-report-reference-manifest-strict \
  EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH=build/release/LLMwiki-source.zip
make release-evidence-closeout-sealed
make auto-improve-readiness
make release-evidence-dashboard
make release-lane-summary
```

각 단계가 실패하면 실패 로그를 읽고 소스/Makefile/test/schema를 수정한 뒤 같은 루프를 다시 실행해야 한다. 최종적으로 P0/P1 DoD가 모두 충족되기 전까지 `can_promote_result=true` 또는 release-ready 표현을 허용하면 안 된다.
