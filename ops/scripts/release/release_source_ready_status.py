from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ops.scripts.release_authority_vocabulary import REASON_MACHINE_RELEASE_NOT_ALLOWED
from ops.scripts.release.release_status_v2 import release_status_v2_view_with_readiness_fallback


DEFAULT_CLOSEOUT = "ops/reports/release-closeout-summary.json"
DEFAULT_OUT = "tmp/release-source-ready-status.json"
AUTHORITATIVE_MACHINE_TARGET = "release-evidence-closeout-sealed-check"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_report(vault: Path, *, closeout_path: str = DEFAULT_CLOSEOUT) -> dict[str, Any]:
    closeout = _load_json(vault / closeout_path)
    if not closeout:
        return {
            "artifact_kind": "release_source_ready_status",
            "producer": "ops.scripts.release_source_ready_status",
            "status": "fail",
            "closeout_path": closeout_path,
            "source_ready": False,
            "machine_release_allowed": False,
            "release_authority_status": "unknown",
            "sealed_release_status": "unknown",
            "blocker_reason_ids": ["release_closeout_summary_missing"],
            "authoritative_machine_release_target": AUTHORITATIVE_MACHINE_TARGET,
        }

    status_view = release_status_v2_view_with_readiness_fallback(closeout)
    release_authority_status = str(status_view["release_authority_status"])
    sealed_release_status = str(status_view["sealed_release_status"])
    blocker_reason_ids = [str(reason) for reason in status_view["blocker_reason_ids"]]
    source_ready = release_authority_status in {"clean_pass", "conditional_pass"} or bool(
        closeout.get("checked_in_release_ready")
    )
    machine_release_allowed = (
        release_authority_status == "clean_pass"
        and REASON_MACHINE_RELEASE_NOT_ALLOWED not in blocker_reason_ids
    )
    return {
        "artifact_kind": "release_source_ready_status",
        "producer": "ops.scripts.release_source_ready_status",
        "status": "pass" if source_ready else "fail",
        "closeout_path": closeout_path,
        "source_ready": source_ready,
        "machine_release_allowed": machine_release_allowed,
        "operator_release_allowed": bool(closeout.get("operator_release_allowed")),
        "compatibility_status_value": str(status_view["compatibility_status_value"]),
        "release_authority_status": release_authority_status,
        "sealed_release_status": sealed_release_status,
        "blocker_reason_ids": blocker_reason_ids,
        "status_v2_used_legacy_fallback_fields": status_view["used_legacy_fallback_fields"],
        "authoritative_machine_release_target": AUTHORITATIVE_MACHINE_TARGET,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    destination = vault / out_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def print_banner(report: dict[str, Any]) -> None:
    print("release-source-ready status")
    print(f"source_ready={str(report['source_ready']).lower()}")
    print(f"machine_release_allowed={str(report['machine_release_allowed']).lower()}")
    print(f"release_authority_status={report['release_authority_status']}")
    print(f"sealed_release_status={report['sealed_release_status']}")
    print(
        "authoritative_machine_release_target="
        f"{report['authoritative_machine_release_target']}"
    )


def _display_path(vault: Path, path: Path) -> str:
    try:
        return path.relative_to(vault).as_posix()
    except ValueError:
        return path.as_posix()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize release-source-ready authority.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--closeout", default=DEFAULT_CLOSEOUT)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, closeout_path=args.closeout)
    destination = write_report(vault, report, args.out)
    print_banner(report)
    print(_display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
