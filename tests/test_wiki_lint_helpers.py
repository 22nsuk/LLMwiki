from __future__ import annotations

import unittest

from ops.scripts.wiki_lint import add_issue


class WikiLintHelperTests(unittest.TestCase):
    def test_add_issue_routes_fail_and_warn_buckets(self) -> None:
        errors: list[dict] = []
        warnings: list[dict] = []

        add_issue({"type": "fatal"}, "fail", errors, warnings)
        add_issue({"type": "advisory"}, "warn", errors, warnings)

        self.assertEqual(errors, [{"type": "fatal"}])
        self.assertEqual(warnings, [{"type": "advisory"}])

        with self.assertRaisesRegex(ValueError, "unsupported lint severity"):
            add_issue({"type": "bad"}, "ignore", errors, warnings)


if __name__ == "__main__":
    unittest.main()
