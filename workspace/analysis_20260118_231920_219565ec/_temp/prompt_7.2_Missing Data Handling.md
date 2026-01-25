# Statistical Analysis Task: SAP 7.2 - Missing Data Handling

## Core Statistical Methods
**Verbatim from Protocol Section 7.2:**
- **Primary method**: Multiple Imputation by Chained Equations (MICE)
- **Framework**: Generate 20–50 imputed datasets
- **Inclusion**: All analysis variables (outcomes, exposures, covariates) + auxiliary variables
- **Model specification**: Conditional models tailored to variable types (PMM for continuous, Logistic for binary)
- **Convergence**: Assess via trace plots
- **Pooling**: Use Rubin's Rules to merge estimates
- **Sensitivity analyses**: 
  - Complete Case Analysis (CCA)
  - MNAR Pattern-Mixture Models (Delta-adjustment for key variables)

## Hard Constraint Extraction (Contract Enforcement)

**1. Sampling Design Contract:**
```json
{
  "design_contract": {
    "weight": "Sampling_Weight",
    "strata": "Geographic_Region",
    "psu": null
  },
  "design_mode": "stratified_weighted",
  "note": "MICE imputation MUST preserve design structure - use survey weights in imputation models"
}
```

**2. Estimand & Exposure Definition:**
- Inherited from 7.1: Exercise_Frequency (primary), Dietary_Habits, Smoking_Status, Alcohol_Frequency, Hemoglobin, Fasting_Glucose
- Outcome: Osteoporosis_Status, Bone_Mineral_Density

**3. Covariate Adjustment Strategy:**
```json
{
  "adjustment_mode": "DAG_fixed",
  "covariates": ["Age", "Gender", "Geographic_Region", "BMI"],
  "note": "Include all DAG covariates in imputation models to strengthen MAR assumption"
}
```

**4. Missing Data Primary Strategy:**
```json
{
  "missing_contract": {
    "primary": "MICE",
    "m_imputations": 20,
    "sensitivity": ["CCA", "MNAR_delta_adjustment"]
  }
}
```

## Data and Variable Requirements
- **Data reading path**: `../7.1/main_output.csv` (fallback to `data.csv` if not exists)
- **Key variables** (from actual data):
  - **Variables with missing**: Hemoglobin (3.1%), Fasting_Glucose (0.9%), Total_Bilirubin (3.1%), Serum_Creatinine (3.1%), Blood_Urea_Nitrogen (3.1%), Total_Cholesterol (3.1%), Triglycerides (3.1%), Self_Rated_Health (0.2%)
  - **Variables to exclude**: Cerebrovascular_Disease (95.7% missing), Other_Neurological_Diseases (99.9% missing)
  - **Imputation model variables**: All analysis variables + auxiliary variables (e.g., biochemical markers)
- **Previous stage information**: Read `../7.1/analysis_summary.json` for `critical_decisions` (design variables, excluded variables)

## Variable Selection Strategy
**A priori mode:**
- Include all DAG-specified covariates in imputation models
- Add auxiliary variables (biochemical markers) to strengthen MAR assumption
- Do NOT use p-value screening for imputation model variables

## Execution Requirements
1. **Missing diagnosis** (from 7.1 output):
   - Read missing rates from `../7.1/analysis_summary.json`
   - Generate missing pattern matrix plot
   - Assess MAR assumption: Test associations between missing indicators and observed covariates
2. **MICE imputation**:
   - Set m=20 imputations (increase to 50 if convergence issues)
   - Specify methods: `pmm` for continuous (Age, BMI, Hemoglobin, Fasting_Glucose, biochemical markers), `logreg` for binary (Gender, Smoking_Status), `polyreg` for categorical (Exercise_Frequency, Dietary_Habits, Osteoporosis_Status)
   - Include survey weights in imputation: Use `mice(..., weights = Sampling_Weight)`
   - Preserve design variables: Ensure Geographic_Region, Sampling_Weight are NOT imputed
   - Convergence check: Plot trace plots for key variables (Hemoglobin, Fasting_Glucose)
3. **Pooling**:
   - Pool estimates using Rubin's Rules (via `pool()` function)
   - Report pooled means, SDs, and 95% CIs for key variables
4. **Sensitivity analyses**:
   - **CCA**: Repeat descriptive statistics on complete cases only
   - **MNAR**: For Hemoglobin (potential MNAR), apply Delta-adjustment (shift imputed values by ±0.5 SD)
5. **Validation**: Each step must include start marker, execution code, result validation, completion confirmation

## Output Requirements
1. **Standard output files**:
   - `main_output.csv`: First imputed dataset (m=1) for downstream analysis
   - `imputed_datasets.rds`: All m=20 imputed datasets (R object for pooling)
   - `analysis_summary.json`:
     ```json
     {
       "stage": "7.2_missing_data_handling",
       "method": "MICE",
       "m_imputations": 20,
       "convergence": "converged",
       "missing_rates_before": {"Hemoglobin": 0.031, ...},
       "missing_rates_after": {"Hemoglobin": 0.0, ...},
       "critical_decisions": {
         "imputation_method": "MICE with survey weights",
         "auxiliary_variables": ["Total_Bilirubin", "Serum_Creatinine", ...],
         "sensitivity_analyses": ["CCA", "MNAR_delta_adjustment"]
       }
     }
     ```
   - `cca_comparison.csv`: Comparison of means/proportions between MICE and CCA

2. **Graphics output (PNG, ENGLISH labels)**:
   - `missing_pattern.png`: Missing pattern matrix (VIM package)
   - `trace_plots.png`: Convergence trace plots for key variables (Hemoglobin, Fasting_Glucose)
   - `density_comparison.png`: Density plots comparing observed vs imputed values
   - **Quality requirements**:
     ```r
     library(mice)
     library(VIM)
     # Missing pattern
     aggr(data, col = c("#4E79A7", "#E15759"), numbers = TRUE, sortVars = TRUE)
     # Trace plots
     plot(imp, c("Hemoglobin", "Fasting_Glucose"))
     # Density comparison
     densityplot(imp, ~Hemoglobin + Fasting_Glucose)
     ```

3. **Code requirements**: Use R with mice, VIM, survey packages; English comments

## Validation Template
```r
cat("Start execution: Missing Diagnosis\n")
library(mice)
md.pattern(data, plot = FALSE)
missing_rates <- colMeans(is.na(data))
if(!exists("missing_rates")) stop("Error: Missing diagnosis failed!")
cat("Validation passed: Missing diagnosis completed\n")

cat("Start execution: MICE Imputation\n")
imp <- mice(data, m = 20, method = "pmm", seed = 123, printFlag = FALSE)
if(!exists("imp")) stop("Error: MICE imputation failed!")
cat("Validation passed: MICE imputation completed\n")

cat("Start execution: Convergence Check\n")
plot(imp, c("Hemoglobin", "Fasting_Glucose"))
if(any(is.na(complete(imp, 1)$Hemoglobin))) stop("Error: Imputation incomplete!")
cat("Validation passed: Convergence check passed\n")

cat("Start execution: Pooling\n")
library(survey)
# Example: Pool means
fit <- with(imp, lm(Bone_Mineral_Density ~ Age + Gender))
pooled <- pool(fit)
if(!exists("pooled")) stop("Error: Pooling failed!")
cat("Validation passed: Pooling completed\n")
```
```

---

## File: prompt_7.3_descriptive_statistics_table1.md

```markdown
