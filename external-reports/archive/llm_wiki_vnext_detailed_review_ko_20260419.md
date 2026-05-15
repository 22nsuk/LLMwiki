# LLM Wiki vNext 코드 검토 및 개선 보고서

작성일: 2026-04-19  
검토 대상: `LLM Wiki vNext(7).zip` 내 코드/설정/테스트/운영 문서  
산출물 언어: 한국어

---

## 1. 검토 범위와 방법

이번 검토는 **코드베이스 전반의 구조적 리뷰 + 정적 분석 + 선별 실행 검증** 방식으로 진행했다.  
주된 검토 대상은 실제 운영 로직이 집중된 다음 표면이다.

- `ops/scripts/*.py`
- `ops/policies/*.yaml`
- `ops/schemas/*.json`
- `tests/test_*.py`
- `Makefile`, `pyproject.toml`, `pytest.ini`, `ARCHITECTURE.md`, `AGENTS*.md`, `ops/README.md`

반대로 `raw/`의 대규모 PDF·웹 스냅샷·콘텐츠 원문은 **코드 리뷰의 본질적 대상이 아니므로** 구조 확인만 하고 상세 평가는 제외했다.

### 수행한 점검

- 저장소 구조 및 운영 문서 검토
- Python 소스 전체 구문 컴파일 검증 (`compileall`) 통과 확인
- 핵심 테스트 선별 실행
  - `test_policy_runtime.py`
  - `test_mechanism_assess.py`
  - `test_promotion_gate_equal_score.py`
  - `test_auto_improve_runtime.py`
  - `test_release_smoke.py`
  - `test_export_public_repo.py`
  - `test_filesystem_runtime.py`
  - `test_behavior_delta_runtime.py`
  - `test_mechanism_run_validation_runtime.py`
  - `test_report_generation_smoke.py`
  - `test_import_fallback_contract.py`
  - `test_makefile_static_gates.py`
  - `test_writer_output_paths.py`
  - `test_wiki_eval_runtime.py`
  - `test_wiki_stage2_eval.py`
  - `test_wiki_lint_runtime.py`
  - `test_subagent_routing.py`
  - `test_raw_registry_runtime.py`
  - `test_planning_gate_validate_runtime.py`
- 모듈/함수 규모 분석, 운영 경계와 자가개선 루프의 성숙도 평가

### 정량 요약

- `ops/scripts/*.py`: **91개 파일**, 총 **22,428줄**
- `tests/test_*.py`: **73개 파일**, 테스트 함수 **389개**
- `ops/schemas/*.json`: **27개**
- `.codex/agents/*.toml`: **9개**
- 400줄 초과 모듈: **20개**
- 80줄 초과 함수: **40개**
- 모듈 길이 중앙값: **171줄**
- 함수 길이 중앙값: **11줄**

이 수치만 보면 저장소는 무질서하게 커진 프로젝트가 아니라, **운영 계약과 자동 검증이 상당히 발달한 도구형 저장소**에 가깝다. 다만 일부 핵심 런타임에 복잡도가 집중돼 있다.

---

## 2. 총평

### 한 줄 결론

이 저장소는 **정책·스키마·테스트·승격 게이트까지 갖춘 고성숙 운영형 코드베이스**다.  
단, **일부 핵심 모듈의 복잡도 집중**, **자가개선 루프의 안전한 실서비스화(canary/shadow, outcome-driven learning) 부족**이 다음 단계의 핵심 보완 포인트다.

### 전체 등급

- **구조 설계:** A-
- **운영 신뢰성:** A-
- **테스트/계약 엄격성:** A
- **유지보수성:** B+
- **자가개선 메커니즘 성숙도:** A- (단, 완전 자율 최적화 수준은 아님)

### 좋은 점

1. **정책 기반 운영 통제**가 매우 강하다.  
   단순 스크립트 모음이 아니라 `policy -> schema -> runtime -> test -> report`로 이어지는 폐루프가 보인다.

2. **자가개선 루프가 설계 수준에서 명시적**이다.  
   `mechanism_review`, `mutation_proposal`, `run_mechanism_experiment`, `promotion_gate`, `auto_improve_loop`, `improvement_observations`가 각각 독립 책임을 갖는다.

3. **안전장치가 깊다.**  
   `allowed_apply_roots`, `behavior-delta`, `promotion-decision-trends`, `routing-provenance-aggregates`, `timeout-failure` 등은 “개선”보다 “통제된 개선”에 무게를 둔 설계다.

4. **테스트의 방향이 좋다.**  
   단순 유틸 테스트뿐 아니라 정책 계약, 승격 예외 조건, 공개 surface export, release smoke, report schema, path hygiene를 함께 검증한다.

### 아쉬운 점

1. **몇몇 모듈에 변경 위험이 과도하게 집중**되어 있다.
2. **자가개선이 규칙 기반 폐루프에는 도달했지만, 실제 성과 기반 학습 루프는 아직 약하다.**

---

## 3. 핵심 발견사항

## 3.1

문서·배포 표면과 실제 canonical install path가 분리되어 있는데, 단일 source of truth가 충분히 정리되지 않음

---

## 3.2 높은 우선순위 — 복잡도가 일부 핵심 모듈에 과도하게 집중됨

### 관찰

대형 모듈과 대형 함수가 몇몇 핵심 경로에 몰려 있다.

#### 큰 모듈 상위 예시

- `ops/scripts/mechanism_review_candidate_runtime.py` — **847줄**
- `ops/scripts/auto_improve_runtime.py` — **779줄**
- `ops/scripts/promotion_gate_mechanism_runtime.py` — **750줄**
- `ops/scripts/mechanism_run_validation_runtime.py` — **683줄**
- `ops/scripts/raw_markdown_runtime.py` — **645줄**
- `ops/scripts/mechanism_assess.py` — **608줄**
- `ops/scripts/mechanism_candidate_registry_runtime.py` — **608줄**
- `ops/scripts/mechanism_run_workspace_runtime.py` — **581줄**

#### 큰 함수 상위 예시

- `build_mechanism_rule_registry(...)` — **263줄**
- `lint(...)` — **240줄**
- `execute_codex_exec_role(...)` — **206줄**
- `evaluate(...)` in `wiki_stage2_eval.py` — **184줄**
- `finalize_run(...)` — **183줄**
- `evaluate(...)` in `wiki_eval.py` — **179줄**
- `run_auto_improve_session(...)` — **172줄**
- `build_behavior_delta_report(...)` — **166줄**

### 해석

이 프로젝트는 이미 “runtime 분리” 노력을 하고 있다. 실제로 wrapper와 runtime을 나누고, 세부 런타임 모듈도 다수 분리되어 있다.  
그럼에도 불구하고 핵심 거버넌스 로직은 여전히 **한 파일 안에서 규칙 정의 + 데이터 조립 + 상태 판정 + 출력 형식화**를 동시에 수행하는 경향이 강하다.

이 구조의 문제는 다음과 같다.

- 변경 한 번이 여러 의미 계층에 동시에 영향을 준다.
- 테스트가 있어도 **리뷰 인지 부하**가 크다.
- 승격 규칙이나 auto-improve 규칙을 바꿀 때 회귀 위험이 커진다.
- 사람이 코드를 읽고 정책을 검증하기보다, 코드를 “해석”해야 하는 상태가 된다.

### 판단

- **심각도:** 높음
- **근본 원인:** 거버넌스 로직이 선언형 데이터가 아니라 절차형 코드 내부에 많이 남아 있음

### 개선 방안

#### 1) 규칙 레지스트리를 더 선언형으로 옮기기

예를 들어 `promotion_gate_mechanism_runtime.py`의 규칙 조립은 이미 `RuleSpec` 기반 구조를 쓰고 있어 방향은 좋다.  
다음 단계는 다음과 같다.

- 규칙 정의를 “빌더 코드”에서 “정적 registry + 작은 evaluator 함수”로 분리
- `rule_id`, `severity`, `artifact dependency`, `reducer`, `human-facing summary template`를 데이터화
- 변경 시 diff가 **정책 변화인지 구현 변화인지** 더 분명하게 보이게 만들기

#### 2) 대형 함수의 phase 객체화

예를 들어 `run_auto_improve_session()`은 사실상 세션 상태기계다.  
이를 다음처럼 더 분해할 수 있다.

- budget evaluation
- queue selection
- routing/scaffold
- execution/evaluation
- quarantine/update
- session finalization

각 단계를 작은 result object로 연결하면 테스트 표면이 더 선명해진다.

#### 3) “판정”과 “설명문 생성” 분리

현재 일부 함수는 threshold 판정과 human-readable detail 문자열 생성을 함께 수행한다.  
먼저 구조화된 판정 결과를 만들고, 마지막에 renderer가 문장을 조립하도록 나누면 유지보수가 훨씬 쉬워진다.

### 권장 액션

- 600줄 이상 모듈부터 리팩터링 우선순위를 부여하되, **한 번에 하나의 책임만 분리**하는 지금의 운영 철학은 유지하는 것이 좋다.
- 우선순위 1순위 후보:
  - `promotion_gate_mechanism_runtime.py`
  - `auto_improve_runtime.py`
  - `mechanism_review_candidate_runtime.py`

---

## 3.3 높은 우선순위 — 자가개선 루프는 강하지만, “실제 성과 기반 학습”은 아직 제한적임

### 관찰

이 저장소는 자가개선 관련 표면이 매우 풍부하다.

- `mechanism_review`
- `mutation_proposal`
- `run_mechanism_experiment`
- `promotion_gate`
- `behavior-delta`
- `improvement_observations`
- `auto_improve_loop`
- `promotion-decision-trends`
- `routing-provenance-aggregates`
- `allowed_apply_roots`
- quarantine / timeout / scope freeze / signoff 정책

즉, 이 프로젝트는 이미 **“개선안을 자동으로 제안하고, 제한된 범위에서 실행하고, 결과를 평가하고, 승격 여부를 결정하는 폐루프”**를 갖추고 있다.

그러나 여전히 개선 판단의 중심은 아래에 가깝다.

- 구조적 지표
- lint/eval/stage2 결과
- 정책 위반 여부
- 테스트 증감
- 위험 플래그
- 규칙 기반 우선순위

반면, 다음은 상대적으로 약하다.

- 실제 운영 성과(lead time, false positive rate, operator time saved, rollback frequency 등) 기반 학습
- canary/shadow apply 기반의 점진적 배포 안전장치
- 공급망 보안(SBOM, provenance, dependency hygiene)과 자동 개선 루프의 연결
- 규칙의 가중치를 empirical outcome으로 재보정하는 체계

`ops/README.md`에도 이미 **shadow/canary apply, provenance/SBOM/Dependabot 흐름이 아직 운영 표면으로 올라오지 않았다**는 취지의 한계가 드러나 있다. 즉, 코드도 이를 인지하고 있다.

### 자가개선 성숙도 평가

아래 5단계 기준으로 보면:

1. **수동 개선** — 사람이 직접 고친다.
2. **스크립트화된 개선** — 자동 검사와 보조 스크립트가 있다.
3. **측정 가능한 개선 루프** — 지표/평가/아티팩트가 있다.
4. **통제된 폐루프 개선** — 제안, 실행, 평가, 승격, 격리까지 자동화된다.
5. **성과 기반 자율 최적화** — 실운영 outcome을 바탕으로 규칙·정책이 계속 보정된다.

현재 상태는 **4단계에 명확히 도달**, 다만 **5단계에는 아직 미달**로 판단한다.

### 종합 점수

- **자가개선 성숙도:** **3.9 / 5.0**
- 해석: **관리형 폐루프(Managed Closed Loop)**

### 세부 점수

- 정책/가드레일: **4.5/5**
- 관측성/감사 추적성: **4.5/5**
- 실험/승격 자동화: **4.0/5**
- 배포 안전장치: **3.0/5**
- 성과 기반 학습: **2.5/5**

### 개선 방안

#### 1) outcome metric을 승격 루프에 연결

현재는 구조적 품질과 정책 위반 감지가 강하다. 여기에 다음을 붙이면 한 단계 올라간다.

- run 이후 재수정 빈도
- rollback / HOLD / DISCARD 비율의 이동평균
- 특정 규칙이 실제로 유효했던 비율
- 운영자 수동 개입 시간 절감량
- 변경 후 defect escape rate

즉, **“좋아 보이는 코드”가 아니라 “실제로 운영 성과가 개선된 변경”**을 선호하도록 루프를 진화시켜야 한다.

#### 2) canary/shadow apply 도입

현재의 `allowed_apply_roots`와 promotion gate는 강력한 write boundary를 제공한다.  
다음 단계는 그 위에 다음을 올리는 것이다.

- dry-run / shadow apply
- limited-scope apply
- rollback rehearsal
- promotion 전후 diff impact score 비교

#### 3) 규칙 가중치의 주기적 재보정

복잡도 점수, 위험 플래그, 우선순위 calibration이 현재는 주로 설계자 의도 기반이다.  
월간 또는 세션 누적 outcome으로 threshold를 재보정하는 batch job을 두면 훨씬 강해진다.

#### 4) dependency / provenance 보강

자가개선 시스템은 “코드가 스스로 바뀌는 시스템”이므로 공급망 신뢰성이 일반 서비스보다 더 중요하다.

- dependency pinning 정책 강화
- SBOM 생성
- artifact provenance 서명
- Dependabot 또는 동급의 dependency freshness pipeline

---

## 3.4 중간 우선순위 — 테스트 전략은 강하지만, 복잡도 hotspot에 대한 변화 중심 테스트는 더 늘릴 가치가 있음

### 관찰

테스트 수와 방향성은 매우 좋다.

- 정책 계약 테스트
- 승격 예외 규칙 테스트
- release smoke
- 공개 미러 export
- output path 정합성
- import fallback contract
- eval/lint/stage2 runtime 검증
- subagent routing, raw registry, planning gate 검증

이는 일반적인 “스크립트 저장소” 수준을 분명히 넘는다.

다만 복잡도 hotspot을 고려하면 다음 보완이 유효하다.

- 대형 규칙 빌더에 대한 **table-driven test** 확대
- manifest/apply guard에 대한 **property-based test** 도입
- auto-improve 세션 상태 전이에 대한 **state-machine test** 보강
- behavior delta / promotion gate / mechanism review 간 **교차 일관성 테스트** 추가

### 해석

지금도 테스트는 충분히 훌륭하다. 문제는 “테스트가 부족하다”가 아니라, **가장 비싼 변경이 일어나는 코드에 더 특화된 테스트가 있으면 좋다**는 것이다.

### 개선 방안

1. 규칙형 함수는 fixture 기반 분기 테스트보다 **데이터 테이블 기반 회귀 스냅샷 테스트**가 더 잘 맞는다.
2. `allowed_apply_roots`, path normalization, manifest apply는 **fuzz/property 테스트**로 강화할 가치가 높다.
3. auto-improve session은 **event-sequence test harness**를 별도 모듈로 두면 상태 전이 회귀를 더 잘 잡을 수 있다.

---

## 3.5 중간 우선순위 — 문서와 구현의 괴리를 자동으로 잡는 메타 검사가 필요함

### 관찰

이 저장소는 문서가 매우 풍부하다. 그러나 문서가 풍부한 프로젝트일수록 drift의 비용이 커진다.

이번 검토에서 이미 다음 유형의 drift가 보였다.

- 설치 경로 설명 drift
- 일부 설계 의도가 코드에 반영되어 있으나, 사람이 문서만 읽으면 현재 canonical path를 오해할 여지

### 개선 방안

다음 메타 검사를 CI에 넣는 것을 권장한다.

- 문서에서 언급한 canonical file/path 존재성 검사
- `pyproject`, `Makefile`, `ops/README.md` 상호 정합성 검사
- public export allowlist와 문서 설명의 동기화 검사
- “이 문서는 현재 canonical contract를 설명한다”는 선언이 붙은 파일의 링크 무결성 검사

---

## 3.6 낮은 우선순위 — CLI wrapper 중복은 의도적이지만 생성형 관리가 가능함

### 관찰

직접 실행 fallback 패턴(`__package__ in (None, "")`)을 가진 CLI 진입 파일이 **23개** 확인됐다.

이 패턴 자체는 이 저장소의 계약상 의도된 것으로 보이며, 관련 테스트도 존재한다. 따라서 이것을 “문제”라고 볼 필요는 없다.

다만 장기적으로는 아래 위험이 있다.

- wrapper 사이의 미세한 drift
- 에러 처리/exit code/출력 형식의 불일치 가능성

### 개선 방안

- 공통 CLI bootstrap helper 또는 wrapper generator를 도입하면 반복을 줄일 수 있다.
- 단, 현재처럼 명시성을 중시하는 프로젝트라면 과도한 추상화는 피하는 편이 낫다.

즉, 이 항목은 **바로 고칠 문제는 아니고, 코드가 더 커질 때 대비한 준비 과제**다.

---

## 4. 자가 개선 관점의 성숙도 진단

## 4.1 지금 잘하고 있는 것

### 1) 개선 대상을 “메커니즘”으로 분리했다

이 저장소는 콘텐츠 변경과 운영 메커니즘 변경을 구분하고, 후자에 대해 별도 실험/승격 절차를 둔다. 이 점은 매우 좋다.  
자가개선 시스템이 위험해지는 가장 흔한 이유는 “무엇을 바꾸는지”와 “어떻게 검증하는지”가 섞이는 데 있는데, 여기서는 그 경계를 분명히 세우려는 노력이 보인다.

### 2) write boundary가 비교적 명확하다

`allowed_apply_roots`, manifest guard, promotion gate의 이중 검사 구조는 자가개선 시스템의 필수 요소다.  
이 부분은 설계 성숙도가 높다.

### 3) 설명 가능한 개선 아티팩트가 남는다

`behavior-delta`, `run-ledger`, `promotion-report`, `routing-provenance-aggregate`, `promotion-decision-trends` 등은 단순 성공/실패 로그가 아니라 **왜 그런 판단이 났는지 추적 가능한 기록**을 남긴다.  
이는 신뢰 가능한 self-improvement 시스템에 매우 중요하다.

## 4.2 아직 부족한 것

### 1) 경험적 효과 측정의 약함

지금은 “정책적으로 안전하고 구조적으로 개선된 것처럼 보이는가”를 잘 본다.  
하지만 “운영 성과가 실제로 좋아졌는가”를 직접 측정하는 루프는 약하다.

### 2) 점진적 배포 메커니즘의 부재

승격 전후의 중간 단계가 약하다. self-improvement 시스템에서는 full promote 이전에 **shadow / canary / staged apply**가 있으면 훨씬 안전하다.

### 3) 외부 변화에 대한 자동 적응력 부족

정책이 매우 정교하지만, 그 정책 자체를 empirical signal로 재학습하는 구조는 약하다.  
즉, 현재는 **잘 설계된 규칙 시스템**이지, **실패로부터 규칙을 스스로 재보정하는 시스템**은 아니다.

---

## 5. 우선순위별 개선 로드맵

## 5.1 1차 (즉시)

### 목표

개발자 계약 정합성 복구 + 복잡도 hotspot의 안전한 분해 시작

### 액션

1. 루트 계약 정리
   - canonical install path를 문서/빌드 모두에서 통일

2. 복잡도 hotspot 분해 시작
   - `promotion_gate_mechanism_runtime.py`에서 규칙 registry 선언형화
   - `auto_improve_runtime.py`의 세션 상태 전이를 phase object로 분해

3. CI 메타 검사 추가
   - 문서가 가리키는 canonical file 존재성 검사
   - `Makefile`/`pyproject`/`ops/README.md` 상호 정합성 검사

## 5.2 2차 (단기)

### 목표

자가개선 루프의 운영 안전성 강화

### 액션

1. shadow/canary apply 경로 설계
2. outcome metric 수집 추가
3. promotion decision trend를 단순 누적이 아니라 경향 분석 입력으로 활용
4. behavior delta와 실제 defect/rollback 상관관계 리포트 추가

## 5.3 3차 (중기)

### 목표

성과 기반 self-improvement로 진화

### 액션

1. 규칙 가중치 재보정 job 도입
2. dependency/provenance/SBOM 파이프라인 통합
3. operator effort, rollback, HOLD/DISCARD 패턴을 활용한 adaptive prioritization 도입

---

## 6. 최종 판단

이 코드베이스는 단순히 “정리된 Python 스크립트 모음”이 아니다.  
**정책 기반 운영 시스템 + 자가개선 실험 프레임워크 + 감사 가능한 승격 체계**를 함께 갖춘, 꽤 높은 수준의 운영 코드다.

특히 좋은 점은 다음이다.

- 변경을 무작정 자동화하지 않고 **통제된 자동화**를 지향한다.
- 스키마와 테스트를 통해 **설계 의도를 코드 계약으로 굳히는 습관**이 있다.
- 자가개선 시스템에서 가장 중요한 **추적성, 격리, 승격 통제**가 이미 상당 수준 구현돼 있다.

반면 다음은 분명히 개선이 필요하다.

- 개발자 계약과 실제 저장소 상태의 drift
- 일부 핵심 모듈의 과도한 복잡도 집중
- outcome-driven self-improvement, canary/shadow, provenance 체계의 미완성

### 최종 결론

- **현재 상태:** 충분히 성숙한 운영형 코드베이스
- **자가개선 성숙도:** **3.9/5.0**, 관리형 폐루프 수준
- **가장 먼저 할 일:** 개발자 계약 정합성 복구 + 핵심 거버넌스 모듈의 점진 분해
- **가장 중요한 다음 단계:** 규칙 기반 self-improvement를 outcome-driven self-improvement로 확장

---

## 7. 부록 — 이번 검토에서 특히 주목한 파일

### 운영/정책 핵심

- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/promotion_gate_mechanism_runtime.py`
- `ops/scripts/mechanism_assess.py`
- `ops/scripts/mechanism_review_candidate_runtime.py`
- `ops/scripts/mechanism_run_validation_runtime.py`
- `ops/scripts/mechanism_run_workspace_runtime.py`
- `ops/scripts/behavior_delta_runtime.py`
- `ops/scripts/filesystem_runtime.py`

### 검증/계약 핵심

- `tests/test_policy_runtime.py`
- `tests/test_mechanism_assess.py`
- `tests/test_promotion_gate_equal_score.py`
- `tests/test_auto_improve_runtime.py`
- `tests/test_release_smoke.py`
- `tests/test_behavior_delta_runtime.py`
- `tests/test_planning_gate_validate_runtime.py`
- `tests/test_wiki_eval_runtime.py`
- `tests/test_wiki_stage2_eval.py`
- `tests/test_wiki_lint_runtime.py`

