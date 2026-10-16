#!/usr/bin/env python3
"""Assemble support files around an already written, registry-grounded manuscript.

Scientific prose is intentionally not generated here. The skill agent writes the
manuscript from contracts and registries; this script performs deterministic
packaging only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


PLACEHOLDER_PATTERNS = [r"\bTODO\b", r"\bTBD\b", r"FILL IN", r"\*\*\*\*"]


def read_json(path: Path):
    if not path.exists():
        raise SystemExit(f"Required file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def unresolved_placeholders(text: str) -> list[str]:
    return [pattern for pattern in PLACEHOLDER_PATTERNS if re.search(pattern, text, re.I)]


def figure_legends(figures: list[dict]) -> str:
    lines = ["# Figure Legends", ""]
    selected = [row for row in figures if row.get("registry_role", "main_text") == "main_text"]
    for idx, row in enumerate(selected, start=1):
        source = Path(str(row.get("source_path", "")))
        if not source.exists():
            raise SystemExit(f"Registered figure source does not exist: {source}")
        caption = row.get("caption") or row.get("display_title") or row.get("title") or row.get("figure_id")
        legend = row.get("legend", "")
        lines.extend([f"## Figure {idx}", "", str(caption), ""])
        if legend:
            lines.extend([str(legend), ""])
        lines.extend([f"Registry ID: `{row.get('figure_id', '')}`", ""])
    if not selected:
        lines.append("No main-text figure was registered for this manuscript.")
    return "\n".join(lines)


def submission_checklist(root: Path, manuscript: Path, results: list[dict], tables: list[dict], figures: list[dict]) -> str:
    required = {
        "manuscript source": manuscript,
        "manuscript contract": root / "manuscript" / "manuscript_contract.json",
        "result registry": root / "registries" / "result_registry.json",
        "table registry": root / "registries" / "table_registry.json",
        "figure registry": root / "registries" / "figure_registry.json",
        "citation registry": root / "literature_review" / "citation_registry.json",
    }
    lines = ["# Submission Package Checklist", ""]
    for label, path in required.items():
        lines.append(f"- [{'x' if path.exists() else ' '}] {label}: `{path}`")
    lines.extend(
        [
            "",
            f"- Registered results: {len(results)}",
            f"- Registered tables: {len(tables)}",
            f"- Registered figures: {len(figures)}",
            "- [ ] Full manuscript-standard validator passed",
            "- [ ] DOCX/PDF rendering visually inspected",
            "- [ ] Journal-specific author, ethics, funding, and disclosure fields confirmed by the user",
        ]
    )
    return "\n".join(lines)


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True)


def export_manuscript(source: Path, output_dir: Path, reference_doc: str = "") -> None:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise SystemExit("pandoc is required for full-manuscript DOCX export.")

    output_dir.mkdir(parents=True, exist_ok=True)
    docx = output_dir / "manuscript.docx"
    pdf = output_dir / "manuscript.pdf"
    docx_command = [
        pandoc,
        str(source),
        "--from",
        "markdown+smart",
        "--to",
        "docx",
        "--standalone",
        "--output",
        str(docx),
    ]
    if reference_doc:
        reference = Path(reference_doc)
        if not reference.exists():
            raise SystemExit(f"Reference DOCX not found: {reference}")
        docx_command.extend(["--reference-doc", str(reference)])
    completed = run(docx_command)
    if completed.returncode or not docx.exists() or docx.stat().st_size == 0:
        raise SystemExit("DOCX export failed:\n" + completed.stderr)

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        converted = run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(docx)]
        )
        if converted.returncode == 0 and pdf.exists() and pdf.stat().st_size > 0:
            print(f"Exported {docx} and {pdf}")
            return

    pdf_command = [
        pandoc,
        str(source),
        "--from",
        "markdown+smart",
        "--to",
        "pdf",
        "--pdf-engine=xelatex",
        "--variable",
        "geometry:margin=1in",
        "--variable",
        "mainfont=Times New Roman",
        "--output",
        str(pdf),
    ]
    completed = run(pdf_command)
    if completed.returncode or not pdf.exists() or pdf.stat().st_size == 0:
        raise SystemExit("PDF export failed:\n" + completed.stderr)
    print(f"Exported {docx} and {pdf}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble registry-grounded manuscript support files.")
    parser.add_argument("project_root")
    parser.add_argument("--manuscript", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--reference-doc", default="")
    args = parser.parse_args()

    root = Path(args.project_root)
    manuscript = Path(args.manuscript) if args.manuscript else root / "manuscript" / "manuscript.md"
    output_dir = Path(args.output_dir) if args.output_dir else root / "manuscript"
    if not manuscript.exists():
        raise SystemExit(f"Completed manuscript not found: {manuscript}")
    contract_path = root / "manuscript" / "manuscript_contract.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("validate_manuscript_contract.py")), str(contract_path)],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("validate_manuscript_registry_binding.py")),
            str(contract_path),
            str(manuscript),
        ],
        check=True,
    )
    text = manuscript.read_text(encoding="utf-8")
    placeholders = unresolved_placeholders(text)
    if placeholders:
        raise SystemExit("Manuscript still contains placeholders: " + ", ".join(placeholders))
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("audit_manuscript_mode.py")),
            str(contract_path),
            str(manuscript),
        ],
        check=True,
    )

    freeze = read_json(root / "analysis" / "frozen" / "freeze_manifest.json")
    if freeze.get("status") != "ready":
        raise SystemExit("Analysis registry is not frozen-ready; manuscript packaging is blocked.")
    results = read_json(root / "registries" / "result_registry.json")
    tables = read_json(root / "registries" / "table_registry.json")
    figures = read_json(root / "registries" / "figure_registry.json")
    read_json(root / "literature_review" / "citation_registry.json")
    if not results:
        raise SystemExit("Result registry is empty; manuscript packaging is blocked.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_manuscript = output_dir / "manuscript.md"
    if output_manuscript.resolve() != manuscript.resolve():
        write_text(output_manuscript, text)
    write_text(output_dir / "figure_legends.md", figure_legends(figures))
    write_text(
        output_dir / "submission_package_checklist.md",
        submission_checklist(root, manuscript, results, tables, figures),
    )

    table_script = Path(__file__).with_name("build_manuscript_tables_docx.py")
    subprocess.run(
        [sys.executable, str(table_script), str(root), "--output", str(output_dir / "tables_for_manuscript.docx")],
        check=True,
    )
    if args.export:
        export_manuscript(manuscript, output_dir, args.reference_doc)
    print(f"Manuscript support package assembled in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
