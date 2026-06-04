from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_OUT = "tmp/generated-artifact-converge-summary.json"
DEFAULT_BEFORE_OUT = "tmp/generated-artifact-converge-summary.before.json"
SEMANTIC_VOLATILE_KEYS = {
    "generated_at",
    "source_revision",
    "source_tree_fingerprint",
    "input_fingerprints",
    "currentness",
    "producer_input_fingerprint",
}
TARGET_OUTPUT_PATHS = {
    "external-report-action-matrix": ("ops/reports/external-report-action-matrix.json",),
    "generated-artifact-index": (
        "ops/operator/artifact-relocation-audit.json",
        "ops/reports/defect-escape-closures.json",
        "ops/reports/rework-closures.json",
        "ops/reports/manual-mutate-defect-registry.json",
        "ops/reports/release-risk-taxonomy-matrix.json",
        "ops/reports/release-risk-taxonomy-matrix.md",
        "ops/reports/generated-artifact-index.json",
    ),
    "artifact-freshness": ("ops/reports/artifact-freshness-report.json",),
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return _sha256_bytes(encoded)


def _strip_semantic_noise(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _strip_semantic_noise(child)
            for key, child in sorted(value.items())
            if str(key) not in SEMANTIC_VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_strip_semantic_noise(child) for child in value]
    return value


def _semantic_text_snapshot(path: Path, raw: bytes) -> tuple[str, str]:
    if path.suffix != ".md":
        return "raw_text", _sha256_bytes(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "raw_text_binary_or_non_utf8", _sha256_bytes(raw)
    semantic_lines = [
        line
        for line in text.splitlines()
        if not line.startswith("- Generated at:")
    ]
    semantic_text = "\n".join(semantic_lines) + ("\n" if text.endswith("\n") else "")
    return "markdown_without_generated_at", _sha256_bytes(semantic_text.encode("utf-8"))


def _path_snapshot(vault: Path, rel_path: str) -> dict[str, Any]:
    path = vault / rel_path
    if not path.exists():
        return {
            "path": rel_path,
            "exists": False,
            "raw_sha256": "",
            "semantic_sha256": "",
            "semantic_mode": "missing",
        }
    raw = path.read_bytes()
    raw_sha256 = _sha256_bytes(raw)
    semantic_mode, semantic_sha256 = _semantic_text_snapshot(path, raw)
    if path.suffix == ".json":
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            semantic_mode = "raw_text_json_unparseable"
        else:
            semantic_mode = "json_without_envelope_fingerprints_or_clock_fields"
            semantic_sha256 = _canonical_digest(_strip_semantic_noise(payload))
    return {
        "path": rel_path,
        "exists": True,
        "raw_sha256": raw_sha256,
        "semantic_sha256": semantic_sha256,
        "semantic_mode": semantic_mode,
    }


def _target_digest(path_snapshots: list[dict[str, Any]], field: str) -> str:
    return _canonical_digest(
        [
            {
                "path": str(item["path"]),
                "exists": bool(item["exists"]),
                field: str(item[field]),
            }
            for item in path_snapshots
        ]
    )


def _target_snapshot(vault: Path, target: str, paths: tuple[str, ...]) -> dict[str, Any]:
    path_snapshots = [_path_snapshot(vault, rel_path) for rel_path in paths]
    return {
        "target": target,
        "paths": list(paths),
        "path_digests": path_snapshots,
        "raw_digest": _target_digest(path_snapshots, "raw_sha256"),
        "semantic_digest": _target_digest(path_snapshots, "semantic_sha256"),
    }


def _load_before(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    summaries = payload.get("target_summaries") if isinstance(payload, dict) else None
    if not isinstance(summaries, list):
        return {}
    return {
        str(item.get("target", "")): item
        for item in summaries
        if isinstance(item, dict) and str(item.get("target", "")).strip()
    }


def _comparison(after: dict[str, Any], before: dict[str, Any] | None) -> dict[str, Any]:
    before = before or {}
    before_path_digests = {
        str(item.get("path", "")): item
        for item in before.get("path_digests", [])
        if isinstance(item, dict)
    }
    semantic_changed_paths: list[str] = []
    raw_changed_paths: list[str] = []
    for item in after["path_digests"]:
        path = str(item["path"])
        before_item = before_path_digests.get(path, {})
        if str(before_item.get("semantic_sha256", "")) != str(item["semantic_sha256"]):
            semantic_changed_paths.append(path)
        if str(before_item.get("raw_sha256", "")) != str(item["raw_sha256"]):
            raw_changed_paths.append(path)
    semantic_changed = bool(semantic_changed_paths)
    raw_changed = bool(raw_changed_paths)
    return {
        "target": after["target"],
        "paths": after["paths"],
        "status": "changed" if semantic_changed else "noop",
        "semantic_changed": semantic_changed,
        "raw_changed": raw_changed,
        "change_classification": (
            "semantic_changed"
            if semantic_changed
            else "envelope_or_raw_only_changed"
            if raw_changed
            else "noop"
        ),
        "semantic_before_digest": str(before.get("semantic_digest", "")),
        "semantic_after_digest": after["semantic_digest"],
        "raw_before_digest": str(before.get("raw_digest", "")),
        "raw_after_digest": after["raw_digest"],
        "semantic_changed_paths": semantic_changed_paths,
        "raw_changed_paths": raw_changed_paths,
        "path_digests": after["path_digests"],
    }


def build_report(
    vault: Path,
    *,
    phase: str,
    before_path: str = DEFAULT_BEFORE_OUT,
) -> dict[str, Any]:
    snapshots = [
        _target_snapshot(vault, target, paths)
        for target, paths in TARGET_OUTPUT_PATHS.items()
    ]
    if phase == "before":
        target_summaries = [
            {
                **snapshot,
                "status": "snapshot",
                "semantic_before_digest": snapshot["semantic_digest"],
                "semantic_after_digest": snapshot["semantic_digest"],
                "raw_before_digest": snapshot["raw_digest"],
                "raw_after_digest": snapshot["raw_digest"],
                "semantic_changed": False,
                "raw_changed": False,
                "change_classification": "snapshot",
                "semantic_changed_paths": [],
                "raw_changed_paths": [],
            }
            for snapshot in snapshots
        ]
    else:
        before = _load_before(vault / before_path)
        target_summaries = [
            _comparison(snapshot, before.get(str(snapshot["target"])))
            for snapshot in snapshots
        ]
    return {
        "artifact_kind": "generated_artifact_converge_summary",
        "producer": "ops.scripts.generated_artifact_converge_summary",
        "phase": phase,
        "status": (
            "changed"
            if any(item["semantic_changed"] for item in target_summaries)
            else "noop"
            if phase == "after"
            else "snapshot"
        ),
        "summary_path_policy": "tmp_only_noncanonical_observability",
        "semantic_digest_mode": "json_without_envelope_fingerprints_or_clock_fields_and_markdown_generated_at",
        "target_summaries": target_summaries,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = vault / out_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def _display_path(vault: Path, path: Path) -> str:
    try:
        return path.relative_to(vault).as_posix()
    except ValueError:
        return path.as_posix()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize generated-artifact-converge changes.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--before", default=DEFAULT_BEFORE_OUT)
    parser.add_argument("--phase", choices=["before", "after"], required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, phase=args.phase, before_path=args.before)
    destination = write_report(vault, report, args.out)
    print(_display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
