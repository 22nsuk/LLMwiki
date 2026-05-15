from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .policy_runtime import report_path


@dataclass(frozen=True)
class _FunctionBudgetProfile:
    name: str
    include_prefixes: tuple[str, ...]
    lines: int
    params: int
    branches: int


@dataclass(frozen=True)
class _FunctionMetrics:
    symbol: str
    line: int
    lines: int
    params: int
    branches: int


def _parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = node.args
    explicit_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    total = len(explicit_args)
    if args.vararg is not None:
        total += 1
    if args.kwarg is not None:
        total += 1
    if explicit_args and explicit_args[0].arg in {"self", "cls"}:
        total -= 1
    return total


class _FunctionMetricsVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.metrics: list[_FunctionMetrics] = []
        self._scope_stack: list[str] = []
        self._function_stack: list[dict[str, int | str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope_stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        symbol_parts = [*self._scope_stack, node.name]
        line = int(getattr(node, "lineno", 1) or 1)
        decorator_lines = [
            int(getattr(decorator, "lineno", line) or line)
            for decorator in getattr(node, "decorator_list", [])
        ]
        start_line = min([line, *decorator_lines])
        end_line = int(getattr(node, "end_lineno", line) or line)
        lines = max(1, end_line - start_line + 1)
        frame: dict[str, int | str] = {
            "symbol": ".".join(symbol_parts),
            "line": start_line,
            "lines": lines,
            "params": _parameter_count(node),
            "branches": 0,
        }

        self._function_stack.append(frame)
        self._scope_stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self._scope_stack.pop()
        completed = self._function_stack.pop()
        self.metrics.append(
            _FunctionMetrics(
                symbol=str(completed["symbol"]),
                line=int(completed["line"]),
                lines=int(completed["lines"]),
                params=int(completed["params"]),
                branches=int(completed["branches"]),
            )
        )

    def _increment_branch(self) -> None:
        if not self._function_stack:
            return
        self._function_stack[-1]["branches"] = int(self._function_stack[-1]["branches"]) + 1

    def visit_If(self, node: ast.If) -> None:
        self._increment_branch()
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._increment_branch()
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._increment_branch()
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._increment_branch()
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._increment_branch()
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._increment_branch()
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._increment_branch()
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self._increment_branch()
        self.generic_visit(node)


def _parse_profiles(config: dict) -> list[_FunctionBudgetProfile]:
    profiles: list[_FunctionBudgetProfile] = []
    for name, profile in config["profiles"].items():
        include_prefixes = tuple(str(prefix) for prefix in profile["include_prefixes"])
        profiles.append(
            _FunctionBudgetProfile(
                name=str(name),
                include_prefixes=include_prefixes,
                lines=int(profile["lines"]),
                params=int(profile["params"]),
                branches=int(profile["branches"]),
            )
        )
    return profiles


def _python_files_for_profile(vault: Path, profile: _FunctionBudgetProfile) -> list[tuple[str, Path]]:
    files: dict[str, Path] = {}
    for prefix in profile.include_prefixes:
        root = vault / prefix
        if root.is_file() and root.suffix == ".py":
            files[report_path(vault, root)] = root
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if not path.is_file():
                continue
            files[report_path(vault, path)] = path
    return sorted(files.items(), key=lambda item: item[0])


def _function_metrics(path: Path) -> list[_FunctionMetrics]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    visitor = _FunctionMetricsVisitor()
    visitor.visit(tree)
    return sorted(visitor.metrics, key=lambda item: (item.line, item.symbol))


def python_function_budget_candidates(vault: Path, config: dict) -> list[dict]:
    profiles = _parse_profiles(config)
    candidates: list[dict] = []

    for profile in profiles:
        for relative_path, path in _python_files_for_profile(vault, profile):
            for metrics in _function_metrics(path):
                triggered = []
                if metrics.lines > profile.lines:
                    triggered.append("function_lines")
                if metrics.params > profile.params:
                    triggered.append("parameter_count")
                if metrics.branches > profile.branches:
                    triggered.append("branch_node_count")
                if not triggered:
                    continue
                candidates.append(
                    {
                        "type": "python_function_budget_candidate",
                        "page": relative_path,
                        "symbol": metrics.symbol,
                        "line": metrics.line,
                        "profile": profile.name,
                        "triggered_budgets": triggered,
                        "value": {
                            "function_lines": metrics.lines,
                            "parameter_count": metrics.params,
                            "branch_node_count": metrics.branches,
                        },
                        "threshold": {
                            "function_lines": profile.lines,
                            "parameter_count": profile.params,
                            "branch_node_count": profile.branches,
                        },
                        "suggested_action": "review_for_function_split_or_interface_object",
                    }
                )

    return sorted(candidates, key=lambda item: (item["page"], int(item["line"]), item["symbol"]))
