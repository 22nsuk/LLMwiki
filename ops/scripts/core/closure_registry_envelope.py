from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact_freshness_runtime import build_canonical_report_envelope
from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    read_json_object,
    resolve_schema_backed_report_output_path,
    write_schema_backed_report,
)
from .output_runtime import display_path
from .policy_runtime import load_policy
from .runtime_context import RuntimeContext

PRODUCER = "ops.scripts.closure_registry_envelope"
DEFAULT_DEFECT_ESCAPE_CLOSURES = "ops/reports/defect-escape-closures.json"
DEFAULT_REWORK_CLOSURES = "ops/reports/rework-closures.json"
DEFECT_ESCAPE_SCHEMA = "ops/schemas/defect-escape-closures.schema.json"
REWORK_SCHEMA = "ops/schemas/rework-closures.schema.json"
REGISTRY_ALL = "all"
REGISTRY_DEFECT_ESCAPE = "defect_escape"
REGISTRY_REWORK = "rework"
REGISTRY_CHOICES = (REGISTRY_ALL, REGISTRY_DEFECT_ESCAPE, REGISTRY_REWORK)


@dataclass(frozen=True)
class ClosureRegistrySpec:
    registry: str
    path: str
    schema_path: str
    artifact_kind: str


REGISTRY_SPECS = {
    REGISTRY_DEFECT_ESCAPE: ClosureRegistrySpec(
        registry=REGISTRY_DEFECT_ESCAPE,
        path=DEFAULT_DEFECT_ESCAPE_CLOSURES,
        schema_path=DEFECT_ESCAPE_SCHEMA,
        artifact_kind="defect_escape_closures",
    ),
    REGISTRY_REWORK: ClosureRegistrySpec(
        registry=REGISTRY_REWORK,
        path=DEFAULT_REWORK_CLOSURES,
        schema_path=REWORK_SCHEMA,
        artifact_kind="rework_closures",
    ),
}


def _normalized_json_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _closure_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    closures = payload.get("closures", [])
    if not isinstance(closures, list):
        raise ValueError("closure registry 'closures' must be a list")
    return [item for item in closures if isinstance(item, dict)]


def _status_is_closed(closure: dict[str, Any]) -> bool:
    return str(closure.get("closure_status", "")).strip() in {"closed", "superseded"}


def _closed_run_ids(closure: dict[str, Any]) -> list[str]:
    run_ids = closure.get("closed_run_ids", [])
    if not isinstance(run_ids, list):
        return []
    return [str(run_id).strip() for run_id in run_ids if str(run_id).strip()]


def _summary(spec: ClosureRegistrySpec, closures: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"closure_count": len(closures)}
    if spec.registry != REGISTRY_REWORK:
        return summary
    closed_run_ids = {
        run_id
        for closure in closures
        if _status_is_closed(closure)
        for run_id in _closed_run_ids(closure)
    }
    summary["closed_rework_count"] = len(closed_run_ids)
    return summary


def build_registry(
    vault: Path,
    spec: ClosureRegistrySpec,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    source_path = resolve_schema_backed_report_output_path(
        vault,
        spec.path,
        default_relative_path=spec.path,
    )
    if not source_path.is_file():
        raise FileNotFoundError(f"closure registry is missing: {display_path(vault, source_path)}")
    existing = read_json_object(source_path)
    closures = _closure_items(existing)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind=spec.artifact_kind,
            producer=PRODUCER,
            source_command=(
                "python -m ops.scripts.closure_registry_envelope "
                f"--vault . --registry {spec.registry}"
            ),
            resolved_policy_path=resolved_policy_path,
            schema_path=spec.schema_path,
            source_paths=["ops/scripts/closure_registry_envelope.py"],
            text_inputs={
                "closure_payload_digest": _normalized_json_digest(closures),
                "registry": spec.registry,
            },
        ),
        "summary": _summary(spec, closures),
        "closures": closures,
    }


def write_registry(vault: Path, spec: ClosureRegistrySpec, payload: dict[str, Any]) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=payload,
            schema_path=spec.schema_path,
            out_path=spec.path,
            default_relative_path=spec.path,
            context=f"closure registry schema validation failed for {spec.path}",
            trailing_newline=True,
        )
    )


def refresh_registries(
    vault: Path,
    *,
    registry: str = REGISTRY_ALL,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> list[Path]:
    selected_specs = list(REGISTRY_SPECS.values()) if registry == REGISTRY_ALL else [REGISTRY_SPECS[registry]]
    written: list[Path] = []
    for spec in selected_specs:
        payload = build_registry(vault, spec, policy_path=policy_path, context=context)
        written.append(write_registry(vault, spec, payload))
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh canonical envelopes on closure registry artifacts.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--registry", choices=REGISTRY_CHOICES, default=REGISTRY_ALL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    written = refresh_registries(
        vault,
        registry=args.registry,
        policy_path=args.policy_path,
    )
    for path in written:
        print(f"written_to={display_path(vault, path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
