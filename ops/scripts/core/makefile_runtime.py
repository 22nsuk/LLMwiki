from __future__ import annotations

import re
from pathlib import Path

INCLUDE_RE = re.compile(r"^include\s+(?P<paths>.+)$")
SCRIPT_MODULE_RE = re.compile(
    r"-m\s+(ops\.scripts\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\b"
)
VARIABLE_ASSIGNMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)\s*(?P<operator>\?=|:=|\+=|=)\s*(?P<value>.*)$"
)
VARIABLE_REFERENCE_RE = re.compile(
    r"\$\((?P<paren>[A-Za-z0-9_.-]+)\)|\$\{(?P<brace>[A-Za-z0-9_.-]+)\}"
)


def _include_tokens(line: str) -> list[str]:
    match = INCLUDE_RE.match(line.strip())
    if match is None:
        return []
    tokens: list[str] = []
    for token in match.group("paths").split():
        if not token or "$" in token or "*" in token:
            continue
        tokens.append(token)
    return tokens


def makefile_source_paths(vault: Path, root: str = "Makefile") -> list[str]:
    resolved_vault = vault.resolve()
    seen: set[str] = set()
    ordered: list[str] = []

    def visit(rel_path: str) -> None:
        normalized = Path(rel_path).as_posix()
        if normalized in seen:
            return
        path = resolved_vault / normalized
        if not path.is_file():
            return
        seen.add(normalized)
        ordered.append(normalized)
        for line in path.read_text(encoding="utf-8").splitlines():
            for include_path in _include_tokens(line):
                visit(include_path)

    visit(root)
    return ordered


def load_makefile_text(vault: Path, root: str = "Makefile") -> tuple[str, list[str]]:
    source_paths = makefile_source_paths(vault, root=root)
    resolved_vault = vault.resolve()
    chunks: list[str] = []
    for rel_path in source_paths:
        chunks.append(f"# source: {rel_path}")
        chunks.append((resolved_vault / rel_path).read_text(encoding="utf-8"))
    return "\n".join(chunks), source_paths


def _makefile_scan_paths(vault: Path) -> list[Path]:
    return [vault / "Makefile", *sorted((vault / "mk").glob("*.mk"))]


def _target_names(line: str) -> list[str]:
    target_text, separator, _tail = line.partition(":")
    if not separator:
        return []
    return [item.strip() for item in target_text.split() if item.strip()]


def _variable_name(match: re.Match[str]) -> str:
    return str(match.group("paren") or match.group("brace") or "")


def _without_shell_comment(text: str) -> str:
    comment_index = text.find("#")
    if comment_index < 0:
        return text
    before_comment = text[:comment_index]
    if (
        not before_comment.strip()
        or before_comment[-1].isspace()
        or before_comment[-1] == ";"
    ):
        return before_comment
    return text


def _modules_in_text(
    text: str,
    assignments: dict[str, list[str]],
    *,
    seen_variables: frozenset[str] = frozenset(),
) -> set[str]:
    text = _without_shell_comment(text)
    modules = set(SCRIPT_MODULE_RE.findall(text))
    for match in VARIABLE_REFERENCE_RE.finditer(text):
        variable = _variable_name(match)
        if not variable or variable in seen_variables:
            continue
        for value in assignments.get(variable, []):
            modules.update(
                _modules_in_text(
                    value,
                    assignments,
                    seen_variables=seen_variables | {variable},
                )
            )
    return modules


def _record_modules(
    modules_by_target: dict[str, set[str]],
    targets: list[str],
    recipe_text: str,
    assignments: dict[str, list[str]],
) -> None:
    if not targets:
        return
    for module in _modules_in_text(recipe_text, assignments):
        modules_by_target.setdefault(module, set()).update(targets)


def _read_makefile_lines(vault: Path) -> list[str]:
    lines: list[str] = []
    for path in _makefile_scan_paths(vault):
        if path.is_file():
            lines.extend(path.read_text(encoding="utf-8").splitlines())
    return lines


def _makefile_assignments(lines: list[str]) -> dict[str, list[str]]:
    assignments: dict[str, list[str]] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if line.startswith("\t"):
            continue
        assignment_match = VARIABLE_ASSIGNMENT_RE.match(line)
        if assignment_match is None:
            continue
        value = assignment_match.group("value")
        while value.rstrip().endswith("\\") and index < len(lines):
            value = value.rstrip()[:-1] + " " + lines[index].strip()
            index += 1
        variable = assignment_match.group("name")
        operator = assignment_match.group("operator")
        if operator == "+=":
            assignments.setdefault(variable, []).append(value)
        elif operator == "?=":
            assignments.setdefault(variable, [value])
        else:
            assignments[variable] = [value]
    return assignments


def makefile_script_module_targets(vault: Path) -> dict[str, list[str]]:
    lines = _read_makefile_lines(vault)
    assignments = _makefile_assignments(lines)
    modules: dict[str, set[str]] = {}
    current_targets: list[str] = []
    continuation_targets: list[str] = []

    for line in lines:
        if continuation_targets:
            recipe_text = line[1:] if line.startswith("\t") else line
            _record_modules(modules, continuation_targets, recipe_text, assignments)
            if not recipe_text.rstrip().endswith("\\"):
                continuation_targets = []
            continue

        if line.startswith("\t"):
            recipe_text = line[1:]
            _record_modules(modules, current_targets, recipe_text, assignments)
            continuation_targets = (
                list(current_targets) if recipe_text.rstrip().endswith("\\") else []
            )
            continue

        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith(("#", ".PHONY:"))
            or VARIABLE_ASSIGNMENT_RE.match(line) is not None
        ):
            current_targets = []
            continue

        if ":" in line:
            current_targets = _target_names(line)
            _prerequisites, separator, recipe_text = line.partition(";")
            if separator:
                _record_modules(modules, current_targets, recipe_text, assignments)
                continuation_targets = (
                    list(current_targets) if recipe_text.rstrip().endswith("\\") else []
                )
        else:
            current_targets = []

    return {
        module: sorted(target for target in targets if target)
        for module, targets in sorted(modules.items())
    }
