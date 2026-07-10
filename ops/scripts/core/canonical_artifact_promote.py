from __future__ import annotations

import argparse
from pathlib import Path

from .artifact_binding_runtime import BINDING_MODES, CONTENT_BINDING_MODE
from .artifact_io_runtime import (
    promote_schema_validated_json,
)
from .output_runtime import display_path, resolve_repo_output_path

REQUIRED_BINDING_BY_ARTIFACT_KIND = {
    "auto_improve_readiness_report": "revision",
    "goal_run_status": "revision",
    "goal_runtime_certificate": "revision",
    "release_closeout_batch_manifest": "revision",
    "release_closeout_finality_attestation": "revision",
    "release_closeout_fixed_point_report": "revision",
    "release_closeout_sealed_rehearsal_check": "revision",
    "release_closeout_summary": "revision",
    "release_evidence_cohort": "revision",
    "remediation_backlog": "revision",
}


def resolve_binding_mode(
    *,
    expected_artifact_kind: str | None,
    requested_binding_mode: str | None,
) -> str:
    required_mode = REQUIRED_BINDING_BY_ARTIFACT_KIND.get(expected_artifact_kind or "")
    if required_mode is not None and requested_binding_mode is None:
        raise ValueError(
            f"{expected_artifact_kind} promotion requires --binding-mode {required_mode}"
        )
    binding_mode = requested_binding_mode or CONTENT_BINDING_MODE
    if required_mode is not None and binding_mode != required_mode:
        raise ValueError(
            f"{expected_artifact_kind} promotion requires {required_mode} binding; "
            f"got {binding_mode}"
        )
    return binding_mode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote a schema-validated report candidate to its canonical repo path.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--schema")
    parser.add_argument("--expected-artifact-kind")
    parser.add_argument("--expected-producer")
    parser.add_argument(
        "--binding-mode",
        choices=sorted(BINDING_MODES),
        help="Select content, revision, or raw authority for no-op promotion.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    binding_mode = resolve_binding_mode(
        expected_artifact_kind=args.expected_artifact_kind,
        requested_binding_mode=args.binding_mode,
    )
    candidate = resolve_repo_output_path(vault, args.candidate)
    destination = resolve_repo_output_path(vault, args.out)
    promoted = promote_schema_validated_json(
        vault,
        candidate_path=candidate,
        destination_path=destination,
        schema_path=args.schema,
        expected_artifact_kind=args.expected_artifact_kind,
        expected_producer=args.expected_producer,
        context=f"canonical artifact promotion failed for {display_path(vault, destination)}",
        binding_mode=binding_mode,
    )
    print(display_path(vault, promoted))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
