from __future__ import annotations

from pathlib import Path

GENERATED_FILES = {
    ".gitignore",
    "ops/script-output-surfaces.json",
}
GENERATED_PREFIXES: tuple[str, ...] = ()
PUBLIC_SOURCE_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "mypy.ini",
    "pyproject.toml",
    "pytest.ini",
    "uv.lock",
}
LOCAL_SOURCE_CONTRACT_FILES = {
    "AGENTS.local.md",
}
PUBLIC_SOURCE_PREFIXES = (
    ".agents/skills/",
    ".codex/agents/",
    ".github/",
    "docs/",
    "mk/",
    "ops/",
    "tests/",
    "tools/",
)
SOURCE_CONTRACT_CATEGORIES = {"public_source", "local_source_contract"}
PRIVATE_OR_TRANSIENT_PREFIXES = (
    ".git/",
    ".venv/",
    "build/",
    "dist/",
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
    "raw/",
    "review/",
    "runs/",
    "system/",
    "tmp/",
    "wiki/",
)
LOCAL_ONLY_PRIVATE_INVENTORY_PATHS = (
    "ops/manifest.json",
    "ops/raw-registry.json",
)
LOCAL_ONLY_PRIVATE_INVENTORY_CATEGORY = "local_only_private_inventory"


def normalize_repo_path(path: str) -> str:
    normalized = Path(path).as_posix()
    if normalized in ("", "."):
        return ""
    if normalized.startswith("/"):
        return "<outside-repo>"
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = normalized.split("/")
    if ".." in parts:
        return "<outside-repo>"
    return normalized


def matches_prefix_or_root(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def classify_path(path: str) -> str:
    normalized = normalize_repo_path(path)
    if not normalized or normalized == "<outside-repo>":
        return "unexpected"
    if normalized in GENERATED_FILES or matches_prefix_or_root(normalized, GENERATED_PREFIXES):
        return "generated_canonical"
    if normalized in LOCAL_SOURCE_CONTRACT_FILES:
        return "local_source_contract"
    if normalized in LOCAL_ONLY_PRIVATE_INVENTORY_PATHS:
        return LOCAL_ONLY_PRIVATE_INVENTORY_CATEGORY
    if matches_prefix_or_root(normalized, PRIVATE_OR_TRANSIENT_PREFIXES):
        return "unexpected"
    if normalized in PUBLIC_SOURCE_FILES or matches_prefix_or_root(normalized, PUBLIC_SOURCE_PREFIXES):
        return "public_source"
    return "unexpected"
