from __future__ import annotations

import argparse
from pathlib import Path

from ops.scripts.test.test_lane_registry_runtime import (
    load_registry,
    pytest_marker_docs,
)

PYTEST_MARKERS_START = "# >>> pytest-marker-registry >>>"
PYTEST_MARKERS_END = "# <<< pytest-marker-registry <<<"


def render_pytest_marker_block(registry: dict[str, object]) -> str:
    lines = [PYTEST_MARKERS_START, "markers ="]
    for marker, semantics in pytest_marker_docs(registry).items():
        lines.append(f"    {marker}: {semantics}")
    lines.append(PYTEST_MARKERS_END)
    return "\n".join(lines)


def _markers_option_bounds(lines: list[str]) -> tuple[int, int]:
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("markers") and line.partition("=")[0].strip() == "markers"
        ),
        -1,
    )
    if start < 0:
        raise ValueError("pytest.ini is missing a markers option")
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line and not line[0].isspace():
            break
        end += 1
    return start, end


def synced_pytest_ini_text(original: str, registry: dict[str, object]) -> str:
    lines = original.splitlines()
    rendered = render_pytest_marker_block(registry).splitlines()
    if PYTEST_MARKERS_START in lines and PYTEST_MARKERS_END in lines:
        start = lines.index(PYTEST_MARKERS_START)
        end = lines.index(PYTEST_MARKERS_END, start) + 1
    else:
        start, end = _markers_option_bounds(lines)
    return "\n".join([*lines[:start], *rendered, *lines[end:]]).rstrip() + "\n"


def sync_pytest_ini(vault: Path, pytest_ini: Path) -> bool:
    registry = load_registry(vault)
    original = pytest_ini.read_text(encoding="utf-8")
    updated = synced_pytest_ini_text(original, registry)
    if updated == original:
        return False
    pytest_ini.write_text(updated, encoding="utf-8")
    return True


def pytest_ini_is_synced(vault: Path, pytest_ini: Path) -> bool:
    registry = load_registry(vault)
    original = pytest_ini.read_text(encoding="utf-8")
    return synced_pytest_ini_text(original, registry) == original


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the pytest.ini marker registry from ops/test-lane-registry.json."
    )
    parser.add_argument("--vault", type=Path, default=Path())
    parser.add_argument("--pytest-ini", type=Path, default=Path("pytest.ini"))
    parser.add_argument("--check", action="store_true", help="Fail if pytest.ini would change.")
    args = parser.parse_args()

    vault = args.vault.resolve()
    pytest_ini = (vault / args.pytest_ini).resolve()
    if args.check:
        synced = pytest_ini_is_synced(vault, pytest_ini)
        print(f"generate_pytest_ini_markers: {'unchanged' if synced else 'would_update'}")
        return 0 if synced else 1
    changed = sync_pytest_ini(vault, pytest_ini)
    print(f"generate_pytest_ini_markers: {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
