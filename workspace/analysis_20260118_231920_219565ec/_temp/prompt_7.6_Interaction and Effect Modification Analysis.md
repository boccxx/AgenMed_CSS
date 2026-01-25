# Statistical Analysis Task: SAP 7.6 - Interaction and Effect Modification Analysis

## Core Statistical Methods
**Verbatim from Protocol Section 7.7:**
- **Purpose**: Examine whether gender, age group, and residential economic circle modify the association between major exposures and bone health
- **Model construction**: Add "Exposure × Moderator" product term to main effect model
- **Covariate adjustment**: Same as main model (Age, Gender, Geographic_Region, BMI)
- **Multiplicity control**: Benjamini–Hochberg (BH) procedure to control False Discovery Rate (FDR)
- **Reporting**: Report both raw P-values and corrected q-values
- **Stratified analysis**: Produce stratified effect estimates (PR or β with 95% CI) and interaction plots ONLY if interaction term is significant (q < 0.05)
- **Interpretation**: If interaction term is NOT significant, main effect model results prevail

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
- Moderators: Gender (Male vs Female), Age_Group (65-74 vs 75-84 vs ≥85), Geographic_Region (West_Coast vs Pingyi vs Boxing)
- Outcome: Osteoporosis_Status (binary), Bone_Mineral_Density (continuous)

**3. Covariate Adjustment Strategy:**
```json
{
  "adjustment_mode": "DAG_fixed",
  "covariates": ["Age", "Gender", "Geographic_Region", "BMI"],
  "note": "If moderator is in adjustment set, do NOT repeat main effect term"
}
```

**4. Missing Data Primary Strategy:**
- Use all m=20 imputed datasets from 7.2, pool results via Rubin's Rules

## Data and Variable Requirements
- **Data reading path**: `../7.2/imputed_datasets.rds`
- **Key variables** (ACTUAL data):
  - **Exposures**: Exercise_Frequency, Dietary_Habits, Smoking_Status, Alcohol_Frequency, Hemoglobin, Fasting_Glucose
  - **Moderators**: Gender (2 levels), Age_Group (create from Age: 65-74, 75-84, ≥85), Geographic_Region (3 levels)
  - **Outcome**: Osteoporosis_Status, Bone_Mineral_Density
  - **Adjustment covariates**: Age, Gender, Geographic_Region, BMI
- **Previous stage information**: Read `../7.5/analysis_summary.json` for main effect estimates

## Variable Selection Strategy
**Pre-specified mode:**
- Test interactions for pre-specified moderators only: Gender, Age_Group, Geographic_Region
- Do NOT test all possible interactions (avoid data dredging)

## Execution Requirements
1. **Create Age_Group variable**:
   ```r
   data$Age_Group <- cut(data$Age, breaks = c(65, 75, 85, Inf), labels = c("65-74", "75-84", "≥85"), right = FALSE)
   ```
2. **Interaction models** (for each exposure-moderator pair):
   - **Model formula** (example: Exercise_Frequency × Gender):
   ```r
   svyglm(Osteoporosis_Status ~ 
          Exercise_Frequency + Gender + Exercise_Frequency:Gender +
          Age + Geographic_Region + BMI,
          design = design,
          family = quasipoisson(link = "log"))
   ```
   - Extract interaction term P-value
3. **FDR control**:
   - Collect all interaction term P-values
   - Apply BH procedure: `p.adjust(p_values, method = "BH")`
   - Report q-values
4. **Stratified analysis** (ONLY if q < 0.05):
   - Fit separate models within each moderator level
   - Report stratified PR/β with 95% CI
   - Generate interaction plots
5. **Pooling**: Pool estimates across MICE datasets using Rubin's Rules
6. **Validation**: Each step must include start marker, execution code, result validation, completion confirmation

## Output Requirements
1. **Standard output files**:
   - `main_output.csv`: Same as input
   - `interaction_results.csv`: All interaction tests (columns: Exposure, Moderator, Outcome, Interaction_P, Interaction_Q)
   - `stratified_results.csv`: Stratified estimates for significant interactions (columns: Exposure, Moderator, Moderator_Level, Outcome, Stratified_PR/Beta, 95%CI, P_Value)
   - `analysis_summary.json`:
     ```json
     {
       "stage": "7.6_interaction_analysis",
       "n_interactions_tested": "XXX",
       "significant_interactions": ["Exercise_Frequency × Gender", ...],
       "critical_decisions": {
         "fdr_threshold": 0.05,
         "note": "Stratified analysis conducted only for significant interactions"
       }
     }
     ```

2. **Graphics output (PNG, ENGLISH labels)**:
   - `interaction_plots.png`: Interaction plots for significant interactions (e.g., stratified PR by moderator level)
   - **Quality requirements**:
     ```r
     library(ggplot2)
     # Example: Interaction plot for Exercise_Frequency × Gender
     ggplot(stratified_data, aes(x = Exercise_Frequency, y = PR, color = Gender, group = Gender)) +
       geom_point(size = 3) +
       geom_line() +
       geom_errorbar(aes(ymin = CI_Lower, ymax = CI_Upper), width = 0.2) +
       theme_minimal(base_size = 12) +
       labs(title = "Interaction: Exercise Frequency × Gender", x = "Exercise Frequency", y = "Prevalence Ratio (95% CI)")
     ggsave("interaction_plots.png", width = 10, height = 6, dpi = 300)
     ```

3. **Code requirements**: Use R with survey, mice, ggplot2 packages; English comments

## Validation Template
```r
cat("Start execution: Create Age_Group Variable\n")
data$Age_Group <- cut(data$Age, breaks = c(65, 75, 85, Inf), labels = c("65-74", "75-84", "≥85"), right = FALSE)
if(!exists("data$Age_Group")) stop("Error: Age_Group creation failed!")
cat("Validation passed: Age_Group variable created\n")

cat("Start execution: Interaction Model\n")
library(survey)
design <- svydesign(ids = ~1, strata = ~Geographic_Region, weights = ~Sampling_Weight, data = data, nest = TRUE)
model_interaction <- svyglm(Osteoporosis_Status ~ Exercise_Frequency + Gender + Exercise_Frequency:Gender + Age + Geographic_Region + BMI, design, family = quasipoisson(link = "log"))
if(!exists("model_interaction")) stop("Error: Interaction model failed!")
cat("Validation passed: Interaction model completed\n")

cat("Start execution: FDR Control\n")
p_values <- c(0.03, 0.15, 0.08, ...)  # Example P-values
q_values <- p.adjust(p_values, method = "BH")
if(!exists("q_values")) stop("Error: FDR control failed!")
cat("Validation passed: FDR control completed\n")

cat("Start execution: Stratified Analysis\n")
# Example: Stratify by Gender
model_male <- svyglm(Osteoporosis_Status ~ Exercise_Frequency + Age + Geographic_Region + BMI, design_male, family = quasipoisson(link = "log"))
model_female <- svyglm(Osteoporosis_Status ~ Exercise_Frequency + Age + Geographic_Region + BMI, design_female, family = quasipoisson(link = "log"))
if(!exists("model_male") | !exists("model_female")) stop("Error: Stratified analysis failed!")
cat("Validation passed: Stratified analysis completed\n")
```
```

---

## File: prompt_7.7_dose_response_relationship_analysis.md

```markdown
