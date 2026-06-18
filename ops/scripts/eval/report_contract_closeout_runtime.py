from __future__ import annotations

import argparse
import json
from pathlib import Path

from ops.scripts.core.artifact_io_runtime import read_json_object

POLICY_PATH = "ops/policies/report-contract-closeout.json"


def load_pre_refresh_targets(vault: Path) -> list[str]:
    payload = read_json_object(vault / POLICY_PATH, context=POLICY_PATH)
    version = payload.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"{POLICY_PATH}: version must be an integer >= 1")
    raw_targets = payload.get("pre_refresh_targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError(f"{POLICY_PATH}: pre_refresh_targets must be a non-empty list")
    targets = [str(item).strip() for item in raw_targets if str(item).strip()]
    if not targets:
        raise ValueError(f"{POLICY_PATH}: pre_refresh_targets must contain at least one target")
    return targets


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve ordered Make targets for report-contract closeout pre-refresh"
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--format", choices=("json", "lines"), default="lines")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    targets = load_pre_refresh_targets(vault)
    if args.format == "json":
        print(json.dumps({"pre_refresh_targets": targets}, ensure_ascii=False))
    else:
        for target in targets:
            print(target)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
