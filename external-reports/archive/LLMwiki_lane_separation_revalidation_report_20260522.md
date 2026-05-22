# LLMwiki Lane-Separated Self-Improvement Revalidation Report

작성일: 2026-05-22 (Asia/Seoul)  
대상: 업로드 ZIP 원본 저장소 `LLMwiki(5).zip`, 기존 작성 보고서, 추가 사용자 가설  
산출물 형식: Markdown  
파일명: `LLMwiki_lane_separation_revalidation_report_20260522.md`

---

## 1. 최종 판정

이번 재검토의 결론은 기존 보고서의 큰 방향을 유지하되, 우선순위를 더 엄격하게 수정해야 한다는 것이다.

기존 보고서는 “테스트가 약한 저장소가 아니라, release / public / report_contract / supply-chain / generated artifact 방어선이 두껍고 그 비용이 커지는 저장소”라고 판단했다. 이 판단은 여전히 맞다. 다만 이번 재검증에서 더 핵심적인 원인이 확인됐다. **문제의 중심은 단순한 테스트 수나 multi-marker 중복이 아니라, 검증 lane과 증거 생성·currentness repair lane이 같은 release closeout 흐름 안에서 섞여 있다는 점**이다.

특히 `check-all`은 개발자 상위 검증 lane이며 `artifact_finalization`을 의도적으로 제외한다. 반대로 `report-contract-closeout`과 `release-evidence-closeout`은 여러 canonical report를 실제로 다시 쓰는 수렴·증거 생성 lane이다. 따라서 “테스트가 실패해서 제품이 깨진다”기보다, **테스트와 closeout target 일부가 canonical report currentness repair 역할까지 맡으면서 release seal 직전·직후의 상태가 계속 움직이는 구조**가 더 정확한 문제 정의다.

가장 중요한 실증 결과는 다음 네 가지다.

1. `release-closeout-fixed-point`는 기존 checked-in report와 재실행 candidate 모두 5회 반복 후에야 `11 -> 10 -> 9 -> 8 -> 0` changed paths로 수렴한다. 이것은 현재 closeout writer set이 실제로 반복 수렴을 필요로 한다는 직접 증거다.
2. checked-in `release-closeout-finality-attestation.json`은 `finality_status=pass`를 담고 있지만, 현재 checked-in 파일 기준 `make release-closeout-finality-verify`는 실패했다. 실패 원인은 `tracked_digest_map_current_mismatch`와 `fixed_point_digest_map_current_mismatch`이며, 세 개 canonical report digest가 현재 파일과 attestation/fixed-point digest map 사이에서 어긋났다.
3. `release-closeout-summary.json`의 `sealed_release_status=unsealed_distribution_not_provided`는 sealed authority와 정면 모순이라기보다, pre-distribution/source closeout surface가 sealed vocabulary를 빌려 쓰는 데서 생기는 의미 충돌이다. 운영자가 이를 모순으로 읽는 것은 정상이며, 명명과 authority 분리를 해야 한다.
4. `make release-evidence-closeout-sealed-dry-run-check`는 distribution ZIP binding 자체는 통과했지만, release authority가 conditional이라 `sealed_conditional_pass`에서 막혔다. 즉 “distribution binding”과 “authoritative sealed clean pass”는 별도 축이다.

따라서 장기 최적 개편의 1순위는 다음 세 lane 분리다.

| 새 lane | 성격 | canonical write 허용 | dirty 허용 | 목적 |
|---|---:|---:|---:|---|
| `release-evidence-converge` | 생성·수렴 lane | 예 | 예 | canonical report writer set을 한 번의 DAG로 수렴시킨다. |
| `release-verify-current` | check-only currentness lane | 아니오 | 아니오 | schema/static/artifact-finalization/public mirror/finality currentness를 검증한다. |
| `release-sealed-verify` | frozen evidence + source ZIP sealed lane | 아니오 | 아니오 | freeze 이후 source ZIP과 frozen evidence manifest 기준으로만 봉인 검증한다. |

---

## 2. 검토 범위와 재검증 방식

검토 대상은 다음이다.

- 업로드된 `LLMwiki(5).zip`을 로컬 원본 저장소로 해제한 작업트리
- 업로드된 기존 보고서 `LLMwiki_self_improvement_review_report_2026-05-22(1).docx`
- 사용자가 제시한 lane 혼합 가설과 구체 line reference
- `Makefile`, `mk/test.mk`, `mk/release.mk`, `ops/README.md`
- `ops/reports/release-closeout-summary.json`
- `ops/reports/release-closeout-fixed-point.json`
- `ops/reports/release-closeout-finality-attestation.json`
- `ops/reports/release-closeout-batch-manifest.json`
- `ops/reports/release-closeout-sealed-rehearsal-check.json`
- `ops/operator/operator-release-summary.json`
- 테스트 collection, 주요 make target, dry-run sealed check, post-check finalizer

저장소 메타데이터는 다음과 같다.

| 항목 | 값 |
|---|---|
| HEAD | `6309b428b703bb3c42b0220db152fb6a7d8f6247` |
| branch | `main` |
| origin | `https://github.com/22nsuk/LLMwiki.git` |
| 작업트리 상태 | Python `zipfile` 해제 후 clean, dry-run 후 tracked 변경 복구 완료 |
| 공개 GitHub 접근 | repo root/tree/actions/commits 모두 404 응답. 공개 상태는 확인 불가. |

의존성은 `.venv`를 재구성해 설치했다. 확인된 핵심 버전은 Python 3.13.5, pytest 8.4.2, pytest-xdist 3.8.0, mypy 1.20.2, ruff 0.15.14다.

---

## 3. 기존 보고서에 대한 수정 평가

기존 보고서의 주요 진단은 다음 네 가지였다.

1. multi-marked 파일이 여러 lane에서 반복 실행되어 비용을 만든다.
2. `fixed_context`, minimal vault seeding, 임시 디렉터리 구성이 파일별로 반복된다.
3. `generated-artifact-converge`가 closeout target 안에서 여러 번 반복된다.
4. CI workflow는 강하지만 bootstrap/reusable workflow/concurrency 관점에서 비용 최적화 여지가 있다.

이번 재검증 결과, 위 네 가지는 모두 타당하다. 다만 **원인 계층이 하나 더 위에 있다.** multi-marker와 fixture 반복은 비용 문제이고, `generated-artifact-converge` 반복은 orchestration 문제다. 하지만 release closeout에서 더 위험한 문제는 **“check라고 읽히는 단계가 실제로 canonical state를 갱신하거나, state 갱신 직후 다시 check-only authority처럼 보이는 surface를 생성한다”**는 점이다.

따라서 기존 보고서의 우선순위는 다음과 같이 보정한다.

| 기존 우선순위 | 보정 후 우선순위 | 이유 |
|---|---|---|
| P1 multi-marked 파일 정리 | P2 | 중요하지만 lane mutability 분리 후 처리해야 비용 절감이 안전하다. |
| P1 fixture/시딩 통합 | P2 | 여전히 유효하나 release authority 혼합보다 낮다. |
| P1 artifact refresh DAG 정리 | P0/P1 | 단순 비용 문제가 아니라 finality/currentness authority 문제다. |
| P2 CI concurrency/reusable workflow | P2 | release lane 의미가 정리된 뒤 matrix를 얇게 해야 한다. |
| 신규 없음 | P0 lane mutability 분리 | 이번 재검증의 핵심이다. |
| 신규 없음 | P0 sealed status vocabulary 분리 | 운영자 모순 인식을 줄이는 데 즉시 필요하다. |
| 신규 없음 | P0 finality attestation verify 실패 해결 | checked-in pass surface와 live verify 결과가 불일치한다. |

---

## 4. 코드 레벨 재검증 결과

### 4.1 `check-all`은 artifact finalization을 의도적으로 제외한다

`Makefile` line 52의 `check-all`은 다음 target들을 묶는다.

```make
check-all: static artifact-freshness-check registry-preflight-check lint eval stage2-eval planning-gate unit-tests-all
```

`mk/test.mk` line 7은 개발자 full marker expression을 다음처럼 정의한다.

```make
PYTEST_DEVELOPER_FULL_MARK_EXPR ?= not artifact_finalization
```

즉 `check-all`이 `artifact_finalization`을 제외하는 것은 빠뜨림이 아니라 의도된 lane 정의다. 이 점에서 기존 보고서가 “artifact finalization 제외”를 단순 gap처럼 읽힐 여지를 남겼다면 보정해야 한다. `artifact_finalization`은 별도 finalization self-check lane이며, 개발자 full check와 같은 의미가 아니다.

### 4.2 `report-contract-closeout`은 check-only가 아니라 mutating closeout lane이다

`mk/test.mk` line 167 이후 `report-contract-closeout`은 다음 흐름을 가진다.

```make
report-contract-closeout:
    $(MAKE) report-contract-closeout-precheck
    $(MAKE) release-smoke-full-reuse
    $(MAKE) test-execution-summary
    $(MAKE) generated-artifact-converge
    $(MAKE) release-closeout-summary-report
    $(MAKE) release-evidence-cohort
    $(MAKE) generated-artifact-converge
    $(MAKE) release-closeout-summary-report
    $(MAKE) auto-improve-readiness-report-body
    $(MAKE) generated-artifact-converge
    $(MAKE) test-artifact-finalization
```

이 target은 이름에 `test`와 `report-contract`가 들어가지만 본질은 **canonical reports를 갱신하고 수렴시키는 생성 lane**이다. 따라서 여기에서 dirty가 생기는 것은 제품 failure라기보다 lane 성격상 정상일 수 있다. 문제는 이 target이 검증 lane처럼 사용되거나 해석될 때 발생한다.

### 4.3 `release-evidence-closeout`도 canonical writer set을 움직이는 lane이다

`mk/release.mk` line 140 이후 `release-evidence-closeout-phase-1`은 `refresh-generated-core`, `release-smoke-full`, `release-source-package-check`, `generated-artifact-converge`, `test-execution-summary-report-contract-refresh`, `release-closeout-summary-report`, `auto-improve-readiness-report-body` 등을 호출한다.

`phase-2` 역시 full-suite summary, function budget proposal, learning evidence, release closeout summary, strict cohort, dashboard, lane summary, blocker ledger, `generated-artifact-converge` 등을 이어서 실행한다. `phase-3`는 `test-artifact-finalization`, `release-closeout-post-check-finalizer-dry-run`, `release-closeout-fixed-point`, `release-closeout-finality-verify`로 끝난다.

따라서 `release-evidence-closeout`은 final authoritative clean lane을 목표로 하지만, 절차상으로는 **write-heavy convergence lane + final verify**가 합쳐져 있다. 장기 최적 구조에서는 이 둘을 target 이름과 output authority에서 분리해야 한다.

---

## 5. 동적 실행 결과 요약

| 실행 | 결과 | 해석 |
|---|---:|---|
| `make static` | pass | ruff/mypy 모두 통과. |
| `pytest --collect-only -q` | 1,461 tests / 192 files | 기존 보고서 수치와 일치. |
| `make test-artifact-finalization` | 9 passed in 3.98s | finalization self-check는 현재 통과. tracked diff 없음. |
| `make test-release-sealing` | 39 passed in 21.72s | target 자체는 통과. 단 marker 전체 46개 중 명시 파일 target은 39개만 실행한다. |
| `make test-subprocess` | 2 passed in 0.17s | subprocess lane 정상. |
| `make release-closeout-finality-verify` | fail | checked-in finality attestation과 현재 tracked artifact digest가 불일치. |
| `make release-closeout-post-check-finalizer-dry-run --fail-on-refresh-required` | exit 2 / attention | 11개 canonical path refresh 필요. |
| `make release-closeout-fixed-point` | candidate pass, make target은 tool cap으로 중단 | candidate 기준 5회 반복 후 수렴. canonical writer set이 반복 repair를 요구한다는 증거. |
| `make release-evidence-closeout-sealed-check` | fail | default `build/release/LLMwiki-source.zip` absent / not bound 상태. |
| `make release-evidence-closeout-sealed-dry-run-check` | fail, but binding pass | distribution ZIP은 생성·binding 통과, release authority가 conditional이라 sealed clean 통과는 아님. |

`make check-all`과 `make test-report-contract`는 이 실행 환경의 tool cap 때문에 완주시키지 못했다. 이는 저장소 failure로 판정하지 않았다. 기존 업로드 보고서의 실행 결과는 fast/public/report-contract 대표 lane의 통과를 이미 기록하고 있으며, 이번 재검증은 그 결과를 부정하지 않는다. 이번 보고서의 핵심은 전체 pass/fail 재판정이 아니라 release currentness와 sealed authority 경계의 재검증이다.

---

## 6. 가장 중요한 발견: finality attestation pass와 live verify 실패

checked-in `ops/reports/release-closeout-finality-attestation.json`은 다음 의미를 가진다.

- `finality_status = pass`
- `finality_failures = []`
- `matches_fixed_point_digest_map = true`

그러나 현재 작업트리에서 `make release-closeout-finality-verify`를 실행하면 실패한다.

```text
failures:
- tracked_digest_map_current_mismatch
- fixed_point_digest_map_current_mismatch
status: fail
```

확인된 digest mismatch는 다음 세 파일이다.

| path | current digest | attestation/fixed-point digest |
|---|---|---|
| `ops/reports/generated-artifact-index.json` | `97114e251a31692273b8b183a8596332876e579e7c026ad6c0721a5dc4c5058b` | `0220ea32953db1f54973fa3a4b348e59e9742a1a8e0080d0a0d61e115f515e5d` |
| `ops/reports/artifact-freshness-report.json` | `97fa672772b6f4c080d63ea62c7384ab4035989e222b4666e823b7136709e888` | `a80608b6a13249eb2d468971098a711ba58fe4b9c93aa339df0f91317ec1dc05` |
| `ops/reports/auto-improve-readiness.json` | `522382b183a61a6cfa12210fbcca0bbacb6af90cc633999cc24dab4b3a1f4b98` | `76bc57e56e1380693c5d2a87fec47c59b03225c0d3bfd97329b116fd9aec6542` |

이 발견은 중요하다. git 작업트리가 clean이어도 checked-in finality surface가 현재 report contents와 의미상 current하지 않을 수 있다. 즉 clean tree와 finality currentness는 같은 것이 아니다.

장기 최적 관점에서 이 문제는 다음처럼 처리해야 한다.

1. `release-verify-current`는 `release-closeout-finality-verify`를 check-only gate로 반드시 포함해야 한다.
2. finality attestation을 생성하는 target은 `release-evidence-converge` 안으로만 들어가야 한다.
3. freeze 이후에는 canonical report writer를 호출하지 못하게 해야 한다.
4. sealed verify는 checked-in currentness가 아니라 frozen evidence manifest + source ZIP + digest map 기준으로 검증해야 한다.

---

## 7. fixed-point 수렴은 “테스트 실패”가 아니라 currentness repair loop의 증거다

`ops/reports/release-closeout-fixed-point.json`과 재실행 candidate 모두 다음 결과를 보였다.

| iteration | changed path count | 의미 |
|---:|---:|---|
| 1 | 11 | 첫 writer set 실행 후 대량 refresh 필요. |
| 2 | 10 | downstream report가 다시 움직임. |
| 3 | 9 | readiness/cohort/dashboard/lane/blocker 계열이 계속 움직임. |
| 4 | 8 | batch/self-check 계열까지 재정렬. |
| 5 | 0 | 최종 수렴. |

이 수렴은 좋은 방어 장치다. 하지만 이 장치가 release 검증 lane 안에서 계속 호출되면 운영자는 다음 두 현상을 겪는다.

- 방금 검증한 상태가 다음 target에서 다시 바뀐다.
- “pass report”와 “current repair 필요 report”가 같은 closeout vocabulary 안에서 공존한다.

따라서 fixed-point writer set은 제거할 것이 아니라 **mutating convergence lane의 유일한 핵심으로 격리**해야 한다.

---

## 8. sealed status vocabulary 문제

### 8.1 closeout summary의 `sealed_release_status`는 이름이 과하다

현재 `ops/reports/release-closeout-summary.json`은 다음 값을 가진다.

```json
{
  "semantic_release_status": "conditional_pass",
  "sealed_release_status": "unsealed_distribution_not_provided",
  "status_v2": {
    "status_axes": {
      "release_authority_status": "conditional_pass",
      "semantic_release_status": "conditional_pass",
      "sealed_release_status": "unsealed_distribution_not_provided"
    }
  }
}
```

이 값은 실제 sealed authority와 모순이라기보다는, source/pre-distribution closeout surface가 sealed vocabulary를 노출하면서 생기는 naming problem이다. 이 summary는 distribution package가 아직 제공되지 않은 상태를 말하고 있을 뿐, 이미 materialized된 sealed distribution sidecar를 부정하는 authority가 아니다.

하지만 운영자 입장에서는 같은 필드명 `sealed_release_status`가 서로 다른 authority level에서 반복되므로 모순처럼 보일 수밖에 없다. 필드명을 낮춰야 한다.

권장 변경:

| 현재 필드 | 권장 필드명 | 의미 |
|---|---|---|
| `release-closeout-summary.sealed_release_status` | `pre_distribution_package_binding_status` | source closeout이 distribution binding 전 상태임을 표시. |
| `status_v2.status_axes.sealed_release_status` in summary | `source_closeout_distribution_binding_status` | sealed authority가 아니라 source closeout axis임을 명확화. |
| authoritative sealed status | 유지 | batch/operator/sealed-check/finality 계열에만 둔다. |

### 8.2 authoritative sealed status surface는 basis-specific이어야 한다

현재 확인된 surface들은 서로 다른 basis를 가진다.

| surface | generated_at | 상태 | basis |
|---|---:|---|---|
| `release-closeout-summary.json` | 2026-05-21T18:01:01Z | `conditional_pass`, `unsealed_distribution_not_provided` | source/pre-distribution closeout |
| `release-closeout-batch-manifest.json` | 2026-05-21T18:01:01Z | `conditional_pass`, `unsealed_distribution_not_provided` | distribution not provided snapshot |
| `release-closeout-sealed-rehearsal-check.json` | 2026-05-21T04:44:00Z | `pass`, `sealed_clean_pass` | tmp sealed dry-run distribution ZIP basis |
| `operator-release-summary.json` | 2026-05-15T19:08:59Z | `clean_pass`, `sealed_clean_pass` | older operator release/source ZIP basis |
| 재실행 `release-evidence-closeout-sealed-dry-run-check` | 2026-05-22T04:37:17Z | `binding_pass_authority_blocked`, `sealed_conditional_pass` | 새 tmp source ZIP basis |

이 표가 보여주는 핵심은 “어떤 status가 맞는가”가 아니라 “status는 evidence basis와 함께 읽어야 한다”는 것이다. 동일한 필드명으로 서로 다른 basis의 authority를 노출하면 운영자는 자연스럽게 모순으로 읽는다.

---

## 9. sealed dry-run 재검증 해석

기본 sealed check는 실패했다.

```text
make release-evidence-closeout-sealed-check
status: fail
preflight_status: binding_failed
distribution_zip.exists: false
distribution_zip.path: build/release/LLMwiki-source.zip
batch_manifest.sealed_release_status: unsealed_distribution_not_provided
```

이 실패는 source ZIP이 materialized되지 않은 기본 상태에서는 예상 가능한 실패다. 즉 제품 결함이라기보다 sealed check의 precondition 불충족이다.

반면 dry-run sealed check는 source ZIP을 생성하고 strict external manifest를 binding했다.

```text
make release-evidence-closeout-sealed-dry-run-check
status: fail
preflight_status: binding_pass_authority_blocked
distribution_binding_status: pass
distribution_zip.exists: true
distribution_zip.entry_count: 1628
batch_manifest.distribution_package_status: materialized
batch_manifest.external_source_zip_bound_status: bound
batch_manifest.release_authority_status: conditional_pass
batch_manifest.sealed_release_status: sealed_conditional_pass
summary: distribution binding pass; release authority blocked
```

이 결과는 사용자의 해석을 지지한다. `sealed_release_status=unsealed_distribution_not_provided`와 `sealed_clean_pass`류 surface는 같은 authority level이 아니며, source closeout과 machine-sealed distribution check를 분리해야 한다.

---

## 10. 테스트 lane 효과 재검토

### 10.1 전체 collection과 marker 분포

재수집 결과는 1,461 tests / 192 files다. marker 조합은 다음과 같다.

| marker 조합 | tests | files |
|---|---:|---:|
| `(fast/unmarked)` | 748 | 107 |
| `artifact_finalization` | 1 | 1 |
| `artifact_finalization|report_contract` | 8 | 1 |
| `integration` | 8 | 1 |
| `integration_heavy|report_contract` | 8 | 1 |
| `integration|report_contract` | 31 | 1 |
| `public` | 220 | 36 |
| `public|release_sealing` | 44 | 3 |
| `public|report_contract` | 205 | 19 |
| `release_sealing` | 2 | 1 |
| `report_contract` | 167 | 14 |
| `slow` | 17 | 8 |
| `subprocess` | 2 | 1 |

기존 보고서의 multi-marked 비용 진단은 유지된다. 다만 이번에는 다음 구분을 추가해야 한다.

- multi-marked 중복은 **비용 문제**다.
- explicit selector와 marker expression의 불일치는 **기대 테스트 효과 문제**다.
- finality currentness mismatch는 **release authority 문제**다.

### 10.2 `test-artifact-finalization`은 현재 기대 효과를 낸다

`mk/test.mk`의 `REPORT_CONTRACT_FINALIZATION_TESTS`는 9개 명시 nodeid를 실행한다. 수집 기준 `artifact_finalization` marker 역시 9개 test다.

- `make test-artifact-finalization`: 9 passed
- marker count: 9
- tracked diff: 없음

따라서 현재 `artifact_finalization` lane은 기대한 효과를 대체로 낸다. 단, 명시 nodeid 목록은 장기적으로 drift risk가 있다. marker expression과 명시 목록의 parity guard를 추가하는 것이 좋다.

### 10.3 `test-release-sealing`은 marker 대비 실행 범위가 좁다

`mk/test.mk` line 15에는 `PYTEST_RELEASE_SEALING_MARK_EXPR ?= release_sealing`이 있다. 하지만 `test-release-sealing` target은 marker expression이 아니라 `RELEASE_SEALING_TESTS` 명시 파일 3개만 실행한다.

현재 수집 기준 `release_sealing` marker는 총 46개 test / 4개 file이다.

| file | release_sealing tests |
|---|---:|
| `tests/test_release_closeout_batch_manifest.py` | 26 |
| `tests/test_release_evidence_closeout_self_check.py` | 11 |
| `tests/test_release_sealing_lane.py` | 2 |
| `tests/test_release_status_v2.py` | 7 |

그런데 `RELEASE_SEALING_TESTS`는 앞의 3개 파일만 포함하고, `tests/test_release_status_v2.py` 7개를 실행하지 않는다. `make test-release-sealing`이 39 passed로 끝난 이유다.

이것은 이번 재검토에서 확인된 “기대한 테스트 효과가 나오지 않는 부분”이다. target이 release sealing marker 전체를 대표한다는 이름을 갖고 있으려면 다음 중 하나를 선택해야 한다.

1. `tests/test_release_status_v2.py`를 `RELEASE_SEALING_TESTS`에 포함한다.
2. target 이름을 `test-release-sealing-core`로 낮추고, 별도 `test-release-sealing-all`을 marker expression으로 만든다.
3. `ops/test-lane-registry.json`에 explicit selector lane과 marker-wide lane을 별도 등록한다.

### 10.4 `test-report-contract`는 marker-wide가 아니라 core pack이다

수집 기준 `report_contract and not artifact_finalization`은 411개 test다. 그러나 `make test-report-contract`는 `REPORT_CONTRACT_CORE_TESTS` 기반 explicit selector pack을 실행한다. 기존 보고서의 `191 passed, 8 deselected` 수치는 이 core pack의 결과이지 marker-wide report_contract 전체의 결과가 아니다.

이 자체가 버그는 아니다. 하지만 운영자와 기여자에게는 다음처럼 명명해야 한다.

- `test-report-contract-core`: 현재 explicit selector pack
- `test-report-contract-all`: marker expression-wide pack
- `report-contract-closeout`: mutating evidence convergence lane

이렇게 이름을 나눠야 “contract test가 통과했다”와 “contract evidence가 수렴했다”를 혼동하지 않는다.

---

## 11. 과다·반복·비용 발생 지점

### 11.1 필요 이상으로 과다한 부분

“테스트가 많다” 자체는 문제가 아니다. 문제는 테스트 목적과 output authority가 섞인 데 있다.

과다하다고 볼 수 있는 것은 다음이다.

- 같은 canonical report currentness를 여러 target에서 반복 repair하는 구조
- explicit selector target이 marker-wide lane처럼 읽히는 naming
- `release-closeout-summary`, `batch-manifest`, `operator-summary`, `sealed-check`가 같은 `sealed_release_status` vocabulary를 공유하는 구조
- `report-contract-closeout` 안에서 `generated-artifact-converge`가 여러 번 호출되는 구조
- closeout finalizer가 drift를 감지하면서도 이후 target들이 다시 canonical write를 수행하는 구조

### 11.2 상호 참조로 반복 비용을 만드는 부분

`release-closeout-summary`, `auto-improve-readiness`, `generated-artifact-index`, `artifact-freshness-report`, `release-evidence-cohort`, `release-evidence-dashboard`, `release-lane-summary`, `release-clean-blocker-ledger`, `release-closeout-batch-manifest`, `release-evidence-closeout-self-check`는 서로 currentness와 digest를 참조한다.

이 구조가 나쁘다는 뜻은 아니다. 운영형 release evidence workspace에서는 필요한 구조다. 다만 지금은 producer와 consumer가 같은 closeout 흐름에서 반복 실행되기 때문에 다음 패턴이 발생한다.

```text
producer A writes
consumer B reads A and writes
index/freshness C reads A/B and writes
summary D reads C and writes
self-check E reads D and writes
finality F binds A/B/C/D/E
next check detects A/B/C drift
```

장기 최적 해법은 producer-refresh-once / validate-many다.

```text
1. source tree fingerprint 확정
2. canonical producer set 1회 refresh
3. generated artifact index/freshness 1회 refresh
4. consumer reports validate-only
5. fixed-point는 converge lane에서만 허용
6. freeze manifest 작성
7. 이후 verify는 frozen manifest 기준 check-only
```

### 11.3 기대 효과가 나오지 않는 테스트

다음은 삭제할 테스트가 아니라 이름·scope·authority를 고쳐야 하는 테스트/target이다.

| 대상 | 현재 문제 | 권장 조치 |
|---|---|---|
| `test-release-sealing` | marker 46개 중 target 39개만 실행 | `core/all` 분리 또는 누락 파일 포함 |
| `test-report-contract` | marker-wide 411개가 아니라 core pack | 이름을 `test-report-contract-core`로 변경 |
| `report-contract-closeout` | test처럼 읽히지만 mutating closeout | `report-contract-evidence-converge` 등으로 rename/alias |
| `release-evidence-closeout` | write-heavy convergence와 final verify 결합 | converge / verify / sealed-verify 분리 |
| `release-closeout-summary.sealed_release_status` | sealed authority처럼 보이는 source closeout field | field rename/demotion |
| `release-closeout-finality-attestation` | checked-in pass이나 live verify 실패 | verify gate 강화, freeze 후 write 금지 |

---

## 12. 권장 target 구조

아래 구조는 기존 target을 전면 폐기하는 것이 아니라, 의미를 명확히 나누는 alias/신규 target 설계다.

### 12.1 Mutating lane: `release-evidence-converge`

목적: canonical report를 실제로 쓰고, currentness repair를 수행하고, fixed-point까지 수렴시킨다. dirty가 정상일 수 있다.

```make
release-evidence-converge:
	$(MAKE) refresh-generated-core
	$(MAKE) bootstrap-preflight
	$(MAKE) registry-preflight
	$(MAKE) static
	$(MAKE) release-smoke-full-reuse
	$(MAKE) test-execution-summary
	$(MAKE) test-execution-summary-report-contract-refresh
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) release-evidence-cohort
	$(MAKE) release-evidence-dashboard-report
	$(MAKE) release-lane-summary
	$(MAKE) release-clean-blocker-ledger
	$(MAKE) release-closeout-fixed-point
	$(MAKE) release-closeout-finality-attestation
```

핵심 규칙:

- canonical writer는 이 lane에만 위치시킨다.
- `generated-artifact-converge`는 중간중간 반복하지 말고 phase boundary에서 최소화한다.
- dirty가 발생하면 정상으로 보고, 마지막에 operator에게 변경 path와 next verify target을 명시한다.

### 12.2 Check-only lane: `release-verify-current`

목적: source tree와 checked-in canonical evidence가 current하고 서로 일관되는지 확인한다. canonical write 금지.

```make
release-verify-current:
	$(MAKE) static
	$(MAKE) artifact-freshness-check
	$(MAKE) registry-preflight-check
	$(MAKE) test-artifact-finalization
	$(MAKE) test-release-sealing-all
	$(MAKE) public-check-summary-check
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required
	$(MAKE) release-closeout-finality-verify
	git diff --exit-code
```

핵심 규칙:

- 모든 output은 `tmp/` 또는 stdout이어야 한다.
- canonical report path write 금지.
- drift가 있으면 “어떤 converge target을 실행해야 하는지”만 알려준다.
- 이 lane에서 dirty가 생기면 lane policy violation으로 본다.

### 12.3 Frozen sealed lane: `release-sealed-verify`

목적: freeze 이후 source ZIP과 frozen evidence manifest를 기준으로 sealed authority만 검증한다.

```make
release-sealed-verify:
	$(PYTHON) -m ops.scripts.release_frozen_manifest_verify \
		--manifest build/release/release-frozen-evidence-manifest.json \
		--source-zip build/release/LLMwiki-source.zip
	$(MAKE) release-evidence-closeout-sealed-check \
		RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=build/release/LLMwiki-source.zip \
		RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT=tmp/release-sealed-verify.json
	git diff --exit-code
```

핵심 규칙:

- freeze 이후 canonical report write 금지.
- source ZIP digest, frozen manifest digest, batch manifest digest, self-check digest, external manifest basis를 함께 묶는다.
- sealed status는 이 lane과 operator summary/batch manifest sidecar에서만 authoritative하게 노출한다.

---

## 13. closeout-summary 필드 개편안

### 13.1 즉시 적용할 alias/deprecation

현재 필드를 바로 제거하기 어렵다면 다음처럼 transitional schema를 둔다.

```json
{
  "semantic_release_status": "conditional_pass",
  "pre_distribution_package_binding_status": "distribution_not_provided",
  "deprecated_fields": {
    "sealed_release_status": {
      "value": "unsealed_distribution_not_provided",
      "deprecated_reason": "source closeout summary is not sealed distribution authority",
      "replacement": "pre_distribution_package_binding_status"
    }
  }
}
```

### 13.2 authoritative status owner

| status | owner | 비고 |
|---|---|---|
| `semantic_release_status` | closeout summary, batch, operator | source/release readiness 의미. |
| `release_authority_status` | batch, sealed-check, finality | machine release gate 의미. |
| `sealed_release_status` | bound batch manifest, operator summary, sealed-check sidecar | source ZIP/distribution binding 이후만 authoritative. |
| `pre_distribution_package_binding_status` | closeout summary | distribution 전 상태. |
| `finality_status` | finality attestation / verify | digest map currentness authority. |

---

## 14. 실행 로드맵

### 0단계: 즉시 조치, 1~2일

1. `release-closeout-finality-verify` 실패를 release closeout currentness blocker로 승격한다.
2. `release-closeout-summary.sealed_release_status`를 deprecated alias로 낮추고 새 필드 `pre_distribution_package_binding_status`를 추가한다.
3. `test-release-sealing`을 `test-release-sealing-core`로 rename하거나 `tests/test_release_status_v2.py`를 포함한다.
4. explicit selector와 marker expression parity guard를 추가한다.
5. `report-contract-closeout`이 mutating lane임을 target help/README/registry에 명시한다.

### 1단계: lane 분리, 1~2주

1. `release-evidence-converge` 신규 target 생성.
2. `release-verify-current` 신규 target 생성.
3. `release-sealed-verify` 신규 target 생성.
4. 기존 `release-evidence-closeout`은 transition alias로 유지하되 내부에서 위 target 순서를 명시한다.
5. canonical report write target은 converge lane에만 등록한다.

### 2단계: DAG 최적화, 2~6주

1. `generated-artifact-converge` 반복 호출을 phase boundary 중심으로 줄인다.
2. fixed-point writer set의 input/output fingerprint를 더 명시적으로 노출한다.
3. `release-closeout-post-check-finalizer`를 check-only lane의 첫 drift detector로 고정한다.
4. public/report_contract/release_sealing multi-marked 파일은 single-lane ownership + thin sentinel 구조로 정리한다.
5. pytest fixture는 `tmp_path_factory` 기반 session template vault와 domain builder fixture로 전환한다.

### 3단계: CI와 저장소 성장 정책, 6~12주

1. GitHub Actions `concurrency`와 `cancel-in-progress`를 PR workflow에 도입한다.
2. Python/uv/bootstrap은 reusable workflow로 모은다.
3. heavy release verify는 대표 Python 버전으로 축소하고, fast/public/subprocess만 multi-version에 남긴다.
4. raw/runs/.git growth guardrail을 둔다.
5. source ZIP 해제 재현성, 비ASCII path 보존, sealed freeze manifest 검사를 source package smoke에 포함한다.

---

## 15. 자가 개선 관점의 최종 제언

LLMwiki의 자가 개선 체계는 이미 상당히 성숙하다. learning evidence, auto-improve readiness, release evidence, generated artifact finalization, public mirror, sealed check까지 갖춘 점은 강점이다. 다만 지금 구조는 자가 개선의 장점인 “currentness repair”가 release authority의 단점인 “seal 이후 불변성”과 같은 lane 안에서 섞여 있다.

자가 개선 시스템에서는 repair loop가 필요하다. 그러나 repair loop는 반드시 mutating convergence lane 안에 있어야 한다. 반대로 release verification은 repair하지 말고, current하지 않으면 실패해야 한다. sealed verification은 더 엄격해야 하며, frozen manifest와 source ZIP 기준으로만 판단해야 한다.

따라서 이번 기회에 다음 원칙을 저장소 운영 규칙으로 고정하는 것이 좋다.

```text
Generate once in converge lane.
Verify without writing in current lane.
Seal only frozen evidence in sealed lane.
```

한국어로 풀면 다음 한 문장이다.

**증거는 수렴 lane에서만 만들고, 검증 lane에서는 절대 고치지 말고, 봉인 lane에서는 freeze된 증거와 source ZIP만 믿어라.**

이 원칙을 적용하면 테스트 강도는 유지하면서도 운영자 혼란, 반복 비용, finality drift, status vocabulary 충돌을 동시에 줄일 수 있다.

---

## Appendix A. 재검증 command log 요약

```text
make dev-install
make static
.venv/bin/python -m pytest --collect-only -q
make test-artifact-finalization
make test-release-sealing
make test-subprocess
make release-closeout-finality-verify
make release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required
make release-closeout-fixed-point
make release-evidence-closeout-sealed-check
make release-evidence-closeout-sealed-dry-run-check
```

일부 장시간 target은 실행 환경의 tool cap으로 make wrapper가 끝까지 완료되지는 않았다. 이 경우에도 생성된 candidate/tmp report와 checked-in report를 함께 대조해 판단했고, tracked 변경은 복구해 clean 상태로 마무리했다.

---

## Appendix B. 참고한 외부 공식 문서

- pytest fixtures: https://docs.pytest.org/en/stable/explanation/fixtures.html
- pytest tmp_path / tmp_path_factory: https://docs.pytest.org/en/stable/how-to/tmp_path.html
- pytest-xdist distribution: https://pytest-xdist.readthedocs.io/en/stable/distribution.html
- GitHub Actions concurrency: https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency
- GitHub Actions reusable workflows: https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows
- GitHub Actions dependency caching: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching

---

## Appendix C. 핵심 체크리스트

| 질문 | 이번 판정 |
|---|---|
| 테스트가 부족한가? | 아니다. 방어선은 강하다. |
| 테스트가 과다한가? | 테스트 수 자체보다 lane 의미 혼합과 repeated currentness repair가 과다하다. |
| `check-all`이 artifact finalization을 빠뜨린 것인가? | 아니다. 의도적 제외다. |
| `report-contract-closeout`은 검증 lane인가? | 아니다. mutating evidence convergence lane이다. |
| `release-closeout-summary`의 sealed status는 authoritative sealed status인가? | 아니다. pre-distribution/source closeout status로 낮춰야 한다. |
| checked-in finality attestation은 current한가? | 이번 live verify 기준 아니다. 세 canonical report digest mismatch가 확인됐다. |
| fixed-point 반복은 의미 있는가? | 의미 있다. 다만 converge lane에 격리해야 한다. |
| 가장 먼저 고칠 것은? | lane 3분리, sealed vocabulary demotion, finality verify gate 강화. |
