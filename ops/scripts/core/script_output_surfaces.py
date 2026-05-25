from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any

from .artifact_freshness_runtime import build_canonical_report_envelope
from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from .output_runtime import display_path
from .policy_runtime import load_policy
from .runtime_context import RuntimeContext

DEFAULT_OUT = "ops/script-output-surfaces.json"
SCHEMA_PATH = "ops/schemas/script-output-surfaces.schema.json"
PRODUCER = "ops.scripts.script_output_surfaces"
CLASSIFICATION_VALUES = (
    "repo_artifact",
    "user_export",
    "mixed",
    "no_output",
    "diagnostic_only",
)
USER_EXPORT_OUTPUT_OPTION_OVERRIDES = frozenset(
    {
        "ops/scripts/public/cbm_public_export.py",
        "ops/scripts/public/export_public_repo.py",
    }
)
DIAGNOSTIC_ONLY_PATHS = frozenset[str]()


def _script_files(vault: Path) -> list[Path]:
    return sorted(path for path in (vault / "ops" / "scripts").rglob("*.py") if path.name != "__init__.py")


def _script_tree(path: Path, rel_path: str) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)


def _referenced_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _has_main_block(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            ):
                return True
    return False


def _output_option_names(tree: ast.AST) -> list[str]:
    options: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        for arg in node.args:
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                continue
            if arg.value == "--out" or arg.value.endswith("-out"):
                options.add(arg.value)
    return sorted(options)


def _classification(
    rel_path: str,
    *,
    output_options: list[str],
    references_resolve_output_path: bool,
    references_resolve_repo_output_path: bool,
) -> tuple[str, str]:
    if references_resolve_output_path and references_resolve_repo_output_path:
        return "mixed", "uses both permissive user export and repo artifact resolvers"
    if references_resolve_output_path:
        return "user_export", "uses permissive user export resolver"
    if references_resolve_repo_output_path:
        return "repo_artifact", "uses repo artifact resolver"
    if output_options:
        if rel_path in USER_EXPORT_OUTPUT_OPTION_OVERRIDES:
            return "user_export", "output option is an intentional user export surface"
        return "repo_artifact", "output option writes a repo-scoped artifact without the permissive resolver"
    if rel_path in DIAGNOSTIC_ONLY_PATHS:
        return "diagnostic_only", "diagnostic command without a durable output artifact"
    return "no_output", "no configurable output path surface detected"


def build_registry(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    script_paths = [path.relative_to(resolved_vault).as_posix() for path in _script_files(resolved_vault)]
    surfaces: list[dict[str, Any]] = []
    for path in (resolved_vault / item for item in script_paths):
        rel_path = path.relative_to(resolved_vault).as_posix()
        tree = _script_tree(path, rel_path)
        names = _referenced_names(tree)
        output_options = _output_option_names(tree)
        references_resolve_output_path = "resolve_output_path" in names
        references_resolve_repo_output_path = "resolve_repo_output_path" in names
        classification, reason = _classification(
            rel_path,
            output_options=output_options,
            references_resolve_output_path=references_resolve_output_path,
            references_resolve_repo_output_path=references_resolve_repo_output_path,
        )
        surfaces.append(
            {
                "path": rel_path,
                "classification": classification,
                "output_options": output_options,
                "references_resolve_output_path": references_resolve_output_path,
                "references_resolve_repo_output_path": references_resolve_repo_output_path,
                "direct_fallback_eligible": _has_main_block(tree),
                "reason": reason,
            }
        )
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="script_output_surfaces",
            producer=PRODUCER,
            source_command="python -m ops.scripts.script_output_surfaces --vault . --out ops/script-output-surfaces.json",
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/core/script_output_surfaces.py"],
            path_group_inputs={"ops_scripts": script_paths},
            text_inputs={
                "classification_values": "\n".join(CLASSIFICATION_VALUES),
            },
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        "version": 1,
        "description": (
            "Generated inventory for ops/scripts output path surfaces. "
            "Tests compare this registry with the live AST-derived inventory."
        ),
        "generated_by": PRODUCER,
        "classification_values": list(CLASSIFICATION_VALUES),
        "surfaces": surfaces,
    }


def write_registry(vault: Path, registry: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=registry,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="script output surfaces schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--policy", default=None, help="Policy path relative to the vault.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output path for the generated registry.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    destination = write_registry(vault, build_registry(vault, policy_path=args.policy), args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
