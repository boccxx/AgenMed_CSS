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

from analysis_registry import (  # noqa: E402
    figure_caption_and_legend,
    figure_registry,
    table_caption_and_note,
    table_registry,
)


class RegistryArtifactProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.table_dir = self.root / "tables"
        self.figure_dir = self.root / "figures"
        self.table_dir.mkdir()
        self.figure_dir.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _artifact(self, path: Path, objective: str = "OBJ001", **extra) -> dict:
        return {
            "source_path": str(path),
            "objective_id": objective,
            "stage_id": "descriptive_stage",
            "sha256": self._sha(path),
            **extra,
        }

    def test_hashes_and_explicit_table_provenance_are_registered(self):
        table_a = self.table_dir / "Table_A.csv"
        table_b = self.table_dir / "Table_B.csv"
        figure = self.figure_dir / "Figure_Distribution.png"
        table_a.write_text("term,estimate\na,1\n", encoding="utf-8")
        table_b.write_text("term,estimate\nb,2\n", encoding="utf-8")
        figure.write_bytes(b"not-a-render-test-but-stable-figure-bytes")
        summary = {
            "artifacts": [
                self._artifact(table_a),
                self._artifact(table_b),
                self._artifact(figure, source_table_paths=["Table_B.csv"]),
            ]
        }
        failures: list[str] = []
        tables = table_registry(
            self.table_dir, summary, ["OBJ001"], [], failures, "survey_weight_only"
        )
        figures = figure_registry(
            self.figure_dir,
            summary,
            ["OBJ001"],
            [],
            tables,
            failures,
            "survey_weight_only",
        )

        self.assertEqual(failures, [])
        table_b_id = next(
            row["table_id"] for row in tables if Path(row["source_path"]).name == "Table_B.csv"
        )
        self.assertEqual(figures[0]["source_table_ids"], [table_b_id])
        self.assertEqual(figures[0]["source_sha256"], self._sha(figure))
        self.assertTrue(all(row["source_sha256"] == self._sha(Path(row["source_path"])) for row in tables))

    def test_ambiguous_scope_never_binds_the_first_table(self):
        table_a = self.table_dir / "Table_A.csv"
        table_b = self.table_dir / "Table_B.csv"
        figure = self.figure_dir / "Figure_Distribution.png"
        table_a.write_text("x\n1\n", encoding="utf-8")
        table_b.write_text("x\n2\n", encoding="utf-8")
        figure.write_bytes(b"figure")
        summary = {
            "artifacts": [self._artifact(table_a), self._artifact(table_b), self._artifact(figure)]
        }
        failures: list[str] = []
        tables = table_registry(self.table_dir, summary, ["OBJ001"], [], failures)
        figures = figure_registry(
            self.figure_dir, summary, ["OBJ001"], [], tables, failures
        )

        self.assertEqual(figures[0]["source_table_ids"], [])
        self.assertTrue(any("ambiguous source tables" in item for item in failures))

    def test_cross_scope_table_declaration_is_rejected(self):
        table = self.table_dir / "Table_OBJ002.csv"
        figure = self.figure_dir / "Figure_OBJ001.png"
        table.write_text("x\n1\n", encoding="utf-8")
        figure.write_bytes(b"figure")
        summary = {
            "artifacts": [
                self._artifact(table, objective="OBJ002"),
                self._artifact(
                    figure, objective="OBJ001", source_table_paths=["Table_OBJ002.csv"]
                ),
            ]
        }
        failures: list[str] = []
        tables = table_registry(
            self.table_dir, summary, ["OBJ001", "OBJ002"], [], failures
        )
        figures = figure_registry(
            self.figure_dir,
            summary,
            ["OBJ001", "OBJ002"],
            [],
            tables,
            failures,
        )

        self.assertEqual(figures[0]["source_table_ids"], [])
        self.assertTrue(any("outside its objective/stage" in item for item in failures))

    def test_weight_only_registry_language_states_variance_boundary(self):
        table_parts = table_caption_and_note(
            "descriptive_stage", "Table_Baseline", "survey_weight_only"
        )
        figure_parts = figure_caption_and_legend(
            "descriptive_stage", "Figure_Distribution", "survey_weight_only"
        )
        table_text = " ".join(table_parts).lower()
        figure_text = " ".join(figure_parts).lower()

        for text in (table_text, figure_text):
            self.assertIn("supplied-weight point description", text)
            self.assertIn("formal survey variance unavailable", text)
            self.assertNotIn("design-weighted", text)
        self.assertIn("formal survey variance unavailable", table_parts[0].lower())
        self.assertIn("formal survey variance unavailable", figure_parts[0].lower())

        model_figure_text = " ".join(
            figure_caption_and_legend(
                "primary_model_stage", "Figure_Forest", "survey_weight_only"
            )
        ).lower()
        self.assertIn("individual-independence working intervals", model_figure_text)
        self.assertNotIn("confidence intervals", model_figure_text)

    def test_registry_schemas_require_hashes_and_figure_table_links(self):
        contracts = Path(__file__).resolve().parents[1] / "contracts"
        table_schema = json.loads((contracts / "table_registry_schema.json").read_text())
        figure_schema = json.loads((contracts / "figure_registry_schema.json").read_text())

        self.assertIn("source_sha256", table_schema["required_fields"])
        self.assertIn("source_sha256", figure_schema["required_fields"])
        self.assertIn("source_table_ids", figure_schema["required_fields"])


if __name__ == "__main__":
    unittest.main()
