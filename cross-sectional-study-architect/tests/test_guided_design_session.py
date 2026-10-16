from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from design_intake import (  # noqa: E402
    answer,
    authorize,
    initialize,
    validate_concept_parse,
)


CONCEPT = {
    "schema_version": "1.0",
    "session_id": "GUIDED_TEST",
    "generated_at": "2026-09-29",
    "source_text": "描述三个指定地区老年人的骨密度分布，并分析相关因素。",
    "user_intent": {"output_request": "none", "interaction_mode": "guided"},
    "study_focus": "三个指定地区老年人骨密度及相关因素",
    "extracted_items": [{"item_id": "ITEM1", "classification": "stated_fact"}],
    "candidate_objectives": [
        {
            "objective_id": "OBJ_BURDEN",
            "objective_label": "描述骨密度分布",
            "objective_family": "prevalence",
        },
        {
            "objective_id": "OBJ_ASSOC",
            "objective_label": "分析相关因素",
            "objective_family": "association",
        },
    ],
    "design_signals": {
        "mentions_probability_sampling": True,
        "mentions_stratification": True,
        "mentions_cluster_sampling": True,
        "mentions_multistage_sampling": False,
        "mentions_unequal_probability": False,
        "has_device_measurement": True,
        "has_scale_measurement": True,
        "has_multiple_data_sources": True,
        "has_continuous_outcome": True,
        "has_binary_outcome": True,
        "wants_broad_population_inference": True,
        "sites_fixed_by_narrative": True,
    },
    "known_information": {
        "population": ["研究地点为三个指定地区。"],
        "setting": ["三个指定地区。"],
        "sampling": ["拟采用分层整群随机抽样。"],
        "measurement": ["拟使用设备测量骨密度。"],
        "outcomes": ["连续骨密度和二分类骨质疏松状态。"],
        "exposures": ["生活方式和生化指标。"],
        "data_sources": ["现场测量和既往体检资料。"],
    },
    "methodological_tensions": [
        {
            "tension_id": "TENSION1",
            "topic": "external_validity",
            "description": "固定地点是否支持更大范围的代表性推断尚未证明。",
            "severity": "blocking",
            "linked_node_ids": ["2.1_population_trinity", "2.2_probability_decision"],
        }
    ],
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def initialize_example(output_dir: Path) -> None:
    concept_path = output_dir / "concept_parse.json"
    write_json(concept_path, CONCEPT)
    initialize(concept_path, output_dir)


def response_for(node_id: str, action: str = "confirm") -> dict:
    return {
        "node_id": node_id,
        "action": action,
        "options_considered": ["Option A", "Option B"],
        "recommended_option": "Option A",
        "user_choice": "Option A",
        "decision_statement": f"Confirmed design decision for {node_id}",
        "rationale_summary": "The choice follows the stated study objective and preserves downstream consistency.",
        "downstream_impacts": ["protocol", "SAP"],
        "evidence_references": ["user-confirmed design input"],
        "field_updates": {"confirmed_design": {node_id: "Option A"}},
    }


class GuidedDesignSessionTests(unittest.TestCase):
    def test_mixed_objectives_create_parallel_framework_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            initialize_example(out)
            session = read_json(out / "guided_design_session.json")
            node_ids = [item["node_id"] for item in session["route"]]
            self.assertIn("1.3_cocopop_specification", node_ids)
            self.assertIn("1.2_peco_specification", node_ids)
            self.assertIn("4.4_backdoor_criterion", node_ids)
            self.assertIn("5.5_data_linkage", node_ids)
            self.assertEqual(session["interaction_mode"], "guided")
            self.assertFalse(session["generation_authorized"])
            self.assertEqual(session["current_node_id"], "1.0_objective_triage")

    def test_fixed_sites_and_broad_inference_remain_visible_as_tension(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            initialize_example(out)
            session = read_json(out / "guided_design_session.json")
            tensions = session["methodological_tensions"]
            self.assertTrue(any(item["topic"] == "external_validity" and item["severity"] == "blocking" for item in tensions))
            population = next(item for item in session["route"] if item["node_id"] == "2.1_population_trinity")
            self.assertTrue(any("三个指定地区" in item for item in population["known_information"]))

    def test_one_blocking_question_at_a_time_and_no_early_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            initialize_example(out)
            confirmation = out / "confirmation.json"
            write_json(confirmation, {"user_confirmed_generation": True, "requested_outputs": ["protocol", "sap"]})
            with self.assertRaises(SystemExit):
                authorize(out / "guided_design_session.json", out / "decision_trace_registry.json", confirmation, out)

            response_path = out / "response.json"
            write_json(response_path, response_for("1.0_objective_triage"))
            answer(out / "guided_design_session.json", out / "decision_trace_registry.json", response_path, out)
            session = read_json(out / "guided_design_session.json")
            self.assertEqual(session["route"][0]["status"], "completed")
            self.assertNotEqual(session["current_node_id"], "1.0_objective_triage")
            self.assertFalse(session["generation_authorized"])
            draft = read_json(out / "design_intake_draft.json")
            self.assertEqual(draft["confirmed_design"]["1.0_objective_triage"], "Option A")

    def test_deferred_decision_returns_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            initialize_example(out)
            response_path = out / "response.json"
            write_json(response_path, response_for("1.0_objective_triage", action="defer"))
            answer(out / "guided_design_session.json", out / "decision_trace_registry.json", response_path, out)
            session = read_json(out / "guided_design_session.json")
            self.assertEqual(session["current_node_id"], "1.0_objective_triage")
            self.assertEqual(session["status"], "paused")
            self.assertFalse(session["generation_authorized"])

    def test_complete_route_can_be_authorized_only_after_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            initialize_example(out)
            response_path = out / "response.json"
            while True:
                session = read_json(out / "guided_design_session.json")
                node_id = session["current_node_id"]
                if node_id is None:
                    break
                write_json(response_path, response_for(node_id))
                answer(out / "guided_design_session.json", out / "decision_trace_registry.json", response_path, out)

            session = read_json(out / "guided_design_session.json")
            self.assertEqual(session["status"], "design_complete_generation_unconfirmed")
            self.assertFalse(session["generation_authorized"])

            confirmation = out / "confirmation.json"
            write_json(confirmation, {"user_confirmed_generation": True, "requested_outputs": ["protocol", "sap", "decision_trace"]})
            authorize(out / "guided_design_session.json", out / "decision_trace_registry.json", confirmation, out)
            session = read_json(out / "guided_design_session.json")
            self.assertEqual(session["status"], "ready_for_contracts")
            self.assertTrue(session["generation_authorized"])

    def test_revising_upstream_decision_invalidates_downstream_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            initialize_example(out)
            response_path = out / "response.json"
            for _ in range(5):
                session = read_json(out / "guided_design_session.json")
                write_json(response_path, response_for(session["current_node_id"]))
                answer(out / "guided_design_session.json", out / "decision_trace_registry.json", response_path, out)

            session_before = read_json(out / "guided_design_session.json")
            completed_before = {item["node_id"] for item in session_before["route"] if item["status"] == "completed"}
            self.assertIn("2.1_population_trinity", completed_before)

            revision = response_for("1.0_objective_triage", action="revise")
            revision["decision_statement"] = "Revised objective priority"
            write_json(response_path, revision)
            answer(out / "guided_design_session.json", out / "decision_trace_registry.json", response_path, out)
            session_after = read_json(out / "guided_design_session.json")
            route = {item["node_id"]: item for item in session_after["route"]}
            self.assertEqual(route["1.0_objective_triage"]["status"], "completed")
            self.assertEqual(route["2.1_population_trinity"]["status"], "pending")
            self.assertFalse(session_after["generation_authorized"])
            registry = read_json(out / "decision_trace_registry.json")
            self.assertTrue(any(item["status"] == "superseded" for item in registry["decisions"]))
            draft = read_json(out / "design_intake_draft.json")
            self.assertNotIn("2.1_population_trinity", draft["confirmed_design"])

    def test_hidden_reasoning_fields_are_rejected(self):
        concept = deepcopy(CONCEPT)
        concept["internal_reasoning"] = "private scratch work"
        with self.assertRaises(SystemExit):
            validate_concept_parse(concept)


if __name__ == "__main__":
    unittest.main()
