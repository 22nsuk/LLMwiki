from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ops.scripts.core.makefile_runtime import load_makefile_text
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)

MANIFEST_PATH = "ops/policies/derived-surfaces.json"
SCHEMA_PATH = "ops/schemas/derived-surfaces.schema.json"
GLOB_CHARS = frozenset("*?[")
MAKE_RECIPE_RE = re.compile(r"\$\((?:MAKE|make)\)\s+(?P<args>[^\n;&|]+)")
MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.%/@-][A-Za-z0-9_.%/@ -]*):(?P<deps>[^\n#]*)")
MODULE_RE = re.compile(
    r"(?:^|\s)-m\s+(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b"
)
PYTHON_SCRIPT_RE = re.compile(
    r"(?P<script>[A-Za-z_][A-Za-z0-9_]*/[A-Za-z0-9_./-]+\.py)\b"
)
TARGET_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.%/@-]+$")
OPTION_OR_ASSIGNMENT_RE = re.compile(r"^(?:-|[A-Za-z_][A-Za-z0-9_]*=)")


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.as_posix()} must contain a JSON object")
    return payload


def load_manifest(vault: Path, manifest_path: str | Path = MANIFEST_PATH) -> dict[str, Any]:
    relative_path = Path(manifest_path)
    resolved_path = relative_path if relative_path.is_absolute() else vault / relative_path
    manifest = _read_json_object(resolved_path)
    schema = load_schema_with_vault_override(vault, SCHEMA_PATH)
    validate_or_raise(
        manifest,
        schema,
        context=f"invalid derived surfaces manifest in {resolved_path.as_posix()}",
    )
    _validate_manifest_invariants(manifest, vault=vault)
    return manifest


def _surface_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces = manifest.get("surfaces")
    if not isinstance(surfaces, list):
        return []
    return [surface for surface in surfaces if isinstance(surface, dict)]


def _sync_surfaces(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        surface
        for surface in _surface_entries(manifest)
        if bool(surface.get("include_in_sync_derived"))
    ]


def _validate_manifest_invariants(manifest: dict[str, Any], *, vault: Path) -> None:
    aggregate = manifest.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ValueError("derived surfaces manifest missing aggregate object")
    _validate_manifest_path(
        "generated_make_fragment.path",
        str(manifest["generated_make_fragment"]["path"]),
    )
    aggregate_targets = {
        str(aggregate.get("sync_target")),
        str(aggregate.get("check_target")),
        str(aggregate.get("internal_sync_target")),
        str(aggregate.get("internal_check_target")),
    }
    if len(aggregate_targets) != 4:
        raise ValueError("derived surfaces aggregate targets must be distinct")

    seen_surface_ids: set[str] = set()
    seen_surface_targets: set[str] = set()
    for surface in _surface_entries(manifest):
        surface_id = str(surface["surface_id"])
        sync_target = str(surface["sync_target"])
        check_target = str(surface["check_target"])
        if surface_id in seen_surface_ids:
            raise ValueError(f"duplicate derived surface id: {surface_id}")
        source_paths = [str(path) for path in surface.get("source_paths", [])]
        tracked_outputs = [str(path) for path in surface.get("tracked_outputs", [])]
        local_outputs = [str(path) for path in surface.get("local_outputs", [])]
        if not source_paths:
            raise ValueError(f"{surface_id} must declare at least one source_path")
        if not tracked_outputs and not local_outputs:
            raise ValueError(
                f"{surface_id} must declare at least one tracked_output or local_output"
            )
        for role, paths in (
            ("source_paths", source_paths),
            ("tracked_outputs", tracked_outputs),
            ("local_outputs", local_outputs),
        ):
            for path in paths:
                _validate_manifest_path(f"{surface_id}.{role}", path)
        if sync_target in aggregate_targets or check_target in aggregate_targets:
            raise ValueError(
                f"{surface_id} must not reuse sync-derived aggregate targets"
            )
        if sync_target == check_target:
            raise ValueError(f"{surface_id} sync/check targets must differ")
        for target in (sync_target, check_target):
            if target in seen_surface_targets:
                raise ValueError(f"duplicate derived surface target: {target}")
            seen_surface_targets.add(target)
        seen_surface_ids.add(surface_id)
    _validate_generator_module_ownership(manifest, vault=vault)


def _validate_manifest_path(context: str, path: str) -> None:
    normalized = path.replace("\\", "/")
    if not path:
        raise ValueError(f"{context} must not be empty")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError(f"{context} must be a relative repository path: {path}")
    if any(part == ".." for part in normalized.split("/")):
        raise ValueError(f"{context} must not contain parent traversal: {path}")


def _validate_generator_module_ownership(manifest: dict[str, Any], *, vault: Path) -> None:
    if not (vault / "Makefile").is_file():
        return
    try:
        makefile_text, _source_paths = load_makefile_text(vault)
    except FileNotFoundError:
        return
    make_targets = _make_target_metadata(makefile_text)
    generated_make_fragment = manifest["generated_make_fragment"]
    aggregate_generator_targets = [
        "derived-surfaces-sync",
        "derived-surfaces-sync-check",
    ]
    if not all(target in make_targets for target in aggregate_generator_targets):
        return
    _require_generator_module_for_targets(
        str(generated_make_fragment["generator_module"]),
        aggregate_generator_targets,
        make_targets,
        context="generated_make_fragment.generator_module",
    )
    for surface in _surface_entries(manifest):
        _require_generator_module_for_targets(
            str(surface["generator_module"]),
            [str(surface["sync_target"]), str(surface["check_target"])],
            make_targets,
            context=f"{surface['surface_id']}.generator_module",
        )


def _make_target_metadata(makefile_text: str) -> dict[str, dict[str, set[str]]]:
    targets: dict[str, dict[str, set[str]]] = {}
    current_targets: list[str] = []
    for raw_line in makefile_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith(" "):
            continue
        if line.startswith("\t"):
            modules = _recipe_modules(line)
            make_targets = _recipe_make_targets(line)
            for target in current_targets:
                target_metadata = targets.setdefault(
                    target,
                    {"modules": set(), "dependencies": set()},
                )
                target_metadata["modules"].update(modules)
                target_metadata["dependencies"].update(make_targets)
            continue
        match = MAKE_TARGET_RE.match(line)
        if match is None:
            current_targets = []
            continue
        current_targets = [item.strip() for item in match.group(1).split() if item.strip()]
        dependencies = _target_line_dependencies(match.group("deps"))
        for target in current_targets:
            target_metadata = targets.setdefault(
                target,
                {"modules": set(), "dependencies": set()},
            )
            target_metadata["dependencies"].update(dependencies)
    return targets


def _recipe_modules(line: str) -> set[str]:
    modules = {match.group("module") for match in MODULE_RE.finditer(line)}
    for match in PYTHON_SCRIPT_RE.finditer(line):
        modules.add(Path(match.group("script")).with_suffix("").as_posix().replace("/", "."))
    return modules


def _recipe_make_targets(line: str) -> set[str]:
    targets: set[str] = set()
    for make_match in MAKE_RECIPE_RE.finditer(line):
        target = _first_make_target(make_match.group("args").split())
        if target is not None:
            targets.add(target)
    return targets


def _first_make_target(tokens: list[str]) -> str | None:
    for token in tokens:
        cleaned = token.strip().strip('"').strip("'")
        if not cleaned or OPTION_OR_ASSIGNMENT_RE.match(cleaned):
            continue
        if TARGET_TOKEN_RE.match(cleaned):
            return cleaned
    return None


def _target_line_dependencies(raw_deps: str) -> set[str]:
    dependencies: set[str] = set()
    for token in raw_deps.split():
        cleaned = token.strip()
        if not cleaned or cleaned.startswith("$") or OPTION_OR_ASSIGNMENT_RE.match(cleaned):
            continue
        if TARGET_TOKEN_RE.match(cleaned):
            dependencies.add(cleaned)
    return dependencies


def _target_closure_modules(
    target: str,
    make_targets: dict[str, dict[str, set[str]]],
    *,
    seen: frozenset[str] = frozenset(),
) -> set[str]:
    if target in seen:
        return set()
    metadata = make_targets.get(target)
    if metadata is None:
        return set()
    modules = set(metadata["modules"])
    for dependency in metadata["dependencies"]:
        modules.update(
            _target_closure_modules(
                dependency,
                make_targets,
                seen=seen | {target},
            )
        )
    return modules


def _require_generator_module_for_targets(
    generator_module: str,
    targets: list[str],
    make_targets: dict[str, dict[str, set[str]]],
    *,
    context: str,
) -> None:
    existing_targets = [target for target in targets if target in make_targets]
    if not existing_targets:
        return
    for target in existing_targets:
        modules = _target_closure_modules(target, make_targets)
        if generator_module not in modules:
            raise ValueError(
                f"{context} {generator_module} is not owned by Make target {target}"
            )


def sync_target_lines(manifest: dict[str, Any]) -> list[str]:
    return [f"$(MAKE) {surface['sync_target']}" for surface in _sync_surfaces(manifest)]


def check_target_lines(manifest: dict[str, Any]) -> list[str]:
    return [f"$(MAKE) {surface['check_target']}" for surface in _sync_surfaces(manifest)]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _is_literal_output_path(path: str) -> bool:
    return bool(path) and not any(char in path for char in GLOB_CHARS)


def currentness_output_paths(manifest: dict[str, Any]) -> list[str]:
    paths = [str(manifest["generated_make_fragment"]["path"])]
    for surface in _sync_surfaces(manifest):
        for output_path in surface.get("tracked_outputs", []):
            path = str(output_path)
            if _is_literal_output_path(path):
                paths.append(path)
    return _dedupe_preserve_order(paths)


def currentness_path_patterns(manifest: dict[str, Any]) -> list[str]:
    paths = [str(manifest["generated_make_fragment"]["path"])]
    for surface in _sync_surfaces(manifest):
        paths.extend(str(path) for path in surface.get("source_paths", []))
        paths.extend(str(path) for path in surface.get("tracked_outputs", []))
    return _dedupe_preserve_order(paths)


def render_derived_surfaces_mk(manifest: dict[str, Any]) -> str:
    generated_make_fragment = manifest["generated_make_fragment"]
    aggregate = manifest["aggregate"]
    generator_module = str(generated_make_fragment["generator_module"])
    source_path = MANIFEST_PATH
    sync_target = str(aggregate["internal_sync_target"])
    check_target = str(aggregate["internal_check_target"])
    lines = [
        f"# Generated by: python -m {generator_module}",
        f"# Source of truth: {source_path}",
        "# Regenerate with: make derived-surfaces-sync",
        f".PHONY: {sync_target} {check_target}",
        "",
        f"{sync_target}:",
    ]
    lines.extend(f"\t{line}" for line in sync_target_lines(manifest))
    lines.extend(["", f"{check_target}:"])
    lines.extend(f"\t{line}" for line in check_target_lines(manifest))
    return "\n".join(lines).rstrip() + "\n"


def write_derived_surfaces_mk(
    vault: Path,
    *,
    manifest_path: str | Path = MANIFEST_PATH,
    out_path: str | Path | None = None,
) -> Path:
    manifest = load_manifest(vault, manifest_path)
    rendered = render_derived_surfaces_mk(manifest)
    output = _output_path(vault, manifest, out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return output


def derived_surfaces_mk_is_current(
    vault: Path,
    *,
    manifest_path: str | Path = MANIFEST_PATH,
    out_path: str | Path | None = None,
) -> bool:
    manifest = load_manifest(vault, manifest_path)
    rendered = render_derived_surfaces_mk(manifest)
    output = _output_path(vault, manifest, out_path)
    current = output.read_text(encoding="utf-8") if output.is_file() else ""
    return current == rendered


def _output_path(
    vault: Path,
    manifest: dict[str, Any],
    out_path: str | Path | None,
) -> Path:
    raw_path = (
        Path(out_path)
        if out_path is not None
        else Path(str(manifest["generated_make_fragment"]["path"]))
    )
    return raw_path if raw_path.is_absolute() else vault / raw_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate mk/derived-surfaces.generated.mk from the derived surfaces manifest."
    )
    parser.add_argument("--vault", type=Path, default=Path())
    parser.add_argument("--manifest", type=Path, default=Path(MANIFEST_PATH))
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Generated Make fragment output path. Defaults to manifest.generated_make_fragment.path.",
    )
    parser.add_argument("--check", action="store_true", help="Fail if output would change.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = args.vault.resolve()
    if args.check:
        current = derived_surfaces_mk_is_current(
            vault,
            manifest_path=args.manifest,
            out_path=args.out,
        )
        print(f"derived_surfaces: {'unchanged' if current else 'would_update'}")
        return 0 if current else 1
    output = write_derived_surfaces_mk(
        vault,
        manifest_path=args.manifest,
        out_path=args.out,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
