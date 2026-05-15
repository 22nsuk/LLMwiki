# LLMwiki Dual New Review Crosscheck Improvement Report

| 항목 | 내용 |
| --- | --- |
| 작성일시 | 2026-05-08 KST |
| 작성 언어 | 한국어 |
| 출력 파일명 | `llmwiki_dual_new_review_crosscheck_report_20260508.md` |
| 신규 검토 대상 리뷰 1 | `llmwiki_integrated_improvement_report_20260508.md` |
| 신규 검토 대상 리뷰 2 | `llmwiki_tri_review_integrated_improvement_report_20260508.md` |
| 함께 대조한 기존 리뷰 | `llmwiki_uploaded_files_improvement_report_20260508.md`, `llmwiki_meta_integrated_improvement_report_20260508(1).md`, `llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506(2).md`, `llmwiki_two_review_actual_crosscheck_improvement_report(4).md`, `LMMwiki교차검증 개선 보고서_20260506(1).md`, `integrated_improvement_report_v3(14).md` |
| 실제 대조 대상 파일 | `LLMwiki-source(1).zip`, `report-reference-manifest(4).json`, `release-post-seal-attestation(1).json`, `test-execution-summary-full.junit(1).xml`, `test-execution-summary-full(1).log`, source ZIP clean extract 작업공간 |
| 이번 턴 직접 재실행 | ZIP inventory 재계산, attestation/manifest 재검토, `pytest --collect-only`, `make bootstrap-preflight`, `make static`, `tests/test_auto_improve_iteration_runtime.py`, `tests/test_generated_report_contracts.py -x`, `tests/test_writer_output_paths.py -x`, `make auto-improve-readiness-report-body`, `make release-distribution-zip` 장시간 재시도 |

---

## 0. 이 문서의 목적

이 보고서는 새로 제공된 두 리뷰를 각각 처음부터 끝까지 검토한 뒤, 이전에 업로드된 기존 리뷰들과 현재 업로드 세트의 실제 파일 상태를 다시 대조하여 **이번 체크포인트에서 어떤 문서를 기준 문서로 삼아야 하는지**, 그리고 **실제로 지금 남아 있는 문제를 어떤 순서로 닫아야 하는지**를 정리하기 위해 작성했다.

이번 문서에서 특히 중시한 것은 다음 네 가지다.

1. 새 두 리뷰가 공통으로 맞게 본 것
2. 새 두 리뷰 중 어느 문서가 더 잘 정리한 부분인지
3. 기존 리뷰와 연결될 때 강화되는 주장과 지금은 폐기해야 하는 주장
4. 실제 파일 재검증을 거치면 문장을 더 엄밀하게 고쳐야 하는 부분

---

## 1. 한눈에 보는 최종 결론

### 1.1 가장 중요한 한 문장

현재 체크포인트의 핵심 문제는 **source ZIP hygiene나 full-suite 건강도 부족이 아니라, source-only package와 evidence-complete workspace를 테스트와 release authority가 서로 다른 전제로 소비하고 있다는 계약 불일치**다.

### 1.2 새 두 리뷰에 대한 최종 판정

- `llmwiki_integrated_improvement_report_20260508.md`는 **현재 canonical 작업 계획 문서**로 채택하기에 가장 적합하다.
  - 장점은 진단, 우선순위, DoD, 미해소 축을 모두 한 문서 안에서 균형 있게 다룬다는 점이다.
  - 특히 P0-A~P0-H 구조는 지금 시점의 주요 리스크를 거의 빠짐없이 묶는다.

- `llmwiki_tri_review_integrated_improvement_report_20260508.md`는 **operator/manager용 요약 통합 문서**로 더 적합하다.
  - 장점은 cross-reference matrix와 phase-based execution order가 매우 읽기 쉽다는 점이다.
  - 다만 실제 파일과의 미세한 접점, 특히 typed field 부재나 재생성 후 테스트 불일치의 세부 증거는 첫 문서보다 덜 상세하다.

### 1.3 기존 리뷰들에 대한 최종 판정

- `llmwiki_uploaded_files_improvement_report_20260508.md`는 **실제 재실행 증거 보조 문서**로 계속 매우 유효하다.
- `llmwiki_meta_integrated_improvement_report_20260508(1).md`는 **문서 체계와 canonical hierarchy를 정리하는 메타 문서**로 유용하지만, 이번 신규 두 리뷰를 기준으로 다시 한 단계 구체화할 필요가 있다.
- `llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506(2).md`, `llmwiki_two_review_actual_crosscheck_improvement_report(4).md`, `LMMwiki교차검증 개선 보고서_20260506(1).md`는 **full snapshot 세대에서 source package 세대로 넘어오는 전환사 기록**으로 가치가 크다. 다만 지금 P0를 직접 지휘하는 기준 문서로 쓰기에는 일부 항목이 시점상 오래되었다.
- `integrated_improvement_report_v3(14).md`는 **운영 계약 drift를 보는 관점**은 여전히 유효하지만, 이번 체크포인트의 주축 이슈인 source/evidence/profile contract보다는 별도 갈래의 문제를 더 많이 다룬다.

---

## 2. 이번 턴에서 실제로 다시 확인한 범위

### 2.1 직접 재검증한 파일

- `LLMwiki-source(1).zip`
- `report-reference-manifest(4).json`
- `release-post-seal-attestation(1).json`
- `test-execution-summary-full.junit(1).xml`
- `test-execution-summary-full(1).log`
- source ZIP을 fresh extract한 `/tmp/llmwiki_source_only_check/LLMwiki`
- source ZIP 안의 `release-archive-self-description.json`
- `Makefile`, `README.md`, `tests/test_generated_report_contracts.py`, `tests/test_writer_output_paths.py`

### 2.2 직접 재실행한 명령

다음 명령은 이번 턴에서 실제로 다시 실행했다.

```bash
.venv/bin/python -m pytest -o addopts= --collect-only -q
make bootstrap-preflight PYTHON=.venv/bin/python
make static PYTHON=.venv/bin/python
.venv/bin/python -m pytest -o addopts= -q tests/test_auto_improve_iteration_runtime.py
.venv/bin/python -m pytest -o addopts= -q tests/test_generated_report_contracts.py -x
.venv/bin/python -m pytest -o addopts= -q tests/test_writer_output_paths.py -x
make auto-improve-readiness-report-body PYTHON=.venv/bin/python
.venv/bin/python -m pytest -o addopts= -q tests/test_generated_report_contracts.py -k checked_in_auto_improve_readiness_surfaces_remaining_learning_gaps -vv
make release-distribution-zip PYTHON=.venv/bin/python
```

### 2.3 이번 턴에서 확인한 핵심 결과

| 항목 | 결과 | 판정 |
| --- | --- | --- |
| ZIP SHA-256 | `3c515df62993b720dfa9e6eceaf5df8097cf5d0437f8347e389d17a1c56668f3` | 일치 |
| ZIP entry/file/dir | `1438 / 1438 / 0` | 일치 |
| ZIP uncompressed bytes | `230,646,256` | 일치 |
| ZIP unique timestamp count | `1` | 일치 |
| `ops/reports/`, `external-reports/`, `runs/`, `tmp/`, `build/` | ZIP 내 파일 수 0 | hygiene 충족 |
| `report-reference-manifest` current/review ZIP SHA | 둘 다 `3c515df...` | provenance 일치 |
| `distribution_provenance.status` | `basis_current_match` | 일치 |
| JUnit tests/failures/errors/skipped | `982 / 0 / 0 / 0` | full-suite 건강도 강함 |
| `pytest --collect-only` | `982 tests collected` | 일치 |
| `make bootstrap-preflight` | pass | 통과 |
| `make static` | ruff/mypy 모두 pass | 통과 |
| `tests/test_auto_improve_iteration_runtime.py` | `8 passed` | 통과 |
| `tests/test_generated_report_contracts.py -x` | canonical artifact 부재로 즉시 실패 | 실패 재현 |
| `tests/test_writer_output_paths.py -x` | `ops/script-output-surfaces.json` 부재로 실패 | 실패 재현 |
| `make auto-improve-readiness-report-body` | canonical report 생성 성공 | 재생성 경로 정상 |
| 생성 후 readiness contract test | `loop_health_summary.status: missing != available`로 실패 | 테스트 기대치 불일치 |
| `make release-distribution-zip` | 10분 시도 후 종료, partial ZIP 잔류 | boundedness 미흡 |

---

## 3. 새 두 리뷰의 구조와 강점 비교

### 3.1 `llmwiki_integrated_improvement_report_20260508.md`

이 문서는 **가장 균형 잡힌 주 문서**다.

#### 강점

1. **진단 → 근본 원인 → 우선순위 → DoD**가 한 흐름으로 이어진다.
2. 단순 consensus 문서가 아니라, **리뷰별 고유 발견사항**을 별도 섹션으로 분리한다.
3. P0를 `release authority`, `source-only/evidence-complete contract`, `truth ladder`, `self-description drift`, `readiness contract`까지 넓게 커버한다.
4. static lane, evidence bundle, release boundedness, writer 공용화 같은 **후속 구조 과제의 배치가 자연스럽다**.

#### 실제 파일과 대조했을 때 특히 강한 부분

- source ZIP hygiene가 강하다는 점
- full-suite evidence가 이미 충분히 강하다는 점
- release authority가 여전히 blocked라는 점
- source-only package와 evidence-complete workspace의 테스트 계약이 어긋난다는 점
- `make auto-improve-readiness-report-body`는 살아 있지만 결과와 test expectation이 어긋난다는 점

#### 보정이 필요한 부분

1. `release-post-seal-attestation(1).json`에서 `full_suite=pass`, `learning_revalidation=missing_signoff`, `accepted_risks=2`, `advisory_lifecycle=1`은 **typed field로 노출된 값이 아니라 `operator_summary` 문자열 안에 들어 있는 값**이다.
   - 즉 문서가 지적한 방향은 맞지만, 현재 구조는 “typed closure 미완”을 더 강하게 드러낸다.
2. self-description과 post-seal sidecar의 광범위한 digest drift는 문서가 말한 대로 매우 그럴듯하고, 실제로 **`report-reference-manifest` hash mismatch는 직접 재확인**했다. 그러나 이번 턴에서는 batch manifest/self-check/operator summary 실제 sidecar 파일이 별도로 업로드되지 않았으므로, 그 세 파일의 drift 전체를 이번 문서에서는 “기존 리뷰에 강하게 지지되고 manifest drift는 직접 확인됨” 수준으로 표현하는 편이 더 엄밀하다.

### 3.2 `llmwiki_tri_review_integrated_improvement_report_20260508.md`

이 문서는 **operator-facing 통합 요약본**으로 매우 좋다.

#### 강점

1. cross-reference matrix가 좋아서, 어떤 사실이 3/3 합의인지 빠르게 파악할 수 있다.
2. Phase 1~4 실행 순서가 선명해 **작업 관리용 문서로 쓰기 쉽다**.
3. “이미 해결된 문제”와 “현재 blocked 상태”를 구분해서 보여주는 방식이 좋다.
4. 세 리뷰의 고유 기여를 구분하는 섹션이 있어 문서 간 역할 분담이 명확하다.

#### 실제 파일과 대조했을 때 강한 부분

- source ZIP hygiene + full-suite evidence strong / post-seal authority blocked라는 핵심 도식
- package profile별 reproducibility contract가 아직 닫히지 않았다는 근본 원인 정의
- Phase별 실행 순서 정리

#### 보정이 필요한 부분

1. 문서가 concise한 대신, **fresh extract 첫 실패 지점의 실제 파일명과 에러 메시지 수준 증거가 약하다**.
   - 이번 턴 재실행에서는 첫 실패가 `ops/reports/artifact-freshness-report.json` 부재였다.
2. `tests/test_writer_output_paths.py` 문제도 “generated artifact 기대치 불일치”로 요약되지만, 실제로는 `ops/script-output-surfaces.json`를 직접 읽다가 `FileNotFoundError`가 발생한다.
3. `make auto-improve-readiness-report-body` 재생성 후 mismatch도 문서가 요약은 잘했지만, 실제 값은 **`learning_readiness.metrics.telemetry_coverage_ratio=0.0`가 nested field에 존재하고, `diagnostics.loop_health_summary.status=missing`이 핵심 실패 원인**이라는 점을 더 정확히 적는 편이 좋다.

### 3.3 두 문서의 역할 분담 결론

| 역할 | 더 적합한 문서 | 이유 |
| --- | --- | --- |
| canonical 작업 기준 문서 | `llmwiki_integrated_improvement_report_20260508.md` | 상세 진단과 우선순위가 가장 균형적임 |
| 운영진/관리자 요약 문서 | `llmwiki_tri_review_integrated_improvement_report_20260508.md` | matrix와 phase가 더 빠르게 읽힘 |
| 티켓 분해/실행 관리 | 두 문서 병행 | 첫 문서는 내용, 둘째 문서는 진행 순서에 강함 |

---

## 4. 기존 리뷰들과의 관계

### 4.1 `llmwiki_uploaded_files_improvement_report_20260508.md`

이번 신규 두 리뷰와 가장 직접적으로 연결되는 기존 문서다.

#### 지금도 유효한 이유

- 업로드 세트만으로 실제 재실행한 결과를 가장 많이 담고 있다.
- source-only package와 evidence sidecar가 분리돼 있다는 현재 상태 설명이 정확하다.
- generated report contract와 writer/output surface가 실제로 깨진다는 점을 현행 업로드 세트로 보여준다.

#### 이번 신규 두 리뷰가 이 문서 위에 추가한 것

- 우선순위 체계의 정교화
- phase-based execution order
- tri-review 통합 관점의 역할 분담

### 4.2 `llmwiki_meta_integrated_improvement_report_20260508(1).md`

이 문서는 **문서 체계와 canonical hierarchy**를 정리하는 데 강하다.

#### 지금도 유효한 이유

- 어떤 문서를 canonical action plan으로 채택해야 하는지 판단하는 구조가 좋다.
- “현재 구현 상태 설명용 문서”와 “역사적 전환점 문서”를 구분한 태도가 좋다.

#### 이번 신규 두 리뷰가 더 나아간 점

- 현재 체크포인트에서 직접 필요한 P0를 더 세밀하게 쪼갠다.
- operator-facing phase plan이 더 실무적이다.
- uploaded-files 기반 actual rerun 결과를 더 직접적으로 흡수한다.

### 4.3 2026-05-06 계열 보고서들

- `llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506(2).md`
- `llmwiki_two_review_actual_crosscheck_improvement_report(4).md`
- `LMMwiki교차검증 개선 보고서_20260506(1).md`

이 문서들은 여전히 가치가 있지만, 현재 체크포인트에서는 **주요 reference라기보다 historical baseline**으로 두는 편이 맞다.

#### 이유

1. 당시에는 full snapshot 또는 그 과도기 상태를 많이 다뤘다.
2. 지금은 source ZIP hygiene, current distribution provenance, full-suite evidence closure가 이미 크게 전진했다.
3. 그래서 이 문서들에서 제시한 일부 P0는 이미 해소됐거나, 표현을 현재형으로 다시 써야 한다.

### 4.4 `integrated_improvement_report_v3(14).md`

이 문서는 운영 계약 drift, direct entrypoint, console script, artifact freshness semantics를 보는 관점에서 여전히 유용하다. 다만 이번 체크포인트의 주 질문은 **release source package / evidence bundle / post-seal authority / source-only reproducibility**이므로, 이 문서를 주 기준으로 삼기보다는 **보조 관점 문서**로 두는 편이 맞다.

---

## 5. 실제 파일 대조 결과 — 이번 턴 확정 사실

### 5.1 Source ZIP과 provenance

#### 직접 확인한 사실

- `LLMwiki-source(1).zip` SHA-256은 `3c515df62993b720dfa9e6eceaf5df8097cf5d0437f8347e389d17a1c56668f3`다.
- ZIP entry/file/dir 수는 `1438 / 1438 / 0`이다.
- `raw=446`, `wiki=417`, `ops=311`, `tests=155`, `system=71`, `root=19`, `.codex=10`, `tools=6`, `.github=2`, `.ouroboros=1`이다.
- `ops/reports/`, `external-reports/`, `runs/`, `tmp/`, `build/`, `.obsidian/`, `.vscode/`, `__pycache__/`는 ZIP 안에 파일이 0개였다.
- `report-reference-manifest(4).json`의 `review_basis_zip.sha256`와 `current_distribution_zip.sha256`는 둘 다 위 ZIP SHA와 같고, `distribution_provenance.status`는 `basis_current_match`였다.

#### 해석

새 두 리뷰가 공통으로 말한 “현재 ZIP은 source-only package로서 hygiene가 강하다”는 진단은 이번 턴에서도 그대로 지지된다.

### 5.2 Full-suite evidence

#### 직접 확인한 사실

- 업로드된 JUnit XML에는 `982 tests`, `0 failures`, `0 errors`, `0 skipped`, `time=224.447`가 기록돼 있었다.
- 업로드된 로그에는 `982 passed in 224.45s (0:03:44)`가 남아 있었다.
- source-only extract에서 `pytest --collect-only -q`를 다시 돌리면 `982 tests collected in 17.78s`가 나왔다.

#### 해석

새 두 리뷰가 공통으로 말한 “full-suite evidence는 더 이상 빈칸이 아니다”라는 판단은 맞다. 이 축은 **새로 만들어야 할 증거**가 아니라 **attestation과 release authority에 더 직접 바인딩해야 할 기존 증거**다.

### 5.3 Post-seal attestation

#### 직접 확인한 사실

- `release-post-seal-attestation(1).json`의 top-level `status`는 `pass`다.
- `verification.status`도 `pass`다.
- `release_authority.batch_manifest_status=fail`
- `release_authority.release_authority_status=blocked`
- `release_authority.semantic_release_status=blocked`
- `release_authority.sealed_release_status=unsealed_release_blocked`
- `release_authority.machine_release_status=blocked`
- `release_authority.operator_release_status=blocked`
- `release_authority.operator_summary_status=attention`

다만 다음 값들은 typed field가 아니라 `release_authority.operator_summary` 문자열 안에 존재한다.

- `full_suite=pass`
- `learning_revalidation=missing_signoff`
- `accepted_risks=2`
- `advisory_lifecycle=1`

#### 해석

새 두 리뷰가 말한 “integrity verification pass와 release authority blocked가 공존한다”는 요지는 맞다. 그러나 이번 턴 재검증 기준으로 더 엄밀한 문장은 다음이다.

> **현재 attestation은 결합 무결성 검증은 통과했지만, release를 막는 일부 사유를 아직 typed field가 아니라 operator summary string에 남겨두고 있다.**

즉 문제는 단순히 blocked라는 사실만이 아니라, **왜 blocked인지가 기계적으로 완결돼 있지 않다**는 점이다.

### 5.4 Source-only clean extract에서 실제로 깨지는 지점

#### 직접 확인한 첫 실패들

1. `tests/test_generated_report_contracts.py -x`
   - 첫 실패: `ops/reports/artifact-freshness-report.json` canonical report가 없으므로 regenerate하라는 assertion failure
2. `tests/test_writer_output_paths.py -x`
   - 첫 실패: `ops/script-output-surfaces.json`를 직접 읽다가 `FileNotFoundError`

#### 해석

이 실패는 source ZIP이 망가졌다는 뜻이 아니다. 오히려 반대로, **source ZIP이 generated artifact를 의도적으로 제외하는 패키지인데 테스트가 evidence-complete workspace를 기대하고 있다는 뜻**이다.

이 점에서 새 두 리뷰의 핵심 진단은 정확하다.

### 5.5 Readiness regeneration의 실제 상태

#### 직접 확인한 사실

`make auto-improve-readiness-report-body`는 성공적으로 다음 canonical report를 생성했다.

- `ops/reports/auto-improve-readiness.json`
- `artifact_kind = auto_improve_readiness_report`
- `artifact_status = current`
- `learning_readiness.status = not_runnable`
- `can_execute_trial = false`
- `can_promote_result = false`
- `diagnostics.loop_health_summary.status = missing`
- `learning_readiness.metrics.telemetry_coverage_ratio = 0.0`
- `diagnostics.loop_health_summary.telemetry_coverage_ratio = 0.0`

이후 다음 테스트를 다시 돌리면 실패한다.

- `tests/test_generated_report_contracts.py -k checked_in_auto_improve_readiness_surfaces_remaining_learning_gaps`
- 실패 이유: `loop_health_summary.status`가 실제로는 `missing`인데 테스트는 `available`을 기대함

#### 해석

새 두 리뷰와 기존 uploaded-files 보고서가 공통으로 짚은 **“재생성 경로는 살아 있지만 regenerated report와 test contract가 맞지 않는다”**는 결론은 이번 턴에서도 그대로 재현됐다.

### 5.6 Self-description과 post-seal manifest의 digest 차이

#### 직접 확인한 사실

source ZIP 내부 `release-archive-self-description.json`에는 다음 linked artifact SHA가 기록돼 있었다.

- `external-reports/report-reference-manifest.json` → `6b89b5fc323f1d94a8e6963ebb0caccacd317a80423d0a309fc9d6449c1b902a`

하지만 실제 업로드된 `report-reference-manifest(4).json`의 SHA는 다음과 같다.

- `fa81be62668889a5ae76f73ca977c317bb6fe00b5577c860b1bd261e989a20f9`

즉 두 값은 일치하지 않는다.

#### 해석

이건 새 두 리뷰가 강조한 **pre-seal self-description vs post-seal sidecar drift**의 실제 사례다. 이번 턴에서는 manifest에 대해서만 직접 확인했지만, 적어도 이 축 자체가 허상이 아니라는 점은 분명하다.

### 5.7 Release-distribution-zip boundedness

#### 직접 확인한 사실

- `make release-distribution-zip`를 장시간 재시도했지만 10분 내에 완료되지 못했다.
- 종료 시점에 `build/release/LLMwiki-source.zip` partial artifact가 남아 있었고 크기는 `145,074,625 bytes`였다.
- 정상 source ZIP 크기 `190,007,603 bytes`보다 작았다.

#### 해석

새 두 리뷰가 말한 “live rerun boundedness 부족”은 이번 턴에서도 강화되었다. 적어도 지금 상태에서는 **실패 또는 장시간 중단이 partial artifact를 깔끔히 봉인/정리하는 구조가 아니다.**

---

## 6. 새 두 리뷰의 주장별 최종 판정

| 주장 | 최종 판정 | 이번 턴 근거 |
| --- | --- | --- |
| source ZIP hygiene는 강하다 | 유지 | 직접 ZIP inventory 재계산으로 확인 |
| current distribution provenance mismatch는 해소되었다 | 유지 | manifest current/review SHA 일치 확인 |
| full-suite evidence는 이미 강하다 | 유지 | JUnit/log/collect-only 모두 일치 |
| release authority는 아직 blocked다 | 유지 | attestation 구조 직접 확인 |
| blocked의 핵심은 batch/signoff/risk/advisory다 | 유지하되 표현 보정 | 현재 일부 값은 typed field가 아니라 operator_summary string에 있음 |
| root cause는 reproducibility contract 미폐쇄다 | 강화 | source-only fresh extract 실패가 직접 재현됨 |
| generated artifact contract가 source-only 모드에서 깨진다 | 유지 | report-contract, writer-output-paths 둘 다 실패 재현 |
| readiness regeneration 결과와 테스트 기대치가 어긋난다 | 유지 | regenerated report + targeted contract test로 재현 |
| self-description vs post-seal digest drift가 있다 | 부분 직접 확인 + 유지 | manifest SHA mismatch 직접 확인 |
| full-suite summary는 attestation의 1급 binding으로 승격돼야 한다 | 유지 | 현재는 operator_summary string 안에만 pass가 드러남 |
| truth ladder를 operator-facing으로 단일화해야 한다 | 유지 | verification pass와 release blocked가 동시에 존재 |

---

## 7. 이번 체크포인트에서 채택할 개선 우선순위

### P0-1. Package Mode / Test Mode를 분리해서 강제한다

가장 먼저 해야 할 일은 source-only package와 evidence-complete workspace를 구분하는 계약을 코드, 테스트, Makefile에 동시에 반영하는 것이다.

#### 반드시 포함할 작업

- `source_only`
- `evidence_complete`
- `review_bundle`
- `full_vault_snapshot`

같은 **명시적 package mode enum**을 정책/테스트/문서에 통일한다.

#### 바로 수정해야 할 테스트

- `tests/test_generated_report_contracts.py`
- `tests/test_writer_output_paths.py`

#### 목표

source ZIP만 풀어도 통과해야 하는 최소 test target과, evidence artifact가 있어야만 통과하는 target을 완전히 분리한다.

### P0-2. Release Authority의 차단 사유를 typed field로 승격한다

현재 가장 중요한 구조 문제는 `release-post-seal-attestation(1).json`이 blocked 상태를 보여주면서도, full-suite/signoff/risk/advisory 중 일부를 `operator_summary` 문자열에 남겨두고 있다는 점이다.

#### 바로 수정해야 할 방향

다음은 operator summary string에서 꺼내 typed field로 올려야 한다.

- `full_suite_status`
- `learning_revalidation_status`
- `accepted_risk_count`
- `advisory_lifecycle_count`
- `blocking_reasons[]`

#### 목표

operator가 한 줄 summary만 봐도 **검증 pass / release blocked / 다음 조치**를 바로 이해할 수 있게 한다.

### P0-3. Batch manifest, signoff, risk lifecycle을 실제 release unlock path로 닫는다

새 두 리뷰는 모두 이 축을 P0로 다뤘고, 이번 턴 실제 파일도 그 판단을 지지한다.

#### 닫아야 할 순서

1. `batch_manifest_status=fail` 원인을 구조화
2. `learning_revalidation=missing_signoff`를 실제 signoff artifact로 해소
3. accepted risk 2건과 advisory lifecycle 1건을 owner/expiry/release effect 포함 typed ledger로 전환

#### 목표

`release_authority_status`가 더 이상 opaque blocked가 아니라, **명시적 unlock 또는 operator waiver**로 설명되게 만든다.

### P0-4. Full-suite summary JSON을 attestation binding으로 승격한다

현재 full-suite pass는 강한 증거인데, attestation에서 중심 위치를 차지하지 못한다.

#### 수정 방향

- `test-execution-summary-full.json`을 attestation `reports` 또는 `bindings`에 직접 추가
- JUnit/log SHA도 함께 watch
- static evidence는 별도 lane으로 유지

#### 목표

full-suite pass가 operator summary string의 일부가 아니라 **1급 evidence binding**이 된다.

### P0-5. Readiness regeneration contract를 테스트와 동기화한다

이번 턴에서 가장 명확하게 재현된 mismatch다.

#### 수정 방향

- `learning_readiness.status = not_runnable`
- `diagnostics.loop_health_summary.status = missing`
- `telemetry_coverage_ratio = 0.0`

같은 상태가 source-only mode에서 정상인지, 아니면 실패인지 정책과 테스트 양쪽에서 같게 정의한다.

#### 목표

재생성된 canonical report와 contract test의 기대가 일치한다.

### P1-1. Evidence bundle을 독립 artifact로 명문화한다

권장 구조는 다음과 같다.

1. `LLMwiki-source.zip` — source/content package
2. `LLMwiki-release-evidence.zip` — reports, summaries, JUnit/log, signoff, manifest
3. `release-post-seal-attestation.json` — 두 artifact와 authority를 묶는 binding

### P1-2. Self-description의 pre-seal/post-seal semantics를 명시한다

현재 self-description linked hash와 post-seal sidecar hash가 달라질 수 있다는 사실은 거의 분명하다. 그러면 필드명과 semantics도 그 사실을 드러내야 한다.

#### 권장 방향

- `sha256` → `pre_seal_observed_sha256`
- `authoritative_post_seal_digest_source`
- `self_description_linkage_status`

같은 필드를 도입한다.

### P1-3. `release-distribution-zip`를 bounded failure 구조로 바꾼다

- atomic temp path 사용
- 실패 시 partial ZIP 자동 정리 또는 quarantine
- incomplete state를 machine-readable로 봉인

### P2-1. 문서와 빌드 도구의 환경 계약을 정리한다

이번 턴에서도 README는 `.venv` 중심, Makefile 기본값은 `$(HOME)/.venvs/llm-wiki-vnext`라는 긴장이 그대로 있었다. 이건 P0는 아니지만, 새 작업자가 다른 interpreter를 잡는 문제를 줄이기 위해 정리할 필요가 있다.

### P2-2. 대형 runtime/test 파일 분해와 artifact writer 공용화는 P0 이후로 미룬다

이건 중요한 구조 과제지만, 지금 당장 먼저 닫아야 할 문제는 **contract closure**다. 즉 리팩터링보다 **판정 구조와 evidence 소비 구조**를 먼저 안정화해야 한다.

---

## 8. 어떤 문서를 기준으로 채택할 것인가

### 8.1 권장 canonical 문서 체계

| 역할 | 채택 문서 | 이유 |
| --- | --- | --- |
| primary canonical plan | `llmwiki_integrated_improvement_report_20260508.md` | 가장 상세하고 균형적인 현재형 실행 문서 |
| operator digest | `llmwiki_tri_review_integrated_improvement_report_20260508.md` | matrix와 phase가 뛰어남 |
| rerun evidence appendix | `llmwiki_uploaded_files_improvement_report_20260508.md` | 실제 재실행 결과가 가장 직접적임 |
| hierarchy / archival interpretation | `llmwiki_meta_integrated_improvement_report_20260508(1).md` | 문서 체계 판단에 도움 |
| historical baseline | 2026-05-06 계열 보고서들 | 시점 이동을 설명하는 배경 자료 |

### 8.2 지금 가장 위험한 오해

가장 위험한 오해는 다음 두 가지다.

1. **source ZIP이 깨끗하니 release도 거의 끝났다**고 보는 것
2. **full-suite가 pass했으니 blocked는 사소하다**고 보는 것

이번 턴 실제 파일은 둘 다 지지하지 않는다.

정확한 문장은 다음과 같다.

> source ZIP hygiene는 강하고 full-suite evidence도 강하다. 그러나 release authority는 아직 typed closure가 덜 끝난 blocked 상태이며, source-only 재현 계약도 테스트 차원에서 닫히지 않았다.

---

## 9. 최종 정리

### 9.1 유지해야 할 판단

- source ZIP hygiene가 강하다는 판단
- full-suite evidence가 충분히 강하다는 판단
- current distribution provenance mismatch가 해소되었다는 판단
- 지금 남은 핵심 문제가 contract closure라는 판단

### 9.2 이번 턴에서 더 엄밀하게 고쳐야 하는 판단

- blocked 사유 중 일부는 아직 typed field가 아니라 operator summary string에 있다.
- self-description drift는 최소 manifest에 대해서는 직접 확인됐지만, 모든 sidecar에 대해 이번 턴에서 직접 재확인한 것은 아니다.
- readiness mismatch는 단순 “telemetry coverage 0” 한 줄보다, **`loop_health_summary.status=missing`와 contract expectation 불일치**로 적는 것이 더 정확하다.

### 9.3 최종 권고

이번 체크포인트에서 실제 작업 기준 문서는 `llmwiki_integrated_improvement_report_20260508.md`로 삼고, `llmwiki_tri_review_integrated_improvement_report_20260508.md`는 운영 요약본으로 병행 사용하는 구성이 가장 좋다.

그리고 첫 작업은 새 기능 추가가 아니라 다음 세 가지를 묶어 닫는 것이다.

1. **package mode / test mode 분리**
2. **release authority blocked reason typed closure**
3. **readiness regeneration contract 동기화**

이 세 가지가 닫히면, 지금까지의 많은 보고서가 지적해 온 문제의 중심축이 처음으로 실제 운영 계약 형태로 정리된다.
