# Literature review: synthesis and delivery



---

# Scoring Rubric

Use four independent evaluation dimensions rather than a single paper-level total.
A single score cannot distinguish a paper whose primary finding is trustworthy from
one whose main contribution is only background framing.

---

## Dimension 1: Record Relevance (0–5)

Used at the candidate screening stage to decide whether a record advances to full reading.

| Score | Meaning |
|---|---|
| 5 | Directly answers the question (population, exposure, comparator, outcome all match) |
| 4 | Strong match on 3 of 4 elements; minor population or outcome drift |
| 3 | Answers a closely related question; useful for measurement, mechanism, or confounder logic |
| 2 | Loosely related; may provide background context or methods signal only |
| 1 | Peripheral; keep only if it fills a specific documented gap |
| 0 | Not relevant; exclude |

**Threshold:** records scoring ≥ 3 advance to full reading. Records scoring ≥ 4 are
candidates for the main synthesis. Records scoring 1–2 may be retained as context or
measurement support but must be labelled as such.

---

## Dimension 2: Study Credibility (strong / adequate / limited / weak)

Applied after full reading. Reflects how much evidential weight the study can carry
for downstream design, analytic, or interpretive decisions.

| Label | Criteria |
|---|---|
| strong | Well-executed study design; explicit confounder rationale; transparent sample; outcome ascertainment validated; findings triangulated |
| adequate | Sound design; adequate confounder handling; some limitations acknowledged; interpretations appropriate for design |
| limited | Relevant findings but notable design weakness, convenience sample, or missing confounder detail; useful for context, not for anchoring decisions |
| weak | Severe design flaws, unexplained adjustment choices, or findings that overreach the design; use for background only or exclude |

---

## Dimension 3: Effect Trustworthiness (high / moderate / low / not_applicable)

Applied to each specific effect estimate cited from the paper.  A study can be
`adequate` overall while producing one trustworthy main-analysis estimate and one
low-trustworthiness subgroup estimate.

| Label | Criteria |
|---|---|
| high | Primary pre-specified analysis; adequate adjustment set; time zero clear; comparator interpretable; confidence interval reported; no major bias detected |
| moderate | Estimate is informative but one concern is present (e.g., residual confounding likely, or this is a secondary analysis, or preprint status) |
| low | Notable bias threat (immortal time, prevalent user bias, confounding by indication, etc.); or estimate is from a subgroup not pre-specified; or adjustment set is inadequate |
| not_applicable | The paper does not report a quantitative effect estimate (e.g., methods paper, narrative review, prevalence-only study) |

When `effect_registry.csv` is populated, assign `trust_level` using this dimension,
not the overall study credibility label.

---

## Dimension 4: Claim Strength (definitive / suggestive / preliminary / background_only)

Controls the language strength allowed in the narrative for any given assertion.
Assign this dimension when populating `claim_registry.csv`.

| Label | Allowed narrative language | Required evidence base |
|---|---|---|
| definitive | "evidence demonstrates", "studies show" | ≥ 2 studies with high effect trustworthiness AND strong/adequate credibility; findings triangulated |
| suggestive | "evidence suggests", "findings indicate" | ≥ 1 study with high/moderate trustworthiness; direction consistent across available studies |
| preliminary | "preliminary evidence suggests", "limited data indicate" | Only one study, or findings from low-trustworthiness estimates, or preprints only |
| background_only | "has been described", "context indicates" | Background or context papers; not direct evidence for the claim |

**Enforcement rule:** the narrative builder must not use language stronger than the
`allowed_strength` recorded in `claim_registry.csv` for each claim.

---

## Mandatory Red Flags (apply across all dimensions)

Do not allow a high relevance score to override these:

- No clear exposure or outcome definition → cap `record_relevance` at 2
- Severe overclaiming beyond what the design supports → cap `study_credibility` at `limited`
- OR interpreted as RR/PR when outcome is common (> 10%) → cap `effect_trustworthiness` at `low`
- Adjustment for likely mediator or collider without justification → cap `effect_trustworthiness` at `low`
- No interpretable sample or setting → cap `study_credibility` at `weak`

---

## Publication-Status Adjustment

- Peer-reviewed primary studies and systematic reviews may reach any label if quality warrants.
- Preprints may reach `record_relevance` 5 and `study_credibility` adequate, but
  `effect_trustworthiness` is capped at `moderate` unless the peer-reviewed version is confirmed.
- When a preprint is used, record `publication_status = preprint` in the study registry
  and do not let it anchor a `definitive` claim alone.

---

## Migration Note

The former 0–100 total score (anchor 85+, core 70–84, etc.) is retired.
Reviewers who have existing registries using the old scale can map:

| Old band | New equivalent |
|---|---|
| 85–100 (anchor) | record_relevance 5, credibility strong, effect high |
| 70–84 (core) | record_relevance 4–5, credibility adequate, effect moderate–high |
| 55–69 (targeted support) | record_relevance 3–4, credibility adequate–limited |
| 40–54 (peripheral) | record_relevance 1–2 |
| < 40 | exclude |


---

# Study Quality Framework

## Purpose

This file defines how to assign evidential weight after topical relevance is established.

The goal is not to force a formal bias tool on every paper. The goal is to stop weak
but on-topic studies from carrying the same weight as stronger or more transferable evidence.

Assign credibility using `scoring_rubric.md` Dimension 2.  Use the bias checklists
in this file to inform that assignment and to populate `bias_registry.csv`.

---

## Design-Aware Weighting

### Evidence syntheses and prior reviews

- Prefer recent systematic reviews or umbrella reviews over unsystematic narrative reviews
- Check whether the review reports databases, search dates, inclusion criteria, and appraisal logic
- If a review is methodologically thin, treat it as background rather than decisive evidence

### Cross-sectional primary studies

Evaluate:

- target population fit
- exposure and outcome measurement validity
- confounder handling quality
- whether the estimand and interpretation are appropriate for a common outcome
- whether claims overreach the design

Well-measured cross-sectional studies are often highly useful for measurement,
prevalence framing, and confounder planning, but they remain weak for temporality.

### Cohort or case-control studies

- Use them to strengthen temporality logic or triangulate associations
- Check follow-up adequacy, exposure timing, outcome ascertainment, and loss-to-follow-up risk
- When these studies disagree with cross-sectional findings, surface the disagreement
  rather than averaging it away

### Measurement-validation studies

- Prioritize papers that report reliability, validity, threshold choice, or population-specific adaptation
- These papers may be more useful for protocol inputs than a loosely related association paper

### Trials or interventions

- Use mainly for mechanism plausibility, behavioral modification logic, or outcome responsiveness
- Do not over-import intervention logic into a purely observational estimand without explanation

### Preprints

- Use preprints as frontier signals, early methods signals, or niche-population evidence
- Flag them clearly as preprints or not-yet-peer-reviewed sources
- Verify metadata carefully because preprint records drift more often
- Do not let a single preprint anchor the main conclusion unless corroborating evidence exists
- If a preprint fills a key gap, say that the gap is provisionally addressed rather than
  definitively closed

---

## Bias Checklists by Study Type

Use these checklists to screen each included study and to populate `bias_registry.csv`.

The required columns in `bias_registry.csv` are:
`paper_id, bias_domain, severity, bias_direction, evidence_of_bias, reviewer_note`

`severity` values: `high / moderate / low / none_detected / unclear`
`bias_direction`: `towards_null / away_from_null / uncertain / not_applicable`

### Pharmacoepidemiology and Treatment Strategy Studies

Required when `question_type = treatment_strategy_comparison`.
Recommended for `exposure_outcome_association` with a drug or healthcare exposure.

| Bias domain | What to check |
|---|---|
| confounding_by_indication | Was the indication for starting/stopping treatment controlled for? Do sicker patients preferentially receive (or discontinue) the drug? |
| prevalent_user_bias | Were incident (new) users identified, or were prevalent users included? Prevalent users have survived an early adverse period, which biases results. |
| immortal_time_bias | Is time zero clearly defined? Is there a period between cohort entry and exposure definition when outcomes could not occur? |
| protopathic_bias | Was the exposure started in response to early symptoms of the outcome? |
| depletion_of_susceptibles | Does long follow-up compare survivors of early adverse effects in one arm against a mixed population in the other? |
| reverse_causation | Could the outcome precede the exposure in time? Is temporality assured by design? |
| measurement_timing_mismatch | Was the exposure window aligned with the outcome risk window? |
| selection_bias | Was the cohort entry rule or follow-up rule applied symmetrically across exposure arms? |
| overadjustment | Were mediators or colliders included in the adjustment set without explicit justification? |
| competing_risk | For non-mortality outcomes, was death or treatment switch addressed as a competing event? |

### Prognosis Studies (Cohort, Time-to-Event)

Recommended when `question_type = prognosis`.

| Bias domain | What to check |
|---|---|
| baseline_imbalance | Were prognostic factors distributed similarly at baseline? Was adjustment adequate? |
| follow_up_completeness | Was loss to follow-up differential by exposure or outcome status? |
| competing_risk | Was competing risk (e.g., death from other causes) handled appropriately? |
| measurement_timing_mismatch | Were predictors measured before the outcome risk period? |
| reverse_causation | Could early-stage disease have influenced the predictor measurement? |

### Diagnostic and Measurement Studies

Recommended when `question_type = diagnostic_measurement`.

| Bias domain | What to check |
|---|---|
| reference_standard | Was the reference standard adequate and independently applied? |
| verification_bias | Did all participants receive the reference standard regardless of index test result? |
| measurement_timing | Was the index test applied close in time to the reference standard? |
| spectrum_effect | Was the study population representative of the target clinical population? |

### Cross-Sectional Association Studies

Minimum expected when `question_type = exposure_outcome_association` and design is cross-sectional.

| Bias domain | What to check |
|---|---|
| reverse_causation | Can the temporal direction of the exposure-outcome relationship be established from the design? |
| overadjustment | Were intermediary variables (on the causal pathway) included in the adjustment set? |
| common_cause_confounding | Were major shared causes of both exposure and outcome controlled for? |
| OR_as_RR | For common outcomes (> 10%), is the OR being interpreted as a prevalence ratio or risk ratio? |

---

## When `bias_registry.csv` Is Required vs Recommended

| question_type + review_goal | bias_registry.csv requirement |
|---|---|
| treatment_strategy_comparison (any goal) | **Required.** Populate the pharmacoepi checklist for every included study. |
| treatment_strategy_comparison + decision_support or protocol_support | **Required and must be complete.** Severity must be assigned for all domains. |
| prognosis + decision_support or protocol_support | **Required.** Populate the prognosis checklist. |
| prognosis + other goals | Recommended. |
| exposure_outcome_association (cross-sectional) | At minimum: reverse_causation, overadjustment, OR_as_RR. |
| background_landscape (any question_type) | Optional. |
| mechanism_mediation | Optional, focus on overadjustment and reverse_causation. |

---

## Practical Appraisal Labels

Use the four-level credibility label from `scoring_rubric.md` Dimension 2:

- `strong`
- `adequate`
- `limited`
- `weak`

Assign based on the paper's actual contribution to the downstream decision,
not only its prestige or journal name.

---

## High-Value Signals

- validated exposure or outcome tool
- explicit confounder rationale using causal reasoning (not automatic stepwise adjustment)
- transparent sample and setting description
- effect measure compatible with study design
- limits stated honestly
- findings triangulated by other studies
- new user / active comparator design for drug studies

## Downgrade Signals

- exposure or outcome poorly defined
- convenience sample with unclear generalizability
- automatic covariate adjustment without causal reasoning
- odds ratios interpreted as if they were risk or prevalence ratios when the outcome is common
- strong causal language from cross-sectional evidence
- missing time zero in longitudinal studies
- no mention of competing risk in time-to-event analyses

---

## How To Use This Framework

1. Score record relevance and advancement with `scoring_rubric.md` Dimension 1.
2. Read the full paper.
3. Assign credibility label using `scoring_rubric.md` Dimension 2.
4. Run the appropriate bias checklist from this file.
5. Assign `effect_trustworthiness` per estimate using `scoring_rubric.md` Dimension 3.
6. Populate `bias_registry.csv` when required or recommended.
7. Let the credibility label and bias findings constrain the `claim_strength`
   (Dimension 4) used in `claim_registry.csv`.


---

# Review Type and Release Standard

## Contents

1. Product-type lock
2. Main-body architecture
3. Search and screening truth
4. Appraisal and deep-reading standard
5. Mature-topic release gate
6. Sparse-evidence exception

## 1. Product-type lock

Set exactly one `review_type` in `review_contract.json` before searching.

| Review type | Required route | Synthesis boundary |
|---|---|---|
| `structured_narrative` | SANRA quality aid plus transparent reproducible search | Thematic critical synthesis; do not claim systematic completeness unless achieved |
| `systematic_no_meta` | PRISMA 2020, PRISMA-S, SWiM | Group by prespecified design/outcome/directness; no vote counting by significance |
| `systematic_meta` | PRISMA 2020 and PRISMA-S | Quantitative model, effect harmonization, heterogeneity, influence and small-study-bias plan |

Put the selected frameworks in `reporting_framework` and name the actual approach in `synthesis_method`.

## 2. Main-body architecture

A mature decision-grade body should normally allocate:

- 500–650 words: importance, prior-review overlap, and exact question
- 450–700: reproducible methods
- 450–650: evidence map and study characteristics
- 1,200–1,500: direct evidence, separated by design and outcome
- 600–800: exposure/outcome measurement
- 400–600: mechanisms and evidence boundaries
- 900–1,100: risk of bias, heterogeneity, counterevidence, reporting bias, and certainty
- 550–750: ranked gaps and study-design consequences
- 150–250: conclusion

Embed populated Study Characteristics and Effect Evidence Matrix tables. The prose must interpret rather than repeat the tables.

## 3. Search and screening truth

An executed row requires a literal source query, date, limits, hit count, retained/downloaded count, and execution status. Preserve query syntax exactly enough to rerun. Reconcile all flow counts to the raw, deduplicated, screening, and included artifacts. Give every full-text exclusion a single primary reason code plus a specific explanation. Run a reading-triggered second round for measurement, confounding, mechanism, contradiction, or terminology.

Refresh the final search when older than six months. If refresh is impossible, set `older_search_cutoff_disclosed=true` and explain the resulting currency limitation in the body.

## 4. Appraisal and deep-reading standard

Mark deep reading only after the full text or an adequate authoritative report has been examined for population, design, measurement, analysis, estimates, and limitations. Record the date and source.

Appraise at least four study-specific domains for each included claim-bearing study. Select domains by design:

- cross-sectional: selection, exposure measurement, outcome measurement, confounding/overadjustment, reverse causation, estimand/reporting
- prospective: selection/attrition, baseline/time zero, changing exposure, outcome measurement, confounding, estimand/reporting
- evidence synthesis: search/screening, study-level bias assessment, synthesis method, heterogeneity, publication/reporting bias

Write a concrete `raw_signal` and `evidence_source` for each judgment. Repeated generic text is not appraisal.

Extract effects for at least 80% of direct/counterevidence studies. Use `NR` only after checking the full text; never turn missing estimates into null effects.

## 5. Mature-topic release gate

For `decision_grade` and `full_package`, require:

- at least 4,500 main-body words; target 5,500–6,500
- at least 30 identity-resolved references; target 45–70
- at least 12 documented deep-read studies; target 12–20
- nonempty study-specific appraisal
- exact search strings and reconciled screening counts
- populated main-body evidence tables
- counterevidence, heterogeneity, and outcome-specific certainty

The floors prevent a structured outline from being mislabeled as a complete review. They do not license repetition, citation dumping, or invented facts.

## 6. Sparse-evidence exception

Use only when the evidence base is genuinely sparse after reproducible saturation. Add:

```json
"sparse_evidence_exception": {
  "applies": true,
  "rationale": "Why fewer studies exist and why the smaller corpus is still informative",
  "search_saturation": "What sources, rounds, citation chains, and stopping evidence establish saturation",
  "scope_boundary": "The narrow population, exposure, outcome, design, language, or period boundary"
}
```

Release as a scoped evidence-gap review, not as a falsely comprehensive mature-topic review. The exception does not waive citation identity, appraisal, search truth, screening reconciliation, or anti-padding checks.


---

# Narrative Review Standard

This file defines the target style for `literature_review_synthesis.md`.

The intended target is a **SANRA-style medical narrative review**, not an evidence-map memo
and not a workflow explanation. `review_briefing.md` carries pipeline-facing material.
`literature_review_synthesis.md` carries reader-facing synthesis.

## Product Split

- `review_briefing.md`
  - evidence map / registry summary / audit trail
  - may mention tiers, anchors, claim registries, and package logic
- `literature_review_synthesis.md`
  - reader-facing narrative review
  - must foreground the literature, not the tool

## Hard Narrative Rules

1. Do not explain the system inside the review body.
   Prohibited examples:
   - "the workflow therefore..."
   - "this upgrade..."
   - "the system is designed..."
   - "v2.1..."
   - "anchor eligibility..."
   - "narrative readiness..."

2. Organize by the scientific question, not by the package.
   The reader should encounter:
   - why the question matters
   - what direct evidence exists
   - what indirect evidence adds
   - which outcomes can and cannot be interpreted
   - what the main literature limitations are
   - what gaps remain

3. Keep the main evidence layer clean.
   The main narrative should only retain:
   - direct strategy-comparison evidence
   - truly informative indirect support
   - a small amount of necessary guideline or policy background

4. Outcome sections should follow the same internal logic.
   Each outcome family should answer:
   - is there direct evidence?
   - what are the strongest anchor studies?
   - how strong is the conclusion?
   - what is the main limitation?

5. Use a few anchor studies, not long citation piles.
   A typical outcome section should rely on 2-4 key studies, not every retained record.

6. Methodological limits must be written as literature limits, not tool rules.
   Preferred:
   - "Discontinuation is often triggered by clinical deterioration, raising concern about confounding by prognosis."
   Avoid:
   - "The workflow therefore separates core_direct_strict from core_direct_broad."

7. Keep Search and Screening brief and late.
   One compact section is enough in the main review. Detailed execution belongs in
   `search_log.csv`, `search_strategy.md`, and `review_briefing.md`.

8. Conclusions should state what the literature supports, not what the package allows.

## Practical Structure

Recommended section order:

1. Clinical importance and review question
2. Direct comparative evidence
3. Broader supporting evidence
4. Outcome-specific interpretation
5. Methodological limits
6. Clinical interpretation and research gap
7. Search basis
8. References

The writing rules in this file are the default narrative blueprint unless the
user explicitly asks for a different review form.

## Paragraph-Level Rule

Each substantive evidence paragraph should usually follow this pattern:

1. scope judgment
2. 1-2 anchor studies
3. immediate limitation
4. bounded interpretation

This is the default antidote to paper-by-paper listing.

## Direct / Indirect / Guideline Separation

Use separate prose roles for each evidence layer:

- `direct comparative evidence`
  - supports the main direction-of-effect discussion
- `broader supporting evidence`
  - adds context, subgroup boundaries, or clinical plausibility
- `patient-centered evidence`
  - explains why discontinuation is considered and what trade-offs matter
- `guideline or policy evidence`
  - frames uncertainty and implementation gaps

Guidelines and prior reviews may inform the narrative but must not substitute for direct
comparative evidence.

## Introduction Rule

The opening should usually take three short paragraphs:

1. why the condition or treatment issue matters
2. why the decision is clinically difficult now
3. the exact review question and key outcomes

Do not open with search workflow, source lists, or screening counts.

## Conclusion Rule

The conclusion should always do three things:

1. state the most stable conclusion
2. state what cannot yet be generalized
3. state the most important next evidence need

Avoid conclusions that merely recap section order or restate package completeness.

## Internal Scoring Rubric

Use this to judge whether the draft reads like a mature narrative review:

- `narrative_form` (0-5)
  - does it read like a review article rather than an evidence brief?
- `core_evidence_purity` (0-5)
  - is the main evidence layer free of obviously irrelevant or low-directness studies?
- `synthesis_depth` (0-5)
  - does it synthesise across studies rather than list them?
- `claim_discipline` (0-5)
  - are claims appropriately constrained by the evidence?
- `readability` (0-5)
  - does the reader learn the field, rather than the pipeline?

Anything below roughly 18/25 should be treated as a drafting problem even if the package is structurally valid.


---

# Review Writing Blueprint

This file defines the default writing architecture for `literature_review_synthesis.md`.

The target is not "a summary with citations." The target is a mature review article that:

- opens with a real clinical or scientific problem
- organizes evidence by question and outcome family
- separates direct evidence from indirect support
- states limitations where they matter
- ends with a bounded conclusion rather than a generic recap

## Core Position

Write the review as a sequence of judgments supported by a small number of key studies.
Do not write it as a sequence of papers.

Each major paragraph should answer:

1. What does this evidence layer suggest?
2. Which 1-2 studies most justify that statement?
3. What is the main reason to be cautious?
4. How far can this conclusion be taken?

If a paragraph does not do those four things, it usually degrades into either:

- annotated bibliography style
- background exposition with no decision value
- workflow chatter

## Preferred Section Order

Use this order unless the question type strongly requires another structure.

1. `Clinical Importance and Review Question`
2. `Direct Comparative Evidence`
3. `Broader Supporting Evidence`
4. `Outcome-Specific Interpretation`
5. `Methodological Limits`
6. `Clinical Interpretation and Research Gap`
7. `Search Basis`
8. `References`

### Section Purpose

`Clinical Importance and Review Question`
- why the topic matters now
- why the continue/stop or exposure/outcome decision is clinically real
- what exact question the review answers

`Direct Comparative Evidence`
- only exact-match or near-exact-match studies
- should carry the main direction-of-effect discussion

`Broader Supporting Evidence`
- disease-specific, subgroup-specific, mechanism, setting-specific, or policy-adjacent evidence
- useful for context and boundaries, not for replacing direct evidence

`Outcome-Specific Interpretation`
- one subsection per outcome family
- each subsection answers: directness, anchors, conclusion strength, main limitation

`Methodological Limits`
- only limitations that materially change interpretation strength

`Clinical Interpretation and Research Gap`
- what is most defensible now
- what should not be overgeneralized
- what study design or data are needed next

`Search Basis`
- one short late section
- numeric and factual
- never the organizing spine of the document

## Standard Intro Pattern

The opening should usually take 3 short paragraphs:

1. Disease burden / clinical prevalence / why the population matters
2. Why the decision is difficult now
3. The exact review question and target outcomes

Do not open with search mechanics, source lists, screening counts, or workflow history.

## Standard Paragraph Pattern

The default evidence paragraph is a four-move unit:

1. `Scope sentence`
   Example shape: "The most direct evidence comes from..."

2. `Anchor-study sentence(s)`
   Summarize 1-2 key studies and their most relevant result.

3. `Constraint sentence`
   State the most important limitation immediately, not three paragraphs later.

4. `Interpretive sentence`
   End by stating what the paragraph can support:
   - direct support
   - indirect support
   - context only
   - gap-defining evidence

This is the default building block for review body prose.

## Evidence-Layer Separation

The review should keep four layers distinct.

### Layer 1: Direct comparative evidence

Eligible for main direction-of-effect claims.

### Layer 2: Broader observational or setting-specific evidence

Useful when it sharpens plausibility, boundaries, or subgroup interpretation.
Must be labeled as indirect when it does not match the main question exactly.

### Layer 3: Patient-centered / symptom / preference evidence

Useful for explaining why discontinuation is considered and what trade-offs matter.
Must not substitute for hard-outcome comparison.

### Layer 4: Guidelines / policy / prior reviews

Useful for framing uncertainty, variation, and practice gaps.
Must not anchor empirical outcome claims.

## Outcome-Family Rule

Each outcome family subsection should answer the same three questions:

1. Is there direct evidence?
2. What are the strongest anchor studies?
3. What is the strongest safe conclusion?

Recommended default outcome families for treatment-strategy reviews:

- `All-Cause Mortality`
- `Cardiovascular Events / MACE`
- `Hospitalization`
- `Patient-Centered Outcomes`
- `Adverse Effects`

If an outcome family has no direct evidence, say so plainly and move it into a gap-oriented interpretation.

## Methodological Limits Rule

Only keep limitations that change how strongly the reader should believe the synthesis.

Preferred categories:

- confounding by prognosis / frailty / indication
- exposure or discontinuation misclassification
- heterogeneous clinical triggers or settings
- weak measurement of patient-centered outcomes

Avoid generic limitations like:

- "more studies are needed"
- "sample sizes varied"
- "there may be bias"

## Conclusion Rule

The conclusion should follow a fixed three-step close:

1. State the most stable main conclusion.
2. State what cannot be generalized.
3. State the most important next evidence need.

That pattern is more useful than a broad recap.

## Anti-Patterns

Treat these as draft failures:

- one-paper-one-sentence enumeration across a whole section
- section openings that begin with search counts
- using guideline language to support empirical effect claims
- long lists of all retained papers
- writing the review as if it were an evidence package explainer
- repeating the same "Study X found..." sentence frame

## Prompt vs Template

For writing-quality upgrades, template-first usually outperforms prompt-only tuning.

Reason:
- prompt changes affect tone and constraint
- template changes affect the shape of every section and paragraph

Best practice is layered:

1. strong structure template
2. explicit narrative rules
3. final prompt reminders in `review_briefing.md`

Do not rely on prompt wording alone to fix structural dryness.


---

# Output Schema

## search_log.csv

Suggested columns:

- search_id
- search_round
- parent_search_id
- concept_focus
- query_family
- question_type (propagated from topic_config; identifies routing used)
- review_goal (propagated from topic_config; identifies depth and output requirements)
- query
- source
- source_query
- date_searched
- date_limit
- language_limit
- recommended_retrieval_target
- n_retrieved
- n_after_dedup
- scope
- status
- rationale_trigger
- note

## screening_decisions.csv

Suggested columns:

- paper_id
- title
- decision
- screening_stage
- role
- reason
- direct_question_match
- design_integrity_ok
- comparator_integrity_ok
- time_zero_clear
- prior_user_design
- directness_tier
- exclusion_reason_code
- question_match_summary
- include_in_synthesis
- include_in_protocol

## candidate_records_raw.csv

Suggested columns:

- search_id
- search_round
- query_family
- source
- source_rank
- title
- authors
- year
- published_date
- doi
- url
- abstract
- publication_status
- source_record_id
- matched_query
- local_relevance_score
- strategy_match_score (0–3; 0 = not a strategy query or no match; 3 = both-side + design vocabulary)

## candidate_records_dedup.csv

Suggested columns:

- same as `candidate_records_raw.csv`, after DOI/title deduplication

## study_registry.csv

Suggested columns:

- paper_id
- synthesis_tier
- anchor_eligible
- primary_role
- secondary_role
- publication_status
- year
- design
- population
- exposure
- outcome
- sample_size
- setting
- measures
- core_findings
- limitations
- protocol_implication
- suggested_methods
- record_relevance (0–5; from scoring_rubric.md Dimension 1)
- study_credibility (strong / adequate / limited / weak; from Dimension 2)
- quality_signal (free-text summary of key quality signals)
- direct_question_match (`yes` / `no` / `unclear`; from eligibility_criteria.md)
- design_integrity_ok (`yes` / `no` / `unclear`)
- comparator_integrity_ok (`yes` / `no` / `unclear`)
- time_zero_clear (`yes` / `no` / `unclear`)
- prior_user_design (`yes` / `no` / `unclear`)
- outcome_family
- outcome_family_all
- title
- doi
- authors

## measurement_registry.csv

Suggested columns:

- construct
- preferred_tool
- evidence_role
- reason_from_literature
- key_example_paper_ids
- supporting_evidence_row_ids
- protocol_use
- limitation_or_bias

## confounder_registry.csv

Suggested columns:

- variable
- classification
- support_level
- supporting_paper_ids
- supporting_evidence_row_ids
- rationale
- recommended_main_model_role

## citation_registry.json

Suggested fields per entry:

- citation_id
- reference_number
- paper_id
- title
- publication_status
- narrative_role
- claim_supported
- supporting_decision_ids
- supporting_evidence_row_ids

## quality_appraisal_registry.csv

Suggested columns:

- paper_id
- domain
- judgment
- raw_signal
- evidence_source
- note

## fulltext_inventory.csv

Suggested columns:

- paper_id
- title
- doi
- text_source
- fulltext_status
- open_access_url
- source_file
- deep_read_completed
- deep_read_date
- claim_bearing
- note

## evidence_to_decision_table.csv

Suggested columns:

- decision_id
- decision
- evidence_summary
- supporting_paper_ids
- supporting_evidence_row_ids
- downstream_use
- confidence

## evidence_sufficiency_report.json

Suggested fields:

- level
- notes
- evidence_density
- design_mix
- measurement_support
- confounder_support
- gap_confidence
- design_fit
- causal_temporality_risk
- estimand_feasibility
- interpretation_risk
- mode_recommendation
- downgrade_reason

## review_contract.json

Suggested fields:

- project_mode
- review_type (`structured_narrative`, `systematic_no_meta`, or `systematic_meta`)
- reporting_framework (for example `SANRA`, or `PRISMA 2020` + `PRISMA-S` + `SWiM`)
- synthesis_method
- question_type
- review_goal
- design_type
- topic
- primary_estimand
- evidence_sufficiency
- decision_ids
- citation_ids
- deliverable_style
- narrative_readiness
- anchor_density_by_outcome

## literature_review_synthesis.md

Default presentation expectations:

- no generator branding or author placeholders in the title block
- review title and opening page should read like a real evidence review
- project-mode disclosure belongs in scope or methods text, not decorative metadata
- use restrained academic formatting suitable for DOCX/PDF export
- target style follows `review_type`: SANRA-aided narrative, PRISMA/SWiM systematic synthesis without meta-analysis, or PRISMA quantitative synthesis
- mature `decision_grade`/`full_package` bodies require at least 4,500 words, 30 identity-resolved references, 12 documented deep reads, and populated study-characteristics/effect tables unless a valid sparse-evidence exception is recorded
- do not mention package internals such as `review_briefing.md`, `study_registry.csv`,
  `claim_registry.csv`, `effect_registry.csv`, `anchor_eligible`, `narrative_readiness`,
  `core_direct_strict`, `core_direct_broad`, or version labels such as `v2.1`
- search and screening should appear as one compact late section, not as the organizing frame
- main sections should foreground the scientific question, direct evidence,
  indirect support, outcome-specific interpretation, literature limitations, and gaps
- multilingual variants should be separate files rather than mixed-language prose
- heavy-delivery mode may additionally emit `literature_review_zh.md`, `references.bib`,
  `reference_list_vancouver.md`, `reference_list_apa.md`, `publication_manifest.json`,
  and `delivery_quality_report.json`

## review_briefing.md

Default presentation expectations:

- pipeline-facing evidence map and audit document
- may mention tiers, anchors, registries, claims, bias tables, and package logic
- not intended to read like journal prose
- should give the LLM enough structure to write the narrative without copying the briefing wording

## literature_review.tex / .docx / .pdf

Default expectations:

- `.tex` is an export artifact for editing, submission preparation, or downstream formatting
- `.docx` and `.pdf` are delivery artifacts, not the source of truth
- multilingual exports should use language-tagged stems or filenames when more than one language is produced

## protocol_inputs.json

Suggested fields:

- project_mode
- study_title_candidate
- population
- exposure
- outcome
- mediator
- moderator
- primary_estimand
- measurement_tools
- confounders
- effect_modifiers
- suggested_methods
- evidence_gaps

## proposal_bridge.md

Default expectations:

- states significance, gap, innovation, and feasibility in evidence-backed language
- locks the proposed population, exposure, comparison, outcome, and primary estimand
- translates review findings into opening-report-ready claims without overstating causality

## effect_registry.csv

Required when `question_type` is `treatment_strategy_comparison`, `exposure_outcome_association`,
or `prognosis`.  Recommended otherwise.

One row per effect estimate.  A single paper may contribute multiple rows
(e.g., main analysis, subgroup, sensitivity analysis).

Suggested columns:

- effect_id (stable row identifier used by claim_registry.csv)
- study_id (links to paper_id in study_registry.csv)
- paper_id
- outcome_family
- outcome
- effect_measure (OR / RR / HR / PR / RD / MD / other)
- point_estimate
- ci_lower
- ci_upper
- exposure_contrast
- effect_directness
- supports_primary_direction_claim
- population_subgroup
- effect_trustworthiness
- notes

## claim_registry.csv

Required for all completed reviews.  One row per claim that appears in the narrative.

This is the **unified schema** — the two earlier definitions (pre-2026) are merged here.
Key addition: `evidence_direction` separates the factual direction from the prose text,
preventing the narrative generator from hard-wiring a claim direction.

Columns (canonical, must match `review.py build_review_scaffold` and
`validation.py validate_review_package`):

- `claim_id` (e.g., "C01", "C02")
- `outcome_family` (links to effect_registry.csv outcome_family)
- `claim_text` (the exact claim as it appears or will appear in the narrative)
- `claim_type` (primary_association / mechanism / measurement / design_justification / gap_statement / feasibility)
- `allowed_strength` (**definitive / suggestive / preliminary / background_only** — see scoring_rubric.md)
- `evidence_direction` (**favorable / harmful / null / mixed / heterogeneous / insufficient / unclear**)
  — must be set BEFORE claim_text is written; prevents the generator from defaulting to a harm narrative
- `anchor_required` (yes / no)
- `supports_primary_direction_claim` (yes / no)
- `eligible_anchor_paper_ids` (comma-separated paper_ids from study_registry.csv)
- `supporting_paper_ids` (additional supporting paper_ids)
- `counter_study_ids` (paper_ids of studies that contradict or qualify this claim)
- `supporting_evidence_row_ids` (comma-separated row identifiers from effect_registry.csv, required for primary claims)
- `confidence` (free-text assessment of why this strength was assigned)
- `narrative_position` (introduction / main_synthesis / discussion / gap_section)
- `note`

**Enforcement rules:**
- `allowed_strength` must be one of: `definitive`, `suggestive`, `preliminary`, `background_only`
- `evidence_direction` must be set before narrative drafting
- Every primary claim (`supports_primary_direction_claim = yes`) must have at least one `supporting_evidence_row_ids` entry
- Primary claims must not use `appendix_only` studies as eligible anchors

## bias_registry.csv

See `study_quality_framework.md` for when this file is required vs recommended.

One row per bias domain assessed per study.

Columns (canonical, must match `review.py build_review_scaffold`):

- `paper_id`
- `bias_domain` (e.g., confounding_by_indication, immortal_time_bias, time_zero_alignment, prevalent_user_bias,
  selection_bias, outcome_misclassification, exposure_misclassification, overadjustment, reverse_causation)
- `severity` (high / moderate / low / none_detected / unclear)
- `bias_direction` (towards_null / away_from_null / uncertain / not_applicable)
  — renamed from `direction` for unambiguous field identification
- `evidence_of_bias` (free-text: specific evidence or reasoning for this judgment)
  — was missing in older schema; required for non-unclear severity
- `reviewer_note` (optional additional annotation)

## methods_snapshot.json

Internal intermediate file. Populated before narrative writing. Consumed by
`review.py build_review_narrative` and the narrative LLM.

Fields:

- `review_question`
- `databases_searched` (list)
- `search_dates` (object: {source: date_searched})
- `date_limits`
- `language_limits`
- `inclusion_criteria` (list)
- `exclusion_criteria` (list)
- `screening_process`
- `fulltext_availability_limitations`
- `quality_appraisal_framework`
- `prisma_counts` (object: identified_total, after_dedup, screened, fulltext_assessed, included, excluded_reasons)
- `access_limitations` (list)

## section_packets.json

Internal intermediate file. One entry per narrative section.
Consumed by the LLM when drafting each section independently.

Fields per entry:

- `section_id`
- `section_name`
- `section_goal`
- `allowed_strength_ceiling` (definitive / suggestive / preliminary / background_only)
- `anchor_paper_ids` (list)
- `supporting_cluster_ids` (list)
- `forbidden_paper_ids` (list — studies that should not be cited as primary support in this section)
- `must_mention_limitations` (list)
- `expected_outcome_families` (list)
- `anti_repetition_blacklist` (list — sentence openers or phrases to avoid)

## Search Strategy Expectations

`search_strategy.md` should document:

- All core sources searched:
  - Free: OpenAlex, PubMed/MEDLINE, Semantic Scholar, Europe PMC, medRxiv, bioRxiv
  - Subscription (log as blocked_auth_required if absent): Embase, Web of Science
- Round structure: broad mapping, reading-driven expansion, citation chaining
- `evidence.py score_candidates` run and scored_candidates.csv produced
- `retrieval.py chase_citations` run on high-scoring anchors (record_relevance ≥ 4)
- Practical default volume targets for each round
- Why later query families were added after reading
- Any source access limitations or deviations from the default stack


---

# Proposal Bridge Standard

## Purpose

This file defines how the literature review should support an opening report, proposal, or research-question defense.

The objective is to prevent a common failure mode: a review that summarizes papers competently but does not sharpen the actual study question.

## What The Proposal Bridge Must Answer

`proposal_bridge.md` should answer these questions explicitly:

1. **Significance**
   Why does the topic matter scientifically, clinically, or from a public-health perspective?

2. **Gap**
   What remains unresolved after reviewing the literature?

3. **Innovation**
   What is new about the planned study?
   For many observational projects, innovation usually comes from population, setting, measurement quality, confounder strategy, estimand discipline, or integration of understudied variables, not from pretending the design is stronger than it is.

4. **Feasibility**
   Why is the study actually executable?
   This includes measurement availability, expected outcome prevalence, plausible sample frame, and a bounded analytic plan.

## Required Sections

- Research problem and significance
- Current evidence and stable findings
- Precise gap statement
- Proposed question lock:
  - population
  - exposure
  - comparison
  - outcome
  - primary estimand
- Variable and measurement feasibility
- Confounder and mechanism boundary
- Risks, limitations, and downgrade triggers

## Writing Rules

- Do not write generic novelty claims such as "few studies have examined this topic" unless the review package shows exactly in what sense the gap exists.
- Keep the innovation claim compatible with the proposed design.
- Feasibility claims must be tied to actual tools, variables, or sample access assumptions.
- If the review only supports a narrow or exploratory question, the proposal bridge must narrow the question instead of inflating it.

## Front-Shifted Principle

The review should not wait until protocol drafting to lock core methodological commitments.

By the end of the proposal bridge, the following should already be constrained:

- primary question form
- target population
- main exposure definition
- main outcome definition
- plausible confounder set
- preferred primary estimand
- major interpretation boundary

This is the main lesson worth carrying over from strong protocolised preprint workflows.


---

# Review Export and Delivery

Use this reference after the evidence registries and
`literature_review_synthesis.md` have passed validation.

## Language Variants

Create translated versions from the same verified registries and citation
registry. Do not manually diverge the evidence base across languages. A
language variant may use names such as:

- `literature_review_zh.md`
- `literature_review_en.md`
- `literature_review_ja.md`

## Publication Package

Use the existing scripts for deterministic packaging:

```bash
python3 cross-sectional-literature-review/scripts/export.py build_publication_package \
  <review_dir>
python3 cross-sectional-literature-review/scripts/export.py export_review \
  --input <review_dir>/literature_review_synthesis.md \
  --output-dir <review_dir> --lang zh-CN
```

Supported language codes are `zh-CN`, `en`, `ja`, `de`, `fr`, and `es`.
Specify `--mainfont` only when the selected PDF renderer needs an explicit
font. Use `--stem` to prevent one language from overwriting another.

The package may contain BibTeX, numbered or author-date reference lists,
DOCX/PDF/TeX exports, citation-verification reports, and a publication
manifest. Every export must be regenerated from the current synthesis and
verified source hashes.

## Delivery Boundary

An export is a delivery format, not evidence of review completeness. Do not
export a `ready` package while searches, screening, deep reading, citation
identity, or claim binding remain unresolved.
