#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/design_documents.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from design_common import (
    bullet_lines,
    build_dag_mermaid,
    front_matter,
    load_json,
    load_bound_execution_spec,
    markdown_table,
    numbered_lines,
    sorted_objectives,
    write_text,
)

# write_protocol_document


def required(mapping: dict, key: str, label: str) -> str:
    value = mapping.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return f"[REQUIRES SPECIFICATION: {label}]"


def validate_blueprint_bindings(intake: dict, core: dict, editorial: dict, document_text: str) -> None:
    """Make the blueprint argument a real writer contract rather than dead input."""
    core_chapters = {str(row.get("chapter_id")): row for row in core.get("chapters", [])}
    editorial_chapters = {str(row.get("chapter_id")): row for row in editorial.get("chapters", [])}
    if not core_chapters or set(core_chapters) != set(editorial_chapters):
        raise SystemExit("Protocol blueprint core/editorial chapter bindings are missing or drifted.")
    objective_ids = {str(row.get("objective_id")) for row in intake.get("study_objectives", [])}
    linked_ids = {
        str(value)
        for row in core_chapters.values()
        for value in row.get("objective_links", [])
    }
    unknown = sorted(linked_ids - objective_ids)
    if unknown:
        raise SystemExit(f"Protocol blueprint contains unknown objective links: {unknown}")
    stat_links = {str(value) for value in core_chapters.get("stat_methods", {}).get("objective_links", [])}
    missing = sorted(objective_ids - stat_links)
    if missing:
        raise SystemExit(f"Statistical-methods blueprint omits objectives: {missing}")
    if str(intake.get("project_mode", "")) == "research":
        forbidden = [str(value) for value in editorial.get("global_forbidden_phrases", []) if str(value)]
        leaked = sorted(value for value in forbidden if value.lower() in document_text.lower())
        if leaked:
            raise SystemExit(f"Research protocol contains blueprint-forbidden writer language: {leaked}")


def build_document_status(intake: dict) -> list[str]:
    profile = intake.get("document_profile", {})
    operations = intake.get("protocol_operations", {})
    rows = []
    for item in operations.get("amendment_history", []):
        rows.append([
            str(item.get("version", "")),
            str(item.get("date", "")),
            str(item.get("change", "")),
            str(item.get("rationale", "")),
            str(item.get("approval", "")),
        ])
    if not rows:
        rows = [["[REQUIRES SPECIFICATION: version]", "[REQUIRES SPECIFICATION: date]", "Initial protocol", "Initial issue", "[REQUIRES SPECIFICATION: approval]"]]
    lines = [
        "## Document Status, Responsibilities, and Change Control",
        "",
        (
            f"This document is {required(operations, 'study_status', 'current study status and recruitment state')}. "
            f"It governs the protocol version identified as {required(profile, 'protocol_version', 'protocol version')} and is paired with "
            f"{required(operations, 'sap_version', 'matching SAP version')}. No empirical participant result or field authorization is reported."
        ),
        "",
        (
            f"Scientific responsibility rests with {required(operations, 'scientific_owner', 'scientific owner and role')}; "
            f"statistical responsibility rests with {required(operations, 'statistical_owner', 'statistical owner and role')}; and "
            f"data-custody responsibility rests with {required(operations, 'data_owner', 'data custodian and role')}. "
            f"The protocol freeze occurs {required(operations, 'freeze_rule', 'protocol freeze rule')}."
        ),
        "",
        "### Version and amendment history",
        "",
    ]
    lines.extend(markdown_table(["Version", "Date", "Change", "Rationale", "Approval"], rows))
    lines.extend([
        "",
        (
            "Any post-freeze amendment must identify the affected objective, estimand, population, measurement, sample-size basis, or analysis commitment; "
            "state whether investigators had access to outcome distributions; and receive approval before the amended procedure is used. Editorial corrections "
            "that cannot change analysis are logged separately from substantive amendments."
        ),
        "",
    ])
    return lines


def build_evidence_map(intake: dict) -> list[str]:
    evidence = intake.get("evidence_basis", {})
    claims = evidence.get("claim_evidence_map", [])
    rows = []
    for item in claims:
        rows.append([
            str(item.get("claim", "")),
            ", ".join(str(x) for x in item.get("citations", [])),
            str(item.get("design_consequence", "")),
        ])
    if not rows:
        rows = [[
            "[REQUIRES SPECIFICATION: claim supported by evidence]",
            "[REQUIRES SPECIFICATION: citation identifiers]",
            "[REQUIRES SPECIFICATION: protocol consequence]",
        ]]
    lines = [
        "### 2.3 Evidence-to-design map",
        "",
        (
            "The protocol uses references as decision evidence rather than decoration. Each claim below is linked to a design consequence; a source that does not "
            "alter the objective, measurement, bias strategy, analysis, or interpretation is not treated as sufficient justification for a commitment."
        ),
        "",
    ]
    lines.extend(markdown_table(["Claim", "Evidence", "Design consequence"], rows))
    lines.append("")
    return lines


def build_sampling_operations(intake: dict) -> list[str]:
    spec = intake.get("_execution_spec", {})
    if spec:
        s = spec["sampling"]
        rows = [[x["ward"], str(x["psu_count"]), str(x["households_per_psu"]), str(x["psu_count"] * x["households_per_psu"])] for x in s["ward_allocation"]]
        lines = [
            "### 3.4 Executable sampling annex and probability trail",
            "",
            f"The sampling-annex state is **{s['restricted_annex']}**. Its demonstration frame date is **{s['frame_reference_date']}** and scope is {s['frame_scope']}. Synthetic execution uses seed **{s['seed']}** and {s['script']}. No real selection is authorized; a verified real annex and script manifest would be mandatory.",
            "",
        ]
        lines.extend(markdown_table(["Ward", "PSUs", "Households/PSU", "Selected households"], rows))
        lines.extend([
            "",
            f"**PSU selection.** {s['pps_method']} The exact equation is `{s['pps_equation']}`.",
            "",
            f"**Household selection.** {s['household_method']}",
            "",
            f"**Adult selection.** {s['adult_method']}",
            "",
            f"The inclusion-probability identity is `{s['base_probability']}`. {s['worked_probability']}",
            "",
            f"**Household nonresponse.** {s['household_nonresponse']}",
            "",
            f"**Selected-adult completion nonresponse.** {s['person_nonresponse']}",
            "",
            f"**Adult-person calibration.** {s['calibration']}",
            "",
            f"**Cut points and ties.** {s['quantile_rule']}",
            "",
            f"**Spline knots.** {s['spline_quantile_rule']}",
            "",
            f"**Trimming and margin restoration.** {s['trimming']}",
            "",
            f"**Variance representation and FPC.** {s['fpc']} Exact primary constructor: `{s['primary_design_call']}`.",
            "",
            f"Lonely PSUs use `{s['lonely_psu']}`. Degrees of freedom are `{s['degrees_of_freedom']}`.",
            "",
            "No household margin is mixed into the adult-person calibration target. Variables used for household response are frame-known for every sampled household; age and frame sex enter only after an eligible adult roster exists. This preserves the estimator's unit and target population.",
            "",
        ])
        return lines
    sampling = intake.get("protocol_operations", {}).get("sampling", {})
    selection = sampling.get("selection_steps", [])
    lines = [
        "### 3.4 Sampling implementation and probability trail",
        "",
        (
            f"The operational frame is {required(sampling, 'frame_definition', 'frame composition, reference date, and deduplication rule')}. "
            f"Frame coverage will be assessed by {required(sampling, 'coverage_check', 'frame coverage check and acceptance rule')}. "
            f"The selection unit sequence is {required(sampling, 'unit_sequence', 'sampling stages and units')}."
        ),
        "",
        "Selection will proceed in this frozen order:",
        "",
    ]
    lines.extend(numbered_lines(selection or ["[REQUIRES SPECIFICATION: reproducible random-selection steps]"]))
    lines.extend([
        "",
        (
            f"The base weight is calculated as {required(sampling, 'base_weight_formula', 'base-weight formula from inclusion probabilities')}. "
            f"Non-response adjustment is {required(sampling, 'non_response_adjustment', 'non-response cells/model and factor formula')}. "
            f"Calibration is {required(sampling, 'calibration', 'calibration margins and method')}; extreme weights are handled by "
            f"{required(sampling, 'weight_trimming', 'weight trimming rule and redistribution')}."
        ),
        "",
        (
            f"Contact attempts follow {required(sampling, 'contact_protocol', 'number, timing, and mode of contact attempts')}. "
            f"Replacement is governed by {required(sampling, 'replacement_rule', 'replacement prohibition or exact rule')}. "
            f"Field disposition codes follow {required(sampling, 'disposition_codes', 'response and non-response disposition taxonomy')}. "
            "The final flow table will reconcile frame records, sampled units, eligible units, consented participants, measurement completion, and each analysis population."
        ),
        "",
        (
            "Sampling is not separated from inference. Primary population estimates must use the frozen design variables and final weights; unweighted counts are retained "
            "for transparent flow accounting. Analyses that omit a design component must be labelled sensitivity analyses and cannot silently replace the population-targeted result."
        ),
        "",
    ])
    return lines


def build_measurement_operations(intake: dict) -> list[str]:
    spec = intake.get("_execution_spec", {})
    if spec:
        m = spec["measurement"]
        lines = [
            "### 5.5 Frozen primary measurement and derivation synopsis",
            "",
            f"The hash-bound source is **{m['dictionary']}**. Dietary coding uses {m['dietary_manual']}. {m['phq9']} {m['ipaq']}",
            "",
            f"**Dietary energy and NOVA equation.** {m['dietary_algorithm']}",
            "",
            f"**Recall validity and scheduling.** {m['recall_validity']}",
            "",
            f"**Energy plausibility and within-person error.** {m['energy_flags']}",
            "",
            f"**Exposure cut points.** {m['quartiles']}",
            "",
            f"**Anthropometry.** {m['anthropometry']}",
            "",
            f"**Categorical variables.** {m['categorical_mappings']}",
            "",
            f"**Conditioning-set boundary.** {m['conditioning_set']}",
            "",
            "### 5.6 Temporal-role diagram and node decisions",
            "",
            "```mermaid",
            "flowchart LR",
            '    P["Pre-exposure demographic, socioeconomic, clinical, and seasonal context"] --> E["Two-day UPF energy percentage"]',
            '    P --> Y["PHQ-9 depressive symptoms"]',
            '    E -. concurrent or downstream .-> D["BMI, physical activity, sleep"]',
            '    Y -. concurrent reverse pathway .-> D',
            '    U["Unmeasured common causes"] --> E',
            '    U --> Y',
            "```",
            "",
        ]
        role_rows = [[x["node"], x["role"], x["primary"]] for x in m["temporal_role_rows"]]
        lines.extend(markdown_table(["Node", "Temporal role", "Primary-model decision"], role_rows))
        lines.extend([
            "",
            "This diagram organizes a descriptive association model; it does not claim that the conditioning set closes every backdoor path. Residual confounding and reverse temporal ordering remain explicit limitations.",
            "",
        ])
        return lines
    measurement = intake.get("measurement_plan", {})
    details = measurement.get("instrument_details", [])
    rows = []
    for item in details:
        appendix = item.get("appendix", {}) if isinstance(item.get("appendix"), dict) else {}
        rows.append([
            str(item.get("variable", "")), str(item.get("instrument", "")), str(item.get("source_type", item.get("origin", ""))), str(item.get("version_language", item.get("version", ""))),
            str(item.get("administration", "")), str(item.get("scoring", "")), str(item.get("item_missing_rule", "")),
            str(item.get("license_status", item.get("licence_status", item.get("permission_or_licence", "")))),
            str(item.get("appendix_ref", appendix.get("path", appendix.get("status", "")))),
            ", ".join(str(x) for x in item.get("citations", [])),
        ])
    if not rows:
        rows = [["[REQUIRES SPECIFICATION: variable]", "[REQUIRES SPECIFICATION: instrument]", "", "", "", "", "", "", "", ""]]
    lines = [
        "### 5.4 Instrument administration, scoring, and missing-item rules",
        "",
        (
            "The table below is the executable measurement specification. Instrument names alone are insufficient: version, language, administration, scoring, allowable "
            "item-level missingness, and validation evidence must all be frozen before training or programming."
        ),
        "",
    ]
    lines.extend(markdown_table(
        ["Variable", "Instrument/source", "Origin", "Version/language", "Administration", "Scoring/derivation", "Item-missing rule", "Permission/licence", "Appendix", "Evidence"], rows
    ))
    lines.extend([
        "",
        (
            f"Translation and cultural adaptation follow {required(measurement, 'translation_plan', 'translation and cognitive-testing procedure')}. "
            f"Pilot acceptance requires {required(measurement, 'pilot_acceptance', 'pilot sample and acceptance thresholds')}. "
            f"Interviewer certification requires {required(measurement, 'certification_rule', 'training, certification, and retraining thresholds')}."
        ),
        "",
        (
            f"Quality control includes {required(measurement, 'field_qc', 'real-time and back-check quality-control rules')}. "
            f"The classification adjudication procedure is: {required(measurement, 'classification_adjudication', 'classification adjudication procedure')}. "
            "Raw responses, transformed values, classification codes, and exclusion flags remain separate fields so that every derived value can be reconstructed."
        ),
        "",
    ])
    return lines


def build_field_data_safety(intake: dict) -> list[str]:
    operations = intake.get("protocol_operations", {})
    field = operations.get("fieldwork", {})
    data = operations.get("data_lifecycle", {})
    safety = operations.get("participant_safety", {})
    return [
        "## 9. Field Operations, Participant Safety, and Data Lifecycle",
        "",
        "### 9.1 Field preparation and supervision",
        "",
        (
            f"Field teams are trained through {required(field, 'training', 'training curriculum, duration, and trainer')}. "
            f"Certification uses {required(field, 'certification', 'competency assessment and pass threshold')}; supervision uses "
            f"{required(field, 'supervision', 'observation, back-check, and retraining schedule')}. Device and questionnaire versions are controlled by "
            f"{required(field, 'version_control', 'field instrument version-control rule')}."
        ),
        "",
        "### 9.2 Sensitive-outcome safety pathway",
        "",
        (
            f"The hypothetical safety trigger is {required(safety, 'trigger', 'sensitive-response trigger')}. Under a future approved implementation, staff would "
            f"{required(safety, 'immediate_action', 'immediate private safety assessment and action')}. The required escalation specification is: "
            f"{required(safety, 'escalation', 'named clinical/supervisory escalation route and timing')}. The required referral specification is: "
            f"{required(safety, 'referral', 'local referral or emergency pathway')}."
        ),
        "",
        (
            f"Safety actions are documented as {required(safety, 'documentation', 'minimum safety documentation and separation from research responses')}. "
            f"The confidentiality exception is explained as {required(safety, 'confidentiality_boundary', 'limits of confidentiality for imminent risk')}. "
            "A positive symptom screen is not presented as a clinical diagnosis, and research participation does not substitute for assessment or treatment."
        ),
        "",
        (
            "This demonstration is intentionally non-field-ready. Before participant contact, a real protocol must name an accountable clinical owner; verify staffed and after-hours coverage; insert jurisdiction-specific emergency and crisis contacts; approve triage questions and imminent-risk criteria; train each role; complete a tabletop test; and bind owner, version, date, and SHA-256 to field materials. Placeholder contacts cannot satisfy this gate. An interviewer may pause and escalate but may not diagnose; a clinical owner determines disposition; a supervisor verifies coverage; and a data custodian segregates the minimum-necessary safety record from research responses. Until every requirement is independently checked, field launch remains blocked."
        ),
        "",
        "### 9.3 Data lifecycle and quality assurance",
        "",
        (
            f"Capture uses {required(data, 'capture', 'EDC system, validation, and offline synchronization rules')}. Corrections follow "
            f"{required(data, 'correction_audit', 'query, correction, timestamp, and audit-trail rule')}. Identifiers are separated through "
            f"{required(data, 'deidentification', 'linkage-key and de-identification procedure')}."
        ),
        "",
        (
            f"The analysis freeze requires {required(data, 'freeze_conditions', 'data-cleaning, reconciliation, and sign-off conditions')}. "
            f"Access is governed by {required(data, 'access_control', 'role-based access and review schedule')}; retention and destruction follow "
            f"{required(data, 'retention', 'retention period and destruction rule')}. The reproducible release contains "
            f"{required(data, 'reproducible_release', 'code, dictionary, environment, logs, and provenance artifacts')}."
        ),
        "",
    ]


def build_transparency_and_references(intake: dict) -> list[str]:
    operations = intake.get("protocol_operations", {})
    transparency = operations.get("transparency", {})
    lines = [
        "## 11. Patient and Public Involvement, Transparency, and Open Science",
        "",
        (
            f"Patient or public involvement is {required(transparency, 'ppi_status', 'PPI status, contributors, stages, and influence')}. "
            f"Registration is {required(transparency, 'registration', 'registry, identifier or pre-fieldwork deadline')}. "
            f"The sharing plan is {required(transparency, 'sharing', 'protocol, SAP, code, metadata, and data-access plan')}."
        ),
        "",
        (
            f"Dissemination to participants and communities follows {required(transparency, 'community_dissemination', 'community-facing dissemination route and timing')}. "
            "Negative, null, imprecise, and sensitivity-dependent findings remain reportable; publication decisions will not be based on statistical significance."
        ),
        "",
    ]
    return lines


def build_reference_list(intake: dict) -> list[str]:
    references = intake.get("references", [])
    lines = ["## References", ""]
    if not references:
        lines.append("[REQUIRES SPECIFICATION: verified reference list with stable identifiers]")
    else:
        for ref in references:
            rid = str(ref.get("id", "")).strip()
            citation = str(ref.get("citation", "")).strip()
            stable = str(ref.get("doi_or_url", "")).strip()
            lines.append(f"{rid}. {citation} {stable}".strip())
    lines.append("")
    return lines


def objective_heading(idx: int, objective: dict) -> list[str]:
    return [
        f"### 2.2.{idx} {objective['objective_id']}: {objective['objective_statement']}",
        "",
    ]


def build_protocol_info(intake: dict) -> list[str]:
    profile = intake.get("document_profile", {})
    rows = [
        ["Protocol version", profile.get("protocol_version", "Version 2.0")],
        ["Registration", profile.get("registration", "Not yet registered")],
        ["Funding", profile.get("funding", "Not stated")],
        ["Study team", profile.get("study_team", "To be finalized")],
        ["Protocol positioning", intake.get("protocol_positioning", "hybrid")],
    ]
    lines = ["## Protocol Information", ""]
    lines.extend(markdown_table(["Field", "Value"], rows))
    lines.append("")
    return lines


def build_abstract(intake: dict, objectives: list[dict], population: dict, study_design: dict) -> list[str]:
    background = intake.get("background_inputs", {})
    objective_summary = "; ".join(obj["objective_statement"] for obj in objectives if obj.get("reporting_role", "main_text") == "main_text")
    design_label = study_design.get("design_label", "cross-sectional observational study")
    setting = study_design.get("study_setting", "the planned setting")
    setting = setting[:1].lower() + setting[1:] if setting else setting
    method_summary = (
        f"This protocol describes a {design_label} in "
        f"{setting}. "
        f"The design uses {study_design.get('sampling_design', 'the specified sampling strategy')} and links each objective "
        "to a prespecified estimand, model, design-awareness rule, and output shell."
    )
    expected_outputs = []
    for obj in objectives:
        expected_outputs.extend(obj.get("primary_output_tables", [])[:1])
    lines = [
        "## 1. Title and Abstract",
        "",
        "### 1.1 Title",
        "",
        f"**{intake.get('full_protocol_title', intake['study_title'])}**",
        "",
        "### 1.2 Structured Abstract",
        "",
        f"**Background:** {background.get('public_health_burden', '')} {background.get('evidence_gap', '')}",
        "",
        f"**Objectives:** {objective_summary}",
        "",
        f"**Methods:** {method_summary}",
        "",
        (
            f"**Study populations:** The target population is {population.get('target_population', '')}; "
            f"the source population is {population.get('source_population', '')}; "
            f"the planned analytic population is {population.get('analytic_population', '')}."
        ),
        "",
        (
            f"**Sample-size strategy:** The planned target sample in this demonstration is {intake['sample_size_plan']['final_adopted_sample_size']} participants, "
            f"chosen from the registered objective-specific sample-size basis after incorporating design effect and non-response inflation."
        ),
        "",
        f"**Expected outputs:** {', '.join(expected_outputs)}.",
        "",
        (
            f"**Interpretation boundary:** This protocol contains {len([o for o in objectives if o.get('reporting_role', 'main_text') == 'main_text'])} main-text objective(s): "
            f"{', '.join(sorted(set(o.get('objective_type', 'unspecified') for o in objectives)))}. Each remains on its registered effect scale and no cross-sectional result is converted into a causal claim."
        ),
        "",
        f"**Keywords:** {'; '.join(intake.get('keywords', []))}",
        "",
    ]
    return lines


def build_background_and_objectives(intake: dict, objectives: list[dict]) -> list[str]:
    background = intake.get("background_inputs", {})
    lines = [
        "## 2. Background and Objectives",
        "",
        "### 2.1 Background",
        "",
        background.get("public_health_burden", ""),
        "",
        background.get("evidence_gap", ""),
        "",
        background.get("mechanistic_rationale", ""),
        "",
        background.get("methodological_gap", ""),
        "",
        background.get("why_this_study", ""),
        "",
        "### 2.2 Objectives and Hypotheses",
        "",
        (
            f"The protocol is structured around {len([o for o in objectives if o.get('reporting_role', 'main_text') == 'main_text'])} retained main-text objective(s). "
            "Each retained objective is written, analysed, and reported according to its own inferential commitments; objective types not present in the registry are not implied."
        ),
        "",
    ]
    for idx, objective in enumerate(objectives, start=1):
        if objective.get("reporting_role", "main_text") != "main_text":
            continue
        lines.extend(objective_heading(idx, objective))
        lines.extend(
            [
                objective["objective_statement"],
                "",
                f"Framework: **{objective['framework']}**; analysis family: **{objective['analysis_family']}**.",
                "",
                f"Reporting role: **{objective.get('reporting_role', 'main_text')}**; causal language required: **{objective.get('requires_causal_language', False)}**.",
                "",
            ]
        )
        if objective.get("hypothesis_policy") == "formal":
            lines.extend(
                [
                    f"Null hypothesis: {objective.get('null_hypothesis', 'Not stated.')}",
                    "",
                    f"Alternative hypothesis: {objective.get('alternative_hypothesis', 'Not stated.')}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "This objective is estimation-oriented and therefore does not rely on a formal null-versus-alternative hypothesis pair.",
                    "",
                ]
            )
    return lines


def build_design_and_setting(population: dict, intake: dict) -> list[str]:
    design = intake["study_design"]
    setting = design.get("study_setting", "the planned setting")
    setting = setting[:1].lower() + setting[1:] if setting else setting
    lines = [
        "## 3. Study Design and Setting",
        "",
        "### 3.1 Study Design",
        "",
        (
            f"This protocol governs a {design.get('design_label', 'cross-sectional observational study')} in "
            f"{setting} during {design.get('time_window', 'the stated study period')}. "
            f"The study uses {design.get('sampling_design', 'the prespecified sampling design')} and treats design-awareness as an analytical obligation rather than an optional sensitivity exercise."
        ),
        "",
        "### 3.2 Setting and Data Source",
        "",
        (
            f"Data will be obtained from {design.get('data_source', 'the stated data source')}. "
            f"The sampling frame is defined as {design.get('sampling_frame', 'the operational frame described in the design intake')}. "
            "The setting description is intentionally operational so that the protocol can govern a real implementation rather than merely describe a hypothetical dataset."
        ),
        "",
        "### 3.3 Sampling Logic and Analysis Consequences",
        "",
        (
            f"The sampling design requires preservation of the following design features: {', '.join(population.get('survey_design_features', [])) or 'no special design features specified'}. "
            "These features are carried forward into the SAP and the bias-control narrative so that population inference, non-response handling, and design-aware sensitivity analyses remain aligned."
        ),
        "",
    ]
    if population.get("design_constraints"):
        lines.extend(["Design constraints:", ""])
        lines.extend(bullet_lines(population["design_constraints"]))
        lines.append("")
    return lines


def build_participants(population: dict) -> list[str]:
    lines = [
        "## 4. Participants",
        "",
        "### 4.1 Population Trinity",
        "",
        (
            f"The target population is {population['target_population']}. "
            f"The source population is {population['source_population']}. "
            f"The analytic population is defined as {population['analytic_population']}. "
            "Keeping these three populations distinct prevents over-claiming generalizability and makes recruitment and exclusion decisions auditable."
        ),
        "",
        "### 4.2 Eligibility Criteria",
        "",
        "Inclusion criteria:",
        "",
    ]
    lines.extend(numbered_lines(population.get("inclusion_criteria", [])))
    lines.extend(["", "Exclusion criteria:", ""])
    lines.extend(numbered_lines(population.get("exclusion_criteria", [])))
    lines.extend(
        [
            "",
            "### 4.3 Recruitment and Non-response",
            "",
            "Recruitment sequence:",
            "",
        ]
    )
    lines.extend(numbered_lines(population.get("recruitment_sequence", [])))
    lines.extend(
        [
            "",
            population.get("non_response_plan", ""),
            "",
            "### 4.4 Generalizability Boundary",
            "",
            population.get("generalizability_boundary", ""),
            "",
            "### 4.5 Eligibility adjudication, withdrawal, and denominator control",
            "",
            (
                "Interviewers do not make discretionary eligibility exceptions. Ambiguous age, residence, language, or capacity information is referred to the field supervisor, "
                "who applies the signed eligibility manual and records the evidence, decision, date, and reviewer. Eligibility is determined before exposure and outcome scoring. "
                "A person who is later found ineligible remains in the flow record with the prespecified reason but is excluded from every analysis population."
            ),
            "",
            (
                "Participants may decline an item, pause, or withdraw without penalty. Withdrawal from further contact does not automatically authorize deletion of data already collected; "
                "the consent form and local ethics decision define whether previously collected data may be retained. The analysis dataset distinguishes refusal, item nonresponse, interrupted interview, "
                "withdrawal, technical loss, and protocol exclusion so these mechanisms are not collapsed into one missing value."
            ),
            "",
        ]
    )
    return lines


def build_variables_and_measurement(variable_registry: dict, objectives: list[dict]) -> list[str]:
    rows = [
        [
            row["variable"],
            row["role"],
            row["operational_form"],
            row["planned_analysis_role"],
        ]
        for row in variable_registry.get("variables", [])
    ]
    lines = [
        "## 5. Variable Definitions and Measurement",
        "",
        (
            "Variable definitions are centralized in the registry layer so that exposure, outcome, confounder, mediator, collider, and modifier labels remain stable across the protocol and SAP. "
            "This avoids the common failure mode in which variables drift from the background to the methods and then to the results shell."
        ),
        "",
        "### 5.1 Variable Roles Table",
        "",
    ]
    lines.extend(markdown_table(["Variable", "Role", "Operational form", "Planned analysis role"], rows))
    lines.extend(["", "### 5.2 Objective-linked Definitions", ""])
    for objective in objectives:
        if objective.get("reporting_role", "main_text") != "main_text":
            continue
        lines.extend(
            [
                f"#### {objective['objective_id']}",
                "",
                (
                    f"For {objective['objective_id']}, the population is {objective.get('population', '')}. "
                    f"The key exposure or condition is {objective.get('exposure', objective.get('condition', 'not stated'))}. "
                    f"The comparison, when applicable, is {objective.get('comparison', objective.get('context', 'not applicable'))}. "
                    f"The outcome or estimand target is {objective.get('outcome', objective.get('condition', 'not stated'))}."
                ),
                "",
            ]
        )
    if variable_registry.get("measurement_sources"):
        lines.extend(["### 5.3 Measurement Sources", ""])
        lines.extend(bullet_lines(variable_registry["measurement_sources"]))
        lines.append("")
    if variable_registry.get("measurement_quality"):
        lines.extend(["### 5.4 Measurement Quality Safeguards", ""])
        lines.extend(numbered_lines(variable_registry["measurement_quality"]))
        lines.append("")
    return lines


def build_bias_and_sample(intake: dict, variable_registry: dict, objectives: list[dict]) -> list[str]:
    bias = intake["bias_control_plan"]
    sample_size = intake["sample_size_plan"]
    lines = [
        "## 6. Bias Control and Sample Size",
        "",
        "### 6.1 Confounding Control",
        "",
        bias.get("confounding_plan", {}).get("summary", ""),
        "",
    ]
    for objective in objectives:
        adjustment = objective.get("adjustment_strategy", {})
        is_adjusted_association = (
            objective.get("objective_type") == "association"
            and bool(adjustment.get("adjustment_set"))
        )
        if not (objective.get("requires_causal_language") or is_adjusted_association):
            continue
        lines.extend(
            [
                f"#### {objective['objective_id']} DAG and Adjustment Strategy",
                "",
                (
                    f"The prespecified adjustment strategy for {objective['objective_id']} is "
                    f"{objective.get('adjustment_strategy', {}).get('strategy', 'not stated')}. "
                    f"The planned adjustment set is {', '.join(objective.get('adjustment_strategy', {}).get('adjustment_set', [])) or 'not specified'}. "
                    f"Excluded variables are {', '.join(objective.get('adjustment_strategy', {}).get('excluded_variables', [])) or 'not specified'}."
                ),
                "",
            ]
        )
        lines.extend(build_dag_mermaid(objective, variable_registry))
        lines.append("")
    lines.extend(
        [
            "### 6.2 Selection Bias Control",
            "",
            bias.get("selection_bias_plan", {}).get("summary", ""),
            "",
            "### 6.3 Information Bias Control",
            "",
            bias.get("information_bias_plan", {}).get("summary", ""),
            "",
            "### 6.4 Missing-data Strategy",
            "",
            bias.get("missing_data_policy", {}).get("summary", ""),
            "",
        ]
    )
    lines.extend(numbered_lines(bias.get("missing_data_policy", {}).get("steps", [])))
    control_rows = []
    for item in bias.get("controls", bias.get("structured_controls", [])):
        control_rows.append([
            str(item.get("objective_id", "")), str(item.get("bias_domain", item.get("domain", ""))),
            str(item.get("mechanism", "")), str(item.get("design_control", item.get("design_prevention", ""))),
            str(item.get("field_control", "")),
            str(item.get("monitoring_indicator", "")), str(item.get("threshold", "")),
            str(item.get("action", item.get("mandatory_action", ""))), str(item.get("analysis_control", item.get("analysis_mitigation", ""))),
            str(item.get("sensitivity_output", "")), str(item.get("residual_risk", "")),
        ])
    lines.extend(["", "### 6.4.1 Bias-control decision ledger", ""])
    lines.extend(markdown_table(
        ["Objective", "Domain", "Mechanism", "Design control", "Field control", "Indicator", "Threshold", "Mandatory action", "Analysis control", "Sensitivity output", "Residual risk"],
        control_rows or [["[REQUIRES SPECIFICATION: objective]", "", "", "", "", "", "", "", "", "", ""]],
    ))
    lines.extend([
        "",
        (
            "Bias controls are linked to observable process indicators. Selection control is assessed from frame coverage, contact disposition, response by design cell, and weight concentration. "
            "Information-bias control is assessed from source-specific completion, item missingness, interviewer effects, back-check discrepancies, equipment calibration, laboratory quality control, and blinded classification agreement. "
            "Confounding control is assessed from adherence to the frozen adjustment set rather than from whether coefficients become statistically significant."
        ),
        "",
            (
                "Residual bias remains possible even when procedures are followed. Differential reporting, device or laboratory error, imperfect classification, nonparticipation related to both exposure and outcome, "
                "and unmeasured common causes can change an estimate. The analysis therefore separates measurement/coding, selection/weighting, missing-data, and model-form sensitivities; agreement across them "
                "supports robustness to the tested assumptions but does not establish exchangeability or temporality."
            ),
            "",
            "Each bias-domain conclusion will name the assumption tested, evidence observed, estimate change, and remaining uncertainty.",
            "",
    ])
    lines.extend(["", "### 6.5 Sample-size Planning", ""])

    basis_rows = []
    for base in sample_size.get("bases", []):
        assumptions = base.get("assumptions", [])
        basis_rows.append(
            [
                base["basis_id"],
                base["objective_id"],
                base["basis_type"],
                str(base["raw_required_n"]),
                str(base["design_effect"]),
                str(base["non_response_inflation"]),
                str(base["adjusted_required_n"]),
            ]
        )
        lines.extend(
            [
                (
                    f"Basis {base['basis_id']} addresses {base['objective_id']} using a {base['basis_type']} approach. "
                    f"The formula family is {base['formula_family']}, the raw required sample is {base['raw_required_n']}, "
                    f"the design effect is {base['design_effect']}, and the non-response inflation is {base['non_response_inflation']}."
                ),
                "",
                f"Assumptions and parameter sources: {', '.join(assumptions)}.",
                "",
                (
                    f"The arithmetic is frozen as raw n = {base['raw_required_n']}; design-adjusted n = "
                    f"{base['raw_required_n']} × {base['design_effect']} = "
                    f"{round(float(base['raw_required_n']) * float(base['design_effect']), 2)}; the final adjusted requirement is "
                    f"{base['adjusted_required_n']} after applying the registered non-response convention. Rounding is upward at each final integer stage."
                ),
                "",
            ]
        )
    lines.extend(markdown_table(
        ["Basis", "Objective", "Type", "Raw n", "DEFF", "Inflation", "Adjusted n"],
        basis_rows,
    ))
    lines.extend(
        [
            "",
            (
                f"The adopted final sample size is **{sample_size['final_adopted_sample_size']}**, "
                f"selected because {sample_size['adoption_reason']}"
            ),
            "",
            (
                f"Scenario analysis: {required(sample_size, 'scenario_analysis', 'sample-size scenarios varying prevalence/effect, design effect, and non-response')}. "
                f"If field yield differs from plan, the stopping and escalation rule is {required(sample_size, 'yield_rule', 'field-yield monitoring and decision rule')}. "
                "No observed exposure-outcome association will be examined to redefine the target sample during recruitment."
            ),
            "",
        ]
    )
    return lines


def build_sample_size_execution(intake: dict) -> list[str]:
    spec_sample = intake.get("_execution_spec", {}).get("sample_size")
    if not spec_sample:
        return []
    scenario_rows = [[str(x[k]) for k in ["p0", "pr", "p1", "exact_raw", "rounded_raw", "final_n", "exceeds_5000"]] for x in spec_sample["scenario_rows"]]
    lines = [
        "### 6.6 Reproducible association-power calculation",
        "",
        f"Method: {spec_sample['method']} [28]. Formula: `{spec_sample['formula']}`. Parameters: `{spec_sample['parameters']}`. {spec_sample['primary_result']}",
        "",
        f"Planning value: {spec_sample['planning_prevalence_source']}. Design effect: {spec_sample['deff']} Rounding: {spec_sample['rounding']}.",
        "",
        "The directional scientific alternative is evaluated with two-sided alpha 0.05 and a two-sided 95% interval; direction does not halve alpha.",
        "",
        "#### Frozen scenario table",
        "",
    ]
    lines.extend(markdown_table(["p0", "PR", "p1", "Exact raw n", "Rounded raw n", "Final n", ">5000"], scenario_rows))
    lines.extend(["", "Scenarios above 5,000 are explicit limitations; field yield is monitored without examining the exposure-outcome association.", ""])
    return lines


def build_stat_methods(intake: dict, objectives: list[dict]) -> list[str]:
    fixed_sequence = intake.get("analysis_plan", {}).get("analysis_sequence", [
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
    ])
    fixed_sequence = [
        str(item.get("stage_id") or item.get("name") or item) if isinstance(item, dict) else str(item)
        for item in fixed_sequence
    ]
    lines = [
        "## 7. Statistical Methods",
        "",
        (
            "Statistical methods are organized by objective rather than by a generic list of techniques. "
            "Each objective carries its own estimand, model specification, covariate policy, design-awareness rule, diagnostics, sensitivity analyses, and planned outputs."
        ),
        "",
        "### 7.0 Frozen execution order",
        "",
    ]
    lines.extend(numbered_lines(fixed_sequence))
    lines.extend([
        "",
        "Multiple imputation is positioned after raw-data and derivation checks but before the first model that requires imputed covariates. Descriptive summaries of observed data precede imputation; pooled inferential estimates require passed imputation diagnostics. The same eligible support set is frozen before comparing M0/M1/M2 so coefficient changes are not artifacts of changing denominators.",
        "",
    ])
    for idx, objective in enumerate(objectives, start=1):
        if objective.get("reporting_role", "main_text") != "main_text":
            continue
        lines.extend(
            [
                f"### 7.{idx} {objective['objective_id']}",
                "",
                f"Objective summary: {objective['objective_statement']}",
                "",
                f"Primary estimand: {objective['estimand_label']} ({objective['target_parameter']}).",
                "",
                f"Primary model: {objective['primary_model']}",
                "",
                (
                    f"Design-awareness rule: {objective['design_awareness']} "
                    f"Missing-data rule: {objective['missing_data_strategy']}"
                ),
                "",
            ]
        )
        if objective.get("adjustment_strategy", {}).get("adjustment_set"):
            lines.extend(
                [
                    f"Covariate set: {', '.join(objective['adjustment_strategy']['adjustment_set'])}.",
                    "",
                    f"Explicit exclusions: {', '.join(objective.get('adjustment_strategy', {}).get('excluded_variables', [])) or 'none stated'}.",
                    "",
                ]
            )
        lines.extend(["Diagnostics:", ""])
        lines.extend(bullet_lines(objective.get("diagnostics", [])))
        lines.extend(["", "Sensitivity analyses:", ""])
        lines.extend(numbered_lines(objective.get("sensitivity_analyses", [])))
        lines.extend(["", "Primary output tables:", ""])
        lines.extend(bullet_lines(objective.get("primary_output_tables", [])))
        if objective.get("supplementary_output_tables"):
            lines.extend(["", "Supplementary output tables:", ""])
            lines.extend(bullet_lines(objective["supplementary_output_tables"]))
        lines.extend(
            [
                "",
                f"Interpretation template: {objective['interpretation_template']}",
                "",
                (
                    "The model is fitted on the registered population and effect scale. Crude and adjusted estimates use the same exposure contrast so that adjustment cannot be confused with recoding. "
                    "Categorical reference groups, continuous-variable functions, survey variance, confidence-interval distribution, and model-failure sequence are fixed in the SAP; this protocol does not "
                    "delegate those choices to analyst discretion."
                ),
                "",
            ]
        )
    lines.extend([
        "### 7.2 Inferential hierarchy and reporting",
        "",
        (
            "The primary estimate is distinguished from descriptive, sensitivity, and exploratory outputs before analysis. A sensitivity result may change confidence in the primary interpretation, but it "
            "cannot replace the primary estimate without a dated deviation. Interaction analyses report the interaction term and stratum-specific marginal estimates with uncertainty; subgroup-specific p values "
            "are not used to claim effect modification. All results include unweighted analysis n and the survey target or denominator needed to interpret them."
        ),
        "",
        (
            "Statistical uncertainty is described with two-sided 95% confidence intervals on the registered scale. Conclusions consider direction, magnitude, interval width, design dependence, missing-data "
            "dependence, and measurement alternatives. The study will report null and imprecise estimates and will not convert a cross-sectional prevalence ratio into a risk ratio, incidence effect, or causal effect."
        ),
        "",
    ])
    return lines


def build_ethics_and_governance(intake: dict) -> list[str]:
    inst = intake["institutional_sections"]
    return [
        "## 10. Ethics, Data Security, and Governance",
        "",
        "### 10.1 Ethics review, consent, and participant rights",
        "",
        inst.get("ethics", ""),
        "",
        inst.get("consent_pathway", ""),
        "",
        "Participants may decline any item or withdraw from further research procedures without losing ordinary services. Withdrawal handling follows the consent form and the approving body's decision on data already incorporated into an irreversibly de-identified or locked analysis set. Foreseeable burdens depend on the registered measurements and may include interview time, measurement discomfort, emotional discomfort, and privacy loss; mitigation includes scheduling flexibility, trained neutral interviewing, private administration, the Section 9.2 safety route when applicable, and data minimization.",
        "",
        "### 10.2 Information governance and breach response",
        "",
        "The data manager approves role assignments against a documented need-to-know matrix. The linkage service, consent repository, safety-event store, and research dataset have separate authorization groups. A proposed data transfer requires a named recipient, minimum-variable disclosure review, encrypted channel, purpose limitation, retention date, onward-transfer prohibition, and entry in the export log. Suspected loss, unauthorized access, or disclosure activates the institutional incident procedure: contain access, preserve logs, notify the data manager and principal investigator, assess participant risk, and report to the approving body or affected participants within applicable institutional and legal timelines.",
        "",
        "### 10.3 Decision authority, amendments, and deviations",
        "",
        "The principal investigator owns scientific and safety decisions; the data manager controls data release; the lead statistician controls analytic freeze; and the independent statistician adjudicates reproducibility and analysis deviations. No role may approve its own unresolved conflict. Protocol amendments are approved and versioned before implementation except when an immediate change is required to remove a participant hazard; such urgent action is documented and reported promptly. Analysis deviations retain the originally frozen specification, timing relative to outcome access, reason, affected identifiers and outputs, impact assessment, and required approvals.",
        "",
        (
            "An ethics, consent, privacy, or safety deviation is escalated immediately to the principal investigator and handled under the approving body's timetable. A statistical deviation is additionally reviewed "
            "by both statisticians and cannot be hidden by overwriting the protocol, SAP, registry, or run manifest. The release checklist links each approved amendment or deviation to the exact document and output hashes it affects."
        ),
        "",
    ]


def build_protocol_display_shells(intake: dict) -> list[str]:
    spec = intake.get("_execution_spec", {})
    if not spec:
        return []
    model_rows = [[x["id"], x["role"], x["effect"], x["output"]] for x in spec["models"]]
    return [
        "## 8. Protocol Display Shells",
        "",
        "These shells freeze the information architecture without inventing result values. `Pending` is a result cell, not an unresolved design choice. The SAP model registry supplies the complete population, formula, estimator, survey-design, and MI fields for every identifier.",
        "",
        "### 8.1 Participant flow shell",
        "",
        "| Stage | Mutually exclusive reason | Unweighted n | Weighted adult population | Source ledger |",
        "| --- | --- | --- | --- | --- |",
        "| Sampled households | none | Pending | not applicable | sampling ledger |",
        "| Completed roster | refusal / noncontact / ineligible / unknown | Pending | Pending | AAPOR RR3 ledger |",
        "| Selected adults | none | Pending | Pending | adult selection table |",
        "| Completed interview | refusal / noncontact / withdrawal | Pending | Pending | person response ledger |",
        "| Valid two-day exposure | invalid or missing recall | Pending | Pending | recall QC |",
        "| Valid PHQ-9 outcome | missing item | Pending | Pending | PHQ scoring |",
        "| PRI-01 population | exposure/outcome complete; covariates observed or imputed | Pending | Pending | population registry |",
        "",
        "### 8.2 Objective-to-model/output shell",
        "",
    ] + markdown_table(["Model", "Role", "Effect/contrast", "Output"], model_rows) + [
        "",
        "### 8.3 Planned figures",
        "",
        "- Figure 1: participant-flow diagram; boxes report each mutually exclusive stage and unweighted n.",
        "- Figure 2: EXP-01 continuous UPF curve; x-axis UPF energy percentage from weighted 5th to 95th percentile in 5-point increments, y-axis adjusted PR, ribbon two-sided 95% CI, reference at observed weighted median.",
        "- Figure 3: INT-01 marginal PR by physical activity <600 versus >=600 MET-min/week with two-sided 95% CI; exploratory label in title and caption.",
        "- Figure 4: log final-weight histogram with 1st/99th cut points and Kish effective n in caption.",
        "- Figure 5: MI chain mean/SD traces with R-hat and slope thresholds in caption.",
        "- Figure 6: leave-one-PSU-out PR forest with PRI-01 vertical reference.",
        "",
    ]


def build_publication(intake: dict) -> list[str]:
    inst = intake["institutional_sections"]
    lines = [
        "## 12. Publication and Dissemination",
        "",
        inst.get("publication_and_dissemination", ""),
        "",
        inst.get("authorship_policy", ""),
        "",
        "Reporting commitments:",
        "",
    ]
    lines.extend(bullet_lines(intake.get("reporting_commitments", [])))
    lines.extend([
        "",
        (
            "The primary report will present the participant flow, weighted sample description, missingness, primary estimate, diagnostics that altered interpretation, and all prespecified sensitivity axes. "
            "Authorship does not confer authority to suppress an unfavorable or inconclusive result. Abstract, tables, figures, and plain-language products must use the same effect scale and cross-sectional boundary."
        ),
        "",
        (
            "Requests for additional analyses are classified before execution as clarification, sensitivity, or exploratory work. They receive a new output identifier and cannot be relabelled as prespecified. "
            "Corrections after release retain the original version, the reason for correction, and the affected table, figure, or conclusion so the public record remains traceable."
        ),
    ])
    lines.extend(["", "## Appendix A. Objective-to-output Mapping", ""])
    rows = []
    for objective in sorted_objectives(intake["study_objectives"]):
        rows.append(
            [
                objective["objective_id"],
                objective["objective_type"],
                objective.get("reporting_role", "main_text"),
                "; ".join(objective.get("primary_output_tables", [])),
            ]
        )
    lines.extend(markdown_table(["Objective", "Type", "Reporting role", "Primary outputs"], rows))
    lines.extend(["", "## Appendix B. Framework Commitments", ""])
    framework_rows = []
    for objective in sorted_objectives(intake["study_objectives"]):
        framework_rows.append(
            [
                objective["objective_id"],
                objective["framework"],
                objective["analysis_family"],
                objective.get("reporting_role", "main_text"),
            ]
        )
    lines.extend(markdown_table(["Objective", "Framework", "Analysis family", "Reporting role"], framework_rows))
    lines.extend(["", "## Appendix C. Sampling-Analysis Mapping", ""])
    sampling_rows = []
    survey_features = intake.get("study_design", {}).get("survey_design_features", [])
    for objective in sorted_objectives(intake["study_objectives"]):
        sampling_rows.append(
            [
                objective["objective_id"],
                ", ".join(survey_features) or "None stated",
                objective["design_awareness"],
            ]
        )
    lines.extend(markdown_table(["Objective", "Preserved design features", "Analysis consequence"], sampling_rows))
    return lines


def main_write_protocol_document() -> None:
    parser = argparse.ArgumentParser(description="Write the v2 study protocol.")
    parser.add_argument("design_intake_json")
    parser.add_argument("contracts_dir")
    parser.add_argument("registries_dir")
    parser.add_argument("blueprint_dir")
    parser.add_argument("protocol_output")
    args = parser.parse_args()

    intake = load_json(Path(args.design_intake_json))
    execution_spec, execution_spec_path = load_bound_execution_spec(intake, Path(args.design_intake_json))
    intake["_bound_execution_spec"] = execution_spec
    intake["_execution_spec"] = (
        execution_spec
        if str(execution_spec.get("spec_id", "")).startswith("CSA_V2_EX1_")
        else {}
    )
    intake["_execution_spec_path"] = str(execution_spec_path)
    registries_dir = Path(args.registries_dir)
    blueprint_dir = Path(args.blueprint_dir)
    blueprint_core = load_json(blueprint_dir / "protocol_blueprint_core.json")
    blueprint_editorial = load_json(blueprint_dir / "protocol_blueprint_editorial.json")
    population = load_json(registries_dir / "population_registry.json")
    variable_registry = load_json(registries_dir / "variable_registry.json")
    objectives = sorted_objectives(intake["study_objectives"])

    lines = front_matter(intake.get("full_protocol_title", intake["study_title"]))
    lines.extend(build_protocol_info(intake))
    lines.extend(build_document_status(intake))
    lines.extend(build_abstract(intake, objectives, population, intake["study_design"]))
    lines.extend(build_background_and_objectives(intake, objectives))
    lines.extend(build_evidence_map(intake))
    lines.extend(build_design_and_setting(population, intake))
    lines.extend(build_sampling_operations(intake))
    lines.extend(build_participants(population))
    lines.extend(build_variables_and_measurement(variable_registry, objectives))
    lines.extend(build_measurement_operations(intake))
    lines.extend(build_bias_and_sample(intake, variable_registry, objectives))
    lines.extend(build_sample_size_execution(intake))
    lines.extend(build_stat_methods(intake, objectives))
    lines.extend(build_protocol_display_shells(intake))
    lines.extend(build_field_data_safety(intake))
    lines.extend(build_ethics_and_governance(intake))
    lines.extend(build_transparency_and_references(intake))
    lines.extend(build_publication(intake))
    lines.extend(build_reference_list(intake))

    document_text = "\n".join(lines)
    validate_blueprint_bindings(intake, blueprint_core, blueprint_editorial, document_text)
    write_text(Path(args.protocol_output), document_text)

# write_sap_document
PENDING = "Pending"


def build_sap_v22(intake: dict, spec: dict) -> list[str]:
    admin = spec["administration"]
    sampling = spec["sampling"]
    sample = spec["sample_size"]
    source_to_local = {int(source_id): local for local, source_id in enumerate(spec["sap_reference_ids"], 1)}

    def localize_citations(value: str) -> str:
        def replace(match):
            expanded = []
            for part in match.group(1).split(","):
                part = part.strip()
                if "-" in part:
                    a, b = (int(x) for x in part.split("-", 1)); expanded.extend(range(a, b + 1))
                else:
                    expanded.append(int(part))
            local = [source_to_local[x] for x in expanded if x in source_to_local]
            return "[" + ",".join(str(x) for x in local) + "]" if local else ""
        import re
        return re.sub(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]", replace, value)

    measurement = {key: localize_citations(value) if isinstance(value, str) else value for key, value in spec["measurement"].items()}
    mi = spec["mi"]
    models = spec["models"]
    diagnostics = spec["diagnostics"]
    primary_obj = sorted_objectives(intake["study_objectives"])[0]
    population = intake["population_trinity"]

    lines = front_matter("Statistical Analysis Plan", subtitle=intake["study_title"])
    lines.extend([
        "# 1. Administration and Release State",
        "",
        f"Study identifier: **{admin['study_id']}**. Protocol version: **{admin['protocol_version']}**. SAP version: **{admin['sap_version']}**. Execution specification: **{spec['spec_id']} version {spec['version']}**.",
        "",
        f"Approval state: {admin['approval_status']}. The planned signature deadline is {admin['planned_signature_date']}. Outcome-access state: {admin['outcome_access_status']}. These statements distinguish a planned approval from a completed signature and prevent the worked example from implying institutional authorization.",
        "",
        "Required approvers are the principal investigator, lead statistician, independent statistician, and data custodian. Each signs the protocol hash, SAP hash, execution-specification hash, bound-asset hashes, version, date, and a declaration that no outcome-labelled analytic extract was accessed before sign-off. Missing or inconsistent signatures block execution.",
        "",
        "## 1.1 Version history",
        "",
        "| Version | Date | Status | Change | Approval required |",
        "| --- | --- | --- | --- | --- |",
        "| 3.0 | 2026-07-19 | Applied-methods workflow demonstration | Correct WR-PSU variance, weighted cut points, full weight chain, exact MI, fallback identity, output shells, executable R acceptance | Field and empirical release blocked |",
        "",
        "A correction that can change a population, derivation, weight, FPC, model, variance, effect scale, missing-data result, or display row is a substantive amendment. The deviation ledger records timing relative to outcome access, reason, affected identifiers, old and new hashes, and interpretive impact. An editorial correction is permitted only when a semantic diff proves no executable field changed.",
        "",
        "# 2. Objective, Estimand, Populations, and Inferential Hierarchy",
        "",
        f"Primary objective **{primary_obj['objective_id']}**: {primary_obj['objective_statement']}",
        "",
        f"Target population: {population['target_population']}. Source population: {population['source_population']}. Primary analysis population: eligible selected adults with two valid nonconsecutive dietary recalls, a fully scored PHQ-9 outcome, valid design variables and weights, and conditioning variables observed or imputed under Section 7.",
        "",
        f"Primary estimand: {primary_obj['estimand_label']}. The contrast is strictly greater than the weighted type-1 75th percentile of two-day mean UPF energy percentage versus values at or below that cut point. The effect scale is the population-average adjusted prevalence ratio. This is a cross-sectional descriptive association; it does not identify a causal effect or temporality.",
        "",
        f"Target parameter: {primary_obj['target_parameter']}",
        "",
        f"Design-awareness rule: {primary_obj['design_awareness']}",
        "",
        f"Interpretation template: {primary_obj['interpretation_template']}",
        "",
        "PRI-01 is the sole primary analysis. Crude estimates are descriptive. DES, EXP, OUT, MISS and MNAR identifiers are sensitivity analyses; INT-01 is exploratory; FALL identifiers are ordered model-failure outputs. One primary contrast is evaluated with two-sided alpha 0.05 and a two-sided 95% confidence interval. The directional scientific expectation of higher prevalence does not change sidedness. No secondary or exploratory p value can replace PRI-01.",
        "",
        "Method evidence: UPF definition and coding [1,2,3], PHQ-9 scoring and threshold [4,5], modified Poisson estimation [6], complex surveys [7], MI [8,9], observational reporting [10,11], AAPOR response rates [12], trial-derived estimand/SAP principles adapted rather than treated as observational mandates [13,14], IPAQ scoring [15], SAMPL reporting [16], association-power calculation [17], and anthropometry procedures [18].",
        "",
        "# 3. Sampling, Nonresponse Weights, Calibration, Trimming, and FPC",
        "",
        f"The restricted binding source is {sampling['restricted_annex']}. Frame reference date: **{sampling['frame_reference_date']}**. Scope: {sampling['frame_scope']}. The selection seed is **{sampling['seed']}** and the implementation is {sampling['script']}.",
        "",
    ])
    ward_rows = [[x["ward"], str(x["psu_count"]), str(x["households_per_psu"]), str(x["psu_count"] * x["households_per_psu"])] for x in sampling["ward_allocation"]]
    lines.extend(markdown_table(["Ward", "PSUs", "Households/PSU", "Selected households"], ward_rows))
    lines.extend([
        "",
        f"**Stage 1.** {sampling['pps_method']} Exact equation: `{sampling['pps_equation']}`.",
        "",
        f"**Stage 2.** {sampling['household_method']}",
        "",
        f"**Stage 3.** {sampling['adult_method']}",
        "",
        f"The base probability and weight are `{sampling['base_probability']}`. {sampling['worked_probability']}",
        "",
        f"Household response is frozen as follows: {sampling['household_nonresponse']}",
        "",
        f"Selected-adult completion response is frozen as follows: {sampling['person_nonresponse']}",
        "",
        f"Calibration uses adult-person margins only: {sampling['calibration']}",
        "",
        f"All cut points follow one convention: {sampling['quantile_rule']}",
        "",
        f"Trimming and restoration are exact: {sampling['trimming']}",
        "",
        f"Primary variance representation and FPC decision are deterministic: {sampling['fpc']} Exact call: `{sampling['primary_design_call']}`.",
        "",
        f"Lonely-PSU option: `{sampling['lonely_psu']}`. Inferential degrees of freedom: `{sampling['degrees_of_freedom']}`. A missing selection probability, calibration total, or invalid weight blocks PRI-01; the registered WR-PSU design cannot be changed after seeing results.",
        "",
        "## 3.1 Ordered construction and reconciliation",
        "",
        f"The executable order is fixed: {sampling['weight_chain']} Household and person factors are stored separately with their chosen collapse level. The resulting design uses final weights, ward strata and PSU identifiers only; it deliberately supplies neither FPC nor PPS options.",
        "",
        "Every transition produces a reconciliation table containing the incoming unit count, outgoing unit count, missing or duplicate identifiers, minimum and maximum weight, sum of weights by ward, and the absolute calibration discrepancy for every control cell. Counts may decrease only through a disposition explicitly authorized in the flow registry; joining errors are not dispositions. A response-adjustment cell with a missing denominator, zero eligible count, response factor outside its registered admissible range, or an unresolved unknown-eligibility allocation stops the run. Calibration must meet the stated epsilon=1e-7 criterion. Trimming is not accepted as complete until ward totals and all joint margins again meet the same tolerance.",
        "",
        "The primary variance object is the conservative with-replacement PSU Taylor representation supported by the verified final weights, ward strata and PSU identifiers. Household and adult identifiers remain in provenance and reconciliation but are not added as one-observation variance stages. Population-size FPC fields and pps='brewer' are prohibited because this demonstration does not supply verified stage sampling fractions and joint PPS variance inputs. A future design change requires a new protocol/SAP, code test and hash; it is not a sensitivity switch.",
        "",
        "The weighting report separates base-weight variation, household-response inflation, person-response inflation, calibration movement, and trimming movement. For each component it gives quantiles, coefficient of variation, Kish effective sample size, maximum-to-median ratio, and ward-specific totals. These quantities diagnose implementation and precision; they do not authorize a data-driven alternative weight. The unweighted analysis is registered as a sensitivity analysis because it changes the population representation, not as a fallback for inconvenient or unstable weighted results.",
        "",
        "# 4. Reproducible Sample Size and Precision",
        "",
        f"Method: {sample['method']} [17]. Formula: `{sample['formula']}`. Frozen parameters: `{sample['parameters']}`. Continuity correction is not used. {sample['primary_result']}.",
        "",
        f"Design effect: {sample['deff']} Planning-value provenance: {sample['planning_prevalence_source']}. Rounding: {sample['rounding']}.",
        "",
        "## 4.1 Scenario grid",
        "",
    ])
    lines.extend(markdown_table(["p0", "PR", "p1", "Exact raw n", "Rounded raw n", "Final n", ">5000"], [[str(x[k]) for k in ["p0", "pr", "p1", "exact_raw", "rounded_raw", "final_n", "exceeds_5000"]] for x in sample["scenario_rows"]]))
    lines.extend([
        "",
        "The grid holds DEFF at 1.50 and response at 0.90. It shows exactly which prevalence/effect combinations exceed 5,000. The primary calculation is reproducible without reverse-engineering the asserted n. Study yield is monitored without exposure-outcome estimates; under-recruitment changes precision, not the target effect or significance threshold.",
        "",
        "The calculation is an association-detection planning calculation, not a claim that the cross-sectional association is causal. The allocation ratio is applied on the anticipated exposure-group scale before inflation. The exact integer requirement is rounded upward to the next hundred, multiplied by the frozen cluster design effect, divided by the anticipated response proportion, and rounded upward again. No intermediate step rounds downward. The scenario rows repeat the complete calculation rather than scaling the final primary number, so an independent reviewer can reproduce each row from p0 and the prevalence-ratio assumption alone.",
        "",
        "If realized recruitment is below 5,000, the team reports the achieved eligible, interviewed, valid-recall, and primary-analysis counts and updates precision projections without inspecting the exposure-outcome association. Recruitment cannot be extended or stopped because a preliminary effect is favorable. If the planned frame cannot yield the registered sample, the protocol and SAP require an amendment that documents the cause, the new attainable precision, and whether the target population remains supportable; alpha, contrast, and model are not retuned to preserve nominal power.",
        "",
        "# 5. Frozen Measurements, Derivations, and Temporal Roles",
        "",
        f"Hash-bound dictionary: {measurement['dictionary']}. {measurement['dietary_manual']}. {measurement['phq9']} {measurement['ipaq']}",
        "",
        f"Dietary equation and component rules: {measurement['dietary_algorithm']}",
        "",
        f"Recall validity and day scheduling: {measurement['recall_validity']}",
        "",
        f"Energy plausibility and within-person error: {measurement['energy_flags']}",
        "",
        f"Weighted cut points and ties: {measurement['quartiles']}",
        "",
        f"Anthropometry: {measurement['anthropometry']}",
        "",
        f"Categorical mappings: {measurement['categorical_mappings']}",
        "",
        f"Conditioning-set rule: {measurement['conditioning_set']}",
        "",
    ])
    lines.extend(markdown_table(["Node", "Temporal role", "Primary-model decision"], [[x["node"], x["role"], x["primary"]] for x in measurement["temporal_role_rows"]]))
    lines.extend([
        "",
        "The temporal-role diagram is used to avoid automatically treating concurrent BMI, activity, or sleep as pre-exposure confounders. The conditioning set supports standardized descriptive comparison, not no-unmeasured-confounding identification. Smoking, alcohol, chronic disease, medication, employment, marital context, season, and total energy are explicitly addressed rather than silently omitted.",
        "",
        "# 6. Source-to-Analysis Derivation Dictionary",
        "",
        "The immutable dictionary version and hash in Section 5 control missing codes, categories, instrument constants, and anthropometric thresholds. The following execution rows supplement it; all source fields remain read-only and every derived value is rebuilt by code.",
        "",
    ])
    derivations = intake.get("sap_details", {}).get("variable_derivations", [])
    # The bound execution specification supersedes vague round-1 fields for the primary exposure/outcome and activity.
    derivation_rows = [
        ["upf_pct/upf_q4/upf_q5", "two recall item files", measurement["dietary_algorithm"], "two valid days; type-1 P75/P80; equality lower", "invalid day -> exposure missing; no automatic energy exclusion"],
        ["phq9_total/phq9_ge_10", "nine PHQ-9 items", "sum 0-3 items; total 0-27; binary >=10", "no prorating; item-9 safety retained", "any missing item -> outcome missing"],
        ["physical_activity/activity_high", "IPAQ-SF days/minutes/intensity", measurement["ipaq"], "cap 180 min/day; high >=600 MET-min/week", "incomplete component -> missing"],
        ["bmi", "up to three height/weight readings", measurement["anthropometry"], "mean two closest; cm/100; kg/m2", "no valid pair -> missing"],
        ["sex/education/income", "questionnaire codes", measurement["categorical_mappings"], "fixed references; no data-dependent category choice", "specified refusal/unknown codes -> missing"],
        ["season/total energy", "interview date/two recall days", "four fixed month groups; arithmetic mean kcal/day then log", "season fixed; energy positive", "invalid date/day -> missing/block as specified"],
    ]
    lines.extend(markdown_table(["Analysis variable", "Source", "Missing rule"], [[row[0], row[1], row[4]] for row in derivation_rows]))
    lines.extend(["", "## 6.1 Variable derivation cards", "", "Each card is normative; the compact index above is for navigation only.", ""])
    for card_number, row in enumerate(derivation_rows, 1):
        lines.extend([f"### 6.1.{card_number} {row[0]}", ""])
        lines.extend(markdown_table(["Field", "Frozen specification"], [
            ["Source", row[1]], ["Exact derivation", row[2]], ["Coding and QC", row[3]], ["Missing rule", row[4]],
        ]))
        lines.append("")
    lines.extend([
        "",
        "# 7. Missing Data and Variable-by-Variable MI",
        "",
        f"Primary activation rule: {mi['primary_rule']} Number of imputations starts at m={mi['m']} and follows the registered escalation with max_m={mi['max_m']}; iterations={mi['iterations']}; seed={mi['seed']}. Initialization: {mi['initialization']}.",
        "",
        f"Clustering/design accommodation: {mi['cluster_handling']}",
        "",
        f"Convergence decision: {mi['convergence']} Monte Carlo decision: {mi['monte_carlo']} Pooling: {mi['pooling']}.",
        "",
    ])
    lines.extend(markdown_table(["Variable", "Primary eligibility", "Method/bounds"], [[x[k] for k in ["variable", "primary", "method"]] for x in mi["variable_rows"]]))
    lines.extend(["", "## 7.1 Variable-specific imputation cards", "", "The following cards retain the complete source-missing, predictor, passive-term, and post-check fields without compressing them into an unreadable wide table.", ""])
    for card_number, row in enumerate(mi["variable_rows"], 1):
        lines.extend([f"### 7.1.{card_number} {row['variable']}", ""])
        lines.extend(markdown_table(["Field", "Frozen specification"], [
            ["Source missing codes", row["source_missing"]], ["Primary eligibility", row["primary"]],
            ["Method and bounds", row["method"]], ["Predictors", row["predictors"]],
            ["Passive terms", row["passive"]], ["Post-check", row["check"]],
        ]))
        lines.append("")
    lines.extend([
        "",
        f"Complete-case population: {mi['complete_case']}",
        "",
        f"Exposure/outcome-inclusive sensitivity: {mi['exposure_outcome_sensitivity']}",
        "",
        "## 7.2 Prespecified MNAR delta grids",
        "",
    ])
    delta_rows = []
    for grid in mi["delta_grids"]:
        for analysis_id, delta in zip(grid["ids"], grid["deltas"], strict=True):
            delta_rows.append([analysis_id, grid["target"], str(delta)])
    lines.extend(markdown_table(["Analysis ID", "Target", "Delta"], delta_rows))
    lines.extend([
        "",
        "**Outcome-grid implementation.** The scale is the logit of the imputation probability. "
        f"{mi['delta_grids'][0]['application']} This grid is run alone; the exposure remains observed.",
        "",
        "**Exposure-grid implementation.** The scale is the logit of the imputation probability. "
        f"{mi['delta_grids'][1]['application']} This grid is run alone; the outcome remains observed.",
        "",
        "The two grids are never crossed or run jointly. Each table row is keyed by its unique analysis ID, and the ID is retained in the run manifest and result shell.",
    ])
    lines.extend(["", f"Tipping-point rule: {mi['tipping_rule']}", "", "# 8. Complete Model, Fallback, and Sensitivity Registry", ""])
    lines.extend(markdown_table(["ID", "Role", "Effect", "Output"], [[x[k] for k in ["id", "role", "effect", "output"]] for x in models]))
    lines.extend(["", "## 8.1 Independently executable model cards", "", "The compact index above is navigational. Every field needed to execute a model appears in its card below.", ""])
    for card_number, model in enumerate(models, 1):
        lines.extend([f"### 8.1.{card_number} {model['id']}", ""])
        lines.extend(markdown_table(["Field", "Frozen specification"], [
            ["Role", model["role"]], ["Population", model["population"]],
            ["Exposure and outcome", model["exposure_outcome"]], ["Formula", model["formula"]],
            ["Family and options", model["family"]], ["Design", model["design"]],
            ["MI and pooling", model["mi"]], ["Effect", model["effect"]], ["Output", model["output"]],
        ]))
        lines.append("")
    lines.extend([
        "",
        "## 8.2 Registry execution and identity",
        "",
        "The table above is normative and each row is executed by identifier. A model is not defined merely by its formula: population, exposure and outcome construction, family and link, survey design, imputation/pooling state, reported transformation, and output destination are all part of the model identity. Every row contains a complete formula and resolved implementation fields; shorthand such as `same as primary`, `primary formula`, or `all primary covariates` is forbidden. Changing any field creates a different model and requires an amendment or deviation. The primary run controller accepts only identifiers present in this registry and refuses ad hoc formulas supplied at the command line.",
        "",
        "## 8.3 Inferential reading and terminal actions",
        "",
        "PRI-01 is interpreted only on its registered population-average prevalence-ratio scale. DES-01 and DES-02 characterize crude or unweighted departures and cannot supersede PRI-01. EXP-01 tests the information loss introduced by dichotomizing exposure while preserving the registered population and outcome. EXP-02 assesses the alternative P80 threshold without redefining the primary threshold. OUT-01 assesses continuous PHQ-9 severity and therefore answers a related but distinct outcome question. INT-01 evaluates prespecified effect-measure modification and remains exploratory irrespective of its p value.",
        "",
        "MISS-CC changes the missing-data assumption by restricting to complete records. MISS-EO allows exposure and outcome imputation in the registered sensitivity procedure. The separate exposure and outcome delta grids alter one missingness mechanism at a time, and the tipping declaration follows the exact grid rule in Section 7. Agreement is assessed by direction, magnitude, interval width, and the assumption changed; crossing 0.05 is not a concordance criterion and does not promote a sensitivity analysis.",
        "",
        "The fallback sequence is terminal and ordered. D-FIT alone can activate it. After a qualifying PRI-01 failure, FALL-LB is attempted once; after a qualifying FALL-LB failure, FALL-LOGIT is attempted once. FALL-LOGIT still targets a population-standardized marginal prevalence ratio: MI is outer, 500 Rao-Wu PSU bootstrap replicates are inner within each completed dataset, and log marginal PRs are Rubin-pooled with finite df.complete and a two-sided t interval. No odds ratio or percentile interval is substituted. D-SPARSE is diagnostic and can block INT-01 but never activates fallback.",
        "",
        "For every model, the run manifest records registry version, model identifier, formula digest, population digest, exposure/outcome derivation hashes, survey-design digest, imputation set, package versions, seed where applicable, warnings, elapsed time, and output hash. A result with a mismatched digest is quarantined rather than copied into a display. Independent review compares these fields to the rendered footnote and verifies that no result was assigned a more favorable inferential role during reporting.",
        "",
    ])
    lines.extend([
        "",
        f"Ordered failure sequence: {spec['fallback_sequence']}",
        "",
        "# 9. Diagnostic Decision Registry",
        "",
    ])
    lines.extend(markdown_table(["ID", "Trigger", "Deterministic action", "Output"], [[x[k] for k in ["id", "trigger", "action", "output"]] for x in diagnostics]))
    lines.extend([
        "",
        "No diagnostic authorizes unlogged observation deletion, p-value-driven conditioning-set change, or a new model. Rank deficiency, invalid weights, failed calibration, unresolved MI failure, and all-fallback failure are release blocks. High influence or concentration with verified data is retained and displayed through the registered sensitivity and diagnostic outputs.",
        "",
        "# 10. Complete Tables and Figures",
        "",
        "Result cells are marked `Pending locked execution`; all design-controlling cells are already concrete.",
        "",
        "## 10.1 Table 1 participant flow",
        "",
    ])
    flow_rows = [
        ["Frame households", "none", "sampling ledger"], ["Selected households", "none", "selection log"],
        ["Completed roster", "household refusal/noncontact/other/unknown/ineligible", "AAPOR ledger"],
        ["Selected eligible adults", "none", "adult selection table"], ["Completed interview", "person refusal/noncontact/withdrawal", "person ledger"],
        ["Two valid recalls", "one/zero valid days", "recall QC"], ["Complete PHQ-9", "one or more item missing", "PHQ scoring"],
        ["PRI-01 population", "observed exposure/outcome; conditioning observed or imputed", "population registry"],
        ["MISS-CC population", "all primary fields observed", "population registry"], ["MISS-EO population", "exposure/outcome eligible for sensitivity imputation", "population registry"],
    ]
    lines.extend(markdown_table(["Stage", "Mutually exclusive reason/definition", "Source", "Unweighted n", "Weighted adult total"], [r + [PENDING, PENDING] for r in flow_rows]))
    lines.extend(["", "## 10.2 Table 2 participant characteristics", ""])
    chars = [
        ["UPF energy %, weighted mean (SE) and median (IQR)", "continuous"], ["Q4 exposure, n and weighted %", "binary"],
        ["PHQ-9 total, weighted mean (SE)", "continuous"], ["PHQ-9>=10, n and weighted %", "binary"],
        ["Age, weighted mean (SE)", "continuous"], ["Sex, n and weighted % per fixed level", "categorical"],
        ["Education, n and weighted % per fixed level", "categorical"], ["Income, n and weighted % per fixed level", "categorical"],
        ["Smoking, n and weighted % per level", "categorical"], ["Alcohol g/day, weighted median (IQR)", "continuous skewed"],
        ["Chronic disease count, weighted mean (SE)", "count"], ["Psychotropic medication, n and weighted %", "binary"],
        ["Employment, n and weighted % per level", "categorical"], ["Marital status, n and weighted % per level", "categorical"],
        ["Season, n and weighted %", "categorical"], ["Total energy kcal/day, weighted mean (SE)", "continuous"],
        ["BMI, weighted mean (SE)", "descriptive"], ["Activity MET-min/week, weighted median (IQR)", "descriptive/exploratory"],
    ]
    lines.extend(markdown_table(["Characteristic (summary frozen)", "Type"], chars))
    lines.extend(["", "**Table 2 result panel**", ""])
    lines.extend(markdown_table(["Characteristic", "Overall", "Lower UPF", "Q4 UPF", "Missing n (%)"], [[a,PENDING,PENDING,PENDING,PENDING] for a,_ in chars]))
    lines.extend(["", "## 10.3 Table 3 missingness and imputation", ""])
    miss_rows = [["upf_q4", "not imputed primary; 2l.binary MISS-EO", "yes", "primary observed-only"], ["phq9_ge_10", "not imputed primary; 2l.binary MISS-EO", "yes", "primary observed-only"]]
    miss_rows += [[x["variable"], x["method"], "yes" if "impute" in x["primary"] else "no", x["primary"]] for x in mi["variable_rows"]]
    lines.extend(markdown_table(["Variable", "Missing n (%)", "By Q4 n (%)", "By outcome n (%)"], [[r[0],PENDING,PENDING,PENDING] for r in miss_rows]))
    lines.extend(["", "**Table 3 implementation panel**", ""])
    lines.extend(markdown_table(["Variable", "Method", "Primary-model role", "Bounds/check"], [[r[0],r[1],r[2],r[3]] for r in miss_rows]))
    lines.extend(["", "## 10.4 Table 4 primary and model registry results", ""])
    lines.extend(markdown_table(["Model", "Role", "Concrete contrast/scale", "Unweighted n / weighted adult total"], [[x["id"],x["role"],x["effect"],f"{PENDING} / {PENDING}"] for x in models]))
    lines.extend(["", "**Table 4 result panel**", ""])
    lines.extend(markdown_table(["Model", "Estimate", "95% CI", "p value", "Status"], [[x["id"],PENDING,PENDING,PENDING,PENDING] for x in models]))
    lines.extend(["", "## 10.5 Table 5 missing-data and delta results", ""])
    md_rows = [["PRI-01", "primary conditioning-variable MI", "0/reference"] , ["MISS-CC", "complete case", "not applicable"], ["MISS-EO", "exposure/outcome-inclusive MI", "not applicable"]]
    for grid in mi["delta_grids"]:
        for d in grid["deltas"]:
            md_rows.append(["MNAR-Y" if "PHQ" in grid["target"] else "MNAR-X", grid["target"], str(d)])
    lines.extend(markdown_table(["Analysis", "Target/method", "Delta", "n"], [[a,b,d,PENDING] for a,b,d in md_rows]))
    lines.extend(["", "**Table 5 result panel**", ""])
    lines.extend(markdown_table(["Analysis", "PR", "95% CI", "Difference from PRI-01", "Tipping status"], [[a,PENDING,PENDING,PENDING,PENDING] for a,_,_ in md_rows]))
    lines.extend(["", "## 10.6 Table 6 sensitivity registry", ""])
    diagnostic_shell_rows = [[x["id"],x["trigger"],x["action"],x["output"]] for x in diagnostics] + [["FALL-LB/FALL-LOGIT", spec["fallback_sequence"], "execute the frozen sequence and apply its terminal block", "Table 7"]]
    lines.extend(markdown_table(["Diagnostic/model", "Trigger/attempt", "Mandatory action", "Released output"], diagnostic_shell_rows))
    lines.extend(["", "**Table 6 observed-decision panel**", ""])
    lines.extend(markdown_table(["Diagnostic/model", "Observed value/message", "Pass/fail", "Action completed"], [[row[0],PENDING,PENDING,PENDING] for row in diagnostic_shell_rows]))
    lines.extend(["", "## 10.7 Table 7 fallback attempt ledger", "", "**Table 7A frozen definitions**", ""])
    fallback_definitions = [
        ["1", "PRI-01", "Always attempted", "Conditional PR"],
        ["2", "FALL-LB", "Qualifying D-FIT after PRI-01", "Conditional PR"],
        ["3", "FALL-LOGIT", "Qualifying D-FIT after FALL-LB", "Standardized marginal PR"],
    ]
    lines.extend(markdown_table(["Order", "Model", "Activation trigger", "Effect scale"], fallback_definitions))
    lines.extend(["", "**Table 7B observed attempts and release decision**", ""])
    lines.extend(markdown_table(
        ["Model", "Converged", "Finite estimate/SE", "Fitted range", "Estimate (SE; 95% CI)", "Release status"],
        [[row[1], PENDING, PENDING, PENDING, PENDING, PENDING] for row in fallback_definitions]))
    lines.extend(["", "## 10.8 Table 8 diagnostic decision ledger", "", "**Table 8A frozen thresholds and actions**", ""])
    lines.extend(markdown_table(
        ["Diagnostic", "Threshold", "Mandatory action", "Output"],
        [[x["id"], x["trigger"], x["action"], x["output"]] for x in diagnostics]))
    lines.extend(["", "**Table 8B observed decisions**", ""])
    lines.extend(markdown_table(
        ["Diagnostic", "Observed metric", "Decision", "Action completed"],
        [[x["id"], PENDING, PENDING, PENDING] for x in diagnostics]))
    lines.extend([
        "",
        "## 10.9 Figure shells",
        "",
        "- Figure 1 participant flow: ordered stage boxes, mutually exclusive exclusions, unweighted n; no weighted count in boxes.",
        "- Figure 2 EXP-01 continuous UPF: x=UPF energy percentage weighted 5th-95th percentile at 5-point increments; y=adjusted PR; 95% CI ribbon; reference=weighted median; PRI population/design/MI.",
        "- Figure 3 INT-01: marginal PR for Q4 within activity <600 and >=600 MET-min/week; 95% CI; exploratory in title/caption.",
        "- Figure 4 weights: x=log final weight, y=unweighted frequency; mark type-1 P1/P99 and caption CV, Kish n_eff, rake error.",
        "- Figure 5 MI: iteration on x; chain mean/SD on y; one panel per imputed variable; caption R-hat/slope/MC thresholds.",
        "- Figure 6 PSU influence: omitted PSU on y, PR and 95% CI on x, PRI-01 vertical line; verified PSUs are never deleted.",
        "",
        "Table footnote fixed for every inferential row: population and unweighted n; weighted adult target; model ID/full formula; conditioning set and references; outcome; missing-data method/m; final weight, ward strata, PSU, WR Taylor variance, no FPC/no PPS; effect scale; two-sided CI/test and finite degrees of freedom; inferential role; fallback/deviation status.",
        "",
        "# 11. Software and No-Discretion Implementation Map",
        "",
    ])
    lines.extend([
        "The implementation cards below are normative. Splitting them into cards preserves every frozen option while keeping long function signatures readable in DOCX and PDF exports.",
        "",
    ])
    for card_number, item in enumerate(spec["implementation_map"], 1):
        lines.extend([f"## 11.{card_number} {item['task']}", ""])
        lines.extend(markdown_table(["Field", "Frozen value"], [
            ["Package/function", item["package_function"]],
            ["Frozen options", item["options"]],
        ]))
        lines.append("")
    lines.extend([
        "",
        "At freeze, exact R and package versions are recorded in renv.lock; the run manifest stores hashes of source data, analysis data, protocol, SAP, execution specification, bound assets, code tree, renv.lock, seeds, logs, tables, and figures. A clean-environment rerun must reproduce counts and estimates within 1e-10 relative tolerance and identical labels/footnotes. Any manual inferential value or spreadsheet-only transformation blocks release.",
        "",
        "The implementation sequence is fixed as validation, derivation, sampling-ledger reconciliation, weight construction, survey-object construction, descriptive outputs, MI diagnostics, model registry execution, diagnostic and fallback adjudication, display assembly, and independent reproduction. Each stage reads only immutable inputs or products whose hashes appear in the preceding successful manifest. A failed stage prevents downstream execution. Cached results are accepted only when all input hashes, code hashes, execution-specification hash, derivation-dictionary hash, and renv.lock hash match exactly; otherwise the cache is invalidated and the stage is rerun.",
        "",
        "The run manifest contains input hashes for the source extracts, frame, control totals, design intake, protocol, SAP, execution specification, derivation dictionary, scripts, and environment lock. It also records the R executable, operating system, locale, time zone, package versions, random-number kind, every seed, command arguments, start/end timestamps, exit status, warnings, output hashes, analyst identity, and reviewer disposition. Secrets and direct identifiers are not copied into the manifest. File paths are recorded relative to the controlled project root so the run can be reproduced in a clean environment without workstation-specific substitutions.",
        "",
        "The independent rerun starts from a newly restored renv.lock and an empty output directory. It rebuilds the analysis objects and compares unit counts, weighted totals, cut points, model coefficients, variance estimates, confidence limits, diagnostic decisions, table cells, labels, and footnotes. Numeric comparisons use the registered 1e-10 relative tolerance only where bitwise identity is not guaranteed; categorical outputs and provenance hashes must match exactly. The reviewer signs the reproduction record only after every committed model and display is accounted for. A mismatch is investigated and resolved in code or data provenance, never concealed by manually replacing a table cell.",
        "",
        "The planning dry run verifies every bound-asset hash and then executes the synthetic R acceptance test. It proves weighted P75/P80 behavior, RR3/adult factors and collapse order, 27-cell rake/trim/rerake tolerance, WR-PSU survey construction, the full production formula with finite estimate/SE, standardization, split-Rhat unit cases, and an actual mice smoke run. It is synthetic software validation only, never empirical effect validation or field authorization.",
        "",
        "# 12. References",
        "",
    ])
    references_by_id = {int(ref["id"]): ref for ref in intake.get("references", [])}
    for local_number, source_id in enumerate(spec["sap_reference_ids"], 1):
        ref = references_by_id[int(source_id)]
        lines.append(f"{local_number}. {ref['citation']} {ref['doi_or_url']}")
    lines.extend([
        "",
        "# 13. Deviations, Sign-off, and Release Blocks",
        "",
        "Every deviation records identifier, discovery date, timing relative to outcome access, reason, affected objective/population/derivation/model/output, old and new hashes, estimate impact, and four-role disposition. A post-outcome change cannot be called prespecified. Planned sensitivity analyses remain separate from deviations.",
        "",
        "A future empirical release would require matching approvals and hashes, a valid real sampling annex, complete stage probabilities, converged adult-person calibration, the frozen derivation dictionary, passing MI/model diagnostics, Tables 7 and 8, clean-environment reproduction, citation resolution and page-level visual inspection. This demonstration lacks those real-study prerequisites and therefore blocks field and empirical release by construction.",
        "",
        "Sign-off artifact fields: PI name/date/signature; lead-statistician name/date/signature; independent-statistician name/date/signature and reproduction result; data-custodian name/date/signature and data/asset hash confirmation. In this worked example those signatures are intentionally absent, so the document demonstrates a closed plan without falsely claiming institutional approval.",
        "",
    ])
    return lines


def build_administration(intake: dict) -> list[str]:
    details = intake.get("sap_details", {})
    profile = intake.get("document_profile", {})
    rows = []
    for item in details.get("amendment_history", []):
        rows.append([
            str(item.get("version", "")), str(item.get("date", "")), str(item.get("change", "")),
            str(item.get("rationale", "")), str(item.get("approval", "")),
        ])
    if not rows:
        rows = [["[REQUIRES SPECIFICATION: SAP version]", "[REQUIRES SPECIFICATION: date]", "Initial issue", "Initial issue", "[REQUIRES SPECIFICATION: sign-off]"]]
    lines = [
        "# 1. Administration, Scope, and Status",
        "",
        (
            f"This is {required(details, 'sap_version', 'SAP version')} for {required(profile, 'protocol_version', 'protocol version')}. "
            f"It is authored by {required(details, 'author_role', 'SAP author and role')}, reviewed by the independent statistical reviewer: {required(details, 'reviewer_role', 'independent statistical reviewer')}, "
            f"and approved by {required(details, 'approver_role', 'scientific approver')}. The planned sign-off point is "
            f"{required(details, 'signoff_rule', 'sign-off timing relative to data access and freeze')}."
        ),
        "",
        (
            f"The data-freeze condition is {required(details, 'data_freeze_condition', 'analysis data-freeze conditions')}. "
            f"Unblinded outcome access before SAP sign-off is governed by {required(details, 'outcome_access_rule', 'pre-sign-off outcome-access restriction')}. "
            "This SAP takes precedence over informal analytic notes; a later change requires a dated deviation or amendment and cannot be concealed by overwriting this file."
        ),
        "",
        "## 1.1 Revision history",
        "",
    ]
    lines.extend(markdown_table(["Version", "Date", "Change", "Rationale", "Approval"], rows))
    lines.extend([
        "",
        f"Protocol positioning: **{intake.get('protocol_positioning', 'hybrid')}**.",
        "",
        f"Project mode: **{intake.get('project_mode', 'research')}**. Scientific release is allowed only after contracts, derivations, design variables, software environment, and output shells are frozen.",
        "",
    ])
    return lines


def build_sample_size_and_hierarchy(intake: dict) -> list[str]:
    plan = intake.get("sample_size_plan", {})
    details = intake.get("sap_details", {})
    rows = []
    for base in plan.get("bases", []):
        rows.append([
            str(base.get("basis_id", "")), str(base.get("objective_id", "")), str(base.get("formula_family", "")),
            "; ".join(str(x) for x in base.get("assumptions", [])), str(base.get("raw_required_n", "")),
            str(base.get("design_effect", "")), str(base.get("non_response_inflation", "")), str(base.get("adjusted_required_n", "")),
        ])
    lines = [
        "# 4. Sample Size, Precision, and Inferential Hierarchy",
        "",
        (
            "Study size is a design commitment, not a result of model fit. Each basis below is bound to an objective, numeric assumptions, and a target effect or precision. "
            "The adopted sample is the maximum objective-specific requirement after the registered design and non-response adjustments."
        ),
        "",
    ]
    lines.extend(markdown_table(
        ["Basis", "Objective", "Formula", "Assumptions/sources", "Raw n", "DEFF", "Non-response", "Adjusted n"], rows
        or [["[REQUIRES SPECIFICATION: basis]", "", "", "", "", "", "", ""]]
    ))
    lines.extend([
        "",
        (
            f"The adopted field sample is **{required(plan, 'final_adopted_sample_size', 'final sample size')}** because "
            f"{required(plan, 'adoption_reason', 'adoption rationale')}. Scenario analysis is {required(plan, 'scenario_analysis', 'sample-size scenario analysis')}. "
            f"Precision reporting will follow {required(details, 'precision_rule', 'precision and minimum-cell reporting rule')}."
        ),
        "",
        (
            f"The confirmatory hierarchy is {required(details, 'inferential_hierarchy', 'primary, secondary, sensitivity, and exploratory hierarchy')}. "
            f"Multiplicity is handled by {required(details, 'multiplicity_rule', 'multiplicity strategy and interpretation')}. "
            "Sensitivity analyses assess assumption dependence; they do not become co-primary because their p value is smaller."
        ),
        "",
    ])
    return lines


def build_survey_and_derivation_specs(intake: dict) -> list[str]:
    details = intake.get("sap_details", {})
    survey = details.get("survey_design", {})
    derivations = details.get("variable_derivations", [])
    rows = []
    for item in derivations:
        rows.append([
            str(item.get("analysis_variable", "")), ", ".join(str(x) for x in item.get("source_fields", [])),
            str(item.get("algorithm", "")), str(item.get("type_units_levels", "")), str(item.get("reference_or_function", "")),
            str(item.get("missing_rule", "")), str(item.get("qc_rule", "")),
        ])
    if not rows:
        rows = [["[REQUIRES SPECIFICATION: analysis variable]", "", "", "", "", "", ""]]
    lines = [
        "# 6. Frozen Variable Derivations and Survey Design",
        "",
        "## 6.1 Source-to-analysis derivations",
        "",
        (
            "The table below is normative. Source fields remain immutable; each derived variable is rebuilt by code, labelled with units and levels, and checked against "
            "the registered range and missingness rules. Descriptive recoding does not redefine the model term unless that distinction is explicitly recorded."
        ),
        "",
    ]
    lines.extend(markdown_table(
        ["Analysis variable", "Source fields", "Algorithm", "Type/units/levels", "Reference/function", "Missing rule", "QC"], rows
    ))
    lines.extend([
        "",
        "## 6.2 Complex-sample specification",
        "",
        (
            f"The survey object uses strata **{required(survey, 'strata', 'strata variable and nesting rule')}**, PSU **{required(survey, 'psu', 'PSU variable')}**, "
            f"and final analysis weight **{required(survey, 'weight', 'final weight variable')}**. Base weights are "
            f"{required(survey, 'base_weight', 'base-weight formula')}; non-response adjustment is {required(survey, 'non_response', 'non-response adjustment')}; "
            f"calibration and trimming are {required(survey, 'calibration_trimming', 'calibration and trimming procedure')}."
        ),
        "",
        (
            f"The lonely-PSU rule is {required(survey, 'lonely_psu', 'lonely-PSU handling')}; finite-population correction is "
            f"{required(survey, 'fpc', 'FPC included/excluded and rationale')}; survey degrees of freedom are "
            f"{required(survey, 'degrees_of_freedom', 'survey degrees-of-freedom rule')}. Subpopulation analyses use "
            f"{required(survey, 'subpopulation_rule', 'domain/subpopulation variance rule')} rather than deleting records before variance estimation."
        ),
        "",
        (
            f"The population-targeted primary analysis is {required(survey, 'primary_design_rule', 'weighted primary analysis rule')}. "
            f"The unweighted comparison is {required(survey, 'unweighted_role', 'role and interpretation of unweighted analysis')}. "
            "A conflict between the target population and design handling is a fatal inconsistency, not an editorial warning."
        ),
        "",
    ])
    return lines


def build_missing_data_algorithm(intake: dict) -> list[str]:
    mi = intake.get("sap_details", {}).get("multiple_imputation", {})
    return [
        "# 8. Missing Data and Multiple Imputation Algorithm",
        "",
        (
            f"The primary missing-data strategy is activated when {required(mi, 'trigger', 'objective missing-data trigger')}. "
            f"Variables eligible for imputation are {required(mi, 'eligible_variables', 'imputed and non-imputed variables')}; exposure and outcome are handled by "
            f"{required(mi, 'exposure_outcome_rule', 'exposure/outcome imputation rule')}."
        ),
        "",
        (
            f"The imputation method by variable type is {required(mi, 'methods', 'method for continuous, binary, ordinal, and nominal variables')}. "
            f"The predictor matrix includes {required(mi, 'predictors', 'analysis and auxiliary predictors')} and handles survey variables by "
            f"{required(mi, 'survey_variables', 'strata/PSU/weight handling in imputation')}. Nonlinear terms and interactions are preserved by "
            f"{required(mi, 'compatibility', 'passive/substantive-model-compatible derivation rule')}."
        ),
        "",
        (
            f"The algorithm creates {required(mi, 'm', 'number of imputations')} imputations, runs {required(mi, 'iterations', 'iterations per imputation')}, "
            f"and uses seed {required(mi, 'seed', 'random seed')}. Convergence is assessed by {required(mi, 'convergence', 'trace and distribution checks')}; "
            f"Monte Carlo adequacy is assessed by {required(mi, 'monte_carlo', 'Monte Carlo error or fraction-missing-information rule')}."
        ),
        "",
        (
            f"Estimates and variances are combined by {required(mi, 'pooling', 'pooling rule, including transformed scales and multi-parameter tests')}. "
            f"Complete-case comparison, alternative imputation, and departure-from-MAR analysis follow {required(mi, 'sensitivity', 'missing-data sensitivity hierarchy')}. "
            "Failure to meet convergence or Monte Carlo criteria blocks the pooled result and triggers the prespecified remediation sequence; it does not authorize selective reporting of a favorable run."
        ),
        "",
    ]


def build_model_and_diagnostics(intake: dict, objectives: list[dict]) -> list[str]:
    details = intake.get("sap_details", {})
    specs = {str(x.get("objective_id")): x for x in details.get("model_specifications", [])}
    lines = ["# 9. Exact Models, Estimation, and Diagnostic Actions", ""]
    for idx, objective in enumerate(objectives, 1):
        spec = specs.get(objective["objective_id"], {})
        strategy = objective.get("adjustment_strategy", {})
        lines.extend([
            f"## 9.{idx} {objective['objective_id']}",
            "",
            (
                f"The frozen model formula is `{required(spec, 'formula', 'exact model formula')}`. The family/link and estimator are "
                f"{required(spec, 'family_link', 'family, link, estimation method, and variance estimator')}. The effect reported is "
                f"{required(spec, 'effect_scale', 'effect scale and transformation')}; the exposure contrast is "
                f"{required(spec, 'contrast', 'exposure contrast and reference')}."
            ),
            "",
            (
                f"Continuous-variable functions are {required(spec, 'continuous_functions', 'continuous-variable functional forms and knots')}. "
                f"Categorical references are {required(spec, 'reference_levels', 'all categorical reference levels')}. Clustering, weights, and degrees of freedom enter through "
                f"{required(spec, 'design_variance', 'design/robust variance specification')}. Marginal or conditional interpretation is "
                f"{required(spec, 'interpretation', 'marginal/conditional interpretation')}."
            ),
            "",
            (
                f"The failure fallback is ordered as follows: {required(spec, 'fallback', 'unique ordered model-failure fallback')}. "
                "A fallback that changes the estimand is reported as a supportive analysis and cannot inherit the primary label."
            ),
            "",
        ])
        sequence_rows = []
        for row in strategy.get("model_sequence", []):
            sequence_rows.append([
                str(row.get("model_id", row.get("level", ""))),
                str(row.get("analysis_sample_id", row.get("sample_id", ""))),
                ", ".join(str(x) for x in row.get("adjustment_set", [])) or "None",
                str(row.get("formula", "")),
                str(row.get("reporting_role", "")),
            ])
        lines.extend(markdown_table(
            ["Model", "Common analysis sample", "Adjustment set", "Formula", "Reporting role"],
            sequence_rows or [["[REQUIRES SPECIFICATION: M0/M1/M2]", "", "", "", ""]],
        ))
        lines.extend([
            "",
            f"Common-sample rule: {required(strategy, 'common_sample_rule', 'one analysis-sample definition shared by M0/M1/M2')}.",
            "",
        ])
    diagnostics = details.get("diagnostic_actions", [])
    rows = [[
        str(x.get("diagnostic", "")), str(x.get("scope", "")), str(x.get("trigger", "")),
        str(x.get("mandatory_action", "")), str(x.get("reporting", "")),
    ] for x in diagnostics]
    lines.extend(["## 9.99 Diagnostic decision table", ""])
    lines.extend(markdown_table(
        ["Diagnostic", "Scope", "Trigger", "Mandatory action", "Reporting"], rows
        or [["[REQUIRES SPECIFICATION: diagnostic]", "", "", "", ""]]
    ))
    lines.extend([
        "",
        (
            "Diagnostic thresholds are decision rules, not automatic data-deletion rules. Every triggered action is retained in the diagnostic registry. A change to population, "
            "estimand, exposure contrast, adjustment set, model family, or primary variance estimator additionally requires a deviation and statistical sign-off."
        ),
        "",
    ])
    return lines


def build_output_shells(intake: dict, objectives: list[dict]) -> list[str]:
    primary_id = next((o["objective_id"] for o in objectives if o.get("priority") == "primary"), objectives[0]["objective_id"])
    pending = "Not populated before locked analysis"
    lines = [
        "# 10. Complete Output Shells",
        "",
        (
            "The following shells are part of the SAP, not title-only promises. Cells reserved for results are deliberately marked as not populated before locked analysis; "
            "denominators, effect scales, model identifiers, and footnotes are frozen now. Additional display rows require a documented amendment or deviation."
        ),
        "",
        "## 10.1 Participant flow shell",
        "",
    ]
    lines.extend(markdown_table(["Stage", "Unweighted n", "Weighted population", "Reason/source"], [
        ["Frame records", pending, pending, "Sampling-frame reconciliation"],
        ["Selected units", pending, pending, "Random-selection log"],
        ["Eligible", pending, pending, "Eligibility rules"],
        ["Consented", pending, pending, "Consent log"],
        ["Primary analysis population", pending, pending, f"{primary_id} population rule"],
    ]))
    lines.extend(["", "## 10.2 Participant characteristics shell", ""])
    lines.extend(markdown_table(["Characteristic", "Overall", "Exposure reference", "Exposure index", "Missing n (%)"], [
        ["Age, mean (SE) or median (IQR)", pending, pending, pending, pending],
        ["Sex, n and weighted %", pending, pending, pending, pending],
        ["Education, n and weighted %", pending, pending, pending, pending],
        ["Primary outcome, n and weighted %", pending, pending, pending, pending],
    ]))
    lines.extend(["", "## 10.3 Missingness shell", ""])
    lines.extend(markdown_table(["Variable", "Missing n (%)", "By exposure", "By outcome", "Imputation method", "Included in primary model"], [
        ["Primary exposure", pending, pending, pending, "Frozen in Section 8", "Yes/no per rule"],
        ["Primary outcome", pending, pending, pending, "Frozen in Section 8", "Yes/no per rule"],
        ["Each covariate", pending, pending, pending, "Type-specific method", "Yes"],
    ]))
    lines.extend(["", "## 10.4 Primary result shell", ""])
    lines.extend(markdown_table(["Objective/model", "Contrast", "Analysis n", "Estimate", "95% CI", "p value", "Effect scale"], [
        [f"{primary_id} primary", "Frozen contrast", pending, pending, pending, pending, "Registered target scale"],
        [f"{primary_id} crude", "Same contrast", pending, pending, pending, pending, "Same effect scale"],
    ]))
    lines.extend(["", "## 10.5 Missing-data sensitivity shell", ""])
    lines.extend(markdown_table(["Objective", "Method", "Analysis n", "Estimate", "95% CI", "Difference from primary", "Interpretive role"], [
        [primary_id, "Multiple imputation", pending, pending, pending, "Reference", "Primary/supportive per frozen rule"],
        [primary_id, "Complete case", pending, pending, pending, pending, "Sensitivity"],
        [primary_id, "Departure from MAR", pending, pending, pending, pending, "Sensitivity"],
    ]))
    lines.extend(["", "## 10.6 Design and model sensitivity shell", ""])
    lines.extend(markdown_table(["Objective", "Design/model", "Analysis n", "Estimate", "95% CI", "Assumption changed", "Concordance"], [
        [primary_id, "Survey-weighted primary", pending, pending, pending, "None", "Reference"],
        [primary_id, "Unweighted model", pending, pending, pending, "Population weighting", pending],
        [primary_id, "Prespecified alternative family", pending, pending, pending, "Mean/variance specification", pending],
    ]))
    lines.extend([
        "",
        (
            "All shells will state unweighted analysis n, weighted population where relevant, missing-data method, model identifier, adjustment set, and whether the display is primary, "
            "secondary, sensitivity, or exploratory. Footnotes must define the reference group, effect scale, confidence-interval method, survey design, and any multiplicity convention."
        ),
        "",
    ])
    return lines


def main_write_sap_document() -> None:
    parser = argparse.ArgumentParser(description="Write the v2 statistical analysis plan.")
    parser.add_argument("design_intake_json")
    parser.add_argument("contracts_dir")
    parser.add_argument("registries_dir")
    parser.add_argument("sap_output")
    args = parser.parse_args()

    intake_path = Path(args.design_intake_json)
    intake = load_json(intake_path)
    execution_spec, _ = load_bound_execution_spec(intake, intake_path)
    if str(execution_spec.get("spec_id", "")).startswith("CSA_V2_EX1_"):
        # Preserve the gold applied-methods example without making its
        # UPF/PHQ-9 assumptions the default for every research study.
        lines = build_sap_v22(intake, execution_spec)
        write_text(Path(args.sap_output), "\n".join(lines))
        return

    # Generic objective-driven writer for real research specifications.
    sap_contract = load_json(Path(args.contracts_dir) / "sap_contract.json")
    estimand_registry = load_json(Path(args.registries_dir) / "estimand_registry.json")
    objectives = sorted_objectives(intake["study_objectives"])
    estimand_map = {item["objective_id"]: item for item in estimand_registry["objective_estimands"]}
    analysis_map = {item["objective_id"]: item for item in sap_contract["analysis_map"]}
    population = intake.get("population_trinity", {})
    design = intake.get("study_design", {})
    measurement = intake.get("measurement_plan", {})
    bias = intake.get("bias_control_plan", {})

    lines = front_matter("Statistical Analysis Plan", subtitle=intake["study_title"])
    lines.extend(build_administration(intake))
    lines.extend(
        [
            "# 2. Analysis Populations and Data Provenance",
            "",
            f"Target population: {population.get('target_population', 'not specified')}",
            "",
            f"Source population: {population.get('source_population', 'not specified')}",
            "",
            f"Primary analytic population: {population.get('analytic_population', 'not specified')}",
            "",
            f"Data source and period: {design.get('data_source', 'not specified')} during {design.get('time_window', 'the prespecified period')}.",
            "",
            f"Sampling design: {design.get('sampling_design', 'not specified')}. Survey strata, PSU, and weight variables must be retained in every analytic dataset.",
            "",
            "Population counts, exclusion reasons, and complete-case or imputed analysis counts will be reconciled in a participant-flow table before model release.",
            "",
            (
                "Dataset construction will begin from an immutable source extract. Exclusions will be applied in the protocol-specified order, "
                "and every step will record the number removed, the governing eligibility rule, and whether the exclusion occurred before or after exposure and outcome derivation. "
                "The analysis dataset will retain the source identifier required for reproducibility but will not overwrite raw variables with derived values."
            ),
            "",
            (
                "The primary analysis population will be frozen only after reconciling the sampling frame, eligibility fields, outcome availability, exposure availability, "
                "and survey-design variables. Any alternative population used for sensitivity analysis will receive a separate population label and denominator; results from different populations will not be combined under one table heading."
            ),
            "",
            (
                "Flow reconciliation is performed from a unit-level disposition ledger, not reconstructed from the final complete cases. The ledger preserves every selected household and adult, eligibility decision, "
                "consent status, source-specific measurement completion, outcome and exposure derivation status, required design variables, imputation eligibility, and final population flag. Counts are checked against the sampling, "
                "consent, capture, derivation, and analysis datasets; any mismatch blocks freeze until corrected or adjudicated."
            ),
            "",
            (
                "The primary analysis population excludes participants without a valid primary exposure or outcome under the frozen scoring rules but does not exclude participants merely because a covariate is missing. "
                "Covariate incompleteness activates Section 8. Exclusions discovered after derivation are applied without reference to the estimated association, and each reason is mutually exclusive in the flow table."
            ),
            "",
            "# 3. Objective Overview",
            "",
        ]
    )
    for idx, objective in enumerate(objectives, start=1):
        lines.extend(
            [
                f"## 3.{idx} {objective['objective_id']}",
                "",
                f"Objective summary: {objective['objective_statement']}",
                "",
                f"Reporting role: {objective.get('reporting_role', 'main_text')}.",
                "",
            ]
        )

    lines.extend(build_sample_size_and_hierarchy(intake))
    lines.extend(["# 5. Objective-aligned Analysis Specifications", ""])
    for idx, objective in enumerate(objectives, start=1):
        amap = analysis_map[objective["objective_id"]]
        estimand = estimand_map[objective["objective_id"]]
        lines.extend(
            [
                f"## 5.{idx} {objective['objective_id']}",
                "",
                f"Objective summary: {objective['objective_statement']}",
                "",
                f"Estimand statement: {estimand['estimand_label']} targeting {estimand['target_parameter']}.",
                "",
                f"Target population: {estimand['target_population']}",
                "",
                f"Outcome definition: {estimand['outcome_definition']}",
                "",
                f"Contrast: {estimand['contrast']}",
                "",
                f"Model specification: {amap['primary_model']}",
                "",
                f"Design-awareness rule: {amap['design_awareness']}",
                "",
                f"Missing-data rule: {amap['missing_data_strategy']}",
                "",
                (
                    f"Effect-scale commitment: all estimates for {objective['objective_id']} will be reported on the registered {estimand['target_parameter']} scale. "
                    "Model coefficients will not be translated to a different effect measure after inspecting statistical significance, and marginal or conditional interpretations will be labelled explicitly."
                ),
                "",
                (
                    "Estimation failure handling: non-convergence, separation, boundary estimates, unstable survey variance, or sparse cells will trigger a documented diagnostic review. "
                    "Only the ordered fallback frozen in Section 9 may be used; a fallback that changes the estimand moves the analysis to a supportive role and cannot silently substitute for the primary analysis."
                ),
                "",
                (
                    f"Execution binding: {objective['objective_id']} uses the population and contrast stated above, source-to-analysis derivations in Section 6, the exact formula and variance in Section 9, "
                    "missing-data implementation in Section 8, diagnostic actions in Section 9.99, and the primary and sensitivity shells in Section 10. A result missing any link in this chain is not releasable."
                ),
                "",
                "The analysis log records the identifier of every executed link and verifies the same denominator and effect scale before release.",
                "",
            ]
        )
        if objective.get("adjustment_strategy", {}).get("adjustment_set"):
            lines.extend(
                [
                    f"Covariate set: {', '.join(objective['adjustment_strategy']['adjustment_set'])}",
                    "",
                    f"Excluded variables: {', '.join(objective.get('adjustment_strategy', {}).get('excluded_variables', [])) or 'none stated'}",
                    "",
                ]
            )
        lines.extend(["Diagnostics:", ""])
        lines.extend(bullet_lines(amap.get("diagnostics", [])))
        lines.extend(["", "Sensitivity section:", ""])
        lines.extend(numbered_lines(amap.get("sensitivity_analyses", [])))
        lines.extend(["", "Result shells:", ""])
        lines.extend(bullet_lines(amap.get("result_shells", [])))
        lines.extend(["", "Primary output tables:", ""])
        lines.extend(bullet_lines(amap.get("primary_output_tables", [])))
        if amap.get("supplementary_output_tables"):
            lines.extend(["", "Supplementary output tables:", ""])
            lines.extend(bullet_lines(amap.get("supplementary_output_tables", [])))
        lines.extend(
            [
                "",
                f"Interpretation template: {amap['interpretation_template']}",
                "",
            ]
        )

    lines.extend(build_survey_and_derivation_specs(intake))
    lines.extend(
        [
            "# 7. Data Quality and Descriptive Analysis",
            "",
            bias.get("missing_data_policy", {}).get("summary", "Missingness will be characterized before modelling."),
            "",
            "Missingness will be summarized by variable and pattern, with separate counts for exposure, outcome, covariates, and survey-design fields. The number of imputations, imputation models, auxiliary variables, convergence checks, and pooling rules must be frozen before imputation; unresolved parameters block multiply imputed inference rather than being guessed.",
            "",
            "Continuous variables will be summarized using mean and standard deviation when distributionally appropriate, or median and interquartile range otherwise. Categorical variables will be reported as counts and percentages. Survey-weighted summaries will state the denominator and weight specification; unweighted counts remain available for flow reconciliation.",
            "",
            (
                "Before inferential modelling, the team will review duplicate identifiers, impossible values, discordant units, extreme survey weights, sparse outcome-by-exposure cells, and discrepancies between raw and derived variables. "
                "Each unresolved anomaly will be classified as a data correction, exclusion, sensitivity condition, or reportable limitation; silent deletion is prohibited."
            ),
            "",
            (
                "Missing-data decisions will be based on variable-specific percentages, joint patterns, likely causes, and compatibility with the planned model. "
                "Complete-case analysis will be accompanied by a comparison of included and excluded participants. If multiple imputation is activated under the Section 8 trigger, the imputation model will include the analysis variables and justified auxiliary predictors, preserve the substantive model structure according to the frozen compatibility rule, and report convergence and Monte Carlo adequacy."
            ),
            "",
            (
                "The descriptive table will be interpreted as a characterization of the realized sample, not as a sequence of significance tests. "
                "Standardized differences or other scale-appropriate contrasts may be used to show imbalance, while p-values will not determine covariate inclusion in the primary model."
            ),
            "",
            (
                "Quality review is completed before outcome modelling and produces a signed issue ledger. Duplicate-person candidates are resolved from identifiers outside the analytic dataset; impossible dates or units are queried against source records; "
                "extreme but valid values are retained and flagged rather than winsorized as ordinary observations. Primary exposure, outcome, anthropometric, laboratory, questionnaire-derived, and survey-weight variables receive source-appropriate independent derivation checks."
            ),
            "",
            (
                "Descriptive reporting distinguishes unweighted sample counts from survey-weighted percentages or means. Each percentage states its denominator and missing category; no denominator is inferred from a rounded percentage. "
                "Continuous distributions are summarized with location and spread plus clinically or operationally meaningful ranges. Exposure groups are described without baseline-significance testing, because imbalance does not decide the adjustment set."
            ),
            "",
        ]
    )
    lines.extend(build_missing_data_algorithm(intake))
    lines.extend(build_model_and_diagnostics(intake, objectives))
    lines.extend(build_output_shells(intake, objectives))
    lines.extend(
        [
            "# 11. Inferential Conventions and Sensitivity Interpretation",
            "",
            "All primary estimates will use two-sided 95% confidence intervals. Effect measures remain on the objective-specific scale, and robust or survey-design variance estimators will be reported explicitly. Model convergence, sparse cells, collinearity, influential observations, and outcome prevalence will be checked before interpretation.",
            "",
            "The objective hierarchy and confirmatory or descriptive status are those frozen in the registry. Sensitivity analyses do not replace a primary result without a logged deviation. Exploratory interactions and subgroup findings will be labelled exploratory, reported with interaction estimates and uncertainty, and not promoted solely because of nominal p-values.",
            "",
            (
                "Diagnostics will be interpreted against the assumptions of the executed model family. Collinearity summaries, residual or influence measures, goodness-of-fit information, and convergence messages will be retained in the diagnostic registry even when they do not alter the primary estimate. "
                "A diagnostic concern that changes the estimand, population, or model family requires a deviation record and re-freeze."
            ),
            "",
            (
                "The sensitivity hierarchy is prespecified as measurement/coding checks, population restrictions, missing-data alternatives, and model-family stress tests. "
                "Concordance will be judged from direction, magnitude, interval width, and the assumptions changed—not from whether every analysis crosses a conventional significance threshold."
            ),
            "",
            "# 12. Software, Reproducibility, and Output Control",
            "",
            "The execution record must preserve the R version, package versions, operating system, random seeds where applicable, and session information. Scripts, logs, registry objects, tables, and figures are linked to the frozen analysis contract; no software version is invented at the planning stage.",
            "",
            "Primary tables will report the analysis population, model, adjustment set, effect scale, estimate, 95% confidence interval, and denominator. Supplementary outputs will identify sensitivity or exploratory status. Reporting will follow STROBE and SAMPL-aligned statistical conventions.",
            "",
            (
                "Every released number must trace to a frozen registry row and every released table or figure must record its objective, analysis stage, source result identifiers, and file hash. "
                "Narrative interpretation will be written only after these objects are frozen, preventing prose from drifting away from the executed estimates."
            ),
            "",
            (
                f"The environment is frozen by {required(intake.get('sap_details', {}), 'environment_lock', 'environment lock and package version capture')}. "
                f"Random processes use {required(intake.get('sap_details', {}), 'seed_policy', 'seed registry')}. Code review and run authorization follow "
                f"{required(intake.get('sap_details', {}), 'code_review', 'independent code review and run sign-off')}; the run manifest records "
                f"{required(intake.get('sap_details', {}), 'run_manifest', 'input hashes, code commit, environment, timestamps, outputs, and reviewer')}."
            ),
            "",
            (
                "The run manifest stores input hashes for the immutable source extract, analysis dataset, protocol, SAP, code tree, and environment lock. It also records the objective, population, model identifier, "
                "seed, start and end time, executing analyst, exit status, warnings, and output hashes. A table or figure is released only when its registry entry points to a successful manifest and the independent review status is complete."
            ),
            "",
            (
                "Reproduction is tested from a clean environment by a reviewer who did not execute the primary run. The reproduction must regenerate analysis counts and all displayed estimates within machine tolerance, "
                "with identical categorical labels and footnotes. Any difference is resolved before narrative drafting; manually typed inferential values and spreadsheet-only transformations are prohibited."
            ),
            "",
            "# 13. Deviation Policy and Final Sign-off",
            "",
            sap_contract.get("deviation_policy", ""),
            " Deviations must state when they occurred, why they were necessary, which objective and output they affect, and whether interpretation changes.",
            "",
        ]
    )
    write_text(Path(args.sap_output), "\n".join(lines))

# export_protocol_package


def validate_release_audits(
    audit_paths: list[Path],
    adjudication_path: Path | None,
    protocol_path: Path | None,
    sap_path: Path | None,
) -> dict[str, bool]:
    warning_audits: list[Path] = []
    bound_inputs: set[str] = set()
    for path in audit_paths:
        if not path.exists():
            raise SystemExit(f"release audit not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        input_hashes = payload.get("input_sha256", {})
        if not isinstance(input_hashes, dict) or not input_hashes:
            raise SystemExit(f"release audit lacks input SHA-256 bindings: {path}")
        for raw_input, expected_hash in input_hashes.items():
            input_path = Path(raw_input)
            if not input_path.exists():
                raise SystemExit(f"release audit input no longer exists: {input_path}")
            if hashlib.sha256(input_path.read_bytes()).hexdigest() != expected_hash:
                raise SystemExit(f"release audit is stale for current input: {input_path}")
            bound_inputs.add(str(input_path.resolve()))
        status = str(payload.get("status", "")).lower()
        if status == "pass":
            continue
        if status == "warn":
            warning_audits.append(path)
            continue
        raise SystemExit(f"release audit blocks export ({status or 'missing status'}): {path}")
    required_current_inputs = {
        str(item.resolve()) for item in (protocol_path, sap_path) if item is not None
    }
    if not required_current_inputs.issubset(bound_inputs):
        raise SystemExit("release audits do not bind the current protocol and SAP inputs")
    if not warning_audits:
        return
    if adjudication_path is None or not adjudication_path.exists():
        raise SystemExit("warning audits require a hash-bound --warning-adjudication file")
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    if adjudication.get("status") != "accepted" or not str(adjudication.get("rationale", "")).strip():
        raise SystemExit("warning adjudication must have status=accepted and a non-empty rationale")
    accepted = {
        str(item.get("audit_sha256", "")): item
        for item in adjudication.get("accepted_audits", [])
        if item.get("decision") == "accept"
        and str(item.get("impact_assessment", "")).strip()
    }
    for path in warning_audits:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in accepted:
            raise SystemExit(f"warning audit is not explicitly hash-bound and adjudicated: {path}")


def find_pandoc() -> str | None:
    for cmd in ("pandoc", "/usr/local/bin/pandoc", "/opt/homebrew/bin/pandoc"):
        try:
            result = subprocess.run([cmd, "--version"], capture_output=True, timeout=10)
            if result.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def default_mainfont(lang: str) -> str:
    lowered = (lang or "").lower()
    if lowered.startswith("zh"):
        return "Songti SC"
    if lowered.startswith("ja"):
        return "Hiragino Mincho ProN"
    if lowered.startswith("ko"):
        return "AppleMyungjo"
    return "Times New Roman"


def pandoc_to_docx(pandoc: str, md_path: Path, out_path: Path, title: str, author: str, lang: str) -> bool:
    cmd = [
        pandoc,
        str(md_path),
        "--from", "markdown+smart",
        "--to", "docx",
        "--output", str(out_path),
        "--standalone",
        f"--metadata=title:{title}",
    ]
    if author:
        cmd.append(f"--metadata=author:{author}")
    if lang:
        cmd.append(f"--metadata=lang:{lang}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return True
        print(f"  [pandoc docx error] {result.stderr[:400]}")
        return False
    except Exception as exc:
        print(f"  [pandoc docx exception] {exc}")
        return False


def pandoc_to_pdf(
    pandoc: str,
    md_path: Path,
    out_path: Path,
    title: str,
    author: str,
    pdf_engine: str,
    lang: str,
    mainfont: str,
) -> bool:
    cmd = [
        pandoc,
        str(md_path),
        "--from", "markdown+smart",
        "--to", "pdf",
        "--output", str(out_path),
        "--standalone",
        f"--pdf-engine={pdf_engine}",
        f"--metadata=title:{title}",
        "--variable", "geometry:margin=2.5cm",
        "--variable", "fontsize=11pt",
        f"--variable=mainfont:{mainfont}",
    ]
    if author:
        cmd.append(f"--metadata=author:{author}")
    if lang:
        cmd.append(f"--metadata=lang:{lang}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return True
        print(f"  [pandoc pdf error] {result.stderr[:400]}")
        return False
    except Exception as exc:
        print(f"  [pandoc pdf exception] {exc}")
        return False


def pandoc_to_html(pandoc: str, md_path: Path, out_path: Path, title: str, author: str, lang: str) -> bool:
    cmd = [
        pandoc,
        str(md_path),
        "--from", "markdown+smart",
        "--to", "html5",
        "--output", str(out_path),
        "--standalone",
        "--embed-resources",
        f"--metadata=title:{title}",
    ]
    if author:
        cmd.append(f"--metadata=author:{author}")
    if lang:
        cmd.append(f"--metadata=lang:{lang}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception:
        return False


def weasyprint_from_html(html_path: Path, pdf_path: Path) -> bool:
    try:
        import weasyprint  # type: ignore

        weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return True
    except ImportError:
        print("  [weasyprint] Not installed. Run: pip install weasyprint")
        return False
    except Exception as exc:
        print(f"  [weasyprint error] {exc}")
        return False


def _apply_inline(para, text: str) -> None:
    pattern = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)")
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            para.add_run(text[pos: match.start()])
        full = match.group(0)
        if full.startswith("**"):
            run = para.add_run(match.group(2))
            run.bold = True
        elif full.startswith("`"):
            run = para.add_run(match.group(4))
            run.font.name = "Courier New"
        else:
            run = para.add_run(match.group(3))
            run.italic = True
        pos = match.end()
    if pos < len(text):
        para.add_run(text[pos:])


def python_docx_export(md_path: Path, out_path: Path, title: str, author: str) -> bool:
    try:
        from docx import Document  # type: ignore
        from docx.enum.text import WD_ALIGN_PARAGRAPH  # type: ignore
        from docx.shared import Pt  # type: ignore
    except ImportError:
        print("  [python-docx] Not installed. Run: pip install python-docx")
        return False

    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)

    if title:
        heading = document.add_heading(title, level=0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if author:
        author_para = document.add_paragraph(author)
        author_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if title or author:
        document.add_paragraph("")

    lines = md_path.read_text(encoding="utf-8").splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        heading_match = re.match(r"^(#{1,4})\s+(.*)", line)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", heading_match.group(2).strip())
            clean = re.sub(r"\*(.+?)\*", r"\1", clean)
            document.add_heading(clean, level=level)
            idx += 1
            continue
        if re.match(r"^---+$", line.strip()):
            document.add_paragraph("─" * 40)
            idx += 1
            continue
        if not line.strip():
            idx += 1
            continue
        if line.strip().startswith("|"):
            table_lines = []
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                table_lines.append(lines[idx])
                idx += 1
            rows = []
            for raw in table_lines:
                if re.match(r"^\|[-:| ]+\|$", raw.strip()):
                    continue
                rows.append([cell.strip() for cell in raw.strip().strip("|").split("|")])
            if rows:
                n_cols = max(len(row) for row in rows)
                table = document.add_table(rows=len(rows), cols=n_cols)
                table.style = "Table Grid"
                for r_idx, row in enumerate(rows):
                    for c_idx, cell in enumerate(row):
                        clean = re.sub(r"\*\*(.+?)\*\*", r"\1", cell)
                        clean = re.sub(r"\*(.+?)\*", r"\1", clean)
                        clean = re.sub(r"`(.+?)`", r"\1", clean)
                        table.cell(r_idx, c_idx).text = clean
            continue
        if re.match(r"^[-*+]\s+", line):
            text = re.sub(r"^[-*+]\s+", "", line)
            para = document.add_paragraph(style="List Bullet")
            _apply_inline(para, text)
            idx += 1
            continue
        if re.match(r"^\d+\.\s+", line):
            text = re.sub(r"^\d+\.\s+", "", line)
            para = document.add_paragraph(style="List Number")
            _apply_inline(para, text)
            idx += 1
            continue
        if line.startswith(">"):
            text = re.sub(r"^>\s*", "", line)
            para = document.add_paragraph()
            run = para.add_run(text)
            run.italic = True
            idx += 1
            continue
        para_lines = [line]
        idx += 1
        while idx < len(lines) and lines[idx].strip() and not re.match(r"^#{1,4}\s", lines[idx]) and not lines[idx].startswith("|"):
            para_lines.append(lines[idx])
            idx += 1
        para = document.add_paragraph()
        _apply_inline(para, " ".join(para_lines))

    document.save(str(out_path))
    return True


def pandoc_to_tex(pandoc: str, md_path: Path, out_path: Path, title: str, author: str, lang: str) -> bool:
    cmd = [
        pandoc,
        str(md_path),
        "--from", "markdown+smart",
        "--to", "latex",
        "--output", str(out_path),
        "--standalone",
        f"--metadata=title:{title}",
    ]
    if author:
        cmd.append(f"--metadata=author:{author}")
    if lang:
        cmd.append(f"--metadata=lang:{lang}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return True
        print(f"  [pandoc tex error] {result.stderr[:400]}")
        return False
    except Exception as exc:
        print(f"  [pandoc tex exception] {exc}")
        return False


def infer_title_from_md(md_path: Path) -> str:
    try:
        for line in md_path.read_text(encoding="utf-8").splitlines():
            title_match = re.match(r'^title:\s*"?(.*?)"?$', line.strip())
            if title_match and title_match.group(1) and title_match.group(1) != "---":
                return title_match.group(1).strip()
            heading_match = re.match(r"^#\s+(.+)", line)
            if heading_match:
                return heading_match.group(1).strip()
    except Exception:
        pass
    return md_path.stem.replace("_", " ").title()


def export_one_markdown(
    *,
    md_path: Path,
    output_dir: Path,
    stem: str,
    title: str,
    author: str,
    lang: str,
    mainfont: str,
    pandoc: str | None,
    include_tex: bool,
    include_word: bool,
    include_pdf: bool,
    pdf_engine: str,
) -> None:
    tex_path = output_dir / f"{stem}.tex"
    docx_path = output_dir / f"{stem}.docx"
    pdf_path = output_dir / f"{stem}.pdf"

    status: dict[str, bool] = {}
    if include_tex:
        print(f"[export_protocol_package] Exporting LaTeX → {tex_path}")
        if pandoc and pandoc_to_tex(pandoc, md_path, tex_path, title, author, lang):
            print(f"[export_protocol_package] LaTeX saved via pandoc: {tex_path}")
            status["tex"] = tex_path.exists() and tex_path.stat().st_size > 0
        else:
            print("[export_protocol_package] LaTeX export failed. Install pandoc to enable .tex export.")
            status["tex"] = False

    if include_word:
        print(f"[export_protocol_package] Exporting Word → {docx_path}")
        if pandoc and pandoc_to_docx(pandoc, md_path, docx_path, title, author, lang):
            print(f"[export_protocol_package] Word saved via pandoc: {docx_path}")
            status["docx"] = docx_path.exists() and docx_path.stat().st_size > 0
        elif python_docx_export(md_path, docx_path, title, author):
            print(f"[export_protocol_package] Word saved via python-docx: {docx_path}")
            status["docx"] = docx_path.exists() and docx_path.stat().st_size > 0
        else:
            print("[export_protocol_package] Word export failed. Install pandoc or python-docx.")
            status["docx"] = False

    if include_pdf:
        print(f"[export_protocol_package] Exporting PDF → {pdf_path}")
        pdf_ok = False
        if pandoc:
            engines = [pdf_engine] if pdf_engine else ["xelatex", "pdflatex", "lualatex", "weasyprint"]
            for engine in engines:
                print(f"  [export_protocol_package] Trying pdf-engine: {engine}")
                if engine == "weasyprint":
                    html_tmp = output_dir / f"{stem}_tmp.html"
                    if pandoc_to_html(pandoc, md_path, html_tmp, title, author, lang):
                        pdf_ok = weasyprint_from_html(html_tmp, pdf_path)
                        try:
                            html_tmp.unlink()
                        except Exception:
                            pass
                    if pdf_ok:
                        break
                else:
                    pdf_ok = pandoc_to_pdf(pandoc, md_path, pdf_path, title, author, engine, lang, mainfont)
                    if pdf_ok:
                        break
        if pdf_ok:
            print(f"[export_protocol_package] PDF saved: {pdf_path}")
            status["pdf"] = pdf_path.exists() and pdf_path.stat().st_size > 0
        else:
            print("[export_protocol_package] PDF export failed. Options:")
            print("  1. Install pandoc + a LaTeX distribution (MacTeX/MiKTeX)")
            print("  2. Install pandoc + weasyprint: pip install weasyprint")
            print("  3. Open the .docx in Word or LibreOffice and export to PDF")
            status["pdf"] = False
    return status


def main_export_protocol_package() -> None:
    parser = argparse.ArgumentParser(
        description="Export study protocol and SAP markdown files to Word, PDF, and optional TeX.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Requirements:
              Word via pandoc: brew install pandoc
              Word via python-docx: pip install python-docx
              PDF via pandoc+xelatex: pandoc + MacTeX / MiKTeX
              PDF via pandoc+weasyprint: pandoc + pip install weasyprint
            """
        ),
    )
    parser.add_argument("--protocol", help="Path to study_protocol.md")
    parser.add_argument("--sap", help="Path to statistical_analysis_plan.md")
    parser.add_argument("--output-dir", required=True, help="Directory to write exports")
    parser.add_argument("--consistency-audit", required=True, help="Passing consistency audit JSON")
    parser.add_argument("--quality-audit", required=True, help="Passing protocol quality audit JSON")
    parser.add_argument("--sap-quality-audit", required=True, help="Passing complete-body SAP quality audit JSON")
    parser.add_argument("--external-validation", help="Optional external-standard validation JSON")
    parser.add_argument("--execution-dry-run", required=True, help="Passing hash-bound deterministic execution-spec dry run JSON")
    parser.add_argument("--warning-adjudication", help="Hash-bound adjudication JSON required for any warning audit")
    parser.add_argument("--author", default="", help="Author name for document metadata")
    parser.add_argument("--lang", default="en", help="Document language tag")
    parser.add_argument("--mainfont", default="", help="Main font for PDF export; auto-selected if omitted")
    parser.add_argument("--no-tex", action="store_true", help="Skip TeX export")
    parser.add_argument("--no-word", action="store_true", help="Skip Word export")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF export")
    parser.add_argument("--pdf-engine", default="", help="Pandoc PDF engine: xelatex, pdflatex, lualatex, weasyprint")
    args = parser.parse_args()

    if not args.protocol and not args.sap:
        print("[export_protocol_package] At least one of --protocol or --sap must be provided.")
        sys.exit(1)

    protocol_input = Path(args.protocol) if args.protocol else None
    sap_input = Path(args.sap) if args.sap else None
    audit_paths = [
        Path(args.consistency_audit),
        Path(args.quality_audit),
        Path(args.sap_quality_audit),
        Path(args.execution_dry_run),
    ]
    if args.external_validation:
        audit_paths.insert(3, Path(args.external_validation))
    validate_release_audits(
        audit_paths,
        Path(args.warning_adjudication) if args.warning_adjudication else None,
        protocol_input,
        sap_input,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pandoc = find_pandoc()
    if pandoc:
        print(f"[export_protocol_package] pandoc found: {pandoc}")
    else:
        print("[export_protocol_package] pandoc not found; Word export will try python-docx fallback.")

    mainfont = args.mainfont or default_mainfont(args.lang)

    targets = []
    if args.protocol:
        protocol_path = Path(args.protocol)
        if not protocol_path.exists():
            print(f"[export_protocol_package] Protocol markdown not found: {protocol_path}")
            sys.exit(1)
        targets.append((protocol_path, "study_protocol"))
    if args.sap:
        sap_path = Path(args.sap)
        if not sap_path.exists():
            print(f"[export_protocol_package] SAP markdown not found: {sap_path}")
            sys.exit(1)
        targets.append((sap_path, "statistical_analysis_plan"))

    failed_outputs: list[str] = []
    for md_path, stem in targets:
        title = infer_title_from_md(md_path)
        output_status = export_one_markdown(
            md_path=md_path,
            output_dir=output_dir,
            stem=stem,
            title=title,
            author=args.author,
            lang=args.lang,
            mainfont=mainfont,
            pandoc=pandoc,
            include_tex=not args.no_tex,
            include_word=not args.no_word,
            include_pdf=not args.no_pdf,
            pdf_engine=args.pdf_engine,
        )
        failed_outputs.extend(f"{stem}.{suffix}" for suffix, ok in output_status.items() if not ok)

    if failed_outputs:
        raise SystemExit("requested exports failed or were empty: " + ", ".join(failed_outputs))

    print("\n[export_protocol_package] Done.")


COMMANDS = {
    "write_protocol_document": main_write_protocol_document,
    "write_sap_document": main_write_sap_document,
    "export_protocol_package": main_export_protocol_package,
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
