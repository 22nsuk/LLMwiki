from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_io_runtime import load_optional_json_object

DEFAULT_SESSION_REPORTS_DIR = "ops/reports/auto-improve-sessions"


@dataclass(frozen=True)
class LatestSuccessfulGoalRun:
    goal_run_id: str
    session_report_path: str
    session_generated_at: str
    iteration_index: int
    iteration_run_id: str
    promotion_report_path: str
    run_telemetry_path: str


def _parse_iso_z(value: object) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        return dt.datetime.min.replace(tzinfo=dt.UTC)
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return dt.datetime.min.replace(tzinfo=dt.UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _repo_rel_path(vault: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(vault.resolve()).as_posix()
    except ValueError:
        return ""


def _candidate_session_reports(vault: Path, session_reports_dir: str) -> Iterable[Path]:
    root = vault / session_reports_dir
    if not root.is_dir():
        return ()
    return sorted(path for path in root.glob("*.json") if path.is_file())


def _payload(vault: Path, rel_path: str) -> Mapping[str, Any]:
    loaded = load_optional_json_object(vault / rel_path)
    return loaded if isinstance(loaded, Mapping) else {}


def _promoted_iteration(iteration: Mapping[str, Any]) -> bool:
    return (
        str(iteration.get("decision", "")).strip() == "PROMOTE"
        or str(iteration.get("outcome", "")).strip() == "promoted"
        or str(iteration.get("status", "")).strip() == "promoted"
    )


def _promotion_report_matches(vault: Path, rel_path: str, iteration_run_id: str) -> bool:
    report = _payload(vault, rel_path)
    if not report:
        return False
    report_run_id = str(report.get("run_id", "")).strip()
    return (
        str(report.get("decision", "")).strip() == "PROMOTE"
        and (not report_run_id or report_run_id == iteration_run_id)
    )


def _run_telemetry_matches(vault: Path, rel_path: str, iteration_run_id: str) -> bool:
    telemetry = _payload(vault, rel_path)
    if not telemetry:
        return False
    return (
        str(telemetry.get("run_id", "")).strip() == iteration_run_id
        and str(telemetry.get("decision", "")).strip() == "PROMOTE"
        and bool(telemetry.get("finalized", False))
    )


def _successful_iterations(
    vault: Path,
    *,
    session_report_path: Path,
    session: Mapping[str, Any],
) -> Iterable[LatestSuccessfulGoalRun]:
    if str(session.get("status", "")).strip() != "complete":
        return ()
    session_id = str(session.get("session_id", "")).strip() or session_report_path.stem
    generated_at = str(session.get("generated_at", "")).strip()
    iterations = session.get("iterations")
    if not isinstance(iterations, list):
        return ()

    candidates: list[LatestSuccessfulGoalRun] = []
    for iteration in iterations:
        if not isinstance(iteration, Mapping):
            continue
        if bool(iteration.get("quarantined", False)) or not _promoted_iteration(iteration):
            continue
        iteration_run_id = str(iteration.get("run_id", "")).strip()
        promotion_report_path = str(iteration.get("promotion_report", "")).strip()
        run_telemetry_path = str(iteration.get("run_telemetry", "")).strip()
        if not iteration_run_id or not promotion_report_path or not run_telemetry_path:
            continue
        if not _promotion_report_matches(vault, promotion_report_path, iteration_run_id):
            continue
        if not _run_telemetry_matches(vault, run_telemetry_path, iteration_run_id):
            continue
        candidates.append(
            LatestSuccessfulGoalRun(
                goal_run_id=session_id,
                session_report_path=_repo_rel_path(vault, session_report_path),
                session_generated_at=generated_at,
                iteration_index=int(iteration.get("index", 0) or 0),
                iteration_run_id=iteration_run_id,
                promotion_report_path=promotion_report_path,
                run_telemetry_path=run_telemetry_path,
            )
        )
    return candidates


def latest_successful_goal_run(
    vault: Path,
    *,
    session_reports_dir: str = DEFAULT_SESSION_REPORTS_DIR,
) -> LatestSuccessfulGoalRun | None:
    candidates: list[LatestSuccessfulGoalRun] = []
    for session_report_path in _candidate_session_reports(vault, session_reports_dir):
        session = load_optional_json_object(session_report_path)
        if isinstance(session, Mapping):
            candidates.extend(
                _successful_iterations(
                    vault,
                    session_report_path=session_report_path,
                    session=session,
                )
            )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            _parse_iso_z(item.session_generated_at),
            item.iteration_index,
            item.goal_run_id,
            item.iteration_run_id,
        ),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--session-reports-dir", default=DEFAULT_SESSION_REPORTS_DIR)
    parser.add_argument("--format", choices=("goal-run-id", "json"), default="goal-run-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    selected = latest_successful_goal_run(
        vault,
        session_reports_dir=args.session_reports_dir,
    )
    if selected is None:
        print(
            "no completed successful goal session with finalized PROMOTE telemetry found",
            file=sys.stderr,
        )
        return 1
    if args.format == "json":
        print(json.dumps(asdict(selected), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(selected.goal_run_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
