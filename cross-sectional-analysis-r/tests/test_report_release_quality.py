from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analysis_report import evaluate_report_release  # noqa: E402


def result(**overrides):
    row = {
        "result_id": "RES001",
        "label": "Primary association",
        "stage_id": "primary_model_stage",
        "effect_measure": "mean difference",
        "estimate": 0.2,
        "ci_lower": 0.004,
        "ci_upper": 0.396,
        "p_value": 0.046,
        "adjustment_set": ["age", "sex"],
        "inference_basis": {
            "standard_error": 0.1,
            "confidence_level": 0.95,
            "reference_distribution": "normal",
            "p_reference_distribution": "normal",
            "critical_value": 1.96,
            "sidedness": "two-sided",
            "exponentiated": False,
        },
    }
    row.update(overrides)
    return row


def bundle(mode="scientific_release", results=None, design=None):
    diagnostic_values = {
        "n_obs": 500,
        "residual_df": 495,
        "parameter_count": 5,
        "convergence": "pass",
        "residual_summary": {"median": 0.0, "maximum": 2.1},
        "max_leverage": 0.04,
        "functional_form": {"status": "pass", "test": "restricted cubic spline comparison"},
    }
    return {
        "execution_state": {
            "analysis_release_mode": mode,
            "inferential_adequacy": {"status": "pass", "rationale": "Events, parameters, and residual df were adequate."},
            "sensitivity_axes": ["model_family", "missing_data", "influence"],
        },
        "profile": {"profile_scope": "full_dataset", "n_rows_profiled": 500, "sample_rows_read": 500},
        "core": {
            "study_identity": {"decision_id": "DEC001"},
            "design_context": design or {"design_mode": "sample", "weight_variable": ""},
        },
        "results": results or [result()],
        "diagnostics": [
            {"diagnostic_type": name, "diagnostic_value": value} for name, value in diagnostic_values.items()
        ],
        "tables": [
            {"registry_role": "main_text", "caption": f"Observed table {index}"} for index in range(6)
        ],
        "figures": [
            {"registry_role": "main_text", "caption": f"Figure {index}"} for index in range(3)
        ],
    }


class ReportReleaseQualityTests(unittest.TestCase):
    def test_rejects_mixed_ci_and_p_reference_distributions(self):
        bad = result()
        bad["inference_basis"]["p_reference_distribution"] = "student_t"
        audit = evaluate_report_release(bundle(results=[bad]))
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(any("CI uses" in item for item in audit["errors"]))

    def test_rejects_adjusted_claim_without_adjustment_evidence(self):
        audit = evaluate_report_release(bundle(results=[result(label="Adjusted association", adjustment_set=[])]))
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(any("adjusted claim" in item for item in audit["errors"]))

    def test_rejects_weighted_caption_for_unweighted_sample(self):
        candidate = bundle()
        candidate["tables"][0]["caption"] = "Weighted baseline characteristics"
        audit = evaluate_report_release(candidate)
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(any("weighted reporting language" in item for item in audit["errors"]))

    def test_demo_requires_banner_and_rejects_confirmatory_language(self):
        candidate = bundle(mode="demonstration_only")
        audit = evaluate_report_release(candidate, "Confirmatory model output")
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(any("non-inference banner" in item for item in audit["errors"]))
        self.assertTrue(any("research-grade" in item for item in audit["errors"]))

    def test_demo_passes_with_explicit_non_inference_text(self):
        candidate = bundle(mode="demonstration_only")
        text = "DEMONSTRATION ONLY — NOT FOR SCIENTIFIC INFERENCE\nIllustrative values verify workflow traceability only."
        audit = evaluate_report_release(candidate, text)
        self.assertEqual(audit["status"], "demonstration_pass")

    def test_scientific_report_requires_body_depth_and_embedded_tables(self):
        audit = evaluate_report_release(bundle(), "short body")
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(any("hard floor" in item for item in audit["errors"]))
        self.assertTrue(any("embeds no numerical" in item for item in audit["errors"]))

    def test_complete_scientific_contract_can_pass(self):
        body = "\n\n".join(
            ("evidence " * 340) + f"paragraph{paragraph}"
            for paragraph in range(12)
        )
        body += "\n| measure | value |\n| --- | --- |\n| analytic_n | 500 |"
        audit = evaluate_report_release(bundle(), body)
        self.assertEqual(audit["status"], "scientific_pass")

    def test_complete_chinese_scientific_contract_can_pass(self):
        body = "\n\n".join(
            ("本段报告抽样设计数据质量变量定义统计方法结果解释局限性。" * 18)
            + str(paragraph)
            for paragraph in range(12)
        )
        body += "\n| 指标 | 数值 |\n| --- | --- |\n| 分析人数 | 500 |"
        audit = evaluate_report_release(bundle(), body)
        self.assertEqual(audit["status"], "scientific_pass")

    def test_repeated_substantive_paragraphs_fail(self):
        repeated = "研究方法结果诊断敏感性分析与局限性均按预先规定流程完成。" * 8
        body = "\n\n".join([repeated, repeated] + [
            ("这是不同的完整结果段落用于说明报告深度与可核查性。" * 18) + str(i)
            for i in range(10)
        ])
        body += "\n| 指标 | 数值 |\n| --- | --- |\n| 分析人数 | 500 |"
        audit = evaluate_report_release(bundle(), body)
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(any("repeated substantive" in item for item in audit["errors"]))

    def test_real_data_provisional_report_keeps_blockers_without_becoming_demo(self):
        candidate = bundle()
        candidate["execution_state"]["report_delivery_class"] = "provisional_blocked_review"
        candidate["execution_state"]["inferential_adequacy"] = {
            "status": "blocked", "rationale": "PSU and strata identifiers are unavailable."
        }
        text = "PROVISIONAL — NOT FOR FINAL SCIENTIFIC INFERENCE\n\nObserved-data description only."
        audit = evaluate_report_release(candidate, text)
        self.assertEqual(audit["status"], "provisional_pass")
        self.assertTrue(any("inferential_adequacy" in item for item in audit["release_blockers"]))

    def test_provisional_report_requires_banner(self):
        candidate = bundle()
        candidate["execution_state"]["report_delivery_class"] = "provisional_blocked_review"
        audit = evaluate_report_release(candidate, "ordinary report")
        self.assertEqual(audit["status"], "fail")
        self.assertTrue(any("blocker banner" in item for item in audit["errors"]))


if __name__ == "__main__":
    unittest.main()
