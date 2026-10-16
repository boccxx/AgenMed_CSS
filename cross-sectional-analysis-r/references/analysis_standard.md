# Analysis standard

This skill supports cross-sectional analysis from a declared protocol and SAP.
It does not turn a contract or a generated table shell into executed evidence.

## Modes

Use `research`, `applied_methods`, or `workflow_methods`. Record whether the
run is a scientific release, demonstration, simulation, or smoke test.

## Stage order

1. QC and data profile
2. missingness diagnosis and declared handling
3. descriptive distributions and Table 1
4. bivariate description
5. primary objective-specific model
6. prespecified interaction or dose-response
7. sensitivity analyses
8. result, table, figure, and deviation registries
9. freeze and report

Every stage is `required`, `conditional`, `not_applicable`,
`blocked_by_data`, or `degraded_with_deviation`. Record the path as full,
simplified, or degraded.

## Method rules

- Use the sampling design, weights, strata, clusters, and degrees of freedom
  actually used. A fixed-site sample cannot silently support a broad
  representativeness claim.
- For common binary outcomes, prefer a prespecified PR path when the estimand
  is prevalence ratio. Use OR only when the estimand and interpretation are
  explicitly odds-based.
- Keep a common support set for model comparisons and record exclusions.
- Diagnose functional form, sparse cells, convergence, influence, collinearity,
  and variance stability before release.
- Test interaction terms directly and report marginal estimates; do not compare
  subgroup p-values as a substitute.
- For missing data, inspect patterns and variables related to missingness before
  selecting complete-case, weighting, or multiple-imputation paths.

## Bundled assets

- `assets/r_methods.R` contains the shared helpers, mainline templates, and
  common extended method implementations.
- `contracts/methods.json` lists the bundled mainline and common-extension
  method families.

Specialized methods are not silently substituted. If a requested method is not
bundled, record it as an explicit extension and write or validate the method
against the declared estimand and design.

## Release gate

Do not call an analysis complete unless real outputs, diagnostics, provenance,
and registry rows exist at the declared paths. Freeze only after:

- every required objective has a result or a declared blocking reason;
- result/table/figure IDs resolve;
- deviations and analytic decisions are recorded;
- the report cannot change frozen results;
- the interpretation stays within cross-sectional limits.
