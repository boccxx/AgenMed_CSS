from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analysis_plan import build_contract, objective_stage_outputs  # noqa: E402


class MultiobjectiveContractIsolationTests(unittest.TestCase):
    def test_objective_specific_missingness_and_adjustment_do_not_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "analysis" / "profile"
            profile_dir.mkdir(parents=True)
            (profile_dir / "data_profile.json").write_text(json.dumps({
                "schema": [], "missingness_by_column": {}, "profile_scope": "full_dataset"
            }), encoding="utf-8")
            requested = {"study_identity": {"decision_id": "D1", "study_title": "Study", "project_mode": "research"}, "design_context_requested": {}}
            executable = {"objectives": [
                {"objective_id": "OBJ1", "priority": "secondary", "exposure_var": "x1", "outcome_var": "y", "effect_measure": "beta", "missing_data_strategy": "complete case", "adjustment_set": ["age"]},
                {"objective_id": "OBJ2", "priority": "primary", "exposure_var": "x2", "outcome_var": "y", "effect_measure": "beta", "missing_data_strategy": "MICE", "adjustment_set": ["age", "sex"]},
            ], "design_mode": "sample", "design_verified_level": "sample_based", "executable_stage_set": {}}
            contract = build_contract(root, requested, executable)
        self.assertEqual(contract["primary_exposure"]["objective_id"], "OBJ2")
        self.assertFalse(contract["missing_data_policy"]["by_objective"]["OBJ1"]["pooling_required"])
        self.assertTrue(contract["missing_data_policy"]["by_objective"]["OBJ2"]["pooling_required"])
        self.assertEqual(contract["adjustment_policy"]["by_objective"]["OBJ1"]["adjustment_set"], ["age"])
        self.assertEqual(contract["adjustment_policy"]["by_objective"]["OBJ2"]["adjustment_set"], ["age", "sex"])

    def test_multiobjective_outputs_are_objective_namespaced(self):
        one = objective_stage_outputs("primary_model_stage", "OBJ1", True)
        two = objective_stage_outputs("primary_model_stage", "OBJ2", True)
        self.assertNotEqual(one, two)
        self.assertIn("OBJ1_", one[0])
        self.assertIn("OBJ2_", two[0])


if __name__ == "__main__":
    unittest.main()
