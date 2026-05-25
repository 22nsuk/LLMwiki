#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.observability_artifacts_runtime import (
        write_promotion_decision_trends,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
else:
    from ops.scripts.observability_artifacts_runtime import (
        write_promotion_decision_trends,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--recent-window", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    policy, resolved_policy_path = load_policy(vault, args.policy_path)
    context = RuntimeContext.from_policy(policy)
    rel_path = write_promotion_decision_trends(
        vault,
        policy,
        resolved_policy_path,
        context=context,
        recent_window=args.recent_window,
    )
    print(display_path(vault, vault / rel_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
