from __future__ import annotations

from dataclasses import dataclass

import pytest

from ops.scripts.core.request_coercion_runtime import coerce_request_or_kwargs


@dataclass(frozen=True)
class ExampleRequest:
    left: str
    right: int


def test_coerce_request_or_kwargs_returns_request_object() -> None:
    request = ExampleRequest(left="a", right=1)

    assert (
        coerce_request_or_kwargs(
            request=request,
            legacy_kwargs={},
            request_type=ExampleRequest,
        )
        is request
    )


def test_coerce_request_or_kwargs_rejects_mixed_request_and_legacy_kwargs() -> None:
    with pytest.raises(TypeError, match="request cannot be combined with legacy keyword arguments: right"):
        coerce_request_or_kwargs(
            request=ExampleRequest(left="a", right=1),
            legacy_kwargs={"right": 2},
            request_type=ExampleRequest,
        )


def test_coerce_request_or_kwargs_builds_request_from_legacy_kwargs() -> None:
    assert coerce_request_or_kwargs(
        request=None,
        legacy_kwargs={"left": "a", "right": 2},
        request_type=ExampleRequest,
    ) == ExampleRequest(left="a", right=2)
