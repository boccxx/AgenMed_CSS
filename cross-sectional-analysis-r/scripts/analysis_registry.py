#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/analysis_registry.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from analysis_common import load_json, make_id, now_iso, result_schema_name, write_json

# build_registries


def infer_stage_from_name(name: str) -> str:
    lowered = name.lower()
    if "missing" in lowered:
        return "missingness_stage"
    if "table1" in lowered or "baseline" in lowered:
        return "descriptive_stage"
    if "interaction" in lowered:
        return "interaction_stage"
    if "dose" in lowered or "trend" in lowered or "spline" in lowered:
        return "dose_response_stage"
    if "sens" in lowered or "weighted" in lowered:
        return "sensitivity_stage"
    if "primary" in lowered or "forest" in lowered or "model" in lowered:
        return "primary_model_stage"
    return "report_stage"


def normalize_numeric(value):
    if value in {"", None}:
        return None
    return value


def prettify_stem(stem: str) -> str:
    cleaned = stem.replace("Table_", "").replace("Figure_", "").replace("Table1_", "")
    return cleaned.replace("_", " ").strip()


def infer_registry_role(stage_id: str, stem: str) -> str:
    lowered = stem.lower()
    if stage_id in {"missingness_stage", "descriptive_stage", "primary_model_stage"}:
        return "main_text"
    if any(token in lowered for token in ("primary", "baseline", "missing", "interaction", "dose", "sensitivity")):
        return "main_text"
    return "supplement"


def artifact_family(stem: str) -> str:
    lowered = stem.lower()
    if "vif" in lowered or "diagnostic" in lowered:
        return "diagnostic"
    if "evalue" in lowered:
        return "sensitivity"
    if "forest" in lowered:
        return "forest"
    if "prediction" in lowered or "marginal" in lowered or "contrast" in lowered or "slope" in lowered:
        return "marginal"
    if "calibration" in lowered:
        return "calibration"
    if "balance" in lowered or "smd" in lowered or "love" in lowered:
        return "balance"
    if "distribution" in lowered or "density" in lowered or "hist" in lowered:
        return "distribution"
    if "missing" in lowered:
        return "missingness"
    if "interaction" in lowered:
        return "interaction"
    if "dose" in lowered or "spline" in lowered or "trend" in lowered:
        return "dose_response"
    if "performance" in lowered:
        return "performance"
    return "generic"


def table_caption_and_note(stage_id: str, stem: str, design_mode: str = "sample") -> tuple[str, str, str]:
    display_title = prettify_stem(stem)
    family = artifact_family(stem)
    family_mapping = {
        ("missingness_stage", "missingness"): (
            "Missingness profile across variables included in the adjudicated analysis bundle",
            "Counts and percentages are reported on the observed dataset before any imputation or complete-case restriction.",
            "Missingness profile",
        ),
        ("descriptive_stage", "balance"): (
            "Covariate balance summary for the descriptive-stage comparison set",
            "Standardized mean differences quantify imbalance and should be interpreted alongside the baseline characteristics table.",
            "Covariate balance summary",
        ),
        ("descriptive_stage", "generic"): (
            ("Design-weighted baseline characteristics and descriptive estimates for the analytic sample"
             if design_mode in {"survey_full", "survey_weight_only"}
             else "Observed baseline characteristics and descriptive estimates for the analytic sample"),
            "Continuous variables should be interpreted using the reported summary family for that stage; standardized mean differences quantify imbalance.",
            "Baseline characteristics",
        ),
        ("bivariate_stage", "generic"): (
            "Design-aware bivariate associations carried forward from the descriptive stage",
            "The table summarizes stage-level exploratory associations and should not be read as a substitute for the primary multivariable model.",
            "Bivariate associations",
        ),
        ("primary_model_stage", "generic"): (
            "Primary model estimates on the frozen estimand scale",
            "Effect estimates, confidence intervals, and p-values are reported on the scale declared in the core contract and preserved through freeze.",
            "Primary model estimates",
        ),
        ("primary_model_stage", "marginal"): (
            "Adjusted predictions and marginal contrasts derived from the primary model",
            "These quantities are post-estimation summaries and should be interpreted alongside the primary coefficient table rather than in isolation.",
            "Adjusted predictions and contrasts",
        ),
        ("interaction_stage", "interaction"): (
            "Effect-modification estimates and subgroup contrasts",
            "Interaction terms are reported only for adjudicated modifiers and should be interpreted alongside multiplicity and sparsity constraints.",
            "Interaction analysis",
        ),
        ("dose_response_stage", "dose_response"): (
            "Dose-response and non-linearity assessment",
            "Trend and non-linearity results should be interpreted jointly; where spline models were used, the table reflects the frozen dose-response parameterization.",
            "Dose-response assessment",
        ),
        ("sensitivity_stage", "generic"): (
            "Sensitivity analyses relative to the primary model",
            "Sensitivity results are reported to stress-test the frozen primary model and do not replace the main interpretation without explicit justification.",
            "Sensitivity analysis",
        ),
        ("report_stage", "diagnostic"): (
            "Model diagnostics summary supporting the frozen primary interpretation",
            "These diagnostics are supportive checks on model stability and should be interpreted together with the formal diagnostics narrative in the report.",
            "Model diagnostics summary",
        ),
        ("report_stage", "sensitivity"): (
            "Supportive sensitivity metric summary retained for final interpretation",
            "These quantities are supportive rather than primary inferential targets and should be read within the interpretation-boundary section.",
            "Supportive sensitivity summary",
        ),
        ("report_stage", "performance"): (
            "Model performance and calibration summary",
            "Performance quantities are supportive outputs and should be interpreted only when prediction-oriented reporting was adjudicated into scope.",
            "Performance summary",
        ),
    }
    caption, note, display_title = family_mapping.get(
        (stage_id, family),
        family_mapping.get((stage_id, "generic"), (display_title, "Interpret together with the stage narrative and frozen audit state.", display_title)),
    )
    if design_mode == "survey_weight_only":
        caption = caption.replace("Design-weighted", "Supplied-weight point").replace(
            "design-weighted", "supplied-weight point"
        )
        note = note.replace("confidence intervals", "individual-independence working intervals").replace(
            "p-values", "working p-values"
        )
        boundary = "Supplied-weight point description; formal survey variance unavailable."
        caption = f"{caption.rstrip()} — {boundary}"
        note = f"{note.rstrip()} {boundary}"
    return caption, note, display_title


def figure_caption_and_legend(stage_id: str, stem: str, design_mode: str = "sample") -> tuple[str, str, str]:
    display_title = prettify_stem(stem)
    family = artifact_family(stem)
    family_mapping = {
        ("missingness_stage", "missingness"): (
            "Missing-data pattern visualization for variables entering the adjudicated analysis bundle",
            "Shaded or highlighted cells denote missing observations; figure interpretation should be aligned with the stage-specific missing-data strategy.",
            "Missingness visualization",
        ),
        ("descriptive_stage", "balance"): (
            "Balance plot for descriptive-stage covariate comparison",
            "Points summarize standardized mean differences, and reference thresholds indicate the predeclared imbalance benchmark.",
            "Covariate balance plot",
        ),
        ("descriptive_stage", "distribution"): (
            "Distributional visualization for descriptive-stage variables",
            ("Plot geometry reflects the observed distribution and should be read with the design-weighted baseline table."
             if design_mode in {"survey_full", "survey_weight_only"}
             else "Plot geometry reflects the observed distribution and should be read with the unweighted sample summary."),
            "Distribution plot",
        ),
        ("bivariate_stage", "distribution"): (
            "Exploratory visualization of bivariate associations carried into design-aware modelling",
            "These plots summarize exploratory relationships only and do not supersede the primary multivariable estimates.",
            "Bivariate visualization",
        ),
        ("primary_model_stage", "forest"): (
            "Forest plot of primary model estimates on the frozen estimand scale",
            "Points denote effect estimates and horizontal intervals denote 95% confidence intervals on the reported scale.",
            "Primary model forest plot",
        ),
        ("primary_model_stage", "marginal"): (
            "Adjusted prediction plot derived from the primary model",
            "Displayed values are post-estimation quantities derived from the frozen primary model and should be interpreted on their reported prediction scale.",
            "Adjusted prediction plot",
        ),
        ("interaction_stage", "interaction"): (
            "Interaction or subgroup visualization for adjudicated effect modifiers",
            "Displayed contrasts should be interpreted in light of sparsity checks, multiplicity handling, and the frozen interaction contract.",
            "Interaction figure",
        ),
        ("dose_response_stage", "dose_response"): (
            "Dose-response visualization for the primary exposure-outcome relationship",
            "Curves represent the frozen model form; shaded bands or intervals correspond to uncertainty around the fitted relationship.",
            "Dose-response figure",
        ),
        ("sensitivity_stage", "forest"): (
            "Sensitivity-analysis forest plot relative to the primary model",
            "Alternative specifications are shown to evaluate robustness and are not a substitute for the primary adjudicated path.",
            "Sensitivity forest plot",
        ),
        ("report_stage", "diagnostic"): (
            "Diagnostic visualization supporting the final interpretation boundary",
            "This figure summarizes supportive diagnostic evidence and should be read alongside the diagnostic section rather than as a stand-alone inferential display.",
            "Diagnostic figure",
        ),
        ("report_stage", "distribution"): (
            "Supplementary distributional visualization retained for final report context",
            "This figure contextualizes the observed analytic sample and should be interpreted with the descriptive-stage results rather than as an independent inferential result.",
            "Supplementary distribution plot",
        ),
        ("report_stage", "calibration"): (
            "Calibration plot for prediction-oriented performance assessment",
            "Observed and predicted values are displayed for supportive performance assessment only, not for primary etiologic interpretation.",
            "Calibration plot",
        ),
    }
    caption, legend, display_title = family_mapping.get(
        (stage_id, family),
        family_mapping.get((stage_id, "generic"), (display_title, "Interpret with the corresponding frozen results and stage narrative.", display_title)),
    )
    if design_mode == "survey_weight_only":
        caption = caption.replace("Design-weighted", "Supplied-weight point").replace(
            "design-weighted", "supplied-weight point"
        )
        legend = legend.replace("Design-weighted", "Supplied-weight point").replace(
            "design-weighted", "supplied-weight point"
        )
        legend = legend.replace("95% confidence intervals", "individual-independence working intervals").replace(
            "confidence intervals", "working intervals"
        )
        boundary = "Supplied-weight point description; formal survey variance unavailable."
        caption = f"{caption.rstrip()} — {boundary}"
        legend = f"{legend.rstrip()} {boundary}"
    return caption, legend, display_title


def build_result_row(summary_key: str, value: dict, objective: dict, core_contract: dict, idx: int) -> dict:
    effect_measure = value.get("effect_measure") or objective.get("effect_measure", "")
    method_family = value.get("model_family") or objective.get(
        "requested_method_family",
        core_contract.get("primary_exposure", {}).get("requested_method_family", "binary_pr"),
    )
    schema_name = value.get("result_type") or result_schema_name(method_family, effect_measure)
    inference_basis = value.get("inference_basis") or {
        "standard_error": normalize_numeric(value.get("std.error", value.get("standard_error"))),
        "confidence_level": normalize_numeric(value.get("confidence_level")),
        "reference_distribution": value.get("reference_distribution"),
        "p_reference_distribution": value.get("p_reference_distribution", value.get("reference_distribution")),
        "degrees_of_freedom": normalize_numeric(value.get("degrees_of_freedom")),
        "critical_value": normalize_numeric(value.get("critical_value")),
        "sidedness": value.get("sidedness"),
        "exponentiated": bool(value.get("exponentiated", False)),
    }
    return {
        "result_id": make_id("RES", idx),
        "label": value.get("label", summary_key),
        "result_type": schema_name,
        "objective_id": objective.get("objective_id", "OBJ001"),
        "stage_id": value.get("stage_id", "primary_model_stage"),
        "outcome_id": objective.get("variable", objective.get("outcome_id", "")),
        "exposure_term": value.get("exposure_term", core_contract.get("primary_exposure", {}).get("variable", "")),
        "effect_measure": effect_measure,
        "estimate": normalize_numeric(value.get("estimate")),
        "ci_lower": normalize_numeric(value.get("conf.low", value.get("ci_low"))),
        "ci_upper": normalize_numeric(value.get("conf.high", value.get("ci_high"))),
        "p_value": normalize_numeric(value.get("p.value", value.get("p_value"))),
        "inference_basis": inference_basis,
        "exposure_unit": value.get("exposure_unit", ""),
        "exposure_contrast": value.get("exposure_contrast", ""),
        "adjustment_set": (
            [item for item in str(value.get("adjustment_set", "")).split(";") if item]
            if not isinstance(value.get("adjustment_set"), list)
            else value.get("adjustment_set")
        ),
        "sensitivity_axis": value.get("sensitivity_axis", ""),
        "model_family": method_family,
        "design_mode": value.get("design_mode", core_contract.get("design_context", {}).get("design_mode", "sample")),
        "pooling_mode": value.get("pooling_mode", "mice_pooling" if value.get("mice_executed") else "none"),
        "registry_role": value.get("registry_role", "main_text"),
        "source_model": value.get("source_model", method_family),
        "source_table_id": value.get("source_table_id", ""),
    }


def canonical_result_rows(summary: dict, core_contract: dict) -> list[dict]:
    outcomes = core_contract.get("outcomes", [])
    outcome_by_objective = {row.get("objective_id", f"OBJ{idx:03d}"): row for idx, row in enumerate(outcomes, start=1)}
    results: list[dict] = []
    result_index = 1

    explicit_results = summary.get("results", [])
    for row in explicit_results:
        objective = outcome_by_objective.get(row.get("objective_id"), outcomes[0] if outcomes else {})
        results.append(build_result_row(row.get("label", f"result_{result_index}"), row, objective, core_contract, result_index))
        result_index += 1

    if results:
        return results

    mappings = [
        ("primary_prevalence", {"effect_measure": "prevalence", "model_family": "descriptive", "stage_id": "descriptive_stage"}),
        ("primary_pr", {"effect_measure": "prevalence ratio", "model_family": "modified_poisson", "stage_id": "primary_model_stage"}),
        ("survey_weighted_pr", {"effect_measure": "prevalence ratio", "model_family": "modified_poisson", "stage_id": "primary_model_stage"}),
        ("primary_or", {"effect_measure": "odds ratio", "model_family": "logistic", "stage_id": "primary_model_stage"}),
        ("primary_beta", {"effect_measure": "beta", "model_family": "linear", "stage_id": "primary_model_stage"}),
        ("primary_ordinal_or", {"effect_measure": "common odds ratio", "model_family": "ordinal", "stage_id": "primary_model_stage"}),
        ("primary_count_ratio", {"effect_measure": "rate ratio", "model_family": "count", "stage_id": "primary_model_stage"}),
    ]
    objective = outcomes[0] if outcomes else {}
    for key, meta in mappings:
        value = summary.get(key)
        if not isinstance(value, dict):
            continue
        seeded = {**value, **meta, "label": key}
        results.append(build_result_row(key, seeded, objective, core_contract, result_index))
        result_index += 1
    return results


def attach_table_links(results: list[dict], tables: list[dict]) -> list[dict]:
    if not tables:
        return results
    stage_to_table = {}
    for table in tables:
        stage_to_table.setdefault(
            (table.get("objective_id"), table.get("stage_id")), table["table_id"]
        )
    for row in results:
        row["source_table_id"] = row.get("source_table_id") or stage_to_table.get(
            (row.get("objective_id"), row.get("stage_id")), ""
        )
    return results


def artifact_metadata(summary: dict) -> dict[str, dict]:
    """Index executor-declared artifact ownership by basename.

    Multi-objective analyses must declare objective_id for each artifact.  A
    basename index keeps the contract portable when projects move directories.
    """
    indexed: dict[str, dict] = {}
    for item in summary.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        raw_path = item.get("source_path") or item.get("path") or item.get("artifact_path") or item.get("name")
        if raw_path:
            indexed[Path(str(raw_path)).name] = item
    return indexed


def resolve_artifact_identity(
    path: Path,
    summary: dict,
    objective_ids: list[str],
    failures: list[str],
) -> tuple[str, str, dict]:
    metadata = artifact_metadata(summary).get(path.name, {})
    objective_id = str(metadata.get("objective_id", "")).strip()
    declared_stage = str(metadata.get("stage_id", "")).strip()
    inferred_stage = infer_stage_from_name(path.name)
    stage_id = declared_stage or inferred_stage
    if not objective_id and len(objective_ids) == 1:
        objective_id = objective_ids[0]
    if not objective_id:
        failures.append(
            f"multi-objective artifact lacks explicit objective_id in analysis_summary.json: {path.name}"
        )
    elif objective_id not in objective_ids:
        failures.append(f"artifact {path.name} references unknown objective_id {objective_id!r}")
    if len(objective_ids) > 1 and not declared_stage:
        failures.append(
            f"multi-objective artifact lacks explicit stage_id in analysis_summary.json: {path.name}"
        )
    if declared_stage and inferred_stage != "report_stage" and declared_stage != inferred_stage:
        failures.append(
            f"artifact {path.name} declares stage_id={declared_stage!r} but filename semantics indicate {inferred_stage!r}"
        )
    declared_hash = str(metadata.get("sha256", "")).strip()
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(objective_ids) > 1 and not declared_hash:
        failures.append(f"multi-objective artifact lacks SHA-256 binding: {path.name}")
    elif declared_hash and declared_hash != actual_hash:
        failures.append(f"artifact SHA-256 mismatch: {path.name}")
    return objective_id, stage_id, metadata


def numeric_match(left, right, tolerance: float = 1e-9) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance * max(1.0, abs(float(right)))
    except (TypeError, ValueError):
        return False


def table_contains_result(path: Path, result: dict) -> bool:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    field_aliases = {
        "estimate": ("estimate",),
        "ci_lower": ("ci_lower", "conf.low", "ci_low"),
        "ci_upper": ("ci_upper", "conf.high", "ci_high"),
        "p_value": ("p_value", "p.value"),
    }
    for row in rows:
        checks = []
        for result_field, aliases in field_aliases.items():
            expected = result.get(result_field)
            if expected in {None, ""}:
                continue
            actual = next((row.get(name) for name in aliases if row.get(name) not in {None, ""}), None)
            checks.append(actual is not None and numeric_match(actual, expected))
        if checks and all(checks):
            return True
    return False


def table_registry(
    table_dir: Path,
    summary: dict,
    objective_ids: list[str],
    results: list[dict],
    failures: list[str],
    design_mode: str = "sample",
) -> list[dict]:
    rows = []
    stage_to_result_ids = {}
    for result in results:
        stage_to_result_ids.setdefault(
            (result.get("objective_id"), result.get("stage_id")), []
        ).append(result["result_id"])
    for idx, path in enumerate(sorted(table_dir.glob("*.csv")), start=1):
        objective_id, stage_id, metadata = resolve_artifact_identity(path, summary, objective_ids, failures)
        candidates = [
            result
            for result in results
            if result.get("objective_id") == objective_id and result.get("stage_id") == stage_id
        ]
        declared_labels = {str(item) for item in metadata.get("source_result_labels", [])}
        if declared_labels:
            selected_results = [result for result in candidates if result.get("label") in declared_labels]
            missing_labels = declared_labels - {result.get("label") for result in selected_results}
            if missing_labels:
                failures.append(f"artifact {path.name} declares unknown source_result_labels: {sorted(missing_labels)}")
        else:
            selected_results = candidates
        if len(objective_ids) > 1 and stage_id in {"primary_model_stage", "sensitivity_stage"} and not declared_labels:
            failures.append(f"multi-objective model table lacks source_result_labels: {path.name}")
        for result in selected_results:
            if not table_contains_result(path, result):
                failures.append(
                    f"artifact content does not reproduce linked result {result.get('result_id')}: {path.name}"
                )
        caption, note, display_title = table_caption_and_note(stage_id, path.stem, design_mode)
        rows.append(
            {
                "table_id": make_id("TAB", idx),
                "objective_id": objective_id,
                "stage_id": stage_id,
                "title": path.stem,
                "display_title": display_title,
                "caption": caption,
                "note": note,
                "registry_role": infer_registry_role(stage_id, path.stem),
                "source_path": str(path.resolve()),
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_result_ids": [result["result_id"] for result in selected_results],
            }
        )
    return rows


def resolve_figure_source_tables(
    figure_path: Path,
    metadata: dict,
    objective_id: str,
    stage_id: str,
    tables: list[dict],
    failures: list[str],
) -> list[str]:
    """Resolve exact table provenance without silently choosing the first table.

    Executors should declare ``source_table_paths`` for a figure whenever an
    objective/stage owns more than one table.  Basenames are used so the
    declaration remains portable after moving a project directory.  A sole
    objective/stage table may be inferred; ambiguous matches are a hard
    registry-construction failure rather than an arbitrary first-table link.
    """
    same_scope = [
        row
        for row in tables
        if row.get("objective_id") == objective_id and row.get("stage_id") == stage_id
    ]
    declared_paths = metadata.get("source_table_paths", [])
    if isinstance(declared_paths, str):
        declared_paths = [declared_paths]
    declared_names = [Path(str(item)).name for item in declared_paths if str(item).strip()]
    if declared_names:
        by_name = {Path(str(row.get("source_path", ""))).name: row for row in tables}
        selected: list[dict] = []
        for name in declared_names:
            table = by_name.get(name)
            if table is None:
                failures.append(f"figure {figure_path.name} declares unknown source table: {name}")
                continue
            if table.get("objective_id") != objective_id or table.get("stage_id") != stage_id:
                failures.append(
                    f"figure {figure_path.name} source table is outside its objective/stage: {name}"
                )
                continue
            selected.append(table)
        return list(dict.fromkeys(row["table_id"] for row in selected))
    if len(same_scope) == 1:
        return [same_scope[0]["table_id"]]
    if len(same_scope) > 1:
        failures.append(
            f"figure {figure_path.name} has ambiguous source tables for {objective_id}/{stage_id}; "
            "declare source_table_paths in analysis_summary.json"
        )
    return []


def figure_registry(
    figure_dir: Path,
    summary: dict,
    objective_ids: list[str],
    results: list[dict],
    tables: list[dict],
    failures: list[str],
    design_mode: str = "sample",
) -> list[dict]:
    rows = []
    stage_to_result_ids = {}
    for result in results:
        stage_to_result_ids.setdefault(
            (result.get("objective_id"), result.get("stage_id")), []
        ).append(result["result_id"])
    for idx, path in enumerate(sorted(figure_dir.glob("*.png")), start=1):
        objective_id, stage_id, metadata = resolve_artifact_identity(path, summary, objective_ids, failures)
        candidates = [
            result
            for result in results
            if result.get("objective_id") == objective_id and result.get("stage_id") == stage_id
        ]
        declared_labels = {str(item) for item in metadata.get("source_result_labels", [])}
        if declared_labels:
            selected_results = [result for result in candidates if result.get("label") in declared_labels]
            missing_labels = declared_labels - {result.get("label") for result in selected_results}
            if missing_labels:
                failures.append(f"figure {path.name} declares unknown source_result_labels: {sorted(missing_labels)}")
            candidates = selected_results
        if len(objective_ids) > 1 and stage_id in {"primary_model_stage", "sensitivity_stage"} and not declared_labels:
            failures.append(f"multi-objective model figure lacks source_result_labels: {path.name}")
        if stage_id in {"primary_model_stage", "sensitivity_stage"} and not candidates:
            failures.append(f"model figure has no linked registered result: {path.name}")
        source_table_ids = resolve_figure_source_tables(
            path, metadata, objective_id, stage_id, tables, failures
        )
        caption, legend, display_title = figure_caption_and_legend(stage_id, path.stem, design_mode)
        rows.append(
            {
                "figure_id": make_id("FIG", idx),
                "objective_id": objective_id,
                "stage_id": stage_id,
                "title": path.stem,
                "display_title": display_title,
                "caption": caption,
                "legend": legend,
                "registry_role": infer_registry_role(stage_id, path.stem),
                "source_path": str(path.resolve()),
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_result_ids": [result["result_id"] for result in candidates],
                "source_table_ids": source_table_ids,
            }
        )
    return rows


def diagnostic_registry(diagnostic_log: dict, objective_ids: list[str]) -> list[dict]:
    rows = []
    by_objective = diagnostic_log.get("diagnostics_by_objective", {})
    if not by_objective and len(objective_ids) == 1 and diagnostic_log.get("diagnostics"):
        by_objective = {objective_ids[0]: diagnostic_log["diagnostics"]}
    idx = 1
    for objective_id, diagnostics in by_objective.items():
        for name, value in diagnostics.items():
            rows.append(
                {
                    "diagnostic_id": make_id("DGN", idx),
                    "objective_id": objective_id,
                    "stage_id": "primary_model_stage",
                    "diagnostic_type": name,
                    "diagnostic_value": value,
                    "threshold": "",
                    "status": "reported",
                    "interpretation_note": "Review diagnostic values in context of the active model family.",
                }
            )
            idx += 1
    return rows


def main_build_registries() -> None:
    parser = argparse.ArgumentParser(description="Build analysis registries from analysis outputs and contracts.")
    parser.add_argument("project_root")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    analysis_out = project_root / "analysis" / "output"
    core_contract = load_json(project_root / "analysis" / "contracts" / "analysis_core_contract.json")
    executable_plan = load_json(project_root / "analysis" / "contracts" / "executable_analysis_plan.json")
    runtime_state = load_json(project_root / "analysis" / "contracts" / "execution_state.json", default={})
    executable_plan_path = project_root / "analysis" / "contracts" / "executable_analysis_plan.json"
    executable_plan_sha256 = hashlib.sha256(executable_plan_path.read_bytes()).hexdigest()
    summary = load_json(analysis_out / "analysis_summary.json")
    diagnostic_log = load_json(analysis_out / "diagnostic_log.json")
    objective_ids = [row.get("objective_id", f"OBJ{idx:03d}") for idx, row in enumerate(core_contract.get("outcomes", []), start=1)] or ["OBJ001"]
    registries_dir = project_root / "registries"

    results = canonical_result_rows(summary, core_contract)
    failures: list[str] = []
    design_mode = core_contract.get("design_context", {}).get("design_mode", "sample")
    tables = table_registry(analysis_out / "tables", summary, objective_ids, results, failures, design_mode)
    results = attach_table_links(results, tables)
    figures = figure_registry(
        analysis_out / "figures", summary, objective_ids, results, tables, failures, design_mode
    )
    diagnostics = diagnostic_registry(diagnostic_log, objective_ids)
    decisions = load_json(project_root / "analysis" / "contracts" / "decision_registry.json", default=[])
    deviations = load_json(project_root / "analysis" / "contracts" / "deviation_register.json", default=[])
    objective_stage_completion = runtime_state.get("objective_stage_completion", {})
    plan_stages = {
        objective.get("objective_id"): set(objective.get("stage_map", {}))
        for objective in executable_plan.get("objectives", [])
    }
    for artifact in tables + figures:
        artifact_objective = artifact.get("objective_id")
        artifact_stage = artifact.get("stage_id")
        if artifact_stage not in plan_stages.get(artifact_objective, set()):
            failures.append(
                f"artifact {Path(artifact.get('source_path', '')).name} declares a stage absent from "
                f"the executable objective plan: {artifact_objective}/{artifact_stage}"
            )
            continue
        declared_evidence = objective_stage_completion.get(artifact_objective, {}).get(artifact_stage, {}).get("evidence_paths", [])
        resolved_evidence = set()
        for raw_path in declared_evidence:
            evidence_path = Path(raw_path)
            if not evidence_path.is_absolute():
                evidence_path = project_root / evidence_path
            resolved_evidence.add(str(evidence_path.resolve()))
        if str(Path(artifact.get("source_path", "")).resolve()) not in resolved_evidence:
            failures.append(
                f"artifact is not declared as execution evidence for {artifact_objective}/{artifact_stage}: "
                f"{Path(artifact.get('source_path', '')).name}"
            )

    write_json(registries_dir / "result_registry.json", results)
    write_json(registries_dir / "table_registry.json", tables)
    write_json(registries_dir / "figure_registry.json", figures)
    write_json(registries_dir / "diagnostic_registry.json", diagnostics)
    write_json(registries_dir / "decision_registry.json", decisions)
    write_json(registries_dir / "deviation_registry.json", deviations)
    primary_result_objective_ids = {
        row.get("objective_id")
        for row in results
        if row.get("stage_id") == "primary_model_stage" and row.get("objective_id")
    }
    required_primary_objectives = []
    for objective in executable_plan.get("objectives", []):
        primary_status = objective.get("stage_map", {}).get("primary_model_stage", {}).get("status")
        if primary_status in {"required", "degraded_with_deviation"}:
            required_primary_objectives.append(objective.get("objective_id", "UNKNOWN"))
    missing_primary_objectives = sorted(
        objective_id
        for objective_id in required_primary_objectives
        if objective_id not in primary_result_objective_ids
    )
    failures.extend(
        [
        f"required primary-model result missing for objective {objective_id}"
        for objective_id in missing_primary_objectives
        ]
    )
    if runtime_state.get("execution_plan_sha256") != executable_plan_sha256:
        failures.append("execution_state.json is missing the current executable-plan SHA-256 binding")
    diagnostic_objective_ids = {row.get("objective_id") for row in diagnostics}
    for objective in executable_plan.get("objectives", []):
        objective_id_for_check = objective.get("objective_id", "UNKNOWN")
        required_execution_stages = {
            stage
            for stage, meta in objective.get("stage_map", {}).items()
            if meta.get("status") == "required" and stage not in {"registry_finalize_stage", "report_stage"}
        }
        objective_completion = objective_stage_completion.get(objective_id_for_check, {})
        for stage in sorted(required_execution_stages):
            completion = objective_completion.get(stage, {})
            if completion.get("status") not in {"completed", "degraded_with_deviation"}:
                failures.append(f"{objective_id_for_check}: required stage lacks completed execution evidence: {stage}")
                continue
            paths = completion.get("evidence_paths", [])
            if not paths:
                failures.append(f"{objective_id_for_check}: required stage has no evidence path: {stage}")
                continue
            for raw_path in paths:
                evidence_path = Path(raw_path)
                if not evidence_path.is_absolute():
                    evidence_path = project_root / evidence_path
                if not evidence_path.exists() or evidence_path.stat().st_size == 0:
                    failures.append(f"{objective_id_for_check}: required stage evidence is missing or empty: {stage} -> {raw_path}")
        if "primary_model_stage" in required_execution_stages and objective_id_for_check not in diagnostic_objective_ids:
            failures.append(f"{objective_id_for_check}: primary model stage has no registered diagnostics")
    realized_methods = sorted(
        {
            str(row.get("source_model") or row.get("model_family"))
            for row in results
            if row.get("source_model") or row.get("model_family")
        }
        | {str(item) for item in runtime_state.get("realized_methods", []) if str(item).strip()}
    )

    write_json(
        project_root / "analysis" / "contracts" / "execution_state.json",
        {
            "generated_at": now_iso(),
            "execution_level": "results_available" if results else "scaffold_only",
            "execution_plan_sha256": runtime_state.get("execution_plan_sha256", ""),
            "objective_stage_completion": objective_stage_completion,
            "realized_methods": realized_methods,
            "skipped_stages": runtime_state.get("skipped_stages", []),
            "degraded_stages": [
                stage for stage, status in executable_plan.get("executable_stage_set", {}).items() if status == "degraded_with_deviation"
            ],
            "runtime_warnings": runtime_state.get("runtime_warnings", []),
            "failures": failures,
            "unresolved_fields": runtime_state.get("unresolved_fields", []),
            "analysis_release_mode": runtime_state.get("analysis_release_mode", ""),
            "inferential_adequacy": runtime_state.get("inferential_adequacy", {}),
            "sensitivity_axes": runtime_state.get("sensitivity_axes", []),
            "sensitivity_not_applicable": runtime_state.get("sensitivity_not_applicable", []),
        }
    )

# freeze_registries


def main_freeze_registries() -> None:
    parser = argparse.ArgumentParser(description="Finalize and freeze v2.2 registries.")
    parser.add_argument("project_root")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    analysis_audit = load_json(project_root / "analysis" / "output" / "analysis_consistency_audit.json", default={})
    design_audit = load_json(project_root / "analysis" / "output" / "design_consistency_audit.json", default={})
    executable_plan_path = project_root / "analysis" / "contracts" / "executable_analysis_plan.json"
    executable_plan = load_json(executable_plan_path, default={})
    result_registry = load_json(project_root / "registries" / "result_registry.json", default=[])
    execution_state = load_json(project_root / "analysis" / "contracts" / "execution_state.json", default={})
    objective_stage_completion = execution_state.get("objective_stage_completion", {})
    audit_statuses = {analysis_audit.get("status", "missing"), design_audit.get("status", "missing")}
    blockers = []
    accepted_audit_statuses = {"pass", "degraded_with_deviation"}
    if not audit_statuses.issubset(accepted_audit_statuses):
        blockers.append("one or more required audits did not pass")
    if execution_state.get("failures"):
        blockers.extend(str(item) for item in execution_state["failures"])

    result_objective_ids = {
        result.get("objective_id")
        for result in result_registry
        if result.get("stage_id") == "primary_model_stage" and result.get("objective_id")
    }
    for objective in executable_plan.get("objectives", []):
        primary_status = objective.get("stage_map", {}).get("primary_model_stage", {}).get("status")
        objective_id = objective.get("objective_id", "UNKNOWN")
        if primary_status in {"required", "degraded_with_deviation"} and objective_id not in result_objective_ids:
            blocker = f"required primary-model result missing for objective {objective_id}"
            if blocker not in blockers:
                blockers.append(blocker)
        required_stages = {
            stage
            for stage, meta in objective.get("stage_map", {}).items()
            if meta.get("status") == "required"
            and stage not in {"registry_finalize_stage", "report_stage"}
        }
        incomplete = sorted(
            stage
            for stage in required_stages
            if objective_stage_completion.get(objective_id, {}).get(stage, {}).get("status")
            not in {"completed", "degraded_with_deviation"}
        )
        if incomplete:
            blockers.append(
                f"objective {objective_id} has incomplete required stages: {', '.join(incomplete)}"
            )
    freeze_status = "ready" if not blockers else "fail"
    freeze_version = "FREEZE_" + now_iso().replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")

    manifest = {
        "freeze_version": freeze_version,
        "generated_at": now_iso(),
        "status": freeze_status,
        "registries": {
            "result_registry": str((project_root / "registries" / "result_registry.json").resolve()),
            "table_registry": str((project_root / "registries" / "table_registry.json").resolve()),
            "figure_registry": str((project_root / "registries" / "figure_registry.json").resolve()),
            "diagnostic_registry": str((project_root / "registries" / "diagnostic_registry.json").resolve()),
            "deviation_registry": str((project_root / "registries" / "deviation_registry.json").resolve()),
            "decision_registry": str((project_root / "registries" / "decision_registry.json").resolve()),
        },
        "audits": {
            "analysis_consistency": analysis_audit.get("status", "missing"),
            "design_consistency": design_audit.get("status", "missing"),
        },
        "blockers": blockers,
    }
    out = project_root / "analysis" / "frozen" / "freeze_manifest.json"
    write_json(out, manifest)

    objective_map = executable_plan.get("objective_execution_map", [])
    degraded_stages = set(execution_state.get("degraded_stages", []))
    for row in objective_map:
        linked_stages = row.get("linked_stages", [])
        required_linked_stages = {
            stage
            for stage in linked_stages
            if stage not in {"registry_finalize_stage", "report_stage"}
            and executable_plan.get("executable_stage_set", {}).get(stage) == "required"
        }
        all_required_complete = all(
            objective_stage_completion.get(row.get("objective_id"), {}).get(stage, {}).get("status")
            in {"completed", "degraded_with_deviation"}
            for stage in required_linked_stages
        )
        has_primary_result = any(
            result.get("objective_id") == row.get("objective_id")
            and result.get("stage_id") == "primary_model_stage"
            for result in result_registry
        )
        has_degraded = any(stage in degraded_stages for stage in linked_stages)
        if freeze_status == "ready" and all_required_complete and has_primary_result:
            row["executed_status"] = "executed_with_deviation" if has_degraded else "frozen_ready"
            row["final_reason"] = (
                "Objective reached registry freeze with degraded stages recorded."
                if has_degraded
                else "Objective reached registry freeze with all required execution stages and the primary result evidenced."
            )
        else:
            row["executed_status"] = "freeze_failed"
            row["final_reason"] = "Registry freeze failed because audits or required result checks did not pass."
    if objective_map:
        write_json(
            project_root / "analysis" / "contracts" / "objective_execution_map.json",
            objective_map,
        )

    if freeze_status != "ready":
        raise SystemExit("Registry freeze blocked: " + "; ".join(blockers))


COMMANDS = {
    "build_registries": main_build_registries,
    "freeze_registries": main_freeze_registries,
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
