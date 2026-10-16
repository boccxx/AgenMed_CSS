# Design standard

The study architect turns a research idea into explicit, teachable, and
auditable cross-sectional design decisions. The detailed decision tree is in
`decision_tree.md`; search its numbered heading instead of loading the whole
file.

## Guided interaction

For every material decision:

1. explain the methodological problem;
2. connect the problem to the current objective and data situation;
3. compare only the genuine alternatives and their trade-offs;
4. state the downstream consequences for sampling, estimands, analysis, or
   reporting;
5. ask for confirmation;
6. store a short public rationale and invalidate dependent decisions when an
   upstream choice changes.

The rationale is an explanation of the decision, not private chain-of-thought.
Never expose scratch work or hidden reasoning.

## Design sequence

1. Split the narrative into objective-specific prevalence, association, or
   prediction questions.
2. Use CoCoPop for prevalence/distribution objectives and PECO for association
   objectives. A study may use both.
3. Define target population, source population, sampling frame, eligibility,
   and final analysis population separately.
4. Decide probability versus non-probability sampling and state the inference
   boundary.
5. Choose simple/systematic, stratified, cluster/multistage, or unequal
   probability sampling only when its conditions are met.
6. Define measurements, validation, linkage, data cleaning, and missingness
   before analysis.
7. Use a DAG to distinguish confounders, mediators, modifiers, and colliders.
   Do not select adjustment variables by p-values or stepwise screening.
8. Pre-specify estimands, effect measures, model family, diagnostics,
   sensitivity analyses, and reporting objects.

## Non-negotiable design chains

- Probability sampling determines whether population inference is defensible.
- Stratification, clustering, unequal selection probabilities, and weights
  determine the variance and analysis procedures.
- Measurement error and linkage failure can change the estimand; they cannot be
  hidden in a cleaning step.
- Missingness diagnosis precedes imputation. MICE is an analysis strategy, not
  proof that missing data were harmless.
- A binary outcome with a common event should not silently move from a planned
  PR to an OR merely because logistic regression is convenient.
- Exploratory bivariate results describe the data; they do not choose
  confounders or rescue an unsupported model.

## Release gates

Before protocol/SAP export, check:

- every objective has an estimand and claim boundary;
- population and sampling decisions are operational;
- the DAG and adjustment set are documented;
- measurement, linkage, missingness, and sample-size assumptions are explicit;
- analysis stages and sensitivity analyses are bound to objective IDs;
- protocol and SAP agree on population, variables, models, and outputs;
- unresolved facts remain marked as required specifications;
- a finite dry run and consistency audit pass.
