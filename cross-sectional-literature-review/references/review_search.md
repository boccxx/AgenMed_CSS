# Literature review: search and evidence



---

# Eligibility Criteria

## Purpose

This file defines what it means for a study to genuinely answer the research question,
as opposed to merely being topically adjacent.  Use it at the screening stage to
populate the eligibility boolean columns in `study_registry.csv`.

A paper can score high on `record_relevance` (from `scoring_rubric.md`) while still
failing one or more eligibility criteria.  Those two judgements serve different purposes:
relevance decides whether to read the paper; eligibility decides whether its estimates
can be used to anchor claims about the specific question.

---

## Eligibility Boolean Columns for `study_registry.csv`

Add these five columns to every `study_registry.csv` row.
Use `yes`, `no`, or `unclear` at screening / abstract stage.
If a criterion is genuinely not applicable to the question type, record `NA`
only after structured extraction confirms that it does not apply.

| Column | Question answered |
|---|---|
| `direct_question_match` | Does this study directly answer the stated PECO/PICO question? |
| `design_integrity_ok` | Is the study design appropriate for the estimand and does it have a clear time zero? |
| `comparator_integrity_ok` | Is the comparator interpretable as the intended alternative strategy or treatment arm? |
| `time_zero_clear` | Is the start of follow-up clearly and symmetrically defined for all arms? |
| `prior_user_design` | For drug/treatment studies: were prevalent users excluded (new/incident user design)? |

Interpretation:

- `yes`: the criterion is clearly satisfied from the available evidence.
- `no`: the criterion clearly fails.
- `unclear`: title/abstract or incomplete extraction does not justify either `yes` or `no`.

If all five are `yes` for a given study, it is eligible to anchor main-synthesis claims.
Studies with one or more `unclear` values may still enter the narrative as direct-but-limited
or indirect support, depending on the synthesis tier.
Studies where one or more are `no` may still contribute context, measurement, or confounder
logic, but should not anchor the primary direction of evidence.

---

## Recommended Synthesis Tiers

Use the five eligibility columns together with `synthesis_tier` and `anchor_eligible`.

| Tier | Typical pattern | Narrative use |
|---|---|---|
| `core_direct_strict` | direct question match and comparator integrity are `yes`; design is robust; no major eligibility failure | Can anchor primary direction-of-effect claims |
| `core_direct_broad` | directly relevant strategy comparison, but one or more design fields remain `unclear` | Can appear in direct-evidence section but should not anchor strong claims alone |
| `indirect_support` | useful for measurement, patient perspective, context, confounding, or implementation | Can support interpretation or gap statements |
| `background_policy` | guideline, policy, narrative review, or broad deprescribing context | Background only |
| `appendix_only` | topically adjacent or too indirect to inform the stated question | Keep out of main evidence sections |

---

## Criterion 1: Direct Question Match

**Ask:** Does this study measure the exposure *and* the outcome *in the population* defined by the research question, using a comparator that is interpretable as the intended alternative?

**Pass:** The study population overlaps substantially with the target population; the exposure construct and outcome construct are operationalised in a compatible way; the comparison is not a proxy or a lookalike.

**Fail examples:**
- The study compares drug users vs never-users when the question is about continuing vs stopping among existing users.
- The outcome is a surrogate without established validity for the target outcome.
- The population is paediatric when the target population is adult.

---

## Criterion 2: Design Integrity

**Ask:** Is the study design capable of answering the question, and does the analytic approach match the estimand?

**Pass:** The design is cohort, RCT, case-control, or target trial emulation as appropriate; the time zero is clearly defined; follow-up is post-exposure.

**Fail examples:**
- Cross-sectional study used to answer a temporality-dependent prognosis question.
- No defined cohort entry date; outcomes measured before exposure assignment is complete.
- Prevalent users are analysed as a single group without distinguishing by treatment duration.

---

## Criterion 3: Comparator Integrity

**Primarily applies to `question_type = treatment_strategy_comparison`.**

**Ask:** Is the comparator the right alternative strategy, not just an absence of treatment or a different drug class?

**Pass criteria:**
- Both arms had prior use of the relevant drug class (active comparator / prior user design).
- The comparator is an active treatment decision, not "no exposure."
- The comparison is interpretable as a real-world strategy choice (continue vs discontinue; escalate vs maintain).

**Fail examples:**
- Metformin users vs metformin non-users (initiation study, not a continuation vs discontinuation study).
- Comparing drug A vs drug B when the question is about continuing vs stopping drug A.
- Patients who ran out of supply (unintentional discontinuation) treated as "discontinuers."

Set `comparator_integrity_ok = NA` for studies that are not strategy comparison studies.

---

## Criterion 4: Time Zero Is Clear

**Ask:** Is the start of follow-up defined consistently and symmetrically across all comparison arms?

**Pass:** Each arm has a clear, clinically meaningful index date; the risk period begins at the same relative point for all participants.

**Fail examples (immortal time risk):**
- Exposure is defined over a look-back window but the outcome clock starts at cohort entry.
- Users who initiated treatment *after* the index date are included in the "treated" arm from the index date onward.
- The grace period is not accounted for, leaving an interval where the exposure is undefined but outcomes are counted.

---

## Criterion 5: Prior User Design (Drug / Treatment Studies Only)

**Ask:** Were prevalent users excluded, or at least analysed separately, to avoid depletion-of-susceptibles bias?

**Pass:** The study uses an incident (new) user design in which follow-up begins at treatment initiation; or a prior user / active comparator design in which all arms have comparable prior treatment history.

**Fail:** Patients who have been on treatment for varying durations are pooled at a cross-sectional snapshot; early discontinuers due to adverse effects have already left the cohort, biasing the remaining "continuers" toward healthier survivors.

Set `prior_user_design = NA` for non-drug studies.

---

## Using These Criteria in Practice

1. For each paper that passes the relevance threshold (`record_relevance ≥ 3`), complete the five columns as part of the screening decision.

2. Record the reasoning briefly in `screening_decisions.csv` `reason` field when any criterion is `FALSE`.

3. In the narrative, distinguish clearly between:
   - **Eligible studies** (all five criteria met): can support direction-of-effect claims.
   - **Ineligible but useful studies** (one or more criteria failed): can support context, measurement, confounder, or mechanism claims only.

4. In `claim_registry.csv`, set `allowed_strength` to at most `suggestive` when no eligible study supports the claim, even if multiple ineligible-but-relevant studies point in the same direction.


---

# Mode Policy

Project mode answers:

- how real the downstream study is
- how strong the downstream manuscript claim may be

Delivery preset answers a different question:

- how complete the review package needs to be

Do not confuse `project_mode` with delivery scope.

## `research`

Use when the review is supporting a real study and real manuscript.

## `applied_methods`

Use when the evidence base is real, but the downstream project is synthetic, pilot, or validation-oriented.

## `workflow_methods`

Use when the task is only a skill demonstration or pipeline validation.

## Delivery Presets

### `brief`

Use when:

- the user needs a fast but structured evidence map
- the corpus is still unstable
- the review should not yet pretend to be a mature narrative review

Typical outputs:

- search tables
- screening tables
- core registries
- `review_briefing.md`

### `decision_grade`

Use when:

- the review is intended to shape a real study, protocol, SAP, or manuscript framing
- claim discipline and registry completeness matter
- a true narrative review is expected if the evidence qualifies

Typical outputs:

- full registries
- `claim_registry.csv`
- `effect_registry.csv` where required
- `bias_registry.csv` where required
- `proposal_bridge.md`
- `protocol_inputs.json`
- `literature_review_synthesis.md`

### `full_package`

Use when:

- the review is near delivery, circulation, or submission
- formatted exports and citation verification are needed

Adds:

- DOCX/PDF export
- citation verification outputs
- stricter handoff expectations

## Sufficiency Gates

- `strong` or `adequate`: protocol-ready
- `limited`: draft-only
- `weak`: do not force a research manuscript

## Downgrade Triggers

- sparse evidence density
- poor design fit for the intended claim
- high causal-temporality risk
- weak estimand feasibility
- high interpretation risk
- mismatch between requested delivery preset and actual narrative readiness


---

# Downgrade Policy

Use downgrade states when the evidence or design fit is insufficient for a stronger downstream mode.

Downgrade decisions operate on two axes:

- **research ambition**
  - what kind of downstream claim or study is allowed
- **delivery form**
  - whether the package can honestly support `brief`, `decision_grade`, or `full_package`

## Allowed States

- `preliminary_review`
  Search and screening exist, but synthesis is too early for protocol generation.
- `narrow_evidence_review`
  The topic is coherent, but the evidence base is too narrow for a broad review claim.
- `protocol_draft_only`
  There is enough support for a draft protocol, but not enough to justify a final protocol or manuscript.
- `sap_not_ready`
  Protocol logic is usable, but the estimand or analytic support is still under-specified.
- `analysis_core_only`
  Core analysis may proceed, but extended methods should remain off.
- `applied_methods_manuscript_only`
  The workflow can support an applied-methods manuscript, but not a real empirical manuscript.
- `workflow_methods_manuscript_only`
  Outputs may support a workflow/methods paper only.
- `research_manuscript_blocked`
  A research-grade manuscript is not allowed because the evidence or design does not support it.

## Default Triggers

- Use `preliminary_review` when the review package lacks a stable study registry or sufficiency assessment.
- Use `narrow_evidence_review` when the corpus is coherent but highly sparse or restricted to a narrow slice of the topic.
- Use `protocol_draft_only` when measurement support or confounder support is limited.
- Use `sap_not_ready` when the main estimand or interpretation boundary is unclear.
- Use `analysis_core_only` when the evidence or design supports the main analysis but not exploratory extensions.
- Use `applied_methods_manuscript_only` when the research question is real but the data are synthetic, pilot, or internal-validation only.
- Use `workflow_methods_manuscript_only` when the topic serves pipeline validation rather than a substantive study.
- Use `research_manuscript_blocked` when evidence is weak, design fit is low, or temporality/interpretation risks make a research-grade paper inappropriate.

## Delivery-Form Downgrade Rule

Even when the project mode stays the same, the package may need to downgrade its delivery form.

- If search and screening are incomplete:
  - downgrade to `brief`
- If registries are complete but direct evidence is sparse or poorly aligned:
  - keep `decision_grade` package outputs
  - but set `deliverable_style = evidence_map`
- If claim discipline, anchor support, and narrative readiness are satisfied:
  - allow `deliverable_style = narrative_review`
- If exports or citation verification are missing:
  - do not pretend the package is `full_package`


---

# Search Reporting Standard

## Purpose

This file adapts PRISMA 2020 and PRISMA-S into a compact operating standard for this skill.

The objective is reproducibility, not cosmetic formality. A reader should be able to tell what was searched, when it was searched, why papers were kept, and what limitations remain.

## Minimum Search Log Fields

Each row in `search_log.csv` should capture at least:

- `search_id`
- `search_round`
- `parent_search_id`
- `concept_focus`
- `query_family`
- `query`
- `source`
- `source_query`
- `date_searched`
- `date_limit`
- `language_limit`
- `recommended_retrieval_target`
- `n_retrieved`
- `n_after_dedup`
- `status`
- `rationale_trigger`
- `note`

If some fields are unavailable, keep the column and state why the value is missing.

## Minimum Screening Decision Fields

Each row in `screening_decisions.csv` should capture at least:

- `paper_id`
- `title`
- `decision`
- `screening_stage`
- `reason`
- `role`
- `include_in_synthesis`
- `include_in_protocol`

Reasons should be specific enough to audit later, for example:

- wrong population
- no validated outcome measure
- exposure too broad or poorly matched
- review article used only for citation chaining
- retained for measurement justification only

## Required Search Behaviors

1. Search both direct-topic and support-topic evidence.
   A defensible review usually needs association papers, measurement papers, and at least some mechanism or confounder logic papers.

2. Query the core sources directly unless a source is truly unavailable.
   The default core set is:
   - `OpenAlex`
   - `PubMed/MEDLINE`
   - `Embase`
   - `Web of Science`
   - `medRxiv`
   - `bioRxiv`

3. Record the actual search date.
   Do not leave it implicit.

4. Capture both recent and seminal work.
   Recent work is important for currency; seminal work is important when it anchors measurement tools, classification schemes, or field-defining associations.

5. Use iterative search rounds.
   Round 1 maps the field broadly. Then read the strongest anchors. Round 2 is driven by what the papers reveal about theory, mechanisms, measurements, confounding structure, effect modification, contradictory results, and design boundaries. Round 3 performs citation chaining, cited-by expansion, and focused retrieval for unresolved tensions.

6. Explain source limitations.
   If you only had access to abstracts, could not run one of the core databases, or had to rely on web search for part of the retrieval, state that plainly.

7. Preserve screening traceability.
   A retained paper should have a clear reason for staying in the synthesis.

8. Verify citation identity before final writing.
   Use DOI resolution, Crossref metadata, or equivalent authority checks so the citation registry does not drift away from the papers actually screened.

9. Log why later queries were created.
   A reading-driven expansion query should not appear magically. The trigger should be recoverable from anchor-paper reading, for example:
   - newly discovered measurement tool
   - named mechanism or theory
   - contradictory subgroup finding
   - null-finding thread
   - landmark review reference chasing

## Preferred Retrieval Stack

For a serious but still reproducible default stack:

- use OpenAlex as the baseline scholarly graph source
- use PubMed/MEDLINE for biomedical indexing and MeSH-linked retrieval
- use Embase to improve biomedical and pharmacological coverage
- use Web of Science for citation coverage and interdisciplinary recall
- use medRxiv and bioRxiv for preprint and frontier capture
- use Crossref or DOI resolution to clean metadata and resolve duplicates

This keeps the search process inspectable and easier to rerun.

## Practical Default Volumes

There is no universally correct fixed number of papers, but the default planning targets should be explicit:

- Round 1 broad mapping: inspect roughly `30-50` ranked records per core source; `40` is a good default target
- Anchor reading before expansion: read at least `12-20` high-value papers after deduplication
- Round 2 reading-driven expansion: inspect roughly `15-30` records per triggered query family and source
- Round 3 citation chaining and contradiction chasing: continue until an additional cycle yields no new decision-relevant evidence

These are planning defaults, not hard caps. If the topic is sparse, read fewer because fewer exist. If the topic is saturated, tighten by relevance and downstream decision value rather than pretending more volume is always better.

## Query Construction Logic

The query should evolve rather than remain a single frozen keyword string.

Use a layered query family:

1. Direct association query.
   Exposure + outcome + population/setting.

2. Population or setting query.
   Population/setting + exposure or outcome variants that may be indexed differently.

3. Measurement query.
   Exposure or outcome + named scales, instruments, thresholds, biomarkers, classification systems, or validation terms.

4. Design and estimand query.
   Exposure + outcome + design terms such as cohort, trial, case-control, prevalence, incidence, odds ratio, risk ratio, hazard ratio, marginal structural model, or mediation.

5. Mechanism or theory query.
   Triggered after reading when papers reveal pathway language, named theories, or biological or behavioral mediators.

6. Contradiction or boundary query.
   Triggered when the first round reveals null findings, subgroup differences, geography-specific patterns, or conflicting operationalizations.

Source syntax should be adapted rather than copied blindly:

- OpenAlex: broad text query and cited-by chaining
- PubMed/MEDLINE: MeSH plus title/abstract fields
- Embase: Emtree-aware and free-text Boolean logic
- Web of Science: topic field queries and citation chasing
- medRxiv and bioRxiv: plain Boolean/free-text frontier sweeps

## Large-Corpus Option

When the candidate set is large enough that manual title/abstract screening becomes the bottleneck, an ASReview-style active-learning workflow is acceptable, provided that:

- all human labels remain exportable
- the stop rule is documented
- the final retained set is still logged in `screening_decisions.csv`
- the review does not present the prioritization model as if it replaced human judgment

## PRISMA-Style Narrative Requirements

The narrative review must state inline counts for:

- records retrieved
- records after deduplication
- records screened
- records retained

These numbers must come from source files such as `search_log.csv` and `screening_decisions.csv`. If the counts cannot be recovered, write `not available`; do not estimate.

## Search Refresh Rule

If the review is meant for a current manuscript submission and the search is old enough that currency is doubtful, rerun or update the search and log the refresh. As a practical default, treat a search older than 6 months as stale unless the user explicitly accepts the older cutoff.

## Common Failure Modes

- Search log records queries but not dates or sources
- Search log records only one keyword pass and never shows reading-driven expansion
- A local paper set is imported and treated as if it were the original search
- Screening decisions only say "include" or "exclude" without reasons
- The narrative delegates all search detail to sidecar files
- Only exposure-outcome papers are retained, while measurement validity and confounder structure are ignored
- Search numbers in the narrative do not match the logs


---

# Live Retrieval Standard

## Purpose

This file defines what counts as a real search execution for this skill.

The key distinction is simple:

- a `search plan` is not yet a search
- a `search_log.csv` with planned rows is not yet a completed retrieval
- a completed search must produce raw source payloads, candidate records, and updated retrieval counts

## Default Execution Stack

The default execution commands are:

- `python3 scripts/retrieval.py build_search_plan`
- `python3 scripts/retrieval.py run_live_search`

The intended order is:

1. build the multi-round plan
2. execute the live search
3. inspect anchor papers
4. revise or refresh later-round query families if the reading reveals new terminology or theories
5. rerun targeted rows as needed

## Source Handling Rules

### Direct API Retrieval

These sources should be queried directly when possible:

- `OpenAlex`
- `PubMed/MEDLINE`
- `medRxiv`
- `bioRxiv`

For `OpenAlex`, `PubMed/MEDLINE`, `medRxiv`, and `bioRxiv`, the retrieval should generate:

- raw JSON or XML-derived payload captures under `raw_results/`
- `candidate_records_raw.csv`
- `candidate_records_dedup.csv`
- updated `search_log.csv` with real `date_searched`, `n_retrieved`, and execution status

If the local environment lacks a usable certificate chain, the
`run_live_search` command may be run with `--insecure-skip-verify`, but this
should be treated as an environment workaround rather than the normal default.

### Access-Controlled Sources

These are still mandatory review sources, but they may require subscription, institutional access, or provider credentials:

- `Embase`
- `Web of Science`

If they cannot be queried programmatically in the current environment:

- keep them in `search_log.csv`
- mark the row honestly, for example `blocked_auth_required`
- state the reason in `note`
- do not delete the source to make the review appear complete

## Preprint Retrieval Rule

The official bioRxiv / medRxiv API exposes interval-style endpoints rather than a fully general keyword-search API.

Therefore, the acceptable default behavior is:

1. retrieve by date window from the official API
2. rank locally by overlap with the planned query
3. keep the scan cap explicit in the search note

This is acceptable only if the search log states that local ranking was applied after official source retrieval.

## Minimum Execution Artifacts

After a real retrieval run, the review directory should usually contain:

- `search_log.csv`
- `search_strategy.md`
- `candidate_records_raw.csv`
- `candidate_records_dedup.csv`
- `raw_results/`

These are upstream retrieval artifacts. They precede screening and synthesis.

## Honesty Rule

Do not claim:

- that all six core sources were successfully queried if some were blocked
- that preprint retrieval was free-text searched if it was actually interval retrieval plus local ranking
- that imported local papers are equivalent to a current multi-source search

The search layer should be inspectable enough that another researcher could understand what actually happened.
