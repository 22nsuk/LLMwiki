# LLMwiki 2026-05-11 두 통합 리뷰 실제 파일 대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-11 KST |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_two_20260511_reviews_crosscheck_improvement_report_20260511.md` |
| 직접 검토한 신규 리뷰 1 | `llmwiki_integrated_review_synthesis_report_20260511.md` |
| 직접 검토한 신규 리뷰 2 | `llmwiki_integrated_review_20260511.md` |
| 기존 비교 리뷰 | `llmwiki_current_zip_vs_20260510_crosscheck_improvement_report_20260511.md` |
| 저장소 내부 기존 보고서 | `external-reports/llmwiki_integrated_reviews_actual_file_crosscheck_improvement_report_20260510.md` |
| 실제 대조 ZIP | `/mnt/data/LLMwiki.zip` |
| 실제 ZIP SHA-256 | `2dec4e575ed73a1441478c896f9a2b73d5adff31e2ca20ac55962db63a79c4af` |
| 실제 ZIP entries | 전체 2102, 파일 1985, 디렉터리 117 |
| 최종 한줄 판정 | **두 신규 리뷰는 현재 체크포인트의 큰 방향을 잘 통합했지만, 실제 clean 추출본 재검증 결과 `aa21958e...`가 현재 clean live fingerprint로 재확인되었고 `make test-artifact-finalization`도 6/6 통과한다. 따라서 최우선 개선안은 “authoritative fingerprint가 아직 미확정”이라는 일반론보다, `aa21958e...` clean baseline을 기준으로 batch manifest distribution binding, source-tree coherence divergence, full-suite 1103/1107 재봉인, 외부보고서 lifecycle 갱신을 닫는 쪽으로 좁혀야 한다.** |

---

## 0. 검토 범위와 방법

이번 대조는 다음 네 층위를 분리하여 수행했다.

1. **두 신규 리뷰의 문장·표·우선순위**: 두 문서는 모두 2026-05-11 동일 ZIP 체크포인트를 대상으로 한 3개 선행 리뷰의 통합본이다. 즉 두 문서는 primary 실행 로그라기보다 secondary synthesis에 가깝다.
2. **기존 리뷰/보고서와의 대조**: 직전 산출물인 `llmwiki_current_zip_vs_20260510_crosscheck_improvement_report_20260511.md` 및 저장소 내부 2026-05-10 보고서를 함께 비교했다.
3. **실제 압축 파일 대조**: `/mnt/data/LLMwiki.zip`을 clean 추출하여 ZIP 중앙 디렉터리, prefix/확장자 분포, 주요 JSON artifact, Makefile 변수, fingerprint runtime 코드를 확인했다.
4. **가능한 범위의 재실행 검증**: 현재 런타임의 단일 tool 실행 상한 때문에 “타임아웃 제한 없는 전체 검증”은 수행할 수 없었다. 대신 60초 내 완료 가능한 핵심 게이트를 직접 재실행하고, 장시간 full-suite refresh/static 완전 봉인은 보고서의 한계로 명시했다.

중요한 전제: 사용자가 말한 “압축 파일은 저장소를 그대로 압축한 원본 파일”이라는 조건은 그대로 반영했다. 따라서 `tmp/`, `runs/`, `external-reports/`가 raw repository snapshot에 포함된 사실 자체를 release packaging 결함으로 보지 않았다. release ZIP 생성 경로가 이를 어떻게 제외하는지만 확인했다.

---

## 1. 실제 ZIP inventory

### 1.1 ZIP 물리 메타데이터

| 항목 | 실제 값 |
| --- | ---: |
| SHA-256 | `2dec4e575ed73a1441478c896f9a2b73d5adff31e2ca20ac55962db63a79c4af` |
| 파일 크기 | 192,874,516 bytes |
| 전체 entries | 2,102 |
| 파일 entries | 1,985 |
| 디렉터리 entries | 117 |

두 신규 리뷰가 공통으로 기록한 `2dec4e57...`, 2,102 entries, 1,985 files, 117 dirs는 실제 ZIP과 일치한다. 2026-05-10 내부 보고서가 기준으로 삼은 `13fc833c...`, 2,071 entries 계열 수치는 현재 ZIP에는 더 이상 적용하면 안 된다.

### 1.2 prefix별 파일 수

| prefix | 파일 수 |
| ops/ | 481 |
| raw/ | 446 |
| wiki/ | 417 |
| runs/ | 263 |
| tests/ | 173 |
| system/ | 71 |
| external-reports/ | 63 |
| tmp/ | 28 |
| root files | 18 |
| .codex/ | 10 |
| tools/ | 6 |
| .obsidian/ | 5 |
| .github/ | 2 |
| .ouroboros/ | 1 |
| .vscode/ | 1 |

### 1.3 확장자별 파일 수

| 확장자 | 파일 수 |
| .md | 981 |
| .json | 461 |
| .py | 381 |
| .pdf | 62 |
| .txt | 44 |
| .yaml | 18 |
| .jsonl | 16 |
| .toml | 11 |
| (none) | 5 |
| .yml | 2 |
| .docx | 2 |
| .ini | 1 |
| .lock | 1 |

### 1.4 external-reports / tmp 상태

| 항목 | 실제 값 |
| --- | ---: |
| `external-reports/` root active files | 2 |
| `external-reports/archive/` files | 61 |
| `tmp/` files | 28 |

실제 root active external report는 다음 2개뿐이다.

- `external-reports/llmwiki_integrated_reviews_actual_file_crosscheck_improvement_report_20260510.md`
- `external-reports/report-reference-manifest.json`

따라서 두 신규 리뷰가 말한 “external report lifecycle은 개선되었고 archive candidate 5건 문제는 해소됨”은 실제 파일과 일치한다. 다만 새로 작성되는 본 보고서까지 active root에 편입한다면 기존 active narrative report와의 superseded 관계를 명시해야 한다.

---

## 2. 직접 재검증 결과

| 검증 | 본 작업 결과 | 관측값 | 해석 |
| `release_source_tree_fingerprint(Path('.'))` | 통과 | `aa21958e10047d0690e6bd90508c2b59860bb1b75e416ac3888b6440a5a9c370` | clean 추출본에서 직접 계산 |
| `make test-artifact-finalization` | 통과 | `6 passed` | clean 추출본 기준. 두 새 리뷰의 R3 관측과 일치 |
| `make artifact-freshness-check` | 통과 | `tmp/artifact-freshness-report-check.json` 생성 | exit code 0 |
| `make release-distribution-zip` | 통과 | `build/release/LLMwiki-source.zip`, 1497 entries, SHA `ccd91362fb32...` | release ZIP 생성 로직 정상, `tmp/`·`external-reports/` 제외 |
| `python3 -m pytest -o addopts= --collect-only -q --capture=no` | 통과 | `1107 tests collected` | checked-in full summary 1103과 4개 차이 |
| `make static` | 미봉인 | 이번 작업의 tool 실행 상한 때문에 fresh exit code를 끝까지 봉인하지 않음 | 두 업로드 리뷰와 기존 보고서의 pass 관측은 보존하되, 본 보고서의 신규 직접 검증값으로는 세지 않음 |

### 2.1 이번 직접 검증의 핵심 의미

- clean 추출본 기준 live fingerprint는 `aa21958e10047d0690e6bd90508c2b59860bb1b75e416ac3888b6440a5a9c370`이다.
- `make test-artifact-finalization`은 현재 clean 추출본에서 6개 모두 통과했다.
- `make release-distribution-zip`은 정상 동작하며 `tmp/`와 `external-reports/`를 release ZIP에 포함하지 않는다.
- selector-free collect-only는 1,107 tests를 수집하므로 checked-in full summary 1,103과의 차이는 여전히 남아 있다.
- Python startup stderr에 `Spreadsheet runtime warmup failed ... hydrateCrdtFromProto requires an empty collaborative document` 잡음이 반복되었지만, 위 핵심 명령들의 exit code에는 영향을 주지 않았다.

---

## 3. 두 신규 리뷰의 주요 주장별 실제 파일 대조

| 쟁점 | 두 신규 리뷰의 주장 | 실제 파일/직접 검증 | 판정 | 보정 필요 |
| --- | --- | --- | --- | --- |
| ZIP 동일성 | 두 리뷰 모두 `2dec4e57...` ZIP, 2,102 entries로 본다 | 실제 ZIP SHA/entry 수와 일치 | 정확 | 없음 |
| 2026-05-10 보고서의 ZIP 수치 | 기존 `13fc833c...`/2,071 entries는 과거 기준 | 실제 현재 ZIP과 다름 | 정확 | 기존 보고서는 superseded 처리 필요 |
| clean machine release-ready | machine clean release-ready 아님 | `release-closeout-summary`: `clean_release_ready=false`, `machine_release_allowed=false`, `conditional_pass` | 정확 | operator/machine lane 문구 분리 유지 |
| batch manifest binding | `distribution_package.status=not_provided`, machine blocked | 실제 `release-closeout-batch-manifest`도 동일 | 정확 | 최상위 P0 유지 |
| auto-improve 과낙관 | `can_promote_result=false`로 개선, 다만 next_action 문구 개선 필요 | 실제 `can_execute_trial=true`, `can_promote_result=false`, blockers 2개 | 정확 | next_action 첫 문장에 promotion 금지 명시 |
| generated artifact index | `archive_candidate_count=0`으로 해결 | 실제 summary `archive_candidate_count=0`, `canonical_report_count=71` | 정확 | 새 보고서 편입 시 lifecycle만 갱신 |
| full-suite node count | 현재는 1103 vs 1107 문제 | checked-in full summary 1103, 직접 collect-only 1107 | 정확 | full refresh 필요 |
| `test-artifact-finalization` | R1/R2는 2 fail, R3는 6 pass로 환경 의존 | 본 clean 추출본은 6 pass | 부분 보정 | “현재 clean baseline에서는 pass”로 한 단계 좁혀야 함 |
| live fingerprint | R1/R2 `770994fd...`, R3 `aa21958e...`; authoritative 미확정 | 본 clean 추출본 직접 계산도 `aa21958e...` | 부분 보정 | “clean authoritative 후보 미확정”이 아니라 “clean baseline은 `aa21958e...`; `770...` 발생 조건을 규명”으로 수정 |
| release ZIP 생성 | 생성 자체 정상, 다만 SHA identity가 리뷰별/manifest별로 다름 | 본 생성 ZIP SHA `ccd91362fb3203eb56c0436385d3356783011d8067419858609ed219afb15f5f`, entries 1497; manifest `17800a.../1494`와 다름 | 정확 | 같은 build artifact를 external manifest와 batch manifest에 동시 바인딩 |
| raw snapshot ZIP vs release ZIP | 둘을 혼용하지 말아야 함 | raw ZIP은 1,985 files, release ZIP은 1497 files이며 `tmp/`·`external-reports/` 제외 | 정확 | Makefile 변수명/manifest 용어 개선 필요 |
| source-tree coherence | 여러 fingerprint cohort 공존 | closeout summary 4개 cohort, release evidence cohort 3개 cohort | 정확 | 두 artifact의 component count를 구분해서 표기 |

---

## 4. 기존 리뷰/보고서 대비 판정 갱신

### 4.1 2026-05-10 내부 보고서의 현재 효력

2026-05-10 내부 보고서는 당시 ZIP에 대해 다음 지적을 했다.

- `d0c6a3...`가 당시 실제 ZIP live truth로 재현됨
- `make test-artifact-finalization` 2 fail / 4 pass
- `generated-artifact-index` archive candidate 5건
- `auto-improve-readiness`의 promotion gate 과낙관
- full-suite node count 축 1086/1092
- distribution binding 누락 및 release evidence 단일 cohort 미달성

현재 ZIP 기준으로는 이 중 일부가 명확히 폐기된다.

| 2026-05-10 보고서 항목 | 현재 실제 판정 |
| --- | --- |
| `d0c6a3...` 중심 live truth | 폐기. 현재 clean truth는 `aa21958e...` |
| `test-artifact-finalization` 2 fail | clean 현재 ZIP 기준 폐기. 직접 재실행 6 pass |
| archive candidate 5건 | 폐기. 실제 `archive_candidate_count=0` |
| `can_promote_result=true` 과낙관 | 폐기. 실제 `can_promote_result=false` |
| 1086/1092 node count | 폐기. 현재는 1103/1107 축 |
| machine clean release-ready 아님 | 유지 |
| distribution package binding 누락 | 유지 |
| source-tree coherence split | 유지 및 강화 |
| release ZIP 생성 자체 정상 | 유지 |
| alias/output surface를 기존 runtime과 연결해야 한다는 방향 | 유지 |

### 4.2 직전 기존 리뷰(`llmwiki_current_zip_vs_20260510...`)와의 관계

직전 기존 리뷰는 현재 clean ZIP 기준에서 `aa21958e...`와 `make test-artifact-finalization` 6 pass를 이미 더 강하게 판정했다. 이번 직접 재검증도 이쪽에 더 가깝다. 따라서 두 신규 리뷰가 말한 “authoritative fingerprint가 아직 `aa...`인지 `770...`인지 명확하지 않다”는 문장은, 현재 clean baseline 증거까지 반영하면 다음처럼 고쳐야 한다.

> clean repository snapshot 기준 authoritative fingerprint는 `aa21958e...`로 재현된다. 남은 문제는 `770994fd...`를 낳은 R1/R2 실행 조건이 실제 release-builder에서 재현되는지, 또는 특정 command/path basis 차이인지 규명하는 것이다.

이 보정은 두 신규 리뷰의 가치를 낮추는 것이 아니라, 그들이 “핵심 불일치”로 표시한 영역을 실제 파일 기준으로 한 단계 더 좁히는 것이다.

---

## 5. 실제 주요 artifact 상태

| artifact | actual status | actual fingerprint/cohort | 핵심 실제값 |
| `ops/reports/release-closeout-summary.json` | pass | aa21958e10... | clean_release_ready=False, machine_release_allowed=False, release_readiness_state=conditional_pass, blocker_count=2, source_tree_coherence=attention, component_fingerprint_count=4 |
| `ops/reports/release-closeout-batch-manifest.json` | fail | aa21958e10... | distribution_package.status=not_provided, sealed_release_status=unsealed_distribution_not_provided, machine_release_status=blocked, clean_lane_status=fail |
| `ops/reports/release-smoke-report.json` | pass | aa21958e10... | packed_file_count=1497 |
| `ops/reports/artifact-freshness-report.json` | pass | aa21958e10... | artifact_count=290, schema_invalid=None, stale=None |
| `ops/reports/generated-artifact-index.json` | pass | aa21958e10... | archive_candidate_count=0, canonical_report_count=71, external root/archive=2/61 |
| `ops/reports/auto-improve-readiness.json` | (boolean gate) | aa21958e10... | can_execute_trial=True, can_promote_result=False, promotion_blockers=2 |
| `ops/reports/test-execution-summary.json` | pass | aa21958e10... | counts={'passed': 150, 'failed': 0, 'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'warnings': 0}, collect_nodeids=150 |
| `ops/reports/test-execution-summary-full.json` | pass | 473466b792... | counts={'passed': 1103, 'failed': 0, 'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'warnings': 0}, collect_nodeids=1103 |
| `ops/reports/release-evidence-cohort.json` | attention | aa21958e10... | strict_same_fingerprint=False, component_fingerprint_count=3, clean_lane_contract_status=fail |
| `ops/reports/release-clean-blocker-ledger.json` | attention | aa21958e10... | blocker_count=1, clean_lane_status=fail, conditional_lane_status=pass |
| `external-reports/report-reference-manifest.json` | (manifest) | d0e782d18e... | basis_current_match=basis_current_match, basis_sha=17800a7b73..., entries=1494 |
| `ops/reports/external-report-action-matrix.json` | attention | 05c38824a5... | implemented=6, requires_release_run_verification=4 |

### 5.1 closeout summary와 evidence cohort의 component count 구분

두 신규 리뷰는 source-tree coherence를 “4개 fingerprint cohort”로 설명한다. 이 설명은 `release-closeout-summary.json` 기준으로 맞다.

반면 `release-evidence-cohort.json`의 summary는 다음과 같다.

- `strict_same_fingerprint=false`
- `component_fingerprint_count=3`
- `clean_lane_contract_status=fail`

즉 보고서 문장에서는 다음처럼 구분하는 편이 더 정확하다.

- **release-closeout-summary source_tree_coherence**: 4개 fingerprint cohort
- **release-evidence-cohort summary**: 3개 fingerprint cohort

두 숫자를 하나로 뭉뚱그려 “3 또는 4”라고만 쓰면 operator가 어느 artifact를 재생성해야 하는지 흐려진다.

---

## 6. fingerprint 쟁점의 보정

### 6.1 두 신규 리뷰가 맞게 본 것

두 신규 리뷰는 다음 점을 정확히 포착했다.

- checked-in currentness 중심 cohort는 `aa21958e...`다.
- `test-execution-summary-full.json`은 `473466b7...` 별도 cohort다.
- `external-reports/report-reference-manifest.json`은 `d0e782d1...` 별도 cohort다.
- `source-package-clean-extract.json` 계열은 `74416971...` older clean-extract cohort다.
- finality/fixed-point 계열에는 `a4f74630...`, `edd5e25c...` 같은 별도 fingerprint가 있다.
- clean lane이 막히는 핵심은 단순 pass/fail보다 source-tree evidence가 strict single cohort로 닫히지 않은 데 있다.

### 6.2 두 신규 리뷰가 보정해야 할 것

`llmwiki_integrated_review_20260511.md`는 R1/R2의 `770994fd...` 원인을 설명하며, fingerprint 함수가 `.venv/`, `__pycache__/`, `tmp/` 산출물 등을 포함할 수 있다고 추정한다. 그러나 실제 코드 `ops/scripts/source_tree_fingerprint_runtime.py`와 `ops/scripts/wiki_manifest.py` 기준으로는 다음이 제외된다.

- excluded prefixes: `ops/reports/`, `external-reports/`, `review/`, `runs/`, `tmp/`, `build/`, `dist/`, `.venv/`, `.venv-`, `.coverage`
- excluded cache/dev hidden directories: `__pycache__`, `.cache`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.eggs`, `.git`, `.hypothesis`, `.idea`, `.nox`, `.obsidian`, `.tox`, `.venv`, `.vscode`
- excluded suffixes: `.pyc`, `.pyo`, `:Zone.Identifier`

또한 fingerprint payload는 path, sha256, size 중심의 manifest를 해시하며, mtime은 캐시 signature에 쓰이지만 최종 fingerprint payload에는 들어가지 않는다. 따라서 `770994fd...`는 단순히 `.venv`나 `tmp` 생성 때문이라고 보기 어렵다. 더 가능성이 높은 원인은 다음 중 하나다.

1. R1/R2가 실제로는 현재 clean ZIP과 다른 파일 상태를 가진 추출 디렉터리를 사용했을 가능성.
2. release source manifest에 포함되는 non-excluded source 파일이 command 실행 과정에서 변경되었을 가능성.
3. path alias, Makefile basis 변수, 또는 외부 report/current distribution ZIP identity가 섞인 별도 계산값을 live fingerprint로 해석했을 가능성.
4. 리뷰 문서 작성 시 R1/R2의 후보 JSON 또는 smoke candidate fingerprint를 clean source-tree fingerprint와 같은 층위로 병합했을 가능성.

### 6.3 보정된 결론

두 신규 리뷰의 P0-1은 다음처럼 고치는 것이 더 정확하다.

| 기존 신규 리뷰식 표현 | 실제 파일 대조 후 보정 표현 |
| --- | --- |
| authoritative live fingerprint가 `aa21958e...`인지 `770994fd...`인지 명확하지 않다 | clean 추출본 기준 authoritative source-tree fingerprint는 `aa21958e...`로 재현된다 |
| `.venv/tmp/cache` 오염 가능성이 주요 원인일 수 있다 | 해당 표면은 이미 exclusion policy에 포함되어 있으므로, `770994fd...` 발생 조건은 non-excluded 파일 변화 또는 basis 혼용 관점에서 재조사해야 한다 |
| finalization은 환경 의존적으로 2 fail/6 pass가 갈린다 | 현재 clean ZIP 기준 finalization은 6 pass다. 다만 R1/R2의 실패 관측은 release-builder/post-command 환경 회귀 테스트로 보존해야 한다 |

---

## 7. release ZIP / raw snapshot ZIP 구분

실제 raw snapshot ZIP과 release distribution ZIP은 아래처럼 다르다.

| 항목 | raw repository snapshot ZIP | release distribution ZIP |
| --- | ---: | ---: |
| 경로 | `/mnt/data/LLMwiki.zip` | `build/release/LLMwiki-source.zip` |
| SHA-256 | `2dec4e575ed73a1441478c896f9a2b73d5adff31e2ca20ac55962db63a79c4af` | `ccd91362fb3203eb56c0436385d3356783011d8067419858609ed219afb15f5f` |
| 파일 수 | 1985 | 1497 |
| 디렉터리 entries | 117 | 0 |
| `tmp/` 포함 | yes, 28 files | false |
| `external-reports/` 포함 | yes, 63 files | false |
| 용도 | 저장소 전체 snapshot 검토 | source-oriented release package |

두 신규 리뷰가 “압축 관련 내용은 저장소가 어떻게 생성하도록 되어 있는지만 확인하면 된다”는 요청 취지에 맞게 release ZIP 생성 자체를 문제 삼지 않은 것은 정확하다. 실제로 `make release-distribution-zip`은 통과했고 manifest comparison도 pass였다.

다만 개선해야 할 점은 여전히 있다. `external-reports/report-reference-manifest.json`은 `17800a7b.../1494 entries`를 basis/current distribution ZIP으로 기록하고 있는데, 이번 재생성 release ZIP은 `ccd91362fb32.../1497 entries`다. 또한 Makefile 기본 변수는 여전히 다음 값을 가진다.

| Makefile 변수 | 현재 기본값 |
| --- | --- |
| `EXTERNAL_REPORT_BASIS_ZIP_NAME` | `LLMwiki.zip` |
| `EXTERNAL_REPORT_BASIS_ZIP_SHA256` | `0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93` |
| `EXTERNAL_REPORT_BASIS_ZIP_ENTRY_COUNT` | `1819` |
| `TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT` | `1103` |

즉 release ZIP 생성 로직은 정상이나, **어떤 distribution ZIP identity를 external report manifest와 batch manifest에 authoritative로 봉인할지**는 아직 닫히지 않았다.

---

## 8. full-suite evidence와 node count

두 신규 리뷰의 “1086/1092가 아니라 1103/1107 문제”라는 판정은 실제 파일과 직접 검증 모두에 부합한다.

| 항목 | 값 |
| --- | ---: |
| Makefile expected | 1103 |
| checked-in full summary collected nodeids | 1103 |
| checked-in full summary passed | 1103 |
| 직접 collect-only | 1107 |

다만 collect-only 1107은 “full-suite pass”가 아니다. 실제 개선은 `make test-execution-summary-full-refresh` 또는 동등한 release-builder entrypoint를 장시간 실행 가능한 환경에서 완료하고, 그 결과가 1103인지 1107인지 봉인하는 방식이어야 한다.

---

## 9. external report action matrix 대조

실제 `ops/reports/external-report-action-matrix.json`의 summary는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| active_report_count | 2 |
| archived_report_count | 58 |
| action_item_count | 10 |
| implemented_count | 6 |
| requires_release_run_verification_count | 4 |
| unmatched_active_report_count | 0 |

| action_id | priority | status | target |
| script_output_surfaces_currentness | P0 | implemented | script-output-surfaces |
| release_writer_dependency_single_source | P0 | implemented | release-workflow-order-guard |
| function_budget_proposal_adapter | P1 | implemented | function-budget-refactor-proposals |
| windows_path_and_archive_alias_parity | P1 | implemented | test-public |
| outcome_provenance_gate_policy | P2 | implemented | outcome-provenance-gate-policy |
| external_report_lifecycle | P1 | implemented | external-report-action-matrix |
| source_package_distribution_binding | P0 | requires_release_run_verification | release-source-package-check |
| release_evidence_bundle_and_attestation | P1 | requires_release_run_verification | release-evidence-closeout-sealed-dry-run |
| full_suite_evidence_currentness | P1 | requires_release_run_verification | test-execution-summary-full-refresh |
| promotion_truth_ladder | P0 | requires_release_run_verification | auto-improve-readiness-report |

두 신규 리뷰가 “10개 action 중 6개 implemented, 4개 requires_release_run_verification”이라고 요약한 내용은 실제 파일과 일치한다. 다만 path는 반드시 `ops/reports/external-report-action-matrix.json`로 써야 한다. 일부 문맥에서 `external-report-action-matrix.json`라고만 쓰면 `external-reports/` 아래 파일로 오해될 수 있다.

---

## 10. 개선 방안

### P0-1. clean baseline 확정 표현을 갱신한다

**현재 상태:** 본 clean 추출본에서 `release_source_tree_fingerprint(Path("."))`는 `aa21958e...`로 재현되며, `make test-artifact-finalization`도 6 pass다.

**개선:** 기존 신규 리뷰의 P0-1 제목을 “authoritative fingerprint 확정”에서 “clean baseline `aa21958e...` 재확인 및 `770994fd...` 발생 조건 회귀 격리”로 바꾼다.

**완료 기준:**
- clean extraction job과 post-install/post-make job을 분리해 둘 다 fingerprint를 기록한다.
- post-install/post-make에서도 `aa21958e...`가 나오면 R1/R2의 `770...` 관측은 historical/환경 차이로 archive한다.
- `770...`가 재현되면 non-excluded changed file list를 manifest diff로 출력한다.

### P0-2. release-closeout-batch-manifest에 실제 distribution ZIP을 바인딩한다

**현재 상태:** `release-closeout-batch-manifest.json`은 `status=fail`, `distribution_package.status=not_provided`, `sealed_release_status=unsealed_distribution_not_provided`다.

**개선:** `make release-distribution-zip`으로 생성한 동일 ZIP을 `release-closeout-batch-manifest-promote`와 `external-report-reference-manifest`에 모두 입력한다. 같은 build artifact를 두 manifest가 참조해야 한다.

**완료 기준:**
- batch manifest `status=pass`
- `distribution_package.status`가 materialized/bound 상태로 전환
- `sealed_release_status`가 clean pass 계열로 전환
- auto-improve promotion blockers에서 batch manifest blocker 제거

### P0-3. release evidence cohort / closeout summary divergence를 분리해서 닫는다

**현재 상태:** closeout summary는 4개 fingerprint cohort, release evidence cohort는 3개 fingerprint cohort를 가진다.

**개선:** 재생성 가능한 currentness artifact는 `aa21958e...` 기준으로 재봉인하고, full-suite 및 external manifest처럼 별도 cohort로 남길 것들은 accepted-risk가 아니라 명시 정책으로 분리한다.

**완료 기준:**
- clean lane을 목표로 하면 strict single cohort를 달성한다.
- 조건부 lane을 유지한다면 divergence 대상, 이유, 만료일, 재검증 command가 dashboard/ledger에 분명히 남는다.

### P0-4. full-suite evidence를 현재 inventory로 재봉인한다

**현재 상태:** checked-in full summary는 1103, 직접 collect-only는 1107이다.

**개선:** 장시간 release-builder 환경에서 full summary refresh를 완료한다. 결과가 1107이면 Makefile expected와 checked-in summary를 함께 갱신한다. 결과가 1103이면 collect-only와 full summary의 selector/environment 차이를 문서화한다.

**완료 기준:**
- Makefile expected count와 refreshed full summary nodeid_count 일치
- collect-only digest 및 outcome consistency pass
- full-suite evidence가 release evidence cohort에 올바르게 반영됨

### P0-5. external report manifest와 Makefile basis 변수를 현 release identity로 정렬한다

**현재 상태:** `report-reference-manifest.json`은 `17800a7b.../1494`를 basis/current match로 기록하고, Makefile 기본 basis는 `0a547950.../1819`다. 본 작업 재생성 release ZIP은 `ccd91362fb32.../1497`다.

**개선:** raw snapshot basis, external-review basis, release distribution current basis를 변수명과 manifest 필드에서 분리한다.

**완료 기준:**
- raw repository snapshot ZIP과 source release ZIP이 같은 필드에 섞이지 않는다.
- `EXTERNAL_REPORT_BASIS_*` 변수의 의미가 “historical review basis”인지 “current release distribution”인지 명확해진다.
- current distribution ZIP을 자동 계산하거나, 수동 입력이면 누락 시 fail-fast한다.

### P1-1. auto-improve next_action 문구를 trial/promotion으로 분리한다

**현재 상태:** `can_execute_trial=true`, `can_promote_result=false`가 동시에 존재한다. machine gate는 안전하지만 human reader가 next_action만 보면 promotion 금지를 놓칠 수 있다.

**개선:** 다음 구조를 권장한다.

- `trial_next_action`: bounded live auto-improve trial 실행 가능
- `promotion_next_action`: release blockers 해소 전 promotion 금지
- top-level `next_action`: promotion blockers가 있으면 첫 문장에 “trial only; do not promote” 표시

### P1-2. 새 외부 보고서 lifecycle을 action matrix에 편입한다

본 보고서가 저장소에 들어갈 경우 다음이 필요하다.

- 기존 `external-reports/llmwiki_integrated_reviews_actual_file_crosscheck_improvement_report_20260510.md`를 superseded 또는 historical basis로 표시
- 새 active report가 root에 남는다면 active_report_count/archived_report_count 갱신
- `ops/reports/external-report-action-matrix.json` 재생성
- `report-reference-manifest.json`의 basis/current identity 갱신

### P1-3. release ZIP reproducibility를 문서화한다

세 리뷰와 본 작업에서 생성된 release ZIP SHA가 서로 다르다. entry count와 manifest comparison은 정상인데 SHA가 달라지는 것은 timestamp/metadata 때문일 수 있다.

**개선:** “byte-for-byte reproducible ZIP”을 요구할지, 아니면 “content manifest reproducible”만 요구할지 정책을 분리한다.

### P2-1. 2026-05-10 보고서를 superseded 처리한다

기존 보고서는 방향성 일부가 유효하지만 수치가 많이 바뀌었다. active root에 계속 둘 경우 operator가 오래된 P0를 다시 수행할 위험이 있다.

**개선:** 보고서 상단에 “현재 ZIP `2dec4e57...` 기준 superseded” 배너를 추가하거나 archive로 이동한다.

---

## 11. 권장 실행 순서

```bash
# 1. clean source-tree fingerprint 재확인
python - <<'PY'
from pathlib import Path
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint
print(release_source_tree_fingerprint(Path(".")))
PY
# 기대값: aa21958e10047d0690e6bd90508c2b59860bb1b75e416ac3888b6440a5a9c370

# 2. 임시 산출물 정리
make tmp-json-clean

# 3. 현재 source 기준 release distribution 생성
make release-distribution-zip

# 4. 같은 release ZIP을 external report manifest와 batch manifest에 바인딩
make external-report-reference-manifest EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH=build/release/LLMwiki-source.zip
make release-closeout-batch-manifest-promote RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=build/release/LLMwiki-source.zip

# 5. closeout/finality/clean blocker/evidence 갱신
make release-closeout-summary
make release-closeout-finality-verify
make release-evidence-cohort
make release-clean-blocker-ledger
make release-evidence-dashboard

# 6. finalization 회귀 확인
make test-artifact-finalization

# 7. 장시간 release-builder에서 full-suite evidence 봉인
make test-execution-summary-full-refresh

# 8. promotion/readiness와 외부보고서 추적 갱신
make auto-improve-readiness
make external-report-action-matrix
```

주의: 위 순서는 저장소 실제 Makefile target 존재를 확인한 뒤 작성했다. 다만 장시간 full-suite refresh는 본 대화형 런타임에서 끝까지 봉인하지 못했으므로 release-builder에서 별도 수행해야 한다.

---

## 12. 최종 판정 매트릭스

| 항목 | 최종 판정 | 우선순위 |
| --- | --- | --- |
| 두 신규 리뷰의 ZIP 메타데이터 | 정확 | 완료 |
| 기존 2026-05-10 보고서의 과거 수치 폐기 | 정확 | 완료 |
| clean machine release-ready 아님 | 정확 | P0 유지 |
| batch manifest distribution binding | 실제 blocker | P0 |
| `aa21958e...` clean baseline | 직접 재확인됨 | P0 보정 |
| `770994fd...` 관측 | clean baseline과 불일치, 발생 조건 재조사 필요 | P0/P1 |
| artifact finalization | clean 현재 ZIP에서는 6 pass | P0에서 회귀방지로 보정 |
| source-tree coherence split | 실제 잔여 blocker | P0 |
| full-suite 1103/1107 | 실제 잔여 불일치 | P0 |
| generated artifact index archive candidate | 해결됨 | 완료/회귀방지 |
| auto-improve promotion gate | machine boolean은 개선됨 | P1 wording |
| release ZIP generation | 정상 | 완료/identity binding 필요 |
| external report action matrix | 실제 6 implemented / 4 verification | P1 |
| old report lifecycle | superseded 처리 필요 | P1/P2 |

---

## 13. 결론

두 신규 리뷰는 현재 ZIP이 2026-05-10 상태보다 크게 전진했다는 점, 이미 해결된 archive candidate/auto-improve 과낙관/1086→1092 논점을 반복하지 말아야 한다는 점, 그리고 남은 핵심이 batch manifest binding·source-tree coherence·full-suite evidence 재봉인이라는 점을 잘 정리했다.

다만 실제 clean 추출본을 다시 대조한 결과, 두 리뷰가 “핵심 불일치”로 남겨둔 fingerprint/finalization 문제는 한 단계 더 좁혀야 한다. 현재 원본 ZIP clean baseline에서는 `aa21958e...`가 직접 재현되고 `make test-artifact-finalization`도 6/6 통과한다. 따라서 개선 보고서의 최우선 문장은 다음처럼 정리하는 것이 가장 정확하다.

> 현재 clean ZIP 기준 currentness artifact baseline은 `aa21958e...`로 닫혀 있다. 남은 release blocker는 `aa` vs `770`의 추상적 선택 문제가 아니라, batch manifest에 실제 distribution ZIP을 바인딩하지 못한 점, release evidence가 strict single cohort로 닫히지 않은 점, full-suite evidence가 1103/1107 사이에서 재봉인되지 않은 점, 그리고 external report/current distribution identity가 여러 SHA로 흩어진 점이다.

이 기준으로 기존 2026-05-10 보고서는 historical/superseded로 처리하고, 본 보고서와 두 신규 리뷰의 개선안은 `aa21958e...` clean baseline 위에서 release authority를 닫는 실행 계획으로 갱신해야 한다.
