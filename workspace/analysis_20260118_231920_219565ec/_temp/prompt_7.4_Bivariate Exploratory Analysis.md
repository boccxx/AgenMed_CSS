# Statistical Analysis Task: SAP 7.4 - Bivariate Exploratory Analysis

## Core Statistical Methods
**Verbatim from Protocol Section 7.4:**
- **Purpose**: (1) Understand raw associations between exposure and outcome; (2) Identify covariate distributions; (3) Detect non-linearity
- **Pairs**: Exposure-Outcome, Exposure-Covariate, Outcome-Covariate, Continuous-Continuous correlations
- **Statistical tests** (all under complex survey framework):
  - Categorical vs Categorical: Rao-Scott Corrected Chi-square Test
  - Continuous vs Categorical: Complex survey weighted t-test (2 groups) or design-based F-test (multi-group)
  - Continuous vs Continuous: Weighted linear regression slope or design-weighted Pearson/Spearman correlation
- **Methodological control**:
  - P-values are exploratory only
  - NOT used for variable selection
  - DAG determines adjustment sets, regardless of bivariate significance

## Hard Constraint Extraction (Contract Enforcement)

**1. Sampling Design Contract:**
```json
{
  "design_contract": {
    "weight": "Sampling_Weight",
    "strata": "Geographic_Region",
    "psu": null
  },
  "design_mode": "stratified_weighted"
}
```

**2. Estimand & Exposure Definition:**
- Primary exposure: Exercise_Frequency (4 levels)
- Secondary exposures: Dietary_Habits, Smoking_Status, Alcohol_Frequency, Hemoglobin, Fasting_Glucose
- Outcome: Osteoporosis_Status (binary: Osteoporosis vs Normal/Low_Bone_Mass), Bone_Mineral_Density (continuous)

**3. Covariate Adjustment Strategy:**
```json
{
  "adjustment_mode": "bivariate_only",
  "note": "NO adjustment in bivariate analysis - raw associations only"
}
```

**4. Missing Data Primary Strategy:**
- Use first imputed dataset (m=1) from 7.2 output

## Data and Variable Requirements
- **Data reading path**: `../7.2/main_output.csv`
- **Key variables** (from actual data):
  - **Exposures**: Exercise_Frequency, Dietary_Habits, Smoking_Status, Alcohol_Frequency, Hemoglobin, Fasting_Glucose
  - **Outcomes**: Osteoporosis_Status, Bone_Mineral_Density
  - **Covariates**: Age, Gender, Geographic_Region, BMI, Self_Rated_Health, Self_Care_Ability, Physical_Function
- **Previous stage information**: Read `../7.3/analysis_summary.json` for exposure grouping

## Variable Selection Strategy
**Exploratory mode:**
- Test all exposure-outcome pairs
- Test all exposure-covariate pairs
- Test all outcome-covariate pairs
- Do NOT use p-values for variable selection in subsequent models

## Execution Requirements
1. **Survey design declaration**: Same as 7.3
2. **Bivariate tests** (per protocol Appendix 7.C checklist):
   - **Exposure vs Outcome**:
     * Exercise_Frequency (categorical) vs Osteoporosis_Status (categorical): Rao-Scott Chi-square
     * Exercise_Frequency (categorical) vs Bone_Mineral_Density (continuous): Design-based F-test
   - **Exposure vs Covariates**:
     * Exercise_Frequency vs Age, Gender, Geographic_Region, BMI: Appropriate tests
   - **Outcome vs Covariates**:
     * Osteoporosis_Status vs Age, Gender, Geographic_Region, BMI, Hemoglobin, Fasting_Glucose: Appropriate tests
   - **Continuous-Continuous correlations**:
     * Bone_Mineral_Density vs Age, BMI, Hemoglobin, Fasting_Glucose: Weighted Pearson correlation
3. **Non-linearity detection**:
   - Plot scatter plots with LOESS smoothing for continuous-continuous pairs
   - Check for U-shaped or threshold effects
4. **Validation**: Each test must include start marker, execution code, result validation, completion confirmation

## Output Requirements
1. **Standard output files**:
   - `main_output.csv`: Same as input
   - `bivariate_results.csv`: All test results with columns: Exposure, Outcome, Test_Type, Statistic, P_Value, Effect_Size
   - `analysis_summary.json`:
     ```json
     {
       "stage": "7.4_bivariate_analysis",
       "n_tests": "XXX",
       "significant_associations": ["Exercise_Frequency vs Osteoporosis_Status", ...],
       "critical_decisions": {
         "note": "P-values are exploratory only - NOT used for variable selection"
       }
     }
     ```

2. **Graphics output (PNG, ENGLISH labels)**:
   - `bivariate_categorical.png`: Mosaic plots or grouped bar charts for categorical-categorical pairs
   - `bivariate_continuous.png`: Boxplots for categorical-continuous pairs
   - `correlation_matrix.png`: Heatmap of weighted correlations for continuous variables
   - `scatter_plots.png`: Scatter plots with LOESS smoothing for key continuous-continuous pairs
   - **Quality requirements**:
     ```r
     library(ggplot2)
     # Example: Boxplot for Exercise_Frequency vs Bone_Mineral_Density
     ggplot(data, aes(x = Exercise_Frequency, y = Bone_Mineral_Density, weight = Sampling_Weight)) +
       geom_boxplot() +
       theme_minimal(base_size = 12) +
       labs(title = "Bone Mineral Density by Exercise Frequency", x = "Exercise Frequency", y = "BMD (g/cm²)")
     ggsave("bivariate_continuous.png", width = 10, height = 6, dpi = 300)
     ```

3. **Code requirements**: Use R with survey, ggplot2 packages; English comments

## Validation Template
```r
cat("Start execution: Rao-Scott Chi-square Test\n")
library(survey)
design <- svydesign(ids = ~1, strata = ~Geographic_Region, weights = ~Sampling_Weight, data = data, nest = TRUE)
chisq_result <- svychisq(~Exercise_Frequency + Osteoporosis_Status, design, statistic = "Chisq")
if(!exists("chisq_result")) stop("Error: Rao-Scott Chi-square test failed!")
cat("Validation passed: Rao-Scott Chi-square test completed\n")

cat("Start execution: Design-based F-test\n")
f_result <- svyglm(Bone_Mineral_Density ~ Exercise_Frequency, design, family = gaussian())
anova_result <- anova(f_result, test = "F")
if(!exists("anova_result")) stop("Error: Design-based F-test failed!")
cat("Validation passed: Design-based F-test completed\n")

cat("Start execution: Weighted Correlation\n")
cor_result <- svycor(~Bone_Mineral_Density + Age, design)
if(!exists("cor_result")) stop("Error: Weighted correlation failed!")
cat("Validation passed: Weighted correlation completed\n")
```
```

---

## File: prompt_7.5_multivariate_modeling_association_analysis.md

```markdown
