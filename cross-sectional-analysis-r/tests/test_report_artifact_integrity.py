from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from analysis_audit import evaluate_report_artifact_integrity  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReportArtifactIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.report_dir = self.root / "analysis" / "output" / "report"
        self.figure_dir = self.root / "analysis" / "output" / "figures"
        self.table_dir = self.root / "analysis" / "output" / "tables"
        self.registry_dir = self.root / "registries"
        for directory in (self.report_dir, self.figure_dir, self.table_dir, self.registry_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.main_figure = self.figure_dir / "main.png"
        self.main_figure.write_bytes(b"main-figure-bytes")
        self.supplement_figure = self.figure_dir / "supplement.png"
        self.supplement_figure.write_bytes(b"supplement-figure-bytes")
        self.table = self.table_dir / "table1.csv"
        self.table.write_text("measure,value\nn,10\n", encoding="utf-8")

        self.write_registries()

    def tearDown(self):
        self.tempdir.cleanup()

    def write_registries(self, figures: list[dict] | None = None, tables: list[dict] | None = None) -> None:
        figures = figures if figures is not None else [
            {
                "figure_id": "FIG001",
                "registry_role": "main_text",
                "source_path": str(self.main_figure),
                "sha256": digest(self.main_figure),
            },
            {
                "figure_id": "FIG002",
                "registry_role": "supplement",
                "source_path": str(self.supplement_figure),
                "sha256": digest(self.supplement_figure),
            },
        ]
        tables = tables if tables is not None else [
            {
                "table_id": "TAB001",
                "registry_role": "main_text",
                "source_path": str(self.table),
                "sha256": digest(self.table),
            }
        ]
        (self.registry_dir / "figure_registry.json").write_text(json.dumps(figures), encoding="utf-8")
        (self.registry_dir / "table_registry.json").write_text(json.dumps(tables), encoding="utf-8")

    def write_report(self, text: str) -> None:
        (self.report_dir / "statistical_analysis_report.md").write_text(text, encoding="utf-8")

    def test_valid_report_passes(self):
        self.write_report(
            "# Report\n\n"
            "### Table 1. Characteristics\n\n"
            "### Figure 1. Main distribution\n\n"
            "![Main distribution](../figures/main.png)\n"
        )
        audit = evaluate_report_artifact_integrity(self.root)
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["counts"]["registered_main_text_figures"], 1)

    def test_missing_duplicate_unregistered_and_hash_mismatch_fail(self):
        extra = self.figure_dir / "extra.png"
        extra.write_bytes(b"unregistered")
        self.write_report(
            "# Report\n\n"
            "![Main](../figures/main.png)\n"
            "![Main again](../figures/main.png)\n"
            "![Extra](../figures/extra.png)\n"
            "![Missing](../figures/missing.png)\n"
        )
        self.write_registries(
            figures=[
                {
                    "figure_id": "FIG001",
                    "registry_role": "main_text",
                    "source_path": str(self.main_figure),
                    "sha256": "0" * 64,
                }
            ]
        )
        audit = evaluate_report_artifact_integrity(self.root)
        self.assertEqual(audit["status"], "fail")
        combined = "\n".join(audit["errors"])
        self.assertIn("registry SHA-256 does not match", combined)
        self.assertIn("must be embedded exactly once; found 2", combined)
        self.assertIn("Markdown image is not registered", combined)
        self.assertIn("Markdown image path does not exist", combined)

    def test_explicit_numbering_must_be_unique_and_continuous(self):
        self.write_report(
            "# Report\n\n"
            "### 表1 基线\n\n"
            "### Table 1. Duplicate\n\n"
            "### 表3 敏感性\n\n"
            "### 图2 分布\n\n"
            "![Main](../figures/main.png)\n"
        )
        audit = evaluate_report_artifact_integrity(self.root)
        self.assertEqual(audit["status"], "fail")
        combined = "\n".join(audit["errors"])
        self.assertIn("table numbering contains duplicate values", combined)
        self.assertIn("table numbering is not continuous from 1; missing: [2]", combined)
        self.assertIn("figure numbering is not continuous from 1; missing: [1]", combined)

    def test_image_alt_captions_and_alphanumeric_table_suffixes_are_valid(self):
        self.write_report(
            "# Report\n\n"
            "### 表1 基线\n\n"
            "### 表1A 扩展基线\n\n"
            "图1展示主要分布。\n\n"
            "![图1 主图](../figures/main.png)\n"
        )
        audit = evaluate_report_artifact_integrity(self.root)
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["counts"]["explicit_figure_numbers"], 2)


if __name__ == "__main__":
    unittest.main()
