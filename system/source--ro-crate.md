---
title: "Research Object Crate (RO-Crate)"
page_type: "source"
corpus: "system"
registry_id: "W-067"
raw_path: "raw/web-snapshots/Research Object Crate (RO-Crate).md"
source_type: "web-snapshot"
domain: "research-object-packaging-and-fair-metadata"
created: "2026-04-13"
aliases:
  - "source--ro-crate"
tags:
  - "corpus/system"
  - "type/source"
---

# source--ro-crate

## Title
Research Object Crate (RO-Crate)

## Source
- `raw/web-snapshots/Research Object Crate (RO-Crate).md`

## Type
web-snapshot

## Summary
RO-Crate는 dataset, workflow, software, person, publication, provenance를 JSON-LD / schema.org 기반 metadata bundle로 묶어 FAIR research object로 다루는 packaging approach다. 요지는 연구 결과를 파일 뭉치가 아니라, identifier와 relationship이 달린 portable crate로 다뤄 findability, accessibility, interoperability, reusability를 높이는 것이다.

## Why it matters
현재 system corpus는 raw registry, run ledger, schema, artifact contract를 가지고 있지만, 이들을 더 portable한 research object 관점으로 묶는 external reference는 없었다. RO-Crate는 `artifact contract + provenance packaging`을 더 넓은 metadata ecosystem 안에 놓고 보게 만든다.

## Key points
- RO-Crate packages data, methods, software, people, and outputs as a linked research object.
- FAIR is framed as metadata, identifiers, and relationships, not just file availability.
- JSON-LD and schema.org make the crate interoperable across repositories and tools.
- provenance and reuse are first-class design goals.
- the model is flexible enough to point to external assets instead of copying everything into one bundle.

## Limitations / caveats
- RO-Crate is a packaging and metadata standard, not a workflow governance system by itself.
- adopting it directly would add format overhead to a repo that currently uses lightweight Markdown and JSON artifacts.
- FAIR metadata does not automatically solve signoff, mutation control, or promotion governance.

## Related pages
- [[concept--artifact-contracts]]
- [[concept--trace-store-and-run-ledger]]
- [[source--stage1-planning-harness-mvp]]
- [[synthesis--stage1-planning-harness-bridge]]

## Open questions
- 이 repo에서 run bundle 전체를 하나의 portable research object로 내보낼 필요가 있는가?
- lightweight local artifact contract와 richer external metadata packaging 사이의 적절한 경계는 어디인가?

## Source trace
- `raw/web-snapshots/Research Object Crate (RO-Crate).md`
- `system/concept--artifact-contracts.md`
- `system/concept--trace-store-and-run-ledger.md`
