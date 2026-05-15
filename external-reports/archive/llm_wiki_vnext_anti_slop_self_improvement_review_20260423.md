# LLM Wiki vNext 현재 코드 정밀 검토 보고서
작성일: 2026-04-23  
작성 목적: 현재 코드베이스를 **anti-slop 관점**과 **자가 개선(self-improvement) 관점**에서 면밀히 검토하고, 실제로 보완해야 할 지점을 우선순위 중심으로 정리한다.

---

## 1. 검토 범위와 접근 방식

이번 검토는 업로드된 현재 작업 트리 기준으로 수행했다. 실제로 훑은 표면은 다음과 같다.

- `ops/scripts/*.py`
- `tests/test_*.py`
- `tools/*.py`
- `pyproject.toml`, `Makefile`, `README.md`, `ARCHITECTURE.md`, `ops/README.md`
- 생성된 운영 아티팩트 일부
  - `ops/reports/auto-improve-readiness.json`
  - `ops/reports/mechanism-review-candidates.json`
  - `ops/reports/mutation-proposals.json`
  - `ops/reports/structural-complexity-budget.json`

반대로, 아래는 **코드 검토의 핵심 범위에서 제외**했다.

- `raw/` 원문 스냅샷의 내용 자체
- `wiki/`, `system/` 문서 본문의 사실성 검토
- 과거 외부 보고서 본문 전체 대조

즉, 이번 보고서는 “저장소 전체의 정보 자산”이 아니라 **현재 동작을 형성하는 Python 런타임과 테스트/정책/생성 보고 체계**를 중심으로 작성했다.

---

## 2. 요약 결론

이 저장소는 단순한 위키 유지 스크립트 모음이 아니라, **지속형 wiki maintainer runtime + meta-maintainer loop + governance artifact 체계**를 한 저장소 안에 밀집시킨 운영형 시스템이다.  
좋은 점은 분명하다. 정책, 스키마, 리포트, 테스트, 런타임 경계가 꽤 잘 드러나 있고, “무엇을 생성하고 어떤 계약을 지키는지”를 명시적으로 다루려는 태도가 강하다.

하지만 현재 시점의 가장 큰 문제는 기능 부족이 아니라 다음 두 가지다.

1. **복잡성 누수(complexity leakage)**  
   모듈 수, 래퍼 수, 생성 산출물 수, 예외 경계, 중복 I/O 패턴이 계속 늘어나면서 “시스템이 자기 설명적이지만 동시에 자기 소음도 함께 증폭”시키고 있다.

2. **자가 개선 루프의 폐쇄성 부족**  
   self-improvement를 위한 후보 탐지, 제안, 실행, 텔레메트리, 결정 기록이 존재하지만, 일부 핵심 경로는 여전히 완전히 닫히지 않았다. 특히 “실험에서 얻은 중요한 결정 정보가 후속 텔레메트리에 완전히 흡수되지 않는 경로”가 실제로 존재한다.

한 문장으로 정리하면 이렇다.

> **이 코드는 ‘질서를 만들려는 시스템’으로서는 강하지만, 그 질서를 유지하는 데 필요한 운영 복잡성이 이미 상당한 수준으로 올라왔고, 일부 자기개선 경로는 아직 제도화보다 수공 패치에 가깝다.**

---

## 3. 정량 스냅샷

이번 점검에서 확인한 현재 규모는 다음과 같다.

- `ops/scripts/*.py`: **150개**
  - 이 중 `_runtime.py`: **104개**
  - 래퍼/엔트리포인트 성격의 파일: **45개**
- `tests/test_*.py`: **105개**
- `tools/*.py`: **5개**
- `ops/scripts` 총 라인 수: **36,096 LOC**
- `tests` 총 라인 수: **27,235 LOC**
- `if __package__ in (None, "")` 직접 실행 fallback 패턴 사용 파일 수: **42개**

가장 큰 런타임 파일 일부:

- `ops/scripts/mutation_proposal_runtime.py` — 921 LOC
- `ops/scripts/filesystem_runtime.py` — 876 LOC
- `ops/scripts/auto_improve_readiness_runtime.py` — 846 LOC
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py` — 762 LOC
- `ops/scripts/policy_validation_runtime.py` — 717 LOC
- `ops/scripts/mechanism_run_workspace_runtime.py` — 708 LOC
- `ops/scripts/codex_exec_executor.py` — 689 LOC

family 기준으로도 `auto_improve`, `mechanism_run`, `promotion_gate`, `finalize_run`, `mechanism_review`가 큰 비중을 차지한다.  
즉, 이 저장소의 복잡성 중심은 문서 생성보다 **자기 운영 메커니즘**에 있다.

---

## 4. 잘한 점

### 4.1 정책/스키마/리포트 중심 운영이 명확하다
`policy_runtime.py`, `schema_runtime.py`, `runtime_context.py`가 핵심 공통층으로 자리 잡고 있고, 대부분의 생성물은 스키마를 통과한 JSON 아티팩트로 남긴다.  
이 방향 자체는 anti-slop에 유리하다. “감으로 처리하는 운영”보다 훨씬 낫다.

### 4.2 테스트 표면이 넓다
테스트 파일 수가 많고, 단순 smoke 수준을 넘어서 contract, schema, export, lint/eval, promotion, auto-improve 흐름까지 건드린다.  
이 점은 현재 시스템이 커진 이유이기도 하지만, 동시에 이 시스템이 아직 버티고 있는 핵심 이유이기도 하다.

### 4.3 경계 의식이 있다
`resolve_repo_output_path`, `allowed_apply_roots`, atomic write, timeout artifact, shadow apply, rollback rehearsal 같은 개념은 “모델이 바꿔도 되는 곳과 바꾸면 안 되는 곳”을 비교적 진지하게 다룬 흔적이다.

### 4.4 운영 문서가 살아 있다
`README.md`, `ARCHITECTURE.md`, `ops/README.md`는 실제 코드와 많이 연결되어 있다.  
문서가 완전히 장식물이 되지 않았다는 점은 이 저장소의 장점이다.

---

## 5. 핵심 문제점과 개선 방향

## 5.1 실제 버그: iteration telemetry가 promotion report의 decision_record를 복구하지 못한다
가장 먼저 고쳐야 할 지점이다.

### 관찰
`ops/scripts/auto_improve_iteration_persistence_runtime.py`의 `write_iteration_telemetry()`는 `decision_record`를 다음 두 곳에서만 가져온다.

- `request.result["decision_record"]`
- 기존 `run-telemetry.json`

문제는 `request.result`에 `decision_record`가 없고 대신 `promotion_report` 경로만 있는 경우다.  
현재 구현은 그 `promotion-report.json` 안에 들어 있는 `decision_record`를 다시 읽어오지 않는다.

### 근거
- `ops/scripts/auto_improve_iteration_persistence_runtime.py:187-214`
- 실제로 저장소에는 이 문제를 보완하려는 수동 패치 스크립트 `tools/manual_mutate_auto_improve_decision_record_fallback.py`가 들어 있다.
- 그런데 현재 런타임 본체에는 그 보완 로직이 반영되어 있지 않다.

### 재현 결과
로컬 재현에서 아래 상황을 만들었을 때:

- `runs/<run-id>/promotion-report.json` 안에는 `decision_record`가 존재
- `write_iteration_telemetry()` 호출 시 `result`에는 `promotion_report` 경로만 전달
- `result["decision_record"]`는 비어 있음

최종 `run-telemetry.json`에는 `decision_record`가 **누락**됐다.

### 왜 중요한가
이건 단순 필드 누락이 아니다.

- self-improvement loop의 핵심은 “실험 → 판정 → 기록 → 다음 후보 생성”의 닫힌 고리다.
- `decision_record`가 중간에 증발하면 이후 calibration, trend, retrospective, audit에서 실험의 실질적 의미가 약화된다.
- 즉, **self-improvement가 자신이 배운 것을 완전히 보존하지 못하는 상태**다.

### 권장 수정
P0로 즉시 수정해야 한다.

1. `write_iteration_telemetry()`에 `_iteration_decision_record()` helper를 추가한다.
2. `result["decision_record"]`가 없을 때 다음 순서로 fallback 한다.
   - 기존 telemetry
   - `result["promotion_report"]` 경로
   - `runs/<run-id>/promotion-report.json`
3. 이 경로를 고정하는 회귀 테스트를 추가한다.
   - 현재 `tests/test_auto_improve_iteration_runtime.py`에는 이 케이스가 없다.

### anti-slop 관점 평가
이 버그는 “정보가 있는데도 최종 canonical artifact에 흡수되지 않는 문제”다.  
이런 종류의 누락은 사람이 문서를 읽을 때도 헷갈리고, LLM이 후속 작업할 때도 문맥 품질을 크게 떨어뜨린다.

---

## 5.2 엔트리포인트 구조가 anti-slop에 불리하다
현재 `pyproject.toml`에는 `[project.scripts]`가 없다.  
대신 `ops/direct-script-entrypoints.txt`로 직접 실행 표면을 따로 관리하고, 실제 코드에서는 `if __package__ in (None, "")` fallback 패턴을 **42개 파일**에서 반복한다.

### 관찰
- `pyproject.toml:1-57`
- `ops/direct-script-entrypoints.txt:1-42`
- 직접 실행 fallback 패턴 다수

### 문제
이 패턴은 동작은 하지만 장기적으로는 slop를 만든다.

- import fallback boilerplate가 반복된다
- CLI boundary 오류 처리 방식이 파일마다 조금씩 달라질 수 있다
- “직접 실행 호환성”이라는 부가 관심사가 본래의 런타임 로직에 스며든다
- 패키징 표준과 저장소 내부 계약이 이중화된다

즉, 현재는 **표준적인 packaging entry point**와 **저장소 내부 entrypoint registry**를 둘 다 안고 있다.

### 권장 수정
P1 우선순위다.

1. `[project.scripts]` 또는 `console_scripts` 기반으로 canonical CLI를 만든다.
2. 지금의 wrapper 파일들은 최대한 얇게 유지하거나 자동 생성한다.
3. `direct-script-entrypoints.txt`는 transitional artifact가 아니라면 제거하고, 남길 거면 생성식으로 바꾼다.
4. 공통 CLI 예외 처리, JSON 출력, `--vault` 해석, `--out` 처리 로직을 공용화한다.

### anti-slop 관점 평가
이건 “당장 깨지는 버그”는 아니다.  
하지만 **반복되는 boundary code는 시간이 지나면 거의 항상 drift를 만든다.**  
지금이 정리하기 좋은 시점이다.

---

## 5.3 complexity budget이 존재하지만, 실제 hot spot을 충분히 제어하지 못한다
`ops/reports/structural-complexity-budget.json`은 pass 상태다.  
하지만 diagnostics를 보면 `function_budget_top_n.total_candidate_count`가 **26**이고, 모두 unmonitored candidate다.

### 관찰
- `ops/reports/structural-complexity-budget.json:1-120`
- summary상 monitored target은 pass
- diagnostics상 unmonitored function budget candidate 다수 존재

### 해석
즉, 지금의 complexity governance는 “중요하다고 이미 지정한 파일들”은 보고 있지만,  
실제로 부풀고 있는 함수/테스트 fixture는 상당 부분 **관찰은 되지만 통제는 안 되는 상태**다.

특히 다음 성격의 표면이 크다.

- giant test seeding 함수
- orchestration helper 내부 대형 함수
- artifact assembly 함수
- review/calibration/report builder 계층

### 문제
이 상태는 anti-slop 측면에서 위험하다.

- “예산 제도는 있는데 실제 문제는 예산 바깥에 있음”
- 개발자는 pass 보고서를 보고 안심하지만, 복잡성은 다른 표면으로 우회 성장함
- 결국 monitored surface만 슬림해지고, supporting surface가 비대해지는 왜곡이 생긴다

### 권장 수정
P1로 추천한다.

1. `diagnostics.function_budget_top_n` 상위 후보를 **다음 라운드 monitored set**으로 순환 편입한다.
2. 테스트도 “예외”가 아니라 “운영 품질 자산”으로 보고 function budget을 별도로 관리한다.
3. giant fixture builder는 builder object 또는 scenario fragment로 분해한다.
4. touched-file 기준 hard gate를 더 적극적으로 사용한다.

### 자가 개선 관점 평가
자가 개선 루프가 복잡성을 줄이려면, 복잡성 측정이 실제 hotspot을 겨냥해야 한다.  
지금 구조는 방향은 맞지만 coverage가 아직 부분적이다.

---

## 5.4 auto-improve readiness의 PASS가 실제 운영 정체를 충분히 반영하지 못한다
현재 생성된 후보/제안 리포트를 보면 self-improvement loop는 이미 특정 표면에서 정체 신호를 감지하고 있다.

### 관찰
`ops/reports/mechanism-review-candidates.json`에 따르면:

- 최근 comparable run history는 확보됨
- `auto_improve_iteration_persistence_runtime.py` 관련 후보 1개가 생성됨
- 최근 여러 run에서 `stage1_same_eval_rate`가 누적됨
- `session_calibration.status`는 `no_session_context`

`ops/reports/mutation-proposals.json`도 이 후보를 그대로 proposal로 내보낸다.

### 문제
이 상황은 “준비됨(pass)”이면서 동시에 “실제로는 같은 표면에서 계속 정체 중”이라는 뜻이다.  
readiness가 현재는 **실행 가능 여부**에 더 가깝고, **개선 잠재력/정체 위험**을 충분히 fail-closed로 반영하지는 않는다.

### 왜 중요한가
self-improvement 시스템에서 가장 위험한 상태는 “아무것도 못하는 상태”보다 “계속 돌아가지만 별로 배우지 못하는 상태”다.  
후자는 운영자에게 착시를 준다.

### 권장 수정
P1~P2 범위에서 다음을 제안한다.

1. readiness에 stagnation shadow gate를 추가한다.
   - 최근 N회 동일 eval + discard/HOLD 누적 시 PASS를 그대로 주지 말고 WARN 강화
2. `session_calibration.status = no_session_context`가 반복되면 별도 operator action을 요구한다.
3. “runnable proposal 존재”와 “최근 실제 개선 발생”을 구분하는 요약치를 상단에 노출한다.
4. readiness에서 `next best intervention`을 더 직접적으로 제시한다.
   - 예: “새 실험 실행”이 아니라 “decision_record propagation bug 먼저 해결 후 재시도”

### anti-slop 관점 평가
지금은 governance artifact가 많지만, 그 중 일부는 operator에게 “상황은 괜찮다”는 느낌을 줄 수 있다.  
좋은 리포트는 많을수록 좋은 게 아니라, **실제 행동을 바꾸는 리포트**여야 한다.

---

## 5.5 생성 산출물과 보고서가 너무 많아 문맥 오염 위험이 크다
현재 트리에는 다음이 존재한다.

- `ops/reports/` 파일 다수
- `external-reports/` 파일 다수
- `runs/` 디렉터리 아래 다수의 run artifact
- review archive/과거 보고서 흔적

### 문제
이건 운영 기록 측면에서는 장점이 있지만, anti-slop 관점에서는 분명한 비용이 있다.

- 코드 리뷰 시 현재 canonical surface와 과거 artifact가 섞인다
- 사람이 “진짜 소스 오브 트루스”를 헷갈리기 쉽다
- LLM 기반 유지보수에서는 더 치명적이다  
  비슷한 이름의 보고서/중간산출물이 많으면 잘못된 파일을 읽거나, 오래된 판단을 최신 상태로 오인할 가능성이 커진다

### 권장 수정
P1로 강하게 권장한다.

1. generated artifact의 역할을 **운영용 / 감사용 / 참고용**으로 등급화한다.
2. 저장소 루트에서 현재 작업에 직접 필요한 canonical generated artifact만 남긴다.
3. 나머지는 `archive/` 또는 별도 저장소/스토리지로 내린다.
4. `external-reports/`는 누적형 폴더가 아니라 “최신 canonical report + archive” 구조로 바꾼다.
5. 파일명 규칙에 `latest` alias 또는 index를 둬서 사람/에이전트가 최신본을 즉시 식별하게 한다.

### 자가 개선 관점 평가
self-improvement 시스템은 스스로 생성한 산출물에 파묻히기 쉽다.  
지금 구조는 이미 그 초기 징후가 보인다.

---

## 5.6 수동 mutate 스크립트가 “제도화되지 않은 학습”을 보여준다
`tools/manual_mutate_auto_improve_decision_record_fallback.py`와  
`tools/manual_mutate_auto_improve_timeout_telemetry.py`는 매우 중요한 신호다.

### 해석
이 파일들은 단순 도구가 아니라 다음을 의미한다.

- self-improve loop가 잡아낸 문제를 사람이 수동 패치하는 경로가 존재한다
- 그런데 그 수정 지식이 항상 canonical runtime과 테스트에 완전히 흡수되지는 않는다
- 즉, **“학습은 일어났는데 체계에 완전히 제도화되지 않았다”**는 뜻이다

실제로 timeout telemetry 쪽 변화는 현재 런타임에 반영된 반면, decision record fallback 쪽은 완전히 닫히지 않았다.

### 권장 수정
P0~P1 범위다.

1. manual mutate script를 “임시 도구”가 아니라 **defect knowledge registry의 입력물**로 취급한다.
2. 각 수동 패치에 대해 다음이 자동으로 남아야 한다.
   - defect class
   - affected target
   - canonical fix status
   - regression test status
   - promotion to policy/runtime 여부
3. unresolved manual patch는 readiness 또는 mechanism review에서 별도 신호로 올린다.

### anti-slop 관점 평가
수동 패치는 나쁜 것이 아니다.  
문제는 **패치가 학습되었는지, 아니면 그냥 지나갔는지**다.  
지금은 둘이 섞여 있다.

---

## 5.7 JSON artifact I/O 패턴이 곳곳에 반복되어 drift 여지가 있다
현재 여러 모듈에서 JSON 로드/쓰기 패턴이 반복된다.

- 직접 `json.loads(path.read_text(...))`
- 직접 `write_output_text(..., json.dumps(...))`
- 개별 모듈마다 `_read_json`, `_load_json_object`, `load_optional_json` 등 유사 helper 사용

### 문제
이건 지금 당장은 읽기 쉬워 보여도 장기적으로는 anti-slop에 불리하다.

- newline 정책, indent 정책, schema validate 시점, optional field 처리, decode error 메시지가 조금씩 달라질 수 있다
- artifact class가 늘수록 helper도 늘어난다
- “데이터 계약”보다 “파일별 습관”이 우세해진다

### 권장 수정
P1로 추천한다.

1. artifact I/O layer를 더 명시적으로 만든다.
   - read_json_object
   - write_schema_validated_json
   - load_optional_schema_validated_json
2. `artifact class -> schema -> path policy -> writer policy`를 registry화한다.
3. 각 report writer에서 공통 formatter, validate, path guard를 재사용한다.

### 자가 개선 관점 평가
LLM/agent가 다루는 코드일수록 반복 패턴은 줄이고 canonical helper를 늘리는 편이 낫다.  
그게 모델의 수정 정확도도 높인다.

---

## 5.8 테스트는 많지만, “실패가 일어났던 자리”를 고정하는 회귀 테스트가 더 필요하다
테스트 수는 충분히 많다. 문제는 양보다 **결함 기억의 정확성**이다.

### 관찰
현재 `tests/test_auto_improve_iteration_runtime.py`는 다음은 검증한다.

- preserved fields contract
- workspace/apply field 보존
- timeout 관련 nested merge

하지만 이번 점검에서 재현한 핵심 문제인  
“promotion report path만 있을 때 decision_record를 telemetry로 복구하는가”는 검증하지 않는다.

### 의미
즉, 테스트가 많아도 “실제 넘어졌던 지점”을 정확히 못 박지 못하면 self-improvement 품질은 제한된다.

### 권장 수정
P0다.

아래 종류의 regression test를 즉시 추가하길 권한다.

1. `promotion_report` 경유 `decision_record` 복구
2. 수동 mutate script가 겨냥한 모든 defect class의 고정 테스트
3. readiness PASS/WARN이 stagnation context에 따라 바뀌는지 검증
4. generated artifact canonical path 선택 규칙 검증

---

## 6. anti-slop 중심 보완안

여기서는 “출력 품질 저하, 문맥 오염, 중복, drift”를 줄이는 방향만 따로 묶는다.

### 6.1 엔트리포인트 정규화
- `[project.scripts]` 도입
- wrapper 자동 생성 또는 공통 CLI runner 도입
- `if __package__ ...` fallback 축소

### 6.2 canonical artifact 축소
- 최신본 1개 + archive 구조
- review/report naming 정규화
- operator용 최신 인덱스 파일 제공

### 6.3 defect-to-test-to-policy 연결
- 수동 패치 스크립트를 defect registry 입력으로 승격
- unresolved defect는 readiness에서 경고
- fixed defect는 regression test 없으면 close 금지

### 6.4 helper canonicalization
- JSON I/O helper 통합
- schema validate/write policy 통합
- path guard와 artifact write를 한 곳으로 모음

### 6.5 complexity governance 실효화
- monitored target 확대
- touched file 기반 hard gate 강화
- giant test fixture도 예산 관리 포함

---

## 7. 자가 개선 중심 보완안

여기서는 “실험이 실제로 학습으로 이어지게 만드는 구조”만 본다.

### 7.1 decision provenance를 절대 잃지 않게 만들 것
self-improvement 시스템은 “무슨 판단이 왜 내려졌는가”를 잃으면 안 된다.  
`decision_record` 누락은 이 원칙을 정면으로 위반한다.

### 7.2 readiness를 실행 가능성만이 아니라 개선 가능성까지 보게 만들 것
- runnable proposal 있음 = PASS
- 최근 개선 없음 = 여전히 PASS  
이 구조는 너무 느슨하다.

readiness는 최소한 아래 두 축을 같이 보여야 한다.

- can run?
- likely to learn?

### 7.3 audit-only metric을 shadow gate로 승격할 준비를 할 것
현재 outcome metrics calibration은 `audit_only`, `gate_effect: none`이다.  
이건 좋은 시작이지만 영원히 audit-only로 남기면 운영을 바꾸지 못한다.

권장 단계:

1. audit-only
2. shadow gate
3. WARN gate
4. strict gate

### 7.4 “반복 실패 family”를 defect family로 재정의할 것
현재도 family 개념이 있지만, 더 실전적으로 바꿀 수 있다.

예:
- telemetry absorption failure
- promotion decision provenance loss
- equal-score stagnation
- report proliferation
- boundary duplication
- helper sprawl

이 family가 있으면 mechanism review도 더 구체적이 된다.

### 7.5 self-improvement의 개선 단위를 더 작게 만들 것
현재 보고서와 proposal도 “한 번에 하나의 mechanism”을 강조하고 있지만, 실제 운영에서는 여전히 supporting target과 artifact layer가 얽혀 있다.  
앞으로는 개선 단위를 더 작게 쪼개야 한다.

- 한 번에 필드 하나
- helper 하나
- report writer 하나
- fallback 하나

이 수준으로 내려가야 same-eval stagnation을 줄이기 쉽다.

---

## 8. 우선순위 실행 계획

## P0 — 즉시 수정
1. `write_iteration_telemetry()`의 `decision_record` fallback 복구
2. 해당 회귀 테스트 추가
3. unresolved manual mutate 지식과 canonical runtime 상태 대조
4. self-improvement 관련 canonical defect 목록 작성

## P1 — 이번 주 안에 정리
1. CLI/entrypoint 구조 정규화 계획 수립
2. artifact I/O helper 통합 시작
3. complexity monitored target 확대
4. report/archive 정리 기준 정의
5. readiness에 stagnation shadow signal 추가

## P2 — 다음 라운드 개선
1. audit-only metrics의 shadow gate 운영
2. defect family 기반 mechanism review 고도화
3. giant test seed 함수 분해
4. external report 최신본 alias/index 도입

---

## 9. 가장 추천하는 첫 작업 순서

현재 상태에서 가장 효과 대비 리스크가 낮은 순서는 아래다.

### 1단계
`auto_improve_iteration_persistence_runtime.py`의 decision_record fallback 수정  
→ 이건 실제 버그이며 self-improvement의 기억 보존 문제다.

### 2단계
해당 버그를 고정하는 테스트 추가  
→ “이번에 발견한 문제”를 시스템 기억으로 바꾼다.

### 3단계
manual mutate script를 defect registry 입력물로 승격  
→ 사람의 수동 학습이 저장소 운영 규칙에 들어오게 만든다.

### 4단계
entrypoint/CLI 정규화 설계  
→ 장기 anti-slop 비용을 줄인다.

### 5단계
artifact/report 최신본 중심 정리  
→ 이후 LLM/인간 리뷰 품질이 좋아진다.

---

## 10. 최종 평가

이 저장소는 대충 만든 시스템이 아니다.  
오히려 **너무 많은 운영 질서를 짧은 시간 안에 한 저장소에 밀도 높게 올린 시스템**에 가깝다.  
그래서 지금의 핵심 리스크는 무질서가 아니라 **과잉 구조가 만드는 문맥 혼잡과 자기개선 경로의 미세 누락**이다.

정리하면:

- **설계 철학은 좋다.**
- **운영 계약도 꽤 잘 보인다.**
- **테스트와 스키마도 분명히 강점이다.**
- 하지만
  - 일부 핵심 정보 흡수 경로가 아직 완전히 닫히지 않았고,
  - 엔트리포인트/아티팩트/I/O/helper 계층에 anti-slop 부채가 누적되고 있으며,
  - self-improvement loop는 “돌아간다”와 “실제로 배운다” 사이에 아직 간극이 있다.

따라서 이 코드베이스의 다음 목표는 기능 추가가 아니라 다음 한 줄이어야 한다.

> **생성하는 시스템이 스스로 만든 산출물과 예외 경계에 압도되지 않도록, canonical 경로를 더 줄이고, 학습이 실제로 보존되는 폐쇄 루프를 완성하라.**

---

## 부록 A. 이번 검토에서 특히 중요하게 본 파일

- `ops/scripts/auto_improve_iteration_persistence_runtime.py`
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/auto_improve_readiness_runtime.py`
- `ops/scripts/mutation_proposal_runtime.py`
- `ops/scripts/codex_exec_executor.py`
- `ops/scripts/filesystem_runtime.py`
- `ops/scripts/policy_runtime.py`
- `ops/scripts/policy_validation_runtime.py`
- `ops/direct-script-entrypoints.txt`
- `pyproject.toml`
- `tests/test_auto_improve_iteration_runtime.py`
- `tools/manual_mutate_auto_improve_decision_record_fallback.py`

## 부록 B. 샘플 점검 메모

- 저장소는 정책/스키마/리포트 기반 운영을 이미 상당히 진지하게 수행하고 있다.
- 생성 보고서와 review artifact가 많아 anti-slop 관점에서는 정리가 필요하다.
- self-improvement가 겨냥하는 현재 hotspot은 `auto_improve_iteration_persistence_runtime.py` 계열이며, 실제로 거기서 결정 기록 누락을 재현했다.
- 따라서 이번 라운드의 최우선 과제는 “새로운 기능”이 아니라 **telemetry/provenance 폐쇄성 보강**이다.
