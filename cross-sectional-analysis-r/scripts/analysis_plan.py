#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/analysis_plan.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from analysis_common import (
    COMMON_EXTENDED_FAMILIES,
    PATH_MODE_VALUES,
    SPECIALIZED_EXTENDED_FAMILIES,
    STAGE_ORDER,
    detect_design_columns,
    default_figure_families,
    discover_inputs,
    ensure_data_profile,
    infer_exposure_form,
    infer_outcome_family,
    load_json,
    load_objectives,
    load_structured,
    make_id,
    method_tier,
    now_iso,
    normalize_project_mode,
    primary_method_id,
    resolve_method_family,
    result_schema_name,
    write_json,
)

# adjudicate_feasibility


def profile_lookup(profile: dict, column: str) -> dict:
    for item in profile.get("schema", []):
        if item.get("name") == column:
            return item
    return {}


def stage_entry(status: str, path_mode: str, reason: str) -> dict:
    assert path_mode in PATH_MODE_VALUES
    return {"status": status, "path_mode": path_mode, "reason": reason}


def adjudicate(project_root: Path, requested_plan: dict, rules: dict) -> dict:
    profile, _ = ensure_data_profile(project_root)
    sparse_levels = profile.get("sparse_levels", {})
    missingness = profile.get("missingness_by_column", {})
    binary_prevalence = profile.get("binary_prevalence", {})
    schema_lookup = {item["name"]: item for item in profile.get("schema", [])}
    design_requested = requested_plan.get("design_context_requested", {})
    weight_var = design_requested.get("weight_variable", "")
    strata_var = design_requested.get("strata_variable", "")
    psu_var = design_requested.get("psu_variable", "")
    design_text = (design_requested.get("sampling_design", "") + " " + design_requested.get("survey_strategy", "")).lower()
    survey_requested = any(
        token in design_text
        for token in ("survey", "stratified", "multi-stage", "multistage", "cluster", "probability sampling")
    )
    decisions = []
    deviations = []
    objective_execution_map = []
    executable_objectives = []

    has_weight = bool(weight_var)
    has_strata = bool(strata_var)
    has_psu = bool(psu_var)
    if survey_requested and has_weight and has_psu:
        design_mode = "survey_full"
        design_verified_level = "full"
        design_capabilities = {
            "point_estimation": "design_weighted",
            "variance_estimation": "survey_design_based",
            "target_population_extrapolation": "requires_verified_frame_and_probability_chain",
        }
    elif survey_requested and has_weight and rules["rules"]["allow_weight_only_without_psu"]:
        design_mode = "survey_weight_only"
        design_verified_level = "degraded_with_deviation"
        design_capabilities = {
            "point_estimation": "supplied_weight_point_description",
            "variance_estimation": "formal_survey_variance_unavailable",
            "target_population_extrapolation": "not_established_by_weights_alone",
        }
        decisions.append(
            {
                "decision_id": make_id("DEC", 1),
                "decision_type": "design_path",
                "source": "data_profile",
                "rule_trigger": "allow_weight_only_without_psu",
                "input_evidence": {"weight_variable": weight_var, "psu_variable": psu_var, "strata_variable": strata_var},
                "selected_option": "survey_weight_only",
                "rejected_options": ["survey_full"],
                "justification": "Weights are available but PSU is missing; the rules allow a degraded weight-only path.",
                "linked_stage_id": "primary_model_stage",
                "linked_objective_id": "GLOBAL"
            }
        )
        deviations.append(
            {
                "deviation_id": make_id("DEV", 1),
                "linked_stage_id": "primary_model_stage",
                "linked_objective_id": "GLOBAL",
                "reason": "PSU variable unavailable",
                "impact": "Full survey variance estimation not available; weight-only path retained as degraded design-aware analysis.",
                "status": "degraded_with_deviation"
            }
        )
    else:
        design_mode = "sample"
        design_verified_level = "sample_based"
        design_capabilities = {
            "point_estimation": "realized_sample",
            "variance_estimation": "individual_independence_unless_cluster_support_is_registered",
            "target_population_extrapolation": "not_established",
        }

    decision_index = len(decisions)
    deviation_index = len(deviations)

    for objective in requested_plan.get("requested_objectives", []):
        objective_id = objective["objective_id"]
        exposure_var = objective.get("exposure_var", "")
        outcome_var = objective.get("outcome_var", "")
        exposure_missing = missingness.get(exposure_var, {}).get("pct_missing", 0.0)
        outcome_missing = missingness.get(outcome_var, {}).get("pct_missing", 0.0)
        max_missing = max(exposure_missing, outcome_missing)
        modifier_sparse = any(len(sparse_levels.get(modifier, {})) > 0 for modifier in objective.get("modifier_candidates", []))
        binary_counts = binary_prevalence.get(outcome_var, {})
        min_events = binary_counts.get("min_level_count", 0)
        requested_family = objective.get("requested_method_family", "")
        outcome_info = schema_lookup.get(outcome_var, {})

        stage_map = {
            "qc_stage": stage_entry("required", "full", "Always required to establish data structure and analytic sample."),
            "missingness_stage": stage_entry(
                "required",
                "full" if max_missing >= rules["rules"]["missingness_pct_for_mi_recommendation"] else "simplified",
                "Missingness stage remains required; path mode depends on observed incompleteness."
            ),
            "descriptive_stage": stage_entry("required", "full", "Descriptive stage is always required."),
            "bivariate_stage": stage_entry("conditional", "simplified", "Exploratory bivariate summaries are optional but recommended."),
            "primary_model_stage": stage_entry("required", "degraded" if design_mode == "survey_weight_only" else "full", "Primary model is always required."),
            "interaction_stage": stage_entry("conditional", "full", "Interaction requires a modifier candidate and sufficient support."),
            "dose_response_stage": stage_entry("conditional", "full", "Dose-response is only relevant for continuous or ordinal exposures."),
            "sensitivity_stage": stage_entry("required", "simplified", "At least one sensitivity path is required."),
            "registry_finalize_stage": stage_entry("required", "full", "Registries must be frozen before reporting."),
            "report_stage": stage_entry("required", "full", "Report stage is required after audits and freeze.")
        }
        extension_activation = "default_mainline"
        if requested_family in COMMON_EXTENDED_FAMILIES:
            extension_activation = "common_extended"
            decision_index += 1
            decisions.append(
                {
                    "decision_id": make_id("DEC", decision_index),
                    "decision_type": "extension_activation",
                    "source": "adjudication_rules",
                    "rule_trigger": "common_extended_family_allowed",
                    "input_evidence": {"requested_method_family": requested_family, "outcome_family": objective.get("outcome_family")},
                    "selected_option": requested_family,
                    "rejected_options": ["default_mainline_substitution"],
                    "justification": "A common extended family was explicitly requested or inferred and remains admissible.",
                    "linked_stage_id": "primary_model_stage",
                    "linked_objective_id": objective_id
                }
            )
        elif requested_family in SPECIALIZED_EXTENDED_FAMILIES:
            extension_activation = "specialized_extended"
            stage_map["primary_model_stage"] = stage_entry(
                "degraded_with_deviation",
                "degraded",
                "Specialized extended methods require explicit implementation support and stronger review."
            )
            decision_index += 1
            decisions.append(
                {
                    "decision_id": make_id("DEC", decision_index),
                    "decision_type": "extension_degrade",
                    "source": "adjudication_rules",
                    "rule_trigger": "specialized_extended_requires_review",
                    "input_evidence": {"requested_method_family": requested_family},
                    "selected_option": "degraded_with_deviation",
                    "rejected_options": ["full_activation"],
                    "justification": "The requested family is specialized extended and cannot silently enter the main execution path.",
                    "linked_stage_id": "primary_model_stage",
                    "linked_objective_id": objective_id
                }
            )
            deviation_index += 1
            deviations.append(
                {
                    "deviation_id": make_id("DEV", deviation_index),
                    "linked_stage_id": "primary_model_stage",
                    "linked_objective_id": objective_id,
                    "reason": f"Requested specialized extended family `{requested_family}` is not part of the validated default execution path.",
                    "impact": "Method remains declared but requires explicit implementation and review before production execution.",
                    "status": "degraded_with_deviation"
                }
            )

        if not objective.get("modifier_candidates"):
            stage_map["interaction_stage"] = stage_entry("not_applicable", "simplified", "No modifier candidate was requested or inherited.")
        elif modifier_sparse or (min_events and min_events < rules["rules"]["interaction_min_cell_count"]):
            stage_map["interaction_stage"] = stage_entry("blocked_by_data", "degraded", "Interaction is blocked by sparse levels or low event support.")
            decision_index += 1
            decisions.append(
                {
                    "decision_id": make_id("DEC", decision_index),
                    "decision_type": "stage_block",
                    "source": "adjudication_rules",
                    "rule_trigger": "interaction_min_cell_count",
                    "input_evidence": {"modifier_candidates": objective.get("modifier_candidates", []), "min_events": min_events},
                    "selected_option": "block_interaction_stage",
                    "rejected_options": ["full_interaction_stage"],
                    "justification": "Interaction requested but sparse support would make the model unstable.",
                    "linked_stage_id": "interaction_stage",
                    "linked_objective_id": objective_id
                }
            )

        if objective.get("exposure_form") not in rules["rules"]["dose_response_requires_exposure_forms"]:
            stage_map["dose_response_stage"] = stage_entry("not_applicable", "simplified", "Exposure form is not continuous or ordinal.")
        if requested_family == "multinomial_nominal" and int(outcome_info.get("n_unique", 0) or 0) < int(rules["rules"]["multinomial_min_levels"]):
            stage_map["primary_model_stage"] = stage_entry("blocked_by_data", "degraded", "Nominal multinomial path requires at least three observed outcome levels.")
        if requested_family == "bounded_proportion" and not outcome_info.get("proportion_candidate"):
            stage_map["primary_model_stage"] = stage_entry("blocked_by_data", "degraded", "Bounded outcome path requires observed 0-1 bounded values.")
        if requested_family in {"count_outcome", "zero_inflated_count"} and not outcome_info.get("count_candidate"):
            stage_map["primary_model_stage"] = stage_entry("blocked_by_data", "degraded", "Count path requires non-negative integer-like outcomes.")
        if requested_family == "clustered_gee" and not any([psu_var, has_strata, objective.get("cluster_variable")]):
            stage_map["primary_model_stage"] = stage_entry("blocked_by_data", "degraded", "Clustered GEE path requires a cluster identifier or compatible grouping structure.")

        if max_missing <= rules["rules"]["missingness_pct_for_cca_only"]:
            stage_map["missingness_stage"] = stage_entry("required", "simplified", "Missingness is low enough for a simplified path.")
        elif "mice" in objective.get("missing_data_strategy", "").lower():
            stage_map["missingness_stage"] = stage_entry("required", "full", "Requested strategy explicitly names MICE.")
        elif max_missing >= rules["rules"]["missingness_pct_for_mi_recommendation"]:
            stage_map["missingness_stage"] = stage_entry("degraded_with_deviation", "degraded", "Missingness is material but MI was not clearly requested.")
            deviation_index += 1
            deviations.append(
                {
                    "deviation_id": make_id("DEV", deviation_index),
                    "linked_stage_id": "missingness_stage",
                    "linked_objective_id": objective_id,
                    "reason": "Material missingness without explicit MICE-ready setup",
                    "impact": "Missing-data handling must be simplified or justified before final release.",
                    "status": "degraded_with_deviation"
                }
            )
        if requested_family in {"binary_pr", "binary_or", "binary_sparse_robust"} and min_events and min_events < rules["rules"]["sparse_min_cell_count"]:
            stage_map["primary_model_stage"] = stage_entry("degraded_with_deviation", "degraded", "Sparse event support requires a robust or simplified binary path.")
            deviation_index += 1
            deviations.append(
                {
                    "deviation_id": make_id("DEV", deviation_index),
                    "linked_stage_id": "primary_model_stage",
                    "linked_objective_id": objective_id,
                    "reason": "Sparse event support detected for the binary outcome.",
                    "impact": "Primary model may require robust sparse-data handling or conservative interpretation.",
                    "status": "degraded_with_deviation"
                }
            )

        adjustment_vars = [str(value) for value in objective.get("adjustment_set", []) if str(value)]
        required_vars = [value for value in [exposure_var, outcome_var, *adjustment_vars] if value]
        missing_required_vars = sorted({value for value in required_vars if value not in schema_lookup})
        objective_availability = {
            "required_variables": required_vars,
            "missing_required_variables": missing_required_vars,
            "missingness_pct": {
                value: missingness.get(value, {}).get("pct_missing")
                for value in required_vars if value in schema_lookup
            },
        }
        if missing_required_vars:
            stage_map["primary_model_stage"] = stage_entry(
                "blocked_by_data", "degraded",
                f"Required variables are absent from the profiled data: {missing_required_vars}.",
            )
            stage_map["interaction_stage"] = stage_entry(
                "blocked_by_data", "degraded", "Primary model inputs are unavailable."
            )
            stage_map["dose_response_stage"] = stage_entry(
                "blocked_by_data", "degraded", "Primary model inputs are unavailable."
            )
            decision_index += 1
            decisions.append({
                "decision_id": make_id("DEC", decision_index),
                "decision_type": "objective_variable_availability",
                "source": "full_data_profile",
                "rule_trigger": "required_variable_absent",
                "input_evidence": objective_availability,
                "selected_option": "block_primary_model",
                "rejected_options": ["guess_mapping", "silent_variable_drop"],
                "justification": "A requested model cannot be executed when an exposure, outcome, or prespecified adjustment variable is absent.",
                "linked_stage_id": "primary_model_stage",
                "linked_objective_id": objective_id,
            })

        objective_execution_map.append(
            {
                "objective_id": objective_id,
                "requested_status": "required",
                "executable_status": "degraded_with_deviation" if any(
                    stage_map[stage]["status"] == "degraded_with_deviation" for stage in stage_map
                ) else "required",
                "executed_status": "pending_execution",
                "linked_stages": [stage for stage in STAGE_ORDER if stage_map[stage]["status"] != "not_applicable"],
                "final_reason": f"Execution state will be finalized after stage runtimes complete. Method family: {requested_family}.",
            }
        )
        executable_objectives.append(
            {
                **objective,
                "design_mode": design_mode,
                "design_verified_level": design_verified_level,
                "extension_activation": extension_activation,
                "objective_data_availability": objective_availability,
                "stage_map": stage_map,
            }
        )

    executable_stage_set = {}
    for stage in STAGE_ORDER:
        statuses = [obj["stage_map"][stage]["status"] for obj in executable_objectives]
        if "required" in statuses:
            executable_stage_set[stage] = "required"
        elif "degraded_with_deviation" in statuses:
            executable_stage_set[stage] = "degraded_with_deviation"
        elif "conditional" in statuses:
            executable_stage_set[stage] = "conditional"
        elif "blocked_by_data" in statuses:
            executable_stage_set[stage] = "blocked_by_data"
        else:
            executable_stage_set[stage] = "not_applicable"

    return {
        "plan_version": "2.2-final",
        "generated_at": now_iso(),
        "design_mode": design_mode,
        "design_verified_level": design_verified_level,
        "design_capabilities": design_capabilities,
        "executable_stage_set": executable_stage_set,
        "objectives": executable_objectives,
        "decisions": decisions,
        "deviations": deviations,
        "objective_execution_map": objective_execution_map,
    }


def main_adjudicate_feasibility() -> None:
    parser = argparse.ArgumentParser(description="Run feasibility adjudication for the v2.2 analysis framework.")
    parser.add_argument("project_root")
    parser.add_argument("--requested-plan", default="")
    parser.add_argument("--rules", default=str(Path(__file__).resolve().parents[1] / "contracts" / "adjudication_rules.yaml"))
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    requested_plan_path = Path(args.requested_plan) if args.requested_plan else project_root / "analysis" / "contracts" / "requested_analysis_plan.json"
    requested_plan = load_json(requested_plan_path)
    rules = load_structured(Path(args.rules))
    outdir = Path(args.output_dir) if args.output_dir else project_root / "analysis" / "contracts"
    payload = adjudicate(project_root, requested_plan, rules)

    write_json(outdir / "executable_analysis_plan.json", payload)
    write_json(outdir / "decision_registry.json", payload["decisions"])
    write_json(outdir / "deviation_register.json", payload["deviations"])
    write_json(outdir / "objective_execution_map.json", payload["objective_execution_map"])

# build_analysis_plan


def build_requested_plan(project_root: Path) -> dict:
    discovered = discover_inputs(project_root)
    intake = load_json(discovered["intake_json"]) if discovered["intake_json"] else {}
    protocol_contract = load_json(discovered["protocol_contract"]) if discovered["protocol_contract"] else {}
    sap_contract = load_json(discovered["sap_contract"]) if discovered["sap_contract"] else {}
    design_intake = load_json(discovered["design_intake_v2"]) if discovered["design_intake_v2"] else {}
    explicit_data = None
    if intake.get("data_csv"):
        explicit_data = (Path(discovered["intake_json"]).parent / intake["data_csv"]).resolve()
    profile, profile_path = ensure_data_profile(project_root, explicit_data or discovered["data_csv"])
    design_columns = detect_design_columns(profile)
    objectives = load_objectives(project_root, protocol_contract, design_intake, sap_contract)
    if not objectives and intake:
        requested_family = intake.get("requested_method_family", "")
        outcome_family = intake.get("primary_outcome_family", "")
        default_analysis_family = {
            "bounded_proportion": "beta regression or fractional-response model",
            "count_outcome": "count regression",
            "zero_inflated_count": "zero-inflated count regression",
            "multinomial_nominal": "multinomial regression",
            "clustered_gee": "generalized estimating equations",
        }.get(
            requested_family,
            {
                "continuous": "weighted linear model",
                "ordinal": "ordinal regression",
                "count": "count regression",
                "bounded": "beta regression or fractional-response model",
            }.get(outcome_family, "modified Poisson regression"),
        )
        objectives = [
            {
                "objective_id": "OBJ1",
                "priority": "primary",
                "objective_type": "association",
                "purpose": intake.get("study_title", project_root.name),
                "exposure": intake.get("primary_exposure", ""),
                "outcome": intake.get("primary_outcome", ""),
                "primary_outcome_family": intake.get("primary_outcome_family", ""),
                "effect_measure": intake.get("primary_effect_measure", "beta" if intake.get("primary_outcome", "").endswith("_score") else "prevalence ratio"),
                "analysis_family": intake.get("analysis_family", default_analysis_family),
                "requested_method_family": intake.get("requested_method_family", ""),
                "interaction_candidates": intake.get("modifier_candidates", []),
                "missing_data_strategy": "Diagnose and adjudicate from observed missingness.",
                "cluster_variable": intake.get("cluster_variable", ""),
            }
        ]
    variable_roles = (
        design_intake.get("measurement_plan", {}).get("variable_roles", [])
        or protocol_contract.get("variable_roles", [])
    )
    if not variable_roles and intake:
        variable_roles = [
            {"variable": intake.get("primary_exposure", ""), "role": "Primary exposure", "planned_analysis_role": "Main exposure"},
            {"variable": intake.get("primary_outcome", ""), "role": "Primary outcome", "planned_analysis_role": "Primary outcome"},
        ]
    role_lookup = {row["variable"]: row for row in variable_roles if row.get("variable")}
    requested_objectives = []
    unresolved_inputs: list[str] = []

    for idx, objective in enumerate(objectives, start=1):
        objective_id = objective.get("objective_id", make_id("OBJ", idx))
        exposure_var = objective.get("exposure_var", "") or next(
            iter([row["variable"] for row in variable_roles if "exposure" in row.get("role", "").lower()]),
            "",
        )
        outcome_var = next(
            iter([row["variable"] for row in variable_roles if "outcome" in row.get("role", "").lower()]),
            "",
        )
        exposure_info = role_lookup.get(exposure_var, {})
        outcome_info = role_lookup.get(outcome_var, {})
        outcome_family = infer_outcome_family(
            {
                **next((item for item in profile.get("schema", []) if item["name"] == outcome_var), {}),
                **outcome_info,
            },
            objective,
        )
        exposure_form = infer_exposure_form(
            {
                **next((item for item in profile.get("schema", []) if item["name"] == exposure_var), {}),
                **exposure_info,
            },
            objective,
        )
        requested_methods = []
        effect_measure = objective.get("effect_measure", objective.get("estimation_metric", ""))
        requested_family = objective.get("requested_method_family", "") or resolve_method_family(
            outcome_family,
            effect_measure,
            objective.get("analysis_family", ""),
        )
        requested_methods.append(primary_method_id(requested_family))

        modifiers = objective.get("interaction_candidates") or [
            row["variable"]
            for row in variable_roles
            if "interaction" in row.get("planned_analysis_role", "").lower()
            or "modifier" in row.get("role", "").lower()
        ]
        requested_objectives.append(
            {
                "objective_id": objective_id,
                "purpose": objective.get("purpose", objective.get("objective_statement", "")),
                "priority": objective.get("priority", "primary"),
                "outcome_family": outcome_family,
                "effect_measure": effect_measure,
                "analysis_family": objective.get("analysis_family", ""),
                "requested_method_family": requested_family,
                "method_tier": method_tier(requested_family),
                "exposure_var": exposure_var,
                "outcome_var": outcome_var,
                "exposure_form": exposure_form,
                "modifier_candidates": modifiers,
                "requested_methods": requested_methods,
                "requested_renderers": objective.get("requested_renderers", default_figure_families(requested_family)),
                "result_schema_name": result_schema_name(requested_family, effect_measure),
                "requested_postestimation": objective.get("requested_postestimation", intake.get("requested_postestimation", False)),
                "requested_performance_outputs": objective.get("requested_performance_outputs", intake.get("requested_performance_outputs", False)),
                "requested_diagnostics": objective.get("diagnostics", sap_contract.get("diagnostic_plan", [])),
                "requested_sensitivity": objective.get("sensitivity_analyses", []),
                "missing_data_strategy": objective.get("missing_data_strategy", sap_contract.get("missing_data_strategy", "")),
                "adjustment_set": objective.get("adjustment_strategy", {}).get("adjustment_set", []),
                "table_figure_targets": objective.get("table_figure_targets", []),
            }
        )
        if not exposure_var:
            unresolved_inputs.append(f"{objective_id}: no exposure variable resolved from variable_roles")
        if not outcome_var:
            unresolved_inputs.append(f"{objective_id}: no outcome variable resolved from variable_roles")

    requested_stage_set = {
        "qc_stage": "required",
        "missingness_stage": "required",
        "descriptive_stage": "required",
        "bivariate_stage": "conditional",
        "primary_model_stage": "required",
        "interaction_stage": "conditional",
        "dose_response_stage": "conditional",
        "sensitivity_stage": "conditional",
        "registry_finalize_stage": "required",
        "report_stage": "required",
    }

    return {
        "plan_version": "2.2-final",
        "generated_at": now_iso(),
        "project_root": str(project_root.resolve()),
        "source_priority": [
            "architect contracts and SAP",
            "explicit user overrides if present",
            "data profile and design detection",
            "free text protocol as fallback"
        ],
        "resolved_inputs": {
            "intake_json": str(discovered["intake_json"]) if discovered["intake_json"] else "",
            "protocol_contract": str(discovered["protocol_contract"]) if discovered["protocol_contract"] else "",
            "sap_contract": str(discovered["sap_contract"]) if discovered["sap_contract"] else "",
            "design_intake_v2": str(discovered["design_intake_v2"]) if discovered["design_intake_v2"] else "",
            "data_csv": str((explicit_data or discovered["data_csv"])) if (explicit_data or discovered["data_csv"]) else "",
            "data_profile": str(profile_path) if profile_path else "",
        },
        "study_identity": {
            "decision_id": protocol_contract.get("decision_id", design_intake.get("decision_id", intake.get("decision_id", "DECISION_PENDING"))),
            "study_title": protocol_contract.get("study_title", design_intake.get("study_title", intake.get("study_title", project_root.name))),
            "project_mode": normalize_project_mode(
                protocol_contract.get("project_mode", design_intake.get("project_mode", "research"))
            ),
        },
        "design_context_requested": {
            "sampling_design": design_intake.get("study_design", {}).get("sampling_design", protocol_contract.get("sampling_design", "")),
            "survey_strategy": sap_contract.get("survey_strategy", ""),
            "weight_variable": design_columns["weight_variable"],
            "strata_variable": design_columns["strata_variable"],
            "psu_variable": design_columns["psu_variable"],
        },
        "requested_objectives": requested_objectives,
        "requested_stage_set": requested_stage_set,
        "reporting_commitments": design_intake.get("reporting_commitments", []),
        "unresolved_inputs": unresolved_inputs,
    }


def main_build_analysis_plan() -> None:
    parser = argparse.ArgumentParser(description="Build requested analysis plan from project inputs.")
    parser.add_argument("project_root")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    payload = build_requested_plan(project_root)
    output = Path(args.output) if args.output else project_root / "analysis" / "contracts" / "requested_analysis_plan.json"
    write_json(output, payload)

# build_contracts
METHOD_BY_STAGE = {
    "qc_stage": ["qc_profile"],
    "missingness_stage": ["missingness_overview"],
    "descriptive_stage": ["weighted_table1_nonnormal_smd"],
    "bivariate_stage": ["weighted_bivariate_bundle"],
    "primary_model_stage": [],
    "interaction_stage": ["weighted_interaction_continuous"],
    "dose_response_stage": ["weighted_rcs_dose_response"],
    "sensitivity_stage": ["sensitivity_bundle"],
    "registry_finalize_stage": [],
    "report_stage": [],
}


def build_contract(project_root: Path, requested_plan: dict, executable_plan: dict) -> dict:
    discovered = discover_inputs(project_root)
    protocol_contract = load_json(discovered["protocol_contract"]) if discovered["protocol_contract"] else {}
    sap_contract = load_json(discovered["sap_contract"]) if discovered["sap_contract"] else {}
    design_intake = load_json(discovered["design_intake_v2"]) if discovered["design_intake_v2"] else {}
    profile, profile_path = ensure_data_profile(project_root, discovered["data_csv"])

    objectives = executable_plan.get("objectives", [])
    primary_objective = next(
        (row for row in objectives if str(row.get("priority", "")).lower() == "primary"),
        objectives[0] if objectives else {},
    )
    design_objectives = {
        str(row.get("objective_id")): row for row in design_intake.get("study_objectives", [])
    }
    objective_analysis_map = []
    for objective in objectives:
        objective_id = str(objective.get("objective_id", ""))
        design_objective = design_objectives.get(objective_id, {})
        objective_analysis_map.append({
            "objective_id": objective_id,
            "priority": objective.get("priority", "secondary"),
            "exposure_variable": objective.get("exposure_var", ""),
            "exposure_form": objective.get("exposure_form", ""),
            "outcome_variable": objective.get("outcome_var", ""),
            "effect_measure": objective.get("effect_measure", ""),
            "requested_method_family": objective.get("requested_method_family", ""),
            "missing_data_strategy": objective.get("missing_data_strategy", ""),
            "pooling_required": "mice" in str(objective.get("missing_data_strategy", "")).lower(),
            "adjustment_set": objective.get("adjustment_set", []),
            "excluded_variables": design_objective.get("adjustment_strategy", {}).get("excluded_variables", []),
            "objective_data_availability": objective.get("objective_data_availability", {}),
        })
    return {
        "contract_version": "2.2-final",
        "schema_version": "2.2-final",
        "generated_at": now_iso(),
        "study_identity": {
            "decision_id": requested_plan.get("study_identity", {}).get("decision_id", "DECISION_PENDING"),
            "study_title": requested_plan.get("study_identity", {}).get("study_title", project_root.name),
            "project_mode": requested_plan.get("study_identity", {}).get("project_mode", "research"),
        },
        "sample_definition": {
            "target_sample": design_intake.get("population_trinity", {}).get(
                "target_population",
                protocol_contract.get("target_population", protocol_contract.get("population", "")),
            ),
            "analytic_sample_rules": design_intake.get("population_trinity", {}).get(
                "analytic_population",
                "Defined by stage-specific QC and missing-data rules.",
            ),
            "eligibility_filters": design_intake.get("population_trinity", {}).get("inclusion_criteria", []),
            "complete_case_rules": "Complete-case definitions are stage-specific and must be logged when used.",
        },
        "design_context": {
            "sampling_design_type": requested_plan.get("design_context_requested", {}).get("sampling_design", ""),
            "survey_strategy": requested_plan.get("design_context_requested", {}).get("survey_strategy", ""),
            "weight_variable": requested_plan.get("design_context_requested", {}).get("weight_variable", ""),
            "strata_variable": requested_plan.get("design_context_requested", {}).get("strata_variable", ""),
            "psu_variable": requested_plan.get("design_context_requested", {}).get("psu_variable", ""),
            "design_mode": executable_plan.get("design_mode", "sample"),
            "design_verified_level": executable_plan.get("design_verified_level", "sample_based"),
            "design_capabilities": executable_plan.get("design_capabilities", {}),
            "data_profile_path": str(profile_path) if profile_path else "",
        },
        "primary_exposure": {
            "objective_id": primary_objective.get("objective_id", ""),
            "variable": primary_objective.get("exposure_var", ""),
            "form": primary_objective.get("exposure_form", ""),
            "effect_measure": primary_objective.get("effect_measure", ""),
            "requested_methods": primary_objective.get("requested_methods", []),
            "requested_method_family": primary_objective.get("requested_method_family", ""),
            "method_tier": primary_objective.get("method_tier", "default_mainline"),
        },
        "objective_analysis_map": objective_analysis_map,
        "outcomes": [
            {
                "objective_id": objective["objective_id"],
                "variable": objective.get("outcome_var", ""),
                "outcome_family": objective.get("outcome_family", ""),
                "effect_measure": objective.get("effect_measure", ""),
                "analysis_family": objective.get("analysis_family", ""),
                "requested_method_family": objective.get("requested_method_family", ""),
                "method_tier": objective.get("method_tier", "default_mainline"),
                "result_schema_name": objective.get("result_schema_name", ""),
                "design_mode": objective.get("design_mode", executable_plan.get("design_mode", "sample")),
            }
            for objective in executable_plan.get("objectives", [])
        ],
        "estimand_family": sap_contract.get("primary_estimand", primary_objective.get("effect_measure", "")),
        "estimand_by_objective": {
            row["objective_id"]: row["effect_measure"] for row in objective_analysis_map
        },
        "missing_data_policy": {
            "requested_strategy": primary_objective.get(
                "missing_data_strategy",
                sap_contract.get("missing_data_strategy", ""),
            ),
            "observed_missingness": profile.get("missingness_by_column", {}),
            "pooling_required": "mice" in str(primary_objective.get("missing_data_strategy", "")).lower(),
            "by_objective": {
                row["objective_id"]: {
                    "requested_strategy": row["missing_data_strategy"],
                    "pooling_required": row["pooling_required"],
                }
                for row in objective_analysis_map
            },
        },
        "adjustment_policy": {
            "primary_objective_id": primary_objective.get("objective_id", ""),
            "primary_adjustment_set": primary_objective.get("adjustment_set", []),
            "excluded_variables": design_objectives.get(
                str(primary_objective.get("objective_id", "")), {}
            ).get("adjustment_strategy", {}).get("excluded_variables", []),
            "by_objective": {
                row["objective_id"]: {
                    "adjustment_set": row["adjustment_set"],
                    "excluded_variables": row["excluded_variables"],
                }
                for row in objective_analysis_map
            },
        },
        "reporting_commitments": requested_plan.get("reporting_commitments", []),
        "requested_stage_set": requested_plan.get("requested_stage_set", {}),
        "executable_stage_set": executable_plan.get("executable_stage_set", {}),
    }


def primary_method(objective: dict) -> str:
    methods = objective.get("requested_methods", [])
    return methods[0] if methods else primary_method_id(objective.get("requested_method_family", "binary_pr"))


def stage_figures(stage: str, objective: dict) -> list[str]:
    requested = objective.get("requested_renderers", [])
    allowlist = {
        "descriptive_stage": {"plot_distribution", "plot_balance", "plot_missingness"},
        "primary_model_stage": {"plot_forest", "plot_marginal_effects", "plot_calibration", "plot_distribution"},
        "interaction_stage": {"plot_marginal_effects", "plot_forest"},
        "dose_response_stage": {"plot_spline", "plot_marginal_effects", "plot_distribution"},
        "sensitivity_stage": {"plot_forest", "plot_marginal_effects", "plot_distribution"},
    }
    return [item for item in requested if item in allowlist.get(stage, set())]


def stage_outputs(stage: str) -> list[str]:
    return {
        "qc_stage": ["analysis/profile/data_profile.json"],
        "missingness_stage": ["analysis/output/tables/Table_MissingnessProfile.csv"],
        "descriptive_stage": ["analysis/output/tables/Table1_BaselineByExposure.csv"],
        "bivariate_stage": ["analysis/output/tables/Table_BivariateBundle.csv"],
        "primary_model_stage": ["analysis/output/tables/Table_PrimaryModel.csv"],
        "interaction_stage": ["analysis/output/tables/Table_InteractionModel.csv"],
        "dose_response_stage": ["analysis/output/tables/Table_DoseResponse.csv"],
        "sensitivity_stage": ["analysis/output/tables/Table_SensitivitySummary.csv"],
        "registry_finalize_stage": ["analysis/frozen/freeze_manifest.json"],
        "report_stage": ["analysis/output/report/statistical_analysis_report.md"],
    }[stage]


def objective_stage_outputs(stage: str, objective_id: str, multi_objective: bool) -> list[str]:
    base = stage_outputs(stage)
    if not multi_objective or stage in {"qc_stage", "registry_finalize_stage", "report_stage"}:
        return base
    return [str(Path(path).with_name(f"{objective_id}_{Path(path).name}")) for path in base]


def build_stage_contracts(project_root: Path, executable_plan: dict) -> None:
    stage_dir = project_root / "analysis" / "stage_contracts"
    objectives = executable_plan.get("objectives", [])
    for stage in STAGE_ORDER:
        stage_status = executable_plan.get("executable_stage_set", {}).get(stage, "not_applicable")
        linked_objectives = [
            obj["objective_id"]
            for obj in objectives
            if obj.get("stage_map", {}).get(stage, {}).get("status") != "not_applicable"
        ]
        linked_rows = [obj for obj in objectives if obj.get("objective_id") in linked_objectives]
        objective_specs = []
        all_required_methods: list[str] = []
        all_required_outputs: list[str] = []
        all_required_figures: list[str] = []
        for objective in linked_rows:
            methods = METHOD_BY_STAGE[stage][:]
            if stage == "primary_model_stage":
                methods = [primary_method(objective)]
                if objective.get("requested_postestimation"):
                    methods.append("adjusted_predictions_contrasts")
                if objective.get("requested_performance_outputs"):
                    methods.append("calibration_performance_bundle")
            outputs = objective_stage_outputs(stage, objective["objective_id"], len(objectives) > 1)
            figures = stage_figures(stage, objective)
            all_required_methods.extend(methods)
            all_required_outputs.extend(outputs)
            all_required_figures.extend(figures)
            stage_meta = objective.get("stage_map", {}).get(stage, {})
            objective_specs.append({
                "objective_id": objective["objective_id"],
                "stage_status": stage_meta.get("status", "not_applicable"),
                "path_mode": stage_meta.get("path_mode", "simplified"),
                "required_methods": methods,
                "required_outputs": outputs,
                "required_figures": figures,
                "blocking_condition": stage_meta.get("reason", ""),
            })
        required_methods = list(dict.fromkeys(all_required_methods or METHOD_BY_STAGE[stage]))
        required_outputs = list(dict.fromkeys(all_required_outputs or stage_outputs(stage)))
        required_figures = list(dict.fromkeys(all_required_figures))
        path_modes = {row["path_mode"] for row in objective_specs}
        stage_path_mode = "degraded" if "degraded" in path_modes else (
            "full" if "full" in path_modes else "simplified"
        )
        decision_links = [
            item["decision_id"]
            for item in executable_plan.get("decisions", [])
            if item.get("linked_stage_id") == stage
        ]
        write_json(stage_dir / f"{stage}.json", {
            "generated_at": now_iso(),
            "stage_id": stage,
            "stage_status": stage_status,
            "path_mode": stage_path_mode,
            "inputs": [
                "analysis/contracts/analysis_core_contract.json",
                "analysis/contracts/executable_analysis_plan.json",
                "analysis/profile/data_profile.json",
            ],
            "required_methods": required_methods,
            "allowed_fallbacks": ["simplified_path"]
            if stage_status in {"conditional", "degraded_with_deviation"}
            else [],
            "forbidden_substitutions": ["logistic_regression_or"]
            if "weighted_modified_poisson_pr" in required_methods
            else [],
            "required_outputs": required_outputs,
            "required_figures": required_figures,
            "blocking_conditions": [row["blocking_condition"] for row in objective_specs]
            or ["No linked objective for this stage."],
            "objective_links": linked_objectives,
            "objective_specs": objective_specs,
            "decision_links": decision_links,
        })


def main_build_contracts() -> None:
    parser = argparse.ArgumentParser(description="Build analysis and stage contracts.")
    parser.add_argument("project_root")
    parser.add_argument("--requested-plan", default="")
    parser.add_argument("--executable-plan", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    requested_plan = load_json(
        Path(args.requested_plan)
        if args.requested_plan
        else project_root / "analysis" / "contracts" / "requested_analysis_plan.json"
    )
    executable_plan_path = (
        Path(args.executable_plan)
        if args.executable_plan
        else project_root / "analysis" / "contracts" / "executable_analysis_plan.json"
    )
    executable_plan = load_json(executable_plan_path)
    payload = build_contract(project_root, requested_plan, executable_plan)
    output = (
        Path(args.output)
        if args.output
        else project_root / "analysis" / "contracts" / "analysis_core_contract.json"
    )
    write_json(output, payload)
    write_json(
        project_root / "analysis" / "contracts" / "execution_state.json",
        {
            "generated_at": now_iso(),
            "analysis_release_mode": "scientific_release"
            if payload["study_identity"]["project_mode"] == "research"
            else "demonstration_only",
            "report_delivery_class": "scientific_final"
            if payload["study_identity"]["project_mode"] == "research"
            else "demonstration_only",
            "execution_level": "scaffold_only",
            "execution_plan_sha256": hashlib.sha256(executable_plan_path.read_bytes()).hexdigest(),
            "objective_stage_completion": {
                row["objective_id"]: {} for row in executable_plan.get("objectives", [])
            },
            "realized_methods": [],
            "skipped_stages": [],
            "degraded_stages": [],
            "runtime_warnings": [],
            "failures": [],
            "unresolved_fields": requested_plan.get("unresolved_inputs", []),
        },
    )
    build_stage_contracts(project_root, executable_plan)


COMMANDS = {
    "adjudicate_feasibility": main_adjudicate_feasibility,
    "build_analysis_plan": main_build_analysis_plan,
    "build_contracts": main_build_contracts,
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
