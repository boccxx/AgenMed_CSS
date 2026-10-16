#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/design_audit.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import subprocess
from pathlib import Path

from design_common import (
    body_word_count,
    contains_token,
    find_section,
    load_bound_execution_spec,
    load_json,
    normalize_project_mode,
    sequence_uniqueness,
    summarize_status,
    write_json,
)

# audit_consistency


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_map(paths: list[Path]) -> dict[str, str]:
    return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main_audit_consistency() -> None:
    parser = argparse.ArgumentParser(description="Run v2 consistency audit.")
    parser.add_argument("protocol_md")
    parser.add_argument("sap_md")
    parser.add_argument("contracts_dir")
    parser.add_argument("registries_dir")
    parser.add_argument("output_json")
    args = parser.parse_args()

    protocol_path = Path(args.protocol_md)
    sap_path = Path(args.sap_md)
    protocol_text = load_text(protocol_path)
    sap_text = load_text(sap_path)
    contracts_dir = Path(args.contracts_dir)
    registries_dir = Path(args.registries_dir)

    protocol_contract = load_json(contracts_dir / "protocol_contract.json")
    estimand_bridge = load_json(contracts_dir / "estimand_bridge.json")
    sap_contract = load_json(contracts_dir / "sap_contract.json")
    variable_registry = load_json(registries_dir / "variable_registry.json")

    errors: list[str] = []
    warnings: list[str] = []

    modes = {
        normalize_project_mode(protocol_contract.get("project_mode")),
        normalize_project_mode(sap_contract.get("project_mode")),
    }
    valid_modes = {"research", "applied_methods", "workflow_methods"}
    if len(modes) != 1 or not modes.issubset(valid_modes):
        errors.append(f"project_mode drift or invalid mode across contracts: {sorted(str(x) for x in modes)}")
    mode = next(iter(modes)) if len(modes) == 1 else "invalid"
    for label, body in [("protocol", protocol_text), ("SAP", sap_text)]:
        lowered = body.lower()
        if mode in {"applied_methods", "workflow_methods"} and (
            "field launch" not in lowered or not any(token in lowered for token in ("applied-methods", "workflow-methods", "demonstration"))
        ):
            errors.append(f"{label} does not preserve demonstration/non-field-ready identity")
        if mode == "research" and "demonstration only" in lowered:
            errors.append(f"{label} is research mode but contains a demonstration-only identity")
        forbidden_design = ["all three stage FPC", "three-stage ids/FPC", "percentile 95% CI", "odds-ratio supportive result"]
        for token in forbidden_design:
            if token.lower() in body.lower():
                errors.append(f"obsolete Round-2 design token in {label}: {token}")

    sap_reference_section = find_section(sap_text, "References")
    if not sap_reference_section:
        warnings.append("SAP local reference section missing")
    else:
        before_references = sap_text.split(sap_reference_section, 1)[0]
        ref_numbers = [int(x) for x in re.findall(r"(?m)^(\d+)\.\s+", sap_reference_section)]
        if ref_numbers != list(range(1, len(ref_numbers) + 1)):
            errors.append(f"SAP local reference numbering is not consecutive from 1: {ref_numbers}")
        cited = set()
        for match in re.finditer(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]", before_references):
            for part in match.group(1).split(","):
                part = part.strip()
                if "-" in part:
                    a, b = (int(x.strip()) for x in part.split("-", 1)); cited.update(x for x in range(a, b + 1) if x > 0)
                else:
                    value = int(part)
                    if value > 0:
                        cited.add(value)
        missing_local = sorted(set(ref_numbers) - cited)
        unknown_local = sorted(cited - set(ref_numbers))
        if missing_local or unknown_local:
            errors.append(f"SAP local citation mismatch: uncited={missing_local}, unknown={unknown_local}")

    objective_ids = [obj["objective_id"] for obj in protocol_contract["study_objectives"]]
    for objective_id in objective_ids:
        if not contains_token(protocol_text, objective_id):
            errors.append(f"objective_id missing from protocol: {objective_id}")
        if not contains_token(sap_text, objective_id):
            errors.append(f"objective_id missing from SAP: {objective_id}")

    for item in estimand_bridge["objective_estimands"]:
        if not contains_token(protocol_text, item["estimand_label"]):
            warnings.append(f"estimand label not found verbatim in protocol: {item['objective_id']}")
        if not contains_token(sap_text, item["target_parameter"]):
            warnings.append(f"target parameter not found verbatim in SAP: {item['objective_id']}")

    sample_size = protocol_contract["sample_size_plan"]
    adopted = sample_size["final_adopted_sample_size"]
    max_basis = max(base["adjusted_required_n"] for base in sample_size["bases"])
    if adopted != max_basis:
        errors.append(
            f"final adopted sample size {adopted} does not equal max adjusted basis {max_basis}"
        )
    if not contains_token(protocol_text, str(adopted)):
        errors.append("final adopted sample size not stated in protocol")

    taxonomy = variable_registry["taxonomy"]
    forbidden_adjustments = set(taxonomy.get("mediator", []) + taxonomy.get("collider", []))
    for objective in protocol_contract["study_objectives"]:
        for variable in objective.get("adjustment_strategy", {}).get("adjustment_set", []):
            if variable in forbidden_adjustments:
                errors.append(
                    f"{variable} appears in adjustment set for {objective['objective_id']} but is classified as mediator/collider"
                )
        if objective.get("requires_causal_language"):
            for variable in objective.get("adjustment_strategy", {}).get("adjustment_set", []):
                if not contains_token(protocol_text, variable):
                    warnings.append(
                        f"adjustment variable not named verbatim in protocol body: {objective['objective_id']} -> {variable}"
                    )
                if not contains_token(sap_text, variable):
                    warnings.append(
                        f"adjustment variable not named verbatim in SAP body: {objective['objective_id']} -> {variable}"
                    )
        if objective.get("design_awareness") and not contains_token(sap_text, objective["design_awareness"]):
            warnings.append(f"design-awareness rule not reproduced verbatim in SAP: {objective['objective_id']}")
        if objective.get("interpretation_template") and not contains_token(sap_text, objective["interpretation_template"]):
            warnings.append(f"interpretation template not reproduced verbatim in SAP: {objective['objective_id']}")

    payload = {
        "validator": "consistency_audit",
        "status": summarize_status(errors, warnings),
        "errors": errors,
        "warnings": warnings,
        "input_sha256": sha256_map(
            [protocol_path, sap_path]
            + sorted(contracts_dir.glob("*.json"))
            + sorted(registries_dir.glob("*.json"))
        ),
    }
    write_json(Path(args.output_json), payload)
    if errors:
        raise SystemExit("Consistency audit failed.")

# audit_protocol


def protocol_protocol_duplicate_paragraphs(text: str) -> list[str]:
    counts: dict[str, int] = {}
    for chunk in [part.strip() for part in text.split("\n\n") if part.strip()]:
        if chunk.startswith("- ") or chunk.startswith("|") or re_match_numbered(chunk.splitlines()[0]):
            continue
        counts[chunk] = counts.get(chunk, 0) + 1
    return [chunk[:80] for chunk, count in counts.items() if count > 1 and body_word_count(chunk) > 20]


def protocol_protocol_fivegram_uniqueness(text: str) -> float:
    return sequence_uniqueness(text)


def reference_numbers(text: str) -> set[int]:
    section = find_section(text, "References")
    return {
        int(match.group(1))
        for line in section.splitlines()
        if (match := re.match(r"^\s*(\d+)\.\s+\S", line))
    }


def cited_numbers(text: str) -> set[int]:
    body = text.split("## References", 1)[0]
    found: set[int] = set()
    for match in re.finditer(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]", body):
        token = match.group(1)
        for part in token.split(","):
            part = part.strip()
            if "-" in part:
                start, end = (int(x.strip()) for x in part.split("-", 1))
                found.update(range(start, end + 1))
            else:
                found.add(int(part))
    return found


def main_audit_protocol() -> None:
    parser = argparse.ArgumentParser(description="Run protocol prose quality audit.")
    parser.add_argument("protocol_md")
    parser.add_argument("blueprint_core_json")
    parser.add_argument("blueprint_editorial_json")
    parser.add_argument("output_json")
    args = parser.parse_args()

    protocol_path = Path(args.protocol_md)
    core_path = Path(args.blueprint_core_json)
    editorial_path = Path(args.blueprint_editorial_json)
    text = load_text(protocol_path)
    core = load_json(core_path)
    editorial = load_json(editorial_path)

    fatal_failures: list[str] = []
    strong_warnings: list[str] = []
    editorial_warnings: list[str] = []

    required_sections = [
        "Title and Abstract",
        "Background and Objectives",
        "Study Design and Setting",
        "Participants",
        "Variable Definitions and Measurement",
        "Bias Control and Sample Size",
        "Statistical Methods",
        "Ethics, Data Security, and Governance",
        "Publication and Dissemination",
    ]
    for section in required_sections:
        if not contains_token(text, section):
            fatal_failures.append(f"missing required section: {section}")

    applied_demo = "applied-methods" in str(core.get("protocol_positioning", "")).lower()
    for token in editorial.get("global_forbidden_phrases", []):
        if applied_demo and token.lower() == "workflow":
            continue
        if contains_token(text, token):
            fatal_failures.append(f"forbidden internal language present in protocol body: {token}")

    wc = body_word_count(text)
    if wc < 6000:
        fatal_failures.append(f"protocol body too short: {wc} language-aware content units")
    ngram_score = protocol_fivegram_uniqueness(text)
    if ngram_score < 0.80:
        fatal_failures.append(
            f"protocol has low five-word sequence diversity ({ngram_score:.3f}); content appears repetitively padded"
        )

    unresolved_tokens = [
        "[REQUIRES SPECIFICATION:",
        "validated instrument",
        "large urban catchment",
        "where feasible",
        "as appropriate",
        "to be finalized",
        "not specified",
        "not stated",
        "when the MAR assumption is judged plausible",
        "DAG-informed backdoor",
    ]
    for token in unresolved_tokens:
        if applied_demo and token == "[REQUIRES SPECIFICATION:" and "field launch" in text.lower():
            # Demonstration safety placeholders are evidence of a hard field
            # block; research documents must still resolve them.
            continue
        if contains_token(text, token):
            fatal_failures.append(f"unresolved or vague specification in protocol: {token}")

    critical_signals = {
        "sampling probability trail": ["systematic PPS without replacement", "AAPOR RR3", "HMAC-SHA256", "base weight=71.428571", "with-replacement PSU Taylor", "No real selection is authorized"],
        "weight construction": ["A_hh=1/RR3", "w_hh=w_base*A_hh", "A_person", "adult-person calibration", "epsilon=1e-7", "weighted_type1", "rerake"],
        "measurement chain": ["USDA FoodData Central", "NOVA equation", "Exactly two nonconsecutive", "IPAQ Short Form", "mean of the two closest", "PHQ9-LOCAL-3.0", "field use is blocked"],
        "sample-size calculation": ["Cohen arcsine", "n_exposed=735", "n_comparison=2205", "DEFF_cluster", "Frozen scenario table"],
        "temporal roles": ["Temporal-role diagram", "not a backdoor-identification claim", "BMI/physical activity/sleep", "unmeasured common causes"],
        "display commitments": ["Participant flow shell", "EXP-01", "Figure 6", "weighted adult population"],
        "participant safety": ["safety trigger", "immediate", "escalation", "referral", "confidentiality exception"],
        "data lifecycle": ["audit-trail", "analysis freeze", "retention", "reproducible release"],
        "transparency": ["patient or public involvement", "registration", "sharing plan"],
    }
    if applied_demo:
        for label, signals in critical_signals.items():
            absent = [token for token in signals if not contains_token(text, token)]
            if absent:
                fatal_failures.append(f"incomplete gold-example {label}: missing {', '.join(absent)}")

    malformed = [
        "Version 2.1 for Version 2.1", "governed by before", "Scenario analysis is the registered",
        "will follow report", "handled by do not", "assessed by inspect", "follow compare", "9.99",
    ]
    for phrase in malformed:
        if contains_token(text, phrase):
            fatal_failures.append(f"malformed or obsolete generated prose: {phrase}")

    refs = reference_numbers(text)
    citations = {number for number in cited_numbers(text) if number > 0}
    if len(refs) < 25:
        fatal_failures.append(f"reference list too short: {len(refs)} references (minimum 25)")
    missing_in_body = sorted(refs - citations)
    unknown_citations = sorted(citations - refs)
    if missing_in_body:
        fatal_failures.append(f"references not cited in body: {missing_in_body}")
    if unknown_citations:
        fatal_failures.append(f"in-text citations absent from reference list: {unknown_citations}")
    reference_section = find_section(text, "References")
    stable_ids = len(re.findall(r"(?:doi\.org/|https?://|PMID\s*:?\s*\d+)", reference_section, flags=re.I))
    if refs and stable_ids < len(refs):
        fatal_failures.append(
            f"reference integrity incomplete: {stable_ids}/{len(refs)} entries have a DOI, PMID, or authoritative URL"
        )

    background = find_section(text, "Background")
    if not any(keyword in background.lower() for keyword in ["gap", "needed", "therefore", "because", "rationale"]):
        strong_warnings.append("background section may not complete a necessity argument")

    bias_section = find_section(text, "Bias Control and Sample Size")
    for token in ["confounding", "selection bias", "information bias", "missing-data"]:
        if not contains_token(bias_section, token):
            strong_warnings.append(f"bias section may under-specify: {token}")

    stat_section = find_section(text, "Statistical Methods")
    if "sensitivity" not in stat_section.lower():
        strong_warnings.append("statistical methods section does not clearly include sensitivity analyses")

    governance = find_section(text, "Ethics, Data Security, and Governance")
    for token in ["consent", "data security", "governance"]:
        if not contains_token(governance, token):
            strong_warnings.append(f"governance section may be incomplete: {token}")

    duplicates = protocol_duplicate_paragraphs(text)
    if duplicates:
        editorial_warnings.append("repeated paragraphs detected")

    bullet_lines = sum(1 for line in text.splitlines() if line.startswith("- ") or re_match_numbered(line))
    nonempty = sum(1 for line in text.splitlines() if line.strip())
    if nonempty and bullet_lines / nonempty > 0.35:
        editorial_warnings.append("protocol relies heavily on list formatting relative to prose")

    for chapter in core.get("chapters", []):
        chapter_text = find_section(text, chapter["chapter_title"])
        if not chapter_text:
            continue
        min_words = 50 if chapter["chapter_title"] == "Publication and Dissemination" else 80
        if body_word_count(chapter_text) < min_words:
            strong_warnings.append(f"chapter may be underdeveloped: {chapter['chapter_title']}")

    section_floors = {
        "Background and Objectives": 500,
        "Study Design and Setting": 500,
        "Participants": 300,
        "Variable Definitions and Measurement": 700,
        "Bias Control and Sample Size": 650,
        "Statistical Methods": 450,
        "Field Operations, Participant Safety, and Data Lifecycle": 500,
        "Ethics, Data Security, and Governance": 180,
        "Publication and Dissemination": 180,
    }
    for section_name, floor in section_floors.items():
        count = body_word_count(find_section(text, section_name))
        if count < floor:
            fatal_failures.append(f"section too short: {section_name} has {count} content units (minimum {floor})")

    payload = {
        "validator": "protocol_quality_audit",
        "status": summarize_status(fatal_failures, strong_warnings + editorial_warnings),
        "word_count": wc,
        "content_units": wc,
        "fivegram_uniqueness": round(ngram_score, 4),
        "fatal_failures": fatal_failures,
        "strong_warnings": strong_warnings,
        "editorial_warnings": editorial_warnings,
        "input_sha256": sha256_map([protocol_path, core_path, editorial_path]),
    }
    write_json(Path(args.output_json), payload)
    if fatal_failures:
        raise SystemExit("Protocol quality audit failed.")


def re_match_numbered(line: str) -> bool:
    parts = line.split(".", 1)
    return len(parts) == 2 and parts[0].isdigit()

# audit_sap


def sap_sap_fivegram_uniqueness(text: str) -> float:
    prose = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("|"))
    prose = prose.replace("Pending locked execution", "")
    return sequence_uniqueness(prose)


def sap_sap_duplicate_paragraphs(text: str) -> list[str]:
    seen: dict[str, int] = {}
    for chunk in (part.strip() for part in text.split("\n\n")):
        if (
            body_word_count(chunk) < 24
            or chunk.startswith("|")
            or chunk.startswith("-")
            or chunk.startswith("Target population:")
            or chunk.startswith("Objective summary:")
        ):
            continue
        seen[chunk] = seen.get(chunk, 0) + 1
    return [chunk[:100] for chunk, count in seen.items() if count > 1]


def generic_research_audit(text: str, intake: dict) -> tuple[list[str], list[str], float]:
    """Audit a real-study SAP without importing the gold UPF/PHQ example."""
    errors: list[str] = []
    warnings: list[str] = []
    units = body_word_count(text)
    if units < 7500:
        errors.append(f"SAP body too short: {units} language-aware content units (minimum 7500)")
    required_sections = [
        "Administration, Scope, and Status",
        "Analysis Populations and Data Provenance",
        "Objective Overview",
        "Sample Size, Precision, and Inferential Hierarchy",
        "Objective-aligned Analysis Specifications",
        "Frozen Variable Derivations and Survey Design",
        "Data Quality and Descriptive Analysis",
        "Missing Data and Multiple Imputation Algorithm",
        "Exact Models, Estimation, and Diagnostic Actions",
        "Complete Output Shells",
        "Inferential Conventions and Sensitivity Interpretation",
        "Software, Reproducibility, and Output Control",
        "Deviation Policy and Final Sign-off",
    ]
    for section in required_sections:
        if not find_section(text, section):
            errors.append(f"missing generic research SAP section: {section}")
    for token in ["[REQUIRES SPECIFICATION:", "not specified", "not stated", "where feasible", "when appropriate"]:
        if contains_token(text, token):
            errors.append(f"unresolved or discretionary SAP language: {token}")
    for objective in intake.get("study_objectives", []):
        objective_id = str(objective.get("objective_id", ""))
        if objective_id and not contains_token(text, objective_id):
            errors.append(f"objective chain incomplete: missing {objective_id}")
        strategy = objective.get("adjustment_strategy", {})
        if strategy:
            for level in ("M0", "M1", "M2"):
                if not contains_token(text, level):
                    errors.append(f"{objective_id}: adjustment sequence missing {level}")
            if not str(strategy.get("common_sample_rule", "")).strip():
                errors.append(f"{objective_id}: common-sample adjustment rule missing")
    shell_section = find_section(text, "Complete Output Shells")
    if shell_section.count("## 10.") < 6 or shell_section.count("|") < 30:
        errors.append("generic SAP output shells are incomplete")
    for token in ["source-to-analysis", "reference levels", "diagnostic", "fallback", "run manifest", "input hashes"]:
        if not contains_token(text, token):
            errors.append(f"generic SAP execution chain missing: {token}")
    diversity = sap_fivegram_uniqueness(text)
    if diversity < 0.80:
        errors.append(f"SAP five-word sequence diversity too low: {diversity:.3f}")
    if sap_duplicate_paragraphs(text):
        errors.append("repeated substantive SAP paragraphs detected")
    return errors, warnings, diversity


def main_audit_sap() -> None:
    parser = argparse.ArgumentParser(description="Run complete-body SAP quality audit.")
    parser.add_argument("sap_md")
    parser.add_argument("design_intake_json")
    parser.add_argument("output_json")
    args = parser.parse_args()

    sap_path = Path(args.sap_md)
    intake_path = Path(args.design_intake_json)
    text = sap_path.read_text(encoding="utf-8")
    intake = load_json(intake_path)
    spec, spec_path = load_bound_execution_spec(intake, intake_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not str(spec.get("spec_id", "")).startswith("CSA_V2_EX1_"):
        errors, warnings, diversity = generic_research_audit(text, intake)
        payload = {
            "validator": "sap_generic_research_quality_audit",
            "status": summarize_status(errors, warnings),
            "word_count": body_word_count(text),
            "content_units": body_word_count(text),
            "fivegram_uniqueness": round(diversity, 4),
            "errors": errors,
            "warnings": warnings,
            "input_sha256": {
                str(sap_path.resolve()): hashlib.sha256(sap_path.read_bytes()).hexdigest(),
                str(intake_path.resolve()): hashlib.sha256(intake_path.read_bytes()).hexdigest(),
                str(spec_path.resolve()): hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            },
        }
        write_json(Path(args.output_json), payload)
        if errors:
            raise SystemExit("Generic research SAP quality audit failed.")
        return

    word_count = body_word_count(text)
    if word_count < 7500:
        errors.append(f"SAP body too short: {word_count} language-aware content units (minimum 7500)")

    required_sections = [
        "Administration and Release State",
        "Objective, Estimand, Populations, and Inferential Hierarchy",
        "Sampling, Nonresponse Weights, Calibration, Trimming, and FPC",
        "Reproducible Sample Size and Precision",
        "Frozen Measurements, Derivations, and Temporal Roles",
        "Source-to-Analysis Derivation Dictionary",
        "Missing Data and Variable-by-Variable MI",
        "Complete Model, Fallback, and Sensitivity Registry",
        "Diagnostic Decision Registry",
        "Complete Tables and Figures",
        "Software and No-Discretion Implementation Map",
        "Deviations, Sign-off, and Release Blocks",
    ]
    for section in required_sections:
        if not find_section(text, section):
            errors.append(f"missing SAP section: {section}")

    unresolved = [
        "[REQUIRES SPECIFICATION:", "where feasible", "when appropriate", "if judged plausible",
        "may simplify", "not specified", "not stated", "moderately worse", "statistical review",
        "widen interpretation", "nonidentification is demonstrated", "each covariate", "yes/no per rule",
        "frozen contrast", "registered target scale", "prespecified alternative family",
    ]
    for token in unresolved:
        if contains_token(text, token):
            errors.append(f"unresolved or discretionary SAP language: {token}")

    critical_groups = {
        "administration": ["applied-methods workflow demonstration", "field launch", "outcome-labelled"],
        "survey design": ["AAPOR RR3", "A_hh=1/RR3", "A_person", "27 joint ward x age-band x frame-sex", "epsilon=1e-7", "weighted_type1", "with-replacement PSU Taylor", "no fpc", "no pps"],
        "sample size": ["Cohen arcsine", "h=0.119336906", "n_exposed=735", "n_comparison=2205", "DEFF_cluster", "scenario grid"],
        "derivations": ["USDA FoodData Central", "two valid nonconsecutive", "equality enters the lower", "IPAQ Short Form", "mean of the two closest"],
        "multiple imputation": ["Variable-by-variable", "2l.pmm", "2l.bin", "rank-normalized folded split-Rhat", "max_m=150", "mice::mice.mids", "delta grids", "Tipping-point", "df.complete"],
        "models": ["PRI-01", "DES-01", "DES-02", "EXP-01", "EXP-02", "OUT-01", "INT-01", "MISS-CC", "MISS-EO", "FALL-LB", "FALL-LOGIT"],
        "diagnostics": ["D-WGT", "D-MI", "D-COL", "D-PSU", "D-SPARSE", "D-FIT"],
        "reproducibility": ["renv.lock", "run manifest", "input hashes", "clean-environment", "1e-10"],
    }
    for label, signals in critical_groups.items():
        absent = [signal for signal in signals if not contains_token(text, signal)]
        if absent:
            errors.append(f"incomplete {label}: missing {', '.join(absent)}")

    shell_names = ["Table 1 participant flow", "Table 2 participant characteristics", "Table 3 missingness and imputation", "Table 4 primary and model registry results", "Table 5 missing-data and delta results", "Table 6 sensitivity registry", "Table 7 fallback attempt ledger", "Table 8 diagnostic decision ledger", "Figure shells"]
    for shell in shell_names:
        section = find_section(text, shell)
        if not section or ("Figure" not in shell and section.count("|") < 10):
            errors.append(f"missing or incomplete output shell: {shell}")

    for objective in intake.get("study_objectives", []):
        objective_id = str(objective.get("objective_id", ""))
        for token in [
            objective_id, str(objective.get("estimand_label", "")), str(objective.get("interpretation_template", "")),
        ]:
            if token and not contains_token(text, token):
                errors.append(f"objective chain incomplete for {objective_id}: missing {token[:80]}")

    diversity = sap_fivegram_uniqueness(text)
    if diversity < 0.80:
        errors.append(f"SAP five-word sequence diversity too low: {diversity:.3f}")
    duplicates = sap_duplicate_paragraphs(text)
    if duplicates:
        errors.append("repeated substantive SAP paragraphs detected")

    # Recompute every sample-size scenario from the frozen formula.
    z_alpha, z_power, ratio = 1.959963984540054, 0.8416212335729143, 3
    for row in spec["sample_size"]["scenario_rows"]:
        p0, p1 = float(row["p0"]), float(row["p1"])
        h = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p0))
        n_exp = math.ceil((z_alpha + z_power) ** 2 * (1 + 1 / ratio) / h ** 2)
        exact = n_exp + ratio * n_exp
        rounded = math.ceil(exact / 100) * 100
        final_n = math.ceil((rounded * 1.5 / 0.90) / 100) * 100
        if exact != int(row["exact_raw"]) or rounded != int(row["rounded_raw"]) or final_n != int(row["final_n"]):
            errors.append(f"sample-size scenario does not reproduce: p0={p0}, p1={p1}")

    for model in spec["models"]:
        for field in ["id", "role", "population", "exposure_outcome", "formula", "family", "design", "mi", "effect", "output"]:
            if not str(model.get(field, "")).strip():
                errors.append(f"model {model.get('id', 'UNKNOWN')} missing {field}")
        model_definition = " ".join(str(model.get(field, "")) for field in ["population", "exposure_outcome", "formula", "family", "design", "mi"]).lower()
        for shorthand in ["same", "pri-01 formula", "all pri covariates", "primary design", "replace upf"]:
            if shorthand in model_definition:
                errors.append(f"model {model.get('id', 'UNKNOWN')} uses non-executable shorthand: {shorthand}")
        if "~" not in str(model.get("formula", "")):
            errors.append(f"model {model.get('id', 'UNKNOWN')} lacks a complete executable formula")
        if not contains_token(text, str(model["id"])) or not contains_token(text, str(model["output"])):
            errors.append(f"model/output binding absent from SAP: {model['id']}")
    for row in spec["mi"]["variable_rows"]:
        if not contains_token(text, row["variable"]) or not contains_token(text, row["method"]):
            errors.append(f"MI row absent or incomplete: {row['variable']}")

    reference_section = find_section(text, "References")
    for local_number, source_id in enumerate(spec["sap_reference_ids"], 1):
        if not re.search(rf"(?m)^\s*{local_number}\.\s+", reference_section):
            errors.append(f"SAP local reference missing: {local_number} (source reference {source_id})")
        if not re.search(rf"\[[^\]]*\b{local_number}\b[^\]]*\]", text.split("# 12. References", 1)[0]):
            errors.append(f"SAP local reference not cited in body: {local_number} (source reference {source_id})")
    listed_numbers = [int(x) for x in re.findall(r"(?m)^\s*(\d+)\.\s+", reference_section)]
    expected_numbers = list(range(1, len(spec["sap_reference_ids"]) + 1))
    if listed_numbers != expected_numbers:
        errors.append(f"SAP references are not consecutively numbered: expected {expected_numbers}, observed {listed_numbers}")

    section_floors = {
        "Sampling, Nonresponse Weights, Calibration, Trimming, and FPC": 700,
        "Reproducible Sample Size and Precision": 340,
        "Frozen Measurements, Derivations, and Temporal Roles": 500,
        "Missing Data and Variable-by-Variable MI": 1000,
        "Complete Model, Fallback, and Sensitivity Registry": 900,
        "Complete Tables and Figures": 1400,
        "Software and No-Discretion Implementation Map": 350,
    }
    for section, floor in section_floors.items():
        count = body_word_count(find_section(text, section))
        if count < floor:
            errors.append(f"SAP section too short: {section} has {count} content units (minimum {floor})")

    payload = {
        "validator": "sap_complete_body_quality_audit",
        "status": summarize_status(errors, warnings),
        "word_count": word_count,
        "content_units": word_count,
        "fivegram_uniqueness": round(diversity, 4),
        "errors": errors,
        "warnings": warnings,
        "input_sha256": {
            str(sap_path.resolve()): hashlib.sha256(sap_path.read_bytes()).hexdigest(),
            str(intake_path.resolve()): hashlib.sha256(intake_path.read_bytes()).hexdigest(),
            str(spec_path.resolve()): hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        },
    }
    write_json(Path(args.output_json), payload)
    if errors:
        raise SystemExit("SAP complete-body quality audit failed.")

# dry_run_execution


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main_dry_run_execution() -> None:
    parser = argparse.ArgumentParser(description="Hash-bound planning and executable synthetic R acceptance run.")
    parser.add_argument("design_intake_json")
    parser.add_argument("output_json")
    args = parser.parse_args()
    intake_path, output_path = Path(args.design_intake_json), Path(args.output_json)
    intake = load_json(intake_path)
    spec, spec_path = load_bound_execution_spec(intake, intake_path)
    checks: list[dict] = []

    def check(name: str, condition: bool, evidence: object) -> None:
        checks.append({"check": name, "status": "pass" if condition else "fail", "evidence": evidence})

    if not str(spec.get("spec_id", "")).startswith("CSA_V2_EX1_"):
        asset_paths: dict[str, Path] = {}
        asset_results = []
        for asset in spec.get("bound_assets", []):
            path = (spec_path.parent / str(asset.get("path", ""))).resolve()
            actual = digest(path) if path.is_file() else "MISSING"
            expected = str(asset.get("sha256", "")).lower()
            match = bool(expected) and actual == expected
            asset_paths[str(asset.get("asset_id", path.name))] = path
            asset_results.append({"path": str(path), "expected": expected, "actual": actual, "match": match})
        check("all_bound_asset_hashes_match", bool(asset_results) and all(x["match"] for x in asset_results), asset_results)

        models = spec.get("models", [])
        complete_models = bool(models) and all(
            str(model.get("id", "")).strip()
            and str(model.get("objective_id", "")).strip()
            and "~" in str(model.get("formula", ""))
            and str(model.get("family", "")).strip()
            and str(model.get("variance", model.get("design", ""))).strip()
            and str(model.get("effect", "")).strip()
            and str(model.get("output", "")).strip()
            and not any(
                shorthand in " ".join(str(value) for value in model.values()).lower()
                for shorthand in ("same as primary", "all covariates", "replace exposure", "primary design")
            )
            for model in models
        )
        check("models_are_independently_executable", complete_models, {"model_count": len(models)})
        acceptance = spec.get("acceptance_test", {})
        command = acceptance.get("command", []) if isinstance(acceptance, dict) else []
        check("generic_acceptance_command_declared", isinstance(command, list) and bool(command), command)
        run = None
        if isinstance(command, list) and command:
            resolved_command = [
                str((spec_path.parent / token).resolve()) if index > 0 and not Path(str(token)).is_absolute() and (spec_path.parent / str(token)).exists() else str(token)
                for index, token in enumerate(command)
            ]
            run = subprocess.run(resolved_command, cwd=spec_path.parent, text=True, capture_output=True, check=False)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path = output_path.parent / "generic_acceptance_stdout.txt"
            stderr_path = output_path.parent / "generic_acceptance_stderr.txt"
            stdout_path.write_text(run.stdout, encoding="utf-8")
            stderr_path.write_text(run.stderr, encoding="utf-8")
            success_token = str(acceptance.get("success_token", "")).strip()
            finite_pattern = str(acceptance.get("finite_estimate_se_pattern", "")).strip()
            finite_match = re.search(finite_pattern, run.stdout) if finite_pattern else None
            finite_ok = bool(finite_match) and all(
                math.isfinite(float(value)) for value in finite_match.groups()[:2]
            ) and float(finite_match.group(2)) > 0
            check(
                "generic_synthetic_end_to_end_acceptance",
                run.returncode == 0 and bool(success_token) and success_token in run.stdout and finite_ok,
                {"command": resolved_command, "returncode": run.returncode, "success_token": success_token, "finite_match": finite_match.group(0) if finite_match else "missing"},
            )
        errors = [x for x in checks if x["status"] == "fail"]
        payload = {
            "validator": "architect_generic_execution_spec_dry_run_v1",
            "scope": "hash bindings, independently executable models, and study-specific synthetic acceptance; not empirical validation",
            "status": "fail" if errors else "pass",
            "checks": checks,
            "input_sha256": {
                str(intake_path.resolve()): digest(intake_path),
                str(spec_path.resolve()): digest(spec_path),
                **{str(path): digest(path) for path in asset_paths.values() if path.is_file()},
            },
        }
        write_json(output_path, payload)
        if errors:
            raise SystemExit("Generic executable dry run failed: " + ", ".join(x["check"] for x in errors))
        return

    check("canonical_applied_methods_identity", intake.get("project_mode") == "applied_methods" and
          spec.get("administration", {}).get("project_mode") == "applied_methods" and
          "not a real study" in spec.get("status", ""),
          {"intake": intake.get("project_mode"), "spec": spec.get("status")})

    asset_paths: dict[str, Path] = {}
    asset_results = []
    for asset in spec["bound_assets"]:
        path = spec_path.parent / asset["path"]
        actual = digest(path) if path.is_file() else "MISSING"
        ok = actual == asset["sha256"]
        asset_paths[asset["asset_id"]] = path
        asset_results.append({"id": asset["asset_id"], "path": str(path), "expected": asset["sha256"], "actual": actual, "match": ok})
    check("all_bound_asset_hashes_match", all(x["match"] for x in asset_results), asset_results)

    reproduced = []
    for row in spec["sample_size"]["scenario_rows"]:
        p0, p1 = float(row["p0"]), float(row["p1"])
        h = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p0))
        n_exp = math.ceil((1.959963984540054 + 0.8416212335729143) ** 2 * (1 + 1 / 3) / h**2)
        exact, rounded = n_exp * 4, math.ceil(n_exp * 4 / 100) * 100
        final_n = math.ceil((rounded * 1.5 / .90) / 100) * 100
        reproduced.append({"p0": p0, "p1": p1, "exact": exact, "final": final_n,
                           "matches": exact == row["exact_raw"] and rounded == row["rounded_raw"] and final_n == row["final_n"]})
    check("sample_size_grid_reproduces", all(x["matches"] for x in reproduced), reproduced)

    with asset_paths["CALIBRATION_CONTROLS"].open(newline="", encoding="utf-8") as handle:
        controls = list(csv.DictReader(handle))
    ids = [x["control_id"] for x in controls]
    check("calibration_controls_are_exact_joint_27_cells",
          len(controls) == 27 and len(set(ids)) == 27 and ids == [f"C{i:02d}" for i in range(1, 28)] and
          sum(int(x["total"]) for x in controls) == 40000 and
          len({(x["ward"], x["age_band"], x["frame_sex"]) for x in controls}) == 27,
          {"cells": len(controls), "total": sum(int(x["total"]) for x in controls), "first_last": [ids[0], ids[-1]]})

    sampling_text = " ".join(str(v) for v in spec["sampling"].values())
    design_ok = ("ids=~psu_id,strata=~ward,weights=~final_weight" in sampling_text.replace(" ", "") and
                 "excluded from primary" in spec["sampling"]["fpc"] and "Do not pass fpc or pps" in spec["sampling"]["fpc"])
    check("wr_psu_taylor_without_fpc_or_pps", design_ok, spec["sampling"]["primary_design_call"])
    check("full_nonresponse_weight_chain", all(x in sampling_text for x in
          ["A_hh=1/RR3", "w_hh=w_base*A_hh", "A_person=sum(w_hh selected eligible)", "w_person=w_hh*A_person", "final_weight=rerake"]),
          spec["sampling"]["weight_chain"])
    check("separate_weighted_cutpoint_and_spline_algorithms",
          "weighted_type1" in spec["sampling"]["quantile_rule"] and
          "weighted_linear_quantile" in spec["sampling"]["spline_quantile_rule"] and
          "stats::quantile" not in spec["sampling"]["quantile_rule"],
          {"classification": spec["sampling"]["quantile_rule"], "spline": spec["sampling"]["spline_quantile_rule"]})

    deriv = load_json(asset_paths["DERIVATION_DICTIONARY"])
    deriv_names = {x["name"] for x in deriv["variables"]}
    required_deriv = {"psu_id","ward","base_weight","A_hh","A_person","final_weight","item_kcal","day_upf_pct",
                      "upf_pct","upf_q4","upf_q5","phq9_total","phq9_ge10","age","sex","education","income",
                      "smoking","alcohol_g_day","chronic_count","psychotropic_med","employment","marital","season",
                      "energy_kcal_day","activity_met_min_week","bmi","sleep_hours"}
    cards_complete = all(all(k in card and card[k] not in (None, "") for k in
                             ["name","role","source_fields","source_range","missing_codes","time_window","components","formula","analysis_range","primary","sensitivity"])
                         for card in deriv["variables"])
    check("derivation_dictionary_complete", required_deriv.issubset(deriv_names) and cards_complete and "energy_rules" in deriv,
          {"required": len(required_deriv), "present": len(deriv_names), "cards_complete": cards_complete})

    safety = load_json(asset_paths["SAFETY_SOP_DEMO"])
    check("safety_demo_hard_block_and_complete_schema",
          safety.get("field_launch_block") is True and safety.get("status") == "NON_FIELD_READY_DEMONSTRATION_ONLY" and
          len(safety.get("triage_questions", [])) >= 4 and all(k in safety for k in
          ["owner","version","branches","roles","coverage_schema","contact_schema","documentation_schema","release_requirements","prohibited"]) and
          "REQUIRED_REAL_VALUE" in str(safety), safety.get("block_reason"))

    mi = load_json(asset_paths["MI_SPEC"])
    check("exact_mi_contract",
          mi["initial"] == {"m":50,"maxit":30,"seed":20270413} and mi["continuation"]["additional_maxit"] == 50 and
          mi["continuation"]["function"] == "mice::mice.mids" and
          all(mi["method"][v] == "" for v in ["upf_q4","phq9_ge10","season","energy_kcal_day","psu_id","ward","final_weight"]) and
          "rank-normalized folded split-Rhat" in mi["diagnostics"]["rhat"] and "survey::degf" in mi["pooling"]["df_complete"] and
          len(mi["delta"]["ids"]) == len(set(mi["delta"]["ids"])) == 10,
          {"visitSequence": mi["visitSequence"], "methods": mi["method"], "continuation": mi["continuation"]})

    model_ids = {x["id"] for x in spec["models"]}
    required_models = {"PRI-01","DES-01","DES-02","EXP-01","EXP-02","OUT-01","INT-01","MISS-CC","MISS-EO","FALL-LB","FALL-LOGIT"}
    forbidden = ("rcs(age", "all three stage fpc", "pps='brewer'", "percentile 95", "odds-ratio")
    full_tokens = ("age_ns1","age_ns2","age_ns3","sex","education","income","smoking","alcohol_g_day",
                   "chronic_count","psychotropic_med","employment","marital","season","energy_kcal_day")
    model_ok = required_models.issubset(model_ids) and all("~" in m["formula"] and
        all(t in m["formula"] for t in full_tokens) and not any(f in str(m).lower() for f in forbidden) and m["output"] for m in spec["models"])
    check("models_full_and_design_consistent", model_ok, {m["id"]: {"formula":m["formula"],"design":m["design"]} for m in spec["models"]})
    fall = next(x for x in spec["models"] if x["id"] == "FALL-LOGIT")
    check("one_fall_logit_estimand_and_nesting", "marginal PR" in fall["effect"] and "MI outer" in fall["mi"] and
          "bootstrap" in fall["mi"] and "Rubin" in fall["mi"] and "no percentile CI" in fall["effect"], fall)
    diag = {x["id"]: x for x in spec["diagnostics"]}
    check("sparse_is_diagnostic_fit_is_sole_fallback_trigger", "do not activate" in diag["D-SPARSE"]["action"] and
          "sole trigger" in diag["D-FIT"]["action"] and "D-FIT alone" in spec["fallback_sequence"], diag)
    shells = spec.get("output_shells", {})
    check("genuine_tables_7_8_and_delta_interaction_shells", all(k in shells for k in
          ["Table7_fallback_attempt_ledger","Table8_diagnostic_decisions","interaction","delta"]) and
          "release_status" in shells.get("Table7_fallback_attempt_ledger", []) and
          "mandatory_action" in shells.get("Table8_diagnostic_decisions", []), shells)
    check("environment_lock_bound", asset_paths["ENVIRONMENT_LOCK"].is_file() and
          all(x in asset_paths["ENVIRONMENT_LOCK"].read_text() for x in ["survey","mice","miceadds","mitools"]),
          str(asset_paths["ENVIRONMENT_LOCK"]))

    r_cmd = ["Rscript", str(asset_paths["R_ACCEPTANCE_TEST"]), str(spec_path.parent)]
    run = subprocess.run(r_cmd, text=True, capture_output=True, check=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    (output_path.parent / "r_acceptance_stdout.txt").write_text(run.stdout, encoding="utf-8")
    (output_path.parent / "r_acceptance_stderr.txt").write_text(run.stderr, encoding="utf-8")
    session = re.search(r"SESSION_INFO_BEGIN\n(.*?)SESSION_INFO_END", run.stdout, re.S)
    (output_path.parent / "r_session_info.txt").write_text((session.group(1) if session else "MISSING") + "\n", encoding="utf-8")
    finite = re.search(r"FINITE_LOG_PR=([-+0-9.eE]+) FINITE_SE=([-+0-9.eE]+) STANDARDIZED_PR=([-+0-9.eE]+) DESIGN_DF=(\d+)", run.stdout)
    check("synthetic_r_end_to_end_acceptance", run.returncode == 0 and "ARCHITECT_R_ACCEPTANCE=PASS" in run.stdout and
          "MICE_SMOKE_TEST=PASS" in run.stdout and finite is not None and all(math.isfinite(float(x)) for x in finite.groups()[:3]) and float(finite.group(2)) > 0,
          {"command": r_cmd, "returncode": run.returncode, "finite_line": finite.group(0) if finite else "missing",
           "stdout_file": str(output_path.parent / "r_acceptance_stdout.txt"), "stderr_file": str(output_path.parent / "r_acceptance_stderr.txt")})

    errors = [x for x in checks if x["status"] == "fail"]
    payload = {
        "validator":"architect_execution_spec_executable_dry_run_v3",
        "scope":"hash, cross-contract, exact algorithm and synthetic R execution acceptance; not empirical validation or field authorization",
        "status":"fail" if errors else "pass",
        "checks":checks,
        "r_acceptance":{"stdout_sha256":digest(output_path.parent / "r_acceptance_stdout.txt"),
                        "stderr_sha256":digest(output_path.parent / "r_acceptance_stderr.txt"),
                        "session_info_sha256":digest(output_path.parent / "r_session_info.txt")},
        "input_sha256":{str(intake_path.resolve()):digest(intake_path),str(spec_path.resolve()):digest(spec_path),
                        **{str(p.resolve()):digest(p) for p in asset_paths.values()}},
    }
    write_json(output_path, payload)
    if errors:
        raise SystemExit("Executable dry run failed: " + ", ".join(x["check"] for x in errors))


COMMANDS = {
    "audit_consistency": main_audit_consistency,
    "audit_protocol": main_audit_protocol,
    "audit_sap": main_audit_sap,
    "dry_run_execution": main_dry_run_execution,
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
