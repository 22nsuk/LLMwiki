from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

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
    paths: tuple[str, ...]
    group: str


@dataclass(frozen=True)
class UsesOccurrence:
    rel_path: str
    line_number: int
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
                group=str(raw["group"]),
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
        if not rule.paths:
            issues.append(f"{rule.rule_id}: paths must not be empty")
    return issues


def _yaml_uses(value: object) -> list[str]:
    if isinstance(value, dict):
        result = [str(value["uses"])] if "uses" in value else []
        for child in value.values():
            result.extend(_yaml_uses(child))
        return result
    if isinstance(value, list):
        return [item for child in value for item in _yaml_uses(child)]
    return []


def _validated_pins(vault: Path) -> tuple[dict[str, str], list[str]]:
    rules = _pin_rules()
    issues = _validate_rules(rules)
    pins: dict[str, str] = {}
    cohorts: dict[str, set[tuple[str, str]]] = {}
    occurrences = _uses_occurrences(vault)
    for path in _workflow_files(vault):
        relative = path.relative_to(vault).as_posix()
        try:
            uses = _yaml_uses(yaml.safe_load(path.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            issues.append(f"{relative}: invalid workflow YAML")
            continue
        parsed = [item.uses for item in occurrences if item.rel_path == relative]
        if sorted(uses) != sorted(parsed):
            issues.append(f"{relative}: uses entries must be standalone scalar lines")
    for occurrence in occurrences:
        if occurrence.is_local:
            continue
        location = f"{occurrence.rel_path}:{occurrence.line_number}"
        matching = _matching_rules(occurrence, rules)
        if len(matching) != 1:
            issues.append(f"{location}: external action must match one allowed action/path rule: {occurrence.uses}")
            continue
        rule = matching[0]
        sha = occurrence.uses.partition("@")[2]
        if not SHA_RE.fullmatch(sha):
            issues.append(f"{location}: action must use a 40 character lowercase SHA")
        version = occurrence.suffix.strip().removeprefix("#").strip()
        if not re.fullmatch(r"v[0-9]+(?:\.[0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", version):
            issues.append(f"{location}: action must have a version comment")
        cohorts.setdefault(rule.group, set()).add((sha, version))
        pins[rule.rule_id] = occurrence.uses
    for rule in rules:
        if rule.rule_id not in pins:
            issues.append(f"{rule.rule_id}: pin rule matched no workflow action uses")
    for group, values in cohorts.items():
        if len(values) != 1:
            issues.append(f"{group}: action SHA/version must agree across its workflow cohort")
    return pins, issues


def workflow_action_pins(vault: Path) -> dict[str, str]:
    pins, issues = _validated_pins(vault.resolve())
    if issues:
        raise ValueError("; ".join(issues))
    return pins


def validate_workflow_action_pins(vault: Path, *, write: bool = False) -> list[str]:
    # Retain the existing --write/Make entrypoint as a non-mutating validation
    # alias. Never choose a winner or overwrite a reviewed workflow update.
    return _validated_pins(vault.resolve())[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate workflow-owned GitHub Action pins and shared-version cohorts.")
    parser.add_argument("--vault", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate SHA pins, allowed paths, and version cohorts.")
    mode.add_argument("--write", action="store_true", help="Compatibility alias for --check; workflow pins are never rewritten.")
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
