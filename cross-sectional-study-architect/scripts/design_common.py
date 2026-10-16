#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import re
from datetime import date
from pathlib import Path

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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bound_execution_spec(intake: dict, intake_path: Path) -> tuple[dict, Path]:
    binding = intake.get("execution_spec", {})
    raw_path = str(binding.get("path", "")).strip()
    expected = str(binding.get("sha256", "")).strip().lower()
    if not raw_path or not expected:
        raise SystemExit("Research release requires execution_spec.path and execution_spec.sha256.")
    path = (intake_path.parent / raw_path).resolve()
    if not path.exists():
        raise SystemExit(f"Execution specification not found: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"Execution specification hash mismatch: expected {expected}, got {actual}")
    spec = load_json(path)
    if not str(spec.get("spec_id", "")).strip() or not str(spec.get("version", "")).strip():
        raise SystemExit("Execution specification lacks spec_id/version.")
    for asset in spec.get("bound_assets", []):
        asset_path = (path.parent / str(asset.get("path", ""))).resolve()
        if not asset_path.exists():
            raise SystemExit(f"Bound execution asset not found: {asset_path}")
        asset_actual = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if asset_actual != str(asset.get("sha256", "")).lower():
            raise SystemExit(f"Bound execution asset hash mismatch: {asset_path}")
    return spec, path


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def today_iso() -> str:
    return date.today().isoformat()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("_", " ").replace("-", " ")).strip()


def contains_token(text: str, token: str) -> bool:
    return normalize(token) in normalize(text)


def front_matter(title: str, subtitle: str | None = None) -> list[str]:
    lines = [
        "---",
        f'title: "{title}"',
    ]
    if subtitle:
        lines.append(f'subtitle: "{subtitle}"')
    lines.extend(
        [
            "geometry: margin=2.5cm",
            "fontsize: 11pt",
            'mainfont: "Times New Roman"',
            "---",
            "",
        ]
    )
    return lines


def bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def numbered_lines(items: list[str]) -> list[str]:
    return [f"{idx}. {item}" for idx, item in enumerate(items, start=1)]


def sorted_objectives(objectives: list[dict]) -> list[dict]:
    priority_order = {"primary": 0, "secondary": 1}
    reporting_order = {"main_text": 0, "supplement_only": 1}
    return sorted(
        objectives,
        key=lambda obj: (
            priority_order.get(obj.get("priority", "secondary"), 9),
            reporting_order.get(obj.get("reporting_role", "main_text"), 9),
            obj.get("objective_id", ""),
        ),
    )


def role_bucket(role: str, planned_role: str = "") -> str:
    merged = normalize(f"{role} {planned_role}")
    if "exposure" in merged:
        return "exposure"
    if "outcome" in merged:
        return "outcome"
    if "confounder" in merged:
        return "confounder"
    if "mediator" in merged:
        return "mediator"
    if "collider" in merged:
        return "collider"
    if "modifier" in merged or "interaction" in merged:
        return "modifier"
    return "supplementary"


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def build_dag_mermaid(objective: dict, variable_registry: dict) -> list[str]:
    if not objective.get("requires_causal_language"):
        return []

    adj = objective.get("adjustment_strategy", {}).get("adjustment_set", [])
    exposures = objective.get("exposure", "") or objective.get("condition", "")
    outcome = objective.get("outcome", "")

    mediators = [
        item["variable"]
        for item in variable_registry.get("variables", [])
        if item.get("bucket") == "mediator"
    ]

    def node_id(label: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", label or "node")[:24]

    exp_id = node_id(exposures)
    out_id = node_id(outcome)
    lines = [
        "```mermaid",
        "flowchart LR",
        f'    {exp_id}["{exposures}"]',
        f'    {out_id}["{outcome}"]',
    ]
    for confounder in adj:
        conf_id = node_id(confounder)
        lines.append(f'    {conf_id}["{confounder}"]')
        lines.append(f"    {conf_id} --> {exp_id}")
        lines.append(f"    {conf_id} --> {out_id}")
    lines.append(f"    {exp_id} --> {out_id}")
    for mediator in mediators[:3]:
        med_id = node_id(mediator)
        lines.append(f'    {med_id}["{mediator} (mediator)"]')
        lines.append(f"    {exp_id} -.-> {med_id}")
        lines.append(f"    {med_id} -.-> {out_id}")
    lines.append("```")
    return lines


def body_word_count(text: str) -> int:
    """Return language-aware content units for prose-depth gates.

    Whitespace word counts materially undercount Chinese protocols.  One CJK
    character and one Latin token are treated as comparable audit units; this
    is a thinness screen, not a claim about linguistic word segmentation.
    """
    body = strip_yaml_frontmatter(text)
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", body))
    latin = len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", body))
    return cjk + latin


def sequence_uniqueness(text: str) -> float:
    """Language-aware anti-padding score for Latin and CJK prose."""
    body = strip_yaml_frontmatter(text)
    latin_tokens = re.findall(r"[a-z]{3,}", re.sub(r"\d+", "#", body.lower()))
    latin_grams = [("latin", *latin_tokens[index:index + 5]) for index in range(max(0, len(latin_tokens) - 4))]
    cjk_chars = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", body)
    cjk_grams = [("cjk", "".join(cjk_chars[index:index + 12])) for index in range(max(0, len(cjk_chars) - 11))]
    grams = latin_grams + cjk_grams
    return len(set(grams)) / len(grams) if grams else 1.0


def strip_yaml_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def find_section(text: str, section_name: str) -> str:
    lines = text.splitlines()
    pattern = re.compile(rf"^(#+)\s+(?:\d+(?:\.\d+)*\.?\s+)?{re.escape(section_name)}(?:\s*$|\s|[:])", re.I)
    active = False
    level = 0
    collected: list[str] = []
    for line in lines:
        if not active:
            match = pattern.match(line)
            if match:
                active = True
                level = len(match.group(1))
                collected.append(line)
        else:
            match = re.match(r"^(#+)\s+", line)
            if match and len(match.group(1)) <= level:
                break
            collected.append(line)
    return "\n".join(collected)


def summarize_status(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "fail"
    if warnings:
        return "warn"
    return "pass"
