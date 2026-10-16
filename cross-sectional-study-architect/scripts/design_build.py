#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/design_build.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from design_common import (
    load_json,
    markdown_table,
    normalize,
    normalize_project_mode,
    role_bucket,
    sorted_objectives,
    today_iso,
    write_json,
    write_text,
)

# build_design_contracts


def build_protocol_contract(intake: dict) -> dict:
    return {
        "contract_version": "2.0",
        "generated_at": intake.get("generated_at", today_iso()),
        "project_mode": normalize_project_mode(intake.get("project_mode", "research")),
        "status": intake.get("status", "draft"),
        "decision_id": intake["decision_id"],
        "study_title": intake["study_title"],
        "full_protocol_title": intake.get("full_protocol_title", intake["study_title"]),
        "protocol_positioning": intake.get("protocol_positioning", "hybrid"),
        "keywords": intake.get("keywords", []),
        "study_objectives": sorted_objectives(intake["study_objectives"]),
        "population_registry_ref": "population_registry.json",
        "variable_registry_ref": "variable_registry.json",
        "estimand_registry_ref": "estimand_registry.json",
        "bias_control_registry_ref": "bias_control_registry.json",
        "analysis_commitment_registry_ref": "analysis_commitment_registry.json",
        "sample_size_plan": intake["sample_size_plan"],
        "institutional_sections": intake["institutional_sections"],
        "reporting_commitments": intake.get("reporting_commitments", []),
    }


def build_estimand_bridge(intake: dict) -> dict:
    objective_estimands = []
    primary_target_parameter = ""
    for objective in sorted_objectives(intake["study_objectives"]):
        if not primary_target_parameter and objective.get("priority") == "primary":
            primary_target_parameter = objective["target_parameter"]
        objective_estimands.append(
            {
                "objective_id": objective["objective_id"],
                "target_population": objective.get(
                    "target_population",
                    intake["population_trinity"]["target_population"],
                ),
                "estimand_label": objective["estimand_label"],
                "contrast": objective.get("contrast", objective.get("comparison", "")),
                "outcome_definition": objective.get("outcome_definition", objective.get("outcome", "")),
                "scale": objective.get("effect_measure", objective.get("estimation_metric", "")),
                "target_parameter": objective["target_parameter"],
                "identification_assumptions": objective.get("identification_assumptions", []),
                "adjustment_strategy": objective.get("adjustment_strategy", {}),
                "interpretation_boundary": objective["interpretation_boundary"],
            }
        )

    return {
        "contract_version": "2.0",
        "generated_at": intake.get("generated_at", today_iso()),
        "project_mode": normalize_project_mode(intake.get("project_mode", "research")),
        "status": intake.get("status", "draft"),
        "decision_id": intake["decision_id"],
        "target_parameter": primary_target_parameter or objective_estimands[0]["target_parameter"],
        "objective_estimands": objective_estimands,
    }


def build_sap_contract(intake: dict) -> dict:
    analysis_map = []
    for objective in sorted_objectives(intake["study_objectives"]):
        analysis_map.append(
            {
                "objective_id": objective["objective_id"],
                "analysis_family": objective["analysis_family"],
                "primary_model": objective["primary_model"],
                "design_awareness": objective["design_awareness"],
                "missing_data_strategy": objective["missing_data_strategy"],
                "diagnostics": objective.get("diagnostics", []),
                "sensitivity_analyses": objective.get("sensitivity_analyses", []),
                "result_shells": objective.get("result_shells", []),
                "primary_output_tables": objective.get("primary_output_tables", []),
                "supplementary_output_tables": objective.get("supplementary_output_tables", []),
                "interpretation_template": objective["interpretation_template"],
            }
        )
    return {
        "contract_version": "2.0",
        "generated_at": intake.get("generated_at", today_iso()),
        "project_mode": normalize_project_mode(intake.get("project_mode", "research")),
        "status": intake.get("status", "draft"),
        "decision_id": intake["decision_id"],
        "protocol_positioning": intake.get("protocol_positioning", "hybrid"),
        "analysis_map": analysis_map,
        "deviation_policy": intake.get("analysis_plan", {}).get(
            "deviation_policy",
            "All deviations must be logged and reported explicitly.",
        ),
    }


def main_build_design_contracts() -> None:
    parser = argparse.ArgumentParser(description="Build v2 contracts from design intake.")
    parser.add_argument("design_intake_json")
    parser.add_argument("output_dir")
    parser.add_argument(
        "--preflight-dir",
        required=True,
        help="Directory containing open_questions.json and objective_triage.json from the same intake.",
    )
    args = parser.parse_args()

    intake = load_json(Path(args.design_intake_json))
    intake_sha256 = hashlib.sha256(Path(args.design_intake_json).read_bytes()).hexdigest()
    preflight_dir = Path(args.preflight_dir)
    open_questions = load_json(preflight_dir / "open_questions.json")
    triage = load_json(preflight_dir / "objective_triage.json")
    if open_questions.get("decision_id") != intake.get("decision_id"):
        raise SystemExit("Preflight decision_id does not match the design intake.")
    if triage.get("decision_id") != intake.get("decision_id"):
        raise SystemExit("Objective-triage decision_id does not match the design intake.")
    if open_questions.get("input_sha256") != intake_sha256 or triage.get("input_sha256") != intake_sha256:
        raise SystemExit("Preflight artifacts are stale or were generated from a different intake hash.")
    if open_questions.get("overall_readiness") != "ready_for_contracts":
        raise SystemExit(
            "Contract freeze blocked by preflight readiness: "
            + str(open_questions.get("overall_readiness", "missing"))
        )
    if open_questions.get("blocking_questions"):
        raise SystemExit("Contract freeze blocked: unresolved preflight questions remain.")
    blocked_actions = {"clarify_then_keep", "reframe_before_freeze", "drop_or_defer"}
    blocked_entries = [
        row.get("objective_id", "UNKNOWN")
        for row in triage.get("triage_entries", [])
        if row.get("recommended_action") in blocked_actions or row.get("missing_inputs")
    ]
    if blocked_entries:
        raise SystemExit(
            "Contract freeze blocked by unresolved objective triage: " + ", ".join(blocked_entries)
        )
    outdir = Path(args.output_dir)

    write_json(outdir / "protocol_contract.json", build_protocol_contract(intake))
    write_json(outdir / "estimand_bridge.json", build_estimand_bridge(intake))
    write_json(outdir / "sap_contract.json", build_sap_contract(intake))

# build_global_registries


def build_population_registry(intake: dict) -> dict:
    population = intake["population_trinity"]
    study_design = intake["study_design"]
    return {
        "registry_name": "population_registry",
        "protocol_positioning": intake.get("protocol_positioning", "hybrid"),
        "target_population": population["target_population"],
        "source_population": population["source_population"],
        "analytic_population": population["analytic_population"],
        "inclusion_criteria": population.get("inclusion_criteria", []),
        "exclusion_criteria": population.get("exclusion_criteria", []),
        "recruitment_sequence": population.get("recruitment_sequence", []),
        "non_response_plan": population.get("non_response_plan", ""),
        "generalizability_boundary": population.get("generalizability_boundary", ""),
        "study_setting": study_design.get("study_setting", ""),
        "time_window": study_design.get("time_window", ""),
        "data_source": study_design.get("data_source", ""),
        "sampling_design": study_design.get("sampling_design", ""),
        "sampling_frame": study_design.get("sampling_frame", ""),
        "survey_design_features": study_design.get("survey_design_features", []),
        "design_constraints": study_design.get("design_constraints", []),
    }


def build_variable_registry(intake: dict) -> dict:
    measurement = intake["measurement_plan"]
    variables = []
    taxonomy = {
        "exposure": [],
        "outcome": [],
        "confounder": [],
        "mediator": [],
        "collider": [],
        "modifier": [],
        "supplementary": [],
    }
    for item in measurement.get("variable_roles", []):
        bucket = role_bucket(item.get("role", ""), item.get("planned_analysis_role", ""))
        record = {
            "variable": item["variable"],
            "display_label": item.get("display_label", item["variable"]),
            "role": item["role"],
            "operational_form": item["operational_form"],
            "planned_analysis_role": item["planned_analysis_role"],
            "measurement_source": item.get("measurement_source", ""),
            "bucket": bucket,
        }
        variables.append(record)
        taxonomy[bucket].append(item["variable"])
    return {
        "registry_name": "variable_registry",
        "variables": variables,
        "taxonomy": taxonomy,
        "measurement_sources": measurement.get("measurement_sources", []),
        "instrument_details": measurement.get("instrument_details", []),
        "measurement_quality": measurement.get("measurement_quality", []),
        "data_management_rules": measurement.get("data_management_rules", []),
        "naming_canon": {row["variable"]: row.get("display_label", row["variable"]) for row in variables},
    }


def build_estimand_registry(estimand_bridge: dict) -> dict:
    return {
        "registry_name": "estimand_registry",
        "objective_estimands": estimand_bridge["objective_estimands"],
    }


def build_bias_control_registry(intake: dict) -> dict:
    bias = intake["bias_control_plan"]
    objectives = sorted_objectives(intake["study_objectives"])
    return {
        "registry_name": "bias_control_registry",
        "objective_adjustment_policies": [
            {
                "objective_id": obj["objective_id"],
                "requires_causal_language": obj.get("requires_causal_language", False),
                "adjustment_strategy": obj.get("adjustment_strategy", {}),
            }
            for obj in objectives
        ],
        "confounding_plan": bias.get("confounding_plan", {}),
        "selection_bias_plan": bias.get("selection_bias_plan", {}),
        "information_bias_plan": bias.get("information_bias_plan", {}),
        "missing_data_policy": bias.get("missing_data_policy", {}),
        "survey_awareness_policy": bias.get("survey_awareness_policy", {}),
        "structured_controls": bias.get("controls", bias.get("structured_controls", [])),
    }


def build_analysis_commitment_registry(intake: dict) -> dict:
    plan = intake.get("analysis_plan", {})
    return {
        "registry_name": "analysis_commitment_registry",
        "objective_reporting_map": [
            {
                "objective_id": obj["objective_id"],
                "priority": obj.get("priority", "secondary"),
                "reporting_role": obj.get("reporting_role", "main_text"),
                "analysis_family": obj["analysis_family"],
                "primary_model": obj["primary_model"],
                "diagnostics": obj.get("diagnostics", []),
                "sensitivity_analyses": obj.get("sensitivity_analyses", []),
            }
            for obj in sorted_objectives(intake["study_objectives"])
        ],
        "reporting_commitments": intake.get("reporting_commitments", []),
        "analysis_sequence": plan.get("analysis_sequence", []),
        "data_linkage_plan": intake.get("data_linkage_plan", {}),
        "adjustment_sequences": plan.get("adjustment_sequences", []),
        "deviation_policy": plan.get(
            "deviation_policy",
            "All deviations must be logged, justified, and reported explicitly.",
        ),
    }


def main_build_global_registries() -> None:
    parser = argparse.ArgumentParser(description="Build v2 global registries.")
    parser.add_argument("design_intake_json")
    parser.add_argument("contracts_dir")
    parser.add_argument("output_dir")
    args = parser.parse_args()

    intake = load_json(Path(args.design_intake_json))
    contracts_dir = Path(args.contracts_dir)
    estimand_bridge = load_json(contracts_dir / "estimand_bridge.json")
    outdir = Path(args.output_dir)

    write_json(outdir / "population_registry.json", build_population_registry(intake))
    write_json(outdir / "variable_registry.json", build_variable_registry(intake))
    write_json(outdir / "estimand_registry.json", build_estimand_registry(estimand_bridge))
    write_json(outdir / "bias_control_registry.json", build_bias_control_registry(intake))
    write_json(outdir / "analysis_commitment_registry.json", build_analysis_commitment_registry(intake))

# build_intake_preflight


def infer_family(objective: dict) -> str:
    explicit = normalize(objective.get("objective_type", ""))
    framework = normalize(objective.get("framework", ""))
    text = normalize(
        " ".join(
            str(objective.get(key, ""))
            for key in [
                "purpose",
                "objective_statement",
                "estimand_label",
                "target_parameter",
            ]
        )
    )

    if explicit in {"prevalence", "description", "descriptive"} or framework == "cocopop":
        return "prevalence"
    if explicit in {"association", "correlational", "explanatory"} or framework == "peco":
        return "association"
    if explicit in {"prediction", "screening"} or "predict" in text or "screen" in text:
        return "prediction"
    if explicit in {"mechanism", "mechanism_exploratory"} or "mediat" in text or "pathway" in text:
        return "mechanism_exploratory"
    if explicit in {"policy", "policy_relevance_only"} or "policy" in text or "intervention" in text:
        return "policy_relevance_only"
    return "unspecified"


def claim_boundary(family: str) -> str:
    boundaries = {
        "prevalence": "Interpret as burden or distribution in the defined population only; do not infer determinants from this objective alone.",
        "association": "Interpret as a cross-sectional adjusted association; do not infer temporality or causality.",
        "prediction": "Interpret as predictive or classification performance only; do not imply etiologic effect.",
        "mechanism_exploratory": "Treat as hypothesis-generating exploratory work; do not present as confirmatory mechanism evidence.",
        "policy_relevance_only": "Use only to motivate the study or discussion; do not freeze as a primary estimand without a design that supports policy-effect claims.",
        "unspecified": "Clarify the inferential task before freezing contracts."
    }
    return boundaries[family]


def required_fields_for_family(family: str) -> list[str]:
    if family == "prevalence":
        return ["population", "condition_or_outcome", "context_or_setting", "metric"]
    if family == "association":
        return ["population", "exposure", "comparison", "outcome", "metric", "analysis_family"]
    if family == "prediction":
        return ["population", "prediction_target", "predictor_domain", "metric"]
    if family == "mechanism_exploratory":
        return ["population", "exposure_or_condition", "mechanism_target", "outcome"]
    if family == "policy_relevance_only":
        return ["policy_question", "decision_context"]
    return ["objective_type"]


def present_fields(objective: dict, family: str) -> dict[str, bool]:
    return {
        "population": bool(objective.get("population")),
        "condition_or_outcome": bool(objective.get("condition") or objective.get("outcome")),
        "context_or_setting": bool(objective.get("context")),
        "metric": bool(objective.get("estimation_metric") or objective.get("effect_measure")),
        "exposure": bool(objective.get("exposure")),
        "comparison": bool(objective.get("comparison") or objective.get("contrast")),
        "outcome": bool(objective.get("outcome")),
        "analysis_family": bool(objective.get("analysis_family")),
        "prediction_target": bool(objective.get("outcome") or objective.get("target_parameter")),
        "predictor_domain": bool(objective.get("exposure") or objective.get("candidate_predictors")),
        "exposure_or_condition": bool(objective.get("exposure") or objective.get("condition")),
        "mechanism_target": bool(objective.get("mediators") or objective.get("mechanism_target")),
        "policy_question": bool(objective.get("purpose") or objective.get("objective_statement")),
        "decision_context": bool(objective.get("context") or objective.get("reporting_role")),
        "objective_type": family != "unspecified",
    }


def objective_label(objective: dict, index: int) -> str:
    return (
        objective.get("objective_statement")
        or objective.get("purpose")
        or objective.get("estimand_label")
        or objective.get("target_parameter")
        or f"Candidate objective {index}"
    )


def triage_entry(objective: dict, index: int) -> dict:
    family = infer_family(objective)
    present = present_fields(objective, family)
    required = required_fields_for_family(family)
    missing = [field for field in required if not present.get(field, False)]
    if len(missing) == 0:
        feasibility = "high"
    elif len(missing) <= 2:
        feasibility = "medium"
    else:
        feasibility = "low"

    priority = objective.get("priority", "unspecified")
    if family == "policy_relevance_only":
        action = "drop_or_defer"
    elif family == "unspecified":
        action = "reframe_before_freeze"
    elif len(missing) == 0 and priority == "primary":
        action = "keep_as_primary"
    elif len(missing) == 0:
        action = "keep_as_secondary"
    elif len(missing) <= 2:
        action = "clarify_then_keep"
    else:
        action = "reframe_before_freeze"

    rationale = [
        f"Inferred objective family: {family}.",
        f"Required completeness check missing {len(missing)} field(s).",
        claim_boundary(family),
    ]
    if objective.get("requires_causal_language"):
        rationale.append(
            "Cross-sectional designs still need explicit non-causal interpretation boundaries even when DAG-informed adjustment is planned."
        )

    return {
        "objective_id": objective.get("objective_id", f"OBJ{index}"),
        "objective_label": objective_label(objective, index),
        "objective_family": family,
        "priority_signal": priority,
        "feasibility": feasibility,
        "claim_boundary": claim_boundary(family),
        "recommended_action": action,
        "missing_inputs": missing,
        "rationale": rationale,
    }


def candidate_objectives(payload: dict) -> list[dict]:
    if payload.get("study_objectives"):
        return payload["study_objectives"]
    if payload.get("candidate_objectives"):
        return payload["candidate_objectives"]
    return []


def top_level_questions(payload: dict) -> list[dict]:
    questions: list[dict] = []
    if not payload.get("study_title"):
        questions.append(
            question(
                "Q001",
                "study_title",
                "What is the final study title or one-sentence study focus?",
                "The preflight and downstream protocol need a stable object of reference.",
                "preflight",
            )
        )
    population = payload.get("population_trinity", {})
    if not population.get("target_population"):
        questions.append(
            question(
                "Q002",
                "population",
                "What is the target population, and how does it differ from the source and analytic populations?",
                "Population ambiguity will propagate into objectives, sample-size logic, and interpretation boundaries.",
                "before_contracts",
            )
        )
    study_design = payload.get("study_design", {})
    if not study_design.get("sampling_design"):
        questions.append(
            question(
                "Q003",
                "sampling_design",
                "What sampling design will be used, and must weights, strata, or clusters be preserved for analysis?",
                "Sampling design affects prevalence estimation, precision, and SAP commitments.",
                "before_contracts",
            )
        )
    sample_size_plan = payload.get("sample_size_plan", {})
    if (
        not sample_size_plan
        or sample_size_plan.get("needs_preflight_confirmation")
        or not sample_size_plan.get("bases")
        or int(sample_size_plan.get("final_adopted_sample_size", 0) or 0) <= 0
    ):
        questions.append(
            question(
                "Q004",
                "sample_size",
                "Which primary objective determines sample-size reasoning, and what assumptions will be used?",
                "Sample-size logic cannot be frozen until one primary objective and its metric are explicit.",
                "before_contracts",
            )
        )
    measurement = payload.get("measurement_plan", {})
    if not measurement.get("variable_roles"):
        questions.append(
            question(
                "Q005",
                "variables",
                "Which variables are outcomes, exposures, confounders, modifiers, and mediators?",
                "Variable-role ambiguity is a common source of drift across registries, protocol prose, and SAP.",
                "before_contracts",
            )
        )
    return questions


def objective_questions(entry: dict) -> list[dict]:
    prompts = {
        "population": "What is the exact target population for this objective?",
        "condition_or_outcome": "What condition or outcome is being estimated?",
        "context_or_setting": "What context, setting, or time window anchors this objective?",
        "metric": "What is the effect measure or estimation metric for this objective?",
        "exposure": "What is the exposure for this objective?",
        "comparison": "What is the comparison or reference group?",
        "outcome": "What is the outcome for this objective?",
        "analysis_family": "Which analysis family is intended for this objective?",
        "prediction_target": "What is the prediction target?",
        "predictor_domain": "Which predictor domain is planned?",
        "exposure_or_condition": "Which exposure or condition anchors this exploratory objective?",
        "mechanism_target": "What mechanism or pathway target is being explored?",
        "policy_question": "What exact policy or decision question is being implied?",
        "decision_context": "What decision context makes this objective protocol-worthy?",
        "objective_type": "Should this candidate be treated as prevalence, association, prediction, mechanism-exploratory, or only policy framing?"
    }
    questions = []
    for idx, missing in enumerate(entry["missing_inputs"], start=1):
        questions.append(
            question(
                f"{entry['objective_id']}_Q{idx}",
                f"{entry['objective_id']}::{missing}",
                prompts[missing],
                f"This objective cannot be frozen cleanly while `{missing}` is unresolved.",
                "before_contracts",
            )
        )
    return questions


def question(question_id: str, topic: str, text: str, why: str, stage: str) -> dict:
    return {
        "question_id": question_id,
        "topic": topic,
        "question": text,
        "why_it_matters": why,
        "recommended_resolution_stage": stage,
    }


def overall_readiness(triage_entries: list[dict], questions: list[dict]) -> str:
    if any(entry["recommended_action"] in {"reframe_before_freeze", "drop_or_defer"} for entry in triage_entries):
        return "clarify_before_contracts"
    if len(questions) >= 5:
        return "major_gaps"
    if questions:
        return "clarify_before_contracts"
    return "ready_for_contracts"


def build_intake_brief(payload: dict, triage_entries: list[dict], open_questions: dict) -> str:
    title = payload.get("study_title", "Untitled cross-sectional study")
    decision_id = payload.get("decision_id", "DECISION_PENDING")
    family_rows = [
        [
            entry["objective_id"],
            entry["objective_family"],
            entry["priority_signal"],
            entry["feasibility"],
            entry["recommended_action"],
        ]
        for entry in triage_entries
    ]
    lines = [
        f"# Intake Brief: {title}",
        "",
        f"- Decision ID: `{decision_id}`",
        f"- Generated at: `{payload.get('generated_at', today_iso())}`",
        f"- Overall readiness: `{open_questions['overall_readiness']}`",
        "",
        "## Study Snapshot",
        "",
        payload.get("background_inputs", {}).get(
            "why_this_study",
            "A preflight summary was generated before contract freeze."
        ),
        "",
    ]
    if triage_entries:
        lines.extend(
            [
                "## Objective Triage",
                "",
                *markdown_table(
                    ["Objective", "Family", "Priority", "Feasibility", "Action"],
                    family_rows,
                ),
                "",
            ]
        )
    if open_questions["blocking_questions"]:
        lines.extend(["## Blocking Questions", ""])
        for item in open_questions["blocking_questions"]:
            lines.append(f"- {item['question']}")
        lines.append("")
    if open_questions["non_blocking_questions"]:
        lines.extend(["## Non-blocking Questions", ""])
        for item in open_questions["non_blocking_questions"]:
            lines.append(f"- {item['question']}")
        lines.append("")
    lines.extend(
        [
            "## Claim Discipline",
            "",
        ]
    )
    for entry in triage_entries:
        lines.append(f"- `{entry['objective_id']}`: {entry['claim_boundary']}")
    if not triage_entries:
        lines.append("- No candidate objectives were found. Clarify the inferential task before freezing contracts.")
    return "\n".join(lines)


def main_build_intake_preflight() -> None:
    parser = argparse.ArgumentParser(description="Build intake preflight artifacts for the cross-sectional architect.")
    parser.add_argument("input_json")
    parser.add_argument("output_dir")
    args = parser.parse_args()

    payload = load_json(Path(args.input_json))
    input_sha256 = hashlib.sha256(Path(args.input_json).read_bytes()).hexdigest()
    objectives = candidate_objectives(payload)
    triage_entries = [triage_entry(obj, idx) for idx, obj in enumerate(objectives, start=1)]

    blocking_questions = top_level_questions(payload)
    non_blocking_questions: list[dict] = []
    for entry in triage_entries:
        objective_specific = objective_questions(entry)
        if entry["recommended_action"] in {"clarify_then_keep", "reframe_before_freeze", "drop_or_defer"}:
            blocking_questions.extend(objective_specific)
        else:
            non_blocking_questions.extend(objective_specific)

    open_questions = {
        "generated_at": payload.get("generated_at", today_iso()),
        "input_sha256": input_sha256,
        "decision_id": payload.get("decision_id", "DECISION_PENDING"),
        "study_title": payload.get("study_title", "Untitled cross-sectional study"),
        "overall_readiness": overall_readiness(triage_entries, blocking_questions),
        "blocking_questions": blocking_questions,
        "non_blocking_questions": non_blocking_questions,
    }

    triage = {
        "generated_at": payload.get("generated_at", today_iso()),
        "input_sha256": input_sha256,
        "decision_id": payload.get("decision_id", "DECISION_PENDING"),
        "study_title": payload.get("study_title", "Untitled cross-sectional study"),
        "triage_entries": triage_entries,
    }

    outdir = Path(args.output_dir)
    write_json(outdir / "objective_triage.json", triage)
    write_json(outdir / "open_questions.json", open_questions)
    write_text(outdir / "intake_brief.md", build_intake_brief(payload, triage_entries, open_questions))

# build_protocol_blueprint


def chapter_core(chapter_id: str, title: str, goal: str, order: list[str], objectives: list[str], facts: list[str], commitments: list[str]) -> dict:
    return {
        "chapter_id": chapter_id,
        "chapter_title": title,
        "chapter_goal": goal,
        "narrative_order": order,
        "objective_links": objectives,
        "must_include_facts": facts,
        "methodological_commitments": commitments,
    }


def chapter_editorial(chapter_id: str, bridge_intents: list[str], appendix_hooks: list[str], open_placeholders: list[str]) -> dict:
    return {
        "chapter_id": chapter_id,
        "style_constraints": [
            "continuous academic prose",
            "no template language",
            "no internal workflow vocabulary",
        ],
        "forbidden_phrases": [
            "Phase",
            "Module",
            "skill",
            "workflow",
            "contract-first",
        ],
        "bridge_intents": bridge_intents,
        "appendix_hooks": appendix_hooks,
        "open_placeholders": open_placeholders,
    }


def main_build_protocol_blueprint() -> None:
    parser = argparse.ArgumentParser(description="Build v2 protocol blueprints.")
    parser.add_argument("design_intake_json")
    parser.add_argument("contracts_dir")
    parser.add_argument("registries_dir")
    parser.add_argument("output_dir")
    args = parser.parse_args()

    intake = load_json(Path(args.design_intake_json))
    registries_dir = Path(args.registries_dir)
    outdir = Path(args.output_dir)

    population_registry = load_json(registries_dir / "population_registry.json")
    variable_registry = load_json(registries_dir / "variable_registry.json")
    analysis_registry = load_json(registries_dir / "analysis_commitment_registry.json")

    objectives = sorted_objectives(intake["study_objectives"])
    objective_ids = [obj["objective_id"] for obj in objectives if obj.get("reporting_role", "main_text") == "main_text"]

    background = intake.get("background_inputs", {})
    core = {
        "protocol_positioning": intake.get("protocol_positioning", "hybrid"),
        "chapters": [
            chapter_core(
                "background_objectives",
                "Background and Objectives",
                "Establish disease burden, evidence gap, methodological gap, and why the protocol needs multiple objectives.",
                ["public health burden", "setting-specific gap", "mechanistic plausibility", "prior method limitations", "study necessity", "objective ladder"],
                objective_ids,
                [
                    background.get("public_health_burden", ""),
                    background.get("evidence_gap", ""),
                    background.get("methodological_gap", ""),
                ],
                ["state why each objective exists", "separate estimation from association aims"],
            ),
            chapter_core(
                "design_setting",
                "Study Design and Setting",
                "Explain the study design, setting, sampling logic, and why design-aware analysis is required.",
                ["design declaration", "setting and time window", "sampling design", "analysis constraints"],
                objective_ids,
                [
                    population_registry.get("study_setting", ""),
                    population_registry.get("sampling_design", ""),
                    ", ".join(population_registry.get("survey_design_features", [])),
                ],
                ["link sampling design to analysis consequences"],
            ),
            chapter_core(
                "participants",
                "Participants",
                "Define target/source/analytic populations and the operational participant path.",
                ["population trinity", "eligibility", "recruitment", "non-response", "generalizability"],
                objective_ids,
                [
                    population_registry.get("target_population", ""),
                    population_registry.get("source_population", ""),
                    population_registry.get("analytic_population", ""),
                ],
                ["do not blur source and target population", "make non-response handling explicit"],
            ),
            chapter_core(
                "variables_measurement",
                "Variable Definitions and Measurement",
                "Define variables consistently across objectives and anchor measurement quality claims.",
                ["variable taxonomy", "objective-specific variables", "measurement sources", "quality safeguards"],
                objective_ids,
                variable_registry.get("taxonomy", {}).get("exposure", []) + variable_registry.get("taxonomy", {}).get("outcome", []),
                ["preserve naming canon", "distinguish confounders, mediators, colliders, and modifiers"],
            ),
            chapter_core(
                "bias_sample",
                "Bias Control and Sample Size",
                "Describe bias-control strategy and justify the adopted sample size across competing objectives.",
                ["confounding", "selection bias", "information bias", "missing data", "sample-size bases", "adopted sample size"],
                objective_ids,
                [intake["sample_size_plan"].get("adoption_reason", "")],
                ["write bias as risk-source-control-analysis", "compare sample-size bases before adopting final n"],
            ),
            chapter_core(
                "stat_methods",
                "Statistical Methods",
                "Map each objective to its estimand, model, diagnostics, sensitivities, and outputs.",
                ["objective ordering", "estimands", "models", "diagnostics", "sensitivity analyses", "reporting outputs"],
                objective_ids,
                [item["objective_id"] for item in analysis_registry.get("objective_reporting_map", [])],
                ["organize by objective_id rather than by method menu"],
            ),
            chapter_core(
                "ethics_governance",
                "Ethics, Data Security, and Governance",
                "State the institutional controls that govern the protocol.",
                ["ethics approval", "consent pathway", "data security", "governance", "deviation control"],
                objective_ids,
                list(intake.get("institutional_sections", {}).keys()),
                ["keep governance in the main body when relevant to positioning"],
            ),
            chapter_core(
                "publication",
                "Publication and Dissemination",
                "Describe reporting standards, authorship, and dissemination commitments.",
                ["reporting commitments", "authorship", "dissemination route", "supplement expectations"],
                objective_ids,
                intake.get("reporting_commitments", []),
                ["make reporting promises explicit"],
            ),
        ],
    }

    editorial = {
        "protocol_positioning": intake.get("protocol_positioning", "hybrid"),
        "global_forbidden_phrases": [
            "Phase",
            "Module",
            "skill",
            "workflow",
            "contract-first",
            "Codex",
        ],
        "chapters": [
            chapter_editorial(
                "background_objectives",
                ["move from burden to necessity", "bridge into a multi-objective design"],
                ["Objective-to-output mapping"],
                [],
            ),
            chapter_editorial(
                "design_setting",
                ["connect sampling design to analysis design awareness"],
                ["Sampling-analysis mapping"],
                [],
            ),
            chapter_editorial(
                "participants",
                ["move from population definition to operational recruitment"],
                ["Eligibility appendix"],
                [],
            ),
            chapter_editorial(
                "variables_measurement",
                ["connect taxonomy to measurement credibility"],
                ["Variable roles table"],
                [],
            ),
            chapter_editorial(
                "bias_sample",
                ["move from bias threats to control strategy to sample-size adoption"],
                ["Sample-size assumptions"],
                [],
            ),
            chapter_editorial(
                "stat_methods",
                ["introduce each objective before naming its model"],
                ["SAP crosswalk"],
                [],
            ),
            chapter_editorial(
                "ethics_governance",
                ["close the methodological body with governance requirements"],
                ["Deviation log expectations"],
                [],
            ),
            chapter_editorial(
                "publication",
                ["end with dissemination and reporting promises"],
                ["Reporting commitments"],
                [],
            ),
        ],
    }

    write_json(outdir / "protocol_blueprint_core.json", core)
    write_json(outdir / "protocol_blueprint_editorial.json", editorial)


COMMANDS = {
    "build_design_contracts": main_build_design_contracts,
    "build_global_registries": main_build_global_registries,
    "build_intake_preflight": main_build_intake_preflight,
    "build_protocol_blueprint": main_build_protocol_blueprint,
}

def main() -> int:
    import sys
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        available = "\n".join(f"  {name}" for name in sorted(COMMANDS))
        print(f"Usage: {sys.argv[0]} <command> [original arguments]\n\nCommands:\n{available}")
        return 0 if len(sys.argv) >= 2 else 2
    command = sys.argv[1].replace("-", "_")
    if command not in COMMANDS:
        raise SystemExit(f"Unknown command {sys.argv[1]!r}; use --help to list commands.")
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    result = COMMANDS[command]()
    return 0 if result is None else int(result)

if __name__ == "__main__":
    raise SystemExit(main())
