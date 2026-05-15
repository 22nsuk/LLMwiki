# LLM Wiki vNext 코드 리뷰 보고서

작성일: 2026-04-21  
대상 아카이브: `LLM Wiki vNext(17).zip`  
보고서 목적: 현재 코드베이스를 누락 없이 정적·동적 관점에서 점검하고, 구조적 개선 방향과 자가 개선 체계의 성숙도를 평가한다.

---

## 1. 검토 범위와 방법

이번 리뷰는 업로드된 ZIP 내부의 실제 저장소 표면을 기준으로 진행했다.

### 1.1 검토 범위
- 루트 문서/설정: `README.md`, `ARCHITECTURE.md`, `AGENTS.md`, `pyproject.toml`, `Makefile`, `pytest.ini`
- 핵심 코드: `ops/`, `tests/`, `tools/`
- 운영/자가 개선 아티팩트: `ops/reports/*`, `ops/runtime-decomposition-plan.md`
- CI: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

### 1.2 수행한 점검
1. 전체 Python 소스 구조 스캔
   - 총 **234개 Python 파일**, 약 **54,921 LOC**
   - `ops/` 약 **30,373 LOC**
   - `tests/` 약 **24,174 LOC**
   - `tools/` 약 **374 LOC**
2. 함수 길이·분기 수·파라미터 수 기반 구조 복잡도 스캔
3. `compileall` 기반 전체 파이썬 문법 컴파일 점검
4. 핵심 리스크 영역 대상 선택 실행 테스트
   - 누적 **147 passed + 175 subtests passed** 확인
5. 자가 개선 관련 정책/리포트/관측 아티팩트 검토

### 1.3 한계와 해석 주의점
- 이번 환경에서는 ZIP 내부 로컬 가상환경(`.venv`)을 분석 대상에서 제외하고 검토했기 때문에, 저장소의 공식 `make static` 전체 경로를 그대로 재실행하지는 않았다.
- 다만 그 공백은 다음으로 보완했다.
  - 전체 정적 구조 분석
  - `compileall` 성공
  - 고위험 모듈 중심 선택 테스트 다수 통과
  - CI/Makefile/정책 정의 직접 검토
- 따라서 본 보고서는 **코드베이스 구조와 유지보수성 진단에는 신뢰도가 높고**, 전체 린트/타입체크의 “현재 시점 100% 재실행 결과”를 대체하는 보고서는 아니다.

---

## 2. 총평

이 저장소는 단순한 위키 정리 스크립트 모음이 아니라, **지속형 wiki maintainer runtime + 그 runtime 자체를 개선하는 meta-maintainer loop**를 함께 운영하려는 구조로 설계되어 있다. 아키텍처 문서와 정책, 스키마, 테스트, CI가 그 의도를 일관되게 반영하고 있다.

전반적인 인상은 다음과 같다.

- **설계 성숙도는 높다.** 문서-정책-스키마-테스트-운영 리포트가 서로 연결되어 있고, public/private 경계도 상당히 엄격하게 관리된다.
- **테스트 기반 운영 습관이 강하다.** 공개 미러, Windows smoke, 공급망 산출물, 스키마 재생성까지 검증하는 점은 일반적인 내부 자동화 저장소보다 한 단계 더 정돈되어 있다.
- **자가 개선 체계는 이미 작동하는 수준**이지만, 아직은 “관찰 가능한 개선 루프”에 더 가깝고, “정량 지표가 우선순위와 결정에 직접 반영되는 완전 폐루프”까지는 도달하지 않았다.
- 가장 큰 기술 부채는 기능 정확도보다 **오케스트레이션 복잡도 누적**이다. 이미 이를 인식하고 분해 작업을 진행 중이지만, 핵심 표면 몇 곳은 여전히 길고 넓고 매개변수가 많은 함수에 의존한다.

한 줄로 정리하면:

> **좋은 운영 체계를 가진 고급 저장소이지만, 다음 단계 성숙도로 가려면 “복잡도 예산을 실제 gate로 승격”하고 “자가 개선 지표를 진짜 의사결정에 연결”해야 한다.**

---

## 3. 잘된 점

### 3.1 아키텍처 경계가 분명하다
- `README.md`, `ARCHITECTURE.md`, `AGENTS.md`가 저장소의 역할, public/private 경계, 운영 레이어를 일관되게 설명한다.
- `raw/`, `wiki/`, `system/`, `ops/`, `runs/`의 역할 분리가 명확하다.
- public mirror 전략이 단순 문서화 수준이 아니라 실제 export/validation 절차까지 이어진다.

이 점은 장기적으로 큰 장점이다. 저장소 규모가 커져도 “무엇이 runtime이고 무엇이 corpus이며 무엇이 artifact인지”가 흐려지지 않는다.

### 3.2 스키마 기반 운영이 잘 자리잡아 있다
`ops/schemas/` 아래에 매우 많은 JSON Schema가 존재하고, 리포트 생성 코드가 이를 검증 대상으로 삼는다. 이는 “산출물을 그냥 JSON으로 떨구는 수준”이 아니라, **리포트 자체를 계약(contract)으로 다룬다**는 뜻이다.

이 구조는 다음에 특히 유리하다.
- 리그레션 방지
- 리뷰 자동화
- CI 안정성
- 후속 도구 연결
- 자가 개선 신호의 누적 관리

### 3.3 테스트 전략이 현실적이면서도 체계적이다
`Makefile`과 `pytest.ini`, CI 워크플로를 보면 테스트를 `fast / slow / integration / integration-heavy / public`으로 분리했다. 이는 이 저장소가 커지더라도 검증 비용을 통제하려는 의도가 잘 드러난다.

특히 좋은 점은 다음과 같다.
- public mirror 검증을 별도 tier로 둠
- Windows smoke를 별도 job으로 운영함
- schema sample regeneration까지 검증함
- 공급망 산출물(CycloneDX, SPDX, OpenVEX, in-toto, Sigstore)까지 CI에 포함함

### 3.4 자가 개선 관련 설계가 이미 “운영 가능한 수준”이다
정책과 아티팩트에서 다음이 확인된다.
- `auto_improve_policy.enabled: true`
- `mechanism_review`
- `mutation_proposal`
- `outcome_metrics`
- `warning_budget`
- `structural_complexity_budget`
- `task-improvement-observations`

즉, 이 저장소는 “좋아 보이는 리팩터링”이 아니라 **관측 → 후보화 → 실험 → 판정 → 기록**의 흐름을 최소한 골격 수준으로는 갖추고 있다. 이건 분명한 강점이다.

### 3.5 외부 리뷰를 받아들이는 방식이 좋다
`ops/runtime-decomposition-plan.md`와 `ops/reports/task-improvement-observations/...`를 보면, 외부 코드 리뷰 내용을 단순 메모로 남긴 것이 아니라 **follow-up automation backlog**와 연결하고 있다. 즉, 리뷰 결과가 산발적 메모로 흩어지지 않고 구조화된 후속 작업으로 전환된다.

이건 자가 개선 문화 측면에서 높게 평가할 만하다.

---

## 4. 핵심 문제와 개선 방안

아래는 우선순위가 높은 순서대로 정리한 내용이다.

### 4.1 오케스트레이션 복잡도 누적이 아직 해소되지 않았다

#### 관찰
구조 복잡도 관점에서 여전히 긴 함수와 큰 조정자(orchestrator) 표면이 남아 있다.

대표 사례:
- `ops/scripts/wiki_doc_audit_runtime.py:171` `external_report_reference_issues`
- `ops/scripts/raw_registry_runtime.py:239` `enrich_registry_entries_with_inventory`
- `ops/scripts/wiki_stage2_eval.py:40` `evaluate`
- `ops/scripts/behavior_delta_runtime.py:271` `build_behavior_delta_report`
- `ops/scripts/codex_exec_executor.py:179` `_materialize_prompt`
- `ops/scripts/codex_exec_executor.py:524` `execute_codex_exec_role`
- `ops/scripts/mechanism_review_candidate_runtime.py:134` `non_trigger_detail`

리뷰 중 직접 생성한 구조 복잡도 예산 리포트에서도, 모니터링 대상 7개 중 5개가 `attention` 상태였다. 특히 다음 표면이 계속 신호를 낸다.
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/promotion_gate_mechanism_runtime.py`
- `ops/scripts/mechanism_run_workspace_runtime.py`
- `ops/scripts/policy_runtime.py`
- `ops/scripts/finalize_run_state_runtime.py`

또한 정책 기준 함수 budget 후보가 **47개** 검출되었다.

#### 해석
현재 저장소는 이미 “분해의 필요성”을 인식하고 있고, 실제로 여러 runtime helper로 나누는 작업도 진행 중이다. 문제는 분해가 시작되었지만, 핵심 orchestration surface에서는 아직 **상태 전이, 검증, 리포트 조립, 이벤트 기록, 경로 계산**이 한 함수 또는 한 파일에 많이 남아 있다는 점이다.

이 상태가 지속되면 생기는 문제는 다음과 같다.
- 변경 한 번에 영향 범위가 넓어짐
- 테스트 픽스처가 과대해짐
- monkeypatch seam이 늘어남
- 타입 명세보다 암묵적 dict 계약이 많아짐
- 향후 자가 개선 루프가 오히려 복잡도 부채를 증폭시킬 수 있음

#### 개선 방안
1. **파일 분해보다 상태 전이 분해를 우선**해야 한다.
   - 이미 `runtime-decomposition-plan.md`에서 이 방향을 취하고 있어 타당하다.
2. 다음 1차 우선순위를 권장한다.
   - `behavior_delta_runtime.build_behavior_delta_report`
   - `raw_registry_runtime.enrich_registry_entries_with_inventory`
   - `wiki_stage2_eval.evaluate`
   - `codex_exec_executor._materialize_prompt`
3. 긴 함수 분해 시 기준을 “기능”이 아니라 아래 단위로 통일하는 것이 좋다.
   - 입력 정규화
   - 상태 계산
   - 판정 로직
   - 리포트 조립
   - 출력/쓰기
4. `dict` 전달이 많은 구간은 `dataclass` 또는 작은 interface object로 바꿔 **매개변수 수를 줄이는 것**이 효과적이다.

#### 우선순위
**상**

---

### 4.2 자가 개선 루프는 존재하지만, 아직 “정량적 폐루프”는 아니다

#### 관찰
정책과 리포트를 보면 자가 개선 구조는 이미 있다. 그러나 실질적으로는 아직 진단형에 가깝다.

증거:
- `ops/policies/wiki-maintainer-policy.yaml`의 `outcome_metrics_preview.mode`가 **`audit_only`**
- 같은 정책 메모에 **“priority_delta wiring requires a later explicit policy step”**가 남아 있음
- `ops/reports/outcome-metrics.json`의 `attempts_considered`가 **2**에 불과함
- `ops/reports/mechanism-review-candidates.json`에서 `candidates_emitted`가 **0**
- 2026-04-21 관측 아티팩트에서 `outcome_metrics_shadow_priority_gap`이 **open** 상태로 남아 있음

#### 해석
이 저장소는 “개선 후보를 제안하고, 실험 결과를 기록하고, 실패 패턴을 분석할 준비”는 되어 있다. 하지만 아직은 다음 단계가 미완성이다.

- outcome metrics가 queue priority를 바꾸지 않음
- complexity budget이 hard gate가 아님
- 시도 횟수가 적어 calibration 신뢰도가 낮음
- 개선 loop가 실제 운영 의사결정을 바꾸는 증거가 약함

즉, **자가 개선은 ‘실행 중’이지만 ‘학습이 운영에 반영되는 단계’까지는 아직 아니다.**

#### 개선 방안
1. `audit_only` 다음 단계로 **`shadow_priority`**를 도입한다.
   - 실제 우선순위는 유지하되, metrics-aware ordering을 계산해 차이만 기록
2. 충분한 시도 수가 쌓이면, 아래 둘 중 하나를 선택한다.
   - queue ordering에 부분 반영
   - human signoff 시 보조 점수로만 반영
3. outcome metrics 최소 데이터 기준을 정책에 명시한다.
   - 예: `attempts_considered >= 10`
   - target family별 최소 comparable run 수
4. complexity budget도 touched file 기준의 narrow gate로 승격한다.
   - 전체 hard gate보다 **변경 표면 한정 gate**가 현실적이다.

#### 우선순위
**상**

---

### 4.3 실행 재현성이 wrapper/설치 경로에 다소 의존한다

#### 관찰
리뷰 환경에서 저장소 루트에서 바로 `pytest`를 실행했을 때, 초기에는 `ops` 패키지를 찾지 못해 수집 단계가 전부 실패했다. `PYTHONPATH=.`를 명시하자 정상 수집/실행이 가능했다.

#### 해석
이건 치명적 버그는 아니다. 실제로 이 저장소는 `make dev-install`, editable install, `.venv/bin/python`, direct-script fallback 등을 적극적으로 사용하도록 설계되어 있다. 다만 개발자가 공식 진입점 밖에서 바로 실행하면,

- import path 설정에 의존하게 되고
- 저장소 사용 경험이 진입점마다 달라지며
- “로컬에서는 왜 안 되지?” 같은 friction이 생길 수 있다.

이 종류의 문제는 대형 저장소에서 작은 비용처럼 보이지만, 시간이 지날수록 개발 생산성을 갉아먹는다.

#### 개선 방안
1. 공식 개발 진입점 외 사용을 막을 생각이 아니라면, 아래 중 하나를 권장한다.
   - 루트 `conftest.py`에서 repo root를 path에 추가
   - `python -m pytest` 기준 editable install 강제를 README 최상단에 더 분명히 표기
   - `tox`/`nox`/`uv run` 기반 단일 진입점을 더 강하게 권장
2. 테스트 환경 실패 시, “editable install or PYTHONPATH missing”를 더 친절히 안내하는 fail-fast 검사도 고려할 수 있다.

#### 우선순위
**중상**

---

### 4.4 구조 복잡도 예산 코드에 의미 없는 no-op 루프가 있다

#### 관찰
`ops/scripts/structural_complexity_budget_runtime.py:95-109`의 `_normalize_target_profiles()`에는 다음 성격의 코드가 있다.

- target을 순회함
- 존재 여부를 검사함
- 존재하면 `continue`
- 존재하지 않아도 아무 작업을 하지 않음
- 결국 루프 전체가 실질적으로 아무 의미를 만들지 않음

#### 해석
이건 기능 오류라기보다 **중간 리팩터링 흔적**에 가깝다. 하지만 이런 코드는 두 가지 측면에서 좋지 않다.
- 독자가 “여기서 원래 무슨 validation을 하려던 거지?”라고 멈추게 만든다.
- 이후 missing target 처리의 책임 위치가 애매해진다.

현재 missing target 자체는 `build_report()` 쪽에서 처리되므로 기능은 돌아간다. 그러나 이런 잔여 코드는 구조 예산 시스템의 신뢰도를 떨어뜨린다. 특히 이 모듈은 복잡도 관리라는 메타 품질 게이트를 담당하므로, 내부가 더 또렷해야 한다.

#### 개선 방안
- 이 루프를 완전히 제거하거나,
- 아니면 여기서 실제 validation을 수행해 `diagnostics` 또는 normalization 결과에 반영하도록 역할을 명확히 해야 한다.

#### 우선순위
**중상**

---

### 4.5 함수 시그니처가 무거운 표면이 아직 많다

#### 관찰
함수 budget 후보 중 상당수는 길이보다 **매개변수 수** 때문에 신호가 발생했다.

대표 사례:
- `ops/scripts/codex_exec_executor.py:179` `_materialize_prompt` — 파라미터 과다
- `ops/scripts/promotion_gate.py:116` `mechanism_class_report` — 파라미터 과다
- `ops/scripts/mechanism_run_scaffold_resolution_runtime.py:219` `resolve_experiment_inputs` — 파라미터 과다
- `ops/scripts/auto_improve_execute_runtime.py`의 여러 phase 함수 — 파라미터 과다

#### 해석
이 상태는 대체로 아래를 의미한다.
- 함수가 너무 많은 책임을 가짐
- 여러 dict와 설정 조각을 외부에서 조립해 넘김
- 호출부가 길어지고 실수 가능성이 커짐
- 테스트에서 fixture 조립 비용이 커짐

#### 개선 방안
1. phase/unit별 입력을 `dataclass`로 묶는다.
2. “항상 같이 다니는 값”은 context object로 합친다.
3. 파라미터 많은 함수는 아래 둘 중 하나만 하게 만든다.
   - pure calculation
   - side-effect orchestration

#### 우선순위
**중**

---

### 4.6 테스트도 점차 ‘대형 자산’이 되고 있다

#### 관찰
가장 큰 파일 다수가 테스트다.

예:
- `tests/test_mechanism_review.py` 1825 LOC
- `tests/minimal_vault_runtime.py` 1155 LOC
- `tests/test_run_mechanism_experiment.py` 1091 LOC
- `tests/test_promotion_gate_equal_score.py` 954 LOC
- `tests/test_mutation_proposal.py` 907 LOC

테스트 함수 budget 후보도 다수 존재한다.

#### 해석
이 저장소는 테스트를 많이 쓰는 점이 장점이지만, 동시에 테스트 자체가 또 하나의 유지보수 대상이 되고 있다. 특히 거대한 fixture builder와 장문 테스트 메서드는 아래 위험을 만든다.

- 테스트 이해 비용 증가
- 회귀 시 원인 분석 시간 증가
- fixture 재사용성 저하
- 실제 기능 분해보다 테스트 분해가 더 늦어질 가능성

#### 개선 방안
1. `tests/minimal_vault_runtime.py`를 역할별 fixture 모듈로 분리한다.
2. 초장문 테스트는 “시나리오 조립”, “입력 fixture”, “검증 assertion”을 분리한다.
3. helper fixture도 production 코드와 동일하게 복잡도 budget preview 대상으로 다루는 것이 좋다.

#### 우선순위
**중**

---

### 4.7 ZIP 산출물 위생은 별도 관리가 필요하다

#### 관찰
업로드된 ZIP에는 `.venv`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.obsidian` 등이 함께 포함되어 있었고, 특히 `.venv`가 압도적으로 많은 항목을 차지했다.

#### 해석
이건 저장소 내용 자체의 문제라기보다 **전달 패키지 위생 문제**다. 코드 리뷰만 놓고 보면 큰 결함은 아니지만,
- 아카이브 크기 증가
- 리뷰 효율 저하
- 환경 종속 산출물 혼입
- 배포물/소스물 경계 혼란
을 만든다.

#### 개선 방안
- 코드 리뷰용/배포용 ZIP은 `.venv`, cache, local artifact를 기본 제외하는 전용 export 명령을 두는 것이 좋다.
- 이미 public export 체계가 있으므로, 내부 리뷰용 export도 같은 패턴으로 만드는 것이 자연스럽다.

#### 우선순위
**중하**

---

## 5. 자가 개선 성숙도 평가

### 5.1 평가 결과
**현재 성숙도: 5단계 기준 3.5 / 5 (관리형과 정량 관리형 사이)**

보다 실무적으로 표현하면:

> **“자가 개선을 실제 운영 artefact와 정책으로 굴리고는 있지만, 정량 지표가 아직 우선순위/판정에 직접 결합되지 않은 단계”**

### 5.2 왜 이 점수를 주는가

#### 이미 갖춘 것
1. **정책 기반 자동 개선 루프 존재**
   - `auto_improve_policy` 활성화
2. **후보 생성 체계 존재**
   - `mechanism_review`, `mutation_proposal`
3. **결과 누적 체계 존재**
   - `outcome-metrics.json`
4. **품질 게이트 존재**
   - warning budget, complexity budget preview, equal-score promotion rules
5. **후속 작업 관측 체계 존재**
   - `task-improvement-observations`
6. **외부 리뷰 수용 및 리포지터리 내 반영 체계 존재**
   - decomposition plan과 observation backlog가 연결됨

#### 아직 부족한 것
1. outcome metrics가 아직 `audit_only`
2. 시도 수가 적어 calibration 신뢰도 낮음
3. complexity budget이 아직 preview 중심
4. 구조 복잡도 증가를 touched-file hard gate로 막는 체계가 약함
5. 일부 핵심 orchestrator가 여전히 크고 복잡함

### 5.3 성숙도 단계별 해석
- **Level 1**: 수동 개선, 기록 약함
- **Level 2**: 반복 가능한 개선 절차 존재
- **Level 3**: 정책/리포트/테스트가 연결된 관리형 개선
- **Level 4**: 정량 지표가 우선순위와 판정에 영향을 미침
- **Level 5**: 폐루프 최적화 + 장기 drift 제어 + 자동 회귀 억제

현재 저장소는 분명 **Level 3은 넘었다**. 다만 `Level 4`로 부르려면,
- outcome metrics가 shadow라도 의사결정 비교에 들어가고
- complexity budget이 touched-surface gate로 승격되며
- 시도 표본이 더 쌓여야 한다.

---

## 6. 보완 방안 제안

### 6.1 단기(가장 먼저 할 것)
1. `structural_complexity_budget_runtime.py`의 no-op loop 제거 또는 역할 명확화
2. `behavior_delta_runtime`, `raw_registry_runtime`, `wiki_stage2_eval` 우선 분해
3. 파라미터 과다 함수에 `dataclass` 기반 입력 객체 도입
4. 테스트/실행 진입점 재현성 개선
   - editable install 강제 또는 테스트 bootstrap 보강

### 6.2 중기(성숙도 끌어올리기)
1. outcome metrics `shadow_priority` 도입
2. touched-file 기반 complexity gate를 `check-strict`에 부분 승격
3. structured runtime event logging 적용 범위 확대
4. 테스트 fixture 대형화 억제를 위한 helper 분리

### 6.3 장기(자가 개선을 진짜 폐루프로 만들기)
1. target family별 comparable run 최소 표본 수 정책화
2. metrics-aware priority ordering A/B 비교
3. promotion 이후 defect escape proxy 연계 강화
4. “복잡도 증가 대비 테스트 증가율”을 지속 추적하는 장기 drift gate 도입

---

## 7. 권장 우선순위 로드맵

### P0
- 구조 복잡도 상위 3개 함수/모듈 분해
- no-op validation 잔재 제거
- 테스트 bootstrap 재현성 보강

### P1
- `shadow_priority` 실험 도입
- touched-surface complexity gate 도입
- 대형 테스트 fixture 분해

### P2
- outcome metrics를 queue ordering 또는 signoff 보조 점수로 승격
- 장기 drift/회귀 추적 지표 강화
- review용 lightweight export 경로 추가

---

## 8. 실행 확인 요약

이번 리뷰에서 직접 확인한 실행 신호는 다음과 같다.

- `python -m compileall -q ops tests tools` 성공
- 선택 테스트 통과
  - 46 passed
  - 36 passed
  - 12 passed
  - 9 passed
  - 25 passed
  - 6 passed
  - 13 passed + 175 subtests passed

즉, 전체 static gate를 동일 환경에서 완전 재현하지는 않았지만, 적어도 핵심 고위험 표면의 회귀 방어력은 상당히 확보되어 있다고 볼 수 있다.

---

## 9. 최종 결론

이 코드베이스는 이미 **운영 체계가 있는 저장소**다. 즉, 코드만 있는 것이 아니라 정책, 계약, 테스트, CI, 산출물, 후속 관측이 서로 연결되어 있다. 이 점은 매우 좋다.

다만 다음 단계로 가려면 방향은 분명하다.

1. **큰 orchestrator를 더 작게 쪼개고**  
2. **복잡도 예산을 실제 gate로 강화하고**  
3. **자가 개선 지표를 audit-only에서 shadow decision으로 올리고**  
4. **테스트/실행 진입점의 재현성을 더 단단하게 만들 것**

현재 상태를 실무적으로 평가하면,

> **“기반은 매우 좋고, 이제는 복잡도와 자가 개선 신호를 실제 운영 제어로 승격해야 하는 시점”**

이다.

