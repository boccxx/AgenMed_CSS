#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/review.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from validation import normalize_project_mode

# build_methods_snapshot


def load_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def build_methods_snapshot(
    review_dir: Path,
    cfg: dict,
) -> dict:
    """Build methods_snapshot from search_log.csv and screening_decisions.csv."""
    search_log = read_csv(review_dir / "search_log.csv")
    screening = read_csv(review_dir / "screening_decisions.csv")
    candidate_raw = read_csv(review_dir / "candidate_records_raw.csv")
    candidate_dedup = read_csv(review_dir / "candidate_records_dedup.csv")
    study_registry = read_csv(review_dir / "study_registry.csv")
    review_contract = load_json(review_dir / "review_contract.json")

    # Databases searched
    sources_searched: dict[str, dict] = {}
    for row in search_log:
        source = normalize(row.get("source") or "")
        status = normalize(row.get("status") or "")
        date_s = normalize(row.get("date_searched") or "")
        if not source:
            continue
        if source not in sources_searched:
            sources_searched[source] = {"status": status, "date_searched": date_s}
        elif date_s and not sources_searched[source]["date_searched"]:
            sources_searched[source]["date_searched"] = date_s

    db_list = [
        {"source": s, "status": info["status"], "date_searched": info["date_searched"]}
        for s, info in sorted(sources_searched.items())
    ]

    search_date_map = {
        item["source"]: item["date_searched"]
        for item in db_list
        if item["date_searched"]
    }

    # Date limits from search_log
    date_limits_set = {
        normalize(row.get("date_limit") or "")
        for row in search_log
        if row.get("date_limit")
    }
    date_limits = "; ".join(sorted(date_limits_set)) or ""

    # PRISMA counts
    n_identified = len(candidate_raw)
    n_dedup = len(candidate_dedup)
    n_screened = len([r for r in screening if r.get("decision")])
    n_excluded_title_abstract = len(
        [r for r in screening if (r.get("screening_stage") or "") in ("title_abstract", "title-abstract")]
    )
    n_fulltext_assessed = len(
        [r for r in screening if (r.get("screening_stage") or "") in ("fulltext", "full_text")]
    )
    included_rows = [
        r for r in screening
        if (r.get("include_in_synthesis") or "").strip().lower() in ("yes", "true", "1")
    ]
    n_included = len(included_rows)
    if n_included == 0:
        # Fallback: count study_registry entries
        n_included = len([r for r in study_registry if r.get("paper_id")])

    # Exclusion reasons
    exclusion_reasons: dict[str, int] = defaultdict(int)
    for r in screening:
        if (r.get("decision") or "").strip().lower() in ("exclude", "excluded"):
            reason = normalize(r.get("exclusion_reason_code") or r.get("reason") or "not_stated")
            exclusion_reasons[reason] += 1

    # Inclusion criteria from topic_config
    harvest = cfg.get("harvest") or {}
    population = cfg.get("population") or ""
    exposure = cfg.get("exposure") or ""
    outcome = cfg.get("outcome") or ""
    question_type = cfg.get("question_type") or ""
    design_type = cfg.get("design_type") or ""

    inclusion_criteria: list[str] = []
    if population:
        inclusion_criteria.append(f"Population: {population}")
    if exposure:
        inclusion_criteria.append(f"Exposure/intervention: {exposure}")
    if outcome:
        inclusion_criteria.append(f"Outcome: {outcome}")
    if design_type:
        inclusion_criteria.append(f"Study design: {design_type}")

    # Language limits from search_log
    lang_limits_set = {
        normalize(row.get("language_limit") or "")
        for row in search_log
        if row.get("language_limit")
    }
    language_limits = "; ".join(sorted(lang_limits_set)) or "No language restriction specified"

    # Access limitations
    access_limitations: list[str] = []
    for row in search_log:
        if (row.get("status") or "").startswith("blocked"):
            access_limitations.append(
                f"{row['source']}: {row.get('status', '')} — {normalize(row.get('note', ''))}"
            )

    snapshot = {
        "_generated": date.today().isoformat(),
        "_instructions": (
            "This file is an internal intermediate — not a user-facing deliverable. "
            "The narrative LLM reads from here to write the Search and Screening section. "
            "Fill any TODO fields before running the narrative generation step."
        ),
        "review_question": (
            f"{exposure} vs comparison in {population}: effect on {outcome}"
            if (exposure and population and outcome)
            else cfg.get("topic") or "TODO: state the review question"
        ),
        "question_type": question_type,
        "review_type": (
            review_contract.get("review_type")
            if isinstance(review_contract, dict)
            else cfg.get("review_type")
        ) or cfg.get("review_type") or "structured_narrative",
        "reporting_framework": (
            review_contract.get("reporting_framework", [])
            if isinstance(review_contract, dict)
            else []
        ),
        "synthesis_method": (
            review_contract.get("synthesis_method", "")
            if isinstance(review_contract, dict)
            else ""
        ),
        "databases_searched": db_list,
        "executed_searches": [
            {
                "search_id": normalize(row.get("search_id") or ""),
                "source": normalize(row.get("source") or ""),
                "source_query": row.get("source_query") or row.get("query") or "",
                "date_searched": normalize(row.get("date_searched") or ""),
                "n_retrieved": normalize(row.get("n_retrieved") or ""),
                "n_after_dedup": normalize(row.get("n_after_dedup") or ""),
                "status": normalize(row.get("status") or ""),
            }
            for row in search_log
            if normalize(row.get("status") or "").lower() in {"retrieved", "completed", "complete", "success", "executed"}
        ],
        "search_dates": search_date_map,
        "date_limits": date_limits or "TODO: specify date range",
        "language_limits": language_limits,
        "inclusion_criteria": inclusion_criteria or ["TODO: list inclusion criteria"],
        "exclusion_criteria": ["TODO: list exclusion criteria"],
        "screening_process": (
            "Two-stage screening: title/abstract followed by full-text review. "
            "TODO: describe who screened and how disagreements were resolved."
        ),
        "fulltext_availability_limitations": (
            "TODO: describe any full-text access constraints "
            "(e.g., subscription-only journals, preprints without peer review)."
        ),
        "quality_appraisal_framework": "scoring_rubric.md + study_quality_framework.md",
        "prisma_counts": {
            "identified_total": n_identified,
            "after_dedup": n_dedup,
            "title_abstract_screened": n_screened,
            "fulltext_assessed": n_fulltext_assessed,
            "included": n_included,
            "excluded_reasons": dict(exclusion_reasons),
        },
        "access_limitations": access_limitations,
    }
    return snapshot


def build_section_packets(
    review_dir: Path,
    cfg: dict,
    question_type: str,
) -> dict:
    """Build section_packets.json from scored_candidates.csv and study_registry.csv."""
    scored = read_csv(review_dir / "scored_candidates.csv")
    study_reg = read_csv(review_dir / "study_registry.csv")

    # Identify anchor papers: record_relevance >= 4 and decision_role = anchor
    anchor_ids: list[str] = []
    direct_ids: list[str] = []
    indirect_ids: list[str] = []
    methods_ids: list[str] = []

    for row in scored:
        pid = (row.get("paper_id") or "").strip()
        if not pid:
            continue
        try:
            rel = int(float(row.get("record_relevance") or 0))
        except (ValueError, TypeError):
            rel = 0
        role = (row.get("decision_role") or "").strip().lower()
        directness = (row.get("likely_directness") or "").strip().lower()
        include = (row.get("include_in_review") or "").strip().lower()

        if include == "no":
            continue
        if role == "anchor":
            anchor_ids.append(pid)
        if directness == "direct":
            direct_ids.append(pid)
        elif directness == "indirect":
            indirect_ids.append(pid)
        elif directness == "background" or role == "methods":
            methods_ids.append(pid)

    # Fallback when scored_candidates.csv not yet filled: use study_registry tiers
    if not anchor_ids and study_reg:
        for row in study_reg:
            pid = (row.get("paper_id") or "").strip()
            tier = (row.get("synthesis_tier") or "").strip()
            eligible = (row.get("anchor_eligible") or "").strip().lower()
            if tier in ("core_direct_strict", "core_direct_broad") and eligible == "yes":
                anchor_ids.append(pid)
            elif tier == "core_direct_broad":
                direct_ids.append(pid)
            elif tier == "indirect_support":
                indirect_ids.append(pid)

    # Outcome families
    harvest = cfg.get("harvest") or {}
    outcome_families = list(harvest.get("outcomes") or [])
    if not outcome_families and cfg.get("outcome"):
        outcome_families = [cfg["outcome"]]

    # Bias types for this question_type
    bias_by_type = {
        "treatment_strategy_comparison": [
            "confounding by indication",
            "immortal time bias",
            "prevalent user bias",
            "time-zero alignment",
            "informative censoring",
        ],
        "exposure_outcome_association": [
            "confounding",
            "reverse causation",
            "OR as RR with common outcome",
            "cross-sectional temporality",
            "overadjustment",
        ],
        "prognosis": [
            "competing risks",
            "loss to follow-up",
            "case-mix variation",
            "outcome ascertainment differences",
        ],
    }
    relevant_biases = bias_by_type.get(question_type, ["confounding", "selection bias", "information bias"])

    packets: list[dict] = [
        {
            "section_id": "evidence_classification",
            "section_name": "Evidence Classification",
            "section_goal": (
                "Classify the evidence base by type before any individual papers are discussed. "
                "State what each type can and cannot support for this specific question."
            ),
            "allowed_strength_ceiling": "background_only",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [
                "Study X found",
                "Study Y found",
                "Study Z found",
                "contributes to the mapped evidence",
            ],
            "drafting_note": (
                "This section should organise the evidence TYPES, not list papers. "
                "Each type entry: name, definition, count in this review, what it can/cannot say."
            ),
        },
        {
            "section_id": "direct_evidence",
            "section_name": "Direct Evidence",
            "section_goal": (
                "Synthesize only the strongest closest-match evidence. "
                "Provide a thematic judgment — direction, consistency, magnitude range, main anchor — "
                "rather than listing individual papers."
            ),
            "allowed_strength_ceiling": "suggestive",
            "anchor_paper_ids": anchor_ids[:5],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": indirect_ids + methods_ids,
            "must_mention_limitations": relevant_biases[:2],
            "expected_outcome_families": outcome_families,
            "anti_repetition_blacklist": [
                "Study X found",
                "In a cohort study,",
                "In an observational study,",
                "Using a retrospective design,",
            ],
            "drafting_note": (
                "Lead with the collective judgment. Mention at most 2 anchor studies by name. "
                "End with the main methodological limitation that constrains interpretation."
            ),
        },
        {
            "section_id": "indirect_evidence",
            "section_name": "Broader Supporting Evidence",
            "section_goal": (
                "Group indirect evidence into 2–4 thematic clusters. "
                "For each cluster state what it adds and what it cannot substitute for direct evidence."
            ),
            "allowed_strength_ceiling": "preliminary",
            "anchor_paper_ids": indirect_ids[:8],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": anchor_ids,
            "must_mention_limitations": ["indirect nature of evidence"],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [
                "provides indirect support",
                "also provides indirect support",
                "similarly provides",
                "Study X provides",
            ],
            "drafting_note": (
                "Do not write one paragraph per paper. Write one paragraph per CLUSTER. "
                "Suggested cluster structure: "
                "(1) initiation/efficacy evidence, "
                "(2) special subgroup evidence, "
                "(3) adherence/persistence descriptors, "
                "(4) guidelines or protocol evidence. "
                "Adapt to the actual question."
            ),
        },
        {
            "section_id": "methodological_challenges",
            "section_name": "Methodological Challenges",
            "section_goal": (
                "Discuss only the limitations that materially change interpretation strength. "
                "Be specific to this question type and the actual studies reviewed."
            ),
            "allowed_strength_ceiling": "background_only",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": relevant_biases,
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [
                "As with all observational studies",
                "Like all retrospective studies",
                "This is a limitation of all",
            ],
            "drafting_note": (
                "Each limitation entry: name it, explain why it is specifically relevant here, "
                "and state what it means for interpretation. "
                "Do not list generic observational-study limitations without explaining their specific impact."
            ),
        },
    ]

    # Add per-outcome-family packets
    for outcome_fam in outcome_families[:5]:
        # Find papers for this outcome
        outcome_anchor_ids = [
            row.get("paper_id", "")
            for row in study_reg
            if outcome_fam.lower() in (row.get("outcome_family_all") or row.get("outcome_family") or "").lower()
            and row.get("paper_id")
        ]
        packets.append({
            "section_id": f"outcome_{re.sub(r'[^a-z0-9]+', '_', outcome_fam.lower())}",
            "section_name": outcome_fam,
            "section_goal": (
                f"For {outcome_fam}: which studies provide direct evidence, "
                "which anchor them, how strong is the conclusion, and what is the main limitation."
            ),
            "allowed_strength_ceiling": "suggestive",
            "anchor_paper_ids": outcome_anchor_ids[:4],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [outcome_fam],
            "anti_repetition_blacklist": [],
            "drafting_note": (
                "If there is no direct evidence for this outcome, say so in one sentence "
                "and explain what indirect evidence suggests (if any). "
                "Do not write a long paragraph that just repeats 'evidence is limited'."
            ),
        })

    return {
        "_generated": date.today().isoformat(),
        "_instructions": (
            "One entry per narrative section. "
            "The LLM drafts each section individually using anchor_paper_ids and anti_repetition_blacklist. "
            "After individual sections are drafted, run a global revision pass to "
            "remove cross-section repetition and verify claim ceilings."
        ),
        "packets": packets,
    }


def build_evidence_clusters(review_dir: Path, cfg: dict) -> dict:
    """Build evidence_clusters.json grouping indirect evidence by thematic cluster.

    Clusters are derived from scored_candidates.csv and study_registry.csv using
    query_family, outcome_family, and synthesis_tier.  The LLM writes ONE paragraph
    per cluster when drafting the Broader Supporting Evidence section.
    """
    scored_csv = review_dir / "scored_candidates.csv"
    study_csv = review_dir / "study_registry.csv"
    scored: list[dict] = read_csv(scored_csv)
    study_reg: list[dict] = read_csv(study_csv)

    # Identify indirect papers — those NOT in study_registry anchor tier
    anchor_ids = {
        r.get("paper_id", "").strip()
        for r in study_reg
        if (r.get("synthesis_tier") or "").lower() in ("core_direct_strict", "core_direct_broad")
        or (r.get("anchor_eligible") or "").lower() == "yes"
    }

    indirect_scored = [
        r for r in scored
        if r.get("paper_id", "").strip() not in anchor_ids
        and (r.get("decision_role") or "").lower() in ("support", "background", "methods")
        and (r.get("include_in_review") or "").lower() in ("yes", "maybe")
    ]

    # Group by query_family as a first-pass clustering proxy
    from collections import defaultdict
    clusters_by_family: dict[str, list[str]] = defaultdict(list)
    for r in indirect_scored:
        qf = (r.get("query_family") or "general").strip().lower()
        pid = r.get("paper_id", "").strip()
        if pid:
            clusters_by_family[qf].append(pid)

    # If scored_candidates lacks data, fall back to study_registry indirect papers
    if not clusters_by_family:
        for r in study_reg:
            tier = (r.get("synthesis_tier") or "").lower()
            if tier in ("supporting", "indirect", "background_policy", "appendix_only"):
                qf = (r.get("outcome_family") or "general").strip().lower()
                pid = r.get("paper_id", "").strip()
                if pid:
                    clusters_by_family[qf].append(pid)

    clusters = []
    for idx, (family, pids) in enumerate(list(clusters_by_family.items())[:5], start=1):
        # Clean up family name for display
        display_name = family.replace("_", " ").title()
        clusters.append({
            "cluster_id": f"C{idx}",
            "theme": display_name,
            "member_paper_ids": pids[:8],
            "what_this_cluster_can_support": (
                "TODO: state what this cluster can contribute to the narrative "
                "(e.g., plausibility, effect size estimates, subgroup context)"
            ),
            "what_it_cannot_support": (
                "TODO: state what this cluster cannot substitute for "
                "(e.g., 'cannot substitute for direct continue vs stop comparisons')"
            ),
            "preferred_anchor_ids": pids[:2],
            "synthesis_note": (
                f"TODO: write a 1–2 sentence synthesis of what these {len(pids)} papers "
                f"collectively suggest about {display_name}"
            ),
        })

    if not clusters:
        clusters = [{
            "cluster_id": "C1",
            "theme": "General indirect support",
            "member_paper_ids": [],
            "what_this_cluster_can_support": "TODO",
            "what_it_cannot_support": "TODO",
            "preferred_anchor_ids": [],
            "synthesis_note": "TODO: fill after screening is complete",
        }]

    return {
        "_generated": date.today().isoformat(),
        "_instructions": (
            "One entry per indirect evidence cluster. "
            "Populated automatically from scored_candidates.csv query_family groupings. "
            "Review and edit the TODO fields before narrative drafting. "
            "The LLM writes ONE paragraph per cluster — not one paragraph per paper. "
            "Each paragraph: state what the cluster suggests → what it cannot replace → bounded interpretation."
        ),
        "clusters": clusters,
    }


def main_build_methods_snapshot() -> None:
    parser = argparse.ArgumentParser(
        description="Build methods_snapshot.json and section_packets.json from review artifacts.",
    )
    parser.add_argument("--review-dir", required=True, help="Path to the literature_review directory")
    parser.add_argument("--topic-config", default="", help="Optional path to topic_config.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")
    args = parser.parse_args()

    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        print(f"[build_methods_snapshot] Review directory not found: {review_dir}")
        return

    cfg: dict = {}
    if args.topic_config and Path(args.topic_config).exists():
        try:
            cfg = json.loads(Path(args.topic_config).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[build_methods_snapshot] Could not load topic_config: {exc}")

    question_type = cfg.get("question_type") or ""

    # Build methods_snapshot.json
    snapshot_path = review_dir / "methods_snapshot.json"
    if not snapshot_path.exists() or args.force:
        snapshot = build_methods_snapshot(review_dir, cfg)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[build_methods_snapshot] Wrote {snapshot_path}")
    else:
        existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if existing.get("_instructions"):
            # File is a placeholder — regenerate
            snapshot = build_methods_snapshot(review_dir, cfg)
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[build_methods_snapshot] Updated placeholder → {snapshot_path}")
        else:
            print(f"[build_methods_snapshot] Skipped (already populated): {snapshot_path} — use --force to overwrite")

    # Build section_packets.json
    packets_path = review_dir / "section_packets.json"
    if not packets_path.exists() or args.force:
        packets = build_section_packets(review_dir, cfg, question_type)
        packets_path.write_text(json.dumps(packets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[build_methods_snapshot] Wrote {packets_path}")
    else:
        print(f"[build_methods_snapshot] Skipped (already populated): {packets_path} — use --force to overwrite")

    # Build evidence_clusters.json
    clusters_path = review_dir / "evidence_clusters.json"
    if not clusters_path.exists() or args.force:
        clusters = build_evidence_clusters(review_dir, cfg)
        clusters_path.write_text(json.dumps(clusters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[build_methods_snapshot] Wrote {clusters_path}")
    else:
        existing_cl = json.loads(clusters_path.read_text(encoding="utf-8"))
        # Regenerate if all clusters have empty member_paper_ids (template placeholder)
        all_empty = all(
            not c.get("member_paper_ids")
            for c in existing_cl.get("clusters", [{}])
        )
        if all_empty:
            clusters = build_evidence_clusters(review_dir, cfg)
            clusters_path.write_text(json.dumps(clusters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[build_methods_snapshot] Updated empty placeholder → {clusters_path}")
        else:
            print(f"[build_methods_snapshot] Skipped (already populated): {clusters_path} — use --force to overwrite")

    print()
    print("Next steps:")
    print("  1. Review and fill any TODO fields in methods_snapshot.json")
    print("  2. Review and edit cluster themes and synthesis_note in evidence_clusters.json")
    print("  3. Review anchor_paper_ids in section_packets.json and adjust if needed")
    print("  4. Run review.py build_review_narrative to generate review_briefing.md")
    print("  5. Draft each section individually using section_packets (Stage N2)")
    print("  6. Apply global revision (Stage N3) before final output")

# build_proposal_bridge


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def unique(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    for value in values:
        v = str(value or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def build_protocol_inputs(evidence_matrix_csv: Path, metadata: dict[str, str]) -> dict:
    rows = read_csv(evidence_matrix_csv)
    return {
        **metadata,
        "measurement_tools": unique(row.get("measures", "") for row in rows),
        "confounders": unique(row.get("candidate_confounders", "") for row in rows),
        "effect_modifiers": unique(row.get("candidate_effect_modifiers", "") for row in rows),
        "suggested_methods": unique(row.get("suggested_methods", "") for row in rows),
        "evidence_gaps": unique(row.get("protocol_implication", "") for row in rows),
    }


def build_text(review_dir: Path) -> str:
    contract = read_json(review_dir / "review_contract.json")
    suff = read_json(review_dir / "evidence_sufficiency_report.json")
    study = read_csv(review_dir / "study_registry.csv")
    measurement = read_csv(review_dir / "measurement_registry.csv")
    confounders = read_csv(review_dir / "confounder_registry.csv")
    decisions = read_csv(review_dir / "evidence_to_decision_table.csv")
    protocol_inputs = read_json(review_dir / "protocol_inputs.json")

    topic = contract.get("topic", "the target study question")
    population = contract.get("population") or protocol_inputs.get("population", "")
    exposure = contract.get("exposure") or protocol_inputs.get("exposure", "")
    outcome = contract.get("outcome") or protocol_inputs.get("outcome", "")
    estimand = contract.get("primary_estimand") or protocol_inputs.get("primary_estimand", "")
    mode = contract.get("project_mode", "")
    design_type = contract.get("design_type", "")

    strength_items = suff.get("key_strengths", [])
    if not strength_items:
        strength_items = [row.get("decision", "") for row in decisions[:3] if row.get("decision")]

    gap_items = suff.get("key_gaps", [])
    if not gap_items:
        gap_items = protocol_inputs.get("evidence_gaps", [])

    tools = unique([row.get("preferred_tool", "") for row in measurement])
    core_confounders = unique(
        [row.get("variable", "") for row in confounders if "confounder" in row.get("classification", "")]
    )
    mechanism_variables = unique(
        [row.get("variable", "") for row in confounders if "mediator" in row.get("classification", "")]
    )
    designs = unique([row.get("design", "") for row in study])

    lines = [
        "# Proposal Bridge",
        "",
        "## Research Problem and Significance",
        "",
        f"The literature supports {topic} as a meaningful research problem"
        + (f" in {population}" if population else "")
        + ".",
        "",
        "## Current Evidence and Stable Findings",
        "",
    ]
    if strength_items:
        lines.extend([f"- {item}" for item in strength_items])
    else:
        lines.append("- The retained literature is sufficient to define a bounded research problem.")

    lines.extend([
        "",
        "## Gap Statement",
        "",
    ])
    if gap_items:
        lines.extend([f"- {item}" for item in gap_items])
    else:
        lines.append("- The main unresolved gap should be stated more precisely after screening and synthesis.")

    lines.extend([
        "",
        "## Proposed Question Lock",
        "",
        f"- Population: {population or 'FILL IN'}",
        f"- Exposure: {exposure or 'FILL IN'}",
        f"- Outcome: {outcome or 'FILL IN'}",
        f"- Primary estimand: {estimand or 'FILL IN'}",
        f"- Design type: {design_type or 'FILL IN'}",
        f"- Project mode: {mode or 'FILL IN'}",
        "",
        "## Measurement and Variable Feasibility",
        "",
        f"- Common study designs in the retained evidence: {', '.join(designs) if designs else 'not yet summarized'}",
        f"- Candidate measurement tools: {', '.join(tools) if tools else 'not yet summarized'}",
        "",
        "## Confounder and Mechanism Boundary",
        "",
        f"- Core confounder candidates: {', '.join(core_confounders) if core_confounders else 'not yet summarized'}",
        f"- Variables that should stay out of the primary model unless justified: {', '.join(mechanism_variables) if mechanism_variables else 'none yet classified'}",
        "",
        "## Risks and Downgrade Triggers",
        "",
        f"- Evidence sufficiency recommendation: {suff.get('mode_recommendation', 'not available')}",
        f"- Design fit: {suff.get('design_fit', 'not available')}",
        f"- Causal-temporality risk: {suff.get('causal_temporality_risk', 'not available')}",
        f"- Interpretation risk: {suff.get('interpretation_risk', 'not available')}",
        "",
        "## Opening-Report Use",
        "",
        "Use this bridge to write significance, gap, innovation, and feasibility sections in the opening report without overstating causality or evidence strength.",
        "",
    ])
    return "\n".join(lines)


def main_build_proposal_bridge() -> None:
    parser = argparse.ArgumentParser(description="Build proposal_bridge.md from a review package.")
    parser.add_argument("review_dir")
    parser.add_argument("--output", default=None)
    parser.add_argument("--evidence-matrix-csv", default="")
    parser.add_argument("--protocol-output", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--project-mode", default="")
    parser.add_argument("--population", default="")
    parser.add_argument("--exposure", default="")
    parser.add_argument("--outcome", default="")
    parser.add_argument("--mediator", default="")
    parser.add_argument("--moderator", default="")
    args = parser.parse_args()

    review_dir = Path(args.review_dir)
    if args.evidence_matrix_csv:
        evidence_matrix = Path(args.evidence_matrix_csv)
        if not evidence_matrix.exists():
            raise SystemExit(f"Evidence matrix not found: {evidence_matrix}")
        protocol_output = (
            Path(args.protocol_output)
            if args.protocol_output
            else review_dir / "protocol_inputs.json"
        )
        protocol_output.parent.mkdir(parents=True, exist_ok=True)
        protocol_output.write_text(
            json.dumps(
                build_protocol_inputs(
                    evidence_matrix,
                    {
                        "project_mode": args.project_mode,
                        "study_title_candidate": args.title,
                        "population": args.population,
                        "exposure": args.exposure,
                        "outcome": args.outcome,
                        "mediator": args.mediator,
                        "moderator": args.moderator,
                    },
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    output = Path(args.output) if args.output else review_dir / "proposal_bridge.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_text(review_dir), encoding="utf-8")

# build_review_narrative
SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def csv_to_md(rows: list[dict], col_map: dict | None = None, max_rows: int = 50) -> str:
    if not rows:
        return "_No data._"
    cols = list(col_map.keys()) if col_map else list(rows[0].keys())
    headers = [col_map.get(c, c) if col_map else c for c in cols]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join([":---"] * len(cols)) + " |",
    ]
    for row in rows[:max_rows]:
        cells = [str(row.get(c, "")).strip().replace("\n", " ")[:120] for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def load_manifest(project_root: Path) -> dict:
    p = project_root / "study_manifest.json"
    if not p.exists():
        sys.exit(
            f"ERROR: study_manifest.json not found in {project_root}.\n"
            "Copy core/schemas/study_manifest_template.json, fill in your topic, and re-run."
        )
    m = json.loads(p.read_text(encoding="utf-8"))
    topic = m.get("topic", {})
    required = ["population", "setting", "exposure", "outcome"]
    empty = [f for f in required if not str(topic.get(f, "")).strip()]
    if empty:
        sys.exit(
            f"ERROR: study_manifest.json topic fields are empty: {empty}\n"
            "Fill in all topic fields before running this script."
        )
    return m


def extract_screening_numbers(review_dir: Path, n_retained: int) -> dict[str, str]:
    search_log = read_csv(review_dir / "search_log.csv")
    screen_dec = read_csv(review_dir / "screening_decisions.csv")

    n_retrieved: str = "not available"
    if search_log:
        totals = [r.get("n_retrieved") or "" for r in search_log]
        totals = [t for t in totals if str(t).strip().isdigit()]
        if totals:
            n_retrieved = str(sum(int(t) for t in totals))

    n_dedup: str = "not available"
    if search_log:
        dedup_vals = [r.get("n_after_dedup") or "" for r in search_log]
        dedup_vals = [v for v in dedup_vals if str(v).strip().isdigit()]
        if dedup_vals:
            n_dedup = str(max(int(v) for v in dedup_vals))

    # Fall back to candidate_records_dedup.csv row count when search_log column is absent
    if n_dedup == "not available":
        dedup_csv = review_dir / "candidate_records_dedup.csv"
        if dedup_csv.exists():
            dedup_rows = read_csv(dedup_csv)
            if dedup_rows:
                n_dedup = str(len(dedup_rows))

    if n_retrieved == "not available":
        raw_csv = review_dir / "candidate_records_raw.csv"
        if raw_csv.exists():
            raw_rows = read_csv(raw_csv)
            if raw_rows:
                n_retrieved = str(len(raw_rows))

    n_screened: str = "not available"
    n_included: str = "not available"
    n_excluded: str = "not available"
    if screen_dec:
        n_screened = str(len(screen_dec))
        inc = sum(1 for r in screen_dec if str(r.get("decision", "")).lower() == "include")
        exc = sum(1 for r in screen_dec if str(r.get("decision", "")).lower() == "exclude")
        n_included = str(inc) if inc > 0 else "not available"
        n_excluded = str(exc) if exc > 0 else "not available"

    return {
        "n_retrieved": n_retrieved,
        "n_dedup": n_dedup,
        "n_screened": n_screened,
        "n_included": str(n_retained) if n_retained > 0 else "not available",
        "n_excluded": n_excluded,
    }


def build_briefing(project_root: Path, review_dir: Path) -> str:
    manifest     = load_manifest(project_root)
    topic_cfg    = manifest["topic"]
    exposure     = topic_cfg["exposure"]
    outcome      = topic_cfg["outcome"]
    population   = topic_cfg["population"]
    setting      = topic_cfg["setting"]
    comparison   = topic_cfg.get("comparison", "")
    design_type  = (manifest.get("design_type") or "observational").strip()
    mode         = normalize_project_mode(manifest.get("project_mode", "research"))
    question_type = (manifest.get("question_type") or "").strip()
    review_goal  = (manifest.get("review_goal") or "").strip()

    # Load review contract for supplementary fields
    rc           = read_json(review_dir / "review_contract.json")
    estimand     = rc.get("primary_estimand", "") or topic_cfg.get("primary_estimand", "")
    mediator     = rc.get("mediator", "") or topic_cfg.get("candidate_mediator", "")
    moderator    = rc.get("moderator", "") or topic_cfg.get("candidate_modifier", "")
    review_type  = rc.get("review_type", "structured_narrative")
    reporting_framework = rc.get("reporting_framework", [])
    synthesis_method = rc.get("synthesis_method", "")

    # Registries
    study_reg      = read_csv(review_dir / "study_registry.csv")
    measure_reg    = read_csv(review_dir / "measurement_registry.csv")
    confounder_reg = read_csv(review_dir / "confounder_registry.csv")
    evidence_dec   = read_csv(review_dir / "evidence_to_decision_table.csv")
    effect_reg     = read_csv(review_dir / "effect_registry.csv")
    claim_reg      = read_csv(review_dir / "claim_registry.csv")
    bias_reg       = read_csv(review_dir / "bias_registry.csv")
    citation_reg   = read_json(review_dir / "citation_registry.json")
    suff_report    = read_json(review_dir / "evidence_sufficiency_report.json")

    # harvest outcomes / confounders from manifest
    harvest = manifest.get("harvest") or topic_cfg.get("harvest") or {}
    harvest_outcomes: list[str] = []
    if isinstance(harvest, dict):
        harvest_outcomes = [str(o).strip() for o in (harvest.get("outcomes") or []) if str(o).strip()]
    confounders_list: list[str] = list(manifest.get("confounders_core") or
                                        topic_cfg.get("confounders_core") or [])
    trigger_vocab: list[str] = list(manifest.get("trigger_vocabulary") or
                                     topic_cfg.get("trigger_vocabulary") or [])

    # Screening numbers
    n_retained = len(study_reg)
    nums = extract_screening_numbers(review_dir, n_retained)

    # Role / tier counts
    from collections import Counter
    role_counts = Counter(r.get("primary_role", "other") for r in study_reg)
    tier_counts = Counter(r.get("synthesis_tier", "unassigned") for r in study_reg)
    anchor_counts = Counter((r.get("anchor_eligible") or "no").strip().lower() for r in study_reg)

    # Citations
    entries = citation_reg.get("entries", []) if isinstance(citation_reg, dict) else []

    # Sufficiency
    suff_level = suff_report.get("level", "") if isinstance(suff_report, dict) else ""
    suff_notes = suff_report.get("notes", "") if isinstance(suff_report, dict) else ""
    deliverable_style = rc.get("deliverable_style", "") if isinstance(rc, dict) else ""
    narrative_readiness = rc.get("narrative_readiness", "") if isinstance(rc, dict) else ""
    anchor_density_by_outcome = rc.get("anchor_density_by_outcome", {}) if isinstance(rc, dict) else {}

    # ---- Assemble briefing ----
    L: list[str] = []

    L += [
        "# Review Briefing",
        "",
        "> **For the LLM writing the narrative synthesis.**",
        "> This document aggregates all structured review data into one place.",
        "> Read every section, then write the literature review following the",
        "> Narrative Spine Requirement in SKILL.md.",
        "> Do NOT reproduce this briefing verbatim — synthesise from it.",
        "",
    ]

    # ---- Topic ----
    L += [
        "## Topic",
        "",
        f"- **Exposure:** {exposure}",
        f"- **Comparison:** {comparison}" if comparison else "",
        f"- **Outcome:** {outcome}",
        f"- **Population:** {population}",
        f"- **Setting:** {setting}",
        f"- **Primary estimand:** {estimand}" if estimand else "",
        f"- **Question type:** {question_type}" if question_type else "",
        f"- **Review goal:** {review_goal}" if review_goal else "",
        f"- **Review type:** {review_type}",
        f"- **Reporting framework:** {', '.join(reporting_framework) if isinstance(reporting_framework, list) else reporting_framework}",
        f"- **Synthesis method:** {synthesis_method}",
        f"- **Design type:** {design_type}",
        f"- **Project mode:** {mode}",
        "",
    ]
    # Remove empty lines
    L = [line for line in L if line != ""]

    L.append("")

    if harvest_outcomes:
        L += ["### Outcomes of interest (from harvest config)", ""]
        for o in harvest_outcomes:
            L.append(f"- {o}")
        L.append("")

    if confounders_list:
        L += ["### Pre-specified confounders (from manifest)", ""]
        for c in confounders_list:
            L.append(f"- {c}")
        L.append("")

    if mediator:
        L += [f"### Candidate mediator: {mediator}", ""]
    if moderator:
        L += [f"### Candidate effect modifier: {moderator}", ""]
    if trigger_vocab:
        L += ["### Clinical trigger vocabulary (from config)", ""]
        for t in trigger_vocab:
            L.append(f"- {t}")
        L.append("")

    # ---- Search and Screening ----
    L += [
        "## Search and Screening (PRISMA numbers)",
        "",
        f"| Stage | n |",
        f"|---|---|",
        f"| Retrieved (all sources) | {nums['n_retrieved']} |",
        f"| After deduplication | {nums['n_dedup']} |",
        f"| Screened (title/abstract) | {nums['n_screened']} |",
        f"| Excluded at title/abstract | {nums['n_excluded']} |",
        f"| Full-text assessed / included | {nums['n_included']} |",
        f"| Retained for synthesis | {n_retained} |",
        "",
        "_Values shown as 'not available' come directly from missing CSV columns — do not estimate._",
        "",
    ]

    # Search log source breakdown
    search_log = read_csv(review_dir / "search_log.csv")
    if search_log:
        source_status: dict[str, dict[str, int]] = {}
        for row in search_log:
            src = row.get("source", "unknown")
            status = row.get("status", "planned")
            source_status.setdefault(src, {})
            source_status[src][status] = source_status[src].get(status, 0) + 1
        L += ["### Source execution summary", ""]
        L += ["| Source | retrieved | blocked / planned |",
              "|---|---|---|"]
        for src, counts in sorted(source_status.items()):
            retrieved = counts.get("retrieved", 0)
            not_retrieved = sum(v for k, v in counts.items() if k != "retrieved")
            L.append(f"| {src} | {retrieved} | {not_retrieved} |")
        L.append("")

    # ---- Cite-Ready Reference List ----
    # This section produces a compact inline-citation guide so the LLM can embed
    # publication-facing numeric markers while keeping registry IDs in the briefing.
    # It is placed BEFORE the full study registry table so it is easy to scan.
    #
    # Author/DOI data is cross-referenced from scored_candidates.csv (which carries
    # these fields from the live search) when study_registry.csv does not have them.
    if study_reg:
        # Build a lookup from scored_candidates.csv (paper_id → row) for fallback metadata.
        scored_lookup: dict[str, dict] = {}
        scored_path = review_dir / "scored_candidates.csv"
        if scored_path.exists():
            for sc_row in read_csv(scored_path):
                pid_key = (sc_row.get("paper_id") or "").strip()
                if pid_key:
                    scored_lookup[pid_key] = sc_row

        L += [
            "## Cite-Ready Reference List (use these for inline citations)",
            "",
            "> **How to cite inline:** use the numeric marker assigned in `citation_registry.json`, for example `[1]`.",
            "> Keep PaperID and citation_id in the registry and binding map; do not expose internal IDs in publication prose.",
            "> Every factual claim about a specific study must use its registered number and match the numbered References entry.",
            "",
        ]
        ref_by_paper = {
            str(entry.get("paper_id", "")): entry.get("reference_number")
            for entry in entries
            if entry.get("paper_id") and entry.get("reference_number")
        }
        for row in study_reg[:50]:
            pid = row.get("paper_id", "")
            yr  = row.get("year", "n.d.")
            # Try study_registry first, then fall back to scored_candidates
            fallback = scored_lookup.get(pid, {})
            authors_raw = (row.get("authors") or row.get("author") or
                           fallback.get("authors") or fallback.get("author") or "")
            title_short = (row.get("title") or fallback.get("title") or "")[:80]
            doi = (row.get("doi") or fallback.get("doi") or
                   row.get("url") or fallback.get("url") or "")
            if authors_raw:
                first_seg = authors_raw.split(";")[0].strip()
                if "," in first_seg:
                    # "LastName, FirstName" or "LastName, FI." format
                    first_author = first_seg.split(",")[0].strip()
                else:
                    # "LastName FI" or "LastName FI." format (PubMed E-utilities / OpenAlex)
                    first_author = first_seg.split()[0].strip() if first_seg else "—"
                n_authors = len([a for a in authors_raw.split(";") if a.strip()])
                author_token = f"{first_author} et al." if n_authors > 2 else first_author
            else:
                author_token = "—"
            role = row.get("primary_role", "")
            reference_number = ref_by_paper.get(pid, "unassigned")
            L.append(f"- **Reference [{reference_number}]** (registry paper_id `{pid}`) {author_token}, {yr} — _{title_short}_ — doi:{doi} [{role}]")
        L.append("")

    # ---- Study Registry ----
    L += ["## Retained Studies (study_registry.csv)", ""]
    if study_reg:
        L += [f"**Total retained: {n_retained}**", ""]
        L += [f"**Role breakdown:** {dict(role_counts)}", ""]
        if tier_counts:
            L += [f"**Synthesis tier breakdown:** {dict(tier_counts)}", ""]
        if anchor_counts:
            L += [f"**Anchor eligibility:** {dict(anchor_counts)}", ""]
        study_cols = {
            "paper_id": "ID",
            "synthesis_tier": "Tier",
            "anchor_eligible": "Anchor",
            "primary_role": "Role",
            "year": "Year",
            "design": "Design",
            "population": "Population",
            "exposure": "Exposure",
            "outcome": "Outcome",
            "direct_question_match": "Question match",
            "comparator_integrity_ok": "Comparator",
            "time_zero_clear": "Time zero",
            "prior_user_design": "Prior user",
            "sample_size": "N",
            "core_findings": "Core findings",
            "limitations": "Limitations",
            "protocol_implication": "Protocol implication",
            "quality_signal": "Quality",
        }
        L.append(csv_to_md(study_reg, study_cols, max_rows=50))
        L.append("")
    else:
        L += [
            "_study_registry.csv is empty. This means screening and data extraction have not yet been completed._",
            "_The narrative synthesis section on evidence (Section 4) should reflect this honestly: no screened and extracted evidence is available yet._",
            "",
        ]

    # ---- Effect Registry ----
    if effect_reg:
        L += ["## Effect Estimates (effect_registry.csv)", ""]
        effect_cols = {
            "paper_id": "Paper",
            "outcome_family": "Outcome family",
            "outcome": "Outcome",
            "exposure_contrast": "Contrast",
            "effect_measure": "Measure",
            "point_estimate": "Estimate",
            "ci_lower": "CI lower",
            "ci_upper": "CI upper",
            "effect_directness": "Directness",
            "supports_primary_direction_claim": "Primary claim",
            "population_subgroup": "Subgroup",
            "effect_trustworthiness": "Trust",
            "note": "Note",
        }
        L.append(csv_to_md(effect_reg, effect_cols, max_rows=40))
        L.append("")

    # ---- Claim Registry ----
    if claim_reg:
        L += ["## Claim Registry (claim_registry.csv)", ""]
        claim_cols = {
            "claim_id": "ID",
            "outcome_family": "Outcome family",
            "claim_text": "Claim",
            "allowed_strength": "Max strength",
            "anchor_required": "Anchor req",
            "supports_primary_direction_claim": "Primary claim",
            "eligible_anchor_paper_ids": "Eligible anchors",
            "supporting_paper_ids": "Papers",
            "note": "Note",
        }
        L.append(csv_to_md(claim_reg, claim_cols, max_rows=30))
        L.append("")

    # ---- Bias Registry ----
    if bias_reg:
        L += ["## Bias Assessment (bias_registry.csv)", ""]
        bias_cols = {
            "paper_id": "Paper",
            "bias_domain": "Domain",
            "severity": "Severity",
            "direction": "Direction",
            "note": "Note",
        }
        L.append(csv_to_md(bias_reg, bias_cols, max_rows=40))
        L.append("")

    # ---- Measurement Registry ----
    L += ["## Measurement Registry (measurement_registry.csv)", ""]
    if measure_reg:
        measure_cols = {
            "construct": "Construct",
            "preferred_tool": "Preferred tool",
            "evidence_role": "Evidence role",
            "reason_from_literature": "Justification",
            "protocol_use": "Protocol use",
            "limitation_or_bias": "Limitation",
        }
        L.append(csv_to_md(measure_reg, measure_cols, max_rows=20))
        L.append("")
    else:
        L += ["_measurement_registry.csv is empty._", ""]

    # ---- Confounder Registry ----
    L += ["## Confounder Registry (confounder_registry.csv)", ""]
    if confounder_reg:
        conf_cols = {
            "variable": "Variable",
            "classification": "Role",
            "support_level": "Support",
            "rationale": "Rationale",
            "recommended_main_model_role": "Model action",
        }
        L.append(csv_to_md(confounder_reg, conf_cols, max_rows=20))
        L.append("")
    else:
        L += ["_confounder_registry.csv is empty._", ""]

    # ---- Evidence-to-Decision ----
    L += ["## Evidence-to-Decision (evidence_to_decision_table.csv)", ""]
    if evidence_dec:
        etd_cols = {
            "decision_id": "ID",
            "decision": "Decision",
            "evidence_summary": "Evidence summary",
            "supporting_paper_ids": "Papers",
            "confidence": "Confidence",
            "downstream_use": "Use",
        }
        L.append(csv_to_md(evidence_dec, etd_cols, max_rows=20))
        L.append("")
    else:
        L += ["_evidence_to_decision_table.csv is empty._", ""]

    # ---- Evidence Sufficiency ----
    L += ["## Evidence Sufficiency (evidence_sufficiency_report.json)", ""]
    if deliverable_style:
        L.append(f"**Deliverable style:** {deliverable_style}")
    if narrative_readiness:
        L.append(f"**Narrative readiness:** {narrative_readiness}")
    if anchor_density_by_outcome:
        L.append(f"**Anchor density by outcome:** {anchor_density_by_outcome}")
    if suff_level:
        L.append(f"**Level:** {suff_level}")
    if suff_notes:
        L.append(f"**Notes:** {suff_notes}")
    if not suff_level and not suff_notes:
        L.append("_evidence_sufficiency_report.json is empty._")
    L.append("")

    # ---- Citations ----
    L += ["## Citation Registry (citation_registry.json)", ""]
    if entries:
        for i, e in enumerate(entries, start=1):
            doi_part = f" doi:{e['doi']}" if e.get("doi") else ""
            pmid_part = f" PMID:{e['pmid']}" if e.get("pmid") else ""
            role_part = f" [{e['role']}]" if e.get("role") else ""
            L.append(
                f"{i}. **{e.get('title', '—')}** ({e.get('year', 'n.d.')}). "
                f"*{e.get('authors', '')}*. {e.get('journal', '')}"
                f"{doi_part}{pmid_part}{role_part}"
            )
        L.append("")
    else:
        L += ["_citation_registry.json is empty or has no entries._",
              "_Populate it after screening and full-text reading._", ""]

    # ---- Methods Snapshot (structured methods layer for narrative) ----
    methods_snap = read_json(review_dir / "methods_snapshot.json")
    if methods_snap and isinstance(methods_snap, dict) and "_instructions" not in methods_snap:
        L += [
            "## Methods Snapshot (methods_snapshot.json)",
            "",
            "> Use this block when writing the Search and Screening section.",
            "> All values here are machine-derived from the actual project files — use them verbatim.",
            "",
        ]
        for k, v in methods_snap.items():
            if v and str(v).strip() not in ("TODO", "not available", "null", ""):
                if isinstance(v, list):
                    L.append(f"**{k}:**")
                    for item in v:
                        L.append(f"  - {item}")
                elif isinstance(v, dict):
                    L.append(f"**{k}:** {json.dumps(v, ensure_ascii=False)}")
                else:
                    L.append(f"**{k}:** {v}")
        L.append("")

    # ---- Section Packets (per-section drafting guidance) ----
    section_pkts = read_json(review_dir / "section_packets.json")
    pkt_list: list[dict] = []
    if isinstance(section_pkts, dict):
        pkt_list = section_pkts.get("sections", [])
    elif isinstance(section_pkts, list):
        pkt_list = section_pkts
    if pkt_list:
        L += [
            "## Section Drafting Packets (section_packets.json)",
            "",
            "> **MANDATORY:** Draft each section below INDIVIDUALLY.",
            "> Do NOT write the entire review in one pass.",
            "> For each section: read its packet, write that section, stop.",
            "> Only after all sections are drafted, apply Stage N3 global revision.",
            "",
        ]
        for pkt in pkt_list:
            sname = pkt.get("section_name") or pkt.get("section") or "unnamed"
            L.append(f"### Section: {sname}")
            for k, v in pkt.items():
                if k in ("section_name", "section"):
                    continue
                if v:
                    if isinstance(v, list):
                        L.append(f"- **{k}:**")
                        for item in v:
                            L.append(f"  - {item}")
                    else:
                        L.append(f"- **{k}:** {v}")
            L.append("")

    # ---- Evidence Clusters (for indirect evidence synthesis) ----
    ev_clusters = read_json(review_dir / "evidence_clusters.json")
    cluster_list: list[dict] = []
    if isinstance(ev_clusters, dict):
        cluster_list = ev_clusters.get("clusters", [])
    if cluster_list:
        # Only surface clusters with member papers (skip template placeholders)
        real_clusters = [c for c in cluster_list if c.get("member_paper_ids")]
        if real_clusters:
            L += [
                "## Evidence Clusters (evidence_clusters.json)",
                "",
                "> Use these clusters when writing the Broader Supporting Evidence section.",
                "> Write ONE paragraph per cluster — NOT one paragraph per paper.",
                "",
            ]
            for cl in real_clusters:
                cid = cl.get("cluster_id") or "?"
                theme = cl.get("theme") or ""
                L.append(f"**Cluster {cid} — {theme}**")
                if cl.get("member_paper_ids"):
                    L.append(f"  Papers: {', '.join(cl['member_paper_ids'])}")
                if cl.get("what_this_cluster_can_support"):
                    L.append(f"  Can support: {cl['what_this_cluster_can_support']}")
                if cl.get("what_it_cannot_support"):
                    L.append(f"  Cannot substitute: {cl['what_it_cannot_support']}")
                if cl.get("synthesis_note"):
                    L.append(f"  Synthesis note: {cl['synthesis_note']}")
                L.append("")

    # ---- Candidate pool summary (for orientation, not for prose) ----
    dedup_csv = review_dir / "candidate_records_dedup.csv"
    if dedup_csv.exists():
        dedup_rows = read_csv(dedup_csv)
        if dedup_rows and n_retained == 0:
            L += [
                "## Candidate Pool (not yet screened)",
                "",
                f"_study_registry.csv is empty but candidate_records_dedup.csv has {len(dedup_rows)} records._",
                "_The following are unscreened candidates. Do NOT treat them as retained studies._",
                "_Use them to orient yourself to what the candidate pool contains before writing._",
                "",
            ]
            cand_cols = {
                "title": "Title",
                "authors": "Authors",
                "year": "Year",
                "doi": "DOI",
                "query_family": "Query family",
                "local_relevance_score": "Score",
            }
            L.append(csv_to_md(dedup_rows, cand_cols, max_rows=60))
            L.append("")

    # ---- Writing instructions (reminder) ----
    L += [
        "---",
        "",
        "## Writing Instructions for the LLM",
        "",
        "Use the data above to write the literature review narrative.",
        "Treat this briefing as the evidence-map layer, not as prose to imitate.",
        f"The selected product is `{review_type}`; follow its declared reporting framework and synthesis method.",
        "Use `references/review_synthesis.md` as the default writing architecture.",
        "",
        "---",
        "",
        "### Stage N1 — Section Planning (do this mentally before writing anything)",
        "",
        "Before drafting, read the Section Drafting Packets above and confirm for each section:",
        "- Which 2–4 anchor papers will this section rely on?",
        "- What is the single central judgment for this section?",
        "- What is the main methodological limitation to name?",
        "- What is the allowed_strength_ceiling? Will no claim exceed it?",
        "- Are there forbidden papers that must not appear as primary support?",
        "",
        "---",
        "",
        "### Stage N2 — Per-Section Drafting (write one section at a time)",
        "",
        "**Write each section individually, not the whole review at once.**",
        "For each section, follow this paragraph structure:",
        "1. Open with a scope judgment (what the evidence as a whole shows) — not with a paper name.",
        "2. Name at most 2 anchor papers with their specific finding and key design feature.",
        "3. State the most important limitation immediately after the finding.",
        "4. End with a bounded interpretation aligned to the section's allowed_strength_ceiling.",
        "",
        "**Anti-listing rule (strictly enforced):**",
        "NEVER write: 'Study X found Y. Study Z found W. Study A also found B.'",
        "INSTEAD write: 'The available direct comparative evidence, concentrated in cohort studies from",
        "Scandinavia and the UK, consistently shows [direction] for [outcome] [3,7],",
        "though all estimates carry [main confounding limitation].'",
        "",
        "**For the Broader Supporting Evidence section:**",
        "Write ONE paragraph per evidence cluster from the Evidence Clusters above.",
        "Do not write one paragraph per paper.",
        "Each cluster paragraph should state what the cluster collectively suggests,",
        "then immediately state what it cannot substitute for.",
        "",
        "**For Outcome-specific sections with no direct evidence:**",
        "Write one sentence stating the gap and one sentence on what indirect evidence implies.",
        "Do NOT write a long paragraph just to say 'evidence is limited.'",
        "",
        "---",
        "",
        "### Stage N3 — Global Revision (after all sections are drafted)",
        "",
        "Before producing the final output, apply these global constraints:",
        "1. Find all sentence openers used 3+ times across sections — delete or vary them.",
        "2. Find all paragraphs that only say 'evidence is limited' without a specific finding — delete or replace.",
        "3. Check every direction-of-effect claim against claim_registry.csv allowed_strength — downgrade if needed.",
        "4. Remove ALL pipeline meta-language: pipeline, registry, tier, candidate pool, briefing, anchor_eligible, skill.",
        "5. Keep the Review Methods reproducible (normally 450–700 words) and the late flow-accounting paragraph compact.",
        "6. Verify every study-specific claim has its registered numeric inline marker, for example [3] or [3,7].",
        "7. Check that no indirect or background paper is being used to support a primary direction-of-effect claim.",
        "8. Populate the main-body Study Characteristics and Effect Evidence Matrix tables from the registries.",
        "",
        "---",
        "",
        "### Follow the Narrative Spine",
        "",
        "1. Open with why this question matters — not with search logistics.",
        "2. Explain why existing literature types cannot directly answer the specific question.",
        "3. Write the direct evidence section around the strongest studies, not every retained study.",
        "4. Use indirect supporting evidence only to interpret context, measurement, bias, and patient perspective.",
        "5. Synthesise by outcome dimension or theme — not by listing papers one by one.",
        "6. Describe methodological challenges as literature limitations, not as package logic.",
        "7. State the research gaps and design implications.",
        "8. Keep Search and Screening brief and late in the review.",
        "",
        "### Evidence-layer separation",
        "",
        "- Direct comparative evidence supports the main direction-of-effect discussion.",
        "- Broader evidence sharpens plausibility or boundaries — must be labeled indirect when not exact-match.",
        "- Patient-centered or symptom evidence explains trade-offs — does not replace hard-outcome evidence.",
        "- Guideline or policy material frames uncertainty — must not anchor empirical outcome claims.",
        "",
        "**Do not reproduce this briefing.** Write prose that a reviewer or epidemiologist would write.",
        "**Do not mention the briefing, the pipeline, or package logic** in the narrative body.",
        "**Inline PRISMA counts** must come from the PRISMA table above — not from narrative estimation.",
        "**Claim strength** must not exceed what claim_registry.csv records as `allowed_strength`.",
        "**Only studies with `anchor_eligible=yes` may support primary direction-of-effect claims.**",
        "**Do not let `appendix_only` or `background_policy` studies support main conclusions.**",
        "**Use `outcome_family` to organise direct evidence and evidence gaps.**",
        "**Do not write one-paper-one-sentence lists across a whole section.**",
        "If the study_registry is empty, say so honestly: no screened evidence is available yet,",
        "and describe what the candidate pool suggests about the field.",
        "",
        "### Forbidden main-text language",
        "",
        "These terms belong in the briefing or validator, not in the main review body:",
        "- workflow, pipeline, upgrade, system, tier, anchor_eligible",
        "- review_briefing.md, study_registry.csv, claim_registry.csv, effect_registry.csv",
        "- candidate pool, screening architecture, package logic, narrative_readiness",
        "",
        "### Inline Citation Requirement (MANDATORY)",
        "",
        "Every sentence that attributes a specific finding, estimate, design feature, or",
        "descriptive fact to a named study MUST include an inline citation. Use the",
        "'Cite-Ready Reference List' above to look up the correct numeric reference marker.",
        "",
        "Required citation format:",
        "  [reference_number] immediately after the supported clause, e.g. [3] or [3,7]",
        "",
        "Examples of CORRECT inline citations:",
        "  'A population-based cohort reported a higher adjusted outcome rate in the exposed group",
        "   [3].'",
        "  'A measurement study found acceptable reliability for the prespecified instrument",
        "   [7].'",
        "",
        "Examples of INCORRECT (missing citations — must be fixed before delivery):",
        "  'A cohort study found a higher outcome rate.' ← no registered numeric citation",
        "  'Guidelines recommend the intervention.' ← no registered numeric citation",
        "",
        "The References section at the end must list every numeric marker cited in the body",
        "in Vancouver or APA format using the full bibliographic data from citation_registry.json.",
        "",
    ]

    return "\n".join(L)


def main_build_review_narrative() -> None:
    parser = argparse.ArgumentParser(
        description="Build a structured data briefing for LLM-written literature review narrative."
    )
    parser.add_argument("project_root",
                        help="Path to the project root (must contain study_manifest.json)")
    parser.add_argument("--review-dir", default=None,
                        help="Path to literature_review/ dir (defaults to <project_root>/literature_review)")
    parser.add_argument("--output", default=None,
                        help="Output path (default: <review_dir>/review_briefing.md)")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    review_dir   = Path(args.review_dir) if args.review_dir else project_root / "literature_review"
    out_path     = Path(args.output) if args.output else review_dir / "review_briefing.md"

    text = build_briefing(project_root, review_dir)
    write_text(out_path, text)
    print(f"Review briefing written to: {out_path}")
    print("Next step: read the briefing and write the narrative following SKILL.md Narrative Spine Requirement.")

# build_review_scaffold
CSV_HEADERS: dict[str, str] = {
    "search_log.csv": (
        "search_id,search_round,parent_search_id,concept_focus,query_family,"
        "question_type,review_goal,query,source,source_query,date_searched,"
        "date_limit,language_limit,recommended_retrieval_target,n_retrieved,"
        "n_after_dedup,scope,status,rationale_trigger,note\n"
    ),
    "candidate_records_raw.csv": (
        "search_id,search_round,query_family,source,source_rank,title,authors,"
        "year,published_date,doi,url,abstract,publication_status,"
        "source_record_id,matched_query,local_relevance_score,strategy_match_score\n"
    ),
    "candidate_records_dedup.csv": (
        "search_id,search_round,query_family,source,source_rank,title,authors,"
        "year,published_date,doi,url,abstract,publication_status,"
        "source_record_id,matched_query,local_relevance_score,strategy_match_score\n"
    ),
    # scored_candidates.csv: produced by evidence.py score_candidates (not a scaffold file)
    "screening_decisions.csv": (
        "paper_id,title,decision,screening_stage,role,reason,"
        "direct_question_match,design_integrity_ok,comparator_integrity_ok,"
        "time_zero_clear,prior_user_design,directness_tier,"
        "exclusion_reason_code,question_match_summary,include_in_synthesis,include_in_protocol\n"
    ),
    "study_registry.csv": (
        "paper_id,synthesis_tier,anchor_eligible,primary_role,secondary_role,"
        "publication_status,year,design,population,exposure,outcome,sample_size,"
        "setting,measures,core_findings,limitations,protocol_implication,"
        "suggested_methods,record_relevance,study_credibility,quality_signal,"
        "direct_question_match,design_integrity_ok,comparator_integrity_ok,"
        "time_zero_clear,prior_user_design,outcome_family,outcome_family_all,"
        "title,doi,authors\n"
    ),
    "measurement_registry.csv": (
        "construct,preferred_tool,evidence_role,reason_from_literature,"
        "key_example_paper_ids,supporting_evidence_row_ids,protocol_use,limitation_or_bias\n"
    ),
    "confounder_registry.csv": (
        "variable,classification,support_level,supporting_paper_ids,"
        "supporting_evidence_row_ids,rationale,recommended_main_model_role\n"
    ),
    "evidence_to_decision_table.csv": (
        "decision_id,decision,evidence_summary,supporting_paper_ids,"
        "supporting_evidence_row_ids,downstream_use,confidence\n"
    ),
    "effect_registry.csv": (
        "effect_id,study_id,paper_id,outcome_family,outcome,effect_measure,"
        "point_estimate,ci_lower,ci_upper,exposure_contrast,direction,effect_directness,"
        "supports_primary_direction_claim,population_subgroup,"
        "effect_trustworthiness,notes\n"
    ),
    # Unified claim_registry: merges both schema definitions from output_schema.md
    "claim_registry.csv": (
        "claim_id,outcome_family,claim_text,claim_type,allowed_strength,"
        "evidence_direction,anchor_required,supports_primary_direction_claim,"
        "eligible_anchor_paper_ids,supporting_paper_ids,counter_study_ids,"
        "supporting_evidence_row_ids,confidence,narrative_position,note\n"
    ),
    # Unified bias_registry: field names aligned with output_schema.md
    "bias_registry.csv": (
        "paper_id,bias_domain,severity,bias_direction,evidence_of_bias,reviewer_note\n"
    ),
    "quality_appraisal_registry.csv": (
        "paper_id,domain,judgment,raw_signal,evidence_source,note\n"
    ),
    "fulltext_inventory.csv": (
        "paper_id,title,doi,text_source,fulltext_status,open_access_url,source_file,"
        "deep_read_completed,deep_read_date,claim_bearing,note\n"
    ),
}
FILES: list[str] = [
    "review_contract.json",
    "search_log.csv",
    "candidate_records_raw.csv",
    "candidate_records_dedup.csv",
    "screening_decisions.csv",
    "study_registry.csv",
    "measurement_registry.csv",
    "confounder_registry.csv",
    "effect_registry.csv",
    "claim_registry.csv",
    "bias_registry.csv",
    "quality_appraisal_registry.csv",
    "fulltext_inventory.csv",
    "citation_registry.json",
    "evidence_to_decision_table.csv",
    "evidence_sufficiency_report.json",
    "methods_snapshot.json",
    "section_packets.json",
    "evidence_clusters.json",
    "publication_manifest.json",
    "delivery_quality_report.json",
    "review_briefing.md",
    "search_strategy.md",
    "research_gaps.md",
    "related_work.md",
    "protocol_inputs.json",
    "proposal_bridge.md",
]
QUESTION_TYPE_OUTCOME_SECTIONS: dict[str, list[str]] = {
    "treatment_strategy_comparison": [
        "Primary Outcome",
        "Secondary Outcomes",
        "Adverse Effects or Safety Outcomes",
        "Patient-Centered and Quality-of-Life Outcomes",
    ],
    "exposure_outcome_association": [
        "Primary Outcome",
        "Secondary Outcomes",
        "Effect Modification and Subgroups",
    ],
    "prognosis": [
        "Event-Free Survival or Time to Event",
        "Secondary Prognostic Outcomes",
        "Subgroup Variation",
    ],
    "diagnostic_measurement": [
        "Sensitivity and Specificity",
        "Positive and Negative Predictive Value",
        "Inter-Rater Reliability and Agreement",
    ],
    "mechanism_mediation": [
        "Primary Pathway Evidence",
        "Supporting Biological Mechanism Evidence",
        "Effect Mediated by Proposed Intermediary",
    ],
    "guideline_to_evidence": [
        "Guideline Recommendation vs Available Evidence",
        "Evidence Gaps Relative to Current Guidance",
    ],
    "methods_estimand": [
        "Target Trial Emulation Evidence",
        "Estimand Framework and Sensitivity Analyses",
    ],
}
GENERIC_OUTCOME_SECTIONS = [
    "Primary Outcome",
    "Secondary Outcomes",
]


def outcome_sections_for_type(question_type: str, outcome_families: list[str]) -> list[str]:
    """Return outcome section names: config-supplied families take priority,
    then question_type defaults, then generic."""
    if outcome_families:
        return outcome_families
    return QUESTION_TYPE_OUTCOME_SECTIONS.get(question_type, GENERIC_OUTCOME_SECTIONS)


def narrative_template(
    question_type: str,
    outcome_families: list[str],
    review_type: str = "structured_narrative",
) -> str:
    """Return the YAML front-matter + section skeleton for the narrative review.

    No statin-specific, disease-specific, or outcome-specific content is
    hardcoded here.  All outcome section headings come from the config or
    from question_type defaults.
    """
    sections_from_type = outcome_sections_for_type(question_type, outcome_families)
    outcome_section_md = "\n\n".join(
        f"## {name}\n\nTODO: for this outcome family — which studies provide direct evidence, "
        "which anchor them, how strong is the conclusion, and what is the main limitation?"
        for name in sections_from_type
    )

    intro_framing = {
        "treatment_strategy_comparison": (
            "TODO: explain the real-world decision burden, why strategy comparison "
            "cannot be replaced by general efficacy evidence, and what the target population needs."
        ),
        "exposure_outcome_association": (
            "TODO: explain the epidemiological significance of the exposure-outcome relationship, "
            "the population-level importance, and why this association warrants systematic review."
        ),
        "prognosis": (
            "TODO: explain the prognostic question, who it affects, and why current prognosis "
            "data are insufficient for clinical or public-health decision-making."
        ),
        "diagnostic_measurement": (
            "TODO: explain the diagnostic gap, what current measurement tools miss, "
            "and why a structured review of diagnostic accuracy evidence is needed."
        ),
        "mechanism_mediation": (
            "TODO: explain the mechanistic hypothesis, why pathway evidence matters "
            "for the broader research question, and what prior evidence is insufficient."
        ),
        "guideline_to_evidence": (
            "TODO: explain how the guideline recommendation arose, what evidence underpins it, "
            "and what evidence gaps challenge its current formulation."
        ),
    }.get(question_type, "TODO: explain the burden, importance, and why this question matters now.")

    decision_framing = {
        "treatment_strategy_comparison": (
            "TODO: explain why this is a strategy question — not just an efficacy or adherence question — "
            "and why existing literature on treatment initiation cannot directly answer it."
        ),
        "exposure_outcome_association": (
            "TODO: explain what designs and analytic approaches are needed to address confounding, "
            "reverse causation, and measurement error for this specific association."
        ),
    }.get(
        question_type,
        "TODO: explain why this question cannot be answered by adjacent or general literature.",
    )

    qt_label = question_type.replace("_", " ") if question_type else "the study question"
    methods_note = (
        f"Question type: `{qt_label}`" if question_type else "Question type: [set question_type in topic_config.json]"
    )

    review_label = {
        "structured_narrative": "Structured Narrative Review",
        "systematic_no_meta": "Systematic Review Without Meta-analysis",
        "systematic_meta": "Systematic Review and Meta-analysis",
    }[review_type]
    framework_note = {
        "structured_narrative": "SANRA is the narrative-quality aid; report the reproducible search and screening transparently.",
        "systematic_no_meta": "Report with PRISMA 2020/PRISMA-S and synthesize without meta-analysis using SWiM.",
        "systematic_meta": "Report with PRISMA 2020/PRISMA-S and prespecify the quantitative synthesis model.",
    }[review_type]

    return "\n".join([
        "---",
        f'title: "{review_label}"',
        "geometry: margin=1in",
        "fontsize: 12pt",
        'mainfont: "Times New Roman"',
        "---",
        "",
        "# Clinical or Scientific Importance and Review Question",
        "",
        f"<!-- {methods_note} -->",
        "",
        "## Why This Matters",
        "",
        intro_framing,
        "",
        "## Why This Cannot Be Answered by Adjacent Literature",
        "",
        decision_framing,
        "",
        "## Review Question and Target Outcome Families",
        "",
        "TODO: define the exact review question (population, exposure/comparison, outcomes, design scope).",
        "",
        "# Review Methods",
        "",
        f"TODO: {framework_note}",
        "Report databases, exact source-specific search strings, final search dates, restrictions,",
        "per-source yields, deduplication, two-stage screening, appraisal method, and synthesis method.",
        "",
        "# Evidence Map and Study Characteristics",
        "",
        "TODO: summarize the design, setting, sample, exposure/outcome measurement, adjustment set, and follow-up where applicable.",
        "",
        "| Study | Design and setting | Sample | Exposure/comparison | Outcome measure | Adjustment/follow-up | Main limitation |",
        "|---|---|---:|---|---|---|---|",
        "| TODO | TODO | TODO | TODO | TODO | TODO | TODO |",
        "",
        "# Effect Evidence Matrix",
        "",
        "TODO: report the main estimate and interval for each direct study; use NR only when the source genuinely does not report it.",
        "",
        "| Study | Design | Contrast | Outcome | Effect measure | Estimate (95% CI) | Risk-of-bias judgment |",
        "|---|---|---|---|---|---|---|",
        "| TODO | TODO | TODO | TODO | TODO | TODO | TODO |",
        "",
        "# Evidence Classification and Directness",
        "",
        "TODO: classify the evidence base by type before listing individual papers.",
        "Types might include: direct comparative studies, indirect supporting evidence,",
        "measurement-validation studies, systematic reviews or guidelines, mechanistic evidence.",
        "For each type, state what it can and cannot support for this specific question.",
        "",
        "# Direct Evidence",
        "",
        "TODO: synthesize only the strongest, closest-match evidence.",
        "Do not list papers one by one — synthesize across them by judgment:",
        "direction of evidence, consistency, main anchor studies, and collective limitation.",
        "",
        "# Broader Supporting Evidence",
        "",
        "TODO: group indirect or adjacent evidence into 2–4 clusters by theme.",
        "For each cluster: state what it contributes and what it cannot substitute.",
        "Do not annotate papers individually.",
        "",
        "# Outcome-Specific Interpretation",
        "",
        outcome_section_md,
        "",
        "# Risk of Bias, Heterogeneity, and Certainty",
        "",
        "TODO: give design-appropriate study-level judgments, explain heterogeneity by measurement/design/adjustment,",
        "identify counterevidence and plausible reporting/publication bias, and state outcome-specific certainty with reasons.",
        "Discuss only limitations that materially change interpretation strength.",
        "Focus on the bias types most relevant to this question type:",
        "  - For treatment_strategy_comparison: confounding by indication, time-zero issues, immortal time, prior-user bias",
        "  - For exposure_outcome_association: confounding, reverse causation, OR-as-RR, cross-sectional temporality",
        "  - For prognosis: competing risks, loss to follow-up, case-mix variation",
        "  - Adapt to the actual question_type.",
        "",
        "# Evidence Gaps and Research Implications",
        "",
        "## What Can Be Said Now",
        "",
        "TODO: state the most defensible conclusion — no stronger than the evidence allows.",
        "",
        "## What Should Not Be Overstated",
        "",
        "TODO: state what the current evidence does NOT justify — be explicit.",
        "",
        "## What Research Is Most Needed",
        "",
        "TODO: state the most important next-step evidence need and preferred study design.",
        "",
        "# Search and Screening Accounting",
        "",
        "TODO: keep this section brief (1–2 paragraphs) and factual.",
        "Report: databases searched, final date, inclusion criteria, records identified, duplicates removed,",
        "title/abstract and full-text screening totals, included studies, and full-text exclusions by reason.",
        "Do not let this section organize the review or appear before the evidence synthesis.",
        "",
        "# References",
        "",
    ])
METHODS_SNAPSHOT_TEMPLATE = {
    "_instructions": (
        "Fill this file before writing the narrative. "
        "review.py build_review_narrative and the narrative LLM read from here. "
        "This is an internal intermediate file — not a user-facing deliverable."
    ),
    "review_question": "",
    "review_type": "structured_narrative",
    "reporting_framework": ["SANRA"],
    "synthesis_method": "thematic synthesis by design, outcome, and directness",
    "databases_searched": [],
    "search_dates": {},
    "date_limits": "",
    "language_limits": "No restriction (or specify)",
    "inclusion_criteria": [],
    "exclusion_criteria": [],
    "screening_process": "",
    "fulltext_availability_limitations": "",
    "quality_appraisal_framework": "scoring_rubric.md + study_quality_framework.md",
    "prisma_counts": {
        "identified_total": 0,
        "after_dedup": 0,
        "title_abstract_screened": 0,
        "fulltext_assessed": 0,
        "included": 0,
        "excluded_reasons": {},
    },
    "access_limitations": [],
}
SECTION_PACKETS_TEMPLATE = {
    "_instructions": (
        "One entry per narrative section. "
        "Generated by review.py build_review_narrative or manually from scored_candidates.csv. "
        "Consumed by the LLM when drafting each section individually. "
        "Each section should be drafted independently before global revision."
    ),
    "packets": [
        {
            "section_id": "direct_evidence",
            "section_name": "Direct Evidence",
            "section_goal": "Synthesize only the strongest exact-match or near-exact-match evidence",
            "allowed_strength_ceiling": "suggestive",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [],
        },
        {
            "section_id": "indirect_evidence",
            "section_name": "Broader Supporting Evidence",
            "section_goal": "Group indirect evidence into 2-4 clusters by theme; state what each adds and cannot substitute",
            "allowed_strength_ceiling": "preliminary",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [],
        },
    ],
}
SEARCH_STRATEGY_TEMPLATE = """# Search Strategy

## Core Sources

| Source | Access | Notes |
|---|---|---|
| OpenAlex | Free | Abstract only (inverted index); no full text |
| PubMed/MEDLINE | Free | NCBI E-utilities |
| Semantic Scholar | Free | Graph API; open-access PDF links for subset |
| Europe PMC | Free | EBI REST API; MEDLINE + PMC + preprints |
| medRxiv | Free | Preprints; interval API + local keyword scoring |
| bioRxiv | Free | Preprints; interval API + local keyword scoring |
| Embase | Subscription | Blocked unless institutional credentials provided |
| Web of Science | Subscription | Blocked unless institutional credentials provided |

## Round Structure

1. Round 1 broad mapping: direct association, population/setting, measurement, and design queries across the core sources.
2. Read anchor papers: identify better terminology, instruments, mechanisms, conflicting findings, and boundary conditions.
3. Run `evidence.py score_candidates` to assign 4-dimensional scores (record_relevance, study_credibility, likely_directness, decision_role).
4. Round 2 expansion: add reading-driven queries triggered by the anchor papers.
5. Run `retrieval.py chase_citations` on high-scoring anchors (record_relevance ≥ 4) for forward + backward citation graph expansion.
6. Round 3 citation chaining: cited-by, reference chasing, and contradiction-focused follow-up.

## Default Volume Targets

- Round 1: inspect about 30-50 ranked records per core source; 40 is a good default target.
- Read at least 12-20 anchor papers (record_relevance ≥ 4) after deduplication before Round 2.
- Round 2: inspect about 15-30 records per triggered query family and source.
- Citation chase: up to 30 new records per anchor (forward + backward combined).
- Stop when an additional expansion cycle no longer changes downstream decisions.

## Logging Rule

For each query, log: search_round, parent_search_id, query_family, source, source_query,
date_searched, retrieval counts, and rationale_trigger in search_log.csv.

TODO: fill in actual search dates and retrieval counts as the review progresses.
"""


def main_build_review_scaffold() -> None:
    parser = argparse.ArgumentParser(
        description="Create a literature-review output scaffold.",
    )
    parser.add_argument("output_dir", help="Directory for review artifacts")
    parser.add_argument(
        "--topic-config",
        default="",
        help="Optional path to topic_config.json; used to inject outcome family names into the narrative template",
    )
    parser.add_argument(
        "--review-type",
        choices=["structured_narrative", "systematic_no_meta", "systematic_meta"],
        default="",
        help="Product type; topic_config.review_type takes precedence when present",
    )
    parser.add_argument(
        "--question-type",
        default="",
        help="Override question_type (treatment_strategy_comparison / exposure_outcome_association / ...); "
        "ignored if topic_config.json already contains question_type",
    )
    args = parser.parse_args()

    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Resolve question_type and outcome families from config or CLI
    cfg: dict = {}
    if args.topic_config:
        cfg = load_json(Path(args.topic_config))
    question_type = cfg.get("question_type") or args.question_type or ""
    review_type = cfg.get("review_type") or args.review_type or "structured_narrative"
    if review_type not in {"structured_narrative", "systematic_no_meta", "systematic_meta"}:
        raise SystemExit(f"Unsupported review_type: {review_type}")
    harvest = cfg.get("harvest") or {}
    outcome_families = [o for o in (harvest.get("outcomes") or []) if o]

    # Create skeleton files
    for name in FILES:
        path = root / name
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing and existing not in ("{}", "{}"):
                continue  # Never overwrite non-empty files
        if name in CSV_HEADERS:
            path.write_text(CSV_HEADERS[name], encoding="utf-8")
        elif name.endswith(".json"):
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")

    contract_path = root / "review_contract.json"
    if contract_path.read_text(encoding="utf-8").strip() in ("{}", ""):
        frameworks = {
            "structured_narrative": ["SANRA"],
            "systematic_no_meta": ["PRISMA 2020", "PRISMA-S", "SWiM"],
            "systematic_meta": ["PRISMA 2020", "PRISMA-S"],
        }[review_type]
        synthesis_methods = {
            "structured_narrative": "thematic critical synthesis by design, outcome, and directness",
            "systematic_no_meta": "SWiM synthesis by design, outcome, directness, and effect direction without significance vote counting",
            "systematic_meta": "quantitative meta-analysis; specify effect harmonization, model, heterogeneity, and sensitivity analyses before release",
        }
        contract_template = {
            "contract_version": "3.0",
            "review_type": review_type,
            "reporting_framework": frameworks,
            "synthesis_method": synthesis_methods[review_type],
            "project_mode": cfg.get("project_mode", "research"),
            "question_type": question_type,
            "review_goal": cfg.get("review_goal", "protocol_support"),
            "delivery_preset": cfg.get("delivery_preset", "decision_grade"),
            "design_type": cfg.get("design_type", "cross_sectional"),
            "generated_at": "",
            "status": "draft",
            "downgrade_state": "",
            "topic": cfg.get("topic", ""),
            "primary_estimand": cfg.get("primary_estimand", ""),
            "evidence_sufficiency": "not_assessed",
            "decision_ids": [],
            "citation_ids": [],
            "older_search_cutoff_disclosed": False,
            "sparse_evidence_exception": {"applies": False},
            "deliverable_style": "narrative_review",
            "narrative_readiness": "draft",
            "anchor_density_by_outcome": {},
        }
        contract_path.write_text(json.dumps(contract_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # search_strategy.md
    search_md = root / "search_strategy.md"
    if not search_md.exists() or not search_md.read_text(encoding="utf-8").strip():
        search_md.write_text(SEARCH_STRATEGY_TEMPLATE, encoding="utf-8")

    # literature_review_synthesis.md — question_type-aware, domain-agnostic
    review_md = root / "literature_review_synthesis.md"
    if not review_md.exists():
        review_md.write_text(narrative_template(question_type, outcome_families, review_type), encoding="utf-8")

    # review_briefing.md placeholder
    briefing_md = root / "review_briefing.md"
    if not briefing_md.exists() or not briefing_md.read_text(encoding="utf-8").strip():
        briefing_md.write_text(
            "# Review Briefing\n\nGenerated by `review.py build_review_narrative`.\n\n"
            "This file is a pipeline-facing evidence map and writing input.\n"
            "Do not copy its language into `literature_review_synthesis.md`.\n",
            encoding="utf-8",
        )

    # proposal_bridge.md placeholder
    proposal_md = root / "proposal_bridge.md"
    if not proposal_md.exists() or not proposal_md.read_text(encoding="utf-8").strip():
        proposal_md.write_text(
            "\n".join([
                "# Proposal Bridge",
                "",
                "## Research Problem and Significance",
                "",
                "TODO: state why the topic matters now in scientific or public-health terms.",
                "",
                "## Current Evidence and Stable Findings",
                "",
                "TODO: summarize what the literature already supports with reasonable confidence.",
                "",
                "## Gap Statement",
                "",
                "TODO: define the unresolved gap precisely rather than claiming generic novelty.",
                "",
                "## Proposed Question Lock",
                "",
                "TODO: lock population, exposure, comparison, outcome, and primary estimand.",
                "",
                "## Measurement and Variable Feasibility",
                "",
                "TODO: justify why the planned variables and tools are actually measurable.",
                "",
                "## Confounder and Mechanism Boundary",
                "",
                "TODO: state the minimal sufficient adjustment logic and what stays out of the primary model.",
                "",
                "## Risks and Downgrade Triggers",
                "",
                "TODO: state what would weaken the proposal or force a narrower claim.",
                "",
            ]) + "\n",
            encoding="utf-8",
        )

    # methods_snapshot.json — structured intermediate for narrative methods section
    methods_path = root / "methods_snapshot.json"
    if not methods_path.exists() or methods_path.read_text(encoding="utf-8").strip() in ("{}", "{}"):
        methods_template = dict(METHODS_SNAPSHOT_TEMPLATE)
        methods_template["review_type"] = review_type
        methods_template["reporting_framework"] = {
            "structured_narrative": ["SANRA"],
            "systematic_no_meta": ["PRISMA 2020", "PRISMA-S", "SWiM"],
            "systematic_meta": ["PRISMA 2020", "PRISMA-S"],
        }[review_type]
        methods_path.write_text(json.dumps(methods_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # section_packets.json — intermediate input for per-section LLM drafting
    packets_path = root / "section_packets.json"
    if not packets_path.exists() or packets_path.read_text(encoding="utf-8").strip() in ("{}", "{}"):
        packets_path.write_text(json.dumps(SECTION_PACKETS_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # evidence_clusters.json — groups indirect evidence by theme for cluster-based synthesis
    clusters_path = root / "evidence_clusters.json"
    if not clusters_path.exists() or clusters_path.read_text(encoding="utf-8").strip() in ("{}", "{}"):
        clusters_template = {
            "_instructions": (
                "Group indirect evidence into 2-4 thematic clusters. "
                "Populated by review.py build_methods_snapshot after scored_candidates.csv is filled. "
                "Consumed by the LLM when drafting the Broader Supporting Evidence section. "
                "The LLM writes ONE paragraph per cluster — not one paragraph per paper."
            ),
            "clusters": [
                {
                    "cluster_id": "C1",
                    "theme": "TODO: name the first evidence cluster (e.g., 'initiation/efficacy evidence')",
                    "member_paper_ids": [],
                    "what_this_cluster_can_support": "TODO: state what this cluster can contribute",
                    "what_it_cannot_support": "TODO: state what this cluster cannot substitute",
                    "preferred_anchor_ids": [],
                    "synthesis_note": "TODO: 1-2 sentence synthesis of what this cluster collectively says",
                },
            ],
        }
        clusters_path.write_text(json.dumps(clusters_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[build_review_scaffold] Scaffold ready at: {root}")
    if question_type:
        print(f"  question_type: {question_type}")
    print(f"  review_type: {review_type}")
    if outcome_families:
        print(f"  outcome families injected: {', '.join(outcome_families)}")
    else:
        print("  outcome families: using question_type defaults (supply --topic-config to customise)")


COMMANDS = {
    "build_methods_snapshot": main_build_methods_snapshot,
    "build_proposal_bridge": main_build_proposal_bridge,
    "build_review_narrative": main_build_review_narrative,
    "build_review_scaffold": main_build_review_scaffold,
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
