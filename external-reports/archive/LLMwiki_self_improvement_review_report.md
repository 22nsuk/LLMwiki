# LLMwiki Self-Improvement Review Report

## 자가 개선 관점의 로컬 저장소 및 GitHub 연동 검토 보고서

작성일: 2026-05-22 | 기준 시간대: Asia/Seoul

검토 대상: /mnt/data/LLMwiki(7).zip에서 추출한 원본 로컬 저장소

파일명: LLMwiki_self_improvement_review_report.md

| **항목**         | **확인값**                                                                                   |
|------------------|----------------------------------------------------------------------------------------------|
| Git remote       | origin https://github.com/22nsuk/LLMwiki.git                                                 |
| 현재 브랜치/커밋 | main / a644b37768d72abab0d171c581d389045c9dd37b                                              |
| 로컬 추적 상태   | main a644b37 \[origin/main\] Close active external report remediation                        |
| 압축본 규모      | 392MB zip, 5,769 entries, 약 553MB uncompressed                                              |
| 검토 원칙        | 업로드된 압축본이 .git 포함 로컬 저장소 원본이라는 전제하에 로컬 evidence를 우선 권위로 채택 |

## 1. 결론 요약

LLMwiki vNext는 단순한 문서 저장소가 아니라, raw source를 지속형 wiki corpus로 정리하고 그 유지 메커니즘 자체를 다시 eval, gate, artifact, run ledger로 개선하려는 meta-maintainer workspace입니다. 구조적 성숙도는 높습니다. 특히 public/private boundary, schema-backed artifact, CI lane 분리, supply-chain artifact 생성, self-improvement run lifecycle의 개념화는 일반적인 개인 wiki 저장소보다 훨씬 강합니다.

다만 자가 개선 시스템으로 운영하려면 “통과 가능한 정책”보다 “반복적으로 저렴하게 실행 가능한 정책”이 더 중요합니다. 이번 검토에서 가장 큰 병목은 정확성보다는 운용성입니다. make check는 ruff와 mypy를 통과한 뒤 artifact_freshness_runtime 단계에서 장시간 정체되어 사용 가능한 실행 창 안에 완주하지 못했습니다. 별도 프로파일링 결과, 1,095개 JSON artifact에 대한 반복 schema validation 경로가 주요 후보 병목으로 관찰됐습니다.

따라서 최우선 개선 방향은 새 기능 추가가 아니라 다음 세 가지입니다. 첫째, long-running gate에 progress/heartbeat를 넣어 관측 가능하게 만들 것. 둘째, artifact freshness 및 readiness 계열 테스트의 반복 비용을 낮출 것. 셋째, self-improvement outcome을 “성공/실패”보다 “증거가 있는 반복 개선 단위”로 더 세밀하게 기록할 것.

| **영역**       | **판정**                      | **근거**                                                                                                           | **우선 개선**                                                                |
|----------------|-------------------------------|--------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| 아키텍처       | 강함                          | raw/wiki/system/ops/runs 계층, public/private mirror 정책, AGENTS 계약이 명확함                                    | authority graph와 producer-consumer graph를 machine-readable하게 강화        |
| 품질 게이트    | 강함이나 무거움               | ruff, mypy, lint, eval, stage2, registry, planning 개별 gate 통과. make check는 artifact freshness에서 장시간 정체 | schema validator cache, incremental freshness, gate timing report            |
| 테스트 체계    | 넓음                          | 전체 collect 1,467 tests, fast lane collect 748 tests. 일부 readiness 테스트는 chunk 실행 기준 4개에 약 28-33초    | fixture cache, parametrized consolidation, slow/fast 재분류                  |
| 자가 개선 루프 | 개념 성숙                     | run, promotion, mutation proposal, readiness, negative lessons, outcome metrics artifact 존재                      | 성과 정의를 “gate pass”와 “학습 persistence”로 분리                          |
| GitHub 연동    | 로컬상 연결됨, 원격 검증 제한 | .git/config remote 존재. 웹 공개 접근/검색은 불가                                                                  | private repo 의도 명시 또는 public mirror URL/attestation 고정               |
| 공급망/릴리스  | 상당히 강함                   | CycloneDX, SPDX, in-toto, OpenVEX, Sigstore, release attestation 관련 script/report/workflow 존재                  | Scorecard/branch protection/attestation 검증 결과를 release authority에 연결 |

## 2. 검토 범위와 방법

검토는 압축본을 로컬 저장소 그대로 압축한 원본으로 간주하고 진행했습니다. 즉, 외부 GitHub 원격 저장소의 현재 상태보다 업로드된 .git 포함 working tree와 그 안의 tracked/untracked artifact, Makefile, CI, test, ops script, README/ARCHITECTURE/AGENTS 계약을 더 강한 evidence로 보았습니다.

- 압축 해제 후 .git metadata, remote, branch, 최근 commit, working tree 상태를 확인했습니다.

- pyproject.toml, pytest.ini, Makefile, mk/\*.mk, .github/workflows/\*.yml, README.md, ARCHITECTURE.md, AGENTS.md, .codex/agents/\*.toml을 검토했습니다.

- uv 기반 dev 환경 설치를 수행하고 editable package 설치까지 확인했습니다.

- Makefile 기반 gate와 pytest collect 및 선택적/chunk 테스트를 실제 실행했습니다.

- artifact_freshness_runtime 병목을 별도 프로파일링해 text/json artifact scan과 schema validation 비용을 분리했습니다.

- 외부 기준은 Python packaging, pytest/xdist, Ruff, mypy, GitHub Actions, OpenSSF Scorecard, SLSA, in-toto, CycloneDX, SPDX, W3C PROV, RO-Crate, self-evolving agent/memory 문헌을 참조했습니다.

제한 사항도 명확합니다. 공개 GitHub URL은 웹에서 열람되지 않아 원격 최신 commit과 로컬 압축본의 차이는 검증하지 못했습니다. 또한 raw/ 하위 PDF와 웹 snapshot의 원문 의미 검토는 이 보고서의 핵심 범위가 아니며, maintainer runtime과 자가 개선 구조를 중심으로 보았습니다.

## 3. 저장소 식별 및 GitHub 연동 상태

| **검사 항목**          | **결과**                                                                                                                        |
|------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| remote -v              | origin https://github.com/22nsuk/LLMwiki.git (fetch/push)                                                                       |
| HEAD                   | a644b37768d72abab0d171c581d389045c9dd37b                                                                                        |
| branch -vv             | \* main a644b37 \[origin/main\] Close active external report remediation                                                        |
| 초기 working tree      | 테스트 전 clean으로 확인. bootstrap-preflight 실행 후 ops/reports/bootstrap-preflight-report.json이 갱신되어 modified 상태 발생 |
| 컨테이너 git ls-remote | github.com DNS 해석 실패로 직접 원격 조회 불가                                                                                  |
| 웹 공개 조회           | https://github.com/22nsuk/LLMwiki 및 site:github.com/22nsuk/LLMwiki 검색에서 공개 저장소 확인 불가                              |

해석: 로컬 저장소는 GitHub remote와 origin/main 추적 정보를 포함하므로 “GitHub와 연동된 로컬 clone”이라는 주장은 로컬 evidence로 성립합니다. 그러나 공개 웹 접근이 되지 않으므로, 이 보고서에서 GitHub 원격의 최신 상태를 단정하지 않습니다. 저장소가 private이라면 정상일 수 있지만, public mirror를 의도했다면 URL, 접근권한, release attestation 또는 공개 mirror manifest를 명확히 해야 합니다.

## 4. 저장소 구조와 역할 분리

| **경로**       | **파일 수** | **규모**   | **해석**                                                               |
|----------------|-------------|------------|------------------------------------------------------------------------|
| ops/           | 1,183       | 약 18.9MB  | policy, eval, schema, script, report 생성 runtime의 핵심 control layer |
| tests/         | 406         | 약 6.9MB   | unit, contract, release, supply-chain, lane별 테스트                   |
| raw/           | 446         | 약 211.7MB | 원본 PDF/web snapshot. full vault source of truth                      |
| wiki/          | 417         | 약 2.0MB   | 사용자/도메인/content corpus                                           |
| system/        | 71          | 약 0.9MB   | maintainer/runtime/meta corpus                                         |
| runs/          | 1,402       | 약 95.7MB  | 실제 planning/improvement run artifact                                 |
| .github/       | 2           | 약 21KB    | CI/release workflow                                                    |
| .codex/agents/ | 11          | 약 33KB    | subagent role surface                                                  |

README, ARCHITECTURE, AGENTS는 모두 같은 구조적 메시지를 반복합니다. raw는 immutable source layer, wiki/system은 corpus layer, ops는 control layer, AGENTS는 operating rule layer입니다. public mirror는 ops/tests/tools/mk/.github/.codex/agents와 루트 개발 파일을 포함하고, raw/wiki/system/runs/external-reports 및 generated private artifact는 제외하는 정책을 갖습니다.

이 분리는 자가 개선 관점에서 매우 중요합니다. 운영 메커니즘 자체를 공개 가능하고 재현 가능한 code/ops surface로 만들면서, private corpus와 live run artifact를 분리하기 때문입니다. 다만 경계가 문서와 policy에만 머물면 release 시 누출 위험이 남습니다. public export 산출물에 대한 negative assertion, 즉 “제외되어야 할 prefix가 실제로 없다”는 machine-readable attestation을 release authority에 포함하는 것이 좋습니다.

## 5. 개발 환경 및 실행 증거

| **명령/검사**                      | **결과**  | **관찰**                                                                                       |
|------------------------------------|-----------|------------------------------------------------------------------------------------------------|
| make dev-install                   | 성공      | uv가 Python 3.13.5 .venv를 만들고 dev dependency 및 editable install 완료                      |
| make bootstrap-preflight           | pass      | Python \>=3.12, jsonschema, PyYAML, mypy, pytest, ruff 확인. 보고서 artifact 갱신              |
| make check                         | 부분 실행 | ruff/mypy 통과 후 artifact_freshness_runtime 단계가 장시간 정체되어 실행 창 안에 완주하지 못함 |
| ruff check ops/scripts tests tools | pass      | All checks passed                                                                              |
| mypy @ops/mypy-allowlist.txt       | pass      | 251 source files에서 no issues                                                                 |
| make registry-preflight-check      | pass      | raw registry preflight 및 cross-environment matrix require-live 완료, 19.18초                  |
| make lint                          | pass      | 487 pages, error 0, warning 0, review_candidate 35, 17.45초                                    |
| make eval                          | pass      | Stage 1 total_score 4,792 / max_score 4,792, 487 pages, 7.91초                                 |
| make stage2-eval                   | pass      | Stage 2 total_score 110 / max_score 110, 99 pages, 3.86초                                      |
| make planning-gate                 | pass      | starter artifact schema 및 run_id alignment 통과, 1.16초                                       |
| pytest --collect-only -q           | collected | 192 test files, 1,467 tests, 12.32초                                                           |
| fast marker collect                | collected | 107 files, 748 tests, 7.77초                                                                   |
| make test-fast                     | 미완주    | xdist fast lane 시작 후 실행 창 안에 종료되지 못하고 terminated                                |

중요한 해석: 실패로 확인된 품질 오류는 없었습니다. 그러나 통합 gate가 운영자가 기다릴 수 있는 단위로 빠르게 수렴하지 못하는 것은 자가 개선 시스템에는 실질적인 결함입니다. 자가 개선은 반복 횟수가 성과를 결정하므로, gate가 무거워질수록 개선 루프의 throughput이 떨어집니다.

## 6. pytest 및 fast lane 관찰

전체 테스트 collect는 1,467개로 확인됐고, fast lane collect는 748개였습니다. 일부 작은 파일은 즉시 통과했습니다. auto_improve_readiness_runtime.py는 파일 전체 실행이 도구 실행 창을 넘었지만, 개별 chunk로 나누면 총 38개 테스트가 모두 통과했습니다. 그러나 4개 테스트 묶음이 약 28-33초 걸리는 구간이 반복되어 setup 비용 또는 fixture 생성 비용이 큰 것으로 보입니다.

| **테스트 조각**                                      | **결과**            | **시간/규모**                      |
|------------------------------------------------------|---------------------|------------------------------------|
| tests/test_artifact_io_runtime.py                    | 11 passed           | 1.17초                             |
| tests/test_auto_improve_execution_runtime.py         | 1 passed            | 1.06초                             |
| tests/test_auto_improve_iteration_runtime.py         | 22 passed           | 9.86초                             |
| tests/test_auto_improve_next_run_decision_runtime.py | 3 passed            | 1.20초                             |
| tests/test_auto_improve_queue_runtime.py             | 3 passed            | 1.05초                             |
| tests/test_auto_improve_route_scaffold_runtime.py    | 2 passed            | 1.33초                             |
| tests/test_auto_improve_readiness_runtime.py         | 38 passed by chunks | 각 4-5개 묶음 약 28-33초 반복      |
| tests/test_auto_improve_runtime.py                   | monolithic 미완주   | 22 tests collected. 개별 분할 필요 |

개선 판단: fast lane은 이름 그대로 “짧은 피드백 루프”가 되어야 합니다. readiness 계열 테스트가 실제 런타임 전체를 반복적으로 조립한다면, fast lane과 integration/slow lane의 목적이 흐려집니다. fixture caching, immutable sample vault reuse, parametrized test의 setup consolidation, per-test timing budget을 권장합니다.

## 7. artifact_freshness_runtime 병목 분석

make check의 병목 후보를 분리하기 위해 artifact freshness runtime 내부 경로를 부분 프로파일링했습니다. text/json artifact path scan과 source tree fingerprint는 병목이 아니었습니다. 반면 1,095개 JSON artifact에 대한 record 생성과 schema validation 루프가 약 37초 이상 소요되어 전체 command가 실행 창을 넘기는 핵심 후보로 보입니다.

| **측정 항목**                   | **결과**                             | **해석**                                                       |
|---------------------------------|--------------------------------------|----------------------------------------------------------------|
| \_text_artifact_paths           | 1,164 text artifacts / 0.601초       | 문서 파일 탐색은 문제 아님                                     |
| \_json_artifact_paths           | 1,095 JSON artifacts / 0.193초       | JSON path discovery는 문제 아님                                |
| root ephemeral scan             | 0 artifacts / 0.001초                | 루트 임시 파일 문제 없음                                       |
| run log placeholders            | 57 entries / 0.075초                 | placeholder scan 비용 낮음                                     |
| non_utf8 text scan              | 0 entries / 0.302초                  | encoding hygiene 양호                                          |
| release_source_tree_fingerprint | 1,627 files, 234.1MB / 1.685초       | fingerprint 자체는 병목 아님                                   |
| \_json_artifact_record loop     | 900개 약 29.4초, 잔여 195개 약 7.7초 | 반복 schema validation 및 artifact record assembly가 병목 후보 |

코드상 \_schema_validation은 artifact마다 load_schema_with_vault_override와 validate_with_schema를 호출합니다. schema_runtime에는 bundled schema와 local registry cache가 있으나, vault-local schema 파일 load와 validator build는 artifact별로 반복될 수 있습니다. jsonschema validator_for/check_schema/build_validator 비용이 1,095회 반복되면 gate wall-clock이 급증합니다.

권장 패치 방향은 명확합니다. ArtifactFreshnessContext 같은 실행 단위 객체를 만들고, 그 안에 schema_path -\> schema digest, schema_path -\> compiled validator, schema_path -\> schema load result를 cache합니다. 또한 --progress jsonl 옵션을 추가해 “phase, processed_count, total_count, elapsed_seconds, current_path”를 주기적으로 출력해야 합니다. timeout이 있더라도 마지막 heartbeat를 보면 어느 phase에서 멈췄는지 즉시 알 수 있습니다.

권장 구조 예시

```text
- ArtifactFreshnessContext(schema_cache, validator_cache, timing_recorder)
- validate_artifact(payload): schema_id를 정규화 -> compiled validator 재사용
- --progress jsonl: {"phase":"json_schema_validation","done":400,"total":1095,"elapsed":12.4}
- perf budget: full-vault artifact freshness p95 < 15s, public mirror < 5s
```

## 8. CI, release, supply-chain 평가

.github/workflows/ci.yml은 Python 3.12, 3.13, 3.14 matrix와 fast/report-contract/release-closeout/artifact-finalization/release-sealing/subprocess/slow/integration/integration-heavy/public tier를 분리합니다. 별도 Windows release smoke, raw registry cross-environment matrix, supply-chain gate도 존재합니다. 이는 저장소의 자체 목표와 잘 맞습니다.

release.yml은 source zip, external report manifest, provenance clean gate, release evidence bundle, live release attestation, build provenance attestation, PyPI publish까지 포함합니다. 공급망 관점에서 CycloneDX, SPDX, OpenVEX, in-toto, Sigstore 관련 script와 report가 존재하는 것도 강점입니다.

| **강점**                    | **잔여 위험**                                                                                                     | **개선 권고**                                                                                                           |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| Python matrix와 lane 분리   | 로컬 pyproject는 ruff/mypy target을 py312로 고정하면서 CI는 py3.14까지 실행. 최신 버전 경고가 늦게 발견될 수 있음 | py312/py313/py314 차이를 release dashboard에 요약하고, py314는 allow-fail인지 hard gate인지 명시                        |
| supply-chain artifacts 존재 | artifact 생성 자체와 외부 표준 schema 검증, consumer verification path가 분리되어 보일 수 있음                    | CycloneDX/SPDX schema validation, in-toto predicateType, SLSA provenance verification result를 release authority에 연결 |
| public/private mirror 정책  | 공개 GitHub 접근 불가로 실제 public surface 확인 제한                                                             | private repo라면 의도 명시. public mirror라면 PUBLIC-EXPORT-MANIFEST와 원격 URL을 보고서/릴리스에 고정                  |
| GitHub Actions timeout 설정 | fast full-vault path에서 make check-finalized가 40분 job에 들어갈 수 있어 feedback loop가 무거움                  | fast tier는 public mirror와 full vault를 분리하고, full vault closeout은 scheduled/release tier로 격리                  |

## 9. 자가 개선 루프의 성숙도 평가

자가 개선 시스템의 핵심은 “무엇을 바꾸고, 왜 바꾸며, 바꾼 결과가 다시 시스템에 어떤 지식으로 남는가”입니다. 이 저장소는 mutation proposal, mechanism review, outcome metrics, promotion gate, negative lessons, readiness ledger, release authority vocabulary를 파일과 schema로 명시하고 있어 개념적 기반이 강합니다.

| **평가 축**        | **점수** | **관찰**                                                                                     |
|--------------------|----------|----------------------------------------------------------------------------------------------|
| 목표/범위 통제     | 4.3 / 5  | single_mechanism_scope, proposal, planning gate, promotion gate 개념이 명확함                |
| 증거 기반성        | 4.2 / 5  | schema-backed generated artifact와 release evidence dashboard가 풍부함                       |
| 반복 비용          | 2.8 / 5  | long gate와 readiness test 비용이 높아 실제 반복 throughput 저하                             |
| 학습 persistence   | 3.7 / 5  | negative lessons와 outcome metrics 존재. 다만 “통과”와 “지식으로 남은 개선”을 더 분리할 필요 |
| 운영 관측성        | 3.2 / 5  | 보고서는 많지만 긴 command의 heartbeat와 per-target timing summary가 부족                    |
| 공개/비공개 안전성 | 4.0 / 5  | 정책은 강함. 원격 공개 검증과 negative attestation은 강화 필요                               |

가장 큰 설계 개선은 outcome taxonomy입니다. 현재 gate pass는 필수지만, 자가 개선의 성공은 gate pass보다 좁고 구체적이어야 합니다. 예를 들어 outcome을 “defect eliminated”, “runtime reduced”, “coverage increased”, “artifact drift reduced”, “negative lesson captured”, “proposal rejected with reusable evidence”로 나누면 시스템은 실패에서도 더 잘 학습합니다.

## 10. 핵심 발견 사항 및 권고

| **우선순위** | **발견**                                                       | **근거**                                                                                            | **권고**                                                                                         |
|--------------|----------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| P0           | long-running gate 관측성 부족                                  | make check가 artifact_freshness_runtime에서 장시간 정체. 진행률/heartbeat가 없어 병목 판단이 어려움 | 모든 10초 이상 gate에 --progress jsonl, per-phase timing, timeout-safe partial report 도입       |
| P0           | artifact freshness 반복 비용                                   | 1,095 JSON artifact record/schema loop가 약 37초 이상. schema validator 반복 build 후보             | schema/validator cache와 incremental --changed-only 모드 도입. perf regression test 추가         |
| P1           | fast lane의 실제 비용 증가                                     | fast collect 748 tests. readiness runtime chunk 4개가 28-33초 반복                                  | fixture cache, shared sample vault, setup consolidation, slow/integration 재분류                 |
| P1           | 대형 함수/테스트 후보 잔존                                     | lint review candidate 35개. 일부 함수/테스트가 150-733 lines 또는 높은 branch/parameter count       | function-budget-refactor-proposals를 실제 refactor backlog로 승격                                |
| P1           | GitHub 원격 최신 상태 검증 불가                                | 로컬 remote는 있으나 공개 웹 접근/검색 불가                                                         | private 의도 명시 또는 public mirror URL 및 attested source zip 연결                             |
| P1           | generated artifact가 실행 중 working tree를 더럽힘             | bootstrap-preflight가 canonical report를 갱신해 git status modified 발생                            | check용 out path와 canonical refresh path를 분리하거나 closeout-only 갱신으로 제한               |
| P2           | public/private boundary의 release-time negative assertion 부족 | 문서 정책은 강하지만 실제 export 누출 검증이 release evidence에 더 강하게 묶일 필요                 | export manifest에 excluded_prefix_absence, local_path_absence, private_pattern_absence를 포함    |
| P2           | dynamic script alias import의 복잡도                           | ops.scripts.\_\_init\_\_가 flat alias를 제공해 호환성은 좋지만 canonical path 추적이 흐려질 수 있음 | deprecation timetable과 canonical import lint를 도입                                             |
| P2           | supply-chain artifact와 외부 검증 연결 강화 필요               | CycloneDX/SPDX/in-toto artifact는 존재. 외부 표준 validator 결과와 Scorecard 결과는 더 명시 필요    | Scorecard CLI/Action, SBOM schema validation, provenance verification을 release dashboard에 포함 |
| P3           | agent memory lifecycle 모델 강화 여지                          | wiki/system corpus는 잘 분리되어 있으나 memory state taxonomy는 더 발전 가능                        | candidate/accepted/superseded/contradicted/negative lesson 상태와 backlink graph를 도입          |

## 11. 30/60/90일 개선 로드맵

### 11.1 즉시 개선: 0-2주

- artifact_freshness_runtime에 progress/heartbeat와 per-phase timing을 추가합니다.

- schema validator cache를 도입하고, full-vault artifact freshness 목표 시간을 15초 이하로 둡니다.

- make check-observed target을 추가해 static, artifact freshness, registry, lint, eval, stage2, planning, tests의 elapsed time을 JSON으로 남깁니다.

- bootstrap-preflight와 check용 artifact out path를 분리해 일반 진단 실행이 canonical report를 불필요하게 갱신하지 않게 합니다.

- auto_improve_readiness_runtime의 가장 느린 fixture setup을 식별하는 pytest --durations report를 CI artifact로 업로드합니다.

### 11.2 중기 개선: 30일

- function budget 후보 중 giant test와 orchestrator 함수를 우선 분해합니다. 특히 test_makefile_static_gates, goal_runtime_runner.\_status_report, goal_run_status.build_report, external_report_lifecycle_runtime.status_from_evidence가 우선 대상입니다.

- self-improvement outcome taxonomy를 도입합니다. “pass”와 “learning captured”를 분리하고, rejected proposal도 reusable evidence로 남기는 구조를 만듭니다.

- public export negative assertion을 PUBLIC-EXPORT-MANIFEST와 release evidence dashboard에 포함합니다.

- fast lane을 “10분 이하” 같은 wall-clock SLA가 아니라 “developer edit loop에 적합한 최소 proof”로 재정의하고, readiness full sweep는 scheduled/integration으로 옮깁니다.

### 11.3 구조 개선: 60일

- artifact producer-consumer graph를 machine-readable하게 만듭니다. 각 report의 producer, input_fingerprints, output path, downstream consumer를 DAG로 표현합니다.

- schema validation 결과를 단순 pass/fail이 아니라 “schema drift source, affected producer, recommended regeneration target”으로 연결합니다.

- CI release authority에 OpenSSF Scorecard, SBOM schema validation, SLSA/in-toto verification, branch protection 상태를 포함합니다.

- ops.scripts flat alias의 canonicalization 정책을 정합니다. public scripts는 canonical package path만 쓰고, flat alias는 compatibility layer로 제한합니다.

### 11.4 장기 개선: 90일

- LLM wiki memory lifecycle을 도입합니다. source note, synthesis, contradiction, negative lesson, superseded claim, unresolved question을 상태 전이로 관리합니다.

- RO-Crate/W3C PROV 스타일의 research object metadata를 raw/wiki/system/run artifact에 연결해 외부 재사용성과 provenance를 높입니다.

- 자가 개선 run의 “효과 크기”를 측정합니다. 예: runtime 감소, warning 감소, coverage 증가, artifact drift 감소, human review load 감소.

- agent 역할별 권한 모델을 강화합니다. explorer/reviewer/validator/provenance-auditor가 서로 다른 artifact를 만들고 교차 검증하도록 합니다.

## 12. 구체적 구현 제안

### 12.1 ArtifactFreshnessContext 도입

현재 artifact freshness runtime은 함수형으로 잘게 나뉘어 있으나 실행 단위 cache와 progress reporting이 약합니다. 하나의 run context를 두고 schema/validator/timing/progress를 묶으면 성능과 디버깅이 동시에 좋아집니다.

```python
class ArtifactFreshnessContext:
    def __init__(self, vault, progress=None):
        self.vault = vault
        self.schema_cache = {}
        self.validator_cache = {}
        self.timings = []
        self.progress = progress

    def validator_for_schema(self, schema_path):
        # schema path 또는 schema digest 기준으로 compiled validator 재사용
        ...
```

### 12.2 make check-observed

자가 개선 시스템은 자기 gate의 비용을 알아야 합니다. make check가 성공했는지뿐 아니라 어떤 target이 얼마 걸렸는지를 ops/reports/check-timing-summary.json에 남기면 다음 개선 후보를 자동으로 선별할 수 있습니다.

추천 output shape

```json
{
  "artifact_kind": "check_timing_summary",
  "targets": [
    {"target": "static", "status": "pass", "elapsed_seconds": 17.1},
    {"target": "artifact-freshness-check", "status": "pass", "elapsed_seconds": 14.8}
  ],
  "slowest_targets": [...],
  "recommended_next_action": "optimize_artifact_freshness"
}
```

### 12.3 outcome taxonomy

promotion gate의 “keep/discard/hold”는 유지하되, self-improvement outcome은 더 세밀해야 합니다. 특히 실패한 실험도 잘 기록되면 다음 proposal의 search space를 줄이는 학습으로 기능합니다.

| **Outcome type**          | **의미**                                              | **예시 metric**                           |
|---------------------------|-------------------------------------------------------|-------------------------------------------|
| defect_eliminated         | 기존 실패나 warning을 제거                            | warning_count 3 -\> 0                     |
| runtime_reduced           | 동일 gate의 실행 시간이 감소                          | artifact freshness 45s -\> 12s            |
| coverage_increased        | 테스트나 eval coverage 증가                           | new test count, branch coverage           |
| drift_reduced             | generated artifact currentness 또는 schema drift 감소 | stale artifact count 감소                 |
| negative_lesson_captured  | 실패했지만 재사용 가능한 제한조건 확보                | proposal rejection reason + evidence path |
| human_review_load_reduced | review candidate나 manual step 감소                   | review_candidate_count 감소               |

## 13. 외부 기준과의 정합성

외부 기준과 비교하면 이 저장소는 이미 많은 현대적 관행을 도입했습니다. pyproject 기반 package metadata, ruff/mypy static checks, pytest/xdist lane, GitHub Actions matrix, SBOM/provenance/attestation artifact가 모두 존재합니다. 다음 단계는 “도입”보다 “검증 결과를 release authority와 self-improvement loop에 연결”하는 것입니다.

| **기준**               | **관련성**                                                | **저장소 적용/권고**                                                                                     |
|------------------------|-----------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| PyPA pyproject.toml    | build-system, project metadata, tool config의 단일 파일화 | 현재 pyproject가 build metadata와 tool config를 보유. Python target matrix와 tool target의 해석을 문서화 |
| pytest / pytest-xdist  | lane별 테스트와 병렬 실행                                 | xdist --dist=loadfile 사용. 단, fast lane wall-clock 관측과 fixture locality 강화 필요                   |
| Ruff / mypy            | 정적 품질 및 타입 검증                                    | ruff/mypy 통과. preview strict allowlist와 function budget을 실제 refactor backlog로 연결                |
| GitHub Actions matrix  | Python/OS/tier 조합 검증                                  | 3.12/3.13/3.14와 다양한 tier가 존재. 각 tier SLA와 release authority 영향 명시                           |
| OpenSSF Scorecard      | 오픈소스 보안 health metric                               | private repo면 CLI 실행, public repo면 Action 도입 후 결과를 supply-chain gate에 연결                    |
| SLSA / in-toto         | build provenance와 verifiable attestation                 | release.yml의 attest-build-provenance와 in-toto report를 consumer verification path로 강화               |
| CycloneDX / SPDX       | SBOM 표준                                                 | 두 형식 모두 생성. schema validation과 vulnerability/VEX linkage를 gate evidence로 포함                  |
| W3C PROV / RO-Crate    | provenance 및 research object packaging                   | raw/wiki/system/run artifact의 provenance graph와 research object metadata 확장에 적합                   |
| Voyager / A-MEM / SAGE | lifelong/self-evolving agent, memory linking, reflection  | 자가 개선 memory lifecycle과 graph-based feedback loop 설계에 참조 가능                                  |

## 14. 한계와 재현성 주의

- 공개 GitHub 원격은 웹에서 검증되지 않았습니다. 로컬 .git metadata 기준으로만 GitHub 연동을 판단했습니다.

- 실행 환경의 도구 호출 제한 때문에 make check와 make test-fast 전체를 단일 command로 끝까지 완주하지는 못했습니다. 대신 개별 gate, collect, chunk 테스트, 병목 프로파일링을 수행했습니다.

- 테스트 중 ops/reports/bootstrap-preflight-report.json이 갱신되어 working tree가 modified 상태가 되었습니다. 이는 검토 과정의 부수 효과이며 원본 압축본의 초기 상태와 구분해야 합니다.

- raw/ 하위 PDF와 웹 snapshot의 사실성·저작권·원문 품질을 전수 검토하지 않았습니다. 이 보고서는 runtime, governance, self-improvement 구조를 중심으로 합니다.

- 외부 문헌과 표준은 최신 상태 확인을 위해 웹 기준을 보조로 사용했습니다. 저장소 내부 판단은 로컬 evidence를 우선했습니다.

## 15. 재실행 명령 요약

```bash
cd /mnt/data/LLMwiki_repo
make dev-install
make bootstrap-preflight
make static
make registry-preflight-check
make lint
make eval
make stage2-eval
make planning-gate
.venv/bin/python -m pytest --collect-only -q
.venv/bin/python -m pytest -m "not slow and not integration and not integration_heavy and not public and not report_contract and not artifact_finalization and not release_sealing and not subprocess" --collect-only -q
```

참고 로그: /mnt/data/llmwiki_bootstrap_preflight.log, /mnt/data/llmwiki_make_check.log, /mnt/data/llmwiki_registry_preflight.log, /mnt/data/llmwiki_lint.log, /mnt/data/llmwiki_eval.log, /mnt/data/llmwiki_stage2_eval.log, /mnt/data/llmwiki_planning_gate.log, /mnt/data/llmwiki_pytest_collect.txt, /mnt/data/llmwiki_fast_collect.txt

## 16. 참고 외부 자료

| **자료**                                                            | **URL**                                                                                                |
|---------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| Python Packaging User Guide - Writing your pyproject.toml           | https://packaging.python.org/en/latest/guides/writing-pyproject-toml/                                  |
| pytest documentation                                                | https://docs.pytest.org/en/stable/                                                                     |
| pytest-xdist distribution docs                                      | https://pytest-xdist.readthedocs.io/en/stable/distribution.html                                        |
| Ruff documentation                                                  | https://docs.astral.sh/ruff/                                                                           |
| mypy configuration documentation                                    | https://mypy.readthedocs.io/en/stable/config_file.html                                                 |
| GitHub Actions workflow syntax                                      | https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax                     |
| GitHub Actions matrix strategies                                    | https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations |
| OpenSSF Scorecard Action                                            | https://github.com/ossf/scorecard-action                                                               |
| SLSA Build Provenance specification                                 | https://slsa.dev/spec/draft/build-provenance                                                           |
| in-toto Attestation Framework                                       | https://github.com/in-toto/attestation                                                                 |
| CycloneDX BOM standard                                              | https://cyclonedx.org/                                                                                 |
| SPDX specifications                                                 | https://spdx.dev/use/specifications/                                                                   |
| W3C PROV overview                                                   | https://www.w3.org/TR/prov-overview/                                                                   |
| RO-Crate overview                                                   | https://www.researchobject.org/ro-crate/about_ro_crate                                                 |
| Voyager: Open-Ended Embodied Agent with LLMs                        | https://arxiv.org/abs/2305.16291                                                                       |
| A-MEM: Agentic Memory for LLM Agents                                | https://arxiv.org/abs/2502.12110                                                                       |
| Self-evolving Agents with reflective and memory-augmented abilities | https://arxiv.org/abs/2409.00872                                                                       |
| Karpathy LLM Wiki gist                                              | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f                                      |

## 17. 최종 권고

LLMwiki는 이미 “자가 개선을 문서로 설명하는 프로젝트”가 아니라 “자가 개선을 artifact와 gate로 실행하려는 프로젝트”입니다. 다음 도약은 더 많은 보고서나 더 많은 gate를 추가하는 것이 아니라, gate를 더 빠르고 관측 가능하게 만들고, 실패한 시도까지 학습 자산으로 남기는 것입니다. 운영 비용을 줄이는 P0 개선을 먼저 끝내면 이후의 self-improvement loop는 훨씬 더 높은 반복 속도로 작동할 수 있습니다.

실행 우선순위는 1) artifact freshness cache/progress, 2) fast lane 비용 절감, 3) outcome taxonomy 강화, 4) public/private release attestation 강화, 5) supply-chain external verification 연결 순서가 적절합니다.
