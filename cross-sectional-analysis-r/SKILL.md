---
name: cross-sectional-analysis-r
description: Plan, execute, audit, and report cross-sectional analyses in R while keeping estimands, design constraints, outputs, and claims traceable.
---

# Cross-Sectional Analysis R

Use this skill after the protocol and SAP have declared the objective,
estimand, population, sampling design, and analysis path. A plan or table shell
is not executed evidence.

## Workflow

1. Profile identifiers, ranges, units, duplicates, missingness, and sampling
   variables without overwriting raw data.
2. Lock the stage order: QC, missingness, descriptive, bivariate, primary
   model, prespecified interaction/dose-response, sensitivity, registries,
   freeze, and report.
3. Apply the sampling design, weights, strata, clusters, and variance estimator
   that the protocol requires.
4. Choose the model from the estimand and outcome type. Do not silently replace
   PR with OR, or use bivariate p-values to select confounders.
5. Check support, convergence, functional form, sparse cells, influence,
   collinearity, and variance stability.
6. Write real tables, figures, diagnostics, provenance, deviations, and result
   registry rows before calling a stage complete.
7. Freeze only when every required objective has a result or a declared
   blocking reason.

Read [references/analysis_standard.md](references/analysis_standard.md) for
the compact release rules. Load
[references/methods_and_dependencies.md](references/methods_and_dependencies.md)
for method selection and package constraints, and
[references/report_and_release.md](references/report_and_release.md) for report
and registry release checks. All bundled R methods, including common
extensions, are in [assets/r_methods.R](assets/r_methods.R); their catalog is
[contracts/methods.json](contracts/methods.json).

The Python orchestration stages remain in five focused scripts:
`analysis_plan.py` for feasibility, plans, and contracts;
`analysis_registry.py` for registry construction and freezing;
`analysis_report.py` for report rendering and DOCX generation; and
`analysis_audit.py` for pipeline, artifact, and PDF audits. The retained
`analysis_common.py` contains shared helpers. The R asset contains the shared
helpers plus mainline and common extended entry points; it is consolidated for
reuse, not reduced to a toy subset.

## Modes

Use `research`, `applied_methods`, or `workflow_methods`. Record whether the
run is a scientific release, demonstration, simulation, or smoke test.

## Boundaries

Do not label a contract-only, scaffold-only, or failed run as a completed
analysis. Do not let a report alter frozen registries. Keep all interpretation
within cross-sectional limits.
