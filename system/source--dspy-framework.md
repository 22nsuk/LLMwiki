---
title: "DSPy"
page_type: "source"
corpus: "system"
registry_id: "W-064"
raw_path: "raw/web-snapshots/DSPy.md"
source_type: "web-snapshot"
domain: "lm-programming-frameworks"
created: "2026-04-13"
aliases:
  - "source--dspy-framework"
tags:
  - "corpus/system"
  - "type/source"
---

# source--dspy-framework

## Title
DSPy

## Source
- `raw/web-snapshots/DSPy.md`

## Type
web-snapshot

## Summary
DSPy는 language model application을 brittle prompt string보다 structured code, signature, module, optimizer의 조합으로 다루게 하는 framework다. 핵심 메시지는 `prompt를 직접 만지기보다 프로그램을 설계하고, 그 프로그램을 compile/optimize한다`는 것이며, signatures, modules, adapters, optimizers를 통해 LM behavior를 더 portable하고 maintainable하게 만든다고 설명한다.

## Why it matters
현재 system corpus의 self-improvement discourse는 harness optimization을 강조하면서도, 실제로 `programming not prompting`을 체계적으로 설명하는 framework source는 없었다. DSPy는 mechanism change를 prompt wording보다 module/signature/eval loop의 구조 문제로 보게 만드는 reference surface다.

## Key points
- DSPy treats AI systems as structured programs rather than prompt blobs.
- signatures separate desired behavior from low-level prompt implementation.
- modules and optimizers make LM systems easier to compose, compare, and improve.
- the framework is explicitly oriented toward portability across models and strategies.
- optimization is described as compiling prompts or weights from code-level structure and metrics.

## Limitations / caveats
- framework homepage prose is persuasive and educational, but not an independent comparison study.
- DSPy’s abstractions are useful, but adopting them wholesale would be a major repo-level mechanism change.
- compile/optimizer language can encourage over-automation if eval and governance contracts are weak.

## Related pages
- [[concept--harness-optimization]]
- [[concept--binary-evals]]
- [[source--kevinrgu-autoagent-repo]]
- [[source--meta-harness]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- this repo should borrow DSPy’s modularity where, in signatures/templates, in eval wiring, or in orchestration boundaries?
- how much of `programming not prompting` can be adopted without importing a whole new framework surface?

## Source trace
- `raw/web-snapshots/DSPy.md`
- `system/concept--harness-optimization.md`
- `system/concept--binary-evals.md`
