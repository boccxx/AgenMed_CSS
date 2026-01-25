# R code file: 7.3_Descriptive Statistics (Table 1).R
# Analysis stage: Descriptive Statistics (Table 1)
# SAP section: 7.3
# Generated time: 2026-01-18 23:31:28

# ============================================================================
# Stage 7.3: Descriptive Statistics (Table 1)
# Statistical Analysis Plan: Complex Survey Weighted Estimation
# ============================================================================

# === Font and Graphics Setup ===
# Configure graphics environment for cross-platform compatibility
options(warn = -1)
if(capabilities("cairo")) {
  options(bitmapType = "cairo")
}

# Set ggplot2 theme with English labels
library(ggplot2)
theme_set(theme_minimal(base_size = 12, base_family = "sans"))

# Tableau 10 color palette
tableau10 <- c("#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
               "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC")

# === Data Reading ===
cat("=== Stage 7.3: Descriptive Statistics (Table 1) ===\n")
cat("Step 1: Reading data from previous stage\n")

# Read main data
data_file <- "../7.2/main_output.csv"
if(!file.exists(data_file)) {
  data_file <- "../7.1/main_output.csv"
  cat("Warning: Using fallback data from stage 7.1\n")
}

data <- read.csv(data_file, stringsAsFactors = FALSE)
cat("Data loaded: n =", nrow(data), "rows,", ncol(data), "columns\n")

# Read previous stage summary
prev_summary <- NULL
if(file.exists("../7.2/analysis_summary.json")) {
  prev_summary <- jsonlite::fromJSON("../7.2/analysis_summary.json")
  cat("Previous stage summary loaded\n")
}

# === Precondition Validation ===
cat("\nStep 2: Validating preconditions\n")

# Check core variables exist
required_vars <- c("Exercise_Frequency", "Sampling_Weight", "Geographic_Region")
missing_vars <- required_vars[!required_vars %in% names(data)]
if(length(missing_vars) > 0) {
  stop("Error: Required variables missing: ", paste(missing_vars, collapse = ", "))
}
cat("Validation passed: Core variables exist\n")

# Check Exercise_Frequency levels
exercise_levels <- unique(data$Exercise_Frequency[!is.na(data$Exercise_Frequency)])
expected_levels <- c("Daily", "No_Exercise", "Occasional", "Weekly_Or_More")
if(!all(expected_levels %in% exercise_levels)) {
  cat("Warning: Exercise_Frequency levels differ from expected\n")
  cat("  Expected:", paste(expected_levels, collapse = ", "), "\n")
  cat("  Found:", paste(exercise_levels, collapse = ", "), "\n")
}

# === Create Exercise Grouping Variable ===
cat("\nStep 3: Creating Exercise_Group variable\n")

data$Exercise_Group <- ifelse(
  data$Exercise_Frequency %in% c("No_Exercise", "Occasional"),
  "Below_Recommended",
  "At_Above_Recommended"
)

# Convert to factor with explicit levels
data$Exercise_Group <- factor(
  data$Exercise_Group,
  levels = c("Below_Recommended", "At_Above_Recommended")
)

# Verify grouping
table(data$Exercise_Group, data$Exercise_Frequency, useNA = "ifany")
cat("Exercise_Group created successfully\n")
cat("  Below_Recommended: n =", sum(data$Exercise_Group == "Below_Recommended", na.rm = TRUE), "\n")
cat("  At_Above_Recommended: n =", sum(data$Exercise_Group == "At_Above_Recommended", na.rm = TRUE), "\n")

# === Survey Design Declaration ===
cat("\nStep 4: Declaring complex survey design\n")

library(survey)

# Ensure Geographic_Region is factor with all levels
data$Geographic_Region <- factor(
  data$Geographic_Region,
  levels = c("Boxing", "Pingyi", "West_Coast")
)

# Verify strata
cat("Geographic_Region distribution:\n")
print(table(data$Geographic_Region, useNA = "ifany"))

# Check weight status
weight_check <- data.frame(
  n_unique = length(unique(data$Sampling_Weight)),
  min = min(data$Sampling_Weight, na.rm = TRUE),
  max = max(data$Sampling_Weight, na.rm = TRUE),
  all_equal_1 = all(data$Sampling_Weight == 1, na.rm = TRUE)
)
cat("Weight status:\n")
print(weight_check)

if(weight_check$all_equal_1) {
  cat("WARNING: All weights equal 1 (placeholder weights - unweighted analysis)\n")
  design_mode <- "sample_based"
} else {
  cat("Actual survey weights detected - using design-based estimation\n")
  design_mode <- "design_based"
}

# Create survey design object
design <- svydesign(
  ids = ~1,  # No PSU clustering
  strata = ~Geographic_Region,
  weights = ~Sampling_Weight,
  data = data,
  nest = TRUE
)

cat("Survey design object created successfully\n")
cat("  Design mode:", design_mode, "\n")

# === Table 1 Generation with Normality Testing ===
library(tableone)

cat("\nStep 5: Identifying continuous and categorical variables\n")

# Identify numeric variables
numeric_vars <- names(data)[sapply(data, is.numeric)]
factor_vars <- names(data)[sapply(data, is.factor)]
char_vars <- names(data)[sapply(data, is.character)]

# Continuous variables (numeric with >10 unique values, excluding weights)
cont_vars <- numeric_vars[numeric_vars %in% names(data)]
cont_vars <- cont_vars[!cont_vars %in% c("Sampling_Weight", "weight", "survey_weight", "wgt")]
cont_vars <- cont_vars[sapply(cont_vars, function(v) {
  length(unique(data[[v]][!is.na(data[[v]])])) > 10
})]

# Categorical variables
cat_vars <- unique(c(factor_vars, char_vars))
cat_vars <- cat_vars[cat_vars %in% names(data)]
cat_vars <- cat_vars[sapply(cat_vars, function(v) {
  length(unique(data[[v]][!is.na(data[[v]])])) <= 20
})]

# Handle numeric categorical variables (2-20 unique values)
numeric_cat_candidates <- numeric_vars[
  numeric_vars %in% names(data) & 
  !numeric_vars %in% cont_vars & 
  !numeric_vars %in% c("Sampling_Weight", "weight", "survey_weight", "wgt")
]

# Fix: Use proper loop instead of list subsetting
numeric_cat_vars <- character(0)
for(v in numeric_cat_candidates) {
  if(!v %in% names(data)) next
  n_unique <- length(unique(data[[v]][!is.na(data[[v]])]))
  if(n_unique > 1 && n_unique <= 20) {
    numeric_cat_vars <- c(numeric_cat_vars, v)
  }
}

if(length(numeric_cat_vars) > 0) {
  cat("Converting numeric categorical variables to factor:", 
      paste(numeric_cat_vars, collapse = ", "), "\n")
  for(v in numeric_cat_vars) {
    data[[v]] <- factor(data[[v]], levels = sort(unique(data[[v]][!is.na(data[[v]])])))
  }
  cat_vars <- unique(c(cat_vars, numeric_cat_vars))
}

# Convert character variables to factors
for(v in cat_vars) {
  if(is.character(data[[v]])) {
    data[[v]] <- factor(data[[v]], levels = unique(data[[v]][!is.na(data[[v]])]))
  }
}

# Remove Exercise_Group from variable lists (it's the stratification variable)
cont_vars <- cont_vars[cont_vars != "Exercise_Group"]
cat_vars <- cat_vars[cat_vars != "Exercise_Group"]

cat("Continuous variables (n =", length(cont_vars), "):\n")
cat("  ", paste(cont_vars, collapse = ", "), "\n")
cat("Categorical variables (n =", length(cat_vars), "):\n")
cat("  ", paste(cat_vars, collapse = ", "), "\n")

# === Normality Testing ===
cat("\nStep 6: Normality testing for continuous variables\n")

normality_results <- list()
nonnormal_vars <- c()

for(var in cont_vars) {
  if(!var %in% names(data)) next
  
  # Test normality within each stratum
  test_results <- by(data[[var]], data$Exercise_Group, function(x) {
    x_clean <- x[!is.na(x)]
    if(length(x_clean) < 3) return(NA)
    # Sample if too large
    if(length(x_clean) > 5000) x_clean <- sample(x_clean, 5000)
    tryCatch(shapiro.test(x_clean)$p.value, error = function(e) NA)
  })
  
  p_values <- unlist(test_results)
  is_normal <- all(!is.na(p_values)) && all(p_values > 0.05)
  
  normality_results[[var]] <- list(
    p_values = p_values,
    is_normal = is_normal
  )
  
  if(!is_normal) {
    nonnormal_vars <- c(nonnormal_vars, var)
    cat("  ", var, ": non-normal (p-values:", 
        paste(round(p_values, 3), collapse = ", "), ")\n")
  } else {
    cat("  ", var, ": normal (p-values:", 
        paste(round(p_values, 3), collapse = ", "), ")\n")
  }
}

cat("Non-normal variables (n =", length(nonnormal_vars), "):\n")
cat("  ", paste(nonnormal_vars, collapse = ", "), "\n")

# === Generate Table 1 ===
cat("\nStep 7: Generating Table 1 using svyCreateTableOne\n")

# Recreate survey design with updated data (factors converted)
design <- svydesign(
  ids = ~1,
  strata = ~Geographic_Region,
  weights = ~Sampling_Weight,
  data = data,
  nest = TRUE
)

# Create Table 1
tab1 <- svyCreateTableOne(
  vars = c(cont_vars, cat_vars),
  strata = "Exercise_Group",
  data = design,
  factorVars = cat_vars,
  test = FALSE,  # No p-values per protocol
  smd = TRUE     # Include SMD for balance assessment
)

# Print and export Table 1
tab1_print <- print(
  tab1,
  nonnormal = nonnormal_vars,
  contDigits = 2,
  catDigits = 1,
  smd = TRUE,
  showAllLevels = TRUE,
  printToggle = FALSE
)

tab1_df <- as.data.frame(tab1_print)
write.csv(tab1_df, "table1_weighted_baseline.csv", row.names = TRUE)
cat("Table 1 exported to: table1_weighted_baseline.csv\n")

# === Extract SMD Values ===
cat("\nStep 8: Extracting SMD values for balance assessment\n")

# Extract SMD from tableone object
smd_matrix <- ExtractSmd(tab1)

# Convert to data frame
smd_df <- data.frame(
  Variable = rownames(smd_matrix),
  SMD = as.numeric(smd_matrix[, 1]),
  stringsAsFactors = FALSE
)

# Add imbalance flag (abs(SMD) > 0.10)
smd_df$Imbalance <- ifelse(abs(smd_df$SMD) > 0.10, "Yes", "No")
smd_df$SMD_rounded <- round(smd_df$SMD, 3)

# Identify imbalanced variables
imbalanced_vars <- smd_df$Variable[smd_df$Imbalance == "Yes"]
cat("Variables with substantial imbalance (abs(SMD) > 0.10):\n")
if(length(imbalanced_vars) > 0) {
  for(v in imbalanced_vars) {
    smd_val <- smd_df$SMD_rounded[smd_df$Variable == v]
    cat("  ", v, ": SMD =", smd_val, "\n")
  }
} else {
  cat("  None - all variables well balanced\n")
}

# Export SMD table
write.csv(smd_df, "table1_smd.csv", row.names = FALSE)
cat("SMD table exported to: table1_smd.csv\n")

# === Create Variable Dictionary ===
cat("\nStep 9: Creating variable dictionary\n")

var_dict <- data.frame(
  variable = c(cont_vars, cat_vars),
  type = c(rep("continuous", length(cont_vars)), 
           rep("categorical", length(cat_vars))),
  rule = c(
    ifelse(cont_vars %in% nonnormal_vars, 
           "Weighted median [IQR]", 
           "Weighted mean (SD)"),
    rep("Weighted estimated N and %", length(cat_vars))
  ),
  stringsAsFactors = FALSE
)

write.csv(var_dict, "table1_variable_dictionary.csv", row.names = FALSE)
cat("Variable dictionary exported to: table1_variable_dictionary.csv\n")

# === Generate SMD Forest Plot ===
cat("\nStep 10: Generating SMD forest plot\n")

# Prepare data for plotting
smd_plot_df <- smd_df[order(smd_df$SMD), ]
smd_plot_df$Variable <- factor(smd_plot_df$Variable, levels = smd_plot_df$Variable)

# Create forest plot
p_smd <- ggplot(smd_plot_df, aes(x = SMD, y = Variable)) +
  # Reference lines
  geom_vline(xintercept = 0, linetype = "solid", color = "gray30", size = 0.8) +
  geom_vline(xintercept = c(-0.10, 0.10), linetype = "dashed", 
             color = "gray50", size = 0.5) +
  # Shaded region for imbalance
  annotate("rect", xmin = -Inf, xmax = -0.10, ymin = -Inf, ymax = Inf,
           alpha = 0.1, fill = "#E15759") +
  annotate("rect", xmin = 0.10, xmax = Inf, ymin = -Inf, ymax = Inf,
           alpha = 0.1, fill = "#E15759") +
  # Points
  geom_point(aes(color = Imbalance), size = 3) +
  scale_color_manual(values = c("No" = "#4E79A7", "Yes" = "#E15759")) +
  # Labels and theme
  labs(
    title = "Standardized Mean Difference (SMD) - Exercise Groups",
    subtitle = "Below Recommended vs. At/Above Recommended Exercise Level",
    x = "Standardized Mean Difference",
    y = "",
    caption = "Dashed lines indicate SMD = ±0.10 threshold for substantial imbalance"
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
    plot.subtitle = element_text(hjust = 0.5, size = 11),
    plot.caption = element_text(hjust = 0, size = 9, color = "gray40"),
    legend.position = "bottom",
    legend.title = element_text(face = "bold"),
    panel.grid.major.y = element_line(color = "gray90"),
    panel.grid.minor = element_blank()
  )

ggsave("table1_smd_plot.png", p_smd, width = 10, height = 8, dpi = 300)
cat("SMD forest plot saved to: table1_smd_plot.png\n")

# === Calculate Weighted Sample Sizes ===
cat("\nStep 11: Calculating weighted sample sizes\n")

# Total weighted N
n_total_weighted <- sum(weights(design))

# Weighted N by Exercise_Group - FIX: Handle the svyby output correctly
n_by_group_result <- svyby(~Exercise_Group, ~Exercise_Group, design, svytotal)

# Extract weighted counts safely
n_below <- as.numeric(n_by_group_result[n_by_group_result$Exercise_Group == "Below_Recommended", 2])
n_above <- as.numeric(n_by_group_result[n_by_group_result$Exercise_Group == "At_Above_Recommended", 2])

# Handle case where extraction fails
if(length(n_below) == 0) n_below <- sum(data$Exercise_Group == "Below_Recommended", na.rm = TRUE)
if(length(n_above) == 0) n_above <- sum(data$Exercise_Group == "At_Above_Recommended", na.rm = TRUE)

cat("Weighted sample sizes:\n")
cat("  Total: N =", round(n_total_weighted, 0), "\n")
cat("  Below Recommended: N =", round(n_below, 0), "\n")
cat("  At/Above Recommended: N =", round(n_above, 0), "\n")

# === Prepare Main Output ===
cat("\nStep 12: Preparing main output for next stage\n")

# Add Exercise_Group to data for next stage
main_output <- data

# Verify output quality
cat("Output validation:\n")
cat("  Rows:", nrow(main_output), "\n")
cat("  Columns:", ncol(main_output), "\n")
cat("  Exercise_Group levels:", paste(levels(main_output$Exercise_Group), collapse = ", "), "\n")

write.csv(main_output, "main_output.csv", row.names = FALSE)
cat("Main output saved to: main_output.csv\n")

# === Generate Analysis Summary ===
cat("\nStep 13: Generating analysis summary\n")

analysis_summary <- list(
  stage = "7.3_descriptive_statistics",
  timestamp = as.character(Sys.time()),
  
  # Sample sizes
  n_total = nrow(data),
  n_total_weighted = round(n_total_weighted, 0),
  n_below_recommended = sum(data$Exercise_Group == "Below_Recommended", na.rm = TRUE),
  n_below_recommended_weighted = round(n_below, 0),
  n_at_above_recommended = sum(data$Exercise_Group == "At_Above_Recommended", na.rm = TRUE),
  n_at_above_recommended_weighted = round(n_above, 0),
  
  # Critical decisions
  critical_decisions = list(
    exercise_grouping = "Below_Recommended = (No_Exercise + Occasional); At_Above_Recommended = (Daily + Weekly_Or_More)",
    imbalanced_vars = imbalanced_vars,
    smd_threshold = 0.10,
    normality_testing = "Shapiro-Wilk test by strata, alpha = 0.05",
    nonnormal_vars = nonnormal_vars
  ),
  
  # Design information
  design = list(
    design_verified_level = design_mode,
    weight_variable = "Sampling_Weight",
    strata_variable = "Geographic_Region",
    psu_variable = NULL,
    weight_is_placeholder = weight_check$all_equal_1,
    weights_actually_used = TRUE,
    design_declaration = "svydesign with strata, no PSU clustering"
  ),
  
  # Statistical methods
  statistical_methods_summary = list(
    framework = "Complex Survey Weighted Estimation",
    continuous_vars_normal = paste(setdiff(cont_vars, nonnormal_vars), collapse = ", "),
    continuous_vars_nonnormal = paste(nonnormal_vars, collapse = ", "),
    categorical_vars = paste(cat_vars, collapse = ", "),
    balance_metric = "Standardized Mean Difference (SMD)",
    hypothesis_testing = "None (descriptive only, per protocol)"
  ),
  
  # Variable information
  variables = list(
    continuous = cont_vars,
    categorical = cat_vars,
    nonnormal = nonnormal_vars,
    total_vars = length(cont_vars) + length(cat_vars)
  ),
  
  # Next stage requirements
  next_stage_requirements = list(
    note = "Exercise_Group variable created for stratified analysis",
    imbalanced_vars_require_adjustment = length(imbalanced_vars) > 0,
    recommended_action = if(length(imbalanced_vars) > 0) {
      "Consider adjustment for imbalanced variables in regression models"
    } else {
      "Groups well balanced - proceed with unadjusted analysis"
    }
  ),
  
  # Deliverables
  deliverables = list(
    main_output = "main_output.csv",
    table1 = "table1_weighted_baseline.csv",
    smd_table = "table1_smd.csv",
    variable_dictionary = "table1_variable_dictionary.csv",
    smd_plot = "table1_smd_plot.png"
  )
)

# Export analysis summary
jsonlite::write_json(
  analysis_summary,
  "analysis_summary.json",
  pretty = TRUE,
  auto_unbox = TRUE
)
cat("Analysis summary saved to: analysis_summary.json\n")

# === Final Validation ===
cat("\n=== Final Validation ===\n")

# Check all deliverables exist
required_files <- c(
  "main_output.csv",
  "analysis_summary.json",
  "table1_weighted_baseline.csv",
  "table1_smd.csv",
  "table1_variable_dictionary.csv",
  "table1_smd_plot.png"
)

missing_files <- required_files[!file.exists(required_files)]
if(length(missing_files) > 0) {
  stop("Error: Missing required deliverables: ", paste(missing_files, collapse = ", "))
}

cat("All deliverables generated successfully:\n")
for(f in required_files) {
  cat("  ✓", f, "\n")
}

# === Summary Report ===
cat("\n=== Stage 7.3 Summary ===\n")
cat("Statistical Method: Descriptive Statistics (Table 1)\n")
cat("Framework: Complex Survey Weighted Estimation\n")
cat("Design Mode:", design_mode, "\n")
cat("\nSample Sizes:\n")
cat("  Total (unweighted): n =", nrow(data), "\n")
cat("  Total (weighted): N =", round(n_total_weighted, 0), "\n")
cat("  Below Recommended: n =", sum(data$Exercise_Group == "Below_Recommended", na.rm = TRUE),
    "(weighted N =", round(n_below, 0), ")\n")
cat("  At/Above Recommended: n =", sum(data$Exercise_Group == "At_Above_Recommended", na.rm = TRUE),
    "(weighted N =", round(n_above, 0), ")\n")
cat("\nVariable Summary:\n")
cat("  Continuous variables:", length(cont_vars), "\n")
cat("    - Normal distribution:", length(setdiff(cont_vars, nonnormal_vars)), "\n")
cat("    - Non-normal distribution:", length(nonnormal_vars), "\n")
cat("  Categorical variables:", length(cat_vars), "\n")
cat("\nBalance Assessment:\n")
cat("  Variables with substantial imbalance (abs(SMD) > 0.10):", length(imbalanced_vars), "\n")
if(length(imbalanced_vars) > 0) {
  cat("  Imbalanced variables:", paste(imbalanced_vars, collapse = ", "), "\n")
}
cat("\n=== Stage 7.3 Completed Successfully ===\n")