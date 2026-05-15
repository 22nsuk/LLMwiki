---
title: "Snapshot: olelehmann100kMRR/autoresearch-skill"
source: "https://github.com/olelehmann100kMRR/autoresearch-skill/blob/main/SKILL.md"
published: "unknown"
created: "2026-04-12"
---

# Snapshot: olelehmann100kMRR/autoresearch-skill
- Capture date: 2026-04-12
- URL: https://github.com/olelehmann100kMRR/autoresearch-skill/blob/main/SKILL.md
- URL: https://github.com/olelehmann100kMRR/autoresearch-skill/blob/main/eval-guide.md

## Key excerpts
- The skill adapts Karpathy-style autoresearch to skill prompts rather than ML code.
- Core loop: generate outputs, score outputs against binary eval criteria, mutate the skill prompt, keep improvements, discard regressions, repeat.
- It requires context gathering before experiments: target skill, test inputs, binary eval criteria, run count, run interval, and budget cap.
- It recommends a live HTML dashboard, results.tsv, results.json, changelog.md, and an unmodified baseline snapshot.
- The evaluation guide's golden rule is binary evals: every eval must be yes/no, not a scale and not a vibe check.
- The guide warns against too many evals, overlapping evals, narrow evals, and subjective evals that an agent cannot score consistently.

## Why this snapshot exists
This snapshot preserves the binary-eval and experiment-logging pattern used in the current review.
