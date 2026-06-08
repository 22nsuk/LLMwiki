# Project-Scoped Subagents

이 디렉터리는 이 저장소에서 공유하는 Codex 서브에이전트 프로필 표면이다.

기본 원칙:
- 프로젝트 공유 프로필은 `.codex/agents/` 아래에 둔다.
- repo-shared 기본 rung는 승인된 ladder 안에서만 고른다.
- `worker.toml`은 기본 구현자다.
- `reviewer.toml`과 `validator.toml`은 실행 sandbox가 temp workspace에서 `workspace-write`일 수 있지만 source/control file contract는 read-only다.
- specialized add-on은 부모 acceptance, generic review, generic validation을 대체하지 않는다.
- 모든 subagent prompt에는 read/write boundary와 의미 있는 결론 전 종료 금지 조건을 명시한다.

## Curated upstream seeds

이 프로필들은 아래 upstream 패턴만 엄격히 골라 이 저장소에 맞게 재작성했다.

- `code-mapper.toml`
- `search-specialist.toml`
- `docs-researcher.toml`
- `tooling-engineer.toml`
- `reviewer.toml`
- `qa-expert.toml`
- `research-analyst.toml`
- `llm-architect.toml`

추가로 cross-project profile seed를 검토해 이 저장소에 맞게 재작성한 것:
- `Headline_Rush/.codex/agents/hr-scope-gate-reviewer.toml` -> `scope-gate-reviewer.toml`

의도적으로 제외한 것:
- frontend/mobile/cloud/business 도메인 특화 에이전트
- 이 저장소의 flat wiki + maintainer runtime 구조와 직접 맞닿지 않는 범용 product 역할
- parent orchestration을 대체하려는 coordinator류 기본 프로필

## Approved ladder

repo-shared defaults는 아래 rung만 사용한다.

| Rung | Model | Effort | Typical use in this repo |
| --- | --- | --- | --- |
| 1 | `gpt-5.5` | `medium` | read-heavy mapping, route discovery, owner boundary clarification |
| 2 | `gpt-5.5` | `high` | bounded implementation, low/moderate-risk validation, risk-focused review, and architecture-sensitive analysis |
| 3 | `gpt-5.5` | `xhigh` | high-complexity validation, replayability, provenance, benchmark, and policy-weight audits |

추가 규칙:
- repo-shared default model은 모든 rung에서 `gpt-5.5`로 통일한다.
- rung 차이는 모델 계열이 아니라 `reasoning_effort`의 `medium`, `high`, `xhigh` 차이로만 표현한다.
- wire-level `reasoning_effort` override가 필요해도 repo-shared default는 위 3단계 ladder를 벗어나지 않는다.
- override가 정말 필요하면 세션에서 명시적으로 승인받고 올린다.

## Dynamic rung selection

이 저장소에서는 `.toml`의 model/reasoning을 최종 배정값으로 보지 않는다.

- `.toml`은 repo-shared fallback instruction surface다.
- 실제 rung 선택은 부모 agent가 `ops/scripts/core/select_subagent_rung.py`로 계산한다.
- selector는 `primary_target`, `supporting_target`, `test_file`, `manual_risk_flag`를 읽고 `complexity_policy`와 `subagent_routing_policy`를 합쳐 선택한다.
- selector report는 `escalation_reasons`, `deescalation_reasons`, `effort_sufficiency`를 함께 남겨, 왜 더 높은 effort를 쓰거나 쓰지 않았는지 audit 가능하게 한다.
- 선택 결과는 항상 approved ladder와 role별 `allowed_rungs` 안으로 clamp된다.
- target/risk가 모두 비어 있는 exploratory dispatch는 complexity `0`으로 시작해 discovery role이 과도하게 무거워지지 않게 한다.
- 자동 `system_mechanism` 루프는 이 selector를 role별로 반복 호출해 `scope-freeze -> routing -> codex exec` 증적 체인을 남긴다.
- `ops/reports/auto-improve-sessions/<session-id>.json`은 이 체인을 session-level rollup으로 다시 묶어, role/rung mix와 executor blocking outcome을 한 번에 읽게 한다.
- `ops/reports/routing-provenance-aggregates/<session-id>.json`은 같은 체인을 audit entrypoint로 고정하고, artifact index와 routing/executor/telemetry `audit_rollup` snapshot을 함께 제공한다.
- 이때 `.toml`은 여전히 fallback instruction surface이고, 실제 run-local 배정은 `runs/<run-id>/subagent-routing.<role>.json`과 `<role>-executor-report.json`이 canonical trace가 된다.
- validator는 준비된 workspace의 `.venv/bin/python`을 우선 사용하고, pytest replay에는 `PYTHONDONTWRITEBYTECODE=1` 및 `-p no:cacheprovider`를 붙여 cache/bytecode 쓰기 때문에 blocked로 오판하지 않게 한다.
- runtime executor는 non-worker role 뒤에 workspace integrity guard를 실행해, reviewer/validator/auditor가 source/control file을 바꾸면 blocking executor report로 전환한다.
- mechanism workspace 준비는 live repo의 `.venv`를 temp workspace에 symlink로 연결해 network 없이도 동일 dependency set으로 worker/validator checks를 실행하게 한다. `.venv` 자체는 diff/apply universe에서 계속 제외된다.

### Manual Dispatch Contract

수동으로 subagent를 고를 때도 `.toml`의 `model_reasoning_effort`를 그대로 최종 실행값으로 쓰지 않는다.

1. 부모 agent는 먼저 `python -m ops.scripts.core.select_subagent_rung --role <role>`을 실행한다.
2. 가능한 경우 `--primary-target`, `--supporting-target`, `--test-file`, `--manual-risk-flag`를 함께 넣어 실제 작업 표면을 반영한다.
3. 의도적으로 더 높은 floor가 필요할 때만 `--requested-rung <1|2|3>`을 추가한다. selector는 role별 `allowed_rungs` 안으로 clamp한다.
4. repo-native `codex_exec`나 model/reasoning override를 받는 controllable
   default/custom subagent 실행면에서는 report의
   `manual_dispatch.launch_parameters` 값을 그대로 사용한다. 이 필드는
   `profile_path`, `model`, `model_reasoning_effort`, `sandbox_mode`를 포함한다.
5. platform named role 실행면처럼 role 이름이 model/reasoning을 고정하는
   surface에서는 selector가 그 값을 override한다고 가정하지 않는다. 선택된
   rung과 platform fixed effort가 다르면 ladder-compliant manual dispatch가
   아니므로, report의 `manual_dispatch.fixed_reasoning_surface`를 확인해
   fixed 값이 `required_model`과 `required_model_reasoning_effort`에 맞는
   role/surface를 고르거나 `mismatch_action`에 따라 controllable 실행면에
   profile instruction을 전달한다.
6. `.toml`은 role intent와 fallback instruction surface다. selector가 실행 가능한 상황에서 `.toml` 기본 effort만으로 수동 dispatch를 끝내지 않는다.

## Profiles

### Core roles

| File | Default rung | Sandbox | Use when |
| --- | --- | --- | --- |
| `explorer.toml` | `gpt-5.5` + `medium` | `read-only` | owning path, router entry point, contract boundary를 먼저 맵핑해야 할 때 |
| `worker.toml` | `gpt-5.5` + `high` | `workspace-write` | bounded implementation or repo edit가 필요할 때 |
| `reviewer.toml` | `gpt-5.5` + `high` | `workspace-write` in temp workspace, source read-only contract | PR-style risk review, missing tests, source-fidelity drift를 보고 싶을 때 |
| `validator.toml` | `gpt-5.5` + `high` | `workspace-write` in temp workspace, source read-only contract | bounded validation, command replay planning, executable regression risk를 확인할 때. Routing policy가 schema/policy/security/high-score 신호를 보면 `xhigh`로 승격한다. |

### Specialized read-only add-ons

| File | Default rung | Use when |
| --- | --- | --- |
| `provenance-auditor.toml` | `gpt-5.5` + `xhigh` | `Source trace`, raw registry, frontmatter provenance, claim fidelity를 엄격히 감사할 때 |
| `parity-replay-auditor.toml` | `gpt-5.5` + `xhigh` | `make check`, packaged-copy parity, baseline/candidate replayability를 따질 때 |
| `benchmark-evidence-analyst.toml` | `gpt-5.5` + `xhigh` | eval/lint/stage2/promotion artifact가 keep/discard를 정당화하는지 판단할 때 |
| `owner-boundary-mapper.toml` | `gpt-5.5` + `medium` | `wiki/`, `system/`, `ops/`, `tests/`, `runs/` 사이의 canonical owner boundary를 잡을 때 |
| `scope-gate-reviewer.toml` | `gpt-5.5` + `high` | 작업이 public/private/generated/release/runtime 경계를 넘는지 구현 전에 차단하거나 좁힐 때 |
| `valuation-policy-auditor.toml` | `gpt-5.5` + `xhigh` | same-eval promotion, policy exception, decision-weight 과대평가 여부를 감사할 때 |
| `release-authority-auditor.toml` | `gpt-5.5` + `xhigh` | release-run/sealed/auto-promotion authority blocker와 stale evidence 원인을 분리할 때 |
| `goal-runtime-triage-auditor.toml` | `gpt-5.5` + `xhigh` | goal runtime trial admission, quarantine, next-run repair, readiness blockers를 분류할 때 |
| `external-report-action-auditor.toml` | `gpt-5.5` + `high` | external report prose, action matrix status/lifecycle, remediation backlog, improvement observations의 구현/보류 상태를 대조할 때 |

### Role boundaries

- `reviewer`는 변경 diff의 correctness와 missing tests를 본다. Release
  manifest authority나 goal-runtime admission 전체를 대신 판정하지 않는다.
- `validator`는 실행 가능한 bounded check를 고른다. Generated evidence의
  의미 해석이나 archive 가능성 판단은 specialized auditor가 보조한다.
- `release-authority-auditor`는 release authority readback만 다룬다. Runtime
  trial을 시작하지 않고, policy weakening이나 manifest 수동 수정을 권하지 않는다.
- `goal-runtime-triage-auditor`는 run admission과 failed-run classification을
  다룬다. Release auto-promotion pass 여부는 `release-authority-auditor`나
  parent release closeout이 판단한다.
- `external-report-action-auditor`는 보고서 권고와 repo evidence의 대응관계를
  action status, lifecycle, evidence currentness로 나눠 분류한다. 실제 archive,
  matrix refresh, backlog mutation은 parent가 명시한 Make/script lane으로만
  진행한다. Archive 가능성은 active/root 위치나 broad implemented count만으로
  판단하지 않고, 보고서별 matched action, unmatched recommendation count, 또는
  operator-only rationale가 확인된 뒤에만 제시한다.

## Routing guidance for this repo

이 저장소에서는 subagent routing을 task complexity와 contract risk로 나눈다.

- light discovery:
  - `explorer`
  - `owner-boundary-mapper`
- scope gating before edits:
  - `scope-gate-reviewer`
- bounded implementation:
  - `worker`
- acceptance and generic risk review:
  - `reviewer`
- bounded validation:
  - `validator`
  - `parity-replay-auditor`
- provenance-heavy questions:
  - `provenance-auditor`
- eval or promotion evidence questions:
  - `benchmark-evidence-analyst`
  - `valuation-policy-auditor`
- release authority questions:
  - `release-authority-auditor`
- goal runtime admission or failed-run triage:
  - `goal-runtime-triage-auditor`
- external report action reconciliation:
  - `external-report-action-auditor`

간단한 규칙:
- 경계가 불명확하면 먼저 `explorer`나 `owner-boundary-mapper`로 좁힌다.
- 요청 자체가 현재 task surface에 허용되는지 불명확하면 `scope-gate-reviewer`로 먼저 허용/축소/보류를 판단한다.
- 실제 수정은 기본적으로 `worker`가 맡는다.
- merge or signoff 전에는 `reviewer` 또는 `validator`를 붙인다.
- specialized add-on은 특정 리스크를 깊게 보는 sidecar로 쓰고, generic review/validation을 생략하지 않는다.

## Auto-Improve Integration

자동 `system_mechanism` 세션에서는 역할 dispatch가 고정 계약을 따른다.

- `worker`는 항상 실행한다.
- `validator`는 scope freeze가 runnable이면 항상 실행하되, low/moderate complexity는 rung 2(`high`)에서 시작하고 schema/policy/security/high-score 신호가 있을 때만 rung 3(`xhigh`)로 승격한다.
- `reviewer`는 target이 `ops/policies/`, `ops/schemas/`, `system/`을 건드리거나 worker score band가 `high|extreme`면 붙인다.
- auditor profile은 policy-backed `risk_flag -> role` mapping으로만 sidecar 실행한다.

실행 흐름:

- `proposal_scope_runtime.py`가 `runs/<run-id>/scope-freeze.json`을 만든다.
- `select_subagent_rung.py`가 role별 routing artifact를 만든다.
- `codex_exec_executor.py`가 `.toml` intent를 prompt로 materialize하고 `codex exec`를 호출한다.
- 각 role은 `runs/<run-id>/<role>-executor-report.json`으로 결과를 남긴다.
- auto-improve runtime은 `auto_improve_policy.allowed_executors`에 없는 executor name을 거부하고, 현재 canonical executor path는 `codex_exec`다.

## Why these profiles fit this repository

이 저장소의 핵심 리스크는 일반 앱 코드와 다르다.

- `raw/` immutable 규칙 위반
- `wiki/` / `system/` / `ops/` / `runs/`의 layer confusion
- frontmatter, raw registry, source trace drift
- eval gain을 mechanism promotion으로 과대해석하는 문제
- README/command/test/schema/policy 사이 contract mismatch

그래서 upstream의 일반 개발자 프로필을 그대로 두지 않고, 이 저장소의 maintainer/runtime failure mode에 맞게 instruction surface를 다시 쪼갰다.

## Sources

- Awesome Codex Subagents: <https://github.com/VoltAgent/awesome-codex-subagents>
- Codex subagents custom agent docs: <https://developers.openai.com/codex/subagents#custom-agents>
