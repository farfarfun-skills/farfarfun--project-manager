import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.architecture_design_checker import analyze_design
from scripts.artifact_consistency_checker import analyze_feature
from scripts.document_bundle import (
    extract_bullet_value,
    extract_list_items,
    extract_table_rows,
    split_sections,
    split_subsections,
)
from scripts.feature_doc_bootstrap import bootstrap
from scripts.test_case_checker import analyze_test_cases


SKILL_ROOT = Path(__file__).resolve().parents[1]


class CoreCheckerTests(unittest.TestCase):
    def test_shared_markdown_parser_preserves_checker_contract(self) -> None:
        markdown = """# Feature

## 1. Basic

- Owner: team-a

## 2. Scope

### Included

- Checkout

| ID | Status |
| --- | --- |
| A-1 | Ready |
"""
        sections = split_sections(markdown)

        self.assertEqual("team-a", extract_bullet_value(sections["1. Basic"], "Owner"))
        self.assertEqual(["Checkout"], extract_list_items(split_subsections(sections["2. Scope"])["Included"]))
        self.assertEqual([["A-1", "Ready"]], extract_table_rows(sections["2. Scope"]))

    def test_empty_architecture_and_test_case_documents_block(self) -> None:
        architecture = analyze_design("")
        test_cases = analyze_test_cases("")

        self.assertEqual("block", architecture["normalized_decision"])
        self.assertIn("linkage.missing", {item["code"] for item in architecture["findings"]})
        self.assertEqual("block", test_cases["normalized_decision"])
        self.assertIn("cases.missing", {item["code"] for item in test_cases["findings"]})

    def test_artifact_consistency_requires_only_current_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            prd = workspace / "docs/product/checkout"
            prd.mkdir(parents=True)
            (prd / "001-overview.md").write_text("# 结账功能\n", encoding="utf-8")

            self.assertEqual("allow", analyze_feature(workspace, "checkout", "intake")["normalized_decision"])
            self.assertEqual("block", analyze_feature(workspace, "checkout", "design")["normalized_decision"])

    def test_feature_governance_cli_runs_real_intake_checkers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            bootstrap(workspace, "checkout", "SHOP-1", overwrite=False)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts/feature_governance_check.py"),
                    "--workspace",
                    str(workspace),
                    "--feature",
                    "checkout",
                    "--stage",
                    "intake",
                    "--format",
                    "json",
                    "--fail-on",
                    "block",
                ],
                capture_output=True,
                text=True,
            )

            report = json.loads(completed.stdout)
            modules = {item["module"] for item in report["modules"]}
            self.assertEqual(1, completed.returncode, completed.stderr)
            self.assertEqual("block", report["normalized_decision"])
            self.assertEqual(
                {"project-status-checker", "prd-qa-checker", "artifact-consistency-checker"},
                modules,
            )


if __name__ == "__main__":
    unittest.main()
