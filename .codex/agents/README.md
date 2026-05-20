# Project-Scoped Subagents

이 디렉터리는 이 저장소에서 공유하는 Codex 서브에이전트 프로필 표면이다.

기본 원칙:
- 프로젝트 공유 프로필은 `.codex/agents/` 아래에 둔다.
- repo-shared 기본 rung는 승인된 ladder 안에서만 고른다.
- `worker.toml`은 기본 구현자다.
- `reviewer.toml`과 `validator.toml`은 실행 sandbox가 temp workspace에서 `workspace-write`일 수 있지만 source/control file contract는 read-only다.
- specialized add-on은 부모 acceptance, generic review, generic validation을 대체하지 않는다.

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
- 실제 rung 선택은 부모 agent가 `ops/scripts/select_subagent_rung.py`로 계산한다.
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
