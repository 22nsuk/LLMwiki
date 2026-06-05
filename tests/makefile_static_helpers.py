from __future__ import annotations

import re
import unittest
from pathlib import Path

MAKEFILE = Path("Makefile")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _makefile_text() -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    for mk_file in sorted(REPO_ROOT.glob("mk/*.mk")):
        text += "\n" + mk_file.read_text(encoding="utf-8")
    return text


def _target_block(text: str, target: str) -> str:
    if target == ".PHONY":
        matches = list(
            re.finditer(
                rf"^{re.escape(target)}:(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
                text,
                flags=re.MULTILINE,
            )
        )
        if not matches:
            raise AssertionError(f"missing Makefile target: {target}")
        return "\n".join(m.group(0) for m in matches)
    match = re.search(
        rf"^{re.escape(target)}:(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
        text,
        flags=re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing Makefile target: {target}")
    return match.group(0)


def _recipe_lines(text: str, target: str) -> list[str]:
    block = _target_block(text, target)
    return [line.strip() for line in block.splitlines()[1:] if line.startswith("\t")]


def _target_dependencies(text: str, target: str) -> tuple[str, ...]:
    header = _target_block(text, target).splitlines()[0]
    _, _, raw_deps = header.partition(":")
    return tuple(raw_deps.split())


def _assert_target_depends_on(
    case: unittest.TestCase, text: str, target: str, dependency: str
) -> None:
    case.assertIn(dependency, _target_dependencies(text, target))


def _makefile_assignment_value(text: str, variable: str) -> str:
    prefix = f"{variable} ?="
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    raise AssertionError(f"missing Makefile assignment: {variable}")


def _assert_assignment_exists(
    case: unittest.TestCase,
    text: str,
    variable: str,
    expected_value: str | None = None,
) -> str:
    value = _makefile_assignment_value(text, variable)
    if expected_value is not None:
        case.assertEqual(value, expected_value)
    return value


def _assert_assignment_not_exists(
    case: unittest.TestCase, text: str, variable: str
) -> None:
    with case.assertRaises(AssertionError):
        _makefile_assignment_value(text, variable)


def _assert_recipe_contains_tokens(
    case: unittest.TestCase,
    text: str,
    target: str,
    required_tokens: tuple[str, ...],
) -> None:
    block = _target_block(text, target)
    missing = [token for token in required_tokens if token not in block]
    case.assertEqual(missing, [], f"{target} recipe missing required tokens")
