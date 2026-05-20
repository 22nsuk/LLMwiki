# LLMwiki Long-Run Integrated Improvement Plan Report

- 작성일: 2026-05-19 KST
- 작성 언어: 한국어
- 파일명: `llmwiki_long_run_integrated_improvement_plan_20260519.md`
- 목적: 업로드된 2026-05-18 리뷰를 기존 2026-05-15/2026-05-16 리뷰, 압축 원본 저장소, 현재 `goal/5day-auto-improve-runtime` 브랜치, 실제 코드/산출물/테스트와 다시 대조하여 **장기 무인 연속 런** 관점에서 최선의 작업 플랜을 도출한다.
- 핵심 초점: 단순한 의견 병합이 아니라, **파일 기준 재대조 → 현재 truth model 확정 → 장기 최적 작업 순서 재설계**에 있다.

---

## 1. 최종 결론

이번 재대조의 결론은 분명하다.

1. 업로드된 2026-05-18 리뷰의 **큰 방향은 맞다**. 현재 `goal/5day-auto-improve-runtime` 브랜치는 bounded 30분 trial을 위한 control plane은 상당 부분 갖췄지만, **5일 sustained unattended runtime을 주장하거나 promotion 가능한 상태는 아니다**.
2. 다만 업로드된 리뷰에는 **실행 가능한 작업 지시로 쓰기엔 보정이 필요한 항목**이 있다. 대표적으로 `GOAL_WORKTREE_MODE=git_worktree` 제안은 실제 CLI와 맞지 않으며, `goal.contract_sha256`를 raw file SHA로 검증하는 제안도 현재 구현과 맞지 않는다.
3. 현재 가장 큰 문제는 “기능이 아예 없다”가 아니라, **현재 코드가 생성할 수 있는 최신 truth와 이미 커밋되어 있는 tracked report들이 같은 시점을 가리키지 않는 것**이다. 즉, 지금의 최우선 과제는 기능 추가보다 **truth surface 정리, refresh ordering, hot state와 tracked snapshot 분리**다.
4. 장기 최적 관점에서 가장 효율적인 순서는 다음과 같다.
   - 먼저 stale/cross-artifact drift를 제거한다.
   - 그 다음 profile budget을 실제 bounded 값으로 낮춘다.
   - 그 다음 실제 30분 trial과 resume evidence를 수집한다.
   - 그 다음 remediation backlog를 닫는다.
   - 마지막으로 6시간 → 2일 → 5일 ladder를 순차적으로 증명한다.
5. `set_goal()`은 현재 **저장소 내부 durable file contract API**로는 충분히 유의미하다. 그러나 사용자가 원하는 “Codex에서 장기 런을 실제로 운용하는 외부 goal control plane”까지 포함하면, 지금 구현은 **완성형이 아니라 1단계**다. 장기적으로는 run-local state backend와 external Codex adapter 계층을 분리해서 올라가야 한다.

즉, 이번 통합 개선 보고서의 핵심 판단은 다음 한 문장으로 요약된다.

> **현재 브랜치는 장기 런의 control plane을 만들기 시작한 상태이며, 지금 당장 해야 할 일은 더 많은 기능 추가가 아니라 “현재 truth를 일관되게 만들고, bounded proof를 실제로 수집하는 것”이다.**

---

## 2. 검토 입력, 해시, 해석 기준

### 2.1 이번에 실제로 대조한 입력

| 구분 | 경로 | SHA-256 / 상태 | 해석 |
|---|---|---|---|
| 원본 ZIP | `/mnt/data/LLMwiki(3).zip` | `4daea836a76e6fc5ae7bcefa0e318f3f6a1050ea74d65a6ba12c7a3780d8eeb9` | 단순 source package가 아니라 `.git` 포함 원본 저장소 압축본으로 취급 |
| 업로드된 최신 리뷰 | `/mnt/data/llmwiki_goal_runtime_reconciliation_report_20260518.md` | `67d13af7642f1d589cd1039802e44216ac50f7c0f9e7edcb3aa38aa96c04bfbd` / 745 lines | 이번 요청의 직접 검토 대상 |
| 기존 보조 보고서 | `/mnt/data/llmwiki_goal_runtime_reconciliation_set_goal_report_20260518.md` | `cf8101f56ca9c038435e28a99ab39742e2403a1c45799a07392dc1dff19c4f48` / 1137 lines | 직전 통합/설계 보고서로 재참조 |
| 2026-05-15 보고서 | `external-reports/llmwiki_integrated_review_reconciliation_improvement_report_20260515.md` | `6818e37303703636bf49075a4c9757666794712f8af01bc2dcb8b43051e5425c` / 668 lines | branch root에 존재하는 핵심 reference |
| 2026-05-16 구현 보고서 | ZIP 내부 `external-reports/llmwiki_code_change_implementation_report_20260516.md` | `6055647ee4a35b2845fb307e00c61711e0913a72fb9d999b8d71602412828b09` / 791 lines | ZIP current checkout에는 있으나 current goal branch root에는 없음 |
| 기존 reconciled 보고서 | `external-reports/llmwiki_review_reconciled_improvement_report.md` | `1fd30714fef78201a8c493e919860b7f3737fd511160cd856da5f49b3cb499a5` / 582 lines | 오래된 active reference로 남아 있음 |

### 2.2 해석 기준

이번 리뷰에서는 입력을 다음 세 층으로 분리했다.

1. **ZIP current checkout**: 압축 당시 파일 시스템과 `.git`가 담고 있는 상태
2. **ZIP 내부 local goal branch**: 압축본 안에 들어 있는 `goal/5day-auto-improve-runtime` 브랜치가 가리키는 clean commit 상태
3. **현재 GitHub goal branch**: 현재 브랜치 헤드가 무엇인지에 대한 별도 기준

이 세 층을 분리하지 않으면, “ZIP에 파일이 있다”와 “current goal branch에 그 파일이 커밋되어 있다”를 혼동하게 된다. 이번 재대조에서 가장 중요한 부분 중 하나가 바로 이 구분이다.

---

## 3. 실제 기준선: ZIP, local goal branch, current branch의 관계

### 3.1 ZIP은 full repo snapshot이다

ZIP을 직접 해제해서 확인한 결과, 이번 ZIP은 replay-only source package가 아니라 **`.git`를 포함한 원본 저장소 스냅샷**이다. 따라서 git-aware preflight가 반드시 필요하다는 2026-05-15 보고서의 전제는 그대로 유지된다.

### 3.2 ZIP current checkout과 goal branch는 다르다

실제 확인 결과는 다음과 같다.

| 항목 | 실제 상태 |
|---|---|
| ZIP current checkout | `main` |
| ZIP current HEAD | `6c3ca7c46c6369ad043d78da5114c84173a14973` |
| ZIP current checkout dirty entry count | 450 |
| ZIP 내부 local `goal/5day-auto-improve-runtime` | `597d5d7eef7a3607fbec0b427e61266aa07e0c0c` |
| clean comparison worktree | `/mnt/data/llmwiki_goal_clean` |
| clean worktree HEAD | `597d5d7eef7a3607fbec0b427e61266aa07e0c0c` |
| clean worktree status | clean |

즉, **ZIP의 현재 파일 시스템은 dirty `main` checkout이고**, 사용자가 지정한 장기 런 브랜치의 기준선은 **ZIP 내부 local goal branch와 현재 GitHub goal branch가 같은 commit을 가리키는 clean 상태**다.

이 차이는 특히 2026-05-16 보고서의 존재 여부를 해석할 때 중요하다.

### 3.3 `external-reports` 실제 상태

current clean goal branch의 `external-reports/` root에는 다음 세 파일만 있다.

- `external-reports/llmwiki_integrated_review_reconciliation_improvement_report_20260515.md`
- `external-reports/llmwiki_review_reconciled_improvement_report.md`
- `external-reports/report-reference-manifest.json`

반면 `llmwiki_code_change_implementation_report_20260516.md`는 **ZIP current checkout의 파일 시스템에는 존재하지만, current goal branch root에는 없다**. 따라서 이 파일은 “아예 없는 문서”가 아니라, **브랜치 governance/evidence chain에 반영되지 못한 문서**로 해석해야 한다.

---

## 4. 업로드된 2026-05-18 리뷰에 대한 재판정

업로드된 최신 리뷰는 전체적으로는 유용하다. 다만 그대로 실행 지침으로 삼기에는 수정이 필요한 부분이 있다. 이번 절에서는 “유지할 주장”과 “보정할 주장”을 분리한다.

### 4.1 그대로 유지해야 하는 핵심 판단

다음 판단은 이번 재대조에서도 그대로 유지된다.

#### 4.1.1 현재 브랜치는 30분 bounded trial은 가능하지만 5일 sustained runtime은 아니다

현재 clean branch의 실제 산출물은 이 결론을 강하게 지지한다.

- `ops/reports/auto-improve-readiness.json`: `can_execute_trial=true`, `can_promote_result=false`
- `ops/reports/remediation-backlog.json`: open item 3개
- `ops/reports/goal-profile-verification.json`: `30m_trial` verification blocked, observed elapsed 0
- `ops/reports/session-synopsis.json`: “Trial only; do not promote”

즉, branch는 **실행 자체를 금지하지는 않지만, 결과를 promotion하거나 sustained claim으로 연결할 수 있는 상태는 아니다**.

#### 4.1.2 remediation backlog 3건은 실제 blocker다

실제 open item은 다음 세 건이다.

1. `active_blocker_goal_status_profile_ladder_incomplete`
2. `active_blocker_learning_claim_unlock_review_not_approved`
3. `active_blocker_post_seal_learning_claim_linkage`

이는 단순 advisory가 아니라 promotion 경로를 막는 실제 backlog다.

#### 4.1.3 `max_proposals=10000` 기본값은 bounded 30분 trial과 맞지 않는다

실제 코드와 Makefile 모두 기본값이 10000이다.

- `ops/scripts/core/codex_goal_client.py`: `max_proposals: int = 10000`
- `mk/mechanism.mk`: `GOAL_MAX_PROPOSALS ?= 10000`

이 값은 현재 contract가 “30분 bounded trial”이라는 의미를 주기에는 과도하게 크다. 이 점은 업로드된 리뷰가 정확하게 짚었다.

#### 4.1.4 2026-05-16 구현 보고서의 branch traceability가 깨져 있다

2026-05-16 문서는 ZIP에는 존재하지만 current goal branch root에는 없고, `external-reports/report-reference-manifest.json`과 `ops/reports/external-report-action-matrix.json`도 이를 active reference로 인식하지 않는다. 이 역시 업로드된 리뷰의 핵심 지적이 맞다.

#### 4.1.5 command streaming observability와 resume 실증은 아직 충분하지 않다

`ops/README.md`는 현재 `command_runtime.py`가 optional heartbeat callback을 제공하지만, **stdout/stderr streaming timestamp 정밀화는 별도 PR로 분리되었다**고 명시한다. 또한 current status artifact의 `command_heartbeat_status`는 `not_recorded`다. 따라서 2026-05-16 보고서의 PR-5는 부분 구현 상태로 보는 것이 맞다.

---

### 4.2 수정이 필요한 항목

업로드된 리뷰는 방향은 맞지만, 아래 항목은 현재 구현과 맞지 않으므로 바로잡아야 한다.

#### 4.2.1 `GOAL_WORKTREE_MODE=git_worktree`는 실제 실행 인자가 아니다

업로드된 리뷰는 preflight 예시에서 다음과 같은 형태를 제안했다.

```bash
make auto-improve-goal-preflight \
  PYTHON=python \
  VAULT=. \
  GOAL_WORKTREE_MODE=git_worktree \
  GOAL_WORKTREE_STRICT=1
```

하지만 실제 CLI는 `goal_worktree_guard.py --requested-mode`에서 다음 세 선택지만 허용한다.

- `auto`
- `git`
- `zip`

실제로 `GOAL_WORKTREE_MODE=git_worktree`로 실행하면 invalid choice 오류가 난다. 올바른 사용법은 다음이다.

```bash
make auto-improve-goal-preflight \
  PYTHON=python \
  VAULT=. \
  GOAL_WORKTREE_MODE=git \
  GOAL_WORKTREE_STRICT=1
```

그리고 이때 **출력 report의 `detected_mode`가 `git_worktree`인지 확인하는 것**이 맞다.

즉,

- `requested_mode`: `git`
- `detected_mode`: `git_worktree`

가 정확한 조합이다.

#### 4.2.2 `goal.contract_sha256`는 raw file SHA가 아니라 canonical JSON digest다

업로드된 리뷰는 `goal-run-status.json`의 `goal.contract_sha256`를 검증할 때 raw file bytes의 SHA-256을 직접 계산하는 예시를 제시했다.

그러나 현재 구현의 `ops/scripts/mechanism/goal_run_status.py`는 raw file SHA를 쓰지 않는다. 실제 구현은 아래와 같다.

```python
def _canonical_json_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
```

그리고 `goal.contract_sha256`는 `backend.get_goal()`로 읽은 contract object에 대해 이 canonical JSON digest를 기록한다.

따라서 정확한 acceptance check는 다음이어야 한다.

```python
from ops.scripts.goal_run_status import _canonical_json_digest

contract = json.loads(Path("ops/reports/codex-goal-contract.json").read_text())
status = json.loads(Path("ops/reports/goal-run-status.json").read_text())
assert status["goal"]["contract_sha256"] == _canonical_json_digest(contract)
```

중요한 점은 다음이다.

- 업로드된 리뷰가 지적한 “현재 committed `goal-run-status.json`가 최신 contract와 안 맞는다”는 문제 자체는 맞다.
- 하지만 **틀린 것은 검증 방식**이고, 올바른 해석은 “raw file SHA mismatch”가 아니라 **stale status artifact / refresh ordering 문제**다.

#### 4.2.3 `goal_run_status.py`가 contract를 안 읽는 게 아니라, committed status가 stale한 것이다

업로드된 리뷰는 `goal_run_status.py`가 status를 생성할 때 항상 `get_goal()`을 읽어야 한다는 식으로 개선안을 제시했다.

그런데 현재 코드의 실제 구현은 이미 다음 흐름을 사용한다.

- `FileGoalBackend(vault=..., contract_path=...)`
- `backend.get_goal()`
- 그 contract를 바탕으로 `promotion_guard`, `goal.contract_sha256`, `profile_ladder`, `health`를 계산

즉, 코드 레벨에서 보면 **이미 contract를 읽는다**. 문제는 이 함수가 틀렸다기보다, **현재 저장소에 커밋되어 있는 `ops/reports/goal-run-status.json`가 최신 contract/readiness와 동기화되지 않은 stale artifact**라는 데 있다.

이 차이는 중요하다. 왜냐하면 해결책이 달라지기 때문이다.

- 잘못된 진단: “코드가 contract를 안 읽음” → 함수 수정
- 실제 진단: “코드는 읽지만, tracked artifact refresh order와 publish 시점이 꼬여 있음” → orchestration/snapshot 모델 수정

#### 4.2.4 `ops/reports/goal-status.md`와 `ops/reports/goal-resume-metadata.json`는 current truth로 쓰면 안 된다

업로드된 리뷰는 이 두 tracked file을 current runtime evidence처럼 다루는 부분이 있었다. 하지만 현재 저장소 구조를 보면 이 둘은 **legacy/stale operator surface**에 가깝다.

실제 상태:

- `ops/reports/goal-status.md`는 아직도 `5-day-sustained`, `promotion_ban_active: False`, old goal id를 담고 있다.
- `ops/reports/goal-resume-metadata.json`도 `goal-20260515-5day-auto-improve-runtime`, `active_profile: 5-day-sustained`를 유지한다.
- 반면 `ops/README.md`는 현재 goal runtime의 run-local artifact를 `runs/goal-<id>/status.md`, `audit-log.jsonl`, `resume-metadata.json`, `checkpoint-command-events.jsonl`로 정의한다.

즉, current runtime truth는 이미 **run-local artifact 중심**으로 이동했는데, tracked legacy report가 정리되지 않아 operator를 헷갈리게 만드는 상태다.

---

## 5. 기존 2026-05-15 / 2026-05-16 보고서와의 재대조

### 5.1 2026-05-15 보고서의 요구 대비 현재 반영 상태

2026-05-15 보고서는 “trial은 가능하지만 promotion은 불가”라는 구조를 제안했고, long-run에 필요한 control plane을 다수 열거했다. 현재 반영 상태를 다시 정리하면 다음과 같다.

| 2026-05-15 요구 | 현재 상태 | 판정 |
|---|---|---|
| goal contract schema/report | 존재 | 구현됨 |
| `set_goal()` 기반 local goal client | 존재 | 구현됨 |
| fake backend production 차단 | `allow_fake=False` 기본, persistent backend 강제 가능 | 구현됨 |
| worktree guard | 존재 | 구현됨 |
| goal runner/status/profile verification | 존재 | 부분 구현 |
| remediation backlog | 존재 | 구현됨, open item 남음 |
| negative lessons | 존재 | 구현됨 |
| release authority sealed rehearsal | current pass | 구현됨 |
| profile ladder evidence | schema/report는 존재 | 실제 증거 미수집 |
| external Codex adapter layer | 없음 | 미구현 |
| active hot state와 tracked snapshot 분리 | 없음 | 미구현 |

핵심은, 2026-05-15가 요구한 **control plane skeleton은 상당수 구현되었지만**, 그 위에 필요한 **운영 truth 정합성과 실제 증거 수집**이 아직 닫히지 않았다는 점이다.

### 5.2 2026-05-16 구현 보고서(PR-1~PR-5) 재판정

2026-05-16 보고서는 단순 리뷰가 아니라 구체 구현 지시서였다. 현재 상태는 다음과 같다.

| 항목 | 요구 내용 | 현재 상태 | 판정 |
|---|---|---|---|
| PR-1 | full expected node count 고정 게이트 제거 | 현재 구조상 구현됨 | 구현됨 |
| PR-2 | source package lane에서 `ops/script-output-surfaces.json` 생성, deselect 축소 | 구현됨 | 구현됨 |
| PR-3 | static string assert를 structural test로 전환 | 일부 helper와 구조화 진행, 아직 긴 exact string test 잔존 | 부분 구현 |
| PR-4 | `FileGoalBackend`, process-persistent backend, fake backend production 차단 | 구현됨 | 구현됨 |
| PR-5 | command runtime heartbeat/status/streaming observability 강화 | heartbeat callback과 일부 test는 있음, streaming timestamp 정밀화/실증 부족 | 부분 구현 |

즉, 2026-05-16 보고서는 **문서 자체는 branch에 누락되었지만, 핵심 구현 내용은 상당 부분 branch에 반영되었다**. 이 점을 분리해서 봐야 한다.

- 구현 반영: 상당수 진행됨
- 문서 traceability: branch evidence chain에서 누락

이 둘을 같은 문제로 취급하면 정확도가 떨어진다.

### 5.3 2026-05-16 문서 누락의 올바른 해석

이 문서는 “없다”가 아니라 “**ZIP current checkout에만 있고 current goal branch root와 active manifest에는 없다**”가 정확한 표현이다.

장기 최적 관점에서는 이 차이가 중요하다. 앞으로는 다음 중 하나를 택해야 한다.

1. **문서를 current goal branch에 복원하고 manifest/action matrix에 정식 반영**한다.
2. 아니면 2026-05-19 통합 개선 보고서가 2026-05-16 내용을 흡수했다고 명시하고, 2026-05-16은 archive reference로 내린다.

현재 상태로 가장 좋지 않은 것은 **ZIP에는 있으나 branch governance에는 없는 반쯤 살아 있는 상태**다.

---

## 6. 현재 브랜치의 실제 truth model

이번 재대조에서 가장 중요한 정리는 “무엇을 current truth로 봐야 하는가”다.

### 6.1 현재 control plane의 핵심 구성요소

현재 branch에는 다음 핵심 control plane이 실제로 존재한다.

- `ops/scripts/core/codex_goal_client.py`
- `ops/scripts/mechanism/goal_worktree_guard.py`
- `ops/scripts/mechanism/goal_run_status.py`
- `ops/scripts/mechanism/goal_runtime_runner.py`
- `ops/scripts/mechanism/goal_profile_verification.py`
- `ops/scripts/learning/remediation_backlog.py`
- `ops/scripts/learning/self_improvement_negative_lessons.py`
- 관련 schema/report/test 일체

즉, “set_goal 기반 control plane 자체가 없다”는 평가는 이미 맞지 않는다.

### 6.2 현재 canonical report 중 신뢰 가능한 것

다음 파일은 현재 상태를 읽는 데 상대적으로 신뢰 가능하다.

| 파일 | 현재 상태 해석 |
|---|---|
| `ops/reports/auto-improve-readiness.json` | trial 가능 / promotion 불가 |
| `ops/reports/remediation-backlog.json` | open blocker 3건 |
| `ops/reports/codex-goal-contract.json` | current profile 30m / backend file / process persistent / proposal budget 10000 |
| `ops/reports/goal-profile-verification.json` | 30m evidence 미확보로 blocked |
| `ops/reports/release-closeout-sealed-rehearsal-check.json` | current clean pass |
| `ops/reports/session-synopsis.json` | trial only; do not promote |
| `ops/reports/external-report-action-matrix.json` | 19개 action item 중 10 implemented, 9 verification pending |

### 6.3 current run-local truth

`ops/README.md`에 따르면 현재 goal runtime은 다음 run-local artifact를 현재 run의 durable evidence로 사용한다.

- `runs/goal-<id>/status.md`
- `runs/goal-<id>/audit-log.jsonl`
- `runs/goal-<id>/resume-metadata.json`
- `runs/goal-<id>/checkpoint-command-events.jsonl`

이번 검토에서 eval worktree에서 실제로 `make auto-improve-goal-status`를 돌려 본 결과, 다음이 실제로 생성되었다.

- `runs/goal-eval-status/status.md`
- `runs/goal-eval-status/resume-metadata.json`
- `runs/goal-eval-status/audit-log.jsonl`

즉, current runtime truth는 이미 run-local로 이동하고 있다.

### 6.4 지금 operator를 혼란스럽게 만드는 legacy surface

반면 다음 tracked file은 current truth로 쓰기에는 위험하다.

| 파일 | 문제 |
|---|---|
| `ops/reports/goal-run-status.json` | current contract/readiness와 drift된 committed 상태가 남아 있음 |
| `ops/reports/goal-status.md` | old 5-day goal id / old profile / promotion ban false |
| `ops/reports/goal-resume-metadata.json` | old 5-day profile / old checkpoint 경로 |
| `ops/reports/goal-prompt.md` | old 5-day prompt narrative |
| `ops/reports/codex-goal-prompt.json` | 현재 generated surface인데 tracked governance와 분리됨 |

특히 `goal-prompt.md`와 `codex-goal-prompt.json`의 이중 표면은 장기적으로 정리해야 한다.

### 6.5 직접 재생성해 본 결과가 말해 주는 것

이번 검토에서 clean branch를 복제한 eval worktree에서 실제로 다음을 실행했다.

1. `make auto-improve-goal-preflight PYTHON=python VAULT=. GOAL_WORKTREE_MODE=git GOAL_WORKTREE_STRICT=1`
2. `make codex-goal-prompt PYTHON=python VAULT=. GOAL_WORKTREE_MODE=git GOAL_WORKTREE_STRICT=1 GOAL_MAX_PROPOSALS=1`
3. `make auto-improve-goal-status PYTHON=python VAULT=. GOAL_RUN_PROFILE=30m_trial GOAL_RUN_ID=eval-status GOAL_MAX_PROPOSALS=1 GOAL_RUN_STATUS=blocked`

그 결과는 매우 중요하다.

#### 6.5.1 status generator는 현재 contract를 읽으면 올바른 blocked 상태를 만들 수 있다

재생성된 eval `ops/reports/goal-run-status.json`은 다음을 만족했다.

- `promotion_guard.can_promote_result = false`
- `health.promotion_status = blocked`
- blocker에 `promotion_blocked_by_remediation_backlog_open` 포함
- `goal.contract_sha256`가 current contract의 **canonical JSON digest**와 일치

즉, **코드 path 자체는 크게 틀리지 않다**. 현재 저장소에 커밋되어 있는 stale report가 문제다.

#### 6.5.2 하지만 status/contract refresh 자체가 tracked file을 바로 dirty하게 만든다

같은 eval worktree에서 위 명령을 실행한 뒤 `git status --short`를 보면 다음 tracked file이 즉시 modified 상태가 된다.

- `ops/reports/codex-goal-contract.json`
- `ops/reports/goal-run-status.json`

그리고 이 상태에서 strict preflight를 다시 돌리면 `git_worktree_dirty` blocker가 발생한다.

이 사실은 매우 중요하다. 왜냐하면 현재 구조가 다음 두 요구를 동시에 만족시키지 못하고 있다는 **실증적 증거**이기 때문이다.

1. 장기 런 중에는 heartbeat/status/checkpoint를 계속 durable하게 써야 한다.
2. promotion 가능성을 판단하려면 clean worktree가 필요하다.

현재 구조는 active runtime state가 tracked artifact를 직접 갱신하므로, **장기 런을 계속 돌리는 순간 스스로 worktree를 dirty하게 만들고, 그 dirty state가 다시 promotion blocker가 되는 self-collision 구조**를 가진다.

이 점은 업로드된 리뷰보다 한 단계 더 중요한 실제 운영 문제다.

---

## 7. 현재 브랜치의 핵심 갭 정리

이번 통합 보고서에서는 장기 최적 관점에서 갭을 다음과 같이 정리한다.

### G1. cross-artifact truth가 일치하지 않는다 (P0)

현재 branch에는 다음이 동시에 존재한다.

- readiness: promotion 불가
- remediation backlog: open blocker 3개
- session synopsis: trial only
- committed goal-run-status: promotion allowed
- committed goal-status.md: 5-day running / promotion ban false

즉, operator가 어떤 파일을 먼저 보느냐에 따라 다른 결론이 나온다.

### G2. active hot state와 tracked snapshot이 분리되지 않았다 (P0)

현재 `auto-improve-goal-status`, `codex-goal-contract`, `auto-improve-goal-run` 계열은 tracked `ops/reports/`를 건드린다. 따라서 장기 런이 살아 있는 동안 promotion-clean 상태를 동시에 유지하기 어렵다.

이 문제를 해결하지 않으면, multi-day unattended runtime은 설계적으로 스스로를 막는다.

### G3. bounded budget 기본값이 과도하다 (P0)

`30m_trial`인데 `max_proposals=10000`은 bounded semantics를 약화한다. profile ladder가 있어도 budget ladder가 없다.

### G4. 2026-05-16 문서 traceability가 branch governance에서 끊겨 있다 (P0)

구현은 일부 반영됐지만, 문서와 manifest/action matrix가 이를 current evidence chain에 넣지 않는다.

### G5. command streaming observability는 아직 partial이다 (P1)

현재 status의 `command_heartbeat_status`는 `not_recorded`가 남고, `ops/README.md`도 stdout/stderr streaming timestamp 정밀화가 별도 PR이라고 말한다.

### G6. profile ladder 증거가 없다 (P1)

현재 `goal-profile-verification.json`은 `30m_trial`조차 blocked이다. 즉, 지금 단계에서 필요한 것은 또 다른 구조 추가가 아니라 **실제 30분 trial evidence**다.

### G7. legacy surface 정리가 안 됐다 (P1)

`goal-status.md`, `goal-resume-metadata.json`, `goal-prompt.md`는 현 구조에서 operator를 오도할 가능성이 높다.

### G8. external Codex control plane은 아직 시작 단계다 (P2)

현재 `set_goal()`은 durable local file contract API다. 이것만으로도 가치가 있지만, external Codex 연동까지 포함하면 아직 다음이 없다.

- remote thread / run / resume mapping
- capability-detected backend adapter
- external pause/resume/clear semantics
- local truth와 external control plane의 sync protocol

### G9. transient artifact cleanup gate가 없다 (P2)

저장소 자체의 improvement observation도 stale goal/source-package artifact 정리 문제를 open observation으로 기록하고 있다. 장기 런에서는 이 문제가 더 심해진다.

---

## 8. 장기 최적 관점에서의 최선의 작업 플랜

이번 요청의 핵심은 “지금 무엇을 먼저 해야 가장 효율적으로 long-run readiness를 올릴 수 있는가”다. 결론부터 말하면, 가장 좋은 순서는 **새 기능 추가 → 테스트**가 아니라 **truth reset → bounded proof 수집 → promotion path 정리 → runtime 고도화**다.

### Phase 0. truth surface 재정의 (최우선, P0)

#### 목표

operator가 어떤 파일을 봐야 현재 truth인지 헷갈리지 않도록, 현재 goal runtime의 authoritative surface를 명확히 고정한다.

#### 해야 할 일

1. `ops/reports/goal-run-status.json`를 current canonical tracked status로 유지할지, 아니면 snapshot 전용으로 내릴지 결정한다.
2. `ops/reports/goal-status.md`, `ops/reports/goal-resume-metadata.json`, `ops/reports/goal-prompt.md`를 다음 중 하나로 정리한다.
   - deprecated 표시 후 archive 이동
   - generated snapshot only surface로 재정의
   - current runtime truth에서 제외
3. `ops/README.md`, `generated-artifact-index`, `script-output-surfaces`, `report-reference-manifest`가 같은 truth model을 가리키게 한다.

#### 완료 조건

다음 질문에 파일 3~4개만으로 일관되게 답할 수 있어야 한다.

- 지금 trial 가능한가?
- 지금 promotion 가능한가?
- 지금 active profile은 무엇인가?
- 지금 current run-local evidence는 어디에 있는가?

---

### Phase 1. refresh orchestration / snapshot order 고정 (P0)

#### 목표

같은 시점의 truth가 contract/status/readiness/synopsis/backlog에 일관되게 반영되도록 refresh order를 고정한다.

#### 권장 신규 target

예시 이름:

- `make goal-runtime-reconcile`
- 또는 `make goal-runtime-refresh`
- 또는 `make goal-runtime-publish-snapshot`

#### 권장 순서

1. transient cleanup gate
2. `goal_worktree_guard`
3. `codex_goal_contract`
4. `goal_run_status`
5. `session_synopsis`
6. `goal_profile_verification` (run complete 시)
7. `remediation_backlog`
8. `auto_improve_readiness`
9. `external_report_action_matrix` / `generated_artifact_index` / `artifact_freshness`

#### 핵심 acceptance criteria

- `goal-run-status.goal.contract_sha256 == canonical_json_digest(codex-goal-contract)`
- `goal-run-status.promotion_guard == contract.promotion_guard`
- `readiness.can_promote_result=false`이고 backlog open이면 `goal-run-status.health.promotion_status == blocked`
- `session-synopsis.summary.sustained_claim_allowed == false`

---

### Phase 2. profile budget을 실제 bounded 값으로 재설정 (P0)

#### 목표

`30m_trial`을 진짜 bounded trial로 만든다.

#### 수정 권장안

- `build_auto_improve_goal_contract()` 기본 `max_proposals`: `10000 -> 1`
- `mk/mechanism.mk` 기본 `GOAL_MAX_PROPOSALS ?= 10000 -> 1`
- profile ladder별 budget/failure ladder 명시

권장값:

| Profile | max_wall_clock | max_proposals | max_consecutive_failures |
|---|---:|---:|---:|
| `30m_trial` | 1800 | 1 | 1 |
| `6h_ramp` | 21600 | 6 | 2 |
| `2d_candidate` | 172800 | 24 | 3 |
| `5d_sustained` | 432000 | 60 | 3 |

#### 이유

현재 ladder는 시간만 바꾸고 action budget을 거의 바꾸지 않는다. 장기 런에서 중요한 것은 wall-clock뿐 아니라 **bounded decision budget**이다.

---

### Phase 3. active hot state와 tracked snapshot 분리 (P0)

이 단계가 long unattended runtime의 핵심이다.

#### 목표

장기 런이 상태를 계속 남겨도 worktree를 dirty하게 만들지 않도록 구조를 바꾼다.

#### 권장 구조

- **active hot state**: ignored / run-local
  - `runs/goal-<id>/state/contract.json`
  - `runs/goal-<id>/state/status.json`
  - `runs/goal-<id>/state/resume-metadata.json`
  - `runs/goal-<id>/state/audit-log.jsonl`
- **tracked canonical snapshot**: 명시적 publish 시점에만 갱신
  - rung 완료
  - closeout
  - promotion closeout
  - human-reviewed release snapshot

#### 추천 구현 방향

1. 현재 `FileGoalBackend`는 유지한다.
2. 장기 런 default backend로 `RunLocalFileGoalBackend` 또는 유사 계층을 추가한다.
3. tracked `ops/reports/`는 별도의 `publish_goal_snapshot()` 단계에서만 갱신한다.
4. `goal_runtime_runner`는 active run 동안 run-local만 갱신하고, tracked surface는 session end / checkpoint publish / rung pass 시점에만 건드린다.

#### 왜 중요한가

이 분리가 없으면 long-running heartbeat 자체가 promotion-clean 상태를 망친다.

---

### Phase 4. external report governance 재정비 (P0)

#### 목표

보고서도 코드와 같은 수준으로 versioned/operator-facing evidence chain에 포함시킨다.

#### 해야 할 일

1. `external-reports/llmwiki_code_change_implementation_report_20260516.md`를 current goal branch에 복원한다.
2. `external-reports/report-reference-manifest.json`의 active reference set을 재정의한다.
3. `ops/reports/external-report-action-matrix.json`가 2026-05-16 요구(PR-1~PR-5)와 이번 통합 개선 보고서를 함께 반영하게 한다.
4. 오래된 `llmwiki_review_reconciled_improvement_report.md`는 active reference에서 내릴지 archive reference로 전환할지 결정한다.

#### 권장 active set

장기 최적 관점에서는 다음 세 문서를 active reference 세트로 유지하는 것이 가장 합리적이다.

1. `llmwiki_integrated_review_reconciliation_improvement_report_20260515.md`
2. `llmwiki_code_change_implementation_report_20260516.md`
3. **이번 통합 개선 보고서(2026-05-19)**

이렇게 하면

- 2026-05-15: 구조적 문제 정의
- 2026-05-16: 구현 change list
- 2026-05-19: 장기 최적 통합 실행 플랜

이라는 역할 분리가 선명해진다.

---

### Phase 5. 실제 30분 trial / resume proof를 먼저 수집 (P1)

#### 목표

지금 가장 부족한 것은 “새 아이디어”가 아니라 “실제 증거”다.

#### 바로 해야 할 일

1. clean worktree에서 corrected preflight 실행
2. bounded contract 재생성 (`max_proposals=1`)
3. 실제 30분 trial 1회 실행
4. run-local `status.md`, `audit-log.jsonl`, `resume-metadata.json`, `checkpoint-command-events.jsonl` 생성 확인
5. `goal-profile-verification`으로 `30m_trial` evidence 평가
6. 중간 interruption 후 `auto-improve-goal-resume` 실증
7. remediation backlog의 `goal_status_profile_ladder_incomplete`를 닫을 수 있는지 판단

#### 왜 이게 먼저인가

현재 control plane은 이미 꽤 있다. 지금 더 많은 설계를 더하는 것보다, **기존 control plane이 진짜 30분 동안 안정적으로 살아 있는지**를 먼저 증명해야 한다.

---

### Phase 6. command runtime streaming observability 완성 (P1)

#### 목표

`command_heartbeat_status=not_recorded`를 실제 current signal로 바꾼다.

#### 구현 권장

1. stdout/stderr nonblocking reader 추가
2. `last_stdout_at`, `last_stderr_at` 기록
3. artifact mtime touch watcher 추가
4. silence timeout과 wall-clock timeout 분리
5. termination ladder (`SIGTERM` → wait → kill) 기록
6. `goal-run-status`와 audit log에 “왜 멈췄는지” 구조화 기록

#### 이유

multi-day unattended runtime에서 가장 위험한 실패는 “죽은 줄도 모르고 멈춘 상태”다. 단순 timeout만으로는 충분하지 않다.

---

### Phase 7. transient artifact cleanup gate 추가 (P1)

#### 목표

오래된 ignored artifact와 obsolete tracked goal report가 currentness를 흐리지 않게 한다.

#### 권장 신규 target

- `make goal-runtime-clean-transient`
- `make long-run-preflight-clean`

#### cleanup 대상 예시

- stale run-local temp tree
- stale source-package extraction tree
- obsolete tracked goal checkpoint report
- current status path에서 더 이상 참조하지 않는 구 report

#### 근거

저장소의 `task-20260518-goal-runtime-reconciliation` improvement observation도 이미 이 필요를 open observation으로 기록하고 있다.

---

### Phase 8. external Codex control plane adapter를 별도 workstream으로 분리 (P2)

#### 목표

저장소 내부 durable goal contract와 외부 Codex 실행 환경을 느슨하게 결합한다.

#### 현재 상태

현재 branch는 다음까지만 구현되어 있다.

- `FakeGoalBackend`
- `FileGoalBackend`
- `detect_goal_backend()`
- `require_persistent_goal_backend()`
- `set_goal()` / `get_goal()` / `update_goal()`

즉, 현재는 **local durable backend layer**다.

#### 장기 권장 구조

- `RunLocalFileGoalBackend`: 장기 런 기본 로컬 backend
- `CodexSdkThreadBackend`: 외부 Codex primary backend
- `CodexAppServerGoalBackend`: experimental capability-detected optional backend
- `CodexExecResumeBackend`: non-interactive fallback backend

#### 중요한 원칙

외부 backend가 붙더라도 **local contract digest와 run-local state가 진실 소스**여야 한다. 외부 backend는 control surface이지 truth source가 아니다.

---

## 9. `set_goal()` 중심의 구체 설계안

이번 절은 “지금 있는 기능”의 설명이 아니라, 장기 무인 런을 실제로 굴리기 위해 `set_goal()`를 어떤 축으로 확장해야 하는지를 정리한 것이다.

### 9.1 유지해야 할 내부 stable API

현재 다음 함수는 내부 stable API로 유지하는 것이 좋다.

- `build_auto_improve_goal_contract()`
- `promotion_guard_from_readiness()`
- `set_goal()`
- `get_goal()`
- `update_goal()`

이 계층은 저장소 내부에서 “goal contract의 durable source of truth”를 다루는 역할로 명확하다.

### 9.2 추가해야 할 운영 API

장기 운용을 위해 다음 정도의 API를 추가하는 것이 좋다.

- `pause_goal()`
- `resume_goal()`
- `clear_goal()`
- `publish_goal_snapshot()`
- `get_goal_capabilities()`

이 중 `publish_goal_snapshot()`이 특히 중요하다. 현재 구조의 핵심 문제는 active run과 tracked snapshot이 뒤섞여 있다는 점이므로, snapshot publish를 독립된 행위로 분리해야 한다.

### 9.3 권장 backend layering

```python
class GoalControlBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def process_persistent(self) -> bool: ...

    @property
    def capabilities(self) -> dict[str, bool]: ...

    def get_goal(self) -> dict[str, Any]: ...
    def set_goal(self, contract: Mapping[str, Any]) -> dict[str, Any]: ...
    def update_goal(self, patch: Mapping[str, Any]) -> dict[str, Any]: ...
    def pause_goal(self, reason: str = "") -> dict[str, Any]: ...
    def resume_goal(self) -> dict[str, Any]: ...
    def clear_goal(self) -> None: ...
    def publish_snapshot(self) -> dict[str, Any]: ...
```

권장 backend 순서는 다음과 같다.

1. `RunLocalFileGoalBackend` — unattended run의 기본
2. `CodexSdkThreadBackend` — 외부 Codex 연동의 primary
3. `CodexAppServerGoalBackend` — experimental capability detected 옵션
4. `CodexExecResumeBackend` — non-interactive fallback

### 9.4 local contract와 external backend의 관계

외부 backend가 생기더라도 다음 원칙을 지켜야 한다.

- `ops/reports/codex-goal-contract.json` 또는 run-local contract가 여전히 source of truth다.
- external backend는 remote thread id / run id / resume handle 같은 매핑만 제공한다.
- local truth가 먼저고, external state는 sync 대상이다.

예시:

```json
{
  "goal_backend": {
    "backend_type": "run_local_file",
    "process_persistent": true,
    "storage_path": "runs/goal-auto-improve/state/contract.json"
  },
  "external_control": {
    "backend": "codex_sdk",
    "thread_id": "...",
    "remote_goal_id": "...",
    "last_synced_at": "...",
    "resume_supported": true
  }
}
```

### 9.5 지금 당장 하면 안 되는 것

다음은 장기 최적 관점에서 피해야 한다.

1. `FakeGoalBackend`를 unattended run 기본값으로 허용하기
2. active runtime이 tracked `ops/reports/`를 heartbeat마다 직접 갱신하게 두기
3. raw file SHA를 contract digest 기준으로 쓰기
4. `GOAL_WORKTREE_MODE=git_worktree` 같은 non-existent CLI value를 운영 문서에 넣기
5. `goal-status.md` 같은 legacy surface를 current truth처럼 안내하기
6. GitHub-hosted single job 하나로 5일 runtime을 곧바로 주장하기

---

## 10. 교정된 운영 절차

아래 절차는 이번 재대조 결과를 반영한 **수정된 operator runbook**이다.

### 10.1 preflight는 이렇게 실행해야 한다

```bash
make auto-improve-goal-preflight \
  PYTHON=python \
  VAULT=. \
  GOAL_WORKTREE_MODE=git \
  GOAL_WORKTREE_STRICT=1
```

확인 포인트:

- `tmp/goal-worktree-guard.json` 생성
- `requested_mode == git`
- `detected_mode == git_worktree`
- `status == pass`
- `dirty_worktree == 0`

`GOAL_WORKTREE_MODE=git_worktree`는 사용하면 안 된다.

### 10.2 bounded contract 주입은 이렇게 해야 한다

```python
from pathlib import Path

from ops.scripts.codex_goal_client import (
    build_auto_improve_goal_contract,
    promotion_guard_from_readiness,
    set_goal,
)

vault = Path('.').resolve()
contract = build_auto_improve_goal_contract(
    contract_id='auto-improve-goal',
    created_by='codex',
    storage_path='ops/reports/codex-goal-contract.json',
    current_profile='30m_trial',
    max_unattended_seconds=1800,
    max_proposals=1,
    max_consecutive_failures=1,
    heartbeat_interval_seconds=300,
    checkpoint_interval_seconds=1800,
    promotion_guard=promotion_guard_from_readiness(
        vault,
        readiness_report_path='ops/reports/auto-improve-readiness.json',
        worktree_guard_report_path='tmp/goal-worktree-guard.json',
    ),
)

state = set_goal(
    contract,
    vault=vault,
    contract_path='ops/reports/codex-goal-contract.json',
    allow_fake=False,
)
```

핵심은 다음 두 가지다.

- `allow_fake=False`
- `max_proposals=1`

### 10.3 status 검증은 raw SHA가 아니라 canonical digest로 해야 한다

```python
import json
from pathlib import Path
from ops.scripts.goal_run_status import _canonical_json_digest

contract = json.loads(Path('ops/reports/codex-goal-contract.json').read_text())
status = json.loads(Path('ops/reports/goal-run-status.json').read_text())

assert status['goal']['contract_sha256'] == _canonical_json_digest(contract)
assert status['promotion_guard']['can_promote_result'] is False
assert status['health']['promotion_status'] == 'blocked'
```

### 10.4 30분 trial의 올바른 first run

```bash
make auto-improve-goal-run \
  PYTHON=python \
  VAULT=. \
  GOAL_RUN_PROFILE=30m_trial \
  GOAL_RUN_ID=auto-improve-$(date -u +%Y%m%dT%H%M%SZ)-30m \
  GOAL_MAX_UNATTENDED_SECONDS=1800 \
  GOAL_MAX_MINUTES=30 \
  GOAL_RUNNER_TIMEOUT_SECONDS=1860 \
  GOAL_MAX_PROPOSALS=1 \
  GOAL_MAX_CONSECUTIVE_FAILURES=1
```

### 10.5 30분 종료 후 반드시 해야 할 것

```bash
make auto-improve-goal-finalize \
  PYTHON=python \
  VAULT=. \
  GOAL_FINAL_STATUS=completed

make goal-profile-verification \
  PYTHON=python \
  VAULT=. \
  GOAL_PROFILE_VERIFICATION_PROFILE=30m_trial \
  GOAL_PROFILE_VERIFICATION_APPLY=1

make remediation-backlog PYTHON=python VAULT=.
make auto-improve-readiness-report PYTHON=python VAULT=.
```

중요한 점은 `goal-profile-verification`과 `remediation-backlog`, `auto-improve-readiness`를 함께 갱신해야 다음 단계 판단이 닫힌다는 것이다.

---

## 11. 장기 런을 위한 우선순위별 작업 목록

### P0 — 바로 착수해야 하는 것

1. truth surface 재정의
2. refresh orchestration target 추가
3. `max_proposals` 기본값 1로 하향
4. profile ladder별 proposal/failure budget 명시
5. 2026-05-16 문서 branch 복원 및 manifest 반영
6. active hot state와 tracked snapshot 분리 설계 착수

### P1 — P0 직후 이어서 할 것

1. 실제 30분 trial evidence 수집
2. resume simulation
3. command streaming observability 강화
4. remediation backlog 3건 정리
5. legacy surface deprecation/archiving
6. transient artifact cleanup gate 추가

### P2 — 장기 고도화

1. external Codex backend adapter 계층
2. self-hosted/local supervisor 기반 multi-day orchestration
3. 6시간 / 2일 / 5일 ladder 실증
4. promotion closeout snapshot workflow 고정

---

## 12. 이 보고서 기준의 최적 작업 순서

지금부터 실제로 작업한다면, 가장 효율적인 순서는 아래다.

1. **문서/코드 truth reset**
   - legacy surface 정리
   - report truth hierarchy 명시
2. **sync order 고정**
   - `goal-runtime-reconcile` 계열 target 추가
3. **budget 수정**
   - `10000 -> 1` 및 ladder budget 분리
4. **2026-05-16 문서 governance 복원**
   - manifest / action matrix 반영
5. **30분 trial 실증**
   - corrected preflight → contract → run → finalize → verification
6. **resume proof**
   - interruption simulation과 재개 evidence 수집
7. **backlog 정리**
   - profile ladder / unlock review / post-seal linkage 정리
8. **run-local / tracked 분리 완료**
   - 장기 런 중 dirty self-collision 제거
9. **6시간 ramp**
10. **2일 candidate**
11. **5일 sustained**

이 순서가 중요한 이유는, 현재 가장 비싼 실패가 “기능 부족”이 아니라 “truth 불일치와 stale evidence”이기 때문이다. 지금 상태에서 바로 5일 프로파일로 가면, 문제를 더 오래 더 크게 축적할 가능성이 높다.

---

## 13. 최종 요약

업로드된 2026-05-18 리뷰는 전반적으로 좋은 방향을 제시했다. 특히 다음 판단은 그대로 유지된다.

- 현재 branch는 trial-ready이지 sustained-ready가 아니다.
- remediation backlog 3건이 promotion을 막고 있다.
- `max_proposals=10000`은 30분 bounded runtime과 맞지 않는다.
- 2026-05-16 문서의 branch traceability가 깨져 있다.
- command streaming observability와 resume evidence는 아직 부족하다.

하지만 이번 재대조를 통해 다음이 분명해졌다.

1. `GOAL_WORKTREE_MODE=git_worktree`는 잘못된 실행 예시다. `git`로 요청하고 `git_worktree`가 detect되어야 한다.
2. `goal.contract_sha256`는 raw file SHA가 아니라 canonical JSON digest다.
3. `goal_run_status.py`는 이미 contract를 읽는다. 현재 문제는 코드가 아니라 stale tracked artifact와 refresh ordering이다.
4. current runtime truth는 run-local로 이동하고 있는데, legacy tracked surface가 정리되지 않아 operator confusion을 만든다.
5. 장기 무인 런을 진짜 가능하게 하려면 active hot state와 tracked canonical snapshot을 분리해야 한다.

따라서 가장 좋은 다음 단계는 “더 많은 기능을 추가하는 것”이 아니라 **현재 truth surface를 정리하고, bounded 30분 proof를 실제로 수집하고, 그 결과를 기반으로 6시간/2일/5일 ladder로 올라가는 것**이다.

이 방향으로 가면 `set_goal()`는 단순 local helper가 아니라,

- 내부에서는 durable contract source of truth,
- runtime에서는 run-local state anchor,
- 외부에서는 Codex adapter 계층의 중심 인터페이스,
- 장기적으로는 snapshot/promotion control plane

으로 진화할 수 있다.

그리고 그때 비로소 이 저장소는 “장기 자동 개선 런을 할 수 있는 코드가 있다”를 넘어, **“장기 자동 개선 런을 실제로 신뢰 가능하게 운영할 수 있는 저장소”**로 넘어간다.
