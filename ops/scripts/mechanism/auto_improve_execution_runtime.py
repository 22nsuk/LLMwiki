from __future__ import annotations

import shlex
import sys
from pathlib import Path


def mutation_command(
    *,
    artifact_root: Path,
    run_id: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    roles: list[str],
    routing_report_rels: list[str],
    policy_path: str,
) -> str:
    parts = [
        shlex.quote(sys.executable),
        "-m",
        "ops.scripts.core.executor",
        "--vault",
        shlex.quote(str(artifact_root)),
        "--run-id",
        shlex.quote(run_id),
        "--policy-path",
        shlex.quote(policy_path),
        "--scope-freeze",
        shlex.quote(scope_freeze_rel),
        "--proposal-snapshot",
        shlex.quote(proposal_snapshot_rel),
    ]
    for role in roles:
        parts.extend(["--role", shlex.quote(role)])
    for rel_path in routing_report_rels:
        parts.extend(["--routing-report", shlex.quote(rel_path)])
    return " ".join(parts)
