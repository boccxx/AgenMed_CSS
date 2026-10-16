---
name: cross-sectional-study-architect
description: Teach and freeze cross-sectional study-design decisions, then produce an aligned protocol and SAP without inventing unresolved facts.
---

# Cross-Sectional Study Architect

Design the study before writing the document. The decision tree in
[references/decision_tree.md](references/decision_tree.md) is the
methodological source of truth.

## Guided decisions

For each material node:

1. explain the problem the node solves;
2. connect it to the current study and objective;
3. compare real alternatives and trade-offs;
4. explain downstream effects on sampling, estimands, analysis, and reporting;
5. ask for confirmation;
6. record a concise public rationale and invalidate dependent choices when an
   upstream decision changes.

Do not expose private chain-of-thought or scratch work.

## Main sequence

1. Split the idea into objective-specific prevalence, association, or
   prediction questions.
2. Use CoCoPop for prevalence/distribution and PECO for association. Both may
   be active in one study.
3. Define target population, source population, sampling frame, eligibility,
   and final analysis population.
4. Choose the sampling design and state the inference boundary.
5. Define measurements, validation, linkage, data cleaning, and missingness.
6. Use a DAG to distinguish confounders, mediators, modifiers, and colliders.
7. Pre-specify estimands, models, diagnostics, sensitivity analyses, and
   reporting objects.
8. Check protocol/SAP consistency and export only after the release gates pass.

Read [references/design_standard.md](references/design_standard.md) for the
compact rules and [references/protocol_standard.md](references/protocol_standard.md)
for intake, guided interaction, protocol, and SAP writing details. Use
[assets/generate_dag.R](assets/generate_dag.R) only when a project needs a
rendered DAG.

The complete decision tree is retained in
[references/decision_tree.md](references/decision_tree.md). Executable stages
are grouped into four scripts: `design_intake.py` for intake adaptation and
guided decisions, `design_build.py` for contracts, registries, preflight, and
blueprints, `design_documents.py` for protocol/SAP writing and export, and
`design_audit.py` for consistency, prose, SAP, and dry-run audits.
Use their subcommands instead of duplicating workflow logic in the prompt.

## Boundaries

- Never choose confounders by univariate p-values or stepwise screening.
- Stratification, clustering, unequal selection probabilities, and weights
  determine the analysis path and variance estimation.
- Do not silently turn a fixed-site sample into a population-representative
  claim.
- Leave unknown consequential facts as explicit required specifications.
- Do not export a protocol or SAP when an estimand, population, adjustment set,
  sample-size basis, or analysis path remains unresolved.
