# Statistical Analysis Task: SAP 7.3 - Descriptive Statistics (Table 1)

## Core Statistical Methods
**Verbatim from Protocol Section 7.3:**
- **Baseline characteristics stratified by primary exposure** (Exercise_Frequency): Total sample, Below recommended level, At/above recommended level
- **Complex Survey Weighted Estimation**: Declare survey design object (Stratum_ID, PSU_ID, weight, FPC)
- **Continuous variables**: Weighted Mean (SD) for normal/approx. normal (Age, BMI, Cognition, Hb, BMD); Weighted Median (IQR) for skewed (Fasting_Glucose)
- **Categorical variables**: Weighted Count (estimated N) and Percentage (%)
- **Balance assessment**: Standardized Mean Difference (SMD); abs(SMD) > 0.10 indicates substantial imbalance
- **No P-values**: Avoid multiple comparison issues (exception: if required by reviewers, use design-based tests)

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
  "validation": "MANDATORY - verify Geographic_Region preserved in imputed data"
}
```

**2. Estimand & Exposure Definition:**
- Primary exposure: Exercise_Frequency (4 levels: Daily, Weekly_Or_More, Occasional, No_Exercise)
- Grouping: "At/above recommended" (Daily + Weekly_Or_More) vs "Below recommended" (Occasional + No_Exercise)

**3. Covariate Adjustment Strategy:**
```json
{
  "adjustment_mode": "descriptive_only",
  "note": "Table 1 is descriptive - no adjustment, just stratified summaries"
}
```

**4. Missing Data Primary Strategy:**
- Use first imputed dataset (m=1) from 7.2 output

## Data and Variable Requirements
- **Data reading path**: `../7.2/main_output.csv` (first imputed dataset)
- **Key variables** (ACTUAL data):
  - **Stratification**: Exercise_Frequency (4 levels)
  - **Demographics**: Age (continuous), Gender (2 levels), Geographic_Region (3 levels)
  - **Anthropometric**: BMI (continuous)
  - **Lifestyle**: Dietary_Habits (3 levels), Smoking_Status (2 levels), Alcohol_Frequency (4 levels), Self_Rated_Health (3 levels), Self_Care_Ability (3 levels), Physical_Function (2 levels)
  - **Biochemical**: Hemoglobin (continuous), Fasting_Glucose (continuous), Total_Bilirubin, Serum_Creatinine, Blood_Urea_Nitrogen, Total_Cholesterol, Triglycerides
  - **Outcome**: Bone_Mineral_Density (continuous), Osteoporosis_Status (3 levels)
- **Previous stage information**: Read `../7.2/analysis_summary.json` for imputation method confirmation

## Variable Selection Strategy
**Descriptive mode:**
- Include all variables listed in protocol Appendix 7.B Table 1 Variable List
- No variable selection based on p-values

## Execution Requirements
1. **Survey design declaration**:
   ```r
   library(survey)
   design <- svydesign(
     ids = ~1,  # No PSU (SRS within strata)
     strata = ~Geographic_Region,
     weights = ~Sampling_Weight,
     data = data,
     nest = TRUE
   )
   ```
2. **Create exposure groups**:
   - Recode Exercise_Frequency: "Daily" + "Weekly_Or_More" → "At/Above Recommended"; "Occasional" + "No_Exercise" → "Below Recommended"
3. **Weighted descriptive statistics**:
   - Continuous (normal): `svymean()`, `svyvar()` → Mean (SD)
   - Continuous (skewed): `svyquantile()` → Median (IQR)
   - Categorical: `svytable()`, `prop.table()` → N (%)
4. **SMD calculation**:
   - For continuous: SMD = (Mean1 - Mean2) / pooled_SD
   - For categorical: SMD = (Prop1 - Prop2) / sqrt((Prop1*(1-Prop1) + Prop2*(1-Prop2))/2)
   - Flag abs(SMD) > 0.10
5. **Validation**: Each step must include start marker, execution code, result validation, completion confirmation

## Output Requirements
1. **Standard output files**:
   - `main_output.csv`: Same as input (no data transformation)
   - `table1_baseline_characteristics.csv`: Table 1 with columns: Variable, Total (N=1265), Below_Recommended (N=XXX), At_Above_Recommended (N=XXX), SMD
     - Format: "Mean (SD)" for continuous normal, "Median [IQR]" for skewed, "N (%)" for categorical
   - `analysis_summary.json`:
     ```json
     {
       "stage": "7.3_descriptive_statistics",
       "n_total": 1265,
       "n_below_recommended": "XXX",
       "n_at_above_recommended": "XXX",
       "imbalanced_variables": ["Age", "BMI", ...],
       "critical_decisions": {
         "exposure_grouping": "Daily+Weekly_Or_More vs Occasional+No_Exercise",
         "smd_threshold": 0.10
       }
     }
     ```

2. **Graphics output**: None required for Table 1

3. **Code requirements**: Use R with survey, tableone packages; English comments

## Validation Template
```r
cat("Start execution: Survey Design Declaration\n")
library(survey)
design <- svydesign(ids = ~1, strata = ~Geographic_Region, weights = ~Sampling_Weight, data = data, nest = TRUE)
if(!exists("design")) stop("Error: Survey design declaration failed!")
cat("Validation passed: Survey design declared\n")

cat("Start execution: Exposure Grouping\n")
data$Exercise_Group <- ifelse(data$Exercise_Frequency %in% c("Daily", "Weekly_Or_More"), "At_Above_Recommended", "Below_Recommended")
if(!exists("data$Exercise_Group")) stop("Error: Exposure grouping failed!")
cat("Validation passed: Exposure grouping completed\n")

cat("Start execution: Weighted Descriptive Statistics\n")
# Example: Weighted mean for Age
mean_age <- svymean(~Age, design)
if(!exists("mean_age")) stop("Error: Weighted mean calculation failed!")
cat("Validation passed: Weighted descriptive statistics completed\n")

cat("Start execution: SMD Calculation\n")
# Example: SMD for Age
smd_age <- (mean_age_group1 - mean_age_group2) / pooled_sd
if(!exists("smd_age")) stop("Error: SMD calculation failed!")
cat("Validation passed: SMD calculation completed\n")
```
```

---

## File: prompt_7.4_bivariate_exploratory_analysis.md

```markdown
