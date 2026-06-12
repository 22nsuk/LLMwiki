from __future__ import annotations

import re
from pathlib import Path
from typing import Any

CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
LOCKED_REQUIREMENTS_EXPORT_PATH = "tmp/locked-requirements.ci.txt"
UV_LOCK_CHECK_COMMAND = "uv lock --check"
UV_CANONICAL_INDEX_URL = "https://pypi.org/simple"
CANONICAL_UV_LOCK_CHECK_COMMAND = (
    f'UV_DEFAULT_INDEX="{UV_CANONICAL_INDEX_URL}" '
    f'{UV_LOCK_CHECK_COMMAND} --default-index "{UV_CANONICAL_INDEX_URL}"'
)
MAKE_UV_LOCK_CHECK_COMMAND = "make uv-lock-check"

PIP_INSTALL_LINE_PATTERN = re.compile(r"python\s+-m\s+pip\s+install\b", flags=re.IGNORECASE)
REQUIREMENTS_DEV_INSTALL_PATTERN = re.compile(
    r"python\s+-m\s+pip\s+install\b[^\n#]*\s-r\s+requirements-dev\.txt(?:\s|$)",
    flags=re.IGNORECASE,
)
EDITABLE_INSTALL_PATTERN = re.compile(
    r"python\s+-m\s+pip\s+install\b[^\n#]*\s-e\s+\.(?:\s|$)",
    flags=re.IGNORECASE,
)
BUILD_PACKAGE_PATTERN = re.compile(
    r"python\s+-m\s+pip\s+install\b[^\n#]*\sbuild(?:\s|$)",
    flags=re.IGNORECASE,
)
LOCKED_REQUIREMENTS_INSTALL_PATTERN = re.compile(
    rf"python\s+-m\s+pip\s+install\b[^\n#]*\s-r\s+{re.escape(LOCKED_REQUIREMENTS_EXPORT_PATH)}(?:\s|$)",
    flags=re.IGNORECASE,
)
LOCAL_ACTION_USES_PATTERN = re.compile(
    r"^\s*(?:-\s*)?uses:\s*['\"]?(?P<path>\./\.github/actions/[A-Za-z0-9_.\-/]+)['\"]?(?:\s|$)",
    flags=re.MULTILINE,
)


def line_has_tokens(line: str, tokens: tuple[str, ...]) -> bool:
    normalized = line.strip()
    return all(token in normalized for token in tokens)


def line_enforces_canonical_uv_lock_check(line: str) -> bool:
    normalized = line.strip()
    if MAKE_UV_LOCK_CHECK_COMMAND in normalized:
        return True
    has_uv_check = line_has_tokens(normalized, ("uv lock", "--check"))
    has_canonical_index_flag = line_has_tokens(
        normalized,
        ("--default-index", UV_CANONICAL_INDEX_URL),
    )
    has_canonical_index_env = line_has_tokens(
        normalized,
        ("UV_DEFAULT_INDEX", UV_CANONICAL_INDEX_URL),
    )
    return has_uv_check and has_canonical_index_flag and has_canonical_index_env


def local_action_evidence_paths(workflow_content: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in LOCAL_ACTION_USES_PATTERN.finditer(workflow_content):
        uses_path = match.group("path")
        rel_path = uses_path[2:] if uses_path.startswith("./") else uses_path
        action_path = f"{rel_path.rstrip('/')}/action.yml"
        if action_path in seen:
            continue
        seen.add(action_path)
        paths.append(action_path)
    return paths


def ci_install_evidence_content(vault: Path, workflow_rel_path: str = CI_WORKFLOW_PATH) -> tuple[bool, str]:
    workflow_path = vault / workflow_rel_path
    if not workflow_path.exists():
        return False, ""

    workflow_content = workflow_path.read_text(encoding="utf-8")
    contents = [workflow_content]
    for rel_path in local_action_evidence_paths(workflow_content):
        path = vault / rel_path
        if path.exists():
            contents.append(path.read_text(encoding="utf-8"))
    return True, "\n".join(contents)


def collect_ci_install_contract(content: str) -> dict[str, Any]:
    command_lines = []
    lock_check_commands = []
    exports_frozen_uv_lock = False
    checks_uv_lock_freshness = False
    for line in content.splitlines():
        if line_enforces_canonical_uv_lock_check(line):
            checks_uv_lock_freshness = True
            lock_check_commands.append(line.strip())
        if line_has_tokens(line, ("uv export", "--frozen", LOCKED_REQUIREMENTS_EXPORT_PATH)):
            exports_frozen_uv_lock = True
        match = PIP_INSTALL_LINE_PATTERN.search(line)
        if match is None:
            continue
        command_lines.append(line[match.start() :].strip())

    installs_locked_requirements = bool(LOCKED_REQUIREMENTS_INSTALL_PATTERN.search(content))
    installs_requirements_dev = bool(REQUIREMENTS_DEV_INSTALL_PATTERN.search(content))
    install_resolution_mode = "unknown"
    if exports_frozen_uv_lock and installs_locked_requirements:
        install_resolution_mode = "canonical_lock_export"
    elif installs_requirements_dev:
        install_resolution_mode = "range_requirements"

    return {
        "install_commands": command_lines,
        "lock_check_commands": lock_check_commands,
        "checks_uv_lock_freshness": checks_uv_lock_freshness,
        "exports_frozen_uv_lock": exports_frozen_uv_lock,
        "installs_locked_requirements": installs_locked_requirements,
        "installs_requirements_dev": installs_requirements_dev,
        "editable_install": bool(EDITABLE_INSTALL_PATTERN.search(content))
        or installs_locked_requirements,
        "includes_build_package": bool(BUILD_PACKAGE_PATTERN.search(content))
        or installs_locked_requirements,
        "install_resolution_mode": install_resolution_mode,
    }
