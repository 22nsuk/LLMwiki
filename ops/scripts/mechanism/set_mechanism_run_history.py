#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.filesystem_runtime import (
        AtomicTextUpdate,
        atomic_multi_write,
        build_atomic_text_updates,
    )
    from ops.scripts.core.observability_artifacts_runtime import (
        write_run_artifact_fingerprint,
    )
    from ops.scripts.core.policy_runtime import load_policy
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        PROMOTION_REPORT_SCHEMA_PATH,
        RUN_LEDGER_SCHEMA_PATH,
    )
    from ops.scripts.core.schema_runtime import load_schema, validate_or_raise
else:
    from ops.scripts.core.filesystem_runtime import (
        AtomicTextUpdate,
        atomic_multi_write,
        build_atomic_text_updates,
    )
    from ops.scripts.core.observability_artifacts_runtime import (
        write_run_artifact_fingerprint,
    )
    from ops.scripts.core.policy_runtime import load_policy
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        PROMOTION_REPORT_SCHEMA_PATH,
        RUN_LEDGER_SCHEMA_PATH,
    )
    from ops.scripts.core.schema_runtime import load_schema, validate_or_raise


PROMOTION_REPORT_SCHEMA = PROMOTION_REPORT_SCHEMA_PATH
RUN_LEDGER_SCHEMA = RUN_LEDGER_SCHEMA_PATH


class SetMechanismRunHistoryError(Exception):
    exit_code = 8


class SetMechanismRunHistoryUsageError(SetMechanismRunHistoryError):
    exit_code = 2


class SetMechanismRunHistoryArtifactError(SetMechanismRunHistoryError):
    exit_code = 4


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SetMechanismRunHistoryArtifactError(f"missing artifact: {path.as_posix()}") from exc
    except json.JSONDecodeError as exc:
        raise SetMechanismRunHistoryArtifactError(
            f"invalid json in {path.as_posix()}: line {exc.lineno} column {exc.colno}"
        ) from exc


def _load_validated_json(vault: Path, path: Path, schema_rel_path: str, *, context: str) -> dict:
    payload = _read_json(path)
    try:
        validate_or_raise(
            payload,
            load_schema(vault / schema_rel_path),
            context=context,
        )
    except FileNotFoundError as exc:
        raise SetMechanismRunHistoryArtifactError(f"missing schema: {schema_rel_path}") from exc
    except ValueError as exc:
        raise SetMechanismRunHistoryArtifactError(str(exc)) from exc
    return payload


def _timestamp(ts: str | None, *, context: RuntimeContext) -> str:
    if ts:
        return ts
    return context.isoformat_z()


def _history_payload(*, status: str, reason: str, by: str, ts: str) -> dict:
    return {
        "status": status,
        "reason": reason,
        "by": by,
        "ts": ts,
    }


def _json_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_history_atomic_updates(
    *,
    promotion_path: Path,
    promotion_report: dict,
    ledger_path: Path,
    run_ledger: dict,
) -> list[AtomicTextUpdate]:
    return build_atomic_text_updates(
        [
            (promotion_path, _json_text(promotion_report)),
            (ledger_path, _json_text(run_ledger)),
        ]
    )


def set_mechanism_run_history(
    vault: Path,
    run_id: str,
    *,
    status: str,
    reason: str,
    by: str,
    ts: str | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    vault = vault.resolve()
    policy, _ = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    promotion_path = (vault / "runs" / run_id / "promotion-report.json").resolve()
    ledger_path = (vault / "runs" / run_id / "run-ledger.json").resolve()

    promotion_report = _load_validated_json(
        vault,
        promotion_path,
        PROMOTION_REPORT_SCHEMA,
        context=f"promotion report schema validation failed for runs/{run_id}/promotion-report.json",
    )
    run_ledger = _load_validated_json(
        vault,
        ledger_path,
        RUN_LEDGER_SCHEMA,
        context=f"run-ledger schema validation failed for runs/{run_id}/run-ledger.json",
    )

    if promotion_report["artifact_class"] != "system_mechanism":
        raise SetMechanismRunHistoryUsageError(
            f"run {run_id} is not a system_mechanism promotion report"
        )
    if status != "active" and not reason.strip():
        raise SetMechanismRunHistoryUsageError(
            "--reason is required when setting history status to archived or quarantined"
        )

    normalized_ts = _timestamp(ts, context=runtime_context)
    normalized_reason = "" if status == "active" else reason.strip()
    target_history = _history_payload(
        status=status,
        reason=normalized_reason,
        by=by,
        ts=normalized_ts,
    )
    current_history = promotion_report.get("history", {})
    if current_history == target_history:
        fingerprint_rel = write_run_artifact_fingerprint(
            vault,
            run_id,
            context=runtime_context,
        )
        return {
            "run_id": run_id,
            "status": status,
            "changed": False,
            "promotion_report": promotion_path.as_posix(),
            "run_ledger": ledger_path.as_posix(),
            "run_artifact_fingerprint": fingerprint_rel,
        }

    promotion_report["history"] = target_history
    run_ledger.setdefault("events", []).append(
        {
            "ts": normalized_ts,
            "type": "history_status_updated",
            "summary": (
                f"Marked mechanism run history as {status}."
                if status != "active"
                else "Restored mechanism run history to active."
            ),
            "artifacts": [
                f"runs/{run_id}/promotion-report.json",
                f"runs/{run_id}/run-ledger.json",
            ],
            "decision": status,
        }
    )
    if status != "active" and run_ledger.get("status") == "running":
        run_ledger["status"] = "blocked"

    validate_or_raise(
        promotion_report,
        load_schema(vault / PROMOTION_REPORT_SCHEMA),
        context="updated promotion report schema validation failed",
    )
    validate_or_raise(
        run_ledger,
        load_schema(vault / RUN_LEDGER_SCHEMA),
        context="updated run-ledger schema validation failed",
    )

    atomic_multi_write(
        _build_history_atomic_updates(
            promotion_path=promotion_path,
            promotion_report=promotion_report,
            ledger_path=ledger_path,
            run_ledger=run_ledger,
        )
    )
    fingerprint_rel = write_run_artifact_fingerprint(
        vault,
        run_id,
        context=runtime_context,
    )

    return {
        "run_id": run_id,
        "status": status,
        "changed": True,
        "promotion_report": promotion_path.as_posix(),
        "run_ledger": ledger_path.as_posix(),
        "run_artifact_fingerprint": fingerprint_rel,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument(
        "--status",
        required=True,
        choices=["active", "archived", "quarantined"],
    )
    ap.add_argument("--reason", default="")
    ap.add_argument("--by", default="")
    ap.add_argument("--ts")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    try:
        args = parse_args(argv)
        result = set_mechanism_run_history(
            Path(args.vault),
            args.run_id,
            status=args.status,
            reason=args.reason,
            by=args.by,
            ts=args.ts,
        )
    except SetMechanismRunHistoryError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
