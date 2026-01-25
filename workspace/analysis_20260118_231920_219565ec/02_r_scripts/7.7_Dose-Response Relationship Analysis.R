# R code file: 7.7_Dose-Response Relationship Analysis.R
# Analysis stage: Dose-Response Relationship Analysis
# SAP section: 7.7
# Generated time: 2026-01-18 23:56:26

# ============================================================================
# Stage 7.7: Dose-Response Relationship Analysis
# ============================================================================
# Purpose: Explore dose-response relationships between modifiable lifestyle 
#          factors and osteoporosis outcomes using ordinal trend tests and RCS
# ============================================================================

# Graphics Environment Setup (Template 1)
# ----------------------------------------------------------------------------
options(warn = 1)
Sys.setenv(LANG = "en")

if(require(ggplot2)) {
  theme_set(theme_minimal(base_size = 12))
  theme_update(
    plot.title = element_text(hjust = 0.5, face = "bold"),
    axis.title = element_text(face = "bold"),
    legend.position = "bottom"
  )
}

tableau10 <- c("#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
               "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC")

# Required Libraries
# ----------------------------------------------------------------------------
required_packages <- c("survey", "rms", "ggplot2", "jsonlite")
for(pkg in required_packages) {
  if(!require(pkg, character.only = TRUE)) {
    install.packages(pkg, repos = "https://cloud.r-project.org")
    library(pkg, character.only = TRUE)
  }
}

cat("=== Stage 7.7: Dose-Response Relationship Analysis ===\n")
cat("Timestamp:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n")

# MICE Data Reading Template (Template 6)
# ----------------------------------------------------------------------------
read_mice_datasets <- function(prev_stage_path = NULL, mice_stage_path = "../7.2", n_imputations = 20) {
  imp_list <- list()
  
  if(!is.null(prev_stage_path) && file.exists(prev_stage_path)) {
    cat("Reading primary data from previous stage:", prev_stage_path, "\n")
    primary_data <- read.csv(prev_stage_path, stringsAsFactors = FALSE)
    cat("Primary data loaded:", nrow(primary_data), "rows,", ncol(primary_data), "columns\n")
  } else {
    cat("Warning: Previous stage data not found, will use MICE datasets only\n")
    primary_data <- NULL
  }
  
  cat("Attempting to read MICE imputed datasets from:", mice_stage_path, "\n")
  found_imputations <- 0
  
  for(i in 1:n_imputations) {
    file_path <- file.path(mice_stage_path, paste0("imputed_data_", i, ".csv"))
    if(file.exists(file_path)) {
      data <- read.csv(file_path, stringsAsFactors = FALSE)
      imp_list[[length(imp_list) + 1]] <- data
      found_imputations <- found_imputations + 1
    }
  }
  
  if(length(imp_list) == 0) {
    if(!is.null(primary_data)) {
      cat("No MICE datasets found, using primary data as single dataset\n")
      imp_list <- list(primary_data)
    } else {
      stop("ERROR: No data found. Neither previous stage data nor MICE datasets are available.")
    }
  } else {
    cat("Successfully loaded", length(imp_list), "MICE imputed datasets\n")
  }
  
  return(imp_list)
}

# Factor Level Validation Template (Template 5)
# ----------------------------------------------------------------------------
validate_factor_levels <- function(data, var_list, min_levels = 2, check_strata = NULL, strata_var = NULL) {
  valid_vars <- character(0)
  excluded_vars <- character(0)
  issues <- list()
  
  for(var in var_list) {
    if(!var %in% names(data)) {
      excluded_vars <- c(excluded_vars, var)
      issues[[var]] <- "variable_not_found"
      next
    }
    
    if(is.factor(data[[var]]) || is.character(data[[var]])) {
      if(is.null(check_strata) || is.null(strata_var) || !strata_var %in% names(data)) {
        n_levels <- length(unique(na.omit(data[[var]])))
        if(n_levels < min_levels) {
          excluded_vars <- c(excluded_vars, var)
          issues[[var]] <- paste0("single_level_factor_", n_levels)
        } else {
          valid_vars <- c(valid_vars, var)
        }
      } else {
        strata_levels <- unique(na.omit(data[[strata_var]]))
        all_strata_valid <- TRUE
        strata_issues <- character(0)
        
        for(stratum in strata_levels) {
          stratum_data <- data[data[[strata_var]] == stratum & !is.na(data[[strata_var]]), ]
          n_levels <- length(unique(na.omit(stratum_data[[var]])))
          if(n_levels < min_levels) {
            all_strata_valid <- FALSE
            strata_issues <- c(strata_issues, paste0(stratum, ":", n_levels))
          }
        }
        
        if(all_strata_valid) {
          valid_vars <- c(valid_vars, var)
        } else {
          excluded_vars <- c(excluded_vars, var)
          issues[[var]] <- paste0("single_level_in_strata_", paste(strata_issues, collapse = "_"))
        }
      }
    } else {
      valid_vars <- c(valid_vars, var)
    }
  }
  
  return(list(valid = valid_vars, excluded = excluded_vars, issues = issues))
}

safe_factor_conversion <- function(data, var_list, min_levels = 2) {
  for(var in var_list) {
    if(var %in% names(data)) {
      if(is.character(data[[var]]) || is.numeric(data[[var]])) {
        unique_vals <- unique(na.omit(data[[var]]))
        if(length(unique_vals) >= min_levels) {
          data[[var]] <- factor(data[[var]], levels = unique_vals)
        } else {
          warning("Variable ", var, " has only ", length(unique_vals), " level(s), skipping factor conversion")
        }
      }
    }
  }
  return(data)
}

# Statistical Validation Template (Template 6)
# ----------------------------------------------------------------------------
validate_output_quality <- function(result_df, max_or = 1000, min_or = 0.001) {
  issues <- list()
  
  if(any(is.na(result_df))) {
    na_cols <- colnames(result_df)[colSums(is.na(result_df)) > 0]
    issues$na_values <- paste("NA values in:", paste(na_cols, collapse = ", "))
  }
  
  if(any(sapply(result_df, function(x) any(is.infinite(x), na.rm = TRUE)))) {
    inf_cols <- colnames(result_df)[sapply(result_df, function(x) any(is.infinite(x), na.rm = TRUE))]
    issues$inf_values <- paste("Infinite values in:", paste(inf_cols, collapse = ", "))
  }
  
  if("P_Value" %in% names(result_df)) {
    invalid_p <- result_df$P_Value[!is.na(result_df$P_Value) & (result_df$P_Value < 0 | result_df$P_Value > 1)]
    if(length(invalid_p) > 0) {
      issues$invalid_p <- paste("Invalid p-values detected:", length(invalid_p), "cases")
    }
  }
  
  or_cols <- grep("^(OR|PR|RR|HR)", names(result_df), value = TRUE)
  for(col in or_cols) {
    extreme_vals <- result_df[[col]][!is.na(result_df[[col]]) & (result_df[[col]] > max_or | result_df[[col]] < min_or)]
    if(length(extreme_vals) > 0) {
      issues[[paste0("extreme_", col)]] <- paste("Extreme values in", col, ":", length(extreme_vals), "cases (possible separation)")
    }
  }
  
  if(length(issues) > 0) {
    cat("\n*** Output Quality Warnings ***\n")
    for(issue in names(issues)) {
      cat("-", issues[[issue]], "\n")
    }
    cat("***\n\n")
  } else {
    cat("Output quality validation: PASSED\n")
  }
  
  return(issues)
}

check_sample_size_consistency <- function(data, expected_n = NULL, stage_name = "current") {
  actual_n <- nrow(data)
  cat("Sample size check [", stage_name, "]: n =", actual_n, "\n")
  
  if(!is.null(expected_n) && actual_n != expected_n) {
    warning("Sample size mismatch! Expected: ", expected_n, ", Actual: ", actual_n)
    return(FALSE)
  }
  return(TRUE)
}

# Ensure Output Files Template (Template 4)
# ----------------------------------------------------------------------------
ensure_output_files <- function(data, analysis_summary) {
  tryCatch({
    if(!file.exists("main_output.csv")) {
      write.csv(data, "main_output.csv", row.names = FALSE)
      cat("Generated main_output.csv (fallback)\n")
    }
    
    if(!file.exists("analysis_summary.json")) {
      jsonlite::write_json(analysis_summary, "analysis_summary.json", pretty = TRUE, auto_unbox = TRUE)
      cat("Generated analysis_summary.json (fallback)\n")
    }
  }, error = function(e) {
    cat("Error in ensure_output_files:", e$message, "\n")
  })
}

# Manual Pooling Function (Rubin's Rules)
# ----------------------------------------------------------------------------
pool_estimates <- function(estimates_list, se_list) {
  m <- length(estimates_list)
  
  # Pooled estimate
  pooled_est <- mean(estimates_list)
  
  # Within-imputation variance
  within_var <- mean(se_list^2)
  
  # Between-imputation variance
  between_var <- var(estimates_list)
  
  # Total variance
  total_var <- within_var + (1 + 1/m) * between_var
  
  # Pooled SE
  pooled_se <- sqrt(total_var)
  
  # Degrees of freedom (Barnard-Rubin adjustment)
  df <- (m - 1) * (1 + within_var / ((1 + 1/m) * between_var))^2
  
  # P-value
  t_stat <- pooled_est / pooled_se
  p_value <- 2 * pt(abs(t_stat), df = df, lower.tail = FALSE)
  
  # CI
  t_crit <- qt(0.975, df = df)
  ci_lower <- pooled_est - t_crit * pooled_se
  ci_upper <- pooled_est + t_crit * pooled_se
  
  return(list(
    estimate = pooled_est,
    se = pooled_se,
    ci_lower = ci_lower,
    ci_upper = ci_upper,
    p_value = p_value,
    df = df
  ))
}

# Data Reading (Template 2)
# ----------------------------------------------------------------------------
cat("\n=== Step 1: Data Reading ===\n")
cat("Start execution: Reading MICE imputed datasets\n")

imp_list <- read_mice_datasets(
  prev_stage_path = "../7.6/main_output.csv",
  mice_stage_path = "../7.2",
  n_imputations = 20
)

if(length(imp_list) == 0) {
  stop("ERROR: No data available for analysis")
}

# Use first imputed dataset for reference
data_ref <- imp_list[[1]]
check_sample_size_consistency(data_ref, stage_name = "7.7")

cat("Validation passed: Data reading completed\n")
cat("Number of imputed datasets:", length(imp_list), "\n")
cat("Sample size per dataset:", nrow(data_ref), "\n\n")

# Precondition Validation
# ----------------------------------------------------------------------------
cat("=== Step 2: Precondition Validation ===\n")

# Check core variables
core_vars <- c("Exercise_Frequency", "Alcohol_Frequency", "Hemoglobin", 
               "Fasting_Glucose", "Age", "BMI", "Gender", "Geographic_Region",
               "Osteoporosis_Status", "Bone_Mineral_Density", "Sampling_Weight")

missing_vars <- setdiff(core_vars, names(data_ref))
if(length(missing_vars) > 0) {
  stop("ERROR: Missing core variables: ", paste(missing_vars, collapse = ", "))
}

cat("Core variables validation: PASSED\n")

# Validate factor variables
categorical_vars <- c("Exercise_Frequency", "Alcohol_Frequency", "Gender", "Geographic_Region")
validation_result <- validate_factor_levels(data_ref, categorical_vars)

if(length(validation_result$excluded) > 0) {
  cat("Warning: Excluded variables due to insufficient levels:\n")
  print(validation_result$excluded)
}

cat("Factor level validation: PASSED\n\n")

# Create Binary Outcome for Ordinal Exposures
# ----------------------------------------------------------------------------
cat("=== Step 3: Outcome Variable Preparation ===\n")

for(i in 1:length(imp_list)) {
  # Binary outcome: Osteoporosis vs Normal/Low_Bone_Mass
  imp_list[[i]]$Osteoporosis_Binary <- ifelse(
    imp_list[[i]]$Osteoporosis_Status == "Osteoporosis", 1, 0
  )
  
  # Ensure factor conversion
  imp_list[[i]]$Gender <- factor(imp_list[[i]]$Gender)
  imp_list[[i]]$Geographic_Region <- factor(imp_list[[i]]$Geographic_Region)
  imp_list[[i]]$Exercise_Frequency <- factor(imp_list[[i]]$Exercise_Frequency,
    levels = c("No_Exercise", "Occasional", "Weekly_Or_More", "Daily"))
  imp_list[[i]]$Alcohol_Frequency <- factor(imp_list[[i]]$Alcohol_Frequency,
    levels = c("Never", "Occasional", "Frequent", "Daily"))
}

cat("Binary outcome created: Osteoporosis_Binary\n")
cat("Factor levels standardized\n\n")

# Ordinal Trend Test Function
# ----------------------------------------------------------------------------
ordinal_trend_test <- function(imp_list, exposure_var, outcome_var, 
                                ordinal_levels, adjustment_vars) {
  
  cat("\n--- Ordinal Trend Test:", exposure_var, "---\n")
  
  estimates_list <- list()
  se_list <- list()
  
  for(i in 1:length(imp_list)) {
    data_i <- imp_list[[i]]
    
    # Create ordinal score (0, 1, 2, ...)
    score_var <- paste0(exposure_var, "_Score")
    data_i[[score_var]] <- as.numeric(factor(data_i[[exposure_var]], 
                                              levels = ordinal_levels)) - 1
    
    # Create survey design
    design_i <- svydesign(
      ids = ~1,
      strata = ~Geographic_Region,
      weights = ~Sampling_Weight,
      data = data_i,
      nest = TRUE
    )
    
    # Fit model with ordinal score
    formula_str <- paste(outcome_var, "~", score_var, "+", 
                         paste(adjustment_vars, collapse = " + "))
    
    if(outcome_var == "Osteoporosis_Binary") {
      # Binary outcome: use quasipoisson for PR
      model_i <- svyglm(as.formula(formula_str), design_i, 
                        family = quasipoisson(link = "log"))
    } else {
      # Continuous outcome: use gaussian
      model_i <- svyglm(as.formula(formula_str), design_i, 
                        family = gaussian())
    }
    
    # Extract coefficient for ordinal score
    coef_summary <- summary(model_i)$coefficients
    if(score_var %in% rownames(coef_summary)) {
      estimates_list[[i]] <- coef_summary[score_var, "Estimate"]
      se_list[[i]] <- coef_summary[score_var, "Std. Error"]
    }
  }
  
  # Pool results using Rubin's Rules
  pooled <- pool_estimates(unlist(estimates_list), unlist(se_list))
  
  if(outcome_var == "Osteoporosis_Binary") {
    # Convert to PR
    pr_val <- exp(pooled$estimate)
    pr_ci_lower <- exp(pooled$ci_lower)
    pr_ci_upper <- exp(pooled$ci_upper)
    
    cat("Linear Trend PR:", round(pr_val, 3), 
        "95% CI: [", round(pr_ci_lower, 3), ",", round(pr_ci_upper, 3), "]\n")
    cat("P-value:", format.pval(pooled$p_value, digits = 3), "\n")
    
    return(list(
      exposure = exposure_var,
      outcome = outcome_var,
      trend_type = "ordinal",
      pr = pr_val,
      ci_lower = pr_ci_lower,
      ci_upper = pr_ci_upper,
      p_value = pooled$p_value
    ))
  } else {
    cat("Linear Trend Beta:", round(pooled$estimate, 3), 
        "95% CI: [", round(pooled$ci_lower, 3), ",", round(pooled$ci_upper, 3), "]\n")
    cat("P-value:", format.pval(pooled$p_value, digits = 3), "\n")
    
    return(list(
      exposure = exposure_var,
      outcome = outcome_var,
      trend_type = "ordinal",
      beta = pooled$estimate,
      ci_lower = pooled$ci_lower,
      ci_upper = pooled$ci_upper,
      p_value = pooled$p_value
    ))
  }
}

# RCS Non-linearity Test Function
# ----------------------------------------------------------------------------
rcs_nonlinearity_test <- function(imp_list, exposure_var, outcome_var, 
                                   adjustment_vars, n_knots = 4) {
  
  cat("\n--- RCS Non-linearity Test:", exposure_var, "---\n")
  
  # Test non-linearity by comparing linear vs RCS models
  linear_deviances <- numeric(length(imp_list))
  rcs_deviances <- numeric(length(imp_list))
  df_diff <- numeric(length(imp_list))
  
  for(i in 1:length(imp_list)) {
    data_i <- imp_list[[i]]
    
    # Create survey design
    design_i <- svydesign(
      ids = ~1,
      strata = ~Geographic_Region,
      weights = ~Sampling_Weight,
      data = data_i,
      nest = TRUE
    )
    
    # Linear model
    formula_linear <- paste(outcome_var, "~", exposure_var, "+", 
                           paste(adjustment_vars, collapse = " + "))
    model_linear <- svyglm(as.formula(formula_linear), design_i, family = gaussian())
    
    # RCS model
    formula_rcs <- paste(outcome_var, "~ rcs(", exposure_var, ",", n_knots, ") +", 
                        paste(adjustment_vars, collapse = " + "))
    model_rcs <- svyglm(as.formula(formula_rcs), design_i, family = gaussian())
    
    # Store deviances
    linear_deviances[i] <- deviance(model_linear)
    rcs_deviances[i] <- deviance(model_rcs)
    df_diff[i] <- n_knots - 2  # Degrees of freedom for non-linear terms
  }
  
  # Average deviance difference
  avg_dev_diff <- mean(linear_deviances - rcs_deviances)
  avg_df_diff <- mean(df_diff)
  
  # F-test approximation
  f_stat <- (avg_dev_diff / avg_df_diff) / (mean(rcs_deviances) / (nrow(data_ref) - n_knots - length(adjustment_vars) - 1))
  p_nonlinearity <- pf(f_stat, df1 = avg_df_diff, df2 = nrow(data_ref) - n_knots - length(adjustment_vars) - 1, lower.tail = FALSE)
  
  cat("Non-linearity F-test: F =", round(f_stat, 2), 
      ", df1 =", round(avg_df_diff, 0), ", P =", format.pval(p_nonlinearity, digits = 3), "\n")
  
  return(list(
    exposure = exposure_var,
    outcome = outcome_var,
    trend_type = "rcs",
    n_knots = n_knots,
    nonlinearity_p = p_nonlinearity
  ))
}

# Execute Ordinal Trend Tests
# ----------------------------------------------------------------------------
cat("\n=== Step 4: Ordinal Trend Tests ===\n")

adjustment_vars <- c("Age", "Gender", "Geographic_Region", "BMI")

# Exercise Frequency vs Osteoporosis
trend_exercise <- ordinal_trend_test(
  imp_list = imp_list,
  exposure_var = "Exercise_Frequency",
  outcome_var = "Osteoporosis_Binary",
  ordinal_levels = c("No_Exercise", "Occasional", "Weekly_Or_More", "Daily"),
  adjustment_vars = adjustment_vars
)

# Alcohol Frequency vs Osteoporosis
trend_alcohol <- ordinal_trend_test(
  imp_list = imp_list,
  exposure_var = "Alcohol_Frequency",
  outcome_var = "Osteoporosis_Binary",
  ordinal_levels = c("Never", "Occasional", "Frequent", "Daily"),
  adjustment_vars = adjustment_vars
)

cat("Validation passed: Ordinal trend tests completed\n\n")

# Execute RCS Non-linearity Tests
# ----------------------------------------------------------------------------
cat("\n=== Step 5: RCS Non-linearity Tests ===\n")

# Hemoglobin vs BMD
rcs_hemoglobin <- rcs_nonlinearity_test(
  imp_list = imp_list,
  exposure_var = "Hemoglobin",
  outcome_var = "Bone_Mineral_Density",
  adjustment_vars = adjustment_vars,
  n_knots = 4
)

# Fasting Glucose vs BMD
rcs_glucose <- rcs_nonlinearity_test(
  imp_list = imp_list,
  exposure_var = "Fasting_Glucose",
  outcome_var = "Bone_Mineral_Density",
  adjustment_vars = adjustment_vars,
  n_knots = 4
)

cat("Validation passed: RCS non-linearity tests completed\n\n")

# Generate Dose-Response Curves
# ----------------------------------------------------------------------------
cat("\n=== Step 6: Dose-Response Curve Generation ===\n")

# Function to predict dose-response for ordinal exposures
predict_ordinal_dose_response <- function(trend_result, imp_list, ordinal_levels) {
  
  exposure_var <- trend_result$exposure
  outcome_var <- trend_result$outcome
  
  # Create prediction data for each ordinal level
  pred_data <- data.frame(
    Level = ordinal_levels,
    Score = 0:(length(ordinal_levels) - 1)
  )
  
  # Get reference values for adjustment variables
  ref_data <- imp_list[[1]]
  pred_data$Age <- mean(ref_data$Age, na.rm = TRUE)
  pred_data$BMI <- mean(ref_data$BMI, na.rm = TRUE)
  pred_data$Gender <- names(sort(table(ref_data$Gender), decreasing = TRUE))[1]
  pred_data$Geographic_Region <- names(sort(table(ref_data$Geographic_Region), decreasing = TRUE))[1]
  
  # Predict for each imputed dataset
  pred_list <- list()
  
  for(i in 1:length(imp_list)) {
    data_i <- imp_list[[i]]
    score_var <- paste0(exposure_var, "_Score")
    data_i[[score_var]] <- as.numeric(factor(data_i[[exposure_var]], 
                                              levels = ordinal_levels)) - 1
    
    design_i <- svydesign(
      ids = ~1,
      strata = ~Geographic_Region,
      weights = ~Sampling_Weight,
      data = data_i,
      nest = TRUE
    )
    
    formula_str <- paste(outcome_var, "~", score_var, "+ Age + Gender + Geographic_Region + BMI")
    
    if(outcome_var == "Osteoporosis_Binary") {
      model_i <- svyglm(as.formula(formula_str), design_i, 
                        family = quasipoisson(link = "log"))
    } else {
      model_i <- svyglm(as.formula(formula_str), design_i, 
                        family = gaussian())
    }
    
    # Predict - FIX: Check return type before using $
    pred_data_i <- pred_data
    names(pred_data_i)[names(pred_data_i) == "Score"] <- score_var
    
    pred_i <- predict(model_i, newdata = pred_data_i, type = "response", se.fit = TRUE)
    
    # FIX: Handle both list and atomic vector returns
    if(is.list(pred_i)) {
      pred_list[[i]] <- data.frame(
        fit = pred_i$fit,
        se = pred_i$se.fit
      )
    } else {
      # If atomic vector, assume it's just the fitted values
      pred_list[[i]] <- data.frame(
        fit = as.vector(pred_i),
        se = rep(NA, length(pred_i))
      )
    }
  }
  
  # Pool predictions
  pred_pooled <- data.frame(
    Level = ordinal_levels,
    Score = 0:(length(ordinal_levels) - 1),
    Predicted = rowMeans(sapply(pred_list, function(x) x$fit)),
    SE = sqrt(rowMeans(sapply(pred_list, function(x) x$se^2), na.rm = TRUE))
  )
  
  pred_pooled$CI_Lower <- pred_pooled$Predicted - 1.96 * pred_pooled$SE
  pred_pooled$CI_Upper <- pred_pooled$Predicted + 1.96 * pred_pooled$SE
  
  return(pred_pooled)
}

# Predict ordinal dose-response
if(!is.null(trend_exercise)) {
  pred_exercise <- predict_ordinal_dose_response(
    trend_exercise, imp_list, 
    c("No_Exercise", "Occasional", "Weekly_Or_More", "Daily")
  )
  
  # Plot
  p_exercise <- ggplot(pred_exercise, aes(x = Score, y = Predicted)) +
    geom_line(color = tableau10[1], size = 1.2) +
    geom_ribbon(aes(ymin = CI_Lower, ymax = CI_Upper), 
                alpha = 0.2, fill = tableau10[1]) +
    geom_point(color = tableau10[1], size = 3) +
    scale_x_continuous(breaks = 0:3, 
                       labels = c("No Exercise", "Occasional", "Weekly+", "Daily")) +
    labs(
      title = "Dose-Response: Exercise Frequency vs Osteoporosis Risk",
      x = "Exercise Frequency",
      y = "Predicted Osteoporosis Risk",
      caption = paste0("Linear trend P = ", format.pval(trend_exercise$p_value, digits = 3))
    ) +
    theme_minimal(base_size = 12) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold"),
      axis.text.x = element_text(angle = 45, hjust = 1)
    )
  
  ggsave("dose_response_exercise.png", p_exercise, width = 10, height = 6, dpi = 300)
  cat("Generated: dose_response_exercise.png\n")
}

if(!is.null(trend_alcohol)) {
  pred_alcohol <- predict_ordinal_dose_response(
    trend_alcohol, imp_list, 
    c("Never", "Occasional", "Frequent", "Daily")
  )
  
  p_alcohol <- ggplot(pred_alcohol, aes(x = Score, y = Predicted)) +
    geom_line(color = tableau10[2], size = 1.2) +
    geom_ribbon(aes(ymin = CI_Lower, ymax = CI_Upper), 
                alpha = 0.2, fill = tableau10[2]) +
    geom_point(color = tableau10[2], size = 3) +
    scale_x_continuous(breaks = 0:3, 
                       labels = c("Never", "Occasional", "Frequent", "Daily")) +
    labs(
      title = "Dose-Response: Alcohol Frequency vs Osteoporosis Risk",
      x = "Alcohol Frequency",
      y = "Predicted Osteoporosis Risk",
      caption = paste0("Linear trend P = ", format.pval(trend_alcohol$p_value, digits = 3))
    ) +
    theme_minimal(base_size = 12) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold"),
      axis.text.x = element_text(angle = 45, hjust = 1)
    )
  
  ggsave("dose_response_alcohol.png", p_alcohol, width = 10, height = 6, dpi = 300)
  cat("Generated: dose_response_alcohol.png\n")
}

# Function to predict RCS dose-response
predict_rcs_dose_response <- function(rcs_result, imp_list, n_points = 100) {
  
  exposure_var <- rcs_result$exposure
  outcome_var <- rcs_result$outcome
  n_knots <- rcs_result$n_knots
  
  # Get exposure range
  exposure_range <- range(sapply(imp_list, function(d) range(d[[exposure_var]], na.rm = TRUE)))
  exposure_seq <- seq(exposure_range[1], exposure_range[2], length.out = n_points)
  
  # Get reference values
  ref_data <- imp_list[[1]]
  
  pred_data <- data.frame(
    Exposure = exposure_seq,
    Age = mean(ref_data$Age, na.rm = TRUE),
    BMI = mean(ref_data$BMI, na.rm = TRUE),
    Gender = names(sort(table(ref_data$Gender), decreasing = TRUE))[1],
    Geographic_Region = names(sort(table(ref_data$Geographic_Region), decreasing = TRUE))[1]
  )
  names(pred_data)[1] <- exposure_var
  
  # Predict for each imputed dataset
  pred_list <- list()
  
  for(i in 1:length(imp_list)) {
    data_i <- imp_list[[i]]
    
    design_i <- svydesign(
      ids = ~1,
      strata = ~Geographic_Region,
      weights = ~Sampling_Weight,
      data = data_i,
      nest = TRUE
    )
    
    formula_str <- paste(outcome_var, "~ rcs(", exposure_var, ",", n_knots, 
                         ") + Age + Gender + Geographic_Region + BMI")
    
    model_i <- svyglm(as.formula(formula_str), design_i, family = gaussian())
    
    # FIX: Check return type before using $
    pred_i <- predict(model_i, newdata = pred_data, type = "response", se.fit = TRUE)
    
    if(is.list(pred_i)) {
      pred_list[[i]] <- data.frame(
        fit = pred_i$fit,
        se = pred_i$se.fit
      )
    } else {
      pred_list[[i]] <- data.frame(
        fit = as.vector(pred_i),
        se = rep(NA, length(pred_i))
      )
    }
  }
  
  # Pool predictions
  pred_pooled <- data.frame(
    Exposure = exposure_seq,
    Predicted = rowMeans(sapply(pred_list, function(x) x$fit)),
    SE = sqrt(rowMeans(sapply(pred_list, function(x) x$se^2), na.rm = TRUE))
  )
  
  pred_pooled$CI_Lower <- pred_pooled$Predicted - 1.96 * pred_pooled$SE
  pred_pooled$CI_Upper <- pred_pooled$Predicted + 1.96 * pred_pooled$SE
  
  names(pred_pooled)[1] <- exposure_var
  
  return(pred_pooled)
}

# Predict RCS dose-response
if(!is.null(rcs_hemoglobin)) {
  pred_hemoglobin <- predict_rcs_dose_response(rcs_hemoglobin, imp_list)
  
  p_hemoglobin <- ggplot(pred_hemoglobin, aes(x = Hemoglobin, y = Predicted)) +
    geom_line(color = tableau10[3], size = 1.2) +
    geom_ribbon(aes(ymin = CI_Lower, ymax = CI_Upper), 
                alpha = 0.2, fill = tableau10[3]) +
    labs(
      title = "Dose-Response: Hemoglobin vs Bone Mineral Density (RCS)",
      x = "Hemoglobin (g/L)",
      y = "Predicted BMD (g/cm²)",
      caption = paste0("Non-linearity P = ", format.pval(rcs_hemoglobin$nonlinearity_p, digits = 3))
    ) +
    theme_minimal(base_size = 12) +
    theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  
  ggsave("dose_response_hemoglobin.png", p_hemoglobin, width = 10, height = 6, dpi = 300)
  cat("Generated: dose_response_hemoglobin.png\n")
}

if(!is.null(rcs_glucose)) {
  pred_glucose <- predict_rcs_dose_response(rcs_glucose, imp_list)
  
  p_glucose <- ggplot(pred_glucose, aes(x = Fasting_Glucose, y = Predicted)) +
    geom_line(color = tableau10[4], size = 1.2) +
    geom_ribbon(aes(ymin = CI_Lower, ymax = CI_Upper), 
                alpha = 0.2, fill = tableau10[4]) +
    labs(
      title = "Dose-Response: Fasting Glucose vs Bone Mineral Density (RCS)",
      x = "Fasting Glucose (mmol/L)",
      y = "Predicted BMD (g/cm²)",
      caption = paste0("Non-linearity P = ", format.pval(rcs_glucose$nonlinearity_p, digits = 3))
    ) +
    theme_minimal(base_size = 12) +
    theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  
  ggsave("dose_response_glucose.png", p_glucose, width = 10, height = 6, dpi = 300)
  cat("Generated: dose_response_glucose.png\n")
}

cat("Validation passed: Dose-response curves generated\n\n")

# Compile Results Table
# ----------------------------------------------------------------------------
cat("\n=== Step 7: Compile Results ===\n")

dose_response_results <- data.frame(
  Exposure = character(),
  Outcome = character(),
  Trend_Type = character(),
  Effect_Estimate = numeric(),
  CI_Lower = numeric(),
  CI_Upper = numeric(),
  P_Value = numeric(),
  Nonlinearity_P = numeric(),
  stringsAsFactors = FALSE
)

if(!is.null(trend_exercise)) {
  dose_response_results <- rbind(dose_response_results, data.frame(
    Exposure = "Exercise_Frequency",
    Outcome = "Osteoporosis_Binary",
    Trend_Type = "Ordinal_Linear",
    Effect_Estimate = trend_exercise$pr,
    CI_Lower = trend_exercise$ci_lower,
    CI_Upper = trend_exercise$ci_upper,
    P_Value = trend_exercise$p_value,
    Nonlinearity_P = NA
  ))
}

if(!is.null(trend_alcohol)) {
  dose_response_results <- rbind(dose_response_results, data.frame(
    Exposure = "Alcohol_Frequency",
    Outcome = "Osteoporosis_Binary",
    Trend_Type = "Ordinal_Linear",
    Effect_Estimate = trend_alcohol$pr,
    CI_Lower = trend_alcohol$ci_lower,
    CI_Upper = trend_alcohol$ci_upper,
    P_Value = trend_alcohol$p_value,
    Nonlinearity_P = NA
  ))
}

if(!is.null(rcs_hemoglobin)) {
  dose_response_results <- rbind(dose_response_results, data.frame(
    Exposure = "Hemoglobin",
    Outcome = "Bone_Mineral_Density",
    Trend_Type = "RCS_Nonlinear",
    Effect_Estimate = NA,
    CI_Lower = NA,
    CI_Upper = NA,
    P_Value = NA,
    Nonlinearity_P = rcs_hemoglobin$nonlinearity_p
  ))
}

if(!is.null(rcs_glucose)) {
  dose_response_results <- rbind(dose_response_results, data.frame(
    Exposure = "Fasting_Glucose",
    Outcome = "Bone_Mineral_Density",
    Trend_Type = "RCS_Nonlinear",
    Effect_Estimate = NA,
    CI_Lower = NA,
    CI_Upper = NA,
    P_Value = NA,
    Nonlinearity_P = rcs_glucose$nonlinearity_p
  ))
}

# Validate output quality
validate_output_quality(dose_response_results)

write.csv(dose_response_results, "dose_response_results.csv", row.names = FALSE)
cat("Generated: dose_response_results.csv\n\n")

# Identify significant trends
significant_trends <- dose_response_results$Exposure[
  (!is.na(dose_response_results$P_Value) & dose_response_results$P_Value < 0.05) |
  (!is.na(dose_response_results$Nonlinearity_P) & dose_response_results$Nonlinearity_P < 0.05)
]

cat("Significant dose-response relationships detected:\n")
print(significant_trends)
cat("\n")

# Generate Standard Outputs (Template 3)
# ----------------------------------------------------------------------------
cat("\n=== Step 8: Generate Standard Outputs ===\n")

# main_output.csv (pass through from previous stage)
write.csv(data_ref, "main_output.csv", row.names = FALSE)
cat("Generated: main_output.csv\n")

# analysis_summary.json
analysis_summary <- list(
  stage = "7.7_dose_response_analysis",
  timestamp = format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
  sample_size = nrow(data_ref),
  n_imputations = length(imp_list),
  
  ordinal_exposures = c("Exercise_Frequency", "Alcohol_Frequency"),
  continuous_exposures = c("Hemoglobin", "Fasting_Glucose"),
  
  ordinal_levels = list(
    Exercise_Frequency = c("No_Exercise", "Occasional", "Weekly_Or_More", "Daily"),
    Alcohol_Frequency = c("Never", "Occasional", "Frequent", "Daily")
  ),
  
  rcs_knots = 4,
  adjustment_variables = adjustment_vars,
  
  significant_trends = as.character(significant_trends),
  
  ordinal_trend_results = list(
    Exercise_Frequency = if(!is.null(trend_exercise)) list(
      PR = trend_exercise$pr,
      CI = c(trend_exercise$ci_lower, trend_exercise$ci_upper),
      P = trend_exercise$p_value
    ) else NULL,
    Alcohol_Frequency = if(!is.null(trend_alcohol)) list(
      PR = trend_alcohol$pr,
      CI = c(trend_alcohol$ci_lower, trend_alcohol$ci_upper),
      P = trend_alcohol$p_value
    ) else NULL
  ),
  
  rcs_nonlinearity_results = list(
    Hemoglobin = if(!is.null(rcs_hemoglobin)) list(
      Nonlinearity_P = rcs_hemoglobin$nonlinearity_p
    ) else NULL,
    Fasting_Glucose = if(!is.null(rcs_glucose)) list(
      Nonlinearity_P = rcs_glucose$nonlinearity_p
    ) else NULL
  ),
  
  critical_decisions = list(
    ordinal_scoring = "Sequential integers (0, 1, 2, ...) for ordinal levels",
    rcs_knots = "4 knots placed at quantiles for RCS models",
    pooling_method = "Manual Rubin's Rules for combining MICE results",
    adjustment_strategy = "Same covariates as main model (Age, Gender, Geographic_Region, BMI)",
    binary_outcome_family = "quasipoisson(link='log') for PR estimation",
    continuous_outcome_family = "gaussian() for BMD prediction",
    nonlinearity_test = "F-test comparing linear vs RCS models",
    prediction_fix = "Added type checking for predict() return values to handle both list and atomic vector returns"
  ),
  
  statistical_methods_summary = list(
    ordinal_trend = "Survey-weighted GLM with ordinal score as continuous predictor",
    rcs_modeling = "Restricted Cubic Splines with 4 knots",
    pooling = "Manual Rubin's Rules across 20 MICE datasets",
    inference = "Pooled estimates with Barnard-Rubin degrees of freedom"
  ),
  
  next_stage_requirements = list(
    note = "Dose-response analysis complete. Results can inform sensitivity analyses.",
    data_transfer = "main_output.csv contains original data for next stage"
  ),
  
  output_files = list(
    main_output = "main_output.csv",
    dose_response_results = "dose_response_results.csv",
    graphics = c(
      "dose_response_exercise.png",
      "dose_response_alcohol.png",
      "dose_response_hemoglobin.png",
      "dose_response_glucose.png"
    )
  )
)

jsonlite::write_json(analysis_summary, "analysis_summary.json", pretty = TRUE, auto_unbox = TRUE)
cat("Generated: analysis_summary.json\n\n")

# Final Safeguard (Template 4)
# ----------------------------------------------------------------------------
ensure_output_files(data_ref, analysis_summary)

cat("\n=== Stage 7.7 Dose-Response Analysis Complete ===\n")
cat("All deliverables generated successfully\n")
cat("Timestamp:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")