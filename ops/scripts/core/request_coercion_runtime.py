from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def coerce_request_or_kwargs[RequestT](
    *,
    request: RequestT | None,
    legacy_kwargs: Mapping[str, Any],
    request_type: type[RequestT],
    mixed_error_prefix: str = "request cannot be combined with legacy keyword arguments",
) -> RequestT:
    if request is not None:
        if legacy_kwargs:
            names = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"{mixed_error_prefix}: {names}")
        return request
    return request_type(**dict(legacy_kwargs))
