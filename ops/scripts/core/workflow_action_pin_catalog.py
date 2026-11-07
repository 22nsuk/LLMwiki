from __future__ import annotations

from typing import TypedDict


class WorkflowActionPinRule(TypedDict):
    id: str
    action: str
    paths: tuple[str, ...]
    group: str


# Policy owns allowed action/path pairs and version cohorts. SHA/version values
# belong to the workflow YAML, which Dependabot updates directly.
WORKFLOW_ACTION_PIN_RULES: tuple[WorkflowActionPinRule, ...] = (
    {
        "id": "checkout-ci",
        "action": "actions/checkout",
        "paths": (".github/workflows/ci.yml",),
        "group": "checkout-ci",
    },
    {
        "id": "checkout-release-security",
        "action": "actions/checkout",
        "paths": (".github/workflows/release.yml", ".github/workflows/codeql.yml", ".github/workflows/dependency-review.yml"),
        "group": "checkout-release-security",
    },
    {
        "id": "setup-python",
        "action": "actions/setup-python",
        "paths": (".github/actions/setup-python-uv/action.yml",),
        "group": "setup-python",
    },
    {
        "id": "setup-uv",
        "action": "astral-sh/setup-uv",
        "paths": (".github/actions/setup-python-uv/action.yml",),
        "group": "setup-uv",
    },
    {
        "id": "upload-artifact",
        "action": "actions/upload-artifact",
        "paths": (".github/workflows/ci.yml", ".github/workflows/release.yml"),
        "group": "upload-artifact",
    },
    {
        "id": "download-artifact",
        "action": "actions/download-artifact",
        "paths": (".github/workflows/ci.yml", ".github/workflows/release.yml"),
        "group": "download-artifact",
    },
    {
        "id": "attest-build-provenance",
        "action": "actions/attest-build-provenance",
        "paths": (".github/workflows/ci.yml", ".github/workflows/release.yml"),
        "group": "attest-build-provenance",
    },
    {
        "id": "codeql-init",
        "action": "github/codeql-action/init",
        "paths": (".github/workflows/codeql.yml",),
        "group": "codeql",
    },
    {
        "id": "codeql-analyze",
        "action": "github/codeql-action/analyze",
        "paths": (".github/workflows/codeql.yml",),
        "group": "codeql",
    },
    {
        "id": "dependency-review",
        "action": "actions/dependency-review-action",
        "paths": (".github/workflows/dependency-review.yml",),
        "group": "dependency-review",
    },
)
