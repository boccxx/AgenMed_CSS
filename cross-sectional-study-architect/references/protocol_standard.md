# Study architect: protocol and release standards



---

# Guided Design Interaction Contract | 交互式研究设计契约

Use this contract before loading any decision-tree reference when the user supplies a research concept, narrative design brief, or partial protocol without explicitly asking for immediate document generation.

## Public explanation boundary

Do not expose hidden chain-of-thought, private scratch work, or token-by-token reasoning. Treat any legacy decision-tree heading named `Reasoning Process`, `Claude's Reasoning Process`, or `推理过程` as a request for a concise public decision trace only.

Each public decision trace must contain only:

1. `recognized_information`: facts and proposals stated by the user
2. `decision_tree_entry`: applicable node identifiers and why they apply
3. `decision_needed`: the one material choice currently requiring confirmation
4. `options`: two or three defensible options when genuine alternatives exist
5. `recommendation`: the recommended option, if evidence and context support one
6. `rationale_summary`: a short teaching explanation containing the method principle, the study-specific reason, and the main consequence
7. `downstream_impacts`: protocol, sampling, measurement, estimand, SAP, or interpretation fields affected
8. `user_confirmation`: confirmed, revised, deferred, or blocked

Do not use phrases such as "my internal reasoning", "I thought step by step", or "chain of thought" in the user-facing trace.

## Teach while traversing | 边执行边教学

Decision-tree execution is also a short methods lesson. For every material node, teach the user before requesting a decision:

1. **Method principle**: what problem this node solves, in plain language.
2. **Study-specific relevance**: why the problem matters for this study and which bias, estimand, or claim boundary it affects.
3. **Option contrast**: what the defensible options trade off, and when each is appropriate.
4. **Downstream lock**: what later choices, analyses, or interpretations will change after this decision.

Keep the lesson compact: usually one short paragraph or three to five bullets. Do not turn every node into a textbook chapter. If there is no genuine choice, explain why the design is constrained and ask the user to confirm the proposed value. If the evidence is insufficient, teach the uncertainty instead of inventing a recommendation.

After the user answers, close the loop with two short statements:

- **Why this choice fits**: connect the selected option to the stated objective, available data, and methodological principle.
- **What it now commits**: name the fields or later nodes that are frozen, and identify any residual uncertainty.

The `rationale_summary` stored in the decision trace is the durable version of this teaching explanation. It is public methodological documentation, not a transcript of private deliberation.

## Interaction modes

Select exactly one mode at intake:

- `guided`: Default for a natural-language research concept or partial design when the user did not explicitly request immediate protocol generation. Parse first, show the applicable route, and ask one material question at a time.
- `direct`: Use only when the user explicitly requests a protocol/SAP or provides a complete structured intake. Still stop for unresolved generation-blocking decisions.
- `audit`: Use when the user supplies an existing protocol or SAP for evaluation or repair.

Do not infer authorization to generate a protocol merely because the narrative starts with phrases such as "本研究拟" or contains detailed design proposals.

## Parse before asking

Classify each extracted statement as one of:

- `stated_fact`: explicitly supplied and suitable to carry forward
- `design_proposal`: proposed by the user but not yet confirmed as methodologically adequate
- `inference`: a cautious interpretation made from the narrative
- `claim_to_verify`: a claim requiring evidence or design support
- `unknown`: a consequential missing field

Never silently promote a `design_proposal`, `inference`, or `claim_to_verify` to a confirmed design decision.

## Objective-level routing

Route each candidate objective independently:

- prevalence or distribution objective -> CoCoPop branch
- association objective -> PECO branch
- prediction objective -> prediction-specific completeness checks
- mechanism-exploratory objective -> exploratory branch with a hypothesis-generating claim boundary
- policy framing -> motivation only unless the design supports a policy estimand

A single study may contain multiple objective families. Do not force the entire study to choose one framework.

## Relevant-node traversal

Traverse all applicable nodes, not every file in the decision-tree library. Mark every routed node as:

- `pending`
- `completed`
- `not_applicable`
- `deferred`
- `blocked`
- `superseded`

Ask one generation-blocking question per turn. Combine only low-impact, non-blocking operational questions when doing so will not hide a methodological choice. Explain the relevant principle before the question so that the user is choosing with understanding rather than merely selecting a menu item.

## Decision card

Render the current question in this order:

```text
Current decision: <plain-language title>
Recognized information: <short summary>
Decision-tree entry: <node id and label>
Method principle: <what problem this node solves>
Why it matters here: <one or two study-specific sentences>
Options: <two or three options>
Recommendation: <option or "no recommendation yet">
Downstream impact: <affected design fields and trade-offs>
Please confirm, revise, ask "why", compare options, or return to an earlier decision.
```

The current card must contain the teaching explanation even when the user has not asked `为什么`. The `为什么` control requests a deeper explanation, examples, or comparison, not the first explanation.

Do not ask a question whose answer is already explicit and internally coherent. Instead, show the proposed value and ask for confirmation only when it materially changes the design.

## State, revision, and invalidation

After every confirmed answer:

1. append a record to `decision_trace_registry.json`
2. update `guided_design_session.json`
3. update the human-readable design snapshot
4. apply the decision's structured `field_updates` to `design_intake_draft.json`
5. give the user the short "why this choice fits" and "what it now commits" explanation
6. move to the next unresolved applicable node

If an earlier decision changes, mark its previous trace `superseded` and invalidate every dependent downstream node. Never leave sample-size, sampling, measurement, estimand, or model decisions frozen after their prerequisite changed.

Rebuild `design_intake_draft.json` from the base concept plus all active confirmed decisions after every answer or revision. Do not edit only the prose snapshot.

## Completion and generation authorization

Do not organize the final protocol or SAP in `guided` mode until:

- every generation-blocking applicable node is `completed` or explicitly adjudicated
- no unresolved contradiction remains
- the user has reviewed the design snapshot
- the user explicitly confirms document generation

When the design traversal is complete, ask:

```text
The applicable design decisions are complete. Would you like to:
1. review the full decision trace
2. revise an earlier decision
3. continue operational details
4. generate the protocol and SAP
```

Unknown release-stage information may remain as `[REQUIRES SPECIFICATION: ...]` in a draft, but it must remain visible and must block a final implementation-ready release when required by the main skill.

## User controls

Support these natural-language controls at any point:

- `为什么`
- `比较其他选项`
- `查看当前路径`
- `显示当前研究设计`
- `返回上一题`
- `修改某项决定`
- `暂时跳过`
- `暂停并保存`
- `继续设计`
- `完成并检查`
- `生成研究方案`


---

# Intake Preflight Rules

Use this reference before freezing `study_objectives[]`.

## Objective families

- `prevalence`: burden estimation or descriptive distribution in a defined population
- `association`: exposure-outcome linkage under a prespecified covariate strategy
- `prediction`: risk classification or screening performance, not etiologic effect
- `mechanism_exploratory`: pathway-oriented or mediator-oriented exploration that must not govern the primary adjustment set
- `policy_relevance_only`: policy framing or intervention relevance that may motivate the study but should not be frozen as a cross-sectional estimand

## Default claim boundaries

- `prevalence`: estimate burden or distribution only; do not imply determinants from this objective alone
- `association`: interpret as cross-sectional adjusted association; do not infer temporality or causality
- `prediction`: interpret as discrimination or classification performance only; do not imply causal drivers
- `mechanism_exploratory`: hypothesis-generating only; do not treat as confirmatory evidence
- `policy_relevance_only`: discuss implications cautiously; do not freeze as a primary objective without a design that supports policy-effect estimation

## Minimum completeness checks

### Prevalence objective

Require:

- population
- condition or outcome
- context
- estimation metric

### Association objective

Require:

- population
- exposure
- comparison
- outcome
- effect measure
- analysis family

### Prediction objective

Require:

- target population
- prediction target
- predictor set or candidate predictor domain
- performance metric

## Follow-up questions worth asking

Use a short interview fallback only when the answer changes the design materially.

- What is the one primary objective that will determine sample-size reasoning?
- Is the main outcome continuous, binary, or ordinal in the final SAP?
- Which variables are exposures, outcomes, confounders, modifiers, or mediators?
- Which claims are too strong for a cross-sectional design and need reframing?
- Does the sampling design require weighting, clustering, or stratified analysis?
- Which unresolved question would cause drift across protocol, registry, and SAP if left implicit?


---

# Complete-body standard for protocol and SAP

Use this reference when generating or auditing the final protocol and statistical analysis plan (SAP). Word counts are release gates for a research-grade worked example, not permission to pad text. A shorter document may be retained only as an explicitly labelled draft that fails the scientific-release gate.

## Protocol body

Require at least 6,000 scientific-body words and normally target 6,500–8,000 words for a full research protocol. Require all of the following chains in the main body:

- evidence: burden -> uncertainty -> study-specific gap -> objective, with verified in-text citations and a reference list;
- sampling: dated frame -> fixed stratum allocation -> explicit selection algorithms -> every stage probability and identifier -> contact/disposition rules -> separately applied household RR3 and adult-completion factors -> full weight chain -> unit-matched calibration controls -> deterministic trimming/restoration -> one survey variance representation supported by supplied design information -> executable analysis consequence;
- measurement: instrument/version/language -> administration/recall window -> item and scale scoring -> range and missing-item rules -> validation evidence -> field quality control;
- study size: formula and derivation -> numeric assumptions and provenance -> group allocation -> exact unadjusted integers -> rounding order -> design effect -> non-response inflation -> adopted sample -> fully recomputable scenario grid -> under-yield action;
- safety: trigger -> immediate action -> escalation/referral -> documentation -> confidentiality boundary for every sensitive outcome;
- data lifecycle: capture -> validation -> correction audit -> de-identification -> freeze/lock -> retention/access -> reproducible release;
- inference: objective -> estimand -> model -> adjustment logic -> diagnostic/fallback -> sensitivity -> interpretation boundary;
- governance: version/amendment history, roles, ethics/consent, study status, PPI status, dissemination, and data/code/material sharing.

Do not invent unknown institutional facts, instrument licences, approvals, registrations, sites, dates, or parameter sources. Emit `[REQUIRES SPECIFICATION: ...]` and block release when any such fact is needed but absent. Ban vague substitutes such as `validated instrument`, `where feasible`, `as appropriate`, `large urban catchment`, `to be finalized`, and `planned` unless the sentence also provides a frozen trigger, owner, and deadline.

For `research` mode, require at least 25 non-duplicate references with stable DOI, PMID, or authoritative URL identifiers. Every numbered reference must be cited in the body. Reference count alone never compensates for missing operational detail.

## SAP body

Require at least 7,500 words and normally target 8,000–10,000 words when a complex survey, MI, and multiple sensitivity axes are present. Adapt the JAMA 55-item SAP framework to observational research while stating that its source is trial-derived. Require 100% coverage of critical items and at least 90% of applicable items.

Every objective must bind:

`objective_id -> estimand -> population -> variable derivations -> exact model formula -> effect scale -> variance estimator -> diagnostic trigger/action -> sensitivity role -> complete output shell`.

Critical SAP content includes:

- document version, approval/sign-off roles, protocol version, data-freeze condition, and amendment history;
- exact target/source/analysis populations and participant-flow reconciliation;
- sample-size/precision basis;
- source-to-analysis derivations, units, category/reference levels, continuous-variable functions, and item-level missing rules;
- exact survey design, including inclusion probabilities, the unit/formula/collapse of each non-response factor, the full weight chain, calibration unit and joint controls, deterministic sparse-cell and trimming rules, strata, PSU, explicit FPC/PPS inclusion or exclusion rationale, exact `svydesign` call, lonely-PSU rule, degrees of freedom, and an end-to-end synthetic finite-estimate/SE test;
- exact primary, descriptive, sensitivity, exploratory, missing-data, and fallback model rows. Every row must independently state its population, exposure/outcome, complete formula, family/link/options, design, MI/pooling, effect, and output; references such as `same`, `primary formula`, `all primary covariates`, or `primary design` are release failures;
- a complete variable-by-variable MI algorithm: exact named method vector, integer predictorMatrix/type-code semantics, visitSequence and post vector; source missing codes, eligibility, bounds, survey/cluster accommodation, initial and same-chain continuation semantics, seed, last-iteration slope definition, rank-normalized folded split-Rhat for mean and SD, MC-error threshold, finite `df.complete`, pooling, complete-case definition, deterministic delta function, unique MNAR IDs and tipping rule;
- multiplicity and inferential hierarchy;
- diagnostics with numeric or categorical triggers and mandatory actions;
- at least eight true shells: flow, characteristics, missingness, primary/model results, missing-data/MNAR, interaction, a genuine ordered fallback-attempt Table 7, and a genuine threshold/decision/action diagnostic Table 8, plus frozen figure shells. Each shell needs concrete rows, columns, denominators, effect scale, footnotes, identifiers and status cells;
- software/package version capture, environment lock, seed, run manifest, code review, provenance, deviation classification, and sign-off.

Block phrases such as `when appropriate`, `if judged plausible`, `may simplify`, or `where feasible` unless tied to a prespecified objective trigger and action. Planning-table cells may contain `Not populated before analysis`; this is not an unresolved design placeholder.

## Scientific-release audit

Audit protocol and SAP separately. Both must pass:

1. body and section-depth floors;
2. unresolved-specification and vague-phrase scans;
3. anti-padding five-gram diversity and duplicate-paragraph checks;
4. complete sampling, measurement, sample-size, safety, MI, survey, diagnostic, and output-shell signals;
5. citation/reference integrity for the protocol;
6. agreement of objective, population, estimand, model, effect scale, design handling, sample size, and adjustment set across both documents.

The intake must bind a versioned execution specification plus calibration, derivation, MI, safety, R runtime/test and environment assets by SHA-256. Before prose release, run the executable planning dry run. It must reproduce every sample-size row; validate all joint calibration cells; test unequal-weight type-1 cut points, ties and invalid inputs; execute the chosen survey design and full production formula on deterministic synthetic data with finite estimate/SE; smoke-run the exact MI configuration; unit-test known converged/nonconverged split-Rhat cases; reject model shorthand and invalid FPC/PPS combinations; and confirm delta, diagnostic, fallback and output registries. Retain stdout, stderr and sessionInfo. This is synthetic software validation, not empirical convergence, field readiness or effect validation.

Independent-document editing is also a release criterion: headings must be sequential, appendix content must not repeat main-body commitments, and each document's reference list must start at 1 and remain consecutive even when references originate from a shared intake registry.

A structural pass, draft pass, or demonstration pass is not a scientific-release pass.


---

# End-to-end standard for a real cross-sectional protocol and SAP

This standard is normative for `project_mode=research`. It records the
transferable lessons from producing a real multisource, multistage elderly
bone-health protocol and its analysis. A polished paragraph cannot substitute
for an executable field or a passed gate.

## Sampling and inference scope

Record the derived sampling name and every stage in structured form: stratum,
cluster or site, sampling unit, frame, randomization method, selection
probability, replacement rule, and evidence retained. Distinguish a probability
sample of the target population from purposively fixed research sites followed
by probability sampling within sites. The latter does not by itself support
province-wide design-based inference. Point estimation, variance estimation,
and target-population extrapolation are three separate adjudications.

## Measurement and questionnaire provenance

Every instrument or platform field must be classified as validated existing,
adapted, self-designed, device-derived, laboratory-derived, or administrative.
Freeze version, language, item wording and options, skip logic, scoring,
item-level missingness, validation evidence, permission/licence, and appendix
location. Preserve raw responses separately from analytic recodes and record a
source or content hash for the frozen appendix.

## Multisource data integration

Freeze the linkage unit and keys, source systems, extraction windows, temporal
alignment, one-to-many resolution, duplicate policy, unit harmonization,
linkage-failure handling, linkage-quality indicators, and the source of truth
for conflicts. Linkage feasibility is decided before analysis populations are
frozen.

## Bias-control ledger

For each objective and bias domain record: mechanism, design prevention, field
control, monitoring indicator and threshold, mandatory action, analysis
mitigation, sensitivity output, and residual risk. Generic assurances such as
“strict quality control” do not satisfy this requirement.

## Adjustment and model sequence

All adjusted association objectives require an explicit temporal/DAG rationale,
including when causal language is prohibited. Freeze C0 (crude), M1 (minimal
demographic/design set), M2 (primary prespecified set), and when needed an
available-case or extended sensitivity model. Compare M0/M1/M2 on the same
eligible support set; report any model-specific denominator separately.
Covariates are selected from subject-matter and design reasoning, never from
bivariate p values or automated stepwise selection.

## Statistical execution order

The dependency order is: source freeze and linkage; identity/unit/range QC;
derivation; sampling/weight/variance adjudication; flow and missingness;
descriptive distributions and prevalence; bivariate firewall; common-sample
crude and adjusted models; diagnostics and fallback; dose-response; interaction;
missing-data and other sensitivities; multiplicity; output registry and
provenance. Multiple imputation is run after variable QC and before the first
model requiring imputed covariates; observed-data descriptions remain visibly
distinct from pooled inferential estimates.

## Delivery classes and release gates

Use one of three explicit delivery classes: `scientific_final`,
`provisional_blocked_review`, or `demonstration_only`. A real-data report may be
substantive yet provisional when design variance, target-population inference,
or inferential adequacy is unresolved. It must display the blocker prominently
and cannot be relabelled as a demonstration. Export requires content audit,
contract/registry consistency, hash/path parity, full-page PDF rendering, and
visual checks for fonts, clipping, blank pages, table width, figure legibility,
and numbering.

