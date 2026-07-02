from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path

MAKEFILE = Path("Makefile")
REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MakeTargetContract:
    target: str
    phony: bool = False
    exact_recipe: tuple[str, ...] | None = None
    required_tokens: tuple[str, ...] = ()
    forbidden_tokens: tuple[str, ...] = ()


def _makefile_text() -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    for mk_file in sorted(REPO_ROOT.glob("mk/*.mk")):
        text += "\n" + mk_file.read_text(encoding="utf-8")
    return text


def _pytest_collect_nodeid_path_counts(stdout: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        stripped = line.strip()
        path, separator, count_text = stripped.rpartition(": ")
        if separator and path.endswith(".py") and count_text.isdigit():
            counts[path] = counts.get(path, 0) + int(count_text)
            continue
        path, separator, _node_id = stripped.partition("::")
        if not separator or not path.endswith(".py"):
            continue
        counts[path] = counts.get(path, 0) + 1
    return counts


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


def _phony_target_names(text: str) -> tuple[str, ...]:
    return tuple(_target_block(text, ".PHONY").replace(".PHONY:", " ").split())


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


def _assert_assignment_values(
    case: unittest.TestCase,
    text: str,
    assignments: tuple[tuple[str, str], ...],
) -> None:
    for variable, expected_value in assignments:
        with case.subTest(variable=variable):
            _assert_assignment_exists(case, text, variable, expected_value)


def _assert_phony_targets(
    case: unittest.TestCase,
    text: str,
    targets: tuple[str, ...],
) -> None:
    phony_targets = set(_phony_target_names(text))
    for target in targets:
        with case.subTest(target=target, surface="phony"):
            case.assertIn(target, phony_targets)


def _assert_recipe_contains_tokens(
    case: unittest.TestCase,
    text: str,
    target: str,
    required_tokens: tuple[str, ...],
) -> None:
    block = _target_block(text, target)
    missing = [token for token in required_tokens if token not in block]
    case.assertEqual(missing, [], f"{target} recipe missing required tokens")


def _assert_text_contains_tokens(
    case: unittest.TestCase,
    text: str,
    tokens: tuple[str, ...],
    *,
    surface: str = "text",
) -> None:
    for token in tokens:
        with case.subTest(surface=surface, token=token):
            case.assertIn(token, text)


def _assert_make_target_contract(
    case: unittest.TestCase,
    text: str,
    contract: MakeTargetContract,
) -> None:
    if contract.phony:
        _assert_phony_targets(case, text, (contract.target,))

    if contract.exact_recipe is not None:
        with case.subTest(target=contract.target, surface="recipe"):
            case.assertEqual(_recipe_lines(text, contract.target), list(contract.exact_recipe))

    block = _target_block(text, contract.target)
    for token in contract.required_tokens:
        with case.subTest(target=contract.target, required_token=token):
            case.assertIn(token, block)
    for token in contract.forbidden_tokens:
        with case.subTest(target=contract.target, forbidden_token=token):
            case.assertNotIn(token, block)


def _assert_make_target_contracts(
    case: unittest.TestCase,
    text: str,
    contracts: tuple[MakeTargetContract, ...],
) -> None:
    for contract in contracts:
        _assert_make_target_contract(case, text, contract)
