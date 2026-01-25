# Statistical Analysis Task: SAP 7.5 - Multivariate Modeling and Association Analysis (with Model Diagnostics)

## Core Statistical Methods
**Verbatim from Protocol Section 7.5 + 7.6:**
- **Primary model**: Modified Poisson Regression (log-link, robust variance) to estimate Prevalence Ratio (PR)
- **Alternative models** (graceful degradation):
  1. Preferred: Log-binomial GLMM (if convergence issues)
  2. Alternative 1: Modified Poisson GLMM (if log-binomial fails)
  3. Alternative 2: Logistic GLMM (if Poisson fails)
  4. Fallback: Survey-weighted GLM (ensure at least some results)
- **Continuous outcome**: Weighted Linear Regression for Bone_Mineral_Density
- **Variable inclusion**: Strictly follows DAG-based minimal adjustment set (Age, Gender, Geographic_Region, BMI)
- **Non-linearity**: Quadratic terms or Restricted Cubic Splines (RCS) for ordinal/continuous exposures
- **Pooled inference**: Rubin's Rules for MICE datasets (m=20)
- **Model diagnostics** (Section 7.6):
  - Multicollinearity: VIF > 5 warning, VIF > 10 severe
  - Overdispersion: Pearson χ²/df ratio
  - Goodness-of-fit: Grouped calibration test (weighted Hosmer-Lemeshow)
  - Log-linearity: Check for non-linear relationships
  - Residual diagnostics: Q-Q plots, residual vs fitted plots
  - Outliers: Cook's Distance, DFBETAS

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
- Primary exposure: Exercise_Frequency (Daily vs No_Exercise)
- Secondary exposures: Dietary_Habits, Smoking_Status, Alcohol_Frequency, Hemoglobin, Fasting_Glucose
- Outcome: Osteoporosis_Status (binary: Osteoporosis vs Normal/Low_Bone_Mass), Bone_Mineral_Density (continuous)

**3. Covariate Adjustment Strategy:**
```json
{
  "adjustment_mode": "DAG_fixed",
  "covariates": ["Age", "Gender", "Geographic_Region", "BMI"],
  "exclude_from_main": ["Physical_Function", "Self_Care_Ability"],
  "note": "Strictly follow DAG - NO stepwise regression or p-value screening"
}
```

**4. Missing Data Primary Strategy:**
- Use all m=20 imputed datasets from 7.2, pool results via Rubin's Rules

## Data and Variable Requirements
- **Data reading path**: `../7.2/imputed_datasets.rds` (all m=20 imputed datasets)
- **Key variables** (ACTUAL data):
  - **Outcome**: Osteoporosis_Status (binary: recode to Osteoporosis=1, Normal/Low_Bone_Mass=0), Bone_Mineral_Density (continuous)
  - **Exposures**: Exercise_Frequency (reference: Daily), Dietary_Habits (reference: Balanced), Smoking_Status (reference: Non_Smoker), Alcohol_Frequency (reference: Never), Hemoglobin (continuous), Fasting_Glucose (continuous)
  - **Adjustment covariates**: Age (continuous), Gender (reference: Male), Geographic_Region (reference: West_Coast), BMI (continuous)
- **Previous stage information**: Read `../7.4/analysis_summary.json` for bivariate findings (exploratory only, NOT for variable selection)

## Variable Selection Strategy
**A priori mode (DAG-based):**
- Strictly use DAG-specified adjustment set: Age, Gender, Geographic_Region, BMI
- Do NOT add/remove variables based on bivariate p-values
- Do NOT adjust for mediators (Physical_Function, Self_Care_Ability) or colliders

## Execution Requirements

### Part A: Bivariate Analysis (Univariate Associations)
1. **Survey design declaration**: Same as 7.3
2. **Univariate models** (one exposure at a time, NO adjustment):
   - For each exposure (Exercise_Frequency, Dietary_Habits, Smoking_Status, Alcohol_Frequency, Hemoglobin, Fasting_Glucose):
     * Fit: `svyglm(Osteoporosis_Status ~ Exposure, design, family = quasipoisson(link = "log"))`
     * Report: Crude PR, 95% CI, P-value
3. **Continuous outcome** (Bone_Mineral_Density):
   - Fit: `svyglm(Bone_Mineral_Density ~ Exposure, design, family = gaussian())`
   - Report: Crude β, 95% CI, P-value

### Part B: Multivariable Analysis (Adjusted Models)
1. **Binary outcome (Osteoporosis_Status)**:
   - **Model formula** (COMPLETE, NO OMISSIONS):
   ```r
   # Modified Poisson Regression (Primary Model)
   svyglm(Osteoporosis_Status ~ 
          # Main exposures (list ALL, do NOT omit)
          Exercise_Frequency + Dietary_Habits + Smoking_Status + Alcohol_Frequency + 
          Hemoglobin + Fasting_Glucose +
          # Adjustment covariates (DAG-specified, list ALL)
          Age + Gender + Geographic_Region + BMI,
          design = design,
          family = quasipoisson(link = "log"))
   ```
   **⚠️ All above variables must be included in the model, do not omit any**

   - **Graceful degradation**:
     * If convergence fails: Try log-binomial (`family = binomial(link = "log")`)
     * If still fails: Try Poisson with robust SE (`family = poisson(link = "log")`)
     * If still fails: Use logistic regression (`family = binomial(link = "logit")`) and report OR with warning
     * Fallback: Survey-weighted GLM without random effects

2. **Continuous outcome (Bone_Mineral_Density)**:
   - **Model formula** (COMPLETE, NO OMISSIONS):
   ```r
   # Weighted Linear Regression
   svyglm(Bone_Mineral_Density ~ 
          # Main exposures (list ALL)
          Exercise_Frequency + Dietary_Habits + Smoking_Status + Alcohol_Frequency + 
          Hemoglobin + Fasting_Glucose +
          # Adjustment covariates (list ALL)
          Age + Gender + Geographic_Region + BMI,
          design = design,
          family = gaussian())
   ```
   **⚠️ All above variables must be included in the model, do not omit any**

3. **Pooling across MICE datasets**:
   - Fit models on each of m=20 imputed datasets
   - Pool estimates using Rubin's Rules: `pool()` function
   - Report: Pooled PR/β, 95% CI, P-value

### Part C: Model Diagnostics (Integrated)
1. **Multicollinearity**:
   - Calculate VIF for all covariates
   - Flag VIF > 5 (warning), VIF > 10 (severe)
   - If severe: Consider centering continuous variables or composite scores
2. **Overdispersion** (Poisson model):
   - Calculate Pearson χ²/df ratio
   - If ratio >> 1: Consider Negative Binomial regression in sensitivity analysis
3. **Goodness-of-fit**:
   - Grouped calibration test: Stratify by predicted prevalence deciles, compare observed vs predicted
   - Report calibration plot
4. **Log-linearity** (continuous covariates):
   - Add quadratic terms (e.g., Age², BMI²) to check non-linearity
   - If significant: Use RCS or categorization
5. **Residual diagnostics** (linear model):
   - Q-Q plot of weighted residuals (check normality)
   - Residual vs fitted plot (check homoscedasticity)
6. **Outliers and influential points**:
   - Calculate Cook's Distance (threshold: 4/n)
   - Calculate DFBETAS (threshold: 2/√n)
   - Flag influential points, conduct sensitivity analysis (exclude and refit)

### Part D: Validation
- Each step must include start marker, execution code, result validation, completion confirmation

## Output Requirements
1. **Standard output files**:
   - `main_output.csv`: Same as input
   - `univariate_results.csv`: Crude associations (columns: Exposure, Outcome, PR/Beta, 95%CI, P_Value)
   - `multivariable_results.csv`: Adjusted associations (columns: Exposure, Outcome, Adjusted_PR/Beta, 95%CI, P_Value)
     **⚠️ MUST include ALL variables (exposures + adjustment covariates) with coefficients, 95%CI, P-values**
   - `model_diagnostics.csv`: VIF, overdispersion ratio, calibration test results
   - `influential_points.csv`: Rows with Cook's D > 4/n or |DFBETAS| > 2/√n
   - `analysis_summary.json`:
     ```json
     {
       "stage": "7.5_multivariate_modeling",
       "primary_model": "Modified Poisson Regression",
       "adjustment_set": ["Age", "Gender", "Geographic_Region", "BMI"],
       "convergence_status": "converged",
       "diagnostics": {
         "vif_max": "XXX",
         "overdispersion_ratio": "XXX",
         "influential_points": "XXX"
       },
       "critical_decisions": {
         "model_selection": "Modified Poisson (primary)",
         "adjustment_strategy": "DAG-based minimal set"
       }
     }
     ```

2. **Graphics output (PNG, ENGLISH labels)**:
   - `forest_plot_osteoporosis.png`: Forest plot for Osteoporosis_Status outcome (all exposures, adjusted PR)
   - `forest_plot_bmd.png`: Forest plot for Bone_Mineral_Density outcome (all exposures, adjusted β)
   - `calibration_plot.png`: Observed vs predicted prevalence by deciles
   - `residual_plots.png`: Q-Q plot + residual vs fitted plot (linear model)
   - `cooks_distance.png`: Cook's Distance plot with threshold line
   - **Quality requirements**:
     ```r
     library(ggplot2)
     library(forestplot)
     # Forest plot example
     forestplot(mean = pr_estimates, lower = ci_lower, upper = ci_upper, 
                labeltext = exposure_names, 
                xlab = "Prevalence Ratio (95% CI)", 
                col = fpColors(box = "#4E79A7", line = "#4E79A7"))
     ggsave("forest_plot_osteoporosis.png", width = 10, height = 8, dpi = 300)
     ```

3. **Code requirements**: Use R with survey, mice, mitools, ggplot2, forestplot packages; English comments

## Validation Template
```r
cat("Start execution: Univariate Models\n")
library(survey)
design <- svydesign(ids = ~1, strata = ~Geographic_Region, weights = ~Sampling_Weight, data = data, nest = TRUE)
model_crude <- svyglm(Osteoporosis_Status ~ Exercise_Frequency, design, family = quasipoisson(link = "log"))
if(!exists("model_crude")) stop("Error: Univariate model failed!")
cat("Validation passed: Univariate models completed\n")

cat("Start execution: Multivariable Model\n")
model_adjusted <- svyglm(Osteoporosis_Status ~ Exercise_Frequency + Dietary_Habits + Smoking_Status + Alcohol_Frequency + Hemoglobin + Fasting_Glucose + Age + Gender + Geographic_Region + BMI, design, family = quasipoisson(link = "log"))
if(!exists("model_adjusted")) stop("Error: Multivariable model failed!")
cat("Validation passed: Multivariable model completed\n")

cat("Start execution: Pooling Across MICE Datasets\n")
library(mice)
library(mitools)
imp <- readRDS("../7.2/imputed_datasets.rds")
fit <- with(imp, svyglm(Osteoporosis_Status ~ Exercise_Frequency + Age + Gender + Geographic_Region + BMI, design, family = quasipoisson(link = "log")))
pooled <- pool(fit)
if(!exists("pooled")) stop("Error: Pooling failed!")
cat("Validation passed: Pooling completed\n")

cat("Start execution: VIF Calculation\n")
library(car)
vif_values <- vif(model_adjusted)
if(!exists("vif_values")) stop("Error: VIF calculation failed!")
cat("Validation passed: VIF calculation completed\n")

cat("Start execution: Cook's Distance\n")
cooks_d <- cooks.distance(model_adjusted)
influential <- which(cooks_d > 4/nrow(data))
if(!exists("influential")) stop("Error: Cook's Distance calculation failed!")
cat("Validation passed: Cook's Distance calculation completed\n")
```
```

---

## File: prompt_7.6_interaction_effect_modification_analysis.md

```markdown
