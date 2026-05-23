# Documentation Map

This directory is the public documentation hub for the current code/ops runtime.
Root documents stay short; detailed procedures live here.

## First Reading Path

1. [../README.md](../README.md) - repository identity, quickstart, and common workflows.
2. [../ARCHITECTURE.md](../ARCHITECTURE.md) - current system model and public/private boundary.
3. [development.md](development.md) - setup, tests, CI tiers, and change-type gates.
4. [ops-runtime.md](ops-runtime.md) - Make, scripts, schemas, templates, and generated artifacts.
5. [self-improvement-runtime.md](self-improvement-runtime.md) - mechanism review, goal runtime, and promotion.

## Topic Index

- Public export and boundary rules: [public-mirror.md](public-mirror.md)
- Release evidence and package sealing: [release.md](release.md)
- Optional codebase-memory-mcp sidecar: [codebase-memory-mcp.md](codebase-memory-mcp.md)
- Ops subsystem index: [../ops/README.md](../ops/README.md)
- Agent role surface: [../.codex/agents/README.md](../.codex/agents/README.md)

## Source Of Truth Rules

- Public surface membership is defined in `ops/scripts/public/public_surface_policy.py`.
- Make target behavior is defined in `Makefile` and `mk/*.mk`.
- Test lane semantics are defined in `ops/test-lane-registry.json`.
- Schema-backed report shape is defined in `ops/schemas/*.json`.
- Agent operating rules are defined in `AGENTS.md`; full-vault local deltas are in `AGENTS.local.md`.
