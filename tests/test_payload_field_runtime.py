from __future__ import annotations

from ops.scripts.core.payload_field_runtime import dict_field


def test_dict_field_returns_nested_dict_value() -> None:
    nested = {"status": "pass"}

    assert dict_field({"summary": nested}, "summary") is nested


def test_dict_field_returns_empty_dict_for_missing_or_non_dict_values() -> None:
    assert dict_field({}, "summary") == {}
    assert dict_field({"summary": []}, "summary") == {}
    assert dict_field({"summary": "pass"}, "summary") == {}
