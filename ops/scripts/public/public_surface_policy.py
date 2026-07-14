from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

PUBLIC_INCLUDE_FILES = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    ".gitattributes",
    ".gitignore",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "pyproject.toml",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "pytest.ini",
    "uv.lock",
)

PUBLIC_INCLUDE_PREFIXES = (
    ".agents/skills/",
    ".codex/agents/",
    ".github/",
    "docs/",
    "mk/",
    "ops/",
    "tests/",
    "tools/",
)

PUBLIC_EXCLUDED_FILES = (
    "AGENTS.local.md",
    "ops/manifest.json",
    "ops/raw-registry.json",
)

PUBLIC_INCLUDED_REPORT_FILES: tuple[str, ...] = ()

PUBLIC_EXCLUDED_PREFIXES = (
    ".obsidian/",
    ".venv/",
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
    "raw/",
    "runs/",
    "system/",
    "tmp/",
    "wiki/",
)

PUBLIC_EXCLUDED_SEGMENTS = (
    ".codebase-memory",
    ".cache",
    ".git",
    ".hypothesis",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
)

PUBLIC_EXCLUDED_LOCAL_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".coverage",
    ".coverage.*",
    "*.swp",
    "*.swo",
    "*~",
    ".DS_Store",
    "Thumbs.db",
)

PUBLIC_LOCAL_ABSOLUTE_PATH_RE = re.compile(
    r"(?:"
    r"(?<![A-Za-z0-9])/(?:home|mnt|workspace|var/folders|private/var/folders)/"
    r"|(?<![A-Za-z0-9])/Users/"
    r"|(?<![A-Za-z0-9])[A-Z]:[\\/]"
    r"|(?i:\\\\(?:wsl\$|wsl\.localhost)\\"
    r"|\\Users\\"
    r")"
    r")"
)


@dataclass(frozen=True)
class PublicLocalPathLiteralExemption:
    text: str
    occurrences: int = 1


def _posix_local_path(root: str, suffix: str = "") -> str:
    return f"/{root}/{suffix}"


def _windows_root_path(root: str, suffix: str = "") -> str:
    return f"\\{root}\\{suffix}"


def _windows_drive_path(drive: str, suffix: str = "") -> str:
    return f"{drive}:\\{suffix}"


def _windows_unc_path(server: str, suffix: str) -> str:
    return f"\\\\{server}\\{suffix}"


PUBLIC_INTENTIONAL_LOCAL_PATH_LITERALS: dict[
    str, tuple[PublicLocalPathLiteralExemption, ...]
] = {
    "ops/scripts/core/output_runtime.py": (
        PublicLocalPathLiteralExemption(_posix_local_path("home", r"""[^/\s\"']+""")),
    ),
    "ops/scripts/core/sanitize_run_artifacts.py": (
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt", r"c/Users/[^/\s]+/AppData/Local/Temp/[^/\s]+/vault/"
            )
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt", r"c/Users/[^/\s]+/AppData/Local/Temp/[^/\s]+/vault\b"
            )
        ),
    ),
    "ops/scripts/mechanism/run_mechanism_experiment_runtime.py": (
        PublicLocalPathLiteralExemption(_posix_local_path("mnt")),
    ),
    "ops/scripts/public/public_surface_policy.py": (
        PublicLocalPathLiteralExemption(_posix_local_path("Users")),
        PublicLocalPathLiteralExemption(_windows_root_path("Users")),
    ),
    "tests/test_backfill_historical_bootstrap_reports.py": (
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt",
                "data/build_llm_wiki_package/LLM Wiki vNext/wiki/source--sample.md",
            )
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path("mnt", "data/build_llm_wiki_package/LLM Wiki vNext"),
            occurrences=2,
        ),
        PublicLocalPathLiteralExemption(_posix_local_path("mnt", "data/")),
    ),
    "tests/test_output_runtime.py": (
        PublicLocalPathLiteralExemption(
            _posix_local_path("home", "example/code/LLMwiki-worktrees/goal-runtime")
        ),
    ),
    "tests/test_public_check_summary.py": (
        PublicLocalPathLiteralExemption(
            _posix_local_path("workspace", ".venv/bin/python"), occurrences=2
        ),
        PublicLocalPathLiteralExemption(_posix_local_path("workspace", "LLMwiki/repo")),
        PublicLocalPathLiteralExemption(
            _posix_local_path("Users", "alice/work/repo"), occurrences=2
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path("private", "var/folders/ab/tmp/repo")
        ),
        PublicLocalPathLiteralExemption(
            f"workspace:{_posix_local_path('home', 'alice/work/repo')}"
        ),
        PublicLocalPathLiteralExemption(_posix_local_path("workspace", "example")),
        PublicLocalPathLiteralExemption(
            _posix_local_path("home", "alice/.venv/bin/python"), occurrences=4
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path("home", "bob/.venv/bin/python")
        ),
    ),
    "tests/test_public_surface_policy.py": (
        PublicLocalPathLiteralExemption(
            f"workspace:{_posix_local_path('home', 'alice/work/repo')}"
        ),
        PublicLocalPathLiteralExemption(
            f"source:{_posix_local_path('Users', 'alice/work/repo')}"
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path("private", "var/folders/ab/tmp/repo")
        ),
        PublicLocalPathLiteralExemption(_posix_local_path("home", "alice/work/repo")),
        PublicLocalPathLiteralExemption(_posix_local_path("mnt", "c/Users/alice/repo")),
        PublicLocalPathLiteralExemption(_posix_local_path("workspace", "LLMwiki/repo")),
        PublicLocalPathLiteralExemption(_posix_local_path("Users", "alice/work/repo")),
        PublicLocalPathLiteralExemption(
            _posix_local_path("var", "folders/ab/tmp/repo")
        ),
        PublicLocalPathLiteralExemption(_windows_drive_path("C", r"Users\alice\repo")),
        PublicLocalPathLiteralExemption(_windows_drive_path("C", r"USERS\alice\repo")),
        PublicLocalPathLiteralExemption(
            _windows_unc_path("WSL$", r"Ubuntu\home\alice\repo")
        ),
        PublicLocalPathLiteralExemption(_windows_root_path("USERS", r"alice\repo")),
    ),
    "tests/test_run_mechanism_experiment_steps.py": (
        PublicLocalPathLiteralExemption(
            _posix_local_path("mnt", "c/Users/ADMINI~1/AppData/Local/Temp")
        ),
    ),
    "tests/test_runtime_hotspot_facade_golden_outputs.py": (
        PublicLocalPathLiteralExemption(_posix_local_path("var", "folders/")),
        PublicLocalPathLiteralExemption(_posix_local_path("mnt")),
        PublicLocalPathLiteralExemption(_posix_local_path("home")),
        PublicLocalPathLiteralExemption(_windows_root_path("Users")),
        PublicLocalPathLiteralExemption(_windows_drive_path("C")),
    ),
    "tests/test_sanitize_run_artifacts.py": (
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt",
                "c/Users/Administrator/Desktop/작업/LLM Wiki vNext/.venv/bin/python",
            )
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt", "c/Users/Administrator/Desktop/작업/LLM Wiki vNext"
            ),
            occurrences=3,
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt",
                "c/Users/ADMINI~1/AppData/Local/Temp/"
                "run-123-workspace-abcd/vault/wiki/page.md",
            )
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt",
                "c/Users/ADMINI~1/AppData/Local/Temp/run-123-workspace-abcd/vault",
            )
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt",
                "c/Users/ADMINI~1/AppData/Local/Temp/"
                "run-1-workspace-a/vault/wiki/page.md",
            )
        ),
    ),
    "tests/test_trusted_candidate_runner.py": (
        PublicLocalPathLiteralExemption(_posix_local_path("home", "tester")),
    ),
}


def redact_intentional_local_path_literals(rel_path: str, text: str) -> str:
    exemptions = sorted(
        PUBLIC_INTENTIONAL_LOCAL_PATH_LITERALS.get(rel_path, ()),
        key=lambda exemption: len(exemption.text),
        reverse=True,
    )
    redacted = text
    for exemption in exemptions:
        replacement = " " * len(exemption.text)
        for _ in range(exemption.occurrences):
            redacted = redacted.replace(exemption.text, replacement, 1)
    return redacted


# Without a trailing slash, Git matches both files and directories named like the segment.
PUBLIC_EXCLUDED_SEGMENT_GITIGNORE_PATTERNS = PUBLIC_EXCLUDED_SEGMENTS

PUBLIC_GITIGNORE_START = "# >>> public-surface-policy >>>"
PUBLIC_GITIGNORE_END = "# <<< public-surface-policy <<<"
PUBLIC_GITIGNORE_TEMPLATE = "ops/templates/public-mirror.gitignore"


def is_public_excluded_by_local_state(rel_path: str) -> bool:
    path = PurePosixPath(rel_path)
    for part in path.parts:
        if part in PUBLIC_EXCLUDED_SEGMENTS:
            return True
        if any(fnmatchcase(part, pattern) for pattern in PUBLIC_EXCLUDED_LOCAL_FILE_PATTERNS):
            return True
    return False


def render_public_gitignore_block() -> str:
    lines = [
        PUBLIC_GITIGNORE_START,
        "# Generated from ops.scripts.public_surface_policy.",
        "# Root public repos should track only this allowlisted surface.",
        "*",
        "!/.gitattributes",
        "!/.gitignore",
        "!/.agents/",
        "!/.agents/skills/",
        "!/.agents/skills/**",
        "!/.codex/",
        "!/.codex/agents/",
        "!/.codex/agents/**",
        "!/.github/",
        "!/.github/**",
        "!/docs/",
        "!/docs/**",
        "!/mk/",
        "!/mk/**",
        "!/AGENTS.md",
        "!/ARCHITECTURE.md",
        "!/CHANGELOG.md",
        "!/CONTRIBUTING.md",
        "!/LICENSE",
        "!/Makefile",
        "!/pyproject.toml",
        "!/README.md",
        "!/SECURITY.md",
        "!/THIRD_PARTY_NOTICES.md",
        "!/ops/",
        "!/ops/**",
        "!/pytest.ini",
        "!/tests/",
        "!/tests/**",
        "!/tools/",
        "!/tools/**",
        "!/uv.lock",
        "# Re-ignore local/private state opened by the allowlisted prefixes above.",
        *PUBLIC_EXCLUDED_FILES,
        "ops/operator/",
        "ops/operator/**",
        "ops/reports/",
        "ops/reports/**",
        *PUBLIC_EXCLUDED_SEGMENT_GITIGNORE_PATTERNS,
        *PUBLIC_EXCLUDED_LOCAL_FILE_PATTERNS,
        "# Generated ops/operator and ops/reports evidence is local-only.",
        PUBLIC_GITIGNORE_END,
    ]
    return "\n".join(lines) + "\n"
