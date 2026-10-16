#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/retrieval.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# build_search_plan
CORE_SOURCES = [
    "OpenAlex",
    "PubMed/MEDLINE",
    "Semantic Scholar",
    "Europe PMC",
    "medRxiv",
    "bioRxiv",
    "Embase",
    "Web of Science",
]
PRIMARY_SOURCES = [
    "PubMed/MEDLINE",
    "OpenAlex",
    "Europe PMC",
    "Semantic Scholar",
    "Embase",
    "Web of Science",
]
PREPRINT_SOURCES = ["medRxiv", "bioRxiv"]
CLINICAL_QUESTION_TYPES = {
    "treatment_strategy_comparison",
    "prognosis",
    "exposure_outcome_association",
    "guideline_to_evidence",
}
PREPRINT_SKIP_FAMILIES = {
    "population_setting",
    "measurement_validation",
    "design_estimand",
    "confounder_logic",
    "contradiction_null_findings",
    "citation_chaining",
}
CONTINUE_HINTS = (
    "continue",
    "continu",
    "persist",
    "maintain",
    "ongoing",
    "stay on",
)
STOP_HINTS = (
    "discontinu",
    "stop",
    "cessat",
    "cease",
    "withdraw",
    "terminat",
    "deprescrib",
    "hold",
)
QUESTION_TYPES = {
    "exposure_outcome_association",
    "treatment_strategy_comparison",
    "prognosis",
    "diagnostic_measurement",
    "mechanism_mediation",
    "guideline_to_evidence",
    "methods_estimand",
}
REVIEW_GOALS = {
    "background_landscape",
    "decision_support",
    "protocol_support",
    "manuscript_positioning",
    "gap_mapping",
    "methods_support",
}
QUESTION_TYPE_DESIGN_TERMS: dict[str, list[str]] = {
    "exposure_outcome_association": [
        "cohort", "case-control", "cross-sectional",
        "odds ratio", "risk ratio", "hazard ratio",
    ],
    "treatment_strategy_comparison": [
        "target trial emulation", "active comparator", "prior user design",
        "grace period", "intention-to-treat", "per-protocol",
        "new user design", "incident user",
    ],
    "prognosis": [
        "cohort", "prospective", "time-to-event",
        "survival analysis", "competing risk", "hazard ratio", "Kaplan-Meier",
    ],
    "diagnostic_measurement": [
        "diagnostic accuracy", "sensitivity", "specificity",
        "AUC", "ROC", "positive predictive value", "kappa", "agreement",
    ],
    "mechanism_mediation": [
        "mechanism", "pathway", "mediation", "biological plausibility",
        "intermediate", "causal pathway",
    ],
    "guideline_to_evidence": [
        "clinical guideline", "practice recommendation",
        "evidence synthesis", "systematic review", "meta-analysis",
    ],
    "methods_estimand": [
        "estimand", "target trial", "DAG", "directed acyclic graph",
        "confounding", "instrumental variable", "causal inference",
    ],
}
POPULATION_LIKE_TERMS = (
    "adult",
    "adults",
    "older",
    "elderly",
    "geriatric",
    "frail",
    "nursing home",
    "very elderly",
    "aged ",
    "years",
    "population",
    "community-dwelling",
    "hospital",
    "care home",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = (value or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def concise_seed_terms(values: list[str]) -> list[str]:
    seeds: list[str] = []
    for value in values:
        value = (value or "").strip()
        if not value:
            continue
        lowered = value.lower()
        word_count = len(value.split())
        if any(token in lowered for token in [" versus ", " vs ", "compared with", "compared to"]):
            continue
        if word_count > 8:
            continue
        seeds.append(value)
    return unique_nonempty(seeds)


def split_enumerated_terms(value: str) -> list[str]:
    """Split comma/semicolon-separated topic prose into queryable phrases."""
    value = (value or "").strip()
    if not value:
        return []
    if "," not in value and ";" not in value:
        return []
    parts = []
    for raw_part in value.replace(";", ",").split(","):
        part = re.sub(r"^(and|or)\s+", "", raw_part.strip(), flags=re.IGNORECASE)
        if part:
            parts.append(part)
    return unique_nonempty(parts)


def split_long_phrase(value: str) -> list[str]:
    """Recover shorter query terms from long natural-language labels.

    This is intentionally conservative. We only split on "with" when the source
    phrase is long enough that using it verbatim as an exact search phrase would
    likely suppress retrieval.
    """
    value = (value or "").strip()
    if not value:
        return []
    lowered = value.lower()
    pieces: list[str] = []
    if len(value.split()) > 8 and " with " in lowered:
        left, right = re.split(r"\bwith\b", value, maxsplit=1, flags=re.IGNORECASE)
        pieces.extend([left.strip(), right.strip()])
    return unique_nonempty([piece for piece in pieces if piece and len(piece.split()) <= 8])


def expand_query_terms(*values: str) -> list[str]:
    """Turn free-text topic fields into shorter, queryable seed terms."""
    expanded: list[str] = []
    for value in values:
        expanded.extend(concise_seed_terms([value]))
        expanded.extend(split_enumerated_terms(value))
        expanded.extend(split_long_phrase(value))
    return unique_nonempty(expanded)


def looks_like_population_term(term: str) -> bool:
    lowered = (term or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in POPULATION_LIKE_TERMS)


def filter_exposure_terms_for_question_type(question_type: str, terms: list[str]) -> list[str]:
    clean = unique_nonempty(terms)
    if question_type != "treatment_strategy_comparison":
        return clean
    return [term for term in clean if not looks_like_population_term(term)]


def quoted(term: str) -> str:
    term = (term or "").strip()
    if not term:
        return ""
    if '"' in term:
        return term
    return f'"{term}"'


def boolean_group(terms: list[str], field_suffix: str = "") -> str:
    clean = [t for t in terms if t]
    if not clean:
        return ""
    pieces = [f"{quoted(term)}{field_suffix}" for term in clean]
    if len(pieces) == 1:
        return pieces[0]
    return "(" + " OR ".join(pieces) + ")"


def plain_group(terms: list[str]) -> str:
    clean = [quoted(term) for term in terms if term]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return "(" + " OR ".join(clean) + ")"


def join_and(parts: list[str]) -> str:
    clean = [part for part in parts if part]
    return " AND ".join(clean)


def contains_hint(text: str, hints: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in hints)


def infer_strategy_terms(cfg: dict, *texts: str) -> list[str]:
    """Return strategy comparison vocabulary for the query plan.

    If topic_config provides a ``strategy_vocabulary`` block with ``continue``
    and/or ``stop`` sub-lists, those override the hint-based inference so the
    caller can supply domain-appropriate synonyms without editing this file.
    """
    vocab = cfg.get("strategy_vocabulary") or {}
    if vocab:
        continue_v = list(vocab.get("continue") or [])
        stop_v = list(vocab.get("stop") or [])
        terms = continue_v + stop_v
        if terms:
            terms.extend(["versus", "comparison"])
            return unique_nonempty(terms)

    blob = " ".join(texts).lower()
    terms: list[str] = []
    if contains_hint(blob, CONTINUE_HINTS):
        terms.extend(["continuing", "continued use", "persistence"])
    if contains_hint(blob, STOP_HINTS):
        terms.extend(["discontinuation", "stopping", "cessation"])
    if terms:
        terms.extend(["versus", "comparison"])
    return unique_nonempty(terms)


def infer_trigger_terms(cfg: dict) -> list[str]:
    """Return clinical trigger vocabulary for the query plan.

    Terms are read exclusively from ``topic_config.json`` via the
    ``trigger_vocabulary`` list.  No domain-specific defaults are hard-coded
    here so the planner stays topic-agnostic.
    """
    vocab = cfg.get("trigger_vocabulary") or []
    return unique_nonempty(list(vocab))


def build_source_query(source: str, exposure_terms: list[str], outcome_terms: list[str], population_terms: list[str], extra_terms: list[str]) -> str:
    if source == "PubMed/MEDLINE":
        return join_and([
            boolean_group(exposure_terms, "[Title/Abstract]"),
            boolean_group(outcome_terms, "[Title/Abstract]"),
            boolean_group(population_terms, "[Title/Abstract]"),
            boolean_group(extra_terms, "[Title/Abstract]"),
        ])
    if source == "Embase":
        return join_and([
            boolean_group(exposure_terms, ":ti,ab"),
            boolean_group(outcome_terms, ":ti,ab"),
            boolean_group(population_terms, ":ti,ab"),
            boolean_group(extra_terms, ":ti,ab"),
        ])
    if source == "Web of Science":
        inner = join_and([
            plain_group(exposure_terms),
            plain_group(outcome_terms),
            plain_group(population_terms),
            plain_group(extra_terms),
        ])
        return f"TS=({inner})" if inner else ""
    if source == "Europe PMC":
        def _epmc_group(terms: list[str]) -> str:
            clean = [t for t in terms if t]
            if not clean:
                return ""
            pieces = [f'(TITLE:"{t}" OR ABSTRACT:"{t}")' for t in clean]
            if len(pieces) == 1:
                return pieces[0]
            return "(" + " OR ".join(pieces) + ")"
        return join_and([
            _epmc_group(exposure_terms),
            _epmc_group(outcome_terms),
            _epmc_group(population_terms),
            _epmc_group(extra_terms),
        ])
    # OpenAlex, Semantic Scholar, medRxiv, bioRxiv: plain free-text query
    return join_and([
        plain_group(exposure_terms),
        plain_group(outcome_terms),
        plain_group(population_terms),
        plain_group(extra_terms),
    ])


def default_date_limit(cfg: dict) -> str:
    time_range = cfg.get("time_range")
    if isinstance(time_range, list) and len(time_range) == 2:
        return f"{time_range[0]}-{time_range[1]}"
    return ""


def retrieval_target(base: int, review_goal: str) -> str:
    """Adjust recommended retrieval target based on review goal."""
    if review_goal == "background_landscape":
        return str(max(base, 50))
    if review_goal in {"decision_support", "protocol_support"}:
        return str(base)
    if review_goal == "gap_mapping":
        return str(base)
    return str(base)


def build_query_plan(cfg: dict) -> list[dict[str, str]]:
    exposure = (cfg.get("exposure") or "").strip()
    comparison = (cfg.get("comparison") or "").strip()
    outcome = (cfg.get("outcome") or "").strip()
    population = (cfg.get("population") or "").strip()
    design_type = (cfg.get("design_type") or "").strip()
    primary_estimand = (cfg.get("primary_estimand") or "").strip()
    mediator = (cfg.get("candidate_mediator") or "").strip()
    modifier = (cfg.get("candidate_modifier") or "").strip()
    confounders = cfg.get("confounders_core") or []
    harvest = cfg.get("harvest") or {}

    question_type = (cfg.get("question_type") or "").strip()
    review_goal = (cfg.get("review_goal") or "").strip()

    exposure_terms = filter_exposure_terms_for_question_type(
        question_type,
        concise_seed_terms([exposure, comparison]) + list(harvest.get("exposures") or []),
    )
    outcome_terms = unique_nonempty(
        expand_query_terms(outcome, harvest.get("outcome", "")) + list(harvest.get("outcomes") or [])
    )
    population_terms = unique_nonempty(
        expand_query_terms(population, harvest.get("population", ""))
    )
    if not outcome_terms and outcome:
        outcome_terms = [outcome]
    if not population_terms and population:
        population_terms = [population]

    # Strategy terms: only inferred when question_type is treatment_strategy_comparison,
    # or when the topic config text contains continuation/stopping language.
    if question_type == "treatment_strategy_comparison":
        strategy_terms = infer_strategy_terms(
            cfg, exposure, comparison, " ".join(harvest.get("exposures") or [])
        )
        if not strategy_terms:
            # Fallback: at least include generic strategy vocabulary
            strategy_terms = unique_nonempty(["continuing", "discontinuation", "versus", "comparison"])
    else:
        strategy_terms = infer_strategy_terms(
            cfg, exposure, comparison, " ".join(harvest.get("exposures") or [])
        )

    # Trigger terms: sourced exclusively from topic_config, no hardcoded defaults.
    trigger_terms = infer_trigger_terms(cfg)

    specific_outcomes = [
        term
        for term in outcome_terms
        if term.lower() not in {"clinical outcomes", "clinical outcome", "multiple clinical outcomes", "outcomes"}
    ]

    # Design terms for the design_estimand family are routed by question_type.
    # If question_type is absent, use only what the config explicitly provides.
    if question_type and question_type in QUESTION_TYPE_DESIGN_TERMS:
        type_design_terms = QUESTION_TYPE_DESIGN_TERMS[question_type]
    else:
        type_design_terms = []
    design_extra_terms = unique_nonempty([design_type, primary_estimand] + type_design_terms)

    plans = [
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "direct association",
            "query_family": "direct_association",
            "extra_terms": [],
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "map the main exposure-outcome literature",
        },
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "population and setting",
            "query_family": "population_setting",
            "extra_terms": population_terms[:3],
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "recover setting-specific and population-specific papers",
        },
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "measurement and validation",
            "query_family": "measurement_validation",
            "extra_terms": ["measurement", "validation", "scale", "instrument", "threshold"],
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "recover instrument, threshold, and psychometric evidence",
        },
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "design and estimand",
            "query_family": "design_estimand",
            "extra_terms": design_extra_terms,
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "recover design-specific methods and estimand choices",
        },
    ]

    # strategy_comparison is activated unconditionally when question_type is
    # treatment_strategy_comparison, or when strategy terms were inferred from the config text.
    if strategy_terms:
        strategy_extra = unique_nonempty(strategy_terms + ["target trial emulation", "grace period", "active comparator"])
        plans.append(
            {
                "search_round": "1",
                "parent_search_id": "",
                "concept_focus": "treatment strategy comparison",
                "query_family": "strategy_comparison",
                "extra_terms": strategy_extra,
                "recommended_retrieval_target": retrieval_target(30, review_goal),
                "rationale_trigger": "baseline field mapping for continuation versus discontinuation questions",
                "scope": "recover explicit continue-versus-stop comparative studies",
            }
        )

    if mediator or question_type == "mechanism_mediation":
        mechanism_extra = unique_nonempty([mediator, "mechanism", "mediation", "pathway"])
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "mechanism or mediation",
                "query_family": "mechanism_mediation",
                "extra_terms": mechanism_extra,
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers suggested mediator or pathway language",
                "scope": "recover pathway evidence that sharpens interpretation boundaries",
            }
        )

    if modifier:
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "effect modification and subgroups",
                "query_family": "modifier_subgroup",
                "extra_terms": [modifier, "effect modification", "interaction", "subgroup"],
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers suggested subgroup heterogeneity",
                "scope": "recover modifier and subgroup evidence",
            }
        )

    if confounders:
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "confounding structure",
                "query_family": "confounder_logic",
                "extra_terms": unique_nonempty(list(confounders)[:4] + ["confounding", "adjustment", "causal model"]),
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers revealed dense confounding structure",
                "scope": "recover papers clarifying confounders, mediators, and colliders",
            }
        )

    if strategy_terms:
        trigger_extra = unique_nonempty(
            strategy_terms + trigger_terms + ["target trial emulation", "treatment strategy"]
        )
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "clinical trigger and treatment strategy",
                "query_family": "clinical_trigger_strategy",
                "extra_terms": trigger_extra,
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers revealed a clinically triggered stop-versus-continue decision",
                "scope": "recover trigger-specific treatment strategy comparisons",
            }
        )

        for specific_outcome in specific_outcomes[:5]:
            plans.append(
                {
                    "search_round": "2",
                    "parent_search_id": "round1-anchor-reading",
                    "concept_focus": f"strategy comparison for outcome: {specific_outcome}",
                    "query_family": "outcome_specific_strategy",
                    "extra_terms": unique_nonempty([specific_outcome] + strategy_terms + trigger_terms),
                    "recommended_retrieval_target": "15",
                    "rationale_trigger": f"anchor reading suggested focused follow-up for outcome: {specific_outcome}",
                    "scope": "recover outcome-specific comparative strategy evidence",
                }
            )

    # gap_mapping goal boosts contradiction retrieval target
    contradiction_target = retrieval_target(30 if review_goal == "gap_mapping" else 20, review_goal)
    plans.append(
        {
            "search_round": "2",
            "parent_search_id": "round1-anchor-reading",
            "concept_focus": "contradictions and null findings",
            "query_family": "contradiction_null_findings",
            "extra_terms": ["null", "inconsistent", "contradictory", "heterogeneity"],
            "recommended_retrieval_target": contradiction_target,
            "rationale_trigger": "anchor reading should test whether only positive studies were captured",
            "scope": "recover contradictory findings and scope boundaries",
        }
    )

    plans.append(
        {
            "search_round": "3",
            "parent_search_id": "round2-synthesis-gap-check",
            "concept_focus": "citation chaining and landmark reviews",
            "query_family": "citation_chaining",
            "extra_terms": ["systematic review", "meta-analysis", "landmark review", "citation chaining"],
            "recommended_retrieval_target": "15",
            "rationale_trigger": "final gap check and reference chasing",
            "scope": "recover missing seminal papers and stabilize the evidence map",
        }
    )

    rows: list[dict[str, str]] = []
    date_limit = default_date_limit(cfg)
    search_id = 1
    for plan in plans:
        free_text_query = " ".join(
            part
            for part in [
                plain_group(exposure_terms),
                plain_group(outcome_terms),
                plain_group(population_terms),
                plain_group(plan["extra_terms"]),
            ]
            if part
        ).strip()

        # Determine which sources to include for this plan entry.
        # For clinical question types, preprints are restricted to Round 1
        # direct_association only; all other families and all Round 2/3 entries
        # use PRIMARY_SOURCES only.
        is_clinical = question_type in CLINICAL_QUESTION_TYPES
        family = plan["query_family"]
        rnd = str(plan["search_round"])
        include_preprints = not is_clinical  # default: preprints for non-clinical types
        if is_clinical:
            # Only include preprints in Round 1 direct_association
            include_preprints = (rnd == "1" and family == "direct_association")
        # Always skip preprints for certain families regardless of question type
        if family in PREPRINT_SKIP_FAMILIES:
            include_preprints = False

        sources_for_plan = list(PRIMARY_SOURCES)
        if include_preprints:
            sources_for_plan = sources_for_plan + list(PREPRINT_SOURCES)

        # Preprint retrieval target is lower than primary sources
        preprint_target = str(max(15, int(plan["recommended_retrieval_target"]) // 2))

        for source in sources_for_plan:
            row_retrieval_target = (
                preprint_target if source in PREPRINT_SOURCES
                else plan["recommended_retrieval_target"]
            )
            rows.append(
                {
                    "search_id": f"S{search_id:03d}",
                    "search_round": plan["search_round"],
                    "parent_search_id": plan["parent_search_id"],
                    "concept_focus": plan["concept_focus"],
                    "query_family": plan["query_family"],
                    "question_type": question_type,
                    "review_goal": review_goal,
                    "query": free_text_query,
                    "source": source,
                    "source_query": build_source_query(
                        source,
                        exposure_terms,
                        outcome_terms,
                        population_terms,
                        plan["extra_terms"],
                    ),
                    "date_searched": "",
                    "date_limit": date_limit,
                    "language_limit": "",
                    "recommended_retrieval_target": row_retrieval_target,
                    "n_retrieved": "",
                    "n_after_dedup": "",
                    "scope": plan["scope"],
                    "status": "planned",
                    "rationale_trigger": plan["rationale_trigger"],
                    "note": "",
                }
            )
            search_id += 1
    return rows


def build_strategy_markdown(cfg: dict, rows: list[dict[str, str]]) -> str:
    topic = cfg.get("topic", "study topic")
    question_type = (cfg.get("question_type") or "").strip()
    review_goal = (cfg.get("review_goal") or "").strip()
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["search_round"], []).append(row)

    lines = [
        "# Search Strategy",
        "",
        f"**Topic:** {topic}",
    ]
    if question_type:
        lines.append(f"**Question type:** {question_type}")
    if review_goal:
        lines.append(f"**Review goal:** {review_goal}")
    lines.extend([
        "",
        "## Core Sources",
        "",
        "- OpenAlex (free, full-text unavailable; abstract via inverted index)",
        "- PubMed/MEDLINE (free; NCBI E-utilities; abstract + MeSH terms)",
        "- Semantic Scholar (free; add --ss-api-key for higher rate limits; abstract + open-access PDFs)",
        "- Europe PMC (free; EBI REST API; abstract + PMC open-access full text)",
        "- medRxiv (preprints; interval API + local keyword scoring)",
        "- bioRxiv (preprints; interval API + local keyword scoring)",
        "- Embase (subscription required; blocked_auth_required if credentials absent)",
        "- Web of Science (subscription required; blocked_auth_required if credentials absent)",
        "",
        "## Working Defaults",
        "",
        "- Round 1 broad mapping: target per source is set by retrieval_target() based on review_goal.",
        "- Read 12-20 anchor papers after deduplication before expanding.",
        "- Round 2 reading-driven expansion: about 20 records per triggered query family and source.",
        "- Round 3 citation chaining: about 15 targeted records per citation-focused family and source where applicable.",
        "",
    ])

    for round_id in sorted(grouped.keys(), key=int):
        lines.extend([f"## Round {round_id}", ""])
        seen_families: set[str] = set()
        for row in grouped[round_id]:
            family = row["query_family"]
            if family in seen_families:
                continue
            seen_families.add(family)
            lines.append(
                f"- `{family}`: {row['concept_focus']}; target {row['recommended_retrieval_target']} per source; trigger: {row['rationale_trigger']}."
            )
        lines.append("")

    lines.extend(
        [
            "## Logging Rule",
            "",
            "Log the actual source syntax, date searched, retrieval count, post-dedup count, and the reason a later-round query was added.",
            "",
        ]
    )
    return "\n".join(lines)


def main_build_search_plan() -> None:
    parser = argparse.ArgumentParser(description="Build a multi-database iterative search plan from topic_config.json.")
    parser.add_argument("--topic-config", required=True, help="Path to topic_config.json")
    parser.add_argument("--output-dir", required=True, help="Directory to write search_strategy.md and search_log.csv")
    args = parser.parse_args()

    cfg = load_json(Path(args.topic_config))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = build_query_plan(cfg)
    write_csv(output_dir / "search_log.csv", rows, rows[0].keys() if rows else [])
    (output_dir / "search_strategy.md").write_text(build_strategy_markdown(cfg, rows), encoding="utf-8")

# run_live_search
USER_AGENT = "study-literature-review/1.0"
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "between", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "the", "to", "using", "with",
}
GENERIC_QUERY_TOKENS = {
    "adult",
    "adults",
    "associated",
    "association",
    "clinical",
    "comparing",
    "comparison",
    "disease",
    "event",
    "events",
    "major",
    "multiple",
    "outcome",
    "outcomes",
    "patient",
    "patients",
    "population",
    "populations",
    "research",
    "risk",
    "risks",
    "study",
    "treated",
    "treatment",
    "versus",
}
CONTINUE_TERMS = ("continue", "continuing", "continued", "persistence", "persistent", "maintained")
STOP_TERMS = ("stop", "stopping", "discontinu", "cessation", "cease", "withdraw", "deprescrib", "termination")
DESIGN_STRATEGY_TERMS = (
    "target trial", "grace period", "active comparator",
    "prior user", "new user design", "incident user",
)
STRATEGY_QUERY_FAMILIES = {
    "direct_association",
    "design_estimand",
    "strategy_comparison",
    "clinical_trigger_strategy",
    "outcome_specific_strategy",
}


class SearchResult:
    title: str
    authors: str
    year: str
    published_date: str
    abstract: str
    doi: str
    url: str
    source_record_id: str
    publication_status: str
    raw: dict[str, Any]
    local_relevance_score: float


def infer_publication_status(*parts: str) -> str:
    blob = " ".join(part or "" for part in parts).lower()
    if any(token in blob for token in ["medrxiv", "biorxiv", "arxiv", "preprint", "preprints202", "ssrn"]):
        return "preprint"
    return "peer_reviewed_or_unknown"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_ssl_context(insecure_skip_verify: bool) -> ssl.SSLContext | None:
    if not insecure_skip_verify:
        return None
    return ssl._create_unverified_context()


def http_get_json(url: str, headers: dict[str, str] | None = None, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    last_error: Exception | None = None
    request_headers = {**(headers or {}), "Connection": "close"}
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=60, context=build_ssl_context(insecure_skip_verify)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # transient truncation/reset is common behind proxies
            last_error = exc
            if attempt < 3:
                time.sleep(0.4 * (attempt + 1))
    assert last_error is not None
    raise last_error


def http_get_text(url: str, headers: dict[str, str] | None = None, *, insecure_skip_verify: bool = False) -> str:
    last_error: Exception | None = None
    request_headers = {**(headers or {}), "Connection": "close"}
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=60, context=build_ssl_context(insecure_skip_verify)) as resp:
                return resp.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.4 * (attempt + 1))
    assert last_error is not None
    raise last_error


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def classify_exception(exc: Exception) -> dict[str, str]:
    """Turn operational failures into actionable diagnostics."""
    message = normalize_space(str(exc))
    lowered = message.lower()

    if isinstance(exc, urllib.error.HTTPError):
        code = getattr(exc, "code", None)
        if code == 429:
            return {
                "class": "http_rate_limited",
                "message": message,
                "hint": "Retry later or add provider API keys such as --ncbi-api-key or --ss-api-key.",
            }
        if code in {401, 403}:
            return {
                "class": "http_auth_or_access_denied",
                "message": message,
                "hint": "Check whether the source requires credentials, institutional access, or a provider key.",
            }
        if code and code >= 500:
            return {
                "class": "http_upstream_server_error",
                "message": message,
                "hint": "The provider appears unavailable; retry later or switch sources for the current round.",
            }

    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        reason_text = normalize_space(str(reason or message)).lower()
        if isinstance(reason, socket.gaierror) or any(
            token in reason_text
            for token in [
                "nodename nor servname provided",
                "name or service not known",
                "temporary failure in name resolution",
                "no address associated with hostname",
            ]
        ):
            return {
                "class": "network_dns_resolution_failed",
                "message": message,
                "hint": "The runtime cannot resolve provider hostnames. Check DNS/network access first; if connectivity is unavailable, seed a manually verified corpus and document the downgrade.",
            }
        if "certificate" in reason_text or "ssl" in reason_text:
            return {
                "class": "network_ssl_error",
                "message": message,
                "hint": "Check local root certificates. If the network is trusted but the certificate store is incomplete, retry with --insecure-skip-verify.",
            }
        if "timed out" in reason_text or isinstance(reason, TimeoutError):
            return {
                "class": "network_timeout",
                "message": message,
                "hint": "The source did not respond in time. Retry later, lower concurrency externally, or narrow the current query family.",
            }
        if any(token in reason_text for token in ["refused", "unreachable", "reset by peer"]):
            return {
                "class": "network_connection_failed",
                "message": message,
                "hint": "The connection failed before a response was returned. Check firewall, proxy, or network policy.",
            }

    return {
        "class": "unexpected_runtime_error",
        "message": message,
        "hint": "Inspect the failing row and raw query, then rerun after narrowing the scope or fixing the local environment.",
    }


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return value or "item"


def query_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\+\.%/]*", (text or "").lower())
    return [t for t in tokens if len(t) > 2 and t not in STOPWORDS and t not in GENERIC_QUERY_TOKENS]


def score_match(query: str, title: str, abstract: str) -> float:
    tokens = query_tokens(query)
    if not tokens:
        return 0.0
    blob = f"{title} {abstract}".lower()
    matched = sum(1 for token in tokens if token in blob)
    title_hits = sum(1 for token in tokens if token in (title or "").lower())
    return matched + 0.5 * title_hits


def rank_results(results: list[SearchResult], max_results: int) -> list[SearchResult]:
    ranked = sorted(
        results,
        key=lambda item: (
            item.local_relevance_score,
            item.published_date or item.year or "",
            item.title,
        ),
        reverse=True,
    )
    # Relevance is a prioritisation signal, not an eligibility filter. Exact-ID
    # verification queries often have zero lexical overlap with their purpose label.
    return ranked[:max_results]


def has_any_term(blob: str, terms: tuple[str, ...]) -> bool:
    lowered = (blob or "").lower()
    return any(term in lowered for term in terms)


def compute_strategy_match_score(row: dict[str, str], result: SearchResult) -> int:
    """Return 0–3 indicating how well a result matches a strategy comparison query.

    This replaces the former hard-filter approach.  No results are deleted;
    instead the score is added as a ranking bonus so that well-matched papers
    rise to the top while marginally-matched papers are preserved for human review.

    Score bands:
      0 — not a strategy query, or no strategy vocabulary in result
      1 — single-side match (continue-only OR stop-only)
      2 — both-side match (continue AND stop vocabulary present)
      3 — both-side match + design vocabulary (target trial, grace period, etc.)
    """
    query_blob = f"{row.get('query', '')} {row.get('source_query', '')}".lower()
    if row.get("query_family") not in STRATEGY_QUERY_FAMILIES:
        return 0
    if not (has_any_term(query_blob, CONTINUE_TERMS) or has_any_term(query_blob, STOP_TERMS)):
        return 0

    blob = f"{result.title} {result.abstract}".lower()
    has_continue = has_any_term(blob, CONTINUE_TERMS)
    has_stop = has_any_term(blob, STOP_TERMS)
    has_design_vocab = has_any_term(blob, DESIGN_STRATEGY_TERMS)

    if has_continue and has_stop:
        return 3 if has_design_vocab else 2
    if has_continue or has_stop:
        return 1
    return 0


def rerank_with_strategy(
    results: list[SearchResult],
    strategy_scores: list[int],
    max_results: int,
) -> tuple[list[SearchResult], list[int]]:
    """Re-rank results by (local_relevance_score + 0.5 * strategy_score), descending.

    Returns the re-ranked results and their corresponding strategy scores,
    both capped at max_results.  All results are preserved before the cap;
    none are deleted.
    """
    paired = list(zip(results, strategy_scores))
    paired.sort(key=lambda x: x[0].local_relevance_score + 0.5 * x[1], reverse=True)
    ranked = paired[:max_results]
    return [r for r, _ in ranked], [s for _, s in ranked]


def reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    words_by_position: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for position in positions:
            words_by_position[position] = word
    return " ".join(words_by_position[pos] for pos in sorted(words_by_position))


def parse_date_limit(limit: str) -> tuple[str, str]:
    value = (limit or "").strip()
    if not value:
        return "", ""
    if "/" in value and "-" in value:
        parts = value.split("-")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    if re.fullmatch(r"\d{4}-\d{4}", value):
        start_year, end_year = value.split("-")
        end_date = f"{end_year}-12-31"
        if int(end_year) >= date.today().year:
            end_date = date.today().isoformat()
        return f"{start_year}-01-01", end_date
    if re.fullmatch(r"\d{4}", value):
        year = int(value)
        end_date = f"{year}-12-31"
        if year >= date.today().year:
            end_date = date.today().isoformat()
        return f"{year}-01-01", end_date
    return "", ""


def month_windows(start_date: str, end_date: str) -> list[tuple[str, str]]:
    if not start_date or not end_date:
        end = date.today()
        start = date(end.year - 1, end.month, 1)
    else:
        start = datetime.strptime(start_date, "%Y-%m-%d").date().replace(day=1)
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

    windows: list[tuple[str, str]] = []
    cursor = date(end.year, end.month, 1)
    while cursor >= start:
        next_month = date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)
        last_day = min(end, next_month.fromordinal(next_month.toordinal() - 1))
        first_day = cursor if cursor >= start else start
        windows.append((first_day.isoformat(), last_day.isoformat()))
        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)
    return windows


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    order: list[str] = []
    best: dict[str, dict[str, str]] = {}
    source_priority = {"PubMed/MEDLINE": 3, "Europe PMC": 2, "Semantic Scholar": 1, "OpenAlex": 0}
    for row in rows:
        doi = (row.get("doi") or "").strip().lower()
        title = normalize_space(row.get("title", "")).lower()
        key = doi or title
        if not key:
            continue
        if key not in best:
            order.append(key)
            best[key] = row
            continue
        current = best[key]
        candidate_score = (len(row.get("abstract", "")), source_priority.get(row.get("source", ""), -1))
        current_score = (len(current.get("abstract", "")), source_priority.get(current.get("source", ""), -1))
        if candidate_score > current_score:
            best[key] = row
    return [best[key] for key in order]


def search_openalex(row: dict[str, str], max_results: int, mailto: str | None, *, insecure_skip_verify: bool = False) -> tuple[list[SearchResult], dict[str, Any]]:
    params = {
        "search": row["query"],
        "per-page": str(min(max_results, 200)),
    }
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    filters = []
    if start_date:
        filters.append(f"from_publication_date:{start_date}")
    if end_date:
        filters.append(f"to_publication_date:{end_date}")
    if filters:
        params["filter"] = ",".join(filters)
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
    results: list[SearchResult] = []
    for work in payload.get("results", []):
        title = normalize_space(work.get("display_name", ""))
        abstract = reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        primary_location = work.get("primary_location") or {}
        url_value = primary_location.get("landing_page_url") or primary_location.get("pdf_url") or work.get("doi") or work.get("id", "")
        year = str(work.get("publication_year") or "")
        pub_date = work.get("publication_date") or ""
        authors = "; ".join(
            author.get("author", {}).get("display_name", "")
            for author in work.get("authorships", [])
            if author.get("author", {}).get("display_name")
        )
        results.append(
            SearchResult(
                title=title,
                authors=authors,
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url_value,
                source_record_id=work.get("id", ""),
                publication_status=(
                    "preprint"
                    if work.get("type") == "posted-content"
                    else infer_publication_status(doi, url_value, title)
                ),
                raw=work,
                local_relevance_score=score_match(row["query"], title, abstract),
            )
        )
    return rank_results(results, max_results), payload


def pubmed_esearch(row: dict[str, str], max_results: int, ncbi_api_key: str | None, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    params = {
        "db": "pubmed",
        "term": row["source_query"] or row["query"],
        "retmode": "json",
        "retmax": str(max_results),
        "sort": "relevance",
        "usehistory": "y",
    }
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    if start_date and end_date:
        params["datetype"] = "pdat"
        params["mindate"] = start_date
        params["maxdate"] = end_date
    if ncbi_api_key:
        params["api_key"] = ncbi_api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    return http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)


def pubmed_efetch(id_list: list[str], ncbi_api_key: str | None, *, insecure_skip_verify: bool = False) -> str:
    params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "xml",
    }
    if ncbi_api_key:
        params["api_key"] = ncbi_api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(params)
    return http_get_text(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)


def parse_pubmed_articles(xml_text: str, query: str) -> list[SearchResult]:
    root = ET.fromstring(xml_text)
    results: list[SearchResult] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        title = normalize_space("".join(article.find(".//ArticleTitle").itertext())) if article.find(".//ArticleTitle") is not None else ""
        abstract = normalize_space(" ".join("".join(node.itertext()) for node in article.findall(".//Abstract/AbstractText")))
        year = (
            article.findtext(".//PubDate/Year")
            or article.findtext(".//ArticleDate/Year")
            or article.findtext(".//DateCompleted/Year")
            or ""
        )
        month = article.findtext(".//ArticleDate/Month", default="01")
        day = article.findtext(".//ArticleDate/Day", default="01")
        pub_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}" if year else ""
        authors = []
        for author in article.findall(".//Author"):
            last = author.findtext("LastName", default="")
            fore = author.findtext("ForeName", default="")
            collective = author.findtext("CollectiveName", default="")
            name = normalize_space(f"{fore} {last}") if (fore or last) else collective
            if name:
                authors.append(name)
        doi = ""
        for article_id in article.findall(".//ArticleId"):
            if article_id.attrib.get("IdType") == "doi":
                doi = normalize_space(article_id.text or "")
                break
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        results.append(
            SearchResult(
                title=title,
                authors="; ".join(authors),
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url,
                source_record_id=pmid,
                publication_status=infer_publication_status(doi, url, title),
                raw={"pmid": pmid, "title": title},
                local_relevance_score=score_match(query, title, abstract),
            )
        )
    return results


def search_pubmed(row: dict[str, str], max_results: int, ncbi_api_key: str | None, *, insecure_skip_verify: bool = False) -> tuple[list[SearchResult], dict[str, Any]]:
    esearch_payload = pubmed_esearch(row, max_results, ncbi_api_key, insecure_skip_verify=insecure_skip_verify)
    id_list = esearch_payload.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return [], esearch_payload
    xml_text = pubmed_efetch(id_list, ncbi_api_key, insecure_skip_verify=insecure_skip_verify)
    articles = parse_pubmed_articles(xml_text, row["query"])
    return rank_results(articles, max_results), {
        "esearch": esearch_payload,
        "efetch_ids": id_list,
        "efetch_xml": xml_text,
    }


def fetch_preprint_interval(server: str, start_date: str, end_date: str, cursor: int, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    url = f"https://api.biorxiv.org/details/{server}/{start_date}/{end_date}/{cursor}/json"
    return http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)


def search_preprint_source(row: dict[str, str], server: str, max_results: int, scan_cap: int, *, insecure_skip_verify: bool = False) -> tuple[list[SearchResult], dict[str, Any]]:
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    windows = month_windows(start_date, end_date)
    harvested = 0
    payload_summary: dict[str, Any] = {
        "windows": [],
        "scan_cap": scan_cap,
        "harvested_records": [],
    }
    collected: list[SearchResult] = []

    for window_start, window_end in windows:
        cursor = 0
        window_info = {"start": window_start, "end": window_end, "pages": 0}
        while harvested < scan_cap:
            payload = fetch_preprint_interval(server, window_start, window_end, cursor, insecure_skip_verify=insecure_skip_verify)
            collection = payload.get("collection", [])
            window_info["pages"] += 1
            if not collection:
                break
            for item in collection:
                harvested += 1
                # Preserve the provider-returned object before local ranking.
                # This is the retrieval truth; the candidate CSV is only a
                # normalized downstream view of these archived objects.
                payload_summary["harvested_records"].append(item)
                title = normalize_space(item.get("title", ""))
                abstract = normalize_space(item.get("abstract", ""))
                score = score_match(row["query"], title, abstract)
                if score <= 0:
                    continue
                doi = normalize_space(item.get("doi", ""))
                preprint_url = f"https://www.{server}.org/content/{doi}v{item.get('version', '1')}" if doi else ""
                collected.append(
                    SearchResult(
                        title=title,
                        authors=normalize_space(item.get("authors", "").replace(";", "; ")),
                        year=(item.get("date", "") or "")[:4],
                        published_date=item.get("date", ""),
                        abstract=abstract,
                        doi=doi,
                        url=preprint_url,
                        source_record_id=doi,
                        publication_status=infer_publication_status(doi, preprint_url, title),
                        raw=item,
                        local_relevance_score=score,
                    )
                )
                if len(collected) >= max_results * 3:
                    break
            if len(collection) < 100 or len(collected) >= max_results * 3 or harvested >= scan_cap:
                break
            cursor += 100
            time.sleep(0.1)
        payload_summary["windows"].append(window_info)
        if len(collected) >= max_results * 3 or harvested >= scan_cap:
            break

    payload_summary["harvested"] = harvested
    payload_summary["locally_matched"] = len(collected)
    return rank_results(collected, max_results), payload_summary


def search_semantic_scholar(
    row: dict[str, str],
    max_results: int,
    ss_api_key: str | None,
    *,
    insecure_skip_verify: bool = False,
) -> tuple[list[SearchResult], dict[str, Any]]:
    """Query Semantic Scholar Graph API.

    Rate limits: 100 requests/5 min without key; add --ss-api-key for higher limits.
    The API does not support date-range filtering on the search endpoint, so date
    limits from the search plan are applied post-hoc by local relevance ranking.
    """
    params = {
        "query": row["query"],
        "limit": str(min(max_results, 100)),
        "fields": "title,abstract,authors,year,publicationDate,externalIds,venue,publicationTypes,openAccessPdf",
    }
    headers = {"User-Agent": USER_AGENT}
    if ss_api_key:
        headers["x-api-key"] = ss_api_key
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers=headers, insecure_skip_verify=insecure_skip_verify)
    results: list[SearchResult] = []
    for paper in payload.get("data", []):
        title = normalize_space(paper.get("title") or "")
        abstract = normalize_space(paper.get("abstract") or "")
        authors = "; ".join(
            a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")
        )
        year = str(paper.get("year") or "")
        pub_date = paper.get("publicationDate") or ""
        ext_ids = paper.get("externalIds") or {}
        doi = normalize_space(ext_ids.get("DOI") or "")
        pmid = ext_ids.get("PubMed") or ""
        paper_id = paper.get("paperId") or ""
        oa_url = (paper.get("openAccessPdf") or {}).get("url") or ""
        url_value = oa_url or (f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{paper_id}")
        pub_types = paper.get("publicationTypes") or []
        pub_status = "preprint" if "Preprint" in pub_types else infer_publication_status(doi, url_value, title)
        results.append(
            SearchResult(
                title=title,
                authors=authors,
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url_value,
                source_record_id=paper_id or pmid or doi or "",
                publication_status=pub_status,
                raw=paper,
                local_relevance_score=score_match(row["query"], title, abstract),
            )
        )
    return rank_results(results, max_results), payload


def search_europe_pmc(
    row: dict[str, str],
    max_results: int,
    *,
    insecure_skip_verify: bool = False,
) -> tuple[list[SearchResult], dict[str, Any]]:
    """Query Europe PMC REST API (free, no authentication required).

    Europe PMC covers MEDLINE, PubMed Central, preprints, and some grey literature.
    It provides structured author metadata and full abstractText for many records.
    The source_query field may use Europe PMC field syntax (TITLE: ABSTRACT:) or
    plain text; plain text is used as fallback.
    """
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    query = (row.get("source_query") or row["query"]).strip()
    if start_date and end_date:
        query = f"({query}) AND FIRST_PDATE:[{start_date} TO {end_date}]"
    params = {
        "query": query,
        "format": "json",
        "pageSize": str(min(max_results, 100)),
        "resultType": "core",
    }
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
    results: list[SearchResult] = []
    for item in (payload.get("resultList") or {}).get("result", []):
        title = normalize_space(item.get("title") or "")
        abstract = normalize_space(item.get("abstractText") or "")
        doi = normalize_space(item.get("doi") or "")
        pmid = item.get("pmid") or ""
        year = str(item.get("pubYear") or "")
        pub_date = item.get("firstPublicationDate") or ""
        author_list = ((item.get("authorList") or {}).get("author")) or []
        authors = "; ".join(
            normalize_space(f"{a.get('firstName', '')} {a.get('lastName', '')}").strip()
            for a in author_list
            if a.get("lastName")
        )
        source_code = item.get("source") or "MED"
        url_value = (
            f"https://europepmc.org/article/{source_code}/{pmid}"
            if pmid
            else (f"https://doi.org/{doi}" if doi else "")
        )
        results.append(
            SearchResult(
                title=title,
                authors=authors,
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url_value,
                source_record_id=pmid or doi or item.get("id", ""),
                publication_status=infer_publication_status(doi, url_value, title),
                raw=item,
                local_relevance_score=score_match(row["query"], title, abstract),
            )
        )
    return rank_results(results, max_results), payload


def serialize_result_rows(
    search_row: dict[str, str],
    results: list[SearchResult],
    strategy_scores: list[int] | None = None,
) -> list[dict[str, str]]:
    rows = []
    for rank, result in enumerate(results, start=1):
        s_score = strategy_scores[rank - 1] if strategy_scores else 0
        rows.append(
            {
                "search_id": search_row["search_id"],
                "search_round": search_row["search_round"],
                "query_family": search_row["query_family"],
                "source": search_row["source"],
                "source_rank": str(rank),
                "title": result.title,
                "authors": result.authors,
                "year": result.year,
                "published_date": result.published_date,
                "doi": result.doi,
                "url": result.url,
                "abstract": result.abstract,
                "publication_status": result.publication_status,
                "source_record_id": result.source_record_id,
                "matched_query": search_row["query"],
                "local_relevance_score": f"{result.local_relevance_score:.2f}",
                "strategy_match_score": str(s_score),
            }
        )
    return rows


def api_total_hits(source: str, payload: dict[str, Any], exported: int) -> int:
    """Return the provider-reported hit count without conflating it with export size."""
    try:
        if source == "OpenAlex":
            return int((payload.get("meta") or {}).get("count") or exported)
        if source == "PubMed/MEDLINE":
            return int((((payload.get("esearch") or {}).get("esearchresult") or {}).get("count")) or exported)
        if source == "Europe PMC":
            return int(payload.get("hitCount") or exported)
        if source == "Semantic Scholar":
            return int(payload.get("total") or exported)
        if source in {"medRxiv", "bioRxiv"}:
            return int(payload.get("harvested") or exported)
    except (TypeError, ValueError):
        return exported
    return exported


def raw_payload_filename(row: dict[str, str]) -> str:
    return f"{row['search_id']}_{slug(row['source'])}.json"


def write_raw_payload(
    raw_dir: Path,
    row: dict[str, str],
    payload: dict[str, Any],
    *,
    results: list[SearchResult],
) -> str:
    """Write one self-describing raw payload for one executed ledger row.

    `exported_records` is constructed from the in-memory provider results at
    execution time and retains each original provider object. It must never be
    reconstructed later from candidate_records_raw.csv.
    """
    filename = raw_payload_filename(row)
    exported_records = [
        {
            "source_record_id": result.source_record_id,
            "doi": result.doi,
            "title": result.title,
            "raw_record": result.raw,
        }
        for result in results
    ]
    wrapper = {
        "search_id": row["search_id"],
        "source": row["source"],
        "query_family": row.get("query_family", ""),
        "query": row.get("query", ""),
        "source_query": row.get("source_query", ""),
        "executed_at": datetime.now(UTC).isoformat(),
        "api_total_hits": api_total_hits(row["source"], payload, len(results)),
        "exported_count": len(results),
        "exported_records": exported_records,
        "payload": payload,
    }
    write_json(raw_dir / filename, wrapper)
    return f"raw_results/{filename}"


def update_search_row(
    row: dict[str, str],
    *,
    retrieved: int,
    status: str,
    note: str,
    exported: int | None = None,
    raw_file: str = "",
) -> dict[str, str]:
    updated = dict(row)
    updated["date_searched"] = date.today().isoformat()
    updated["n_retrieved"] = str(retrieved)
    updated["api_total_hits"] = str(retrieved)
    updated["n_exported"] = str(retrieved if exported is None else exported)
    updated["raw_file"] = raw_file
    updated["status"] = status
    existing_note = normalize_space(row.get("note", ""))
    updated["note"] = normalize_space(" ".join(part for part in [existing_note, note] if part))
    return updated


def execute_row(
    row: dict[str, str],
    output_dir: Path,
    max_override: int | None,
    mailto: str | None,
    ncbi_api_key: str | None,
    ss_api_key: str | None,
    preprint_scan_cap: int,
    insecure_skip_verify: bool,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    source = row["source"]
    max_results = max_override or int(row.get("recommended_retrieval_target") or "40")
    raw_dir = output_dir / "raw_results"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if source == "OpenAlex":
        results, payload = search_openalex(row, max_results, mailto, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note="queried OpenAlex API"), serialize_result_rows(row, results, strategy_scores)

    if source == "PubMed/MEDLINE":
        results, payload = search_pubmed(row, max_results, ncbi_api_key, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note="queried NCBI E-utilities; raw payload includes efetch XML"), serialize_result_rows(row, results, strategy_scores)

    if source == "medRxiv":
        results, payload = search_preprint_source(row, "medrxiv", max_results, preprint_scan_cap, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        note = f"queried official medRxiv interval API and locally ranked matches; scan_cap={preprint_scan_cap}"
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note=note), serialize_result_rows(row, results, strategy_scores)

    if source == "bioRxiv":
        results, payload = search_preprint_source(row, "biorxiv", max_results, preprint_scan_cap, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        note = f"queried official bioRxiv interval API and locally ranked matches; scan_cap={preprint_scan_cap}"
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note=note), serialize_result_rows(row, results, strategy_scores)

    if source == "Semantic Scholar":
        results, payload = search_semantic_scholar(row, max_results, ss_api_key, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        key_note = "queried Semantic Scholar Graph API (add --ss-api-key for higher rate limits)"
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note=key_note), serialize_result_rows(row, results, strategy_scores)

    if source == "Europe PMC":
        results, payload = search_europe_pmc(row, max_results, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note="queried Europe PMC REST API"), serialize_result_rows(row, results, strategy_scores)

    if source == "Embase":
        return update_search_row(row, retrieved=0, exported=0, status="blocked_auth_required", note="Embase API access is subscription-gated; export or API key workflow still required"), []

    if source == "Web of Science":
        return update_search_row(row, retrieved=0, exported=0, status="blocked_auth_required", note="Web of Science API access is credential-gated; Starter or Expanded API workflow still required"), []

    return update_search_row(row, retrieved=0, exported=0, status="skipped_unknown_source", note="source not recognized by retrieval.py run_live_search"), []


def main_run_live_search() -> None:
    parser = argparse.ArgumentParser(description="Run a live literature search from search_log.csv.")
    parser.add_argument("--search-log", required=True, help="Path to search_log.csv produced by retrieval.py build_search_plan")
    parser.add_argument("--output-dir", required=True, help="Directory for updated search_log.csv and candidate records")
    parser.add_argument("--max-per-query", type=int, default=None, help="Override recommended_retrieval_target for all rows")
    parser.add_argument("--mailto", default="", help="Optional email for polite-pool APIs such as OpenAlex")
    parser.add_argument("--ncbi-api-key", default="", help="Optional NCBI API key for PubMed E-utilities")
    parser.add_argument("--ss-api-key", default="", help="Optional Semantic Scholar API key (x-api-key header) for higher rate limits")
    parser.add_argument("--preprint-scan-cap", type=int, default=500, help="Maximum raw interval records to scan per preprint-source query (default 500; use 2000 for broader preprint sweeps)")
    parser.add_argument("--skip-preprints", action="store_true", help="Skip medRxiv and bioRxiv queries entirely (recommended for clinical/pharmacoepi questions where peer-reviewed coverage is adequate)")
    parser.add_argument("--insecure-skip-verify", action="store_true", help="Skip SSL certificate verification when the local environment lacks required root certificates")
    parser.add_argument("--clean-output", action="store_true", help="Remove prior retrieval artifacts in OUTPUT_DIR before execution so stale raw payloads cannot survive")
    parser.add_argument("--append-existing", action="store_true", help="Retain existing candidate/raw artifacts and append only newly planned rows; use with the current output search_log")
    parser.add_argument(
        "--execute-statuses",
        default="planned,refresh_requested",
        help="Comma-separated search_log statuses that should be executed",
    )
    parser.add_argument("--only-query-families", default="", help="Optional comma-separated allowlist of query_family values to execute")
    parser.add_argument("--only-sources", default="", help="Optional comma-separated allowlist of source values to execute")
    args = parser.parse_args()

    search_log_path = Path(args.search_log)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.clean_output:
        raw_dir = output_dir / "raw_results"
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
        for name in ("candidate_records_raw.csv", "candidate_records_dedup.csv", "live_search_diagnostics.json"):
            path = output_dir / name
            if path.exists():
                path.unlink()
    rows = read_csv(search_log_path)

    executable_statuses = {item.strip() for item in args.execute_statuses.split(",") if item.strip()}
    only_query_families = {item.strip() for item in args.only_query_families.split(",") if item.strip()}
    only_sources = {item.strip() for item in args.only_sources.split(",") if item.strip()}
    skip_preprint_sources = {"medRxiv", "bioRxiv"} if args.skip_preprints else set()
    updated_rows: list[dict[str, str]] = []
    candidate_rows: list[dict[str, str]] = []
    if args.append_existing and (output_dir / "candidate_records_raw.csv").exists():
        candidate_rows = read_csv(output_dir / "candidate_records_raw.csv")
        executable_ids = {
            row.get("search_id", "") for row in rows
            if (row.get("status") or "").strip() in executable_statuses
            and (not only_query_families or row.get("query_family") in only_query_families)
            and (not only_sources or row.get("source") in only_sources)
        }
        candidate_rows = [row for row in candidate_rows if row.get("search_id", "") not in executable_ids]
    diagnostics: list[dict[str, str]] = []

    for row in rows:
        status = (row.get("status") or "").strip()
        if status and status not in executable_statuses:
            updated_rows.append(row)
            continue
        if only_query_families and row.get("query_family") not in only_query_families:
            updated_rows.append(row)
            continue
        if only_sources and row.get("source") not in only_sources:
            updated_rows.append(row)
            continue
        if skip_preprint_sources and row.get("source") in skip_preprint_sources:
            updated_rows.append(update_search_row(row, retrieved=0, exported=0, status="skipped_preprints_disabled",
                                                   note="--skip-preprints flag set; preprint sources bypassed"))
            continue
        try:
            updated, candidates = execute_row(
                row,
                output_dir=output_dir,
                max_override=args.max_per_query,
                mailto=args.mailto or None,
                ncbi_api_key=args.ncbi_api_key or None,
                ss_api_key=args.ss_api_key or None,
                preprint_scan_cap=args.preprint_scan_cap,
                insecure_skip_verify=args.insecure_skip_verify,
            )
            updated_rows.append(updated)
            candidate_rows.extend(candidates)
        except Exception as exc:  # pragma: no cover - operational fallback
            diag = classify_exception(exc)
            failed = update_search_row(
                row,
                retrieved=0,
                exported=0,
                status="error",
                note=f"[{diag['class']}] search failed: {diag['message']} next_step: {diag['hint']}",
            )
            updated_rows.append(failed)
            diagnostics.append(
                {
                    "search_id": row.get("search_id", ""),
                    "source": row.get("source", ""),
                    "query_family": row.get("query_family", ""),
                    "error_class": diag["class"],
                    "message": diag["message"],
                    "next_step": diag["hint"],
                }
            )

    deduped_rows = dedupe_rows(candidate_rows)
    dedup_owned_counts: dict[str, int] = defaultdict(int)
    for candidate in deduped_rows:
        dedup_owned_counts[candidate.get("search_id", "")] += 1
    for row in updated_rows:
        row["n_after_dedup"] = str(dedup_owned_counts.get(row.get("search_id", ""), 0))

    fieldnames = list(updated_rows[0].keys()) if updated_rows else []
    if fieldnames:
        write_csv(output_dir / "search_log.csv", updated_rows, fieldnames)

    raw_fieldnames = [
        "search_id",
        "search_round",
        "query_family",
        "source",
        "source_rank",
        "title",
        "authors",
        "year",
        "published_date",
        "doi",
        "url",
        "abstract",
        "publication_status",
        "source_record_id",
        "matched_query",
        "local_relevance_score",
        "strategy_match_score",
    ]
    write_csv(output_dir / "candidate_records_raw.csv", candidate_rows, raw_fieldnames)
    write_csv(output_dir / "candidate_records_dedup.csv", deduped_rows, raw_fieldnames)
    status_counts = defaultdict(int)
    for row in updated_rows:
        status_counts[row.get("status", "")] += 1
    write_json(
        output_dir / "live_search_diagnostics.json",
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "search_log": str(search_log_path),
            "output_dir": str(output_dir),
            "executed_statuses": sorted(executable_statuses),
            "only_query_families": sorted(only_query_families),
            "only_sources": sorted(only_sources),
            "status_counts": dict(status_counts),
            "candidate_row_count": len(candidate_rows),
            "dedup_candidate_row_count": len(deduped_rows),
            "api_total_hits": sum(int(row.get("api_total_hits") or 0) for row in updated_rows),
            "raw_payload_count": len(list((output_dir / "raw_results").glob("*.json"))) if (output_dir / "raw_results").exists() else 0,
            "issues": diagnostics,
        },
    )

# chase_citations
USER_AGENT = "study-literature-review/1.0"
OPENALEX_WORKS_BASE = "https://api.openalex.org/works"


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return doi


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    words_by_pos: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words_by_pos[pos] = word
    return " ".join(words_by_pos[p] for p in sorted(words_by_pos))


def existing_dois_and_titles(rows: list[dict[str, str]]) -> tuple[set[str], set[str]]:
    dois: set[str] = set()
    titles: set[str] = set()
    for row in rows:
        doi = normalize_doi(row.get("doi") or "")
        if doi:
            dois.add(doi)
        title = normalize_space(row.get("title") or "").lower()
        if title:
            titles.add(title)
    return dois, titles


def fetch_openalex_work_by_doi(doi: str, mailto: str | None, *, insecure_skip_verify: bool = False) -> dict[str, Any] | None:
    params = {"filter": f"doi:{doi}"}
    if mailto:
        params["mailto"] = mailto
    url = OPENALEX_WORKS_BASE + "?" + urllib.parse.urlencode(params)
    try:
        payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
        results = payload.get("results", [])
        return results[0] if results else None
    except Exception as exc:
        print(f"  [chase] Could not fetch OpenAlex work for doi:{doi}: {exc}")
        return None


def fetch_openalex_works_batch(openalex_ids: list[str], mailto: str | None, *, insecure_skip_verify: bool = False) -> list[dict[str, Any]]:
    """Fetch up to 50 OpenAlex works by their IDs in one request."""
    if not openalex_ids:
        return []
    ids_filter = "|".join(openalex_ids[:50])
    params = {"filter": f"openalex_id:{ids_filter}", "per-page": "50"}
    if mailto:
        params["mailto"] = mailto
    url = OPENALEX_WORKS_BASE + "?" + urllib.parse.urlencode(params)
    try:
        payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
        return payload.get("results", [])
    except Exception as exc:
        print(f"  [chase] Batch fetch failed: {exc}")
        return []


def fetch_citing_works(openalex_work_id: str, max_results: int, mailto: str | None, *, insecure_skip_verify: bool = False) -> list[dict[str, Any]]:
    """Return works that cite the given OpenAlex work ID (forward chasing)."""
    params = {
        "filter": f"cites:{openalex_work_id}",
        "per-page": str(min(max_results, 200)),
        "sort": "cited_by_count:desc",
    }
    if mailto:
        params["mailto"] = mailto
    url = OPENALEX_WORKS_BASE + "?" + urllib.parse.urlencode(params)
    try:
        payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
        return payload.get("results", [])
    except Exception as exc:
        print(f"  [chase] Forward chase failed for {openalex_work_id}: {exc}")
        return []


def openalex_work_to_row(work: dict[str, Any], chase_type: str, anchor_doi: str) -> dict[str, str]:
    title = normalize_space(work.get("display_name") or "")
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    doi = normalize_doi(work.get("doi") or "")
    primary_loc = work.get("primary_location") or {}
    url_value = primary_loc.get("landing_page_url") or primary_loc.get("pdf_url") or (f"https://doi.org/{doi}" if doi else work.get("id", ""))
    year = str(work.get("publication_year") or "")
    pub_date = work.get("publication_date") or ""
    authors = "; ".join(
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    )
    pub_status = "preprint" if work.get("type") == "posted-content" else "peer_reviewed_or_unknown"
    return {
        "search_id": f"CHASE_{chase_type.upper()}",
        "search_round": "chase",
        "query_family": f"citation_chase_{chase_type}",
        "source": "OpenAlex",
        "source_rank": "",
        "title": title,
        "authors": authors,
        "year": year,
        "published_date": pub_date,
        "doi": doi,
        "url": url_value,
        "abstract": abstract,
        "publication_status": pub_status,
        "source_record_id": work.get("id", ""),
        "matched_query": f"citation_chase from anchor doi:{anchor_doi}",
        "local_relevance_score": "0.00",
        "strategy_match_score": "0",
    }


def is_duplicate(row: dict[str, str], existing_dois: set[str], existing_titles: set[str]) -> bool:
    doi = normalize_doi(row.get("doi") or "")
    if doi and doi in existing_dois:
        return True
    title = normalize_space(row.get("title") or "").lower()
    return bool(title and title in existing_titles)


def chase_anchor(
    doi: str,
    existing_dois: set[str],
    existing_titles: set[str],
    max_per_anchor: int,
    do_forward: bool,
    do_backward: bool,
    mailto: str | None,
    insecure_skip_verify: bool,
) -> list[dict[str, str]]:
    print(f"  [chase] Anchor: doi:{doi}")
    work = fetch_openalex_work_by_doi(doi, mailto, insecure_skip_verify=insecure_skip_verify)
    if not work:
        print(f"  [chase] Not found on OpenAlex: doi:{doi}")
        return []

    openalex_id = work.get("id") or ""
    new_rows: list[dict[str, str]] = []
    time.sleep(0.1)

    if do_forward and openalex_id:
        citing = fetch_citing_works(openalex_id, max_per_anchor, mailto, insecure_skip_verify=insecure_skip_verify)
        print(f"    forward: {len(citing)} citing works retrieved")
        for cw in citing:
            row = openalex_work_to_row(cw, "forward", doi)
            if not is_duplicate(row, existing_dois, existing_titles):
                new_rows.append(row)
                existing_dois.add(normalize_doi(row["doi"]))
                existing_titles.add(normalize_space(row["title"]).lower())
        time.sleep(0.2)

    if do_backward:
        ref_ids = work.get("referenced_works") or []
        print(f"    backward: {len(ref_ids)} referenced works in record")
        for batch_start in range(0, min(len(ref_ids), max_per_anchor * 2), 50):
            batch = ref_ids[batch_start: batch_start + 50]
            ref_works = fetch_openalex_works_batch(batch, mailto, insecure_skip_verify=insecure_skip_verify)
            for rw in ref_works:
                row = openalex_work_to_row(rw, "backward", doi)
                if not is_duplicate(row, existing_dois, existing_titles):
                    new_rows.append(row)
                    existing_dois.add(normalize_doi(row["doi"]))
                    existing_titles.add(normalize_space(row["title"]).lower())
            time.sleep(0.15)
            if len(new_rows) >= max_per_anchor:
                break

    print(f"    → {len(new_rows)} new unique records from this anchor")
    return new_rows


def build_summary_md(
    anchor_dois: list[str],
    total_new: int,
    do_forward: bool,
    do_backward: bool,
    output_path: Path,
) -> str:
    direction = []
    if do_forward:
        direction.append("forward (citing)")
    if do_backward:
        direction.append("backward (references)")
    lines = [
        "# Citation Expansion Summary",
        "",
        f"**Anchors processed:** {len(anchor_dois)}",
        f"**Chase direction(s):** {', '.join(direction) or 'none'}",
        f"**New unique records added:** {total_new}",
        f"**Output:** {output_path}",
        "",
        "## Anchor DOIs",
        "",
    ]
    for doi in anchor_dois:
        lines.append(f"- {doi}")
    lines += [
        "",
        "## Next Step",
        "",
        "Run `evidence.py score_candidates` on `citation_expansion_candidates.csv` (or merge it",
        "into `candidate_records_dedup.csv` first) to score the newly discovered papers.",
    ]
    return "\n".join(lines)


def main_chase_citations() -> None:
    parser = argparse.ArgumentParser(
        description="Expand candidate pool via OpenAlex citation graph traversal.",
    )
    parser.add_argument("--existing-candidates", required=True, help="Path to candidate_records_dedup.csv")
    parser.add_argument("--output-dir", required=True, help="Directory to write citation_expansion_candidates.csv")
    parser.add_argument("--anchor-dois", default="", help="Comma-separated list of anchor DOIs (e.g. 10.1234/abc,10.5678/def)")
    parser.add_argument("--anchor-csv", default="", help="Path to scored_candidates.csv; use papers with score >= --min-score as anchors")
    parser.add_argument("--min-score", type=int, default=7, help="Minimum llm_relevance_score for anchor selection from --anchor-csv (default: 7)")
    parser.add_argument("--max-anchors", type=int, default=20, help="Maximum number of anchor papers to chase (default: 20)")
    parser.add_argument("--max-per-anchor", type=int, default=30, help="Maximum new records to collect per anchor paper (default: 30)")
    parser.add_argument("--forward", action="store_true", default=True, help="Chase forward (papers that cite the anchor)")
    parser.add_argument("--backward", action="store_true", default=True, help="Chase backward (papers the anchor cites)")
    parser.add_argument("--no-forward", dest="forward", action="store_false", help="Disable forward citation chasing")
    parser.add_argument("--no-backward", dest="backward", action="store_false", help="Disable backward citation chasing")
    parser.add_argument("--mailto", default="", help="Email for OpenAlex polite pool (recommended)")
    parser.add_argument("--insecure-skip-verify", action="store_true", help="Skip SSL certificate verification")
    args = parser.parse_args()

    existing_path = Path(args.existing_candidates)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_rows = read_csv(existing_path) if existing_path.exists() else []
    existing_dois, existing_titles = existing_dois_and_titles(existing_rows)
    print(f"[chase_citations] Existing pool: {len(existing_rows)} records, {len(existing_dois)} unique DOIs")

    # Collect anchor DOIs
    anchor_dois: list[str] = []

    if args.anchor_dois:
        for doi in args.anchor_dois.split(","):
            doi = normalize_doi(doi.strip())
            if doi:
                anchor_dois.append(doi)

    if args.anchor_csv and Path(args.anchor_csv).exists():
        scored = read_csv(Path(args.anchor_csv))
        for row in scored:
            try:
                score = float(row.get("llm_relevance_score") or 0)
            except ValueError:
                score = 0.0
            if score >= args.min_score:
                doi = normalize_doi(row.get("doi") or "")
                if doi and doi not in anchor_dois:
                    anchor_dois.append(doi)

    if not anchor_dois:
        # Fall back to top records by local_relevance_score
        try:
            sorted_rows = sorted(existing_rows, key=lambda r: float(r.get("local_relevance_score") or 0), reverse=True)
        except Exception:
            sorted_rows = existing_rows
        for row in sorted_rows:
            doi = normalize_doi(row.get("doi") or "")
            if doi and doi not in anchor_dois:
                anchor_dois.append(doi)
            if len(anchor_dois) >= args.max_anchors:
                break

    anchor_dois = anchor_dois[: args.max_anchors]
    print(f"[chase_citations] Chasing {len(anchor_dois)} anchor(s) | forward={args.forward} | backward={args.backward}")

    all_new: list[dict[str, str]] = []
    for doi in anchor_dois:
        new = chase_anchor(
            doi=doi,
            existing_dois=existing_dois,
            existing_titles=existing_titles,
            max_per_anchor=args.max_per_anchor,
            do_forward=args.forward,
            do_backward=args.backward,
            mailto=args.mailto or None,
            insecure_skip_verify=args.insecure_skip_verify,
        )
        all_new.extend(new)
        time.sleep(0.3)

    print(f"\n[chase_citations] Total new records: {len(all_new)}")

    raw_fieldnames = [
        "search_id", "search_round", "query_family", "source", "source_rank",
        "title", "authors", "year", "published_date", "doi", "url", "abstract",
        "publication_status", "source_record_id", "matched_query",
        "local_relevance_score", "strategy_match_score",
    ]
    out_path = output_dir / "citation_expansion_candidates.csv"
    write_csv(out_path, all_new, raw_fieldnames)
    print(f"[chase_citations] Wrote {out_path}")

    summary_md = build_summary_md(anchor_dois, len(all_new), args.forward, args.backward, out_path)
    summary_path = output_dir / "citation_expansion_summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    print(f"[chase_citations] Wrote {summary_path}")


COMMANDS = {
    "build_search_plan": main_build_search_plan,
    "run_live_search": main_run_live_search,
    "chase_citations": main_chase_citations,
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
