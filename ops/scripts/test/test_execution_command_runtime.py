from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.output_runtime import sanitize_report_text

TAIL_LINE_COUNT = 80
RELEASE_BUILDER_ENVIRONMENT = ".venv clean release-builder"
SUPPORTED_PYTHON_MAJOR_MINOR = ("3.11", "3.12", "3.13", "3.14")
MINIMUM_PYTEST_MAJOR = 8
PYTEST_COUNT_RE = re.compile(
    r"(?P<count>\d+)\s+"
    r"(?:(?P<subtest_label>subtests?)\s+)?"
    r"(?P<label>passed|failed|error|errors|skipped|xfailed|xpassed|warning|warnings)"
)
PYTEST_DESELECTED_RE = re.compile(r"(?P<count>\d+)\s+deselected")
PYTEST_JUNIT_OUTPUT_FLAGS = {"--junit-xml", "--junitxml"}
PYTEST_OPTION_VALUE_FLAGS = {
    *PYTEST_JUNIT_OUTPUT_FLAGS,
    "-c",
    "-k",
    "-m",
    "-n",
    "-o",
    "-p",
    "-r",
    "-W",
    "--basetemp",
    "--capture",
    "--confcutdir",
    "--deselect",
    "--ignore",
    "--ignore-glob",
    "--dist",
    "--log-cli-level",
    "--maxfail",
    "--maxprocesses",
    "--max-worker-restart",
    "--override-ini",
    "--rootdir",
    "--tb",
    "--assert",
    "--color",
    "--code-highlight",
    "--durations",
    "--durations-min",
    "--import-mode",
    "--junit-prefix",
    "--junitprefix",
    "--lfnf",
    "--last-failed-no-failures",
    "--log-level",
    "--log-format",
    "--log-date-format",
    "--log-file",
    "--log-file-level",
    "--log-file-format",
    "--log-file-date-format",
    "--pythonwarnings",
    "--show-capture",
    "--verbosity",
}
PYTEST_CACHE_SELECTION_FLAGS = {
    "--lf", "--last-failed", "--sw", "--stepwise", "--sw-skip", "--stepwise-skip",
}
PYTEST_COLLECTION_FILTER_FLAGS = {
    "-k", "-m", "--deselect", "--ignore", "--ignore-glob", *PYTEST_CACHE_SELECTION_FLAGS,
}
PYTEST_BOOLEAN_FLAGS = {
    "-q", "--quiet", "-v", "--verbose", "-s", "-x", "--exitfirst",
    "--cache-clear", "--disable-warnings", "--disable-pytest-warnings",
    "--strict", "--strict-config", "--strict-markers", "--showlocals", "--no-showlocals",
    "--full-trace", "--continue-on-collection-errors", "--noconftest", "--pyargs",
    "--keep-duplicates", "--ff", "--failed-first", "--nf", "--new-first",
    "--collect-only", "--co", *PYTEST_COLLECTION_FILTER_FLAGS,
} - PYTEST_OPTION_VALUE_FLAGS
PYTEST_PLUGIN_AUTOLOAD_ENV = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"


@dataclass(frozen=True)
class PytestArgument:
    option: str | None
    value: str | None
    tokens: tuple[str, ...]


def _pytest_args_start(command: list[str]) -> int | None:
    for index, item in enumerate(command):
        if item == "-m" and index + 1 < len(command) and command[index + 1] == "pytest":
            return index + 2
        if Path(item).name in {"pytest", "py.test", "pytest.exe", "py.test.exe"}:
            return index + 1
    return None


def is_pytest_command(command: list[str]) -> bool:
    return _pytest_args_start(command) is not None


def pytest_args(command: list[str]) -> list[str]:
    start = _pytest_args_start(command)
    return command[start:] if start is not None else []


def parsed_pytest_args(command: list[str]) -> list[PytestArgument]:
    """Tokenize once for coverage, collection, deselection, and entrypoint guidance."""
    args = iter(pytest_args(command))
    parsed: list[PytestArgument] = []
    for token in args:
        if token == "--":
            parsed.append(PytestArgument("--", None, (token,)))
            parsed.extend(PytestArgument(None, value, (value,)) for value in args)
            break
        if not token.startswith("-"):
            parsed.append(PytestArgument(None, token, (token,)))
            continue
        option, separator, value = token.partition("=")
        tokens: tuple[str, ...] = (token,)
        if len(token) > 2 and token[:2] in PYTEST_OPTION_VALUE_FLAGS:
            option, value, separator = token[:2], token[2:].removeprefix("="), "attached"
        if option in PYTEST_OPTION_VALUE_FLAGS and not separator:
            next_value = next(args, None)
            value = next_value if next_value is not None else ""
            tokens = (token, value) if next_value is not None else (token,)
        if option.startswith("-") and set(option[1:]) in ({"q"}, {"v"}):
            option = option[:2]
        parsed.append(PytestArgument(option, value if separator or option in PYTEST_OPTION_VALUE_FLAGS else None, tokens))
    return parsed


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def classify_interpreter_path(vault: Path, executable: str) -> str:
    value = str(executable).strip()
    if not value:
        return "unknown"
    if value in {"python", "python3", "py"}:
        return "path_lookup"
    path = Path(value)
    if not path.is_absolute():
        if ".venv" in path.parts:
            return "repo_virtualenv"
        resolved = (vault / path).resolve()
        if _is_relative_to(resolved, vault.resolve()):
            return "repo_relative"
        return "relative_external"
    resolved = path.resolve()
    if _is_relative_to(resolved, vault.resolve()):
        return "repo_virtualenv" if ".venv" in resolved.parts else "repo_absolute"
    if ".venv" in resolved.parts or "venv" in resolved.parts:
        return "external_virtualenv"
    return "external_absolute"


def semantic_command(command: list[str]) -> list[str]:
    if not command:
        return []
    idx = 0
    while idx < len(command):
        token = command[idx]
        if token == "-m" and idx + 1 < len(command):
            return command[idx:]
        if "pytest" in Path(token).name:
            return command[idx:]
        idx += 1
    return command[1:] if len(command) > 1 else command


def collection_semantic_command(command: list[str]) -> list[str]:
    semantic = semantic_command(command)
    args = pytest_args(command)
    prefix = semantic[:len(semantic) - len(args)] if args else semantic
    return [*prefix, *(token for arg in parsed_pytest_args(command)
                       if arg.option not in PYTEST_JUNIT_OUTPUT_FLAGS for token in arg.tokens)]


def _pytest_version() -> str:
    try:
        return importlib.metadata.version("pytest")
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _major_minor(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2:
        return version
    return f"{parts[0]}.{parts[1]}"


def _major_version(value: str) -> int | None:
    try:
        return int(value.split(".", 1)[0])
    except ValueError:
        return None


def _toolchain_contract(python_version: str, pytest_version: str) -> dict[str, Any]:
    python_supported = _major_minor(python_version) in SUPPORTED_PYTHON_MAJOR_MINOR
    pytest_major = _major_version(pytest_version)
    pytest_supported = pytest_major is not None and pytest_major >= MINIMUM_PYTEST_MAJOR
    status = "pass" if python_supported and pytest_supported else "unsupported"
    reason_parts: list[str] = []
    if not python_supported:
        reason_parts.append(
            f"python {_major_minor(python_version)} is outside supported set "
            f"{', '.join(SUPPORTED_PYTHON_MAJOR_MINOR)}"
        )
    if not pytest_supported:
        reason_parts.append(f"pytest {pytest_version} is below required major {MINIMUM_PYTEST_MAJOR}")
    return {
        "status": status,
        "python_supported": python_supported,
        "pytest_supported": pytest_supported,
        "supported_python_major_minor": list(SUPPORTED_PYTHON_MAJOR_MINOR),
        "minimum_pytest_major": MINIMUM_PYTEST_MAJOR,
        "release_evidence_effect": "eligible" if status == "pass" else "blocked_unsupported_toolchain",
        "reason": "; ".join(reason_parts) if reason_parts else "toolchain is eligible for release evidence",
    }


def build_execution_environment(vault: Path, command: list[str]) -> dict[str, Any]:
    env_value = os.environ.get(PYTEST_PLUGIN_AUTOLOAD_ENV, "")
    command_executable = str(command[0]) if command else ""
    python_version = platform.python_version()
    pytest_version = _pytest_version()
    return {
        "python_version": python_version,
        "pytest_version": pytest_version,
        "plugin_autoload_policy": {
            "env_var": PYTEST_PLUGIN_AUTOLOAD_ENV,
            "value": env_value,
            "autoload_disabled": env_value == "1",
            "policy": "disabled" if env_value == "1" else "not_set" if not env_value else "custom",
        },
        "interpreter_path_class": classify_interpreter_path(vault, command_executable),
        "toolchain_contract": _toolchain_contract(python_version, pytest_version),
    }


def tail_text(text: str, max_lines: int = TAIL_LINE_COUNT) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def display_command(vault: Path, command: list[str]) -> str:
    return shlex.join([sanitize_report_text(vault, item) for item in command])


def semantic_command_text(vault: Path, command: list[str]) -> str:
    return shlex.join([sanitize_report_text(vault, item) for item in semantic_command(command)])


def collection_semantic_command_text(vault: Path, command: list[str]) -> str:
    return shlex.join(
        [sanitize_report_text(vault, item) for item in collection_semantic_command(command)]
    )


def toolchain_fingerprint(execution_environment: dict[str, Any]) -> str:
    python_version = str(execution_environment.get("python_version", "")).strip()
    pytest_version = str(execution_environment.get("pytest_version", "")).strip()
    plugin_policy = execution_environment.get("plugin_autoload_policy", {})
    autoload_disabled = bool(plugin_policy.get("autoload_disabled"))
    raw = f"python={python_version}|pytest={pytest_version}|plugin_autoload_disabled={autoload_disabled}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_pytest_counts(*streams: str) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 0,
        "subtests_passed": 0,
    }
    text = "\n".join(streams)
    for match in PYTEST_COUNT_RE.finditer(text):
        label = match.group("label")
        if match.group("subtest_label") in {"subtest", "subtests"} and label == "passed":
            normalized = "subtests_passed"
        else:
            normalized = {
                "error": "errors",
                "warning": "warnings",
            }.get(label, label)
        counts[normalized] = max(counts[normalized], int(match.group("count")))
    return counts


def classify_status(result: TimedProcessResult, counts: dict[str, int]) -> str:
    if result.timed_out:
        return "timeout"
    if result.returncode in {130, -2}:
        return "interrupted"
    if result.returncode == 0:
        return "pass"
    if counts["passed"] > 0 and (counts["failed"] > 0 or counts["errors"] > 0):
        return "partial-pass"
    return "fail"
