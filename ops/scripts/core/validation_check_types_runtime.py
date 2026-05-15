from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeAlias, TypedDict


ValidationCheckResult = TypedDict(
    "ValidationCheckResult",
    {
        "check": str,
        "pass": bool,
        "detail": Any,
    },
)
PhaseCheckResult: TypeAlias = ValidationCheckResult


def validation_check(check: str, passed: bool, detail: Any) -> ValidationCheckResult:
    return {
        "check": check,
        "pass": passed,
        "detail": detail,
    }


def validation_check_from_mapping(payload: Mapping[str, Any]) -> ValidationCheckResult:
    check = payload.get("check", "")
    passed = payload.get("pass", False)
    return validation_check(
        str(check) if isinstance(check, str) else "",
        passed if isinstance(passed, bool) else False,
        payload.get("detail"),
    )


__all__ = [
    "PhaseCheckResult",
    "ValidationCheckResult",
    "validation_check",
    "validation_check_from_mapping",
]
