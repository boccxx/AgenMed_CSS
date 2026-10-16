from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analysis_common import load_structured  # noqa: E402
from analysis_plan import adjudicate  # noqa: E402


class FeasibilityVariableAndDesignGateTests(unittest.TestCase):
    def test_absent_required_variable_blocks_model_and_weight_only_has_bounded_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "analysis" / "profile"
            profile_dir.mkdir(parents=True)
            profile = {
                "schema": [{"name": "y", "n_unique": 10}, {"name": "w", "n_unique": 10}],
                "missingness_by_column": {"y": {"pct_missing": 0}, "w": {"pct_missing": 0}},
                "sparse_levels": {}, "binary_prevalence": {},
            }
            (profile_dir / "data_profile.json").write_text(json.dumps(profile), encoding="utf-8")
            plan = {
                "design_context_requested": {
                    "sampling_design": "multistage probability survey",
                    "survey_strategy": "survey weighted",
                    "weight_variable": "w", "strata_variable": "", "psu_variable": "",
                },
                "requested_objectives": [{
                    "objective_id": "OBJ001", "exposure_var": "missing_x", "outcome_var": "y",
                    "adjustment_set": [], "modifier_candidates": [], "requested_method_family": "continuous_linear",
                    "outcome_family": "continuous", "exposure_form": "continuous", "missing_data_strategy": "complete case",
                }],
            }
            rules = load_structured(Path(__file__).resolve().parents[1] / "contracts" / "adjudication_rules.yaml")
            result = adjudicate(root, plan, rules)
        obj = result["objectives"][0]
        self.assertEqual(obj["stage_map"]["primary_model_stage"]["status"], "blocked_by_data")
        self.assertEqual(obj["objective_data_availability"]["missing_required_variables"], ["missing_x"])
        self.assertEqual(result["design_capabilities"]["variance_estimation"], "formal_survey_variance_unavailable")
        self.assertEqual(result["design_capabilities"]["target_population_extrapolation"], "not_established_by_weights_alone")


if __name__ == "__main__":
    unittest.main()
