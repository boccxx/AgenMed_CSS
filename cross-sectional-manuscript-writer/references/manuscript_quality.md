# Manuscript writing and release rules



---

# Manuscript Mode Matrix

## research

- Use for real data and real submission claims.
- Introduction may frame a scientific gap.
- Results may report empirical associations from registered outputs.
- Discussion may make substantive inferences, with limitations.
- No synthetic-data language anywhere. If "synthetic" or "validation" appears, it is a validator error.

## applied_methods

- Use for synthetic, pilot, or internal-validation data tied to a real question.
- Uses a normal scientific-paper structure, while keeping every inference bounded to synthetic, pilot, or internal-validation data.
- Introduction frames a **scientific gap**, same as `research` mode.
- Results report registered validation estimates without presenting them as empirical population observations.
- Discussion opens with the strongest scientifically relevant but mode-bounded finding.
- Synthetic-data disclosure appears in exactly two places:
  1. Last sentence of the Abstract Methods paragraph.
  2. First paragraph of the Limitations section.
- The Discussion's contribution statement must be about the scientific question or the analytical method — not about workflow, pipeline, or contract enforcement.

### Acceptable applied_methods language examples

**Discussion opening (correct):**
> "In the validation dataset, high bedtime smartphone use was associated with a higher modeled prevalence of poor sleep quality after adjustment for the prespecified covariates; this estimate evaluates the analytic specification and does not establish the association in a real undergraduate population."

**Limitations disclosure (correct):**
> "The primary limitation is that this analysis used a synthetic dataset generated to match realistic distributions rather than empirical observations from a real student cohort. The findings therefore support the analytic framework and method choices rather than providing direct evidence about the undergraduate population."

### Prohibited applied_methods language examples

**Discussion opening (incorrect — validator will reject):**
> "The principal contribution of this paper is methodological. The manuscript remained aligned with its review, protocol, estimand, and analysis artefacts…"

**Abstract Methods (incorrect — disclosure is the dominant framing):**
> "We conducted an applied-methods validation using a synthetic multi-campus dataset… The writing process was anchored to prespecified review, protocol, estimand, SAP, result, table, figure, and citation artefacts."

## workflow_methods

- Use for skill validation or pipeline demonstration.
- The paper is about the workflow itself.
- Claims must stay at the level of method design, contract enforcement, and reproducibility.
- Do not imply a real epidemiologic finding.
- Title and abstract may foreground the pipeline or contract-driven design.


---

# Writing Rules

## General Persona

Write as an epidemiologist and academic author preparing a submission to a peer-reviewed observational journal. Do not write as a system summarising its workflow. A reader with no knowledge of the skill chain must not be able to distinguish this manuscript from one written by a human researcher.

## Title

- `research`: state the scientific topic and study design.
- `applied_methods`: state the scientific topic first. Put validation language in the abstract or methods unless it is scientifically necessary in the title.
- `workflow_methods`: foreground the workflow or contract-driven pipeline.
- Do not put generator branding, author placeholders, dates, or pipeline labels into the title block by default.
- Prefer a restrained journal-like first page over a decorative cover page.

## Abstract

- Background should open with a scientific observation about the topic, not with a description of the analytical problem or the workflow.
- Methods should summarise source contracts and executed analysis scope. For `applied_methods`, the last sentence of Abstract Methods must disclose that the data are synthetic (e.g. "Analyses used a synthetic validation dataset of N participants.").
- Results should only use registered findings.
- Conclusions should match the allowed claim level.

## Introduction

- Open with a scientific gap statement grounded in the evidence from `citation_registry`.
- Do not open with a description of the analytical or pipeline problem.
- Keep methods justification in the methods section unless the paper is explicitly a methods paper (`workflow_methods` mode).
- For `applied_methods` mode: the Introduction must frame a real scientific gap, not a workflow gap. "Many studies still rely on convenience samples and vague exposure definitions" is a scientific framing. "Many pipelines lack contract enforcement" is not.

## Methods

- Describe only what was actually executed or validated.
- Do not add a third synthetic-data disclosure in the main Methods body; keep the required disclosure in Abstract Methods and Limitations.
- State the estimand and model family when relevant.
- Put mode disclosure in methods or a short document-status note, not as splash-page metadata.

## Results

- Report values, intervals, and diagnostics from registries.
- The primary point estimate and 95% CI must appear in the running text, not only in a table.
- Do not add unregistered interpretations.
- Do not mention the skill chain, workflow, or pipeline in the Results section.

## Discussion

- Open with the strongest mode-bounded scientific or methodological finding, not a population claim unsupported by validation data.
- Separate empirical interpretation from workflow evaluation.
- The contribution statement must describe a substantive finding about the research question, the methods, or the measurement approach — not "we validated a pipeline" or "we demonstrated a workflow."
- Always state the main limitation of the manuscript mode.
- For `applied_methods`: synthetic-data limitation goes in the first paragraph of Limitations. It must not appear as the opening sentence of the Discussion.

## Applied-Methods Disclosure Placement (Hard Rule)

For `applied_methods` mode, the following placement rules are enforced by the validator:

| Location | Permitted? |
|---|---|
| Title | No |
| Abstract Background | No |
| Abstract Methods — last sentence | Yes |
| Introduction | No |
| Methods body | No additional disclosure; avoid a third occurrence |
| Results | No |
| Discussion — opening | No |
| Discussion — Limitations first paragraph | Yes |

Any other placement is a validator error and must be corrected before delivery.

## Prohibited Phrases (All Modes)

These must never appear in any section of the manuscript body:

- "skill-chain"
- "Codex"
- "workflow validation"
- "validate the workflow"
- "Codex skill-chain"
- "Example 1"
- "applied-methods validation" (as the paper's identity or main framing)


---

# Full-body manuscript quality standard

Use this standard for `research` and `applied_methods` manuscripts intended to be complete, independently readable articles. Journal-specific limits may override the numerical targets only when the target instructions are recorded in the manuscript contract. A shorter journal format does not waive factual, registry, citation, or display completeness.

## Published-body calibration

The local 2026-07-19 benchmark measured three full cross-sectional articles in BMJ Open and JAMA Network Open. Their scientific bodies contained 3,669–4,965 words (median 4,383), Results contained 1,244–1,511 words, reference lists contained 35–55 entries, and each article used five main tables/figures. These values calibrate the targets below; they are not permission to add filler.

## Body and section targets

| Component | Hard floor | Preferred range |
|---|---:|---:|
| Main body, excluding abstract/references/YAML | 4,000 | 4,200–5,200 |
| Abstract | 220 | 250–350 |
| Introduction | 450 | 500–700 |
| Methods | 1,100 | 1,300–1,700 |
| Results | 900 | 1,150–1,500 |
| Discussion including limitations | 900 | 1,100–1,400 |
| Verifiable references | 25 | 35–60 |
| Main-text tables/figures combined | 3 | 3–6 |

The validator treats these as full-body release floors. A documented target-journal limit may lower the word floor, but the contract must name the journal and record the exact applicable limit.

## Information-density rule

Every paragraph must add at least one of the following:

- a registered population, measurement, method, result, diagnostic, or sensitivity detail;
- a verified comparison with prior evidence;
- a specific bias mechanism with direction or consequence;
- an interpretation tied to an observed effect scale;
- a concrete generalizability or decision consequence.

Repeated caveats, generic methods teaching, and theme-swapped prose do not count. If the registered evidence cannot support the target length, stop and identify missing evidence objects instead of padding.

## Methods-to-execution rule

Every past-tense execution verb—for example `assessed`, `compared`, `adjusted`, `weighted`, `imputed`, `tested`, or `examined`—must resolve to an executed contract, result, table, figure, diagnostic, or deviation record. Planned-but-unexecuted work belongs only in a clearly labelled limitation or future-work sentence.

The Methods must name the actual family, link, variance estimator, design treatment, exposure contrast and unit, outcome scale, adjustment set, missing-data method, diagnostic actions, sensitivity analyses, software and versions. Do not call a quasibinomial model beta regression. Do not interpret a link-scale coefficient as a direct mean difference.

## Results chain

Report, in order:

1. source and analysis populations, exclusions, and final N;
2. missingness and the realized handling path;
3. participant, exposure, outcome, and adjustment-variable distributions;
4. crude and adjusted primary estimates when both were executed;
5. effect scale, exposure contrast/unit, 95% CI, and clinically or scientifically interpretable transformation;
6. registered secondary, subgroup, interaction, dose-response, diagnostic, and sensitivity results, or explicit non-execution reasons;
7. direct calls to every main-text table and figure.

Do not compare coefficients across models on different scales as though their numerical magnitudes were commensurable.

## Mode and truthfulness gates

- `research`: require real data provenance and study metadata. Reject toy, demo, synthetic, smoke-test, or internal-validation inputs.
- `applied_methods`: require the prescribed disclosure and prevent any population-level empirical claim. The title or running header must make demonstration status unambiguous when the data contain only a tiny deterministic example.
- Any dataset with fewer observations than required for the fitted degrees of freedom must block inferential prose.
- An empty adjustment set prohibits `adjusted association`, `adjusted estimate`, `controlled for`, and equivalent claims.
- Sample-mode analysis without a registered weight prohibits `weighted` result claims.
- Every estimate/SE/CI/p-value set must be recomputed under one coherent reference distribution, degrees of freedom, sidedness, and variance method.

## Citation and display gates

For `research` and `applied_methods`, require at least 25 verified, allowed references. All substantive background, measurement, methodological-choice, and literature-comparison claims require registered citations. Placeholder citations and incomplete bibliographic identities block release.

Require at least three registered main-text displays, normally participant/descriptive information, primary model results, and one scientifically informative figure or sensitivity/diagnostic display. Every display must be cited in the body and have a self-contained title, denominator, units, model/adjustment note, and abbreviations.

## Cross-document consistency

Before release, compare the manuscript with the analysis report and frozen registries for:

- study/data mode and final N;
- model family, link, variance estimator, design mode, and weights;
- adjustment variables and missing-data method;
- primary and sensitivity estimates, intervals, and p values;
- table/figure inventory;
- deviations and interpretation ceiling.

Any unresolved conflict is a hard failure.


---

# Manuscript Output Schema

## Core Manuscript Files

- `manuscript.md`
- `manuscript.docx`
- `manuscript.pdf`

Default presentation expectation:

- restrained academic typography
- no generator branding in the title block
- no required subtitle field
- page-numbered DOCX/PDF output

## Supporting Files

- `figure_legends.md`
- `submission_package_checklist.md`
- `tables_for_manuscript.docx`

## Registry Dependencies

The manuscript must resolve claims through registries:

- `result_registry.json` for numeric results
- `table_registry.json` for table numbering and placement
- `figure_registry.json` for figure numbering and captions
- `citation_registry.json` for literature-backed narrative

## Claim Discipline

- Title, abstract, and discussion must not exceed the selected mode.
- Methods must be traceable to the protocol and SAP.
- Results must come from the analysis registry only.
