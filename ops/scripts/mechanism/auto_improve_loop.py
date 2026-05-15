#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.auto_improve_goal_runtime import GoalAutoImproveRequest, run_goal_bound_auto_improve
    from ops.scripts.auto_improve_runtime import AutoImproveError, run_auto_improve_session
else:
    from .auto_improve_goal_runtime import GoalAutoImproveRequest, run_goal_bound_auto_improve
    from .auto_improve_runtime import AutoImproveError, run_auto_improve_session


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--session-id")
    ap.add_argument("--resume-session")
    ap.add_argument("--max-proposals", type=int)
    ap.add_argument("--max-minutes", type=int)
    ap.add_argument("--max-consecutive-failures", type=int)
    ap.add_argument("--executor", default="codex_exec")
    ap.add_argument("--class", dest="artifact_class", default="system_mechanism")
    ap.add_argument("--allow-learning-uncertain", action="store_true")
    ap.add_argument("--goal-contract")
    ap.add_argument("--goal-profile", default="5-day-sustained")
    ap.add_argument("--status-out", default="ops/reports/goal-run-status.json")
    ap.add_argument("--audit-jsonl", default="ops/reports/goal-audit-log.jsonl")
    ap.add_argument("--resume-from-checkpoint")
    ap.add_argument("--heartbeat-interval", type=int)
    ap.add_argument("--checkpoint-interval", type=int)
    ap.add_argument("--sustain-until-budget", action="store_true")
    ap.add_argument("--sustain-budget-seconds", type=float)
    ap.add_argument("--goal-dry-run", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    try:
        args = parse_args(argv)
        if args.goal_contract:
            result = run_goal_bound_auto_improve(
                GoalAutoImproveRequest(
                    vault=Path(args.vault),
                    policy_path=args.policy,
                    goal_contract=args.goal_contract,
                    goal_profile=args.goal_profile,
                    status_out=args.status_out,
                    audit_jsonl=args.audit_jsonl,
                    resume_from_checkpoint=args.resume_from_checkpoint,
                    session_id=args.session_id,
                    resume_session=args.resume_session,
                    executor_name=args.executor,
                    artifact_class=args.artifact_class,
                    allow_learning_uncertain=args.allow_learning_uncertain,
                    heartbeat_interval_minutes=args.heartbeat_interval,
                    checkpoint_interval_minutes=args.checkpoint_interval,
                    sustain_until_budget=args.sustain_until_budget,
                    sustain_budget_seconds=args.sustain_budget_seconds,
                    dry_run=args.goal_dry_run,
                )
            )
        else:
            result = run_auto_improve_session(
                Path(args.vault),
                policy_path=args.policy,
                session_id=args.session_id,
                resume_session=args.resume_session,
                max_proposals=args.max_proposals,
                max_minutes=args.max_minutes,
                max_consecutive_failures=args.max_consecutive_failures,
                executor_name=args.executor,
                artifact_class=args.artifact_class,
                allow_learning_uncertain=args.allow_learning_uncertain,
            )
    except AutoImproveError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(exc.exit_code)
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
