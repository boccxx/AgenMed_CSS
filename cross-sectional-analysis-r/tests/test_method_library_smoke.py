from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class MethodLibrarySmokeTests(unittest.TestCase):
    def test_interaction_and_dose_response_run_in_all_design_modes(self):
        rscript = shutil.which("Rscript")
        if not rscript:
            self.skipTest("Rscript is unavailable")
        skill_root = Path(__file__).resolve().parents[1]
        dependency_probe = subprocess.run(
            [
                rscript,
                "-e",
                "quit(status=ifelse(all(vapply(c('survey','readr','dplyr','ggplot2','jsonlite','showtext'), requireNamespace, logical(1), quietly=TRUE)),0,2))",
            ],
            cwd=skill_root,
            capture_output=True,
            text=True,
        )
        if dependency_probe.returncode == 2:
            self.skipTest("Required R analysis packages are unavailable")
        self.assertEqual(dependency_probe.returncode, 0, dependency_probe.stderr)

        run = subprocess.run(
            [rscript, "tests/smoke_method_library.R"],
            cwd=skill_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stdout + "\n" + run.stderr)
        self.assertIn("METHOD_LIBRARY_SMOKE=PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
