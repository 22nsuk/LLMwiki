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

_POSIX_LOCAL_ROOTS = (
    "private/var/folders",
    "var/folders",
    "workspace",
    "Users",
    "home",
    "mnt",
)
_WINDOWS_LOCAL_ROOTS = ("Users",)
_WINDOWS_UNC_SERVERS = ("wsl$", "wsl.localhost")
_BACKSLASH_PATTERN = re.escape("\\")
_DOUBLE_BACKSLASH_PATTERN = re.escape("\\\\")
_POSIX_LOCAL_ROOT_PATTERN = "|".join(re.escape(root) for root in _POSIX_LOCAL_ROOTS)
_WINDOWS_LOCAL_ROOT_PATTERN = "|".join(re.escape(root) for root in _WINDOWS_LOCAL_ROOTS)
_WINDOWS_UNC_SERVER_PATTERN = "|".join(
    re.escape(server) for server in _WINDOWS_UNC_SERVERS
)
_PUBLIC_LOCAL_PATH_CANDIDATE_RE = re.compile(
    rf"(?P<posix>(?<![A-Za-z0-9])/(?:{_POSIX_LOCAL_ROOT_PATTERN})/)"
    rf"|(?P<drive>(?<![A-Za-z0-9])[A-Za-z]:[\\/])"
    rf"|(?P<windows>(?<![A-Za-z0-9])(?i:"
    rf"{_DOUBLE_BACKSLASH_PATTERN}(?:{_WINDOWS_UNC_SERVER_PATTERN})"
    rf"{_BACKSLASH_PATTERN}"
    rf"|{_BACKSLASH_PATTERN}(?:{_WINDOWS_LOCAL_ROOT_PATTERN})"
    rf"{_BACKSLASH_PATTERN}"
    rf"))"
)
_URI_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_ESCAPED_CONTROL_CHARACTER_RE = re.compile(
    r"""^[abfnrtv](?=$|[\s"'`,;\)\]\}])""",
    flags=re.IGNORECASE,
)
_COMPLETE_LITERAL_TERMINATORS = frozenset("\t\r\n\"'`,;)]}")


@dataclass(frozen=True)
class PublicLocalPathLiteralExemption:
    text: str


@dataclass(frozen=True)
class PublicLocalPathLeak:
    kind: str
    text: str
    start: int
    end: int


def _posix_local_path(root: str, suffix: str = "") -> str:
    return f"/{root}/{suffix}"


def _windows_root_path(root: str, suffix: str = "") -> str:
    return f"\\{root}\\{suffix}"


def _windows_drive_path(
    drive: str,
    suffix: str = "",
    *,
    separator: str = "\\",
) -> str:
    return f"{drive}:{separator}{suffix}"


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
    "tests/test_backfill_historical_bootstrap_reports.py": (
        PublicLocalPathLiteralExemption(
            _posix_local_path(
                "mnt",
                "data/build_llm_wiki_package/LLM Wiki vNext/wiki/source--sample.md",
            )
        ),
        PublicLocalPathLiteralExemption(
            _posix_local_path("mnt", "data/build_llm_wiki_package/LLM Wiki vNext")
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
            _posix_local_path("workspace", ".venv/bin/python")
        ),
        PublicLocalPathLiteralExemption(_posix_local_path("workspace", "LLMwiki/repo")),
        PublicLocalPathLiteralExemption(_posix_local_path("Users", "alice/work/repo")),
        PublicLocalPathLiteralExemption(
            _posix_local_path("private", "var/folders/ab/tmp/repo")
        ),
        PublicLocalPathLiteralExemption(
            f"workspace:{_posix_local_path('home', 'alice/work/repo')}"
        ),
        PublicLocalPathLiteralExemption(_posix_local_path("workspace", "example")),
        PublicLocalPathLiteralExemption(
            _posix_local_path("home", "alice/.venv/bin/python")
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
        PublicLocalPathLiteralExemption(_windows_drive_path("c", r"temp\repo")),
        PublicLocalPathLiteralExemption(
            _windows_drive_path("d", "a/project", separator="/")
        ),
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
            )
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


def _is_uri_path_context(text: str, start: int) -> bool:
    token_start = start
    while token_start > 0 and not text[token_start - 1].isspace():
        if text[token_start - 1] in "\"'`":
            break
        token_start -= 1
    return _URI_SCHEME_RE.search(text[token_start:start]) is not None


def _has_local_path_start_context(text: str, start: int) -> bool:
    if start > 0 and text[start - 1].isalnum():
        return False
    return not _is_uri_path_context(text, start)


def _is_ambiguous_control_character_escape(
    text: str,
    candidate: re.Match[str],
) -> bool:
    return (
        candidate.lastgroup == "drive"
        and candidate.group(0).endswith("\\")
        and bool(_ESCAPED_CONTROL_CHARACTER_RE.match(text[candidate.end() :]))
    )


def _source_root_markers(source_root: str | None) -> tuple[str, ...]:
    if not source_root:
        return ()
    raw_marker = str(source_root).rstrip("/\\")
    if not raw_marker:
        return ()
    return tuple(
        sorted(
            {
                raw_marker,
                raw_marker.replace("\\", "/"),
                raw_marker.replace("/", "\\"),
            },
            key=len,
            reverse=True,
        )
    )


def _has_source_root_end_context(text: str, end: int) -> bool:
    if end >= len(text):
        return True
    next_character = text[end]
    if next_character in "/\\":
        return True
    if next_character == ".":
        after_period = end + 1
        return after_period >= len(text) or text[after_period].isspace()
    return not (next_character.isalnum() or next_character in "._~-")


def _candidate_local_path_leaks(
    text: str,
    *,
    source_root: str | None,
) -> list[PublicLocalPathLeak]:
    candidates: list[PublicLocalPathLeak] = []
    for match in _PUBLIC_LOCAL_PATH_CANDIDATE_RE.finditer(text):
        if not _has_local_path_start_context(text, match.start()):
            continue
        if _is_ambiguous_control_character_escape(text, match):
            continue
        kind = match.lastgroup
        assert kind is not None
        candidates.append(
            PublicLocalPathLeak(
                kind=kind,
                text=match.group(0),
                start=match.start(),
                end=match.end(),
            )
        )

    for marker in _source_root_markers(source_root):
        search_start = 0
        while True:
            start = text.find(marker, search_start)
            if start < 0:
                break
            end = start + len(marker)
            if _has_local_path_start_context(
                text, start
            ) and _has_source_root_end_context(text, end):
                candidates.append(
                    PublicLocalPathLeak(
                        kind="source_root",
                        text=marker,
                        start=start,
                        end=end,
                    )
                )
            search_start = start + 1

    candidates.sort(key=lambda item: (item.start, -(item.end - item.start), item.kind))
    longest_candidate_by_start: dict[int, PublicLocalPathLeak] = {}
    for leak in candidates:
        longest_candidate_by_start.setdefault(leak.start, leak)
    return list(longest_candidate_by_start.values())


def _is_complete_literal_occurrence(text: str, end: int) -> bool:
    return end >= len(text) or text[end] in _COMPLETE_LITERAL_TERMINATORS


def _intentional_local_path_literal_spans(
    rel_path: str,
    text: str,
) -> tuple[tuple[int, int], ...]:
    spans: set[tuple[int, int]] = set()
    for exemption in PUBLIC_INTENTIONAL_LOCAL_PATH_LITERALS.get(rel_path, ()):
        search_start = 0
        while True:
            start = text.find(exemption.text, search_start)
            if start < 0:
                break
            end = start + len(exemption.text)
            if _is_complete_literal_occurrence(text, end):
                spans.add((start, end))
            search_start = start + 1
    return tuple(sorted(spans))


def find_public_local_path_leaks(
    text: str,
    *,
    rel_path: str = "",
    source_root: str | None = None,
) -> tuple[PublicLocalPathLeak, ...]:
    exemption_spans = _intentional_local_path_literal_spans(rel_path, text)
    return tuple(
        candidate
        for candidate in _candidate_local_path_leaks(text, source_root=source_root)
        if not any(
            start <= candidate.start and candidate.end <= end
            for start, end in exemption_spans
        )
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
