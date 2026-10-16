---
name: cross-sectional-manuscript-writer
description: Write and validate cross-sectional manuscripts from frozen protocol, analysis, result, table, figure, and citation evidence.
---

# Cross-Sectional Manuscript Writer

Write publication prose from frozen upstream evidence. The manuscript is not a
place to repair missing design or analysis.

## Workflow

1. Resolve and hash the available review, protocol, estimand, SAP, analysis,
   release-quality, result, table, figure, citation, and binding-map inputs.
2. Declare project mode, manuscript mode, claim ceiling, target journal, and
   deliverables.
3. Bind claims to allowed registry IDs.
4. Draft the scaffold, then write Introduction, Methods, Results, and
   Discussion from their permitted sources.
5. Run contract, mode, registry-binding, body-quality, and placeholder checks.
6. Export only after checking DOCX/PDF pagination, tables, figures, captions,
   and references.

Read [references/manuscript_standard.md](references/manuscript_standard.md) for
the compact rules and [references/manuscript_quality.md](references/manuscript_quality.md)
for mode, writing, output, and body-quality details. Use
[contracts/manuscript_contract.json](contracts/manuscript_contract.json) as the
minimum contract field set.

The executable scaffold, package, table-export, contract, registry-binding,
and mode-audit stages remain in `scripts/`; keep them together because each
checks a different release boundary.

## Boundaries

- Never invent numbers, citations, ethics approval, registration, funding,
  authorship, tables, or figures.
- Never turn association into causation or OR into PR/RR.
- Describe only executed methods and label departures from the SAP.
- Every numeric sentence must resolve to a result, table, or figure registry
  row.
- Label synthetic, pilot, and workflow-method outputs; do not present them as
  population evidence.
