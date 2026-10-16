# Analysis report, registry, and release rules



---

# Output Standards

The output stack is:

1. contracts
2. stage outputs
3. registries
4. frozen registries
5. report/docx/pdf
6. `analysis/output/report_release_quality_audit.json`

Reports are delivery artifacts, not the source of truth.

## Minimum Required Artifacts

- `analysis/contracts/requested_analysis_plan.json`
- `analysis/contracts/executable_analysis_plan.json`
- `analysis/contracts/analysis_core_contract.json`
- `analysis/contracts/objective_execution_map.json`
- `analysis/stage_contracts/*.json`
- `registries/result_registry.json`
- `registries/table_registry.json`
- `registries/figure_registry.json`
- `registries/diagnostic_registry.json`
- `registries/deviation_registry.json`
- `registries/decision_registry.json`
- `analysis/frozen/freeze_manifest.json`

## Report Rule

Report generation must happen only after registry freeze.

The report should read like a formal statistical analysis report rather than a pipeline transcript. It should:

- state study purpose before stage details
- summarize main methods before result interpretation
- distinguish expected analysis content from executed content
- give each active stage an overview, findings, and implications

## Main-Text Traceability

Every main-text estimate, table, and figure must trace to:

- one `objective_id`
- one `stage_id`
- one frozen registry row

## Presentation Rule

Main-text report artifacts must be rendered in publication style:

- tables use three-line formatting
- table captions appear above tables
- table notes appear below tables
- figure captions appear below figures
- figure legends appear below captions when applicable
- report-facing numbering uses sequential `Table 1`, `Figure 1`, etc., while registry IDs remain internal trace keys
- Markdown, Word, and PDF must embed substantive main-text table contents and figures rather than listing captions alone
- scientific delivery requires `scientific_pass`; `provisional_pass` authorizes only a real-data review artifact with the final-inference blocker banner and explicit blockers; a `demonstration_pass` report must carry the demonstration banner in every format

## Canonical Schema Rule

Result rows must use the canonical schema catalog. New method families are not allowed to introduce ad hoc result columns outside the declared schemas.

## Figure Traceability

Every main-text figure must carry:

- one stable `figure_id`
- one `objective_id`
- one `stage_id`
- one or more `source_result_ids`


---

# Report Writing Principles

This skill's final long-form statistical analysis report should borrow from the strongest parts of:

- ICH E3 clinical study report structure
- STROBE-style observational reporting logic
- observational SAP prespecification discipline
- publication-quality figure and table guidance

Reference anchors:

- ICH E3 Structure and Content of Clinical Study Reports
- STROBE Explanation and Elaboration
- A Statistical Analysis Plan Template for Observational Studies
- figure and table guidance emphasizing informative displays over display quantity

The goal is not to imitate any single template mechanically. The goal is to write a report that is:

- easy to review
- explicit about study purpose and estimand
- design-aware
- stage-aware
- interpretation-aware
- traceable to frozen evidence objects

## Structural Principles

The report should move in this order:

1. study type
2. executive summary
3. study purpose
4. main methods
5. expected analysis content
6. stage-by-stage analytic narrative
7. diagnostics and interpretation boundary
8. decisions and deviations
9. discussion
10. conclusion

## Writing Principles

- Start by explaining why the analysis exists before listing what was done.
- Explain how the requested plan became the executable plan.
- State the realized design, not just the requested design.
- For each analytic stage, separate:
  - overview
  - key findings
  - analytical implications
- Treat tables and figures as evidence objects, not decoration.
- Keep confirmatory, supportive, and exploratory claims distinct.
- Make every interpretation conditional on design, missingness, and adjudicated deviations.

## Display Principles

- Tables should be publication-style three-line tables.
- Table captions should explain what the table contributes, not repeat the filename.
- Table notes should clarify scale, summaries, and interpretation limits.
- Figure captions should identify the estimand or display purpose.
- Figure legends should explain how to read the geometry, intervals, and grouping.

## Interpretation Principles

- Primary results should be interpreted on the declared estimand scale.
- Descriptive and bivariate results should motivate, not replace, multivariable interpretation.
- Sensitivity analyses should be framed as robustness checks.
- Diagnostics should bound interpretation, not stand alone as conclusions.
- Deviations should be visible and justified.

## Reporting Tone

- Write like a statistical analysis report, not like a pipeline log.
- Avoid internal system language in the final prose when possible.
- Avoid dumping raw registry IDs into the narrative.
- Prefer readable stage titles, readable table/figure references, and methodologically explicit prose.


---

# Statistical Analysis Report Release Standard

Use this reference when producing or validating the final analysis report. It applies ICH E3's integrated-completeness principle and STROBE's cross-sectional reporting logic without pretending that an observational analysis report is a regulatory clinical study report.

## Release classes

Declare exactly one `analysis_release_mode` and one `report_delivery_class` in `analysis/contracts/execution_state.json`.

- `scientific_release` permits scientific conclusions only after every gate below passes.
- `demonstration_only`, `simulation_only`, and `smoke_test_only` permit workflow verification only. Display `DEMONSTRATION ONLY — NOT FOR SCIENTIFIC INFERENCE` at the start of every rendered format. Describe estimates as illustrative outputs and suppress substantive conclusions.

Delivery classes are `scientific_final`, `provisional_blocked_review`, and `demonstration_only`. Use `provisional_blocked_review` for genuine real-data work whose supported descriptive output is useful but whose final inference is blocked. Display `PROVISIONAL — NOT FOR FINAL SCIENTIFIC INFERENCE`, enumerate the blockers, and do not convert the report to a demonstration. `provisional_pass` means that the provisional boundary is truthful; it is not scientific release.

Registry freeze means the evidence objects are stable. It does not establish sample adequacy, inferential correctness, report completeness, or scientific release.

## Inferential result contract

For each estimate, register:

- population and analytic N
- outcome and scale
- exposure term, unit, and contrast
- model family and link
- exact adjustment set
- effect measure and whether it is exponentiated
- estimate, standard error, interval endpoints, p value, and confidence level
- one shared reference distribution for interval and p value
- degrees of freedom when a t, F, or design-based reference applies
- sidedness and critical value
- source model and source table

Reject mixed-reference inference. In particular, do not construct a 95% interval with `1.96×SE` when the reported p value uses a small-sample t distribution. Do not label a logit-link coefficient as a raw outcome change. Add a marginal contrast or predicted-value difference when interpretation on the response scale is needed.

## Execution-language evidence

Permit these words only with matching evidence:

- `weighted`: non-empty weight variable and executed survey/weighted model path
- `adjusted`: non-empty registered adjustment set present in the fitted formula
- `imputed`: executed imputation and pooling metadata
- `interaction` or `subgroup`: registered interaction term, support counts, and multiplicity boundary
- `diagnosed` or `passed diagnostics`: named diagnostic values, thresholds or interpretation rules, and actions

An unweighted sample summary must never receive a generated `weighted` caption.

## Scientific report body

Use 4,000 language-aware content units (CJK characters plus Latin word tokens) and 12 substantive paragraphs as the hard release floor for an ordinary real study. Let study complexity, not filler, determine the final size. A substantive paragraph must add a number, evidence object, assumption, decision, limitation, or consequence.

Cover:

1. executive summary containing N, estimand, main estimate, interval, and bounded conclusion
2. objectives, hypotheses, population, setting, dates, and design realization
3. participant/sample reconciliation and exclusions
4. variable definitions, coding, ranges, quality control, and analysis sets
5. complete missingness profile and realized handling
6. descriptive distributions and denominators
7. crude and adjusted primary results with interpretable exposure contrasts
8. secondary, interaction, subgroup, or dose-response results when prespecified
9. model diagnostics and actions
10. at least three relevant sensitivity axes, each tied to the assumption changed and the impact on inference
11. deviations and their impact
12. interpretation, limitations, generalizability, conclusion, and reproducibility trace

Normally embed at least six substantive numerical tables: sample flow, variable/QC, characteristics, primary models, secondary or subgroup results, sensitivity matrix, diagnostics, and deviations as applicable. Normally embed at least three informative figures: participant flow, distributions, exposure-response or marginal effect, and diagnostic/influence visualization as applicable. Record a study-specific release exception when an item is genuinely inapplicable.

## Scientific hard stops

Block scientific release when:

- the decision identity or release mode is unresolved
- inferential adequacy lacks a pass decision and rationale
- a required result lacks coherent inference metadata
- diagnostics omit sample/df, fit, residual, influence, or functional-form evidence
- fewer than three independent sensitivity axes are tested or justified as inapplicable
- main tables are merely named rather than embedded
- unsupported execution language appears
- the body is below the hard floor
- padding, placeholders, or invented study facts are detected


---

# Registry Hardening

Registries are the fact layer.

Required registries:

- `result_registry.json`
- `table_registry.json`
- `figure_registry.json`
- `diagnostic_registry.json`
- `deviation_registry.json`
- `decision_registry.json`

## Rules

1. Reports consume registries; they do not invent facts.
2. Registry freeze is a separate stage.
3. Every degrade/skip must appear in both decision and deviation artifacts when applicable.
4. Canonical results must be schema-valid before freeze.
5. A result must trace to exactly one objective and one stage.


---

# Identity And Versioning

Use these identifiers consistently across contracts, registries, audits, and reports.

- `objective_id`: `OBJ###`
- `stage_id`: fixed stage names such as `primary_model_stage`
- `decision_id`: `DEC###`
- `deviation_id`: `DEV###`
- `result_id`: `R_OBJ###_###`
- `table_id`: `T_OBJ###_###`
- `figure_id`: `F_OBJ###_###`
- `contract_version`: semantic contract family version such as `2.2-final`
- `schema_version`: semantic schema version such as `2.2-final`
- `freeze_version`: `FREEZE_YYYYMMDD_HHMMSS`

Rules:

- A frozen registry set must carry one `freeze_version`.
- Every `result_id` must trace to exactly one `objective_id` and one `stage_id`.
- Every report citation to a table or figure must use a stable `table_id` or `figure_id`.
