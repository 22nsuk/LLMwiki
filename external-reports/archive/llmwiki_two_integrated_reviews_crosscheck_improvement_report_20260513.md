# LLMwiki 두 통합 리뷰 실제 파일 대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-13 (KST) |
| 작성 언어 | 한국어 |
| 산출 파일명 | `llmwiki_two_integrated_reviews_crosscheck_improvement_report_20260513.md` |
| 검토 대상 리뷰 1 | 사용자 본문: `LLMwiki 통합 장기 Anti-Slop 및 자가 개선 최적화 보고서` |
| 검토 대상 리뷰 2 | 사용자 본문: `LLMwiki Anti-Slop & 자가 개선 통합 장기 최적 개선 보고서` |
| 기존 리뷰 대조 | `llmwiki_anti_slop_self_improvement_long_term_report_20260513.md`, `llmwiki_two_20260511_reviews_crosscheck_improvement_report_20260511.md` |
| 실제 파일 대조 | `LLMwiki-source.zip` 및 업로드된 release/test evidence JSON·JUnit·log 전체 |
| 실제 source ZIP SHA-256 | `7b99056858b0855ef7ce7ca66935377dacff0cf2c37569ec2ed301ab661de7d5` |
| 코드 변경 여부 | 없음. 본 산출물은 분석·검증·개선 권고 보고서이며 저장소 코드는 수정하지 않았다. |

---

## 0. 검토 방식과 결론 범위

이번 검토는 사용자가 본문에 제공한 두 개의 장문 통합 리뷰를 **독립된 2차 리뷰 문서**로 보고, 각 리뷰의 주장·숫자·우선순위를 실제 업로드 파일과 대조했다. 두 리뷰는 서로 다른 제목을 가지지만 핵심 구조는 매우 유사하다. 둘 다 2026-05-13 체크포인트를 대상으로 하며, 내부적으로 리뷰 A/B/C라는 세 하위 리뷰의 발견을 통합한다.

검토는 네 단계로 진행했다.

1. 작업 계약 확인: `Codex-Subagent-Orchestrator.zip`을 추출하고 루트 `AGENTS.md`, parent-session skill, plan-mode skill, anti-overengineering skill을 확인했다.
2. 실제 소스 확인: `LLMwiki-source.zip`을 clean workspace에 추출하고 루트 `AGENTS.md`, `AGENTS.local.md`, `README.md`, `Makefile`, `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/ci.yml`, `ops/scripts/__init__.py`를 확인했다.
3. 증거 파일 대조: closeout summary, batch manifest, finality attestation, fixed-point report, evidence dashboard, lane summary, clean blocker ledger, risk taxonomy, smoke report, post-seal attestation, full-suite JUnit/log를 읽어 두 리뷰의 핵심 수치를 검산했다.
4. 가능한 로컬 재실행: source package 추출본에서 `make dev-install`, `make static`, `pytest --collect-only`, flat/canonical CLI help, `make check-clean`, `tests/test_source_package_clean_extract.py`, `make test-artifact-finalization`을 실행해 두 리뷰의 실행 관련 주장을 검증했다.

최종 결론은 다음과 같다.

> **두 리뷰의 큰 방향은 실제 파일과 대체로 일치한다.** 현재 2026-05-13 source package와 release evidence는 `clean_pass` / `sealed_clean_pass` 상태이며, source ZIP digest binding, fixed-point convergence, finality attestation, full-suite 1,141/1,141 pass 증거가 서로 정합한다.  
> **동시에 두 리뷰가 지적한 장기 개선 방향도 타당하다.** 다음 최우선 과제는 pass 개수를 늘리는 것이 아니라, Python 3.13 flat CLI 실행 표면 봉인, source package/full-vault lane UX 개선, status v2 어휘 정리, 거대 report builder 분해, self-improvement claim 단계 분리, lockfile 기반 재현성 강화다.

---

## 1. 두 리뷰의 성격과 중복도 판정

### 1.1 리뷰 1의 성격

리뷰 1은 제목상 `LLMwiki 통합 장기 Anti-Slop 및 자가 개선 최적화 보고서`이며, 다음 특징을 가진다.

- 세 하위 리뷰 A/B/C를 요약한 executive-level 통합본이다.
- release authority가 이미 강하게 닫혀 있다는 점을 먼저 판정한다.
- P0/P1/P2 로드맵을 비교적 간결하게 정리한다.
- 장기 목표를 "더 많은 gate"가 아니라 "더 적은 builder, 더 적은 중복 vocabulary, 더 명확한 mode boundary, 더 강한 long-horizon structural budget"으로 정의한다.

### 1.2 리뷰 2의 성격

리뷰 2는 제목상 `LLMwiki Anti-Slop & 자가 개선 통합 장기 최적 개선 보고서`이며, 리뷰 1과 결론은 같지만 다음 면에서 더 세밀하다.

- 실제 파일별로 어떤 증거를 읽었는지 더 길게 나열한다.
- 직접 검증 결과 표가 더 자세하다.
- 코드 구조 분석, 파일별 개선 제안, status vocabulary, self-improvement state model, report graph/DAG 제안을 더 구체화한다.
- Python 3.13 flat alias 결함의 재현 조건과 원인을 더 정확히 설명한다.

### 1.3 두 리뷰 간 중복과 차이

두 리뷰는 서로 충돌하는 독립 의견이라기보다, 같은 하위 발견을 서로 다른 압축률로 정리한 통합본이다. 리뷰 1은 의사결정자가 빠르게 읽을 수 있는 수준의 통합 요약에 가깝고, 리뷰 2는 실제 개선 계획으로 옮기기 쉬운 상세 설계 노트에 가깝다. 따라서 본 보고서는 두 리뷰를 경쟁시키지 않고 다음 기준으로 합쳤다.

- 숫자와 상태값은 실제 업로드 파일에서 재검산한 값을 우선한다.
- 두 리뷰가 공통으로 말한 항목은 "공통 확인"으로 승격한다.
- 한 리뷰만 발견한 항목이 실제 파일로 재현되면 "고유 발견이지만 유효"로 분류한다.
- 실제 파일 검산에서 범위 차이가 드러난 숫자는 "오류"보다 "측정 범위 보정 필요"로 분류한다.

---

## 2. 실제 source ZIP inventory 대조

### 2.1 ZIP 물리 메타데이터

| 항목 | 실제 확인값 |
| --- | ---: |
| SHA-256 | `7b99056858b0855ef7ce7ca66935377dacff0cf2c37569ec2ed301ab661de7d5` |
| 전체 ZIP entries | 1,525 |
| 파일 entries | 1,525 |
| 디렉터리 entries | 0 |
| root prefix | `LLMwiki/` |
| timestamp unique count | 1 |
| timestamp min/max | `1980-01-01T00:00:00` |
| 압축 전 크기 | 232,005,787 bytes |
| source manifest file count | 1,524 |
| source manifest digest | `c15fec6b6ca39c44515c49d1ba70e6aac18444ef5f168f10d3e492560f105dd6` |

두 리뷰가 말한 source ZIP SHA, 1,525 entries, normalized timestamp, root prefix는 실제 ZIP과 일치한다.

### 2.2 prefix별 파일 수

| prefix | 파일 수 |
| --- | ---: |
| `raw/` | 446 |
| `wiki/` | 417 |
| `ops/` | 369 |
| `tests/` | 174 |
| `system/` | 71 |
| root files | 19 |
| `.codex/` | 10 |
| `mk/` | 10 |
| `tools/` | 6 |
| `.github/` | 2 |
| `.ouroboros/` | 1 |

두 리뷰가 "source package는 raw repository snapshot이 아니라 policy-driven release source package"라고 해석한 것은 맞다. 다만 2026-05-11 기존 리뷰의 `LLMwiki.zip`은 전체 2,102 entries, 파일 1,985, 디렉터리 117인 다른 성격의 raw ZIP이었다. 현재 대조 대상은 `LLMwiki-source.zip`이며, packaging policy에 따라 `ops/reports/`, `ops/operator/`, `external-reports/`, `runs/`, `tmp/`, `build/`, `.venv/`가 제외된다.

### 2.3 확장자별 파일 수

| 확장자 | 파일 수 |
| --- | ---: |
| `.md` | 893 |
| `.py` | 395 |
| `.json` | 136 |
| `.pdf` | 61 |
| `.toml` | 11 |
| `.mk` | 10 |
| 없음 | 5 |
| `.txt` | 5 |
| `.yaml` | 5 |
| `.yml` | 2 |
| `.ini` | 1 |
| `.lock` | 1 |

### 2.4 `release-archive-self-description.json` 확인

source package 내부 `release-archive-self-description.json`은 다음을 명시한다.

- `artifact_kind=release_archive_self_description`
- `profile=fast`
- `evidence_linkage.embedded_evidence_policy=digest_link_only`
- `post_seal_authority=ops/reports/release-closeout-batch-manifest.json`
- `source_package_embeds_report_payloads=false`
- `ops/reports/`, `ops/operator/`, `external-reports/`, `runs/`, `tmp/`, `build/` 제외
- linked artifact payload는 ZIP에 포함하지 않고 path/sha256/size로만 연결

리뷰 2가 지적한 "self-description의 profile은 fast이고 업로드된 full smoke report는 profile=full"이라는 관찰은 실제 파일과 일치한다. 이것은 즉시 결함이라기보다, pre-seal package snapshot과 post-seal/full smoke evidence 사이의 phase vocabulary를 더 명확히 해야 한다는 UX 개선 포인트다.

---

## 3. Release evidence 실제 대조

### 3.1 closeout summary

| 필드 | 실제 값 |
| --- | --- |
| `artifact_kind` | `release_closeout_summary` |
| `generated_at` | `2026-05-13T07:46:59Z` |
| `source_tree_fingerprint` | `b8005f5a5ba6662fb30af27b41cd3a728eddd07fc5ae36534610a12799a52de6` |
| `status` | `pass` |
| `checked_in_release_ready` | `true` |
| `live_rerun_release_ready` | `true` |
| `conditional_release_ready` | `false` |
| `clean_release_ready` | `true` |
| `release_readiness_state` | `clean_pass` |
| `machine_release_allowed` | `true` |
| `operator_release_allowed` | `true` |
| `requires_accepted_risk_review` | `false` |
| `live_make_check.status` | `pass` |
| `live_make_check.ready` | `true` |
| `live_make_check.represents_full_suite` | `true` |
| `live_make_check.nodeid_count` | 1,141 |

두 리뷰가 release authority가 clean pass라고 판정한 것은 실제 파일과 일치한다.

### 3.2 batch manifest

| 필드 | 실제 값 |
| --- | --- |
| `artifact_kind` | `release_closeout_batch_manifest` |
| `generated_at` | `2026-05-13T07:46:59Z` |
| `status` | `pass` |
| `batch_integrity_status` | `pass` |
| `distribution_package.status` | `materialized` |
| `distribution_package.archive_profile` | `source_content_package` |
| `distribution_package.sha256` | `7b99056858b0855ef7ce7ca66935377dacff0cf2c37569ec2ed301ab661de7d5` |
| `distribution_package.file_count` | 1,525 |
| `path_set_matches_release_manifest` | `true` |
| `content_digest_matches_release_manifest` | `true` |
| `release_authority_status` | `clean_pass` |
| `semantic_release_status` | `clean_pass` |
| `sealed_release_status` | `sealed_clean_pass` |
| `machine_release_status` | `allowed` |
| `operator_release_status` | `allowed` |
| `learning_claim_allowed` | `false` |
| `accepted_risk_count` | 1 |
| `gate_attention_count` | 0 |

batch manifest에는 이미 `status_semantics`와 `status_v2_preview`가 들어 있다. 두 리뷰의 "status v2 preview를 실제 migration으로 끌어올려야 한다"는 권고는 유효하다. 현재 구조는 호환성 필드와 의미론적 필드가 공존하는 과도기 상태다.

### 3.3 finality attestation과 fixed-point

| 항목 | 실제 값 |
| --- | --- |
| fixed-point `status` | `pass` |
| fixed-point `iteration_count` | 4 |
| fixed-point `converged` | `true` |
| fixed-point `converged_iteration` | 4 |
| finality `finality_status` | `pass` |
| finality `matches_fixed_point_digest_map` | `true` |
| finality digest mismatch | 없음 |

두 리뷰가 "fixed-point 4회 수렴과 finality pass가 release seal을 강하게 보강한다"고 평가한 것은 실제 파일과 일치한다.

### 3.4 evidence dashboard / lane / clean blocker ledger

| 항목 | 실제 값 |
| --- | --- |
| dashboard `status` | `pass` |
| dashboard closeout input status | `pass` |
| dashboard closeout release state | `clean_pass` |
| lane `clean_lane_status` | `pass` |
| lane `conditional_lane_status` | `pass` |
| lane `auto_improve_lane_status` | `pass` |
| lane `learning_lane_status` | `pass` |
| lane `release_authority_status` | `clean_pass` |
| ledger `blocker_count` | 0 |
| ledger `clean_lane_blocking_family_count` | 0 |
| ledger `learning_claim_blocking_family_count` | 0 |
| ledger `accepted_risk_family_count` | 1 |
| ledger `advisory_lifecycle_family_count` | 1 |
| ledger `learning_claim_allowed` | `false` |

clean blocker ledger에는 accepted advisory가 1개 있으며, 내용은 `generated_index_archive_advisory`다. `risk_owner=runtime-maintainer`, `expires_at=2026-05-20T07:46:59Z`, `closure_action=Rerun generated-artifact-index before the next release closeout.`가 이미 들어 있다. 따라서 리뷰들이 말한 "advisory lifecycle 강화"는 방향은 맞지만, 현재 산출물에는 이미 owner/expiry/closure action 일부가 존재한다. 개선은 "필드 추가"보다 "만료·반복 시 자동 승격과 dashboard attention 연결"에 초점을 맞춰야 한다.

### 3.5 risk taxonomy

| 항목 | 실제 값 |
| --- | ---: |
| risk code count | 43 |
| clean-lane blocking count | 30 |
| clean-lane non-blocking count | 13 |
| conditional operator review count | 38 |
| learning-claim blocking count | 14 |
| advisory lifecycle backlog count | 2 |

두 리뷰가 risk taxonomy를 clean lane, conditional lane, learning claim lane, advisory lifecycle로 분리한 것은 실제 파일과 일치한다.

### 3.6 full-suite 증거

| 항목 | 실제 값 |
| --- | ---: |
| JUnit testcase count | 1141 |
| failures | 0 |
| errors | 0 |
| skipped | 0 |
| log 요약 | `1141 passed in 308.37s (0:05:08)` |

업로드된 JUnit/log 증거는 두 리뷰의 `1,141 passed` 주장과 일치한다. 본 검토에서도 `.venv/bin/python -m pytest --collect-only -q`를 실행해 1,141개 테스트 node 수집을 재확인했다.

---

## 4. 직접 재실행 검증 결과

이번 검토에서 실제 source package 추출본 위에서 수행한 명령과 결과는 다음과 같다.

| 명령 | 결과 | 해석 |
| --- | --- | --- |
| `make dev-install` | pass, 약 4.7초 | `uv`로 `.venv` 생성/갱신 및 editable install 완료 |
| `make static` | pass, 약 16.2초 | `ruff check ops/scripts tests tools` 통과, `mypy @ops/mypy-allowlist.txt` 210 source files 통과 |
| `.venv/bin/python -m pytest --collect-only -q` | pass, 1,141 tests 수집, 약 10.3초 | 업로드 full-suite 증거와 test scope 일치 |
| `.venv/bin/python -m pytest tests/test_source_package_clean_extract.py -q` | pass, 2 tests | source package clean extract contract 정상 |
| `.venv/bin/python -m ops.scripts.core.artifact_freshness_runtime --help` | pass | canonical module path는 정상 |
| `.venv/bin/python -m ops.scripts.artifact_freshness_runtime --help` | fail | Python 3.13 flat alias 실행에서 `sys.argv[0]=None`으로 `argparse` TypeError |
| `.venv/bin/python -m ops.scripts.test_execution_summary --help` | fail | 같은 flat alias 결함 |
| `.venv/bin/python -m ops.scripts.release_evidence_dashboard --help` | fail | 같은 flat alias 결함 |
| `make check-clean` | fail, 약 1.9초 | `artifact-freshness-check`에서 flat alias 결함으로 즉시 중단 |
| `make test-artifact-finalization` | fail, 8 failures, 약 2.9초 | source package에는 `ops/reports/`, `ops/script-output-surfaces.json` 등이 의도적으로 없어서 full-vault 전용 target이 실패 |

이 결과는 두 리뷰의 핵심 실행 주장과 일치한다. 특히 리뷰 B가 강조한 Python 3.13 flat alias 결함은 본 검토에서도 그대로 재현됐다.

### 4.1 Python 3.13 flat alias 결함의 실제 원인

실제 `ops/scripts/__init__.py`는 `_ReexportFinder`와 `_ProxyLoader`로 `ops.scripts.<flat_name>`을 `ops.scripts.<subpackage>.<name>`으로 우회한다. 이 구조는 import fallback에는 유용하지만, `python -m` 실행에서는 loader/spec/runpy 메타데이터가 충분히 표준적이지 않아 `argparse.ArgumentParser()`가 `_sys.argv[0]`를 읽는 순간 `None`을 만나 실패한다.

실제 실패 핵심은 다음이다.

```text
File "/usr/lib/python3.13/argparse.py", line 1802, in __init__
  prog = _os.path.basename(_sys.argv[0])
TypeError: expected str, bytes or os.PathLike object, not NoneType
```

따라서 두 리뷰의 "기능 로직 결함이 아니라 공식 실행 표면 결함"이라는 해석은 정확하다.

### 4.2 source package에서 `test-artifact-finalization`이 실패하는 이유

실제 source package에는 다음이 포함되지 않는다.

- `ops/reports/`
- `ops/operator/`
- `external-reports/`
- `runs/`
- `tmp/`
- `build/`
- `ops/script-output-surfaces.json`

따라서 `test-artifact-finalization`이 source package 추출본에서 실패하는 것은 release artifact 결함이 아니라 lane mismatch다. 다만 실패 메시지가 "이 target은 full-vault 전용"이라고 먼저 설명하지 않으므로, 두 리뷰의 "friendly fail-fast 필요" 권고는 타당하다.

---

## 5. 기존 리뷰와의 대조

### 5.1 2026-05-11 기존 리뷰 대비

2026-05-11 기존 리뷰는 당시 ZIP 기준으로 다음을 최우선 개선으로 지목했다.

- batch manifest distribution binding
- source-tree coherence divergence
- full-suite 1103/1107 재봉인
- 외부보고서 lifecycle 갱신
- clean baseline fingerprint 정리

2026-05-13 현재 산출물 기준으로 이 중 상당 부분은 닫혔다.

| 2026-05-11 주요 항목 | 2026-05-13 실제 상태 |
| --- | --- |
| distribution ZIP binding 미완 | batch manifest `distribution_package.sha256`가 source ZIP SHA와 일치, `external_source_zip_bound.status=bound` |
| full-suite count 불일치 | JUnit/log와 closeout summary 모두 1,141 full-suite scope로 일치 |
| source-tree coherence divergence | closeout summary와 dashboard에서 source-tree coherence pass |
| finality/fixed-point 불명확 | fixed-point 4회 수렴, finality attestation pass |
| external report lifecycle 미정리 | source package에서는 external-reports 제외, report reference manifest는 post-seal linkage로 관리 |

따라서 두 새 리뷰가 "2026-05-11 P0였던 release sealing/binding/finality 문제는 2026-05-13에서 대부분 해소됐다"고 판정한 것은 실제 파일과 일치한다.

### 5.2 직전 2026-05-13 기존 보고서 대비

직전 `llmwiki_anti_slop_self_improvement_long_term_report_20260513.md`는 다음을 주요 결론으로 삼았다.

- release authority는 clean/sealed 상태다.
- long-term improvement는 anti-slop와 self-improvement claim guard에 초점을 맞춰야 한다.
- source package는 generated reports를 포함하지 않는 구조가 맞다.
- learning claim은 `false`로 닫혀 있으며 이것이 안전한 설계다.
- Python 3.13 flat alias/Makefile 실행 표면 결함을 P0로 봐야 한다.

두 새 리뷰는 직전 보고서의 결론을 거의 그대로 확장한다. 특히 리뷰 2는 직전 보고서의 ZIP inventory, AGENTS/public-private boundary, source package lane UX, placeholder terminology, advisory lifecycle, evidence vs improvement naming을 더 상세하게 재구성했다.

---

## 6. 두 리뷰 주요 주장별 실제 대조 매트릭스

| 주장 | 리뷰 출처 | 실제 파일/실행 대조 | 판정 |
| --- | --- | --- | --- |
| 현재 release authority는 `clean_pass`다 | 리뷰 1·2 | closeout summary, batch manifest, lane summary 모두 `clean_pass` | 확인 |
| 현재 sealed release는 `sealed_clean_pass`다 | 리뷰 1·2 | batch manifest `sealed_release_status=sealed_clean_pass` | 확인 |
| source ZIP SHA는 `7b990568...de7d5`다 | 리뷰 1·2 | 직접 SHA-256 계산 및 batch manifest/post-seal 일치 | 확인 |
| source ZIP entries는 1,525다 | 리뷰 1·2 | zipfile inventory 1,525 files, dirs 0 | 확인 |
| timestamp는 1980-01-01로 정규화됐다 | 리뷰 1·2 | ZIP entry date_time unique count 1 | 확인 |
| full-suite는 1,141 pass다 | 리뷰 1·2 | JUnit testcase 1,141, fail/error/skip 0, log 1,141 passed | 확인 |
| `make static`은 통과한다 | 리뷰 1·2 | 본 검토에서 재실행 pass | 확인 |
| Python 3.13 flat alias가 깨진다 | 리뷰 1·2, 특히 리뷰 B | 본 검토에서 flat `--help`와 `make check-clean` 재현 fail | 확인 |
| canonical module path는 정상이다 | 리뷰 1·2 | `ops.scripts.core.artifact_freshness_runtime --help` pass | 확인 |
| source package에서 full-vault target이 실패한다 | 리뷰 1·2 | `make test-artifact-finalization` 8 failures 재현 | 확인 |
| 이것은 packaging 결함이 아니라 lane UX 문제다 | 리뷰 1·2 | source package exclusion policy와 self-description 확인 | 확인 |
| `build_report` 직접 보유 모듈 수는 50개다 | 리뷰 1·2 | AST/regex 스캔 50개 | 확인 |
| Python 파일 수는 395개다 | 리뷰 1·2 | 직접 스캔 395개 | 확인 |
| 전체 nonblank LOC는 118,605다 | 리뷰 1·2 | 직접 스캔 118,605 | 확인 |
| `build_batch_manifest`는 348 LOC/분기 54 수준이다 | 리뷰 1·2 | AST 스캔 348 LOC, branch count 54 | 확인 |
| `placeholder`는 약 222회다 | 리뷰 1·2 | source package에서 `.venv` 제외 전체 텍스트 221회, Python 파일만 166회 | 거의 확인, 측정 범위 명시 필요 |
| `TODO`는 7회다 | 리뷰 1·2 | `.venv` 제외 전체 텍스트 5회, Python 파일만 2회 | 부분 보정 필요 |
| `Any`는 2,125회다 | 리뷰 1·2 | `.venv` 제외 전체 텍스트 1,914회, Python 파일만 1,886회 | 부분 보정 필요 |
| advisory backlog에는 owner/expiry가 필요하다 | 리뷰 1·2 | 현재 ledger에는 이미 owner/expiry/closure_action 일부 존재 | 방향은 맞지만 표현 보정 필요 |
| CI matrix는 3.12/3.14만 있다 | 리뷰 1·2 | `.github/workflows/ci.yml` 확인 | 확인 |
| 의존성은 lockfile이 CI/release에 연결되지 않았다 | 리뷰 1·2 | CI는 pip + requirements-dev range install, `uv.lock` 존재 | 확인 |
| project scripts는 다수 존재한다 | 리뷰 2 | `[project.scripts]` 65개 확인 | 확인 |
| Makefile flat `python -m ops.scripts.*` 호출이 넓다 | 리뷰 2 | mk/Makefile에서 164개 flat 호출 패턴 확인 | 확인 |

---

## 7. 보정이 필요한 부분

두 리뷰의 핵심 결론은 강하게 맞지만, 다음 항목은 보고서·실행 계획에 옮길 때 표현을 보정하는 것이 좋다.

### 7.1 advisory backlog 필드는 이미 일부 존재한다

두 리뷰는 advisory backlog에 owner, expiry, closure action, last reviewed, next check를 추가하라고 제안한다. 실제 `release-clean-blocker-ledger.json`의 accepted advisory에는 이미 다음 필드가 있다.

- `risk_owner=runtime-maintainer`
- `expires_at=2026-05-20T07:46:59Z`
- `closure_action=Rerun generated-artifact-index before the next release closeout.`
- `rollback_trigger=Treat generated artifact index advisory debt as a blocker if current artifacts go missing.`

따라서 개선 문구는 "필드를 새로 추가"보다 다음처럼 바꾸는 편이 정확하다.

> advisory backlog의 기본 필드는 이미 존재하므로, 다음 개선은 만료·반복·미조치 상태를 자동으로 gate attention 또는 operator review required로 승격하는 lifecycle enforcement다.

### 7.2 placeholder/TODO/Any 수치는 측정 범위가 필요하다

두 리뷰의 문자열 카운트는 대체로 맞지만, 실제 재스캔에서는 범위에 따라 달라졌다.

| 패턴 | 두 리뷰 주장 | 본 검토 재스캔 |
| --- | ---: | ---: |
| `placeholder` | 222 | `.venv` 제외 전체 텍스트 221, Python 파일만 166 |
| `TODO` | 7 | `.venv` 제외 전체 텍스트 5, Python 파일만 2 |
| `no cover` | 143 | `.venv` 제외 전체 텍스트 143 |
| `Any` | 2,125 | `.venv` 제외 전체 텍스트 1,914, Python 파일만 1,886 |
| `type: ignore` | 0 | 0 |
| `FIXME` | 0 | 0 |
| `HACK` | 0 | 0 |

이는 결론을 뒤집는 차이가 아니다. 다만 앞으로 anti-slop score를 만들 때는 "Python source만", "schema 포함", "문서 포함", "vendored/venv 제외" 같은 범위를 필수 metadata로 기록해야 한다.

### 7.3 dashboard top-level에 일부 상태 필드가 직접 존재하지 않는다

리뷰 일부 문장은 dashboard top-level에 `learning_claim_allowed`나 `confirmed_learning_improvement_status`가 있는 것처럼 읽힐 수 있다. 실제 값은 `inputs.learning_delta_scoreboard` 하위에 존재한다. 따라서 소비자 문서에서는 "dashboard가 하위 input으로 노출한다"는 식으로 표현하는 것이 더 정확하다.

### 7.4 fast self-description과 full smoke report의 관계를 결함처럼 과장하지 말 것

source package 내부 self-description은 `profile=fast`이고 업로드된 full smoke report는 `profile=full`이다. 이 자체만으로 결함이라고 볼 근거는 없다. 그러나 운영자 UX 측면에서는 `build_profile`, `seal_profile`, `post_seal_profile`을 나눠 설명하면 혼동을 줄일 수 있다.

---

## 8. Anti-Slop 관점의 장기 개선 방안

### 8.1 P0 — 공식 실행 표면 봉인

현재 가장 분명한 P0는 Python 3.13에서 flat alias `python -m ops.scripts.<name>`가 실패한다는 점이다. 이 결함은 본 검토에서 재현됐다. CI가 Python 3.13을 포함하지 않으므로, 지원 범위 내 버전 회귀를 놓치고 있다.

권장 개선은 다음 순서다.

1. CI matrix에 Python 3.13을 추가한다.
2. `tests/test_cli_surface_execution_contract.py`를 신설해 다음을 모두 검증한다.
   - `[project.scripts]` 65개 console script의 `--help`
   - `mk/*.mk`와 `Makefile`의 `python -m ops.scripts.*` 호출 module의 `--help`
   - `ops/script-module-surfaces.json` 또는 그 대체 inventory의 direct CLI facade
3. flat alias 유지 전략을 결정한다.
   - 최단기 안정화: Makefile과 `source_command`를 canonical module path로 전환한다.
   - 하위 호환 유지: 실제 wrapper 파일을 생성한다.
   - 비권장: `_ProxyLoader`를 더 복잡하게 보강한다. 이는 Python minor version별 runpy 회귀 리스크가 남는다.
4. `make check-clean`이 Python 3.12/3.13/3.14에서 모두 pass해야 완료로 본다.

### 8.2 P0 — source package/full-vault lane UX 개선

source package에서 full-vault 전용 target을 실행하면 현재는 missing artifact 실패가 나온다. 이 메시지는 기술적으로 맞지만 anti-slop UX로는 부족하다.

권장 개선:

- `ops/policies/execution-lanes.json`을 만들어 각 Make target의 허용 lane을 선언한다.
- source package root에 `release-archive-self-description.json`이 있고 `ops/reports/`가 없으면 `source_package_extract` mode로 판정한다.
- full-vault 전용 target 실행 시 1초 이내에 다음 구조의 에러를 출력한다.

```text
This target requires a full vault with generated release reports.
Detected source package extract: ops/reports/ is intentionally absent.
Use: make source-package-check
```

이 개선은 release correctness를 바꾸지 않지만 사용자의 오판을 크게 줄인다.

### 8.3 P0/P1 — status v2를 preview에서 migration으로 전환

batch manifest에는 이미 `status_v2_preview`가 있다. 다음 단계는 preview를 실제 소비자 migration으로 옮기는 것이다.

권장 vocabulary:

| 축 | 필드 | 의미 |
| --- | --- | --- |
| artifact materialization | `artifact_materialization_status` | 산출물이 실제로 생성되었는가 |
| release authority | `release_authority_status` | clean/conditional/blocked 등 릴리스 의미론 |
| sealing | `sealed_release_status` | package/digest/finality 봉인 상태 |
| finality | `finality_status` | fixed-point digest map과 최종 산출물 일치 |
| learning claim | `learning_claim_status` | 개선 주장 허용 여부 |
| advisory lifecycle | `advisory_lifecycle_status` | non-blocking backlog 상태 |

모든 human-facing report 첫 문장은 다음처럼 고정하는 것이 좋다.

```text
Release authority: clean_pass / sealed_clean_pass.
Learning improvement claim: not claimed / not allowed.
Advisory lifecycle: accepted non-blocking backlog = 1.
```

### 8.4 P1 — 거대 builder 분해

실제 AST 스캔 결과 다음이 최우선 분해 대상이다.

| 우선순위 | 파일/함수 | 현재 상태 | 목표 |
| --- | --- | --- | --- |
| 1 | `release_closeout_batch_manifest.py::build_batch_manifest` | 348 LOC, branch 54 | 100~140 LOC orchestrator |
| 2 | `release_evidence_dashboard.py::_learning_delta_guard_summary` | 226 LOC, branch 37 | learning lane projection으로 분리 |
| 3 | `release_evidence_dashboard.py::_finalizer_duration_signal` | 202 LOC, branch 42 | finalizer signal module로 분리 |
| 4 | `release_closeout_summary.py::build_report` | 223 LOC, branch 26 | component normalize + authority synthesize 분리 |
| 5 | `learning_claim_evidence_bundle.py::build_report` | 221 LOC, branch 40 | evidence bundle builder 분리 |
| 6 | `auto_improve_readiness_runtime.py` | 2,676 physical LOC | execution/promotion/claim/preflight 분리 |
| 7 | `test_execution_summary.py` | 1,590 physical LOC | command runner, JUnit parser, aggregate writer 분리 |

분해 원칙은 두 리뷰가 제시한 대로 `load / normalize / classify / decide / render / seal`이다. 중요한 점은 추상화를 늘리는 것이 아니라, filesystem 없이 unit test 가능한 순수 decision unit을 만드는 것이다.

### 8.5 P1 — report writer proliferation 축소

`build_report` 직접 보유 모듈은 50개다. 이는 schema-backed report 문화를 잘 만든 결과이지만, 동시에 vocabulary drift와 중복 writer slop의 신호다.

권장 개선:

- 공통 `ReportEnvelopeBuilder`나 `ReportNode`를 만들되, 단일 거대 추상화가 되지 않도록 release/eval/learning/core 별로 작은 helper를 둔다.
- 각 report schema에 `surface_role`과 `canonical_owner`를 추가한다.
- report surface를 `authoritative`, `derived-summary`, `operator-handoff`, `advisory`, `tmp-diagnostic`으로 분류한다.
- 새 report 추가 전 "기존 report graph projection으로 해결 가능한가?"를 체크한다.

### 8.6 P1 — 의존성 결정성 강화

실제 `.github/workflows/ci.yml`은 Python 3.12/3.14에서 pip cache와 `requirements-dev.txt` range install을 사용한다. `uv.lock`은 존재하지만 CI/release 설치 경로의 authority가 아니다.

권장 개선:

- CI/release는 `uv sync --locked --extra dev` 또는 hash-locked requirements를 사용한다.
- `requirements-dev.txt`는 개발자 편의용 range 파일로만 남긴다.
- `ops/reports/toolchain-lock-report.json`을 생성해 다음을 기록한다.
  - Python version
  - platform
  - pytest/ruff/mypy/jsonschema/PyYAML versions
  - `uv.lock` digest
  - install mode
- `release-closeout-summary.json`와 `test-execution-summary-full.json`에 toolchain digest를 연결한다.

---

## 9. Self-Improvement 관점의 장기 개선 방안

### 9.1 release pass와 learning claim의 분리 유지

현재 가장 좋은 점은 `clean_release_ready=true`이면서도 `learning_claim_allowed=false`라는 점이다. 즉 "배포 가능"과 "자가 개선이 입증됨"을 섞지 않는다. 이 구조는 반드시 유지해야 한다.

권장 문구:

```text
The repository is release-ready.
It does not claim confirmed learning improvement.
```

한국어 report에서는 다음처럼 표현한다.

```text
릴리스는 허용된다. 그러나 자가 개선이 입증됐다고 주장하지 않는다.
```

### 9.2 self-improvement 상태 5단계 명시화

두 리뷰가 공통으로 제안한 5단계 모델을 채택하는 것이 좋다.

| 단계 | 의미 | release와의 관계 |
| --- | --- | --- |
| `proposal_ready` | 후보 개선안을 만들 수 있음 | release와 독립 |
| `trial_runnable` | 격리 실행 가능 | release와 독립 |
| `evidence_complete` | before/after, same-eval, digest 증거가 있음 | claim 전 단계 |
| `promotion_allowed` | policy상 keep 가능 | release와 분리 |
| `claim_allowed` | 외부 문서에서 개선됐다고 말할 수 있음 | 가장 엄격 |

현재는 evidence cohort가 auto-confirmed이고 claim은 not-ready인 구조가 맞다. 다만 명칭이 오해를 만들 수 있으므로 다음처럼 바꾼다.

- `confirmed_evidence_status` → `evidence_cohort_status`
- `confirmed_learning_improvement_status` → `improvement_claim_status`
- `confirmed_wording_allowed` → `claim_wording_allowed`

### 9.3 predicate naming 개선

현재 dashboard 하위 learning delta에는 `confirmed_blocking_predicate_ids=["no_learning_claim_blockers"]`가 있다. 실제 predicate result에서는 이 ID가 `status=fail`이고 observed value는 `learning_claim_blocker_count=2`다. 즉 의미는 맞지만 이름이 직관에 반한다.

권장 이름:

- `learning_claim_blocker_clearance_failed`
- `learning_claim_blockers_present`
- `learning_claim_clearance_required`

부정형 문장(`no_learning_claim_blockers`)을 실패 predicate ID로 쓰지 않는 것이 좋다.

### 9.4 promotion-grade evidence 필수화

새 self-improvement run에는 다음이 필수여야 한다.

| 필드 | 이유 |
| --- | --- |
| `hypothesis` | 무엇을 개선하려 했는지 명시 |
| `one_mechanism_assertion` | 한 번에 하나의 mechanism 원칙 |
| `baseline_eval_digest` | before 증거 |
| `candidate_eval_digest` | after 증거 |
| `same_eval_basis` | 동일 평가 조건 보장 |
| `secondary_axis_non_regression` | 부작용 방지 |
| `behavior_delta_digest` | 실제 행동 변화 hash |
| `changed_files_manifest` | 변경 범위 추적 |
| `holdout_eval_digest` | overfit 방지 |
| `negative_control_result` | 개선 착시 방지 |
| `rollback_rehearsal_result` | 되돌릴 수 있음 보장 |
| `promotion_decision` | keep/discard 근거 |
| `claim_wording_decision` | 외부 문구 허용 여부 |

legacy reconstruction은 historical compatibility에만 남기고, 새 run은 reconstruction-free를 목표로 한다.

### 9.5 structural budget을 self-improvement에 연결

자가 개선 시스템이 장기적으로 안전하려면 "성능 개선"만 보지 말고 "구조가 덜 복잡해졌는가"도 봐야 한다.

권장 structural budget:

| 지표 | warn | block 또는 review-required |
| --- | ---: | ---: |
| single function LOC | 200 | 300 |
| branch count | 30 | 50 |
| direct `build_report` writer count | 55 | 65 |
| new branch without test delta | 5 | 10 |
| duplicated status axis fields | 3 | 5 |
| new Make target without lane metadata | 1 | 3 |

초기에는 release blocker가 아니라 dashboard attention과 refactor proposal 생성으로 연결한다. 반복 초과 시 operator review required로 승격한다.

### 9.6 policy pruning을 positive signal로 인정

self-improvement는 규칙을 더하는 방향으로만 가면 장기적으로 slop를 만든다. 다음도 개선으로 인정해야 한다.

- 중복 policy branch 삭제
- 같은 safety를 더 적은 status field로 표현
- giant builder 분해 후 invariant 유지
- obsolete report surface archive/demotion
- 같은 test coverage를 더 명확한 semantic shard로 재배치

---

## 10. 최종 우선순위 로드맵

### P0 — 다음 릴리스 전 닫을 항목

| ID | 개선 항목 | 완료 기준 |
| --- | --- | --- |
| P0-1 | Python 3.13 flat CLI alias 봉인 | Python 3.12/3.13/3.14에서 flat/canonical/console script `--help` pass, `make check-clean` pass |
| P0-2 | CI matrix에 Python 3.13 추가 | GitHub Actions matrix에 3.13 포함 |
| P0-3 | source package lane fail-fast | full-vault target 실행 시 missing artifact stacktrace 대신 lane 안내 출력 |
| P0-4 | status v2 migration plan | legacy `status` consumer inventory와 v2 schema migration guide 작성 |
| P0-5 | learning predicate naming 정리 | `no_learning_claim_blockers` 같은 부정형 실패 ID 제거 또는 alias 처리 |
| P0-6 | dependency lock 연결 시작 | CI/release 설치가 lock digest를 사용하거나 최소한 toolchain report를 생성 |

### P1 — 단기 구조 개선

| ID | 개선 항목 | 완료 기준 |
| --- | --- | --- |
| P1-1 | `build_batch_manifest` 분해 | 100~140 LOC orchestrator, branch-heavy decision unit 분리 |
| P1-2 | dashboard learning/finality signal 분리 | `_learning_delta_guard_summary`, `_finalizer_duration_signal` 독립 module화 |
| P1-3 | `auto_improve_readiness_runtime.py` 분해 | execution/promotion/claim/release preflight dataclass 분리 |
| P1-4 | `test_execution_summary.py` evidence kernel화 | command runner, JUnit parser, aggregate writer 분리 |
| P1-5 | report surface role 라벨링 | `surface_role`, `canonical_owner` schema 필드 도입 |
| P1-6 | advisory lifecycle enforcement | expiry/반복/미조치 시 gate attention 또는 operator review 자동 승격 |
| P1-7 | self-improvement 5단계 JSON 모델 | proposal/trial/evidence/promotion/claim 필드 분리 |

### P2 — 중기 아키텍처 개선

| ID | 개선 항목 | 완료 기준 |
| --- | --- | --- |
| P2-1 | release evidence DAG | artifact/command/input digest/decision node로 claim 추적 가능 |
| P2-2 | report graph runtime | report writer가 공통 graph projection 사용 |
| P2-3 | reproducible build double-run | 동일 checkout 2회 빌드 hash 또는 manifest digest 비교 |
| P2-4 | SBOM/provenance 단일 attestation | CycloneDX/SPDX/in-toto/source ZIP digest 연결 |
| P2-5 | report text ↔ machine decision round-trip test | human wording이 허용된 field 조합에서만 출현 |
| P2-6 | anti-slop score | stale evidence, ambiguous vocabulary, expired advisory, lane mismatch를 component score로 표시 |
| P2-7 | outcome metrics → refactor proposal | structural budget 초과가 자동 refactor proposal로 연결 |
| P2-8 | policy pruning positive signal | 규칙 삭제/중복 축소도 promotion 근거로 인정 |

---

## 11. 실행 계획으로 옮길 때의 최소 안전 설계

두 리뷰의 권고를 실제 구현으로 옮길 때는 다음 순서를 추천한다. 이 순서는 작은 변경으로 가장 큰 불확실성을 먼저 제거한다.

1. **CLI surface test부터 만든다.**  
   현재 실제로 깨지는 지점은 Python 3.13 flat alias다. 먼저 테스트로 고정해야 한다.

2. **Makefile canonical path 전환 또는 wrapper 파일 생성 중 하나를 선택한다.**  
   장기적으로는 실제 wrapper 파일이 가장 명확하다. 단기적으로는 Makefile canonical path 전환이 더 작다.

3. **source package lane fail-fast를 추가한다.**  
   release correctness를 건드리지 않고 사용자 오판을 줄이는 고효율 개선이다.

4. **status v2 migration guide를 문서화한다.**  
   실제 schema 변경 전 consumer inventory를 만든다.

5. **`build_batch_manifest`만 먼저 분해한다.**  
   세 리뷰가 공통으로 최고 위험 hotspot으로 본다. 한 번에 모든 builder를 분해하지 않는다.

6. **self-improvement naming을 바꾼다.**  
   evidence confirmed와 improvement claim confirmed를 이름부터 분리한다.

7. **toolchain report를 추가한다.**  
   lockfile 강제 전이라도 최소한 현재 실행 버전과 lock digest를 release evidence에 남긴다.

---

## 12. 최종 판정

두 리뷰는 실제 파일과 대체로 정확히 일치한다. 특히 다음 핵심 판단은 모두 확인됐다.

- 현재 source ZIP은 `7b99056858b0855ef7ce7ca66935377dacff0cf2c37569ec2ed301ab661de7d5`이며 batch manifest/post-seal/source package가 같은 digest를 가리킨다.
- release authority는 `clean_pass`, sealed release는 `sealed_clean_pass`다.
- full-suite evidence는 1,141/1,141 pass다.
- clean blocker는 0이고 accepted advisory는 non-blocking이다.
- learning claim은 의도적으로 허용되지 않는다.
- Python 3.13 flat alias CLI 결함은 실제로 재현된다.
- source package에서 full-vault target이 실패하는 것은 release 결함이 아니라 lane boundary UX 문제다.
- 코드 구조상 giant builder, report writer proliferation, status vocabulary drift risk는 실제로 존재한다.

따라서 새 개선 보고서의 최종 권고는 다음 한 문장으로 압축된다.

> **LLMwiki의 다음 장기 최적화 목표는 release pass를 더 강하게 주장하는 것이 아니라, 이미 pass하는 authority 체계를 더 재현 가능하고 덜 중복되며 덜 오해되는 구조로 줄이는 것이다. Python 3.13 공식 실행 표면을 먼저 봉인하고, source/full-vault lane UX와 status v2를 정리한 뒤, giant report builder와 self-improvement claim model을 작은 증거 단위로 분해해야 한다.**

---

## 부록 A. 실제 검토한 주요 파일 목록

| 파일 | 역할 |
| --- | --- |
| `Codex-Subagent-Orchestrator.zip` | 작업 계약 확인 |
| `LLMwiki-source.zip` | 실제 source package |
| `release-closeout-summary.json` | release readiness authority |
| `release-closeout-batch-manifest.json` | distribution package binding 및 seal |
| `release-closeout-finality-attestation.json` | finality 검증 |
| `release-closeout-fixed-point.json` | post-check fixed-point convergence |
| `release-evidence-closeout-self-check.json` | closeout self-check |
| `release-evidence-cohort.json` | strict same fingerprint evidence cohort |
| `release-evidence-dashboard.json` | dashboard projection |
| `release-lane-summary.json` | lane summary |
| `release-clean-blocker-ledger.json` | clean/learning/advisory blocker ledger |
| `release-risk-taxonomy-matrix.json` / `.md` | risk taxonomy |
| `release-smoke-report.json` | full smoke report |
| `release-smoke-report-fast.json` | fast smoke historical evidence |
| `release-post-seal-attestation.json` | post-seal non-cyclic sidecar |
| `test-execution-summary-full.junit.xml` | full-suite JUnit |
| `test-execution-summary-full.log` | full-suite stdout/stderr |
| `llmwiki_anti_slop_self_improvement_long_term_report_20260513.md` | 직전 2026-05-13 기존 보고서 |
| `llmwiki_two_20260511_reviews_crosscheck_improvement_report_20260511.md` | 2026-05-11 기존 비교 리뷰 |

## 부록 B. 직접 검증 로그 요약

```text
make dev-install
→ pass, uv 기반 .venv 준비

make static
→ ruff: All checks passed
→ mypy: Success: no issues found in 210 source files

.venv/bin/python -m pytest --collect-only -q
→ pass, 1,141 tests collected

.venv/bin/python -m pytest tests/test_source_package_clean_extract.py -q
→ pass, 2 tests

.venv/bin/python -m ops.scripts.core.artifact_freshness_runtime --help
→ pass

.venv/bin/python -m ops.scripts.artifact_freshness_runtime --help
→ fail, argparse TypeError because sys.argv[0] is None

make check-clean
→ fail at artifact-freshness-check due to the same flat alias TypeError

make test-artifact-finalization
→ fail, 8 failures caused by intentionally absent full-vault generated artifacts in source package
```

## 부록 C. 코드 구조 재스캔 요약

| 항목 | 실제 확인값 |
| --- | ---: |
| Python files | 395 |
| total nonblank LOC | 118,605 |
| total physical LOC | 132,226 |
| `ops/` nonblank LOC | 67,314 |
| `tests/` nonblank LOC | 50,256 |
| `tools/` nonblank LOC | 1,035 |
| direct `build_report` modules | 50 |
| `[project.scripts]` console scripts | 65 |
| `mk/`/Makefile flat `python -m ops.scripts.*` 호출 패턴 | 164 |

상위 파일:

| 파일 | nonblank LOC | physical LOC |
| --- | ---: | ---: |
| `tests/test_makefile_static_gates.py` | 2,541 | 2,703 |
| `ops/scripts/mechanism/auto_improve_readiness_runtime.py` | 2,484 | 2,676 |
| `tests/test_auto_improve_readiness_runtime.py` | 2,019 | 2,113 |
| `tests/test_mechanism_review.py` | 1,912 | 2,021 |
| `ops/scripts/release/release_closeout_summary.py` | 1,730 | 1,849 |
| `ops/scripts/mechanism/mutation_proposal_runtime.py` | 1,566 | 1,739 |
| `ops/scripts/core/artifact_freshness_runtime.py` | 1,524 | 1,693 |
| `ops/scripts/test/test_execution_summary.py` | 1,458 | 1,590 |
| `ops/scripts/release/release_closeout_fixed_point.py` | 1,451 | 1,574 |

상위 함수:

| 함수 | 파일 | LOC | branch count |
| --- | --- | ---: | ---: |
| `build_batch_manifest` | `ops/scripts/release/release_closeout_batch_manifest.py` | 348 | 54 |
| `build_report` | `ops/scripts/release/release_evidence_dashboard.py` | 231 | 21 |
| `_learning_delta_guard_summary` | `ops/scripts/release/release_evidence_dashboard.py` | 226 | 37 |
| `build_report` | `ops/scripts/release/release_closeout_summary.py` | 223 | 26 |
| `build_report` | `ops/scripts/learning/learning_claim_evidence_bundle.py` | 221 | 40 |
| `_finalizer_duration_signal` | `ops/scripts/release/release_evidence_dashboard.py` | 202 | 42 |

---

*끝.*
