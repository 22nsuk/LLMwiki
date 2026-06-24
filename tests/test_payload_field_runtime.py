from __future__ import annotations

import unittest

from ops.scripts.core.payload_field_runtime import (
    bool_at,
    dict_field,
    dict_value,
    int_at,
    list_of_dicts,
    str_at,
)


class PayloadFieldRuntimeTests(unittest.TestCase):
    def test_dict_field_returns_nested_dict_value(self) -> None:
        nested = {"status": "pass"}
        self.assertIs(dict_field({"summary": nested}, "summary"), nested)

    def test_dict_field_returns_empty_dict_for_missing_or_non_dict_values(self) -> None:
        self.assertEqual(dict_field({}, "summary"), {})
        self.assertEqual(dict_field({"summary": []}, "summary"), {})
        self.assertEqual(dict_field({"summary": "pass"}, "summary"), {})

    def test_bool_at_reads_nested_bool(self) -> None:
        payload = {"queue": {"ready": True}}
        self.assertTrue(bool_at(payload, ("queue", "ready")))
        self.assertFalse(bool_at(payload, ("queue", "missing")))

    def test_str_at_reads_nested_string_with_default(self) -> None:
        payload = {"learning_readiness": {"status": "learning_likely"}}
        self.assertEqual(str_at(payload, ("learning_readiness", "status")), "learning_likely")
        self.assertEqual(str_at({}, ("missing",), "fallback"), "fallback")

    def test_int_at_reads_nested_integer(self) -> None:
        payload = {"queue": {"runnable_proposal_count": 2}}
        self.assertEqual(int_at(payload, ("queue", "runnable_proposal_count")), 2)
        self.assertEqual(int_at(payload, ("queue", "missing"), 5), 5)

    def test_list_of_dicts_filters_non_dict_items(self) -> None:
        rows = [{"id": "a"}, "skip", {"id": "b"}]
        self.assertEqual(list_of_dicts(rows), [{"id": "a"}, {"id": "b"}])
        self.assertEqual(list_of_dicts("nope"), [])

    def test_dict_value_returns_dict_or_empty(self) -> None:
        self.assertEqual(dict_value({"x": 1}), {"x": 1})
        self.assertEqual(dict_value([]), {})
