from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.frontmatter_runtime import (
    parse_frontmatter,
    validate_frontmatter,
    validate_frontmatter_metadata,
    validate_frontmatter_pending_required_fields,
    validate_source_frontmatter_against_registry,
)
from ops.scripts.core.policy_runtime import load_policy
from tests.minimal_vault_runtime import seed_minimal_vault


class FrontmatterRuntimeTest(unittest.TestCase):
    def test_parse_frontmatter_supports_mapping_and_empty_blocks(self) -> None:
        self.assertEqual(
            parse_frontmatter("---\ntitle: Probe\ncount: 2\n---\n# Body\n"),
            {"title": "Probe", "count": 2},
        )
        self.assertEqual(parse_frontmatter("---\n---\n# Body\n"), {})
        self.assertIsNone(parse_frontmatter("# No frontmatter\n"))

    def test_parse_frontmatter_rejects_invalid_blocks(self) -> None:
        with self.assertRaisesRegex(ValueError, "unterminated frontmatter block"):
            parse_frontmatter("---\ntitle: Broken\n# Body\n")

        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            parse_frontmatter("---\n- item\n---\n# Body\n")

    def test_validate_frontmatter_applies_conditional_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            contract = policy["frontmatter_contract"]

            path = vault / "wiki" / "source--research.md"
            frontmatter = {
                "title": "Research Source",
                "page_type": "source",
                "corpus": "wiki",
                "registry_id": "R-200",
                "raw_path": "raw/research.pdf",
                "source_type": "domain-research-paper",
                "domain": "research",
                "aliases": ["source--research"],
                "tags": ["corpus/wiki", "type/source"],
            }

            issues = validate_frontmatter(vault, path, "source--research", frontmatter, contract)
            self.assertIn("missing_frontmatter_field", {issue["type"] for issue in issues})

            frontmatter["research_mode"] = "invalid"
            issues = validate_frontmatter(vault, path, "source--research", frontmatter, contract)
            value_issue = next(issue for issue in issues if issue["type"] == "frontmatter_value_mismatch")
            self.assertEqual(
                value_issue["detail"]["research_mode"]["expected_one_of"],
                ["experiment", "model", "reference"],
            )

    def test_validate_frontmatter_metadata_checks_aliases_and_tags(self) -> None:
        contract = {
            "metadata_review": {
                "require_alias_stem": True,
                "required_tag_templates": ["corpus/{corpus}", "type/{page_type}", "research/{research_mode}"],
                "source_page_slug": {
                    "ascii_summary_slug_pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                    "disallowed_slug_substrings": ["intake-w-"],
                },
            }
        }
        frontmatter = {
            "page_type": "source",
            "corpus": "wiki",
            "aliases": ["alias-only"],
            "tags": ["corpus/wiki"],
        }

        issues = validate_frontmatter_metadata(frontmatter, "source--fake", contract)
        issue_types = {issue["type"] for issue in issues}
        self.assertIn("frontmatter_alias_missing_stem", issue_types)
        tag_issue = next(issue for issue in issues if issue["type"] == "frontmatter_tag_mismatch")
        self.assertEqual(tag_issue["detail"]["missing_tags"], ["type/source"])

    def test_validate_frontmatter_metadata_flags_noncanonical_source_slug(self) -> None:
        contract = {
            "metadata_review": {
                "require_alias_stem": True,
                "required_tag_templates": ["corpus/{corpus}", "type/{page_type}"],
                "source_page_slug": {
                    "ascii_summary_slug_pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                    "disallowed_slug_substrings": ["intake-w-"],
                },
            }
        }
        frontmatter = {
            "page_type": "source",
            "corpus": "wiki",
            "aliases": ["source--한글-제목-2026-04-21"],
            "tags": ["corpus/wiki", "type/source"],
        }

        issues = validate_frontmatter_metadata(frontmatter, "source--한글-제목-2026-04-21", contract)

        naming_issue = next(issue for issue in issues if issue["type"] == "noncanonical_source_page_slug")
        self.assertEqual(naming_issue["detail"]["slug"], "한글-제목")
        self.assertIn("slug_not_ascii_summary", naming_issue["detail"]["violations"])

    def test_validate_frontmatter_pending_required_fields_warns_before_required_cutover(self) -> None:
        schema_versioning = {
            "artifact_contract_version": 1,
            "frontmatter_contract_version": 1,
            "frontmatter_field_rollouts": [
                {
                    "field": "created",
                    "status": "optional_before_required",
                    "severity": "warn",
                    "applies_to_page_types": ["source"],
                    "introduced_on": "2026-04-18",
                    "required_after": None,
                    "migration": "Backfill after review.",
                    "rationale": "Surface migration debt before hard requirement.",
                }
            ],
        }

        issues = validate_frontmatter_pending_required_fields(
            {"page_type": "source"},
            schema_versioning,
        )

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["type"], "frontmatter_field_pending_required")
        self.assertEqual(issues[0]["detail"]["missing_field"], "created")
        self.assertEqual(issues[0]["detail"]["frontmatter_contract_version"], 1)
        self.assertEqual(issues[0]["detail"]["artifact_contract_version"], 1)
        self.assertEqual(
            validate_frontmatter_pending_required_fields(
                {"page_type": "source", "created": "2026-04-18"},
                schema_versioning,
            ),
            [],
        )

    def test_policy_accepts_concept_taxonomy_optional_frontmatter_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            contract = policy["frontmatter_contract"]

            path = vault / "wiki" / "concept--taxonomy.md"
            frontmatter = {
                "title": "Taxonomy Concept",
                "page_type": "concept",
                "corpus": "wiki",
                "canonical": True,
                "aliases": ["concept--taxonomy"],
                "tags": ["corpus/wiki", "type/concept"],
                "topic_area": "AI",
                "topic_subarea": "capability validation",
                "primary_lens": "evidence type before capability narrative",
                "jurisdiction_scope": ["global"],
                "concept_role": "canonical_lens",
            }

            issues = validate_frontmatter(vault, path, "concept--taxonomy", frontmatter, contract)
            self.assertEqual(issues, [])

    def test_policy_accepts_source_route_optional_frontmatter_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            contract = policy["frontmatter_contract"]

            path = vault / "wiki" / "source--route.md"
            frontmatter = {
                "title": "Route Source",
                "page_type": "source",
                "corpus": "wiki",
                "registry_id": "W-999",
                "raw_path": "raw/fake.pdf",
                "source_type": "news-snapshot",
                "domain": "ai-adoption",
                "aliases": ["source--route"],
                "tags": ["corpus/wiki", "type/source"],
                "primary_concept": "concept--ai-adoption-labor-and-public-sector-deployment",
                "primary_lens": "workflow redesign before adoption headline",
                "authority_class": "supporting_evidence",
                "route_decision": "absorb_existing_concept",
            }

            issues = validate_frontmatter(vault, path, "source--route", frontmatter, contract)
            self.assertEqual(issues, [])

    def test_validate_source_frontmatter_against_registry_accepts_locator_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            contract = policy["frontmatter_contract"]

            frontmatter = {
                "corpus": "wiki",
                "registry_id": "R-100",
                "raw_path": "./raw/fake.pdf",
                "source_type": "news-snapshot",
                "domain": "fake",
            }
            registry_entry = {
                "target_page": "source--fake",
                "corpus": "wiki",
                "registry_id": "R-100",
                "storage_path": "raw/fake.pdf",
                "path_aliases": ["./raw/fake.pdf", "raw\\fake.pdf"],
                "type": "news-snapshot",
                "domain": "fake",
            }

            issues = validate_source_frontmatter_against_registry(
                "source--fake",
                frontmatter,
                registry_entry,
                contract,
            )
            self.assertEqual(issues, [])

    def test_validate_source_frontmatter_against_registry_reports_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            contract = policy["frontmatter_contract"]

            frontmatter = {
                "corpus": "system",
                "registry_id": "R-100",
                "raw_path": "raw/other.pdf",
                "source_type": "domain-research-paper",
                "domain": "other",
            }
            registry_entry = {
                "target_page": "source--fake",
                "corpus": "wiki",
                "registry_id": "R-100",
                "storage_path": "raw/fake.pdf",
                "type": "news-snapshot",
                "domain": "fake",
            }

            issues = validate_source_frontmatter_against_registry(
                "source--fake",
                frontmatter,
                registry_entry,
                contract,
            )
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["type"], "source_frontmatter_registry_mismatch")
            self.assertIn("corpus", issues[0]["detail"])
            self.assertIn("raw_path", issues[0]["detail"])
            self.assertIn("source_type", issues[0]["detail"])
            self.assertIn("domain", issues[0]["detail"])


if __name__ == "__main__":
    unittest.main()
