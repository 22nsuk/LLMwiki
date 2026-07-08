from __future__ import annotations

from typing import TypedDict


class WorkflowActionPinRule(TypedDict):
    id: str
    action: str
    sha: str
    version_comment: str
    paths: tuple[str, ...]


CI_CHECKOUT_ACTION_SHA = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
RELEASE_SECURITY_CHECKOUT_ACTION_SHA = "de0fac2e4500dabe0009e67214ff5f5447ce83dd"
SETUP_PYTHON_ACTION_SHA = "a309ff8b426b58ec0e2a45f0f869d46889d02405"
SETUP_UV_ACTION_SHA = "08807647e7069bb48b6ef5acd8ec9567f424441b"
UPLOAD_ARTIFACT_ACTION_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
DOWNLOAD_ARTIFACT_ACTION_SHA = "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
ATTEST_BUILD_PROVENANCE_ACTION_SHA = "0f67c3f4856b2e3261c31976d6725780e5e4c373"
PYPI_PUBLISH_ACTION_SHA = "cef221092ed1bacb1cc03d23a2d87d1d172e277b"
CODEQL_ACTION_SHA = "99df26d4f13ea111d4ec1a7dddef6063f76b97e9"
DEPENDENCY_REVIEW_ACTION_SHA = "a1d282b36b6f3519aa1f3fc636f609c47dddb294"

PINNED_CI_CHECKOUT_ACTION = f"actions/checkout@{CI_CHECKOUT_ACTION_SHA}"
PINNED_RELEASE_SECURITY_CHECKOUT_ACTION = (
    f"actions/checkout@{RELEASE_SECURITY_CHECKOUT_ACTION_SHA}"
)
PINNED_CHECKOUT_ACTION = PINNED_RELEASE_SECURITY_CHECKOUT_ACTION
PINNED_SETUP_PYTHON_ACTION = f"actions/setup-python@{SETUP_PYTHON_ACTION_SHA}"
PINNED_SETUP_UV_ACTION = f"astral-sh/setup-uv@{SETUP_UV_ACTION_SHA}"
PINNED_UPLOAD_ARTIFACT_ACTION = f"actions/upload-artifact@{UPLOAD_ARTIFACT_ACTION_SHA}"
PINNED_DOWNLOAD_ARTIFACT_ACTION = f"actions/download-artifact@{DOWNLOAD_ARTIFACT_ACTION_SHA}"
PINNED_ATTEST_BUILD_PROVENANCE_ACTION = (
    f"actions/attest-build-provenance@{ATTEST_BUILD_PROVENANCE_ACTION_SHA}"
)
PINNED_PYPI_PUBLISH_ACTION = (
    f"pypa/gh-action-pypi-publish@{PYPI_PUBLISH_ACTION_SHA}"
)
PINNED_CODEQL_ACTION_PREFIX = "github/codeql-action/"
PINNED_CODEQL_INIT_ACTION = f"github/codeql-action/init@{CODEQL_ACTION_SHA}"
PINNED_CODEQL_ANALYZE_ACTION = f"github/codeql-action/analyze@{CODEQL_ACTION_SHA}"
PINNED_DEPENDENCY_REVIEW_ACTION = (
    f"actions/dependency-review-action@{DEPENDENCY_REVIEW_ACTION_SHA}"
)

WORKFLOW_ACTION_PIN_RULES: tuple[WorkflowActionPinRule, ...] = (
    {
        "id": "checkout-ci",
        "action": "actions/checkout",
        "sha": CI_CHECKOUT_ACTION_SHA,
        "version_comment": "v7.0.0",
        "paths": (".github/workflows/ci.yml",),
    },
    {
        "id": "checkout-release-security",
        "action": "actions/checkout",
        "sha": RELEASE_SECURITY_CHECKOUT_ACTION_SHA,
        "version_comment": "v6.0.2",
        "paths": (
            ".github/workflows/release.yml",
            ".github/workflows/codeql.yml",
            ".github/workflows/dependency-review.yml",
        ),
    },
    {
        "id": "setup-python",
        "action": "actions/setup-python",
        "sha": SETUP_PYTHON_ACTION_SHA,
        "version_comment": "v6.2.0",
        "paths": (".github/actions/setup-python-uv/action.yml",),
    },
    {
        "id": "setup-uv",
        "action": "astral-sh/setup-uv",
        "sha": SETUP_UV_ACTION_SHA,
        "version_comment": "v8.1.0",
        "paths": (".github/actions/setup-python-uv/action.yml",),
    },
    {
        "id": "upload-artifact",
        "action": "actions/upload-artifact",
        "sha": UPLOAD_ARTIFACT_ACTION_SHA,
        "version_comment": "v7.0.1",
        "paths": (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        ),
    },
    {
        "id": "download-artifact",
        "action": "actions/download-artifact",
        "sha": DOWNLOAD_ARTIFACT_ACTION_SHA,
        "version_comment": "v8.0.1",
        "paths": (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        ),
    },
    {
        "id": "attest-build-provenance",
        "action": "actions/attest-build-provenance",
        "sha": ATTEST_BUILD_PROVENANCE_ACTION_SHA,
        "version_comment": "v4.1.1",
        "paths": (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        ),
    },
    {
        "id": "pypi-publish",
        "action": "pypa/gh-action-pypi-publish",
        "sha": PYPI_PUBLISH_ACTION_SHA,
        "version_comment": "release/v1.14",
        "paths": (".github/workflows/release.yml",),
    },
    {
        "id": "codeql-init",
        "action": "github/codeql-action/init",
        "sha": CODEQL_ACTION_SHA,
        "version_comment": "v4.37.0",
        "paths": (".github/workflows/codeql.yml",),
    },
    {
        "id": "codeql-analyze",
        "action": "github/codeql-action/analyze",
        "sha": CODEQL_ACTION_SHA,
        "version_comment": "v4.37.0",
        "paths": (".github/workflows/codeql.yml",),
    },
    {
        "id": "dependency-review",
        "action": "actions/dependency-review-action",
        "sha": DEPENDENCY_REVIEW_ACTION_SHA,
        "version_comment": "v5.0.0",
        "paths": (".github/workflows/dependency-review.yml",),
    },
)
