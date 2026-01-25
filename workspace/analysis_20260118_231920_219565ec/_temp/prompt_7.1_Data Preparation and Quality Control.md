# Statistical Analysis Task: SAP 7.1 - Data Preparation and Quality Control

## Core Statistical Methods
**Verbatim from Protocol Section 7.1:**
- Multi-source data integration from: (1) Bone density screening system; (2) Health questionnaire system; (3) Regional health big data platform; (4) Primary healthcare archives
- Non-destructive cleaning via version-controlled scripts (R/Python)
- Automated quality checks: duplicate handling, range/logic checks, consistency verification
- Outlier identification via boxplots and density plots
- Strategy: Obvious errors → missing; Extreme real values → retain in main analysis, evaluate in sensitivity

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
  "validation": "MANDATORY - verify Geographic_Region has 3 levels (Boxing, Pingyi, West_Coast)"
}
```
**CRITICAL Variable Mapping:**
- Protocol mentions "strata by Economic Circle" → Actual data has "Geographic_Region" with 3 levels (Boxing, Pingyi, West_Coast)
- Set "strata": "Geographic_Region" (NOT null)
- Protocol does not explicitly mention PSU/cluster variable → Set "psu": null (assume SRS within strata)

**2. Estimand & Exposure Definition:**
- Primary exposure: "Exercise_Frequency" (Daily vs No_Exercise)
- Secondary exposures: Dietary_Habits, Smoking_Status, Alcohol_Frequency, Hemoglobin, Fasting_Glucose
- Outcome: Osteoporosis_Status (binary: Osteoporosis vs Normal/Low_Bone_Mass), Bone_Mineral_Density (continuous)

**3. Covariate Adjustment Strategy:**
```json
{
  "adjustment_mode": "DAG_fixed",
  "covariates": ["Age", "Gender", "Geographic_Region", "BMI"],
  "exclude_from_main": ["Physical_Function", "Self_Care_Ability"],
  "note": "Protocol specifies DAG-based minimal adjustment set - DO NOT use p-value screening"
}
```

**4. Missing Data Primary Strategy:**
```json
{
  "missing_contract": {
    "primary": "MICE",
    "sensitivity": ["CCA", "MNAR_delta_adjustment"]
  }
}
```

**CRITICAL: Design Variable Preservation (MANDATORY):**
- NEVER filter data by Geographic_Region or Sampling_Weight
- ALWAYS preserve all levels: `factor(Geographic_Region, levels = c("Boxing", "Pingyi", "West_Coast"))`
- NEVER use `droplevels()` on design variables
- Verify Geographic_Region has 3 levels BEFORE analysis

## Data and Variable Requirements
- **Data reading path**: `data.csv` (original file)
- **Key variables** (ACTUAL data variables):
  - **Design variables**: Sampling_Weight (weight), Geographic_Region (strata)
  - **Outcome**: Bone_Mineral_Density (continuous), Osteoporosis_Status (categorical: Normal/Low_Bone_Mass/Osteoporosis)
  - **Exposures**: Exercise_Frequency (4 levels), Dietary_Habits (3 levels), Smoking_Status (2 levels), Alcohol_Frequency (4 levels), Hemoglobin (continuous), Fasting_Glucose (continuous)
  - **Covariates**: Age (continuous), Gender (2 levels), BMI (continuous), Self_Rated_Health (3 levels), Self_Care_Ability (3 levels), Physical_Function (2 levels)
  - **Biochemical**: Total_Bilirubin, Serum_Creatinine, Blood_Urea_Nitrogen, Total_Cholesterol, Triglycerides
  - **Disease history**: Cerebrovascular_Disease (95.7% missing), Other_Neurological_Diseases (99.9% missing)
- **Variable types**: Use actual data types (int64 for Age, float64 for BMI/biomarkers, object for categorical)
- **Previous stage information**: N/A (first stage)

## Variable Selection Strategy
**A priori mode (DAG-based):**
- Strictly follow protocol's predefined adjustment set: Age, Gender, Geographic_Region, BMI
- Prohibit variable selection based on bivariate p-values
- Previous stage information: N/A (this is the first stage)

## Execution Requirements
1. **Data integration**: Read `data.csv`, verify all 23 variables present
2. **Data dictionary**: Create standardized variable definitions (name, type, unit, coding, range)
3. **Automated QC**:
   - Duplicate check: Verify no duplicate rows (use all columns as key)
   - Range check: Flag out-of-range values per protocol Appendix 7.A
     * Age: [65, 120]
     * BMI: [10, 50] (flag 378.70 as extreme outlier)
     * Hemoglobin: [50, 200]
     * Fasting_Glucose: [2.5, 30]
     * Bone_Mineral_Density: [0.1, 1.5]
   - Logic check: Verify Gender coding, Geographic_Region levels
4. **Outlier handling**:
   - Identify via boxplots (IQR method) and Z-scores (|Z| > 3)
   - Obvious errors (e.g., BMI=378.70) → set to missing, log change
   - Extreme real values → retain, flag for sensitivity analysis
5. **Missing data diagnosis**:
   - Calculate missing rates by variable
   - Generate missing pattern matrix (VIM/mice package)
   - Flag variables with >40% missing (Cerebrovascular_Disease, Other_Neurological_Diseases) for exclusion
6. **Validation**: Each step must include start marker, execution code, result validation, completion confirmation

## Output Requirements
1. **Standard output files**:
   - `main_output.csv`: Cleaned data with QC flags (columns: all original + `QC_flag_BMI`, `QC_flag_Hb`, etc.)
   - `analysis_summary.json`: 
     ```json
     {
       "stage": "7.1_data_preparation",
       "n_total": 1265,
       "n_after_qc": "XXX",
       "missing_rates": {"Hemoglobin": 0.031, "Fasting_Glucose": 0.009, ...},
       "outliers_flagged": {"BMI": ["row_X"], ...},
       "critical_decisions": {
         "design_variables": {"weight": "Sampling_Weight", "strata": "Geographic_Region", "psu": null},
         "excluded_variables": ["Cerebrovascular_Disease", "Other_Neurological_Diseases"],
         "qc_summary": "..."
       }
     }
     ```
   - `data_dictionary.csv`: Variable definitions (columns: variable_name, type, unit, coding, range, source)
   - `qc_log.txt`: Detailed QC log (duplicates, range violations, outliers)

2. **Graphics output (PNG, ENGLISH labels, publication quality)**:
   - **MANDATORY Distribution/Diagnostic Plots**:
     * `outlier_boxplots_continuous.png`: Boxplots for ALL continuous variables (Age, BMI, Hemoglobin, Fasting_Glucose, Bone_Mineral_Density, biochemical markers)
       - Multi-panel layout: 4×4 grid (16 vars per plot)
       - If > 16 vars: Split into `outlier_boxplots_part1.png`, `part2.png`
       - Highlight outliers in red
     * `distribution_continuous.png`: Histograms for ALL continuous variables
       - Multi-panel layout: 4×4 grid
       - Split if > 16 vars
     * `distribution_categorical.png`: Bar charts for ALL categorical variables (Gender, Geographic_Region, Exercise_Frequency, Dietary_Habits, Smoking_Status, Alcohol_Frequency, Osteoporosis_Status, Self_Rated_Health, Self_Care_Ability, Physical_Function)
       - Multi-panel layout: 3×4 grid (12 vars per plot)
       - Split if > 12 vars
   - **Quality requirements**:
     ```r
     library(ggplot2)
     theme_set(theme_minimal(base_size = 12))
     plot_colors <- c("#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F")
     # Example for boxplots:
     ggplot(data_long, aes(x = variable, y = value)) +
       geom_boxplot(outlier.color = "red", outlier.size = 2) +
       facet_wrap(~variable, scales = "free", ncol = 4) +
       theme(axis.text.x = element_text(angle = 45, hjust = 1))
     ggsave("outlier_boxplots_continuous.png", width = 12, height = 8, dpi = 300)
     ```

3. **Code requirements**: Use R with tidyverse, mice, VIM packages; English comments

## Validation Template
```r
cat("Start execution: Data Integration\n")
data <- read.csv("data.csv", stringsAsFactors = FALSE)
if(nrow(data) != 1265 | ncol(data) != 23) stop("Error: Data dimensions mismatch!")
cat("Validation passed: Data integration successful\n")

cat("Start execution: Range Check\n")
# Flag BMI outliers
data$QC_flag_BMI <- ifelse(data$BMI < 10 | data$BMI > 50, "outlier", "normal")
if(!exists("data$QC_flag_BMI")) stop("Error: Range check failed!")
cat("Validation passed: Range check completed\n")

cat("Start execution: Missing Pattern Analysis\n")
library(mice)
md.pattern(data, plot = FALSE)
missing_rates <- colMeans(is.na(data))
if(!exists("missing_rates")) stop("Error: Missing analysis failed!")
cat("Validation passed: Missing pattern analysis completed\n")

cat("Start execution: Design Variable Verification\n")
# CRITICAL: Verify Geographic_Region has 3 levels
if(length(unique(data$Geographic_Region)) != 3) stop("Error: Geographic_Region does not have 3 levels!")
cat("Validation passed: Design variables verified (Geographic_Region = 3 levels)\n")
```
```

---

## File: prompt_7.2_missing_data_handling.md

```markdown
