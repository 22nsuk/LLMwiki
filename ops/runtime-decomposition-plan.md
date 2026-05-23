# Runtime Orientation

This file replaces the older decomposition note with a newcomer-friendly map of
the current maintainer runtime. It is not the full contract; it points to the
live owners and explains how the pieces fit together.

## Mental Model

The runtime has three cooperating layers:

1. Policy and schemas define allowed behavior and report shape.
2. Make targets orchestrate repeatable workflows.
3. Python packages implement bounded runtime steps and write schema-backed evidence.

Most work should start from a Make target, then follow the target to its script
package and schema.

## Main Runtime Areas

| Area | Package | Make file | What it owns |
| --- | --- | --- | --- |
| Shared runtime helpers | `ops/scripts/core/` | `mk/core.mk`, `mk/artifact.mk` | artifact IO, paths, policy, schemas, command execution, workflow planning |
| Eval and lint | `ops/scripts/eval/` | `mk/eval.mk`, `mk/test.mk` | wiki lint/eval, warning budget, complexity, doc audit |
| Registry | `ops/scripts/registry/` | `mk/registry.mk` | raw registry export, preflight, normalization, intake routing |
| Mechanism loop | `ops/scripts/mechanism/` | `mk/mechanism.mk` | mechanism review, mutation proposal, goal runtime, promotion experiments |
| Release | `ops/scripts/release/` | `mk/release.mk` | release evidence, external report lifecycle, sealing, closeout summaries |
| Learning | `ops/scripts/learning/` | `mk/release.mk` | learning claims, readiness signoff, remediation backlog, negative lessons |
| Public export | `ops/scripts/public/` | `mk/public.mk` | public mirror, public check, CBM public export |
| Supply chain | `ops/scripts/supply_chain/` | `mk/supply_chain.mk` | provenance, SBOM, advisory, OpenVEX, in-toto, Sigstore |

## How To Trace A Change

1. Identify the Make target that a user would run.
2. Read the recipe in `mk/*.mk`.
3. Follow the `python -m ops.scripts...` entrypoint to the canonical package.
4. Read the schema for any report the script writes.
5. Add or update tests near the runtime owner.
6. Close with the narrow Make/Pytest gate for that surface.

## Current Design Direction

- Keep orchestrators thin and move reusable state transitions into helper modules.
- Prefer schema-backed reports over prose-only evidence.
- Keep public export reproducible without private corpus state.
- Keep generated artifact promotion explicit: candidate under `tmp/`, validated durable report under policy-approved output.
- Keep compatibility aliases only as migration surfaces; new docs should teach current package paths.

## Entry Documents

- Repository overview: [../README.md](../README.md)
- Architecture: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Ops runtime map: [../docs/ops-runtime.md](../docs/ops-runtime.md)
- Self-improvement loop: [../docs/self-improvement-runtime.md](../docs/self-improvement-runtime.md)
- Development checks: [../docs/development.md](../docs/development.md)
