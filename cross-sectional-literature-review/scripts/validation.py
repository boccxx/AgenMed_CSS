#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/validation.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

# common_validation
CANONICAL_PROJECT_MODES = {"research", "applied_methods", "workflow_methods"}
LEGACY_PROJECT_MODE_ALIASES = {
    "simulation": "applied_methods",
    "methods_demo": "workflow_methods",
}


def normalize_project_mode(value: object, *, default: str = "research") -> str:
    raw = str(value or default).strip()
    canonical = LEGACY_PROJECT_MODE_ALIASES.get(raw, raw)
    if canonical not in CANONICAL_PROJECT_MODES:
        allowed = ", ".join(sorted(CANONICAL_PROJECT_MODES | set(LEGACY_PROJECT_MODE_ALIASES)))
        raise ValueError(f"project_mode '{raw}' is not valid; expected one of: {allowed}")
    return canonical


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def first_n_lines(text: str, n: int = 25) -> str:
    return "\n".join(text.splitlines()[:n])


def normalize(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ")


def contains_token(text: str, token: str) -> bool:
    return normalize(token) in normalize(text)


def find_missing_sections(text: str, sections: list[str]) -> list[str]:
    norm = normalize(text)
    return [section for section in sections if normalize(section) not in norm]


def path_exists(base: Path, names: list[str]) -> list[str]:
    missing = []
    for name in names:
        if not (base / name).exists():
            missing.append(name)
    return missing


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_status(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def word_count(text: str) -> int:
    """Count words in text, stripping YAML frontmatter if present."""
    body = strip_yaml_frontmatter(text)
    return len(body.split())


def strip_yaml_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block delimited by --- ... --- at the start."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def strip_references_section(text: str) -> str:
    """Remove a trailing References or Bibliography section for word-count purposes."""
    pattern = re.compile(
        r"\n#+\s*(References|Bibliography|参考文献)\b.*$",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub("", text)


def body_word_count(text: str) -> int:
    """Word count of narrative body: strips YAML frontmatter and References section."""
    body = strip_yaml_frontmatter(text)
    body = strip_references_section(body)
    return len(body.split())


def check_prohibited_in_body(text: str, phrases: list[str]) -> list[str]:
    """Return prohibited phrases that appear anywhere in the text body."""
    body = strip_yaml_frontmatter(text)
    norm_body = normalize(body)
    found = []
    for phrase in phrases:
        if normalize(phrase) in norm_body:
            found.append(phrase)
    return found


def extract_section(text: str, section_name: str) -> str:
    """
    Extract the content of a named Markdown section (heading + body until next
    same-or-higher-level heading).  Returns empty string if not found.
    """
    lines = text.splitlines()
    # Allow optional numeric prefix in headings, e.g. "## 6.5 Sample-size Planning".
    pattern = re.compile(
        r"^(#{1,4})\s+(?:\d+(?:\.\d+)*\s+)?"
        + re.escape(section_name.strip())
        + r"\s*$",
        re.IGNORECASE,
    )
    candidates = [(index, len(match.group(1))) for index, line in enumerate(lines) if (match := pattern.match(line))]
    if not candidates:
        return ""
    # A structured abstract may contain "## Methods" and "## Results" before
    # the full top-level sections. Prefer the highest-level matching heading.
    section_level = min(level for _, level in candidates)
    start = next(index for index, level in candidates if level == section_level)
    collected: list[str] = [lines[start]]
    for line in lines[start + 1:]:
        heading_match = re.match(r"^(#{1,4})\s+", line)
        if heading_match and len(heading_match.group(1)) <= section_level:
            break
        collected.append(line)

    return "\n".join(collected)


def has_numbers_in_section(section_text: str) -> bool:
    """Return True if the section contains at least one explicit integer (for count checks)."""
    return bool(re.search(r"\b\d+\b", section_text))


def check_inline_screening_numbers(text: str) -> bool:
    """
    Heuristic: the Search and Screening section must contain at least 3 distinct
    integers (retrieved, screened, retained counts).
    """
    section = extract_section(text, "Search and Screening")
    if not section:
        return False
    numbers = re.findall(r"\b\d+\b", section)
    return len(numbers) >= 3


def check_explicit_estimand(text: str) -> bool:
    """Return True if the text contains an explicit labelled primary estimand statement."""
    patterns = [
        r"primary estimand",
        r"primary.*estimand",
        r"estimand.*primary",
    ]
    norm = normalize(text)
    return any(re.search(p, norm) for p in patterns)


def check_numeric_sample_size(text: str) -> bool:
    """
    Return True if the sample-size section contains at least 4 integers,
    suggesting explicit numeric inputs rather than narrative description only.
    """
    section = (
        extract_section(text, "Sample-size Planning")
        or extract_section(text, "Sample-size Inputs")
        or extract_section(text, "Sample Size")
        or extract_section(text, "Sample")
        or extract_section(text, "sample-size")
        or extract_section(text, "Bias Control")
    )
    numbers = re.findall(r"\b\d+[\.,]?\d*\b", section)
    return len(numbers) >= 4


def check_disclosure_in_permitted_sections_only(
    text: str,
    disclosure_tokens: list[str],
    permitted_sections: list[str],
    forbidden_section_names: list[str],
) -> list[str]:
    """
    For applied_methods mode: check that disclosure tokens do not appear in
    forbidden sections (Introduction, title area, main Discussion paragraphs).
    Returns a list of violation descriptions.
    """
    violations = []
    for section_name in forbidden_section_names:
        section_text = extract_section(text, section_name)
        if not section_text:
            continue
        for token in disclosure_tokens:
            if contains_token(section_text, token):
                violations.append(
                    f"disclosure token '{token}' found in forbidden section '{section_name}'"
                )
    return violations


def _section_body_paragraphs(section_text: str) -> list[str]:
    lines = section_text.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    return [part.strip() for part in "\n".join(lines).split("\n\n") if part.strip()]


def check_applied_methods_disclosure_exact(
    text: str,
    disclosure_tokens: list[str],
) -> list[str]:
    """Enforce the suite's two-location disclosure policy.

    Each disclosure token must occur in the final sentence of Abstract Methods
    and the first paragraph of Limitations, and nowhere else.
    """
    violations: list[str] = []
    abstract = extract_section(text, "Abstract")
    abstract_methods = extract_section(abstract, "Methods") if abstract else ""
    limitations = extract_section(text, "Limitations")
    if not abstract_methods:
        return ["Abstract Methods subsection is missing"]
    if not limitations:
        return ["Limitations subsection is missing"]

    abstract_parts = _section_body_paragraphs(abstract_methods)
    abstract_body = " ".join(abstract_parts)
    abstract_sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?。！？])\s+", abstract_body)
        if item.strip()
    ]
    abstract_last_sentence = abstract_sentences[-1] if abstract_sentences else abstract_body
    limitation_parts = _section_body_paragraphs(limitations)
    limitation_first_paragraph = limitation_parts[0] if limitation_parts else ""
    allowed_text = f"{abstract_last_sentence}\n{limitation_first_paragraph}"

    for token in disclosure_tokens:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", re.IGNORECASE)
        if not pattern.search(abstract_last_sentence):
            violations.append(f"'{token}' missing from the final sentence of Abstract Methods")
        if not pattern.search(limitation_first_paragraph):
            violations.append(f"'{token}' missing from the first Limitations paragraph")
        total_count = len(pattern.findall(text))
        allowed_count = len(pattern.findall(allowed_text))
        if total_count != allowed_count:
            violations.append(f"'{token}' appears outside the two permitted disclosure locations")
    return violations


def check_discussion_contribution(
    text: str,
    forbidden_contribution_phrases: list[str],
) -> list[str]:
    """
    Check that the Discussion section does not open with workflow-validation
    as the primary contribution.
    """
    section = extract_section(text, "Discussion")
    if not section:
        return []
    found = []
    for phrase in forbidden_contribution_phrases:
        if contains_token(section, phrase):
            found.append(phrase)
    return found

# validate_review_semantics

def load_semantic_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
EXECUTED = {"retrieved", "completed", "searched", "executed"}
PLACEHOLDER_ABSTRACT = re.compile(
    r"identity[- ]resolved candidate|retained for direct evidence|abstract unavailable|placeholder|todo|tbd",
    re.I,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "yes", "true", "y"}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def record_key(row: dict[str, str]) -> str:
    doi = (row.get("doi") or "").strip().lower().removeprefix("https://doi.org/")
    return f"doi:{doi}" if doi else f"title:{norm(row.get('title', ''))}"


def raw_candidate_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    source_id = norm(str(row.get("source_record_id") or ""))
    doi = str(row.get("doi") or "").strip().lower().removeprefix("https://doi.org/")
    title = norm(str(row.get("title") or ""))
    return source_id, doi, title


def integer(row: dict[str, str], field: str, errors: list[str], label: str) -> int:
    value = (row.get(field) or "").strip()
    if not value.isdigit():
        errors.append(f"{label} lacks integer {field}")
        return 0
    return int(value)


def validate_semantics(root: Path) -> list[str]:
    errors: list[str] = []
    log = read_csv(root / "search_log.csv")
    raw = read_csv(root / "candidate_records_raw.csv")
    dedup = read_csv(root / "candidate_records_dedup.csv")
    screening = read_csv(root / "screening_decisions.csv")
    studies = read_csv(root / "study_registry.csv")
    effects = read_csv(root / "effect_registry.csv")
    appraisals = read_csv(root / "quality_appraisal_registry.csv")
    fulltexts = read_csv(root / "fulltext_inventory.csv")
    citations = load_semantic_json(root / "citation_registry.json").get("entries", [])
    decisions = read_csv(root / "evidence_to_decision_table.csv")
    claims = read_csv(root / "claim_registry.csv")
    diagnostics = load_semantic_json(root / "live_search_diagnostics.json")
    flow = load_semantic_json(root / "flow_counts.json")
    contract = load_semantic_json(root / "review_contract.json")
    protocol = load_semantic_json(root / "protocol_inputs.json")
    narrative = (root / "literature_review_synthesis.md").read_text(encoding="utf-8") if (root / "literature_review_synthesis.md").exists() else ""

    # 1. Search ledger and raw payloads must be one-to-one, with no stale files.
    executed = [row for row in log if (row.get("status") or "").strip().lower() in EXECUTED]
    ledger_files: set[str] = set()
    raw_by_search = Counter(row.get("search_id", "") for row in raw)
    dedup_by_search = Counter(row.get("search_id", "") for row in dedup)
    for row in executed:
        sid = (row.get("search_id") or "").strip()
        label = f"search {sid or '?'}"
        raw_file = (row.get("raw_file") or "").strip()
        if not raw_file:
            errors.append(f"{label} is executed but has no raw_file binding")
            continue
        path = root / raw_file
        ledger_files.add(str(path.resolve()))
        if not path.is_file():
            errors.append(f"{label} raw_file does not exist: {raw_file}")
            continue
        try:
            payload = load_semantic_json(path)
        except Exception as exc:
            errors.append(f"{label} raw payload is not valid JSON: {exc}")
            continue
        for field in ("search_id", "source", "query", "source_query"):
            if str(payload.get(field, "")).strip() != str(row.get(field, "")).strip():
                errors.append(f"{label} raw payload {field} does not match search_log.csv")
        exported = integer(row, "n_exported", errors, label)
        api_hits = integer(row, "api_total_hits", errors, label)
        if api_hits < exported:
            errors.append(f"{label} api_total_hits is smaller than n_exported")
        if int(payload.get("exported_count", -1)) != exported:
            errors.append(f"{label} raw exported_count does not match n_exported")
        exported_records = payload.get("exported_records")
        if not isinstance(exported_records, list):
            errors.append(f"{label} raw payload is metadata-only and lacks exported_records provider objects")
            exported_records = []
        if len(exported_records) != exported:
            errors.append(f"{label} raw exported_records count {len(exported_records)} does not match n_exported {exported}")
        raw_identities: list[tuple[str, str, str]] = []
        for index, record in enumerate(exported_records, start=1):
            if not isinstance(record, dict):
                errors.append(f"{label} exported_records item {index} is not an object")
                continue
            if not isinstance(record.get("raw_record"), dict) or not record.get("raw_record"):
                errors.append(f"{label} exported_records item {index} lacks the actual provider raw_record object")
            identity = raw_candidate_identity(record)
            if not any(identity):
                errors.append(f"{label} exported_records item {index} lacks source ID, DOI, and title identity")
            raw_identities.append(identity)
        candidate_identities = [raw_candidate_identity(item) for item in raw if item.get("search_id") == sid]
        if Counter(raw_identities) != Counter(candidate_identities):
            errors.append(f"{label} exported provider objects do not identity-match candidate rows by source ID/DOI/title")
        if row.get("source") in {"medRxiv", "bioRxiv"}:
            harvested_records = (payload.get("payload") or {}).get("harvested_records")
            if not isinstance(harvested_records, list) or not harvested_records:
                errors.append(f"{label} preprint payload lacks interval-harvested provider record objects")
            else:
                harvested_keys = {
                    (
                        str(item.get("doi") or "").strip().lower().removeprefix("https://doi.org/"),
                        norm(str(item.get("title") or "")),
                    )
                    for item in harvested_records if isinstance(item, dict)
                }
                for record in exported_records:
                    key = (
                        str(record.get("doi") or "").strip().lower().removeprefix("https://doi.org/"),
                        norm(str(record.get("title") or "")),
                    )
                    if key not in harvested_keys:
                        errors.append(f"{label} exported preprint record is absent from archived interval provider objects: {key}")
        if raw_by_search[sid] != exported:
            errors.append(f"{label} candidate raw rows {raw_by_search[sid]} do not match n_exported {exported}")
        owned = integer(row, "n_after_dedup", errors, label)
        if dedup_by_search[sid] != owned:
            errors.append(f"{label} deduplicated ownership count {dedup_by_search[sid]} does not match n_after_dedup {owned}")

    actual_raw_files = {
        str(path.resolve()) for path in (root / "raw_results").glob("*.json")
    } if (root / "raw_results").is_dir() else set()
    if actual_raw_files != ledger_files:
        stale = sorted(Path(path).name for path in actual_raw_files - ledger_files)
        missing = sorted(Path(path).name for path in ledger_files - actual_raw_files)
        errors.append(f"raw_results/search_log one-to-one mapping failed; stale={stale}, missing={missing}")
    if len(raw) != sum(int(row.get("n_exported") or 0) for row in executed):
        errors.append("candidate_records_raw row count does not equal summed executed-search n_exported")
    if len(dedup) != sum(int(row.get("n_after_dedup") or 0) for row in executed):
        errors.append("candidate_records_dedup row count does not equal summed n_after_dedup ownership")
    if len({record_key(row) for row in dedup}) != len(dedup):
        errors.append("candidate_records_dedup still contains duplicate DOI/title identities")
    if not {record_key(row) for row in dedup}.issubset({record_key(row) for row in raw}):
        errors.append("candidate_records_dedup contains records absent from candidate_records_raw")
    if diagnostics:
        if int(diagnostics.get("candidate_row_count", -1)) != len(raw):
            errors.append("live_search_diagnostics candidate_row_count conflicts with candidate_records_raw")
        if int(diagnostics.get("dedup_candidate_row_count", -1)) != len(dedup):
            errors.append("live_search_diagnostics dedup_candidate_row_count conflicts with candidate_records_dedup")
        if int(diagnostics.get("raw_payload_count", -1)) != len(actual_raw_files):
            errors.append("live_search_diagnostics raw_payload_count conflicts with raw_results")

    # 2. Candidate abstracts must be content, not repeated screening boilerplate.
    if raw:
        abstracts = [(row.get("abstract") or "").strip() for row in raw]
        substantive = [a for a in abstracts if len(a) >= 80 and not PLACEHOLDER_ABSTRACT.search(a)]
        if len(substantive) / len(abstracts) < 0.70:
            errors.append(f"candidate_records_raw has authentic/substantive abstracts for only {len(substantive)}/{len(abstracts)} rows; require at least 70%")
        dominant = Counter(norm(a) for a in abstracts if a).most_common(1)
        if dominant and dominant[0][1] / len(abstracts) > 0.10:
            errors.append("candidate_records_raw contains a dominant repeated abstract/placeholder string")
    if any(PLACEHOLDER_ABSTRACT.search((row.get("abstract") or "")) for row in dedup):
        errors.append("candidate_records_dedup contains placeholder abstract text")

    # 3. Screening is one row per deduplicated record and flow comes from row-level states.
    required_screen_cols = {"report_sought", "report_retrieved", "content_assessed", "full_text_assessed", "content_level", "access_type", "evidence_lane", "source_file"}
    if screening and not required_screen_cols.issubset(screening[0]):
        errors.append("screening_decisions.csv lacks report/full-text/content-level provenance columns")
    screening_keys = [record_key(row) for row in screening]
    if Counter(screening_keys) != Counter(record_key(row) for row in dedup):
        errors.append("screening_decisions must map one-to-one to candidate_records_dedup by DOI/title")
    computed_flow = {
        "api_total_hits": sum(int(row.get("api_total_hits") or 0) for row in executed),
        "records_exported": len(raw),
        "records_after_deduplication": len(dedup),
        "title_abstract_screened": len(screening),
        "total_content_assessed": sum(truthy(row.get("content_assessed")) for row in screening),
        "total_full_text_access": sum(truthy(row.get("content_assessed")) and row.get("access_type") == "full_text" for row in screening),
        "total_authoritative_abstract_access": sum(truthy(row.get("content_assessed")) and row.get("access_type") == "authoritative_abstract" for row in screening),
        "direct_empirical_content_assessed": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "direct_empirical" for row in screening),
        "direct_empirical_full_text_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "direct_empirical" and row.get("access_type") == "full_text" for row in screening),
        "direct_empirical_authoritative_abstract_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "direct_empirical" and row.get("access_type") == "authoritative_abstract" for row in screening),
        "direct_empirical_included": sum(truthy(row.get("include_in_synthesis")) and row.get("evidence_lane") == "direct_empirical" for row in screening),
        "direct_empirical_excluded": sum(row.get("decision") == "exclude" and row.get("evidence_lane") == "direct_empirical" and truthy(row.get("content_assessed")) for row in screening),
        "contextual_content_assessed": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "contextual" for row in screening),
        "contextual_full_text_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "contextual" and row.get("access_type") == "full_text" for row in screening),
        "contextual_authoritative_abstract_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "contextual" and row.get("access_type") == "authoritative_abstract" for row in screening),
        "contextual_included": sum(truthy(row.get("include_in_synthesis")) and row.get("evidence_lane") == "contextual" for row in screening),
        "included_in_synthesis": sum(truthy(row.get("include_in_synthesis")) for row in screening),
    }
    for field, value in computed_flow.items():
        if int(flow.get(field, -1)) != value:
            errors.append(f"flow_counts.json {field}={flow.get(field)} does not match row-level truth {value}")
    if int(flow.get("direct_empirical_content_assessed", -1)) - int(flow.get("direct_empirical_excluded", -1)) != int(flow.get("direct_empirical_included", -1)):
        errors.append("flow direct empirical arithmetic must satisfy content assessed minus excluded equals included")
    if int(flow.get("direct_empirical_included", -1)) + int(flow.get("contextual_included", -1)) != int(flow.get("included_in_synthesis", -1)):
        errors.append("flow total must distinguish direct empirical from contextual sources")
    if int(flow.get("total_sources_cited", -1)) != int(flow.get("included_in_synthesis", -1)):
        errors.append("flow total_sources_cited must equal the role-resolved included evidence set")
    if int(flow.get("total_full_text_access", -1)) + int(flow.get("total_authoritative_abstract_access", -1)) != int(flow.get("total_content_assessed", -1)):
        errors.append("flow access arithmetic must distinguish full text from authoritative abstract content")
    for row in screening:
        if truthy(row.get("full_text_assessed")) and not truthy(row.get("report_retrieved")):
            errors.append(f"{row.get('paper_id')} claims full-text assessment without report retrieval")
        if truthy(row.get("full_text_assessed")) != (row.get("access_type") == "full_text" and truthy(row.get("content_assessed"))):
            errors.append(f"{row.get('paper_id')} full_text_assessed conflicts with access_type/content_assessed")
        if truthy(row.get("include_in_synthesis")) and not truthy(row.get("content_assessed")):
            errors.append(f"{row.get('paper_id')} is included without content assessment")
        source_file = root / (row.get("source_file") or "")
        if truthy(row.get("content_assessed")) and (not source_file.is_file() or source_file.stat().st_size == 0):
            errors.append(f"{row.get('paper_id')} content assessment lacks archived source_file")
        if row.get("evidence_lane") == "contextual" and (row.get("role") or "").lower() in {"direct_evidence", "counterevidence", "inconsistent_evidence"}:
            errors.append(f"{row.get('paper_id')} contextual source is mislabeled as a direct empirical report")

    # 4. Full-text/content locators must bind every numerical direct effect to an archived source.
    fulltext_by_id = {row.get("paper_id", ""): row for row in fulltexts}
    direct_ids = {
        row.get("paper_id", "") for row in studies
        if (row.get("primary_role") or "").strip().lower() in {"direct_evidence", "counterevidence", "inconsistent_evidence"}
    }
    for effect in effects:
        pid = (effect.get("paper_id") or effect.get("study_id") or "").strip()
        if pid not in direct_ids:
            continue
        for field in ("source_file", "source_locator", "evidence_snippet"):
            if len((effect.get(field) or "").strip()) < (20 if field == "evidence_snippet" else 3):
                errors.append(f"direct effect {effect.get('effect_id')} ({pid}) lacks substantive {field}")
        source = root / (effect.get("source_file") or "")
        if not source.is_file() or source.stat().st_size == 0:
            errors.append(f"direct effect {effect.get('effect_id')} ({pid}) source_file is missing/empty")
        if pid not in fulltext_by_id:
            errors.append(f"direct effect {effect.get('effect_id')} ({pid}) has no fulltext_inventory row")
    central_direct_ids = {
        str(pid).strip() for pid in contract.get("central_direct_paper_ids", []) if str(pid).strip()
    }
    if not central_direct_ids:
        central_direct_ids = {
            row.get("paper_id", "") for row in studies
            if truthy(row.get("anchor_eligible")) and (row.get("primary_role") or "").strip().lower() == "direct_evidence"
        }
    for central in sorted(central_direct_ids):
        rows = [row for row in effects if row.get("paper_id") == central]
        if not rows or any(not row.get("source_locator") or not row.get("source_file") for row in rows):
            errors.append(f"central direct study {central} lacks content-level effect provenance")

    # 5. Study and appraisal registries must contain paper-specific facts.
    if studies:
        key_fields = ("population", "exposure", "outcome", "setting", "measures", "core_findings", "limitations")
        signatures = Counter(tuple(norm(row.get(field, "")) for field in key_fields) for row in studies)
        if signatures.most_common(1)[0][1] / len(studies) > 0.15:
            errors.append("study_registry.csv is dominated by repeated template study-characteristic rows")
        for row in studies:
            if any(len((row.get(field) or "").strip()) < 12 for field in key_fields):
                errors.append(f"study_registry.csv {row.get('paper_id')} lacks study-specific characteristic detail")
    appraisal_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    appraisal_signatures: Counter[tuple[str, str]] = Counter()
    for row in appraisals:
        appraisal_by_id[row.get("paper_id", "")].append(row)
        appraisal_signatures[(norm(row.get("raw_signal", "")), norm(row.get("evidence_source", "")))] += 1
        source_ref = (row.get("evidence_source") or "").split("::", 1)[0]
        if "::" not in (row.get("evidence_source") or ""):
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} lacks source_file::locator evidence_source")
        elif not (root / source_ref).is_file():
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} references missing source {source_ref}")
        if len((row.get("raw_signal") or "").strip()) < 35:
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} raw_signal is not study-specific")
        capability = (row.get("source_capability") or "").strip().lower()
        judgment = (row.get("judgment") or "").strip().lower()
        domain = (row.get("domain") or "").strip().lower()
        signal = (row.get("raw_signal") or "").strip().lower()
        if capability == "authoritative_abstract" and any(token in signal for token in ("does not report", "does not provide", "omits", "insufficient")):
            if not any(token in judgment for token in ("unclear", "not assessable")):
                errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} overjudges an unreported abstract-only domain")
        if capability == "authoritative_abstract" and any(token in domain for token in ("selection", "attrition")) and any(token in judgment for token in ("low concern", "adequate")):
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} assigns favorable selection/attrition judgment from abstract-only access")
        design = next((item.get("design", "").lower() for item in studies if item.get("paper_id") == row.get("paper_id")), "")
        if capability == "full_text" and any(token in design for token in ("cohort", "prospective", "longitudinal")) and any(token in domain for token in ("selection", "attrition")):
            if not re.search(r"\b\d[\d,]*(?:%|\b)", signal) or not any(token in signal for token in ("retained", "leaving", "excluded", "follow-up", "remaining", "entered")):
                errors.append(f"cohort appraisal {row.get('paper_id')} lacks actual participant-flow/attrition facts despite full-text access")
    if appraisals and appraisal_signatures.most_common(1)[0][1] / len(appraisals) > 0.10:
        errors.append("quality_appraisal_registry.csv repeats the same signal/source across too many domains")
    claim_bearing = {row.get("paper_id", "") for row in fulltexts if truthy(row.get("claim_bearing"))}
    for pid in claim_bearing:
        if len(appraisal_by_id.get(pid, [])) < 4:
            errors.append(f"claim-bearing study {pid} lacks four study-specific appraisal domains")

    # 6. Counterevidence and citation bindings must be semantically specific.
    study_role = {row.get("paper_id", ""): (row.get("primary_role") or "").strip().lower() for row in studies}
    effect_direction = defaultdict(set)
    for row in effects:
        effect_direction[row.get("paper_id", "")].add((row.get("direction") or "").strip().lower())
    for claim in claims:
        for pid in re.split(r"[,;|]", claim.get("counter_study_ids") or ""):
            pid = pid.strip()
            if not pid:
                continue
            if study_role.get(pid) not in {"counterevidence", "inconsistent_evidence"}:
                errors.append(f"claim {claim.get('claim_id')} counter study {pid} is not classified as genuine counter/inconsistent evidence")
            if not (effect_direction.get(pid, set()) & {"null", "mixed", "heterogeneous", "inconsistent"}):
                errors.append(f"claim {claim.get('claim_id')} counter study {pid} has no null/mixed/inconsistent effect row")
    decision_papers = {row.get("decision_id", ""): set(re.split(r"[,;|]", row.get("supporting_paper_ids") or "")) for row in decisions}
    citation_signatures = Counter()
    for entry in citations:
        pid = str(entry.get("paper_id", ""))
        decision_ids = {str(x).strip() for x in entry.get("supporting_decision_ids", []) if str(x).strip()}
        effect_ids = {str(x).strip() for x in entry.get("supporting_evidence_row_ids", []) if str(x).strip()}
        claim_ids = {str(x).strip() for x in entry.get("supporting_claim_ids", []) if str(x).strip()}
        citation_signatures[(entry.get("claim_supported", ""), tuple(sorted(decision_ids)), tuple(sorted(effect_ids)), tuple(sorted(claim_ids)))] += 1
        if not claim_ids:
            errors.append(f"citation {entry.get('citation_id')} lacks specific supporting_claim_ids")
        if entry.get("evidence_lane") == "contextual":
            for field in ("content_source_file", "content_locator", "content_snippet"):
                if len(str(entry.get(field) or "").strip()) < (35 if field == "content_snippet" else 5):
                    errors.append(f"contextual citation {entry.get('citation_id')} lacks substantive {field}")
            content_source = root / str(entry.get("content_source_file") or "")
            if not content_source.is_file() or content_source.stat().st_size == 0:
                errors.append(f"contextual citation {entry.get('citation_id')} references missing archived content")
        for did in decision_ids:
            if pid not in decision_papers.get(did, set()):
                errors.append(f"citation {entry.get('citation_id')} claims decision {did} but {pid} is absent from that decision row")
        for eid in effect_ids:
            owner = next((row.get("paper_id") for row in effects if row.get("effect_id") == eid), None)
            if owner != pid:
                errors.append(f"citation {entry.get('citation_id')} effect {eid} belongs to {owner}, not {pid}")
    if citations and citation_signatures.most_common(1)[0][1] / len(citations) > 0.15:
        errors.append("citation_registry.json is dominated by generic all-purpose claim/decision bindings")

    # 7. Protocol decisions must be locked identically across contract, protocol,
    # decisions, confounder registry, and reader-facing narrative.
    decision_text = " ".join((row.get("decision") or "") for row in decisions).lower()
    contract_lock = " ".join(str(contract.get(field, "")) for field in ("primary_estimand", "secondary_estimand", "primary_contrast", "primary_adjustment_policy")).lower()
    protocol_lock = " ".join(str(protocol.get(field, "")) for field in ("comparison", "primary_estimand", "secondary_estimand", "mediator")).lower()
    for label, text in (("review_contract", contract_lock), ("protocol_inputs", protocol_lock), ("evidence_to_decision_table", decision_text), ("narrative", narrative.lower())):
        if "p75" not in text or "prevalence ratio" not in text:
            errors.append(f"{label} does not lock the primary weighted P75 prevalence-ratio contrast")
        if not ("10-percentage-point" in text or "10 percentage-point" in text):
            errors.append(f"{label} does not lock the per-10-point exposure estimand as secondary")
    sensitivity_terms = ("bmi", "sleep", "diet quality", "inflammation")
    sensitivity_rows = [row for row in read_csv(root / "confounder_registry.csv") if all(term in (row.get("variable") or "").lower() for term in sensitivity_terms)]
    if len(sensitivity_rows) != 1 or "sensitivity-only" not in sensitivity_rows[0].get("recommended_main_model_role", "").lower() or "not a primary confounder" not in sensitivity_rows[0].get("classification", "").lower():
        errors.append("confounder_registry must classify BMI/sleep/diet quality/inflammation as sensitivity-only and not primary confounders")
    primary_confounder_blob = " ".join(str(x).lower() for x in protocol.get("confounders", []))
    if any(term in primary_confounder_blob for term in sensitivity_terms):
        errors.append("protocol_inputs confounders improperly include sensitivity-only BMI/sleep/diet quality/inflammation")
    if set(str(x).lower() for x in protocol.get("sensitivity_only_variables", [])) != {"bmi", "sleep", "overall diet quality", "inflammation"}:
        errors.append("protocol_inputs sensitivity_only_variables must exactly enumerate BMI, sleep, overall diet quality, and inflammation")
    if narrative:
        opening = narrative.split("## Evidence Map", 1)[0]
        if "dietary interventions" in opening.lower() and not re.search(r"dietary interventions[^\n]{0,220}\[29\]", opening, re.I):
            errors.append("narrative dietary-intervention opening claim is not bound to reference [29]")
        umbrella_context = " ".join(part for part in narrative.split("\n\n") if "umbrella" in part.lower())
        if not all(token in umbrella_context.lower() for token in ("class i", "class ii", "low quality")):
            errors.append("narrative umbrella evidence must state class I combined common disorders, class II depressive outcomes, and low quality separately")

    # 8. Flow display and its visual inspection are release evidence, not optional decoration.
    for name in ("flow_diagram.svg", "flow_diagram.png", "visual_inspection_report.json"):
        path = root / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing visual flow artifact: {name}")
    visual = load_semantic_json(root / "visual_inspection_report.json")
    if visual.get("status") != "pass" or not visual.get("inspected_file_sha256"):
        errors.append("visual_inspection_report.json must record a passed human/agent inspection and inspected file hash")

    return errors


def main_validate_review_semantics() -> int:
    parser = argparse.ArgumentParser(description="Validate literature-review provenance and semantic integrity.")
    parser.add_argument("review_dir")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(args.review_dir)
    errors = validate_semantics(root)
    report = {"validator": "review_semantic_provenance", "status": "fail" if errors else "pass", "errors": errors, "review_dir": str(root)}
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Literature review semantic/provenance validation passed.")
    return 0

# validate_review_package
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))
REQUIRED_FILES = [
    "search_log.csv",
    "candidate_records_raw.csv",
    "candidate_records_dedup.csv",
    "screening_decisions.csv",
    "study_registry.csv",
    "measurement_registry.csv",
    "confounder_registry.csv",
    "citation_registry.json",
    "evidence_to_decision_table.csv",
    "evidence_sufficiency_report.json",
    "review_contract.json",
    "protocol_inputs.json",
    "proposal_bridge.md",
]
FULL_PACKAGE_FILES = [
    "publication_manifest.json",
    "references.bib",
    "citation_verification_report.csv",
    "citation_verification_summary.md",
    "literature_review.docx",
    "literature_review.pdf",
    "literature_review.tex",
]
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
REQUIRED_FREE_SOURCES = {
    "OpenAlex",
    "PubMed/MEDLINE",
    "Semantic Scholar",
    "Europe PMC",
    "medRxiv",
    "bioRxiv",
}
ALLOWED_NARRATIVE_ROLES = {
    "anchor",
    "background",
    "methods_justification",
    "mechanism",
    "direct_evidence",
    "supporting_evidence",
    "measurement",
    "confounding",
    "gap",
    "discussion",
}
ALLOWED_REVIEW_TYPES = {"structured_narrative", "systematic_no_meta", "systematic_meta"}
COMPLETED_STATUSES = {"ready", "released", "complete", "completed"}
EXECUTED_SEARCH_STATUSES = {"retrieved", "completed", "complete", "success", "executed"}
PLACEHOLDER_PATTERNS = [
    r"\bexposure\s+and\s+outcome\b",
    r"\bstudy topic\b",
    r"\b(?:todo|tbd|fill in)\b",
    r"\{\{[^}]+\}\}",
    r"\[[^\]]*(?:insert|specify|set)[^\]]*\]",
]
ALLOWED_STRENGTH_VALUES = {"definitive", "suggestive", "preliminary", "background_only"}
STUDY_CREDIBILITY_VALUES = {"strong", "adequate", "limited", "weak"}
EFFECT_TRUSTWORTHINESS_VALUES = {"high", "moderate", "low", "not_applicable"}
LIKELY_DIRECTNESS_VALUES = {"direct", "indirect", "background"}
DECISION_ROLE_VALUES = {"anchor", "support", "methods", "background", "exclude"}
EVIDENCE_DIRECTION_VALUES = {
    "favorable", "harmful", "null", "mixed", "heterogeneous", "insufficient", "unclear",
}
EFFECT_ROW_DIRECTION_VALUES = {"favorable", "harmful", "null", "mixed", "unclear"}
BIAS_DOMAIN_VALUES_PHARMACOEPI = {
    "confounding_by_indication", "confounding_by_prognosis", "immortal_time_bias",
    "prevalent_user_bias", "time_zero_alignment", "informative_censoring",
    "outcome_misclassification", "exposure_misclassification", "reverse_causation",
    "selection_bias", "loss_to_followup", "overadjustment",
}
BIAS_SEVERITY_VALUES = {"high", "moderate", "low", "none_detected", "unclear"}
BIAS_DIRECTION_VALUES = {"towards_null", "away_from_null", "uncertain", "not_applicable"}
METHODS_COMPLETENESS_PATTERNS = [
    (r"search(?:ed|ing)?\s+(?:the\s+)?(?:database|pubmed|openalex|semantic scholar|europe pmc|medline)", "database search"),
    (r"\d{4}\s*(?:to|through|–|-)\s*\d{4}", "date range"),
    (r"(?:inclus|exclus)ion\s+criteri", "inclusion/exclusion criteria"),
    (r"\d+\s+(?:study|studies|articles|records|papers)\s+(?:was\s+|were\s+)?(?:included|retained|screened)", "PRISMA-style count"),
]
REVIEW_CONTRACT_FIELDS = [
    "contract_version",
    "review_type",
    "reporting_framework",
    "synthesis_method",
    "project_mode",
    "question_type",
    "review_goal",
    "design_type",
    "generated_at",
    "status",
    "downgrade_state",
    "topic",
    "primary_estimand",
    "evidence_sufficiency",
    "decision_ids",
    "citation_ids",
]
CANONICAL_PROJECT_MODES = {"research", "applied_methods", "workflow_methods"}
TREATMENT_STRATEGY_REVIEW_CONTRACT_FIELDS = [
    "deliverable_style",
    "narrative_readiness",
    "anchor_density_by_outcome",
]
SUFFICIENCY_FIELDS = [
    "evidence_density",
    "design_fit",
    "causal_temporality_risk",
    "estimand_feasibility",
    "interpretation_risk",
    "mode_recommendation",
]
PROHIBITED_BODY_PHRASES = [
    "skill-chain",
    "Codex",
    "workflow validation",
    "this review supports",
    "to support protocol development",
    "this review was designed to support",
    "Example 1",
    "applied-methods validation",
    "review_briefing.md",
    "study_registry.csv",
    "claim_registry.csv",
    "effect_registry.csv",
    "anchor_eligible",
    "narrative_readiness",
    "core_direct_strict",
    "core_direct_broad",
    "appendix_only",
    "background_policy",
    "screening architecture",
    "package logic",
    "candidate pool",
]
OVERCLAIM_WARNING_PHRASES = [
    "demonstrates",
    "proves",
    "establishes that",
    "confirms that",
    "clearly shows",
    "definitively",
    "causally linked",
    " causes ",
    "leads to",
]
META_LANGUAGE_PATTERNS = [
    r"\bthis workflow\b",
    r"\bthe workflow\b",
    r"\bthis pipeline\b",
    r"\bthe pipeline\b",
    r"\bthis upgrade\b",
    r"\bv2\.1\b",
    r"\bthe system is\b",
    r"\bthis system\b",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_csv_rows_if_exists(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_csv_rows(path)


def require_columns(rows: list[dict[str, str]], required: list[str], label: str, *, allow_empty: bool = False) -> list[str]:
    if not rows:
        return [] if allow_empty else [f"{label} is empty"]
    present = set(rows[0].keys())
    missing = [column for column in required if column not in present]
    return [f"{label} missing columns: {', '.join(missing)}"] if missing else []


def check_overclaim_phrases(text: str, phrases: list[str]) -> list[str]:
    """Return phrases found in the text body (case-insensitive).

    These are reported as warnings rather than hard failures because:
    - they may appear inside direct quotations of cited papers
    - they may appear in the background section where causal language
      is contextually appropriate
    - regex matching cannot distinguish those cases from true overclaims

    The human reviewer should check each flagged phrase and either adjust
    the prose or confirm that the corresponding claim_registry.csv entry
    has allowed_strength = definitive.
    """
    found: list[str] = []
    for phrase in phrases:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(phrase.lower())}(?![A-Za-z])")
        if pattern.search(text.lower()):
            found.append(phrase)
    return found


def check_meta_language(text: str, patterns: list[str]) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for pattern in patterns:
        if re.search(pattern, lowered):
            found.append(pattern)
    return found


def check_methods_completeness(text: str) -> list[str]:
    """Return method concepts that are missing from the narrative body."""
    missing = []
    for pattern, label in METHODS_COMPLETENESS_PATTERNS:
        if not re.search(pattern, text, re.IGNORECASE):
            missing.append(label)
    return missing


def is_placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in PLACEHOLDER_PATTERNS)


def sparse_exception(contract: dict) -> tuple[bool, str]:
    exception = contract.get("sparse_evidence_exception")
    if not isinstance(exception, dict) or not truthy(exception.get("applies")):
        return False, ""
    required = ["rationale", "search_saturation", "scope_boundary"]
    missing = [field for field in required if is_placeholder(str(exception.get(field, "")))]
    if missing:
        return False, "sparse_evidence_exception is incomplete: " + ", ".join(missing)
    return True, ""


def check_review_type_route(contract: dict) -> list[str]:
    errors: list[str] = []
    review_type = str(contract.get("review_type", "")).strip()
    frameworks_raw = contract.get("reporting_framework", [])
    if isinstance(frameworks_raw, str):
        frameworks = {part.strip().lower() for part in re.split(r"[,;|]", frameworks_raw) if part.strip()}
    else:
        frameworks = {str(part).strip().lower() for part in frameworks_raw if str(part).strip()}
    synthesis = str(contract.get("synthesis_method", "")).strip().lower()
    if review_type not in ALLOWED_REVIEW_TYPES:
        return [f"review_contract.json review_type must be one of {sorted(ALLOWED_REVIEW_TYPES)}; got {review_type!r}"]
    if is_placeholder(synthesis):
        errors.append("review_contract.json synthesis_method must be explicit and non-placeholder")
    if review_type == "structured_narrative" and not any("sanra" in item for item in frameworks):
        errors.append("structured_narrative must declare SANRA as its narrative-quality framework")
    if review_type == "systematic_no_meta":
        if not any("prisma" in item for item in frameworks):
            errors.append("systematic_no_meta must declare PRISMA/PRISMA-S")
        if not any("swim" in item for item in frameworks):
            errors.append("systematic_no_meta must declare SWiM")
        if "vote count" in synthesis and "direction" not in synthesis:
            errors.append("systematic_no_meta may not use unsafeguarded vote counting")
    if review_type == "systematic_meta":
        if not any("prisma" in item for item in frameworks):
            errors.append("systematic_meta must declare PRISMA/PRISMA-S")
        if not re.search(r"meta|random.effects|fixed.effect|quantitative", synthesis):
            errors.append("systematic_meta must name a quantitative/meta-analytic synthesis method")
    return errors


def check_search_execution(search_log: list[dict[str, str]], completed: bool) -> list[str]:
    if not completed:
        return []
    errors: list[str] = []
    for index, row in enumerate(search_log, start=2):
        status = (row.get("status") or "").strip().lower()
        if status not in EXECUTED_SEARCH_STATUSES:
            continue
        source_query = row.get("source_query") or row.get("query") or ""
        if is_placeholder(source_query) or len(source_query.strip()) < 12:
            errors.append(f"search_log.csv row {index} has an executed but placeholder/underspecified source_query")
        if is_placeholder(row.get("date_searched") or ""):
            errors.append(f"search_log.csv row {index} has no real date_searched")
        for field in ("n_retrieved", "n_after_dedup"):
            raw = (row.get(field) or "").strip()
            if not raw.isdigit():
                errors.append(f"search_log.csv row {index} executed search lacks integer {field}")
        if (row.get("n_retrieved") or "").isdigit() and (row.get("n_after_dedup") or "").isdigit():
            if int(row["n_after_dedup"]) > int(row["n_retrieved"]):
                errors.append(f"search_log.csv row {index} has n_after_dedup greater than n_retrieved")
    executed = [row for row in search_log if (row.get("status") or "").strip().lower() in EXECUTED_SEARCH_STATUSES]
    if not executed:
        errors.append("completed review has no executed search rows")
    return errors


def check_search_freshness(search_log: list[dict[str, str]], contract: dict, completed: bool) -> list[str]:
    if not completed:
        return []
    dates: list[date] = []
    for row in search_log:
        if (row.get("status") or "").strip().lower() not in EXECUTED_SEARCH_STATUSES:
            continue
        try:
            dates.append(datetime.strptime((row.get("date_searched") or "").strip(), "%Y-%m-%d").date())
        except ValueError:
            continue
    if not dates:
        return ["completed review has no parseable executed search date"]
    age = (date.today() - max(dates)).days
    if age > 183 and not truthy(contract.get("older_search_cutoff_disclosed")):
        return [f"latest executed search is {age} days old; refresh it or set older_search_cutoff_disclosed=true with a rationale"]
    return []


def check_search_strategy_document(text: str, completed: bool) -> list[str]:
    if not completed:
        return []
    if not text.strip():
        return ["completed review requires non-empty search_strategy.md"]
    errors: list[str] = []
    if re.search(r"\b(?:TODO|TBD|FILL IN)\b|\{\{[^}]+\}\}", text, re.IGNORECASE):
        errors.append("search_strategy.md contains unresolved placeholder text")
    if not re.search(r"\b(?:PubMed|MEDLINE|OpenAlex|Europe PMC|Embase|Web of Science)\b", text, re.IGNORECASE):
        errors.append("search_strategy.md does not name a searched bibliographic source")
    if not re.search(r"\b\d{4}-\d{2}-\d{2}\b", text):
        errors.append("search_strategy.md does not report an exact search date")
    if not re.search(r"\b(?:retrieved|yield|records?)\b.{0,40}\b\d+\b|\b\d+\b.{0,40}\b(?:retrieved|yield|records?)\b", text, re.IGNORECASE):
        errors.append("search_strategy.md does not report a numeric retrieval yield")
    return errors


def check_screening_accounting(
    screening: list[dict[str, str]],
    completed: bool,
    sparse_ok: bool,
) -> list[str]:
    if not completed:
        return []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(screening, start=2):
        paper_id = (row.get("paper_id") or "").strip()
        if not paper_id:
            errors.append(f"screening_decisions.csv row {index} lacks paper_id")
        elif paper_id in seen_ids:
            errors.append(f"screening_decisions.csv has duplicate paper_id {paper_id!r}")
        seen_ids.add(paper_id)
        decision = (row.get("decision") or "").strip().lower()
        stage = (row.get("screening_stage") or "").strip().lower()
        reason = (row.get("reason") or "").strip()
        if decision in {"exclude", "excluded"} and (is_placeholder(reason) or len(reason) < 15):
            errors.append(f"screening_decisions.csv row {index} exclusion lacks a specific reason")
        is_full_text = "full" in stage or (row.get("access_type") or "").strip().lower() == "full_text"
        if is_full_text and decision in {"exclude", "excluded"}:
            code = (row.get("exclusion_reason_code") or "").strip()
            if is_placeholder(code):
                errors.append(f"screening_decisions.csv row {index} full-text exclusion lacks exclusion_reason_code")
    fulltext_exclusions = [
        row for row in screening
        if ("full" in (row.get("screening_stage") or "").lower()
            or (row.get("access_type") or "").strip().lower() == "full_text")
        and (row.get("decision") or "").strip().lower() in {"exclude", "excluded"}
    ]
    if len(screening) >= 10 and not fulltext_exclusions and not sparse_ok:
        errors.append("mature completed review has no recorded full-text exclusions; document exclusions or justify a sparse-evidence exception")
    return errors


def check_quality_appraisal(
    appraisal: list[dict[str, str]],
    included_ids: set[str],
    completed: bool,
    design_by_paper: dict[str, str] | None = None,
) -> list[str]:
    if not completed:
        return []
    errors: list[str] = []
    if not appraisal:
        return ["completed review requires non-empty quality_appraisal_registry.csv"]
    rows_by_paper: dict[str, list[dict[str, str]]] = defaultdict(list)
    signatures: Counter[tuple[str, str, str]] = Counter()
    for index, row in enumerate(appraisal, start=2):
        paper_id = (row.get("paper_id") or "").strip()
        rows_by_paper[paper_id].append(row)
        for field in ("domain", "judgment", "raw_signal", "evidence_source"):
            if is_placeholder(row.get(field) or ""):
                errors.append(f"quality_appraisal_registry.csv row {index} has blank/template {field}")
        signatures[(row.get("judgment", ""), row.get("raw_signal", ""), row.get("note", ""))] += 1
    missing = sorted(included_ids - set(rows_by_paper))
    if missing:
        errors.append("included claim-bearing studies lack quality appraisal: " + ", ".join(missing))
    for paper_id in sorted(included_ids & set(rows_by_paper)):
        domains = {(row.get("domain") or "").strip().lower() for row in rows_by_paper[paper_id] if (row.get("domain") or "").strip()}
        if len(domains) < 4:
            errors.append(f"quality appraisal for {paper_id} covers only {len(domains)} domains; at least 4 design-appropriate domains are required")
        design = (design_by_paper or {}).get(paper_id, "").lower()
        domain_text = " ".join(domains)
        required_concepts: list[tuple[str, tuple[str, ...]]] = []
        if "cross" in design:
            required_concepts = [
                ("selection", ("selection", "sampling")),
                ("measurement", ("measurement", "misclassification", "validity")),
                ("confounding", ("confound", "adjustment", "overadjust")),
                ("reverse causation/temporality", ("reverse", "temporality")),
            ]
        elif any(token in design for token in ("cohort", "prospective", "longitudinal")):
            required_concepts = [
                ("selection/attrition", ("selection", "attrition", "loss")),
                ("measurement", ("measurement", "misclassification", "validity")),
                ("confounding", ("confound", "adjustment", "overadjust")),
                ("temporality/time zero", ("temporality", "time zero", "baseline")),
            ]
        elif any(token in design for token in ("systematic review", "meta-analysis", "umbrella")):
            required_concepts = [
                ("search/screening", ("search", "screen")),
                ("risk of bias", ("risk of bias", "appraisal")),
                ("synthesis", ("synthesis", "meta-analysis", "pooling")),
                ("heterogeneity/reporting bias", ("heterogeneity", "publication", "reporting bias")),
            ]
        missing_concepts = [
            label for label, aliases in required_concepts
            if not any(alias in domain_text for alias in aliases)
        ]
        if missing_concepts:
            errors.append(f"quality appraisal for {paper_id} ({design}) lacks design-appropriate domains: {', '.join(missing_concepts)}")
    if len(appraisal) >= 8 and signatures and signatures.most_common(1)[0][1] / len(appraisal) > 0.60:
        errors.append("quality appraisal is predominantly repeated template text rather than study-specific evidence")
    return errors


def check_depth_and_reference_floor(
    contract: dict,
    citations: list[dict],
    fulltexts: list[dict[str, str]],
    completed: bool,
) -> list[str]:
    if not completed:
        return []
    preset = str(contract.get("delivery_preset", "decision_grade"))
    if preset not in {"decision_grade", "full_package"}:
        return []
    sparse_ok, sparse_error = sparse_exception(contract)
    errors = [sparse_error] if sparse_error else []
    verified_count = sum(
        1 for entry in citations
        if truthy(entry.get("verified"))
        or str(entry.get("verification_status", "")).strip().lower() == "verified"
        or entry.get("doi") or entry.get("pmid")
    )
    deep_read_ids = {
        (row.get("paper_id") or "").strip()
        for row in fulltexts
        if (truthy(row.get("deep_read_completed"))
            or (row.get("fulltext_status") or "").strip().lower() in {"deep_read", "deep_read_completed", "full_text_reviewed", "completed"})
        and (row.get("paper_id") or "").strip()
    }
    if not sparse_ok and verified_count < 30:
        errors.append(f"{preset} mature-topic review requires at least 30 verified/identity-resolved references; found {verified_count}")
    if not sparse_ok and len(deep_read_ids) < 12:
        errors.append(f"{preset} review requires at least 12 documented deep-read studies; found {len(deep_read_ids)}")
    return errors


def check_effect_coverage(
    studies: list[dict[str, str]],
    effects: list[dict[str, str]],
    completed: bool,
) -> list[str]:
    if not completed:
        return []
    direct_ids = {
        (row.get("paper_id") or "").strip()
        for row in studies
        if (row.get("primary_role") or "").strip().lower() in {"anchor", "direct_evidence", "counterevidence"}
        and (row.get("paper_id") or "").strip()
    }
    if not direct_ids:
        return ["completed review has no direct/counterevidence studies identified in study_registry.csv"]
    complete_ids: set[str] = set()
    for row in effects:
        paper_id = (row.get("paper_id") or row.get("study_id") or "").strip()
        estimate = (row.get("point_estimate") or "").strip()
        lower = (row.get("ci_lower") or "").strip()
        upper = (row.get("ci_upper") or "").strip()
        if paper_id and estimate and ((lower and upper) or estimate.lower() in {"nr", "not reported"}):
            complete_ids.add(paper_id)
    coverage = len(direct_ids & complete_ids) / len(direct_ids)
    if coverage < 0.80:
        return [f"effect_registry.csv has complete estimate/interval or explicit NR for only {coverage:.0%} of direct/counterevidence studies; require at least 80%"]
    return []


def markdown_table_data_rows(section: str) -> int:
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?", stripped):
            continue
        rows.append(stripped)
    return max(0, len(rows) - 1)


def check_embedded_evidence_tables(text: str) -> list[str]:
    errors: list[str] = []
    for heading, minimum in (("Evidence Map and Study Characteristics", 3), ("Effect Evidence Matrix", 3)):
        section = extract_section(text, heading)
        if not section:
            errors.append(f"literature_review_synthesis.md lacks required main-body section: {heading}")
        elif markdown_table_data_rows(section) < minimum:
            errors.append(f"{heading} must contain at least {minimum} populated study rows in the main body")
        elif is_placeholder(section):
            errors.append(f"{heading} still contains placeholder content")
    return errors


def reconcile_screening_counts(
    text: str,
    candidate_raw: list[dict[str, str]],
    candidate_dedup: list[dict[str, str]],
    screening: list[dict[str, str]],
) -> list[str]:
    """Hard-check reader-facing screening counts against registry truth."""
    section = extract_section(text, "Search and Screening")
    patterns = {
        "retrieved": r"\b(\d+)\s+(?:records?|articles?|papers?)\s+(?:was\s+|were\s+)?retrieved\b",
        "deduplicated": r"\b(\d+)\s+(?:records?|articles?|papers?)\s+(?:remained\s+)?after\s+deduplication\b",
        "screened": r"\b(\d+)\s+(?:content\s+sources?|reports?|items?)\s+(?:was\s+|were\s+)?assessed\b",
        "included": r"\b(\d+)\s+(?:study|studies|articles?|papers?|sources?)\s+(?:was\s+|were\s+)?(?:retained(?:\s+and\s+included)?|included)\b",
    }
    reported: dict[str, int] = {}
    errors: list[str] = []
    for label, pattern in patterns.items():
        match = re.search(pattern, section, re.IGNORECASE)
        if not match:
            errors.append(f"Search and Screening section is missing a parseable {label} count")
        else:
            reported[label] = int(match.group(1))
    if errors:
        return errors
    content_rows = [
        row for row in screening
        if truthy(row.get("content_assessed"))
    ]
    expected = {
        "retrieved": len(candidate_raw),
        "deduplicated": len(candidate_dedup),
        "screened": len(content_rows),
        "included": sum(
            1
            for row in screening
            if (row.get("include_in_synthesis") or "").strip().lower() in {"yes", "true", "1"}
            or (row.get("decision") or "").strip().lower() == "include"
        ),
    }
    for label, value in expected.items():
        if reported[label] != value:
            errors.append(
                f"Search and Screening {label} count {reported[label]} does not match registry count {value}"
            )
    return errors


def check_enum_values(
    rows: list[dict[str, str]],
    column: str,
    allowed: set[str],
    label: str,
    *,
    allow_empty: bool = True,
) -> list[str]:
    """Return errors for any row where `column` contains an unrecognised value."""
    errors = []
    for i, row in enumerate(rows, start=2):  # row 1 is header
        val = (row.get(column) or "").strip()
        if not val:
            continue  # blank is acceptable during active filling
        if val not in allowed:
            errors.append(
                f"{label} row {i}: invalid {column}={val!r}; allowed: {sorted(allowed)}"
            )
    return errors


def check_claim_evidence_binding(
    claim_registry: list[dict[str, str]],
    effect_registry: list[dict[str, str]],
    label: str,
) -> list[str]:
    """Warn when a primary claim has no supporting_evidence_row_ids bound to effect_registry."""
    if not claim_registry or not effect_registry:
        return []
    effect_ids = {
        (row.get("effect_id") or row.get("paper_id") or "").strip()
        for row in effect_registry
        if (row.get("effect_id") or row.get("paper_id") or "").strip()
    }
    errors = []
    for row in claim_registry:
        if (row.get("supports_primary_direction_claim") or "").strip().lower() != "yes":
            continue
        row_ids = [
            r.strip()
            for r in (row.get("supporting_evidence_row_ids") or "").split(",")
            if r.strip()
        ]
        if not row_ids:
            errors.append(
                f"{label} claim {row.get('claim_id', '?')}: primary claim has no supporting_evidence_row_ids; "
                "bind at least one effect_registry row"
            )
        else:
            missing_ids = [r for r in row_ids if r not in effect_ids]
            if missing_ids:
                errors.append(
                    f"{label} claim {row.get('claim_id', '?')}: supporting_evidence_row_ids "
                    f"{missing_ids} not found in effect_registry (effect_id column)"
                )
    return errors


def check_direction_consistency(
    claim_registry: list[dict[str, str]],
    effect_registry: list[dict[str, str]],
) -> list[str]:
    """Warn when a primary claim's evidence_direction contradicts directions in effect_registry.

    Uses the optional `direction` column added to effect_registry.csv.
    Only checks primary claims (supports_primary_direction_claim=yes) with
    evidence_direction explicitly set to harmful or favorable.
    """
    if not claim_registry or not effect_registry:
        return []

    CONTRADICTIONS = {
        "harmful": "favorable",
        "favorable": "harmful",
    }

    # Build paper_id → set of effect directions from effect_registry
    effect_directions_by_paper: dict[str, set[str]] = {}
    for row in effect_registry:
        pid = (row.get("paper_id") or "").strip()
        direction = (row.get("direction") or "").strip().lower()
        if pid and direction in EFFECT_ROW_DIRECTION_VALUES:
            effect_directions_by_paper.setdefault(pid, set()).add(direction)

    warnings: list[str] = []
    for claim in claim_registry:
        if (claim.get("supports_primary_direction_claim") or "").lower() != "yes":
            continue
        claim_dir = (claim.get("evidence_direction") or "").strip().lower()
        if claim_dir not in CONTRADICTIONS:
            continue
        opposite = CONTRADICTIONS[claim_dir]
        claim_id = claim.get("claim_id") or "?"
        anchor_ids = [
            a.strip()
            for a in (claim.get("eligible_anchor_paper_ids") or "").split(",")
            if a.strip()
        ]
        for aid in anchor_ids:
            directions = effect_directions_by_paper.get(aid, set())
            if opposite in directions:
                warnings.append(
                    f"claim {claim_id}: evidence_direction={claim_dir!r} but anchor paper {aid} "
                    f"has effect direction={opposite!r} in effect_registry — review before finalising"
                )
    return warnings


def split_ids(value: str) -> set[str]:
    return {
        item.strip()
        for item in re.split(r"[,;|]", value or "")
        if item.strip()
    }


def split_json_ids(value) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return split_ids(str(value or ""))


def duplicate_values(rows: list[dict], field: str) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        value = str(row.get(field, "")).strip()
        if not value:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def check_referential_integrity(
    review_contract: dict,
    citation_registry: dict,
    study_registry: list[dict[str, str]],
    claim_registry: list[dict[str, str]],
    effect_registry: list[dict[str, str]],
    evidence_table: list[dict[str, str]],
    narrative_text: str,
) -> list[str]:
    errors: list[str] = []
    study_ids = {row.get("paper_id", "").strip() for row in study_registry if row.get("paper_id", "").strip()}
    decision_ids = {row.get("decision_id", "").strip() for row in evidence_table if row.get("decision_id", "").strip()}
    entries = citation_registry.get("entries", [])
    citation_ids = {row.get("citation_id", "").strip() for row in entries if row.get("citation_id", "").strip()}
    effect_ids = {row.get("effect_id", "").strip() for row in effect_registry if row.get("effect_id", "").strip()}
    citation_numbers: dict[str, int] = {}
    number_owners: dict[int, list[str]] = {}
    for entry in entries:
        citation_id = str(entry.get("citation_id", "")).strip()
        try:
            number = int(entry.get("reference_number"))
            if number < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"citation {citation_id or 'UNKNOWN'} lacks a positive integer reference_number")
            continue
        citation_numbers[citation_id] = number
        number_owners.setdefault(number, []).append(citation_id)
    duplicate_reference_numbers = {number: ids for number, ids in number_owners.items() if len(ids) > 1}
    if duplicate_reference_numbers:
        errors.append(f"citation registry contains duplicate reference_number values: {duplicate_reference_numbers}")
    for label, rows, field in (
        ("citation_registry", entries, "citation_id"),
        ("study_registry", study_registry, "paper_id"),
        ("evidence_to_decision_table", evidence_table, "decision_id"),
        ("claim_registry", claim_registry, "claim_id"),
        ("effect_registry", effect_registry, "effect_id"),
    ):
        duplicates = duplicate_values(rows, field)
        if duplicates:
            errors.append(f"{label} contains duplicate {field} values: {sorted(duplicates)}")
    for entry in entries:
        citation_id = entry.get("citation_id", "UNKNOWN")
        paper_id = str(entry.get("paper_id", "")).strip()
        if not paper_id or paper_id not in study_ids:
            errors.append(f"citation {citation_id} references unknown paper_id {paper_id!r}")
        unknown_decisions = split_json_ids(entry.get("supporting_decision_ids")) - decision_ids
        if unknown_decisions:
            errors.append(f"citation {citation_id} references unknown decision IDs: {sorted(unknown_decisions)}")
        unknown_effects = split_json_ids(entry.get("supporting_evidence_row_ids")) - effect_ids
        if unknown_effects:
            errors.append(f"citation {citation_id} references unknown effect IDs: {sorted(unknown_effects)}")
    unknown_contract_citations = set(review_contract.get("citation_ids", [])) - citation_ids
    if unknown_contract_citations:
        errors.append(f"review_contract citation_ids are unresolved: {sorted(unknown_contract_citations)}")
    unknown_contract_decisions = set(review_contract.get("decision_ids", [])) - decision_ids
    if unknown_contract_decisions:
        errors.append(f"review_contract decision_ids are unresolved: {sorted(unknown_contract_decisions)}")
    for row in evidence_table:
        unknown = split_ids(row.get("supporting_paper_ids", "")) - study_ids
        if unknown:
            errors.append(f"decision {row.get('decision_id', 'UNKNOWN')} references unknown papers: {sorted(unknown)}")
    for row in claim_registry:
        referenced = set()
        for field in ("eligible_anchor_paper_ids", "supporting_paper_ids", "counter_study_ids"):
            referenced.update(split_ids(row.get(field, "")))
        unknown = referenced - study_ids
        if unknown:
            errors.append(f"claim {row.get('claim_id', 'UNKNOWN')} references unknown papers: {sorted(unknown)}")
    inline_ids = set(re.findall(r"\[((?:CIT|P)[A-Za-z0-9_.-]+)\]", narrative_text))
    if inline_ids:
        errors.append(f"narrative exposes internal citation IDs instead of publication markers: {sorted(inline_ids)}")
    numeric_markers = {
        int(number)
        for marker in re.findall(r"\[(\d+(?:,\d+)*)\]", narrative_text)
        for number in marker.split(",")
    }
    unresolved_numbers = numeric_markers - set(citation_numbers.values())
    if unresolved_numbers:
        errors.append(f"narrative contains unresolved numeric citation markers: {sorted(unresolved_numbers)}")
    if citation_ids and not numeric_markers:
        errors.append("completed narrative has citation registry entries but no numeric inline citation markers")
    references_match = re.search(r"^#{1,3}\s+References\s*$([\s\S]*)", narrative_text, re.M | re.I)
    references_text = references_match.group(1) if references_match else ""
    for entry in entries:
        citation_id = str(entry.get("citation_id", "")).strip()
        number = citation_numbers.get(citation_id)
        if number is None:
            continue
        reference_match = re.search(rf"^\s*{number}\.\s+(.+)$", references_text, re.M)
        if not reference_match:
            errors.append(f"References section lacks numbered entry {number} for citation {citation_id}")
            continue
        title = str(entry.get("title", "")).strip()
        normalized_title = re.sub(
            r"[^a-z0-9]+",
            " ",
            unicodedata.normalize("NFKD", title.lower())
            .encode("ascii", "ignore")
            .decode("ascii"),
        ).strip()
        normalized_reference = re.sub(
            r"[^a-z0-9]+",
            " ",
            unicodedata.normalize("NFKD", reference_match.group(1).lower())
            .encode("ascii", "ignore")
            .decode("ascii"),
        ).strip()
        if not normalized_title or normalized_title not in normalized_reference:
            errors.append(f"reference {number} does not match the registered title for citation {citation_id}")
        authors = str(entry.get("authors", "")).strip()
        if authors:
            first_author = authors.split(";")[0].strip()
            surname = (first_author.split(",")[0] if "," in first_author else first_author.split()[0]).lower()
            normalized_surname = re.sub(
                r"[^a-z0-9]+",
                " ",
                unicodedata.normalize("NFKD", surname).encode("ascii", "ignore").decode("ascii"),
            ).strip()
            if normalized_surname and normalized_surname not in normalized_reference:
                errors.append(f"reference {number} does not match the registered first author for citation {citation_id}")
        year = str(entry.get("year", "")).strip()
        if year and not re.search(rf"\b{re.escape(year)}\b", reference_match.group(1)):
            errors.append(f"reference {number} does not match the registered year for citation {citation_id}")
        doi = str(entry.get("doi", "")).strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
        if doi and doi not in reference_match.group(1).lower():
            errors.append(f"reference {number} does not match the registered DOI for citation {citation_id}")
    for row in claim_registry:
        claim_text = str(row.get("claim_text", "")).strip()
        supporting_ids = split_ids(row.get("supporting_paper_ids", "")) | split_ids(
            row.get("eligible_anchor_paper_ids", "")
        )
        if not claim_text or not supporting_ids:
            continue
        matching_paragraphs = [part for part in narrative_text.split("\n\n") if claim_text in part]
        if not matching_paragraphs:
            errors.append(f"claim {row.get('claim_id', 'UNKNOWN')} is absent from the completed narrative")
            continue
        if narrative_text.count(claim_text) != 1:
            errors.append(f"claim {row.get('claim_id', 'UNKNOWN')} must occur exactly once in the completed narrative")
            continue
        citation_ids_for_papers = {
            entry.get("citation_id")
            for entry in entries
            if entry.get("paper_id") in supporting_ids
        }
        allowed_claim_numbers = {
            citation_numbers[citation_id]
            for citation_id in citation_ids_for_papers
            if citation_id in citation_numbers
        }
        paragraph_numbers = {
            int(number)
            for marker in re.findall(r"\[(\d+(?:,\d+)*)\]", matching_paragraphs[0])
            for number in marker.split(",")
        }
        if not paragraph_numbers.intersection(allowed_claim_numbers):
            errors.append(
                f"claim {row.get('claim_id', 'UNKNOWN')} lacks a supporting inline citation marker in the same paragraph"
            )
            continue
        exact_sentence = False
        for sentence in re.findall(r"[^.!?\n]+[.!?]?", matching_paragraphs[0]):
            sentence_numbers = {
                int(number)
                for marker in re.findall(r"\[(\d+(?:,\d+)*)\]", sentence)
                for number in marker.split(",")
            }
            if not sentence_numbers.intersection(allowed_claim_numbers):
                continue
            prose = re.sub(r"\[\d+(?:,\d+)*\]", "", sentence).strip().rstrip(".!?").strip()
            expected = claim_text.strip().rstrip(".!?").strip()
            if prose == expected:
                exact_sentence = True
                break
        if not exact_sentence:
            errors.append(
                f"claim {row.get('claim_id', 'UNKNOWN')} is not exactly bound to its citation marker at sentence level"
            )
    return errors


def check_section_composition(text: str) -> list[str]:
    """Detect common section composition problems:
    - Outcome sections that only state evidence gaps without any finding
    - Direct evidence section that appears very short relative to indirect
    - Consecutive paragraphs with identical first-word openers
    """
    warnings: list[str] = []

    # Pattern: sections that are only "evidence is limited/gap/absent" — no actual finding
    gap_only_sections = re.findall(
        r"#{1,3}[^\n]+\n+(?:(?:currently lacks|no direct|evidence gap|remains thin|"
        r"limited evidence|evidence is limited|insufficient evidence)[^\n]*\n+){2,}",
        text,
        re.IGNORECASE,
    )
    if gap_only_sections:
        warnings.append(
            f"literature_review_synthesis.md has {len(gap_only_sections)} outcome section(s) "
            "that contain only gap statements without any actual finding — condense or remove"
        )

    # Pattern: paragraph opening with "This study" or "This research" many times
    this_study_count = len(re.findall(r"\bThis (?:study|research|paper|article)\b", text, re.IGNORECASE))
    if this_study_count >= 5:
        warnings.append(
            f"literature_review_synthesis.md contains {this_study_count} 'This study/paper' openers — "
            "prefer naming author and year, or restructure as thematic synthesis"
        )

    return warnings


def check_repeated_sentence_patterns(text: str) -> list[str]:
    """Detect near-identical sentence openers that suggest template-driven prose."""
    warnings: list[str] = []
    body = re.split(r"^##\s+References\s*$", text, maxsplit=1, flags=re.M | re.I)[0]
    body = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("|"))
    sentences = re.split(r"(?<=[.!?])\s+", body)
    opener_counts: dict[str, int] = {}
    for sent in sentences:
        words = sent.strip().split()
        if len(words) >= 5:
            opener = re.sub(r"\d+", "#", " ".join(words[:5]).lower())
            opener_counts[opener] = opener_counts.get(opener, 0) + 1
    repeated = [(opener, count) for opener, count in opener_counts.items() if count >= 3]
    if repeated:
        examples = "; ".join(f'"{o}" ×{c}' for o, c in repeated[:3])
        warnings.append(
            f"literature_review_synthesis.md contains repeated sentence openers (template signal): {examples}"
        )
    return warnings


def fivegram_uniqueness(text: str) -> float:
    body = re.split(r"^##\s+References\s*$", text, maxsplit=1, flags=re.M | re.I)[0]
    tokens = re.findall(r"[a-z]{3,}", re.sub(r"\d+", "#", body.lower()))
    grams = [tuple(tokens[index:index + 5]) for index in range(max(0, len(tokens) - 4))]
    return len(set(grams)) / len(grams) if grams else 1.0


def high_similarity_paragraph_pairs(text: str, threshold: float = 0.82) -> list[tuple[int, int, float]]:
    body = re.split(r"^##\s+References\s*$", text, maxsplit=1, flags=re.M | re.I)[0]
    stopwords = {
        "about", "after", "also", "among", "because", "before", "between", "could", "from", "have",
        "into", "more", "most", "only", "other", "should", "such", "than", "that", "their", "there",
        "these", "this", "through", "using", "were", "which", "while", "with", "within", "would",
    }
    paragraphs = []
    for part in re.split(r"\n\s*\n", body):
        if part.lstrip().startswith("#") or len(part.split()) < 45:
            continue
        words = set(re.findall(r"[a-z]{4,}", re.sub(r"\d+", "#", part.lower()))) - stopwords
        if words:
            paragraphs.append(words)
    pairs: list[tuple[int, int, float]] = []
    for left in range(len(paragraphs)):
        for right in range(left + 1, len(paragraphs)):
            union = paragraphs[left] | paragraphs[right]
            score = len(paragraphs[left] & paragraphs[right]) / len(union) if union else 0.0
            if score >= threshold:
                pairs.append((left + 1, right + 1, round(score, 3)))
    return pairs


def validate_publication_bundle(root: Path, warnings: list[str], errors: list[str]) -> None:
    manifest_path = root / "publication_manifest.json"
    if not manifest_path.exists():
        return
    manifest = load_json(manifest_path)
    # The scaffold reserves this filename with an empty object. Publication
    # checks become binding only after the packaging step populates the manifest.
    if not manifest:
        return
    for field in ["manifest_version", "venue_profile", "citation_style", "languages", "source_files", "artifacts"]:
        if field not in manifest:
            errors.append(f"publication_manifest.json missing field: {field}")
    source_files = manifest.get("source_files", [])
    if not isinstance(source_files, list) or not source_files:
        errors.append("publication_manifest.json must list at least one source file")
        source_files = []
    source_names: list[str] = []
    for item in source_files:
        if not isinstance(item, dict):
            errors.append("publication_manifest.json source_files entries must be hash-bound objects")
            continue
        name = str(item.get("file", ""))
        source_names.append(name)
        path = root / name
        if not name or Path(name).name != name or not path.exists() or path.stat().st_size == 0:
            errors.append(f"publication_manifest.json references missing/empty source file: {name!r}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if item.get("sha256") != actual_hash or item.get("size_bytes") != path.stat().st_size:
            errors.append(f"publication source hash/size mismatch: {name}")
    if source_names and "literature_review_synthesis.md" not in source_names:
        errors.append("publication_manifest.json source_files must include literature_review_synthesis.md")
    artifact_rows = manifest.get("artifacts", [])
    if not isinstance(artifact_rows, list) or not artifact_rows:
        errors.append("publication_manifest.json must contain a non-empty artifacts list")
    else:
        artifact_names = [str(item.get("file", "")) for item in artifact_rows]
        duplicate_artifacts = {name for name in artifact_names if name and artifact_names.count(name) > 1}
        if duplicate_artifacts:
            errors.append(f"publication_manifest.json contains duplicate artifact entries: {sorted(duplicate_artifacts)}")
        for item in artifact_rows:
            name = str(item.get("file", ""))
            path = root / name
            if not name or Path(name).name != name or not path.exists() or path.stat().st_size == 0:
                errors.append(f"publication_manifest.json references missing/empty artifact: {name!r}")
                continue
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if item.get("sha256") != actual_hash or item.get("size_bytes") != path.stat().st_size:
                errors.append(f"publication artifact hash/size mismatch: {name}")
        manifest_bound_files = [name for name in FULL_PACKAGE_FILES if name != "publication_manifest.json"]
        missing_manifest_entries = set(manifest_bound_files + ["literature_review_synthesis.md", "delivery_quality_report.json"]) - set(artifact_names)
        if missing_manifest_entries:
            errors.append(f"publication manifest does not enumerate required artifacts: {sorted(missing_manifest_entries)}")
        missing_source_artifacts = set(source_names) - set(artifact_names)
        if missing_source_artifacts:
            errors.append(f"publication source_files are not enumerated as artifacts: {sorted(missing_source_artifacts)}")
        source_path = root / "literature_review_synthesis.md"
        if source_path.exists():
            current_source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            for name in ("literature_review.docx", "literature_review.pdf", "literature_review.tex"):
                row = next((item for item in artifact_rows if item.get("file") == name), None)
                if row and row.get("source_sha256") != current_source_hash:
                    errors.append(f"publication export is stale relative to source: {name}")
                if row and not str(row.get("generator", "")).strip():
                    errors.append(f"publication export lacks generator provenance: {name}")
    if not (root / "references.bib").exists():
        errors.append("references.bib is missing despite publication_manifest.json being present")
    if not (root / "delivery_quality_report.json").exists():
        errors.append("delivery_quality_report.json is missing despite publication_manifest.json being present")
    else:
        report = load_json(root / "delivery_quality_report.json")
        if not report.get("files"):
            errors.append("delivery_quality_report.json must contain a non-empty files list")
        for item in report.get("files", []):
            if not item.get("sections"):
                warnings.append(
                    f"delivery_quality_report.json file entry has no section metrics: {item.get('file', 'unknown')}"
                )


def inspect_pdf(path: Path) -> tuple[bool, str]:
    """Return whether a real PDF parser can read at least one page, plus metadata text."""
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        try:
            result = subprocess.run(
                [pdfinfo, str(path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, ""
        if result.returncode != 0:
            return False, result.stdout + result.stderr
        match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
        return bool(match and int(match.group(1)) > 0), result.stdout
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        metadata = "\n".join(f"{key}: {value}" for key, value in (reader.metadata or {}).items())
        return len(reader.pages) > 0, metadata
    except Exception:
        return False, ""


def detect_listy_profile_lines(text: str) -> int:
    return sum(
        1
        for line in text.splitlines()
        if line.strip().startswith("- **")
        and "contributes to the mapped evidence" in line.lower()
    )


def rough_body_word_count(text: str) -> int:
    tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)
    return len(tokens)


def main_validate_review_package() -> int:
    parser = argparse.ArgumentParser(description="Validate a structured literature-review package.")
    parser.add_argument("review_dir")
    parser.add_argument(
        "--min-body-words",
        type=int,
        default=0,
        help="Optional stricter floor. Mature decision-grade/full-package reviews always enforce at least 4500 body words.",
    )
    parser.add_argument(
        "--allow-structure-only",
        action="store_true",
        help="Allow validation to pass without literature_review_synthesis.md.",
    )
    args = parser.parse_args()

    root = Path(args.review_dir)
    errors: list[str] = []
    warnings: list[str] = []

    missing = [name for name in REQUIRED_FILES if not (root / name).exists()]
    if missing:
        errors.append(f"missing required files: {', '.join(missing)}")

    if errors:
        raise SystemExit("\n".join(errors))

    search_log = read_csv_rows(root / "search_log.csv")
    candidate_records_raw = read_csv_rows(root / "candidate_records_raw.csv")
    candidate_records_dedup = read_csv_rows(root / "candidate_records_dedup.csv")
    screening_decisions = read_csv_rows(root / "screening_decisions.csv")
    study_registry = read_csv_rows(root / "study_registry.csv")
    measurement_registry = read_csv_rows(root / "measurement_registry.csv")
    confounder_registry = read_csv_rows(root / "confounder_registry.csv")
    evidence_table = read_csv_rows(root / "evidence_to_decision_table.csv")
    effect_registry = read_csv_rows_if_exists(root / "effect_registry.csv")
    claim_registry = read_csv_rows_if_exists(root / "claim_registry.csv")
    bias_registry = read_csv_rows_if_exists(root / "bias_registry.csv")
    quality_appraisal = read_csv_rows_if_exists(root / "quality_appraisal_registry.csv")
    fulltext_inventory = read_csv_rows_if_exists(root / "fulltext_inventory.csv")
    protocol_inputs = load_json(root / "protocol_inputs.json")

    allow_empty = args.allow_structure_only

    errors.extend(require_columns(search_log, ["query", "source", "status"], "search_log.csv", allow_empty=allow_empty))
    errors.extend(
        require_columns(
            search_log,
            [
                "search_round",
                "query_family",
                "query",
                "source",
                "source_query",
                "date_searched",
                "status",
            ],
            "search_log.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            candidate_records_raw,
            ["search_id", "source", "title", "url", "publication_status"],
            "candidate_records_raw.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            candidate_records_dedup,
            ["search_id", "source", "title", "url", "publication_status"],
            "candidate_records_dedup.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            screening_decisions,
            ["paper_id", "decision", "screening_stage", "reason", "include_in_synthesis"],
            "screening_decisions.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            study_registry,
            ["paper_id", "primary_role", "design", "population", "core_findings"],
            "study_registry.csv",
            allow_empty=allow_empty,
        )
    )
    eligibility_cols = [
        "direct_question_match",
        "design_integrity_ok",
        "comparator_integrity_ok",
        "time_zero_clear",
        "prior_user_design",
    ]
    strategy_fields = [
        "synthesis_tier",
        "anchor_eligible",
        *eligibility_cols,
    ]
    strategy_screening_fields = [
        *eligibility_cols,
        "directness_tier",
        "exclusion_reason_code",
        "question_match_summary",
    ]
    if study_registry and not all(col in study_registry[0] for col in eligibility_cols):
        missing_elig = [c for c in eligibility_cols if c not in study_registry[0]]
        warnings.append(
            f"study_registry.csv is missing eligibility columns: {', '.join(missing_elig)}. "
            "Add these for treatment_strategy_comparison or decision_support reviews."
        )
    errors.extend(
        require_columns(
            measurement_registry,
            ["construct", "preferred_tool", "protocol_use"],
            "measurement_registry.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            confounder_registry,
            ["variable", "classification", "recommended_main_model_role"],
            "confounder_registry.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            evidence_table,
            ["decision_id", "decision", "supporting_paper_ids"],
            "evidence_to_decision_table.csv",
            allow_empty=allow_empty,
        )
    )

    review_contract = load_json(root / "review_contract.json")
    sufficiency = load_json(root / "evidence_sufficiency_report.json")
    citation_registry = load_json(root / "citation_registry.json")
    question_type = (
        review_contract.get("question_type")
        or protocol_inputs.get("question_type")
        or ""
    )
    status = str(review_contract.get("status", "")).strip().lower()
    completed = status in COMPLETED_STATUSES and not args.allow_structure_only
    sparse_ok, sparse_error = sparse_exception(review_contract)

    if not args.allow_structure_only:
        errors.extend(check_review_type_route(review_contract))
        errors.extend(check_search_execution(search_log, completed))
        errors.extend(check_search_freshness(search_log, review_contract, completed))
        search_strategy_text = (root / "search_strategy.md").read_text(encoding="utf-8") if (root / "search_strategy.md").exists() else ""
        errors.extend(check_search_strategy_document(search_strategy_text, completed))
        errors.extend(check_screening_accounting(screening_decisions, completed, sparse_ok))
        if sparse_error:
            errors.append(sparse_error)

    if review_contract.get("delivery_preset") == "full_package" and not args.allow_structure_only:
        missing_full_package = [name for name in FULL_PACKAGE_FILES if not (root / name).exists() or (root / name).stat().st_size == 0]
        if missing_full_package:
            errors.append("full_package is missing required publication artifacts: " + ", ".join(missing_full_package))
        verification_rows = read_csv_rows_if_exists(root / "citation_verification_report.csv")
        if not verification_rows:
            errors.append("full_package requires a non-empty citation_verification_report.csv")
        else:
            unresolved_verification = [
                row.get("doi") or row.get("local_title") or "UNKNOWN"
                for row in verification_rows
                if row.get("verification_status") != "verified"
            ]
            if unresolved_verification:
                errors.append(
                    "full_package contains citations that are not verified: "
                    + ", ".join(unresolved_verification)
                )
            entries = citation_registry.get("entries", [])
            verification_by_id = {row.get("citation_id", ""): row for row in verification_rows if row.get("citation_id")}
            if len(verification_by_id) != len(verification_rows):
                errors.append("citation verification rows must have unique, non-empty citation_id values")
            registered_ids = {str(entry.get("citation_id", "")) for entry in entries if entry.get("citation_id")}
            reported_ids = set(verification_by_id)
            if reported_ids != registered_ids:
                errors.append(
                    "citation verification citation_id set must exactly match citation_registry.json; "
                    f"missing={sorted(registered_ids - reported_ids)}, extra={sorted(reported_ids - registered_ids)}"
                )
            for entry in entries:
                citation_id = str(entry.get("citation_id", ""))
                row = verification_by_id.get(citation_id)
                if not row:
                    errors.append(f"citation verification report does not cover {citation_id}")
                    continue
                expected = {
                    "reference_number": str(entry.get("reference_number", "")),
                    "local_title": str(entry.get("title", "")).strip(),
                    "local_year": str(entry.get("year", "")).strip(),
                }
                for field, expected_value in expected.items():
                    if str(row.get(field, "")).strip() != expected_value:
                        errors.append(f"citation verification identity mismatch for {citation_id}: {field}")
                registered_authors = str(entry.get("authors", "")).strip()
                expected_author = ((registered_authors.split(";")[0].split(",")[0]) if "," in registered_authors.split(";")[0] else registered_authors.split(";")[0].split()[0] if registered_authors else "").strip()
                if str(row.get("local_first_author", "")).strip().lower() != expected_author.lower():
                    errors.append(f"citation verification identity mismatch for {citation_id}: local_first_author")
                registered_doi = str(entry.get("doi", "")).strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
                reported_doi = str(row.get("doi", "")).strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
                if reported_doi != registered_doi:
                    errors.append(f"citation verification identity mismatch for {citation_id}: doi")

        pdf_path = root / "literature_review.pdf"
        current_source_hash = hashlib.sha256((root / "literature_review_synthesis.md").read_bytes()).hexdigest()
        if pdf_path.exists():
            pdf_ok, pdf_metadata = inspect_pdf(pdf_path)
            if not pdf_ok:
                errors.append("literature_review.pdf is not readable as a non-empty PDF document")
            elif f"source_sha256_{current_source_hash}" not in pdf_metadata:
                errors.append("literature_review.pdf does not contain the current source SHA-256 provenance marker")
        docx_path = root / "literature_review.docx"
        if docx_path.exists():
            if not zipfile.is_zipfile(docx_path):
                errors.append("literature_review.docx is not a valid DOCX ZIP package")
            else:
                with zipfile.ZipFile(docx_path) as archive:
                    if "word/document.xml" not in archive.namelist():
                        errors.append("literature_review.docx lacks word/document.xml")
                    core_xml = archive.read("docProps/core.xml").decode("utf-8", errors="replace") if "docProps/core.xml" in archive.namelist() else ""
                    if f"source_sha256:{current_source_hash}" not in core_xml:
                        errors.append("literature_review.docx does not contain the current source SHA-256 provenance marker")
        tex_path = root / "literature_review.tex"
        if tex_path.exists():
            tex_text = tex_path.read_text(encoding="utf-8", errors="replace")
            if "\\documentclass" not in tex_text or "\\begin{document}" not in tex_text:
                errors.append("literature_review.tex is not a complete LaTeX document")
            if f"% source_sha256:{current_source_hash}" not in tex_text:
                errors.append("literature_review.tex does not contain the current source SHA-256 provenance marker")

    if not args.allow_structure_only:
        for field in REVIEW_CONTRACT_FIELDS:
            if field not in review_contract:
                errors.append(f"review_contract.json missing field: {field}")

        if question_type == "treatment_strategy_comparison":
            for field in TREATMENT_STRATEGY_REVIEW_CONTRACT_FIELDS:
                if field not in review_contract:
                    errors.append(f"review_contract.json missing treatment-strategy field: {field}")

        for field in SUFFICIENCY_FIELDS:
            if field not in sufficiency:
                errors.append(f"evidence_sufficiency_report.json missing field: {field}")

        entries = citation_registry.get("entries")
        if not isinstance(entries, list) or not entries:
            errors.append("citation_registry.json must contain a non-empty entries list")
        else:
            required_entry_fields = {
                "citation_id",
                "paper_id",
                "title",
                "narrative_role",
                "claim_supported",
                "supporting_decision_ids",
                "supporting_evidence_row_ids",
                "reference_number",
            }
            for index, entry in enumerate(entries, start=1):
                if not required_entry_fields.issubset(entry):
                    missing_entry_fields = sorted(required_entry_fields - set(entry))
                    errors.append(
                        f"citation_registry.json entry {index} missing fields: "
                        + ", ".join(missing_entry_fields)
                    )
                nonempty_entry_fields = required_entry_fields - {
                    "supporting_decision_ids",
                    "supporting_evidence_row_ids",
                }
                empty_entry_fields = sorted(field for field in nonempty_entry_fields if not entry.get(field))
                if empty_entry_fields:
                    errors.append(
                        f"citation_registry.json entry {index} has empty fields: "
                        + ", ".join(empty_entry_fields)
                    )
                role = str(entry.get("narrative_role", "")).strip()
                if role and role not in ALLOWED_NARRATIVE_ROLES:
                    errors.append(
                        f"citation_registry.json entry {index} has unsupported narrative_role: {role!r}"
                    )

        included_ids = {
            (row.get("paper_id") or "").strip()
            for row in screening_decisions
            if ((row.get("include_in_synthesis") or "").strip().lower() in {"yes", "true", "1"}
                or (row.get("decision") or "").strip().lower() == "include")
            and (row.get("paper_id") or "").strip()
        }
        claim_bearing_ids = {
            (row.get("paper_id") or "").strip()
            for row in fulltext_inventory
            if truthy(row.get("claim_bearing")) and (row.get("paper_id") or "").strip()
        } or included_ids
        design_by_paper = {
            (row.get("paper_id") or "").strip(): (row.get("design") or "").strip()
            for row in study_registry
            if (row.get("paper_id") or "").strip()
        }
        errors.extend(check_quality_appraisal(quality_appraisal, claim_bearing_ids, completed, design_by_paper))
        errors.extend(
            check_depth_and_reference_floor(
                review_contract,
                entries if isinstance(entries, list) else [],
                fulltext_inventory,
                completed,
            )
        )
        errors.extend(check_effect_coverage(study_registry, effect_registry, completed))

        mode = review_contract.get("project_mode")
        if mode not in CANONICAL_PROJECT_MODES:
            errors.append(
                f"review_contract.json project_mode must be canonical; got {mode!r}"
            )
        recommended_mode = sufficiency.get("mode_recommendation")
        if mode == "research" and recommended_mode != "research":
            errors.append(
                "review_contract.json claims research mode but evidence_sufficiency_report.json "
                "does not recommend research"
            )

        if question_type == "treatment_strategy_comparison":
            errors.extend(
                require_columns(
                    screening_decisions,
                    strategy_screening_fields,
                    "screening_decisions.csv",
                    allow_empty=allow_empty,
                )
            )
            errors.extend(
                require_columns(
                    study_registry,
                    strategy_fields,
                    "study_registry.csv",
                    allow_empty=allow_empty,
                )
            )
            if review_contract.get("deliverable_style") == "narrative_review":
                if not claim_registry:
                    errors.append(
                        "claim_registry.csv is required when deliverable_style=narrative_review"
                    )
                if not effect_registry:
                    errors.append(
                        "effect_registry.csv is required when deliverable_style=narrative_review"
                    )
                strict_anchor_rows = [
                    row for row in study_registry
                    if (row.get("synthesis_tier") or "").strip() == "core_direct_strict"
                    and (row.get("anchor_eligible") or "").strip().lower() == "yes"
                ]
                if not strict_anchor_rows:
                    readiness = (review_contract.get("narrative_readiness") or "").strip()
                    if readiness != "suggestive_narrative_broad_support":
                        errors.append(
                            "deliverable_style=narrative_review requires at least one "
                            "core_direct_strict anchor study, or "
                            "narrative_readiness=suggestive_narrative_broad_support"
                        )

                appendix_ids = {
                    row.get("paper_id", "")
                    for row in study_registry
                    if (row.get("synthesis_tier") or "").strip() == "appendix_only"
                }
                primary_claim_rows = [
                    row for row in claim_registry
                    if (row.get("supports_primary_direction_claim") or "").strip().lower() == "yes"
                ]
                if not primary_claim_rows:
                    errors.append(
                        "claim_registry.csv must contain at least one row with "
                        "supports_primary_direction_claim=yes for a narrative review"
                    )
                for row in primary_claim_rows:
                    anchors = {
                        item.strip()
                        for item in (row.get("eligible_anchor_paper_ids") or "").split(",")
                        if item.strip()
                    }
                    if not anchors:
                        errors.append(
                            f"claim_registry.csv claim {row.get('claim_id', 'unknown')} "
                            "has no eligible_anchor_paper_ids"
                        )
                    if anchors & appendix_ids:
                        errors.append(
                            f"claim_registry.csv claim {row.get('claim_id', 'unknown')} "
                            "uses appendix_only studies as eligible anchors"
                        )
                    if not row.get("outcome_family", "").strip():
                        errors.append(
                            f"claim_registry.csv claim {row.get('claim_id', 'unknown')} "
                            "is missing outcome_family"
                        )
                for row in effect_registry:
                    if not row.get("outcome_family", "").strip():
                        errors.append(
                            "effect_registry.csv is missing outcome_family values for one or more rows"
                        )
                    if (
                        row.get("supports_primary_direction_claim", "").strip().lower() == "yes"
                        and not row.get("effect_directness", "").strip()
                    ):
                        errors.append(
                            "effect_registry.csv primary-claim rows must specify effect_directness"
                        )

        if question_type in {"treatment_strategy_comparison", "exposure_outcome_association", "prognosis"}:
            if not effect_registry:
                errors.append(f"effect_registry.csv is required for completed {question_type} reviews")
        if not claim_registry:
            errors.append("claim_registry.csv is required for every completed review")
        if question_type in {"treatment_strategy_comparison", "exposure_outcome_association"} and not bias_registry:
            errors.append(f"bias_registry.csv is required for completed {question_type} reviews")

    # ---- Enum consistency checks ----
    if bias_registry:
        errors.extend(
            require_columns(
                bias_registry,
                ["paper_id", "bias_domain", "severity", "bias_direction", "evidence_of_bias"],
                "bias_registry.csv",
                allow_empty=allow_empty,
            )
        )
        errors.extend(
            check_enum_values(bias_registry, "severity", BIAS_SEVERITY_VALUES, "bias_registry.csv")
        )
        errors.extend(
            check_enum_values(
                bias_registry, "bias_direction", BIAS_DIRECTION_VALUES, "bias_registry.csv"
            )
        )
    if claim_registry:
        errors.extend(
            check_enum_values(claim_registry, "allowed_strength", ALLOWED_STRENGTH_VALUES, "claim_registry.csv")
        )
        errors.extend(
            check_enum_values(claim_registry, "evidence_direction", EVIDENCE_DIRECTION_VALUES, "claim_registry.csv")
        )

    # Scored candidates (optional file)
    scored_path = root / "scored_candidates.csv"
    if scored_path.exists():
        scored = read_csv_rows(scored_path)
        if scored:
            errors.extend(check_enum_values(scored, "study_credibility", STUDY_CREDIBILITY_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "effect_trustworthiness", EFFECT_TRUSTWORTHINESS_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "likely_directness", LIKELY_DIRECTNESS_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "decision_role", DECISION_ROLE_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "claim_strength_ceiling", ALLOWED_STRENGTH_VALUES, "scored_candidates.csv"))

    # Claim–evidence binding check
    if claim_registry and effect_registry:
        errors.extend(
            check_claim_evidence_binding(claim_registry, effect_registry, "claim_registry.csv")
        )
        # Claim direction consistency: claim.evidence_direction vs effect_registry.direction
        errors.extend(check_direction_consistency(claim_registry, effect_registry))

    rounds_present = {row.get("search_round", "").strip() for row in search_log if row.get("search_round", "").strip()}
    review_md_exists = (root / "literature_review_synthesis.md").exists()
    validate_publication_bundle(root, warnings, errors)
    if review_md_exists and not args.allow_structure_only:
        if len(rounds_present) < 2:
            errors.append(
                "search_log.csv should document at least two search rounds for a completed review "
                "(initial mapping plus reading-driven expansion)"
            )

        search_sources = {row.get("source", "").strip() for row in search_log if row.get("source", "").strip()}
        # Only require free-access sources; subscription sources are expected to be absent when blocked
        missing_free_sources = [s for s in REQUIRED_FREE_SOURCES if s not in search_sources]
        if missing_free_sources:
            errors.append(
                "search_log.csv is missing free-access core sources for a completed review: "
                + ", ".join(missing_free_sources)
                + ". Add entries with status=blocked_auth_required if access is unavailable."
            )

    review_md = root / "literature_review_synthesis.md"
    if review_md_exists and not args.allow_structure_only:
        text = load_text(review_md)
        wc = max(body_word_count(text), rough_body_word_count(text))
        delivery_preset = str(review_contract.get("delivery_preset", "decision_grade"))
        mature_floor = 4500 if completed and delivery_preset in {"decision_grade", "full_package"} and not sparse_ok else 1500
        required_words = max(args.min_body_words, mature_floor)
        if wc < required_words:
            errors.append(
                f"literature_review_synthesis.md body too short: {wc} words "
                f"(minimum {required_words} for this release profile)"
            )
        citation_entries = citation_registry.get("entries", [])
        if delivery_preset in {"decision_grade", "full_package"} and len(citation_entries) < 3:
            errors.append(
                f"{delivery_preset} requires at least 3 independently registered sources; "
                f"found {len(citation_entries)}. Downgrade the deliverable or retrieve a broader evidence base."
            )
        ngram_score = fivegram_uniqueness(text)
        if ngram_score < 0.55:
            errors.append(
                f"literature_review_synthesis.md has low five-word sequence diversity ({ngram_score:.3f}); "
                "length appears to come from templated repetition rather than new evidence or interpretation"
            )
        similar_pairs = high_similarity_paragraph_pairs(text)
        if len(similar_pairs) >= 3:
            errors.append(
                "literature_review_synthesis.md contains too many highly similar substantive paragraphs: "
                + ", ".join(f"{left}-{right} ({score:.2f})" for left, right, score in similar_pairs[:6])
            )
        if not check_inline_screening_numbers(text):
            errors.append(
                "literature_review_synthesis.md must contain explicit inline screening numbers "
                "in the Search and Screening section"
            )
        errors.extend(
            reconcile_screening_counts(
                text,
                candidate_records_raw,
                candidate_records_dedup,
                screening_decisions,
            )
        )
        if completed and delivery_preset in {"decision_grade", "full_package"}:
            errors.extend(check_embedded_evidence_tables(text))
        if completed and re.search(r"\b(?:TODO|TBD|FILL IN)\b|\{\{[^}]+\}\}", text, re.IGNORECASE):
            errors.append("literature_review_synthesis.md contains unresolved placeholder text")
        errors.extend(
            check_referential_integrity(
                review_contract,
                citation_registry,
                study_registry,
                claim_registry,
                effect_registry,
                evidence_table,
                text,
            )
        )
        prohibited = check_prohibited_in_body(text, PROHIBITED_BODY_PHRASES)
        if prohibited:
            errors.append(
                "literature_review_synthesis.md contains prohibited body phrases: "
                + ", ".join(prohibited)
            )
        meta_language = check_meta_language(text, META_LANGUAGE_PATTERNS)
        if meta_language:
            errors.append(
                "literature_review_synthesis.md contains workflow/package meta language: "
                + ", ".join(meta_language)
            )

        # Overclaim check: warning level only.
        # See OVERCLAIM_WARNING_PHRASES for rationale on why these are warnings, not failures.
        overclaims = check_overclaim_phrases(text, OVERCLAIM_WARNING_PHRASES)
        if overclaims:
            warnings.append(
                "literature_review_synthesis.md contains potential overclaim phrases "
                "(verify each against claim_registry.csv allowed_strength): "
                + ", ".join(f'"{p.strip()}"' for p in overclaims)
            )
        listy_lines = detect_listy_profile_lines(text)
        if listy_lines >= 6:
            warnings.append(
                "literature_review_synthesis.md still contains many one-paper-one-sentence "
                f"evidence-profile lines ({listy_lines} detected); prefer thematic synthesis."
            )

        # Methods completeness check
        missing_methods = check_methods_completeness(text)
        if missing_methods:
            warnings.append(
                "literature_review_synthesis.md Search and Screening section may be missing: "
                + ", ".join(missing_methods)
            )

        # Repeated sentence opener check (template-prose signal)
        repeated_openers = check_repeated_sentence_patterns(text)
        if repeated_openers:
            errors.extend(repeated_openers)

        # Section composition check
        warnings.extend(check_section_composition(text))

    elif not args.allow_structure_only:
        errors.append(
            "literature_review_synthesis.md is missing; rerun with --allow-structure-only "
            "only if you are validating an unfinished scaffold"
        )

    if warnings:
        print("WARNINGS (not failures — review before finalising):")
        for w in warnings:
            print(f"  ⚠  {w}")

    if completed and not args.allow_structure_only:
        errors.extend(validate_semantics(root))

    if errors:
        raise SystemExit("\n".join(errors))

    print("Review package validated.")
    return 0


COMMANDS = {
    "validate_review_semantics": main_validate_review_semantics,
    "validate_review_package": main_validate_review_package,
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
