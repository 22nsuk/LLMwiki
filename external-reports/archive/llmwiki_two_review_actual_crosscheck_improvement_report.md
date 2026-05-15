# LLMwiki 두 통합 리뷰 실제 파일 대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일시 | 2026-05-05 14:25:02 KST |
| 작성 언어 | 한국어 |
| 출력 파일 | `llmwiki_two_review_actual_crosscheck_improvement_report.md` |
| 기존 보고서 | `/mnt/data/llmwiki_substantive_improvement_report.md` |
| 신규 리뷰 A | `/mnt/data/llmwiki_integrated_review_report.md` |
| 신규 리뷰 B | `/mnt/data/LLMwiki 통합 실질 개선 리뷰 보고서.md` |
| 실제 대조 ZIP | `/mnt/data/LLMwiki.zip` |
| 실제 ZIP SHA-256 | `aef28bb86842b38f596af3e07adc1115c141c8f5175d4c08c2f54a425e60a9f0` |
| 실제 ZIP 엔트리 / 파일 / 디렉터리 | 1839 / 1740 / 99 |
| 실제 ZIP 압축 해제 바이트 합계 | 243,591,901 bytes |
| 운영 계약 확인 | `Codex-Subagent-Orchestrator.zip` 추출 후 루트 `AGENTS.md`, parent-session, routing, plan-mode, anti-overengineering 문서 확인 |
| 직접 실행 확인 | targeted auto-improve iteration test 7개 통과, batch manifest fresh-extract check 실패 재현 |
| 한계 | 전체 pytest suite와 132개 report-contract test는 현재 도구 실행 제한 때문에 새 성공 증거로 주장하지 않음 |

---

## 1. 최종 요약

두 신규 리뷰는 기존 보고서의 큰 결론을 강화한다. 세 문서가 모두 가리키는 핵심은 동일하다.

> 현재 저장소의 병목은 “테스트 부족”이 아니라, **테스트·리포트·생성 산출물이 실질 개선의 증거가 아니라 개선 자체처럼 소비되는 운영 구조**다.

실제 ZIP 내부 파일과 체크인된 JSON 리포트를 대조한 결과, 다음 결론은 강하게 유지된다.

1. `auto-improve-readiness.json`은 `can_execute_trial=true`이지만 `can_promote_result=false`이며, `learning_readiness.status=learning_uncertain`, `likely_to_learn=false`, `telemetry_coverage_ratio=0.0`을 기록한다.
2. `mutation-proposals.json`과 `mechanism-review-candidates.json`은 동일하게 `repeated_same_eval_or_discard__auto-improve-iteration-persistence-runtime`을 다음 단일 개선 후보로 지목한다.
3. `test-execution-summary.json`은 `suite=report-contract-summary`, `represents_full_suite=false`, `full_suite_evidence.status=not_represented`를 명시한다.
4. 릴리스 상태는 clean/machine release가 아니라 conditional/operator release다. `release-closeout-summary.json`은 `release_readiness_state=conditional_pass`, `clean_release_ready=false`, `machine_release_allowed=false`, `operator_release_allowed=true`를 기록한다.
5. fresh extract 환경에서 `release_closeout_batch_manifest --check`가 실패하는 현상은 실제로 재현된다. 원인은 현재 검증 기준이 ZIP 멤버 메타데이터가 아니라 파일시스템 `mtime`에 의존하기 때문이다.
6. `external-reports/report-reference-manifest.json`은 실제 업로드 ZIP SHA가 아니라 과거 배포 ZIP(`LLMwiki(12).zip`)을 current distribution으로 참조한다.
7. ZIP 안에 `tmp/` 파일 7개가 실제 포함되어 있다.

다만 두 리뷰의 일부 표현은 실제 파일 기준으로 보정해야 한다.

- 현재 업로드 ZIP 자체의 정확한 파일 수는 **1,740개**다. 추출 후 실행 과정에서 생기는 `__pycache__` 등은 실제 ZIP 파일 수에 포함하면 안 된다.
- 체크인된 `release-closeout-batch-manifest.json` 자체는 `source_evidence_freshness.status=pass`, `changed_after_generated_at_count=0`을 담고 있다. 실패는 **fresh extract 후 재계산할 때** 발생한다.
- ZIP 멤버 타임스탬프는 timezone 정보를 갖지 않으므로, 단순 UTC 해석과 KST 해석의 결과가 달라질 수 있다. 현재 체크인된 리포트와 일관된 해석은 KST 기반이며, 이 기준에서는 source 파일 변경 수가 0이고 전체 ZIP 기준으로는 batch manifest 자신만 `generated_at` 이후다.
- `loop_health_telemetry_coverage_missing`의 실제 JSON severity는 `warn`이다. 운영상 심각도는 높지만, 보고서에서는 “JSON severity=critical”이라고 쓰면 실제 파일과 맞지 않는다.
- `test-execution-summary-full` Makefile target은 이미 존재하지만, `ops/reports/test-execution-summary-full.json`과 shard artifact는 존재하지 않는다. 따라서 개선 과제는 target 신설이 아니라 **실제 full-suite artifact 생성·봉인·소비 경로 완성**이다.
- `auto_improve_iteration_persistence_runtime.py`에는 이미 `behavior_delta` 문자열 보존, decision record fallback, timeout merge, 기존 telemetry field preserve 로직이 일부 구현되어 있다. 다음 개선은 “behavior_delta를 새로 추가”가 아니라 **digest/원인분류/backfill/discoverability를 완성**하는 쪽이어야 한다.

---

## 2. 검토 입력과 무결성

| 구분 | 파일 | SHA-256 | 라인 수 | 바이트 |
| --- | --- | --- | ---: | ---: |
| 기존 보고서 | `llmwiki_substantive_improvement_report.md` | `0a81d5adeb0bd9c25ca2198ca178973f52e7b4f9318e1719dddf8ab8f6a4a957` | 461 | 33,415 |
| 신규 리뷰 A | `llmwiki_integrated_review_report.md` | `4be0fb57bab279df624b8fbde640ba56d1fb91e91fd96381c354e2e975c8635e` | 793 | 44,013 |
| 신규 리뷰 B | `LLMwiki 통합 실질 개선 리뷰 보고서.md` | `40fb9e9e104a8f4b7f15232be8ca191c896a35e04a75da686b9a977f3059e4b4` | 877 | 46,995 |

| 실제 ZIP | `LLMwiki.zip` | `aef28bb86842b38f596af3e07adc1115c141c8f5175d4c08c2f54a425e60a9f0` | - | 191,904,128 |

### 2.1 검토 방식

이번 보고서는 다음 네 가지 축을 함께 사용했다.

1. 두 신규 리뷰의 목차, 결론, P0/P1/P2 실행안, 부록을 전부 읽고 항목별로 분해했다.
2. 기존 보고서(`llmwiki_substantive_improvement_report.md`)의 진단·로드맵·누락 항목을 대조했다.
3. 실제 ZIP을 새 작업공간에 압축 해제하고 `ops/reports`, `external-reports`, `runs`, `tests`, `ops/scripts`, `ops/schemas`, `Makefile`을 직접 확인했다.
4. 장시간 full-suite 재실행 대신, 이번 쟁점에 직접 연결되는 targeted command와 정적 파일 분석을 수행했다.

### 2.2 직접 실행한 확인

| 확인 | 명령/방식 | 결과 | 해석 |
| --- | --- | --- | --- |
| ZIP inventory | Python `zipfile` | 1839 entries / 1740 files / 99 dirs | 리뷰 B의 1,839 entries / 1,740 files와 일치 |
| Python source/test LOC | AST/파일 스캔 | `ops/**/*.py` 179개, `tests/**/*.py` 143개, AST test 함수 909개 | 두 리뷰의 핵심 수치와 일치 |
| Targeted auto-improve iteration test | `python -m pytest tests/test_auto_improve_iteration_runtime.py -q` | 7 passed | 해당 타깃의 현행 계약 테스트는 통과 |
| Batch manifest fresh check | `python -m ops.scripts.release_closeout_batch_manifest --vault <fresh> --check` | exit 1, `changed_after_generated_at_count=1408` | fresh extract 오탐/재현성 문제 확인 |
| Report-contract long run | `python -m pytest tests/test_generated_report_contracts.py -q` | 도구가 약 60초 후 interrupt | 성공/실패 증거로 사용하지 않음 |

실행 중 Python startup에서 spreadsheet runtime warmup 경고가 stderr에 함께 찍혔지만, targeted pytest는 return code 0으로 끝났고, batch manifest check는 script 자체의 실패 메시지를 출력했다. 이 경고는 이번 결론의 근거로 사용하지 않았다.

---

## 3. 두 신규 리뷰의 관계

### 3.1 리뷰 A: `llmwiki_integrated_review_report.md`

리뷰 A는 “통합 정밀 검토 보고서” 형식으로, 세 독립 리뷰의 공통 진단을 항목화하고 P0/P1/P2 과제를 깔끔하게 재정렬한다. 장점은 다음이다.

- 통합 핵심 결론을 간결하게 고정한다.
- P0에 telemetry discoverability, batch manifest, report-reference manifest, clean/conditional lane 분리를 모두 배치한다.
- P1/P2에 full-suite summary, learning-delta-scoreboard, subprocess timeout, evidence scope, 대형 런타임 분해, changed-files planner를 둔다.
- “실질 개선 인정 기준”과 “핵심 운영 규칙”이 명확하다.

보완점은 다음이다.

- 일부 수치가 실제 업로드 ZIP 기준과 섞인다. 특히 “리뷰 3의 1,756 파일”은 현재 ZIP inventory와 일치하지 않으므로 실제 ZIP 수치 1,740을 기준으로 고정해야 한다.
- `loop_health_telemetry_coverage_missing`을 “critical”처럼 해석한 대목은 운영 위험 해석으로는 타당하지만, 실제 JSON severity는 `warn`이다.
- batch manifest ZIP timestamp 설명은 방향은 맞지만, timezone 없는 ZIP timestamp의 해석 문제까지 명시해야 재현성 수정이 완전해진다.

### 3.2 리뷰 B: `LLMwiki 통합 실질 개선 리뷰 보고서.md`

리뷰 B는 리뷰 A보다 실행 검증과 실제 파일 대조를 더 많이 포함한다. 장점은 다음이다.

- ZIP SHA, entry count, tmp 오염, report-reference manifest 불일치 등 배포물 재현성 문제를 더 직접적으로 기록한다.
- 전체 테스트 부분 실행 상태, 132개 계약 테스트, batch manifest fresh-extract 실패를 실행 증거 중심으로 정리한다.
- “테스트 통과가 개선 효과를 대체하고 있다”는 운영 메커니즘을 상세히 설명한다.
- P0/P1/P2 실행 계획이 실제 파일명과 연결되어 있다.

보완점은 다음이다.

- “LLMwiki(16).zip”이라는 이름은 현재 업로드 경로 `/mnt/data/LLMwiki.zip`과 다르다. SHA-256은 리뷰 B가 적은 값과 현재 업로드 ZIP이 일치하므로 이름은 저장/전달 과정의 표시 차이로 보는 것이 안전하다.
- full-suite와 report-contract 재실행 수치는 리뷰 자체의 근거로만 사용해야 하며, 이번 새 검토에서 장시간 suite를 새로 완주했다는 주장으로 재사용하면 안 된다.
- `batch manifest 자신 1개만 generated_at 이후`라는 표현은 “전체 ZIP 파일 기준”으로는 맞지만, release source freshness의 exclude policy를 적용하면 source file changed count는 0으로 표현하는 것이 더 정확하다.

### 3.3 기존 보고서와의 차이

기존 보고서는 이미 다음 핵심 방향을 맞게 잡고 있었다.

- 테스트는 목표가 아니라 증거다.
- 한 번에 하나의 mechanism만 바꿔야 한다.
- same-eval 상황에서는 secondary axis를 사전에 선언해야 한다.
- release lane과 learning lane을 분리해야 한다.
- `auto_improve_iteration_persistence_runtime.py`, `run-telemetry.schema.json`, `tests/test_auto_improve_iteration_runtime.py`가 핵심 타깃이다.

하지만 기존 보고서는 두 신규 리뷰에 비해 다음 항목이 덜 구체적이었다.

| 보강 필요 항목 | 기존 보고서 상태 | 두 신규 리뷰 및 실제 파일 대조 후 판단 |
| --- | --- | --- |
| Batch manifest fresh-extract 오탐 | release 상태로만 간략 언급 | `Path.stat().st_mtime` 의존으로 fresh extract에서 1,408개 source 변경 오탐이 실제 재현됨 |
| ZIP timestamp basis | 거의 미언급 | ZIP timestamp는 timezone 없는 local time이므로 basis와 timezone을 명시해야 함 |
| `report-reference-manifest` current ZIP mismatch | distribution finalizer 필요성만 언급 | 실제 manifest는 `LLMwiki(12).zip`, SHA `4704...`, entry 1,829를 current로 가리킴 |
| `tmp/` 오염 | subprocess/tmp 이슈로 언급 | 실제 ZIP에 7개 tmp file 포함 |
| no test-only promotion 정책 | 원칙으로 존재 | 정책 예외, 테스트 가치 태그, generated-only 제외 기준까지 더 명시해야 함 |
| full-suite artifact 상태 | 필요성 언급 | Makefile target은 있으나 canonical artifact와 shard가 없음으로 보정 |
| auto-improve telemetry 세부 | coverage 0 언급 | 최신 routing aggregate 선택 때문에 coverage 0이 되는 구조까지 확인됨 |

---

## 4. 실제 파일 대조 결과

### 4.1 ZIP 구조와 규모

| 항목 | 실제 값 |
| --- | ---: |
| ZIP SHA-256 | `aef28bb86842b38f596af3e07adc1115c141c8f5175d4c08c2f54a425e60a9f0` |
| ZIP size | 191,904,128 bytes |
| entry count | 1839 |
| file count | 1740 |
| directory count | 99 |
| uncompressed bytes | 243,591,901 |
| ZIP timestamp 범위 | (2026, 4, 12, 16, 3, 6) ~ (2026, 5, 5, 11, 56, 2) |
| `tmp/` 포함 파일 수 | 7 |

디렉터리별 ZIP 파일 수는 다음과 같다.

| 경로 | 파일 수 | 비고 |
| --- | ---: | --- |
| `raw` | 446 | |
| `wiki` | 417 | |
| `ops` | 387 | |
| `runs` | 166 | |
| `tests` | 149 | |
| `system` | 71 | |
| `external-reports` | 55 | |
| `.codex` | 10 | |
| `tmp` | 7 | |
| `.obsidian` | 5 | |
| `tools` | 5 | |
| `.github` | 2 | |

핵심 보정: 실제 ZIP 파일 수는 1,740개다. 압축 해제 후 import/test를 수행하면 `__pycache__` 같은 런타임 산출물이 생길 수 있으므로, 실제 배포물 수치에는 ZIP inventory만 사용해야 한다.

### 4.2 코드와 테스트 규모

| 영역 | 파일 수 | 전체 LOC | 비공백 LOC |
| --- | ---: | ---: | ---: |
| `ops/**/*.py` | 179 | 54,528 | 48,547 |
| `tests/**/*.py` | 143 | 42,845 | 38,289 |
| `tools/**/*.py` | 5 | 789 | 699 |

AST 기준 `tests/**/*.py`의 `test_` 함수 수는 909개다. 이는 두 신규 리뷰가 공통으로 언급한 “전체 테스트 함수 909개”와 일치한다.

대형 파일 상위권도 리뷰의 진단과 일치한다. 특히 `ops/scripts/auto_improve_readiness_runtime.py`, `ops/scripts/mutation_proposal_runtime.py`, `tests/test_mechanism_review.py`, `tests/test_mutation_proposal.py`가 대형 파일이다. 다만 현재 파일 기준 LOC는 리뷰의 시점별 값과 약간 다르다. 예를 들어 `tests/test_mechanism_review.py`는 현재 1,967 LOC이고, `ops/scripts/auto_improve_readiness_runtime.py`는 1,663 LOC다.

### 4.3 Test evidence 상태

`ops/reports/test-execution-summary.json` 실제 핵심 필드는 다음과 같다.

| 필드 | 실제 값 |
| --- | --- |
| `suite` | `report-contract-summary` |
| `status` | `pass` |
| `represents_full_suite` | `False` |
| `full_suite_evidence.status` | `not_represented` |
| `not_full_suite_reason` | `report-contract-summary is a targeted report-contract subset; use full release-builder evidence before treating this as full-suite proof.` |

따라서 리뷰들의 “132개 계약 테스트 통과는 full-suite 증거가 아니다”라는 판단은 실제 파일과 일치한다. 추가로 실제 Makefile에는 `test-execution-summary-full` target이 이미 존재한다.

```make
test-execution-summary-full:
    $(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)" --suite full --collect-nodeids -- $(PYTHON) -m pytest $(PYTEST_SERIAL_FLAGS)
```

그러나 실제 `ops/reports/test-execution-summary-full.json`은 존재하지 않고, `ops/reports/test-execution-summary-shards/`도 비어 있다. 따라서 개선 과제는 “target 만들기”가 아니라 다음이다.

- full suite를 실제로 실행해 canonical artifact를 생성한다.
- shard별 JSON과 aggregate digest를 봉인한다.
- report-contract summary가 full-suite evidence처럼 소비되지 않도록 consumer를 분리한다.
- subprocess/flaky lane은 별도 artifact로 격리하되, clean release 정책에 어떻게 반영되는지 명확히 한다.

### 4.4 Auto-improve readiness 상태

`ops/reports/auto-improve-readiness.json` 실제 핵심 필드는 다음과 같다.

| 항목 | 실제 값 |
| --- | --- |
| `can_execute_trial` | `true` |
| `can_promote_result` | `false` |
| `learning_readiness.status` | `learning_uncertain` |
| `learning_readiness.gate_effect` | `review_required` |
| `learning_readiness.likely_to_learn` | `false` |
| `attempts_considered` | 7 |
| `min_attempts_considered` | 10 |
| `session_reports_considered` | 3 |
| `telemetry_coverage_ratio` | 0.0 |
| `rework_count` | 2 |
| `hold_moving_average` | 0.2857 |
| `discard_moving_average` | 0.1429 |
| `defect_escape_pair_count` | 1 |

실제 learning signals는 다음이다.

| signal | severity | 실제 detail 요약 |
| --- | --- | --- |
| `outcome_metrics_attempt_history_below_minimum` | `warn` | attempts_considered=7 is below min_attempts_considered=10 |
| `loop_health_telemetry_coverage_missing` | `warn` | loop_health.telemetry_coverage_ratio=0.0000 so routing provenance still lacks telemetry-backed learning evidence |
| `recent_hold_moving_average` | `warn` | hold_moving_average=0.2857 is at or above threshold=0.2500 |
| `high_rework` | `warn` | rework_count=2 is at or above threshold=1 |
| `defect_escape_proxy` | `warn` | defect_escape_pair_count=1 is at or above threshold=1 |

중요한 보정: `loop_health_telemetry_coverage_missing`은 실제 JSON에서 `severity=warn`이다. 하지만 이 값이 P0가 아니라는 뜻은 아니다. `can_promote_result=false`의 직접 원인 중 하나이므로 운영 우선순위는 여전히 높다.

### 4.5 Telemetry coverage 0의 정확한 원인

두 리뷰는 “telemetry coverage 0”을 핵심 병목으로 잡았다. 실제 파일을 보면, 이 표현은 “run telemetry 파일이 전혀 없다”는 뜻이 아니라 **auto-improve readiness가 최신 routing provenance aggregate를 선택했을 때 그 aggregate의 loop-health telemetry coverage가 0**이라는 뜻에 가깝다.

실제 aggregate 상태는 다음과 같다.

| aggregate | generated_at | run_count | telemetry_report_count | telemetry coverage 성격 |
| --- | --- | ---: | ---: | --- |
| `auto-improve-2026-05-02t03-27-31z.json` | `2026-05-05T02:55:00Z` | 1 | 0 | telemetry=0.0 |
| `auto-improve-20260428-readiness-preflight.json` | `2026-04-30T22:34:38Z` | 0 | 0 | telemetry=0.0 |
| `standalone-run-telemetry.json` | `2026-05-02T03:03:47Z` | 6 | 3 | telemetry=0.5 |

`auto-improve-readiness.json`의 diagnostics는 최신 aggregate로 `ops/reports/routing-provenance-aggregates/auto-improve-2026-05-02t03-27-31z.json`을 사용한다. 이 aggregate는 `run_count=1`, `telemetry_report_count=0`, `telemetry_coverage=0.0`이며, `missing_telemetry_coverage`, `unfinalized_runs_present`, `recent_hold_present`를 health flag로 가진다.

반면 `standalone-run-telemetry.json`은 `run_count=6`, `telemetry_report_count=3`, telemetry coverage 0.5를 가진다. 그러므로 다음 개선은 단순히 run-telemetry 파일을 쓰는 것만으로 충분하지 않다. **session aggregate 선택·merge·backfill 규칙**을 고쳐야 한다.

권장 보정:

1. 최신 aggregate 하나만 절대화하지 말고, current proposal family와 관련된 aggregate를 우선 선택하거나 병합한다.
2. `run_telemetry`가 존재하는 standalone history를 최신 auto-improve session의 비어 있는 artifact reference에 backfill할지 여부를 명시한다.
3. `proposal_id`, `source_candidate_id`, `observed_at`, `decision_record`, `run_telemetry` path가 비어 있는 경우 “unknown”으로만 남기지 말고 복구 가능 source와 복구 실패 source를 분리한다.
4. readiness metric에는 “latest session coverage”와 “proposal-family historical coverage”를 별도 필드로 둔다.

### 4.6 Mechanism review와 mutation proposal 상태

실제 `mechanism-review-candidates.json`은 candidate 1개를 방출한다.

| 항목 | 실제 값 |
| --- | --- |
| candidate id | `mechanism_eval_stagnation_candidate__auto-improve-iteration-persistence-runtime` |
| primary target | `ops/scripts/auto_improve_iteration_persistence_runtime.py` |
| supporting target | `ops/schemas/run-telemetry.schema.json` |
| metrics triggered | `stage1_same_eval_rate` |
| runs examined | 4 |
| same eval runs | 4 |
| discard runs | 1 |
| latest baseline/candidate eval | 4792 / 4792 |

실제 `mutation-proposals.json`도 proposal 1개를 방출한다.

| 항목 | 실제 값 |
| --- | --- |
| proposal id | `repeated_same_eval_or_discard__auto-improve-iteration-persistence-runtime` |
| failure mode | `repeated_same_eval_or_discard` |
| primary target | `ops/scripts/auto_improve_iteration_persistence_runtime.py` |
| supporting target | `ops/schemas/run-telemetry.schema.json` |
| must change tests | `tests/test_auto_improve_iteration_runtime.py` |
| expected binary signal | `candidate_eval > baseline_eval` 또는 equal-score strict secondary improvement |

따라서 두 신규 리뷰와 기존 보고서의 단일 mechanism 실험 권고는 실제 파일과 정확히 맞다.

### 4.7 `auto_improve_iteration_persistence_runtime.py`의 현재 구현 상태

두 리뷰는 `auto_improve_iteration_persistence_runtime.py`를 고쳐야 한다고 말한다. 실제 파일을 보면 일부 기반은 이미 있다.

| 기능 | 실제 파일 상태 | 다음 개선 방향 |
| --- | --- | --- |
| `proposal_id` / `source_candidate_id` 쓰기 | `write_iteration_telemetry()` payload에 포함 | 기존 run/history/session aggregate backfill과 outcome metrics 연결이 필요 |
| decision record fallback | result → existing telemetry → promotion report 순서로 복구 | 모든 decision 상태(HOLD/DISCARD/SKIPPED/PROMOTE) envelope 통일 필요 |
| timeout merge | nested timeout fields merge 구현 | subprocess drain race와 별도 lane 연결 필요 |
| `behavior_delta` | 문자열 path/field 보존 | `behavior_delta_digest`, same-eval reason, strict secondary improvement machine check 필요 |
| `observed_at` | run-telemetry schema/property에 없음 | outcome metrics와 aggregate에서 사용하는 observed timestamp를 telemetry envelope에 포함할지 결정 필요 |
| same eval reason | schema/property에 없음 | `same_eval_reason` enum 또는 equivalent classifier 필요 |
| targeted tests | 7개 통과 | 기존 기능 중복 테스트보다 missing behavior를 검증해야 함 |

이 때문에 “behavior_delta 추가”라는 표현은 너무 넓다. 정확한 과제는 다음이어야 한다.

- 기존 `behavior_delta` path를 유지하면서 digest 또는 summary를 추가한다.
- eval 동점 상황을 `noop_mutation`, `insufficient_benchmark`, `secondary_improvement_present`, `unmeasured_delta`, `unknown` 등으로 분류한다.
- promotion report, run telemetry, outcome metrics가 같은 decision/proposal/source candidate를 가리키게 한다.
- 최신 auto-improve session aggregate가 telemetry coverage 0으로 덮어쓰는 문제를 막는다.

### 4.8 Release evidence 상태

실제 핵심 release report는 다음 상태다.

| Artifact | 실제 상태 | 해석 |
| --- | --- | --- |
| `release-closeout-summary.json` | `status=pass`, `release_readiness_state=conditional_pass`, `clean_release_ready=false`, `machine_release_allowed=false`, `operator_release_allowed=true` | 조건부 operator release만 가능 |
| `release-closeout-batch-manifest.json` | `status=fail`, `batch_integrity_status=pass`, `release_authority_status=conditional_pass`, `clean_lane_status=fail` | batch integrity는 pass이나 clean lane 실패 |
| `release-evidence-dashboard.json` | `status=attention`, accepted risk gate attention 3 | 주의 상태 |
| `release-lane-summary.json` | `clean_lane_status=fail`, `conditional_lane_status=pass`, `machine_release_status=blocked`, `operator_release_status=allowed` | clean/machine 차단 |
| `release-clean-blocker-ledger.json` | blocker 2개 | accepted risk 때문에 clean lane 차단 |
| `operator-release-summary.json` | `status=attention`, `sealed_conditional_pass` | operator conditional |
| `release-evidence-cohort.json` | `clean_lane_contract.status=fail` | strict cohort/clean lane 미완료 |

두 리뷰의 release lane 진단은 실제 파일과 일치한다.

### 4.9 Clean blocker ledger

실제 clean blocker는 2개다.

| blocker id | source | severity | gate effect | clean lane effect |
| --- | --- | --- | --- | --- |
| `auto_improve_readiness:learning_blocked_by_review_required` | `auto_improve_readiness` | warn | accepted_risk | blocks_clean_lane |
| `generated_index:generated_index_archive_advisory` | `generated_index` | warn | accepted_risk | blocks_clean_lane |

리뷰들이 강조한 “operator_release_allowed=true가 clean/machine release 가능을 뜻하지 않는다”는 결론은 정확하다.

### 4.10 Batch manifest fresh-extract 재현성 문제

체크인된 `ops/reports/release-closeout-batch-manifest.json`의 source freshness는 다음과 같다.

| 필드 | 체크인 값 |
| --- | --- |
| `source_evidence_freshness.status` | `pass` |
| `source_file_count` | 1408 |
| `latest_source_mtime` | `2026-05-05T02:54:40Z` |
| `latest_source_path` | `tests/test_generated_report_contracts.py` |
| `changed_after_generated_at_count` | 0 |

하지만 fresh extract 후 같은 스크립트를 `--check`로 실행하면 실패가 재현된다.

```text
batch manifest check failed: content differs from ops/reports/release-closeout-batch-manifest.json
batch manifest check failed: source files changed after checked-in manifest generated_at
source_evidence_freshness status=fail; changed_after_generated_at_count=1408; source_file_count=1408
```

실제 코드 `ops/scripts/release_closeout_batch_manifest.py`는 `_source_evidence_freshness()`에서 `path.stat().st_mtime`을 사용한다. 그리고 현재 script에는 `zipfile`, `ZipInfo`, `--zip-metadata` 같은 ZIP metadata 기반 검증 경로가 없다. 따라서 두 리뷰의 fresh-extract 오탐 진단은 실제 파일과 일치한다.

다만 보정해야 할 점이 있다. ZIP 멤버 타임스탬프는 timezone을 담지 않는다. 현재 ZIP timestamp를 KST local time으로 해석하면, release source exclude policy 적용 후 `generated_at=2026-05-05T02:55:33Z` 이후 source 변경은 0개이고, 전체 ZIP 파일 기준으로는 `ops/reports/release-closeout-batch-manifest.json` 1개만 이후다. 반대로 ZIP timestamp를 무조건 UTC로 해석하면 source 5개가 이후처럼 보인다. 따라서 구현 시 다음 필드가 필요하다.

- `source_evidence_freshness.basis`: `filesystem_mtime` / `zip_member_timestamp`
- `source_evidence_freshness.timestamp_timezone_assumption`: 예: `Asia/Seoul` 또는 `archive_local_time`
- `source_evidence_freshness.archive_timestamp_has_timezone`: `false`
- `changed_after_generated_at_count`는 source exclude policy 적용 여부를 명시

### 4.11 Report-reference manifest 불일치

실제 `external-reports/report-reference-manifest.json`은 다음 값을 담고 있다.

| 항목 | manifest 값 | 실제 업로드 ZIP |
| --- | --- | --- |
| current distribution name | `LLMwiki(12).zip` | `LLMwiki.zip` |
| current distribution sha256 | `470475533932575a0e42dc5e770b005290ee94e5775f9faa7707fc4f196cf209` | `aef28bb86842b38f596af3e07adc1115c141c8f5175d4c08c2f54a425e60a9f0` |
| current distribution entry count | 1829 | 1839 |
| basis zip name | `LLMwiki.zip` | `LLMwiki.zip` |
| basis zip sha256 | `0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93` | `aef28bb86842b38f596af3e07adc1115c141c8f5175d4c08c2f54a425e60a9f0` |
| basis zip entry count | 1819 | 1839 |

이 불일치는 두 신규 리뷰가 지적한 대로 실제다. 특히 current distribution이 과거 ZIP을 가리키므로, 현재 ZIP을 검토했다는 release evidence closure가 약해진다.

### 4.12 `tmp/` 배포 오염

실제 ZIP에는 다음 `tmp/` 파일이 포함되어 있다.

- `tmp/_patch_vocab_refs.py`
- `tmp/codex-plan-review/archive-execution-manifest.json`
- `tmp/codex-plan-review/artifact-freshness-report.json`
- `tmp/codex-plan-review/current-raw-registry-evidence-bundle.json`
- `tmp/codex-plan-review/current-release-evidence-cohort-strict.json`
- `tmp/codex-plan-review/raw-registry-cross-environment-matrix.json`
- `tmp/codex-plan-review/release-closeout-summary.json`

`.gitignore`는 `tmp/`를 제외 대상으로 삼고 있으므로, 배포 ZIP 생성 경로에서 tmp directory를 명시적으로 제외하거나 packaging 직전 clean step을 강제해야 한다. 이 문제는 auto-improve 학습 병목과 별개인 release hygiene 문제다. 같은 PR/실험에 섞으면 다시 리포트·테스트 갱신 루프로 빠질 수 있다.

---

## 5. 두 신규 리뷰의 주장별 판정 매트릭스

| 주장/권고 | 리뷰 A | 리뷰 B | 기존 보고서 | 실제 파일 대조 | 최종 판정 |
| --- | --- | --- | --- | --- | --- |
| 테스트 부족이 아니라 테스트/리포트가 개선 대체물이 됨 | 강함 | 강함 | 강함 | auto readiness, mutation proposal, full-suite absence가 뒷받침 | 유지 |
| `repeated_same_eval_or_discard` 단일 후보 우선 | 강함 | 강함 | 강함 | mutation/mechanism reports가 동일 후보 방출 | 유지 |
| telemetry coverage 0 해소가 P0 | 강함 | 강함 | 강함 | readiness diagnostics 최신 aggregate coverage 0 | 유지하되 aggregate 선택/merge 문제로 정밀화 |
| full-suite 증거 부재 | 강함 | 강함 | 강함 | full summary artifact/shard 없음 | 유지 |
| batch manifest fresh-extract 오탐 | 강함 | 강함 | 약함 | 직접 재현됨 | 신규 P0로 격상 |
| report-reference manifest current ZIP mismatch | 강함 | 강함 | 약함 | 실제 manifest가 `LLMwiki(12).zip` 참조 | 신규 P0로 격상 |
| tmp 오염 | 일부 | 강함 | 약함 | ZIP 내 7개 파일 확인 | 신규 P0 release hygiene |
| clean/operator/machine lane 분리 | 강함 | 강함 | 강함 | release lane/ledger/closeout 모두 조건부 상태 | 유지 |
| no test-only promotion | 강함 | 강함 | 중간 | 현재 문제 양상과 부합 | 운영 규칙으로 도입 |
| learning-delta-scoreboard | 강함 | 강함 | 없음/약함 | 현재 단일 scoreboard artifact 없음 | P1로 도입 |
| 대형 런타임 분해 | 강함 | 중간 | 약함 | structural budget와 LOC가 뒷받침 | P2로 유지 |
| subprocess timeout/drain race | 강함 | 강함 | 강함 | 이번 검토에서 직접 재현하지 않음 | 별도 lane에서 다룰 것 |
| evidence scope 전면 표기 | 강함 | 중간 | 약함 | partial/full 혼동 위험 실재 | P1로 도입 |

---

## 6. 실질 개선으로 전환하기 위한 우선순위

### P0-A. Release evidence basis를 먼저 고정한다

이 작업은 auto-improve 학습 개선과 섞지 말고 release hygiene lane에서 처리한다.

#### 대상 파일

- `ops/scripts/release_closeout_batch_manifest.py`
- `ops/schemas/release-closeout-batch-manifest.schema.json`
- `external-reports/report-reference-manifest.json`
- `ops/scripts/external_report_reference_manifest.py`
- `Makefile`
- ZIP packaging target 또는 release finalizer
- 관련 테스트: `tests/test_external_report_reference_manifest.py`, batch manifest 관련 테스트

#### 해야 할 일

1. `release_closeout_batch_manifest.py`에 `--zip-metadata <zip>` 입력을 추가한다.
2. `source_evidence_freshness.basis`를 `filesystem_mtime`과 `zip_member_timestamp`로 분리한다.
3. ZIP timestamp timezone basis를 명시한다. 최소한 “archive local timestamp interpreted as Asia/Seoul for this package”처럼 재현 가능한 정책이 필요하다.
4. fresh extract check가 filesystem mtime 때문에 실패할 때, ZIP metadata basis check로 배포물 자체를 검증할 수 있게 한다.
5. `report-reference-manifest`를 실제 current ZIP SHA/entry count로 재생성한다.
6. packaging 직전에 `tmp/`, `.venv/`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `__pycache__`를 제외한다.
7. `distribution-provenance.json` 또는 equivalent finalizer artifact를 만들어 ZIP SHA, entry count, source tree fingerprint, generated_at을 봉인한다.

#### 완료 조건

- fresh extract에서 `--zip-metadata` basis batch check가 통과한다.
- filesystem mtime basis와 zip metadata basis가 리포트에 구분되어 기록된다.
- `external-reports/report-reference-manifest.json`의 current distribution SHA가 실제 ZIP SHA와 일치한다.
- ZIP 내 `tmp/` 파일 수가 0이다.
- clean lane blocker 중 release evidence basis 관련 blocker가 사라진다.

### P0-B. Auto-improve telemetry discoverability를 정확히 복구한다

이 작업은 learning lane에서 처리한다. release packaging, full-suite artifact 생성과 같은 PR/실험에 섞으면 안 된다.

#### 대상 파일

- `ops/scripts/auto_improve_iteration_persistence_runtime.py`
- `ops/scripts/auto_improve_readiness_runtime.py`
- `ops/scripts/outcome_metrics_runtime.py` 또는 outcome metrics 생산자
- `ops/schemas/run-telemetry.schema.json`
- `ops/schemas/behavior-delta.schema.json`
- `tests/test_auto_improve_iteration_runtime.py`
- 필요한 경우 routing provenance aggregate 테스트

#### 해야 할 일

1. `write_iteration_telemetry()`가 이미 쓰는 `proposal_id`, `source_candidate_id`, `decision_record`, `behavior_delta`를 outcome metrics와 routing provenance aggregate가 확실히 발견하도록 한다.
2. 최신 aggregate 하나가 coverage 0이면 전체 readiness를 0으로 덮는 구조를 보정한다. proposal-family related history와 latest session history를 분리한다.
3. run-local telemetry, promotion report, proposal snapshot, session report 사이의 backfill 우선순위를 명문화한다.
4. `observed_at`을 run telemetry에 넣을지, 아니면 outcome metrics 전용으로 둘지 결정하고 일관되게 적용한다.
5. same-eval reason을 machine-readable하게 분류한다.
6. 기존 `behavior_delta` path에 더해 `behavior_delta_digest` 또는 equivalent strict summary를 둔다.
7. equal-score promotion에서는 “어떤 strict secondary improvement가 있었는지”를 promotion report와 readiness/outcome metrics가 함께 읽을 수 있게 한다.

#### 완료 조건

- `auto-improve-readiness.json`에서 latest session coverage와 proposal-family historical coverage가 구분된다.
- `telemetry_coverage_ratio`가 0에서 양수로 오르거나, coverage 0의 원인이 “현재 세션 scope_blocked”로 명확히 분류된다.
- 최근 attempts에서 `proposal_id`, `source_candidate_id`, `observed_at`, `run_telemetry`, `promotion_report` 공백이 줄어든다.
- 같은 proposal이 다음 queue에 동일 failure mode로 다시 떠오르지 않는다.
- `candidate_eval == baseline_eval`이어도 strict secondary improvement가 없으면 promote하지 않는다.
- 새 테스트는 기존 7개 테스트가 이미 보장하는 동작을 중복하지 않고, aggregate discoverability와 same-eval reason을 검증한다.

### P0-C. Full-suite evidence와 targeted summary의 소비 경로를 분리한다

이 작업은 test evidence lane에서 처리한다.

#### 대상 파일

- `ops/scripts/test_execution_summary.py`
- `ops/schemas/test-execution-summary.schema.json`
- `Makefile`
- `tests/test_test_execution_summary.py`
- `tests/test_makefile_static_gates.py`
- release closeout consumer

#### 해야 할 일

1. 이미 존재하는 `test-execution-summary-full` target을 실제 release builder에서 실행한다.
2. `ops/reports/test-execution-summary-full.json`을 생성하고 canonical promote한다.
3. shard directory를 비어 있지 않게 만들고, shard digest/count를 aggregate에 봉인한다.
4. `test-execution-summary.json`은 계속 report-contract summary로 두되, release clean lane에서 full-suite evidence로 소비하지 못하게 한다.
5. 장시간 suite가 flaky/subprocess 문제로 불안정하면 subprocess lane을 별도 artifact로 분리한다.

#### 완료 조건

- `ops/reports/test-execution-summary-full.json` 존재
- `represents_full_suite=true`
- shard artifacts non-empty
- aggregate count와 shard digest 일치
- report-contract summary는 release 품질 증거가 아니라 contract evidence로만 쓰임

---

## 7. “테스트 반복만 하는 양상”을 끊는 운영 규칙

### 규칙 1. Test-only promotion 금지

다음 예외를 제외하고 테스트만 바뀐 변경은 실질 개선으로 승격하지 않는다.

- 기존 테스트가 명백히 잘못된 요구사항을 고정하고 있어 정정하는 경우
- 외부 공식 스펙/API 변경으로 contract update가 필요한 경우
- flaky test quarantine으로 full verification 신뢰도를 회복하는 경우

그 외 테스트 변경에는 반드시 하나 이상이 동반되어야 한다.

- runtime/script/schema behavior change
- release verification reproducibility improvement
- telemetry/output behavior change
- accepted risk 제거
- full-suite artifact 대표성 회복

### 규칙 2. 생성 산출물만 바뀐 변경은 개선 건수에서 제외

다음 변경은 “실질 개선” 집계에서 제외한다.

- generated artifacts only
- report refresh only
- schema-only alignment without runtime delta
- snapshot/fixture expected output refresh only
- shape-only test addition

### 규칙 3. 한 사이클에 하나의 failure mode만 닫는다

현재 단일 failure mode는 `repeated_same_eval_or_discard`다. 이 실험에는 release reference manifest, batch manifest ZIP metadata, tmp cleanup, full-suite sharding을 섞지 않는다.

### 규칙 4. Same-eval promotion은 secondary axis를 사전 선언한다

`candidate_eval > baseline_eval`이 어려운 상황에서는 다음 중 하나를 사전에 고른다.

- telemetry coverage 증가
- decision/proposal/source candidate recoverability 증가
- hold/discard reason category 감소
- finalized run ratio 증가
- behavior delta digest 생성
- accepted risk 제거
- timeout/drain race 오분류 감소

선언하지 않은 사후 지표를 근거로 promote하지 않는다.

### 규칙 5. Evidence scope를 모든 주요 summary artifact 전면에 둔다

권장 필드:

```json
{
  "evidence_scope": "report_contract_subset | full_suite | learning_loop | release_provenance | release_authority",
  "represents_full_suite": false,
  "represents_runtime_learning": false,
  "represents_release_contract_only": true
}
```

### 규칙 6. Release lane과 learning lane을 별도 scoreboard로 본다

단일 “green” 상태를 만들지 말고 다음 네 축을 분리한다.

| Scoreboard | 핵심 지표 | 실패 예 |
| --- | --- | --- |
| Learning delta | telemetry coverage, hold/discard, same-eval reason, behavior delta | coverage 0, same eval unknown |
| Test evidence | full-suite artifact, shard digest, flaky/subprocess lane | only report-contract summary |
| Release provenance | ZIP SHA, entry count, manifest freshness basis, tmp exclusion | stale ZIP reference, mtime false fail |
| Release authority | clean/machine/operator/conditional lane | operator allowed but machine blocked |

---

## 8. 권장 실행 순서

### 1단계: Release hygiene hotfix branch

목표는 실제 배포물 기준 증거를 맞추는 것이다.

1. `tmp/` 오염 제거 및 packaging exclusion 확인
2. `report-reference-manifest` current ZIP을 실제 SHA로 재생성
3. batch manifest에 ZIP metadata basis 추가
4. fresh extract에서 ZIP metadata basis 검증 통과
5. closeout batch, evidence cohort, dashboard를 같은 source fingerprint로 재생성

이 단계는 auto-improve runtime을 건드리지 않는다.

### 2단계: Learning mechanism experiment branch

목표는 `repeated_same_eval_or_discard`를 단일 failure mode로 닫는 것이다.

1. proposal id: `repeated_same_eval_or_discard__auto-improve-iteration-persistence-runtime`
2. primary target: `ops/scripts/auto_improve_iteration_persistence_runtime.py`
3. supporting target: `ops/schemas/run-telemetry.schema.json`
4. test target: `tests/test_auto_improve_iteration_runtime.py`
5. secondary axis: telemetry discoverability/recoverability
6. 금지: release packaging, full-suite sharding, tmp cleanup을 같은 실험에 포함하지 않음

이 단계의 산출물은 baseline/candidate assessment, behavior-delta, promotion-report, run-telemetry, outcome metrics, readiness refresh다.

### 3단계: Full-suite evidence branch

목표는 full-suite 대표 증거를 따로 만드는 것이다.

1. `test-execution-summary-full` target을 실제 release-builder path에 연결
2. shard artifact 생성
3. aggregate digest/count 봉인
4. subprocess lane 분리
5. release closeout consumer가 full summary만 full verification evidence로 사용하게 변경

### 4단계: Governance hardening branch

목표는 같은 정체가 반복되지 않게 하는 것이다.

1. learning-delta-scoreboard 도입
2. no test-only promotion rule 문서화 및 check 추가
3. changed-files manifest 기반 workflow dependency planner 연결
4. generated artifact refresh를 closeout 단계로 집중
5. 대형 runtime/test helper를 P2로 점진 분해

---

## 9. 상세 Definition of Done

### P0 완료 조건

| 영역 | 완료 조건 |
| --- | --- |
| Release provenance | current ZIP SHA/entry count가 실제 ZIP과 일치 |
| Batch freshness | fresh extract에서 ZIP metadata basis 검증 통과 |
| Timestamp basis | filesystem/zip basis와 timezone assumption이 리포트에 기록 |
| Tmp hygiene | ZIP 내 `tmp/` 파일 0 |
| Learning candidate | single proposal/failure mode가 active experiment로 고정 |
| Telemetry discoverability | latest session coverage와 proposal-family coverage가 분리 또는 병합 정책으로 설명됨 |
| Same-eval reason | 동점 원인이 machine-readable category로 남음 |
| Behavior delta | path뿐 아니라 digest/strict summary가 기록 |
| Test evidence | targeted summary가 full-suite로 소비되지 않음 |
| Test discipline | 테스트-only/fixture-only 변경이 improvement로 승격되지 않음 |

### P1 완료 조건

| 영역 | 완료 조건 |
| --- | --- |
| Full-suite artifact | `test-execution-summary-full.json` 존재, `represents_full_suite=true` |
| Shards | shard artifacts non-empty, aggregate count/digest 일치 |
| Scoreboard | `learning-delta-scoreboard`가 실질 개선 여부를 판정 |
| Release authority | clean/machine/operator/conditional lane taxonomy 일치 |
| Subprocess lane | timeout/drain race를 full suite와 별도 diagnostic으로 분리 |
| Evidence scope | 주요 summary artifact가 evidence scope를 명시 |

### P2 완료 조건

| 영역 | 완료 조건 |
| --- | --- |
| Runtime complexity | 대형 runtime을 collector/normalizer/classifier/writer로 점진 분해 |
| Test helper complexity | 대형 테스트 파일에서 fixture/data builder 중복 제거 |
| Generated artifacts | generated-only 변경을 closeout 단계로 집중 |
| Workflow planner | changed-files manifest가 필요한 검증 lane을 자동 선택 |
| Release finalizer | distribution provenance가 ZIP 내부/외부에서 봉인됨 |

---

## 10. 다음 커밋/작업 제목 제안

가장 먼저 해야 할 작업은 두 개로 나눠야 한다.

1. `Fix ZIP-based release evidence verification and current distribution provenance`
2. `Close repeated same-eval auto-improve telemetry discoverability gap`

이 둘을 하나의 작업으로 합치면 다시 테스트·리포트·릴리스 산출물이 뒤섞여 실제 mechanism 개선 여부를 판정하기 어려워진다.

---

## 11. 이번 검토의 결론

두 신규 리뷰는 기존 보고서를 대체한다기보다, 기존 보고서의 방향을 더 구체적인 실행 항목으로 보강한다. 실제 파일 대조 결과, 핵심 진단은 유효하다. 다만 이제는 “테스트를 더 돌리자”나 “리포트를 더 정리하자”가 아니라, 다음 네 문장을 운영 규칙으로 고정해야 한다.

1. 부분 테스트 통과는 full-suite evidence가 아니다.
2. telemetry coverage가 0이거나 same-eval reason이 unknown이면 학습 개선을 주장하지 않는다.
3. fresh extract에서 실패하는 release check는 배포물 검증이 아니라 검증 환경 검증이므로 ZIP metadata basis로 고친다.
4. current distribution manifest가 실제 ZIP을 가리키기 전에는 release evidence closure가 완결됐다고 보지 않는다.

이 네 가지를 닫은 뒤에야, `auto_improve_iteration_persistence_runtime.py`에 대한 단일 mechanism 실험이 “테스트를 고친 것”이 아니라 “실질 개선을 만든 것”으로 평가될 수 있다.
