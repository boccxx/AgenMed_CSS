from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from design_intake import (  # noqa: E402
    REQUIRED_ANALYSIS_STAGE_ORDER,
    validate_design_intake,
)


def bias_control(domain: str) -> dict:
    return {
        "objective_id": "OBJ_ASSOC",
        "bias_domain": domain,
        "mechanism": f"prespecified {domain} mechanism",
        "design_control": "prespecified design control",
        "field_control": "field quality-control procedure",
        "analysis_control": "registered analysis mitigation",
        "sensitivity_output": "registered domain-specific sensitivity table",
        "monitoring_indicator": "domain-specific process indicator",
        "threshold": "registered threshold",
        "action": "mandatory query, correction, sensitivity analysis, or release block",
        "residual_risk": "residual uncertainty will be reported",
    }


def valid_intake() -> dict:
    return {
        "project_mode": "research",
        "study_objectives": [
            {
                "objective_id": "OBJ_ASSOC",
                "objective_type": "association",
                "framework": "PECO",
                "adjustment_strategy": {
                    "common_sample_rule": "Use complete cases on the union of variables required by the M2 formula for all three models.",
                    "model_sequence": [
                        {"level": "M0", "analysis_sample_id": "AS_M2_CC", "adjustment_set": []},
                        {"level": "M1_available", "analysis_sample_id": "AS_M2_CC", "adjustment_set": ["age", "sex", "site"]},
                        {"level": "M2_available", "analysis_sample_id": "AS_M2_CC", "adjustment_set": ["age", "sex", "site", "smoking", "alcohol"]},
                    ],
                },
            }
        ],
        "sampling_plan": {
            "canonical_design_name": "Fixed-site stratified multistage cluster probability sampling within selected sites",
            "stratification_variables": ["economic_circle"],
            "stages": [
                {
                    "stage_id": "SITE",
                    "order": 1,
                    "unit": "study site",
                    "frame": "named study sites",
                    "selection_type": "fixed",
                    "selection_method": "sites fixed a priori for coverage of three economic circles",
                    "id_variable": "site_id",
                },
                {
                    "stage_id": "PSU",
                    "order": 2,
                    "unit": "community cluster",
                    "frame": "dated community roster within each site",
                    "selection_type": "probability",
                    "selection_method": "simple random sampling without replacement",
                    "probability_formula": "selected communities / eligible communities in site",
                    "id_variable": "psu_id",
                    "is_psu": True,
                },
                {
                    "stage_id": "PERSON",
                    "order": 3,
                    "unit": "eligible older resident",
                    "frame": "dated eligible-person roster within selected communities",
                    "selection_type": "probability",
                    "selection_method": "simple random sampling without replacement",
                    "probability_formula": "selected persons / eligible persons in community",
                    "id_variable": "participant_id",
                },
            ],
            "probability_chain_complete": False,
            "analysis_design": {
                "strata_variable": "economic_circle",
                "psu_variable": "psu_id",
                "weight_variable": "final_weight",
                "variance_estimator": "Taylor linearization conditional on the selected sites",
            },
            "inference_boundary": {
                "scope": "selected_sites_only",
                "statement": "Population inference is conditional on the three fixed study sites and does not establish province-wide representativeness.",
                "representativeness_claim": "Representative of the enumerated source frames within the selected sites only",
            },
        },
        "measurement_plan": {
            "instrument_details": [
                {
                    "variable": "cognition_score",
                    "instrument_type": "scale",
                    "source_type": "validated_existing",
                    "instrument": "Validated cognition scale",
                    "source_reference": "PMID:12345678",
                    "version": "Version 2",
                    "language": "validated Chinese translation",
                    "license_status": "public_domain",
                    "scoring": "Sum the registered items according to the official scoring manual.",
                    "item_missing_rule": "No prorating; any missing scored item makes the total missing.",
                    "appendix": {
                        "status": "included",
                        "items": [
                            {"item_id": "Q1", "wording": "Registered item text", "response_options": ["0", "1"], "skip_logic": "none"}
                        ],
                    },
                },
                {
                    "variable": "radial_bmd",
                    "instrument_type": "device_measurement",
                    "source_type": "device_measurement",
                    "instrument": "Peripheral DXA",
                    "version": "LS-100",
                    "language": "not applicable",
                    "scoring": "Use the frozen device and ROI derivation rule.",
                    "item_missing_rule": "A failed quality-control scan is missing and is not replaced by self-report.",
                },
            ]
        },
        "data_linkage_plan": {
            "status": "required",
            "sources": [
                {"source_id": "FIELD", "snapshot_or_period": "fieldwork freeze", "unit": "participant"},
                {"source_id": "PLATFORM", "snapshot_or_period": "frozen historical examination window", "unit": "participant examination"},
            ],
            "linkage_keys": ["encrypted_participant_linkage_id"],
            "linkage_method": "deterministic exact linkage in a segregated trusted service",
            "temporal_window": "use the nearest eligible examination before the BMD visit within the frozen look-back window",
            "duplicate_resolution": "apply the prespecified nearest-date and completeness hierarchy",
            "unmatched_rule": "retain the field record, flag platform variables missing, and report linkage yield",
            "quality_checks": ["unique key check", "one-to-many reconciliation", "linkage yield by site"],
            "privacy_separation": "linkage identifiers are removed before the analysis extract is released",
        },
        "bias_control_plan": {
            "controls": [
                bias_control("selection_bias"),
                bias_control("information_bias"),
                bias_control("confounding"),
                bias_control("missing_data"),
            ]
        },
        "analysis_plan": {"analysis_sequence": list(REQUIRED_ANALYSIS_STAGE_ORDER)},
    }


class DesignIntakeSemanticValidatorTests(unittest.TestCase):
    def test_complete_research_intake_passes(self):
        audit = validate_design_intake(valid_intake())
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["errors"], [])

    def test_fixed_site_sampling_cannot_claim_province_wide_inference(self):
        intake = valid_intake()
        intake["sampling_plan"]["probability_chain_complete"] = True
        intake["sampling_plan"]["inference_boundary"] = {
            "scope": "full_target_population",
            "statement": "Inference is intended for the province.",
            "representativeness_claim": "Province-wide representative sample",
        }
        audit = validate_design_intake(intake)
        self.assertEqual(audit["status"], "fail")
        joined = "\n".join(audit["errors"])
        self.assertIn("probability_chain_complete must be false", joined)
        self.assertIn("overstates coverage", joined)

    def test_missing_measurement_linkage_bias_and_wrong_order_are_blocking(self):
        intake = valid_intake()
        intake["measurement_plan"]["instrument_details"][0].pop("license_status")
        intake.pop("data_linkage_plan")
        intake["bias_control_plan"]["controls"] = [bias_control("selection_bias")]
        intake["analysis_plan"]["analysis_sequence"] = list(reversed(REQUIRED_ANALYSIS_STAGE_ORDER))
        audit = validate_design_intake(intake)
        self.assertEqual(audit["status"], "fail")
        joined = "\n".join(audit["errors"])
        self.assertIn("license_status", joined)
        self.assertIn("data_linkage_plan is required", joined)
        self.assertIn("lacks the information domain", joined)
        self.assertIn("not in the frozen execution order", joined)

    def test_m0_m1_m2_must_share_sample_and_be_nested(self):
        intake = valid_intake()
        sequence = intake["study_objectives"][0]["adjustment_strategy"]["model_sequence"]
        sequence[0]["adjustment_set"] = ["post_treatment_variable"]
        sequence[2]["analysis_sample_id"] = "AS_M2_DIFFERENT"
        audit = validate_design_intake(intake)
        self.assertEqual(audit["status"], "fail")
        joined = "\n".join(audit["errors"])
        self.assertIn("must use the same analysis_sample_id", joined)
        self.assertIn("M0 adjustment set must be nested within M1", joined)

    def test_cli_writes_failure_json_and_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_path = root / "intake.json"
            output_path = root / "audit.json"
            bad = deepcopy(valid_intake())
            bad.pop("sampling_plan")
            intake_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "design_intake.py"),
                    "validate_design_intake_semantics",
                    str(intake_path),
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertTrue(output_path.is_file())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertIn(str(intake_path.resolve()), payload["input_sha256"])


if __name__ == "__main__":
    unittest.main()
