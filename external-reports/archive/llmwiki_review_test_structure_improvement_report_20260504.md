# LLMwiki 리뷰 대조 및 테스트 구조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-04 (Asia/Seoul) |
| 산출 파일 | `llmwiki_review_test_structure_improvement_report_20260504.md` |
| 기준 ZIP | `LLMwiki.zip` |
| 기준 ZIP SHA-256 | `0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93` |
| 기준 ZIP entry 수 | 1,819 |
| 검토 방식 | 신규 리뷰 2건 전체 확인 → 이전 리뷰 대조 → 실제 ZIP/Makefile/JSON/테스트 구조 대조 → 선택적 재검증 |
| 코드 수정 여부 | 없음. 읽기 중심 검토이며, 실행 검증은 별도 추출본에서 수행했다. |

---

## 1. 입력 자료와 검토 범위

이번 검토는 사용자가 추가로 제공한 두 리뷰를 중심으로 수행했다.

| 구분 | 파일명 | 라인 수 | SHA-256 |
| --- | --- | ---: | --- |
| 이전 리뷰 | `llmwiki_external_reports_remaining_work_review_20260504.md` | 543 | `57a7904d108cc36072a229aab2095412bfcc55906749ee8f012dbb7b386e89a3` |
| 신규 리뷰 1 | `llmwiki_external_reports_integrated_review_20260504.md` | 596 | `8f07c2e4a3ca4e475529d41df11e61eeb0d01d3aac13aae25506a1ca63817c4b` |
| 신규 리뷰 2 | `LLMwiki External Reports 통합 재검토 보고서.md` | 412 | `c8b3f3000a44b2325b6aa5042279635959397f27faac59d0aee64d8cdbf9d42b` |

비교 기준은 세 층이다. 첫째, 이전 리뷰인 `llmwiki_external_reports_remaining_work_review_20260504.md`다. 둘째, 신규 리뷰 2건인 `llmwiki_external_reports_integrated_review_20260504.md`와 `LLMwiki External Reports 통합 재검토 보고서.md`다. 셋째, 실제 `LLMwiki.zip` 추출본의 `Makefile`, `pyproject.toml`, `pytest.ini`, `tests/`, `ops/scripts/`, `ops/reports/*.json`, `external-reports/`다.

이 보고서는 기존 리뷰들의 결론을 단순 재서술하지 않고, 특히 **현재 테스트 구조가 테스트 자체를 위한 테스트로 흘러가고 있는지**, **release evidence 검증 체계를 대대적으로 개편해야 하는지**를 별도 축으로 검토했다.

---

## 2. 최종 판정

현재 ZIP은 과거 비보관 보고서들이 지적한 direct wrapper drift, output surface registry, strict fingerprint coherence, artifact freshness, release lane summary 같은 상당수 P0를 이미 흡수했다. 그러나 신규 리뷰 2건과 실제 파일을 대조하면 다음 결론이 더 정확하다.

> 체크인 산출물은 `clean_pass` 계열까지 도달했지만, 아직 **봉인된 clean release**가 아니다. 핵심 이유는 `release-closeout-batch-manifest`가 실제 dashboard digest와 불일치하고, `tmp/*.json`가 release package verify precondition과 충돌하며, learning readiness signoff가 due 상태이고, test evidence가 전체 테스트 구조를 대표하지 못하기 때문이다.

테스트 구조에 대한 별도 판정은 다음과 같다.

> 현재 테스트가 전부 "테스트를 위한 테스트"는 아니다. 이 저장소의 목적이 runtime/evidence/정책 산출물을 관리하는 것이므로 schema, Makefile, generated artifact, release evidence를 검증하는 meta/contract test는 필요하다. 다만 지금 구조는 **meta-test와 release-finalization test가 실제 운영 무결성을 충분히 닫지 못하면서도 release confidence처럼 소비되는 문제**가 있다. 테스트 전체 폐기 수준의 재작성은 필요하지 않지만, **gate topology와 release evidence test lane은 대대적으로 재편해야 한다.**

---

## 3. 신규 리뷰 2건과 이전 리뷰의 대조

### 3.1 세 리뷰가 일치하는 항목

| 항목 | 통합 판정 |
| --- | --- |
| batch manifest / dashboard digest mismatch | 최우선 P0. baseline 실제 파일 기준 mismatch는 dashboard 1건이다. |
| `tmp/*.json` package 오염 | release verify precondition과 ZIP 내용이 충돌한다. |
| accepted-risk vocabulary 혼선 | closeout/cohort/lane/dashboard/ledger가 같은 위험을 서로 다른 언어로 표현한다. |
| learning readiness | signoff는 clean readiness가 아니라 conditional waiver에 가깝다. |
| command runtime | 정상 완료 subprocess가 환경에 따라 timeout으로 오인될 수 있다. |
| self-check path 오류 | 신규 리뷰에서 보강된 P0. 실제 self-check가 존재하지 않는 JSON path를 watch한다. |
| full-suite evidence 부족 | `test-execution-summary.json`의 119 pass는 전체 874개 테스트를 대표하지 않는다. |
| external report provenance | 비보관 보고서와 archive/reference/checkpoint를 machine-readable하게 연결해야 한다. |

### 3.2 신규 리뷰 1의 보강점

`llmwiki_external_reports_integrated_review_20260504.md`는 이전 리뷰보다 P0를 더 세밀하게 분리했다. 특히 다음 항목이 이전 보고서보다 강해졌다.

- `learning-readiness-signoff-revalidation-check` 실패를 P0로 승격.
- `release-evidence-closeout-self-check.json`의 `batch_manifest_component_count=0` 및 `batch_manifest.summary.release_authority_status` path 오류를 명시.
- `Full-Suite / Live-Builder 재검증 안정화`를 별도 P0로 분리.
- `sealed clean`과 `semantic clean` 분리, finalization 이후 canonical artifact 불변 관리, write-free check mode를 구조 개선 과제로 제시.

### 3.3 신규 리뷰 2의 보강점

`LLMwiki External Reports 통합 재검토 보고서.md`는 더 압축적이지만, 운영자가 취할 실행 순서가 분명하다.

- P0를 9개로 정리하면서 `dashboard 갱신과 batch finalizer 순서 고정`을 별도 P0로 둔다.
- `test-execution-summary`의 suite scope 문제를 명시한다.
- `operator one-page release summary`, `promotion CLI hang/cleanup guard`, `check 계열 write-free mode`를 실행 가능한 개선안으로 정리한다.
- 테스트 구조 관점에서는 "report-contract-summary 119개 pass가 전체 874개를 대표하지 않는다"는 위험을 분명하게 지적한다.

### 3.4 이전 리뷰에서 유지해야 할 내용

| 이전 리뷰 항목 | 현재 보정 |
| --- | --- |
| P0-1 batch manifest 재봉인 | 유지. 단, self-check path validator와 finalizer write-free invariant까지 포함해야 한다. |
| P0-2 `tmp/*.json` 오염 제거 | 유지. release package mode 분리가 더 명확한 해법이다. |
| P0-3 clean pass와 digest mismatch 공존 | 유지. mismatch가 diagnostic-only인지 release-blocking인지 schema에 명시해야 한다. |
| P0-4 accepted-risk vocabulary | 유지. 신규 리뷰의 field vocabulary를 채택할 수 있다. |
| P0-5 learning readiness | 유지. signoff lifecycle/revalidation을 release gate에 연결해야 한다. |
| P0-6 dashboard/finalizer 순서 | 유지. `sealed_clean_pass` 개념까지 확장할 필요가 있다. |
| P1 command_runtime | **P0로 승격 권장**. 현재 환경에서 `python -c` 정상 완료가 timeout으로 재현되었다. |
| P1 finalization test lane | **P0/P1 경계로 승격 권장**. release evidence가 전체 테스트를 대표하지 않는 문제가 직접 release confidence에 영향을 준다. |
| self-check field path 오류 | 이전 리뷰에는 없거나 약했으므로 **신규 P0로 추가**해야 한다. |

---

## 4. 실제 파일 대조 결과

### 4.1 Release evidence 핵심 상태

| 파일 | 실제 값 / 관찰 | 판정 |
| --- | --- | --- |
| `ops/reports/release-closeout-summary.json` | `status=pass`, `release_readiness_state=clean_pass`, `clean_release_ready=true`, `machine_release_allowed=true` | 선언상 clean pass |
| 같은 파일 | `downstream_input_digest_mismatch.status=mismatch`, `mismatch_count=7` | clean pass와 digest mismatch 의미가 충돌 |
| `ops/reports/release-closeout-batch-manifest.json` | `status=pass`, `release_authority_status=clean_pass`, required 10/10 current | 체크인 manifest 자체는 pass |
| baseline digest 대조 | batch manifest와 실제 파일 mismatch: `ops/reports/release-evidence-dashboard.json` | 현재 ZIP 기준 봉인 불일치 |
| `ops/reports/release-evidence-dashboard.json` | manifest 기대 `generated_at=2026-05-03T17:21:22Z`, 실제 `generated_at=2026-05-03T17:36:19Z` | dashboard가 batch manifest 이후 다시 써진 정황 |
| `tmp/` | `tmp/release-evidence-dashboard.candidate.json` | release verify precondition과 충돌 |
| `ops/reports/learning-readiness-signoff-revalidation.json` | `status=attention`, `revalidation.status=due` | revalidation due |
| `ops/reports/test-execution-summary.json` | `suite=report-contract-summary`, passed `119`, failed `0` | 전체 suite 대표 아님 |

### 4.2 Batch manifest baseline mismatch

현재 ZIP 원본 기준 batch manifest가 봉인한 artifact 10개 중 실제 digest와 다른 것은 다음 1건이다.

| path | manifest digest prefix | actual digest prefix | manifest generated_at | actual generated_at |
| --- | --- | --- | --- | --- |
| `ops/reports/release-evidence-dashboard.json` | `e9362674c1b3ba36` | `3d7126cc3c014957` | `2026-05-03T17:21:22Z` | `2026-05-03T17:36:19Z` |

주의할 점은 일부 live check 명령이 canonical report를 다시 쓰는 구조라서 **검증 실행 자체가 추가 mismatch를 만들 수 있다**는 점이다. 별도 실행본에서 `learning-readiness-signoff-revalidation-check`를 실행한 뒤 batch verify를 다시 돌리면 learning revalidation artifact까지 digest mismatch에 추가될 수 있었다. 이는 신규 리뷰들이 제안한 **write-free check mode**가 실제로 필요하다는 근거다.

### 4.3 Self-check의 path 오류

`ops/reports/release-evidence-closeout-self-check.json`은 status를 pass로 기록하지만 다음 문제가 있다.

| 항목 | 현재 값 | 실제 의미 |
| --- | --- | --- |
| `closeout_snapshot.batch_manifest_component_count` | `0` | batch manifest의 `summary.artifact_count`는 `10` |
| `drift_watch_list[0].field_path` | `batch_manifest.summary.release_authority_status` | 실제 `release_authority_status`는 batch manifest top-level 필드 |
| `drift_watch_list[0].snapshot_value` | `None` | path가 틀려 null을 캡처한 것으로 보인다 |

이 문제는 단순 문서 오류가 아니다. "self-check가 pass인데 실제로는 중요한 field path를 감시하지 못한다"는 뜻이므로, release finalization의 마지막 방어선이 약하다.

---

## 5. 현재 테스트 구조 전체 검토

### 5.1 테스트 인벤토리

| 항목 | 값 |
| --- | ---: |
| `tests/test_*.py` 파일 수 | 131 |
| AST 기준 test 함수 수 | 874 |
| Makefile target 수 | 133 |
| `pytest.ini` marker | slow, integration, integration_heavy, public, finalization |
| 체크인 `test-execution-summary` suite | `report-contract-summary` |
| 체크인 `test-execution-summary` passed | 119 |
| `report-contract-summary` collect nodeid | 119 |

파일 단위 marker로 근사하면 다음과 같다.

| marker | 파일 수 | 테스트 함수 수 근사 |
| --- | ---: | ---: |
| public | 22 | 176 |
| slow | 8 | 16 |
| integration | 2 | 28 |
| integration_heavy | 1 | 8 |
| finalization | 1 | 0 |
| 명시 file-level tier marker 없음 | - | 646 |

해석:

- 테스트 수 자체는 작지 않다. 874개 테스트 함수가 존재한다.
- 하지만 release evidence가 직접 기록한 것은 `report-contract-summary` 119개 pass다.
- `public` marker 파일은 public mirror 계약을 검증하지만, 기본 `make test` / `unit-tests`에서는 제외된다.
- `finalization` marker는 현재 `test_generated_report_contracts.py` 하나에 집중되어 있고, final package digest/sealing을 직접 닫는 데는 부족하다.

### 5.2 Makefile gate topology

| target | 역할 | 관찰 |
| --- | --- | --- |
| `make test` | `unit-tests` alias | fast marker expression: `not slow and not integration and not integration_heavy and not public` |
| `make test-all` | 전체 pytest | 실제 전체 suite 874개 수준. 신규 리뷰들은 완료하지 못했다고 보고 |
| `make check` | static + artifact freshness + registry/lint/eval/stage2/planning + unit-tests | public/finalization/release sealing 전체를 대표하지 않음 |
| `make check-clean` | `check` + warning-budget + report-contract-finalization + cohort check | batch manifest verify는 포함하지 않음 |
| `make release-clean` | `release-check` + warning-budget + release-evidence-closeout + cohort check | 가장 강한 release 계열 |
| `make release-evidence-closeout` | core refresh → static → release smoke → test summary → generated index → freshness → closeout → cohort/dashboard/lane/ledger → finalization → batch manifest → self-check → tmp clean → batch verify | 의도상 release evidence 봉인 recipe |

문제는 target의 이름과 실제 보증 범위가 운영자에게 혼동될 수 있다는 점이다. 예를 들어 `test-execution-summary`는 "테스트 실행 요약"처럼 보이지만 실제 suite는 `report-contract-summary`이고, 전체 874개 테스트의 요약이 아니다. 또한 `report-contract-finalization`은 checked-in generated artifact 일부만 검사하며, 현재 batch manifest digest mismatch를 막지 못했다.

### 5.3 현재 구조가 "테스트를 위한 테스트"인지

판정은 **부분적으로 그렇지만, 전체적으로는 아니다**.

#### 필요한 meta-test

다음 유형은 이 저장소 성격상 정당하다.

- `test_makefile_static_gates.py`: release/check target의 정책적 구성 drift를 잡는다.
- `test_pytest_entrypoint_guidance.py`: bare `pytest` 금지와 plugin policy를 강제한다.
- `test_generated_report_contracts.py`: checked-in generated artifact의 schema/envelope/currentness를 검증한다.
- `test_script_module_surface_contract.py`, `test_import_fallback_contract.py`: console script / direct fallback surface drift를 잡는다.
- `test_test_execution_summary.py`: test evidence builder 자체의 parsing/reuse/deselection semantics를 검증한다.

이런 테스트는 "테스트를 위한 테스트"라기보다 **운영 계약 자체를 테스트하는 contract test**다.

#### 문제가 되는 meta-test

다만 현재는 다음 지점에서 테스트가 자기목적화될 위험이 있다.

1. **정적 recipe test가 실제 봉인 불변식을 대체한다.**  
   `test_makefile_static_gates.py`는 recipe order를 확인하지만, 실제 ZIP에는 `tmp/*.json`와 dashboard digest mismatch가 남아 있다. 즉 "Makefile이 올바르게 보인다"는 테스트가 "release package가 봉인됐다"를 보장하지 못한다.

2. **generated artifact test가 artifact 생성 시스템의 실제 재실행 안정성을 대표하지 못한다.**  
   `test_generated_report_contracts.py`는 checked-in JSON의 shape/currentness를 많이 본다. 그러나 finalizer 이후 dashboard가 다시 쓰이는 문제, self-check watch path 오류, batch manifest live verify 실패는 빠져나갔다.

3. **test evidence가 테스트 전체를 대표하지 않는데 release confidence처럼 보인다.**  
   `test-execution-summary.json`은 119개 report-contract-summary pass를 기록한다. 전체 874개나 integration/subprocess-heavy lane의 상태와 분리되어 있음이 명확히 표시되지 않으면 운영자는 `status=pass`를 과대해석할 수 있다.

4. **self-check test가 self-check의 핵심 실패 모드를 놓쳤다.**  
   `test_release_evidence_closeout_self_check.py`는 drift watch list 존재와 snapshot capture를 확인하지만, watch path가 실제 payload에 존재하는지까지 검증하지 못했다.

5. **환경 민감 subprocess test가 unit lane과 섞여 있다.**  
   `command_runtime`은 fake backend로 충분히 단위 검증할 부분과 real subprocess startup 환경 검증을 분리해야 한다. 현재는 site import/startup hook 오염이 정상 완료 path를 timeout으로 보이게 한다.

### 5.4 대대적 개편이 필요한가

**테스트 코드 전체를 버리는 대대적 재작성은 필요하지 않다.** 현재 테스트는 많은 중요한 계약을 이미 포착하고 있고, minimal vault fixture와 schema validation 중심 구조도 재사용 가치가 높다.

하지만 **release gate 구조는 대대적인 재편이 필요하다.** 구체적으로는 다음 수준의 개편이 맞다.

| 영역 | 개편 수준 | 이유 |
| --- | --- | --- |
| 개별 unit/runtime tests | 중간 | 큰 파일 분해와 subprocess 분리 필요 |
| generated report contract tests | 중간~큼 | checked-in shape 검증에서 producer 재실행/봉인 invariant 검증으로 확장 필요 |
| release finalization tests | 큼 | batch manifest, self-check, dashboard, tmp hygiene, write-free check를 하나의 clean workspace scenario로 묶어야 함 |
| Makefile gate topology | 큼 | target 이름과 보증 범위를 재정의해야 함 |
| `test-execution-summary` artifact | 큼 | suite scope/matrix/full-suite status를 명확히 기록해야 함 |
| public/private/release package mode | 큼 | `tmp/`, generated reports, external reports 포함 정책을 분리해야 함 |

---

## 6. 제안하는 테스트 lane 재구성

### 6.1 Fast unit lane

목적: 개발자가 빠르게 돌리는 순수 동작 검증.

포함:
- pure runtime unit tests
- fake backend 기반 command runtime tests
- schema helper / path helper / policy helper
- minimal vault 기반 in-process tests

제외:
- real subprocess timeout tests
- checked-in generated artifact finalization tests
- ZIP/package sealing tests
- public export end-to-end tests

완료 기준:
- `make test-fast` 또는 현 `make test`가 이 lane만 대표한다고 명시.
- `test-execution-summary`가 이 lane을 기록할 때 `suite_scope=fast_unit`로 표시.

### 6.2 Public contract lane

목적: public mirror가 corpus 없이 동작하는지 확인.

포함:
- `public` marker tests
- import fallback
- script module surface
- Makefile static gates
- public surface policy
- export/public-check contract

완료 기준:
- `make check`가 public lane을 포함할지, 아니면 `make public-check`가 별도 필수 gate인지 release docs에 명시.
- release evidence에는 public lane 미실행 여부가 `not_run`으로 표시되어야 한다.

### 6.3 Generated artifact contract lane

목적: checked-in JSON/report의 schema, envelope, currentness 검증.

포함:
- `test_generated_report_contracts.py`
- `test_report_schemas.py`
- `test_report_schema_sample_regeneration.py`

개편:
- "checked-in shape 검증"과 "producer 재실행 결과 비교"를 분리한다.
- checked-in artifact test가 pass해도 live builder가 fail할 수 있음을 summary에 표시한다.

### 6.4 Release finalization / sealing lane

목적: machine release 직전 봉인 무결성 검증.

필수 scenario:
1. clean extracted workspace에서 `tmp/*.json` 없음 확인.
2. required artifact 10개 digest를 batch manifest와 비교.
3. dashboard/revalidation 같은 required artifact가 finalizer 이후 다시 쓰였는지 확인.
4. self-check watch path가 실제 payload에 존재하는지 확인.
5. `--check` 모드는 canonical report를 쓰지 않는지 확인.
6. batch verify status를 dashboard/lane summary/operator summary에 반영.

이 lane은 `report-contract-finalization`보다 강해야 하며, `release-clean`의 필수 하위 gate가 되어야 한다.

### 6.5 Integration / subprocess lane

목적: OS/Python/startup hook/timeout/real subprocess interaction 검증.

포함:
- real `command_runtime`
- release smoke
- run mechanism experiment
- public export subprocess path
- canonical promotion CLI hang/cleanup guard

개편:
- Python `-S` 또는 clean env 기반 hermetic subprocess runner를 별도 mode로 둔다.
- environment-sensitive 실패는 unit fail과 구분해서 기록하되, release builder 환경에서는 필수 gate로 삼는다.

### 6.6 Full release-builder lane

목적: release confidence의 최종 기준.

필수 기록:
- 전체 collect count
- 실행 count
- pass/fail/error/skip
- deselected count와 이유
- timeout된 nodeid
- 마지막 실행 nodeid
- per-test duration top N
- Python version, OS, plugin autoload, interpreter path class
- dependency install source
- clean workspace 여부
- `tmp/*.json` hygiene
- batch verify result
- signoff revalidation result

`test-execution-summary.json`은 이 lane을 기록할 수 있어야 하며, report-contract summary만 기록할 때는 그 범위가 제목과 필드에서 즉시 보이도록 해야 한다.

---

## 7. 우선순위별 개선 보고

### P0-1. Release package 봉인 무결성 복구

**현재 증거**

- baseline actual mismatch: `ops/reports/release-evidence-dashboard.json`.
- manifest digest prefix `e9362674c1b3ba36` vs actual digest prefix `3d7126cc3c014957`.
- dashboard actual `generated_at=2026-05-03T17:36:19Z`이 manifest 기대 `generated_at=2026-05-03T17:21:22Z`보다 늦다.
- top-level tmp JSON: `tmp/release-evidence-dashboard.candidate.json`.

**필요 작업**

- release package에서 `tmp/*.json` 제외 또는 package mode 분리.
- 모든 required artifact를 최종 생성한 뒤 batch manifest를 마지막 release-bound 봉인 artifact로 재생성.
- `release-closeout-batch-manifest-verify`가 clean extracted ZIP에서 pass하도록 보장.
- batch verify 결과를 dashboard/lane/operator summary에 표면화.

**추가 테스트**

- clean temp ZIP fixture에서 batch manifest verify가 pass해야 한다.
- `tmp/*.json`가 포함된 release package fixture는 fail하되, 메시지가 package mode 위반을 명확히 설명해야 한다.
- required artifact가 batch manifest 이후 바뀌면 finalization lane이 fail해야 한다.

### P0-2. Self-check watch path validator 추가

**현재 증거**

- `batch_manifest_component_count=0`, 실제 artifact count는 `10`.
- watch path `batch_manifest.summary.release_authority_status`는 실제 field 위치와 다르다.
- snapshot value가 null인데도 self-check status는 pass다.

**필요 작업**

- `get_path(payload, dotted_path)` 유틸 추가.
- required watch path가 missing이면 self-check status fail.
- `batch_manifest.release_authority_status`처럼 실제 top-level path를 참조.
- `batch_manifest_component_count`는 `summary.artifact_count` 또는 `len(artifacts)`와 일치시킨다.

**추가 테스트**

- 존재하지 않는 watch path를 넣으면 fail.
- top-level `release_authority_status` 변경을 감지하는 fixture 추가.
- self-check가 단순 snapshot artifact가 아니라 drift validator임을 test name과 schema에 반영.

### P0-3. `test-execution-summary`의 대표성 문제 수정

**현재 증거**

- 체크인 summary: `suite=report-contract-summary`, passed `119`.
- 실제 AST 기준 테스트 함수: `874`.
- collect nodeid: `119`.
- 신규 리뷰 2건 모두 전체 suite 완료 실패 또는 미완료를 지적했다.

**필요 작업**

- `suite_scope`를 필수 필드로 추가: `fast_unit`, `public_contract`, `report_contract_summary`, `finalization`, `integration`, `full_suite`, `release_builder_full`.
- `represents_full_suite: boolean` 추가.
- 전체 테스트가 아닌 summary에는 `not_full_suite_reason`을 필수화.
- release closeout summary가 test evidence를 읽을 때 suite scope를 함께 표시.

**추가 테스트**

- report-contract-summary가 full suite로 오인되지 않도록 schema/test invariant 추가.
- full suite 미실행이면 operator summary에 `full_suite_status=not_run` 표시.

### P0-4. `command_runtime` hermetic subprocess mode

**현재 증거**

별도 실행본에서 다음 차이를 확인했다.

| command | 결과 |
| --- | --- |
| `python -c "print('ok')"` | 10초 내 정상 종료하지 못하고 SIGTERM성 returncode `-15` |
| `python -S -c "print('ok')"` | 약 0.2초 내 `ok` 출력 후 정상 종료 |

이는 신규 리뷰의 "site import/startup hook이 timeout budget을 오염시킨다"는 판단과 일치한다.

**필요 작업**

- `run_with_timeout()`에 clean env / hermetic Python option을 추가하거나, Python subprocess용 wrapper contract를 별도로 둔다.
- unit test는 fake backend 중심으로 유지.
- real subprocess test는 integration lane으로 이동.
- launch latency와 execution timeout을 분리 기록.

**추가 테스트**

- `python -S -c` 또는 hermetic runner가 정상 완료 path를 안정적으로 통과.
- startup stderr가 있어도 timeout 판정이 왜 발생했는지 diagnostic에 남김.
- site import 오염이 있는 환경에서는 integration lane이 명확한 실패/attention을 낸다.

### P0-5. accepted-risk vocabulary 단일화

**현재 증거**

| artifact | 표현 |
| --- | --- |
| closeout summary | accepted risk family 1, clean pass |
| cohort | summary accepted risk 0, clean lane contract total accepted risk 1, zero accepted risk true |
| lane summary | clean lane pass 계열 |
| dashboard | accepted risk gate attention 2 |
| blocker ledger | blocker 1, accepted risk family 1, clean lane blocking 0 |

**필요 작업**

공통 vocabulary를 다음처럼 고정한다.

```json
{
  "accepted_risk_instance_count": 1,
  "accepted_risk_family_count": 1,
  "operator_accepted_risk_family_count": 1,
  "clean_lane_blocking_accepted_risk_family_count": 0,
  "dashboard_attention_gate_count": 2,
  "learning_readiness_blocker_open": true,
  "learning_readiness_blocker_operator_accepted": true
}
```

**추가 테스트**

- closeout/cohort/dashboard/lane/ledger/batch가 같은 fixture에서 같은 count semantics를 산출하는 reconcile test.
- `zero_accepted_risk_family=true`와 `total_accepted_risk_family_count>0`가 같은 축으로 해석되지 않도록 schema 설명 보강.

### P0-6. Learning readiness signoff lifecycle 정리

**현재 증거**

- `learning-readiness-signoff-revalidation.json`: `status=attention`, `revalidation.status=due`.
- signoff expiry: `2026-05-10T03:00:01Z`.
- `auto-improve-readiness.json`: `can_execute_trial=True`, `can_promote_result=False`, `learning_readiness.status=learning_uncertain`.

**필요 작업**

- metric 개선으로 learning readiness blocker를 닫거나,
- clean lane에서는 blocked로 남기고 conditional/operator-accepted lane에서만 release 허용하는 방식으로 artifact language를 분리한다.
- signoff 만료/재검증 due 상태가 release summary와 operator summary에 직접 표시되어야 한다.

**추가 테스트**

- active signoff, due signoff, expired signoff, metrics-clean 상태 4종 fixture.
- due signoff가 clean lane인지 conditional lane인지 expected field로 명확히 검증.

### P0-7. clean pass와 digest mismatch 공존 invariant

**현재 증거**

`release-closeout-summary.json`은 clean pass를 선언하면서 `downstream_input_digest_mismatch.status=mismatch`, `mismatch_count=7`을 함께 기록한다.

**필요 작업**

- mismatch가 diagnostic-only라면 `diagnostic_only=true`, `release_blocking=false`, `comparison_scope=previous_window` 같은 field를 추가.
- release-blocking이면 `clean_release_ready=false`.
- schema/test에 clean pass와 release-blocking mismatch의 동시 존재 금지 invariant 추가.

### P0-8. Check command write-free mode

**현재 증거**

- `release-evidence-cohort-check`는 diagnostic out을 `tmp/...`로 쓰지만, `learning-readiness-signoff-revalidation-check`는 canonical path를 직접 쓴다.
- `artifact-freshness-check`도 candidate 생성 후 canonical promote를 수행한다.
- 검증 실행 자체가 source tree와 batch manifest digest 관계를 바꿀 수 있다.

**필요 작업**

- `--check`는 기본적으로 write-free 또는 tmp-only.
- canonical promote는 명시적 `--promote` 또는 non-check target에서만 수행.
- `release-closeout-batch-manifest-verify` 전에는 required artifact canonical write 금지.

**추가 테스트**

- check target 실행 전후 required artifact digest가 같아야 한다.
- check가 실패해도 canonical output이 변경되지 않아야 한다.

### P0-9. Full-suite / release-builder evidence 안정화

**현재 증거**

- AST 기준 874개 테스트 함수.
- 신규 리뷰들은 전체 pytest suite 완료를 확인하지 못했다.
- 현재 체크인 summary는 119개 report-contract-summary만 pass.

**필요 작업**

- release-builder full lane을 별도 target으로 정의.
- full suite가 너무 무거우면 shard summary를 만들고 aggregate report를 release evidence로 삼는다.
- timeout, last nodeid, duration top N, shard status를 저장한다.

---

## 8. P1/P2 구조 개선

### P1

1. `operator-release-summary.md/json` 추가: clean pass, sealed status, accepted learning risk, full-suite status, batch verify status를 한 화면에 표시.
2. `external-reports/report-reference-manifest.json` 추가: 비보관 보고서 4건의 checksum, 기준 ZIP, 참조 archive, evidence role을 machine-readable하게 관리.
3. `promotion CLI` inflight/cleanup guard: `.promote-inflight.json`, phase 기록, stale inflight 감지, timeout diagnostic.
4. `public/release/review-full package mode` 분리: `tmp/`, `external-reports/`, `runs/`, `raw/`, `wiki/`, `system/` 포함 정책 명시.
5. 대형 test 파일 분해: `test_release_smoke.py` 1,000라인대, `test_artifact_freshness_runtime.py` 700라인대 파일은 fixture/helper와 behavior suite로 분리.

### P2

1. `semantic_clean_pass`와 `sealed_clean_pass`를 별도 축으로 artifact에 표시.
2. 공통 artifact envelope/writer를 강화해 generated_at/source_tree_fingerprint/input_fingerprints/currentness를 동일 경로로 생성.
3. release finalization 후 canonical artifact 불변 정책 도입.
4. release evidence를 "checked-in summary"가 아니라 "clean workspace에서 재현된 sealed evidence" 중심으로 이동.
5. meta-test 비율이 높아지는 것을 막기 위해 각 meta-test에 대응되는 live invariant 또는 scenario test를 1개 이상 연결한다.

---

## 9. 테스트 구조 개편 후 목표 상태

| 축 | 기대 field | 의미 |
| --- | --- | --- |
| semantic release | `semantic_release_status` | risk/lane semantics 기준 release 가능 여부 |
| sealed release | `sealed_release_status` | batch manifest와 실제 artifact digest가 일치하는지 |
| test coverage | `test_suite_scope` / `represents_full_suite` | 테스트 summary가 무엇을 대표하는지 |
| learning readiness | `learning_readiness_status` / `signoff_revalidation_status` | 학습 blocker가 닫혔는지, waiver인지 |
| accepted risk | `operator_accepted_risk_family_count` / `clean_lane_blocking_accepted_risk_family_count` | accepted risk가 release-blocking인지 |
| package hygiene | `release_package_mode` / `tmp_json_policy_status` | tmp/diagnostic artifact 포함 정책 |
| check write behavior | `check_mode_write_policy` | check 명령이 canonical output을 바꾸지 않는지 |

---

## 10. 검증 실행 내역과 한계

| 확인 | 결과 |
| --- | --- |
| `LLMwiki.zip` SHA-256 계산 | `0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93` |
| ZIP 추출 및 `AGENTS.md`/`AGENTS.local.md` 확인 | 완료 |
| 신규 리뷰 2건과 이전 리뷰 전체 읽기 | 완료 |
| `tests/` AST 인벤토리 | 131개 test file, 874개 test 함수 |
| `Makefile` target 인벤토리 | 133개 target |
| baseline batch manifest digest 대조 | dashboard 1건 mismatch |
| top-level `tmp/*.json` 확인 | `tmp/release-evidence-dashboard.candidate.json` |
| `python -c` vs `python -S -c` 직접 probe | `python -c` timeout / `python -S` pass |
| `make release-closeout-batch-manifest-verify` 별도 실행본 | tmp precondition fail; tmp 제거 후 dashboard mismatch fail. 실행 순서에 따라 writeful check가 추가 mismatch를 만들 수 있음 |
| `make learning-readiness-signoff-revalidation-check` 별도 실행본 | fail. canonical output을 쓰는 구조 확인 |
| 전체 pytest suite | 현재 도구 실행 제한과 startup hook 영향 때문에 끝까지 수행하지 않음. 실제 파일/리뷰 기준으로 full-suite evidence 부족을 판정 |

중요한 한계:

- 사용자는 timeout 제한 없이 끝까지 진행하라고 요청했지만, 현재 실행 도구에는 개별 실행 제한과 Python startup hook 문제가 있다. 따라서 전체 874개 테스트를 "무제한"으로 끝까지 돌렸다고 주장하지 않는다.
- `ruff`, `mypy`는 현재 실행 환경에서 import module로 사용할 수 없었다. 신규 리뷰의 static pass 기록은 그대로 참고하되, 이번 실행에서 재검증했다고 주장하지 않는다.
- 별도 실행본의 check 명령은 canonical report를 쓸 수 있으므로, baseline 판정은 항상 원본 추출본의 정적 digest 대조를 우선했다.

---

## 11. Definition of Done

1. clean extracted release package에서 `tmp/*.json` 없이 `make release-closeout-batch-manifest-verify`가 pass.
2. batch manifest의 10개 required artifact digest가 실제 파일 digest와 모두 일치.
3. `release-evidence-dashboard.json`이 batch manifest 이후 재생성되지 않거나, 재생성 시 batch manifest가 다시 봉인됨.
4. `release-evidence-closeout-self-check.json`이 실제 존재하는 JSON path만 watch하고, missing required path는 fail.
5. `test-execution-summary.json`이 `suite_scope`, `represents_full_suite`, `not_full_suite_reason`을 명시.
6. full-suite 또는 release-builder-full lane 결과가 별도 summary로 남음.
7. `command_runtime` 정상 완료 path가 hermetic subprocess mode에서 안정적으로 pass.
8. check target은 write-free 또는 tmp-only로 동작하고, canonical output 변경은 promote target에서만 발생.
9. accepted-risk vocabulary가 closeout/cohort/dashboard/lane/ledger/batch에서 동일.
10. learning readiness signoff가 due/expired/accepted/metrics-clean 상태별로 release effect를 명확히 표시.
11. operator one-page summary가 semantic clean, sealed clean, full-suite status, accepted learning risk를 분리 표시.
12. external report reference manifest가 비보관 보고서의 기준 ZIP/checkpoint/reference/archive 상태를 검증.

---

## 12. 결론

신규 리뷰 2건은 이전 리뷰의 결론을 대체하기보다 더 정확하게 보강한다. 이전 리뷰의 핵심 P0는 여전히 유효하고, 신규 리뷰를 반영하면 `self-check path validator`, `full-suite evidence scope`, `write-free check mode`, `sealed clean vs semantic clean`이 반드시 추가되어야 한다.

테스트 구조는 "쓸모없는 테스트를 위한 테스트"로 단정할 수 없다. 이 저장소의 테스트 대상은 코드 함수뿐 아니라 release evidence, schema, Makefile gate, public/private boundary, generated artifact contract 자체다. 그러므로 meta-test는 필요하다. 하지만 지금은 meta-test가 실제 release sealing을 충분히 닫지 못하면서 `clean_pass` 주변의 신뢰감을 과하게 만든다.

따라서 다음 작업은 기능 추가가 아니라 **테스트 lane과 release evidence gate의 의미를 다시 봉인하는 구조 개편**이어야 한다. 가장 작은 안전한 순서는 다음과 같다.

1. `tmp/*.json` release package 오염 제거.
2. dashboard 포함 batch manifest 재봉인.
3. self-check watch path validator 추가.
4. `test-execution-summary` suite scope 명시.
5. `command_runtime` hermetic subprocess mode 도입.
6. check target write-free화.
7. release finalization/sealing lane을 별도 최종 gate로 승격.

이 순서가 완료되면 현재의 `clean_pass`는 단순한 semantic pass가 아니라, 실제 package digest와 테스트 evidence까지 닫힌 **sealed clean pass**로 해석할 수 있다.
