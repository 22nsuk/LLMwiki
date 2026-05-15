from __future__ import annotations

import argparse
from pathlib import Path

from .artifact_io_runtime import promote_schema_validated_json
from .output_runtime import display_path, resolve_repo_output_path


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
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
    )
    print(display_path(vault, promoted))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
