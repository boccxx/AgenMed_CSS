#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/design_intake.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from design_common import load_json, normalize_project_mode, today_iso, write_json, write_text
# adapt_review_to_design_intake


def load_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def clean_list(values) -> list[str]:
    items = values if isinstance(values, list) else [values]
    seen: list[str] = []
    for value in items:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def first_nonempty(*values) -> str:
    for value in values:
        if isinstance(value, list):
            cleaned = clean_list(value)
            if cleaned:
                return cleaned[0]
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def slugify(text: str, fallback: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return lowered[:40] or fallback


def detect_effect_measure(primary_estimand: str, statistical_approach: str, objective_type: str) -> str:
    combined = " ".join([primary_estimand, statistical_approach]).lower()
    if objective_type == "prevalence":
        return "weighted prevalence"
    if "hazard ratio" in combined or "cox" in combined or re.search(r"\bhr\b", combined):
        return "hazard ratio"
    if "prevalence ratio" in combined or re.search(r"\bpr\b", combined):
        return "prevalence ratio"
    if "odds ratio" in combined or re.search(r"\bor\b", combined):
        return "odds ratio"
    if "risk ratio" in combined or re.search(r"\brr\b", combined):
        return "risk ratio"
    return "prevalence ratio"


def detect_analysis_family(primary_estimand: str, statistical_approach: str, suggested_methods: list[str], objective_type: str) -> str:
    combined = " ".join([primary_estimand, statistical_approach, *suggested_methods]).lower()
    if objective_type == "prevalence":
        if "survey" in combined or "weighted" in combined:
            return "survey-weighted prevalence estimation"
        return "prevalence estimation"
    if "modified poisson" in combined or ("poisson" in combined and "robust" in combined):
        return "modified Poisson regression"
    if "log binomial" in combined:
        return "log-binomial regression"
    if "logistic" in combined:
        return "logistic regression"
    if "cox" in combined:
        return "Cox regression"
    return "modified Poisson regression"


def extract_min_sample(protocol_inputs: dict) -> int | None:
    candidate_texts = []
    candidate_texts.extend(clean_list(protocol_inputs.get("data_sources_recommended", [])))
    candidate_texts.extend(clean_list(protocol_inputs.get("suggested_methods", [])))
    candidate_texts.append(str(protocol_inputs.get("statistical_approach", "")))
    for text in candidate_texts:
        match = re.search(r"minimum sample size\s*:\s*([0-9][0-9,]*)", text, flags=re.I)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def build_variable_roles(
    exposure: str,
    outcome: str,
    confounders: list[str],
    mediator: str,
    modifiers: list[str],
    measurement_tools: list[str],
) -> list[dict]:
    roles_by_variable: dict[str, dict] = {}
    measurement_source = "; ".join(measurement_tools) if measurement_tools else "Evidence-informed measurement tool to be specified during intake preflight"

    def add_role(entry: dict) -> None:
        key = entry["variable"]
        existing = roles_by_variable.get(key)
        if not existing:
            roles_by_variable[key] = entry
            return
        merged_role = clean_list([existing["role"], entry["role"]])
        merged_analysis = clean_list([existing["planned_analysis_role"], entry["planned_analysis_role"]])
        merged_sources = clean_list([existing["measurement_source"], entry["measurement_source"]])
        existing["role"] = " and ".join(merged_role)
        existing["planned_analysis_role"] = " and ".join(merged_analysis)
        existing["measurement_source"] = "; ".join(merged_sources)

    if exposure:
        add_role(
            {
                "variable": slugify(exposure, "exposure"),
                "display_label": exposure,
                "role": "Primary exposure",
                "operational_form": "Operational definition to be finalized during intake preflight",
                "planned_analysis_role": "Main exposure",
                "measurement_source": measurement_source,
            }
        )
    if outcome:
        add_role(
            {
                "variable": slugify(outcome, "outcome"),
                "display_label": outcome,
                "role": "Primary outcome",
                "operational_form": "Operational definition to be finalized during intake preflight",
                "planned_analysis_role": "Primary outcome",
                "measurement_source": measurement_source,
            }
        )
    if mediator:
        add_role(
            {
                "variable": slugify(mediator, "mediator"),
                "display_label": mediator,
                "role": "Mediator candidate",
                "operational_form": "Exploratory mechanism definition to be finalized during intake preflight",
                "planned_analysis_role": "Reserved for exploratory mechanism analysis",
                "measurement_source": measurement_source,
            }
        )
    for modifier in modifiers:
        add_role(
            {
                "variable": slugify(modifier, "modifier"),
                "display_label": modifier,
                "role": "Modifier candidate",
                "operational_form": "Interaction coding to be finalized during intake preflight",
                "planned_analysis_role": "Interaction and subgroup analysis",
                "measurement_source": measurement_source,
            }
        )
    for confounder in confounders:
        add_role(
            {
                "variable": slugify(confounder, "confounder"),
                "display_label": confounder,
                "role": "Confounder candidate",
                "operational_form": "Coding to be finalized during intake preflight",
                "planned_analysis_role": "Adjustment set candidate",
                "measurement_source": "Evidence-informed covariate specification from the literature review",
            }
        )
    return list(roles_by_variable.values())


def build_background(protocol_inputs: dict, exposure: str, outcome: str) -> dict:
    topic = first_nonempty(protocol_inputs.get("study_title_candidate", ""), protocol_inputs.get("topic", ""))
    evidence_gaps = clean_list(
        protocol_inputs.get("evidence_gaps", [])
        or protocol_inputs.get("key_evidence_gaps_this_review_identified", [])
    )
    review_goal = first_nonempty(protocol_inputs.get("review_goal", ""), protocol_inputs.get("question_type", "cross-sectional review"))
    burden = (
        f"The upstream literature review identified {topic or 'the target topic'} as a protocol-worthy cross-sectional question. "
        f"The review goal was {review_goal}, which provides the substantive starting point for the draft intake."
    )
    gap = (
        " ".join(evidence_gaps[:2])
        if evidence_gaps
        else "The literature review suggests a stable evidence base exists, but the final protocol still needs a setting-specific gap statement."
    )
    mechanism = (
        f"The review indicates a plausible substantive link between {exposure} and {outcome}, but the exact temporality boundary and measurement definitions still need to be fixed during intake preflight."
        if exposure and outcome
        else f"The review supports {outcome or 'the target condition'} as a protocol-worthy outcome, but the final exposure, context, and operational definitions still require clarification."
    )
    return {
        "public_health_burden": burden,
        "evidence_gap": gap,
        "mechanistic_rationale": mechanism,
        "methodological_gap": "The literature review can nominate variables, measurement tools, and model families, but it does not by itself freeze sampling design, estimand wording, or cross-sectional interpretation boundaries.",
        "why_this_study": "This draft intake is therefore generated as a bridge artifact. It should move through intake preflight before contracts, registries, and protocol prose are frozen.",
    }


def build_objectives(protocol_inputs: dict, exposure: str, outcome: str, comparison: str, modifiers: list[str]) -> list[dict]:
    statistical_approach = first_nonempty(protocol_inputs.get("statistical_approach", ""))
    suggested_methods = clean_list(protocol_inputs.get("suggested_methods", []))
    primary_estimand = first_nonempty(protocol_inputs.get("primary_estimand", ""))
    population = first_nonempty(protocol_inputs.get("population", ""), "Population to be specified during intake preflight")

    if exposure and outcome:
        effect_measure = detect_effect_measure(primary_estimand, statistical_approach, "association")
        analysis_family = detect_analysis_family(primary_estimand, statistical_approach, suggested_methods, "association")
        objective_statement = (
            f"To estimate the cross-sectional association between {exposure} and {outcome} in {population.lower()}."
        )
        return [
            {
                "objective_id": "OBJ1",
                "priority": "primary",
                "objective_type": "association",
                "framework": "PECO",
                "purpose": f"Estimate the adjusted association between {exposure} and {outcome}",
                "population": population,
                "exposure": exposure,
                "comparison": comparison or "Reference group to be specified during intake preflight",
                "outcome": outcome,
                "effect_measure": effect_measure,
                "analysis_family": analysis_family,
                "hypothesis_policy": "formal",
                "reporting_role": "main_text",
                "requires_causal_language": True,
                "table_figure_targets": [
                    "Primary adjusted association table",
                    "Sensitivity analysis table",
                ],
                "objective_statement": objective_statement,
                "estimand_label": first_nonempty(primary_estimand, f"Adjusted {effect_measure} comparing {exposure} groups"),
                "target_parameter": first_nonempty(
                    primary_estimand,
                    f"Adjusted {effect_measure} for {outcome} comparing {exposure} against the reference group",
                ),
                "contrast": comparison or "Reference group to be specified during intake preflight",
                "outcome_definition": outcome,
                "identification_assumptions": [
                    "No unmeasured confounding conditional on the final prespecified adjustment set",
                    "Exposure and outcome definitions are finalized before analysis",
                    "Cross-sectional timing limits causal interpretation",
                ],
                "adjustment_strategy": {
                    "strategy": "Literature-informed adjustment set to be finalized during intake preflight",
                    "adjustment_set": clean_list(
                        protocol_inputs.get("confounders", [])
                        or protocol_inputs.get("key_confounders_main_model", [])
                    ),
                    "excluded_variables": clean_list([protocol_inputs.get("mediator", "")]),
                },
                "null_hypothesis": f"After adjustment for the final prespecified covariates, the {effect_measure} for {outcome} is 1.0 when comparing {exposure} groups.",
                "alternative_hypothesis": f"After adjustment for the final prespecified covariates, {exposure} is associated with {outcome}.",
                "primary_model": first_nonempty(
                    statistical_approach,
                    f"{analysis_family} with final covariate coding to be specified during intake preflight",
                ),
                "design_awareness": "Whether the primary analysis must be survey-aware depends on the final sampling design and will be frozen after intake preflight.",
                "missing_data_strategy": "Missing-data handling will be finalized during intake preflight after clarifying whether exposure, outcome, or confounders are expected to be incomplete.",
                "diagnostics": [
                    "Model diagnostics will be finalized once the primary model family is confirmed",
                    "Outcome prevalence and covariate overlap will be checked before freezing the SAP",
                ],
                "sensitivity_analyses": clean_list(protocol_inputs.get("sensitivity_analyses", []))
                or ["Sensitivity analyses to be specified after intake preflight"],
                "result_shells": [
                    f"Primary {effect_measure} result shell for {outcome}",
                    "Sensitivity result shell aligned to the prespecified covariate and design rules",
                ],
                "primary_output_tables": ["Primary association model table"],
                "supplementary_output_tables": ["Sensitivity analysis appendix table"],
                "interpretation_boundary": "Interpret as a cross-sectional adjusted association only; do not infer temporality or causality.",
                "interpretation_template": "Interpret the primary estimate as a cross-sectional adjusted association and not as causal evidence.",
                "reporting_role": "main_text",
                "table_figure_targets": [
                    "Primary association model table",
                    "Sensitivity analysis appendix table",
                    *[f"Interaction output for {item}" for item in modifiers[:2]],
                ],
            }
        ]

    estimation_metric = detect_effect_measure(primary_estimand, statistical_approach, "prevalence")
    analysis_family = detect_analysis_family(primary_estimand, statistical_approach, suggested_methods, "prevalence")
    return [
        {
            "objective_id": "OBJ1",
            "priority": "primary",
            "objective_type": "prevalence",
            "framework": "CoCoPop",
            "purpose": f"Estimate the prevalence or distribution of {outcome or 'the target condition'}",
            "population": population,
            "condition": outcome or "Condition to be specified during intake preflight",
            "context": first_nonempty(protocol_inputs.get("setting", ""), "Setting and time window to be specified during intake preflight"),
            "estimation_metric": estimation_metric,
            "analysis_family": analysis_family,
            "hypothesis_policy": "estimation_only",
            "reporting_role": "main_text",
            "requires_causal_language": False,
            "table_figure_targets": [
                "Primary prevalence estimate table",
                "Stratified descriptive table",
            ],
            "objective_statement": f"To estimate the prevalence of {outcome or 'the target condition'} in {population.lower()}.",
            "estimand_label": first_nonempty(primary_estimand, f"Population prevalence of {outcome or 'the target condition'}"),
            "target_parameter": first_nonempty(primary_estimand, f"Population prevalence of {outcome or 'the target condition'}"),
            "contrast": "",
            "outcome_definition": outcome or "Condition to be specified during intake preflight",
            "identification_assumptions": [
                "The sampling frame and measurement definitions are finalized before fieldwork",
                "The final sampling design supports the intended population estimate",
            ],
            "adjustment_strategy": {
                "strategy": "Not applicable as a primary prevalence objective; any stratification will be prespecified during intake preflight",
                "adjustment_set": [],
                "excluded_variables": [],
            },
            "primary_model": first_nonempty(statistical_approach, "Prevalence estimation approach to be specified during intake preflight"),
            "design_awareness": "Whether weighted prevalence estimation is required depends on the final sampling design and will be frozen after intake preflight.",
            "missing_data_strategy": "Missing-data handling will be finalized during intake preflight after clarifying field procedures and measurement completeness.",
            "diagnostics": ["Descriptive completeness and design consistency checks will be specified before analysis."],
            "sensitivity_analyses": clean_list(protocol_inputs.get("sensitivity_analyses", []))
            or ["Sensitivity analyses to be specified after intake preflight"],
            "result_shells": [f"Primary prevalence estimate shell for {outcome or 'the target condition'}"],
            "primary_output_tables": ["Primary prevalence table"],
            "supplementary_output_tables": ["Stratified descriptive appendix table"],
            "interpretation_boundary": "Interpret as burden or distribution in the defined population only; do not infer determinants from this objective alone.",
            "interpretation_template": "Interpret the estimate as a population prevalence or distribution measure only.",
        }
    ]


def build_sample_size_plan(protocol_inputs: dict, objective_type: str) -> dict:
    min_sample = extract_min_sample(protocol_inputs)
    if min_sample is None:
        return {
            "needs_preflight_confirmation": True,
            "bases": [],
            "final_adopted_sample_size": 0,
            "adoption_reason": "The literature review nominated the study question but did not provide a final cross-sectional sample-size basis. This must be resolved during intake preflight before contracts are frozen.",
        }
    basis_type = "association_power" if objective_type == "association" else "prevalence_precision"
    return {
        "needs_preflight_confirmation": True,
        "bases": [
            {
                "basis_id": "B1",
                "objective_id": "OBJ1",
                "basis_type": basis_type,
                "formula_family": "literature-review bridge placeholder",
                "assumptions": [
                    "Imported from literature-review protocol inputs",
                    "Requires confirmation of sampling design, design effect, and non-response assumptions during intake preflight",
                ],
                "raw_required_n": min_sample,
                "design_effect": 1.0,
                "non_response_inflation": 0.0,
                "adjusted_required_n": min_sample,
            }
        ],
        "final_adopted_sample_size": min_sample,
        "adoption_reason": "A minimum sample-size hint was imported from the literature-review package, but the final adopted value still requires preflight confirmation against the frozen primary objective and sampling design.",
    }


def main_adapt_review_to_design_intake() -> None:
    parser = argparse.ArgumentParser(
        description="Adapt literature-review protocol_inputs.json into a draft design_intake_v2.json for the cross-sectional architect."
    )
    parser.add_argument("protocol_inputs_json")
    parser.add_argument("output_json")
    parser.add_argument("--decision-id", default="REVIEW_BRIDGED_DRAFT")
    parser.add_argument("--protocol-positioning", default="hybrid", choices=["institutional", "journal_ready", "hybrid"])
    parser.add_argument("--setting", default="")
    parser.add_argument("--time-window", default="")
    parser.add_argument("--data-source", default="")
    args = parser.parse_args()

    protocol_inputs = load_json(Path(args.protocol_inputs_json))

    study_title = first_nonempty(
        protocol_inputs.get("study_title_candidate", ""),
        protocol_inputs.get("topic", ""),
        "Review-bridged cross-sectional study draft",
    )
    population = first_nonempty(protocol_inputs.get("population", ""), "Population to be specified during intake preflight")
    exposure = first_nonempty(protocol_inputs.get("exposure", ""))
    comparison = first_nonempty(protocol_inputs.get("comparator", ""))
    outcome = first_nonempty(protocol_inputs.get("outcome", ""), protocol_inputs.get("primary_outcomes", []))
    mediator = first_nonempty(protocol_inputs.get("mediator", ""))
    modifiers = clean_list(
        protocol_inputs.get("effect_modifiers", [])
        or protocol_inputs.get("pre_specified_subgroups", [])
    )
    confounders = clean_list(
        protocol_inputs.get("confounders", [])
        or protocol_inputs.get("key_confounders_main_model", [])
    )
    measurement_tools = clean_list(protocol_inputs.get("measurement_tools", []))
    objective_type = "association" if exposure and outcome else "prevalence"

    payload = {
        "contract_version": "2.0",
        "generated_at": today_iso(),
        "project_mode": normalize_project_mode(protocol_inputs.get("project_mode", "research")),
        "status": "draft",
        "decision_id": args.decision_id,
        "study_title": study_title,
        "full_protocol_title": f"{study_title}: Draft protocol intake bridged from literature-review outputs",
        "protocol_positioning": args.protocol_positioning,
        "keywords": clean_list(
            [
                protocol_inputs.get("design_type", "cross-sectional"),
                protocol_inputs.get("question_type", ""),
                protocol_inputs.get("review_goal", ""),
                exposure,
                outcome,
            ]
        ),
        "document_profile": {
            "protocol_version": "Version 2.1-draft-bridge",
            "registration": "To be specified after intake preflight",
            "funding": "To be specified during protocol setup",
            "study_team": "To be specified during intake preflight",
        },
        "background_inputs": build_background(protocol_inputs, exposure, outcome),
        "population_trinity": {
            "target_population": population,
            "source_population": "Source population to be specified during intake preflight",
            "analytic_population": "Analytic population to be specified after clarifying inclusion, exclusion, and data completeness rules",
            "inclusion_criteria": [
                "Core eligibility criteria to be frozen during intake preflight",
            ],
            "exclusion_criteria": [
                "Protocol-level exclusions to be frozen during intake preflight",
            ],
            "recruitment_sequence": [
                "Sampling and recruitment pathway to be specified during intake preflight",
                "Non-response handling to be made explicit before contracts are frozen",
            ],
            "non_response_plan": "Non-response handling is not frozen by the literature review alone and must be specified during intake preflight.",
            "generalizability_boundary": "The literature review can motivate the target population, but the final generalizability boundary depends on the eventual setting and sampling design.",
        },
        "study_design": {
            "design_label": "cross-sectional observational study",
            "study_setting": first_nonempty(args.setting, protocol_inputs.get("setting", ""), "Study setting to be specified during intake preflight"),
            "time_window": first_nonempty(args.time_window, "Time window to be specified during intake preflight"),
            "data_source": first_nonempty(
                args.data_source,
                clean_list(protocol_inputs.get("data_sources_recommended", [])),
                "Data source to be specified during intake preflight",
            ),
            "sampling_design": "Sampling design to be specified during intake preflight",
            "sampling_frame": "Sampling frame to be specified during intake preflight",
            "survey_design_features": [],
            "design_constraints": [
                "Do not freeze design-aware language until the sampling design is explicit",
                "Preserve any design variables required for weighted or clustered analysis if the final design is complex",
            ],
        },
        "measurement_plan": {
            "variable_roles": build_variable_roles(
                exposure,
                outcome,
                confounders,
                mediator,
                modifiers,
                measurement_tools,
            ),
            "measurement_sources": measurement_tools or ["Measurement tools to be finalized during intake preflight"],
            "measurement_quality": [
                "Operational scoring rules should be fixed before contracts are frozen",
                "Exposure and outcome definitions should not be rewritten after the protocol and SAP are aligned",
            ],
            "data_management_rules": [
                "Raw source data should remain read-only",
                "Derived variables should be generated reproducibly from documented code",
            ],
        },
        "study_objectives": build_objectives(protocol_inputs, exposure, outcome, comparison, modifiers),
        "bias_control_plan": {
            "confounding_plan": {
                "summary": "Confounder candidates were imported from the literature review, but the final adjustment set must be frozen during intake preflight rather than inferred from the evidence package alone."
            },
            "selection_bias_plan": {
                "summary": "Selection bias control cannot be finalized until the sampling frame, contact procedures, and analytic inclusion pathway are specified."
            },
            "information_bias_plan": {
                "summary": "Measurement tools were imported from the literature review, but information-bias safeguards still require final operational definitions and field procedures."
            },
            "missing_data_policy": {
                "summary": "Missing-data handling is not frozen by the literature review package and must be specified after clarifying likely patterns of incompleteness.",
                "steps": [
                    "Clarify whether exposure, outcome, or confounders may be incomplete",
                    "Define whether complete-case analysis, imputation, or both will be required",
                ],
            },
            "survey_awareness_policy": {
                "summary": "Survey-awareness remains conditional on the final sampling design and should not be declared as fixed until intake preflight is complete.",
                "required_features": [],
            },
        },
        "sample_size_plan": build_sample_size_plan(protocol_inputs, objective_type),
        "analysis_plan": {
            "deviation_policy": "This bridge artifact is draft-only. All protocol and SAP deviations from the final preflight-frozen intake must be logged explicitly."
        },
        "institutional_sections": {
            "ethics": "Ethics requirements must be written for the eventual data source and setting after intake preflight.",
            "consent_pathway": "Consent procedures depend on whether the final design uses primary data collection, existing records, or linked routine data.",
            "data_security": "Data-security controls must match the final data source, identifiers, and linkage plan.",
            "governance": "Protocol amendments and analysis deviations should be version-controlled once the design intake is frozen.",
            "authorship_policy": "Authorship and writing responsibilities should be finalized during protocol setup rather than inferred from the literature review package.",
            "publication_and_dissemination": "The final dissemination plan should be aligned to the protocol positioning after preflight and contract freeze.",
        },
        "reporting_commitments": [
            "Separate literature-review evidence synthesis from protocol commitments",
            "Freeze estimand, adjustment, and sample-size logic only after intake preflight",
            "Report deviations from the prespecified plan explicitly",
        ],
        "bridge_metadata": {
            "bridge_source": str(Path(args.protocol_inputs_json)),
            "bridge_type": "literature_review_protocol_inputs_to_design_intake_v2",
            "decision_ids": clean_list(protocol_inputs.get("decision_ids", [])),
        },
    }

    write_json(Path(args.output_json), payload)

# manage_guided_design_session
SCHEMA_VERSION = "1.0"
FORBIDDEN_TRACE_KEYS = {"reasoning", "internal_reasoning", "chain_of_thought", "scratchpad"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def reject_hidden_reasoning_fields(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            require(key not in FORBIDDEN_TRACE_KEYS, f"Hidden-reasoning field is prohibited at {path}.{key}")
            reject_hidden_reasoning_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_hidden_reasoning_fields(item, f"{path}[{index}]")


def validate_concept_parse(concept: dict) -> None:
    required = {
        "schema_version",
        "session_id",
        "generated_at",
        "source_text",
        "user_intent",
        "study_focus",
        "extracted_items",
        "candidate_objectives",
        "design_signals",
        "known_information",
        "methodological_tensions",
    }
    missing = sorted(required - set(concept))
    require(not missing, f"Concept parse missing required fields: {', '.join(missing)}")
    require(concept["schema_version"] == SCHEMA_VERSION, "Unsupported concept parse schema_version.")
    require(str(concept["session_id"]).strip(), "session_id must be non-empty.")
    require(str(concept["source_text"]).strip(), "source_text must be non-empty.")
    require(str(concept["study_focus"]).strip(), "study_focus must be non-empty.")
    require(isinstance(concept["candidate_objectives"], list) and concept["candidate_objectives"], "At least one candidate objective is required.")
    objective_ids = [str(item.get("objective_id", "")).strip() for item in concept["candidate_objectives"]]
    require(all(objective_ids), "Every candidate objective needs objective_id.")
    require(len(objective_ids) == len(set(objective_ids)), "candidate objective_id values must be unique.")

    intent = concept["user_intent"]
    output_request = intent.get("output_request")
    interaction_mode = intent.get("interaction_mode")
    require(output_request in {"none", "discuss", "generate", "audit"}, "Invalid output_request.")
    require(interaction_mode in {"guided", "direct", "audit"}, "Invalid interaction_mode.")
    if output_request in {"none", "discuss"}:
        require(interaction_mode == "guided", "A concept without an explicit generation request must enter guided mode.")
    if output_request == "audit":
        require(interaction_mode == "audit", "An audit request must enter audit mode.")

    signals = concept["design_signals"]
    signal_fields = {
        "mentions_probability_sampling",
        "mentions_stratification",
        "mentions_cluster_sampling",
        "mentions_multistage_sampling",
        "mentions_unequal_probability",
        "has_device_measurement",
        "has_scale_measurement",
        "has_multiple_data_sources",
        "has_continuous_outcome",
        "has_binary_outcome",
        "wants_broad_population_inference",
        "sites_fixed_by_narrative",
    }
    require(not (signal_fields - set(signals)), "design_signals is incomplete.")
    require(all(isinstance(signals[key], bool) for key in signal_fields), "Every design signal must be boolean.")
    reject_hidden_reasoning_fields(concept)


def objective_groups(concept: dict) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for objective in concept["candidate_objectives"]:
        groups.setdefault(objective["objective_family"], []).append(objective["objective_id"])
    return groups


def deep_merge(target: dict, updates: dict) -> dict:
    """Merge confirmed structured field updates without mutating the inputs."""
    merged = deepcopy(target)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def rebuild_design_state(session: dict, registry: dict) -> None:
    """Rebuild design state from the immutable parse plus active decisions.

    Rebuilding, rather than incrementally mutating, ensures that revising an
    upstream decision also removes field updates from superseded downstream
    decisions.
    """
    state = deepcopy(session.get("base_design_state", {}))
    for decision in registry.get("decisions", []):
        if decision.get("status") == "confirmed":
            state = deep_merge(state, decision.get("field_updates", {}))
    session["design_state"] = state


def node(
    node_id: str,
    title: str,
    domain: str,
    source_reference: str,
    objective_ids: list[str],
    entry_reason: str,
    question: str,
    downstream_impacts: list[str],
    depends_on: list[str] | None = None,
    blocks_generation: bool = True,
    resolution_stage: str = "before_contracts",
    known_information: list[str] | None = None,
) -> dict:
    return {
        "order": 0,
        "node_id": node_id,
        "title": title,
        "domain": domain,
        "source_reference": source_reference,
        "objective_ids": objective_ids,
        "entry_reason": entry_reason,
        "question": question,
        "blocks_generation": blocks_generation,
        "resolution_stage": resolution_stage,
        "depends_on": depends_on or [],
        "status": "pending",
        "known_information": known_information or [],
        "downstream_impacts": downstream_impacts,
        "decision_id": None,
    }


def known(concept: dict, *domains: str) -> list[str]:
    output: list[str] = []
    for domain in domains:
        for item in concept.get("known_information", {}).get(domain, []):
            if item not in output:
                output.append(item)
    return output


def build_route(concept: dict) -> list[dict]:
    groups = objective_groups(concept)
    all_objectives = [item["objective_id"] for item in concept["candidate_objectives"]]
    signals = concept["design_signals"]
    route: list[dict] = []

    route.append(
        node(
            "1.0_objective_triage",
            "研究目标拆分与优先级",
            "objectives",
            "references/design_standard.md",
            all_objectives,
            "The narrative contains one or more candidate scientific aims that must be separated and ranked before design commitments are frozen.",
            "Which objective is primary, which are secondary, and what claim boundary belongs to each?",
            ["estimands", "sample-size basis", "reporting order", "claim boundary"],
            known_information=known(concept, "objectives"),
        )
    )

    framework_nodes: list[str] = []
    if groups.get("prevalence"):
        framework_nodes.append("1.3_cocopop_specification")
        route.append(
            node(
                "1.3_cocopop_specification",
                "描述与患病率目标规范化",
                "objectives",
                "references/decision_tree.md",
                groups["prevalence"],
                "At least one objective estimates a distribution, burden, or prevalence and therefore requires a CoCoPop specification.",
                "What condition or distribution, context, population, and estimation metric define each descriptive objective?",
                ["target parameter", "representativeness requirement", "prevalence terminology"],
                depends_on=["1.0_objective_triage"],
                known_information=known(concept, "objectives", "population", "outcomes"),
            )
        )
    if groups.get("association"):
        framework_nodes.append("1.2_peco_specification")
        route.append(
            node(
                "1.2_peco_specification",
                "关联目标规范化",
                "objectives",
                "references/decision_tree.md",
                groups["association"],
                "At least one objective concerns an exposure-outcome association and therefore requires an objective-specific PECO specification.",
                "For each association objective, what are the population, exposure, comparison, outcome, and effect measure?",
                ["variable roles", "DAG route", "effect measure", "analysis family"],
                depends_on=["1.0_objective_triage"],
                known_information=known(concept, "objectives", "exposures", "outcomes"),
            )
        )
    if groups.get("prediction"):
        framework_nodes.append("1.P_prediction_specification")
        route.append(
            node(
                "1.P_prediction_specification",
                "预测目标规范化",
                "objectives",
                "references/design_standard.md",
                groups["prediction"],
                "At least one objective concerns prediction or classification rather than association.",
                "What target, prediction horizon or index time, predictor domain, and performance metric define the prediction objective?",
                ["analysis family", "validation plan", "performance reporting"],
                depends_on=["1.0_objective_triage"],
                known_information=known(concept, "objectives", "outcomes", "exposures"),
            )
        )

    route.append(
        node(
            "2.1_population_trinity",
            "目标、来源与分析人群",
            "population",
            "references/decision_tree.md",
            all_objectives,
            "Every objective needs an explicit population and inference boundary.",
            "Who is the target population, who can actually enter the sampling frame, and who will enter the final analysis?",
            ["eligibility", "sampling frame", "external validity", "analysis population"],
            depends_on=["1.0_objective_triage"],
            known_information=known(concept, "population", "setting"),
        )
    )
    route.append(
        node(
            "2.2_probability_decision",
            "概率抽样与推断边界",
            "sampling",
            "references/decision_tree.md",
            all_objectives,
            "The sampling claim must be reconciled with the available frames and the intended population inference.",
            "Are all relevant stages probability sampled, and what population can the resulting sample represent?",
            ["representativeness claim", "selection probabilities", "weights", "variance estimation"],
            depends_on=["2.1_population_trinity"],
            known_information=known(concept, "sampling", "population", "setting"),
        )
    )

    sampling_nodes: list[str] = []
    if signals["mentions_stratification"]:
        sampling_nodes.append("2.4_stratified_sampling")
        route.append(
            node(
                "2.4_stratified_sampling",
                "分层设计",
                "sampling",
                "references/decision_tree.md",
                all_objectives,
                "The narrative proposes stratification, so strata, allocation, and analysis consequences must be specified.",
                "What defines each stratum, how is sample allocated, and must strata be retained in analysis?",
                ["sample allocation", "weights", "precision", "survey design object"],
                depends_on=["2.2_probability_decision"],
                known_information=known(concept, "sampling", "setting"),
            )
        )
    if signals["mentions_cluster_sampling"] or signals["mentions_multistage_sampling"]:
        sampling_nodes.append("2.5_cluster_multistage")
        route.append(
            node(
                "2.5_cluster_multistage",
                "整群与多阶段抽样",
                "sampling",
                "references/decision_tree.md",
                all_objectives,
                "The narrative proposes cluster or multistage sampling, so PSUs, stages, frames, and probability formulas must be explicit.",
                "What are the sampling stages, PSUs, frames, and selection probabilities at each stage?",
                ["design effect", "sample size", "PSU variable", "survey variance"],
                depends_on=["2.2_probability_decision"],
                known_information=known(concept, "sampling", "setting"),
            )
        )
    if signals["mentions_unequal_probability"]:
        sampling_nodes.append("2.6_unequal_probability")
        route.append(
            node(
                "2.6_unequal_probability",
                "不等概率抽样与权重",
                "sampling",
                "references/decision_tree.md",
                all_objectives,
                "Unequal selection probabilities are proposed or implied and must generate a weight contract.",
                "Why are probabilities unequal, how will they be calculated, and how will weights be constructed?",
                ["base weights", "calibration", "population estimates", "sensitivity analysis"],
                depends_on=["2.2_probability_decision"],
                known_information=known(concept, "sampling"),
            )
        )

    analysis_sampling_dependencies = sampling_nodes or ["2.2_probability_decision"]
    route.append(
        node(
            "2.7_analysis_constraints",
            "抽样设计生成的分析约束",
            "sampling",
            "references/decision_tree.md",
            all_objectives,
            "The sampling design must propagate into the SAP rather than remain descriptive protocol prose.",
            "Which strata, PSU, weight, FPC, or supported variance representation must be carried into analysis?",
            ["survey analysis", "standard errors", "confidence intervals", "model execution"],
            depends_on=analysis_sampling_dependencies,
            known_information=known(concept, "sampling"),
        )
    )

    route.append(
        node(
            "3.1_measurement_validity",
            "结局、暴露与测量有效性",
            "measurement",
            "references/decision_tree.md",
            all_objectives,
            "The narrative names outcomes, instruments, or data fields that require operational definitions and validity checks.",
            "Which measurement definitions, versions, reference databases, scoring rules, and quality controls are valid for each variable?",
            ["outcome definition", "misclassification", "variable registry", "release terminology"],
            depends_on=["1.0_objective_triage"],
            known_information=known(concept, "measurement", "outcomes", "exposures"),
        )
    )
    route.append(
        node(
            "INTAKE.sample_size",
            "样本量依据",
            "sample_size",
            "references/design_standard.md",
            all_objectives,
            "Sample-size logic cannot be frozen until the primary objective, population, measurement, and sampling design are explicit.",
            "Which primary objective governs sample size, and what sourced assumptions, design effect, and nonresponse allowance apply?",
            ["final target sample", "field yield", "precision or power", "number of clusters"],
            depends_on=["1.0_objective_triage", "2.1_population_trinity", "2.7_analysis_constraints", "3.1_measurement_validity"],
            known_information=known(concept, "sample_size"),
        )
    )

    association_ids = groups.get("association", [])
    if association_ids:
        route.append(
            node(
                "4.1_dag_rationale",
                "关联问题的DAG边界",
                "bias_control",
                "references/decision_tree.md",
                association_ids,
                "Association objectives require explicit variable-role and adjustment logic even though cross-sectional temporality limits causal interpretation.",
                "What causal or temporal assumptions are defensible enough to organize confounders, mediators, colliders, and modifiers?",
                ["claim boundary", "DAG scope", "adjustment strategy", "sensitivity analysis"],
                depends_on=["1.2_peco_specification", "3.1_measurement_validity"],
                known_information=known(concept, "bias_control", "exposures", "outcomes"),
            )
        )
        route.append(
            node(
                "4.3_confounder_mediator",
                "变量角色判定",
                "bias_control",
                "references/decision_tree.md",
                association_ids,
                "Candidate predictors cannot be placed into one fully adjusted model without objective-specific role adjudication.",
                "For each exposure, which variables are confounders, mediators, colliders, or effect modifiers?",
                ["variable registry", "model sequence", "interaction plan", "overadjustment prevention"],
                depends_on=["4.1_dag_rationale"],
                known_information=known(concept, "bias_control", "exposures"),
            )
        )
        route.append(
            node(
                "4.4_backdoor_criterion",
                "暴露特异调整集",
                "bias_control",
                "references/decision_tree.md",
                association_ids,
                "Each association objective needs a prespecified adjustment set derived from the accepted structure.",
                "What is the minimum and primary adjustment set for each exposure-specific objective?",
                ["C0/M1/M2 models", "common-sample rule", "SAP formulas", "result interpretation"],
                depends_on=["4.3_confounder_mediator"],
                known_information=known(concept, "bias_control"),
            )
        )

    if signals["has_multiple_data_sources"]:
        route.append(
            node(
                "5.5_data_linkage",
                "多源数据关联",
                "data_governance",
                "references/decision_tree.md",
                all_objectives,
                "The study combines field measurements with another data source, so linkage rules and quality evidence are required.",
                "What keys, time window, duplicate rule, unmatched rule, linkage quality checks, and privacy separation govern integration?",
                ["analysis population", "missingness", "privacy", "linkage bias"],
                depends_on=["2.1_population_trinity", "3.1_measurement_validity"],
                known_information=known(concept, "data_sources", "data_linkage"),
            )
        )

    missing_dependencies = ["5.5_data_linkage"] if signals["has_multiple_data_sources"] else ["3.1_measurement_validity"]
    route.append(
        node(
            "5.3_missing_data",
            "缺失数据诊断与策略",
            "data_governance",
                "references/decision_tree.md",
            all_objectives,
            "Every analysis requires a prespecified missing-data diagnosis and fallback strategy.",
            "How will variable-level, record-level, and linkage-related missingness be diagnosed and handled?",
            ["analysis sample", "multiple imputation", "complete-case comparison", "limitations"],
            depends_on=missing_dependencies,
            known_information=known(concept, "missing_data", "data_sources"),
        )
    )

    analysis_dependencies = ["INTAKE.sample_size", "2.7_analysis_constraints", "5.3_missing_data"]
    if association_ids:
        analysis_dependencies.append("4.4_backdoor_criterion")
    route.append(
        node(
            "6.0_analysis_sequence",
            "统计分析依赖顺序",
            "analysis",
            "references/decision_tree.md",
            all_objectives,
            "The SAP must bind each objective to an executable sequence after sampling, measurement, bias-control, and missingness decisions are frozen.",
            "What estimand, analysis family, diagnostic actions, sensitivity hierarchy, and output shell belong to each objective?",
            ["SAP", "model formulas", "diagnostics", "tables and figures"],
            depends_on=analysis_dependencies,
            known_information=known(concept, "analysis"),
        )
    )

    route.append(
        node(
            "8.1_ethics_data_sharing",
            "伦理、隐私与共享计划",
            "governance",
            "references/decision_tree.md",
            all_objectives,
            "A protocol draft must expose rather than invent unresolved ethical, privacy, and data-sharing commitments.",
            "Which ethics, consent, privacy, data-access, and sharing elements are confirmed, pending, or unavailable?",
            ["release status", "protocol placeholders", "data governance", "dissemination"],
            depends_on=["2.1_population_trinity"],
            blocks_generation=False,
            resolution_stage="before_release",
            known_information=known(concept, "governance", "ethics"),
        )
    )
    for order, item in enumerate(route, start=1):
        item["order"] = order
    return route


def next_blocking_node(session: dict) -> dict | None:
    # A deferred node is temporarily skipped while later pending nodes remain,
    # then returned before the design can be authorized.
    statuses = {item["node_id"]: item["status"] for item in session["route"]}

    def prerequisites_complete(item: dict) -> bool:
        return all(statuses.get(dep) in {"completed", "not_applicable"} for dep in item["depends_on"])

    for item in session["route"]:
        if item["blocks_generation"] and item["status"] in {"pending", "blocked"} and prerequisites_complete(item):
            return item
    for item in session["route"]:
        if item["blocks_generation"] and item["status"] == "deferred" and prerequisites_complete(item):
            return item
    return None


def route_index(session: dict) -> dict[str, dict]:
    return {item["node_id"]: item for item in session["route"]}


def transitive_dependents(session: dict, node_id: str) -> set[str]:
    dependents: set[str] = set()
    changed = True
    while changed:
        changed = False
        for item in session["route"]:
            if item["node_id"] == node_id or item["node_id"] in dependents:
                continue
            if node_id in item["depends_on"] or any(dep in dependents for dep in item["depends_on"]):
                dependents.add(item["node_id"])
                changed = True
    return dependents


def refresh_session_status(session: dict) -> None:
    current = next_blocking_node(session)
    if current:
        session["current_node_id"] = current["node_id"]
        if current["status"] == "blocked":
            session["status"] = "blocked"
        elif current["status"] == "deferred":
            session["status"] = "paused"
        else:
            session["status"] = "in_progress"
    else:
        session["current_node_id"] = None
        session["status"] = "ready_for_contracts" if session.get("generation_authorized") else "design_complete_generation_unconfirmed"


def validate_session(session: dict, registry: dict) -> list[str]:
    errors: list[str] = []
    if session.get("schema_version") != SCHEMA_VERSION:
        errors.append("Unsupported session schema_version.")
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append("Unsupported registry schema_version.")
    if session.get("session_id") != registry.get("session_id"):
        errors.append("Session and registry session_id values differ.")
    if not isinstance(session.get("base_design_state"), dict):
        errors.append("base_design_state must be an object.")
    if not isinstance(session.get("design_state"), dict):
        errors.append("design_state must be an object.")
    node_ids = [item.get("node_id") for item in session.get("route", [])]
    if len(node_ids) != len(set(node_ids)):
        errors.append("Route node_id values must be unique.")
    nodes = set(node_ids)
    for item in session.get("route", []):
        missing_dependencies = set(item.get("depends_on", [])) - nodes
        if missing_dependencies:
            errors.append(f"{item.get('node_id')} has missing dependencies: {sorted(missing_dependencies)}")
        if item.get("decision_id"):
            matches = [decision for decision in registry.get("decisions", []) if decision.get("decision_id") == item["decision_id"]]
            if len(matches) != 1:
                errors.append(f"{item.get('node_id')} decision_id does not bind exactly one registry row.")
    if session.get("generation_authorized"):
        unresolved = [
            item["node_id"]
            for item in session.get("route", [])
            if item.get("blocks_generation") and item.get("status") != "completed"
        ]
        if unresolved:
            errors.append(f"Generation authorization exists with unresolved blocking nodes: {unresolved}")
    reject_hidden_reasoning_fields(session)
    reject_hidden_reasoning_fields(registry)
    return errors


def render_snapshot(session: dict, registry: dict) -> str:
    completed = sum(1 for item in session["route"] if item["status"] == "completed")
    blocking_total = sum(1 for item in session["route"] if item["blocks_generation"])
    blocking_complete = sum(1 for item in session["route"] if item["blocks_generation"] and item["status"] == "completed")
    lines = [
        "# Guided Design Snapshot",
        "",
        f"- Session: `{session['session_id']}`",
        f"- Mode: `{session['interaction_mode']}`",
        f"- Status: `{session['status']}`",
        f"- Current node: `{session.get('current_node_id') or 'none'}`",
        f"- Progress: `{completed}/{len(session['route'])}` routed nodes completed",
        f"- Generation gate: `{blocking_complete}/{blocking_total}` blocking nodes completed",
        f"- Generation authorized: `{session.get('generation_authorized', False)}`",
        "",
        "## Route",
        "",
        "| Order | Node | Domain | Status | Blocks generation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in session["route"]:
        lines.append(
            f"| {item['order']} | `{item['node_id']}` {item['title']} | {item['domain']} | {item['status']} | {item['blocks_generation']} |"
        )
    lines.extend(["", "## Confirmed decision trace", ""])
    active = [item for item in registry.get("decisions", []) if item.get("status") != "superseded"]
    if not active:
        lines.append("- No decision has been confirmed yet.")
    for item in active:
        lines.append(f"- `{item['decision_id']}` / `{item['node_id']}`: {item['decision_statement']}")
        lines.append(f"  - Basis: {item['rationale_summary']}")
        lines.append(f"  - Impacts: {', '.join(item['downstream_impacts'])}")
    lines.extend(
        [
            "",
            "## Current structured design",
            "",
            "```json",
            json.dumps(session.get("design_state", {}), ensure_ascii=False, indent=2),
            "```",
        ]
    )
    return "\n".join(lines)


def write_session_outputs(output_dir: Path, session: dict, registry: dict) -> None:
    rebuild_design_state(session, registry)
    refresh_session_status(session)
    errors = validate_session(session, registry)
    require(not errors, "Guided-session validation failed:\n- " + "\n- ".join(errors))
    write_json(output_dir / "guided_design_session.json", session)
    write_json(output_dir / "decision_trace_registry.json", registry)
    write_json(output_dir / "design_intake_draft.json", session["design_state"])
    current = route_index(session).get(session.get("current_node_id"))
    write_json(
        output_dir / "next_decision.json",
        {
            "session_id": session["session_id"],
            "status": session["status"],
            "current_decision": current,
            "generation_authorized": session.get("generation_authorized", False),
        },
    )
    write_text(output_dir / "design_snapshot.md", render_snapshot(session, registry))


def initialize(concept_path: Path, output_dir: Path) -> None:
    concept = load_json(concept_path)
    validate_concept_parse(concept)
    route = build_route(concept)
    base_design_state = {
        "schema_version": SCHEMA_VERSION,
        "session_id": concept["session_id"],
        "study_focus": concept["study_focus"],
        "source_text": concept["source_text"],
        "candidate_objectives": concept["candidate_objectives"],
        "design_signals": concept["design_signals"],
        "known_information": concept["known_information"],
        "methodological_tensions": concept["methodological_tensions"],
    }
    session = {
        "schema_version": SCHEMA_VERSION,
        "session_id": concept["session_id"],
        "source_sha256": hashlib.sha256(concept["source_text"].encode("utf-8")).hexdigest(),
        "interaction_mode": concept["user_intent"]["interaction_mode"],
        "status": "in_progress",
        "generation_authorized": False,
        "current_node_id": None,
        "requested_outputs": [],
        "study_focus": concept["study_focus"],
        "methodological_tensions": concept["methodological_tensions"],
        "base_design_state": base_design_state,
        "design_state": deepcopy(base_design_state),
        "route": route,
    }
    registry = {"schema_version": SCHEMA_VERSION, "session_id": concept["session_id"], "decisions": []}
    write_session_outputs(output_dir, session, registry)


def validate_response(response: dict) -> None:
    required = {
        "node_id",
        "action",
        "options_considered",
        "recommended_option",
        "user_choice",
        "decision_statement",
        "rationale_summary",
        "downstream_impacts",
        "field_updates",
    }
    missing = sorted(required - set(response))
    require(not missing, f"Decision response missing fields: {', '.join(missing)}")
    require(response["action"] in {"confirm", "defer", "block", "revise"}, "Invalid response action.")
    require(isinstance(response["options_considered"], list), "options_considered must be an array.")
    require(isinstance(response["downstream_impacts"], list) and response["downstream_impacts"], "downstream_impacts must be a non-empty array.")
    require(isinstance(response["field_updates"], dict), "field_updates must be an object.")
    for field in ["node_id", "user_choice", "decision_statement", "rationale_summary"]:
        require(str(response[field]).strip(), f"{field} must be non-empty.")
    reject_hidden_reasoning_fields(response)


def invalidate_downstream(session: dict, registry: dict, revised_node_id: str) -> None:
    affected = transitive_dependents(session, revised_node_id)
    for item in session["route"]:
        if item["node_id"] in affected and item["status"] in {"completed", "deferred", "blocked"}:
            if item.get("decision_id"):
                for decision in registry["decisions"]:
                    if decision["decision_id"] == item["decision_id"]:
                        decision["status"] = "superseded"
            item["status"] = "pending"
            item["decision_id"] = None
    session["generation_authorized"] = False
    session["requested_outputs"] = []


def answer(session_path: Path, registry_path: Path, response_path: Path, output_dir: Path) -> None:
    session = deepcopy(load_json(session_path))
    registry = deepcopy(load_json(registry_path))
    response = load_json(response_path)
    validate_response(response)
    nodes = route_index(session)
    node_id = response["node_id"]
    require(node_id in nodes, f"Unknown decision-tree node: {node_id}")
    target = nodes[node_id]

    if response["action"] != "revise":
        require(node_id == session.get("current_node_id"), "Only the current blocking node may be answered unless action=revise.")
    else:
        require(target["status"] == "completed", "Only a completed decision can be revised.")
        previous_decision_id = target.get("decision_id")
        require(previous_decision_id, "Revised node lacks a bound decision.")
        for decision in registry["decisions"]:
            if decision["decision_id"] == previous_decision_id:
                decision["status"] = "superseded"
        invalidate_downstream(session, registry, node_id)
        target["status"] = "pending"
        target["decision_id"] = None

    decision_id = f"GD-{len(registry['decisions']) + 1:04d}"
    action_status = {
        "confirm": ("completed", "confirmed"),
        "revise": ("completed", "confirmed"),
        "defer": ("deferred", "deferred"),
        "block": ("blocked", "blocked"),
    }
    node_status, decision_status = action_status[response["action"]]
    supersedes = response.get("supersedes")
    if response["action"] == "revise" and not supersedes:
        supersedes = previous_decision_id
    trace = {
        "decision_id": decision_id,
        "node_id": node_id,
        "objective_ids": target["objective_ids"],
        "options_considered": response["options_considered"],
        "recommended_option": response.get("recommended_option", ""),
        "user_choice": response["user_choice"],
        "decision_statement": response["decision_statement"],
        "rationale_summary": response["rationale_summary"],
        "evidence_references": response.get("evidence_references", []),
        "downstream_impacts": response["downstream_impacts"],
        "field_updates": response["field_updates"],
        "status": decision_status,
        "supersedes": supersedes,
        "recorded_at": response.get("recorded_at", now_iso()),
    }
    registry["decisions"].append(trace)
    target["status"] = node_status
    target["decision_id"] = decision_id
    if node_status != "completed" and target["blocks_generation"]:
        session["generation_authorized"] = False
    write_session_outputs(output_dir, session, registry)


def authorize(session_path: Path, registry_path: Path, confirmation_path: Path, output_dir: Path) -> None:
    session = deepcopy(load_json(session_path))
    registry = deepcopy(load_json(registry_path))
    confirmation = load_json(confirmation_path)
    require(confirmation.get("user_confirmed_generation") is True, "Explicit user confirmation is required.")
    requested = confirmation.get("requested_outputs", [])
    require(requested and all(item in {"protocol", "sap", "decision_trace", "design_snapshot"} for item in requested), "requested_outputs is invalid.")
    unresolved = [
        item["node_id"]
        for item in session["route"]
        if item["blocks_generation"] and item["status"] != "completed"
    ]
    require(not unresolved, f"Cannot authorize generation; unresolved blocking nodes: {', '.join(unresolved)}")
    session["generation_authorized"] = True
    session["requested_outputs"] = requested
    session["generation_authorized_at"] = confirmation.get("confirmed_at", now_iso())
    write_session_outputs(output_dir, session, registry)


def validate_files(session_path: Path, registry_path: Path) -> None:
    session = load_json(session_path)
    registry = load_json(registry_path)
    errors = validate_session(session, registry)
    if errors:
        raise SystemExit("Guided-session validation failed:\n- " + "\n- ".join(errors))
    print("GUIDED_DESIGN_VALID")


def main_manage_guided_design_session() -> None:
    parser = argparse.ArgumentParser(description="Create and update auditable guided cross-sectional design sessions.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init")
    init_parser.add_argument("concept_parse")
    init_parser.add_argument("output_dir")

    answer_parser = sub.add_parser("answer")
    answer_parser.add_argument("session")
    answer_parser.add_argument("registry")
    answer_parser.add_argument("response")
    answer_parser.add_argument("output_dir")

    authorize_parser = sub.add_parser("authorize")
    authorize_parser.add_argument("session")
    authorize_parser.add_argument("registry")
    authorize_parser.add_argument("confirmation")
    authorize_parser.add_argument("output_dir")

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("session")
    validate_parser.add_argument("registry")

    args = parser.parse_args()
    if args.command == "init":
        initialize(Path(args.concept_parse), Path(args.output_dir))
    elif args.command == "answer":
        answer(Path(args.session), Path(args.registry), Path(args.response), Path(args.output_dir))
    elif args.command == "authorize":
        authorize(Path(args.session), Path(args.registry), Path(args.confirmation), Path(args.output_dir))
    else:
        validate_files(Path(args.session), Path(args.registry))

# validate_design_intake_semantics
REQUIRED_ANALYSIS_STAGE_ORDER = [
    "data_freeze_and_linkage",
    "data_quality_control",
    "variable_derivation",
    "survey_design_construction",
    "analysis_population_and_missingness",
    "descriptive_analysis",
    "bivariate_descriptive_analysis",
    "primary_model_sequence",
    "model_diagnostics",
    "advanced_and_interaction_analysis",
    "sensitivity_analysis",
    "multiplicity_control",
    "tables_figures_and_provenance",
]
PROBABILITY_SELECTION_TYPES = {"probability", "random", "census"}
NONPROBABILITY_SELECTION_TYPES = {"fixed", "purposive", "convenience", "nonprobability"}
QUESTIONNAIRE_SOURCE_TYPES = {
    "validated_existing",
    "adapted_existing",
    "study_authored",
    "questionnaire",
    "scale",
}
LICENCE_STATUSES = {
    "public_domain",
    "permission_obtained",
    "licensed",
    "not_required",
    "restricted_not_reproduced",
}
INFERENCE_SCOPES = {
    "full_target_population",
    "source_frame_only",
    "selected_sites_only",
    "sample_only",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", _text(value).lower()).strip("_")


def _nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _field(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping and mapping[name] not in (None, "", []):
            return mapping[name]
    return None


def _append(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _contains_any(value: Any, tokens: Iterable[str]) -> bool:
    haystack = _text(value).lower()
    return any(token.lower() in haystack for token in tokens)


def _check_sampling(intake: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    sampling = _first_mapping(
        intake.get("sampling_plan"),
        intake.get("protocol_operations", {}).get("sampling")
        if isinstance(intake.get("protocol_operations"), dict)
        else None,
    )
    _append(errors, bool(sampling), "sampling_plan is required in research mode")
    if not sampling:
        return errors, {"stage_count": 0}

    name = _text(_field(sampling, "canonical_design_name", "design_name"))
    _append(errors, bool(name), "sampling_plan.canonical_design_name is required")
    stages = _field(sampling, "stages", "selection_stages")
    _append(errors, _nonempty_list(stages), "sampling_plan.stages must be a non-empty array")
    if not _nonempty_list(stages):
        return errors, {"canonical_design_name": name, "stage_count": 0}

    orders: list[int] = []
    selection_types: list[str] = []
    selection_stage_ids: list[str] = []
    has_stratification = bool(_field(sampling, "strata", "stratification_variables"))
    has_cluster = False
    for index, raw_stage in enumerate(stages, start=1):
        if not isinstance(raw_stage, dict):
            errors.append(f"sampling stage {index} must be an object")
            selection_stage_ids.append(f"stage_{index}")
            selection_types.append("")
            continue
        label = _text(raw_stage.get("stage_id")) or f"stage {index}"
        selection_stage_ids.append(label)
        order = raw_stage.get("order")
        _append(errors, isinstance(order, int) and order > 0, f"{label}: positive integer order is required")
        if isinstance(order, int):
            orders.append(order)
        for key in ("stage_id", "unit", "frame", "selection_type", "selection_method", "id_variable"):
            _append(errors, bool(_text(raw_stage.get(key))), f"{label}: {key} is required")
        selection_type = _norm(raw_stage.get("selection_type"))
        selection_types.append(selection_type)
        if selection_type in PROBABILITY_SELECTION_TYPES and selection_type != "census":
            _append(
                errors,
                bool(_text(raw_stage.get("probability_formula"))),
                f"{label}: probability_formula is required for probability selection",
            )
        if selection_type not in PROBABILITY_SELECTION_TYPES | NONPROBABILITY_SELECTION_TYPES:
            errors.append(f"{label}: unsupported selection_type '{selection_type or 'missing'}'")
        has_stratification = has_stratification or bool(raw_stage.get("strata"))
        has_cluster = has_cluster or bool(raw_stage.get("is_psu")) or _contains_any(
            raw_stage.get("unit"), ["cluster", "community", "village", "ward", "psu", "整群", "村", "社区"]
        )

    _append(errors, len(orders) == len(set(orders)), "sampling stage orders must be unique")
    if orders:
        _append(errors, sorted(orders) == list(range(1, len(orders) + 1)), "sampling stage orders must be consecutive from 1")

    analysis_design = sampling.get("analysis_design", {})
    _append(errors, isinstance(analysis_design, dict) and bool(analysis_design), "sampling_plan.analysis_design is required")
    if isinstance(analysis_design, dict):
        if has_stratification:
            _append(errors, bool(_text(analysis_design.get("strata_variable"))), "analysis_design.strata_variable is required for stratified sampling")
        if has_cluster or len(stages) > 1:
            _append(errors, bool(_text(analysis_design.get("psu_variable"))), "analysis_design.psu_variable is required for clustered/multistage sampling")
        if len(stages) > 1 or any(x != "census" for x in selection_types):
            _append(errors, bool(_text(analysis_design.get("weight_variable"))), "analysis_design.weight_variable is required for multistage/unequal-probability sampling")
        _append(errors, bool(_text(analysis_design.get("variance_estimator"))), "analysis_design.variance_estimator is required")

    boundary = sampling.get("inference_boundary", {})
    _append(errors, isinstance(boundary, dict) and bool(boundary), "sampling_plan.inference_boundary is required")
    scope = _norm(boundary.get("scope")) if isinstance(boundary, dict) else ""
    statement = _text(boundary.get("statement")) if isinstance(boundary, dict) else ""
    claim = _text(boundary.get("representativeness_claim")) if isinstance(boundary, dict) else ""
    _append(errors, scope in INFERENCE_SCOPES, f"inference_boundary.scope must be one of {sorted(INFERENCE_SCOPES)}")
    _append(errors, bool(statement), "inference_boundary.statement is required")
    _append(errors, bool(claim), "inference_boundary.representativeness_claim is required")

    nonprobability_stages = [
        selection_stage_ids[index]
        for index, kind in enumerate(selection_types)
        if kind in NONPROBABILITY_SELECTION_TYPES
    ]
    declared_complete = sampling.get("probability_chain_complete")
    if nonprobability_stages:
        _append(errors, declared_complete is False, "probability_chain_complete must be false when any sampling stage is fixed or non-probability")
        _append(errors, scope in {"selected_sites_only", "sample_only"}, "fixed/non-probability stages require an inference boundary limited to selected sites or the sample")
        prohibited_claim = _contains_any(
            claim,
            ["province-wide", "provincial", "national", "full target", "全省", "省级代表", "全国", "目标总体代表"],
        )
        _append(errors, not prohibited_claim, "representativeness_claim overstates coverage despite a fixed/non-probability sampling stage")
        _append(errors, _contains_any(name, ["fixed", "purposive", "固定", "目的"]), "canonical_design_name must disclose a fixed/purposive stage")
    else:
        _append(errors, declared_complete is True, "probability_chain_complete must be true when every non-census stage is probabilistic")
        _append(errors, bool(_text(sampling.get("overall_inclusion_probability_formula"))), "overall_inclusion_probability_formula is required for a complete probability chain")
        _append(errors, bool(_text(sampling.get("base_weight_formula"))), "base_weight_formula is required for a complete probability chain")

    if has_stratification:
        _append(errors, _contains_any(name, ["stratified", "分层"]), "canonical_design_name must identify stratification")
    if has_cluster or len(stages) > 1:
        _append(errors, _contains_any(name, ["cluster", "multistage", "multi-stage", "整群", "多阶段"]), "canonical_design_name must identify clustering or multistage selection")

    return errors, {
        "canonical_design_name": name,
        "stage_count": len(stages),
        "selection_types": selection_types,
        "nonprobability_stages": nonprobability_stages,
        "inference_scope": scope,
    }


def _is_questionnaire_or_scale(item: dict[str, Any]) -> bool:
    kind = _norm(item.get("instrument_type"))
    source_type = _norm(item.get("source_type"))
    text = " ".join(_text(item.get(key)) for key in ("instrument", "measurement_source", "variable"))
    return (
        kind in {"questionnaire", "scale"}
        or source_type in QUESTIONNAIRE_SOURCE_TYPES
        or _contains_any(text, ["questionnaire", "scale", "survey", "inventory", "问卷", "量表"])
    )


def _check_measurement(intake: dict[str, Any], base_dir: Path | None) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    measurement = intake.get("measurement_plan", {})
    details = measurement.get("instrument_details", []) if isinstance(measurement, dict) else []
    _append(errors, isinstance(details, list), "measurement_plan.instrument_details must be an array")
    if not isinstance(details, list):
        return errors, {"questionnaire_scale_count": 0}
    question_items = [item for item in details if isinstance(item, dict) and _is_questionnaire_or_scale(item)]
    appendix_hashes: dict[str, str] = {}
    for index, item in enumerate(question_items, start=1):
        label = _text(item.get("variable")) or f"questionnaire/scale {index}"
        source_type = _norm(item.get("source_type"))
        _append(errors, source_type in QUESTIONNAIRE_SOURCE_TYPES, f"{label}: recognized source_type is required")
        _append(errors, bool(_text(item.get("instrument"))), f"{label}: instrument name is required")
        _append(errors, bool(_field(item, "source_reference", "citations", "source_citation")), f"{label}: source citation/reference is required")
        _append(errors, bool(_field(item, "version", "version_language")), f"{label}: instrument version is required")
        _append(errors, bool(_field(item, "language", "version_language")), f"{label}: instrument language is required")
        licence = _norm(_field(item, "license_status", "licence_status"))
        _append(errors, licence in LICENCE_STATUSES, f"{label}: license_status must be one of {sorted(LICENCE_STATUSES)}")
        _append(errors, bool(_text(item.get("scoring"))), f"{label}: scoring rule is required")
        _append(errors, bool(_text(item.get("item_missing_rule"))), f"{label}: item_missing_rule is required")
        appendix = item.get("appendix", {})
        _append(errors, isinstance(appendix, dict) and bool(appendix), f"{label}: appendix disposition is required")
        if isinstance(appendix, dict):
            status = _norm(appendix.get("status"))
            _append(errors, status in {"included", "official_source_only", "restricted_not_reproduced"}, f"{label}: unsupported appendix.status")
            if status == "included":
                inline_items = appendix.get("items")
                path_value = _text(appendix.get("path"))
                _append(errors, _nonempty_list(inline_items) or bool(path_value), f"{label}: included appendix needs inline items or path")
                if _nonempty_list(inline_items):
                    for item_index, appendix_item in enumerate(inline_items, start=1):
                        if not isinstance(appendix_item, dict):
                            errors.append(f"{label}: appendix item {item_index} must be an object")
                            continue
                        for key in ("item_id", "wording", "response_options", "skip_logic"):
                            value = appendix_item.get(key)
                            valid = _nonempty_list(value) if key == "response_options" else bool(_text(value))
                            _append(errors, valid, f"{label}: appendix item {item_index} requires {key}")
                    appendix_hashes[label] = hashlib.sha256(
                        json.dumps(inline_items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                if path_value and base_dir is not None:
                    appendix_path = base_dir / path_value
                    _append(errors, appendix_path.is_file(), f"{label}: appendix path does not exist: {path_value}")
                    declared_sha = _text(appendix.get("sha256")).lower()
                    _append(errors, bool(re.fullmatch(r"[0-9a-f]{64}", declared_sha)), f"{label}: appendix path requires sha256")
                    if appendix_path.is_file() and re.fullmatch(r"[0-9a-f]{64}", declared_sha):
                        actual_sha = hashlib.sha256(appendix_path.read_bytes()).hexdigest()
                        _append(errors, actual_sha == declared_sha, f"{label}: appendix sha256 mismatch")
                        appendix_hashes[label] = actual_sha
            elif status in {"official_source_only", "restricted_not_reproduced"}:
                _append(errors, bool(_text(appendix.get("official_source"))), f"{label}: official_source is required when items are not reproduced")
            if licence == "restricted_not_reproduced":
                _append(errors, status == "restricted_not_reproduced", f"{label}: restricted licence must use appendix.status=restricted_not_reproduced")
    return errors, {"instrument_count": len(details), "questionnaire_scale_count": len(question_items), "appendix_sha256": appendix_hashes}


def _check_linkage(intake: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    plan = intake.get("data_linkage_plan")
    _append(errors, isinstance(plan, dict) and bool(plan), "data_linkage_plan is required in research mode")
    if not isinstance(plan, dict) or not plan:
        return errors, {"status": "missing"}
    status = _norm(plan.get("status"))
    _append(errors, status in {"required", "not_applicable"}, "data_linkage_plan.status must be required or not_applicable")
    if status == "not_applicable":
        _append(errors, bool(_text(plan.get("rationale"))), "data_linkage_plan.rationale is required when linkage is not applicable")
        return errors, {"status": status, "source_count": 1}
    if status != "required":
        return errors, {"status": status or "invalid"}

    sources = plan.get("sources")
    _append(errors, isinstance(sources, list) and len(sources) >= 2, "required data linkage needs at least two source records")
    if isinstance(sources, list):
        for index, source in enumerate(sources, start=1):
            if not isinstance(source, dict):
                errors.append(f"data linkage source {index} must be an object")
                continue
            label = _text(source.get("source_id")) or f"source {index}"
            for key in ("source_id", "snapshot_or_period", "unit"):
                _append(errors, bool(_text(source.get(key))), f"{label}: {key} is required")
    required_fields = {
        "linkage_keys": lambda value: _nonempty_list(value),
        "linkage_method": lambda value: bool(_text(value)),
        "temporal_window": lambda value: bool(_text(value)),
        "duplicate_resolution": lambda value: bool(_text(value)),
        "unmatched_rule": lambda value: bool(_text(value)),
        "quality_checks": lambda value: _nonempty_list(value),
        "privacy_separation": lambda value: bool(_text(value)),
    }
    for key, predicate in required_fields.items():
        _append(errors, predicate(plan.get(key)), f"data_linkage_plan.{key} is required")
    return errors, {"status": status, "source_count": len(sources) if isinstance(sources, list) else 0}


def _check_bias_controls(intake: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    plan = intake.get("bias_control_plan", {})
    controls = plan.get("controls") if isinstance(plan, dict) else None
    _append(errors, _nonempty_list(controls), "bias_control_plan.controls must be a non-empty structured array")
    if not _nonempty_list(controls):
        return errors, {"control_count": 0, "domains": []}
    objective_ids = {_text(row.get("objective_id")) for row in intake.get("study_objectives", []) if isinstance(row, dict)}
    domains: set[str] = set()
    required = [
        "objective_id",
        "bias_domain",
        "mechanism",
        "design_control",
        "field_control",
        "analysis_control",
        "sensitivity_output",
        "monitoring_indicator",
        "threshold",
        "action",
        "residual_risk",
    ]
    for index, control in enumerate(controls, start=1):
        if not isinstance(control, dict):
            errors.append(f"bias control {index} must be an object")
            continue
        label = _text(control.get("bias_domain")) or f"bias control {index}"
        for key in required:
            _append(errors, bool(_text(control.get(key))), f"{label}: {key} is required")
        objective_id = _text(control.get("objective_id"))
        _append(errors, objective_id in objective_ids, f"{label}: objective_id must match a declared study objective")
        domains.add(_norm(control.get("bias_domain")))
    canonical_domains = {
        "selection": {"selection", "selection_bias", "选择偏倚"},
        "information": {"information", "information_bias", "measurement", "信息偏倚", "测量偏倚"},
        "confounding": {"confounding", "confounding_bias", "混杂", "混杂偏倚"},
        "missing_data": {"missing_data", "missingness", "缺失数据", "缺失"},
    }
    for label, aliases in canonical_domains.items():
        _append(errors, bool(domains & aliases), f"bias_control_plan.controls lacks the {label} domain")
    return errors, {"control_count": len(controls), "domains": sorted(domains)}


def _stage_ids(intake: dict[str, Any]) -> list[str]:
    analysis_plan = intake.get("analysis_plan", {})
    sap_details = intake.get("sap_details", {})
    raw = None
    if isinstance(analysis_plan, dict):
        raw = analysis_plan.get("analysis_sequence")
    if raw is None and isinstance(sap_details, dict):
        raw = sap_details.get("analysis_sequence")
    if not isinstance(raw, list):
        return []
    result = []
    for stage in raw:
        if isinstance(stage, dict):
            result.append(_norm(_field(stage, "stage_id", "id")))
        else:
            result.append(_norm(stage))
    return result


def _check_analysis_sequence(intake: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    observed = _stage_ids(intake)
    _append(errors, bool(observed), "analysis_plan.analysis_sequence is required")
    positions: list[int] = []
    for required in REQUIRED_ANALYSIS_STAGE_ORDER:
        if required not in observed:
            errors.append(f"analysis sequence missing required stage: {required}")
        else:
            positions.append(observed.index(required))
    if len(positions) == len(REQUIRED_ANALYSIS_STAGE_ORDER):
        _append(errors, positions == sorted(positions), "required statistical stages are not in the frozen execution order")
    _append(errors, len(observed) == len(set(observed)), "analysis sequence stage identifiers must be unique")
    return errors, {"observed": observed, "required": REQUIRED_ANALYSIS_STAGE_ORDER}


def _model_level(value: Any) -> str:
    normalized = _norm(value)
    for level in ("m0", "m1", "m2"):
        if normalized == level or normalized.startswith(level + "_"):
            return level.upper()
    return ""


def _check_adjustment_sequences(intake: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    inspected: list[str] = []
    for objective in intake.get("study_objectives", []):
        if not isinstance(objective, dict):
            continue
        objective_id = _text(objective.get("objective_id")) or "UNKNOWN"
        objective_type = _norm(objective.get("objective_type"))
        framework = _norm(objective.get("framework"))
        strategy = objective.get("adjustment_strategy", {})
        is_association = objective_type == "association" or framework == "peco" or bool(strategy)
        if not is_association:
            continue
        inspected.append(objective_id)
        _append(errors, isinstance(strategy, dict) and bool(strategy), f"{objective_id}: adjustment_strategy is required for an association objective")
        if not isinstance(strategy, dict):
            continue
        common_rule = _text(_field(strategy, "common_sample_rule", "analysis_sample_definition"))
        _append(errors, bool(common_rule), f"{objective_id}: common_sample_rule is required for M0/M1/M2")
        sequence = _field(strategy, "model_sequence", "models")
        _append(errors, _nonempty_list(sequence), f"{objective_id}: adjustment_strategy.model_sequence is required")
        if not _nonempty_list(sequence):
            continue
        rows: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(sequence, start=1):
            if not isinstance(row, dict):
                errors.append(f"{objective_id}: model sequence row {index} must be an object")
                continue
            level = _model_level(_field(row, "level", "model_level", "model_id"))
            _append(errors, bool(level), f"{objective_id}: model sequence row {index} must identify M0, M1, or M2")
            if level:
                _append(errors, level not in rows, f"{objective_id}: duplicate {level} model row")
                rows[level] = row
        for level in ("M0", "M1", "M2"):
            _append(errors, level in rows, f"{objective_id}: model sequence missing {level}")
        if not all(level in rows for level in ("M0", "M1", "M2")):
            continue
        sample_ids = [_text(_field(rows[level], "analysis_sample_id", "sample_id")) for level in ("M0", "M1", "M2")]
        _append(errors, all(sample_ids), f"{objective_id}: every M0/M1/M2 row requires analysis_sample_id")
        _append(errors, len(set(sample_ids)) == 1, f"{objective_id}: M0/M1/M2 must use the same analysis_sample_id")
        adjustment_sets: dict[str, set[str]] = {}
        for level in ("M0", "M1", "M2"):
            value = rows[level].get("adjustment_set")
            _append(errors, isinstance(value, list), f"{objective_id}: {level}.adjustment_set must be an array")
            adjustment_sets[level] = {_text(item) for item in value} if isinstance(value, list) else set()
        _append(errors, adjustment_sets["M0"].issubset(adjustment_sets["M1"]), f"{objective_id}: M0 adjustment set must be nested within M1")
        _append(errors, adjustment_sets["M1"].issubset(adjustment_sets["M2"]), f"{objective_id}: M1 adjustment set must be nested within M2")
    return errors, {"association_objectives_checked": inspected}


def validate_design_intake(intake: dict[str, Any], base_dir: Path | None = None) -> dict[str, Any]:
    """Return a JSON-serializable semantic audit for one design intake."""

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    project_mode = _norm(intake.get("project_mode"))
    if project_mode != "research":
        warnings.append("strict design-intake semantic checks were skipped because project_mode is not research")
        checks.append({"check": "research_mode_gate", "status": "skipped", "evidence": {"project_mode": project_mode}})
        return {
            "validator": "cross_sectional_design_intake_semantics",
            "status": "warn",
            "project_mode": project_mode,
            "checks": checks,
            "errors": errors,
            "warnings": warnings,
        }

    validators = [
        ("sampling_probability_and_inference_boundary", lambda: _check_sampling(intake)),
        ("questionnaire_scale_provenance", lambda: _check_measurement(intake, base_dir)),
        ("data_linkage_plan", lambda: _check_linkage(intake)),
        ("structured_bias_control", lambda: _check_bias_controls(intake)),
        ("fixed_statistical_sequence", lambda: _check_analysis_sequence(intake)),
        ("common_sample_adjustment_sequence", lambda: _check_adjustment_sequences(intake)),
    ]
    for name, validator in validators:
        domain_errors, evidence = validator()
        errors.extend(domain_errors)
        checks.append(
            {
                "check": name,
                "status": "fail" if domain_errors else "pass",
                "errors": domain_errors,
                "evidence": evidence,
            }
        )
    return {
        "validator": "cross_sectional_design_intake_semantics",
        "status": "fail" if errors else ("warn" if warnings else "pass"),
        "project_mode": project_mode,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main_validate_design_intake_semantics() -> int:
    parser = argparse.ArgumentParser(description="Validate semantic completeness of a cross-sectional design intake.")
    parser.add_argument("design_intake_json")
    parser.add_argument("output_json")
    args = parser.parse_args()
    intake_path = Path(args.design_intake_json).resolve()
    output_path = Path(args.output_json)
    try:
        raw = intake_path.read_bytes()
        intake = json.loads(raw.decode("utf-8"))
        if not isinstance(intake, dict):
            raise ValueError("top-level design intake must be a JSON object")
        payload = validate_design_intake(intake, base_dir=intake_path.parent)
        payload["input_sha256"] = {str(intake_path): hashlib.sha256(raw).hexdigest()}
    except Exception as exc:  # Ensure malformed input also yields an auditable JSON failure.
        payload = {
            "validator": "cross_sectional_design_intake_semantics",
            "status": "fail",
            "project_mode": "unknown",
            "checks": [],
            "errors": [f"unable to validate design intake: {exc}"],
            "warnings": [],
            "input_sha256": {},
        }
    _write_json(output_path, payload)
    if payload["status"] == "fail":
        return 1
    return 0


COMMANDS = {
    "adapt_review_to_design_intake": main_adapt_review_to_design_intake,
    "manage_guided_design_session": main_manage_guided_design_session,
    "validate_design_intake_semantics": main_validate_design_intake_semantics,
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
