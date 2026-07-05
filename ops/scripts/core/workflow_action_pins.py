from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.workflow_action_pin_catalog import WORKFLOW_ACTION_PIN_RULES
else:
    from .workflow_action_pin_catalog import WORKFLOW_ACTION_PIN_RULES

USES_LINE_RE = re.compile(
    r"^(?P<prefix>\s*(?:-\s*)?uses:\s*)(?P<quote>['\"]?)"
    r"(?P<uses>[^'\"\s#]+)(?P=quote)(?P<suffix>\s*(?:#.*)?)$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class PinRule:
    rule_id: str
    action: str
    sha: str
    version_comment: str
    paths: tuple[str, ...]

    @property
    def expected_uses(self) -> str:
        return f"{self.action}@{self.sha}"

    @property
    def expected_suffix(self) -> str:
        return f" # {self.version_comment}"


@dataclass(frozen=True)
class UsesOccurrence:
    rel_path: str
    line_number: int
    line: str
    prefix: str
    uses: str
    suffix: str

    @property
    def action(self) -> str:
        return self.uses.split("@", 1)[0]

    @property
    def is_local(self) -> bool:
        return self.uses.startswith("./")


def _pin_rules() -> tuple[PinRule, ...]:
    rules: list[PinRule] = []
    for raw in WORKFLOW_ACTION_PIN_RULES:
        paths = tuple(str(path).strip() for path in raw["paths"] if str(path).strip())
        rules.append(
            PinRule(
                rule_id=str(raw["id"]),
                action=str(raw["action"]),
                sha=str(raw["sha"]),
                version_comment=str(raw["version_comment"]),
                paths=paths,
            )
        )
    return tuple(rules)


def _workflow_files(vault: Path) -> tuple[Path, ...]:
    roots = (vault / ".github" / "workflows", vault / ".github" / "actions")
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.yml")))
        files.extend(sorted(root.rglob("*.yaml")))
    return tuple(sorted(set(files)))


def _line_body(raw_line: str) -> tuple[str, str]:
    if raw_line.endswith("\n"):
        body = raw_line[:-1]
        if body.endswith("\r"):
            return body[:-1], "\r\n"
        return body, "\n"
    return raw_line, ""


def _uses_occurrences(vault: Path) -> tuple[UsesOccurrence, ...]:
    occurrences: list[UsesOccurrence] = []
    for path in _workflow_files(vault):
        rel_path = path.relative_to(vault).as_posix()
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = USES_LINE_RE.match(raw_line)
            if match is None:
                continue
            occurrences.append(
                UsesOccurrence(
                    rel_path=rel_path,
                    line_number=line_number,
                    line=raw_line,
                    prefix=match.group("prefix"),
                    uses=match.group("uses"),
                    suffix=match.group("suffix"),
                )
            )
    return tuple(occurrences)


def _matching_rules(occurrence: UsesOccurrence, rules: tuple[PinRule, ...]) -> tuple[PinRule, ...]:
    return tuple(
        rule
        for rule in rules
        if rule.action == occurrence.action and occurrence.rel_path in rule.paths
    )


def _validate_rules(rules: tuple[PinRule, ...]) -> list[str]:
    issues: list[str] = []
    seen_ids: set[str] = set()
    for rule in rules:
        if rule.rule_id in seen_ids:
            issues.append(f"duplicate workflow action pin rule id: {rule.rule_id}")
        seen_ids.add(rule.rule_id)
        if not SHA_RE.fullmatch(rule.sha):
            issues.append(f"{rule.rule_id}: sha must be a 40 character lowercase hex digest")
        if not rule.paths:
            issues.append(f"{rule.rule_id}: paths must not be empty")
    return issues


def _rewrite_file(vault: Path, rel_path: str, updates: dict[int, str]) -> None:
    path = vault / rel_path
    new_lines: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(keepends=True), start=1):
        if line_number not in updates:
            new_lines.append(raw_line)
            continue
        _body, eol = _line_body(raw_line)
        new_lines.append(f"{updates[line_number]}{eol}")
    path.write_text("".join(new_lines), encoding="utf-8")


def validate_workflow_action_pins(vault: Path, *, write: bool = False) -> list[str]:
    resolved_vault = vault.resolve()
    rules = _pin_rules()
    issues = _validate_rules(rules)
    matched_rule_counts = {rule.rule_id: 0 for rule in rules}
    updates_by_path: dict[str, dict[int, str]] = {}

    for occurrence in _uses_occurrences(resolved_vault):
        if occurrence.is_local:
            continue
        matching_rules = _matching_rules(occurrence, rules)
        if not matching_rules:
            issues.append(
                f"{occurrence.rel_path}:{occurrence.line_number}: uncovered external action {occurrence.uses}"
            )
            continue
        if len(matching_rules) > 1:
            issues.append(
                f"{occurrence.rel_path}:{occurrence.line_number}: external action {occurrence.uses} "
                f"matches multiple pin rules: {', '.join(rule.rule_id for rule in matching_rules)}"
            )
            continue
        rule = matching_rules[0]
        matched_rule_counts[rule.rule_id] += 1
        expected_line = f"{occurrence.prefix}{rule.expected_uses}{rule.expected_suffix}"
        if occurrence.line == expected_line:
            continue
        if write:
            updates_by_path.setdefault(occurrence.rel_path, {})[occurrence.line_number] = expected_line
        else:
            issues.append(
                f"{occurrence.rel_path}:{occurrence.line_number}: expected {rule.expected_uses}{rule.expected_suffix}"
            )

    for rule in rules:
        if matched_rule_counts[rule.rule_id] == 0:
            issues.append(f"{rule.rule_id}: pin rule matched no workflow action uses")

    if write and updates_by_path and not issues:
        for rel_path, updates in updates_by_path.items():
            _rewrite_file(resolved_vault, rel_path, updates)
        return validate_workflow_action_pins(resolved_vault, write=False)

    return issues


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync GitHub workflow action pins from helper constants.")
    parser.add_argument("--vault", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail if workflow action pins are stale.")
    mode.add_argument("--write", action="store_true", help="Rewrite stale workflow action uses lines.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    issues = validate_workflow_action_pins(Path(args.vault), write=args.write)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
