---
name: cross-sectional-literature-review
description: Build an auditable literature review that informs cross-sectional study design, analysis, and manuscript claims.
---

# Cross-Sectional Literature Review

Turn evidence into traceable decisions. A paper list or generated summary is
not a completed review.

## Workflow

1. Resolve population, setting, exposure/comparator, outcomes, design,
   question type, review goal, date/language limits, and the downstream
   decision.
2. Define eligibility before retrieval. Record exact sources, queries, dates,
   limits, hit counts, retained counts, and blocked access.
3. Deduplicate records and record an exclusion reason for every screened item.
4. Appraise design, measurement, bias, directness, and applicability.
5. Extract evidence rows and verify citation identity before writing prose.
6. Synthesize by evidence role and uncertainty, then build the protocol bridge.
7. State what is complete, blocked, downgraded, and still unsafe to decide.

Read [references/review_standard.md](references/review_standard.md) for the
entry rules, then load the relevant detail:

- retrieval and evidence collection:
  [references/review_search.md](references/review_search.md)
- appraisal, synthesis, schemas, and delivery:
  [references/review_synthesis.md](references/review_synthesis.md)

The executable stages remain in five focused scripts:

- `scripts/retrieval.py`: `build_search_plan`, `run_live_search`, `chase_citations`;
- `scripts/evidence.py`: `run_fulltext_extraction`, `score_candidates`, `verify_citations`;
- `scripts/review.py`: scaffold, snapshot, narrative, and proposal-bridge commands;
- `scripts/validation.py`: semantic and package validation;
- `scripts/export.py`: narrative export and publication packaging.

Run the narrowest command that matches the current stage; do not rebuild these
steps in prose.

## Delivery

- `brief`: traceable search/screening records and a short briefing;
- `decision_grade`: evidence registries, sufficiency judgment, and protocol
  inputs;
- `full_package`: decision-grade outputs plus citation verification and export.

Do not fabricate search counts, full-text reading, estimates, citations, or
certainty. Cross-sectional evidence supports prevalence or association claims,
not temporality or causal effects.
