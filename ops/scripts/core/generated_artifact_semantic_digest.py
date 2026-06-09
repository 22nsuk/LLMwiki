from __future__ import annotations

import hashlib
import json
from pathlib import Path

SHA256_MISSING = "missing"
JSON_TOP_LEVEL_ENVELOPE_MODE = "json_without_top_level_envelope_fingerprints_or_clock_fields"
JSON_ARTIFACT_KIND_POINTER_MODE = (
    "json_without_top_level_envelope_fingerprints_or_clock_fields"
    "_and_artifact_kind_declared_clock_fields"
)
MARKDOWN_GENERATED_AT_MODE = "markdown_without_generated_at"

TOP_LEVEL_ENVELOPE_VOLATILE_KEYS = frozenset(
    {
        "generated_at",
        "source_revision",
        "source_tree_fingerprint",
        "input_fingerprints",
        "currentness",
        "producer_input_fingerprint",
    }
)
ARTIFACT_KIND_VOLATILE_JSON_POINTERS = {
    "artifact_freshness_report": (("artifact_records", "*", "generated_at"),),
}
ARTIFACT_FRESHNESS_SELF_REFERENCE_PATHS = frozenset(
    {
        "ops/reports/artifact-freshness-report.json",
        "ops/reports/generated-artifact-index.json",
        "ops/reports/release-closeout-finality-attestation.json",
        "ops/reports/release-closeout-fixed-point.json",
    }
)
ARTIFACT_FRESHNESS_DERIVED_TOP_LEVEL_KEYS = frozenset(
    {
        "summary",
        "top_debt",
        "top_debt_files",
        "debt_queues",
        "owner_surface",
        "phase_timings",
    }
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256_bytes(encoded)


def _path_matches(pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
    return len(pattern) == len(path) and all(
        pattern_token in ("*", path_token)
        for pattern_token, path_token in zip(pattern, path, strict=True)
    )


def _has_descendant_match(
    patterns: tuple[tuple[str, ...], ...],
    path: tuple[str, ...],
) -> bool:
    return any(
        len(pattern) > len(path)
        and all(
            pattern_token in ("*", path_token)
            for pattern_token, path_token in zip(pattern[: len(path)], path, strict=True)
        )
        for pattern in patterns
    )


def _strip_declared_json_pointer_noise(
    value: object,
    patterns: tuple[tuple[str, ...], ...],
    *,
    path: tuple[str, ...] = (),
) -> object:
    if not patterns:
        return value
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, child in sorted(value.items()):
            child_path = (*path, str(key))
            if any(_path_matches(pattern, child_path) for pattern in patterns):
                continue
            normalized[str(key)] = (
                _strip_declared_json_pointer_noise(child, patterns, path=child_path)
                if _has_descendant_match(patterns, child_path)
                else child
            )
        return normalized
    if isinstance(value, list):
        child_path = (*path, "*")
        return [
            _strip_declared_json_pointer_noise(child, patterns, path=child_path)
            if _has_descendant_match(patterns, child_path)
            else child
            for child in value
        ]
    return value


def _artifact_kind_json_pointer_patterns(value: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, dict):
        return ()
    artifact_kind = str(value.get("artifact_kind", "")).strip()
    return ARTIFACT_KIND_VOLATILE_JSON_POINTERS.get(artifact_kind, ())


def _strip_artifact_freshness_self_observation(value: dict[str, object]) -> dict[str, object]:
    normalized = {
        key: child
        for key, child in value.items()
        if key not in ARTIFACT_FRESHNESS_DERIVED_TOP_LEVEL_KEYS
    }
    records = normalized.get("artifact_records")
    if isinstance(records, list):
        normalized["artifact_records"] = [
            record
            for record in records
            if not (
                isinstance(record, dict)
                and str(record.get("path", "")).strip()
                in ARTIFACT_FRESHNESS_SELF_REFERENCE_PATHS
            )
        ]
    return normalized


def strip_report_semantic_noise(value: object) -> object:
    if not isinstance(value, dict):
        return value
    without_envelope = {
        str(key): child
        for key, child in sorted(value.items())
        if str(key) not in TOP_LEVEL_ENVELOPE_VOLATILE_KEYS
    }
    if str(value.get("artifact_kind", "")).strip() == "artifact_freshness_report":
        without_envelope = _strip_artifact_freshness_self_observation(without_envelope)
    return _strip_declared_json_pointer_noise(
        without_envelope,
        _artifact_kind_json_pointer_patterns(value),
    )


def semantic_file_digest(path: Path) -> tuple[str, str]:
    if not path.is_file():
        return "missing", SHA256_MISSING
    raw = path.read_bytes()
    if path.suffix == ".json":
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "raw_text_json_unparseable", sha256_bytes(raw)
        patterns = _artifact_kind_json_pointer_patterns(payload)
        semantic_mode = (
            JSON_ARTIFACT_KIND_POINTER_MODE
            if patterns
            else JSON_TOP_LEVEL_ENVELOPE_MODE
        )
        return semantic_mode, canonical_digest(strip_report_semantic_noise(payload))
    if path.suffix == ".md":
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return "raw_text_binary_or_non_utf8", sha256_bytes(raw)
        semantic_lines = [
            line
            for line in text.splitlines()
            if not line.startswith("- Generated at:")
        ]
        semantic_text = "\n".join(semantic_lines) + ("\n" if text.endswith("\n") else "")
        return MARKDOWN_GENERATED_AT_MODE, sha256_bytes(semantic_text.encode("utf-8"))
    return "raw_text", sha256_bytes(raw)


def semantic_digest_maps(vault: Path, paths: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    digest_map: dict[str, str] = {}
    mode_map: dict[str, str] = {}
    for rel_path in paths:
        mode, digest = semantic_file_digest(vault / rel_path)
        digest_map[rel_path] = digest
        mode_map[rel_path] = mode
    return digest_map, mode_map
