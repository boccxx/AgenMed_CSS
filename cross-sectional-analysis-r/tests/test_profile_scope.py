from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from analysis_common import profile_csv  # noqa: E402


class ProfileScopeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.csv = Path(self.tempdir.name) / "data.csv"
        self.csv.write_text(
            "id,weight,stratum,psu,x\n"
            + "".join(f"{index},{1 + index / 100:.2f},{index % 4},{index % 8},{'' if index == 249 else index}\n" for index in range(1, 301)),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_default_profiles_entire_dataset(self):
        profile = profile_csv(self.csv)
        self.assertEqual(profile["profile_scope"], "full_dataset")
        self.assertEqual(profile["n_rows_profiled"], 300)
        self.assertEqual(profile["missingness_by_column"]["x"]["n_missing"], 1)

    def test_explicit_sample_is_marked_nonrelease(self):
        profile = profile_csv(self.csv, sample_rows=200)
        self.assertEqual(profile["profile_scope"], "sampled_nonrelease")
        self.assertEqual(profile["n_rows_profiled"], 200)


if __name__ == "__main__":
    unittest.main()
