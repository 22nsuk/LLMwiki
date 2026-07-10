from __future__ import annotations

import hashlib
import json
from pathlib import Path

SHA256_MISSING = "missing"
CONTENT_BINDING_MODE = "content"
REVISION_BINDING_MODE = "revision"
RAW_BINDING_MODE = "raw"
BINDING_MODES = frozenset(
    {
        CONTENT_BINDING_MODE,
        REVISION_BINDING_MODE,
        RAW_BINDING_MODE,
    }
)
MARKDOWN_CONTENT_BINDING_MODE = "markdown_content_binding"

CONTENT_BINDING_VOLATILE_KEYS = frozenset({"generated_at", "source_revision"})
REVISION_BINDING_VOLATILE_KEYS = frozenset({"generated_at"})
ARTIFACT_KIND_VOLATILE_JSON_POINTERS = {
    "artifact_freshness_report": (("artifact_records", "*", "generated_at"),),
}


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


def _binding_volatile_keys(binding_mode: str) -> frozenset[str]:
    if binding_mode == CONTENT_BINDING_MODE:
        return CONTENT_BINDING_VOLATILE_KEYS
    if binding_mode == REVISION_BINDING_MODE:
        return REVISION_BINDING_VOLATILE_KEYS
    if binding_mode == RAW_BINDING_MODE:
        return frozenset()
    raise ValueError(f"unsupported artifact binding mode: {binding_mode}")


def _normalize_currentness_clock(value: object) -> object:
    if not isinstance(value, dict):
        return value
    return {
        str(key): child
        for key, child in sorted(value.items())
        if str(key) != "checked_at"
    }


def normalize_report_binding_payload(
    value: object,
    *,
    binding_mode: str = CONTENT_BINDING_MODE,
) -> object:
    if not isinstance(value, dict):
        return value
    volatile_keys = _binding_volatile_keys(binding_mode)
    without_envelope = {
        str(key): (
            _normalize_currentness_clock(child)
            if str(key) == "currentness"
            else child
        )
        for key, child in sorted(value.items())
        if str(key) not in volatile_keys
    }
    return _strip_declared_json_pointer_noise(
        without_envelope,
        _artifact_kind_json_pointer_patterns(value),
    )


def binding_payload_digest(value: object, *, binding_mode: str) -> str:
    if binding_mode == RAW_BINDING_MODE:
        raise ValueError("raw binding requires serialized bytes")
    return canonical_digest(
        normalize_report_binding_payload(value, binding_mode=binding_mode)
    )


def binding_file_digest(path: Path, *, binding_mode: str) -> tuple[str, str]:
    if binding_mode not in BINDING_MODES:
        raise ValueError(f"unsupported artifact binding mode: {binding_mode}")
    if not path.is_file():
        return "missing", SHA256_MISSING
    raw = path.read_bytes()
    if binding_mode == RAW_BINDING_MODE:
        return RAW_BINDING_MODE, sha256_bytes(raw)
    if path.suffix == ".json":
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "raw_text_json_unparseable", sha256_bytes(raw)
        patterns = _artifact_kind_json_pointer_patterns(payload)
        mode = f"json_{binding_mode}_binding"
        if patterns:
            mode += "_and_artifact_kind_declared_clock_fields"
        return mode, binding_payload_digest(payload, binding_mode=binding_mode)
    if path.suffix == ".md":
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return "raw_text_binary_or_non_utf8", sha256_bytes(raw)
        bound_lines = [
            line for line in text.splitlines() if not line.startswith("- Generated at:")
        ]
        bound_text = "\n".join(bound_lines) + ("\n" if text.endswith("\n") else "")
        return MARKDOWN_CONTENT_BINDING_MODE, sha256_bytes(
            bound_text.encode("utf-8")
        )
    return "raw_text", sha256_bytes(raw)
