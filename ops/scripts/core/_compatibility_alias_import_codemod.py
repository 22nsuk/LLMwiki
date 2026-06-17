from __future__ import annotations

import argparse
import ast
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .compatibility_alias_deprecation import build_report
from .output_runtime import display_path
from .runtime_context import RuntimeContext

SUPPORTED_USAGE_KINDS = {"from_import", "from_package_import", "import"}
SOURCE_PATHS_ASSIGNMENT_RE = re.compile(r"(?<![A-Za-z0-9_])source_paths\s*=")


def _normalized_prefixes(prefixes: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(prefix.strip().lstrip("./") for prefix in prefixes if prefix.strip())
    if not normalized:
        raise ValueError("at least one --prefix is required")
    return normalized


def _selected_path(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def _python_files_under_prefixes(vault: Path, prefixes: Sequence[str]) -> list[Path]:
    files: dict[str, Path] = {}
    for prefix in prefixes:
        candidate = vault / prefix
        if candidate.is_file() and candidate.suffix == ".py":
            files[candidate.relative_to(vault).as_posix()] = candidate
            continue
        if candidate.is_dir():
            for path in sorted(candidate.rglob("*.py")):
                files[path.relative_to(vault).as_posix()] = path
    return [files[key] for key in sorted(files)]


def _source_path_replacements(inventory: dict[str, Any]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for item in inventory.get("aliases", []):
        if not isinstance(item, dict) or item.get("alias_type") != "flat_import_reexport":
            continue
        alias_name = str(item.get("name", ""))
        stem = alias_name.rsplit(".", maxsplit=1)[-1]
        canonical_path = str(item.get("path", ""))
        if stem and canonical_path:
            flat_path = f"ops/scripts/{stem}.py"
            if flat_path != canonical_path:
                replacements[flat_path] = canonical_path
    return replacements


def _replace_known_source_paths(line: str, replacements: dict[str, str]) -> tuple[str, int]:
    new_line = line
    changed_count = 0
    for old_path, new_path in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        occurrences = new_line.count(old_path)
        if occurrences:
            new_line = new_line.replace(old_path, new_path)
            changed_count += occurrences
    return new_line, changed_count


def _bracket_depth(text: str) -> int:
    return sum(text.count(opening) for opening in "([{") - sum(
        text.count(closing) for closing in ")]}"
    )


def _rewrite_source_path_metadata(
    text: str,
    replacements: dict[str, str],
) -> tuple[str, int]:
    if not replacements:
        return text, 0

    lines = text.splitlines(keepends=True)
    rewritten_lines: list[str] = []
    changed_count = 0
    in_source_paths = False
    source_paths_depth = 0

    for line in lines:
        assignment_match = SOURCE_PATHS_ASSIGNMENT_RE.search(line)
        should_rewrite = in_source_paths or assignment_match is not None
        if should_rewrite:
            line, line_change_count = _replace_known_source_paths(line, replacements)
            changed_count += line_change_count

        if assignment_match is not None and not in_source_paths:
            source_paths_depth = _bracket_depth(line[assignment_match.end():])
            in_source_paths = source_paths_depth > 0
        elif in_source_paths:
            source_paths_depth += _bracket_depth(line)
            in_source_paths = source_paths_depth > 0

        rewritten_lines.append(line)

    return "".join(rewritten_lines), changed_count


def _canonical_from_import_line(replacement: str, imported_name: str, asname: str | None) -> str:
    parent, module_name = replacement.rsplit(".", maxsplit=1)
    alias_suffix = f" as {asname}" if asname else ""
    return f"from {parent} import {module_name}{alias_suffix}\n"


def _rewrite_import_alias_line(
    line: str,
    *,
    alias: str,
    replacement: str,
) -> str | None:
    if f"import {alias} as " in line or f", {alias} as " in line:
        return line.replace(alias, replacement, 1)
    if line.strip() == f"import {alias}":
        return None
    return line.replace(alias, replacement, 1) if alias in line else None


def _rewrite_direct_import_callers(
    lines: list[str],
    callers: Sequence[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    changed_count = 0
    missed_rewrites: list[dict[str, Any]] = []
    for item in sorted(callers, key=lambda value: int(value.get("line", 0) or 0)):
        line_no = int(item.get("line", 0) or 0)
        if line_no < 1 or line_no > len(lines):
            missed_rewrites.append(item)
            continue
        alias = str(item.get("alias", ""))
        replacement = str(item.get("preferred_replacement", ""))
        usage_kind = str(item.get("usage_kind", ""))
        original_line = lines[line_no - 1]
        if usage_kind == "from_import":
            old_token = f"from {alias} import"
            new_token = f"from {replacement} import"
            if old_token not in original_line:
                missed_rewrites.append(item)
                continue
            lines[line_no - 1] = original_line.replace(old_token, new_token)
        elif usage_kind == "import":
            rewritten_line = _rewrite_import_alias_line(
                original_line,
                alias=alias,
                replacement=replacement,
            )
            if rewritten_line is None or rewritten_line == original_line:
                missed_rewrites.append(item)
                continue
            lines[line_no - 1] = rewritten_line
        else:
            missed_rewrites.append(item)
            continue
        changed_count += 1
    return changed_count, missed_rewrites


def _rewrite_from_package_import_callers(
    lines: list[str],
    callers: Sequence[dict[str, Any]],
    *,
    filename: str,
) -> tuple[int, list[dict[str, Any]]]:
    if not callers:
        return 0, []

    source = "".join(lines)
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return 0, list(callers)

    callers_by_line_and_stem: dict[tuple[int, str], dict[str, Any]] = {}
    for item in callers:
        alias = str(item.get("alias", ""))
        callers_by_line_and_stem[
            (int(item.get("line", 0) or 0), alias.rsplit(".", maxsplit=1)[-1])
        ] = item

    replacement_spans: list[tuple[int, int, list[str]]] = []
    rewritten_keys: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "ops.scripts" or node.level != 0:
            continue
        end_lineno = getattr(node, "end_lineno", node.lineno)
        generated_lines: list[str] = []
        target_count = 0
        for imported_alias in node.names:
            key = (node.lineno, imported_alias.name)
            caller_item = callers_by_line_and_stem.get(key)
            if caller_item is None:
                alias_suffix = f" as {imported_alias.asname}" if imported_alias.asname else ""
                generated_lines.append(
                    f"from ops.scripts import {imported_alias.name}{alias_suffix}\n"
                )
                continue
            generated_lines.append(
                _canonical_from_import_line(
                    str(caller_item.get("preferred_replacement", "")),
                    imported_alias.name,
                    imported_alias.asname,
                )
            )
            rewritten_keys.add(key)
            target_count += 1
        if target_count:
            replacement_spans.append((node.lineno, end_lineno, generated_lines))

    for start, end, generated_lines in sorted(replacement_spans, reverse=True):
        lines[start - 1 : end] = generated_lines

    missed_rewrites = [
        item
        for item in callers
        if (
            int(item.get("line", 0) or 0),
            str(item.get("alias", "")).rsplit(".", maxsplit=1)[-1],
        )
        not in rewritten_keys
    ]
    return len(rewritten_keys), missed_rewrites


def rewrite_compatibility_alias_imports(
    vault: Path,
    *,
    prefixes: Sequence[str],
    write: bool = False,
    source_path_references: bool = False,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    selected_prefixes = _normalized_prefixes(prefixes)
    inventory = build_report(resolved_vault, context=context)
    selected_callers = [
        item
        for item in inventory.get("flat_import_actual_callers", [])
        if isinstance(item, dict)
        and _selected_path(str(item.get("path", "")), selected_prefixes)
    ]
    callers_by_path: dict[str, list[dict[str, Any]]] = {}
    unsupported_callers: list[dict[str, Any]] = []
    for item in selected_callers:
        usage_kind = str(item.get("usage_kind", ""))
        if usage_kind not in SUPPORTED_USAGE_KINDS:
            unsupported_callers.append(item)
            continue
        callers_by_path.setdefault(str(item.get("path", "")), []).append(item)

    missed_rewrites: list[dict[str, Any]] = []
    changed_files: list[dict[str, Any]] = []
    import_rewrite_count = 0
    for rel_path, callers in sorted(callers_by_path.items()):
        path = resolved_vault / rel_path
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        direct_callers = [
            item for item in callers if str(item.get("usage_kind", "")) in {"from_import", "import"}
        ]
        package_callers = [
            item for item in callers if str(item.get("usage_kind", "")) == "from_package_import"
        ]
        direct_changed_count, direct_misses = _rewrite_direct_import_callers(
            lines,
            direct_callers,
        )
        package_changed_count, package_misses = _rewrite_from_package_import_callers(
            lines,
            package_callers,
            filename=rel_path,
        )
        missed_rewrites.extend(direct_misses)
        missed_rewrites.extend(package_misses)
        changed_count = direct_changed_count + package_changed_count
        if changed_count:
            import_rewrite_count += changed_count
            changed_files.append({"path": rel_path, "import_rewrite_count": changed_count})
            if write:
                path.write_text("".join(lines), encoding="utf-8")

    source_path_files: list[dict[str, Any]] = []
    source_path_rewrite_count = 0
    if source_path_references:
        replacements = _source_path_replacements(inventory)
        for path in _python_files_under_prefixes(resolved_vault, selected_prefixes):
            rel_path = path.relative_to(resolved_vault).as_posix()
            text = path.read_text(encoding="utf-8")
            new_text, changed_count = _rewrite_source_path_metadata(text, replacements)
            if changed_count:
                source_path_rewrite_count += changed_count
                source_path_files.append(
                    {"path": rel_path, "source_path_rewrite_count": changed_count}
                )
                if write:
                    path.write_text(new_text, encoding="utf-8")

    status = "fail" if unsupported_callers or missed_rewrites else "pass"
    return {
        "artifact_kind": "compatibility_alias_import_codemod",
        "status": status,
        "mode": "write" if write else "dry_run",
        "prefixes": list(selected_prefixes),
        "selected_caller_count": len(selected_callers),
        "changed_file_count": len(changed_files),
        "import_rewrite_count": import_rewrite_count,
        "changed_files": changed_files,
        "source_path_reference_rewrite_count": source_path_rewrite_count,
        "source_path_reference_files": source_path_files,
        "unsupported_caller_count": len(unsupported_callers),
        "unsupported_callers": unsupported_callers,
        "missed_rewrite_count": len(missed_rewrites),
        "missed_rewrites": missed_rewrites,
        "summary": (
            f"mode={'write' if write else 'dry_run'}; "
            f"selected_caller_count={len(selected_callers)}; "
            f"import_rewrite_count={import_rewrite_count}; "
            f"source_path_reference_rewrite_count={source_path_rewrite_count}; "
            f"unsupported_caller_count={len(unsupported_callers)}; "
            f"missed_rewrite_count={len(missed_rewrites)}"
        ),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrite selected flat ops.scripts import callers to canonical subpackage imports."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--prefix", action="append", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--source-path-references", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = rewrite_compatibility_alias_imports(
        vault,
        prefixes=args.prefix,
        write=bool(args.write),
        source_path_references=bool(args.source_path_references),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["status"] != "pass":
        return 1
    if args.write:
        print(f"rewritten_under={display_path(vault, vault)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
