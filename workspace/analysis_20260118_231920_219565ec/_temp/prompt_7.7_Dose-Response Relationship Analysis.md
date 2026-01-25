# Statistical Analysis Task: SAP 7.7 - Dose-Response Relationship Analysis

## Core Statistical Methods
**Verbatim from Protocol Section 2.2.2 (Secondary Objectives):**
- **Purpose**: Explore dose-response relationships between major modifiable lifestyle factors (e.g., physical exercise frequency, dietary patterns) and radial osteoporosis prevalence
- **Continuous exposures**: Assess linear or non-linear associations between continuous exposure variables (intellectual ability, hemoglobin, fasting blood glucose) and radial BMD
- **Methods**:
  - Ordinal exposures (e.g., Exercise_Frequency): Test for linear trend using ordinal coding
  - Continuous exposures: Use Restricted Cubic Splines (RCS) to model non-linear relationships
  - Report: Dose-response curves with 95% CI bands

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
- Ordinal exposures: Exercise_Frequency (4 levels: No_Exercise < Occasional < Weekly_Or_More < Daily), Alcohol_Frequency (4 levels)
- Continuous exposures: Hemoglobin, Fasting_Glucose, Age, BMI
- Outcome: Osteoporosis_Status (binary), Bone_Mineral_Density (continuous)

**3. Covariate Adjustment Strategy:**
```json
{
  "adjustment_mode": "DAG_fixed",
  "covariates": ["Age", "Gender", "Geographic_Region", "BMI"],
  "note": "Same adjustment set as main model"
}
```

**4. Missing Data Primary Strategy:**
- Use all m=20 imputed datasets from 7.2, pool results via Rubin's Rules

## Data and Variable Requirements
- **Data reading path**: `../7.2/imputed_datasets.rds`
- **Key variables** (ACTUAL data):
  - **Ordinal exposures**: Exercise_Frequency (4 levels), Alcohol_Frequency (4 levels)
  - **Continuous exposures**: Hemoglobin, Fasting_Glucose, Age, BMI
  - **Outcome**: Osteoporosis_Status, Bone_Mineral_Density
  - **Adjustment covariates**: Age, Gender, Geographic_Region, BMI
- **Previous stage information**: Read `../7.5/analysis_summary.json` for main effect estimates

## Variable Selection Strategy
**Pre-specified mode:**
- Test dose-response for pre-specified exposures only: Exercise_Frequency, Alcohol_Frequency, Hemoglobin, Fasting_Glucose
- Do NOT test all possible exposures

## Execution Requirements
1. **Ordinal exposures (linear trend test)**:
   - Assign ordinal scores: Exercise_Frequency (0=No_Exercise, 1=Occasional, 2=Weekly_Or_More, 3=Daily)
   - Fit model with ordinal score as continuous predictor:
   ```r
   svyglm(Osteoporosis_Status ~ Exercise_Frequency_Score + Age + Gender + Geographic_Region + BMI, 
          design, family = quasipoisson(link = "log"))
   ```
   - Test linear trend: P-value for ordinal score coefficient
2. **Continuous exposures (RCS)**:
   - Use Restricted Cubic Splines with 3-5 knots (placed at quantiles)
   - Fit model:
   ```r
   library(rms)
   svyglm(Bone_Mineral_Density ~ rcs(Hemoglobin, 4) + Age + Gender + Geographic_Region + BMI, 
          design, family = gaussian())
   ```
   - Test non-linearity: Wald test for non-linear terms
3. **Dose-response curves**:
   - Predict outcome across range of exposure values
   - Plot predicted values with 95% CI bands
4. **Pooling**: Pool estimates across MICE datasets using Rubin's Rules
5. **Validation**: Each step must include start marker, execution code, result validation, completion confirmation

## Output Requirements
1. **Standard output files**:
   - `main_output.csv`: Same as input
   - `dose_response_results.csv`: Linear trend tests and non-linearity tests (columns: Exposure, Outcome, Linear_Trend_P, Nonlinearity_P)
   - `analysis_summary.json`:
     ```json
     {
       "stage": "7.7_dose_response_analysis",
       "ordinal_exposures": ["Exercise_Frequency", "Alcohol_Frequency"],
       "continuous_exposures": ["Hemoglobin", "Fasting_Glucose"],
       "significant_trends": ["Exercise_Frequency (linear)", ...],
       "critical_decisions": {
         "rcs_knots": 4,
         "note": "Non-linearity tested via Wald test"
       }
     }
     ```

2. **Graphics output (PNG, ENGLISH labels)**:
   - `dose_response_ordinal.png`: Dose-response curves for ordinal exposures (e.g., Exercise_Frequency)
   - `dose_response_continuous.png`: Dose-response curves for continuous exposures (e.g., Hemoglobin, Fasting_Glucose) with RCS
   - **Quality requirements**:
     ```r
     library(ggplot2)
     library(rms)
     # Example: RCS dose-response curve for Hemoglobin
     pred_data <- data.frame(Hemoglobin = seq(min(data$Hemoglobin), max(data$Hemoglobin), length.out = 100),
                             Age = mean(data$Age), Gender = "Male", Geographic_Region = "West_Coast", BMI = mean(data$BMI))
     pred_data$BMD_pred <- predict(model_rcs, newdata = pred_data, se.fit = TRUE)
     ggplot(pred_data, aes(x = Hemoglobin, y = BMD_pred)) +
       geom_line(color = "#4E79A7", size = 1.2) +
       geom_ribbon(aes(ymin = BMD_pred - 1.96*se, ymax = BMD_pred + 1.96*se), alpha = 0.2, fill = "#4E79A7") +
       theme_minimal(base_size = 12) +
       labs(title = "Dose-Response: Hemoglobin vs Bone Mineral Density", x = "Hemoglobin (g/L)", y = "Predicted BMD (g/cm²)")
     ggsave("dose_response_continuous.png", width = 10, height = 6, dpi = 300)
     ```

3. **Code requirements**: Use R with survey, rms, ggplot2 packages; English comments

## Validation Template
```r
cat("Start execution: Ordinal Trend Test\n")
library(survey)
design <- svydesign(ids = ~1, strata = ~Geographic_Region, weights = ~Sampling_Weight, data = data, nest = TRUE)
data$Exercise_Score <- as.numeric(factor(data$Exercise_Frequency, levels = c("No_Exercise", "Occasional", "Weekly_Or_More", "Daily"))) - 1
model_trend <- svyglm(Osteoporosis_Status ~ Exercise_Score + Age + Gender + Geographic_Region + BMI, design, family = quasipoisson(link = "log"))
if(!exists("model_trend")) stop("Error: Ordinal trend test failed!")
cat("Validation passed: Ordinal trend test completed\n")

cat("Start execution: RCS Non-linearity Test\n")
library(rms)
model_rcs <- svyglm(Bone_Mineral_Density ~ rcs(Hemoglobin, 4) + Age + Gender + Geographic_Region + BMI, design, family = gaussian())
if(!exists("model_rcs")) stop("Error: RCS model failed!")
cat("Validation passed: RCS non-linearity test completed\n")

cat("Start execution: Dose-Response Curve Prediction\n")
pred_data <- data.frame(Hemoglobin = seq(min(data$Hemoglobin), max(data$Hemoglobin), length.out = 100))
pred_data$BMD_pred <- predict(model_rcs, newdata = pred_data)
if(!exists("pred_data$BMD_pred")) stop("Error: Dose-response prediction failed!")
cat("Validation passed: Dose-response curve prediction completed\n")
```
```

---

## File: prompt_7.8_sensitivity_analysis.md

```markdown
