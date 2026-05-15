# LLMwiki 메타 통합 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일시 | 2026-05-08 KST |
| 작성 언어 | 한국어 |
| 출력 파일명 | `llmwiki_meta_integrated_improvement_report_20260508.md` |
| 신규 검토 대상 리뷰 1 | `llmwiki_current_integrated_crosscheck_report_20260507.md` |
| 신규 검토 대상 리뷰 2 | `llmwiki_integrated_improvement_report_20260507.md` |
| 기존 리뷰 1 | `llmwiki_current_archive_comparison_improvement_report_20260507.md` |
| 기존 기준 보고서 | `external-reports/llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506.md` |
| 실제 검토 대상 저장소 | `LLMwiki(24).zip` 원본 압축본 |
| 실제 검증 방식 | ZIP inventory 재계산, 핵심 JSON 아티팩트 재검토, 개발 의존성 설치 후 선택적 명령/테스트 재실행 |

---

## 0. 이 문서의 목적

이 문서는 새로 제공된 두 리뷰를 각각 처음부터 끝까지 면밀히 읽은 뒤, 직전에 작성된 기존 개선 보고서와 원본 저장소 ZIP의 실제 상태를 다시 대조하여 **현재 시점에서 가장 신뢰할 수 있는 단일 개선 로드맵**을 만드는 것을 목적으로 한다.

이번 메타 검토의 핵심은 단순 요약이 아니다.  
다음 네 가지를 분리해서 판단했다.

1. **새 두 리뷰가 공통으로 맞게 본 것**
2. **새 두 리뷰 중 한쪽이 더 강하게 정리했지만 실제 파일로도 지지되는 것**
3. **기존 리뷰와 새 리뷰 사이에서 표현을 수정해야 하는 것**
4. **실제 파일 재검증을 거치면 문장을 더 정밀하게 고쳐야 하는 것**

---

## 1. 최종 결론

이번 검토 결과, 새로 제공된 두 리뷰는 모두 방향성 면에서 강하고 유의미하다. 다만 역할이 다르다.

- `llmwiki_current_integrated_crosscheck_report_20260507.md`는 **현 상태 진단 보고서**로서 강하다.
  - 기준 보고서의 옛 주장 중 무엇이 여전히 유효하고 무엇이 이미 해소됐는지를 구조적으로 잘 정리했다.
  - 현재 ZIP을 기준으로 실제 drift와 contract mismatch를 분리한 점이 좋다.

- `llmwiki_integrated_improvement_report_20260507.md`는 **실행 우선순위 보고서**로서 더 강하다.
  - P0-A, P0-B처럼 지금 손대야 할 문제를 재분류했다.
  - 세 리뷰 간 충돌을 노출한 뒤 우선순위를 재배열한 점이 실무적으로 가장 유용하다.

- 기존에 작성된 `llmwiki_current_archive_comparison_improvement_report_20260507.md`는 이번 두 신규 리뷰와 실질적으로 같은 방향을 공유하며, **기초 검증 보고서**로서는 여전히 가치가 있다.
  - 다만 현재는 두 신규 리뷰가 더 넓은 범위를 다뤘고, 특히 세 리뷰 통합 관점의 우선순위 재배열은 신규 리뷰 쪽이 더 발전된 상태다.

- 기준 보고서 `external-reports/llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506.md`는 지금도 중요한 역사적 전환점 문서지만, **현재 구현/아티팩트 상태를 그대로 설명하는 운영 기준 문서로 쓰기에는 오래된 문장들이 섞여 있다.**

### 한 문장 최종 판정

> 현재 canonical 실행 계획으로 채택해야 할 문서는 `llmwiki_integrated_improvement_report_20260507.md`의 우선순위 체계이고, `llmwiki_current_integrated_crosscheck_report_20260507.md`는 그 우선순위를 뒷받침하는 상태 증빙 문서로 쓰는 것이 가장 적절하다. 기존 archive comparison 보고서는 이 둘을 보강하는 1차 대조 근거로 유지하되, 기준 보고서의 오래된 P0 문장을 되살리는 용도로는 사용하면 안 된다.

---

## 2. 이번 메타 검토에서 실제로 확인한 대상

### 2.1 문서 기준 검토 대상

1. `llmwiki_current_integrated_crosscheck_report_20260507.md`
2. `llmwiki_integrated_improvement_report_20260507.md`
3. `llmwiki_current_archive_comparison_improvement_report_20260507.md`
4. `external-reports/llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506.md`

### 2.2 실제 파일 기준 재검증 대상

원본 ZIP을 직접 풀어서 아래 핵심 파일들을 다시 확인했다.

- `external-reports/report-reference-manifest.json`
- `ops/reports/release-closeout-batch-manifest.json`
- `ops/reports/release-evidence-dashboard.json`
- `ops/reports/learning-delta-scoreboard.json`
- `ops/reports/auto-improve-readiness.json`
- `ops/reports/operator-release-summary.json`
- `ops/reports/test-execution-summary-full.json`
- `ops/reports/learning-claim-unlock-review.json`
- `tests/test_generated_report_contracts.py`
- `ops/policies/distribution-profile-matrix.json`
- `ops/schemas/distribution-profile-matrix.schema.json`
- `Makefile`
- ZIP inventory 전체

### 2.3 실제로 재실행한 검증

개발 의존성을 설치한 뒤 다음을 다시 확인했다.

- `make bootstrap-preflight PYTHON=.venv/bin/python`
- `.venv/bin/python -m pytest -o addopts= --collect-only -q`
- `.venv/bin/python -m pytest -o addopts= -q tests/test_generated_report_contracts.py -k checked_in_auto_improve_readiness_surfaces_remaining_learning_gaps`
- `ops.scripts.release_closeout_batch_manifest --check --zip-metadata /mnt/data/LLMwiki(24).zip`
- `make release-distribution-zip PYTHON=.venv/bin/python`의 live rerun 시도

---

## 3. 새 두 리뷰의 공통 합의와 실제 파일 재검증 결과

아래 항목들은 신규 두 리뷰가 사실상 공통으로 지적했고, 실제 파일 재검증으로도 지지되었다.

### 3.1 기준 보고서의 일부 핵심 P0는 이미 해소되었다

실제 파일 확인 결과, 아래 문제들은 **“부재”가 아니라 “이미 구현된 상태”**로 봐야 한다.

| 항목 | 현재 실제 상태 | 메타 판정 |
| --- | --- | --- |
| archive profile / package profile 체계 | `ops/policies/distribution-profile-matrix.json`, schema, 테스트 존재 | “부재” 표현 폐기 |
| release closeout batch의 distribution sealing | `distribution_package.status=materialized`, `sealed_release_status=sealed_clean_pass` | “구조 부재” 표현 폐기 |
| full-suite nodeid digest 부재 | `test-execution-summary-full.json`에 `status=collected`, `nodeid_count=961` | 해결 |
| typed learning evidence 0 | `learning-delta-scoreboard.json` summary 기준 coverage 전부 full | 해결 |

즉 새 두 리뷰가 공통으로 말한 “기준 보고서의 여러 P0 문장은 현재 시점에서는 그대로 쓰면 안 된다”는 판단은 옳다.

### 3.2 여전히 열려 있는 오래된 문제도 있다

아래 항목은 기준 보고서의 문제의식이 여전히 유효하다.

| 항목 | 현재 실제 상태 | 메타 판정 |
| --- | --- | --- |
| `report-reference-manifest.json`의 current ZIP provenance 미결박 | `current_distribution_zip_known=false` | 유지 |
| active external report set drift | `active_reference_set_status=drift`, `report_count=4` | 유지 |
| full snapshot과 source package 구분 필요성 | 현재 ZIP file count 1,871 vs source manifest 1,430, ZIP-only 441 | 유지 |

즉 기준 보고서는 완전히 obsolete가 아니라, **문제의 방향은 맞지만 현재 수치와 우선순위가 달라진 상태**다.

### 3.3 현재 진짜 시급한 문제는 새 리뷰들이 끌어올린 항목들이다

실제 파일 기준으로 가장 강하게 확인된 현재 문제는 다음 세 가지다.

1. `release-closeout-batch-manifest.json`의 artifact digest drift
2. `auto-improve-readiness.json` 상태값과 generated report contract test의 불일치
3. snapshot hygiene 문제 (`tmp/*.candidate.json`, `tools/__pycache__/*.pyc`)

이 세 항목은 신규 두 리뷰가 옳게 승격시킨 현재형 이슈다.

---

## 4. 새 두 리뷰의 차이와 어떤 문서를 canonical로 삼아야 하는가

### 4.1 `llmwiki_current_integrated_crosscheck_report_20260507.md`의 강점

이 문서는 다음 역할에서 가장 좋다.

- 기준 보고서의 개별 주장별로 현재 상태를 대응시키는 **항목별 대조표**
- “무엇이 이미 닫혔고 무엇이 새로 열렸는지”를 설명하는 **상태 재판정 문서**
- 현재 ZIP의 inventory / prefix 분포 / manifest 대비 drift 규모를 설명하는 **증빙형 문서**

특히 다음 판단은 지금도 유효하게 유지할 수 있다.

- 현재 업로드 ZIP은 sealed source package가 아니라 full snapshot 성격이다.
- 기준 보고서가 지적한 방향은 맞지만 수치와 우선순위는 현재 기준으로 보정해야 한다.
- 새 P0는 canonical artifact 재동기화 쪽으로 이동했다.

### 4.2 `llmwiki_integrated_improvement_report_20260507.md`의 강점

이 문서는 다음 역할에서 더 우수하다.

- 세 리뷰의 공통점과 충돌을 모두 보존한 **메타 통합 문서**
- P0-A / P0-B / P1 등으로 현재형 우선순위를 재설정한 **실행 계획 문서**
- 어떤 파일/스크립트/테스트를 수정해야 하는지까지 내려간 **실무 로드맵 문서**

실무 관점에서 이 문서가 더 강한 이유는, 단순히 “상태를 서술”하는 수준이 아니라 **바로 작업 티켓으로 쪼갤 수 있는 구조**를 갖고 있기 때문이다.

### 4.3 기존 `llmwiki_current_archive_comparison_improvement_report_20260507.md`의 위치

이 문서는 여전히 유효한 1차 교차 검증 보고서다. 다만 현재는 다음 식으로 위치를 조정하는 것이 적절하다.

- **보관 가치:** 높음
- **현재 canonical 실행 문서로서의 우선순위:** 신규 두 리뷰보다 낮음
- **가장 적합한 쓰임:** 새 두 리뷰의 결론을 뒷받침하는 초기 대조 근거

### 4.4 권장 canonical 문서 체계

권장 체계는 아래와 같다.

1. **실행 기준 문서**
   - `llmwiki_integrated_improvement_report_20260507.md`

2. **상태 증빙 문서**
   - `llmwiki_current_integrated_crosscheck_report_20260507.md`

3. **1차 대조 보조 문서**
   - `llmwiki_current_archive_comparison_improvement_report_20260507.md`

4. **역사적 기준 문서**
   - `external-reports/llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506.md`

---

## 5. 실제 파일 재검증 결과

이 절은 이번 메타 검토에서 직접 다시 확인한 실제 결과다.  
중요한 점은, 아래 항목들은 신규 두 리뷰의 주장을 그대로 복제한 것이 아니라 **저장소 원본에서 재확인한 내용**이라는 점이다.

### 5.1 ZIP inventory 재검증

원본 `LLMwiki(24).zip` 기준 실제 값은 아래와 같다.

| 항목 | 실제 값 |
| --- | --- |
| SHA-256 | `997c9522a7d75d5c71b322398ad0824d3dfd5897297fd0f88f84545e3e0acc42` |
| entry 수 | 1,977 |
| file entry 수 | 1,871 |
| directory entry 수 | 106 |
| 비압축 총 바이트 | 249,252,209 |
| 고유 timestamp 수 (전체/파일) | 848 / 832 |
| timestamp max | 2026-05-07 14:16:38 |

이 수치는 신규 두 리뷰의 기초 전제가 맞다는 것을 지지한다.

### 5.2 prefix 분포와 snapshot hygiene

원본 ZIP을 다시 확인한 결과, 문제로 지적된 경로들은 실제로 존재한다.

#### 실제 포함된 candidate JSON

```text
tmp/auto-improve-readiness.candidate.json
tmp/learning-claim-unlock-review.candidate.json
tmp/learning-delta-scoreboard.candidate.json
tmp/release-evidence-dashboard.candidate.json
tmp/script-output-surfaces.candidate.json
```

#### 실제 포함된 pycache 산출물

```text
tools/__pycache__/regenerate_report_schema_samples.cpython-314.pyc
tools/__pycache__/ruff_strict_preview.cpython-314.pyc
```

따라서 신규 두 리뷰가 공통으로 주장한 **review snapshot hygiene 미완성** 진단은 실제 파일 기준으로도 맞다.

### 5.3 `report-reference-manifest.json` 재검증

실제 summary는 아래 상태다.

- `report_count=4`
- `current_distribution_zip_known=false`
- `zip_provenance_status=current_distribution_missing`
- `active_reference_set_status=drift`

즉, 새 두 리뷰와 기존 리뷰가 공통으로 지적한 “current ZIP provenance가 닫히지 않았다”는 문제는 현재도 실제로 남아 있다.

### 5.4 `release-closeout-batch-manifest.json` 재검증

실제 batch manifest 핵심 값은 아래와 같다.

- `status=pass`
- `semantic_release_status=clean_pass`
- `sealed_release_status=sealed_clean_pass`
- `distribution_package.status=materialized`
- `distribution_package.archive_profile=source_content_package`
- `distribution_package.file_count=1428`
- `distribution_package.path_set_matches_release_manifest=True`
- `distribution_package.content_digest_matches_release_manifest=True`

즉, 기준 보고서의 옛 주장인 “distribution sealing 구조 부재”는 현재는 사실로 유지할 수 없다.

다만 이것이 곧 “아무 문제 없음”을 뜻하지는 않는다.

### 5.5 batch manifest artifact digest drift 재검증

실제 파일 digest를 다시 계산한 결과, batch manifest에 봉인된 12개 artifact 중 2개가 현재 파일과 일치하지 않았다.

| path | batch digest | actual digest | 판정 |
| --- | --- | --- | --- |
| `ops/reports/learning-delta-scoreboard.json` | `451af8c5e61019c12d2e8f39ab03334ef4e782fe8818f1309ff980326d74aa07` | `a30a4dfb2711458ef9f54189952013f0509668c93978c9a24afcb8b49bddc5b8` | mismatch |
| `ops/reports/release-evidence-dashboard.json` | `56685c85a23b89d4cedd7e77fd904368a52e0f06d9c8f6f28edb31b8ae076ed9` | `48660e155f1b11d5ae23b9707e72492d2a48873b1e0c9060a06477b6e3f6aa16` | mismatch |

또한 실제 파일의 `generated_at`은 다음과 같았다.

| path | actual generated_at | actual source_tree_fingerprint |
| --- | --- | --- |
| `ops/reports/learning-delta-scoreboard.json` | `2026-05-07T05:16:33Z` | `bc2af8b69cd3a43e66e931027c860162b7ceff9aec25f5d8348b55d3545037a1` |
| `ops/reports/release-evidence-dashboard.json` | `2026-05-07T05:16:37Z` | `bc2af8b69cd3a43e66e931027c860162b7ceff9aec25f5d8348b55d3545037a1` |

이 항목은 신규 두 리뷰, 기존 리뷰 모두가 강조한 새 핵심 문제이며, 실제 재검증으로도 가장 확실하게 확인됐다.

### 5.6 `auto-improve-readiness.json`와 contract test 불일치 재검증

실제 `auto-improve-readiness.json`의 핵심 값은 아래와 같았다.

- `can_execute_trial=false`
- `can_promote_result=false`
- `learning_readiness.status=not_runnable`
- reason: `no runnable proposal is available`

반면 테스트 코드는 아래 기대값을 유지하고 있다.

```python
assert payload.get("learning_readiness", {}).get("status") == "learning_uncertain"
```

실제 targeted test 재실행 결과도 실패가 재현되었다.

- 실행 대상: `tests/test_generated_report_contracts.py -k checked_in_auto_improve_readiness_surfaces_remaining_learning_gaps`
- 실제 결과: **FAIL**
- mismatch:
  - expected: `learning_uncertain`
  - actual: `not_runnable`

이 항목은 신규 두 리뷰 중 특히 `llmwiki_integrated_improvement_report_20260507.md`가 더 잘 정리한 현재형 defect이며, 이번 메타 검토에서 직접 재현되었다.

### 5.7 full-suite forensic evidence 재검증

`ops/reports/test-execution-summary-full.json`은 아래 상태였다.

- `counts.passed=961`
- `pytest_collect_nodeid_digest.status=collected`
- `pytest_collect_nodeid_digest.nodeid_count=961`
- `pytest_collect_nodeid_digest.sha256=d136d568265a33afb02e4e19e1a0242affb98756aed92ee40bbf7d1c4d813a4d`

즉 “nodeid digest가 없다”는 옛 문장은 폐기해야 한다.

다만 live collect-only 재실행 결과는 아래와 같았다.

- `.venv/bin/python -m pytest -o addopts= --collect-only -q`
- summary: **969 tests collected**

따라서 현재 문제는 “증거 부재”가 아니라 **증거 refresh lag** 쪽으로 이동했다는 신규 두 리뷰의 판단이 타당하다.

### 5.8 `make bootstrap-preflight` 재검증

실제 재실행 결과는 **pass**였다.

- python: 3.13.5 (minimum 3.12.0) [pass]
- jsonschema [ok]
- PyYAML [ok]
- mypy [ok]
- pytest [ok]
- ruff [ok]

즉 개발 환경 구성 자체는 현재도 큰 문제가 없다.

### 5.9 `release_closeout_batch_manifest --check --zip-metadata` 재검증

실제 재실행 시 아래 신호가 다시 확인되었다.

- `content differs from ops/reports/release-closeout-batch-manifest.json`
- `source files changed after checked-in manifest generated_at`
- `changed_after_generated_at_count=57`
- `missing_zip_member_count=332`
- artifact digest mismatches 2건 재확인

이 결과는 신규 두 리뷰의 핵심 주장과 일치한다.

### 5.10 live `make release-distribution-zip` 재검증에서 확인된 추가 nuance

이번 메타 검토에서는 `make release-distribution-zip PYTHON=.venv/bin/python`도 재시도했다.  
다만 이번 환경에서는 이전 리뷰 일부가 말한 “장시간 hang/timeout”으로 가지 않고, 더 빠르게 **임시 파일 쓰기 단계에서 실패**했다.

실패 핵심:

- `ops.scripts.filesystem_runtime.FilesystemTransactionError`
- `Permission denied: '/mnt/data/ll_unzip/tmp/.release-distribution-zip-smoke.json....tmp'`

이 항목이 의미하는 바는 다음과 같다.

1. “release ZIP 생성 문제가 있다”는 큰 방향은 여전히 맞다.
2. 그러나 그 실패 양상은 환경에 따라 **timeout/hang**일 수도 있고, **workspace writability / tmp atomic write failure**일 수도 있다.
3. 따라서 이 문제는 단순히 “hang이 난다”로 좁히기보다, **live rerun path가 bounded하고 환경 독립적으로 실패/성공하도록 만들지 못했다**는 더 넓은 문제로 정리하는 것이 정확하다.

이 점은 신규 두 리뷰가 다뤘던 runner/ZIP generation 문제를 한 단계 더 정밀하게 보정해 준다.

또 하나 중요한 점은, 원본 ZIP inventory 기준으로는 `build/release/LLMwiki-source.zip`이 포함되어 있지 않았다.  
즉 batch manifest가 source ZIP 경로를 가리키더라도, **원본 snapshot 자체에는 그 실물이 없었다**는 기존 판단은 유지된다. live rerun이 그 파일을 생성할 수 있다는 사실은 이 판단을 뒤집지 않는다.

---

## 6. 이번 메타 검토가 채택하는 최종 우선순위

신규 두 리뷰와 기존 리뷰, 실제 파일 재검증을 모두 합친 최종 우선순위는 아래와 같다.

### 6.1 P0 — 즉시 조치

#### P0-1. Batch manifest digest drift 해소 및 closeout invalidation 강화

가장 우선순위가 높다.

문제:
- `release-closeout-batch-manifest.json`은 `sealed_clean_pass`를 말하지만,
- 실제 canonical artifact 두 개가 이후 다시 생성되어 digest가 어긋난다.

필요 조치:
- `release-closeout-batch-manifest` 검증 로직에 현재 artifact digest 재비교 추가
- `release-evidence-closeout-self-check`를 digest-level 검증까지 확장
- closeout 이후 canonical artifact overwrite 발생 시 manifest invalidation 또는 closeout 재실행 강제

권장 수정 위치:
- `ops/scripts/release_closeout_batch_manifest.py`
- `ops/scripts/release_evidence_closeout_self_check.py`
- `tests/test_release_closeout_batch_manifest.py`
- `tests/test_release_evidence_closeout_self_check.py`

#### P0-2. `not_runnable` vs `learning_uncertain` contract 정렬

문제:
- artifact semantics는 이미 `not_runnable`로 이동했는데
- test contract는 여전히 `learning_uncertain`을 기대한다.

권장 방향:
- `not_runnable`을 유지
- generated report contract / narrative / summary를 이에 맞게 수정

권장 수정 위치:
- `tests/test_generated_report_contracts.py`
- `ops/reports` 생성 스크립트 서술 계층
- 관련 README 또는 상태 어휘 설명 문서

#### P0-3. External report current ZIP provenance 결박

문제:
- `report-reference-manifest.json`에 current distribution ZIP이 비어 있음
- active report set drift도 함께 남아 있음

필요 조치:
- closeout or review lane에서 current ZIP path / name / SHA / entry_count를 강제 입력
- `report-reference-manifest.json` 재생성 및 promote
- active report set lifecycle도 함께 정리

권장 수정 위치:
- `ops/scripts/external_report_reference_manifest.py`
- `Makefile`
- `tests/test_external_report_reference_manifest.py`

---

### 6.2 P1 — P0 직후 처리

#### P1-1. Snapshot hygiene 정리

대상:
- `tmp/*.candidate.json`
- `tools/__pycache__/*.pyc`
- 필요 시 `.obsidian/`, `.vscode/` 정책 명문화

핵심 목표:
- review snapshot과 local workspace를 정책상 분리
- 업로드/검토용 snapshot은 clean profile을 만족하도록 export

#### P1-2. Release ZIP live rerun path를 bounded failure로 개선

문제:
- 일부 리뷰에서는 timeout/hang
- 이번 메타 검토에서는 tmp atomic write 단계에서 permission failure

정확한 목표:
- 어떤 환경이든 live rerun path가 무한 대기하지 않고,
- diagnostic과 함께 성공 또는 bounded failure를 반환하게 할 것

핵심 조치:
- temp file write / rename atomicity 정리
- tmp 디렉터리 writability preflight
- progress surface 추가
- timeout/hang/permission failure를 구분하는 machine-readable report 추가

#### P1-3. operator-facing truth ladder 정렬

문제:
- batch manifest는 `sealed_clean_pass`
- operator summary는 `blocked_tmp_json`, `attention`

조치:
- semantic release / sealed release / workspace hygiene / learning unlock / live rerun status를 분리 표기
- operator가 “무엇이 실제 배포 차단인지”를 한눈에 보게 만들 것

#### P1-4. Learning claim unlock gate 정리

현재는 typed evidence 부족이 아니라,
- operator review 미승인
- runnable proposal queue 부재
가 핵심 blocker다.

따라서 재생성보다 절차/상태 정합성이 중요하다.

#### P1-5. source package portability 및 handoff 분리

현재는 batch manifest가 source ZIP을 가리키더라도 원본 snapshot에는 그 실물이 없다.  
따라서 full snapshot / source ZIP / evidence bundle / attestation을 별도 artifact로 명시하는 방식이 필요하다.

---

### 6.3 P2 — 구조 개선

#### P2-1. full-suite evidence refresh lane 정식화

현재 checked-in full summary는 961 nodeids인데, live collect-only는 969 collected다.  
즉 full-suite evidence refresh를 더 자주 또는 더 자동으로 돌릴 필요가 있다.

#### P2-2. snapshot self-description manifest 도입

원본 ZIP 자체에 다음을 명시하는 machine-readable manifest를 두는 것이 좋다.

- archive profile
- source/public/review/workspace 분류
- contains runs / contains external reports / contains tmp candidate 여부
- current ZIP identity
- basis/source manifest linkage

#### P2-3. active external report lifecycle 정책 고정

무엇을 active root에 남기고, 무엇을 archive로 밀어 넣는지 정책을 명확히 해야 한다.  
지금 상태의 `active_reference_set_status=drift`는 운영 습관이 아직 policy보다 앞서 있다는 신호다.

---

## 7. 각 리뷰에 대한 최종 평정

### 7.1 `llmwiki_current_integrated_crosscheck_report_20260507.md`

**평정:** 우수한 현재 상태 대조 보고서.  
**가장 적합한 쓰임:** 기준 보고서의 문장을 현재 저장소 기준으로 다시 번역하는 참조 문서.

강점:
- 기준 보고서의 개별 P0 항목을 현재 상태와 잘 매핑함
- ZIP inventory / drift 규모 / actual artifact 상태를 구체적으로 설명함

보완점:
- 실행 우선순위 체계 자체는 후속 통합 보고서보다 덜 정제되어 있음

### 7.2 `llmwiki_integrated_improvement_report_20260507.md`

**평정:** 현재 canonical 실행 로드맵으로 가장 적합한 문서.  
**가장 적합한 쓰임:** 작업 분해, 우선순위 부여, 실무 티켓화의 기준 문서.

강점:
- 세 리뷰 간 충돌을 숨기지 않고 드러냄
- 현재형 P0를 명확히 재지정함
- 수정해야 할 파일/스크립트/테스트 위치를 잘 제시함

보완점:
- 일부 항목은 상태 진단 문서의 세부 수치 설명을 함께 봐야 완전한 맥락이 생김

### 7.3 `llmwiki_current_archive_comparison_improvement_report_20260507.md`

**평정:** 여전히 유효한 1차 대조 보고서.  
**가장 적합한 쓰임:** 새 두 리뷰의 결론을 뒷받침하는 보조 기준.

강점:
- 실제 ZIP 대조의 기초 틀을 잘 세움
- 기준 보고서의 오래된 주장과 현재 상태 차이를 초기에 잘 포착함

보완점:
- 세 리뷰 간 충돌 정리와 실행 우선순위 재배치 면에서는 신규 통합 보고서보다 덜 발전함

### 7.4 `external-reports/llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506.md`

**평정:** 역사적 전환점 문서.  
**가장 적합한 쓰임:** 왜 archive profile / source package / evidence sealing 같은 구조가 도입되었는지를 설명하는 배경 문서.

주의:
- 현재 운영 우선순위를 그대로 대변하는 문서로 쓰면 안 된다.

---

## 8. 실무 권고안

지금 바로 작업을 시작한다면, 다음 순서가 가장 효율적이다.

1. **batch manifest / self-check digest 재동기화**
2. **`not_runnable` contract mismatch 수정**
3. **external report current ZIP provenance 결박**
4. **snapshot hygiene 정리**
5. **release ZIP live rerun bounded failure 보장**
6. **operator summary truth ladder 정리**
7. **learning unlock review 절차 정리**
8. **source ZIP / full snapshot / evidence bundle handoff 분리**
9. **full-suite evidence refresh lane 및 snapshot self-description 도입**

이 순서는 신규 두 리뷰가 공통으로 본 현재형 이슈와, 실제 파일 재검증에서 즉시 확인된 결함의 강도를 같이 반영한 것이다.

---

## 9. 최종 판정

이번 메타 검토 기준에서의 단일 결론은 아래와 같다.

1. 새로 제공된 두 리뷰는 서로 충돌하는 문서가 아니라,  
   **하나는 상태 증빙**, **하나는 실행 로드맵** 역할을 하는 상호보완 문서다.

2. 기존 개선 보고서는 이번 두 신규 리뷰와 방향이 일치하며,  
   **보조 근거 문서로 계속 유효**하다.

3. 2026-05-06 기준 보고서는 여전히 중요한 배경 문서지만,  
   **현재 구현 상태를 직접 설명하는 canonical 운영 문서로는 사용하면 안 된다.**

4. 현재 최우선 과제는 새 기능 도입이 아니라,  
   **이미 도입된 계약을 현재 snapshot 기준으로 다시 맞추는 것**이다.

### 최종 핵심 문장

> 지금 이 저장소에서 가장 먼저 해야 할 일은 새로운 구조를 더 발명하는 것이 아니라, 이미 존재하는 release / learning / report 계약을 현재 압축본과 다시 동기화하고, review snapshot을 policy에 맞게 정리하며, live rerun 경로가 환경에 상관없이 bounded하게 성공 또는 실패하도록 만드는 것이다.

---

## 부록 A. 이번 메타 검토에서 직접 다시 확인한 핵심 사실

- 원본 ZIP SHA-256: `997c9522a7d75d5c71b322398ad0824d3dfd5897297fd0f88f84545e3e0acc42`
- ZIP file entry 수: 1,871
- `ops/manifest.json` file count: 1,430
- ZIP-only path count: 441
- `tmp/*.candidate.json`: 5개 실제 포함
- `tools/__pycache__/*.pyc`: 2개 실제 포함
- `report-reference-manifest.json`:
  - `current_distribution_zip_known=false`
  - `active_reference_set_status=drift`
- `release-closeout-batch-manifest.json`:
  - `distribution_package.status=materialized`
  - `sealed_release_status=sealed_clean_pass`
- batch artifact digest mismatch:
  - `learning-delta-scoreboard.json`
  - `release-evidence-dashboard.json`
- `auto-improve-readiness.json`:
  - `learning_readiness.status=not_runnable`
- `tests/test_generated_report_contracts.py`:
  - expected `learning_uncertain`
- targeted pytest:
  - 실제 1개 실패 재현
- checked-in full summary:
  - `passed=961`
  - `pytest_collect_nodeid_digest.status=collected`
- live collect-only:
  - `969 tests collected`
- bootstrap-preflight:
  - pass
- live `make release-distribution-zip` rerun:
  - 이번 환경에서는 timeout보다 tmp atomic write permission failure가 먼저 드러남

---

## 부록 B. 후속 수정이 집중될 파일

| 파일 | 권장 역할 |
| --- | --- |
| `ops/scripts/release_closeout_batch_manifest.py` | batch digest drift 검증 강화 |
| `ops/scripts/release_evidence_closeout_self_check.py` | self-check를 digest-level로 확장 |
| `ops/scripts/external_report_reference_manifest.py` | current ZIP provenance 강제 결박 |
| `tests/test_release_closeout_batch_manifest.py` | P0-1 회귀 테스트 추가 |
| `tests/test_release_evidence_closeout_self_check.py` | P0-1 회귀 테스트 추가 |
| `tests/test_external_report_reference_manifest.py` | P0-3 회귀 테스트 추가 |
| `tests/test_generated_report_contracts.py` | `not_runnable` 정렬 |
| `ops/policies/distribution-profile-matrix.json` | snapshot hygiene 적용 기준 |
| `Makefile` | current ZIP binding / export lane / preflight 강화 |
| `ops/reports/operator-release-summary.json` 관련 생성 스크립트 | truth ladder 정리 |
