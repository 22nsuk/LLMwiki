from __future__ import annotations

from collections.abc import Sequence

EXECUTOR_NOOP_MUTATION_FAILURE_MARKER = (
    "reported pass without modifying any declared primary target"
)


def executor_noop_mutation_failure_message(
    role: str,
    primary_targets: Sequence[str],
) -> str:
    joined_targets = ", ".join(str(target).strip() for target in primary_targets if str(target).strip())
    actor = str(role).strip() or "worker"
    return (
        f"{actor} {EXECUTOR_NOOP_MUTATION_FAILURE_MARKER}; "
        f"primary_targets=[{joined_targets}]"
    )


def text_has_executor_noop_mutation_failure(text: str) -> bool:
    return EXECUTOR_NOOP_MUTATION_FAILURE_MARKER in text
