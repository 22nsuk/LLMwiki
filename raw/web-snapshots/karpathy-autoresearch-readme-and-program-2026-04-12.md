---
title: "Snapshot: karpathy/autoresearch README + program.md"
source: "https://github.com/karpathy/autoresearch"
published: "unknown"
created: "2026-04-12"
---

# Snapshot: karpathy/autoresearch README + program.md
- Capture date: 2026-04-12
- URL: https://github.com/karpathy/autoresearch
- URL: https://github.com/karpathy/autoresearch/blob/master/program.md

## Key excerpts
- The repo idea is to give an AI agent a small but real LLM training setup, let it modify the code, train for 5 minutes, check if the result improved, keep or discard, and repeat.
- The repository is intentionally small: `prepare.py` is fixed, `train.py` is the only edited file, and `program.md` provides the agent instructions.
- The design emphasizes a fixed 5-minute time budget, single-file modification, and a simple keep/discard loop.
- `program.md` requires a fresh run tag, a dedicated branch, baseline measurement first, and TSV logging of every experiment.
- The loop rule is explicit: modify one file, commit, run, read metric, keep if improved, otherwise reset.
- Simplicity is a criterion: small improvements that add ugly complexity may not be worth keeping.

## Why this snapshot exists
This repository can change quickly. The snapshot preserves the minimal-autoresearch pattern used in the current review.
