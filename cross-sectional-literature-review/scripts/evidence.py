#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/evidence.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import textwrap
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

# run_fulltext_extraction
ALLOWED_DIRECTIONS = {"favorable", "harmful", "null", "mixed", "unclear"}
ALLOWED_DIRECTNESS = {"direct", "indirect", "background"}
ALLOWED_TRUST = {"high", "moderate", "low", "not_applicable"}
ALLOWED_BIAS_SEVERITY = {"high", "moderate", "low", "none_detected", "unclear"}
ALLOWED_BIAS_DIRECTION = {"towards_null", "away_from_null", "uncertain", "not_applicable"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def included_records(review_dir: Path) -> list[dict[str, str]]:
    scored = read_csv(review_dir / "scored_candidates.csv")
    if scored:
        rows = [row for row in scored if row.get("include_in_review", "").strip().lower() in {"yes", "true", "1", "include"}]
        if rows:
            return rows
    screening = read_csv(review_dir / "screening_decisions.csv")
    include_ids = {
        row.get("paper_id", "")
        for row in screening
        if row.get("include_in_synthesis", "").strip().lower() in {"yes", "true", "1"}
        or row.get("decision", "").strip().lower() == "include"
    }
    studies = read_csv(review_dir / "study_registry.csv")
    return [row for row in studies if row.get("paper_id", "") in include_ids] or studies


def packet_template(record: dict[str, str]) -> dict:
    paper_id = record.get("paper_id") or record.get("id") or ""
    return {
        "paper_id": paper_id,
        "citation_title": record.get("title", ""),
        "source_file_or_url": record.get("fulltext_path") or record.get("url") or "",
        "text_source": "abstract | fulltext | unavailable",
        "deep_read_date": "",
        "claim_bearing": "yes | no",
        "study_design": record.get("study_design") or record.get("design") or "",
        "population_summary": record.get("population", ""),
        "direct_question_match": "yes | no | unclear",
        "comparator_integrity_ok": "yes | no | unclear | NA",
        "time_zero_clear": "yes | no | unclear | NA",
        "prior_user_design": "yes | no | unclear | NA",
        "effect_rows": [],
        "bias_appraisal": [],
        "quality_appraisal": [
            {
                "domain": "",
                "judgment": "",
                "raw_signal": "",
                "evidence_source": "section/table/page",
                "note": "",
            }
        ],
        "study_contribution": {"can_support": "", "cannot_support": "", "main_limitation": ""},
        "review_status": "needs_manual_extraction",
    }


def prepare(review_dir: Path) -> int:
    packets_dir = review_dir / "fulltext_extractions"
    packets_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    for record in included_records(review_dir):
        paper_id = record.get("paper_id") or record.get("id") or ""
        if not paper_id:
            continue
        path = packets_dir / f"{paper_id}.json"
        if not path.exists():
            write_json(path, packet_template(record))
            created += 1
    print(f"Prepared {created} new extraction packet(s) in {packets_dir}")
    return created


def validate_packet(path: Path, payload: dict) -> list[str]:
    errors: list[str] = []
    paper_id = payload.get("paper_id") or path.stem
    if payload.get("review_status") != "complete":
        errors.append(f"{paper_id}: review_status must be 'complete'")
    for field in ("study_design", "population_summary", "direct_question_match"):
        if not str(payload.get(field, "")).strip():
            errors.append(f"{paper_id}: missing {field}")
    if not str(payload.get("deep_read_date", "")).strip():
        errors.append(f"{paper_id}: deep_read_date is required for a completed extraction")
    if str(payload.get("text_source", "")).strip().lower() in {"", "abstract", "unavailable", "abstract | fulltext | unavailable"}:
        errors.append(f"{paper_id}: completed deep reading requires a full-text or authoritative-report text_source")
    contribution = payload.get("study_contribution", {})
    for field in ("can_support", "cannot_support", "main_limitation"):
        if not str(contribution.get(field, "")).strip():
            errors.append(f"{paper_id}: study_contribution.{field} is empty")
    for idx, row in enumerate(payload.get("effect_rows", []), start=1):
        prefix = f"{paper_id} effect row {idx}"
        for field in ("outcome_family", "outcome", "effect_measure", "direction", "quote_text", "quote_source", "effect_directness", "effect_trustworthiness"):
            if not str(row.get(field, "")).strip():
                errors.append(f"{prefix}: missing {field}")
        if row.get("direction") not in ALLOWED_DIRECTIONS:
            errors.append(f"{prefix}: invalid direction")
        if row.get("effect_directness") not in ALLOWED_DIRECTNESS:
            errors.append(f"{prefix}: invalid effect_directness")
        if row.get("effect_trustworthiness") not in ALLOWED_TRUST:
            errors.append(f"{prefix}: invalid effect_trustworthiness")
        estimate = str(row.get("point_estimate", "")).strip()
        if not estimate:
            errors.append(f"{prefix}: missing point_estimate; use NR only after checking the full text")
        elif estimate.lower() not in {"nr", "not reported"}:
            if not str(row.get("ci_lower", "")).strip() or not str(row.get("ci_upper", "")).strip():
                errors.append(f"{prefix}: numeric point_estimate requires ci_lower and ci_upper")
    for idx, row in enumerate(payload.get("bias_appraisal", []), start=1):
        prefix = f"{paper_id} bias row {idx}"
        if row.get("severity") not in ALLOWED_BIAS_SEVERITY:
            errors.append(f"{prefix}: invalid severity")
        if row.get("bias_direction") not in ALLOWED_BIAS_DIRECTION:
            errors.append(f"{prefix}: invalid bias_direction")
        if not str(row.get("evidence_of_bias", "")).strip():
            errors.append(f"{prefix}: evidence_of_bias is empty")
    appraisal = payload.get("quality_appraisal", [])
    if len({str(row.get("domain", "")).strip().lower() for row in appraisal if str(row.get("domain", "")).strip()}) < 4:
        errors.append(f"{paper_id}: quality_appraisal must cover at least 4 distinct design-appropriate domains")
    for idx, row in enumerate(appraisal, start=1):
        prefix = f"{paper_id} quality row {idx}"
        for field in ("domain", "judgment", "raw_signal", "evidence_source"):
            value = str(row.get(field, "")).strip()
            if not value or value.lower() in {"todo", "tbd", "fill in", "section/table/page"}:
                errors.append(f"{prefix}: missing or placeholder {field}")
    return errors


def finalize(review_dir: Path) -> None:
    packets = sorted((review_dir / "fulltext_extractions").glob("*.json"))
    if not packets:
        raise SystemExit("No extraction packets found; run without --finalize first.")
    effect_rows: list[dict] = []
    bias_rows: list[dict] = []
    inventory_rows: list[dict] = []
    quality_rows: list[dict] = []
    errors: list[str] = []
    for path in packets:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        errors.extend(validate_packet(path, payload))
        paper_id = payload.get("paper_id") or path.stem
        inventory_rows.append(
            {
                "paper_id": paper_id,
                "title": payload.get("citation_title", ""),
                "text_source": payload.get("text_source", ""),
                "fulltext_status": payload.get("review_status", ""),
                "source_file": payload.get("source_file_or_url", ""),
                "deep_read_completed": "yes" if payload.get("review_status") == "complete" else "no",
                "deep_read_date": payload.get("deep_read_date") or date.today().isoformat(),
                "claim_bearing": payload.get("claim_bearing", "yes"),
                "note": payload.get("study_contribution", {}).get("main_limitation", ""),
            }
        )
        for idx, row in enumerate(payload.get("effect_rows", []), start=1):
            effect_rows.append(
                {
                    "effect_id": row.get("effect_id") or f"{paper_id}_E{idx:02d}",
                    "study_id": paper_id,
                    "paper_id": paper_id,
                    "outcome_family": row.get("outcome_family", ""),
                    "outcome": row.get("outcome", ""),
                    "effect_measure": row.get("effect_measure", ""),
                    "point_estimate": row.get("point_estimate", ""),
                    "ci_lower": row.get("ci_lower", ""),
                    "ci_upper": row.get("ci_upper", ""),
                    "exposure_contrast": row.get("exposure_contrast", ""),
                    "direction": row.get("direction", ""),
                    "effect_directness": row.get("effect_directness", ""),
                    "supports_primary_direction_claim": row.get("supports_primary_direction_claim", "no"),
                    "population_subgroup": row.get("population_subgroup", ""),
                    "effect_trustworthiness": row.get("effect_trustworthiness", ""),
                    "notes": row.get("quote_text", ""),
                }
            )
        for row in payload.get("bias_appraisal", []):
            bias_rows.append(
                {
                    "paper_id": paper_id,
                    "bias_domain": row.get("bias_domain", ""),
                    "severity": row.get("severity", ""),
                    "bias_direction": row.get("bias_direction", ""),
                    "evidence_of_bias": row.get("evidence_of_bias", ""),
                    "reviewer_note": row.get("reviewer_note", ""),
                }
            )
        for row in payload.get("quality_appraisal", []):
            quality_rows.append(
                {
                    "paper_id": paper_id,
                    "domain": row.get("domain", ""),
                    "judgment": row.get("judgment", ""),
                    "raw_signal": row.get("raw_signal", ""),
                    "evidence_source": row.get("evidence_source", ""),
                    "note": row.get("note", ""),
                }
            )
    if errors:
        raise SystemExit("Extraction validation failed:\n" + "\n".join(errors))
    write_csv(review_dir / "effect_registry.csv", effect_rows, ["effect_id", "study_id", "paper_id", "outcome_family", "outcome", "effect_measure", "point_estimate", "ci_lower", "ci_upper", "exposure_contrast", "direction", "effect_directness", "supports_primary_direction_claim", "population_subgroup", "effect_trustworthiness", "notes"])
    write_csv(review_dir / "bias_registry.csv", bias_rows, ["paper_id", "bias_domain", "severity", "bias_direction", "evidence_of_bias", "reviewer_note"])
    write_csv(review_dir / "quality_appraisal_registry.csv", quality_rows, ["paper_id", "domain", "judgment", "raw_signal", "evidence_source", "note"])
    write_csv(review_dir / "fulltext_inventory.csv", inventory_rows, ["paper_id", "title", "text_source", "fulltext_status", "source_file", "deep_read_completed", "deep_read_date", "claim_bearing", "note"])
    print(f"Finalized {len(effect_rows)} effect row(s), {len(bias_rows)} bias row(s), and {len(quality_rows)} quality-appraisal row(s).")


def main_run_fulltext_extraction() -> int:
    parser = argparse.ArgumentParser(description="Prepare or validate topic-neutral per-paper evidence extraction packets.")
    parser.add_argument("project_root")
    parser.add_argument("--review-dir", default="")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root)
    review_dir = Path(args.review_dir) if args.review_dir else root / "literature_review"
    if args.finalize:
        finalize(review_dir)
    else:
        prepare(review_dir)
    return 0

# score_candidates
SCORING_COLUMNS = [
    # Provenance fields (pre-filled by this script)
    "paper_id",
    "title",
    "authors",
    "year",
    "source",
    "doi",
    "url",
    "query_family",
    "publication_status",
    "abstract_snippet",
    # ---- Scoring dimensions (LLM fills these) ----
    # Dimension 1: Record Relevance (0–5)
    "record_relevance",
    # Dimension 2: Study Credibility
    "study_credibility",
    # Dimension 3: Effect Trustworthiness
    "effect_trustworthiness",
    # Dimension 4: Claim Strength Ceiling
    "claim_strength_ceiling",
    # Additional judgment fields
    "likely_directness",
    "decision_role",
    "study_design",
    "key_finding",
    "main_limitation",
    "rationale",
    "include_in_review",
    "include_in_anchor_reading",
]
RECORD_RELEVANCE_RUBRIC = """\
| Score | Meaning |
|---|---|
| 5 | Directly answers the question — population, exposure, comparator, and outcome all match |
| 4 | Strong match on 3 of 4 elements; minor population or outcome drift |
| 3 | Answers a closely related question; useful for measurement, mechanism, or confounder logic |
| 2 | Loosely related; background context or methods signal only |
| 1 | Peripheral; retain only if it fills a specific documented gap |
| 0 | Not relevant — exclude |"""
STUDY_CREDIBILITY_RUBRIC = """\
| Label | Criteria |
|---|---|
| `strong` | Well-executed design; explicit confounder rationale; transparent sample; validated outcome ascertainment; triangulated findings |
| `adequate` | Sound design; adequate confounder handling; some limitations acknowledged; interpretations appropriate for design |
| `limited` | Notable design weakness, convenience sample, or missing confounder detail; useful for context, not for anchoring decisions |
| `weak` | Severe design flaws, unexplained adjustment, or findings that overreach the design; background only or exclude |"""
EFFECT_TRUSTWORTHINESS_RUBRIC = """\
| Label | Criteria |
|---|---|
| `high` | Primary pre-specified analysis; adequate adjustment; time zero clear; interpretable comparator; CI reported; no major bias |
| `moderate` | Informative but one concern: residual confounding, secondary analysis, or preprint status |
| `low` | Notable bias: immortal time, prevalent user bias, confounding by indication, inadequate adjustment |
| `not_applicable` | No quantitative effect estimate (methods paper, narrative review, prevalence-only study) |"""
CLAIM_STRENGTH_RUBRIC = """\
| Label | Allowed narrative language |
|---|---|
| `definitive` | "evidence demonstrates", "studies show" — requires ≥2 high-trustworthiness + strong/adequate credibility, findings triangulated |
| `suggestive` | "evidence suggests", "findings indicate" — requires ≥1 high/moderate trustworthiness; direction consistent |
| `preliminary` | "preliminary evidence suggests", "limited data indicate" — only one study, or low-trustworthiness estimates, or preprints only |
| `background_only` | "has been described", "context indicates" — background or context papers |"""
DIRECTNESS_RUBRIC = """\
| Label | Meaning |
|---|---|
| `direct` | Study directly compares the strategies/exposures of interest in the target population |
| `indirect` | Related population, adjacent exposure, or outcome proxy; supports interpretation but cannot replace direct evidence |
| `background` | Provides context or prevalence data only; not usable as effect evidence |"""
DECISION_ROLE_RUBRIC = """\
| Label | Meaning |
|---|---|
| `anchor` | Highest-quality direct evidence; should organize the primary synthesis argument |
| `support` | Corroborates or extends anchor evidence; useful in synthesis but not standalone |
| `methods` | Primarily a design, measurement, or estimand paper; informs analytic decisions |
| `background` | Provides epidemiological context, prevalence, or burden data only |
| `exclude` | Should be excluded from synthesis (irrelevant, methodologically disqualifying) |"""
THRESHOLD_NOTE = """\
Inclusion thresholds:
- `include_in_review = yes` if record_relevance ≥ 3
- `include_in_anchor_reading = yes` if record_relevance ≥ 4 AND study_credibility in (strong, adequate)
- `decision_role = anchor` only if record_relevance = 5 AND study_credibility = strong/adequate AND effect_trustworthiness = high/moderate"""


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def count_words(text: str) -> int:
    return len((text or "").split())


def truncate_abstract(abstract: str, max_words: int = 80) -> str:
    words = abstract.split()
    if len(words) <= max_words:
        return abstract
    return " ".join(words[:max_words]) + " …"


def load_topic_config(path: Path | None) -> dict:
    if path and path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def build_scoring_prompt(
    papers: list[dict[str, str]],
    cfg: dict,
    min_abstract_words: int,
) -> str:
    topic = cfg.get("topic") or cfg.get("title") or "the research question"
    population = cfg.get("population") or ""
    exposure = cfg.get("exposure") or ""
    outcome = cfg.get("outcome") or ""
    question_type = cfg.get("question_type") or ""

    lines: list[str] = []

    lines += [
        "# Semantic Scoring Brief",
        "",
        "## Your Task",
        "",
        "Read each paper and fill in ALL scoring dimensions in `scored_candidates.csv`.",
        "Do not skip any paper — assign record_relevance = 0 if clearly irrelevant.",
        "Fill every column; use `not_assessed` only for effect_trustworthiness when there is no effect estimate.",
        "",
        "## Research Question",
        "",
        f"**Topic:** {topic}",
    ]
    if population:
        lines.append(f"**Population:** {population}")
    if exposure:
        lines.append(f"**Exposure:** {exposure}")
    if outcome:
        lines.append(f"**Outcome:** {outcome}")
    if question_type:
        lines.append(f"**Question type:** {question_type}")
    lines.append("")

    lines += [
        "---",
        "",
        "## Dimension 1: Record Relevance (0–5)",
        "",
        RECORD_RELEVANCE_RUBRIC,
        "",
        "## Dimension 2: Study Credibility",
        "",
        STUDY_CREDIBILITY_RUBRIC,
        "",
        "## Dimension 3: Effect Trustworthiness",
        "",
        EFFECT_TRUSTWORTHINESS_RUBRIC,
        "",
        "## Dimension 4: Claim Strength Ceiling",
        "",
        CLAIM_STRENGTH_RUBRIC,
        "",
        "## Directness",
        "",
        DIRECTNESS_RUBRIC,
        "",
        "## Decision Role",
        "",
        DECISION_ROLE_RUBRIC,
        "",
        THRESHOLD_NOTE,
        "",
        "---",
        "",
        "## Mandatory Red Flags",
        "",
        "These cap scores regardless of other strengths:",
        "- No clear exposure or outcome definition → cap `record_relevance` at 2",
        "- Severe overclaiming beyond what design supports → cap `study_credibility` at `limited`",
        "- OR interpreted as RR/PR with common outcome (>10%) → cap `effect_trustworthiness` at `low`",
        "- Adjustment for likely mediator/collider without justification → cap `effect_trustworthiness` at `low`",
        "- Preprint: cap `effect_trustworthiness` at `moderate` maximum",
        "",
        "---",
        "",
        f"## Papers to Score (N={len(papers)})",
        "",
    ]

    sparse_abstract_count = 0
    for i, row in enumerate(papers, start=1):
        abstract = normalize_space(row.get("abstract") or "")
        if count_words(abstract) < min_abstract_words:
            sparse_abstract_count += 1

        paper_id = row.get("paper_id") or f"P{i:03d}"
        title = normalize_space(row.get("title") or "(no title)")
        year = row.get("year") or "?"
        source = row.get("source") or "?"
        doi = row.get("doi") or ""
        authors_raw = normalize_space(row.get("authors") or "")
        first_author = authors_raw.split(";")[0].strip() if authors_raw else "?"
        qfam = row.get("query_family") or ""
        pub_status = row.get("publication_status") or ""
        abstract_snippet = truncate_abstract(abstract, max_words=80)

        lines += [
            f"### {paper_id}: {title}",
            "",
            f"**Year:** {year} | **Source:** {source} | **First author:** {first_author}",
        ]
        if doi:
            lines.append(f"**DOI:** {doi}")
        if qfam:
            lines.append(f"**Query family:** `{qfam}`")
        if pub_status:
            lines.append(f"**Publication status:** {pub_status}")
        lines.append("")
        if abstract_snippet:
            lines.append(f"**Abstract:** {abstract_snippet}")
        else:
            lines.append("**Abstract:** *(not available — score from title and query family context)*")
        lines.append("")
        lines += [
            "**Fill these fields in scored_candidates.csv:**",
            "- `record_relevance` (0–5): ",
            "- `study_credibility` (strong/adequate/limited/weak): ",
            "- `effect_trustworthiness` (high/moderate/low/not_applicable): ",
            "- `claim_strength_ceiling` (definitive/suggestive/preliminary/background_only): ",
            "- `likely_directness` (direct/indirect/background): ",
            "- `decision_role` (anchor/support/methods/background/exclude): ",
            "- `study_design`: ",
            "- `key_finding`: ",
            "- `main_limitation`: ",
            "- `rationale`: ",
            "- `include_in_review` (yes/no/maybe): ",
            "- `include_in_anchor_reading` (yes/no): ",
            "",
            "---",
            "",
        ]

    if sparse_abstract_count > 0:
        lines.insert(
            next(i for i, l in enumerate(lines) if "Papers to Score" in l) + 2,
            f"\n> **Note:** {sparse_abstract_count} paper(s) have sparse abstracts (<{min_abstract_words} words). "
            "Score from title and query_family context; assign record_relevance ≤ 3 unless the title is a clear match.\n",
        )

    return "\n".join(lines)


def main_score_candidates() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare LLM scoring brief and CSV template from deduplicated candidates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            After running:
              1. Read scoring_prompt.md
              2. For each paper fill in all scoring dimensions
              3. Save as scored_candidates.csv (replacing the template)
        """),
    )
    parser.add_argument("--candidates", required=True, help="Path to candidate_records_dedup.csv")
    parser.add_argument("--output-dir", required=True, help="Directory to write scoring_prompt.md and scored_candidates_template.csv")
    parser.add_argument("--topic-config", default="", help="Optional path to topic_config.json for research question context")
    parser.add_argument("--min-abstract-words", type=int, default=10, help="Flag papers with fewer abstract words (default: 10)")
    parser.add_argument("--max-papers", type=int, default=300, help="Maximum papers to include in the scoring prompt (default: 300)")
    args = parser.parse_args()

    candidates_path = Path(args.candidates)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    topic_config_path = Path(args.topic_config) if args.topic_config else None
    cfg = load_topic_config(topic_config_path)

    rows = read_csv(candidates_path)
    if not rows:
        print(f"[score_candidates] No records found in {candidates_path}")
        return

    # Assign sequential paper IDs
    for i, row in enumerate(rows, start=1):
        row["paper_id"] = f"P{i:03d}"

    # Sort by local_relevance_score descending, cap at max-papers
    try:
        rows_sorted = sorted(rows, key=lambda r: float(r.get("local_relevance_score") or 0), reverse=True)
    except Exception:
        rows_sorted = rows
    rows_to_score = rows_sorted[: args.max_papers]

    print(f"[score_candidates] {len(rows)} candidates → scoring {len(rows_to_score)}")

    # Write scoring_prompt.md
    prompt_md = build_scoring_prompt(rows_to_score, cfg, args.min_abstract_words)
    prompt_path = output_dir / "scoring_prompt.md"
    prompt_path.write_text(prompt_md, encoding="utf-8")
    print(f"[score_candidates] Wrote {prompt_path}")

    # Write scored_candidates_template.csv (blank scoring columns)
    template_rows = []
    for row in rows_to_score:
        template_rows.append(
            {
                "paper_id": row.get("paper_id", ""),
                "title": normalize_space(row.get("title") or ""),
                "authors": normalize_space(row.get("authors") or ""),
                "year": row.get("year") or "",
                "source": row.get("source") or "",
                "doi": row.get("doi") or "",
                "url": row.get("url") or "",
                "query_family": row.get("query_family") or "",
                "publication_status": row.get("publication_status") or "",
                "abstract_snippet": truncate_abstract(normalize_space(row.get("abstract") or ""), max_words=60),
                # Blank scoring fields
                "record_relevance": "",
                "study_credibility": "",
                "effect_trustworthiness": "",
                "claim_strength_ceiling": "",
                "likely_directness": "",
                "decision_role": "",
                "study_design": "",
                "key_finding": "",
                "main_limitation": "",
                "rationale": "",
                "include_in_review": "",
                "include_in_anchor_reading": "",
            }
        )

    template_path = output_dir / "scored_candidates_template.csv"
    write_csv(template_path, template_rows, SCORING_COLUMNS)
    print(f"[score_candidates] Wrote template → {template_path}")
    print()
    print("Next: read scoring_prompt.md, fill scoring columns, save as scored_candidates.csv.")

# verify_citations
USER_AGENT = "study-literature-review/1.0 (crossref-polite-pool)"
CROSSREF_BASE = "https://api.crossref.org/works"


def build_ssl_context(insecure_skip_verify: bool) -> ssl.SSLContext | None:
    if not insecure_skip_verify:
        return None
    return ssl._create_unverified_context()


def http_get_json(url: str, headers: dict[str, str] | None = None, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30, context=build_ssl_context(insecure_skip_verify)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return doi


def first_author_surname(authors_raw: str) -> str:
    first = normalize_space(authors_raw).split(";")[0].strip()
    if not first:
        return ""
    return (first.split(",")[0] if "," in first else first.split()[0]).strip()


def title_similarity(a: str, b: str) -> float:
    """Simple token-overlap Jaccard similarity between two titles."""
    a_tokens = set(re.findall(r"[a-z0-9]+", a.lower()))
    b_tokens = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = a_tokens & b_tokens
    union = a_tokens | b_tokens
    return len(intersection) / len(union)


def crossref_lookup(doi: str, mailto: str | None, *, insecure_skip_verify: bool = False) -> dict[str, Any] | None:
    encoded_doi = urllib.parse.quote(doi, safe="")
    url = f"{CROSSREF_BASE}/{encoded_doi}"
    headers = {"User-Agent": USER_AGENT}
    if mailto:
        headers["User-Agent"] = f"{USER_AGENT}; mailto:{mailto}"
    try:
        payload = http_get_json(url, headers=headers, insecure_skip_verify=insecure_skip_verify)
        return payload.get("message")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def extract_crossref_year(message: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued"):
        date_parts = (message.get(key) or {}).get("date-parts")
        if date_parts and date_parts[0]:
            return str(date_parts[0][0])
    return ""


def extract_crossref_first_author_last(message: dict[str, Any]) -> str:
    authors = message.get("author") or []
    if authors:
        return normalize_space(authors[0].get("family") or "")
    return ""


def extract_crossref_title(message: dict[str, Any]) -> str:
    titles = message.get("title") or []
    return normalize_space(titles[0]) if titles else ""


def extract_crossref_journal(message: dict[str, Any]) -> str:
    container = message.get("container-title") or []
    return normalize_space(container[0]) if container else ""


def extract_crossref_type(message: dict[str, Any]) -> str:
    return message.get("type") or ""


def verify_record(
    doi: str,
    local_title: str,
    local_year: str,
    local_first_author: str,
    title_threshold: float,
    mailto: str | None,
    insecure_skip_verify: bool,
) -> dict[str, str]:
    """Look up a DOI on CrossRef and return a verification result dict."""
    result: dict[str, str] = {
        "doi": doi,
        "local_title": local_title,
        "local_year": local_year,
        "local_first_author": local_first_author,
        "crossref_title": "",
        "crossref_year": "",
        "crossref_first_author": "",
        "crossref_journal": "",
        "crossref_type": "",
        "title_similarity": "",
        "year_match": "",
        "author_match": "",
        "verification_status": "",
        "notes": "",
    }

    if not doi:
        result["verification_status"] = "no_doi"
        return result

    try:
        message = crossref_lookup(doi, mailto, insecure_skip_verify=insecure_skip_verify)
    except Exception as exc:
        result["verification_status"] = "error"
        result["notes"] = str(exc)[:200]
        return result

    if message is None:
        result["verification_status"] = "doi_not_found"
        result["notes"] = "DOI returned 404 on CrossRef"
        return result

    cr_title = extract_crossref_title(message)
    cr_year = extract_crossref_year(message)
    cr_author = extract_crossref_first_author_last(message)
    cr_journal = extract_crossref_journal(message)
    cr_type = extract_crossref_type(message)

    result["crossref_title"] = cr_title
    result["crossref_year"] = cr_year
    result["crossref_first_author"] = cr_author
    result["crossref_journal"] = cr_journal
    result["crossref_type"] = cr_type

    sim = title_similarity(local_title, cr_title) if local_title and cr_title else 0.0
    result["title_similarity"] = f"{sim:.3f}"

    year_ok = not local_year or not cr_year or local_year == cr_year
    result["year_match"] = "yes" if year_ok else "no"

    local_last = ""
    if local_first_author:
        parts = re.split(r"[\s,;]+", local_first_author.strip())
        local_last = parts[-1].lower() if parts else ""
    author_ok = not local_last or not cr_author or (local_last in cr_author.lower())
    result["author_match"] = "yes" if author_ok else "no"

    if sim >= title_threshold and year_ok and author_ok:
        result["verification_status"] = "verified"
    elif sim >= title_threshold:
        result["verification_status"] = "title_ok_metadata_mismatch"
        notes = []
        if not year_ok:
            notes.append(f"year: local={local_year} crossref={cr_year}")
        if not author_ok:
            notes.append(f"first_author: local={local_last!r} crossref={cr_author!r}")
        result["notes"] = "; ".join(notes)
    elif sim > 0.3:
        result["verification_status"] = "partial_match_review_needed"
        result["notes"] = f"title_similarity={sim:.3f}; may be a related but different paper"
    else:
        result["verification_status"] = "likely_mismatch"
        result["notes"] = f"title_similarity={sim:.3f}; CrossRef title: {cr_title[:80]!r}"

    return result


def load_input(path: Path) -> list[dict[str, str]]:
    """Return citation identity records from CSV or a citation registry JSON."""
    suffix = path.suffix.lower()
    records: list[dict[str, str]] = []

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("entries", data.get("citations", data.get("items", [])))
        for item in items:
            doi = normalize_doi(item.get("doi") or "")
            title = normalize_space(item.get("title") or "")
            year = str(item.get("year") or "")
            authors_raw = item.get("authors") or item.get("author") or ""
            if isinstance(authors_raw, list):
                authors_raw = "; ".join(str(a) for a in authors_raw)
            first_last = first_author_surname(str(authors_raw))
            records.append({
                "citation_id": str(item.get("citation_id") or ""),
                "reference_number": str(item.get("reference_number") or ""),
                "doi": doi,
                "title": title,
                "year": year,
                "first_author": first_last,
            })
    else:
        rows = read_csv(path)
        for row in rows:
            doi = normalize_doi(row.get("doi") or "")
            title = normalize_space(row.get("title") or "")
            year = str(row.get("year") or "")
            authors_raw = normalize_space(row.get("authors") or "")
            first_last = first_author_surname(authors_raw)
            records.append({
                "citation_id": str(row.get("citation_id") or row.get("paper_id") or ""),
                "reference_number": str(row.get("reference_number") or ""),
                "doi": doi,
                "title": title,
                "year": year,
                "first_author": first_last,
            })

    return records


def build_summary_md(results: list[dict[str, str]]) -> str:
    status_counts: dict[str, int] = {}
    for r in results:
        s = r.get("verification_status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1

    lines = [
        "# Citation Verification Summary",
        "",
        f"**Total records checked:** {len(results)}",
        "",
        "## Status Breakdown",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| `{status}` | {count} |")

    mismatches = [r for r in results if r.get("verification_status") not in ("verified", "no_doi")]
    if mismatches:
        lines += [
            "",
            "## Records Needing Review",
            "",
            "| DOI | Status | Notes |",
            "|---|---|---|",
        ]
        for r in mismatches[:50]:
            doi = r.get("doi") or ""
            status = r.get("verification_status") or ""
            notes = (r.get("notes") or "")[:80]
            lines.append(f"| {doi} | `{status}` | {notes} |")
        if len(mismatches) > 50:
            lines.append(f"| … | … | {len(mismatches) - 50} more — see full report CSV |")

    lines += [
        "",
        "## Verification Status Key",
        "",
        "| Status | Meaning |",
        "|---|---|",
        "| `verified` | Title, year, and author all match CrossRef |",
        "| `title_ok_metadata_mismatch` | Title matches but year or author differs (usually harmless) |",
        "| `partial_match_review_needed` | Title partially matches; review manually |",
        "| `likely_mismatch` | Title similarity < 0.3; possible wrong DOI |",
        "| `doi_not_found` | DOI not in CrossRef database |",
        "| `no_doi` | No DOI available for this record |",
        "| `error` | Network or API error during lookup |",
    ]
    return "\n".join(lines)


def main_verify_citations() -> None:
    parser = argparse.ArgumentParser(
        description="Verify citation metadata against CrossRef.",
    )
    parser.add_argument("--input", required=True, help="Path to scored_candidates.csv or citation_registry.json")
    parser.add_argument("--output-dir", required=True, help="Directory to write citation_verification_report.csv")
    parser.add_argument("--mailto", default="", help="Email for CrossRef polite pool (recommended; improves rate limits)")
    parser.add_argument("--title-similarity-threshold", type=float, default=0.75, help="Jaccard title similarity threshold for verification (default: 0.75)")
    parser.add_argument("--skip-no-doi", action="store_true", help="Skip records without a DOI entirely")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between CrossRef requests (default: 0.5)")
    parser.add_argument("--insecure-skip-verify", action="store_true", help="Skip SSL certificate verification")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_input(input_path)
    print(f"[verify_citations] Loaded {len(records)} records from {input_path}")

    if args.skip_no_doi:
        records = [record for record in records if record["doi"]]
        print(f"[verify_citations] After --skip-no-doi filter: {len(records)} records")

    results: list[dict[str, str]] = []
    for i, record in enumerate(records, start=1):
        if i % 20 == 0:
            print(f"  [{i}/{len(records)}] …")
        result = verify_record(
            doi=record["doi"],
            local_title=record["title"],
            local_year=record["year"],
            local_first_author=record["first_author"],
            title_threshold=args.title_similarity_threshold,
            mailto=args.mailto or None,
            insecure_skip_verify=args.insecure_skip_verify,
        )
        result["citation_id"] = record["citation_id"]
        result["reference_number"] = record["reference_number"]
        results.append(result)
        if record["doi"]:
            time.sleep(args.delay)

    report_fieldnames = [
        "citation_id", "reference_number",
        "doi", "local_title", "local_year", "local_first_author",
        "crossref_title", "crossref_year", "crossref_first_author",
        "crossref_journal", "crossref_type",
        "title_similarity", "year_match", "author_match",
        "verification_status", "notes",
    ]
    report_path = output_dir / "citation_verification_report.csv"
    write_csv(report_path, results, report_fieldnames)
    print(f"[verify_citations] Wrote {report_path}")

    summary_md = build_summary_md(results)
    summary_path = output_dir / "citation_verification_summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    print(f"[verify_citations] Wrote {summary_path}")

    verified = sum(1 for r in results if r.get("verification_status") == "verified")
    mismatches = sum(1 for r in results if r.get("verification_status") == "likely_mismatch")
    not_found = sum(1 for r in results if r.get("verification_status") == "doi_not_found")
    print(f"\n[verify_citations] verified={verified} | likely_mismatch={mismatches} | doi_not_found={not_found}")


COMMANDS = {
    "run_fulltext_extraction": main_run_fulltext_extraction,
    "score_candidates": main_score_candidates,
    "verify_citations": main_verify_citations,
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
