# Analysis method and dependency rules



---

# Method Selection Rules

Method choice is no longer a pure keyword-detection problem.

Choose methods from the combination of:

- requested estimand
- outcome family
- exposure form
- survey design availability
- missing-data path
- adjudication outcome
- stage contract
- dependency availability

## Mainline Defaults

- Binary outcome + PR target: `weighted_modified_poisson_pr`
- Binary outcome + OR target: `logistic_regression_or`
- Continuous outcome: `weighted_linear_model`
- Ordered outcome: `ordinal_model`
- Material missingness + MI-ready path: `mi_survey_pooling_wrapper`
- Interaction: only when a modifier candidate exists and adjudication does not block it
- Dose-response: only for continuous or ordinal exposures
- Adjusted predictions / contrasts: add `adjusted_predictions_contrasts` when the objective requests marginal outputs
- Balance output family: add `balance_assessment_bundle` when weighting or balance reporting is part of the contract

## Common Extended Activation

- Multinomial outcome: only when 3+ observed nominal levels are available and adjudication approves `multinomial_nominal`
- Bounded outcome: only when the outcome is empirically bounded on 0-1 and adjudication approves `bounded_proportion`
- Clustered cross-sectional path: only when a cluster/group identifier exists and adjudication approves `clustered_gee`
- Count outcome: only when the outcome is non-negative integer-like and adjudication approves `count_outcome`
- Zero-inflated / hurdle path: only when excess-zero handling is explicitly requested and adjudication approves `zero_inflated_count`
- Calibration/performance outputs: only when the contract requests prediction-style reporting or performance metrics

## Design Rules

- `survey_full`: weights + PSU available
- `survey_weight_only`: weights available, PSU unavailable, rule permits degraded path
- `sample`: no design-based path available or required

## Missing-Data Rules

- low missingness: simplified missingness stage may be acceptable
- material missingness + explicit MI request: full missingness path
- material missingness without MI-ready setup: degraded with deviation

## Forbidden Substitutions

- Do not silently replace PR with OR
- Do not fake a survey path when weights are absent
- Do not open interaction or dose-response merely because templates exist
- Do not activate extended families merely because a package is installed
- Do not let family-specific extractors write fields outside the canonical result schemas

## Source Priority

When implementing or refactoring a family:

1. CRAN Task Views
2. official vignettes / pkgdown
3. CRAN manuals
4. package examples / tests
5. blogs only as auxiliary references


---

# Methods Catalog

This catalog is a **method-family map** for the execution framework.

## Default Mainline

| Family | Typical Use | Canonical Schemas | Primary Packages | Fit / Extract / Render Anchors |
|---|---|---|---|---|
| `prevalence_descriptive` | Weighted descriptive summaries, prevalence, Table 1, SMD | `prevalence_descriptive_result` | `survey`, `tableone`, `gtsummary` | `assets/r_methods.R` |
| `binary_pr` / `binary_or` | Binary outcome with PR or OR target | `binary_association_result` | `survey`, `stats`, `sandwich` | `assets/r_methods.R` |
| `continuous_linear` | Continuous outcome, weighted or sample-based linear path | `continuous_association_result` | `survey`, `broom` | `assets/r_methods.R` |
| `continuous_mi_weighted` | MICE + weighted pooling path | `continuous_association_result`, `binary_association_result` | `mice`, `survey`, `miceafter`, `miceadds` | `assets/r_methods.R` |
| `ordinal_clm` | Ordered outcome mainline path | `ordinal_association_result` | `ordinal` | `assets/r_methods.R` |
| `interaction_bundle` | Prespecified effect modification | main outcome schema + marginal effect schema | `emmeans`, `marginaleffects`, `survey` | `assets/r_methods.R` |
| `dose_response_bundle` | Continuous or ordinal exposure nonlinearity / trend | main outcome schema + marginal effect schema | `rms`, `survey` | `assets/r_methods.R` |
| `sensitivity_bundle` | CCA, alternate adjustment, coding sensitivity | schema follows linked primary family | base + project methods | `assets/r_methods.R` |
| `adjusted_predictions` | Adjusted means, probabilities, contrasts, slopes | `marginal_effect_prediction_result` | `marginaleffects` | `assets/r_methods.R` |
| `balance_assessment` | Weighted balance diagnostics and SMD outputs | `prevalence_descriptive_result` | `cobalt` | `assets/r_methods.R` |

## Common Extended

| Family | Typical Use | Canonical Schemas | Primary Packages | Activation Rule |
|---|---|---|---|---|
| `multinomial_nominal` | Nominal multicategory outcome | `multinomial_association_result` | `nnet` | Only when adjudication confirms 3+ outcome levels and explicit contract support |
| `bounded_proportion` | Outcomes constrained to 0-1 | bounded or continuous schema rows | `betareg` | Only when observed values are bounded and model intent is explicit |
| `clustered_gee` | Clustered cross-sectional marginal path | binary / continuous / count schema | `geepack` | Only when a cluster identifier or compatible grouping structure exists |
| `count_outcome` | Count outcomes without excess-zero branch | `count_association_result` | `MASS` / base Poisson | Only when outcome is non-negative integer-like |
| `zero_inflated_count` | Count outcomes with structural zeros | `count_association_result` | `glmmTMB` | Only when zero inflation is plausible and adjudication permits |
| `domain_analysis` | Survey subpopulation/domain estimates | linked mainline schema | `survey`, `srvyr` | Only when a domain variable is explicitly requested |
| `calibration_performance` | Prediction-style reporting, calibration, discrimination | `diagnostic_result`, `marginal_effect_prediction_result` | `marginaleffects`, `psfmi` | Only when prediction/performance output is requested |

## Outside The Bundle

Families outside the mainline and common-extension tables are intentionally not
shipped as executable templates. Record the request as a specialized
extension and stop for explicit implementation and review.

## Source Priority

When adding or refactoring a method family, use this source order:

1. CRAN Task Views
2. Official vignette or pkgdown reference
3. CRAN reference manual
4. Package examples or tests
5. Blogs only as auxiliary material

## Notes

- A family can be declared without being default-enabled.
- Adjudication decides activation; template existence does not.
- New families must plug into `fit -> extract -> render -> registry -> audit`.
- Shared fit, extraction, diagnostics, plotting, and registry helpers live in
  one private file so the public method library stays easy to scan.


---

# Dependency Strategy

Dependency handling is part of adjudication, not an afterthought.

## Default Mainline Required

These package families are treated as default-mainline dependencies:

- `survey` / `srvyr`
- `mice`
- `gtsummary` or `tableone`
- `modelsummary`
- `marginaleffects`
- `rms`
- `ordinal`
- `cobalt`

If one of these is missing, the system must not silently continue with an undocumented substitute. The allowed outcomes are:

- explicit simplified path with deviation
- hard fail

The choice depends on the stage contract and adjudication rules.

## Common Extended

These packages are optional until a common extended family is activated:

- `nnet`
- `betareg`
- `geepack`
- `glmmTMB`
- `psfmi`
- `miceafter`
- `miceadds`

If a family is activated and its package is absent:

- use `degraded_with_deviation` only when the contract explicitly allows fallback
- otherwise `fail`

## Outside The Bundle

Methods outside the mainline and common-extension tables are not assumed to be
production-ready merely because a package is installed. They require an
explicit implementation, contract entry, adjudication approval, and
method-specific validation before release.

## Non-Negotiable Rule

Environment differences must not silently change the executed method family.


---

# Real-data execution lessons and required gates

These rules are normative for real cross-sectional data, especially multisource
or incompletely specified complex-sample studies.

## Data quality and feasibility

Profile the full file before model selection. Record row/column counts; candidate
IDs and duplicates; parsing failures; raw category levels; missing codes;
unit/range plausibility; source conflicts; cluster/stratum nesting; weight
missingness, zeros, negatives, concentration and effective sample size; outcome,
exposure and covariate availability by objective; and support for requested
interactions or spline terms. A passed file-read is not feasibility.

Feasibility decisions are objective-specific. Separate:

- point-estimation support;
- variance-estimation support;
- target-population extrapolation support.

Supplied weights without PSU/strata information may support weighted point
descriptions but do not create design-based standard errors or province-level
representativeness. Captions and conclusions must state the supported scope.

## Variable and population contracts

Retain raw categories and analytic recodes as separate registered fields. Freeze
mapping, reference levels, missing rules, units, contrast, and derivation source.
Before M0/M1/M2 comparisons, freeze a common support set and record both the
common-sample n and any model-specific n. Never let a later model appear to
change because its denominator changed silently.

## Missing data, dose-response, and interaction

Multiple imputation requires trace/distribution diagnostics, logged events,
Monte Carlo adequacy, and pooling evidence. A failed diagnostic blocks pooled
interpretation. Dose-response requires frozen knots/reference/support, overall
and nonlinearity tests, prediction grid and extrapolation checks. Interaction
requires the product-term test plus marginal/stratum estimates and uncertainty;
separate subgroup p values do not establish interaction.

## Report delivery and artifact integrity

Use `scientific_final`, `provisional_blocked_review`, or `demonstration_only`.
A real-data report with unresolved design variance or inferential adequacy is
provisional, not a demonstration. It may report supported descriptive results
while prominently retaining the blocker and prohibiting unsupported inference.

Every registered table and figure records its source hash. Figures link to the
source table identifiers that generated them. Validate Markdown image paths,
registry membership, hashes, one-time main-text embedding and numbering before
DOCX/PDF export. Then render every PDF page and inspect fonts, clipping, blank or
near-blank pages, wide-table type size, figure legibility and caption placement.

