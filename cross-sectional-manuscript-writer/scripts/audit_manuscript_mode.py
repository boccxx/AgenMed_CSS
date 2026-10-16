#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MODE_RULES = {
    "research": {
        "must_contain": [],
        "must_not_contain": [
            "synthetic dataset",
            "synthetic validation",
            "workflow validation",
            "validate the workflow",
            "applied-methods",
        ],
    },
    "applied_methods": {
        "must_contain": ["synthetic", "validation"],
        "must_not_contain": ["empirical evidence", "population evidence without qualification"],
    },
    "workflow_methods": {
        "must_contain": ["workflow", "validation"],
        "must_not_contain": [],
    },
}


def extract_section(text: str, section_name: str) -> str:
    pattern = re.compile(
        r"^(#{1,4})\s+(?:\d+(?:\.\d+)*\s+)?"
        + re.escape(section_name.strip())
        + r"\s*$",
        re.IGNORECASE,
    )
    lines = text.splitlines()
    matches = [
        (index, len(match.group(1)))
        for index, line in enumerate(lines)
        if (match := pattern.match(line))
    ]
    if not matches:
        return ""
    level = min(item[1] for item in matches)
    start = next(item[0] for item in matches if item[1] == level)
    body = [lines[start]]
    for line in lines[start + 1:]:
        heading = re.match(r"^(#{1,4})\s+", line)
        if heading and len(heading.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def _paragraphs(section: str) -> list[str]:
    lines = section.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    return [part.strip() for part in "\n".join(lines).split("\n\n") if part.strip()]


def check_applied_methods_disclosure_exact(text: str, tokens: list[str]) -> list[str]:
    violations: list[str] = []
    abstract = extract_section(text, "Abstract")
    abstract_methods = extract_section(abstract, "Methods") if abstract else ""
    limitations = extract_section(text, "Limitations")
    if not abstract_methods:
        return ["Abstract Methods subsection is missing"]
    if not limitations:
        return ["Limitations subsection is missing"]

    abstract_parts = _paragraphs(abstract_methods)
    limitation_parts = _paragraphs(limitations)
    abstract_body = " ".join(abstract_parts)
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?。！？])\s+", abstract_body)
        if item.strip()
    ]
    final_sentence = sentences[-1] if sentences else abstract_body
    first_limitation = limitation_parts[0] if limitation_parts else ""
    allowed = f"{final_sentence}\n{first_limitation}"

    for token in tokens:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", re.IGNORECASE)
        if not pattern.search(final_sentence):
            violations.append(f"'{token}' missing from the final sentence of Abstract Methods")
        if not pattern.search(first_limitation):
            violations.append(f"'{token}' missing from the first Limitations paragraph")
        if len(pattern.findall(text)) != len(pattern.findall(allowed)):
            violations.append(f"'{token}' appears outside the two permitted disclosure locations")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit manuscript text against its manuscript mode.")
    parser.add_argument("manuscript_contract_json")
    parser.add_argument("manuscript_markdown")
    args = parser.parse_args()

    contract = json.loads(Path(args.manuscript_contract_json).read_text(encoding="utf-8"))
    text = Path(args.manuscript_markdown).read_text(encoding="utf-8").lower()
    mode = contract["manuscript_mode"]
    rules = MODE_RULES[mode]

    if mode == "applied_methods":
        violations = check_applied_methods_disclosure_exact(
            Path(args.manuscript_markdown).read_text(encoding="utf-8"),
            ["synthetic", "validation"],
        )
        if violations:
            raise SystemExit("applied_methods disclosure violation: " + "; ".join(violations))

    missing = [token for token in rules["must_contain"] if token not in text]
    if missing:
        raise SystemExit(f"manuscript missing required mode markers: {', '.join(missing)}")

    forbidden = [token for token in rules["must_not_contain"] if token in text]
    if forbidden:
        raise SystemExit(f"manuscript contains forbidden mode markers: {', '.join(forbidden)}")

    print("Manuscript mode audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
