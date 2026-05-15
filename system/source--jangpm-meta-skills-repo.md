---
title: "byungjunjang/jangpm-meta-skills repository"
page_type: "source"
corpus: "system"
registry_id: "W-003"
raw_path: "raw/web-snapshots/jangpm-meta-skills-readme-2026-04-12.md"
source_type: "github-snapshot"
domain: "meta-skill-workflows"
created: "2026-04-12"
aliases:
  - "source--jangpm-meta-skills-repo"
tags:
  - "corpus/system"
  - "type/source"
---

# source--jangpm-meta-skills-repo

## Title
byungjunjang/jangpm-meta-skills repository

## Source
- `raw/web-snapshots/jangpm-meta-skills-readme-2026-04-12.md`

## Type
github-repository

## Summary
이 저장소는 Claude Code와 Codex에 배포 가능한 meta-skill 묶음이다. `blueprint`, `deep-dive`, `autoresearch`, `reflect`를 연속 워크플로우로 배치해 요구사항 구체화, 설계, 최적화, 세션 마무리를 구조화한다.

## Why it matters
현재 LLM Wiki 초안도 ingest / query / lint만 있지, **세션 종료 후 reflect**, **요구사항 구체화용 deep-dive**, **설계 문서 생산용 blueprint** 같은 운영 레이어는 약하다. 이 저장소는 wiki를 일회성 답변이 아니라 반복 가능한 작업 흐름으로 묶는 데 유용하다.

## Key points
- `blueprint -> deep-dive -> implement -> autoresearch -> reflect` 순서를 권장한다.
- `blueprint`는 구조 검증 스크립트를 포함하는 설계 문서 생성에 초점을 둔다.
- `deep-dive`는 다단계 인터뷰로 요구사항을 구조화한다.
- `autoresearch`는 skill optimization 루프를 제공한다.
- `reflect`는 작업 세션 요약, 문서 업데이트 포인트, 다음 액션 정리를 담당한다.
- 배포 단위를 skill 폴더로 잡아 Claude Code와 Codex 모두에 맞춘다.

## Limitations / caveats
- meta-skill composition은 강력하지만, 각 단계가 실제 runtime state machine으로 연결되지는 않는다.
- wiki maintenance에 바로 쓰려면 page naming, source trace, link policy 같은 위키 특화 규칙이 추가로 필요하다.
- skill 배포 방식과 wiki vault 구조는 별도 계층으로 조정해야 한다.

## Related pages
- [[concept--planning-gates]]
- [[concept--cross-reference-maintenance]]
- [[concept--self-improving-wiki-loop]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- wiki에서 `reflect`를 별도 명령으로 둘지, 모든 major query 후 자동 실행할지?
- `blueprint`와 `deep-dive` 산출물을 wiki page로 저장할지 `ops/` artifact로 둘지?
- dual-runtime deployment를 wiki maintainer에도 적용할 필요가 있는가?

## Source trace
- `raw/web-snapshots/jangpm-meta-skills-readme-2026-04-12.md`
