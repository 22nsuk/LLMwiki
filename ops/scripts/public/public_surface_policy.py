from __future__ import annotations

PUBLIC_INCLUDE_FILES = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    ".gitattributes",
    ".gitignore",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "pyproject.toml",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "requirements.txt",
    "requirements-dev.txt",
    "pytest.ini",
    "uv.lock",
)

PUBLIC_INCLUDE_PREFIXES = (
    ".codex/agents/",
    ".github/",
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

PUBLIC_EXCLUDED_PREFIXES = (
    ".obsidian/",
    ".venv/",
    "external-reports/",
    "ops/reports/",
    "raw/",
    "runs/",
    "system/",
    "tmp/",
    "wiki/",
)

PUBLIC_EXCLUDED_SEGMENTS = (
    ".cache",
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".vscode",
    "__pycache__",
)

PUBLIC_GITIGNORE_START = "# >>> public-surface-policy >>>"
PUBLIC_GITIGNORE_END = "# <<< public-surface-policy <<<"


def render_public_gitignore_block() -> str:
    lines = [
        PUBLIC_GITIGNORE_START,
        "# Generated from ops.scripts.public_surface_policy.",
        "# Root public repos should track only this allowlisted surface.",
        "*",
        "!/.gitattributes",
        "!/.gitignore",
        "!/.codex/",
        "!/.codex/agents/",
        "!/.codex/agents/**",
        "!/.github/",
        "!/.github/workflows/",
        "!/.github/workflows/**",
        "!/mk/",
        "!/mk/**",
        "!/AGENTS.md",
        "!/ARCHITECTURE.md",
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
        "!/requirements-dev.txt",
        "!/requirements.txt",
        "!/tests/",
        "!/tests/**",
        "!/tools/",
        "!/tools/**",
        "!/uv.lock",
        "AGENTS.local.md",
        "ops/manifest.json",
        "ops/raw-registry.json",
        "ops/reports/",
        PUBLIC_GITIGNORE_END,
    ]
    return "\n".join(lines) + "\n"
