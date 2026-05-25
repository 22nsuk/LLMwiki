#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.finalize_run_runtime import (
        FinalizeRunArtifactDecodeError,
        FinalizeRunArtifactMissingError,
        FinalizeRunArtifactSchemaError,
        FinalizeRunError,
        FinalizeRunUsageError,
        FinalizeRunWriteError,
        finalize_run,
    )
else:
    from .finalize_run_runtime import (
        FinalizeRunArtifactDecodeError,
        FinalizeRunArtifactMissingError,
        FinalizeRunArtifactSchemaError,
        FinalizeRunError,
        FinalizeRunUsageError,
        FinalizeRunWriteError,
        finalize_run,
    )

__all__ = [
    "FinalizeRunArtifactDecodeError",
    "FinalizeRunArtifactMissingError",
    "FinalizeRunArtifactSchemaError",
    "FinalizeRunError",
    "FinalizeRunUsageError",
    "FinalizeRunWriteError",
    "finalize_run",
    "main",
    "parse_args",
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--promotion-report")
    ap.add_argument("--run-ledger")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    vault = Path(args.vault).resolve()
    try:
        result = finalize_run(
            vault,
            args.run_id,
            promotion_report_rel=args.promotion_report,
            run_ledger_rel=args.run_ledger,
        )
    except FinalizeRunError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
