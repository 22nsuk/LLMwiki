# LLM Wiki vNext 코드베이스 상세 검토 보고서

- 작성일: 2026-04-20
- 대상: `LLM Wiki vNext(12).zip`
- 산출물 형식: Markdown
- 작성 언어: 한국어

## 1. 검토 범위와 방법

이번 검토는 저장소의 **소스 코드, 테스트, 설정, CI/CD 워크플로, 생성된 운영 리포트, 문서**를 함께 보는 방식으로 진행했다.  

### 실제로 확인한 항목
1. 루트 문서: `README.md`, `ARCHITECTURE.md`, `Makefile`, `pyproject.toml`, `pytest.ini`
2. 핵심 패키지: `ops/scripts/*.py`
3. 테스트 표면: `tests/*.py`
4. CI/CD: `.github/workflows/ci.yml`, `.github/workflows/release.yml`
5. 운영 산출물: `ops/reports/*.json`
6. 구조/복잡도: AST 기반 정적 메트릭, 파일/함수 길이, 예외 처리 패턴, 래퍼 반복 패턴
7. 실행 검증:
   - `python -m compileall -q ops tests tools` 성공
   - 대표 테스트 7건 직접 실행 성공
   - 기존 리포트 중 lint/eval/supply-chain/SBOM readiness 결과 확인

### 한계와 정직한 주석
- 전체 fast/full suite 전체 완주 여부까지 이번 세션에서 끝까지 재검증하지는 않았다.
- 대신 **대표 회귀 테스트, 스키마 계약 테스트, 공급망 게이트 테스트, 컴파일 검증, 워크플로 정의, 기존 생성 리포트**를 함께 대조했다.
- 따라서 이 보고서는 “표면만 본 감상문”이 아니라, **구조·품질 게이트·자가개선 메커니즘까지 포함한 실전형 코드 리뷰**에 가깝다.

---

## 2. 한눈에 보는 결론

### 총평
이 저장소는 일반적인 단일 애플리케이션 저장소가 아니라,  
**지식 코퍼스 유지 런타임 + 평가/승격 게이트 + 메커니즘 개선 루프 + 공급망 검증 체계**를 한곳에 모은 운영 저장소다.

그 기준으로 보면 완성도는 높다.  
특히 다음이 강하다.

- **정책 중심(policy-driven) 구조**
- **생성 산출물과 스키마 계약의 명시화**
- **테스트 비중이 높은 편**
- **자가 개선(auto-improve) 루프가 실제 운영 개체로 존재**
- **SBOM / OpenVEX / in-toto / Sigstore / provenance 등 공급망 표면을 이미 다룸**
- **public/private export 경계 의식이 분명함**

다만, 지금 단계의 가장 큰 리스크는 “망가지는 코드”라기보다 다음 두 가지다.

1. **복잡도가 누적되는 핵심 런타임 모듈의 유지보수 비용**
2. **실행 환경 재현성의 암묵적 전제(PYTHONPATH, pytest plugin autoload, 로컬/CI 차이)**

즉, 현재의 문제는 기능 부재보다 **운영 복잡도 관리** 쪽이다.

### 종합 평가
- 아키텍처 방향성: **우수**
- 테스트/계약 관리: **우수**
- 공급망/릴리스 거버넌스: **우수**
- 코드 단위 유지보수성: **보통 이상이나 핵심 모듈은 경고 수준**
- 실행 재현성/로컬 개발 편의성: **보완 필요**
- 자가 개선 성숙도: **높음(단, 아직은 규칙 기반 최적화 중심)**

---

## 3. 정량 요약

## 3-1. 구조 메트릭

| 항목 | 값 |
|---|---:|
| 소스 Python 파일 수 | 109 |
| 테스트/지원 Python 파일 수(`tests/`) | 93 |
| `pytest` 수집 대상 테스트 파일 수(`test_*.py`) | 88 |
| 소스 LOC | 28,665 |
| 소스 유효 코드 LOC(주석/공백 제외) | 25,247 |
| 테스트 LOC | 21,196 |
| 테스트 유효 코드 LOC | 18,800 |
| 테스트 LOC / 소스 LOC 비율 | 0.74 |

이 비율은 **테스트가 형식적으로만 존재하는 저장소가 아니라는 신호**다.  
특히 이 저장소는 단순한 API 서버가 아니라 운영 런타임/리포트 생성기/스키마 검증기 성격이 강하므로, 이 정도 테스트 밀도는 긍정적이다.

## 3-2. 대형 파일 상위 예시

| 파일 | LOC | 함수 수 | 최장 함수 길이 | 최대 복잡도(근사) |
|---|---:|---:|---:|---:|
| `ops/scripts/mechanism_review_candidate_runtime.py` | 1314 | 41 | 148 | 22 |
| `ops/scripts/auto_improve_runtime.py` | 946 | 27 | 145 | 11 |
| `ops/scripts/promotion_gate_mechanism_runtime.py` | 902 | 36 | 153 | 18 |
| `ops/scripts/filesystem_runtime.py` | 876 | 39 | 82 | 12 |
| `ops/scripts/observability_artifacts_runtime.py` | 794 | 33 | 101 | 24 |
| `ops/scripts/mechanism_run_workspace_runtime.py` | 714 | 32 | 123 | 10 |

## 3-3. 복잡도가 높은 함수 예시

| 파일 | 함수 | 길이 | 복잡도(근사) |
|---|---|---:|---:|
| `ops/scripts/wiki_doc_audit_runtime.py` | `external_report_reference_issues` | 125 | 35 |
| `ops/scripts/planning_gate_validate_runtime.py` | `validate_run_dir` | 124 | 30 |
| `ops/scripts/raw_registry_runtime.py` | `enrich_registry_entries_with_inventory` | 78 | 29 |
| `ops/scripts/registry_review_candidate_passes_runtime.py` | `_backlog_refactor_threshold_pass` | 178 | 28 |
| `ops/scripts/wiki_stage2_eval.py` | `evaluate` | 184 | 28 |

## 3-4. 반복 패턴 관찰

- `if __package__ in (None, ""):` 형태의 **직접 실행 fallback 래퍼**가 다수(약 37개 모듈) 존재
- `except Exception` 계열의 **넓은 예외 경계**가 일부 CLI/런타임 경계에 존재
- 핵심 orchestration 모듈이 800~1300 LOC까지 비대화되어 있음

이 패턴들은 치명적 버그를 뜻하진 않지만, **장기 유지보수 비용과 회귀 리스크를 올리는 신호**다.

---

## 4. 실행 검증 결과

### 4-1. 컴파일 검증
- `python -m compileall -q ops tests tools` 성공

즉, 최소한의 문법/모듈 해석 레벨에서 즉시 깨지는 상태는 아니었다.

### 4-2. 대표 테스트 직접 검증
아래 테스트는 이번 리뷰 중 직접 실행해 통과를 확인했다.

- `tests/test_auto_improve_runtime.py::AutoImproveRuntimeTests::test_run_auto_improve_session_writes_successful_session_report`
- `tests/test_mechanism_review_candidate_runtime.py::MechanismReviewCandidateRuntimeTest::test_build_candidates_uses_injected_loader_and_reuses_run_session_cache`
- `tests/test_planning_gate_validate_runtime.py::PlanningGateValidateRuntimeTest::test_validate_run_dir_uses_injected_runtime_context_timestamp`
- `tests/test_filesystem_runtime.py::FilesystemRuntimeTests::test_apply_manifest_transaction_rolls_back_partial_workspace_apply`
- `tests/test_policy_runtime.py::PolicyRuntimeTest::test_live_policy_loads_as_single_source_of_truth`
- `tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_supply_chain_provenance_validates_and_requires_inputs`
- `tests/test_supply_chain_gate_runtime.py::SupplyChainGateRuntimeTests::test_gate_passes_when_all_checks_are_satisfied`

### 4-3. 기존 운영 리포트 상태
저장소 내부 `ops/reports/` 기준으로 다음과 같은 신호를 확인했다.

- `lint-initial-2026-04-12.json`: `status = pass`
- `eval-initial-2026-04-12.json`: `149/149`
- `supply-chain-gate-report.json`: `status = pass`
- `sbom-readiness-gate-report.json`: `status = pass`
- `outcome-metrics.json`: 최근 시도 집계 존재

이 정보는 “지금 코드가 잘 작성되었다”는 증명은 아니지만,  
**운영자가 품질 상태를 기계적으로 추적하고 있다는 증거**로는 충분하다.

---

## 5. 잘한 점

## 5-1. 자가 개선 루프가 개념이 아니라 코드로 존재한다
이 저장소의 차별점은 `auto_improve_*`, `mechanism_review_*`, `mutation_proposal*`, `promotion_gate*`, `outcome_metrics*` 계열이 실제로 존재한다는 점이다.

즉, “좋아질 것이다”가 아니라 다음이 이미 코드화되어 있다.

- 후보 메커니즘 리뷰
- 실험 대상 제안 생성
- 실행/평가
- 실패 taxonomy 기록
- quarantine / hold / discard / promote 처리
- 세션/런 단위 telemetry 및 artifact 축적

이 정도면 **자가 개선 프레임을 운영 artifact 수준으로 구현한 저장소**다.

## 5-2. 품질 게이트가 다층적이다
이 저장소는 단일 `pytest`만 돌리는 구조가 아니다.

- `ruff`
- `mypy`
- `raw_registry_preflight`
- `wiki_lint`
- `wiki_eval`
- `wiki_stage2_eval`
- `planning_gate_validate`
- warning budget
- release smoke
- supply-chain gate
- SBOM readiness gate

즉, **코드 품질 / 콘텐츠 품질 / 산출물 품질 / 릴리스 품질 / 공급망 품질**을 분리해 관리한다.  
운영 저장소로서는 매우 좋은 방향이다.

## 5-3. 파일시스템/배포 안전장치가 생각보다 강하다
`filesystem_runtime.py`와 관련 테스트를 보면 다음 안전 개념이 분명하다.

- 허용 루트 밖 경로 차단
- symlink 세그먼트 차단
- shadow apply
- rollback rehearsal
- partial apply 롤백

이건 단순한 “파일 쓰기 유틸”이 아니라 **변경 적용을 transaction처럼 다루려는 설계**다.  
메커니즘 self-modification을 다루는 저장소에서는 매우 중요한 강점이다.

## 5-4. 공급망 표면이 이미 성숙한 편이다
`.github/workflows/release.yml`과 `ops/scripts/*sbom*`, `*openvex*`, `*in_toto*`, `*sigstore*` 계열을 보면, 이 저장소는 릴리스 신뢰를 단순 업로드가 아니라 **증명 가능한 artifact 체인**으로 다루려는 방향을 채택하고 있다.

운영 코드 저장소가 이 단계까지 간 경우는 흔치 않다.

## 5-5. public/private 경계를 설계 차원에서 다룬다
이 저장소는 `export_public_repo`, public check, public mirror contract를 별도 운영한다.  
이는 내부/외부 surface를 분리해 다루는 성숙한 설계다.

---

## 6. 핵심 개선 포인트

여기부터는 “좋은 점”보다 더 중요한 **실제 보완 과제**다.

## 6-1. 최우선: 대형 orchestration 모듈 분해
### 관찰
다음 모듈들은 기능이 지나치게 많이 모여 있다.

- `ops/scripts/mechanism_review_candidate_runtime.py`
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/promotion_gate_mechanism_runtime.py`
- `ops/scripts/filesystem_runtime.py`
- `ops/scripts/observability_artifacts_runtime.py`

### 문제
이 상태가 지속되면 다음이 생긴다.

- 함수 하나 수정이 다른 경로에 미치는 영향 범위를 빠르게 파악하기 어려움
- 신규 참여자 온보딩 비용 상승
- 회귀 테스트가 있어도 “왜 깨졌는지” 추론 비용이 큼
- 자가 개선 루프가 더 복잡해질수록 오케스트레이터가 병목이 됨

### 권고
대형 파일을 **기능 축이 아니라 상태 전이 축**으로 분해하는 것이 좋다.

예시:
- `auto_improve_runtime.py`
  - `session_start.py`
  - `proposal_selection.py`
  - `routing_scaffold.py`
  - `execution_evaluation.py`
  - `iteration_persistence.py`
  - `session_finalize.py`

- `mechanism_review_candidate_runtime.py`
  - `candidate_rules.py`
  - `session_calibration.py`
  - `outcome_metrics_calibration.py`
  - `candidate_identity.py`
  - `report_builders.py`

### 기대 효과
- 변경 범위 축소
- 테스트 격리 용이
- self-improve loop 자체에 대한 재귀적 유지보수성 향상

---

## 6-2. 최우선: 실행 환경 재현성 하드닝
### 관찰
이번 검토에서 초기에 `pytest`가 `ops` 패키지를 찾지 못해 실패했다.  
`PYTHONPATH=.`를 주면 정상 동작했고, 대표 테스트도 통과했다.

### 해석
즉, 저장소는 실질적으로 다음 둘 중 하나를 전제로 한다.

1. editable install(`pip install -e .`)
2. 저장소 루트 기준의 import path 보정

CI에서는 `python -m pip install -e .`를 수행하므로 문제 없지만, 로컬/임시 환경에서는 이 전제가 불명확할 수 있다.

### 추가 관찰
현재 `pytest`는 설치된 서드파티 plugin을 자동 로드한다. 이번 검토 환경에서도 plugin autoload가 수집/실행 경험에 영향을 주었다.

### 권고
1. **로컬 개발 표준 진입점 단일화**
   - `make test`와 `make check`만 공식 진입점으로 강하게 유도
   - README에 “직접 `pytest` 호출보다 먼저 `make dev-install` 또는 `pip install -e .`”를 더 강하게 명시

2. **pytest plugin autoload 통제**
   - CI/공식 재현 경로에서 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 또는 `--disable-plugin-autoload` 적용 검토
   - 필요한 plugin만 명시적으로 로드

3. **개발 환경 래퍼 추가**
   - `tox` 또는 `nox` 같은 세션 러너를 붙여 “환경 생성 + 테스트 명령”을 한 번에 고정하는 것도 유효

### 기대 효과
- “내 환경에서는 되는데 다른 환경에서는 이상함” 감소
- 외부 plugin 간섭 최소화
- 자가 개선 루프의 검증 결과 신뢰도 상승

---

## 6-3. 상위 우선순위: 정적 품질 게이트를 한 단계 더 공격적으로
### 관찰
현재 `ruff` 설정은 `E4`, `E7`, `E9`, `F` 위주로 매우 보수적이다.  
즉, **문법 오류/명백한 오류 중심**이고, 스타일/단순화/잠재 버그/현대화 규칙은 넓게 잡지 않는다.

`mypy` 역시 `follow_imports = "skip"`, `ignore_missing_imports = true`로 완전 엄격 모드는 아니다.

### 문제
지금 구조는 “깨진 코드 방지”에는 충분할 수 있지만,  
**복잡도 누적 억제**와 **설계 부채 조기 탐지**에는 약하다.

### 권고
다음 순서로 점진 확대를 권한다.

1. `ruff`에 `B`(bugbear), `SIM`, `UP`, `I` 일부 도입
2. 신규/변경 파일만 stricter profile 적용
3. 핵심 orchestration 모듈부터 `mypy --strict`에 가까운 별도 gate 시범 운영
4. 복잡도 budget(예: 함수 길이/분기 수) 리포트 자동화

### 기대 효과
- 유지보수성 저하를 사후가 아니라 사전 차단
- 자가 개선 코드가 스스로 복잡도를 폭증시키는 현상 억제

---

## 6-4. 상위 우선순위: CLI bootstrap / 예외 경계 중복 제거
### 관찰
`if __package__ in (None, ""):` 형태의 직접 실행 fallback이 다수 모듈에 반복된다.  
또한 일부 CLI 경계에서 `except Exception as exc` 패턴이 반복된다.

### 문제
반복은 곧 drift 포인트다.

- 어떤 모듈은 메시지가 다르고
- 어떤 모듈은 exit code 처리 방식이 다르고
- 어떤 모듈은 import bootstrap이 살짝 다를 가능성이 생긴다

### 권고
공통 CLI 엔트리 추상화를 두는 것이 좋다.

예:
- `cli_bootstrap.py`
- `cli_boundary.py`
- `run_cli(main_func, *, usage_error_cls, fatal_error_cls, direct_script_support=True)`

### 기대 효과
- 예외 처리 정책 일관화
- direct-script fallback drift 제거
- 신규 스크립트 추가 속도 향상

---

## 6-5. 상위 우선순위: 자가 개선 루프의 “학습”을 더 계량화
### 현재 상태
자가 개선 루프는 이미 존재한다. 하지만 현재의 핵심은 **정책/규칙/게이트 기반의 운영 최적화**에 가깝다.

즉, 강점은 다음이다.
- 후보 선정
- 실험 실행
- 승격/보류/폐기
- 세션/런 이력 축적

하지만 아직 아래는 상대적으로 약하다.
- 장기적 개선률의 정교한 계량
- proposal ranking의 예측 정확도 측정
- 실제 운영 성과와 후보 우선순위 간 상관성 검증
- “어떤 규칙이 정말 효과 있었는가”의 교차 run 분석

### 권고
1. **proposal ranking 품질 지표 추가**
   - top-N proposal hit rate
   - promoted/discarded precision
   - false-positive candidate family 비중

2. **장기 성과 추세 리포트 추가**
   - 7/30/90일 moving window
   - family별 promotion yield
   - rollback/hold 유발 family

3. **실험 원인-결과 연결 강화**
   - “어떤 mutation이 어떤 지표를 얼마나 바꿨는지”를 표준화된 delta artifact로 축적

4. **shadow mode / canary scoring 확대**
   - 실제 변경 반영 전, candidate ranking만 shadow로 운영해 우선순위 엔진 품질 측정

### 기대 효과
- 자가 개선이 “운영 자동화”에서 “측정 가능한 최적화”로 이동
- Level 5에 가까운 최적화 루프 기반 확보

---

## 6-6. 중간 우선순위: 문서와 코드의 canonical source를 더 엄격히 정렬
### 관찰
README, ARCHITECTURE, 정책 파일, 운영 리포트가 전반적으로 잘 정리되어 있다.  
다만, 이런 저장소는 문서가 많아질수록 **설명 문서와 실제 게이트 동작이 미세하게 어긋날 위험**이 있다.

### 권고
- 핵심 운영 규칙은 가능한 한 **policy/schema/report**를 canonical source로 두고
- README/ARCHITECTURE는 이를 요약하는 방향으로 유지
- 문서가 정책을 복제하지 않도록 링크/참조 중심으로 얇게 유지

---

## 6-7. 중간 우선순위: 메커니즘 복잡도 budget을 first-class artifact로
이 저장소는 이미 outcome metrics, supply-chain artifacts, schema reports가 강하다.  
그렇다면 다음 단계는 **코드 구조 복잡도 자체를 운영 artifact로 올리는 것**이다.

예:
- 파일별 LOC 상한
- 함수 길이 상한
- 분기 복잡도 상한
- “신규 변경이 total structural metrics를 악화시키는지”를 정식 게이트로 반영

특히 이 저장소는 자가 개선이 핵심이므로,  
**개선 메커니즘이 스스로를 복잡하게 만드는 현상**을 제어해야 한다.

---

## 7. 자가 개선 성숙도 평가

## 7-1. 결론
이 저장소의 자가 개선 성숙도는 **상당히 높은 편**이다.  
다만 “완전 자율 학습형”이라기보다는 **정책-기반 관리형 최적화(managed optimization)**에 가깝다.

### 제안 평가
- **성숙도 레벨: 4 / 5**
- 해석: **Managed 단계가 매우 잘 잡혀 있고, Optimizing 단계의 일부 특성을 이미 보유**
- 한 줄 평:  
  **“자가 개선 루프는 이미 제품화되어 있으나, 아직은 규칙 기반 운영 최적화가 중심이며, 성능 학습/우선순위 학습의 계량화가 더 필요하다.”**

## 7-2. 왜 높은 편인가
다음 요소가 이미 존재한다.

1. **후보 발굴**
   - mechanism review candidate
   - mutation proposal queue

2. **실험 실행 체계**
   - scaffold / execution / evaluation / finalize

3. **안전장치**
   - quarantine
   - hold/discard/promote
   - filesystem rollback
   - policy gate
   - signoff/override 구조

4. **관측성**
   - session report
   - run telemetry
   - outcome metrics
   - promotion decision trends
   - routing provenance aggregate

5. **공급망/릴리스 신뢰**
   - SBOM
   - OpenVEX
   - in-toto
   - Sigstore
   - provenance attestation

이 정도면 보통의 “자동화 스크립트 모음”이 아니라, **자기 자신을 통제 가능한 단위로 개선하려는 운영 시스템**이다.

## 7-3. 왜 아직 5단계는 아닌가
Level 5에 가깝다고 말하려면, 단순히 자동화가 많은 것만으로는 부족하다.  
다음이 더 필요하다.

- 우선순위 엔진의 장기 성능 검증
- 개선 규칙의 효과성 통계화
- 실패 family에 대한 자동 정책 조정 근거 축적
- 구조 복잡도 증가에 대한 자동 억제
- shadow/canary/rollback 데이터를 통한 폐쇄 루프 최적화

현재 저장소는 **운영 자동화 + 강한 게이트 + 풍부한 artifact**는 갖췄다.  
하지만 “무엇이 가장 잘 먹히는 개선인지”를 학습적으로 최적화하는 단계는 아직 부분적이다.

---

## 8. 우선순위별 액션 플랜

## 8-1. 2주 이내
1. 공식 테스트 진입점에 plugin autoload 통제 전략 추가
2. README에 로컬 실행 표준(예: editable install 또는 Make target 우선)을 더 명시
3. `ruff` 규칙군 확장 실험 브랜치 생성
4. `auto_improve_runtime.py`, `mechanism_review_candidate_runtime.py` 분해 설계안 작성

## 8-2. 1개월 이내
1. orchestration 모듈 2~3개 분해 완료
2. 복잡도 budget artifact 생성기 추가
3. proposal ranking 품질 지표 추가
4. 문서-정책 drift 감시용 테스트 또는 lint 추가

## 8-3. 1~2개월 이내
1. shadow ranking / canary scoring 체계 도입
2. family별 장기 promotion yield 리포트 추가
3. strict type gate를 핵심 모듈에 시범 적용
4. CLI bootstrap 공통화 완료

---

## 9. 실무적으로 가장 중요한 판단

### 지금 당장 리라이트가 필요한가?
아니다.  
현재 코드는 **리라이트보다 점진적 분해와 게이트 강화**가 훨씬 적절하다.

### 지금 당장 위험한가?
크리티컬한 붕괴 신호는 보지 못했다.  
오히려 **품질과 안전을 꽤 진지하게 다루는 코드베이스**다.

### 무엇이 가장 먼저 문제를 일으킬 가능성이 큰가?
1. 대형 orchestration 모듈의 변경 난이도 상승
2. 로컬/CI/외부 환경 간 실행 재현성 차이
3. 자가 개선 코드가 스스로 복잡도를 키우는 현상

---

## 10. 최종 판단

이 저장소는 **엔지니어링 성숙도가 높은 편**이며,  
특히 **자가 개선 메커니즘을 실험-평가-승격 artifact로 운영한다는 점**에서 보기 드문 수준이다.

다만 다음을 반드시 기억해야 한다.

- 지금의 핵심 리스크는 “기능이 없다”가 아니라 **복잡도 관리**
- 지금의 핵심 기회는 “자가 개선을 더 많이 돌리자”가 아니라 **자가 개선의 효과를 더 잘 측정하자**
- 따라서 최적의 다음 수는 **대형 런타임 분해 + 재현성 하드닝 + 복잡도/랭킹 품질 계량화**다

한 문장으로 정리하면:

> **이 코드는 이미 잘 설계된 운영 체계 위에 서 있지만, 다음 성장 단계로 가려면 ‘더 많은 자동화’보다 ‘더 나은 복잡도 통제와 더 정교한 개선 효과 측정’이 필요하다.**

---

## 부록 A. 이번 리뷰에서 직접 확인한 파일 표면

- 루트: `README.md`, `ARCHITECTURE.md`, `pyproject.toml`, `pytest.ini`, `Makefile`
- 워크플로: `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- 핵심 런타임:
  - `ops/scripts/auto_improve_runtime.py`
  - `ops/scripts/auto_improve_session_runtime.py`
  - `ops/scripts/mechanism_review_candidate_runtime.py`
  - `ops/scripts/promotion_gate_mechanism_runtime.py`
  - `ops/scripts/filesystem_runtime.py`
  - `ops/scripts/planning_gate_validate_runtime.py`
  - `ops/scripts/observability_artifacts_runtime.py`
  - `ops/scripts/command_runtime.py`
- 테스트:
  - `tests/test_auto_improve_runtime.py`
  - `tests/test_mechanism_review_candidate_runtime.py`
  - `tests/test_planning_gate_validate_runtime.py`
  - `tests/test_filesystem_runtime.py`
  - `tests/test_policy_runtime.py`
  - `tests/test_report_schemas.py`
  - `tests/test_supply_chain_gate_runtime.py`

## 부록 B. 성숙도 평가 참고 기준(외부)
아래 기준은 이번 성숙도 판단의 보조 프레임으로 참고했다.

- NIST SSDF SP 800-218: Secure Software Development Framework  
  https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SP 800-218A: Generative AI / Dual-Use Foundation Models Community Profile  
  https://csrc.nist.gov/pubs/sp/800/218/a/final
- SLSA Specification v1.2  
  https://slsa.dev/spec/v1.2/
- OWASP Code Review Guide  
  https://owasp.org/www-project-code-review-guide/
- pytest plugin autoload 문서  
  https://docs.pytest.org/en/stable/how-to/plugins.html
- Python Packaging User Guide – Trusted Publishing  
  https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
- CISA SBOM 자료  
  https://www.cisa.gov/sbom
