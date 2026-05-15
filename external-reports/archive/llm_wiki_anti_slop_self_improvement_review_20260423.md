# LLM Wiki vNext 코드 리뷰 보고서
작성일: 2026-04-23  
대상 번들: `LLM Wiki vNext(26).zip`  
관점: **anti-slop** + **자가 개선(self-improvement)**

---

## 1. 검토 목적과 기준

이 보고서는 현재 코드베이스를 **“작동은 하지만 신뢰도와 학습 효율이 조금씩 침식되는 상태”**로 보지 않기 위해, 다음 두 축에서 점검한 결과를 정리한다.

### 1-1. Anti-slop 기준
여기서 anti-slop은 단순한 코드 스타일 정리가 아니라, 아래와 같은 현상을 줄이는 방향을 뜻한다.

- 출력물은 많지만 **행동 폐쇄(action closure)** 가 약한 구조
- 정책/리포트/가드가 많지만 실제로는 **거짓 통과(false pass)** 혹은 **거짓 실패(false fail)** 를 만들 수 있는 구조
- 문자열 규칙, 템플릿 표식, 운영 관습에 지나치게 의존해 **의미 구조가 코드에 고정되지 않은 상태**
- 진단 파일이 누적되지만 운영자가 **무엇을 먼저 고쳐야 하는지 선명하지 않은 상태**
- 테스트와 런타임이 서로를 보호하기보다 **복잡도를 같이 끌어올리는 상태**

### 1-2. 자가 개선 기준
자가 개선 관점에서는 아래를 중점적으로 봤다.

- 시스템이 실제로 **학습 가능한 피드백 루프**를 가지는가
- “개선 제안 생성”과 “개선의 효과 검증”이 **같은 언어/같은 단위**로 이어지는가
- 실행기(executor), 리뷰기(reviewer), 정책(policy), 리포트(report)가 서로 **측정 가능한 상태 전이**를 공유하는가
- 개선 시도 수가 늘어날수록 운영 비용이 선형이 아니라 **폭발적으로 증가하지 않는가**

---

## 2. 검토 범위와 방법

### 2-1. 번들 구성 요약
압축 번들 기준 대략 다음과 같은 구성이 확인됐다.

- 전체 파일 수: **약 1,890개**
- 추출/검토 대상 핵심 파일: **약 901개**
- Python 파일 수: **272개**
- Markdown 파일 수: **931개**
- JSON 파일 수: **208개**
- `.pyc` 파일 수: **275개**

상위 디렉터리 분포는 대체로 다음과 같다.

- `ops/` : 런타임/정책/리포트/실행 제어 중심
- `wiki/` : 지식 코퍼스
- `tests/` : 회귀/정책/가드 테스트
- `system/` : 시스템 코퍼스/레지스트리/운영 문맥
- `runs/`, `external-reports/`, `raw/` : 실행 흔적, 외부 보고서, 원본 스냅샷

### 2-2. 수행한 점검
다음 작업을 수행했다.

1. 압축 파일 구조와 코드 분포를 전수 스캔
2. 핵심 런타임 모듈의 길이/함수 수/복잡도 근사치 분석
3. 테스트 일부를 직접 실행하여 재현 가능한 실패 여부 확인
4. 주요 리포트 JSON을 열어 **“현재 시스템이 스스로 무엇을 알고 있는지”** 확인
5. anti-slop 및 self-improvement 관점에서 우선순위를 재정렬

---

## 3. 핵심 결론 요약

현재 코드베이스는 **“정책과 가드, 리포트, 자기 점검 장치가 매우 풍부한 운영형 시스템”** 이다. 단순한 장난감 수준은 이미 넘어섰고, 파일 시스템 안전성·원자적 쓰기·적용 경계 검증 같은 부분은 꽤 잘 되어 있다.

하지만 동시에 아래의 문제가 분명하다.

### 결론 A. “자가 개선 시스템”의 겉모습은 충분하지만, 실제 학습 증거는 아직 얕다.
현재 readiness는 `pass` 이지만, 실제 근거는 얇다.

- `attempts_considered = 7`
- `min_attempts_considered = 10` 미달
- `session_reports_considered = 0`
- `session_calibration.status = no_session_context`

즉, 시스템은 **“돌릴 수 있음(can run)”** 과 **“배울 가능성이 높음(likely to learn)”** 을 분리하려는 좋은 방향을 갖고 있지만, 아직은 **학습 증거보다 운영 준비 신호가 앞서 있다**.

### 결론 B. 복잡도 관리 장치는 존재하지만, 아직 “모니터링 범위 밖”이 넓다.
`structural-complexity-budget.json` 기준으로:

- 함수 예산 후보 총수: `27`
- 모니터링 중 후보: `1`
- 모니터링 밖 후보: `26`
- 게이트 효과: `preview`

즉, 복잡도 거버넌스는 이미 설계돼 있지만, **실제로는 관찰만 하고 아직 제어하고 있지 못한 상태**다.

### 결론 C. 가장 위험한 slop은 “문자열/리포트/딕셔너리 조립” 중심 오케스트레이션이다.
특히 다음 유형이 반복된다.

- `dict[str, Any]` 기반 대형 payload 조립
- 여러 리포트를 읽어 상태를 다시 조합하는 대형 함수
- 템플릿 마커/헤딩 문자열로 품질을 판정하는 검증기
- CLI wrapper가 많은데, 공통 인터페이스보다 파일별 wrapper가 늘어나는 구조

이 패턴은 초기에 빠르지만, 시스템이 커질수록 다음 문제가 생긴다.

- 의미 단위가 타입으로 고정되지 않음
- 상태 전이가 문서/관습/키 이름에 숨어버림
- 수정 시 연쇄적으로 리포트 포맷이 흔들림
- “보고서가 많아질수록 오히려 현재 상태가 덜 선명해지는” 역설 발생

### 결론 D. 지금 가장 먼저 손봐야 할 것은 “거짓 실패를 만드는 실행 래퍼”다.
`ops/scripts/command_runtime.py` 와 `tests/test_command_runtime.py`를 보면, 정상 종료해야 하는 짧은 Python 프로세스가 현재 재현 환경에서 timeout 처리로 떨어진다. 이 계층은 실행기, 검증기, 자동화 루프의 하부 공통 의존성에 가깝기 때문에, 여기의 오동작은 전체 self-improvement 파이프라인에 **노이즈를 주입하는 기반 결함**이 된다.

---

## 4. 잘 되어 있는 점

이 프로젝트는 문제만 있는 코드베이스가 아니다. 오히려 “어디까지는 이미 잘하고 있는지”를 분리해서 보는 것이 중요하다.

### 4-1. 파일 시스템 안전성은 강점이다
`ops/scripts/filesystem_runtime.py`는 이 코드베이스에서 가장 인상적인 부분 중 하나다.

강점:

- 임시 파일 staging 후 `os.replace`로 커밋
- 다중 파일 쓰기 시 rollback 고려
- duplicate target path 검출
- symlink segment 차단
- root escape 방지
- changed-files manifest에 대한 허용 루트 검증

이 계층은 anti-slop 관점에서 매우 중요하다. “LLM이 제안한 변경”을 다루는 시스템은 **파일 적용 경계가 느슨하면 바로 신뢰를 잃기 때문**이다.

### 4-2. readiness에서 `can_run`과 `likely_to_learn`를 분리한 발상은 좋다
`auto_improve_readiness_runtime.py`의 shadow gate 철학은 매우 좋다.  
많은 자가 개선 시스템이 “실행 가능”과 “학습 가치가 있음”을 혼동하는데, 여기서는 이를 구분하려는 흔적이 있다.

이 방향은 계속 살려야 한다.

### 4-3. 리포트 중심 운영 체계는 재현성과 감사성 측면에서 유리하다
`ops/reports/*.json`이 풍부하다는 사실 자체는 단점만은 아니다.

장점:

- 특정 시점 상태를 재현하기 쉽다
- 자동화 루프의 의사결정 근거를 남길 수 있다
- 회귀 추적이 가능하다
- 사람 리뷰어가 개입할 지점을 잡기 쉽다

다만 지금은 **“리포트 생성”은 충분히 발달했지만, “리포트 감축 및 통합”은 아직 약한 상태**다.

---

## 5. 가장 시급한 문제들

## 5-1. P0 — `command_runtime`의 timeout 래퍼 오동작 가능성
### 관찰
- 파일: `ops/scripts/command_runtime.py`
- 관련 테스트: `tests/test_command_runtime.py`
- `run_with_timeout([sys.executable, "-c", "print('ok')"], timeout_seconds=5)` 가 기대상 정상 종료여야 하나, 현 재현에서는 timeout 분기로 빠져 `returncode=-15`, `timed_out=True` 형태로 확인됐다.
- 테스트는 `result.returncode == 0`, `stdout == "ok\n"`, `timed_out == False` 를 기대한다.

### 왜 위험한가
이 계층은 **“외부 명령 실행의 참/거짓”** 을 판정하는 하부 공통 모듈이다.  
여기서 거짓 timeout이 생기면:

- 정상 개선 시도를 실패로 기록할 수 있다
- 자동 개선 루프가 잘못된 rollback / hold / discard 판단을 할 수 있다
- outcome metrics가 왜곡된다
- self-improvement 시스템이 **실패를 학습하는 것이 아니라 측정 오류를 학습**하게 된다

### 개선 권장
1. `run_with_timeout()`을 **platform-specific backend**로 분리
   - POSIX 프로세스 그룹 처리
   - Windows 처리
   - 테스트용 fake backend
2. timeout 판정 전에
   - `poll()` 확인
   - 종료 race condition 재검사
   - first timeout 이후 짧은 재시도(read drain) 추가
3. `start_new_session` + `killpg` 조합의 환경 민감성에 대해 별도 테스트 매트릭스 구축
4. 실행 결과를 `returncode/timed_out/termination_reason`만 보지 말고
   - `launch_succeeded`
   - `stdout_received`
   - `signal_sent`
   - `final_state_observed`
   로 분해 기록
5. “timeout wrapper 신뢰성” 자체를 검증하는 독립 테스트 세트 추가

### 판단
이건 단순한 테스트 깨짐이 아니라 **자가 개선 루프의 센서 오염** 문제다.  
최우선(P0)으로 수정해야 한다.

---

## 5-2. P0 — readiness가 `pass`여도 학습 증거는 아직 부족함
### 관찰
`ops/reports/auto-improve-readiness.json`의 상태는 `pass`이지만, diagnostics에는 다음이 드러난다.

- `attempts_considered=7` < `min_attempts_considered=10`
- `session_reports_considered=0`
- `session_calibration.status=no_session_context`
- `likely_to_learn=False`
- `can_run=True`

### 왜 위험한가
이 상태는 운영적으로는 “실행 가능”일 수 있다.  
하지만 자가 개선 관점에서는 아직 아래 문제가 남아 있다.

- 제안 생성은 되는데 **session rollup이 없다**
- 어떤 제안이 실제로 학습 가치가 있었는지 **증거 축적이 부족하다**
- 결과적으로 시스템이 “proposal emission machine”이 될 위험이 있다

### 개선 권장
1. readiness 최상위 상태를 단일 `pass/fail`로 두지 말고 최소 2축으로 노출
   - `operational_readiness`
   - `learning_readiness`
2. queue non-empty이면 실행 가능하다는 판단과 별개로,
   - 학습 증거 부족
   - 세션 문맥 부재
   - outcome metrics 미성숙
   를 **상위 요약에 더 강하게 노출**
3. auto-improve 세션 완료 시 반드시
   - proposal
   - execution
   - review
   - final outcome
   - follow-up state
   가 한 개의 **session envelope**로 연결되도록 구조화
4. `session_reports_considered=0` 상태를 단순 warn이 아니라
   - live trial 가능
   - promotion 금지
   - learning evidence incomplete
   같은 더 직접적인 운영 의미로 표현

### 판단
현재 구조는 좋은 방향으로 설계돼 있으나, 아직은 **실행 준비성과 학습 준비성을 혼동할 여지**가 남아 있다.

---

## 5-3. P1 — 대형 오케스트레이션 함수가 너무 많은 책임을 가진다
### 주요 후보
- `ops/scripts/auto_improve_readiness_runtime.py::build_readiness_report`
- `ops/scripts/codex_exec_executor.py::execute_codex_exec_role`
- `ops/scripts/observability_routing_provenance_runtime.py::build_routing_provenance_aggregate`
- `ops/scripts/mechanism_review_history_runtime.py::load_mechanism_run_snapshots`
- `ops/scripts/mechanism_review_session_calibration_runtime.py::session_calibration_summary`

### 공통 문제
이 함수들은 대체로 다음을 한 번에 수행한다.

- 여러 리포트 읽기
- 보조 진단 계산
- 상태 판정
- 요약 문자열 조합
- JSON payload 생성
- sometimes 파일 기록까지 연결

이 패턴의 문제는 다음과 같다.

1. **상태 전이와 표현 계층이 섞임**
2. 결과 payload가 `dict[str, Any]`로 흘러 다님
3. 한 함수 수정이 여러 리포트 포맷 변경으로 이어질 수 있음
4. 테스트가 “의미 검증”보다 “필드 존재 검증” 중심이 되기 쉬움

### 개선 권장
각 대형 함수를 최소 다음 레벨로 분리하라.

- `load_*`: 입력 로드
- `compute_*`: 도메인 계산
- `assess_*`: 판정/등급화
- `render_*`: JSON/Markdown 표현
- `persist_*`: 파일 쓰기

그리고 각 단계의 반환형을 `dataclass(frozen=True)` 또는 명시적인 얇은 타입 객체로 고정하라.

예시:

```python
@dataclass(frozen=True)
class LearnabilityAssessment:
    can_run: bool
    likely_to_learn: bool
    reasons: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    attempts_considered: int
    session_reports_considered: int
```

이렇게 해야 리포트 키 이름이 아니라 **의미 단위**가 중심이 된다.

---

## 5-4. P1 — 문자열 마커 기반 품질 검증은 초기에 유용하지만 장기적으로 취약하다
### 관찰
`ops/scripts/raw_intake_promotion_validation_runtime.py`는 다음과 같은 문자열 표식을 이용해 품질을 검사한다.

- `SYNTHESIS_ANALYSIS_TEMPLATE_MARKERS`
- `SYNTHESIS_FOLLOW_UP_SPLIT_MARKERS`
- `CONCEPT_CONTINUITY_MARKERS`
- `CONCEPT_SPLIT_CONTINUITY_HEADINGS`

### 왜 위험한가
이 방식은 빨리 만들 수 있지만, 시간이 지나면 아래 문제가 생긴다.

- 표현 방식이 바뀌면 의미는 맞아도 validator가 실패
- 반대로 문구만 맞추면 의미는 빈약한데 통과 가능
- 한국어/영어/표현 다변화에 약함
- 결국 “좋은 글”이 아니라 “validator를 만족시키는 글”을 유도할 수 있음

이건 anti-slop 관점에서 매우 중요하다.  
**형식적 표식이 의미를 대체하면 slop이 시스템 내부 규칙으로 굳어진다.**

### 개선 권장
1. 텍스트 마커 검증은 보조 신호로 격하
2. 핵심 검증은 구조 필드로 전환
   - `analysis_blocks[*].purpose`
   - `bridge_integration.kind`
   - `continuity_resolution.status`
   - `follow_up_question_count`
3. prose 검사와 구조 검사 분리
   - structure gate
   - prose heuristic gate
4. validator 에러 타입을
   - `schema_error`
   - `semantic_contract_error`
   - `heuristic_warning`
   로 분리

---

## 5-5. P1 — 테스트 픽스처 자체가 너무 커져서 테스트의 설명력이 떨어진다
### 관찰
`tests/minimal_vault_runtime.py::seed_minimal_vault`는 매우 길다.  
구조를 한 번에 생성하는 데는 편리하지만, 테스트 실패 원인을 국소화하기 어렵다.

### 왜 위험한가
픽스처가 너무 크면 다음 현상이 생긴다.

- 실패가 발생해도 “테스트 대상”보다 “픽스처 세계관”을 먼저 이해해야 한다
- 작은 정책 변화가 많은 테스트를 연쇄적으로 깨뜨린다
- fixture는 재사용되지만 의미는 재사용되지 않는다
- 결과적으로 테스트가 **설명 문서가 아니라 환경 생성 스크립트**가 된다

### 개선 권장
`seed_minimal_vault()`를 다음 수준으로 쪼개라.

- `seed_system_index()`
- `seed_raw_registry()`
- `seed_fake_source()`
- `seed_fake_concept()`
- `seed_fake_query()`
- `seed_fake_synthesis()`
- `seed_default_policy()`

그리고 테스트에서 필요한 블록만 조합해서 쓰게 하라.  
지금처럼 거대한 기본 세계를 한 번에 넣으면 anti-slop이 아니라 **fixture slop**이 된다.

---

## 5-6. P1 — 보고서와 산출물이 많아졌는데, 정리보다 생성이 앞서 있다
### 관찰
`ops/reports/generated-artifact-index.json` 기준:

- `external_reports_root_file_count = 15`
- `canonical_report_count = 31`
- `archive_candidate_count = 13`

또한 번들에는 이미 다수의 코드 리뷰/자기개선 관련 보고서가 누적되어 있다.

### 왜 위험한가
이 시스템은 자기 점검에 적극적이다. 하지만 현재는:

- 새 리포트가 계속 생김
- 어떤 리포트가 canonical인지 이미 정의는 있으나
- 실사용자는 여전히 root-level artifact를 여러 개 보게 됨
- 결국 “리포트가 많을수록 현재 상태 파악이 쉬워지는 것”이 아니라  
  “리포트가 많을수록 최신 판단이 흐려지는 것”이 된다

### 개선 권장
1. 생성보다 감축 규칙을 먼저 강화
2. 동일 목적 보고서는 latest-canonical 하나만 root에 남기고 나머지는 자동 archive
3. 리포트마다 `supersedes`, `superseded_by`, `decision_relevance` 필드 추가
4. operator가 봐야 하는 문서는 항상 3개 이하로 수렴시키기
   - now
   - next
   - why blocked

---

## 5-7. P2 — `.pyc`와 실행 부산물이 번들에 섞여 있다
### 관찰
압축 파일에 `.pyc`가 다수 포함되어 있다.

### 왜 문제인가
이건 기능 결함은 아니지만, anti-slop 관점에서는 좋지 않다.

- 리뷰 대상과 실행 부산물이 섞인다
- diff/noise가 증가한다
- 번들 신뢰도가 떨어진다
- 재현성과 검토 효율이 낮아진다

### 개선 권장
- 배포/리뷰 번들 생성 시 `.pyc`, `__pycache__`, 임시 산출물 제외
- “review bundle profile”을 별도 정의
- generated artifact와 source artifact를 명시적으로 분리

---

## 6. 파일별 상세 소견

## 6-1. `ops/scripts/command_runtime.py`
### 진단
좋은 의도:
- timeout 강제
- 프로세스 그룹 종료
- 결과를 dataclass로 반환

문제:
- 실행/종료 race condition에 취약할 수 있음
- timeout 처리와 종료 후 drain이 지나치게 단순
- 환경별 차이를 흡수하는 추상화 레이어가 없음

### 보완 방향
- `ProcessController` 인터페이스 도입
- POSIX/Windows/test fake 구현 분리
- 프로세스 lifecycle event를 더 세분화
- timeout wrapper에 대한 dedicated test matrix 구축

---

## 6-2. `ops/scripts/filesystem_runtime.py`
### 진단
이 모듈은 전체적으로 품질이 좋다.  
특히 원자적 쓰기와 root escape / symlink 차단은 매우 좋다.

### 보완 방향
- 현재의 강점을 다른 write path에도 일관되게 강제해야 한다
- 모든 보고서/manifest write가 이 계층만 통하도록 정리하면 더 좋다
- `atomic_multi_write()` 호출부에서 “실패 시 어떤 도메인 연산이 rollback되었는지”까지 상위 레벨 메타데이터로 남기면 self-improvement 관점에서 더 좋아진다

---

## 6-3. `ops/scripts/auto_improve_readiness_runtime.py`
### 진단
`build_readiness_report()`에 너무 많은 책임이 모여 있다.

현재 한 함수 안에서 사실상 다음을 한다.

- 정책 로드
- 리포트 로드
- 큐 상태 확인
- fallback 계산
- evidence gap 집계
- check list 구성
- next action 생성
- diagnostics 조립
- 최종 payload 반환

### 보완 방향
이 파일은 “보고서 생성기”가 아니라 **상태 기계(state machine)** 가 되어야 한다.

권장 구조:

1. `ReadinessInputs`
2. `OperationalReadinessAssessment`
3. `LearningReadinessAssessment`
4. `ReadinessReportView`
5. `persist_readiness_report()`

이렇게 분리하면,  
**운영 판정**, **학습 판정**, **표현 렌더링**이 서로 독립적으로 테스트된다.

---

## 6-4. `ops/scripts/codex_exec_executor.py`
### 진단
`execute_codex_exec_role()`은 사실상 “한 함수 안의 실행 파이프라인”이다.

섞여 있는 책임:

- 입력 구성
- argv 생성
- prompt materialization
- subprocess 실행
- stdout/stderr 저장
- 결과 요약
- timeout 실패 부착
- report write
- ledger write
- runtime event log

### 왜 문제인가
지금은 작동하더라도, 여기에 기능이 더 붙으면  
곧 **실행기 자체가 작은 운영체제**처럼 커질 가능성이 높다.

### 보완 방향
다음 단계로 쪼개라.

- `build_execution_request`
- `launch_execution`
- `capture_execution_artifacts`
- `assess_execution_result`
- `persist_execution_outcome`

그리고 각 단계가 반환하는 타입을 명시하라.

---

## 6-5. `ops/scripts/observability_routing_provenance_runtime.py`
### 진단
이 계층은 여러 리포트를 종합해 provenance aggregate를 만들고 loop health를 구성한다. 개념적으로는 좋지만, 조립형 딕셔너리가 많아 **관측(telemetry)** 과 **정책 판정(policy)** 이 너무 가까이 붙어 있다.

### 보완 방향
- raw telemetry aggregation
- derived health metrics
- gate-facing signals
- operator summary
를 분리하라.

관측 데이터와 정책 데이터가 섞이면, 나중에 metric의 의미를 바꾸기 어려워진다.

---

## 6-6. `ops/scripts/raw_intake_promotion_validation_runtime.py`
### 진단
이 모듈은 “slop 탐지”를 적극적으로 하려는 의도가 강하다.  
방향성은 좋다. 하지만 지금 구현은 **문자열 규약에 과도하게 묶여 있다.**

### 보완 방향
- 템플릿 흔적 탐지는 heuristic warning으로 한정
- 의미 계약은 schema/typed model로 승격
- prose content quality와 structural completeness를 अलग개의 축으로 관리

---

## 6-7. `tests/minimal_vault_runtime.py`
### 진단
테스트 보조 모듈이 사실상 “거대한 샘플 세계 생성기”다.

### 보완 방향
- composition-friendly fixture builder로 리팩터링
- 필요한 테스트만 필요한 세계 조각을 조립
- 픽스처 자체에도 structural complexity budget 적용

---

## 7. Anti-slop 관점의 구조적 개선안

## 7-1. “리포트 생산”보다 “의사결정 객체”를 먼저 만들기
지금은 많은 곳에서 최종 산출이 곧 `dict[str, Any]` JSON payload다.  
이 방식은 빠르지만, 시간이 지날수록 상태 정의가 리포트 포맷에 갇힌다.

### 권장 원칙
- 내부: typed decision object
- 외부: JSON/Markdown renderer

즉:

```python
assessment = assess_learning_readiness(inputs)
payload = render_learning_readiness_report(assessment)
write_json(payload)
```

이 순서가 되어야 한다.

---

## 7-2. Gate를 늘리기 전에 “gate provenance”를 더 명확히 하기
자가 개선 시스템이 망가지는 대표 이유는 “왜 막혔는지”보다 “무엇이 막혔는지”만 남기기 때문이다.

각 gate 결과에 최소 다음을 남겨라.

- `signal_id`
- `source_metric`
- `threshold`
- `evaluation_window`
- `policy_origin`
- `operator_override_possible`
- `recommended_next_observation`

지금도 일부는 있지만, 전체적으로 일관되게 적용되지는 않는다.

---

## 7-3. 문자열 규칙 기반 검출을 구조화된 의미 모델로 점진 전환하기
모든 텍스트 품질을 schema로 완전히 대체할 수는 없다.  
하지만 최소한 아래는 구조 필드로 올릴 수 있다.

- 분석 블록의 역할
- bridge integration 존재 여부
- continuity 처리 여부
- follow-up question 충족 여부
- excluded scope 존재 여부
- evidence count 및 evidence kind

---

## 7-4. “자기개선 제안”보다 “자기개선 결과 해석”을 더 정교하게
현재 시스템은 제안 생성 능력은 충분히 갖추고 있다.  
다음 단계는 제안 수를 늘리는 것이 아니라, **어떤 제안이 왜 효과 있었는지** 를 더 잘 해석하는 것이다.

권장:

- proposal-level outcome
- session-level outcome
- family-level outcome
- policy-level outcome

을 구분해 축적하라.

예를 들어 proposal 하나의 성공은 아래와 같이 분리되어야 한다.

- 실행 성공
- 검증 성공
- 리뷰 승인
- 회귀 없음
- 이후 재작업 감소
- 동일 family에서 재발 감소

이 중 어디까지 만족해야 “학습했다”고 볼지 명시해야 한다.

---

## 8. 자가 개선 관점의 구체적 보완안

## 8-1. Session envelope를 표준화하라
현재 evidence gap의 핵심은 `session_reports_considered=0`, `no_session_context`다.  
즉, proposal과 outcome 사이를 연결하는 세션 구조가 충분히 강하지 않다.

### 제안하는 표준 envelope
```json
{
  "session_id": "...",
  "proposal_id": "...",
  "family": "...",
  "inputs": {...},
  "execution": {...},
  "validation": {...},
  "review": {...},
  "final_outcome": {...},
  "follow_up": {...},
  "learning_summary": {...}
}
```

이 envelope를 모든 self-improvement run의 canonical evidence로 삼아야 한다.

---

## 8-2. readiness를 2차원 매트릭스로 바꿔라
현재의 `pass` 단일 상태는 요약에는 편하지만, 실제 운영에서는 부족하다.

권장 축:

- **Execution readiness**
- **Learning readiness**

가능한 상태 예시:

- execution_ready / learning_unready
- execution_ready / learning_shadow
- execution_ready / learning_ready
- execution_blocked / learning_unknown

이렇게 해야 운영자가 “돌려도 되는가?”와 “배울 수 있는가?”를 동시에 볼 수 있다.

---

## 8-3. 제안 큐보다 evidence queue를 더 중요하게 보라
현재는 runnable proposal queue가 readiness에서 강한 신호를 가진다.  
하지만 장기적으로는 proposal queue보다 **evidence queue** 가 중요하다.

질문을 바꿔야 한다.

- “실행할 제안이 있나?” → 현재 구조
- “학습을 확정할 증거가 충분한가?” → 앞으로 필요한 구조

---

## 8-4. 개선 결과를 “코드 변경량”이 아니라 “재발 감소”로 측정하라
self-improvement가 흔히 실패하는 이유는, 시스템이 다음을 성과로 착각하기 때문이다.

- 제안 수 증가
- 보고서 수 증가
- 수정 파일 수 증가
- gate 추가 수 증가

실제로 중요한 것은:

- 재작업 감소
- defect escape 감소
- hold/discard 감소
- 동일 family의 반복 발생 감소
- operator intervention 감소

현재 일부 신호는 이미 수집하려 하지만, 상위 의사결정에서의 가중치가 더 커져야 한다.

---

## 9. 구체적 실행 우선순위

## P0 (즉시)
1. `command_runtime` timeout wrapper 수정 및 재현 테스트 안정화
2. readiness 상위 요약에 `learning_readiness` 축 추가
3. auto-improve 세션 결과를 session envelope로 묶는 canonical artifact 정의

## P1 (다음 단계)
4. `build_readiness_report()` 분해
5. `execute_codex_exec_role()` 분해
6. 문자열 마커 기반 validator를 구조 기반 validator + heuristic warning으로 분리
7. `tests/minimal_vault_runtime.py` 픽스처 분해

## P2 (정리 단계)
8. generated artifact 정리 정책 강화
9. review bundle에서 `.pyc` / 캐시 / 임시 산출물 제외
10. structural complexity budget을 preview에서 실질 gate로 승격하기 위한 monitored profile 확대

---

## 10. 추천 리팩터링 청사진

### 10-1. 내부 모델
- `dataclass(frozen=True)` 기반 상태 객체
- 필요 시 `TypedDict`는 I/O 경계에서만 사용
- JSON 저장 전 renderer 계층에서 직렬화

### 10-2. 리포트 생성 패턴
- `load_*`
- `compute_*`
- `assess_*`
- `render_*`
- `persist_*`

### 10-3. 테스트 패턴
- 거대 fixture → 작은 builder 조합
- 한 테스트는 한 상태 전이만 검증
- 리포트 필드 존재보다 의미 판정 검증 강화

### 10-4. 자가 개선 패턴
- proposal 중심 → session 중심
- session 중심 → learning evidence 중심
- learning evidence 중심 → policy tuning 중심

---

## 11. 최종 평가

이 코드베이스는 이미 **“자가 점검을 전혀 하지 않는 시스템”** 단계는 지났다.  
오히려 반대 방향의 문제, 즉 **점검 장치와 리포트가 풍부해진 만큼 구조적 응집력을 다시 높여야 하는 시점**에 와 있다.

가장 중요한 판단은 다음 한 줄로 요약된다.

> 현재 시스템의 주된 위험은 “개선 기능이 없는 것”이 아니라,  
> “개선 신호·리포트·가드가 늘어나는 속도에 비해 의미 구조와 학습 폐쇄가 따라가지 못하는 것”이다.

따라서 지금 필요한 것은 새로운 리포트를 더 만드는 일이 아니다.  
다음 세 가지를 먼저 해야 한다.

1. **거짓 실패를 줄이는 실행 계층 안정화**
2. **학습 증거를 세션 단위로 닫는 구조화**
3. **딕셔너리/문자열 중심 오케스트레이션을 의미 객체 중심으로 전환**

이 세 가지가 되면, 현재의 풍부한 정책/가드/리포트 생태계는 부담이 아니라 강점으로 전환될 가능성이 크다.

---

## 부록 A. 직접 확인한 주요 근거

### A-1. 재현된 테스트/런타임 이슈
- `tests/test_command_runtime.py`는 짧은 정상 종료 프로세스가 성공해야 한다고 가정
- 하지만 현 재현에서는 `run_with_timeout()`가 timeout으로 처리되는 케이스가 확인됨

### A-2. readiness 관련 근거
- `ops/reports/auto-improve-readiness.json`
  - `status = pass`
  - `likely_to_learn = false`
  - `attempts_considered = 7`
  - `session_reports_considered = 0`
  - `session_calibration.status = no_session_context`

### A-3. complexity 관련 근거
- `ops/reports/structural-complexity-budget.json`
  - `function_budget_candidate_count = 27`
  - `monitored_candidate_count = 1`
  - `unmonitored_candidate_count = 26`
  - `gate_effect = preview`

### A-4. artifact sprawl 관련 근거
- `ops/reports/generated-artifact-index.json`
  - `external_reports_root_file_count = 15`
  - `canonical_report_count = 31`
  - `archive_candidate_count = 13`

### A-5. 구조적 hotspot
- 대형 함수 및 다책임 함수가 `ops/scripts/*runtime.py` 전반에 분포
- `dict[str, Any]` 사용이 런타임 핵심 모듈 전반에 광범위하게 존재
- 문자열 마커 기반 검증이 일부 promotion/validation 계층의 의미 검증을 대체하고 있음

---

## 부록 B. 유지해야 할 설계 원칙

이 프로젝트는 다음 원칙을 유지하면 좋아진다.

1. **파일 시스템 안전성은 절대 후퇴하지 말 것**
2. **운영 가능성과 학습 가능성을 분리할 것**
3. **리포트는 결과물이고, 진짜 핵심은 상태 객체일 것**
4. **문자열 규약보다 구조 계약을 우선할 것**
5. **self-improvement의 성과는 제안 수가 아니라 재발 감소로 측정할 것**
