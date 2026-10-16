#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


REQUIRED = [
    "review_contract.json",
    "protocol_contract.json",
    "estimand_bridge.json",
    "sap_contract.json",
    "analysis_core_contract.json",
    "report_release_quality_audit.json",
    "result_registry.json",
    "table_registry.json",
    "figure_registry.json",
    "citation_registry.json",
]

REQUIRED_FIELDS = [
    "contract_version",
    "project_mode",
    "manuscript_mode",
    "upstream_contract_version",
    "generated_at",
    "status",
    "downgrade_state",
    "title",
    "source_inputs",
    "allowed_claim_level",
    "allowed_result_ids",
    "allowed_table_ids",
    "allowed_figure_ids",
    "allowed_citation_ids",
    "binding_map",
]


def resolve_source(project_root: Path, item) -> tuple[Path | None, str, str]:
    if not isinstance(item, dict):
        return None, "", ""
    path = Path(str(item.get("path", "")))
    if not path.is_absolute():
        path = project_root / path
    return path, str(item.get("sha256", "")), str(item.get("status", ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a manuscript contract.")
    parser.add_argument("manuscript_contract_json")
    args = parser.parse_args()
    path = Path(args.manuscript_contract_json)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        parser.error(f"contract not found: {path}")
    except json.JSONDecodeError as exc:
        parser.error(f"contract is not valid JSON: {exc}")
    missing_fields = [item for item in REQUIRED_FIELDS if item not in data]
    if missing_fields:
        print("missing required fields:", ", ".join(missing_fields))
        return 1
    missing = [item for item in REQUIRED if item not in data.get("required_inputs", [])]
    if missing and "required_inputs" in data:
        print("missing required inputs:", ", ".join(missing))
        return 1
    if data.get("manuscript_mode") not in {"research", "applied_methods", "workflow_methods"}:
        print("invalid manuscript_mode")
        return 1
    if data.get("project_mode") != data.get("manuscript_mode"):
        print("project_mode and manuscript_mode must match")
        return 1
    project_root = path.parent.parent
    source_inputs = data.get("source_inputs")
    if not isinstance(source_inputs, dict) or not source_inputs:
        print("source_inputs must be a non-empty mapping of required files to path/hash/status records")
        return 1
    source_errors = []
    source_modes = []
    release_quality_payload = None
    for name in REQUIRED:
        source, expected_hash, expected_status = resolve_source(project_root, source_inputs.get(name))
        if source is None or not source.exists():
            source_errors.append(f"missing source input: {name}")
            continue
        actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if not expected_hash or actual_hash != expected_hash:
            source_errors.append(f"source hash missing or stale: {name}")
        if expected_status not in {"ready", "frozen", "verified"}:
            source_errors.append(f"source status is not release-ready: {name}")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict):
            if name == "report_release_quality_audit.json":
                release_quality_payload = payload
            serialized = json.dumps(payload, ensure_ascii=False)
            unresolved_tokens = [
                token for token in ("DECISION_PENDING", "[REQUIRES SPECIFICATION", "TODO", "TBD")
                if token.lower() in serialized.lower()
            ]
            if unresolved_tokens:
                source_errors.append(
                    f"source payload contains unresolved release blockers in {name}: {', '.join(unresolved_tokens)}"
                )
            actual_status = payload.get("status")
            if actual_status and actual_status not in {"ready", "frozen", "verified"}:
                source_errors.append(f"source payload status is not release-ready: {name}")
            source_mode = payload.get("project_mode") or payload.get("study_identity", {}).get("project_mode")
            if source_mode:
                source_modes.append((name, source_mode))
            if data.get("project_mode") == "research":
                study_identity = payload.get("study_identity", {})
                study_title = str(
                    study_identity.get("study_title", "") if isinstance(study_identity, dict) else payload.get("study_title", "")
                )
                if study_title and re.search(r"\b(example|demo|toy|smoke[ -]?test)\b", study_title, re.I):
                    source_errors.append(f"research source uses a demonstration-style study title in {name}: {study_title!r}")
    for name, source_mode in source_modes:
        allowed_source_modes = {data.get("project_mode")}
        if data.get("manuscript_mode") == "applied_methods":
            allowed_source_modes.add("research")
        if source_mode not in allowed_source_modes:
            source_errors.append(
                f"source project_mode mismatch: {name}={source_mode!r}, contract={data.get('project_mode')!r}"
            )
    if isinstance(release_quality_payload, dict):
        release_mode = str(release_quality_payload.get("analysis_release_mode", ""))
        release_status = str(release_quality_payload.get("status", ""))
        manuscript_mode = str(data.get("manuscript_mode", ""))
        if manuscript_mode == "research" and (release_mode != "scientific_release" or release_status != "scientific_pass"):
            source_errors.append(
                "research manuscript requires analysis scientific_release with scientific_pass; "
                f"got mode={release_mode!r}, status={release_status!r}"
            )
        if release_status == "demonstration_pass" and manuscript_mode == "research":
            source_errors.append("demonstration analysis cannot feed a research manuscript")
        if release_status not in {"scientific_pass", "demonstration_pass"}:
            source_errors.append(f"analysis report release audit is not pass-ready: {release_status!r}")
    if source_errors:
        print("; ".join(source_errors))
        return 1
    binding_map = Path(str(data.get("binding_map", "")))
    if not binding_map.is_absolute():
        binding_map = project_root / binding_map
    if not binding_map.exists():
        print(f"binding map not found: {binding_map}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
