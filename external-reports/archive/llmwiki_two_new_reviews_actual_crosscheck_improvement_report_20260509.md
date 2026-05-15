# LLMwiki 두 신규 리뷰-기존 리뷰-실제 파일 대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-09 KST |
| 작성 언어 | 한국어 |
| 출력 파일명 | `llmwiki_two_new_reviews_actual_crosscheck_improvement_report_20260509.md` |
| 검토 대상 압축본 | `/mnt/data/LLMwiki.zip` |
| ZIP SHA-256 | `6731aa87fb3d1b9dac5d61c6610dca5ec702458e75ab989dea1e0ca2a9055db6` |
| ZIP 엔트리 | 2,007개 (파일 1,896개 + 디렉터리 111개) |
| 비압축/압축 크기 | 250,081,827 bytes / 191,967,886 bytes |
| 신규 리뷰 1 | `llmwiki_integrated_review_report_20260509.md` |
| 신규 리뷰 2 | `llmwiki_integrated_crosscheck_improvement_report_20260509.md` |
| 기존 리뷰 | `llmwiki_current_zip_crosscheck_improvement_report_20260509.md` |
| 기준 보고서 | `external-reports/llmwiki_dual_new_review_crosscheck_report_20260508.md`, `external-reports/integrated_improvement_report_v3.md` |
| 실제 재검증 작업복사본 | `/mnt/data/LLMwiki_review_current_fresh` |

---

## 0. 최종 결론

두 신규 리뷰의 중심 결론은 대체로 타당하다. 현재 압축본은 2026-05-08 계열 기준 보고서와 직전 기존 리뷰가 지적한 여러 P0를 이미 상당 부분 해소했지만, **live `make check`가 `artifact-freshness-check`에서 schema-invalid canonical artifact 6건으로 실패하는 동안 checked-in release authority는 `clean_pass`/`clean_release_ready=true`를 표시한다.** 이 불일치는 현재도 가장 중요한 release truth drift다.

다만 이번 재검증에서 두 신규 리뷰 중 일부 주장은 보정이 필요하다.

1. **재현 확정:** `make check` 실패, schema-invalid artifact 6건, checked-in artifact-freshness pass와 live fail의 불일치, auto-improve `can_promote_result=true`의 과낙관, full-suite collect count drift, archive root naming의 작업 디렉터리 의존성.
2. **현재 파일 기준 보정:** 신규 리뷰가 언급한 `external-reports/LMMwiki...` 한글 경로가 실제 clean extract에서 `#Uxxxx` 형태로 바뀌는 현상은 이번 검증에서는 재현되지 않았다. ZIP namelist, Python clean extract, `report-reference-manifest`, `generated-artifact-index` 모두 한글 path를 동일하게 가리켰다.
3. **현재 파일 기준 보정:** 신규 리뷰 2가 적은 generated artifact fingerprint stale / targeted contract 일부 실패는 이번 재검증의 4개 계약 테스트 묶음 68개에서는 재현되지 않았다. 현재 P0로 둘 것은 stale fingerprint가 아니라 **artifact freshness schema validation fail 6건**이다.
4. **압축 경로 판단:** repo-generated source ZIP 생성 자체는 fast profile에서 정상이다. 압축 관련 개선은 “압축 파일이 잘 생성되는가”보다 **archive member root가 `vault.name`에 묶여 재현 가능한 digest를 깨뜨릴 수 있는가**에 집중하면 된다.

따라서 최우선 개선 순서는 다음으로 갱신한다.

1. learning evidence / release dashboard 계열 schema-invalid artifact 6건을 producer와 schema 기준으로 정합화한다.
2. release closeout/dashboard/batch manifest가 live `make check` 실패를 clean pass로 덮지 못하게 한다.
3. auto-improve promotion gate가 전역 artifact contract fail을 직접 blocker로 삼게 한다.
4. full-suite summary를 현재 collect count와 다시 결합한다.
5. release archive root를 고정 slug로 바꿔 source ZIP digest 재현성을 확보한다.
6. source package pytest phase와 full smoke boundedness를 별도 evidence로 닫는다.
7. path portability는 “현재 blocker”가 아니라 cross-platform provenance guard로 재분류해 manifest alias/hash 구조를 보강한다.

---

## 1. 검토 입력과 보고서 간 관계

### 1.1 신규 리뷰 1: `llmwiki_integrated_review_report_20260509.md`

이 문서는 세 개의 독립 리뷰를 다시 통합한 **2차 통합 보고서**다. 장점은 합의/차이점을 표로 정리하고, `make check` 실패와 schema-invalid artifact 6건을 release truth drift의 핵심으로 격상했다는 점이다. 또한 archive root naming, full suite node count, auto-improve promotion safety를 추가 이슈로 흡수했다.

보정이 필요한 지점은 두 가지다.

- path encoding 문제를 “실제 clean extract 후 파일명이 `#Uxxxx`로 바뀐다”는 확인 사실로 다루지만, 이번 압축본의 ZIP namelist와 Python clean extract에서는 해당 현상이 재현되지 않았다.
- stale fingerprint/contract failure 계열을 P0-4로 유지하지만, 현재 작업복사본에서 관련 계약 테스트 68개는 통과했다. 이 항목은 “현재 실패”가 아니라 “재발 방지/재생성 discipline”으로 낮춰 다루는 편이 정확하다.

### 1.2 신규 리뷰 2: `llmwiki_integrated_crosscheck_improvement_report_20260509.md`

이 문서는 직전 기존 리뷰와 가장 유사한 **실제 ZIP 대조형 개선 보고서**다. 장점은 checked-in release artifact들의 낙관 상태와 live `make check` 실패를 직접 대비하고, source ZIP 생성 경로를 저장소 구현 관점으로 설명했다는 점이다.

보정이 필요한 지점은 다음과 같다.

- `generated-artifact-index` stale 및 selected targeted contract failure는 이번 검증에서는 재현되지 않았다.
- path encoding 문제는 현 파일 시스템에서 직접 깨지는 이슈로 확정하기보다, C locale/Info-ZIP/Unicode normalization 환경에서 발생 가능한 portability-provenance risk로 재분류해야 한다.
- `release-source-package-check` pytest phase는 이번에도 최종 완료 결과를 얻지 못했으므로 pass/fail 어느 쪽으로도 단정하면 안 된다.

### 1.3 기존 리뷰: `llmwiki_current_zip_crosscheck_improvement_report_20260509.md`

기존 리뷰의 중심 판단은 여전히 유효하다.

- direct entrypoint/console script drift, writer/output surface drift, generated report contract, source package/test mode 분리는 현재 상당 부분 개선 또는 해소되었다.
- 현재 남은 핵심은 `artifact-freshness-check` live fail과 checked-in clean pass의 공존이다.
- auto-improve readiness는 “실행 가능성” 면에서는 개선됐지만 “promotion safety” 면에서는 artifact contract status와 결합이 필요하다.

신규 리뷰들이 기존 리뷰 위에 추가한 가치 있는 항목은 다음 세 가지다.

1. archive root naming 비재현성.
2. full-suite collect count drift.
3. path portability/provenance manifest 구조 보강 필요성.

---

## 2. 원본 ZIP과 저장소 구조 재확인

### 2.1 ZIP 통계

| 항목 | 값 |
| --- | ---: |
| SHA-256 | `6731aa87fb3d1b9dac5d61c6610dca5ec702458e75ab989dea1e0ca2a9055db6` |
| 전체 ZIP entries | 2,007 |
| 파일 수 | 1,896 |
| 디렉터리 수 | 111 |
| 비압축 크기 | 250,081,827 bytes |
| 압축 크기 | 191,967,886 bytes |

### 2.2 top-level prefix별 파일 수

| prefix | 파일 수 |
| --- | ---: |
| `raw` | 446 |
| `ops` | 437 |
| `wiki` | 417 |
| `runs` | 263 |
| `tests` | 159 |
| `system` | 71 |
| `external-reports` | 60 |
| `<root>` | 18 |
| `.codex` | 10 |
| `tools` | 6 |
| `.obsidian` | 5 |
| `.github` | 2 |
| `.ouroboros` | 1 |
| `.vscode` | 1 |

이 압축본은 `runs/`, `external-reports/`, `ops/reports/`, `raw/`, `wiki/`, `system/`까지 포함한 **전체 저장소 원본 스냅샷**이다. 따라서 2026-05-08 기준 보고서의 source-only package 전제를 현재 ZIP에 그대로 적용하면 안 된다. source-only release ZIP의 hygiene는 `make release-distribution-zip`로 별도 판단하고, 현재 업로드 ZIP은 full vault snapshot으로 판단해야 한다.

---

## 3. 실제 재검증 결과

### 3.1 실행한 명령과 결과

| 검증 | 결과 | 핵심 관찰 | 로그 |
| --- | --- | --- | --- |
| `make bootstrap-preflight PYTHON=/mnt/data/llmwiki_venv/bin/python` | pass | Python 3.13.5, jsonschema/PyYAML/mypy/pytest/ruff 확인 | `/mnt/data/llmwiki_review_bootstrap_preflight_20260509.log` |
| `make artifact-freshness-check PYTHON=/mnt/data/llmwiki_venv/bin/python` | **fail** | schema-invalid artifact 6건 | `/mnt/data/llmwiki_review_make_artifact_freshness_20260509.log` |
| `make check PYTHON=/mnt/data/llmwiki_venv/bin/python` | **fail** | ruff pass, mypy pass 후 artifact-freshness에서 중단 | `/mnt/data/llmwiki_review_make_check_20260509.log` |
| `python -m pytest -q -o addopts= tests/test_generated_report_contracts.py tests/test_writer_output_paths.py tests/test_import_fallback_contract.py tests/test_script_module_surface_contract.py` | pass | 68 passed | `/mnt/data/llmwiki_review_selected_contract_tests_20260509.log` |
| `python -m pytest -o addopts= --collect-only -q` | pass | **1028 tests collected** | `/mnt/data/llmwiki_review_pytest_collect_20260509.log` |
| `make release-distribution-zip PYTHON=/mnt/data/llmwiki_venv/bin/python` | pass | packed 1453 files, manifest comparison pass | `/mnt/data/llmwiki_review_release_distribution_zip_20260509.log` |
| `make release-source-package-check ...` | 미완료 | 도구 런타임의 60초 interrupt로 최종 pass/fail 확보 못 함 | 최종 로그 없음(중단되어 근거로 사용하지 않음) |

`release-source-package-check`는 사용자의 “시간 제한 없이” 의도와 달리 현재 실행 도구 계층에서 60초 interrupt가 발생해 최종 결과를 얻지 못했다. 따라서 이 보고서에서는 해당 명령을 pass/fail 증거로 쓰지 않는다. 이미 확정된 P0는 더 짧은 경로인 `make artifact-freshness-check`와 `make check`로 재현된다.

### 3.2 `make check`의 실제 실패 위치

`make check`는 다음과 같이 실패했다.

```text
ruff check ops/scripts tests tools        -> pass
mypy @ops/mypy-allowlist.txt              -> pass
artifact-freshness-check                  -> fail
```

live `tmp/artifact-freshness-report-check.json` summary:

| metric | 값 |
| --- | ---: |
| artifact_count | 276 |
| json_artifact_count | 276 |
| stale_artifact_count | 0 |
| missing_schema_count | 0 |
| missing_artifact_envelope_count | 0 |
| schema_invalid_artifact_count | **6** |
| stable_contract_debt_artifact_count | 6 |
| stable_contract_debt_issue_count | 6 |

반면 checked-in `ops/reports/artifact-freshness-report.json`는 `status=pass`, `summary.schema_invalid_artifact_count=0`, `summary.stable_contract_debt_issue_count=0`다. 이 불일치가 두 신규 리뷰와 기존 리뷰가 공통으로 잡은 핵심 truth drift다.

### 3.3 schema-invalid artifact 6건

| artifact | error count | 대표 validation error |
| --- | ---: | --- |
| `ops/reports/learning-claim-evidence-bundle.json` | 29 | `$.confirmed_telemetry_evidence[0]: missing required property 'legacy_reconstruction_selection_reason'`<br>`$.confirmed_telemetry_evidence[0]: missing required property 'legacy_reconstruction_reasons'`<br>`$.confirmed_telemetry_evidence[0]: missing required property 'secondary_axis_evidence_source'` |
| `ops/reports/learning-claim-unlock-review.json` | 1 | `$.machine_policy_decision.confirmed_evidence_summary: missing required property 'legacy_reconstruction_summary'` |
| `ops/reports/learning-confirmed-evidence-cohort.json` | 26 | `$.run_evidence[0]: missing required property 'legacy_reconstruction_status'`<br>`$.run_evidence[0]: missing required property 'legacy_reconstruction_selection_reason'`<br>`$.run_evidence[0]: missing required property 'legacy_reconstruction_reasons'` |
| `ops/reports/learning-confirmed-legacy-reconstruction.json` | 12 | `$.run_reconstructions[0]: missing required property 'selection_reason'`<br>`$.run_reconstructions[0]: missing required property 'parsed_secondary_axis_evidence'`<br>`$.run_reconstructions[1]: missing required property 'selection_reason'` |
| `ops/reports/learning-delta-scoreboard.json` | 3 | `$.confirmed_evidence_summary: missing required property 'legacy_reconstruction_summary'`<br>`$.learning_claim_unlock_review.confirmed_evidence_summary: missing required property 'legacy_reconstruction_summary'`<br>`$.summary.confirmed_evidence_summary: missing required property 'legacy_reconstruction_summary'` |
| `ops/reports/release-evidence-dashboard.json` | 3 | `$.confirmed_evidence_summary: missing required property 'legacy_reconstruction_summary'`<br>`$.inputs.learning_delta_scoreboard.confirmed_evidence_summary: missing required property 'legacy_reconstruction_summary'`<br>`$.summary.confirmed_evidence_summary: missing required property 'legacy_reconstruction_summary'` |

이 6개는 모두 learning claim / confirmed evidence / release dashboard 계열이다. 단일 JSON 파일의 누락이 아니라 **legacy reconstruction / secondary-axis evidence 필드가 여러 producer surface에 동시에 반영되지 않은 schema evolution drift**로 보는 편이 맞다.

---

## 4. checked-in release authority와 live gate의 충돌

### 4.1 checked-in artifacts가 말하는 상태

| artifact | checked-in 상태 |
| --- | --- |
| `ops/reports/release-closeout-summary.json` | `status=pass`, `clean_release_ready=True` |
| `ops/reports/release-evidence-dashboard.json` | `status=pass`, `summary.accepted_risk_count=1`, `summary.gate_attention_count=0` |
| `ops/reports/release-closeout-batch-manifest.json` | `release_authority_status=clean_pass`, `machine_release_status=allowed`, `operator_release_status=allowed`, `sealed_release_status=sealed_clean_pass` |
| `ops/reports/auto-improve-readiness.json` | `can_promote_result=True`, `promotion_blockers=[]` |
| `ops/reports/test-execution-summary-full.json` | `status=pass`, `nodeid_count=1022` |

이 상태만 보면 release는 clean pass처럼 보인다. 그러나 live `make check`가 실패하므로, checked-in release authority는 현재 최종 release 근거가 될 수 없다.

### 4.2 auto-improve readiness의 과낙관

`auto-improve-readiness.json`은 `can_promote_result=true`, `promotion_blockers=[]`다. 하지만 live artifact freshness는 canonical ops report 6개가 schema-invalid라고 판단한다. 따라서 auto-improve readiness는 실행 가능성(`can_execute_trial`)과 promotion 가능성(`can_promote_result`)을 분리해야 한다.

권장 정책:

- `can_execute_trial`: proposal/readiness/telemetry 조건으로 판단.
- `can_promote_result`: `artifact_freshness.status=pass`, `schema_invalid_artifact_count=0`, release dashboard schema validation pass, learning claim artifact schema validation pass를 모두 요구.
- 실패 시 `promotion_blockers[]`에 schema-invalid artifact path와 schema error summary를 직접 기록.

---

## 5. 두 신규 리뷰와 실제 파일 대조 판정표

| 주장/이슈 | 신규 리뷰 1 | 신규 리뷰 2 | 기존 리뷰 | 실제 재검증 | 최종 판정 |
| --- | --- | --- | --- | --- | --- |
| 현재 ZIP은 source-only가 아니라 full repository snapshot | 확정 | 확정 | 확정 | ZIP prefix와 파일 수로 확인 | **확정** |
| `make check`는 artifact-freshness에서 실패 | 확정 | 확정 | 확정 | `make check` rc=2, ruff/mypy 후 중단 | **P0 확정** |
| schema-invalid canonical artifact는 6건 | 확정 | 확정 | 확정 | live report `schema_invalid_artifact_count=6` | **P0 확정** |
| checked-in release authority는 clean pass/allowed | 확정 | 확정 | 확정 | `clean_release_ready=true`, batch `clean_pass/allowed` | **P0 확정** |
| direct entrypoint / console script drift 해소 | 확정 | 확정 | 확정 | 56 console scripts, 관련 contract tests pass | **해소 확정** |
| writer/output surface drift 해소 | 확정 | 확정 | 확정 | `ops/script-output-surfaces.json` surfaces 191, 관련 tests pass | **해소 확정** |
| generated artifact / writer selected contract tests 일부 실패 | P0-4로 유지 | 실패로 언급 | advisory로 언급 | 이번 selected contract 68 passed | **현재 실패로는 재현 안 됨. P1 재생성 discipline으로 재분류** |
| 한글 path가 clean extract 후 `#Uxxxx`로 바뀜 | 신규 발견으로 확정 | 확정에 가깝게 언급 | 미언급 | ZIP namelist/actual extract/manifest/index 모두 한글 path | **현재 blocker로는 미확정. portability risk로 재분류** |
| archive root naming이 `vault.name`에 의존 | 신규 발견 | 신규 발견 | 미언급 | `release_smoke.py`와 generated archive member path로 확인 | **P1 확정** |
| full suite node count 불일치 | 신규 발견 | 일부 반영 | 미언급 | checked-in 1022 vs fresh collect-only 1028 | **P1 확정** |
| release-distribution-zip fast profile pass | 확정 | 확정 | 확정 | `make release-distribution-zip` pass, packed 1453 | **확정** |
| source package pytest phase 미완료 | 미완료 | 미완료 | 미완료 | 이번 재시도도 final result 없음 | **미완료 유지** |
| full smoke boundedness 미완료 | 미완료 | 미완료 | 미완료 | 이번에는 재실행하지 않음 | **미완료 유지** |

---

## 6. path encoding / provenance 항목의 보정

신규 리뷰들은 다음 path drift를 중요 이슈로 제시했다.

```text
external-reports/LMMwiki교차검증 개선 보고서_20260506.md
external-reports/LMMwiki#Uad50#Ucc28#Uac80#Uc99d #Uac1c#Uc120 #Ubcf4#Uace0#Uc11c_20260506.md
```

이번 실제 파일 대조 결과는 다음과 같다.

| 확인 대상 | 값 |
| --- | --- |
| ZIP namelist match | `['external-reports/LMMwiki교차검증 개선 보고서_20260506.md']` |
| clean extract 실제 파일 | `['external-reports/LMMwiki교차검증 개선 보고서_20260506.md']` |
| `external-reports/report-reference-manifest.json` reference | `['external-reports/LMMwiki교차검증 개선 보고서_20260506.md']` |
| `ops/reports/generated-artifact-index.json` 관련 path | `['external-reports/LMMwiki교차검증 개선 보고서_20260506.md', 'external-reports/archive/LMMwiki교차검증 개선 보고서_20260506.md']` |
| selected generated/writer/entrypoint contract tests | 68 passed |

따라서 현재 압축본/현재 Python extract 기준으로는 `#Uxxxx` storage path가 실제 blocker라는 주장은 확인되지 않는다. 다만 이 항목을 완전히 폐기하면 안 된다. 저장소에는 path portability runtime이 있고, release smoke도 `python_unicode_escape_filename_bytes`, `posix_escape_expanded_filename_bytes`, `infozip_c_locale_escape_filename_bytes`를 계산한다. 즉 문제의 본질은 “현재 파일이 깨졌다”가 아니라 **cross-platform archive/extract 환경에서 사람이 보는 display name과 machine canonical path/provenance를 안정적으로 연결할 수 있는가**다.

권장 보정:

- P0에서 제외하고 P1/P2 provenance hardening으로 이동.
- `report-reference-manifest` schema에 `storage_path`, `display_name`, `path_aliases[]`, `content_sha256`를 추가.
- generated artifact index가 path 문자열만이 아니라 content hash로도 reference를 resolve할 수 있게 한다.
- 한글 path와 escaped diagnostics를 혼동하지 않도록 report field 이름을 `display_path`, `archive_path`, `escape_expanded_diagnostic_path`처럼 분리한다.

---

## 7. 압축/패키징 경로 검토

### 7.1 repo-generated source ZIP은 정상 생성된다

`make release-distribution-zip` fast profile 결과:

| 항목 | 값 |
| --- | --- |
| status | `pass` |
| archive_path | `build/release/LLMwiki-source.zip` |
| packed_file_count | 1453 |
| manifest_comparison.pass | `True` |
| missing_paths | `[]` |
| unexpected_paths | `[]` |
| sha_mismatches | `[]` |
| archive self-description member | `LLMwiki_review_current_fresh/release-archive-self-description.json` |

구현상 release ZIP 생성은 다음 흐름을 따른다.

1. source manifest를 만든다.
2. ZIP timestamp/file mode normalization policy를 적용한다.
3. temp archive에 먼저 쓴다.
4. self-description을 ZIP 안에 추가한다.
5. archive verify와 manifest comparison을 통과하면 final path로 atomic replace한다.
6. 예외 또는 interrupt 발생 시 partial archive는 quarantine path로 보낸다.

압축 관련해서는 신규 리뷰들의 판단대로, 현재는 “압축본이 어떻게 생성되는지 확인하고 문제가 없으면 넘어가도 되는” 상태에 가깝다. fast source package 생성 자체는 pass다.

### 7.2 남은 압축 이슈는 archive root naming 재현성이다

`ops/scripts/release_smoke.py`는 archive member name을 다음 방식으로 만든다.

```python
arcname = _archive_member_name(vault.name, entry["path"])

def _archive_member_name(vault_name: str, rel_path: str) -> str:
    return f"{vault_name}/{rel_path}"
```

이번 실행 copy 이름이 `/mnt/data/LLMwiki_review_current_fresh`였기 때문에 self-description member path도 다음처럼 생성됐다.

```text
LLMwiki_review_current_fresh/release-archive-self-description.json
```

동일한 저장소 내용을 다른 작업 디렉터리 이름에서 빌드하면 ZIP 내부 path가 바뀌고, 그 결과 ZIP digest도 바뀔 수 있다. 이 문제는 fast generation pass 여부와 별개인 **reproducibility defect**다.

권장 수정:

- policy에 `release_packaging.archive_root_name` 또는 CLI `--archive-root-name`을 둔다.
- 기본값은 `LLMwiki` 같은 fixed slug로 고정한다.
- manifest, self-description, verify/extract root도 같은 fixed slug 기준으로 기록한다.
- backward compatibility가 필요하면 이전 `vault.name` root를 legacy profile에서만 허용한다.

---

## 8. full-suite evidence 보정

checked-in `ops/reports/test-execution-summary-full.json`은 `pytest_collect_nodeid_digest.nodeid_count=1022`를 기록한다. 그러나 이번 fresh collect-only는 `1028 tests collected`였다.

| 항목 | 값 |
| --- | ---: |
| checked-in full summary nodeid count | 1022 |
| fresh `pytest --collect-only -q` count | 1028 |
| 차이 | +6 |

이 차이는 곧바로 테스트 실패를 뜻하지는 않는다. 그러나 release authority가 full-suite evidence를 1급 근거로 사용하려면, 현재 소스 트리에서 collect되는 node count와 checked-in summary가 맞아야 한다. schema-invalid P0를 닫은 뒤에는 full summary와 downstream dashboard를 다시 생성해야 한다.

권장 순서:

1. `python -m pytest -o addopts= --collect-only -q` 기준 nodeid digest 재산출.
2. full suite 실행 또는 reuse policy 명시.
3. `ops/reports/test-execution-summary-full.json` refresh.
4. release evidence dashboard / closeout summary / batch manifest 재생성.
5. release authority가 사용한 full-suite digest와 source tree fingerprint를 명시.

---

## 9. 최종 개선 우선순위

### P0-1. schema-invalid canonical artifact 6개를 먼저 닫는다

직접 blocker다. `make check`가 이 단계에서 중단된다.

대상:

1. `ops/reports/learning-claim-evidence-bundle.json`
2. `ops/reports/learning-claim-unlock-review.json`
3. `ops/reports/learning-confirmed-evidence-cohort.json`
4. `ops/reports/learning-confirmed-legacy-reconstruction.json`
5. `ops/reports/learning-delta-scoreboard.json`
6. `ops/reports/release-evidence-dashboard.json`

작업 방향:

- schema required field가 의도된 변경인지 확인한다.
- 의도된 변경이면 producer를 수정해 누락 필드를 채운다.
- `legacy_reconstruction_summary`, `operator_summary`, `operator_reconstruction_diagnostics`, `selection_reason`, `parsed_secondary_axis_evidence`, `secondary_axis_evidence_*` 계열을 공통 builder에서 생성한다.
- dashboard/delta/unlock/evidence cohort가 같은 `confirmed_evidence_summary` builder를 쓰게 한다.
- `tmp/*.candidate.json` 생성 → schema validation → artifact freshness check → promote 순서로만 canonical rewrite를 허용한다.

Definition of Done:

- `make artifact-freshness-check` pass.
- `schema_invalid_artifact_count=0`.
- `stable_contract_debt_issue_count=0`.
- `make check`가 artifact freshness 이후 단계로 진행.

### P0-2. release authority가 live gate 실패를 clean pass로 표시하지 못하게 한다

현재 가장 위험한 상태는 checked-in `clean_release_ready=true`와 live `make check` fail의 공존이다.

필수 변경:

- release closeout summary, release dashboard, batch manifest에 `last_live_make_check_status`, `last_live_make_check_returncode`, `last_live_make_check_failed_target`, `artifact_freshness_status`, `schema_invalid_artifact_count`, `schema_invalid_artifacts[]`를 추가한다.
- live gate fail이면 `clean_release_ready=false`, `machine_release_status=blocked`, `operator_release_status=blocked_or_requires_waiver`로 강제한다.
- accepted risk는 clean lane 면죄부가 아니라 conditional/waiver lane으로 분리한다.
- checked-in evidence와 live rerun evidence가 충돌하면 live rerun이 우선한다는 truth ladder를 schema에 명시한다.

### P0-3. auto-improve promotion safety를 artifact contract status에 묶는다

현재 `can_promote_result=true`는 schema invalid 6건과 충돌한다.

필수 변경:

- `can_execute_trial`과 `can_promote_result`를 분리.
- `can_promote_result`는 artifact freshness pass와 schema invalid 0건을 hard prerequisite으로 둔다.
- schema invalid 상태에서는 `promotion_blockers[]`에 6개 artifact path와 error summary를 기록한다.

### P1-1. full-suite evidence를 현재 collect count에 맞춰 refresh한다

현재 checked-in full summary는 1022 nodeid, fresh collect-only는 1028이다. P0를 닫은 뒤 full-suite evidence를 refresh하고 release dashboard/closeout에 다시 bind해야 한다.

### P1-2. archive root naming을 fixed slug로 바꾼다

`vault.name` 의존은 source ZIP reproducibility를 깨뜨릴 수 있다. `LLMwiki` 같은 fixed slug를 policy/CLI로 고정한다.

### P1-3. source package pytest phase를 별도 evidence로 닫는다

`release-distribution-zip`은 pass지만, `release-source-package-check`의 pytest phase final result는 이번에도 확보하지 못했다. source package check를 다음 세 lane으로 분리하면 진단이 쉬워진다.

- `source-package-static`
- `source-package-contract`
- `source-package-full`

각 lane은 summary JSON에 deselection policy, collected count, executed count, skipped/deselected count, runtime, returncode를 남긴다.

### P1-4. path portability/provenance manifest를 보강한다

현재 blocker로는 재현되지 않았지만, 한글/escaped path 문제는 cross-platform evidence portability risk다.

필수 변경:

- `storage_path`
- `display_name`
- `path_aliases[]`
- `content_sha256`
- `normalization_form`
- `escape_diagnostics`

### P1-5. release evidence bundle을 source ZIP과 분리한다

source ZIP은 `ops/reports/`, `external-reports/`, `runs/`를 포함하지 않는 것이 정상이다. 그렇다면 release 근거는 별도 evidence bundle로 보존해야 한다.

권장 3-part output:

1. `LLMwiki-source.zip`
2. `LLMwiki-release-evidence.zip`
3. post-seal binding manifest: source ZIP SHA, evidence ZIP SHA, full-suite digest, live gate result, operator decision.

### P2-1. 대형 runtime/test 리팩터링은 P0 이후 진행한다

대형 파일 분해는 여전히 유효하지만, 지금은 release truth 회복이 먼저다. P0가 닫힌 뒤 collector / validator / report builder / writer 단위로 나누는 순서가 안전하다.

### P2-2. README와 Makefile 환경 기본값을 맞춘다

README는 `.venv`를 표준처럼 설명하고, Makefile 기본은 `$(HOME)/.venvs/llm-wiki-vnext`를 사용한다. 새 작업자 혼선을 줄이려면 하나를 canonical로 정하거나 Makefile 상단에 의도를 명시한다.

---

## 10. 신규 리뷰별 채택/보정 목록

### 10.1 신규 리뷰 1에서 그대로 채택할 항목

- 세 리뷰가 동일 체크포인트를 봤다는 전제.
- 현재 ZIP은 full repository snapshot이라는 전제.
- `make check` fail과 schema-invalid 6건의 P0 판정.
- checked-in `clean_pass`와 live fail의 truth drift 판정.
- auto-improve promotion safety 결합 필요.
- archive root naming, full-suite node count를 후속 개선 항목으로 포함.

### 10.2 신규 리뷰 1에서 보정할 항목

- path encoding을 “현재 실제 파일이 깨짐”으로 확정하지 말고 “portability/provenance risk”로 낮춘다.
- stale fingerprint artifact 재생성은 현 selected contract tests가 통과했으므로 P0가 아니라 P1/P2 discipline으로 낮춘다.
- targeted contract test 결과는 현재 재검증값 68 passed를 기준으로 갱신한다.

### 10.3 신규 리뷰 2에서 그대로 채택할 항목

- 현재 ZIP이 이전 source-only package 전제와 다르다는 판단.
- source ZIP fast profile 생성 경로가 정상이라는 판단.
- `release authority clean pass`와 live `make check fail`의 불일치.
- learning evidence artifact schema drift를 최우선으로 닫아야 한다는 판단.
- source package pytest phase, full smoke boundedness 미완료 유지.

### 10.4 신규 리뷰 2에서 보정할 항목

- generated artifact index stale / writer output fingerprint failure는 현재 selected contract tests에서 재현되지 않았다.
- path encoding claim은 현 압축본의 직접 파일명/manifest/index와 일치하지 않으므로 현재 blocker로 쓰지 않는다.
- source package check는 이번에도 final result가 없으므로 “부분 pass” 이상의 결론은 내리지 않는다.

### 10.5 기존 리뷰에서 계속 유지할 항목

- 현재 핵심 P0는 schema-invalid 6건과 live gate / release authority 불일치.
- direct entrypoint, console script, writer/output drift는 해소 또는 완화로 재분류.
- source package lane deselection policy는 2026-06-08 expiry 전까지 lifecycle 관리 필요.
- release evidence bundle 분리와 environment contract 정리는 여전히 필요.

---

## 11. 최종 Definition of Done

현재 압축본 기준으로 다음을 모두 만족해야 release/evidence 체계를 안정권으로 볼 수 있다.

| # | 완료 조건 | 우선순위 |
| ---: | --- | --- |
| 1 | `make artifact-freshness-check`가 pass한다 | P0 |
| 2 | `schema_invalid_artifact_count=0`이다 | P0 |
| 3 | `make check`가 pass한다 | P0 |
| 4 | release closeout/dashboard/batch manifest가 live `make check` 실패를 clean pass로 표시하지 않는다 | P0 |
| 5 | `auto-improve-readiness.json`이 artifact contract fail 상태에서 `can_promote_result=false`를 표시한다 | P0 |
| 6 | 6개 learning/release evidence artifact가 current schema 기준으로 재생성되어 promote된다 | P0 |
| 7 | fresh collect-only node count와 checked-in full test summary node count가 일치한다 | P1 |
| 8 | full-suite digest가 release authority에 1급 evidence로 bind된다 | P1 |
| 9 | source ZIP archive member root가 fixed slug를 사용한다 | P1 |
| 10 | `release-source-package-check` pytest phase의 최종 결과가 machine-readable summary로 남는다 | P1 |
| 11 | full smoke partial/final semantics와 timeout/boundedness가 report schema에 명시된다 | P1 |
| 12 | path manifest가 `storage_path`, `display_name`, `path_aliases[]`, `content_sha256`를 제공한다 | P1 |
| 13 | source ZIP과 release evidence ZIP이 역할별로 분리된다 | P1 |
| 14 | README와 Makefile의 개발 환경 기본값이 충돌하지 않는다 | P2 |
| 15 | 대형 runtime/test 파일 분해는 P0 이후 진행한다 | P2 |

---

## 12. 최종 권고

두 신규 리뷰는 전체 방향에서 유용하지만, 현재 실제 파일 기준 최종 개선안은 다음처럼 정리하는 것이 가장 안전하다.

- **즉시 닫을 P0:** learning/release evidence schema invalid 6건, release authority의 live gate 반영 누락, auto-improve promotion safety 누락.
- **P1로 올려 관리할 항목:** full-suite node count drift, archive root fixed slug, source package pytest phase evidence, full smoke boundedness, release evidence bundle 분리.
- **현재 blocker에서 내릴 항목:** 한글 path가 실제 `#Uxxxx` storage path로 바뀌었다는 주장, generated artifact selected contract failure. 이번 재검증에서는 둘 다 직접 재현되지 않았다.
- **계속 유지할 원칙:** live gate가 checked-in report보다 우선한다. checked-in artifact가 아무리 `clean_pass`라고 적어도, live `make check`가 fail이면 release authority는 blocked 또는 conditional이어야 한다.

현재 저장소는 이미 많은 schema-backed report와 release evidence machinery를 갖고 있다. 지금 필요한 것은 더 많은 기능이 아니라, **현재 schema, 현재 파일 시스템, 현재 live gate, 현재 release authority가 같은 사실을 말하게 만드는 정합화 작업**이다.
