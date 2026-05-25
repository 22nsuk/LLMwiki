from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import read_json_object
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH

from .mechanism_run_common_runtime import timestamp, write_json

IMPROVEMENT_OBSERVATIONS_SCHEMA = IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH
IMPROVEMENT_OBSERVATIONS_FILENAME = "improvement-observations.json"
IMPROVEMENT_OBSERVATIONS_TASK_DIR = "ops/reports/task-improvement-observations"
PRODUCER = "ops.scripts.improvement_observations_runtime"
SOURCE_COMMAND = "python -m ops.scripts.improvement_observations"
SOURCE_PATHS = [
    "ops/scripts/mechanism/improvement_observations_runtime.py",
    "ops/scripts/mechanism/improvement_observations.py",
]
RUN_SCOPE = "system_mechanism_run"
TASK_SCOPE = "repo_maintenance_task"


@dataclass(frozen=True)
class ImprovementObservationsBuildRequest:
    record_id: str
    scope: str
    summary: str
    vault: Path | None = None
    context: RuntimeContext | None = None
    run_id: str | None = None
    task_id: str | None = None
    observations: list[dict] | None = None
    captured_at: str | None = None
    policy_path: str | None = None
    source_command: str = SOURCE_COMMAND


def run_improvement_observations_rel(run_id: str) -> str:
    return f"runs/{run_id}/{IMPROVEMENT_OBSERVATIONS_FILENAME}"


def task_improvement_observations_rel(task_id: str) -> str:
    return (
        Path(IMPROVEMENT_OBSERVATIONS_TASK_DIR)
        / task_id
        / IMPROVEMENT_OBSERVATIONS_FILENAME
    ).as_posix()


def default_summary_for_scope(scope: str, record_id: str) -> str:
    if scope == RUN_SCOPE:
        return (
            "Record reusable automation or repo hygiene follow-ups discovered "
            f"while executing mechanism run {record_id}."
        )
    return (
        "Record reusable automation or repo hygiene follow-ups discovered "
        f"while completing standalone task {record_id}."
    )


def _artifact_kind(scope: str) -> str:
    if scope == RUN_SCOPE:
        return "run_improvement_observations"
    return "task_improvement_observations"


def _envelope_text_inputs(
    *,
    record_id: str,
    scope: str,
    summary: str,
    observations: list[dict],
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "scope": scope,
        "summary": summary,
        "observations": json.dumps(observations, ensure_ascii=False, sort_keys=True),
    }


def _build_envelope(
    vault: Path,
    *,
    generated_at: str,
    record_id: str,
    scope: str,
    summary: str,
    observations: list[dict],
    policy_path: str | None,
    source_command: str,
) -> dict[str, Any]:
    _policy, resolved_policy_path = load_policy(vault, policy_path)
    return build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind=_artifact_kind(scope),
        producer=PRODUCER,
        source_command=source_command,
        resolved_policy_path=resolved_policy_path,
        schema_path=IMPROVEMENT_OBSERVATIONS_SCHEMA,
        source_paths=SOURCE_PATHS,
        text_inputs=_envelope_text_inputs(
            record_id=record_id,
            scope=scope,
            summary=summary,
            observations=observations,
        ),
    )


def build_improvement_observations(request: ImprovementObservationsBuildRequest) -> dict:
    generated_at = timestamp(request.context)
    captured = request.captured_at or generated_at
    observation_items = list(request.observations or [])
    resolved_vault = (request.vault or Path(".")).resolve()
    payload = {
        **_build_envelope(
            resolved_vault,
            generated_at=generated_at,
            record_id=request.record_id,
            scope=request.scope,
            summary=request.summary,
            observations=observation_items,
            policy_path=request.policy_path,
            source_command=request.source_command,
        ),
        "record_id": request.record_id,
        "captured_at": captured,
        "scope": request.scope,
        "summary": request.summary,
        "observations": observation_items,
    }
    if request.run_id:
        payload["run_id"] = request.run_id
    if request.task_id:
        payload["task_id"] = request.task_id
    return payload


def build_run_improvement_observations(
    run_id: str,
    *,
    vault: Path | None = None,
    context: RuntimeContext | None = None,
    observations: list[dict] | None = None,
    summary: str | None = None,
    captured_at: str | None = None,
    policy_path: str | None = None,
) -> dict:
    return build_improvement_observations(
        ImprovementObservationsBuildRequest(
            record_id=run_id,
            run_id=run_id,
            scope=RUN_SCOPE,
            summary=summary or default_summary_for_scope(RUN_SCOPE, run_id),
            vault=vault,
            context=context,
            observations=observations,
            captured_at=captured_at,
            policy_path=policy_path,
        )
    )


def build_task_improvement_observations(
    task_id: str,
    *,
    vault: Path | None = None,
    context: RuntimeContext | None = None,
    observations: list[dict] | None = None,
    summary: str | None = None,
    captured_at: str | None = None,
    policy_path: str | None = None,
) -> dict:
    return build_improvement_observations(
        ImprovementObservationsBuildRequest(
            record_id=task_id,
            task_id=task_id,
            scope=TASK_SCOPE,
            summary=summary or default_summary_for_scope(TASK_SCOPE, task_id),
            vault=vault,
            context=context,
            observations=observations,
            captured_at=captured_at,
            policy_path=policy_path,
        )
    )


def write_run_improvement_observations(
    vault: Path,
    *,
    run_id: str,
    context: RuntimeContext | None = None,
    observations: list[dict] | None = None,
    summary: str | None = None,
    policy_path: str | None = None,
) -> str:
    rel_path = run_improvement_observations_rel(run_id)
    payload = build_run_improvement_observations(
        run_id,
        vault=vault,
        context=context,
        observations=observations,
        summary=summary,
        policy_path=policy_path,
    )
    write_json(vault, rel_path, payload, IMPROVEMENT_OBSERVATIONS_SCHEMA)
    return rel_path


def write_task_improvement_observations(
    vault: Path,
    *,
    task_id: str,
    context: RuntimeContext | None = None,
    observations: list[dict] | None = None,
    summary: str | None = None,
    rel_path: str | None = None,
    policy_path: str | None = None,
) -> str:
    target_rel_path = rel_path or task_improvement_observations_rel(task_id)
    payload = build_task_improvement_observations(
        task_id,
        vault=vault,
        context=context,
        observations=observations,
        summary=summary,
        policy_path=policy_path,
    )
    write_json(vault, target_rel_path, payload, IMPROVEMENT_OBSERVATIONS_SCHEMA)
    return target_rel_path


def improvement_observation_paths(vault: Path) -> list[str]:
    paths: list[Path] = []
    task_root = vault / IMPROVEMENT_OBSERVATIONS_TASK_DIR
    if task_root.exists():
        paths.extend(task_root.glob(f"*/{IMPROVEMENT_OBSERVATIONS_FILENAME}"))
    runs_root = vault / "runs"
    if runs_root.exists():
        paths.extend(runs_root.glob(f"*/{IMPROVEMENT_OBSERVATIONS_FILENAME}"))
    return [report_path(vault, path) for path in sorted(path for path in paths if path.is_file())]


def _dict_observations(items: object) -> list[dict]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _backfilled_payload(
    vault: Path,
    rel_path: str,
    payload: dict[str, Any],
    *,
    context: RuntimeContext | None,
    policy_path: str | None,
) -> dict:
    scope = str(payload.get("scope", "")).strip()
    record_id = str(payload.get("record_id", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    if not record_id:
        if scope == RUN_SCOPE:
            record_id = str(payload.get("run_id", "")).strip()
        elif scope == TASK_SCOPE:
            record_id = str(payload.get("task_id", "")).strip()
    if not scope:
        scope = RUN_SCOPE if rel_path.startswith("runs/") else TASK_SCOPE
    if not record_id:
        record_id = Path(rel_path).parent.name
    if not summary:
        summary = default_summary_for_scope(scope, record_id)
    kwargs: dict[str, Any] = {
        "vault": vault,
        "context": context,
        "observations": _dict_observations(payload.get("observations")),
        "summary": summary,
        "captured_at": str(payload.get("captured_at", "")).strip() or None,
        "policy_path": policy_path,
    }
    if scope == RUN_SCOPE:
        return build_run_improvement_observations(
            str(payload.get("run_id", "")).strip() or record_id,
            **kwargs,
        )
    return build_task_improvement_observations(
        str(payload.get("task_id", "")).strip() or record_id,
        **kwargs,
    )


def backfill_improvement_observations(
    vault: Path,
    rel_paths: Iterable[str] | None = None,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> list[str]:
    written: list[str] = []
    for rel_path in rel_paths or improvement_observation_paths(vault):
        payload = read_json_object(vault / rel_path, context=rel_path)
        backfilled = _backfilled_payload(
            vault,
            rel_path,
            payload,
            context=context,
            policy_path=policy_path,
        )
        write_json(vault, rel_path, backfilled, IMPROVEMENT_OBSERVATIONS_SCHEMA)
        written.append(rel_path)
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "Scaffold an improvement-observations artifact for either a mechanism run "
            "or a standalone repo maintenance task."
        )
    )
    ap.add_argument("--vault", type=Path, default=Path("."))
    ap.add_argument("--run-id")
    ap.add_argument("--task-id")
    ap.add_argument("--summary")
    ap.add_argument("--out")
    ap.add_argument("--policy-path")
    ap.add_argument(
        "--backfill-existing",
        action="store_true",
        help="Backfill all existing improvement-observations artifacts with the current envelope contract.",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.backfill_existing:
        if args.run_id or args.task_id or args.out:
            raise SystemExit("--backfill-existing cannot be combined with --run-id, --task-id, or --out")
        vault = args.vault.resolve()
        written = backfill_improvement_observations(vault, policy_path=args.policy_path)
        print(
            json.dumps(
                {
                    "scope": "all",
                    "backfilled_count": len(written),
                    "paths": written,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if bool(args.run_id) == bool(args.task_id):
        raise SystemExit("exactly one of --run-id or --task-id is required")

    vault = args.vault.resolve()
    if args.run_id:
        rel_path = args.out or run_improvement_observations_rel(args.run_id)
        if rel_path != run_improvement_observations_rel(args.run_id):
            payload = build_run_improvement_observations(
                args.run_id,
                vault=vault,
                summary=args.summary,
                policy_path=args.policy_path,
            )
            write_json(vault, rel_path, payload, IMPROVEMENT_OBSERVATIONS_SCHEMA)
        else:
            rel_path = write_run_improvement_observations(
                vault,
                run_id=args.run_id,
                summary=args.summary,
                policy_path=args.policy_path,
            )
        print(
            json.dumps(
                {
                    "scope": RUN_SCOPE,
                    "record_id": args.run_id,
                    "path": rel_path,
                },
                ensure_ascii=False,
            )
        )
        return 0

    rel_path = write_task_improvement_observations(
        vault,
        task_id=args.task_id,
        summary=args.summary,
        rel_path=args.out,
        policy_path=args.policy_path,
    )
    print(
        json.dumps(
            {
                "scope": TASK_SCOPE,
                "record_id": args.task_id,
                "path": rel_path,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
