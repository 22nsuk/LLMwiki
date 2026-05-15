# LLMwiki 통합 리뷰 2종 실제 파일 대조 개선 보고서

> archive_status: superseded
> superseded_by: external-reports/llmwiki_two_20260511_reviews_crosscheck_improvement_report_20260511.md
> archived_reason: 2026-05-11 actual-file cross-check narrowed the clean baseline and remaining release blockers more precisely.

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-10 KST |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_integrated_reviews_actual_file_crosscheck_improvement_report_20260510.md` |
| 직접 검토한 업로드 리뷰 1 | `llmwiki_three_reviews_integrated_report_20260510.md` |
| 직접 검토한 업로드 리뷰 2 | `llmwiki_three_reviews_integrated_improvement_report_20260510.md` |
| 추가 대조 리뷰 | `llmwiki_current_zip_vs_20260509_crosscheck_improvement_report_20260510.md` |
| 저장소 내부 기준 리뷰 | `external-reports/llmwiki_two_uploaded_reviews_actual_crosscheck_improvement_report_20260509.md` |
| 실제 검토 ZIP | `LLMwiki(30).zip` |
| ZIP SHA-256 | `13fc833c0bcafee2d17aefd62e706554e558635db6f9114e2a2c2dacc0a29018` |
| 검토 방식 | 업로드 리뷰 2종 전수 검토 + 기존 리뷰 대조 + 실제 ZIP 추출본 직접 재실행 |
| 최종 한줄 판정 | **두 업로드 리뷰는 방향은 대체로 맞지만, 핵심 fingerprint 해석에서 실제 ZIP 기준보다 낙관적이며, 우선순위 1번은 “23cde 계열 유지”가 아니라 “실제 배포물 기준 authoritative fingerprint를 다시 정의·재생성”이어야 한다.** |

---

## 0. 최종 결론

업로드된 두 문서는 모두 잘 정리된 통합 리뷰이며, 다음 큰 줄기에서는 실제 파일과 **대체로 일치**한다.

1. 현재 ZIP이 machine clean release-ready 상태가 아니라는 점
2. release evidence가 단일 cohort로 닫히지 않았다는 점
3. `release-closeout-batch-manifest.json`에 distribution ZIP binding이 빠져 있다는 점
4. `auto-improve-readiness.json`이 machine-blocked 상태를 충분히 반영하지 못한다는 점
5. release ZIP 생성 로직 자체는 정상이라는 점

하지만 실제 ZIP을 다시 풀어 직접 검증한 결과, 두 문서는 공통으로 다음 세 가지를 **과도하게 낙관**하거나 **원인 진단을 빗나가게** 서술한다.

### A. `23cde...`를 “pristine 추출본에서 재현되는 live truth”처럼 다루는 부분은 실제 재검증과 맞지 않는다

실제 ZIP 추출본에서 아래를 다시 돌리면:

- `python -c "from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint ..."` → `d0c6a3b8...`
- `make artifact-freshness-check`가 새로 쓴 candidate report → `source_tree_fingerprint=d0c6a3b8...`
- `make release-distribution-zip`이 새로 쓴 release smoke report → `source_tree_fingerprint=d0c6a3b8...`
- `make test-artifact-finalization` → **2 failed, 4 passed**

즉, 업로드 리뷰들이 “리뷰 A/B는 pristine에서 23cde가 맞았고 리뷰 C만 workcopy 오염으로 d0c6a3를 봤다”는 식으로 정리한 부분은 실제 ZIP 기준 진실 계층을 정확히 반영하지 못한다. **실제 배포물 추출본에서도 d0c6a3 계열이 바로 재현된다.**

### B. 원인을 `.venv`, `tmp`, `.pyc`, mtime 오염 쪽으로 돌린 설명은 핵심을 비켜간다

실제 코드 `ops/scripts/source_tree_fingerprint_runtime.py`를 보면:

- `.venv/`, `tmp/`, `build/`, `ops/reports/`, `external-reports/`, `.pyc`, `.egg-info` 등은 이미 release source-tree fingerprint 계산에서 제외된다.
- fingerprint 본체는 **path + sha256 + size**를 정렬한 manifest를 해시한다.
- 내부 signature에는 mtime이 쓰이지만, 그것은 캐시 무효화용이며 최종 fingerprint payload에는 들어가지 않는다.

따라서 두 업로드 리뷰가 제안한 “`.gitignore` 패턴을 더 제외하자”, “workcopy에서 `.venv`가 생겨서 fingerprint가 흔들린다”는 진단은 **부분적으로는 그럴듯하지만 현재 실제 코드와는 핵심 인과가 맞지 않다.**

### C. `1086 -> 1092` 갱신 제안은 아직 확정 action item으로 쓰기 어렵다

두 업로드 리뷰는 여러 선행 리뷰의 관찰을 따라 `TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT`를 1086에서 1092로 바꾸는 방향을 강하게 제안한다. 그러나 이번 실제 재검증에서는:

- checked-in full summary는 여전히 **1086 passed**
- Makefile expected count도 **1086**
- supported entrypoint 기반 full collect/full summary 재생성은 이 세션에서 최종 봉인까지 완료하지 못함

즉 **1092는 “기존 리뷰들이 보고한 live observation”이지, 이번 실제 대조에서 다시 봉인한 authoritative current value는 아니다.**  
따라서 지금 당장 expected count를 1092로 바꾸는 것은 개선안이 아니라 **미검증 가정 반영**이 될 수 있다.

---

## 1. 검토 범위와 실제 재검증 방식

## 1.1 직접 검토한 문서

### 업로드 리뷰 1
- 파일명: `llmwiki_three_reviews_integrated_report_20260510.md`
- 분량: 437 lines
- 성격: 3개 선행 리뷰의 통합 요약판

### 업로드 리뷰 2
- 파일명: `llmwiki_three_reviews_integrated_improvement_report_20260510.md`
- 분량: 673 lines
- 성격: 통합 요약판을 개선안 중심으로 확장한 상세판

### 추가 대조 문서
- `/mnt/data/llmwiki_current_zip_vs_20260509_crosscheck_improvement_report_20260510.md`
- `external-reports/llmwiki_two_uploaded_reviews_actual_crosscheck_improvement_report_20260509.md`

## 1.2 실제 ZIP 재검증 방식

### 고정 사실 확인
- ZIP SHA-256
- ZIP prefix별 파일 수
- checked-in canonical JSON들의 현재 상태값

### 직접 실행한 검증
- `make static`
- `make artifact-freshness-check`
- `make release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT=tmp/test-release.zip RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT=tmp/test-release-smoke.json`
- `make test-artifact-finalization`
- `python -c "from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint(...)"`

### 실제 추출본 기준 주의사항
이번 보고서는 “원래 작업 트리”가 아니라 **사용자가 올린 ZIP 자체**를 source of truth로 삼았다.  
따라서 본 보고서의 핵심 질문은 다음이었다.

> “이 저장소가 upstream checkout에서 무엇이었는가?”가 아니라,  
> **“사용자가 올린 ZIP을 실제로 풀었을 때 어떤 진실 계층이 재현되는가?”**

이 기준으로 보면, 두 업로드 리뷰의 일부 문장은 upstream checkout 관점에서는 성립할 수 있어도, **현재 사용자가 준 압축본의 실제 재현 진실**로는 다소 부정확하다.

---

## 2. 실제 ZIP에서 다시 확인한 핵심 사실

## 2.1 ZIP 자체

| 항목 | 실제 값 |
| --- | ---: |
| SHA-256 | `13fc833c0bcafee2d17aefd62e706554e558635db6f9114e2a2c2dacc0a29018` |
| 전체 entries | 2,071 |
| 파일 entries | 1,956 |
| 디렉터리 entries | 115 |

## 2.2 ZIP prefix별 파일 수

이 값은 실제 ZIP central directory를 기준으로 다시 셌다.

| prefix | 파일 수 |
| --- | ---: |
| `ops/` | 476 |
| `raw/` | 446 |
| `wiki/` | 417 |
| `runs/` | 263 |
| `tests/` | 172 |
| `system/` | 71 |
| `external-reports/` | 62 |
| 루트 파일 | 18 |

이 값은 업로드 리뷰 2의 “ZIP prefix별 파일 수” 방향성과는 맞지만, 본문 일부의 `ops 476~541`, `tests 172`, `external-reports 62~63` 같은 흔들리는 표현은 정밀 보고서 관점에서는 정리될 필요가 있다. **ZIP 파일 수를 말할 때는 central directory 기준 고정값을 쓰는 편이 정확하다.**

## 2.3 checked-in canonical state

실제 추출본에서 확인한 checked-in 상태는 다음과 같다.

| 파일 | 핵심 상태 |
| --- | --- |
| `ops/reports/release-closeout-summary.json` | `status=pass`, `clean_release_ready=false`, `release_readiness_state=conditional_pass`, `machine_release_allowed=false`, `operator_release_allowed=true` |
| `ops/reports/release-closeout-batch-manifest.json` | `status=fail`, `release_authority_status=conditional_pass`, `sealed_release_status=unsealed_distribution_not_provided`, `distribution_package.status=not_provided` |
| `ops/reports/auto-improve-readiness.json` | `can_promote_result=true` |
| `ops/reports/generated-artifact-index.json` | `status=attention`, `archive_candidate_count=5` |
| `external-reports/report-reference-manifest.json` | `basis_zip.sha256=0a547950...`, `current_distribution_zip_known=false` |
| `ops/reports/test-execution-summary-full.json` | `status=pass`, `pytest_collect_nodeid_digest.nodeid_count=1086` |
| `ops/script-output-surfaces.json` | `source_tree_fingerprint=23cde664...` |
| `ops/reports/release-smoke-report.json` | `source_tree_fingerprint=23cde664...` |
| `ops/reports/artifact-freshness-report.json` | `source_tree_fingerprint=23cde664...`, summary상 schema invalid/stale 0 |

이 checked-in 상태만 보면 두 업로드 리뷰의 주요 요약은 대체로 맞다.  
문제는 **실제 재실행 시 새로 계산되는 값이 여기서 바로 어긋난다**는 점이다.

---

## 3. 직접 재실행 결과: 업로드 리뷰의 핵심 낙관이 깨지는 지점

## 3.1 `make static` — 통과

의존성(`ruff`, `mypy`)을 설치한 뒤 실제 추출본에서 다시 실행한 결과:

- `ruff check ops/scripts tests tools` → pass
- `mypy @ops/mypy-allowlist.txt` → pass

이 항목은 업로드 리뷰들의 판정과 일치한다.  
즉, **정적 품질 게이트는 실제 ZIP 기준으로도 재현된다.**

## 3.2 `make artifact-freshness-check` — 통과, 하지만 새 fingerprint는 `d0c6a3...`

실행 결과:

- `status=pass`
- `schema_invalid_artifact_count=0`
- `stale_artifact_count=0`
- 새로 쓴 report의 `source_tree_fingerprint = d0c6a3b8f12cd1c03939f190aa4eeeddb52e67c2cf6ad6bd8472d0ebe627cf21`

이 의미는 중요하다.

업로드 리뷰들은 “artifact freshness는 pass이므로 이 항목은 닫혔다”고 썼는데, 그 말 자체는 맞다.  
하지만 실제로는 **닫힌 것이 schema-invalid/stale axis일 뿐이고, 그 report가 참조하는 current fingerprint는 checked-in `23cde...`가 아니라 extracted live `d0c6a3...`**다.

즉, 이 항목은 “닫힘”과 동시에 “checked-in current cohort와의 어긋남”을 함께 보여 준다.

## 3.3 `make release-distribution-zip` — 통과, live release smoke fingerprint는 `d0c6a3...`

실행 결과:

- archive root: `LLMwiki`
- manifest comparison: pass
- packed file count: 1493
- 새로 생성된 release smoke report의 `source_tree_fingerprint = d0c6a3...`

이 결과는 두 업로드 리뷰의 다음 서술 중 절반만 맞고 절반은 빗나간다.

### 맞는 부분
- ZIP 생성 로직 자체는 정상이다.
- `LLMwiki` root packaging은 문제 없다.

### 빗나간 부분
- “23cde 계열 artifact가 pristine 기준 current truth일 수 있다”는 뉘앙스는 실제 재실행과 맞지 않는다.
- 실제 배포물 추출본에서 release smoke를 다시 돌리면 **바로 d0c6a3 계열**이 나온다.

## 3.4 `make test-artifact-finalization` — 실제로 2 fail / 4 pass 재현

실행 결과:

- pass 4
- fail 2

실패 테스트:
1. `test_checked_in_generated_artifact_index_matches_live_inventory_and_fingerprints`
2. `test_checked_in_release_smoke_report_matches_live_envelope_fingerprints`

핵심 실패 내용:
- checked-in `source_tree_fingerprint=23cde...`
- live regenerated expected `source_tree_fingerprint=d0c6a3...`

그리고 generated artifact index 쪽은 단순 fingerprint 값만 다른 것이 아니라, archive candidate의 외부 보고서 family/path/suggested archive path가 **escaped path 기준으로 재생성**되며 checked-in payload와 달라진다.

즉, **업로드 리뷰 2가 "리뷰 C(workcopy)에서만 본 현상"처럼 정리한 실패가 실제 ZIP 추출본에서도 그대로 재현된다.**

---

## 4. 두 업로드 리뷰가 잘 짚은 점

## 4.1 공통적으로 정확한 판단

다음 항목들은 두 문서 모두 실제 파일과 잘 맞는다.

### 1) machine clean release-ready가 아님
실제 `release-closeout-summary.json` 기준으로:
- `clean_release_ready=false`
- `machine_release_allowed=false`
- `release_readiness_state=conditional_pass`

이건 정확하다.

### 2) distribution package binding 누락
실제 `release-closeout-batch-manifest.json` 기준으로:
- `distribution_package.status=not_provided`
- `sealed_release_status=unsealed_distribution_not_provided`
- `status=fail`

이건 정확하다.

### 3) auto-improve 과낙관
실제 `auto-improve-readiness.json` 기준으로:
- `can_promote_result=true`

반면 machine release 쪽은 blocked/fail 상태다.  
따라서 “promotion safety가 여전히 열린 문제”라는 평가는 맞다.

### 4) generated-artifact-index의 archive candidate 문제
실제 `generated-artifact-index.json` 기준으로:
- `status=attention`
- archive candidate 5건 존재

이건 정확하다.

### 5) source tree coherence split
실제 checked-in closeout summary 기준으로 component fingerprint는 최소 2개 군집으로 분리되어 있다:
- `23cde...`
- `744169...`

이건 정확하다.

---

## 5. 두 업로드 리뷰의 핵심 보정 포인트

## 5.1 가장 큰 보정: `23cde...`는 “현재 ZIP live truth”가 아니라 “checked-in historical cohort”로 보는 편이 정확하다

두 문서는 공통으로 다음 구조를 취한다.

- checked-in 23cde 군집은 대체로 current
- 리뷰 C의 d0c6a3는 workcopy 오염에서 비롯된 추가 drift
- 따라서 23cde를 중심 cohort로 놓고 나머지를 정리하자

하지만 실제 ZIP 재실행 결과는 반대로 말한다.

### 실제 truth ladder
1. **실제 ZIP에서 지금 재계산되는 live fingerprint:** `d0c6a3...`
2. **checked-in latest-ish artifact cohort:** `23cde...`
3. **older cohort:** `744169...`

즉 지금 필요한 개선은 “23cde를 유지하는 방향”이 아니라:

> **“왜 실제 배포물 추출본은 d0c6a3를 내는가”를 authoritative basis로 받아들이고,  
> 23cde cohort를 current로 되살릴지, 아니면 d0c6a3 기준으로 canonical artifacts를 재생성할지 먼저 결정하는 것”**

이다.

이 우선순위 차이는 매우 크다.  
왜냐하면 23cde를 live truth로 오판하면 이후 모든 개선 계획이 “stale artifact 일부만 갱신”으로 흐르는데, 실제로는 **release truth basis 자체를 다시 정해야 하는 단계**일 수 있기 때문이다.

## 5.2 원인 진단 보정: `.venv/tmp/pyc` exclusion 추가는 이미 구현되어 있다

두 업로드 리뷰는 fingerprint drift의 원인을 주로 다음처럼 본다.

- workcopy에서 `.venv` 생김
- `tmp` 생성물 생김
- `.pyc` 등 노이즈 생김
- 그래서 fingerprint가 흔들림

하지만 실제 코드상 release fingerprint는 이미 다음을 제외한다.

- `ops/reports/`
- `external-reports/`
- `review/`
- `runs/`
- `tmp/`
- `build/`
- `dist/`
- `.venv/`
- `.venv-`
- `.coverage`
- `__pycache__`
- `.pytest_cache`
- `.ruff_cache`
- `.mypy_cache`
- `.egg-info`
- `.pyc`, `.pyo`

따라서 이 부분을 P0/P2 개선안으로 다시 올리는 것은 **실제 원인을 잘못 겨냥한 처방**일 가능성이 높다.

### 더 가능성이 높은 실제 원인
현재 extracted ZIP에는 한글 파일명이 다수 `#U...` escaped path로 materialize되어 있다.  
release source-tree fingerprint는 file **path 자체**를 해시 payload에 포함하므로, upstream checkout과 ZIP extract의 path surface가 다르면 fingerprint가 달라질 수 있다.

즉 실제 원인은 더 가깝게는 다음 둘 중 하나다.

1. **extracted ZIP path surface와 generation workspace path surface가 다르다**
2. **checked-in 23cde cohort가 생성될 당시의 included file set/content와 현재 ZIP이 다르다**

이 둘이 핵심이고, `.venv/tmp` 설명은 현재 코드 구현과 맞지 않는다.

## 5.3 `1092`는 “즉시 수정값”이 아니라 “재검증 후 결정할 후보값”으로 내려야 한다

두 업로드 리뷰는 1086→1092 갱신을 상당히 강하게 주장한다.  
하지만 이번 실제 검토에서 확인 가능한 authoritative current evidence는 아직 다음뿐이다.

- checked-in full summary: 1086
- Makefile expected count: 1086

선행 리뷰들이 관찰한 1092는 중요한 시그널이지만, **지금 이 문서에서 바로 “반드시 1092로 바꿔라”라고 쓰기보다는** 다음처럼 쓰는 편이 정확하다.

> “full-suite evidence를 current authoritative basis로 다시 갱신하고, 그 결과가 1092로 봉인되면 그때 expected count를 함께 올려라.”

즉 숫자 변경은 목표가 아니라 **재생성 결과의 후속 반영**이어야 한다.

## 5.4 `storage_path` / `display_path` 제안은 “신규 설계”보다 “기존 alias 모델의 외부보고서 적용 확장”으로 좁히는 편이 맞다

업로드 리뷰 2는 external report path canonicalization을 위해 `storage_path`/`display_path` 분리를 새로 제안한다. 방향은 좋다.  
하지만 실제 저장소에는 이미 `ops/README.md`와 raw registry 계층에서:

- machine canonical key
- `storage_path`
- `display_path`
- escaped path alias

개념이 존재한다.

따라서 이 개선안의 정확한 표현은 다음이어야 한다.

- “storage/display split을 새로 발명하자”가 아니라
- **“이미 raw registry 쪽에 있는 alias/canonical locator 모델을 external report inventory와 generated-artifact-index에도 일관되게 재사용하자”**

이렇게 적어야 중복 설계가 아니라 구조 통일이 된다.

---

## 6. 문서별 세부 평가

## 6.1 업로드 리뷰 1 평가  
파일: `llmwiki_three_reviews_integrated_report_20260510.md`

### 장점
- 세 리뷰를 한 번에 읽기 좋게 압축했다.
- 기준 보고서와 현재 ZIP을 구분해야 한다는 판단이 맞다.
- release evidence split / distribution binding / auto-improve 낙관 / release vocabulary 문제를 핵심 blocker로 정리한 부분이 좋다.
- 실행 순서를 제안한 점은 실무적으로 유용하다.

### 한계
- 23cde vs d0c6a3 해석에서 23cde 쪽에 너무 무게를 실었다.
- drift 원인을 `.venv/tmp/pyc` 중심으로 설명한 부분은 실제 구현과 맞지 않는다.
- 1092를 사실상 current baseline처럼 다루는 부분은 근거 봉인 정도가 부족하다.
- “source tree coherence 2군집 + d0c6a3는 부차적”이라는 정리는 실제 ZIP 추출본 재실행 결과를 과소평가한다.

### 판정
**좋은 통합 개요 문서지만, 실제 ZIP을 authoritative truth로 삼는 최종 개선 보고서로 쓰기에는 원인 분석이 덜 정밀하다.**

## 6.2 업로드 리뷰 2 평가  
파일: `llmwiki_three_reviews_integrated_improvement_report_20260510.md`

### 장점
- 실행 환경 차이를 표로 정리해 문서 밀도가 높다.
- `release-closeout-batch-manifest`의 다층 상태 해석이 좋다.
- archive candidate 5건을 구체적으로 집어낸 부분이 실용적이다.
- P0/P1/P2 우선순위와 명령 시퀀스가 더 운영 친화적이다.

### 한계
- 업로드 리뷰 1의 가장 큰 약점인 23cde/pristine 가정을 그대로 이어받았다.
- d0c6a3를 “workcopy dev install 후 기대되는 다음 상태” 정도로 낮게 잡았지만, 실제 ZIP 추출본 재실행에서도 이미 나온다.
- `storage_path/display_path` 분리 제안이 “기존 alias 모델의 확장”이 아니라 “신규 스키마 발명”처럼 읽힐 여지가 있다.
- full-suite node count 1092 반영을 너무 앞단에 둔다.

### 판정
**실무적으로 더 유용한 문서이지만, 가장 중요한 첫 단추인 authoritative fingerprint basis 재정의가 빠져 있다.**  
즉 “좋은 개선 계획서”이긴 하나, 맨 앞의 문제 정의가 약간 비껴가 있다.

---

## 7. 이번 실제 대조에서 새롭게 드러난 핵심 보정 결론

## 7.1 진짜 1순위는 “canonical artifact 일부 재생성”이 아니라 “authoritative fingerprint basis 재정의”다

현재 선택지는 둘 중 하나다.

### 선택지 A. ZIP extract surface를 authoritative truth로 인정
- 실제 사용자가 받는 배포물은 escaped path를 포함한 추출본이므로,
- `d0c6a3...` 계열을 기준으로 canonical artifacts를 재생성한다.

### 선택지 B. path alias canonicalization을 먼저 도입
- extracted ZIP이 escaped path를 써도,
- fingerprint 계산 또는 upstream-to-zip parity layer가 canonical alias를 통해 동일 fingerprint를 내도록 만든다.
- 그 후 canonical artifacts를 다시 생성한다.

둘 중 어느 쪽을 택하든, **지금처럼 23cde cohort를 사실상 current로 간주한 채 후속 artifact만 조금 고치는 접근은 불충분하다.**

## 7.2 release smoke / generated artifact index / artifact freshness는 실제 ZIP 기준으로는 이미 stale로 보는 편이 맞다

checked-in 파일은 23cde를 가리키지만, 실제 재생성 결과는 d0c6a3를 가리킨다.  
따라서 이번 ZIP을 기준으로 한 판정에서는 다음처럼 적는 편이 정확하다.

- checked-in cohort 내부 상호일관성: 일부 존재
- 실제 ZIP live parity: **깨짐**
- 결과: artifact-finalization 2 fail 재현

즉 “문서상 current”와 “실제 배포물 current”를 분리해야 한다.

## 7.3 auto-improve gate는 여전히 P0가 맞지만, 선행 조건 순서가 바뀌어야 한다

두 업로드 리뷰는 auto-improve gate를 P0로 둔 점은 맞다.  
하지만 실제 순서는 다음이 더 낫다.

1. authoritative fingerprint basis 결정
2. canonical artifacts current basis로 재생성
3. closeout/batch/reference manifest binding 완료
4. 그 다음에 auto-improve promotion 조건을 그 결과에 맞게 연결

즉 auto-improve gate 보수화는 중요하지만, **그 전에 “무엇을 current truth로 볼 것인가”가 먼저 닫혀야 한다.**

---

## 8. 수정된 우선순위 개선안

## P0 — 바로 손대야 할 항목

| 번호 | 항목 | 수정된 권고 |
| ---: | --- | --- |
| P0-1 | authoritative fingerprint basis 결정 | `23cde` 유지 가정부터 버리고, 실제 ZIP 추출본 기준 `d0c6a3`가 왜 나오는지 규명한 뒤 기준 cohort를 확정한다. |
| P0-2 | fingerprint/path parity 정책 확정 | escaped ZIP path와 upstream path를 같은 identity로 볼지, ZIP surface를 그대로 canonical로 볼지 결정한다. |
| P0-3 | canonical artifact 재생성 | 위 기준이 정해진 뒤 `release-smoke-report`, `generated-artifact-index`, 필요 시 `script-output-surfaces`, 관련 currentness artifacts를 한 번에 재생성한다. |
| P0-4 | artifact finalization 재통과 | `make test-artifact-finalization` 6개 전부 통과시킨다. |
| P0-5 | distribution ZIP binding | 새 distribution ZIP을 `release-closeout-batch-manifest.json`과 `external-reports/report-reference-manifest.json`에 실제 값으로 바인딩한다. |
| P0-6 | auto-improve promotion gate 보수화 | machine blocked / batch manifest fail / finalization fail 중 하나라도 있으면 `can_promote_result=false`로 내린다. |

## P1 — 그 다음에 닫아야 할 항목

| 번호 | 항목 | 수정된 권고 |
| ---: | --- | --- |
| P1-1 | full-suite evidence currentization | current authoritative basis로 full-suite evidence를 새로 봉인한 뒤, 그 결과가 실제로 1092면 그때 expected count를 올린다. |
| P1-2 | external report alias model 정렬 | raw registry가 이미 쓰는 storage/display/escaped alias 모델을 external report inventory에도 일관 적용한다. |
| P1-3 | release authority vocabulary 정리 | `status`, `release_authority_status`, `sealed_release_status`, `machine_release_status`의 의미를 소비자가 오해하지 않게 정리한다. |
| P1-4 | archive candidate 정리 | external reports 4건 + run 1건 archive hygiene를 수행한다. |
| P1-5 | historical report labeling | 2026-05-09 기준 보고서와 23cde cohort 문서들을 “historical basis”로 명시한다. |

## P2 — 유지보수/문서화

| 번호 | 항목 | 수정된 권고 |
| ---: | --- | --- |
| P2-1 | ZIP-based verification 문서화 | “배포 ZIP 추출본에서 fingerprint가 어떻게 재현되어야 하는가”를 README/ops 문서에 명문화한다. |
| P2-2 | supported entrypoint 기준 full collect 문서화 | `1086` / `1092`류 숫자 충돌이 다시 생기지 않게 authoritative collection 절차를 문서화한다. |
| P2-3 | command cookbook 정리 | closeout/finality/reference manifest binding을 한 번에 재현하는 운영 절차를 정리한다. |

---

## 9. 실제 실행 기준 권장 순서

```bash
# 0. 환경
python3 -m pip install ruff mypy

# 1. 먼저 현재 ZIP 추출본의 authoritative fingerprint를 확인
python3 - <<'PY'
from pathlib import Path
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint
print(release_source_tree_fingerprint(Path(".")))
PY

# 2. 실제 ZIP surface 기준으로 release smoke / freshness / generated index를 재생성
make artifact-freshness-check
make release-distribution-zip \
  RELEASE_DISTRIBUTION_ZIP_OUT=tmp/release.zip \
  RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT=tmp/release-smoke.json

# generated-artifact-index는 authoritative path policy를 확정한 뒤 재생성

# 3. finalization 통과 여부 확인
make test-artifact-finalization

# 4. 기준 cohort가 확정되면 distribution ZIP binding
make external-report-reference-manifest-strict \
  EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH=tmp/release.zip

# 5. 그 다음에야 full-suite evidence currentization과 expected node count 조정
make test-execution-summary-full-refresh

# 6. 마지막에 auto-improve gate를 current machine truth에 연결
```

핵심은 순서다.  
**node count를 먼저 바꾸거나 archive candidate부터 치우는 것이 아니라, fingerprint truth basis부터 고정해야 한다.**

---

## 10. 최종 판정 매트릭스

| 항목 | 업로드 리뷰들의 주장 | 실제 파일 대조 판정 |
| --- | --- | --- |
| machine clean release-ready 아님 | 맞음 | **유지** |
| distribution ZIP binding 누락 | 맞음 | **유지** |
| auto-improve 과낙관 | 맞음 | **유지** |
| release ZIP 생성 로직 정상 | 맞음 | **유지** |
| archive candidate 5건 | 맞음 | **유지** |
| 23cde cohort가 pristine current truth에 가깝다 | 과장 | **수정 필요** |
| d0c6a3는 workcopy 오염 쪽 현상이다 | 부정확 | **수정 필요** |
| `.venv/tmp/pyc` exclusion을 더 강화하면 해결된다 | 원인 진단 약함 | **수정 필요** |
| 1086 -> 1092 즉시 갱신 | 성급함 | **조건부로 보류** |
| storage/display split을 새로 설계 | 방향은 좋음 | **기존 alias 모델 재사용으로 좁혀 수정** |

---

## 11. 최종 권고

두 업로드 리뷰는 **버릴 문서가 아니라, 방향은 좋은데 첫 단추를 다시 끼워야 하는 문서**다.  
실제 ZIP을 다시 대조한 결과, 가장 먼저 바뀌어야 할 문장은 다음이다.

### 업로드 리뷰식 표현
- “23cde cohort를 중심으로 stale artifact를 정리하자”
- “d0c6a3는 workcopy 오염 가능성이 높다”

### 실제 ZIP 기준으로 고친 표현
- **“현재 사용자가 올린 ZIP을 실제로 풀어 재실행하면 d0c6a3 계열이 재현되므로, 먼저 authoritative fingerprint basis를 다시 정해야 한다.”**
- **“23cde cohort는 checked-in historical/current-ish evidence이지, 이번 ZIP live truth로 단정할 수 없다.”**

이번 요청 기준 최종 판정은 다음 한 줄이다.

> **두 업로드 리뷰는 절반 이상 맞지만, 현재 ZIP의 실제 진실 계층을 기준으로 다시 쓰면 최우선 과제는 archive hygiene나 node count 조정이 아니라, extracted ZIP surface를 포함한 authoritative fingerprint 기준 재정의와 그에 따른 canonical artifact 일괄 재생성이다.**

---

## 12. 부록 — 이번 실제 대조에서 직접 확인한 재현 포인트

### A. 실제로 통과한 것
- `make static`
- `make artifact-freshness-check`
- `make release-distribution-zip` (archive root `LLMwiki`, manifest comparison pass)

### B. 실제로 실패 재현한 것
- `make test-artifact-finalization` → **2 failed, 4 passed**

### C. 실제로 새로 계산된 live fingerprint
- `d0c6a3b8f12cd1c03939f190aa4eeeddb52e67c2cf6ad6bd8472d0ebe627cf21`

### D. 현재 checked-in current-ish cohort fingerprint
- `23cde66451855377f121b47c29484b2d477b2019a2b77921791cfabf6f91b789`

### E. older cohort fingerprint
- `744169710c461b60445b0460c104b1fd979854962676b19e7aa45d85a0602d49`
