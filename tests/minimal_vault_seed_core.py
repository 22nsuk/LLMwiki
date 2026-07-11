from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _shared() -> Any:
    from tests import minimal_vault_runtime as shared

    return shared


@dataclass(frozen=True)
class _RegistryLinks:
    shard_pages: list[str]
    wiki_family_shard_pages: list[str]
    system_family_shard_pages: list[str]
    generated_shard_pages: list[str]
    shard_links: str
    wiki_family_links: str
    system_family_links: str
    registry_related_links: str
    wiki_shard_related_links: str
    system_shard_related_links: str


def _schema_copy_names(shared: Any, schema_names: Collection[str] | None) -> tuple[str, ...]:
    if schema_names is None:
        return tuple(shared.SCHEMA_PATHS)
    return tuple(sorted({Path(name).name for name in schema_names}))


def _prepare_minimal_vault_surface(
    root: Path,
    shared: Any,
    *,
    schema_names: Collection[str] | None = None,
) -> None:
    (root / "wiki").mkdir()
    (root / "system").mkdir()
    (root / "raw").mkdir()
    (root / "ops" / "policies").mkdir(parents=True)
    (root / "ops" / "schemas").mkdir(parents=True)
    (root / "raw" / "fake.pdf").write_text("", encoding="utf-8")
    (root / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        shared.POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for policy_name in (
        "release-risk-taxonomy.json",
        "learning-claim-auto-unlock.json",
        "learning-claim-confirmed-improvement.json",
        "release-closeout-fixed-point.json",
    ):
        policy_source = shared.REPO_ROOT / "ops" / "policies" / policy_name
        if policy_source.exists():
            (root / "ops" / "policies" / policy_name).write_text(
                policy_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
    for name in _schema_copy_names(shared, schema_names):
        source = shared.SCHEMA_PATHS.get(name)
        if source and source.exists():
            (root / "ops" / "schemas" / name).write_text(
                source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )


def _registry_links(shared: Any) -> _RegistryLinks:
    shard_pages = shared.live_registry_shard_pages()
    wiki_family_shard_pages = shared.live_registry_wiki_family_shard_pages()
    system_family_shard_pages = shared.live_registry_child_shard_pages(
        "system/system-raw-registry/system.md"
    )
    generated_shard_pages = [
        path
        for path in shard_pages
        if path
        not in {
            "system/system-raw-registry/wiki.md",
            "system/system-raw-registry/system.md",
        }
    ]
    return _RegistryLinks(
        shard_pages=shard_pages,
        wiki_family_shard_pages=wiki_family_shard_pages,
        system_family_shard_pages=system_family_shard_pages,
        generated_shard_pages=generated_shard_pages,
        shard_links=shared.bullet_wikilinks(shard_pages),
        wiki_family_links=shared.bullet_wikilinks(wiki_family_shard_pages),
        system_family_links=shared.bullet_wikilinks(system_family_shard_pages),
        registry_related_links=shared.bullet_wikilinks(
            [path for path in shard_pages if path != "system/system-raw-registry.md"]
        ),
        wiki_shard_related_links=shared.bullet_wikilinks(
            [path for path in shard_pages if path != "system/system-raw-registry/wiki.md"]
        ),
        system_shard_related_links=shared.bullet_wikilinks(
            [path for path in shard_pages if path != "system/system-raw-registry/system.md"]
        ),
    )


def _system_index_page(source_trace_ref: str) -> str:
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
- x
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


def _system_log_page(source_trace_ref: str) -> str:
    return f"""---
title: "System Log"
page_type: "system-log"
corpus: "system"
special_role: "chronology"
aliases:
  - "system-log"
tags:
  - "corpus/system"
  - "type/system-log"
---

# system-log

## Related pages
- [[system-index]]
- [[system-raw-registry]]
## Source trace
- `{source_trace_ref}`
"""


def _system_raw_registry_page(source_trace_ref: str, links: _RegistryLinks) -> str:
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
{links.shard_links}

## Pending ingest
- none

## Related pages
- [[system-index]]
- [[index]]
{links.registry_related_links}
## Source trace
- `{source_trace_ref}`
"""


def _wiki_raw_registry_shard_page(source_trace_ref: str, links: _RegistryLinks) -> str:
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
{links.wiki_family_links}

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
{links.wiki_shard_related_links}
- [[index]]
## Source trace
- `{source_trace_ref}`
"""


def _system_raw_registry_shard_page(source_trace_ref: str, links: _RegistryLinks) -> str:
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

## Second-order shards
{links.system_family_links or "- none currently"}

## Directly listed raw sources
- none currently

## Related pages
- [[system-raw-registry]]
{links.system_shard_related_links}
- [[system-index]]
## Source trace
- `{source_trace_ref}`
"""


def _wiki_index_page(source_trace_ref: str) -> str:
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
- x
## How to use this wiki
- x
## Sources
- [[source--fake]]
## Queries
- [[query--fake]]
## Concepts
- [[concept--fake]]
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


def _fake_source_page(source_trace_ref: str) -> str:
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
Fake Source documents a synthetic fixture used across lint and eval tests. It records a placeholder news snapshot with explicit trace back to raw/fake.pdf for deterministic registry checks.
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
- [[concept--fake]]
## Open questions
- x
## Source trace
- `{source_trace_ref}`
"""


def _fake_concept_page(source_trace_ref: str) -> str:
    return f"""---
title: "Fake Concept"
page_type: "concept"
corpus: "wiki"
canonical: true
aliases:
  - "concept--fake"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--fake

## Summary
- x
## Why it matters here
- x
## Main body
- x
### Core model
- x
### Common misread
- x
### Key variables
- x
### Mechanism
- x
### Evidence ladder
- x
### Concrete examples
- [[source--fake]]
### Boundary
- x
## Scope boundaries
- x
## Examples and non-examples
- example: [[source--fake]]
- non-example: unrelated scratch note
## How to reuse this concept
- use when a synthesis needs a canonical interpretation anchor
## Related pages
- [[index]]
- [[source--fake]]
## Open questions
- x
## Source trace
- `{source_trace_ref}`
"""


def _fake_synthesis_page(source_trace_ref: str) -> str:
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
### Core model
- x
### Common misread
- x
### Key variables
- x
### Mechanism
- x
### Evidence ladder
- x
### Concrete examples
- [[source--fake]]
### Boundary
- x
## What this synthesis excludes
- exclude unrelated adjacent question
## Tensions / contradictions
- tension: source breadth may exceed current answer scope
## Implications for future ingest
- route future source to this synthesis only if it reinforces the same question
## Decision / takeaway
- x
## Follow-up questions
- x
## Related pages
- [[index]]
- [[concept--fake]]
## Source trace
- `{source_trace_ref}`
"""


def _fake_query_page(source_trace_ref: str) -> str:
    return f"""---
title: "Fake Query"
page_type: "query"
corpus: "wiki"
aliases:
  - "query--fake"
tags:
  - "corpus/wiki"
  - "type/query"
---

# query--fake

## Question
q
## Short answer
a
## Evidence considered
- [[source--fake]]
## Analysis
- x
## Decision / takeaway
- x
## Follow-up questions
- x
## Related pages
- [[index]]
- [[concept--fake]]
## Source trace
- `{source_trace_ref}`
"""


def _core_pages(source_trace_ref: str, links: _RegistryLinks) -> dict[str, str]:
    return {
        "system/system-index.md": _system_index_page(source_trace_ref),
        "system/system-log.md": _system_log_page(source_trace_ref),
        "system/system-raw-registry.md": _system_raw_registry_page(source_trace_ref, links),
        "system/system-raw-registry/wiki.md": _wiki_raw_registry_shard_page(
            source_trace_ref, links
        ),
        "system/system-raw-registry/system.md": _system_raw_registry_shard_page(
            source_trace_ref, links
        ),
        "wiki/index.md": _wiki_index_page(source_trace_ref),
        "wiki/source--fake.md": _fake_source_page(source_trace_ref),
        "wiki/concept--fake.md": _fake_concept_page(source_trace_ref),
        "wiki/synthesis--fake.md": _fake_synthesis_page(source_trace_ref),
        "wiki/query--fake.md": _fake_query_page(source_trace_ref),
    }


def _add_registry_family_shards(
    files: dict[str, str],
    shared: Any,
    links: _RegistryLinks,
    source_trace_ref: str,
) -> None:
    for relative_path in links.generated_shard_pages:
        files[relative_path] = shared.build_registry_family_shard_page(relative_path, source_trace_ref)


def _write_seed_files(root: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def seed_minimal_vault(
    root: Path,
    source_trace_ref: str = "raw/fake.pdf",
    *,
    schema_names: Collection[str] | None = None,
) -> None:
    shared = _shared()
    _prepare_minimal_vault_surface(root, shared, schema_names=schema_names)
    links = _registry_links(shared)
    files = _core_pages(source_trace_ref, links)
    _add_registry_family_shards(files, shared, links, source_trace_ref)
    _write_seed_files(root, files)
    shared._ensure_created_frontmatter(root)
