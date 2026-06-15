from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import load_optional_json_object
from ops.scripts.output_runtime import display_path

DEFAULT_GOAL_RUN_ID = "auto-improve-trial"
DEFAULT_GOAL_RUN_STATUS = "ops/reports/goal-run-status.json"
DEFAULT_GOAL_RUNTIME_CERTIFICATE = "ops/reports/goal-runtime-certificate.json"
DEFAULT_OUT = "tmp/goal-runtime-certificate-run-id-guard.json"
PRODUCER = "ops.scripts.goal_runtime_certificate_run_id_guard"


@dataclass(frozen=True)
class GoalRuntimeCertificateRunIdGuardRequest:
    vault: Path
    goal_run_id: str
    goal_run_id_origin: str = ""
    default_goal_run_id: str = DEFAULT_GOAL_RUN_ID
    goal_run_status_path: str = DEFAULT_GOAL_RUN_STATUS
    goal_runtime_certificate_path: str = DEFAULT_GOAL_RUNTIME_CERTIFICATE
    out_path: str = DEFAULT_OUT


def _run_id_from_report(payload: dict[str, Any]) -> str:
    run = payload.get("run")
    if not isinstance(run, dict):
        return ""
    return str(run.get("run_id", "")).strip()


def _status_from_report(payload: dict[str, Any]) -> str:
    run = payload.get("run")
    if not isinstance(run, dict):
        return ""
    return str(run.get("status", run.get("run_status", ""))).strip()


def _load_report(vault: Path, rel_path: str) -> dict[str, Any]:
    payload = load_optional_json_object(vault / rel_path)
    return payload if isinstance(payload, dict) else {}


def _is_makefile_default_run_id(request: GoalRuntimeCertificateRunIdGuardRequest) -> bool:
    return (
        request.goal_run_id == request.default_goal_run_id
        and request.goal_run_id_origin in {"default", "file", ""}
    )


def build_report(request: GoalRuntimeCertificateRunIdGuardRequest) -> dict[str, Any]:
    vault = request.vault.resolve()
    status_report = _load_report(vault, request.goal_run_status_path)
    certificate_report = _load_report(vault, request.goal_runtime_certificate_path)
    status_run_id = _run_id_from_report(status_report)
    certificate_run_id = _run_id_from_report(certificate_report)
    observed = {
        "goal_run_status": {
            "path": request.goal_run_status_path,
            "exists": bool(status_report),
            "run_id": status_run_id,
            "run_status": _status_from_report(status_report),
        },
        "goal_runtime_certificate": {
            "path": request.goal_runtime_certificate_path,
            "exists": bool(certificate_report),
            "run_id": certificate_run_id,
            "run_status": _status_from_report(certificate_report),
        },
    }
    conflicting_run_ids = sorted(
        run_id
        for run_id in {status_run_id, certificate_run_id}
        if run_id and run_id != request.goal_run_id
    )
    blockers: list[str] = []
    if _is_makefile_default_run_id(request) and conflicting_run_ids:
        blockers.append("default_goal_run_id_would_overwrite_existing_run_evidence")
    return {
        "artifact_kind": "goal_runtime_certificate_run_id_guard",
        "producer": PRODUCER,
        "status": "fail" if blockers else "pass",
        "requested": {
            "goal_run_id": request.goal_run_id,
            "goal_run_id_origin": request.goal_run_id_origin,
            "default_goal_run_id": request.default_goal_run_id,
            "using_makefile_default_goal_run_id": _is_makefile_default_run_id(request),
        },
        "observed": observed,
        "conflicting_run_ids": conflicting_run_ids,
        "blockers": blockers,
        "recommended_next_action": (
            "Pass GOAL_RUN_ID=<completed-run-id> when refreshing the certificate, "
            "or explicitly set GOAL_RUN_ID=auto-improve-trial if replacing existing "
            "goal evidence is intentional."
            if blockers
            else ""
        ),
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = vault / out_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--goal-run-id", required=True)
    parser.add_argument("--goal-run-id-origin", default="")
    parser.add_argument("--default-goal-run-id", default=DEFAULT_GOAL_RUN_ID)
    parser.add_argument("--goal-run-status", default=DEFAULT_GOAL_RUN_STATUS)
    parser.add_argument("--goal-runtime-certificate", default=DEFAULT_GOAL_RUNTIME_CERTIFICATE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRuntimeCertificateRunIdGuardRequest(
            vault=vault,
            goal_run_id=args.goal_run_id,
            goal_run_id_origin=args.goal_run_id_origin,
            default_goal_run_id=args.default_goal_run_id,
            goal_run_status_path=args.goal_run_status,
            goal_runtime_certificate_path=args.goal_runtime_certificate,
            out_path=args.out,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if report["status"] == "fail":
        print(report["recommended_next_action"])
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
