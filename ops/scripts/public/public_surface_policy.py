from __future__ import annotations

import re
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
    r"(?<![A-Za-z0-9])/(?:home|mnt|workspace|var/folders)/"
    r"|(?<![A-Za-z0-9])/Users/"
    r"|(?i:"
    r"(?<![A-Za-z0-9])[A-Z]:[\\/]"
    r"|\\\\(?:wsl\$|wsl\.localhost)\\"
    r"|\\Users\\"
    r")"
    r")"
)

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
