from __future__ import annotations

import unittest
from pathlib import Path

import yaml
from ops.scripts.yaml_runtime import WikiLoader, parse_simple_yaml

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class YamlRuntimeTest(unittest.TestCase):
    def test_wiki_loader_does_not_mutate_global_safe_loader_resolvers(self) -> None:
        def has_timestamp_resolver(loader_cls: type[yaml.SafeLoader]) -> bool:
            for resolvers in loader_cls.yaml_implicit_resolvers.values():
                for tag, _regexp in resolvers:
                    if tag == "tag:yaml.org,2002:timestamp":
                        return True
            return False

        self.assertIsNot(yaml.SafeLoader.yaml_implicit_resolvers, WikiLoader.yaml_implicit_resolvers)
        self.assertTrue(has_timestamp_resolver(yaml.SafeLoader))
        self.assertFalse(has_timestamp_resolver(WikiLoader))

    def test_unquoted_url_list_item_stays_string(self) -> None:
        text = (FIXTURES / "yaml" / "unquoted-url-list.yaml").read_text(encoding="utf-8")
        data = parse_simple_yaml(text)
        self.assertEqual(data["items"], ["https://example.com/path?a=1"])

    def test_block_scalar_is_supported(self) -> None:
        text = (FIXTURES / "yaml" / "block-scalar.yaml").read_text(encoding="utf-8")
        data = parse_simple_yaml(text)
        self.assertEqual(data["note"], "line one\nline two\n")
        self.assertEqual(data["aliases"], ["alpha", "beta"])

    def test_unquoted_date_like_scalar_stays_string(self) -> None:
        data = parse_simple_yaml("created: 2026-04-13\n")
        self.assertEqual(data["created"], "2026-04-13")


if __name__ == "__main__":
    unittest.main()
