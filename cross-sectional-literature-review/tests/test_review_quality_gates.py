from __future__ import annotations

import importlib.util
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_module("review_validator", SKILL_ROOT / "scripts" / "validation.py")
extraction = load_module("fulltext_extraction", SKILL_ROOT / "scripts" / "evidence.py")
semantic = validator


class ReviewQualityGateTests(unittest.TestCase):
    def test_metadata_only_raw_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw_results").mkdir()
            payload = {
                "search_id": "S001", "source": "PubMed", "query": "x",
                "source_query": "x", "exported_count": 1,
            }
            (root / "raw_results" / "S001.json").write_text(json.dumps(payload), encoding="utf-8")
            log_fields = ["search_id", "source", "query", "source_query", "status", "raw_file", "n_exported", "api_total_hits", "n_after_dedup"]
            with (root / "search_log.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=log_fields)
                writer.writeheader()
                writer.writerow({"search_id": "S001", "source": "PubMed", "query": "x", "source_query": "x", "status": "retrieved", "raw_file": "raw_results/S001.json", "n_exported": "1", "api_total_hits": "1", "n_after_dedup": "1"})
            candidate_fields = ["search_id", "source_record_id", "doi", "title", "abstract"]
            for name in ("candidate_records_raw.csv", "candidate_records_dedup.csv"):
                with (root / name).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=candidate_fields)
                    writer.writeheader()
                    writer.writerow({"search_id": "S001", "source_record_id": "1", "doi": "10.1/x", "title": "A substantive candidate", "abstract": "A" * 100})
            errors = semantic.validate_semantics(root)
            self.assertTrue(any("metadata-only" in error and "exported_records" in error for error in errors))

    def test_validator_imports_by_file_path_outside_scripts_directory(self) -> None:
        code = f'''\nimport importlib.util\nfrom pathlib import Path\npath = Path({str(SKILL_ROOT / "scripts" / "validation.py")!r})\nspec = importlib.util.spec_from_file_location("standalone_review_validator", path)\nmodule = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\nassert callable(module.validate_semantics)\n'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(tempfile.gettempdir()),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scaffold_routes_systematic_no_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "topic.json"
            cfg.write_text(
                json.dumps(
                    {
                        "review_type": "systematic_no_meta",
                        "question_type": "exposure_outcome_association",
                        "harvest": {"outcomes": ["Depressive symptoms"]},
                    }
                ),
                encoding="utf-8",
            )
            output = root / "review"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "review.py"),
                    "build_review_scaffold",
                    str(output),
                    "--topic-config",
                    str(cfg),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            methods = json.loads((output / "methods_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(methods["review_type"], "systematic_no_meta")
            self.assertIn("SWiM", methods["reporting_framework"])
            narrative = (output / "literature_review_synthesis.md").read_text(encoding="utf-8")
            self.assertIn("# Evidence Map and Study Characteristics", narrative)
            self.assertIn("# Effect Evidence Matrix", narrative)

    def test_placeholder_executed_query_is_rejected(self) -> None:
        rows = [
            {
                "status": "retrieved",
                "source_query": "exposure AND outcome",
                "date_searched": "2026-07-19",
                "n_retrieved": "",
                "n_after_dedup": "",
            }
        ]
        errors = validator.check_search_execution(rows, completed=True)
        self.assertTrue(any("placeholder" in error for error in errors))
        self.assertTrue(any("n_retrieved" in error for error in errors))

    def test_placeholder_search_strategy_is_rejected(self) -> None:
        errors = validator.check_search_strategy_document(
            "# Search Strategy\nPubMed\nTODO: add final dates and retrieved records",
            completed=True,
        )
        self.assertTrue(any("placeholder" in error for error in errors))
        self.assertTrue(any("search date" in error for error in errors))

    def test_wrong_review_type_framework_is_rejected(self) -> None:
        contract = {
            "review_type": "systematic_no_meta",
            "reporting_framework": ["SANRA"],
            "synthesis_method": "narrative overview",
        }
        errors = validator.check_review_type_route(contract)
        self.assertTrue(any("PRISMA" in error for error in errors))
        self.assertTrue(any("SWiM" in error for error in errors))

    def test_empty_appraisal_is_rejected(self) -> None:
        errors = validator.check_quality_appraisal([], {"P001"}, completed=True)
        self.assertEqual(errors, ["completed review requires non-empty quality_appraisal_registry.csv"])

    def test_templated_appraisal_is_rejected(self) -> None:
        rows = []
        for paper_id in ("P001", "P002"):
            for domain in ("selection", "measurement", "confounding", "reporting"):
                rows.append(
                    {
                        "paper_id": paper_id,
                        "domain": domain,
                        "judgment": "moderate",
                        "raw_signal": "same generic signal",
                        "evidence_source": "Methods",
                        "note": "same generic note",
                    }
                )
        errors = validator.check_quality_appraisal(rows, {"P001", "P002"}, completed=True)
        self.assertTrue(any("template text" in error for error in errors))

    def test_cross_sectional_appraisal_requires_reverse_causation(self) -> None:
        rows = [
            {"paper_id": "P001", "domain": domain, "judgment": "moderate", "raw_signal": f"signal {domain}", "evidence_source": f"Methods {domain}", "note": ""}
            for domain in ("selection", "exposure measurement", "outcome measurement", "confounding")
        ]
        errors = validator.check_quality_appraisal(
            rows,
            {"P001"},
            completed=True,
            design_by_paper={"P001": "cross-sectional"},
        )
        self.assertTrue(any("reverse causation" in error for error in errors))

    def test_full_text_exclusion_requires_specific_reason_code(self) -> None:
        rows = [
            {
                "paper_id": "P001",
                "decision": "exclude",
                "screening_stage": "full_text",
                "reason": "No",
                "exclusion_reason_code": "",
            }
        ]
        errors = validator.check_screening_accounting(rows, completed=True, sparse_ok=True)
        self.assertTrue(any("specific reason" in error for error in errors))
        self.assertTrue(any("exclusion_reason_code" in error for error in errors))

    def test_mature_release_requires_references_and_deep_reads(self) -> None:
        contract = {"delivery_preset": "decision_grade"}
        citations = [{"doi": f"10.1/{index}"} for index in range(10)]
        fulltexts = [
            {"paper_id": f"P{index}", "deep_read_completed": "yes"}
            for index in range(5)
        ]
        errors = validator.check_depth_and_reference_floor(contract, citations, fulltexts, completed=True)
        self.assertTrue(any("30" in error for error in errors))
        self.assertTrue(any("12" in error for error in errors))

    def test_sparse_exception_must_be_complete(self) -> None:
        ok, error = validator.sparse_exception(
            {"sparse_evidence_exception": {"applies": True, "rationale": "Only two studies"}}
        )
        self.assertFalse(ok)
        self.assertIn("search_saturation", error)

    def test_effect_coverage_requires_interval_or_explicit_nr(self) -> None:
        studies = [
            {"paper_id": "P1", "primary_role": "anchor"},
            {"paper_id": "P2", "primary_role": "counterevidence"},
        ]
        effects = [{"paper_id": "P1", "point_estimate": "1.2", "ci_lower": "", "ci_upper": ""}]
        errors = validator.check_effect_coverage(studies, effects, completed=True)
        self.assertTrue(any("80%" in error for error in errors))

    def test_main_body_tables_must_be_populated(self) -> None:
        text = """# Evidence Map and Study Characteristics

| Study | Design |
|---|---|
| TODO | TODO |

# Effect Evidence Matrix

| Study | Effect |
|---|---|
| P1 | 1.2 |
"""
        errors = validator.check_embedded_evidence_tables(text)
        self.assertEqual(len(errors), 2)

    def test_completed_extraction_requires_deep_read_and_four_domains(self) -> None:
        payload = {
            "paper_id": "P001",
            "review_status": "complete",
            "text_source": "abstract",
            "study_design": "cross-sectional",
            "population_summary": "Adults",
            "direct_question_match": "yes",
            "study_contribution": {
                "can_support": "association",
                "cannot_support": "causality",
                "main_limitation": "reverse causation",
            },
            "effect_rows": [],
            "bias_appraisal": [],
            "quality_appraisal": [],
        }
        errors = extraction.validate_packet(Path("P001.json"), payload)
        self.assertTrue(any("deep_read_date" in error for error in errors))
        self.assertTrue(any("full-text" in error for error in errors))
        self.assertTrue(any("4 distinct" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
