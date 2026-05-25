from __future__ import annotations

import sys
from pathlib import Path

import pytest

BARE_PYTEST_GUIDANCE = (
    "plain `pytest` is not a supported entrypoint for this repository. "
    "Use `make test`, `make check`, `make public-check`, or `.venv/bin/python -m pytest ...` instead; "
    "the supported entrypoints preserve repo import semantics and the documented pytest plugin policy."
)


def _is_bare_pytest_invocation(argv0: str) -> bool:
    return Path(argv0).stem.lower() in {"pytest", "py.test"}


def pytest_configure(config: pytest.Config) -> None:
    del config
    if _is_bare_pytest_invocation(sys.argv[0]):
        raise pytest.UsageError(BARE_PYTEST_GUIDANCE)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    from ops.scripts.test_lane_registry_runtime import (
        allowed_marker_combinations,
        authoritative_markers,
        forbidden_marker_combinations,
        load_registry,
    )

    registry = load_registry(Path("."))
    markers = authoritative_markers(registry)
    allowed = allowed_marker_combinations(registry)
    forbidden = forbidden_marker_combinations(registry)
    for item in items:
        tier_marks = {mark.name for mark in item.iter_markers() if mark.name in markers}
        for marker in sorted(tier_marks):
            forbidden_hits = sorted(tier_marks & forbidden.get(marker, set()))
            if forbidden_hits:
                raise pytest.UsageError(
                    f"{item.nodeid} declares forbidden marker combination for {marker}: {forbidden_hits}"
                )
            unknown_overlap = sorted(
                other
                for other in tier_marks
                if other != marker
                and other not in allowed.get(marker, set())
                and marker not in allowed.get(other, set())
                and other not in forbidden.get(marker, set())
            )
            if unknown_overlap:
                raise pytest.UsageError(
                    f"{item.nodeid} declares unauthorized marker combination for {marker}: {unknown_overlap}"
                )
