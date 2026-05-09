# Statistical Analysis Sub-Prompt Generator

## Core Task
Generate independent sub-prompt files for each numbered subsection (7.1, 7.2, 7.3, etc.) in Section 7.0 "Statistical Analysis Methods" of the research protocol.

**⚠️ Critical Constraints:**
- **Only use variables that exist in the actual data file**: Do not reference variables that are not in the data file
- **Must be based on provided actual data variable information**: Strictly limit variable selection scope

**Key Principles:**
1. **Follow protocol subsection numbering**: Generate one sub-prompt per numbered subsection (7.1, 7.2, 7.3, etc.), preserving the protocol's section structure
2. **Strictly parse statistical analysis methods**: Must extract specific statistical methods, core variables, and analysis requirements from each subsection word by word
3. **No generalization**: Do not replace specific requirements in research protocol with generic statistical methods or reorganize by research objectives
4. **Generate sub-prompt files**: Create files in format `prompt_7.X_[english_name].md` matching the protocol subsection number

## Sub-Prompt Template Structure
```markdown
# Statistical Analysis Task: SAP 7.X - [Section Name]

## Core Statistical Methods
[Extract verbatim from protocol Section 7.0, must include:]
- **Specific model name** (e.g., "survey-weighted log-binomial generalized linear mixed model")
- **Key parameters** (e.g., "geographic region as random intercept", "survey weights")
- **Link function** (e.g., "binomial(link = 'log')")
- **Alternative approaches** (e.g., "modified Poisson GLMM")
- **Diagnostic methods** (e.g., "Hosmer-Lemeshow test")
- **Any other technical details explicitly mentioned in research protocol**

## Hard Constraint Extraction (Contract Enforcement)

For EACH analysis stage, extract and enforce:

1. **Sampling Design Contract**:
   - Extract: weight variable name, strata variable, PSU variable from protocol
   - If not specified: Flag as "design_mode: SRS_assumption"
   - Output in sub-prompt: "design_contract": {"weight": "var_name", "strata": null, "psu": null}
   - Enforcement: R code MUST use these exact variables or clearly state "unweighted analysis"
   
   **CRITICAL: Variable Mapping for Design Variables (MANDATORY)**:
   - If protocol mentions "strata by Economic Circle", "stratification by region", "strata by geographic area", or similar concepts:
     * Check actual data for variables with semantic equivalence (e.g., "Economic Circle" → Geographic_Region, Region, Area, Location)
     * If found: Map protocol concept to actual variable name (e.g., "Economic Circle" → "Geographic_Region")
     * Verify the mapped variable has >= 2 unique values (required for stratification)
     * Set "strata": "actual_variable_name" (NOT null) in design_contract
   - If protocol mentions "PSU", "cluster", "primary sampling unit", or "village/community":
     * Check actual data for variables with semantic equivalence (e.g., PSU_ID, Cluster_ID, Village_ID, Community_ID)
     * If found: Map protocol concept to actual variable name
     * Set "psu": "actual_variable_name" (NOT null) in design_contract
   - **DO NOT set strata/psu to null** if protocol explicitly requires stratification/clustering AND a semantically equivalent variable exists in data
   - **Example**: If protocol says "strata by Economic Circle" and data has "Geographic_Region" with 3 values (Boxing, Pingyi, West_Coast), set "strata": "Geographic_Region"

2. **Estimand & Exposure Definition**:
   - Extract EXACT exposure variable and grouping (e.g., "Exercise: daily vs none")
   - If multiple definitions found: Choose primary and flag inconsistency
   - Output: "exposure_definition": "Exercise (daily physical activity: yes/no)"
   - Enforcement: Use ONLY this definition consistently across all stages

3. **Covariate Adjustment Strategy**:
   - If DAG/a priori mentioned: Extract adjustment set, flag as "adjustment_mode: DAG_fixed"
   - If baseline imbalance/data-driven: Flag as "adjustment_mode: data_driven"
   - Extract excluded variables: mediators, colliders, outcomes
   - Output: "adjustment_contract": {"mode": "DAG_fixed", "covariates": [...], "exclude_from_main": ["BMI"]}
   - Enforcement: R code MUST NOT deviate from specified adjustment strategy
   - **CRITICAL**: Extract and list ALL protocol-specified variables (especially from DAG adjustment set) in sub-prompt, even if they are missing from actual data

4. **Missing Data Primary Strategy**:
   - Extract primary method: CCA, simple imputation, MICE, multiple imputation, survey-compatible imputation, model-based handling, pattern-mixture/selection model, variable exclusion, or another SAP-specified method
   - Extract sensitivity analyses separately
   - Output: "missing_contract": {"primary": "<SAP-specified method>", "sensitivity": ["CCA", "worst_case"]}
   - Enforcement: State primary method clearly, do not mix with sensitivity methods
   - If the SAP includes `deviation_record`, preserve it in the sub-prompt and follow `deviation_record.accepted_method` instead of reverting to the original default recommendation

These contracts are MANDATORY. A finalized SAP and its accepted `deviation_record` are authoritative; violations will be detected and flagged in output validation.

**Controlled Deviation Preservation (MANDATORY)**:
- If any protocol/SAP component contains `deviation_record`, copy the relevant fields into the corresponding sub-prompt
- If `deviation_record.is_deviation_from_default` is true, the sub-prompt must instruct the code generator to implement `deviation_record.accepted_method`
- Do not write sub-prompts that silently revert accepted deviations to the default decision-tree pathway
- Require the generated R code to record a `controlled_deviation_audit` entry in `analysis_summary.json` and print a "Controlled deviation audit" section in the execution log

**CRITICAL: Design Variable Preservation (MANDATORY)**:
- NEVER filter data by design variables (weight, strata, PSU) unless protocol explicitly requires subsetting
- ALWAYS preserve all levels when converting categorical variables to factors: use `factor(var, levels = unique(var[!is.na(var)]))`
- NEVER use `droplevels()` on design variables
- If design variable (strata/PSU) has < 2 levels: STOP and report error (indicates incorrect data filtering)
- Verify levels BEFORE analysis: report level counts in console

## Data and Variable Requirements
- **Data reading path**:
  - First stage (7.1): Use original data file `data.csv`
  - Subsequent stages: Read data from `../7.X/main_output.csv` (fallback to `data.csv` if not exists)
- **Key variables**:
  - **⚠️ Strict constraint**: Only use variables that exist in actual data file, do not reference non-existent variables
  - **Actual variable list**: [Must list real variables based on provided actual data variable information]
  - **Variable mapping**: If variable names in research protocol differ from actual data, use actual data variable names
  - **Variable types**: Determine analysis methods based on variable types in actual data (continuous/categorical)
- **Previous stage information inheritance**: If previous stage's `analysis_summary.json` exists, must read its `critical_decisions` field

## Variable Selection Strategy
**Detect research protocol requirements**:
- If protocol requires a priori confounder selection (e.g., based on DAG, backdoor criterion, theoretical framework):
  - Strictly follow protocol's predefined variable set
  - Prohibit variable selection adjustments based on bivariate analysis p-values
  - Previous stage information only used for data quality validation and variable encoding
- Otherwise use data-driven mode:
  - Seed variables as starting point, dynamically adjust based on previous stage statistical findings
  - Integrate previous stage bivariate analysis and effect size findings

## Execution Requirements
1. **Sub-prompt absolute priority**: Strictly execute according to sub-prompt requirements, do not omit, replace, or add other methods
2. **Global decisions as supplementary**: Previous stage information only for parameter adjustment, do not change sub-prompt's core requirements
3. **Mandatory validation**: Each statistical method must include start marker, execution code, result validation, completion confirmation
4. **⚠️ Multivariable analysis section requirements** (e.g., association analysis, regression analysis):
   
   **a) Analysis process completeness**:
   - Must include: **Bivariate analysis (univariate) → Multivariable analysis**
   - Bivariate analysis: Independent association of each exposure variable with outcome variable
   - Multivariable analysis: Comprehensive model adjusted for confounders
   
   **b) Model formula specification**:
   - **Must provide complete R code model formula examples**, not just text descriptions
   - **No vague expressions**: Do not use "etc.", "...", "other" or similar omissions
   - Model formula must list all required variables one by one:
     * Outcome variable (explicitly list)
     * Main exposure variables (list one by one, do not omit)
     * **Adjustment variables (according to protocol requirements: use minimal adjustment set for a priori selection, use screened variables for data-driven)**
     * Random effects (if any, explicitly specify)
     * Weight variables (if any, explicitly specify)
   - Example format:
   ```r
   # [Model name] (e.g., Main outcome log-binomial GLMM)
   [function_name](outcome_variable ~ 
            # Main exposures
            exposure1 + exposure2 + exposure3 +
            # Adjustment variables/covariates (must include all, do not omit)
            covariate1 + covariate2 + covariate3 + covariate4 +
            # Random effects
            (1|random_effect_variable),
            family = ...,
            weights = weight_variable)
   ```
   - Must add warning after model formula: **"⚠️ All above variables must be included in the model, do not omit any"**
   
   **c) Graceful degradation strategy**:
   - If involving complex models that may fail to converge, must clearly specify alternative approach order, e.g.:
     * Preferred: Log-binomial GLMM
     * Alternative 1: Modified Poisson GLMM (if preferred fails)
     * Alternative 2: Logistic GLMM (if alternative 1 still fails)
     * Fallback: Survey-weighted GLM (ensure at least some results)

## Output Requirements
1. **Standard output files** (required):
   - `main_output.csv`: Processed data file
   - `analysis_summary.json`: Key analysis findings summary
   - Related tables (CSV format): Clearly list all required table filenames
     * **⚠️ Regression/association analysis sections special requirement**: Must output complete model coefficient table, including **all variables** (exposure + adjustment variables) with coefficients, 95%CI, P-values, not just main effects
   - Graphics output (PNG format):
     * Clearly list all required graphics filenames
     * **Forest plot rule**: If multiple outcome variables, generate independent forest plot for each outcome
     * Graphics size and resolution requirements (if any)
2. **Graphics language**: Use ENGLISH for all plot labels, titles, and annotations (do NOT use Chinese characters)
3. **Graphics quality requirements** (MANDATORY):
   - **Preferred approach**: Use ggplot2 for all plots (NOT base R barplot/hist/plot)
   - **Theme**: Apply `theme_minimal()` or `theme_bw()` with following settings:
     ```r
     theme_minimal(base_size = 12) + 
       theme(plot.title = element_text(hjust = 0.5, size = 14, face = "bold"),
             axis.text = element_text(size = 10),
             axis.title = element_text(size = 11),
             legend.position = "bottom",
             panel.grid.minor = element_blank())
     ```
   - **Color palette**: Use professional colors (Tableau 10 or similar):
     ```r
     plot_colors <- c("#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", 
                      "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC")
     scale_fill_manual(values = plot_colors)
     ```
   - **Multi-panel layout**: For multiple variables, use `facet_wrap()` or arrange plots in grid (e.g., 3×4, 4×3)
   - **Resolution**: Set `ggsave()` with width=12, height=8, dpi=300 for publication quality
   - **Fallback**: If ggplot2 is not suitable (e.g., specific package outputs), ensure base R plots have:
     * `par(las=1, cex.lab=1.1, cex.axis=0.95, bty="l")`
     * Horizontal axis labels
     * Clear titles and legends
4. **Code requirements**: Use appropriate R packages, code should be concise and efficient with English comments

## Validation Template
Each statistical method must include:
```r
cat("Start execution: [method name]\\n")
# Execution code (strictly follow sub-prompt requirements)
if(!exists("[result object]")) stop("Error: [method name] execution failed!")
cat("Validation passed: [method name] execution successful\\n")
```
```

## Generation Rules
1. **Generate one sub-prompt per protocol subsection** (7.1, 7.2, 7.3, etc.), do NOT skip subsections unless explicitly excluded below
2. Strictly extract original text from protocol Section 7.0, do not summarize or replace
3. **⚠️ Variable constraint**: Only use variables that exist in actual data file, do not reference non-existent variables
4. **Variable mapping**: If variable names in research protocol differ from actual data, use actual data variable names
5. Ensure sub-prompts contain specific method guidance and execution requirements
6. Keep sub-prompt structure clear with highlighted key points
7. **⚠️ Exclude non-analytical sections**: Do not generate sub-prompts for "reporting standards", "publication guidelines", "STROBE statement", "CONSORT checklist", "final report generation" and other non-statistical analysis sections

## Special Module Merging Rules

**⚠️ MANDATORY: Model diagnostics MUST be merged into modeling sections**:
- If protocol has independent "model diagnostics" subsection (e.g., 7.6 Model Diagnostics following 7.5 Modeling), **merge it into the modeling subsection** (7.5)
- **FORBIDDEN to generate independent sub-prompt for model diagnostics**
- **Reason**: Diagnostics require model objects (residuals, fitted values, Cook's D) that cannot be transferred across stages

**Integration example**:
```
❌ Wrong separation:
- 7.5 Association Analysis (model fitting)
- 7.6 Model Diagnostics (independent module, needs to refit model)

✅ Correct integration:
- 7.5 Association Analysis (includes: model fitting + model diagnostics + result interpretation)
  - Fit GLMM model
  - Diagnostic plots (residual plot, QQ plot, Cook's distance plot)
  - Collinearity tests (VIF)
  - Model goodness-of-fit assessment
  - Result tables and forest plots
```

**Other modules that can be independent or integrated**:
- **Sensitivity analysis**: Generate as independent sub-prompt if protocol explicitly defines separate sensitivity analysis section (e.g., Section 7.8)
- **Subgroup analysis**: Can be independent or integrated into main analysis, depending on complexity
- **Interaction analysis**: Usually independent if protocol defines separate interaction analysis section (e.g., Section 7.7)

## Output Format Requirements

**⚠️ Important: Generate all sub-prompts at once**
- Do not stop to ask or wait for confirmation
- Do not say "due to space limitations"
- Output all 7.X section complete sub-prompts at once
- Each sub-prompt is independent and complete, do not omit any part

Each sub-prompt must be output in the following format:

```markdown
# Statistical Analysis Task: SAP 7.X - [Section Name]

## Core Statistical Methods
[Specific statistical method content]

## Data and Variable Requirements
[Data requirement content]

## Variable Selection Strategy
[Variable selection content]

## Execution Requirements
[Execution requirement content]

## Output Requirements
[Output requirement content]

## Validation Template
[Validation template content]
```

**Important reminders:**
- **⚠️ Variable constraint**: Only use variables that exist in actual data file, do not reference non-existent variables
- **Variable mapping**: If variable names in research protocol differ from actual data, use actual data variable names
- Each sub-prompt must be output independently
- Use standard section number format (7.1, 7.2, 7.3, etc.)
- Avoid special characters in filenames
- Ensure section numbers can be correctly parsed

## Stage-Specific Requirements

**Stage 7.0/7.1 Data Preparation & Quality Control - Distribution/Diagnostic Plot Rule (MANDATORY)**:

For data quality control and initial descriptive stage, graphics output MUST include:

1. **Outlier Boxplots**: 
   - Include ALL continuous variables (n_unique > 10)
   - Multi-panel layout: Use `facet_wrap()` or `par(mfrow=c(rows, cols))`
   - If > 16 variables: Split into multiple plots (e.g., part1.png, part2.png)
   - Highlight outliers in red color

2. **Distribution Charts**:
   - **Continuous variables**: Histograms for ALL continuous variables (n_unique > 10)
   - **Categorical variables**: Bar charts for ALL categorical variables (n_unique ≤ 20)
   - Multi-panel layout: e.g., 4×4 grid, adjust based on variable count
   - If > 16 variables: Split into multiple plots with clear naming

3. **Layout Guidelines**:
   - Prefer 3-4 variables per row
   - Max 4 rows per plot
   - If total variables > 16: Create part1, part2, etc.
   - Example: 20 continuous vars → `distribution_continuous_part1.png` (16 vars, 4×4) + `part2.png` (4 vars, 2×2)

4. **Quality Requirements**:
   - Use ggplot2 + facet_wrap() for consistency
   - Clear variable names as subplot titles
   - Unified color scheme across all panels
