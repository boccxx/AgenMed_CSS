#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


MODE_SECTIONS = {
    "research": [
        "Abstract",
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
        "References",
    ],
    "applied_methods": [
        "Abstract",
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
        "References",
    ],
    "workflow_methods": [
        "Abstract",
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
        "References",
    ],
}


FULL_BODY_HINTS = {
    "Introduction": (
        "TODO: establish the substantive burden, synthesize registered prior evidence, identify the exact unresolved gap, "
        "and end with the prespecified objective and non-causal cross-sectional estimand. Target 500-700 words."
    ),
    "Methods": (
        "TODO: report setting/dates, source and analysis populations, sampling/recruitment, eligibility, named instruments "
        "and scoring, variables/units, bias controls, reproducible study-size basis, executed model family/link/variance/design, "
        "missing-data algorithm, diagnostics with actions, sensitivities, deviations, software/versions, ethics and provenance. "
        "Describe only executed work. Target 1300-1700 words."
    ),
    "Results": (
        "TODO: report participant reconciliation and N, missingness, descriptive distributions, crude/adjusted estimates only "
        "when executed, interpretable contrasts with 95% CIs, diagnostics, every registered main-text sensitivity result, and "
        "direct calls to at least three registered tables/figures. Use registered numbers only. Target 1150-1500 words."
    ),
    "Discussion": (
        "TODO: state the bounded finding, compare it with multiple registered studies, explain effect scale and plausible mechanisms, "
        "address conflicting evidence, practical meaning, strengths, temporality, selection, measurement, residual confounding, "
        "missingness, multiplicity and transportability, then give a claim-bounded conclusion. Target 1100-1400 words."
    ),
    "References": "TODO: render every allowed verified reference exactly from the citation registry; minimum 25 for a complete article.",
}


def build_scaffold(contract: dict) -> str:
    mode = contract.get("manuscript_mode", contract.get("mode", "applied_methods"))
    title = contract.get("title", "Manuscript Title")
    lines = [
        "---",
        f'title: "{title}"',
        "geometry: margin=1in",
        "fontsize: 12pt",
        'mainfont: "Times New Roman"',
        "---",
        "",
    ]

    if mode == "research":
        abstract_hint = [
            "# Abstract",
            "",
            "## Background",
            "",
            "TODO: summarize the scientific gap only.",
            "",
            "## Methods",
            "",
            "TODO: summarize design, population, estimand, and model.",
            "",
            "## Results",
            "",
            "TODO: report registered estimates only.",
            "",
            "## Conclusions",
            "",
            "TODO: stay within the research claim boundary.",
            "",
        ]
    elif mode == "applied_methods":
        abstract_hint = [
            "# Abstract",
            "",
            "## Background",
            "",
            "TODO: state the scientific topic and evidence gap without branding the title page.",
            "",
            "## Methods",
            "",
            "TODO: end this paragraph with one sentence stating that analyses used a synthetic validation dataset.",
            "",
            "## Results",
            "",
            "TODO: report registered estimates without upgrading them to empirical population claims.",
            "",
            "## Conclusions",
            "",
            "TODO: state the strongest mode-bounded scientific or methodological conclusion.",
            "",
        ]
    else:
        abstract_hint = [
            "# Abstract",
            "",
            "## Background",
            "",
            "TODO: foreground the workflow problem.",
            "",
            "## Methods",
            "",
            "TODO: describe the workflow components and validation context.",
            "",
            "## Results",
            "",
            "TODO: report workflow outputs and consistency checks.",
            "",
            "## Conclusions",
            "",
            "TODO: state the workflow contribution only.",
            "",
        ]
    lines.extend(abstract_hint)

    for section in MODE_SECTIONS.get(mode, MODE_SECTIONS["applied_methods"])[1:]:
        lines.append(f"# {section}")
        lines.append("")
        lines.append(FULL_BODY_HINTS.get(section, f"TODO: fill {section.lower()} for `{mode}` mode."))
        lines.append("")
        if section == "Discussion":
            lines.extend(
                [
                    "## Limitations",
                    "",
                    "TODO: in applied_methods mode, begin with the synthetic validation disclosure and state that the estimates are not empirical population evidence.",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    contract = json.loads(Path(args.contract).read_text())
    Path(args.output).write_text(build_scaffold(contract))


if __name__ == "__main__":
    main()
