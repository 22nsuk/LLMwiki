from __future__ import annotations

TEMPLATE_PLACEHOLDER_RUN_IDS = frozenset(
    {
        "<run-id>",
        "run-YYYYMMDD-slug",
        "run-YYYYMMDD-mechanism-slug",
    }
)


def is_template_placeholder_run_id(run_id: str) -> bool:
    return run_id.strip() in TEMPLATE_PLACEHOLDER_RUN_IDS


def reject_template_placeholder_run_id(run_id: str, *, field_name: str = "run_id") -> None:
    value = run_id.strip()
    if is_template_placeholder_run_id(value):
        raise ValueError(f"{field_name} must not be a template placeholder run id: {value}")
