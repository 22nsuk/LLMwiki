# LLM Wiki vNext 현재 코드 검토 및 개선 방안 보고서

## 1. 개요

본 보고서는 업로드된 저장소의 **실행 가능한 코드, 테스트, 스키마, 정책, CI/릴리즈 워크플로, 패키징 설정**을 중심으로 현재 상태를 점검하고, 구조적 개선 방안과 **자가개선(self-improvement) 성숙도 평가**를 정리한 문서다.

이번 검토는 단순 스타일 리뷰가 아니라, 다음 관점으로 수행했다.

- **정합성**: 코드·스키마·샘플·테스트가 서로 같은 계약(contract)을 보고 있는가
- **운영성**: CI/릴리즈/공급망 아티팩트가 실제 운영 경로와 일관되게 묶여 있는가
- **변경 안전성**: 복잡한 오케스트레이션 로직이 변경 시 안전하게 유지될 수 있는가
- **자가개선 성숙도**: 관측 → 후보화 → 실행 → 평가 → 승격/보류의 폐루프가 어느 정도까지 구현되어 있는가

---

## 2. 검토 범위와 방법

### 2.1 실제 검토 범위
다음 표면을 우선 대상으로 보았다.

- `ops/scripts/**/*.py`
- `tests/test_*.py`
- `ops/schemas/*.json`
- `ops/policies/*.yaml`
- `pyproject.toml`, `pytest.ini`, `Makefile`
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- `README.md`, `ARCHITECTURE.md`
- 기존 리포트 아티팩트 일부 (`ops/reports/**`)

### 2.2 검토 방식
1. 압축본을 해제해 저장소 구조를 파악했다.
2. Python 코드/테스트/스키마/설정 파일을 구조적으로 스캔했다.
3. 일부 핵심 테스트와 컴파일 검증을 실제로 실행했다.
4. 자가개선 관련 모듈과 현재 문서화된 운영 계약을 교차 검토했다.
5. 확인된 실패를 “추정”이 아니라 **재현 가능한 이슈**로 분리해 정리했다.

### 2.3 한계
- 원본 zip 안의 일부 `raw/web-snapshots/...` 경로는 파일명이 매우 길어 일반 unzip으로 전체 해제가 실패했다.  
  다만 **핵심 검토 대상인 코드/테스트/설정/스키마/워크플로는 별도로 추출해 검토**했다.
- 현재 실행 환경에는 저장소가 기대하는 `ruff`, `mypy` 개발 도구가 설치되어 있지 않아, **정적 분석 타깃 자체는 설정을 검토했지만 로컬에서 동일하게 재실행하지는 못했다.**  
  이는 저장소 결함이라기보다 이번 분석 환경의 제약이다.

---

## 3. 저장소 스냅샷

### 3.1 구조 지표
- `ops/scripts` Python 모듈 수: **111**
- `ops/scripts` 총 LOC: **28,497**
- 함수 수: **1,082**
- 클래스 수: **114**
- `tests/test_*.py` 파일 수: **88**
- 테스트 LOC: **21,222**
- 테스트 케이스 수: **458**
- `ops/schemas/*.json` 수: **43**
- GitHub Actions 워크플로 수: **2**

### 3.2 복잡도 관찰
- 함수 길이 중앙값: **11 LOC**
- 함수 길이 상위 95백분위: **약 71 LOC**
- 즉, 저장소 전체 평균은 비교적 통제되어 있으나, **일부 대형 오케스트레이터에 복잡도가 집중**되어 있다.

#### 큰 모듈 상위 예시
- `ops/scripts/promotion_gate_mechanism_runtime.py` — **902 LOC**
- `ops/scripts/filesystem_runtime.py` — **876 LOC**
- `ops/scripts/auto_improve_runtime.py` — **798 LOC**
- `ops/scripts/observability_artifacts_runtime.py` — **794 LOC**
- `ops/scripts/mechanism_run_workspace_runtime.py` — **714 LOC**
- `ops/scripts/mechanism_run_validation_runtime.py` — **683 LOC**
- `ops/scripts/policy_runtime.py` — **681 LOC**

#### 긴 함수 상위 예시
- `ops/scripts/wiki_stage2_eval.py:evaluate` — **184 LOC**
- `ops/scripts/finalize_run_runtime.py:finalize_run` — **183 LOC**
- `ops/scripts/wiki_eval.py:evaluate` — **179 LOC**
- `ops/scripts/registry_review_candidate_passes_runtime.py:_backlog_refactor_threshold_pass` — **178 LOC**
- `ops/scripts/behavior_delta_runtime.py:build_behavior_delta_report` — **166 LOC**
- `ops/scripts/promotion_gate_mechanism_runtime.py:build_mechanism_promotion_state` — **153 LOC**
- `ops/scripts/auto_improve_runtime.py:_route_scaffold_phase` — **145 LOC**
- `ops/scripts/policy_runtime.py:validate_policy_registry_references` — **145 LOC**

### 3.3 테스트/실행 확인
실제로 다음 검증을 수행했다.

- `python -m compileall -q ops/scripts tests` → **성공**
- `tests/test_path_runtime.py` → **통과**
- `tests/test_filesystem_runtime.py` → **통과**
- `tests/test_import_fallback_contract.py` → **통과**
- `tests/test_release_workflow_static.py` → **통과**
- 위 4개 묶음 결과: **22 passed, 74 subtests passed**
- `tests/test_report_schemas.py` → **1건 실패 확인**
- `tests/test_openvex_draft.py` → **1건 실패 확인**

---

## 4. 총평

이 저장소는 단순한 스크립트 모음이 아니라, 이미 다음 요소를 갖춘 **운영형 메커니즘 저장소**에 가깝다.

- 정책(schema/policy) 기반 검증
- 테스트와 계약 샘플을 통한 회귀 방지
- public/private surface 분리 의식
- 공급망 아티팩트(CycloneDX / SPDX / OpenVEX / in-toto / Sigstore) 정렬 시도
- mechanism review / mutation proposal / promotion gate / observability artifact를 포함한 자가개선 폐루프 설계

즉, 방향은 상당히 좋다.  
다만 현재 시점의 핵심 리스크는 기능 부족보다 **정합성 드리프트와 구조 복잡도 집중**이다.

요약하면 다음과 같다.

> **강점은 “운영 계약을 코드와 아티팩트로 만들려는 의지”이고, 약점은 “그 계약이 모든 경로에서 완전히 동기화되어 있지는 않다”는 점이다.**

---

## 5. 잘된 점

### 5.1 자가개선 루프가 이미 폐루프 형태를 갖추고 있음
`README.md:138-152`를 보면 현재 저장소는 다음 흐름을 명시적으로 운영 계약으로 둔다.

- `mechanism_review`
- `mutation_proposal`
- `scope freeze`
- `subagent routing`
- `executor`
- `repo health`
- `promotion`
- `finalize`
- `queue refresh`

이는 `ops/scripts/auto_improve_runtime.py`, `mechanism_review_runtime.py`, `mutation_proposal_runtime.py`, `promotion_gate_mechanism_runtime.py`, `observability_artifacts_runtime.py` 등과 직접 대응한다.  
즉, 자가개선이 “개념”이 아니라 **실제 런타임 표면**으로 구현돼 있다.

### 5.2 정책·스키마·리포트 아티팩트 중심의 운영
`policy_runtime.py`는 단순 로딩이 아니라 정책 안전 불변식과 레지스트리 참조 정합성까지 검증한다.  
또한 `ops/schemas/*.json`과 `ops/reports/**`가 넓게 배치돼 있어, 결과를 그냥 로그가 아니라 **계약 가능한 데이터 산출물**로 다루려는 방향이 분명하다.

### 5.3 공급망/릴리즈 성숙도가 높음
다음 파일들을 보면 일반적인 내부 툴 저장소보다 공급망 품질 의식이 훨씬 높다.

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `ops/scripts/cyclonedx_sbom.py`
- `ops/scripts/openvex_draft.py`
- `ops/scripts/spdx_sbom.py`
- `ops/scripts/in_toto_statement*.py`
- `ops/scripts/sigstore*.py`

릴리즈 워크플로는 build provenance attestation과 PyPI Trusted Publishing을 염두에 둔 구조다.  
이 방향 자체는 매우 좋다.

### 5.4 공개 표면과 직접 실행 fallback 계약을 테스트로 고정하고 있음
- `ops/direct-script-entrypoints.txt`에 **37개** 엔트리포인트가 관리된다.
- 동일한 수의 fallback 패턴이 실제 스크립트에 존재한다.
- `tests/test_import_fallback_contract.py`가 이를 고정한다.

즉, 다소 번거로운 방식이지만, **의도된 배포/실행 계약을 테스트로 묶어둔 점은 장점**이다.

### 5.5 이미 “리뷰에서 나온 개선점”을 재흡수하는 장치가 있다
`ops/reports/task-improvement-observations/**/improvement-observations.json`가 누적되어 있고,  
예를 들어 `task-20260421-runtime-decomposition`에서는 다음 문제가 이미 내부적으로 인식되어 있다.

- promotion gate runtime 대형화
- 구조 복잡도 예산(Complexity budget) 부재

이것은 저장소가 외부 리뷰 결과를 일회성으로 소비하지 않고, **다음 자동화 backlog로 재편입**하고 있다는 뜻이다.

---

## 6. 핵심 이슈와 개선 방안

## 6.1 [P0] OpenVEX 샘플/스키마/생성기 계약 드리프트

### 확인 내용
다음 테스트가 실제로 실패했다.

- `tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_openvex_draft_validates_and_requires_tooling`

실패 내용은 다음과 같다.

- `artifact_context` 누락
- `metadata.advisory_count` 누락
- `metadata.artifact_set_id` 누락
- `tooling.security_advisories_ref` 누락
- `tooling.spdx_ref` 누락
- `tooling.spdx_emitter_decision` 값 불일치

### 근거 파일
- 샘플: `tests/fixtures/report_schema_samples.json:1409-1432`
- 스키마: `ops/schemas/openvex-draft.schema.json:6-18, 74-80, 113-140`
- 생성기: `ops/scripts/openvex_draft.py:168-195`

### 진단
이 문제는 단순 fixture 누락이 아니다.  
**생성기와 스키마는 이미 한 단계 진화했는데, 샘플 계약이 과거 상태에 남아 있는 상태**다.

특히 샘플은 여전히:

- `spdx_emitter_decision = "deferred-after-cyclonedx-graph-and-openvex-stabilize"`

를 사용하지만, 현재 스키마는:

- `"shared-artifact-model-spdx-enabled"`

만 허용한다.

즉, 공급망 아티팩트 계열에서 **계약의 canonical source가 하나로 정리되지 않았다.**

### 영향
- 스키마 테스트가 깨져 CI 신뢰도를 낮춘다.
- 샘플을 문서/예시로 보는 사람에게 현재 계약이 아닌 과거 계약을 주입한다.
- 향후 OpenVEX/SPDX/CycloneDX 공통 모델 정렬 작업에서 드리프트를 다시 유발한다.

### 권장 조치
1. `tests/fixtures/report_schema_samples.json`의 `openvex_draft` 샘플을 현재 생성기 출력과 완전히 동기화
2. 가능하면 샘플 JSON을 수동 유지하지 말고, **생성기 기반 golden sample 재생성 스크립트**로 관리
3. 공급망 아티팩트군(CycloneDX/OpenVEX/SPDX/in-toto/Sigstore)에 대해  
   **“공통 canonical artifact model → 파생 emitter → schema fixture”** 순서의 단일 갱신 경로를 만든다

### 우선순위 판단
**즉시 수정(P0)**  
이건 설계 취향 문제가 아니라, 이미 테스트가 깨지는 실결함이다.

---

## 6.2 [P0] 기존 CycloneDX BOM 재사용 경로에서 component_count 메타데이터 불일치

### 확인 내용
다음 테스트가 실제로 실패했다.

- `tests/test_openvex_draft.py::OpenVexDraftTests::test_build_openvex_draft_reuses_existing_cyclonedx_bom`

실패 요약:
- 기대값: `report["metadata"]["component_count"] == 1`
- 실제값: `0`

### 근거 파일
- 테스트: `tests/test_openvex_draft.py:63-128`
- 생성기: `ops/scripts/openvex_draft.py:160-167, 188-194`

### 진단
현재 구현은 BOM 재사용 여부와 관계없이:

```python
component_count = len(model.get("components", []))
```

를 사용한다.  
그런데 같은 함수 안에서 `dependency_edge_count`는 BOM 재사용 경로를 반영한다.

즉, **동일 함수 내부에서 메타데이터의 출처가 서로 다르게 움직인다.**

- `dependency_edge_count`는 재사용 BOM 기준
- `component_count`는 artifact model 기준

이 상태는 생성 결과가 “부분적으로만 reuse-aware” 하다는 뜻이다.

### 영향
- BOM 재사용 fast path의 메타데이터 신뢰도가 떨어진다.
- downstream에서 component_count를 health signal로 쓰면 잘못된 해석이 생긴다.
- “shared artifact model을 단일 진실 원천으로 쓰겠다”는 설계 메시지와 어긋난다.

### 권장 조치
둘 중 하나로 명확히 정해야 한다.

#### 방안 A: 재사용 BOM이 있으면 모든 요약 메타데이터를 BOM 기준으로 통일
- `component_count`
- `dependency_edge_count`
- 필요하면 기타 개수성 메타데이터도 같은 기준 적용

#### 방안 B: 메타데이터를 항상 artifact model 기준으로 통일
- 대신 `tooling` 또는 `notes`에 “reused existing BOM” 여부를 별도로 기록

현재 테스트 의도상으로는 **방안 A가 더 자연스럽다.**

### 우선순위 판단
**즉시 수정(P0)**  
이 역시 이미 테스트가 깨지는 실결함이다.

---

## 6.3 [P1] 오케스트레이터 대형화와 복잡도 집중

### 확인 내용
대형 모듈이 몇 군데에 집중돼 있다.

- `promotion_gate_mechanism_runtime.py` — 902 LOC
- `auto_improve_runtime.py` — 798 LOC
- `mechanism_run_workspace_runtime.py` — 714 LOC
- `policy_runtime.py` — 681 LOC
- `observability_artifacts_runtime.py` — 794 LOC

또한 내부에서도 120~180 LOC 수준의 긴 함수가 여러 개 확인된다.

### 진단
저장소 전체 평균은 괜찮다.  
문제는 **핵심 결정 로직이 소수의 파일과 함수에 과밀하게 몰려 있다는 점**이다.

이 패턴은 다음 문제를 만든다.

- 리뷰 난이도 상승
- 분기 누락 위험 증가
- 테스트 작성 단위가 커짐
- 리팩터링이 “파일 전체 건드리기”가 되기 쉬움
- 자가개선 루프가 스스로 자신의 핵심을 안전하게 다루기 어려워짐

특히 이 저장소는 자가개선과 승격 게이트를 가진 시스템이므로,  
**오케스트레이터는 똑똑해야 하기보다 얇고 예측 가능해야 한다.**

### 참고 사항
이미 `ops/runtime-decomposition-plan.md`가 존재하고,  
`task-20260421-runtime-decomposition`에서도 같은 문제가 backlog로 잡혀 있다.  
즉, 문제 인식은 되어 있으나 아직 해결이 끝난 상태는 아니다.

### 권장 조치
1. **상태 전이(state transition) 기준으로 분해**
   - 예: `promotion_gate_mechanism_runtime.py`
     - state loading
     - rule evaluation
     - evidence aggregation
     - report assembly
     - finalize/persist
2. 함수 단위 budget 설정
   - 예: 80 LOC 초과 함수는 신규 추가 금지
   - 예: touched file의 함수 길이/branch count/decision count를 리포트화
3. `ops/reports/complexity-budget.json` 같은 **구조 복잡도 리포트** 신설
4. `make ruff-strict-preview`에 들어가는 helper runtime 범위를 점진 확대

### 우선순위 판단
**높음(P1)**  
지금 당장 서비스가 깨지는 문제는 아니지만, 장기적으로 가장 비싼 기술부채다.

---

## 6.4 [P1] 정적 분석 강도가 아직 제한적임

### 확인 내용
`pyproject.toml` 기준:

- Ruff lint 선택: `["E4", "E7", "E9", "F"]`
- mypy:
  - `follow_imports = "skip"`
  - `ignore_missing_imports = true`
  - `warn_unused_ignores = true`

또한 `Makefile`의 `ruff-strict-preview`는 존재하지만, 적용 대상은 일부 helper runtime 파일에 한정돼 있다.

### 진단
현재 설정은 “개발 속도를 해치지 않는 최소 안전선”으로는 적절하다.  
하지만 이 저장소는 이미 schema/gate/promotion까지 다루는 운영형 코드다.  
그에 비해 정적 분석 강도는 아직 **보수적 초기값**에 가깝다.

### 권장 조치
1. Ruff 규칙 확대를 일괄 적용하지 말고 **폴더/파일 allowlist 방식**으로 단계 확장
2. mypy도 전체 일괄 강화보다, 변경이 잦은 핵심 runtime부터
   - `disallow_untyped_defs`
   - `no_implicit_optional`
   - `warn_return_any`
   등을 선택 적용
3. strict-preview 통과 파일은 PR마다 증가만 허용하는 식으로 관리

### 우선순위 판단
**높음(P1)**  
특히 자가개선 루프가 코드 변경을 자동으로 제안/적용하는 구조라면,  
정적 분석 강도는 사람이 보는 코드 리뷰를 보완하는 핵심 안전장치다.

---

## 6.5 [P1] CI가 Linux 중심이라 OS 분기 리스크가 남아 있음

### 확인 내용
`.github/workflows/ci.yml`은 `ubuntu-latest`에서만 실행된다.  
그런데 `ops/scripts/command_runtime.py:22-45, 59-68`은 `os.name == "nt"` 분기를 포함해 Windows 처리를 별도로 두고 있다.

### 진단
즉, 코드 자체는 cross-platform을 의식하고 있지만,  
**CI는 그 의도를 검증하지 않는다.**

이 경우 가장 흔한 문제는:
- Windows timeout/termination 처리 드리프트
- path/encoding 차이
- process group 처리 차이

### 권장 조치
1. 최소한의 `windows-latest` smoke lane 추가
   - 전 테스트가 아니라 `compileall + 핵심 계약 테스트 + command_runtime 관련 테스트`
2. 여유가 되면 `macos-latest` smoke lane도 추가
3. full matrix가 부담되면 fast tier만 멀티 OS로 운영

### 우선순위 판단
**높음(P1)**  
이미 코드가 OS 분기를 가진 이상, 검증도 최소한 따라가야 한다.

---

## 6.6 [P2] 직접 실행 fallback 래퍼가 많아 유지보수 비용이 큼

### 확인 내용
- `ops/direct-script-entrypoints.txt` 엔트리: **37개**
- 동일 수의 `if __package__ in (None, "")` fallback 존재

### 진단
현재 방식은 계약이 분명하고 테스트도 있다.  
하지만 파일 수가 계속 늘면 다음 비용이 누적된다.

- import/fallback boilerplate 중복
- public export와 package install 시 표면 관리 부담
- CLI 진입점 수정 시 동기화 포인트 증가

### 권장 조치
1. 신규 스크립트부터는 가능하면 `python -m ops.scripts.<name>` 또는 `[project.scripts]` entry point 우선
2. 기존 fallback은 한 번에 제거하지 말고 **allowlist 축소형 migration** 진행
3. `direct-script-entrypoints.txt`는 “예외 허용 목록”으로 성격을 바꾸는 것이 좋다

### 우선순위 판단
**중간(P2)**  
급한 문제는 아니지만, 장기 운영 비용을 줄이는 데 의미가 있다.

---

## 6.7 [P2] 일부 broad exception 경로의 관측성이 아쉽다

### 확인 내용
`except Exception` 사용은 총 15곳으로 많지는 않다.  
대부분 CLI boundary에서 방어적으로 쓰이고 있어 큰 문제는 아니다.  
다만 다음 예시는 관측성 측면에서 보완 여지가 있다.

- `ops/scripts/raw_markdown_runtime.py:134-137`
  - YAML 파싱 실패를 전부 삼키고 frontmatter 없음으로 처리
- `ops/scripts/filesystem_runtime.py:63-75`
  - cleanup 용 broad exception 후 재전파

### 진단
두 번째는 cleanup 경로라 비교적 타당하다.  
하지만 첫 번째는 파싱 에러와 “실제로 frontmatter가 없는 문서”를 같은 결과로 만들 수 있다.

### 권장 조치
- `split_frontmatter()`는 `diagnostics` 또는 debug hook에서라도 parse failure reason을 남기게 개선
- 최소한 테스트에서 malformed frontmatter 처리 의도를 더 명확히 고정

### 우선순위 판단
**중간(P2)**  
즉시 장애보다, 디버깅 비용 절감 측면에서 의미가 있다.

---

## 6.8 [P2] 일반적인 Python line/branch coverage gate는 저장소 표면에서 약하게 보임

### 확인 내용
저장소에는 `wiki_eval_coverage`, `coverage_gap_count` 등 **도메인별 coverage 개념**은 풍부하다.  
그러나 `pytest-cov`나 line/branch coverage 임계치를 `Makefile`, `pytest.ini`, `pyproject.toml`에서 강하게 운영하는 흔적은 뚜렷하지 않았다.

### 진단
현재 저장소는 “도메인 의미 coverage”에는 강하다.  
하지만 **전통적인 코드 coverage governance**는 상대적으로 약하다.

둘은 대체 관계가 아니다.

- 도메인 coverage: 이 변경이 의미상 어디를 건드렸는지
- 코드 coverage: 실제 분기/라인이 얼마나 검증됐는지

### 권장 조치
- 전체 하드게이트가 부담되면 우선 핵심 runtime 대상에 한해
  - changed-files coverage
  - branch coverage floor
  - PR 감소 방지(non-regression) 방식
  를 도입

### 우선순위 판단
**중간(P2)**  
정적 분석 강화와 함께 병행하면 효과가 좋다.

---

## 7. 자가개선 성숙도 평가

## 7.1 평가 결과
### 현재 수준: **5단계 기준 3.7 / 5.0**
판정 표현으로는 다음이 적절하다.

> **정책 기반 준자율 폐루프 단계(상)**  
> 또는  
> **관리형 self-improvement 시스템의 초기 성숙 단계**

### 7.2 왜 이 점수인가

#### 강한 근거
1. **폐루프 구조가 실제 코드로 존재**
   - `auto_improve_runtime.py`
   - `mechanism_review_runtime.py`
   - `mutation_proposal_runtime.py`
   - `promotion_gate_mechanism_runtime.py`
   - `observability_artifacts_runtime.py`

2. **실행 결과가 아티팩트로 남음**
   - session report
   - routing provenance aggregate
   - promotion trends
   - outcome metrics
   - behavior delta
   - run telemetry
   - artifact fingerprint

3. **허용 범위와 apply root가 정책화돼 있음**
   - README에 명시
   - policy/runtime validation과 연결

4. **자체 리뷰 결과를 improvement observation으로 재흡수**
   - `ops/reports/task-improvement-observations/**`

즉, 이 저장소는 이미  
“문제를 발견하면 로그만 남기는 시스템”이 아니라  
**문제 → 후보 → 실험 → 평가 → 추세 관측**의 구조를 갖고 있다.

### 7.3 아직 4.5~5.0 단계가 아닌 이유

#### (1) audit-only 신호가 아직 핵심 gate에 완전히 승격되지 않음
`README.md:151`과 `README.md:181`을 보면 다음 신호들이 여전히 audit-only다.

- `outcome-metrics.json`
- outcome metrics calibration

즉, 관측은 하지만 **핵심 의사결정 가중치로 완전 승격되지는 않았다.**

#### (2) 공급망 계약 드리프트가 실제로 발생함
이번 검토에서 OpenVEX 샘플/스키마/생성기 정합성 깨짐이 확인됐다.  
이는 “자가개선 시스템이 산출물 가족 전체를 항상 동기화한다”는 수준에는 아직 못 갔다는 뜻이다.

#### (3) 오케스트레이터 복잡도가 아직 높음
자가개선 시스템은 스스로를 자주 만질수록, 핵심 orchestration이 얇고 모듈적이어야 한다.  
현재는 그 방향으로 가는 중이지만, 아직 완성 단계는 아니다.

#### (4) 구조 복잡도 budget이 아직 gate로 승격되지 않음
`task-20260421-runtime-decomposition`도 같은 문제를 지적한다.  
즉, “복잡도가 늘어나는지”를 자동으로 감시하는 메커니즘이 아직 약하다.

---

## 8. 자가개선 성숙도 보완 방안

## 8.1 단기 보완 (1~2주)
1. **OpenVEX 계약 드리프트 수정**
   - 샘플 fixture 갱신
   - 재사용 BOM 경로 component_count 수정
2. **공급망 아티팩트군 golden contract 재생성 경로 도입**
   - 수동 fixture 관리 축소
3. **promotion gate / auto improve 핵심 함수에 길이 예산 도입**
   - 신규 100+ LOC 함수 금지
4. **strict-preview 적용 대상 확대**
   - 새로 분해된 helper 파일부터 우선 적용

## 8.2 중기 보완 (2~6주)
1. **complexity-budget report 신설**
   - touched file별 함수 수, 함수 길이 상위값, decision density 등 기록
2. **OS smoke matrix 추가**
   - Windows fast lane
3. **coverage governance 추가**
   - changed-files 중심 branch/line coverage non-regression
4. **direct-script fallback 축소 계획 수립**
   - 신규 스크립트는 console script 또는 `python -m` 우선

## 8.3 장기 보완 (6주 이상)
1. **audit-only outcome metrics 일부를 실제 gate 신호로 승격**
   - 예: 반복 HOLD/DISCARD 상승 시 candidate priority 자동 조정
2. **자가개선 루프의 “복잡도 증가 억제”를 자동 정책으로 편입**
3. **공급망 아티팩트군 전체에 canonical generator pipeline 일원화**
4. **자가개선 성과를 정량화하는 장기 KPI 연결**
   - rework 감소
   - defect escape proxy 감소
   - 평균 promotion lead time 안정화
   - rollback rehearsal signal 추세 개선

---

## 9. 우선순위별 실행 로드맵

## P0 — 즉시
- OpenVEX fixture/schema/generator 정합성 복구
- BOM 재사용 경로 `component_count` 계산 기준 통일
- 관련 테스트를 고정 회귀 테스트로 유지

## P1 — 다음 스프린트
- promotion/auto-improve/policy runtime 분해
- strict-preview 및 mypy 강화 범위 확대
- Windows smoke CI 추가

## P2 — 이후
- direct-script fallback 축소
- malformed frontmatter observability 개선
- line/branch coverage governance 추가

---

## 10. 결론

이 저장소는 이미 **“자기 점검과 자기 수정”을 코드/정책/리포트 아티팩트로 운영하는 상당히 진화한 시스템**이다.  
따라서 지금 필요한 것은 새 기능의 대량 추가가 아니라, 다음 세 가지의 정교화다.

1. **계약 동기화**
2. **오케스트레이터 분해**
3. **관측 신호의 실제 게이트 승격**

가장 중요한 메시지는 다음 한 문장으로 정리된다.

> **현재 자가개선 체계는 존재하고 작동도 하지만, 아직 “안전하게 스스로를 더 빠르게 개선할 수 있는 단계”로 완전히 올라서지는 않았다.**

즉, 방향성은 맞고 기반도 좋다.  
지금은 **정합성 드리프트와 구조 복잡도**를 먼저 줄여야 다음 단계로 올라간다.

---

## 11. 부록: 핵심 근거 파일

### 확인된 실패와 직접 관련된 파일
- `tests/test_report_schemas.py:363-366`
- `tests/test_openvex_draft.py:63-128`
- `tests/fixtures/report_schema_samples.json:1409-1432`
- `ops/scripts/openvex_draft.py:160-195`
- `ops/schemas/openvex-draft.schema.json:6-18, 74-80, 113-140`

### 자가개선 성숙도 판단 근거
- `README.md:138-152`
- `README.md:171-181`
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/mechanism_review_runtime.py`
- `ops/scripts/mutation_proposal_runtime.py`
- `ops/scripts/promotion_gate_mechanism_runtime.py`
- `ops/scripts/observability_artifacts_runtime.py`
- `ops/reports/task-improvement-observations/task-20260421-runtime-decomposition/improvement-observations.json`
- `ops/runtime-decomposition-plan.md`

### 구조 복잡도 판단 근거
- `ops/scripts/promotion_gate_mechanism_runtime.py`
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/mechanism_run_workspace_runtime.py`
- `ops/scripts/policy_runtime.py`
- `ops/scripts/observability_artifacts_runtime.py`

### 설정/CI 판단 근거
- `pyproject.toml`
- `Makefile`
- `pytest.ini`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
