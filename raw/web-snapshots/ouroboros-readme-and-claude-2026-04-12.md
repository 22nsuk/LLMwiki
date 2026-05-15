---
title: "Snapshot: Q00/ouroboros README + CLAUDE.md"
source: "https://github.com/Q00/ouroboros"
published: "unknown"
created: "2026-04-12"
---

# Snapshot: Q00/ouroboros README + CLAUDE.md
- Capture date: 2026-04-12
- URL: https://github.com/Q00/ouroboros
- URL: https://github.com/Q00/ouroboros/blob/main/CLAUDE.md

## Key excerpts
- Ouroboros is described as a specification-first workflow engine for AI coding agents.
- It positions the main failure mode at the input stage: vague prompts, no spec, and manual QA.
- The loop is explicit: Interview -> Seed -> Execute -> Evaluate -> Evolve.
- It uses an ambiguity gate (`<= 0.2`) before code generation and an immutable seed spec.
- Evaluation is a 3-stage automated gate: mechanical, semantic, and multi-model consensus.
- The project exposes `ooo` commands that map to individual skills, and `ooo ralph` is the persistent loop that continues until convergence.
- The README describes event sourcing, drift measurement, stagnation detection, and runtime backends for Claude Code and Codex CLI.
- `CLAUDE.md` maps commands like `ooo interview`, `ooo seed`, `ooo run`, `ooo evaluate`, `ooo evolve`, and `ooo ralph` to skill files or MCP actions.

## Why this snapshot exists
The snapshot preserves the specification-first, gated-state-machine, and persistent-loop ideas used in the current review.
