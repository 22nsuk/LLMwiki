from __future__ import annotations

from copy import deepcopy
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - dependency bootstrap
    raise RuntimeError(
        "PyYAML is required for YAML parsing. Install it with "
        "`python3 -m pip install -r requirements.txt`."
    ) from exc


class WikiLoader(yaml.SafeLoader):
    # Isolate resolver mutations from yaml.SafeLoader so local timestamp handling
    # does not leak into unrelated callers that import PyYAML directly.
    yaml_implicit_resolvers = deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)


def _drop_implicit_resolver(tag: str) -> None:
    for first_char, resolvers in list(WikiLoader.yaml_implicit_resolvers.items()):
        filtered = [
            (resolver_tag, regexp)
            for resolver_tag, regexp in resolvers
            if resolver_tag != tag
        ]
        if filtered:
            WikiLoader.yaml_implicit_resolvers[first_char] = filtered
        else:
            del WikiLoader.yaml_implicit_resolvers[first_char]


_drop_implicit_resolver("tag:yaml.org,2002:timestamp")


def parse_simple_yaml(text: str) -> dict[str, Any]:
    data = yaml.load(text, Loader=WikiLoader)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("yaml root must be a mapping")
    return data
