#!/usr/bin/env python3
"""Consolidated workflow commands for this skill.

Run as ``python scripts/analysis_audit.py <command> ...``. Each command keeps the
argument contract of its former standalone script.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, ImageDraw, ImageOps, ImageStat

from analysis_common import load_json, make_id, now_iso, write_json
from analysis_report import load_report_bundle, write_release_audit
# audit_pipeline


def build_analysis_audit(project_root: Path) -> dict:
    core = load_json(project_root / "analysis" / "contracts" / "analysis_core_contract.json")
    schema_catalog = load_json(Path(__file__).resolve().parents[1] / "contracts" / "result_schema_catalog.json")
    results = load_json(project_root / "registries" / "result_registry.json", default=[])
    execution_state = load_json(project_root / "analysis" / "contracts" / "execution_state.json", default={})
    errors: list[str] = []
    warnings: list[str] = []

    for row in results:
        effect_measure = row.get("effect_measure")
        schema_name = row.get("result_type") or (
            "continuous_association_result"
            if effect_measure == "beta"
            else "binary_association_result"
        )
        required = schema_catalog["result_schemas"][schema_name]["required_fields"]
        missing = [field for field in required if field not in row]
        if missing:
            errors.append(f"{row.get('result_id', 'UNKNOWN')}: missing fields {missing}")
        if row.get("effect_measure") == "prevalence ratio" and row.get("model_family") == "logistic":
            errors.append(f"{row['result_id']}: prevalence ratio cannot be backed by logistic model family")
        if row.get("result_type") == "continuous_association_result" and row.get("model_family") not in {
            "linear",
            "survey_linear",
            "continuous_linear",
            "bounded_proportion",
            "beta_regression",
            "fractional_response",
        }:
            errors.append(f"{row['result_id']}: continuous/beta effect must map to a compatible model family")
        if row.get("result_type") == "multinomial_association_result" and row.get("model_family") not in {
            "multinomial",
            "nominal",
        }:
            errors.append(f"{row['result_id']}: multinomial schema requires multinomial/nominal model family")
        if row.get("result_type") == "count_association_result" and row.get("model_family") not in {
            "count",
            "negative_binomial",
            "zero_inflated",
        }:
            errors.append(f"{row['result_id']}: count schema requires a count-compatible model family")

    if execution_state.get("failures"):
        errors.extend(f"execution failure: {item}" for item in execution_state["failures"])

    primary_result_objective_ids = {
        row.get("objective_id")
        for row in results
        if row.get("stage_id") == "primary_model_stage" and row.get("objective_id")
    }
    diagnostic_objective_ids = {
        row.get("objective_id")
        for row in load_json(project_root / "registries" / "diagnostic_registry.json", default=[])
        if row.get("objective_id")
    }
    objective_completion = execution_state.get("objective_stage_completion", {})
    descriptive_families = {"prevalence_descriptive", "descriptive", "distribution"}
    for outcome in core.get("outcomes", []):
        objective_id = outcome.get("objective_id")
        completion = objective_completion.get(objective_id, {})
        primary_meta = completion.get("primary_model_stage")
        descriptive_meta = completion.get("descriptive_stage", {})
        family = str(outcome.get("requested_method_family", "")).lower()
        if primary_meta:
            status = primary_meta.get("status")
            if status in {"blocked_by_data", "not_applicable"}:
                if not primary_meta.get("evidence_paths"):
                    errors.append(f"{objective_id}: blocked/not-applicable primary stage lacks evidence")
                continue
            if status in {"completed", "required", "degraded_with_deviation", "simplified"}:
                if objective_id not in primary_result_objective_ids:
                    errors.append(f"{objective_id}: no registered primary_model_stage result")
                if objective_id not in diagnostic_objective_ids:
                    errors.append(f"{objective_id}: no registered primary-model diagnostic")
                continue
        if family in descriptive_families or outcome.get("outcome_family") == "prevalence":
            if descriptive_meta.get("status") not in {"completed", "degraded_with_deviation", "simplified"}:
                errors.append(f"{objective_id}: descriptive objective lacks completed/degraded descriptive-stage evidence")
            elif not descriptive_meta.get("evidence_paths"):
                errors.append(f"{objective_id}: descriptive objective has no registered execution evidence")
            continue
        if objective_id and objective_id not in primary_result_objective_ids:
            errors.append(f"{objective_id}: no registered primary_model_stage result")
        if objective_id and objective_id not in diagnostic_objective_ids:
            errors.append(f"{objective_id}: no registered primary-model diagnostic")

    report_path = project_root / "analysis" / "output" / "report" / "statistical_analysis_report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    release_quality = write_release_audit(project_root, load_report_bundle(project_root), report_text)
    errors.extend(f"report release: {item}" for item in release_quality.get("errors", []))
    warnings.extend(f"report release: {item}" for item in release_quality.get("warnings", []))
    return {
        "audit_id": make_id("AUD", 1),
        "generated_at": now_iso(),
        "status": "fail" if errors else (
            "degraded_with_deviation" if execution_state.get("degraded_stages") else "pass"
        ),
        "errors": errors,
        "warnings": warnings,
        "study_identity": core.get("study_identity", {}),
        "report_release_quality": release_quality,
    }


def build_design_audit(project_root: Path) -> dict:
    core = load_json(project_root / "analysis" / "contracts" / "analysis_core_contract.json")
    decisions = load_json(project_root / "registries" / "decision_registry.json", default=[])
    deviations = load_json(project_root / "registries" / "deviation_registry.json", default=[])
    stage_contracts = sorted((project_root / "analysis" / "stage_contracts").glob("*.json"))
    errors: list[str] = []
    warnings: list[str] = []
    design_context = core.get("design_context", {})
    if design_context.get("survey_strategy") and not design_context.get("weight_variable") and design_context.get("design_mode") != "sample":
        errors.append("Survey strategy was requested but no weight variable was resolved.")
    if design_context.get("design_mode") == "survey_weight_only" and (not decisions or not deviations):
        errors.append("Weight-only degraded design requires both decision and deviation records.")
    if design_context.get("design_mode") == "survey_full" and not design_context.get("psu_variable"):
        errors.append("Full survey design requires a PSU variable.")
    for contract_path in stage_contracts:
        contract = load_json(contract_path)
        if contract.get("stage_status") == "degraded_with_deviation" and contract.get("path_mode") != "degraded":
            errors.append(f"{contract_path.name}: degraded stage must carry path_mode=degraded")
    return {
        "audit_id": make_id("AUD", 2),
        "generated_at": now_iso(),
        "status": "fail" if errors else (
            "degraded_with_deviation"
            if design_context.get("design_mode") == "survey_weight_only"
            else "pass"
        ),
        "errors": errors,
        "warnings": warnings,
        "design_context": design_context,
    }


def main_audit_pipeline() -> None:
    parser = argparse.ArgumentParser(description="Run design and analysis consistency audits.")
    parser.add_argument("project_root")
    parser.add_argument("--scope", choices=["all", "analysis", "design"], default="all")
    parser.add_argument("--no-fail-exit", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root)
    payloads: list[tuple[Path, dict]] = []
    if args.scope in {"all", "analysis"}:
        payloads.append((
            root / "analysis" / "output" / "analysis_consistency_audit.json",
            build_analysis_audit(root),
        ))
    if args.scope in {"all", "design"}:
        payloads.append((
            root / "analysis" / "output" / "design_consistency_audit.json",
            build_design_audit(root),
        ))
    for path, payload in payloads:
        write_json(path, payload)

    failures = [
        f"{path.name}: {item}"
        for path, payload in payloads
        for item in payload.get("errors", [])
    ]
    if failures and not args.no_fail_exit:
        raise SystemExit("Consistency audit failed: " + "; ".join(failures))

# validate_report_artifacts
IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*(?P<target><[^>]+>|[^\s)]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
CAPTION_NUMBER_RE = re.compile(
    r"^\s*(?:!\[[^\]]*?)?(?:#{1,6}\s+|[-*+]\s+)?(?:\*\*)?\s*"
    r"(?P<kind>Table|Figure|表|图)\s*(?P<number>[0-9]+)(?P<suffix>[A-Za-z]?)(?=\D|$)",
    flags=re.IGNORECASE,
)
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_registry_path(project_root: Path, raw_path: str) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def resolve_markdown_target(report_path: Path, raw_target: str) -> tuple[Path | None, str | None]:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = unquote(target)
    parsed = urlparse(target)
    if parsed.scheme in {"http", "https", "data"}:
        return None, parsed.scheme
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).resolve(), None
    # Queries and fragments are not part of the local filesystem path.
    local_text = unquote(parsed.path)
    path = Path(local_text)
    if not path.is_absolute():
        path = report_path.parent / path
    return path.resolve(), None


def extract_markdown_images(report_text: str, report_path: Path) -> list[dict]:
    images: list[dict] = []
    for match in IMAGE_RE.finditer(report_text):
        raw_target = match.group("target")
        resolved, external_scheme = resolve_markdown_target(report_path, raw_target)
        images.append(
            {
                "target": raw_target.strip("<>"),
                "resolved_path": str(resolved) if resolved else "",
                "external_scheme": external_scheme or "",
                "line": report_text.count("\n", 0, match.start()) + 1,
            }
        )
    return images


def extract_caption_numbers(report_text: str) -> dict[str, list[dict]]:
    numbers: dict[str, list[dict]] = {"table": [], "figure": []}
    for line_number, line in enumerate(report_text.splitlines(), start=1):
        match = CAPTION_NUMBER_RE.match(line)
        if not match:
            continue
        raw_kind = match.group("kind").lower()
        kind = "table" if raw_kind in {"table", "表"} else "figure"
        numbers[kind].append({
            "number": int(match.group("number")),
            "suffix": match.group("suffix").upper(),
            "label": match.group("number") + match.group("suffix").upper(),
            "is_image_alt": line.lstrip().startswith("!["),
            "line": line_number,
        })
    return numbers


def registry_artifacts(
    project_root: Path,
    rows: list[dict],
    id_key: str,
    artifact_kind: str,
    errors: list[str],
) -> list[dict]:
    artifacts: list[dict] = []
    for index, row in enumerate(rows, start=1):
        artifact_id = str(row.get(id_key) or f"{artifact_kind.upper()}_ROW_{index}")
        raw_path = str(row.get("source_path") or "").strip()
        if not raw_path:
            errors.append(f"{artifact_id}: registry row is missing source_path")
            artifacts.append({**row, "_artifact_id": artifact_id, "_path": None, "_actual_sha256": ""})
            continue

        path = resolve_registry_path(project_root, raw_path)
        actual_sha = ""
        if not path.exists() or not path.is_file():
            errors.append(f"{artifact_id}: registered {artifact_kind} path does not exist: {path}")
        else:
            actual_sha = sha256_file(path)

        declared_sha = str(row.get("sha256") or row.get("source_sha256") or "").strip()
        if not SHA256_RE.fullmatch(declared_sha):
            errors.append(f"{artifact_id}: registry row is missing a valid SHA-256 binding")
        elif actual_sha and declared_sha.lower() != actual_sha:
            errors.append(f"{artifact_id}: registry SHA-256 does not match file content")

        artifacts.append(
            {
                **row,
                "_artifact_id": artifact_id,
                "_path": path,
                "_actual_sha256": actual_sha,
                "_declared_sha256": declared_sha.lower(),
            }
        )
    return artifacts


def image_matches_registry(image: dict, artifact: dict) -> bool:
    if not image.get("resolved_path") or artifact.get("_path") is None:
        return False
    image_path = Path(image["resolved_path"])
    if image_path == artifact["_path"]:
        return True
    if not image_path.exists() or not image_path.is_file():
        return False
    declared_sha = artifact.get("_declared_sha256", "")
    return bool(declared_sha and SHA256_RE.fullmatch(declared_sha) and sha256_file(image_path) == declared_sha)


def validate_numbering(caption_numbers: dict[str, list[dict]], errors: list[str]) -> None:
    for kind, occurrences in caption_numbers.items():
        if not occurrences:
            continue
        by_label: dict[str, list[dict]] = {}
        for item in occurrences:
            by_label.setdefault(item["label"], []).append(item)
        duplicates = sorted(
            label for label, rows in by_label.items()
            if sum(bool(row.get("is_image_alt")) for row in rows) > 1
            or (not any(row.get("is_image_alt") for row in rows) and len(rows) > 1)
        )
        if duplicates:
            errors.append(f"{kind} numbering contains duplicate values: {duplicates}")
        unique_numbers = sorted({item["number"] for item in occurrences})
        expected = list(range(1, max(unique_numbers) + 1))
        missing = sorted(set(expected) - set(unique_numbers))
        if missing:
            errors.append(f"{kind} numbering is not continuous from 1; missing: {missing}")


def evaluate_report_artifact_integrity(
    project_root: Path,
    report_path: Path | None = None,
    figure_registry_path: Path | None = None,
    table_registry_path: Path | None = None,
) -> dict:
    project_root = project_root.resolve()
    report_path = (report_path or project_root / "analysis" / "output" / "report" / "statistical_analysis_report.md").resolve()
    figure_registry_path = (figure_registry_path or project_root / "registries" / "figure_registry.json").resolve()
    table_registry_path = (table_registry_path or project_root / "registries" / "table_registry.json").resolve()

    errors: list[str] = []
    warnings: list[str] = []
    if not report_path.exists():
        report_text = ""
        errors.append(f"Markdown report does not exist: {report_path}")
    else:
        report_text = report_path.read_text(encoding="utf-8")

    raw_figures = load_json(figure_registry_path, default=[])
    raw_tables = load_json(table_registry_path, default=[])
    if not isinstance(raw_figures, list):
        errors.append("figure registry must contain a JSON array")
        raw_figures = []
    if not isinstance(raw_tables, list):
        errors.append("table registry must contain a JSON array")
        raw_tables = []

    figures = registry_artifacts(project_root, raw_figures, "figure_id", "figure", errors)
    tables = registry_artifacts(project_root, raw_tables, "table_id", "table", errors)
    images = extract_markdown_images(report_text, report_path)

    local_images = [image for image in images if not image.get("external_scheme")]
    for image in local_images:
        path = Path(image["resolved_path"])
        if not path.exists() or not path.is_file():
            errors.append(f"Markdown image path does not exist at line {image['line']}: {path}")
            continue
        if not any(image_matches_registry(image, artifact) for artifact in figures):
            errors.append(f"Markdown image is not registered at line {image['line']}: {path}")

    for image in images:
        if image.get("external_scheme"):
            warnings.append(
                f"External Markdown image cannot be verified at line {image['line']}: {image['target']}"
            )

    for artifact in figures:
        if artifact.get("registry_role") != "main_text":
            continue
        matches = [image for image in local_images if image_matches_registry(image, artifact)]
        if len(matches) != 1:
            errors.append(
                f"{artifact['_artifact_id']}: main-text figure must be embedded exactly once; found {len(matches)}"
            )

    caption_numbers = extract_caption_numbers(report_text)
    validate_numbering(caption_numbers, errors)

    return {
        "generated_at": now_iso(),
        "status": "fail" if errors else "pass",
        "report_path": str(report_path),
        "figure_registry_path": str(figure_registry_path),
        "table_registry_path": str(table_registry_path),
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "markdown_images": len(images),
            "local_markdown_images": len(local_images),
            "registered_figures": len(figures),
            "registered_main_text_figures": sum(row.get("registry_role") == "main_text" for row in figures),
            "registered_tables": len(tables),
            "explicit_figure_numbers": len(caption_numbers["figure"]),
            "explicit_table_numbers": len(caption_numbers["table"]),
        },
    }


def main_validate_report_artifacts() -> None:
    parser = argparse.ArgumentParser(description="Validate Markdown report artifact integrity against table and figure registries.")
    parser.add_argument("project_root")
    parser.add_argument("--report", default="")
    parser.add_argument("--figure-registry", default="")
    parser.add_argument("--table-registry", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--no-fail-exit", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root)
    payload = evaluate_report_artifact_integrity(
        root,
        report_path=Path(args.report) if args.report else None,
        figure_registry_path=Path(args.figure_registry) if args.figure_registry else None,
        table_registry_path=Path(args.table_registry) if args.table_registry else None,
    )
    output = Path(args.output) if args.output else root / "analysis" / "output" / "report_artifact_integrity_audit.json"
    write_json(output, payload)
    if payload["errors"] and not args.no_fail_exit:
        raise SystemExit("Report artifact integrity validation failed: " + "; ".join(payload["errors"]))

# validate_pdf


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_output(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def build_contact_sheets(pages: list[Path], render_dir: Path, per_sheet: int = 12) -> list[dict]:
    sheets: list[dict] = []
    for sheet_index, start in enumerate(range(0, len(pages), per_sheet), start=1):
        batch = pages[start:start + per_sheet]
        thumbnails = []
        for page_number, path in enumerate(batch, start=start + 1):
            with Image.open(path) as source:
                thumb = source.convert("RGB")
                thumb.thumbnail((280, 380))
                canvas = Image.new("RGB", (300, 420), "white")
                canvas.paste(thumb, ((300 - thumb.width) // 2, 25))
                ImageDraw.Draw(canvas).text((10, 5), f"Page {page_number}", fill="black")
                thumbnails.append(ImageOps.expand(canvas, border=1, fill="#777777"))
        sheet = Image.new("RGB", (302 * 4, 422 * 3), "#dddddd")
        for index, thumb in enumerate(thumbnails):
            sheet.paste(thumb, ((index % 4) * 302, (index // 4) * 422))
        path = render_dir / f"contact-sheet-{sheet_index:02d}.png"
        sheet.save(path)
        sheets.append({"path": str(path.resolve()), "sha256": digest(path), "pages": [start + 1, start + len(batch)]})
    return sheets


def render_pdf(project_root: Path, pdf_path: Path, render_dir: Path, signoff_path: Path | None = None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if not pdf_path.is_file():
        return {"generated_at": now_iso(), "status": "fail", "errors": [f"PDF does not exist: {pdf_path}"], "warnings": []}
    required_commands = {name: shutil.which(name) for name in ("pdftoppm", "pdfinfo", "pdffonts", "pdftotext")}
    missing = [name for name, path in required_commands.items() if not path]
    if missing:
        return {"generated_at": now_iso(), "status": "fail", "errors": [f"missing PDF QA commands: {missing}"], "warnings": []}

    render_dir.mkdir(parents=True, exist_ok=True)
    for old in render_dir.glob("page-*.png"):
        old.unlink()
    info = command_output([required_commands["pdfinfo"], str(pdf_path)])
    page_match = re.search(r"(?m)^Pages:\s+(\d+)", info.stdout)
    expected_pages = int(page_match.group(1)) if page_match else 0
    if info.returncode != 0 or expected_pages <= 0:
        errors.append("pdfinfo could not establish a positive page count")

    render = command_output([
        required_commands["pdftoppm"], "-png", "-r", "120", str(pdf_path), str(render_dir / "page")
    ])
    if render.returncode != 0:
        errors.append("pdftoppm failed: " + render.stderr.strip())
    pages = sorted(render_dir.glob("page-*.png"))
    if expected_pages and len(pages) != expected_pages:
        errors.append(f"rendered page count {len(pages)} does not match PDF page count {expected_pages}")

    page_metrics = []
    for page_number, path in enumerate(pages, start=1):
        with Image.open(path) as image:
            grayscale = image.convert("L")
            thumbnail = grayscale.copy()
            thumbnail.thumbnail((400, 400))
            histogram = thumbnail.histogram()
            total = sum(histogram)
            nonwhite = sum(histogram[:245]) / total if total else 0.0
            mean_luminance = ImageStat.Stat(thumbnail).mean[0]
            pixels = thumbnail.load()
            active_rows = sum(
                1 for y in range(thumbnail.height)
                if sum(pixels[x, y] < 245 for x in range(thumbnail.width)) / thumbnail.width >= 0.005
            )
            active_row_fraction = active_rows / thumbnail.height if thumbnail.height else 0.0
            page_metrics.append({
                "page": page_number,
                "path": str(path.resolve()),
                "sha256": digest(path),
                "width_px": image.width,
                "height_px": image.height,
                "nonwhite_fraction": round(nonwhite, 6),
                "active_row_fraction": round(active_row_fraction, 6),
                "mean_luminance": round(mean_luminance, 3),
            })
            if nonwhite < 0.001:
                errors.append(f"page {page_number} is blank or near-blank (nonwhite_fraction={nonwhite:.6f})")
            elif nonwhite < 0.004:
                warnings.append(f"page {page_number} has very little rendered content and requires visual review")
            if active_row_fraction < 0.12:
                warnings.append(
                    f"page {page_number} uses less than 12% active text/image rows and may be a near-blank or poorly paginated page"
                )
            if nonwhite > 0.65:
                warnings.append(f"page {page_number} is unusually dense and requires clipping/overlap review")
    contact_sheets = build_contact_sheets(pages, render_dir) if pages else []

    fonts = command_output([required_commands["pdffonts"], str(pdf_path)])
    if fonts.returncode != 0:
        errors.append("pdffonts failed: " + fonts.stderr.strip())
    font_rows = []
    for line in fonts.stdout.splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 7:
            embedded = parts[-4].lower() == "yes"
            font_rows.append({"name": parts[0], "embedded": embedded, "raw": line})
            if not embedded:
                errors.append(f"PDF font is not embedded: {parts[0]}")

    text_path = render_dir / "extracted_text.txt"
    text_run = command_output([required_commands["pdftotext"], str(pdf_path), str(text_path)])
    extracted = text_path.read_text(encoding="utf-8", errors="replace") if text_run.returncode == 0 and text_path.exists() else ""
    for token in ("[REQUIRES SPECIFICATION:", "turn0search", "�"):
        if token in extracted:
            errors.append(f"PDF extracted text contains prohibited token: {token}")

    visual_signoff = load_json(signoff_path, default={}) if signoff_path else {}
    signoff_pass = (
        visual_signoff.get("status") == "pass"
        and bool(str(visual_signoff.get("reviewer", "")).strip())
        and bool(str(visual_signoff.get("reviewed_at", "")).strip())
        and visual_signoff.get("pdf_sha256") == digest(pdf_path)
    )
    delivery_class = load_json(
        project_root / "analysis" / "contracts" / "execution_state.json", default={}
    ).get("report_delivery_class", "scientific_final")
    if delivery_class == "scientific_final" and not signoff_pass:
        warnings.append("scientific_final still requires independent full-page visual sign-off bound to this PDF hash")

    status = "fail" if errors else ("pass" if signoff_pass else "technical_pass_visual_review_required")
    return {
        "generated_at": now_iso(),
        "status": status,
        "pdf_path": str(pdf_path.resolve()),
        "pdf_sha256": digest(pdf_path),
        "page_count": expected_pages,
        "rendered_page_count": len(pages),
        "pages": page_metrics,
        "contact_sheets": contact_sheets,
        "fonts": font_rows,
        "visual_signoff": visual_signoff,
        "errors": errors,
        "warnings": warnings,
        "required_visual_review": [
            "Chinese glyph integrity and font consistency",
            "clipped or overlapping text and tables",
            "wide-table type size and legibility",
            "figure sharpness, axis labels, captions, and legends",
            "blank/near-blank pages, page breaks, headers, footers, and numbering",
        ],
    }


def main_validate_pdf() -> None:
    parser = argparse.ArgumentParser(description="Render and audit every page of the statistical analysis PDF.")
    parser.add_argument("project_root")
    parser.add_argument("--pdf", default="")
    parser.add_argument("--render-dir", default="")
    parser.add_argument("--visual-signoff", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(args.project_root)
    report_dir = root / "analysis" / "output" / "report"
    pdf_path = Path(args.pdf) if args.pdf else report_dir / "statistical_analysis_report.pdf"
    render_dir = Path(args.render_dir) if args.render_dir else report_dir / "pdf_render_qa"
    output = Path(args.output) if args.output else report_dir / "pdf_render_qa_manifest.json"
    payload = render_pdf(
        root, pdf_path, render_dir,
        signoff_path=Path(args.visual_signoff) if args.visual_signoff else None,
    )
    write_json(output, payload)
    if payload["status"] == "fail":
        raise SystemExit("PDF render QA failed: " + "; ".join(payload["errors"]))


COMMANDS = {
    "audit_pipeline": main_audit_pipeline,
    "validate_report_artifacts": main_validate_report_artifacts,
    "validate_pdf": main_validate_pdf,
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
