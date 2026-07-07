from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest
from hypothesis import HealthCheck, settings

from ops.scripts.test.test_execution_command_runtime import PYTEST_OPTION_VALUE_FLAGS
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.report_contract_test_runtime import (
    ReportPayloadMap,
    load_generated_report_payload_map,
)
from tests.runtime_test_context import frozen_context as build_frozen_context

BARE_PYTEST_GUIDANCE = (
    "plain `pytest` is not a supported entrypoint for this repository. "
    "Use `make test`, `make test-all`, `make check`, `make public-check`, "
    "or a focused `.venv/bin/python -m pytest ...` selector instead; "
    "use `make test-execution-summary-full-current-or-refresh` for release-grade full-suite evidence."
)
SELECTORLESS_PYTEST_GUIDANCE = (
    "selectorless `.venv/bin/python -m pytest` is not a supported ad hoc entrypoint for this repository. "
    "Use `make test-all` for developer full regression, "
    "`make test-execution-summary-full-current-or-refresh` for release-grade full-suite evidence, "
    "or pass a focused pytest selector."
)
MAKE_PYTEST_ENTRYPOINT_ENV = "LLMWIKI_MAKE_PYTEST_ENTRYPOINT"
HYPOTHESIS_PROFILE = "llmwiki"
DEFAULT_HYPOTHESIS_MAX_EXAMPLES = 30
PYTEST_SCOPE_VALUE_FLAGS = {"-k", "-m", "--deselect", "--ignore", "--ignore-glob"}


def _is_bare_pytest_invocation(argv0: str) -> bool:
    return Path(argv0).stem.lower() in {"pytest", "py.test"}


def _is_python_module_pytest_invocation(argv0: str) -> bool:
    path = Path(argv0)
    return path.name == "__main__.py" and path.parent.name == "pytest"


def _is_broad_pytest_selector(arg: str) -> bool:
    normalized = arg.rstrip("/")
    return normalized in {".", "tests"}


def _argv_has_focused_pytest_scope(argv: list[str]) -> bool:
    skip_next = False
    for arg in argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg == "--":
            continue
        if arg in PYTEST_SCOPE_VALUE_FLAGS:
            return True
        if any(arg.startswith(f"{flag}=") for flag in PYTEST_SCOPE_VALUE_FLAGS if flag.startswith("--")):
            return True
        if arg in PYTEST_OPTION_VALUE_FLAGS:
            skip_next = True
            continue
        if any(arg.startswith(f"{flag}=") for flag in PYTEST_OPTION_VALUE_FLAGS if flag.startswith("--")):
            continue
        if arg.startswith("-"):
            continue
        if not _is_broad_pytest_selector(arg):
            return True
    return False


@pytest.fixture
def frozen_context():
    return build_frozen_context()


@pytest.fixture
def seeded_vault(tmp_path: Path) -> Path:
    seed_minimal_vault(tmp_path)
    return tmp_path


@pytest.fixture
def vault(seeded_vault: Path) -> Path:
    return seeded_vault


@pytest.fixture
def fresh_vault(tmp_path: Path) -> Iterator[Path]:
    """Yield an isolated seeded vault directory for one test function."""
    seed_minimal_vault(tmp_path)
    yield tmp_path


@pytest.fixture(scope="session")
def report_schema_sample_payload_factory() -> Callable[[], ReportPayloadMap]:
    return load_generated_report_payload_map


@pytest.fixture
def report_schema_sample_payloads(
    report_schema_sample_payload_factory: Callable[[], ReportPayloadMap],
) -> ReportPayloadMap:
    return report_schema_sample_payload_factory()


def pytest_configure(config: pytest.Config) -> None:
    del config
    if _is_bare_pytest_invocation(sys.argv[0]):
        raise pytest.UsageError(BARE_PYTEST_GUIDANCE)
    if (
        _is_python_module_pytest_invocation(sys.argv[0])
        and os.environ.get(MAKE_PYTEST_ENTRYPOINT_ENV) != "1"
        and not _argv_has_focused_pytest_scope(sys.argv)
    ):
        raise pytest.UsageError(SELECTORLESS_PYTEST_GUIDANCE)
    max_examples = int(
        os.environ.get("LLMWIKI_HYPOTHESIS_MAX_EXAMPLES", str(DEFAULT_HYPOTHESIS_MAX_EXAMPLES))
    )
    settings.register_profile(
        HYPOTHESIS_PROFILE,
        max_examples=max_examples,
        deadline=None,
        database=None,
        derandomize=True,
        suppress_health_check=(HealthCheck.function_scoped_fixture,),
    )
    settings.load_profile(HYPOTHESIS_PROFILE)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    from ops.scripts.test.test_lane_registry_runtime import (
        allowed_marker_combinations,
        authoritative_markers,
        forbidden_marker_combinations,
        load_registry,
    )

    registry = load_registry(Path())
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
