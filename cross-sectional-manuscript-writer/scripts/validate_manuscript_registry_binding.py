#!/usr/bin/env python3
"""Validate manuscript claims against allowed frozen registry objects."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def number_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text))


def numeric_forms(value) -> set[str]:
    if value in {None, ""}:
        return set()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return set()
    forms = {str(value), f"{number:g}", f"{number:.2f}", f"{number:.3f}", f"{number:.4f}"}
    return {item.rstrip("0").rstrip(".") if "." in item else item for item in forms}


def manuscript_body_without_references(text: str) -> str:
    """Return all claim-bearing manuscript text before the references section."""
    return re.split(r"^#\s+References\s*$", text, maxsplit=1, flags=re.M | re.I)[0]


def repeated_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if len(part.split()) >= 30]
    counts: dict[str, int] = {}
    examples: dict[str, str] = {}
    for paragraph in paragraphs:
        normalized = re.sub(r"\d+", "#", paragraph.lower())
        normalized = re.sub(r"[^a-z#\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        counts[normalized] = counts.get(normalized, 0) + 1
        examples[normalized] = paragraph[:120]
    return [f"{examples[key]}... x{count}" for key, count in counts.items() if count >= 3]


def repeated_sentences(text: str) -> list[str]:
    counts: dict[str, int] = {}
    examples: dict[str, str] = {}
    prose = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for sentence in re.split(r"(?<=[.!?])\s+", prose):
        sentence = sentence.strip()
        if len(sentence.split()) < 12:
            continue
        normalized = re.sub(r"\d+", "#", sentence.lower())
        normalized = re.sub(r"[^a-z#\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        counts[normalized] = counts.get(normalized, 0) + 1
        examples[normalized] = sentence[:140]
    return [f"{examples[key]}... x{count}" for key, count in counts.items() if count >= 3]


def fivegram_uniqueness(text: str) -> float:
    body = manuscript_body_without_references(text)
    tokens = re.findall(r"[a-z]{3,}", re.sub(r"\d+", "#", body.lower()))
    grams = [tuple(tokens[index:index + 5]) for index in range(max(0, len(tokens) - 4))]
    return len(set(grams)) / len(grams) if grams else 1.0


def high_similarity_paragraph_pairs(text: str, threshold: float = 0.82) -> list[tuple[int, int, float]]:
    body = manuscript_body_without_references(text)
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


def top_level_section(text: str, heading: str) -> str:
    match = re.search(
        rf"^#\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^#\s+|\Z)",
        text,
        flags=re.M | re.I,
    )
    return match.group(1) if match else ""


def complete_main_body_word_count(text: str) -> int:
    return sum(
        len(re.findall(r"[A-Za-z][A-Za-z'-]*", top_level_section(text, section)))
        for section in ("Introduction", "Methods", "Results", "Discussion")
    )


def recursive_values(payload, key_names: set[str]) -> list:
    values: list = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in key_names:
                values.append(value)
            values.extend(recursive_values(value, key_names))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(recursive_values(value, key_names))
    return values


def source_payload(contract: dict, root: Path, name: str):
    item = contract.get("source_inputs", {}).get(name, {})
    path = Path(str(item.get("path", ""))) if isinstance(item, dict) else Path("")
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def citation_numbers_in_text(text: str) -> set[int]:
    numbers: set[int] = set()
    for raw in re.findall(r"\[(\d+(?:[-,]\d+)*)\]", text):
        for component in raw.split(","):
            if "-" in component:
                start, end = map(int, component.split("-", 1))
                if start <= end:
                    numbers.update(range(start, end + 1))
            else:
                numbers.add(int(component))
    return numbers


def validate_block_binding_format(
    *,
    contract: dict,
    manuscript: str,
    binding: dict,
    results: list[dict],
    tables: list[dict],
    figures: list[dict],
    citations: list[dict],
    allowed: dict[str, set[str]],
    root: Path,
) -> list[str]:
    """Validate the block-oriented binding map emitted by real-data manuscripts.

    The legacy sentence-oriented map can bind numbers only to result objects. Real
    manuscripts also report participant flow, descriptive table cells, diagnostics,
    and executed-method constants. This format requires every numeric or citation-
    bearing block to resolve to a registered result/table/figure/citation or an
    explicit source key, while leaving the legacy path unchanged.
    """
    errors: list[str] = []
    indexes = {
        "result": {row.get("result_id"): row for row in results},
        "table": {row.get("table_id"): row for row in tables},
        "figure": {row.get("figure_id"): row for row in figures},
        "citation": {row.get("citation_id"): row for row in citations},
    }
    for kind in allowed:
        dangling = allowed[kind] - set(indexes[kind])
        if dangling:
            errors.append(f"allowed_{kind}_ids contain unknown IDs: {sorted(dangling)}")

    number_to_citation: dict[int, str] = {}
    duplicate_numbers: dict[int, list[str]] = {}
    for row in citations:
        citation_id = row.get("citation_id")
        try:
            number = int(row.get("reference_number"))
            if number < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"citation {citation_id!r} lacks a positive integer reference_number")
            continue
        if number in number_to_citation:
            duplicate_numbers.setdefault(number, [number_to_citation[number]]).append(citation_id)
        else:
            number_to_citation[number] = citation_id
    if duplicate_numbers:
        errors.append(f"citation registry contains duplicate reference_number values: {duplicate_numbers}")

    covered_blocks: list[str] = []
    for item in binding.get("bindings", []):
        binding_id = str(item.get("binding_id", ""))
        claim = str(item.get("claim_text", "")).strip()
        if not claim or claim not in manuscript:
            errors.append(f"{binding_id or 'binding'} claim block is absent from manuscript")
            continue
        ids_by_kind = {
            "result": item.get("result_ids", []),
            "table": item.get("table_ids", []),
            "figure": item.get("figure_ids", []),
            "citation": item.get("citation_ids", []),
        }
        for kind, ids in ids_by_kind.items():
            invalid = set(ids) - allowed[kind]
            if invalid:
                errors.append(f"{binding_id} uses disallowed/unknown {kind} IDs: {sorted(invalid)}")

        sources = [str(value) for value in item.get("source_keys", []) if str(value)]
        has_binding = bool(sources or any(ids_by_kind.values()))
        if re.search(r"\d", claim) and not has_binding:
            errors.append(f"numeric claim block has no registered artifact or source binding: {binding_id}")

        marker_numbers = citation_numbers_in_text(claim)
        linked_numbers = {
            number
            for number, citation_id in number_to_citation.items()
            if citation_id in set(ids_by_kind["citation"])
        }
        if marker_numbers and marker_numbers != linked_numbers:
            errors.append(
                f"{binding_id} citation markers do not match linked citation IDs: "
                f"markers={sorted(marker_numbers)}, linked={sorted(linked_numbers)}"
            )
        if ids_by_kind["citation"] and not marker_numbers:
            errors.append(f"{binding_id} links citations but contains no publication reference marker")
        covered_blocks.append(claim)

    body = manuscript_body_without_references(manuscript)
    body = re.sub(r"\A---\n.*?\n---\n", "", body, flags=re.S)
    for block in [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]:
        if block.startswith("#") or block.startswith("**Keywords"):
            continue
        if re.search(r"\d", block) and not any(block in claim for claim in covered_blocks):
            errors.append(f"manuscript body contains an unbound numeric block: {block[:140]!r}")
    unknown_reference_numbers = citation_numbers_in_text(body) - set(number_to_citation)
    if unknown_reference_numbers:
        errors.append(f"manuscript uses unregistered reference numbers: {sorted(unknown_reference_numbers)}")

    references_match = re.search(r"^#\s+References\s*$([\s\S]*)", manuscript, re.M | re.I)
    references_text = references_match.group(1) if references_match else ""
    for citation_id in allowed["citation"]:
        row = indexes["citation"].get(citation_id, {})
        try:
            number = int(row.get("reference_number"))
        except (TypeError, ValueError):
            continue
        reference_match = re.search(rf"^\s*{number}\.\s+(.+)$", references_text, re.M)
        if not reference_match:
            errors.append(f"References section lacks numbered entry {number} for citation {citation_id}")
            continue
        title = str(row.get("title", "")).strip()
        normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        normalized_reference = re.sub(r"[^a-z0-9]+", " ", reference_match.group(1).lower()).strip()
        if not normalized_title or normalized_title not in normalized_reference:
            errors.append(f"reference {number} does not match the registered title for citation {citation_id}")

    duplicates = repeated_paragraphs(manuscript)
    if duplicates:
        errors.append("manuscript contains repeated filler paragraphs: " + "; ".join(duplicates[:3]))
    sentence_duplicates = repeated_sentences(manuscript)
    if sentence_duplicates:
        errors.append("manuscript contains repeated filler sentences: " + "; ".join(sentence_duplicates[:3]))
    if fivegram_uniqueness(manuscript) < 0.60:
        errors.append("manuscript has low five-word sequence diversity")
    similar_pairs = high_similarity_paragraph_pairs(manuscript)
    if len(similar_pairs) >= 3:
        errors.append("manuscript contains too many highly similar substantive paragraphs")

    mode = str(contract.get("manuscript_mode", ""))
    minimums = {
        "Abstract": 220,
        "Introduction": 450,
        "Methods": 1100,
        "Results": 900,
        "Discussion": 900,
    } if mode in {"research", "applied_methods"} else {
        "Abstract": 120,
        "Introduction": 350,
        "Methods": 650,
        "Results": 300,
        "Discussion": 550,
    }
    for section, minimum in minimums.items():
        count = len(re.findall(r"[A-Za-z][A-Za-z'-]*", top_level_section(manuscript, section)))
        if count < minimum:
            errors.append(f"manuscript section {section!r} is underdeveloped: {count} words (minimum {minimum})")
    if mode in {"research", "applied_methods"}:
        main_body_words = complete_main_body_word_count(manuscript)
        if main_body_words < 4000:
            errors.append(f"complete manuscript main body is too short: {main_body_words} words (minimum 4000)")
        if len(allowed["citation"]) < 25:
            errors.append(
                f"complete manuscript has too few verified allowed references: {len(allowed['citation'])} (minimum 25)"
            )
        reference_entries = re.findall(r"^\s*\d+\.\s+.+$", references_text, re.M)
        if len(reference_entries) < 25:
            errors.append(f"References section is too thin: {len(reference_entries)} entries (minimum 25)")
        display_calls = set(re.findall(r"\b(?:Table|Figure)\s+\d+[A-Za-z]?\b", body, re.I))
        if len(display_calls) < 3:
            errors.append(f"manuscript body cites too few main-text displays: {len(display_calls)} (minimum 3)")

    analysis_core = source_payload(contract, root, "analysis_core_contract.json")
    if isinstance(analysis_core, dict):
        adjustment_sets = recursive_values(analysis_core, {"primary_adjustment_set"})
        explicitly_empty_adjustment = bool(adjustment_sets) and all(value in (None, "", [], {}) for value in adjustment_sets)
        if explicitly_empty_adjustment and re.search(
            r"\b(adjusted association|adjusted estimate|after adjustment|controlled for confounding)\b", body, re.I
        ):
            errors.append("manuscript claims adjustment although the executed primary adjustment set is empty")
    return errors


def validate(contract_path: Path, manuscript_path: Path) -> list[str]:
    contract = read_json(contract_path)
    manuscript = manuscript_path.read_text(encoding="utf-8")
    root = contract_path.parent.parent
    binding_path = Path(str(contract.get("binding_map", "")))
    if not binding_path.is_absolute():
        binding_path = root / binding_path
    if not binding_path.exists():
        return [f"binding map not found: {binding_path}"]
    binding = read_json(binding_path)
    results = read_json(root / "registries" / "result_registry.json")
    tables = read_json(root / "registries" / "table_registry.json")
    figures = read_json(root / "registries" / "figure_registry.json")
    citations = read_json(root / "literature_review" / "citation_registry.json").get("entries", [])
    indexes = {
        "result": {row.get("result_id"): row for row in results},
        "table": {row.get("table_id"): row for row in tables},
        "figure": {row.get("figure_id"): row for row in figures},
        "citation": {row.get("citation_id"): row for row in citations},
    }
    allowed = {
        "result": set(contract.get("allowed_result_ids", [])),
        "table": set(contract.get("allowed_table_ids", [])),
        "figure": set(contract.get("allowed_figure_ids", [])),
        "citation": set(contract.get("allowed_citation_ids", [])),
    }
    if isinstance(binding.get("bindings"), list):
        return validate_block_binding_format(
            contract=contract,
            manuscript=manuscript,
            binding=binding,
            results=results,
            tables=tables,
            figures=figures,
            citations=citations,
            allowed=allowed,
            root=root,
        )
    errors: list[str] = []
    mode = str(contract.get("manuscript_mode", ""))
    for kind in allowed:
        dangling = allowed[kind] - set(indexes[kind])
        if dangling:
            errors.append(f"allowed_{kind}_ids contain unknown IDs: {sorted(dangling)}")
    citation_numbers: dict[str, int] = {}
    number_owners: dict[int, list[str]] = {}
    for citation_id, entry in indexes["citation"].items():
        raw_number = entry.get("reference_number")
        try:
            reference_number = int(raw_number)
            if reference_number < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"citation {citation_id!r} lacks a positive integer reference_number")
            continue
        citation_numbers[citation_id] = reference_number
        number_owners.setdefault(reference_number, []).append(citation_id)
    duplicate_numbers = {number: ids for number, ids in number_owners.items() if len(ids) > 1}
    if duplicate_numbers:
        errors.append(f"citation registry contains duplicate reference_number values: {duplicate_numbers}")

    covered_numeric_claims: list[str] = []
    for item in binding.get("numeric_claims", []):
        claim = str(item.get("claim_text", "")).strip()
        ids = item.get("result_ids", [])
        if not claim or claim not in manuscript:
            errors.append(f"numeric binding claim is absent from manuscript: {claim!r}")
            continue
        if manuscript.count(claim) != 1:
            errors.append(f"numeric binding claim must occur exactly once in manuscript: {claim!r}")
        if not ids:
            errors.append(f"numeric claim has no result_ids: {claim!r}")
            continue
        invalid = set(ids) - allowed["result"]
        if invalid:
            errors.append(f"numeric claim uses disallowed/unknown result IDs: {sorted(invalid)}")
            continue
        permitted_numbers = {"95"}
        for result_id in ids:
            result = indexes["result"].get(result_id, {})
            for field in ("estimate", "ci_lower", "ci_upper", "p_value"):
                permitted_numbers.update(numeric_forms(result.get(field)))
        invented = number_tokens(claim) - permitted_numbers
        if invented:
            errors.append(f"numeric claim contains values absent from linked results: {sorted(invented)}")
        covered_numeric_claims.append(claim)

    citation_claims = binding.get("citation_claims", [])
    if allowed["citation"] and not citation_claims:
        errors.append("binding map must contain citation_claims when citations are allowed")
    covered_citation_markers: list[str] = []
    valid_citation_bindings: list[tuple[str, str]] = []
    for item in citation_claims:
        claim = str(item.get("claim_text", "")).strip()
        marker = str(item.get("marker_text", "")).strip()
        ids = item.get("citation_ids", [])
        if not claim or claim not in manuscript:
            errors.append(f"citation binding claim is absent from manuscript: {claim!r}")
        elif manuscript.count(claim) != 1:
            errors.append(f"citation binding claim must occur exactly once in manuscript: {claim!r}")
        invalid = set(ids) - allowed["citation"]
        if not ids or invalid:
            errors.append(f"citation claim uses missing/disallowed citation IDs: {sorted(invalid)}")
        paragraph = next((part for part in manuscript.split("\n\n") if claim and claim in part), "")
        linked_numbers = [citation_numbers.get(citation_id) for citation_id in ids]
        expected_marker = "[" + ",".join(str(number) for number in linked_numbers if number is not None) + "]"
        if not marker or marker not in paragraph:
            errors.append(f"citation claim lacks its declared inline marker in the same paragraph: {claim!r}")
        elif not re.fullmatch(r"\[\d+(?:,\d+)*\]", marker):
            errors.append(f"citation marker must be a compact numeric reference marker such as [1] or [1,2]: {marker!r}")
        elif any(number is None for number in linked_numbers) or marker != expected_marker:
            errors.append(
                f"citation marker must be derived exactly from linked citation reference numbers: expected={expected_marker!r}, got={marker!r}"
            )
        else:
            covered_citation_markers.append(marker)
            valid_citation_bindings.append((claim, marker))

    body = manuscript_body_without_references(manuscript)
    visible_ids = set(re.findall(r"\[((?:CIT|P)[A-Za-z0-9_.-]+)\]", body))
    if visible_ids:
        errors.append(f"manuscript exposes internal citation IDs instead of publication markers: {sorted(visible_ids)}")
    for sentence in re.findall(r"[^.!?\n]+[.!?]?", body):
        if not re.search(r"\[\d+(?:,\d+)*\]", sentence):
            continue
        exact_match = False
        for claim, marker in valid_citation_bindings:
            if marker not in sentence:
                continue
            prose = sentence.replace(marker, "").strip().rstrip(".!?").strip()
            expected = claim.strip().rstrip(".!?").strip()
            if prose == expected:
                exact_match = True
                break
        if not exact_match:
            errors.append(f"citation-bearing sentence is absent from the binding map: {sentence.strip()!r}")

    references_match = re.search(r"^#\s+References\s*$([\s\S]*)", manuscript, re.M | re.I)
    references_text = references_match.group(1) if references_match else ""
    for citation_id in allowed["citation"]:
        number = citation_numbers.get(citation_id)
        if number is None:
            continue
        reference_match = re.search(rf"^\s*{number}\.\s+(.+)$", references_text, re.M)
        if not reference_match:
            errors.append(f"References section lacks numbered entry {number} for citation {citation_id}")
            continue
        title = str(indexes["citation"].get(citation_id, {}).get("title", "")).strip()
        normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        normalized_reference = re.sub(r"[^a-z0-9]+", " ", reference_match.group(1).lower()).strip()
        if not normalized_title or normalized_title not in normalized_reference:
            errors.append(f"reference {number} does not match the registered title for citation {citation_id}")
        entry = indexes["citation"].get(citation_id, {})
        authors = str(entry.get("authors", "")).strip()
        if authors:
            first_author = authors.split(";")[0].strip()
            surname = (first_author.split(",")[0] if "," in first_author else first_author.split()[0]).lower()
            if surname and surname not in normalized_reference.split():
                errors.append(f"reference {number} does not match the registered first author for citation {citation_id}")
        year = str(entry.get("year", "")).strip()
        if year and not re.search(rf"\b{re.escape(year)}\b", reference_match.group(1)):
            errors.append(f"reference {number} does not match the registered year for citation {citation_id}")
        doi = str(entry.get("doi", "")).strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
        if doi and doi not in reference_match.group(1).lower():
            errors.append(f"reference {number} does not match the registered DOI for citation {citation_id}")

    uncovered = body
    for claim in covered_numeric_claims:
        uncovered = uncovered.replace(claim, "")
    for marker in covered_citation_markers:
        uncovered = uncovered.replace(marker, "")
    unexplained = number_tokens(uncovered) - {"95"}
    if unexplained:
        errors.append(f"manuscript body contains unbound numeric values: {sorted(unexplained)}")

    duplicates = repeated_paragraphs(manuscript)
    if duplicates:
        errors.append("manuscript contains repeated filler paragraphs: " + "; ".join(duplicates[:3]))
    sentence_duplicates = repeated_sentences(manuscript)
    if sentence_duplicates:
        errors.append("manuscript contains repeated filler sentences: " + "; ".join(sentence_duplicates[:3]))
    ngram_score = fivegram_uniqueness(manuscript)
    if ngram_score < 0.60:
        errors.append(
            f"manuscript has low five-word sequence diversity ({ngram_score:.3f}); "
            "word count appears to be inflated by templated prose"
        )
    similar_pairs = high_similarity_paragraph_pairs(manuscript)
    if len(similar_pairs) >= 3:
        errors.append(
            "manuscript contains too many highly similar substantive paragraphs: "
            + ", ".join(f"{left}-{right} ({score:.2f})" for left, right, score in similar_pairs[:6])
        )
    section_minimums = (
        {
            "Abstract": 220,
            "Introduction": 450,
            "Methods": 1100,
            "Results": 900,
            "Discussion": 900,
        }
        if mode in {"research", "applied_methods"}
        else {"Abstract": 120, "Introduction": 350, "Methods": 650, "Results": 300, "Discussion": 550}
    )
    for section, minimum in section_minimums.items():
        section_words = len(re.findall(r"[A-Za-z][A-Za-z'-]*", top_level_section(manuscript, section)))
        if section_words < minimum:
            errors.append(f"manuscript section {section!r} is underdeveloped: {section_words} words (minimum {minimum})")

    if mode in {"research", "applied_methods"}:
        main_body_words = complete_main_body_word_count(manuscript)
        if main_body_words < 4000:
            errors.append(f"complete manuscript main body is too short: {main_body_words} words (minimum 4000)")
        if len(allowed["citation"]) < 25:
            errors.append(
                f"complete manuscript has too few verified allowed references: {len(allowed['citation'])} (minimum 25)"
            )
        reference_entries = re.findall(r"^\s*\d+\.\s+.+$", references_text, re.M)
        if len(reference_entries) < 25:
            errors.append(f"References section is too thin: {len(reference_entries)} entries (minimum 25)")

        main_table_ids = {
            row.get("table_id") for row in tables
            if row.get("registry_role", "main_text") == "main_text" and row.get("table_id") in allowed["table"]
        }
        main_figure_ids = {
            row.get("figure_id") for row in figures
            if row.get("registry_role", "main_text") == "main_text" and row.get("figure_id") in allowed["figure"]
        }
        if len(main_table_ids | main_figure_ids) < 3:
            errors.append(
                "complete manuscript requires at least three allowed main-text tables/figures "
                f"(found {len(main_table_ids | main_figure_ids)})"
            )
        display_calls = set(re.findall(r"\b(?:Table|Figure)\s+\d+[A-Za-z]?\b", body, re.I))
        if len(display_calls) < 3:
            errors.append(f"manuscript body cites too few main-text displays: {len(display_calls)} (minimum 3)")

    analysis_core = source_payload(contract, root, "analysis_core_contract.json")
    if isinstance(analysis_core, dict):
        adjustment_sets = recursive_values(analysis_core, {"primary_adjustment_set"})
        explicitly_empty_adjustment = bool(adjustment_sets) and all(
            value in (None, "", [], {}) for value in adjustment_sets
        )
        if explicitly_empty_adjustment and re.search(
            r"\b(adjusted association|adjusted estimate|after adjustment|controlled for confounding)\b",
            body,
            re.I,
        ):
            errors.append("manuscript claims adjustment although the executed primary adjustment set is empty")

        design_modes = [str(value).lower() for value in recursive_values(analysis_core, {"design_mode"})]
        weights = recursive_values(analysis_core, {"weight", "weight_variable", "sampling_weight"})
        has_weight = any(value not in (None, "", [], {}) for value in weights)
        if design_modes and all(value in {"sample", "simple", "unweighted"} for value in design_modes) and not has_weight:
            if re.search(r"\bweighted\b", top_level_section(manuscript, "Results"), re.I):
                errors.append("Results claim weighted analysis although the executed design is unweighted sample mode")

        serialized_core = json.dumps(analysis_core, ensure_ascii=False).lower()
        demonstration_core = any(token in serialized_core for token in ('"synthetic"', '"toy"', '"demo"', '"smoke'))
        if mode == "research" and demonstration_core:
            errors.append("research manuscript is bound to synthetic/toy/demo analysis inputs")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate numeric and citation bindings in a manuscript.")
    parser.add_argument("manuscript_contract_json")
    parser.add_argument("manuscript_markdown")
    args = parser.parse_args()
    errors = validate(Path(args.manuscript_contract_json), Path(args.manuscript_markdown))
    if errors:
        raise SystemExit("Manuscript registry binding failed:\n" + "\n".join(errors))
    print("Manuscript registry binding passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
