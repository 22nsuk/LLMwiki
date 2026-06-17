#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.output_runtime import resolve_repo_output_path
    from ops.scripts.mechanism.auto_improve_runtime import (
        AutoImproveError,
        AutoImproveUsageError,
        maintenance_action_resume_plan,
        refresh_auto_improve_session_report,
        run_auto_improve_session,
        write_maintenance_action_resume_plan,
    )
else:
    from ops.scripts.core.output_runtime import resolve_repo_output_path

    from .auto_improve_runtime import (
        AutoImproveError,
        AutoImproveUsageError,
        maintenance_action_resume_plan,
        refresh_auto_improve_session_report,
        run_auto_improve_session,
        write_maintenance_action_resume_plan,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--session-id")
    ap.add_argument("--resume-session")
    ap.add_argument("--goal-contract")
    ap.add_argument("--max-proposals", type=int)
    ap.add_argument("--max-minutes", type=int)
    ap.add_argument("--max-consecutive-failures", type=int)
    ap.add_argument("--executor", default="codex_exec")
    ap.add_argument("--class", dest="artifact_class", default="system_mechanism")
    ap.add_argument("--allow-learning-uncertain", action="store_true")
    ap.add_argument("--maintain-until-budget", action="store_true")
    ap.add_argument("--maintenance-interval-seconds", type=int)
    ap.add_argument("--post-promote-maintenance-cycles", type=int)
    ap.add_argument("--print-maintenance-action-next-max-proposals", action="store_true")
    ap.add_argument("--maintenance-action-plan-out")
    ap.add_argument("--refresh-session-report", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    try:
        args = parse_args(argv)
        if args.print_maintenance_action_next_max_proposals:
            session_id = args.resume_session or args.session_id
            if not session_id:
                raise AutoImproveUsageError(
                    "--print-maintenance-action-next-max-proposals requires "
                    "--resume-session or --session-id"
                )
            plan = maintenance_action_resume_plan(
                Path(args.vault),
                session_id=session_id,
            )
            if args.maintenance_action_plan_out:
                maintenance_plan_out = resolve_repo_output_path(
                    Path(args.vault),
                    args.maintenance_action_plan_out,
                ).relative_to(Path(args.vault).resolve())
                write_maintenance_action_resume_plan(
                    Path(args.vault),
                    plan,
                    out_path=maintenance_plan_out.as_posix(),
                )
            if not plan["decisions"]["can_resume"]:
                raise AutoImproveUsageError(str(plan["recommended_next_action"]))
            print(plan["next_max_proposals"])
            return
        if args.refresh_session_report:
            session_id = args.resume_session or args.session_id
            if not session_id:
                raise AutoImproveUsageError(
                    "--refresh-session-report requires --resume-session or --session-id"
                )
            result = refresh_auto_improve_session_report(
                Path(args.vault),
                policy_path=args.policy,
                session_id=session_id,
                executor_name=args.executor,
            )
        else:
            result = run_auto_improve_session(
                Path(args.vault),
                policy_path=args.policy,
                session_id=args.session_id,
                resume_session=args.resume_session,
                goal_contract_path=args.goal_contract,
                max_proposals=args.max_proposals,
                max_minutes=args.max_minutes,
                max_consecutive_failures=args.max_consecutive_failures,
                executor_name=args.executor,
                artifact_class=args.artifact_class,
                allow_learning_uncertain=args.allow_learning_uncertain,
                maintain_until_budget=args.maintain_until_budget,
                maintenance_interval_seconds=args.maintenance_interval_seconds,
                post_promote_maintenance_cycles=args.post_promote_maintenance_cycles,
            )
    except AutoImproveError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
