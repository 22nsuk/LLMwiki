#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_io_runtime import (
        read_json_object,
        write_schema_validated_json,
    )
    from ops.scripts.core.command_log_summary_runtime import write_command_log_summary
    from ops.scripts.core.generated_artifact_retention_clean import (
        build_report as build_retention_report,
    )
    from ops.scripts.core.observability_artifacts_runtime import (
        write_run_artifact_fingerprint,
    )
    from ops.scripts.core.output_runtime import (
        display_path,
        resolve_repo_output_path,
        write_output_text,
    )
    from ops.scripts.core.policy_runtime import report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        COMMAND_LOG_SUMMARY_BACKFILL_SCHEMA_PATH,
        EXECUTOR_REPORT_SCHEMA_PATH,
        REWORK_CLOSURES_SCHEMA_PATH,
        RUN_LEDGER_SCHEMA_PATH,
        TIMEOUT_FAILURE_SCHEMA_PATH,
    )
    from ops.scripts.core.schema_runtime import (
        load_schema_with_vault_override,
        validate_with_schema,
    )
else:
    from .artifact_io_runtime import read_json_object, write_schema_validated_json
    from .command_log_summary_runtime import write_command_log_summary
    from .generated_artifact_retention_clean import (
        build_report as build_retention_report,
    )
    from .observability_artifacts_runtime import write_run_artifact_fingerprint
    from .output_runtime import (
        display_path,
        resolve_repo_output_path,
        write_output_text,
    )
    from .policy_runtime import report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import (
        COMMAND_LOG_SUMMARY_BACKFILL_SCHEMA_PATH,
        EXECUTOR_REPORT_SCHEMA_PATH,
        REWORK_CLOSURES_SCHEMA_PATH,
        RUN_LEDGER_SCHEMA_PATH,
        TIMEOUT_FAILURE_SCHEMA_PATH,
    )
    from .schema_runtime import load_schema_with_vault_override, validate_with_schema


DEFAULT_OUT = "tmp/command-log-summary-backfill.json"
PRODUCER = "ops.scripts.command_log_summary_backfill"
DELETE_CONFIRMATION = "CONFIRM_COMMAND_LOG_RAW_DELETE"
RUN_COMMAND_PREFIXES = frozenset({"mutation-command", "repo-health"})
RUN_COMMAND_TIMEOUT_KEYS = {
    "mutation-command": "mutation_command",
    "repo-health": "repo_health",
}
RUN_COMMAND_SUCCESS_EVENTS = {
    "mutation-command": {("mutation_applied", "candidate_ready_for_capture")},
    "repo-health": {("repo_health_checked", "repo_health_pass")},
}
REPORT_REFERENCE_SUFFIXES = (
    "-executor-report.json",
    "-last-message.json",
    "-timeout-failure.json",
    "run-ledger.json",
)


@dataclass(frozen=True)
class LogGroup:
    run_id: str
    owning_run: str
    prefix: str
    kind: str
    raw_paths: dict[str, str]


@dataclass
class _BackfillState:
    records: list[dict[str, Any]] = field(default_factory=list)
    touched_raw_paths: set[str] = field(default_factory=set)
    touched_runs: set[str] = field(default_factory=set)
    summary_paths: set[str] = field(default_factory=set)
    evidence_refs_by_run: dict[str, set[str]] = field(default_factory=dict)
    backfilled_raw_by_run: dict[str, set[str]] = field(default_factory=dict)
    reference_needles_by_run: dict[str, set[str]] = field(default_factory=dict)


def _context(clock: dt.datetime | None = None) -> RuntimeContext:
    instant = clock or RuntimeContext(display_timezone=dt.UTC).utcnow().replace(microsecond=0)
    return RuntimeContext(display_timezone=dt.UTC, clock=lambda: instant)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return read_json_object(path, context=path.as_posix())
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    write_output_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _run_id_from_owning_run(owning_run: str) -> str:
    return Path(owning_run).name


def _owning_run_path(vault: Path, rel_path: str) -> str:
    parts = Path(rel_path).parts
    if len(parts) < 2 or parts[0] != "runs":
        return ""
    if len(parts) >= 3 and parts[1] == "archive":
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def _stream_parts(filename: str) -> tuple[str, str]:
    if filename.endswith(".stdout.txt"):
        return filename.removesuffix(".stdout.txt"), "stdout"
    if filename.endswith(".stderr.txt"):
        return filename.removesuffix(".stderr.txt"), "stderr"
    return "", ""


def _is_nonempty_stream_log(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    prefix, stream = _stream_parts(path.name)
    if not prefix or not stream:
        return False
    return path.stat().st_size > 0


def _candidate_groups(vault: Path, run_ids: set[str]) -> list[LogGroup]:
    grouped: dict[tuple[str, str], dict[str, str]] = {}
    for path in sorted((vault / "runs").rglob("*")):
        if not _is_nonempty_stream_log(path):
            continue
        rel_path = report_path(vault, path)
        owning_run = _owning_run_path(vault, rel_path)
        run_id = _run_id_from_owning_run(owning_run)
        if run_ids and run_id not in run_ids:
            continue
        prefix, stream = _stream_parts(path.name)
        grouped.setdefault((owning_run, prefix), {})[stream] = rel_path

    groups: list[LogGroup] = []
    for (owning_run, prefix), raw_paths in sorted(grouped.items()):
        run_id = _run_id_from_owning_run(owning_run)
        report = vault / owning_run / f"{prefix}-executor-report.json"
        kind = "executor" if report.is_file() else "run_command" if prefix in RUN_COMMAND_PREFIXES else ""
        if kind:
            groups.append(
                LogGroup(
                    run_id=run_id,
                    owning_run=owning_run,
                    prefix=prefix,
                    kind=kind,
                    raw_paths=raw_paths,
                )
            )
    return groups


def _result_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return {}
    required = ("returncode", "timed_out", "timeout_seconds", "termination_reason")
    if not all(field in result for field in required):
        return {}
    return {
        "returncode": int(result.get("returncode", 0)),
        "timed_out": bool(result.get("timed_out", False)),
        "timeout_seconds": int(result.get("timeout_seconds", 0) or 0),
        "termination_reason": str(result.get("termination_reason", "")).strip(),
    }


def _executor_report_update(
    vault: Path,
    group: LogGroup,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report_rel = f"{group.owning_run}/{group.prefix}-executor-report.json"
    payload = _read_json(vault / report_rel)
    if not payload:
        return {}, {"status": "missing_or_malformed", "path": report_rel}
    command = payload.get("command")
    argv = command.get("argv") if isinstance(command, dict) else None
    result = _result_fields(payload)
    artifacts = payload.get("artifacts")
    if not isinstance(argv, list) or not result or not isinstance(artifacts, dict):
        return {}, {"status": "missing_metadata", "path": report_rel}

    updated = json.loads(json.dumps(payload))
    updated_artifacts = updated["artifacts"]
    updated_artifacts["stdout"] = f"{group.owning_run}/{group.prefix}.stdout-trace.txt"
    updated_artifacts["stderr"] = f"{group.owning_run}/{group.prefix}.stderr-trace.txt"
    updated_artifacts["command_log_summary"] = f"{group.owning_run}/command-log-summary.json"
    schema = load_schema_with_vault_override(vault, EXECUTOR_REPORT_SCHEMA_PATH)
    issues = validate_with_schema(updated, schema)
    if issues:
        return {}, {
            "status": "schema_invalid_after_update",
            "path": report_rel,
            "schema_issues": issues[:5],
        }
    return updated, {
        "status": "ready",
        "path": report_rel,
        "argv": [str(item) for item in argv],
        "result": result,
    }


def _run_telemetry(vault: Path, owning_run: str) -> dict[str, Any]:
    return _read_json(vault / owning_run / "run-telemetry.json")


def _is_promoted_finalized(vault: Path, owning_run: str) -> bool:
    telemetry = _run_telemetry(vault, owning_run)
    return telemetry.get("decision") == "PROMOTE" and bool(telemetry.get("finalized"))


def _run_command_result(vault: Path, group: LogGroup) -> tuple[dict[str, Any], dict[str, Any]]:
    telemetry = _run_telemetry(vault, group.owning_run)
    if not (telemetry.get("decision") == "PROMOTE" and bool(telemetry.get("finalized"))):
        return {}, {"status": "not_promoted_finalized"}
    timeouts = telemetry.get("command_timeouts")
    timeout_key = RUN_COMMAND_TIMEOUT_KEYS[group.prefix]
    timeout_payload = timeouts.get(timeout_key) if isinstance(timeouts, dict) else None
    if not isinstance(timeout_payload, dict):
        return {}, {"status": "missing_command_timeout_metadata"}
    ledger = _read_json(vault / group.owning_run / "run-ledger.json")
    events = ledger.get("events")
    if not isinstance(events, list):
        return {}, {"status": "missing_run_ledger_events"}
    success_events = RUN_COMMAND_SUCCESS_EVENTS[group.prefix]
    matched_success = any(
        isinstance(event, dict)
        and (str(event.get("type", "")), str(event.get("decision", ""))) in success_events
        for event in events
    )
    if not matched_success:
        return {}, {"status": "missing_success_ledger_event"}
    return {
        "command": "",
        "argv": [],
        "returncode": 0,
        "timed_out": bool(timeout_payload.get("timed_out", False)),
        "timeout_seconds": int(timeout_payload.get("timeout_seconds", 0) or 0),
        "termination_reason": str(timeout_payload.get("termination_reason", "completed")).strip()
        or "completed",
    }, {"status": "ready"}


def _replace_raw_refs(value: Any, replacements: Mapping[str, str]) -> tuple[Any, int]:
    if isinstance(value, str):
        return replacements.get(value, value), 1 if value in replacements else 0
    if isinstance(value, list):
        changed = 0
        items = []
        for item in value:
            replaced, count = _replace_raw_refs(item, replacements)
            changed += count
            items.append(replaced)
        return items, changed
    if isinstance(value, dict):
        changed = 0
        result = {}
        for key, item in value.items():
            replaced, count = _replace_raw_refs(item, replacements)
            changed += count
            result[key] = replaced
        return result, changed
    return value, 0


def _schema_for_reference_file(filename: str) -> str:
    if filename.endswith(("-executor-report.json", "-last-message.json")):
        return EXECUTOR_REPORT_SCHEMA_PATH
    if filename.endswith("-timeout-failure.json"):
        return TIMEOUT_FAILURE_SCHEMA_PATH
    if filename == "run-ledger.json":
        return RUN_LEDGER_SCHEMA_PATH
    return ""


def _complete_executor_artifacts(payload: Any, rel_path: str) -> Any:
    if not isinstance(payload, dict) or not Path(rel_path).name.endswith(("-executor-report.json", "-last-message.json")):
        return payload
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict) and "command_log_summary" not in artifacts:
        artifacts["command_log_summary"] = f"{Path(rel_path).parent.as_posix()}/command-log-summary.json"
    return payload


def _update_same_run_reference_file(
    vault: Path,
    rel_path: str,
    replacements: Mapping[str, str],
    *,
    apply: bool,
) -> dict[str, Any]:
    path = vault / rel_path
    payload = _read_json(path)
    if not payload:
        return {"path": rel_path, "status": "missing_or_malformed", "updated": False}
    replaced, count = _replace_raw_refs(payload, replacements)
    if count == 0:
        return {"path": rel_path, "status": "unchanged", "updated": False}
    replaced = _complete_executor_artifacts(replaced, rel_path)
    schema_path = _schema_for_reference_file(path.name)
    if schema_path:
        schema = load_schema_with_vault_override(vault, schema_path)
        issues = validate_with_schema(replaced, schema)
        if issues:
            return {
                "path": rel_path,
                "status": "schema_invalid_after_update",
                "updated": False,
                "schema_issues": issues[:5],
            }
    if apply:
        _write_json(path, replaced)
    return {"path": rel_path, "status": "updated", "updated": True, "replacement_count": count}


def _reference_file_rels(vault: Path, owning_run: str) -> list[str]:
    run_dir = vault / owning_run
    if not run_dir.is_dir():
        return []
    return [
        report_path(vault, path)
        for path in sorted(run_dir.rglob("*.json"))
        if path.name.endswith(REPORT_REFERENCE_SUFFIXES)
    ]


def _same_run_raw_references(vault: Path, owning_run: str, raw_paths: Iterable[str]) -> list[dict[str, str]]:
    needles = set(raw_paths)
    references: list[dict[str, str]] = []
    for rel_path in _reference_file_rels(vault, owning_run):
        text = (vault / rel_path).read_text(encoding="utf-8", errors="replace")
        for raw_path in sorted(needles):
            if raw_path in text:
                references.append({"path": rel_path, "raw_path": raw_path})
    return references


def _write_summary_for_group(
    vault: Path,
    group: LogGroup,
    *,
    result: Mapping[str, Any],
    argv: list[str],
    context: RuntimeContext,
) -> str:
    return write_command_log_summary(
        vault,
        group.run_id,
        group.prefix,
        result,
        raw_paths=group.raw_paths,
        context=context,
        command_argv=argv,
        run_root_rel=group.owning_run,
    )


def _raw_path_aliases(raw_path: str, owning_run: str, run_id: str) -> set[str]:
    filename = Path(raw_path).name
    aliases = {
        raw_path,
        f"{owning_run}/{filename}",
        f"runs/{run_id}/{filename}",
        f"runs/archive/{run_id}/{filename}",
    }
    return {path for path in aliases if path.strip()}


def _group_replacements(group: LogGroup) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for stream, raw_path in group.raw_paths.items():
        trace_path = f"{group.owning_run}/{group.prefix}.{stream}-trace.txt"
        for alias in _raw_path_aliases(raw_path, group.owning_run, group.run_id):
            replacements[alias] = trace_path
    return replacements


def _raw_reference_needles(group: LogGroup) -> set[str]:
    needles: set[str] = set()
    for raw_path in group.raw_paths.values():
        needles.update(_raw_path_aliases(raw_path, group.owning_run, group.run_id))
    return needles


def _summary_replacements(vault: Path, owning_run: str) -> dict[str, str]:
    run_id = _run_id_from_owning_run(owning_run)
    payload = _read_json(vault / owning_run / "command-log-summary.json")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return {}
    replacements: dict[str, str] = {}
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        raw_path = str(stream.get("original_path", "")).strip()
        trace_path = str(stream.get("trace_path", "")).strip()
        if not raw_path or not trace_path or not (vault / trace_path).is_file():
            continue
        for alias in _raw_path_aliases(raw_path, owning_run, run_id):
            replacements[alias] = trace_path
    return replacements


def _summary_run_roots(vault: Path, selected_run_ids: set[str], *, all_runs: bool) -> list[str]:
    roots: list[str] = []
    seen: set[str] = set()
    for summary_path in sorted((vault / "runs").rglob("command-log-summary.json")):
        if not summary_path.is_file():
            continue
        rel_path = report_path(vault, summary_path)
        owning_run = str(Path(rel_path).parent).replace("\\", "/")
        run_id = _run_id_from_owning_run(owning_run)
        if not all_runs and run_id not in selected_run_ids:
            continue
        if owning_run not in seen:
            roots.append(owning_run)
            seen.add(owning_run)
    return roots


def _repair_summary_references(
    vault: Path,
    owning_run: str,
    *,
    apply: bool,
) -> list[dict[str, Any]]:
    replacements = _summary_replacements(vault, owning_run)
    if not replacements:
        return []
    updates = []
    for rel_path in _reference_file_rels(vault, owning_run):
        update = _update_same_run_reference_file(
            vault,
            rel_path,
            replacements,
            apply=apply,
        )
        if update["status"] != "unchanged":
            updates.append(update)
    return updates


def _build_group_record(
    vault: Path,
    group: LogGroup,
    *,
    include_run_commands: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    base: dict[str, Any] = {
        "run_id": group.run_id,
        "owning_run": group.owning_run,
        "prefix": group.prefix,
        "kind": group.kind,
        "raw_paths": [group.raw_paths[key] for key in sorted(group.raw_paths)],
        "status": "skipped",
        "reasons": [],
        "summary_path": f"{group.owning_run}/command-log-summary.json",
        "trace_paths": [
            f"{group.owning_run}/{group.prefix}.{stream}-trace.txt"
            for stream in sorted(group.raw_paths)
        ],
        "reference_updates": [],
    }
    if group.kind == "run_command" and not include_run_commands:
        base["reasons"].append("run_command_backfill_not_enabled")
        return base, None, {}
    if group.kind == "executor":
        updated_report, metadata = _executor_report_update(vault, group)
        if metadata.get("status") != "ready":
            base["reasons"].append(str(metadata["status"]))
            base["executor_report"] = metadata
            return base, None, {}
        result = {
            "command": " ".join(metadata["argv"]),
            **metadata["result"],
        }
        base["executor_report"] = metadata
        return base, updated_report, {"result": result, "argv": metadata["argv"]}
    result, metadata = _run_command_result(vault, group)
    if metadata.get("status") != "ready":
        base["reasons"].append(str(metadata["status"]))
        base["run_command"] = metadata
        return base, None, {}
    base["run_command"] = metadata
    return base, None, {"result": result, "argv": []}


def _raw_retention_reason_by_path(retention_report: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    records = retention_report.get("run_log_retention")
    if not isinstance(records, list):
        return result
    for record in records:
        if isinstance(record, dict):
            result[str(record.get("path", ""))] = str(record.get("reason", ""))
    return result


def _closure_payload(vault: Path) -> dict[str, Any]:
    path = vault / "ops/reports/rework-closures.json"
    if path.is_file():
        return _read_json(path)
    return {
        "$schema": REWORK_CLOSURES_SCHEMA_PATH,
        "artifact_kind": "rework_closures",
        "generated_at": "",
        "summary": {"closure_count": 0, "closed_rework_count": 0},
        "closures": [],
    }


def _closed_run_ids(payload: Mapping[str, Any]) -> set[str]:
    closed: set[str] = set()
    closures = payload.get("closures")
    if not isinstance(closures, list):
        return closed
    for closure in closures:
        if not isinstance(closure, dict):
            continue
        run_ids = closure.get("closed_run_ids")
        if isinstance(run_ids, list):
            closed.update(str(run_id) for run_id in run_ids if str(run_id).strip())
    return closed


def _append_rework_closure(
    vault: Path,
    run_ids: list[str],
    *,
    evidence_refs: list[str],
    generated_at: str,
    apply: bool,
) -> dict[str, Any]:
    if not run_ids:
        return {"status": "not_needed", "closed_run_ids": []}
    payload = _closure_payload(vault)
    closed = _closed_run_ids(payload)
    new_run_ids = [run_id for run_id in run_ids if run_id not in closed]
    if not new_run_ids:
        return {"status": "already_closed", "closed_run_ids": []}
    closures = payload.setdefault("closures", [])
    if not isinstance(closures, list):
        return {"status": "malformed_rework_closures", "closed_run_ids": []}
    closures.append(
        {
            "rework_key": "retention:legacy-command-log-summary-backfill",
            "closure_status": "closed",
            "closure_reason": (
                "Promoted finalized run has schema-backed command-log summaries and capped traces "
                "for legacy raw command logs; raw logs may be retained or deleted by retention policy."
            ),
            "superseding_run_id": "",
            "closed_at": generated_at,
            "closed_run_ids": new_run_ids,
            "evidence_refs": sorted(set(evidence_refs)),
        }
    )
    payload["generated_at"] = generated_at
    payload["summary"] = {
        "closure_count": len(closures),
        "closed_rework_count": len(_closed_run_ids(payload)),
    }
    if apply:
        schema = load_schema_with_vault_override(vault, REWORK_CLOSURES_SCHEMA_PATH)
        write_schema_validated_json(
            vault / "ops/reports/rework-closures.json",
            payload,
            schema,
            context="schema validation failed for ops/reports/rework-closures.json",
            trailing_newline=True,
        )
    return {"status": "updated", "closed_run_ids": new_run_ids}


def _all_nonempty_raw_logs_for_run(vault: Path, owning_run: str) -> set[str]:
    run_dir = vault / owning_run
    if not run_dir.is_dir():
        return set()
    return {
        report_path(vault, path)
        for path in run_dir.rglob("*")
        if _is_nonempty_stream_log(path)
    }


def _raw_delete_records(retention_report: Mapping[str, Any], touched_paths: set[str]) -> list[dict[str, Any]]:
    candidates = retention_report.get("delete_candidates")
    if not isinstance(candidates, list):
        return []
    return [
        item
        for item in candidates
        if isinstance(item, dict)
        and item.get("category") == "raw_command_log_with_summary"
        and item.get("delete_allowed") is True
        and str(item.get("path", "")) in touched_paths
    ]


def _delete_paths(vault: Path, records: list[dict[str, Any]], *, apply: bool) -> list[str]:
    deleted: list[str] = []
    for record in records:
        rel_path = str(record["path"])
        if apply:
            path = vault / rel_path
            if path.is_file() and not path.is_symlink():
                path.unlink()
        deleted.append(rel_path)
    return deleted


def _selected_groups(vault: Path, selected_run_ids: set[str], *, all_runs: bool) -> list[LogGroup]:
    groups = _candidate_groups(vault, selected_run_ids)
    if not all_runs and not selected_run_ids:
        return []
    return groups


def _collect_backfill_records(
    vault: Path,
    groups: list[LogGroup],
    before_reasons: Mapping[str, str],
    *,
    include_run_commands: bool,
    apply: bool,
    context: RuntimeContext,
) -> _BackfillState:
    state = _BackfillState()
    for group in groups:
        record, updated_report, metadata = _build_group_record(
            vault,
            group,
            include_run_commands=include_run_commands,
        )
        record["pre_retention_reasons"] = {
            path: before_reasons.get(path, "") for path in record["raw_paths"]
        }
        if metadata:
            _apply_group_metadata(
                vault,
                group,
                record,
                updated_report,
                metadata,
                apply=apply,
                context=context,
                state=state,
            )
        state.records.append(record)
    return state


def _apply_group_metadata(
    vault: Path,
    group: LogGroup,
    record: dict[str, Any],
    updated_report: dict[str, Any] | None,
    metadata: dict[str, Any],
    *,
    apply: bool,
    context: RuntimeContext,
    state: _BackfillState,
) -> None:
    replacements = _group_replacements(group)
    reference_updates = []
    if group.kind == "executor":
        report_rel = f"{group.owning_run}/{group.prefix}-executor-report.json"
        reference_updates.append({"path": report_rel, "status": "updated", "updated": True})
        if apply and updated_report is not None:
            _write_json(vault / report_rel, updated_report)
            state.evidence_refs_by_run.setdefault(group.owning_run, set()).add(report_rel)
    for rel_path in _reference_file_rels(vault, group.owning_run):
        if group.kind == "executor" and rel_path == f"{group.owning_run}/{group.prefix}-executor-report.json":
            continue
        update = _update_same_run_reference_file(
            vault,
            rel_path,
            replacements,
            apply=apply,
        )
        if update.get("updated"):
            state.evidence_refs_by_run.setdefault(group.owning_run, set()).add(rel_path)
        reference_updates.append(update)
    record["reference_updates"] = reference_updates
    record["status"] = "applied" if apply else "eligible"
    if not apply:
        return
    summary_rel = _write_summary_for_group(
        vault,
        group,
        result=metadata["result"],
        argv=metadata["argv"],
        context=context,
    )
    state.summary_paths.add(summary_rel)
    state.evidence_refs_by_run.setdefault(group.owning_run, set()).add(summary_rel)
    state.touched_runs.add(group.owning_run)
    state.touched_raw_paths.update(group.raw_paths.values())
    state.backfilled_raw_by_run.setdefault(group.owning_run, set()).update(group.raw_paths.values())
    state.reference_needles_by_run.setdefault(group.owning_run, set()).update(
        _raw_reference_needles(group)
    )


def _repair_existing_summary_reference_files(
    vault: Path,
    selected_run_ids: set[str],
    *,
    all_runs: bool,
    apply: bool,
    state: _BackfillState,
) -> list[dict[str, Any]]:
    if not apply:
        return []
    updates: list[dict[str, Any]] = []
    summary_repair_roots = set(state.touched_runs)
    summary_repair_roots.update(
        _summary_run_roots(
            vault,
            selected_run_ids,
            all_runs=all_runs,
        )
    )
    for owning_run in sorted(summary_repair_roots):
        replacements = _summary_replacements(vault, owning_run)
        if replacements:
            state.reference_needles_by_run.setdefault(owning_run, set()).update(replacements.keys())
        repaired = _repair_summary_references(
            vault,
            owning_run,
            apply=apply,
        )
        if not repaired:
            continue
        updates.extend({"owning_run": owning_run, **item} for item in repaired)
        state.touched_runs.add(owning_run)
        for item in repaired:
            if item.get("updated"):
                state.evidence_refs_by_run.setdefault(owning_run, set()).add(str(item["path"]))
    return updates


def _stale_same_run_references_before_delete(
    vault: Path,
    state: _BackfillState,
    *,
    apply: bool,
    delete_raw: bool,
) -> list[dict[str, str]]:
    if not (apply and delete_raw):
        return []
    references: list[dict[str, str]] = []
    for owning_run, backfilled_paths in sorted(state.reference_needles_by_run.items()):
        references.extend(_same_run_raw_references(vault, owning_run, backfilled_paths))
    return references


def _closable_promoted_runs(
    vault: Path,
    state: _BackfillState,
    before_reasons: Mapping[str, str],
    *,
    apply: bool,
    close_promoted_unreferenced: bool,
) -> tuple[list[str], list[str]]:
    if not (apply and close_promoted_unreferenced):
        return [], []
    closable_run_ids: list[str] = []
    closable_owning_runs: list[str] = []
    for owning_run, backfilled_paths in sorted(state.backfilled_raw_by_run.items()):
        if not _is_promoted_finalized(vault, owning_run):
            continue
        all_raw_paths = _all_nonempty_raw_logs_for_run(vault, owning_run)
        if all_raw_paths != backfilled_paths:
            continue
        references = _same_run_raw_references(vault, owning_run, all_raw_paths)
        if references:
            continue
        reasons = {before_reasons.get(path, "") for path in all_raw_paths}
        if reasons == {"run is not archived or closed by rework-closures evidence"}:
            closable_run_ids.append(_run_id_from_owning_run(owning_run))
            closable_owning_runs.append(owning_run)
    return closable_run_ids, closable_owning_runs


def _closure_evidence_refs(
    state: _BackfillState,
    closable_owning_runs: list[str],
) -> list[str]:
    return sorted(
        {
            evidence_ref
            for owning_run in closable_owning_runs
            for evidence_ref in state.evidence_refs_by_run.get(owning_run, set())
        }
    )


def _refresh_run_fingerprints(
    vault: Path,
    owning_runs: Iterable[str],
    *,
    context: RuntimeContext,
) -> list[str]:
    return [
        write_run_artifact_fingerprint(
            vault,
            _run_id_from_owning_run(owning_run),
            context=context,
            run_root_rel=owning_run,
        )
        for owning_run in sorted(set(owning_runs))
    ]


def _delete_raw_backfill_artifacts(
    vault: Path,
    state: _BackfillState,
    after_retention: dict[str, Any],
    stale_same_run_references: list[dict[str, str]],
    *,
    apply: bool,
    delete_raw: bool,
    context: RuntimeContext,
) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any]]:
    delete_records = (
        _raw_delete_records(after_retention, state.touched_raw_paths)
        if apply and delete_raw and not stale_same_run_references
        else []
    )
    deleted_raw_paths = _delete_paths(vault, delete_records, apply=apply)
    if not (apply and deleted_raw_paths):
        return delete_records, deleted_raw_paths, [], after_retention
    deleted_runs = {_owning_run_path(vault, rel_path) for rel_path in deleted_raw_paths}
    fingerprints = _refresh_run_fingerprints(vault, deleted_runs, context=context)
    return delete_records, deleted_raw_paths, fingerprints, build_retention_report(vault)


def _backfill_summary(
    *,
    groups: list[LogGroup],
    state: _BackfillState,
    fingerprints: list[str],
    summary_reference_updates: list[dict[str, Any]],
    closure: Mapping[str, Any],
    delete_records: list[dict[str, Any]],
    deleted_raw_paths: list[str],
    stale_same_run_references: list[dict[str, str]],
) -> dict[str, int]:
    return {
        "candidate_group_count": len(groups),
        "eligible_group_count": sum(
            1 for record in state.records if record["status"] in {"eligible", "applied"}
        ),
        "applied_group_count": sum(1 for record in state.records if record["status"] == "applied"),
        "summary_path_count": len(state.summary_paths),
        "fingerprint_refresh_count": len(fingerprints),
        "reference_repair_count": sum(1 for item in summary_reference_updates if item.get("updated")),
        "closed_run_count": len(closure.get("closed_run_ids", [])),
        "raw_delete_candidate_count": len(delete_records),
        "deleted_raw_count": len(deleted_raw_paths),
        "stale_same_run_reference_count": len(stale_same_run_references),
    }


def build_report(
    vault: Path,
    *,
    apply: bool = False,
    run_ids: set[str] | None = None,
    all_runs: bool = False,
    include_run_commands: bool = False,
    close_promoted_unreferenced: bool = False,
    delete_raw: bool = False,
    operator_confirmation: str = "",
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    if apply and not (all_runs or run_ids):
        raise ValueError("--apply requires --all or at least one --run-id")
    if delete_raw and operator_confirmation != DELETE_CONFIRMATION:
        raise ValueError(f"--delete-raw requires --operator-confirmation {DELETE_CONFIRMATION}")
    resolved_vault = vault.resolve()
    runtime_context = context or _context()
    generated_at = runtime_context.isoformat_z()
    selected_run_ids = run_ids or set()
    groups = _selected_groups(resolved_vault, selected_run_ids, all_runs=all_runs)

    before_retention = build_retention_report(resolved_vault)
    before_reasons = _raw_retention_reason_by_path(before_retention)
    state = _collect_backfill_records(
        resolved_vault,
        groups,
        before_reasons,
        include_run_commands=include_run_commands,
        apply=apply,
        context=runtime_context,
    )
    summary_reference_updates = _repair_existing_summary_reference_files(
        resolved_vault,
        selected_run_ids,
        all_runs=all_runs,
        apply=apply,
        state=state,
    )
    stale_same_run_references = _stale_same_run_references_before_delete(
        resolved_vault,
        state,
        apply=apply,
        delete_raw=delete_raw,
    )
    closable_run_ids, closable_owning_runs = _closable_promoted_runs(
        resolved_vault,
        state,
        before_reasons,
        apply=apply,
        close_promoted_unreferenced=close_promoted_unreferenced,
    )
    closure_evidence_refs = _closure_evidence_refs(state, closable_owning_runs)

    closure = (
        _append_rework_closure(
            resolved_vault,
            closable_run_ids,
            evidence_refs=closure_evidence_refs,
            generated_at=generated_at,
            apply=apply,
        )
        if apply and close_promoted_unreferenced
        else {"status": "not_requested", "closed_run_ids": []}
    )

    fingerprints = (
        _refresh_run_fingerprints(resolved_vault, state.touched_runs, context=runtime_context)
        if apply
        else []
    )

    after_retention = build_retention_report(resolved_vault)
    delete_records, deleted_raw_paths, delete_fingerprints, after_retention = (
        _delete_raw_backfill_artifacts(
            resolved_vault,
            state,
            after_retention,
            stale_same_run_references,
            apply=apply,
            delete_raw=delete_raw,
            context=runtime_context,
        )
    )
    fingerprints.extend(delete_fingerprints)

    status = "fail" if stale_same_run_references else "pass"
    return {
        "$schema": COMMAND_LOG_SUMMARY_BACKFILL_SCHEMA_PATH,
        "artifact_kind": "command_log_summary_backfill",
        "schema_version": 1,
        "generated_at": generated_at,
        "producer": PRODUCER,
        "apply": apply,
        "include_run_commands": include_run_commands,
        "close_promoted_unreferenced": close_promoted_unreferenced,
        "delete_raw": delete_raw,
        "status": status,
        "summary": _backfill_summary(
            groups=groups,
            state=state,
            fingerprints=fingerprints,
            summary_reference_updates=summary_reference_updates,
            closure=closure,
            delete_records=delete_records,
            deleted_raw_paths=deleted_raw_paths,
            stale_same_run_references=stale_same_run_references,
        ),
        "records": state.records,
        "closure": closure,
        "fingerprints": sorted(set(fingerprints)),
        "deleted_raw_paths": deleted_raw_paths,
        "stale_same_run_references": stale_same_run_references,
        "retention_after": {
            "status": after_retention.get("status", ""),
            "summary": after_retention.get("summary", {}),
        },
    }


def write_report(vault: Path, report: Mapping[str, Any], out_path: str) -> Path:
    destination = resolve_repo_output_path(vault, out_path, default_relative_path=DEFAULT_OUT)
    schema = load_schema_with_vault_override(vault, COMMAND_LOG_SUMMARY_BACKFILL_SCHEMA_PATH)
    write_schema_validated_json(
        destination,
        report,
        schema,
        context=f"schema validation failed for {display_path(vault, destination)}",
        trailing_newline=True,
    )
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill command-log-summary and capped traces for legacy run logs."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--include-run-commands", action="store_true")
    parser.add_argument("--close-promoted-unreferenced", action="store_true")
    parser.add_argument("--delete-raw", action="store_true")
    parser.add_argument("--operator-confirmation", default="")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        Path(args.vault),
        apply=args.apply,
        run_ids={str(run_id).strip() for run_id in args.run_id if str(run_id).strip()},
        all_runs=args.all,
        include_run_commands=args.include_run_commands,
        close_promoted_unreferenced=args.close_promoted_unreferenced,
        delete_raw=args.delete_raw,
        operator_confirmation=args.operator_confirmation,
    )
    path = write_report(Path(args.vault).resolve(), report, args.out)
    print(display_path(Path(args.vault).resolve(), path))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
