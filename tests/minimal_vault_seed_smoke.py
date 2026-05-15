from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.minimal_vault_seed_core import seed_minimal_vault


def _shared() -> Any:
    from tests import minimal_vault_runtime as shared

    return shared


def _remove_open_question_extra_pages(root: Path) -> None:
    for relative_path in (
        "wiki/concept--fake.md",
        "wiki/query--fake.md",
        "wiki/synthesis--fake.md",
        "system/system-raw-registry/wiki/ai-capability.md",
        "system/system-raw-registry/wiki/ai-compute-control.md",
        "system/system-raw-registry/wiki/ai-execution.md",
        "system/system-raw-registry/wiki/coffee.md",
        "system/system-raw-registry/wiki/europe-tech-sovereignty.md",
        "system/system-raw-registry/wiki/global-policy-and-market-seeds.md",
        "system/system-raw-registry/wiki/korea-fx.md",
        "system/system-raw-registry/wiki/middle-east.md",
        "system/system-raw-registry/wiki/middle-east-followups.md",
    ):
        path = root / relative_path
        if path.exists():
            path.unlink()


def _configure_open_question_registry_policy(root: Path, shared: Any) -> None:
    shared.set_policy_value(
        root,
        ("registry_contract", "raw_registry_shard_pages"),
        [
            "system/system-raw-registry/wiki.md",
            "system/system-raw-registry/system.md",
        ],
    )
    shared.set_policy_value(
        root,
        ("registry_contract", "raw_registry_entry_page_corpus"),
        {
            "system/system-raw-registry/wiki.md": "wiki",
            "system/system-raw-registry/system.md": "system",
        },
    )


def _open_question_system_index_page(source_trace_ref: str) -> str:
    return f"""---
title: "System Index"
page_type: "system-index"
corpus: "system"
special_role: "router"
aliases:
  - "system-index"
tags:
  - "corpus/system"
  - "type/system-index"
---

# system-index

## Summary
- system corpus pages: `5`
- system raw entries: `0`
- wiki raw entries: `1`
## How to use this system corpus
- x
## System pages
- [[system-log]]
- [[system-raw-registry]]
## System knowledge pages
- [[system-log]]
- [[system-raw-registry]]
## Content corpus handoff
- [[index]]
## Ops surface
- [[system-log]]
- [[system-raw-registry]]
## Related pages
- [[system-log]]
- [[system-raw-registry]]
## Source trace
- `{source_trace_ref}`
"""


def _open_question_raw_registry_page(source_trace_ref: str) -> str:
    return f"""---
title: "System Raw Registry"
page_type: "registry"
corpus: "system"
special_role: "raw-registry"
aliases:
  - "system-raw-registry"
tags:
  - "corpus/system"
  - "type/registry"
---

# System Raw Registry

## Summary
- total registered paths: `1`
- system corpus entries: `0`
- wiki corpus entries: `1`
- ingested: `1`
- registered-not-ingested: `0`

## Registry rules
- x

## Registry shards
- [[system-raw-registry/wiki]]
- [[system-raw-registry/system]]

## Pending ingest
- none

## Related pages
- [[system-index]]
- [[index]]
- [[system-raw-registry/wiki]]
- [[system-raw-registry/system]]
## Source trace
- `{source_trace_ref}`
"""


def _open_question_wiki_registry_shard_page(source_trace_ref: str) -> str:
    return f"""---
title: "Wiki Raw Registry Shard"
page_type: "registry-shard"
corpus: "system"
special_role: "raw-registry-shard"
aliases:
  - "wiki"
  - "system-raw-registry/wiki"
tags:
  - "corpus/system"
  - "type/registry-shard"
---

# system-raw-registry/wiki

## Summary
- corpus shard router: `wiki`
- total registered entries across wiki shard tree: `1`
- directly listed entries on this page: `1`
- family shard entries managed below: `0`

## Family shards
- none currently

## Directly listed raw sources
#### R-100
- storage_path: `raw/fake.pdf`
- display_path: `raw/fake.pdf`
- title: *Fake*
- type: news-snapshot
- corpus: wiki
- target_page: `source--fake`
- status: ingested
- domain: fake

## Related pages
- [[system-raw-registry]]
- [[system-raw-registry/system]]
- [[index]]
## Source trace
- `{source_trace_ref}`
"""


def _open_question_system_registry_shard_page(source_trace_ref: str) -> str:
    return f"""---
title: "System Raw Registry Shard"
page_type: "registry-shard"
corpus: "system"
special_role: "raw-registry-shard"
aliases:
  - "system"
  - "system-raw-registry/system"
tags:
  - "corpus/system"
  - "type/registry-shard"
---

# system-raw-registry/system

## Summary
- system corpus registry shard
- registered entries: `0`

## Registered raw sources
- none currently

## Related pages
- [[system-raw-registry]]
- [[system-index]]
## Source trace
- `{source_trace_ref}`
"""


def _open_question_index_page(source_trace_ref: str) -> str:
    return f"""---
title: "Index"
page_type: "index"
corpus: "wiki"
special_role: "router"
aliases:
  - "index"
tags:
  - "corpus/wiki"
  - "type/index"
---

# index

## Summary
- news / market / geopolitics sources: `1`
- coffee science sources: `0`
- query artifacts: `0`
- canonical concepts: `0`
- domain syntheses: `0`
## How to use this wiki
- x
## Sources
### News / market / geopolitics
- [[source--fake]]
### Coffee science / sensory / brewing
- none
## Queries
- none
## Concepts
- none
## Syntheses
- none
## Pending ingest
- none
## Related pages
- [[system-index]]
- [[system-raw-registry]]
## Source trace
- `{source_trace_ref}`
"""


def _open_question_source_page(source_trace_ref: str) -> str:
    return f"""---
title: "Fake Source"
page_type: "source"
corpus: "wiki"
registry_id: "R-100"
raw_path: "raw/fake.pdf"
source_type: "news-snapshot"
domain: "fake"
aliases:
  - "source--fake"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--fake

## Title
Fake Source
## Source
- `raw/fake.pdf`
## Type
news-snapshot
## Summary
- x
## Why it matters
- x
## Key points
- a
- b
- c
- d
## Limitations / caveats
- x
## Related pages
- [[index]]
- [[system-index]]
## Open questions
- x
## Source trace
- `{source_trace_ref}`
"""


def _open_question_pages(source_trace_ref: str) -> dict[str, str]:
    return {
        "system/system-index.md": _open_question_system_index_page(source_trace_ref),
        "system/system-raw-registry.md": _open_question_raw_registry_page(
            source_trace_ref
        ),
        "system/system-raw-registry/wiki.md": _open_question_wiki_registry_shard_page(
            source_trace_ref
        ),
        "system/system-raw-registry/system.md": _open_question_system_registry_shard_page(
            source_trace_ref
        ),
        "wiki/index.md": _open_question_index_page(source_trace_ref),
        "wiki/source--fake.md": _open_question_source_page(source_trace_ref),
    }


def _eval_coverage_index_page(source_trace_ref: str) -> str:
    return f"""---
title: "Index"
page_type: "index"
corpus: "wiki"
special_role: "router"
aliases:
  - "index"
tags:
  - "corpus/wiki"
  - "type/index"
---

# index

## Summary
- news / market / geopolitics sources: `1`
- coffee science sources: `0`
- query artifacts: `0`
- canonical concepts: `0`
- domain syntheses: `1`
## How to use this wiki
- x
## Sources
### News / market / geopolitics
- [[source--fake]]
### Coffee science / sensory / brewing
- none
## Queries
- none
## Concepts
- none
## Syntheses
- [[synthesis--fake]]
## Pending ingest
- none
## Related pages
- [[system-index]]
- [[system-raw-registry]]
## Source trace
- `{source_trace_ref}`
"""


def _eval_coverage_synthesis_page(source_trace_ref: str) -> str:
    return f"""---
title: "Fake Synthesis"
page_type: "synthesis"
corpus: "wiki"
source_count: 1
aliases:
  - "synthesis--fake"
tags:
  - "corpus/wiki"
  - "type/synthesis"
---

# synthesis--fake

## Question
q
## Short answer
a
## Evidence considered
- [[source--fake]]
## Analysis
- x
## What this synthesis excludes
- x
## Tensions / contradictions
- x
## Implications for future ingest
- x
## Decision / takeaway
- x
## Follow-up questions
- x
## Related pages
- [[index]]
- [[source--fake]]
## Source trace
- `{source_trace_ref}`
"""


def _write_pages(root: Path, pages: dict[str, str]) -> None:
    for relative_path, content in pages.items():
        (root / relative_path).write_text(content, encoding="utf-8")


def seed_open_question_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    shared = _shared()
    seed_minimal_vault(root, source_trace_ref)
    _remove_open_question_extra_pages(root)
    _configure_open_question_registry_policy(root, shared)
    _write_pages(root, _open_question_pages(source_trace_ref))
    shared._ensure_created_frontmatter(root)


def seed_doc_audit_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    seed_open_question_smoke_vault(root, source_trace_ref)


def seed_registry_review_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    seed_open_question_smoke_vault(root, source_trace_ref)


def seed_eval_coverage_smoke_vault(root: Path, source_trace_ref: str = "raw/fake.pdf") -> None:
    shared = _shared()
    seed_open_question_smoke_vault(root, source_trace_ref)
    _write_pages(
        root,
        {
            "wiki/index.md": _eval_coverage_index_page(source_trace_ref),
            "wiki/synthesis--fake.md": _eval_coverage_synthesis_page(source_trace_ref),
        },
    )
    shared._ensure_created_frontmatter(root)
