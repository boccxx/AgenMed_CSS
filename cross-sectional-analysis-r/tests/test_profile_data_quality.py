from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analysis_common import profile_csv  # noqa: E402


class ProfileDataQualityTests(unittest.TestCase):
    def test_profiles_ids_parse_weights_levels_and_nesting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            path.write_text(
                "participant_id,stratum,psu,analysis_weight,raw_group,numeric_text\n"
                "1,A,1,1.0,x,10\n"
                "1,A,1,0,x,bad\n"
                "2,B,1,-2,y,12\n"
                "3,B,2,3.0,y,13\n",
                encoding="utf-8",
            )
            profile = profile_csv(path)
        self.assertEqual(profile["identifier_candidates"][0]["n_duplicated_nonmissing"], 2)
        self.assertEqual(profile["weight_diagnostics"]["analysis_weight"]["n_zero"], 1)
        self.assertEqual(profile["weight_diagnostics"]["analysis_weight"]["n_negative"], 1)
        self.assertEqual(profile["parse_diagnostics"]["numeric_text"]["n_parse_failures"], 1)
        self.assertEqual(profile["raw_levels"]["raw_group"]["n_unique"], 2)
        self.assertEqual(profile["design_nesting_diagnostics"][0]["psus_in_multiple_strata"], 1)


if __name__ == "__main__":
    unittest.main()
