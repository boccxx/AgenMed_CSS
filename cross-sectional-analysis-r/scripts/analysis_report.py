#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/analysis_report.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from analysis_common import STAGE_ORDER, load_json, now_iso, write_json, write_text

# report_writer_common
STAGE_LABELS = {
    "qc_stage": "Data Preparation And Quality Control",
    "missingness_stage": "Missingness And Data Handling",
    "descriptive_stage": "Descriptive And Baseline Characteristics",
    "bivariate_stage": "Bivariate Analysis",
    "primary_model_stage": "Primary Model",
    "interaction_stage": "Interaction Analysis",
    "dose_response_stage": "Dose-Response Analysis",
    "sensitivity_stage": "Sensitivity Analysis",
}


def sort_registry_items(items: list[dict], id_key: str) -> list[dict]:
    stage_rank = {stage: idx for idx, stage in enumerate(STAGE_ORDER)}
    role_rank = {"main_text": 0, "supplement": 1, "report_only": 2}
    return sorted(
        items,
        key=lambda item: (
            stage_rank.get(item.get("stage_id", ""), 999),
            role_rank.get(item.get("registry_role", "supplement"), 9),
            item.get(id_key, ""),
        ),
    )


def load_report_bundle(project_root: Path) -> dict:
    executable_plan = load_json(project_root / "analysis" / "contracts" / "executable_analysis_plan.json")
    frozen_objective_map = load_json(
        project_root / "analysis" / "contracts" / "objective_execution_map.json", default=[]
    )
    if frozen_objective_map:
        executable_plan = dict(executable_plan)
        executable_plan["objective_execution_map"] = frozen_objective_map
    return {
        "freeze": load_json(project_root / "analysis" / "frozen" / "freeze_manifest.json"),
        "core": load_json(project_root / "analysis" / "contracts" / "analysis_core_contract.json"),
        "requested_plan": load_json(project_root / "analysis" / "contracts" / "requested_analysis_plan.json"),
        "executable_plan": executable_plan,
        "execution_state": load_json(project_root / "analysis" / "contracts" / "execution_state.json", default={}),
        "profile": load_json(project_root / "analysis" / "profile" / "data_profile.json", default={}),
        "analysis_audit": load_json(project_root / "analysis" / "output" / "analysis_consistency_audit.json", default={}),
        "design_audit": load_json(project_root / "analysis" / "output" / "design_consistency_audit.json", default={}),
        "stage_contracts": {
            path.stem: load_json(path)
            for path in sorted((project_root / "analysis" / "stage_contracts").glob("*.json"))
        },
        "results": sort_registry_items(load_json(project_root / "registries" / "result_registry.json", default=[]), "result_id"),
        "diagnostics": sort_registry_items(load_json(project_root / "registries" / "diagnostic_registry.json", default=[]), "diagnostic_id"),
        "decisions": sort_registry_items(load_json(project_root / "registries" / "decision_registry.json", default=[]), "decision_id"),
        "deviations": sort_registry_items(load_json(project_root / "registries" / "deviation_registry.json", default=[]), "deviation_id"),
        "tables": sort_registry_items(load_json(project_root / "registries" / "table_registry.json", default=[]), "table_id"),
        "figures": sort_registry_items(load_json(project_root / "registries" / "figure_registry.json", default=[]), "figure_id"),
    }


def plain_text(value: str) -> str:
    return re.sub(r"`([^`]*)`", r"\1", value)


def format_scalar(value) -> str:
    if value in (None, "", []):
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        if "term" in value and "vif" in value:
            return f"{value['term']} ({format_scalar(value['vif'])})"
        pairs = []
        for key, item in list(value.items())[:4]:
            pairs.append(f"{key}={format_scalar(item)}")
        return ", ".join(pairs)
    if isinstance(value, list):
        if not value:
            return "NA"
        if all(isinstance(item, dict) for item in value):
            if all("term" in item and "vif" in item for item in value[:5]):
                ordered = sorted(value, key=lambda item: float(item.get("vif", 0) or 0), reverse=True)
                return ", ".join(f"{item['term']} ({format_scalar(item['vif'])})" for item in ordered[:5])
            compact = []
            for item in value[:4]:
                compact.append(format_scalar(item))
            return "; ".join(compact)
        return ", ".join(format_scalar(item) for item in value[:5])
    return str(value)


def display_number_map(bundle: dict, kind: str) -> dict[str, int]:
    items = bundle["tables"] if kind == "table" else bundle["figures"]
    id_key = "table_id" if kind == "table" else "figure_id"
    filtered = [row for row in items if row.get("registry_role") == "main_text"]
    return {row[id_key]: idx for idx, row in enumerate(filtered, start=1)}


def result_sentence(row: dict, demonstration: bool = False) -> str:
    info = row.get("inference_basis", {})
    level = 100 * float(info.get("confidence_level", 0.95) or 0.95)
    contrast = row.get("exposure_contrast") or row.get("exposure_unit") or "the registered exposure contrast"
    adjustment = row.get("adjustment_set") or []
    adjustment_text = (
        "adjusted for " + ", ".join(str(item) for item in adjustment)
        if adjustment
        else "unadjusted"
    )
    prefix = "Illustrative model output" if demonstration else row.get("label", row.get("result_id", "Result"))
    distribution = info.get("reference_distribution")
    distribution_text = f" using the declared {distribution} reference distribution" if distribution else ""
    return (
        f"{prefix} for {contrast} was {format_scalar(row.get('estimate'))} on the "
        f"{row.get('effect_measure', 'target scale')} scale ({adjustment_text}), with a {level:.0f}% CI from "
        f"{format_scalar(row.get('ci_lower'))} to {format_scalar(row.get('ci_upper'))}; "
        f"the reported p-value was {format_scalar(row.get('p_value'))}{distribution_text}."
        + (" These values are displayed only to verify the pipeline and must not be interpreted as study evidence." if demonstration else "")
    )


def stage_display_refs(bundle: dict, stage_id: str, kind: str) -> str:
    items = bundle["tables"] if kind == "table" else bundle["figures"]
    label = "Table" if kind == "table" else "Figure"
    id_key = "table_id" if kind == "table" else "figure_id"
    numbering = display_number_map(bundle, kind)
    filtered = [row for row in items if row.get("stage_id") == stage_id and row.get("registry_role") == "main_text"]
    refs = []
    for row in filtered:
        number = numbering.get(row.get(id_key), "?")
        refs.append(f"{label} {number}: {row.get('display_title') or row.get('caption') or row.get('title', label)}")
    return "; ".join(refs)


def executive_summary_paragraph(bundle: dict) -> str:
    results = bundle["results"]
    demonstration = bundle.get("release_quality", {}).get("analysis_release_mode") in {
        "demonstration_only", "simulation_only", "smoke_test_only"
    }
    if results:
        leading = result_sentence(results[0], demonstration=demonstration)
    else:
        leading = "No main-text frozen estimate was available at the time of report generation."
    return (
        ("This report documents a pipeline demonstration" if demonstration else "This report summarizes the adjudicated cross-sectional analysis")
        + " after requested methods were translated into an executable plan, "
        "after stage outputs were audited, and after registries were frozen. "
        + leading
        + (" The output is not eligible for scientific inference or substantive conclusions."
           if demonstration else
           " The report is review-friendly, design-aware, and explicit about primary, supportive, and exploratory evidence within the frozen bundle.")
    )


def study_purpose_paragraph(bundle: dict) -> str:
    requested = bundle["requested_plan"]
    core = bundle["core"]
    objective_rows = core.get("outcomes", [])
    purpose = requested.get("study_identity", {}).get("study_title", "the active study")
    demonstration = bundle.get("release_quality", {}).get("analysis_release_mode") in {
        "demonstration_only", "simulation_only", "smoke_test_only"
    }
    if demonstration:
        return (
            f"This run uses {purpose} only to verify intake, model execution, registry binding, auditing, and rendering. "
            "It does not answer the substantive study question and it does not estimate a release-eligible scientific effect."
        )
    if objective_rows:
        primary = objective_rows[0]
        target = primary.get("outcome_label") or primary.get("outcome_id") or primary.get("variable") or "the primary outcome"
        exposure = core.get("primary_exposure", {}).get("label") or core.get("primary_exposure", {}).get("variable") or "the primary exposure"
        return (
            f"This analysis was undertaken to address the primary study question in {purpose}, with particular focus on the association between "
            f"{exposure} and {target}. The report treats the statistical analysis as an inferential object rather than a code log: it explains why the adjudicated design, "
            "missing-data strategy, modelling path, and sensitivity checks were selected, and how those choices constrain the interpretation of the final estimates."
        )
    return (
        f"This analysis was undertaken to address the study question in {purpose}. "
        "The report emphasizes design realization, estimand alignment, and auditable interpretation rather than simply listing model outputs."
    )


def main_methods_paragraph(bundle: dict) -> str:
    core = bundle["core"]
    design = core.get("design_context", {})
    missing = core.get("missing_data_policy", {})
    outcomes = core.get("outcomes", [])
    objective = outcomes[0] if outcomes else {}
    demonstration = bundle.get("release_quality", {}).get("analysis_release_mode") in {
        "demonstration_only", "simulation_only", "smoke_test_only"
    }
    return (
        f"The main analytical methods were chosen to respect the realized design mode `{design.get('design_mode', 'sample')}`, the declared estimand family "
        f"`{core.get('estimand_family', '')}`, and the requested missing-data strategy `{missing.get('requested_strategy', 'Not specified')}`. "
        f"The primary outcome family was `{objective.get('outcome_family', 'unspecified')}`, and the requested analysis family was "
        f"`{objective.get('analysis_family', objective.get('requested_method_family', 'unspecified'))}`. "
        + (" The listed stages were executed only to verify workflow behavior; none authorizes substantive inference."
           if demonstration else
           " Descriptive, bivariate, primary-model, interaction, dose-response, sensitivity, and diagnostic stages were retained or simplified only after adjudication against the actual data structure.")
    )


def expected_analysis_content_paragraph(bundle: dict) -> str:
    plan = bundle["executable_plan"]
    objective_map = plan.get("objective_execution_map", [])
    if objective_map:
        scope = "; ".join(
            f"{row.get('objective_id')}: executable `{row.get('executable_status')}`, executed `{row.get('executed_status')}`"
            for row in objective_map
        )
    else:
        scope = "No objective execution map was available."
    return (
        "The expected analysis content of this report was not treated as a fixed recipe. Instead, the report was expected to include only those descriptive summaries, "
        "model estimates, tables, figures, and interpretation statements that remained admissible after design adjudication and registry freeze. "
        f"The resulting scope was: {scope}."
    )


def objective_scope_lines(bundle: dict) -> list[str]:
    lines: list[str] = []
    for row in bundle["executable_plan"].get("objective_execution_map", []):
        lines.append(
            f"{row.get('objective_id', '')} moved from requested status `{row.get('requested_status', '')}` "
            f"to executable status `{row.get('executable_status', '')}` and currently sits at executed status "
            f"`{row.get('executed_status', '')}`. {row.get('final_reason', '')}"
        )
    return lines


def design_summary_paragraph(bundle: dict) -> str:
    core = bundle["core"]
    design_context = core.get("design_context", {})
    requested = bundle["requested_plan"].get("study_identity", {})
    analysis_audit = bundle["analysis_audit"].get("status", "missing")
    design_audit = bundle["design_audit"].get("status", "missing")
    return (
        f"The current analysis report pertains to {requested.get('study_title', 'the active study')} and is anchored to decision "
        f"`{core.get('study_identity', {}).get('decision_id', 'DECISION_PENDING')}`. The realized design mode was "
        f"`{design_context.get('design_mode', 'sample')}`, with weight variable "
        f"`{design_context.get('weight_variable') or 'none'}`, strata variable `{design_context.get('strata_variable') or 'none'}`, "
        f"and PSU variable `{design_context.get('psu_variable') or 'none'}`. This design realization passed through "
        f"the analysis consistency audit with status `{analysis_audit}` and the design consistency audit with status `{design_audit}`, "
        f"so the narrative below reflects only frozen evidence objects rather than provisional stage outputs."
    )


def stage_narrative(bundle: dict, stage_id: str) -> list[str]:
    stage_contract = bundle["stage_contracts"].get(stage_id, {})
    stage_results = [row for row in bundle["results"] if row.get("stage_id") == stage_id]
    stage_tables = [row for row in bundle["tables"] if row.get("stage_id") == stage_id]
    stage_figures = [row for row in bundle["figures"] if row.get("stage_id") == stage_id]
    if not stage_contract and not stage_results and not stage_tables and not stage_figures:
        return []

    stage_status = stage_contract.get("stage_status", "not_applicable")
    path_mode = stage_contract.get("path_mode", "simplified")
    methods = ", ".join(stage_contract.get("required_methods", [])) or "no registered method"
    paragraphs = [
        (
            f"This stage was adjudicated as `{stage_status}` and executed under a `{path_mode}` path. "
            f"The active method commitments for the stage were: {methods}. "
            f"The stage was linked to objectives {', '.join(stage_contract.get('objective_links', [])) or 'none'}, "
            f"and any blocking or qualification notes were carried through the contract before execution."
        )
    ]
    if stage_results:
        paragraphs.append("The stage yielded the following frozen statistical findings: " + " ".join(result_sentence(row) for row in stage_results[:4]))
    else:
        paragraphs.append(
            "No main-text result rows were frozen for this stage. This usually means the stage was descriptive, "
            "non-estimand-defining, or deliberately simplified after adjudication."
        )
    if stage_tables or stage_figures:
        table_text = ", ".join(
            f"{row.get('table_id', '')} ({row.get('display_title') or row.get('caption') or row.get('title', '')})"
            for row in stage_tables[:4]
        ) or "no frozen tables"
        figure_text = ", ".join(
            f"{row.get('figure_id', '')} ({row.get('display_title') or row.get('caption') or row.get('title', '')})"
            for row in stage_figures[:4]
        ) or "no frozen figures"
        paragraphs.append(
            f"Frozen evidence objects associated with this stage included {table_text}; figures included {figure_text}. "
            "These objects are the only sources that downstream report rendering is allowed to cite."
        )
    return paragraphs


def stage_overview_paragraph(bundle: dict, stage_id: str) -> str:
    stage_contract = bundle["stage_contracts"].get(stage_id, {})
    stage_status = stage_contract.get("stage_status", "not_applicable")
    path_mode = stage_contract.get("path_mode", "simplified")
    methods = ", ".join(stage_contract.get("required_methods", [])) or "no registered method"
    objective_links = ", ".join(stage_contract.get("objective_links", [])) or "none"
    label = STAGE_LABELS.get(stage_id, stage_id)
    purposes = {
        "qc_stage": "This step established the row-level integrity, variable ranges, coding consistency, and design fields required before an analytic denominator could be declared.",
        "missingness_stage": "This step characterized variable-specific and joint incompleteness so that the chosen analysis population and any imputation decision were tied to observed data rather than defaults.",
        "descriptive_stage": "This step described the realized sample, exposure distribution, outcome burden, and covariate composition before adjustment, preserving the denominators needed to interpret later models.",
        "bivariate_stage": "This step examined unadjusted exposure-outcome and covariate-outcome patterns as exploratory context, without allowing screening p-values to redefine the adjustment set.",
        "primary_model_stage": "This step estimated the prespecified primary estimand with the frozen outcome definition, exposure contrast, covariate policy, and variance estimator.",
        "interaction_stage": "This step evaluated prespecified effect modification on the registered scale while retaining the interaction term, component terms, subgroup support, and multiplicity boundary.",
        "dose_response_stage": "This step examined functional form and non-linearity without replacing the primary exposure contrast or selecting a curve solely for visual fit.",
        "sensitivity_stage": "This step stressed the assumptions most likely to change the primary estimate, including population definition, missing-data handling, coding, and model family where registered.",
    }
    return (
        f"{purposes.get(stage_id, label + ' preserved its registered analytical purpose.')} "
        f"The executable contract classified the step as `{stage_status}` on a `{path_mode}` path, linked it to {objective_links}, "
        f"and retained the following method commitments: {methods}."
    )


def stage_findings_paragraph(bundle: dict, stage_id: str) -> str:
    stage_results = [row for row in bundle["results"] if row.get("stage_id") == stage_id]
    table_refs = stage_display_refs(bundle, stage_id, "table")
    figure_refs = stage_display_refs(bundle, stage_id, "figure")
    parts = []
    if stage_results:
        demonstration = bundle.get("release_quality", {}).get("analysis_release_mode") in {
            "demonstration_only", "simulation_only", "smoke_test_only"
        }
        parts.append("Key frozen findings were as follows: " + " ".join(result_sentence(row, demonstration=demonstration) for row in stage_results[:4]))
    else:
        no_result_explanations = {
            "qc_stage": "No inferential result belongs to quality control; its evidence is the reconciled sample, issue log, and verified variable structure.",
            "missingness_stage": "No standalone effect estimate was registered here; the substantive output is the missingness profile and the resulting handling decision.",
            "descriptive_stage": "The stage contributes denominators and distributions rather than a primary association estimate; these appear in its frozen descriptive table.",
            "bivariate_stage": "No bivariate coefficient was promoted to the main text, preventing exploratory screening from competing with the adjusted estimand.",
            "interaction_stage": "No interaction estimate met the prespecified support and reporting requirements, so the report does not imply subgroup heterogeneity.",
            "dose_response_stage": "No dose-response estimate was frozen; functional-form claims are therefore outside the released evidence set.",
            "sensitivity_stage": "No sensitivity coefficient was promoted to the main text; robustness is limited to the checks documented in the diagnostic and decision records.",
        }
        parts.append(no_result_explanations.get(stage_id, "No main-text result row was frozen for this analytical step."))
    if table_refs:
        parts.append(f"The main text retained the following tables for this stage: {table_refs}.")
    if figure_refs:
        parts.append(f"The main text retained the following figures for this stage: {figure_refs}.")
    return " ".join(parts)


def stage_implication_paragraph(bundle: dict, stage_id: str) -> str:
    demonstration = bundle.get("release_quality", {}).get("analysis_release_mode") in {
        "demonstration_only", "simulation_only", "smoke_test_only"
    }
    if demonstration and stage_id in {"primary_model_stage", "sensitivity_stage"}:
        return (
            "This stage verifies that the registered model path and its supporting checks can be reproduced. "
            "Its numerical output has no scientific or decision-making interpretation."
        )
    templates = {
        "qc_stage": "The implication of this stage is that later inference rests on a vetted analytic sample and documented data structure rather than on raw file assumptions.",
        "missingness_stage": "The implication of this stage is that subsequent estimates should be read in light of the observed incompleteness and the adjudicated missing-data path, especially where simplified handling replaced fuller imputation.",
        "descriptive_stage": "The implication of this stage is that baseline composition, imbalance, and distributional form remain visible before multivariable adjustment, helping to anchor later causal or associational interpretation.",
        "bivariate_stage": "The implication of this stage is that exploratory pairwise relationships can motivate later modelling, but they do not override the primary multivariable estimand.",
        "primary_model_stage": "The implication of this stage is that the main inferential claim should be read on the frozen estimand scale and not replaced opportunistically by supportive or exploratory modules.",
        "interaction_stage": "The implication of this stage is that any evidence of effect modification should be read cautiously and alongside sparsity, multiplicity, and design constraints.",
        "dose_response_stage": "The implication of this stage is that trend and non-linearity interpretation must respect the frozen exposure parameterization and any restrictions imposed during adjudication.",
        "sensitivity_stage": "The implication of this stage is that robustness should be judged against the primary model, not by selecting whichever supporting analysis appears most favorable.",
    }
    return templates.get(stage_id, "The implication of this stage should be interpreted together with the frozen evidence objects and adjudicated execution path.")


def diagnostic_paragraph(bundle: dict) -> str:
    diagnostics = bundle["diagnostics"]
    if not diagnostics:
        return "No explicit diagnostic rows were frozen, so interpretation should remain conservative and tied to the executed model family only."
    parts = []
    for row in diagnostics[:6]:
        diagnostic_type = row.get("diagnostic_type", "")
        diagnostic_value = row.get("diagnostic_value")
        if diagnostic_type == "vif_top" and isinstance(diagnostic_value, list):
            ordered = sorted(diagnostic_value, key=lambda item: float(item.get("vif", 0) or 0), reverse=True)
            if ordered:
                max_vif = ordered[0].get("vif")
                terms = ", ".join(f"{item['term']} ({format_scalar(item['vif'])})" for item in ordered[:5])
                parts.append(
                    f"The highest variance inflation factors were modest, with a maximum VIF of {format_scalar(max_vif)}; "
                    f"the leading terms were {terms}. Status: {row.get('status', 'reported')}."
                )
                continue
        parts.append(
            f"{diagnostic_type} was recorded as {format_scalar(diagnostic_value)} "
            f"with status `{row.get('status', 'reported')}`."
        )
    return " ".join(parts) + " These diagnostics bound interpretation and should be read alongside the design and deviation records."


def deviation_paragraph(bundle: dict) -> str:
    decisions = bundle["decisions"]
    deviations = bundle["deviations"]
    execution_state = bundle["execution_state"]
    parts: list[str] = []
    if decisions:
        parts.append("Key analysis decisions included: " + " ".join(item.get("justification", "") for item in decisions[:4] if item.get("justification")))
    if deviations:
        parts.append("Recorded deviations included: " + " ".join(item.get("reason", "") for item in deviations[:4] if item.get("reason")))
    if execution_state.get("degraded_stages"):
        parts.append(
            "The following stages remained degraded at freeze: "
            + ", ".join(f"`{stage}`" for stage in execution_state["degraded_stages"])
            + "."
        )
    if not parts:
        return "No explicit deviation record was frozen; accordingly, the interpretation boundary is driven mainly by the design realization and the executed model family."
    return " ".join(parts)


def discussion_paragraph(bundle: dict) -> str:
    core = bundle["core"]
    results = bundle["results"]
    demonstration = bundle.get("release_quality", {}).get("analysis_release_mode") in {
        "demonstration_only", "simulation_only", "smoke_test_only"
    }
    if demonstration:
        primary_line = (
            "This demonstration verifies data-to-registry-to-report traceability only. "
            "The illustrative coefficients, intervals, and p values do not support a scientific association claim."
        )
    elif results:
        primary = results[0]
        primary_line = (
            f"The leading frozen estimate was {format_scalar(primary.get('estimate'))} on the "
            f"{primary.get('effect_measure', 'target')} scale, with uncertainty bounded by the recorded confidence interval."
        )
    else:
        primary_line = "No primary frozen estimate was available, which pushes this report toward a process-focused rather than effect-focused interpretation."
    design_mode = core.get("design_context", {}).get("design_mode", "sample")
    return (
        primary_line
        + f" More broadly, the analysis package now behaves like an adjudicated execution system rather than a template launcher: "
        f"requested analyses were filtered through executable constraints, design mode `{design_mode}` was preserved into the frozen artifacts, "
        f"and all main-text claims were chained back to result, table, and figure registries. "
        f"Interpretation remains bounded by the cross-sectional design, the adjudicated stage set, and any frozen deviation records."
    )
DEMO_MODES = {"demonstration_only", "simulation_only", "smoke_test_only"}
SCIENCE_MODE = "scientific_release"
SUPPORTED_MODES = DEMO_MODES | {SCIENCE_MODE}
DELIVERY_CLASSES = {"scientific_final", "provisional_blocked_review", "demonstration_only"}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def report_length_metrics(text: str) -> dict[str, int]:
    """Language-aware report depth metrics.

    Chinese/Japanese/Korean prose cannot be adjudicated with an English word
    regex.  Count CJK characters and whitespace-delimited Latin words as
    comparable content units, while excluding Markdown table separators.
    """
    prose = "\n".join(
        line for line in text.splitlines()
        if not re.match(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$", line)
    )
    cjk_characters = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", prose))
    latin_words = len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", prose))
    substantive_paragraphs = sum(
        1 for part in re.split(r"\n\s*\n", prose)
        if len(re.sub(r"[#>*_`|\s-]", "", part)) >= 40
    )
    return {
        "cjk_characters": cjk_characters,
        "latin_words": latin_words,
        "content_units": cjk_characters + latin_words,
        "substantive_paragraphs": substantive_paragraphs,
    }


def repeated_paragraphs(text: str) -> list[str]:
    normalized: dict[str, int] = {}
    for part in re.split(r"\n\s*\n", text):
        clean = re.sub(r"\s+", " ", re.sub(r"[`*_#>|]", "", part)).strip().lower()
        if len(clean) < 120 or clean.startswith("http"):
            continue
        normalized[clean] = normalized.get(clean, 0) + 1
    return [paragraph[:100] for paragraph, count in normalized.items() if count > 1]


def _infer_release_mode(bundle: dict) -> tuple[str, str]:
    state = bundle["execution_state"]
    explicit = str(state.get("analysis_release_mode", "")).strip()
    if explicit in SUPPORTED_MODES:
        return explicit, "explicit execution-state declaration"
    profile = bundle.get("profile", {})
    n_rows = _number(profile.get("n_rows_profiled", profile.get("sample_rows_read")))
    decision_id = str(bundle["core"].get("study_identity", {}).get("decision_id", ""))
    if (n_rows is not None and n_rows < 30) or decision_id in {"", "DECISION_PENDING"}:
        return "demonstration_only", "conservative inference from tiny sample or unresolved decision identity"
    return "unclassified", "no explicit analysis_release_mode was declared"


def _inference_errors(row: dict) -> list[str]:
    """Check that one declared reference distribution generates CI and p value."""
    result_id = row.get("result_id", "UNKNOWN")
    info = row.get("inference_basis")
    if not isinstance(info, dict):
        return [f"{result_id}: missing inference_basis (SE, confidence level, reference distribution, sidedness)"]
    required = ["standard_error", "confidence_level", "reference_distribution", "critical_value", "sidedness"]
    missing = [name for name in required if info.get(name) in {None, ""}]
    if missing:
        return [f"{result_id}: inference_basis missing {missing}"]
    errors: list[str] = []
    reference = str(info.get("reference_distribution", "")).lower()
    p_reference = str(info.get("p_reference_distribution", reference)).lower()
    if p_reference != reference:
        errors.append(
            f"{result_id}: CI uses {reference!r} but p value uses {p_reference!r}"
        )
    if reference in {"t", "student_t"} and _number(info.get("degrees_of_freedom")) is None:
        errors.append(f"{result_id}: t reference distribution requires degrees_of_freedom")
    estimate = _number(row.get("estimate"))
    se = _number(info.get("standard_error"))
    critical = _number(info.get("critical_value"))
    lower = _number(row.get("ci_lower"))
    upper = _number(row.get("ci_upper"))
    transformed = bool(info.get("exponentiated", False))
    if None not in {estimate, se, critical, lower, upper}:
        center = math.log(estimate) if transformed and estimate > 0 else estimate
        expected_lower = center - critical * se
        expected_upper = center + critical * se
        if transformed:
            expected_lower = math.exp(expected_lower)
            expected_upper = math.exp(expected_upper)
        tolerance = max(1e-7, 5e-4 * max(1.0, abs(expected_lower), abs(expected_upper)))
        if abs(lower - expected_lower) > tolerance or abs(upper - expected_upper) > tolerance:
            errors.append(
                f"{result_id}: CI endpoints do not match estimate ± critical_value×SE on the declared scale"
            )
    return errors


def evaluate_report_release(bundle: dict, report_text: str = "", project_root: Path | None = None) -> dict:
    mode, mode_basis = _infer_release_mode(bundle)
    state = bundle["execution_state"]
    delivery_class = str(state.get("report_delivery_class", "")).strip()
    if not delivery_class:
        delivery_class = "demonstration_only" if mode in DEMO_MODES else "scientific_final"
    errors: list[str] = []
    warnings: list[str] = []
    science_errors: list[str] = []
    core = bundle["core"]
    if delivery_class not in DELIVERY_CLASSES:
        errors.append(f"unsupported report_delivery_class: {delivery_class!r}")
    if mode in DEMO_MODES and delivery_class != "demonstration_only":
        errors.append("demonstration analysis_release_mode requires report_delivery_class=demonstration_only")
    if mode == SCIENCE_MODE and delivery_class == "demonstration_only":
        errors.append("real scientific_release cannot be relabelled as demonstration_only")
    design = core.get("design_context", {})
    results = bundle["results"]
    diagnostics = bundle["diagnostics"]
    tables = [row for row in bundle["tables"] if row.get("registry_role") == "main_text"]
    figures = [row for row in bundle["figures"] if row.get("registry_role") == "main_text"]

    if mode == "unclassified":
        errors.append("analysis_release_mode is unclassified; declare scientific_release or demonstration_only")

    for row in results:
        row_errors = _inference_errors(row)
        if mode == SCIENCE_MODE:
            errors.extend(row_errors)
        else:
            warnings.extend(row_errors)
        estimate = _number(row.get("estimate"))
        lower = _number(row.get("ci_lower"))
        upper = _number(row.get("ci_upper"))
        if None not in {estimate, lower, upper} and not lower <= estimate <= upper:
            errors.append(f"{row.get('result_id', 'UNKNOWN')}: estimate is outside its confidence interval")

    searchable_claims = " ".join(
        str(value)
        for row in tables + figures
        for value in (row.get("display_title"), row.get("caption"), row.get("note"), row.get("legend"))
        if value
    ).lower()
    if "weighted" in searchable_claims and (
        design.get("design_mode") == "sample" or not design.get("weight_variable")
    ):
        errors.append("weighted reporting language lacks an executed weight/design path")

    for row in results:
        claim_text = " ".join(str(row.get(key, "")) for key in ("label", "effect_measure")).lower()
        if "adjusted" in claim_text and not row.get("adjustment_set"):
            errors.append(f"{row.get('result_id', 'UNKNOWN')}: adjusted claim lacks a non-empty adjustment_set")
        if "imputed" in claim_text and row.get("pooling_mode") != "mice_pooling":
            errors.append(f"{row.get('result_id', 'UNKNOWN')}: imputed claim lacks pooled-imputation execution evidence")

    if mode == SCIENCE_MODE:
        profile = bundle.get("profile", {})
        if profile.get("profile_scope") != "full_dataset":
            science_errors.append("scientific release requires a full-dataset profile; sampled profiles are exploratory only")
        decision_id = str(core.get("study_identity", {}).get("decision_id", ""))
        if decision_id in {"", "DECISION_PENDING"}:
            science_errors.append("scientific release requires a resolved decision_id")
        adequacy = state.get("inferential_adequacy", {})
        if adequacy.get("status") != "pass":
            science_errors.append("scientific release requires inferential_adequacy.status=pass with rationale")
        if not str(adequacy.get("rationale", "")).strip():
            science_errors.append("inferential adequacy requires a study-specific rationale")

        def meaningful_diagnostic(row: dict) -> bool:
            value = row.get("diagnostic_value")
            name = str(row.get("diagnostic_type", "")).lower()
            if value is None or value == "" or value == []:
                return False
            text = str(value).lower()
            if any(token in text for token in ("not_assessed", "must be assessed", "todo", "pending")):
                return False
            number = _number(value)
            if number is not None and not math.isfinite(number):
                return False
            positive_numeric = {"n_obs", "complete_case_n", "residual_df", "parameter_count", "effective_sample_size"}
            nonnegative_numeric = {"max_leverage", "max_cooks_distance", "overdispersion_ratio", "residual_deviance"}
            if name in positive_numeric and (number is None or number <= 0):
                return False
            if name in nonnegative_numeric and (number is None or number < 0):
                return False
            return str(row.get("status", "reported")).lower() not in {"fail", "failed", "missing"}

        diagnostic_types = {
            str(row.get("diagnostic_type", "")).lower()
            for row in diagnostics
            if meaningful_diagnostic(row)
        }
        diagnostic_groups = {
            "sample_df": {"n_obs", "complete_case_n", "residual_df", "parameter_count", "effective_sample_size"},
            "fit": {"convergence", "rank", "singularity", "runtime_warnings"},
            "residual": {"residual_summary", "overdispersion_ratio", "residual_deviance", "boundary_check"},
            "influence": {"max_leverage", "max_cooks_distance", "influence_summary"},
            "form": {"functional_form", "nonlinearity_test", "link_test", "prediction_range"},
        }
        for group, alternatives in diagnostic_groups.items():
            if not diagnostic_types.intersection(alternatives):
                science_errors.append(f"diagnostic evidence is missing group {group}: one of {sorted(alternatives)}")

        axes = {str(item).strip() for item in state.get("sensitivity_axes", []) if str(item).strip()}
        axes.update(
            str(row.get("sensitivity_axis", "")).strip()
            for row in results
            if row.get("stage_id") == "sensitivity_stage" and str(row.get("sensitivity_axis", "")).strip()
        )
        justified_absences = state.get("sensitivity_not_applicable", [])
        if len(axes) + len(justified_absences) < 3:
            science_errors.append("fewer than three sensitivity axes or explicit not-applicable justifications")
        if len(tables) < 6:
            science_errors.append(f"scientific report has {len(tables)} main-text tables; require at least 6 or explicit release exception")
        if len(figures) < 3:
            science_errors.append(f"scientific report has {len(figures)} main-text figures; require at least 3 or explicit release exception")

        if report_text:
            metrics = report_length_metrics(report_text)
            if metrics["content_units"] < 4000 or metrics["substantive_paragraphs"] < 12:
                science_errors.append(
                    "scientific report body is below the language-aware hard floor: "
                    f"{metrics['content_units']} language-aware content units and "
                    f"{metrics['substantive_paragraphs']} substantive paragraphs; "
                    "require at least 4000 units and 12 substantive paragraphs"
                )
            duplicates = repeated_paragraphs(report_text)
            if duplicates:
                science_errors.append("scientific report contains repeated substantive paragraphs")
            if "DEMONSTRATION ONLY" in report_text:
                science_errors.append("scientific report contains a demonstration-only label")
            embedded_tables = len(re.findall(r"^\|.+\|$", report_text, flags=re.MULTILINE))
            if embedded_tables == 0:
                science_errors.append("report lists tables but embeds no numerical Markdown table")
    elif report_text:
        if "DEMONSTRATION ONLY — NOT FOR SCIENTIFIC INFERENCE" not in report_text:
            errors.append("demonstration report lacks the required non-inference banner")
        prohibited = re.findall(
            r"\b(confirmatory|definitive|scientifically conclusive)\b|as an inferential object|main inferential claim|primary inferential object",
            report_text,
            flags=re.I,
        )
        if prohibited:
            errors.append(f"demonstration report uses research-grade claim terms: {sorted(set(item.lower() for item in prohibited))}")

    blockers: list[str] = []
    if mode == SCIENCE_MODE and delivery_class == "provisional_blocked_review":
        blockers = science_errors
        if report_text and not (
            "PROVISIONAL" in report_text.upper()
            and "NOT FOR FINAL SCIENTIFIC INFERENCE" in report_text.upper()
        ):
            errors.append("provisional report lacks the required final-inference blocker banner")
    else:
        errors.extend(science_errors)
    if errors:
        status = "fail"
    elif delivery_class == "provisional_blocked_review":
        status = "provisional_pass"
    elif mode in DEMO_MODES:
        status = "demonstration_pass"
    else:
        status = "scientific_pass"
    return {
        "generated_at": now_iso(),
        "analysis_release_mode": mode,
        "mode_basis": mode_basis,
        "report_delivery_class": delivery_class,
        "status": status,
        "errors": errors,
        "release_blockers": blockers,
        "warnings": warnings,
        "scientific_release_requirements": science_errors,
        "counts": {
            "results": len(results),
            "diagnostics": len(diagnostics),
            "main_text_tables": len(tables),
            "main_text_figures": len(figures),
            **(report_length_metrics(report_text) if report_text else {}),
        },
    }


def write_release_audit(project_root: Path, bundle: dict, report_text: str = "") -> dict:
    payload = evaluate_report_release(bundle, report_text, project_root=project_root)
    write_json(project_root / "analysis" / "output" / "report_release_quality_audit.json", payload)
    return payload

# render_report


def markdown_csv(path: Path, max_rows: int = 30) -> list[str]:
    """Embed a registered CSV as a Markdown table rather than a title-only promise."""
    if not path.exists() or path.suffix.lower() != ".csv":
        return [f"Registered table source unavailable: `{path}`."]
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return ["Registered table contains no rows."]
    width = max(len(row) for row in rows)
    clean = lambda value: str(value).replace("|", "\\|").replace("\n", " ").strip()
    padded = [[clean(value) for value in row] + [""] * (width - len(row)) for row in rows[: max_rows + 1]]
    output = ["| " + " | ".join(padded[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    output.extend("| " + " | ".join(row) + " |" for row in padded[1:])
    if len(rows) > max_rows + 1:
        output.append(f"\n*Display truncated after {max_rows} data rows; the frozen source retains all rows.*")
    return output


def main_render_report() -> None:
    parser = argparse.ArgumentParser(description="Render a long-form, registry-first statistical analysis report markdown.")
    parser.add_argument("project_root")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    bundle = load_report_bundle(project_root)
    freeze_manifest = bundle["freeze"]
    if not freeze_manifest or freeze_manifest.get("status") != "ready":
        raise SystemExit("Cannot render report before registry freeze passes.")

    preflight = write_release_audit(project_root, bundle)
    if preflight.get("status") == "fail":
        raise SystemExit("Report release-quality preflight failed: " + "; ".join(preflight.get("errors", [])))
    bundle["release_quality"] = preflight
    demonstration = preflight.get("analysis_release_mode") in DEMO_MODES
    provisional = preflight.get("status") == "provisional_pass"

    core = bundle["core"]
    title = core.get("study_identity", {}).get("study_title", "Statistical analysis report")
    results = bundle["results"]
    tables = bundle["tables"]
    figures = bundle["figures"]
    table_counter = 1
    figure_counter = 1

    lines = [
        f"# {title}",
        "",
    ]
    if demonstration:
        lines.extend(
            [
                "> **DEMONSTRATION ONLY — NOT FOR SCIENTIFIC INFERENCE**",
                "> This small or unresolved example verifies workflow behavior. Its numerical outputs must not be used as study findings, evidence, or decisions.",
                "",
            ]
        )
    elif provisional:
        lines.extend([
            "> **PROVISIONAL — NOT FOR FINAL SCIENTIFIC INFERENCE**",
            "> This is a real-data review report. Final inference remains blocked by the release conditions listed below.",
            "",
            "Release blockers:",
            "",
        ])
        lines.extend(f"- {item}" for item in preflight.get("release_blockers", []))
        lines.append("")
    lines.extend([
        "## Study Type",
        "",
        ("This demonstration report documents contract, execution, registry, and rendering behavior. "
         "Numbers are shown only as traceable pipeline artifacts and have no scientific interpretation."
         if demonstration else
         "This cross-sectional statistical analysis report summarizes the prespecified objectives, realized analyses, diagnostics, and interpretation boundaries. All quantitative statements are tied to audited and frozen evidence objects."),
        "",
        "## Executive Summary",
        "",
        executive_summary_paragraph(bundle),
        "",
        "## Study Purpose",
        "",
        study_purpose_paragraph(bundle),
        "",
        "## Main Methods",
        "",
        main_methods_paragraph(bundle),
        "",
        "## Expected Analysis Content",
        "",
        expected_analysis_content_paragraph(bundle),
        "",
    ])

    summary_bullets = [
        f"Decision ID: `{core.get('study_identity', {}).get('decision_id', 'DECISION_PENDING')}`.",
        f"Primary estimand family: `{core.get('estimand_family', '')}`.",
        f"Main frozen evidence objects: {len(tables)} tables and {len(figures)} figures.",
    ]
    if results:
        summary_bullets.extend(result_sentence(row, demonstration=demonstration) for row in results[: min(4, len(results))])
    lines.extend(f"- {item}" for item in summary_bullets)

    lines.extend(
        [
            "",
            "## Analytic Sample And Realized Design",
            "",
            design_summary_paragraph(bundle),
            "",
            "## Requested, Executable, And Executed Scope",
            "",
            "The report distinguishes what was originally requested, what the available data and design would support, "
            "and what was ultimately executed and frozen. These distinctions preserve the prespecified estimand while making "
            "method changes, unavailable analyses, and data-driven feasibility constraints transparent.",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in objective_scope_lines(bundle))

    lines.extend(
        [
            "",
            "## Missing-data Policy And Observed Completeness",
            "",
            f"The requested missing-data strategy was `{core.get('missing_data_policy', {}).get('requested_strategy', 'Not specified')}`. "
            "Observed missingness was profiled before any model execution and was used to determine whether complete-case analysis, imputation, "
            "or sensitivity-only handling was defensible within the current execution contract.",
            "",
        ]
    )
    observed_missingness = core.get("missing_data_policy", {}).get("observed_missingness", {})
    if observed_missingness:
        for variable, meta in list(observed_missingness.items())[:10]:
            lines.append(f"- `{variable}`: {meta.get('n_missing', 0)} missing ({meta.get('pct_missing', 0)}%).")

    lines.extend(["", "## Staged Analysis Narrative", ""])
    for stage in STAGE_ORDER:
        if stage in {"registry_finalize_stage", "report_stage"}:
            continue
        stage_paragraphs = bundle["stage_contracts"].get(stage) or [
            {}
        ]
        stage_results = [row for row in results if row.get("stage_id") == stage]
        stage_tables = [row for row in tables if row.get("stage_id") == stage]
        stage_figures = [row for row in figures if row.get("stage_id") == stage]
        if not stage_results and not stage_tables and not stage_figures and not bundle["stage_contracts"].get(stage):
            continue
        lines.extend([f"### {STAGE_LABELS.get(stage, stage)}", ""])
        lines.append("**Overview.** " + stage_overview_paragraph(bundle, stage))
        lines.append("")
        lines.append("**Findings.** " + stage_findings_paragraph(bundle, stage))
        lines.append("")
        lines.append("**Analytical implications.** " + stage_implication_paragraph(bundle, stage))
        if stage_tables:
            lines.append("")
            lines.append("Frozen tables for this stage:")
            lines.append("")
            for item in stage_tables:
                lines.append(f"- Table {table_counter}. {item.get('caption') or item.get('display_title') or item.get('title', 'Table')}")
                if item.get("note"):
                    lines.append(f"  Note: {item.get('note')}")
                lines.append("")
                lines.extend(markdown_csv(Path(item.get("source_path", ""))))
                table_counter += 1
        if stage_figures:
            lines.append("")
            lines.append("Frozen figures for this stage:")
            lines.append("")
            for item in stage_figures:
                lines.append(f"- Figure {figure_counter}. {item.get('caption') or item.get('display_title') or item.get('title', 'Figure')}")
                if item.get("legend"):
                    lines.append(f"  Legend: {item.get('legend')}")
                source = Path(item.get("source_path", ""))
                if source.exists():
                    lines.append(f"  ![{item.get('display_title') or item.get('title', 'Figure')}]({source.as_posix()})")
                figure_counter += 1
        lines.append("")

    lines.extend(
        [
            "## Primary Association Model",
            "",
            ("The primary-model section verifies model-to-registry traceability only; its illustrative values do not estimate a release-eligible scientific effect."
             if demonstration else
             "This provisional section preserves traceability for supported real-data descriptions while final inferential claims remain blocked."
             if provisional else
             "Primary effect interpretation must follow the estimand and design path frozen in the core contract. The main model is therefore read as the primary inferential object, while any extended modules remain subordinate and cannot replace the primary estimand without explicit justification."),
            "",
        ]
    )
    primary_results = [row for row in results if row.get("stage_id") == "primary_model_stage"]
    if primary_results:
        lines.extend(f"- {result_sentence(row, demonstration=demonstration)}" for row in primary_results[:6])

    lines.extend(
        [
            "",
            "## Design-Aware Sensitivity Analysis",
            "",
            "Sensitivity analysis is interpreted as a design- and assumption-stress test rather than as an opportunity to replace the main model opportunistically. "
            "Any degraded stages or alternate paths are retained explicitly so that robustness can be judged against the requested plan rather than inferred informally.",
            "",
        ]
    )
    sensitivity_results = [row for row in results if row.get("stage_id") == "sensitivity_stage"]
    if sensitivity_results:
        lines.extend(f"- {result_sentence(row, demonstration=demonstration)}" for row in sensitivity_results[:6])
    else:
        lines.append("- No sensitivity result rows were frozen into the main-text registry.")

    lines.extend(
        [
            "",
            "## Diagnostics And Interpretation Boundaries",
            "",
            diagnostic_paragraph(bundle),
            "",
            "The interpretation boundary is defined by the realized design, executed model family, registered diagnostics, and recorded deviations.",
            "",
            "Interpretation is further bounded by the cross-sectional design itself: associations may be estimated precisely, but temporality, mechanism, and transportability remain constrained by the design context, the executed stage set, and any deviations recorded before freeze.",
            "",
            "## Decisions And Deviations",
            "",
            deviation_paragraph(bundle),
            "",
            "## Discussion",
            "",
            discussion_paragraph(bundle),
            "",
            "## Conclusion",
            "",
            ("This demonstration establishes only that the declared pipeline can produce traceable artifacts; it supports no scientific conclusion."
             if demonstration else
             "The reported estimates must be interpreted within the cross-sectional design, the realized analytic sample, the recorded diagnostics and deviations, and the uncertainty shown in the frozen result registry."),
            "",
            "## Frozen Evidence Objects",
            "",
            f"- Freeze version: `{freeze_manifest.get('freeze_version', '')}`",
            f"- Analysis consistency audit: `{bundle['analysis_audit'].get('status', 'missing')}`",
            f"- Design consistency audit: `{bundle['design_audit'].get('status', 'missing')}`",
            f"- Tables frozen: {len(tables)}",
            f"- Figures frozen: {len(figures)}",
        ]
    )

    output = Path(args.output) if args.output else project_root / "analysis" / "output" / "report" / "statistical_analysis_report.md"
    report_text = "\n".join(lines)
    postflight = write_release_audit(project_root, bundle, report_text)
    if postflight.get("status") == "fail":
        raise SystemExit("Rendered report failed release-quality audit: " + "; ".join(postflight.get("errors", [])))
    write_text(output, report_text)

# build_report_docx
TEXT = RGBColor(0, 0, 0)
MUTED = RGBColor(70, 70, 70)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def set_default_font(doc: Document) -> None:
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.font.color.rgb = TEXT
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.35

    for style_name, size in [("Title", 16), ("Heading 1", 12), ("Heading 2", 11.5), ("Heading 3", 11)]:
        style = styles[style_name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = TEXT
        style.paragraph_format.space_before = Pt(8)
        style.paragraph_format.space_after = Pt(3)
        style.paragraph_format.line_spacing = 1.15

    styles["Normal Table"].font.name = "Times New Roman"
    styles["Normal Table"].font.size = Pt(10.5)


def set_document_layout(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)


def add_page_number(section) -> None:
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr)
    run._r.append(fld_char2)
    run.font.name = "Times New Roman"
    run.font.size = Pt(10)
    run.font.color.rgb = MUTED


def add_paragraph(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(plain_text(text))
    run.font.name = "Times New Roman"
    run.font.size = Pt(12)
    run.font.color.rgb = TEXT


def add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        run = p.add_run(plain_text(item))
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)
        run.font.color.rgb = TEXT


def set_cell_text(cell, text: str, bold: bool = False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(str(text))
    run.bold = bold
    run.font.name = "Times New Roman"
    run.font.size = Pt(10.5)


def clear_table_borders(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        edge = borders.find(qn(f"w:{side}"))
        if edge is None:
            edge = OxmlElement(f"w:{side}")
            borders.append(edge)
        edge.set(qn("w:val"), "nil")


def set_cell_border(cell, **kwargs) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_borders = tc_pr.first_child_found_in("w:tcBorders")
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge_name, edge_data in kwargs.items():
        tag = f"w:{edge_name}"
        element = tc_borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            tc_borders.append(element)
        for key, value in edge_data.items():
            element.set(qn(f"w:{key}"), str(value))


def apply_three_line_style(table) -> None:
    clear_table_borders(table)
    border = {"val": "single", "sz": 10, "space": 0, "color": "000000"}
    for cell in table.rows[0].cells:
        set_cell_border(cell, top=border, bottom=border)
    for cell in table.rows[-1].cells:
        set_cell_border(cell, bottom=border)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER


def prettify_stem(stem: str) -> str:
    return stem.replace("_", " ").replace("Table ", "").replace("Figure ", "").strip()


def sort_items(items: list[dict], id_key: str) -> list[dict]:
    stage_rank = {stage: idx for idx, stage in enumerate(STAGE_ORDER)}
    role_rank = {"main_text": 0, "supplement": 1, "report_only": 2}
    return sorted(
        items,
        key=lambda item: (
            stage_rank.get(item.get("stage_id", ""), 999),
            role_rank.get(item.get("registry_role", "supplement"), 9),
            item.get(id_key, ""),
        ),
    )


def add_csv_table(doc: Document, csv_path: Path, caption: str) -> None:
    rows = read_csv(csv_path)
    if not rows:
        return
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cap.add_run(plain_text(caption))
    run.bold = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(11)

    headers = list(rows[0].keys())
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = True
    for idx, header in enumerate(headers):
        set_cell_text(table.rows[0].cells[idx], header, bold=True)
    for row in rows:
        cells = table.add_row().cells
        for idx, header in enumerate(headers):
            set_cell_text(cells[idx], row.get(header, ""))
    apply_three_line_style(table)


def add_table_note(doc: Document, note: str) -> None:
    if not note:
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(f"Note. {plain_text(note)}")
    run.italic = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(10)
    run.font.color.rgb = MUTED


def add_figure(doc: Document, path: Path, caption: str, width: float = 5.8) -> None:
    if not path.exists():
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cap.add_run(plain_text(caption))
    run.italic = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(10.5)


def add_figure_legend(doc: Document, legend: str) -> None:
    if not legend:
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(f"Legend. {plain_text(legend)}")
    run.font.name = "Times New Roman"
    run.font.size = Pt(10)
    run.font.color.rgb = MUTED


def objective_summary_lines(objective_map: list[dict]) -> list[str]:
    lines: list[str] = []
    for row in objective_map:
        lines.append(
            f"{row.get('objective_id', '')}: requested `{row.get('requested_status', '')}`, "
            f"executable `{row.get('executable_status', '')}`, executed `{row.get('executed_status', '')}`. "
            f"{row.get('final_reason', '')}"
        )
    return lines


def result_summary_lines(results: list[dict]) -> list[str]:
    lines: list[str] = []
    for row in results:
        est = row.get("estimate", "NA")
        ci_lo = row.get("ci_lower", "NA")
        ci_hi = row.get("ci_upper", "NA")
        p = row.get("p_value", "NA")
        lines.append(
            f"{row.get('label', row.get('result_id', 'result'))} ({row.get('effect_measure', '')}) = "
            f"{est}; 95% CI {ci_lo} to {ci_hi}; p = {p}."
        )
    return lines


def export_pdf(docx_path: Path, output_dir: Path) -> Path:
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(docx_path)],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return pdf_path

    pandoc = shutil.which("pandoc")
    if pandoc:
        result = subprocess.run(
            [pandoc, str(docx_path), "-o", str(pdf_path), "--pdf-engine=xelatex"],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return pdf_path

    raise SystemExit("PDF export requires a working soffice/libreoffice or pandoc+xelatex installation.")


def main_build_report_docx() -> None:
    parser = argparse.ArgumentParser(description="Build a formal statistical analysis report DOCX from the current registry-first analysis bundle.")
    parser.add_argument("project_root")
    parser.add_argument("--output", default="")
    parser.add_argument("--export-pdf", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root)
    bundle = load_report_bundle(root)
    freeze = bundle["freeze"]
    if not freeze or freeze.get("status") != "ready":
        raise SystemExit("Cannot build DOCX before registry freeze is ready.")
    markdown_path = root / "analysis" / "output" / "report" / "statistical_analysis_report.md"
    report_text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    release_quality = write_release_audit(root, bundle, report_text)
    if release_quality.get("status") == "fail":
        raise SystemExit("Cannot build DOCX because release-quality audit failed: " + "; ".join(release_quality.get("errors", [])))
    bundle["release_quality"] = release_quality
    demonstration = release_quality.get("analysis_release_mode") in DEMO_MODES
    provisional = release_quality.get("status") == "provisional_pass"

    core = bundle["core"]
    executable_plan = bundle["executable_plan"]
    execution_state = bundle["execution_state"]
    analysis_audit = bundle["analysis_audit"]
    design_audit = bundle["design_audit"]
    diagnostics = bundle["diagnostics"]
    decisions = bundle["decisions"]
    deviations = bundle["deviations"]
    results = bundle["results"]
    tables = bundle["tables"]
    figures = bundle["figures"]
    table_counter = 1
    figure_counter = 1
    table_numbers = display_number_map(bundle, "table")
    figure_numbers = display_number_map(bundle, "figure")

    doc = Document()
    set_default_font(doc)
    set_document_layout(doc)
    add_page_number(doc.sections[0])

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(core.get("study_identity", {}).get("study_title", "Statistical Analysis Report"))
    run.bold = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(16)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("Statistical Analysis Report")
    run.font.name = "Times New Roman"
    run.font.size = Pt(11)
    run.font.color.rgb = MUTED

    if demonstration:
        banner = doc.add_paragraph()
        banner.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = banner.add_run("DEMONSTRATION ONLY — NOT FOR SCIENTIFIC INFERENCE")
        run.bold = True
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)
    elif provisional:
        banner = doc.add_paragraph()
        banner.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = banner.add_run("PROVISIONAL — NOT FOR FINAL SCIENTIFIC INFERENCE")
        run.bold = True
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)
        add_paragraph(doc, "Final-inference blockers: " + "; ".join(release_quality.get("release_blockers", [])))

    doc.add_heading("Study Type", level=1)
    add_paragraph(
        doc,
        ("This pipeline demonstration contains illustrative, traceable numbers only and supports no scientific association claim."
         if demonstration else
         "This real-data review artifact reports only the scope supported by the current design and feasibility evidence; final scientific inference remains blocked."
         if provisional else
         "This cross-sectional analytical report summarizes the prespecified objectives, realized analyses, diagnostics, and interpretation boundaries. Quantitative statements are tied to audited and frozen evidence objects.")
    )

    doc.add_heading("Executive Summary", level=1)
    add_paragraph(doc, executive_summary_paragraph(bundle))

    doc.add_heading("Study Purpose", level=1)
    add_paragraph(doc, study_purpose_paragraph(bundle))

    doc.add_heading("Main Methods", level=1)
    add_paragraph(doc, main_methods_paragraph(bundle))

    doc.add_heading("Expected Analysis Content", level=1)
    add_paragraph(doc, expected_analysis_content_paragraph(bundle))

    doc.add_heading("Requested, Executable, And Executed Analysis Scope", level=1)
    add_bullets(doc, objective_summary_lines(executable_plan.get("objective_execution_map", [])))

    doc.add_heading("Analytic Sample And Realized Design", level=1)
    add_paragraph(doc, design_summary_paragraph(bundle))

    doc.add_heading("Missingness And Data Handling", level=1)
    missing_policy = core.get("missing_data_policy", {})
    add_paragraph(
        doc,
        f"Requested missing-data strategy: {missing_policy.get('requested_strategy', 'Not specified')}. "
        "Observed missingness was profiled before any main model execution and used to justify whether complete-case handling, imputation, or sensitivity-only handling remained compatible with the frozen contract."
    )
    missingness_rows = []
    for variable, meta in missing_policy.get("observed_missingness", {}).items():
        missingness_rows.append(f"{variable}: {meta.get('n_missing', 0)} missing ({meta.get('pct_missing', 0)}%)")
    if missingness_rows:
        add_bullets(doc, missingness_rows[:10])

    for stage in STAGE_ORDER:
        if stage in {"registry_finalize_stage", "report_stage"}:
            continue
        stage_tables = [item for item in tables if item.get("stage_id") == stage]
        stage_figures = [item for item in figures if item.get("stage_id") == stage]
        if not stage_tables and not stage_figures and not any(item.get("stage_id") == stage for item in results) and stage not in bundle["stage_contracts"]:
            continue
        doc.add_heading(STAGE_LABELS.get(stage, stage), level=1)
        add_paragraph(doc, "Overview. " + stage_overview_paragraph(bundle, stage))
        add_paragraph(doc, "Findings. " + stage_findings_paragraph(bundle, stage))
        add_paragraph(doc, "Analytical implications. " + stage_implication_paragraph(bundle, stage))
        for item in stage_tables:
            table_counter = table_numbers.get(item["table_id"], table_counter)
            add_csv_table(
                doc,
                Path(item["source_path"]),
                f"Table {table_counter}. {item.get('caption') or item.get('display_title') or prettify_stem(item.get('title', 'Table'))}",
            )
            add_table_note(doc, item.get("note", ""))
        for item in stage_figures:
            figure_counter = figure_numbers.get(item["figure_id"], figure_counter)
            add_figure(
                doc,
                Path(item["source_path"]),
                f"Figure {figure_counter}. {item.get('caption') or item.get('display_title') or prettify_stem(item.get('title', 'Figure'))}",
            )
            add_figure_legend(doc, item.get("legend", ""))

    doc.add_heading("Diagnostics", level=1)
    add_paragraph(doc, diagnostic_paragraph(bundle))
    add_paragraph(
        doc,
        "The interpretation boundary is defined by the realized design, executed model family, registered diagnostics, and recorded deviations.",
    )
    add_bullets(
        doc,
        [
            f"Analysis consistency audit: `{analysis_audit.get('status', 'missing')}`.",
            f"Design consistency audit: `{design_audit.get('status', 'missing')}`.",
            f"Freeze version: `{freeze.get('freeze_version', '')}`.",
        ],
    )

    doc.add_heading("Decisions, Deviations, And Interpretation Boundary", level=1)
    add_paragraph(doc, deviation_paragraph(bundle))
    if decisions:
        add_bullets(doc, [item.get("justification", "") for item in decisions[:6] if item.get("justification")])
    if deviations:
        add_bullets(doc, [item.get("reason", "") for item in deviations[:6] if item.get("reason")])
    if execution_state.get("degraded_stages"):
        add_bullets(doc, [f"Degraded stage: `{stage}`" for stage in execution_state["degraded_stages"]])

    doc.add_heading("Discussion", level=1)
    add_paragraph(doc, discussion_paragraph(bundle))

    doc.add_heading("Conclusion", level=1)
    add_paragraph(
        doc,
        ("This demonstration establishes workflow traceability only and supports no scientific conclusion."
         if demonstration else
         "The reported estimates must be interpreted within the cross-sectional design, the realized analytic sample, the recorded diagnostics and deviations, and the uncertainty shown in the frozen result registry.")
    )

    output = Path(args.output) if args.output else root / "analysis" / "output" / "report" / "statistical_analysis_report.docx"
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    if args.export_pdf:
        export_pdf(output, output.parent)


COMMANDS = {
    "render_report": main_render_report,
    "build_report_docx": main_build_report_docx,
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
