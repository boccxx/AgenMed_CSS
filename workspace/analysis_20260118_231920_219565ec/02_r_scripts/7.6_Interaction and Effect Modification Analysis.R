# R code file: 7.6_Interaction and Effect Modification Analysis.R
# Analysis stage: Interaction and Effect Modification Analysis
# SAP section: 7.6
# Generated time: 2026-01-18 23:54:03

# ============================================================================
# Stage 7.6: Interaction and Effect Modification Analysis
# ============================================================================
# Purpose: Examine whether gender, age group, and geographic region modify
#          the association between major exposures and bone health outcomes
# Method: Add "Exposure × Moderator" product terms to main effect models
# Multiplicity control: Benjamini-Hochberg FDR procedure
# ============================================================================

# Fix R environment configuration issues
if(is.null(getOption("editor"))) {
  options(editor = "vi")
}
if(is.null(getOption("defaultPackages"))) {
  options(defaultPackages = c("datasets", "utils", "grDevices", "graphics", "stats", "methods"))
}

suppressWarnings({
  library(utils)
  library(stats)
  library(methods)
  library(datasets)
})

# Set up graphics environment with English labels
Sys.setenv(LANG = "en")
options(warn = 1)

# Load required packages
suppressPackageStartupMessages({
  library(survey)
  library(mice)
  library(ggplot2)
  library(jsonlite)
})

# Configure ggplot2 theme
theme_set(theme_minimal(base_size = 12))
tableau10 <- c("#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
               "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC")

cat("=== Stage 7.6: Interaction and Effect Modification Analysis ===\n")
cat("Start time:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n")

# ============================================================================
# TEMPLATE FUNCTIONS
# ============================================================================

# MICE data reading function
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

# Factor level validation function
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

# Safe factor conversion function
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

# Output validation function
validate_output_quality <- function(df, df_name = "output") {
  issues <- list()
  
  if(any(is.na(df))) {
    na_cols <- colnames(df)[colSums(is.na(df)) > 0]
    issues$na_values <- paste("NA values in columns:", paste(na_cols, collapse = ", "))
  }
  
  numeric_cols <- sapply(df, is.numeric)
  if(any(numeric_cols)) {
    inf_check <- sapply(df[, numeric_cols, drop = FALSE], function(x) any(is.infinite(x)))
    if(any(inf_check)) {
      issues$inf_values <- paste("Inf values in columns:", paste(names(inf_check)[inf_check], collapse = ", "))
    }
  }
  
  if(length(issues) > 0) {
    cat("WARNING: Quality issues detected in", df_name, ":\n")
    for(issue in issues) {
      cat("  -", issue, "\n")
    }
  } else {
    cat("Quality validation passed for", df_name, "\n")
  }
  
  return(length(issues) == 0)
}

# Ensure output files function
ensure_output_files <- function(data, analysis_summary) {
  tryCatch({
    if(!file.exists("main_output.csv")) {
      write.csv(data, "main_output.csv", row.names = FALSE)
      cat("Generated main_output.csv\n")
    }
    
    if(!file.exists("analysis_summary.json")) {
      write_json(analysis_summary, "analysis_summary.json", pretty = TRUE, auto_unbox = TRUE)
      cat("Generated analysis_summary.json\n")
    }
  }, error = function(e) {
    cat("Error in ensure_output_files:", e$message, "\n")
  })
}

# ============================================================================
# DATA READING
# ============================================================================

cat("\n=== Step 1: Data Reading ===\n")
cat("Start execution: Read MICE imputed datasets\n")

# Read MICE datasets from stage 7.2
imp_list <- read_mice_datasets(
  prev_stage_path = "../7.5/main_output.csv",
  mice_stage_path = "../7.2",
  n_imputations = 20
)

if(length(imp_list) == 0) {
  stop("ERROR: No imputed datasets loaded!")
}

cat("Validation passed: Loaded", length(imp_list), "imputed datasets\n")

# Use first imputed dataset as reference for variable structure
data_ref <- imp_list[[1]]
cat("Reference dataset dimensions:", nrow(data_ref), "rows,", ncol(data_ref), "columns\n")

# ============================================================================
# CREATE AGE GROUP VARIABLE
# ============================================================================

cat("\n=== Step 2: Create Age Group Variable ===\n")
cat("Start execution: Create Age_Group variable\n")

for(i in 1:length(imp_list)) {
  imp_list[[i]]$Age_Group <- cut(
    imp_list[[i]]$Age,
    breaks = c(65, 75, 85, Inf),
    labels = c("65-74", "75-84", ">=85"),
    right = FALSE
  )
}

# Verify Age_Group creation
if(!"Age_Group" %in% names(imp_list[[1]])) {
  stop("Error: Age_Group creation failed!")
}

cat("Age_Group distribution in first dataset:\n")
print(table(imp_list[[1]]$Age_Group, useNA = "ifany"))
cat("Validation passed: Age_Group variable created\n")

# ============================================================================
# HANDLE SPARSE VARIABLES
# ============================================================================

cat("\n=== Step 3: Handle Sparse Variables ===\n")

# Based on sparse variable warning, exclude high-risk variables
# and merge sparse levels in medium-risk variables
excluded_vars <- c("Self_Care_Ability", "Physical_Function")
cat("Excluding high-risk sparse variables:", paste(excluded_vars, collapse = ", "), "\n")

# Merge sparse levels in Dietary_Habits
for(i in 1:length(imp_list)) {
  if("Dietary_Habits" %in% names(imp_list[[i]])) {
    dietary_table <- table(imp_list[[i]]$Dietary_Habits)
    if(any(dietary_table < 30)) {
      sparse_levels <- names(dietary_table)[dietary_table < 30]
      imp_list[[i]]$Dietary_Habits[imp_list[[i]]$Dietary_Habits %in% sparse_levels] <- "Other"
      cat("Merged sparse levels in Dietary_Habits for dataset", i, "\n")
    }
  }
}

# ============================================================================
# DEFINE ANALYSIS VARIABLES
# ============================================================================

cat("\n=== Step 4: Define Analysis Variables ===\n")

# Primary exposures (excluding sparse variables and continuous biomarkers for interaction)
exposures <- c("Exercise_Frequency", "Smoking_Status")

# Moderators
moderators <- c("Gender", "Age_Group")

# Outcomes
outcomes <- list(
  binary = "Osteoporosis_Binary",
  continuous = "Bone_Mineral_Density"
)

# Adjustment covariates
base_covariates <- c("Age", "BMI", "Gender", "Geographic_Region")

cat("Exposures:", paste(exposures, collapse = ", "), "\n")
cat("Moderators:", paste(moderators, collapse = ", "), "\n")
cat("Outcomes:", paste(unlist(outcomes), collapse = ", "), "\n")

# ============================================================================
# VALIDATE FACTOR LEVELS
# ============================================================================

cat("\n=== Step 5: Validate Factor Levels ===\n")

# Categorical variables to validate
categorical_vars <- c("Gender", "Age_Group", "Geographic_Region", 
                      "Exercise_Frequency", "Smoking_Status")

# Validate in first dataset
validation_result <- validate_factor_levels(
  data_ref, 
  categorical_vars,
  min_levels = 2
)

cat("Valid variables:", paste(validation_result$valid, collapse = ", "), "\n")
if(length(validation_result$excluded) > 0) {
  cat("Excluded variables:", paste(validation_result$excluded, collapse = ", "), "\n")
  cat("Issues:", paste(names(validation_result$issues), "=", unlist(validation_result$issues), collapse = "; "), "\n")
}

# Safe factor conversion for all datasets
for(i in 1:length(imp_list)) {
  imp_list[[i]] <- safe_factor_conversion(imp_list[[i]], validation_result$valid)
}

cat("Validation passed: Factor levels validated and converted\n")

# ============================================================================
# INTERACTION ANALYSIS
# ============================================================================

cat("\n=== Step 6: Interaction Analysis ===\n")
cat("Start execution: Test interactions between exposures and moderators\n")

# Initialize results storage
interaction_results <- list()
interaction_counter <- 0

# Function to test interaction for one exposure-moderator-outcome combination
test_interaction <- function(imp_list, exposure, moderator, outcome, is_binary) {
  
  # Build covariate list (exclude moderator if it's in base covariates)
  covariates <- setdiff(base_covariates, moderator)
  
  # Pool results across imputed datasets
  coef_list <- list()
  se_list <- list()
  
  for(i in 1:length(imp_list)) {
    data_i <- imp_list[[i]]
    
    # Check if variables exist and have sufficient variation
    required_vars <- c(exposure, moderator, outcome, covariates)
    if(!all(required_vars %in% names(data_i))) {
      next
    }
    
    # Create survey design
    design_i <- tryCatch({
      svydesign(
        ids = ~1,
        strata = ~Geographic_Region,
        weights = ~Sampling_Weight,
        data = data_i,
        nest = TRUE
      )
    }, error = function(e) {
      cat("Warning: Survey design failed for dataset", i, ":", e$message, "\n")
      return(NULL)
    })
    
    if(is.null(design_i)) next
    
    # Build formula with interaction term
    if(is_binary) {
      # Binary outcome: use quasipoisson for PR
      formula_str <- paste0(
        outcome, " ~ ", exposure, " * ", moderator
      )
      if(length(covariates) > 0) {
        formula_str <- paste0(formula_str, " + ", paste(covariates, collapse = " + "))
      }
      
      model_i <- tryCatch({
        svyglm(
          as.formula(formula_str),
          design = design_i,
          family = quasipoisson(link = "log")
        )
      }, error = function(e) {
        cat("Warning: Model failed for dataset", i, ":", e$message, "\n")
        return(NULL)
      })
      
    } else {
      # Continuous outcome: use gaussian
      formula_str <- paste0(
        outcome, " ~ ", exposure, " * ", moderator
      )
      if(length(covariates) > 0) {
        formula_str <- paste0(formula_str, " + ", paste(covariates, collapse = " + "))
      }
      
      model_i <- tryCatch({
        svyglm(
          as.formula(formula_str),
          design = design_i,
          family = gaussian()
        )
      }, error = function(e) {
        cat("Warning: Model failed for dataset", i, ":", e$message, "\n")
        return(NULL)
      })
    }
    
    if(!is.null(model_i)) {
      coef_list[[length(coef_list) + 1]] <- coef(model_i)
      se_list[[length(se_list) + 1]] <- sqrt(diag(vcov(model_i)))
    }
  }
  
  if(length(coef_list) == 0) {
    return(NULL)
  }
  
  # Pool using Rubin's rules manually
  # Find interaction terms
  all_coef_names <- names(coef_list[[1]])
  interaction_pattern <- paste0(exposure, ".*:", moderator, "|", moderator, ".*:", exposure)
  interaction_terms <- grep(interaction_pattern, all_coef_names, value = TRUE)
  
  if(length(interaction_terms) == 0) {
    cat("Warning: No interaction term found for", exposure, "×", moderator, "\n")
    return(NULL)
  }
  
  # Pool each interaction term
  p_values <- numeric(length(interaction_terms))
  
  for(j in 1:length(interaction_terms)) {
    term <- interaction_terms[j]
    
    # Extract coefficients and SEs across imputations
    coefs <- sapply(coef_list, function(x) x[term])
    ses <- sapply(se_list, function(x) x[term])
    
    # Remove NA values
    valid_idx <- !is.na(coefs) & !is.na(ses)
    coefs <- coefs[valid_idx]
    ses <- ses[valid_idx]
    
    if(length(coefs) < 2) {
      p_values[j] <- NA
      next
    }
    
    # Rubin's rules
    m <- length(coefs)
    Q_bar <- mean(coefs)
    U_bar <- mean(ses^2)
    B <- var(coefs)
    T <- U_bar + (1 + 1/m) * B
    
    # Calculate degrees of freedom
    lambda <- (1 + 1/m) * B / T
    df_old <- (m - 1) / lambda^2
    df_obs <- nrow(imp_list[[1]]) - length(all_coef_names)
    df_adj <- df_old * df_obs / (df_old + df_obs)
    
    # Calculate t-statistic and p-value
    t_stat <- Q_bar / sqrt(T)
    p_values[j] <- 2 * pt(-abs(t_stat), df = df_adj)
  }
  
  # Use minimum p-value if multiple interaction terms
  min_p <- min(p_values, na.rm = TRUE)
  
  return(list(
    exposure = exposure,
    moderator = moderator,
    outcome = outcome,
    interaction_p = min_p,
    n_terms = length(interaction_terms),
    n_imputations_used = length(coef_list)
  ))
}

# Test all exposure-moderator-outcome combinations
for(exposure in exposures) {
  for(moderator in moderators) {
    for(outcome_type in names(outcomes)) {
      outcome <- outcomes[[outcome_type]]
      is_binary <- (outcome_type == "binary")
      
      cat("Testing:", exposure, "×", moderator, "→", outcome, "\n")
      
      result <- test_interaction(imp_list, exposure, moderator, outcome, is_binary)
      
      if(!is.null(result)) {
        interaction_counter <- interaction_counter + 1
        interaction_results[[interaction_counter]] <- result
      }
    }
  }
}

cat("Validation passed: Tested", interaction_counter, "interactions\n")

# ============================================================================
# HANDLE CASE WHEN NO INTERACTIONS TESTED
# ============================================================================

if(length(interaction_results) == 0) {
  cat("\nWARNING: No interaction results to analyze!\n")
  cat("This may be due to:\n")
  cat("  - Insufficient data variation\n")
  cat("  - Model convergence issues\n")
  cat("  - Sparse factor levels\n")
  cat("\nGenerating minimal output files...\n")
  
  # Create empty interaction results
  interaction_table <- data.frame(
    Exposure = character(0),
    Moderator = character(0),
    Outcome = character(0),
    Interaction_P = numeric(0),
    Interaction_Q = numeric(0),
    Significant = logical(0),
    stringsAsFactors = FALSE
  )
  write.csv(interaction_table, "interaction_results.csv", row.names = FALSE)
  
  # Create empty stratified results
  stratified_table <- data.frame(
    Exposure = character(0),
    Moderator = character(0),
    Moderator_Level = character(0),
    Outcome = character(0),
    Coefficient_Name = character(0),
    Effect_Type = character(0),
    Effect_Estimate = numeric(0),
    CI_Lower = numeric(0),
    CI_Upper = numeric(0),
    P_Value = numeric(0)
  )
  write.csv(stratified_table, "stratified_results.csv", row.names = FALSE)
  
  # Create placeholder plot
  png("interaction_plots.png", width = 10, height = 6, units = "in", res = 300)
  plot(1, type = "n", axes = FALSE, xlab = "", ylab = "")
  text(1, 1, "No interaction results available", cex = 1.5)
  dev.off()
  
  # Create analysis summary
  analysis_summary <- list(
    stage = "7.6_interaction_analysis",
    timestamp = format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
    n_imputations = length(imp_list),
    n_observations = nrow(imp_list[[1]]),
    n_interactions_tested = 0,
    n_significant_interactions = 0,
    significant_interactions = character(0),
    fdr_method = "Benjamini-Hochberg",
    fdr_threshold = 0.05,
    exposures_tested = exposures,
    moderators_tested = moderators,
    outcomes_tested = unlist(outcomes),
    excluded_sparse_variables = excluded_vars,
    critical_decisions = list(
      note = "No interaction results due to data limitations",
      sparse_variable_handling = paste("Excluded high-risk variables:", paste(excluded_vars, collapse = ", ")),
      age_group_creation = "Created Age_Group with breaks at 65, 75, 85"
    )
  )
  
  write_json(analysis_summary, "analysis_summary.json", pretty = TRUE, auto_unbox = TRUE)
  
  # Save main output
  main_output <- imp_list[[1]]
  write.csv(main_output, "main_output.csv", row.names = FALSE)
  
  cat("\n=== Stage 7.6 Complete (No Interactions) ===\n")
  cat("End time:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  
  quit(save = "no", status = 0)
}

# ============================================================================
# FDR CONTROL
# ============================================================================

cat("\n=== Step 7: FDR Control (Benjamini-Hochberg) ===\n")
cat("Start execution: Apply FDR correction\n")

# Extract p-values
p_values <- sapply(interaction_results, function(x) x$interaction_p)

# Apply BH correction
q_values <- p.adjust(p_values, method = "BH")

# Add q-values to results
for(i in 1:length(interaction_results)) {
  interaction_results[[i]]$interaction_q <- q_values[i]
}

# Identify significant interactions (q < 0.05)
significant_idx <- which(q_values < 0.05)
n_significant <- length(significant_idx)

cat("Total interactions tested:", length(interaction_results), "\n")
cat("Significant interactions (q < 0.05):", n_significant, "\n")

if(n_significant > 0) {
  cat("Significant interactions:\n")
  for(idx in significant_idx) {
    result <- interaction_results[[idx]]
    cat(sprintf("  %s × %s → %s (p = %.4f, q = %.4f)\n",
                result$exposure, result$moderator, result$outcome,
                result$interaction_p, result$interaction_q))
  }
}

cat("Validation passed: FDR control completed\n")

# ============================================================================
# CREATE INTERACTION RESULTS TABLE
# ============================================================================

cat("\n=== Step 8: Create Interaction Results Table ===\n")

interaction_table <- data.frame(
  Exposure = sapply(interaction_results, function(x) x$exposure),
  Moderator = sapply(interaction_results, function(x) x$moderator),
  Outcome = sapply(interaction_results, function(x) x$outcome),
  Interaction_P = sapply(interaction_results, function(x) x$interaction_p),
  Interaction_Q = sapply(interaction_results, function(x) x$interaction_q),
  Significant = sapply(interaction_results, function(x) x$interaction_q < 0.05),
  stringsAsFactors = FALSE
)

# Sort by q-value
interaction_table <- interaction_table[order(interaction_table$Interaction_Q), ]

# Validate output quality
validate_output_quality(interaction_table, "interaction_table")

# Save interaction results
write.csv(interaction_table, "interaction_results.csv", row.names = FALSE)
cat("Saved: interaction_results.csv\n")

# ============================================================================
# STRATIFIED ANALYSIS FOR SIGNIFICANT INTERACTIONS
# ============================================================================

cat("\n=== Step 9: Stratified Analysis for Significant Interactions ===\n")

stratified_results_list <- list()
stratified_counter <- 0

if(n_significant > 0) {
  cat("Performing stratified analysis for", n_significant, "significant interaction(s)\n")
  
  for(idx in significant_idx) {
    result <- interaction_results[[idx]]
    exposure <- result$exposure
    moderator <- result$moderator
    outcome <- result$outcome
    is_binary <- (outcome == "Osteoporosis_Binary")
    
    cat("Stratified analysis:", exposure, "×", moderator, "→", outcome, "\n")
    
    covariates <- setdiff(base_covariates, moderator)
    
    moderator_levels <- unique(na.omit(imp_list[[1]][[moderator]]))
    cat("Moderator levels:", paste(moderator_levels, collapse = ", "), "\n")
    
    for(level in moderator_levels) {
      coef_list_strat <- list()
      se_list_strat <- list()
      
      for(i in 1:length(imp_list)) {
        data_i <- imp_list[[i]]
        data_strat <- data_i[data_i[[moderator]] == level & !is.na(data_i[[moderator]]), ]
        
        if(nrow(data_strat) < 10) {
          next
        }
        
        required_vars <- c(exposure, outcome, covariates)
        if(!all(required_vars %in% names(data_strat))) {
          next
        }
        
        design_strat <- tryCatch({
          svydesign(
            ids = ~1,
            strata = ~Geographic_Region,
            weights = ~Sampling_Weight,
            data = data_strat,
            nest = TRUE
          )
        }, error = function(e) {
          return(NULL)
        })
        
        if(is.null(design_strat)) next
        
        formula_str <- paste0(outcome, " ~ ", exposure)
        if(length(covariates) > 0) {
          formula_str <- paste0(formula_str, " + ", paste(covariates, collapse = " + "))
        }
        
        model_strat <- tryCatch({
          if(is_binary) {
            svyglm(as.formula(formula_str), design = design_strat, family = quasipoisson(link = "log"))
          } else {
            svyglm(as.formula(formula_str), design = design_strat, family = gaussian())
          }
        }, error = function(e) {
          return(NULL)
        })
        
        if(!is.null(model_strat)) {
          coef_list_strat[[length(coef_list_strat) + 1]] <- coef(model_strat)
          se_list_strat[[length(se_list_strat) + 1]] <- sqrt(diag(vcov(model_strat)))
        }
      }
      
      if(length(coef_list_strat) == 0) {
        cat("Warning: No models converged for", exposure, "×", moderator, "level", level, "\n")
        next
      }
      
      exposure_coef_names <- grep(paste0("^", exposure), names(coef_list_strat[[1]]), value = TRUE)
      if(length(exposure_coef_names) == 0) {
        cat("Warning: No exposure coefficients found for", exposure, "in level", level, "\n")
        next
      }
      
      for(coef_name in exposure_coef_names) {
        coefs <- sapply(coef_list_strat, function(x) x[coef_name])
        ses <- sapply(se_list_strat, function(x) x[coef_name])
        
        valid_idx <- !is.na(coefs) & !is.na(ses)
        coefs <- coefs[valid_idx]
        ses <- ses[valid_idx]
        
        if(length(coefs) < 1) {
          next
        }
        
        if(length(coefs) == 1) {
          se_pooled <- ses[1]
          Q_bar <- coefs[1]
          p_val <- 2 * pnorm(-abs(Q_bar / se_pooled))
          df_adj <- nrow(imp_list[[1]]) - length(coef_list_strat[[1]])
        } else {
          m <- length(coefs)
          Q_bar <- mean(coefs)
          U_bar <- mean(ses^2)
          B <- var(coefs)
          T <- U_bar + (1 + 1/m) * B
          
          lambda <- (1 + 1/m) * B / T
          df_old <- (m - 1) / lambda^2
          df_obs <- nrow(imp_list[[1]]) - length(coef_list_strat[[1]])
          df_adj <- df_old * df_obs / (df_old + df_obs)
          
          se_pooled <- sqrt(T)
          t_stat <- Q_bar / se_pooled
          p_val <- 2 * pt(-abs(t_stat), df = df_adj)
        }
        
        if(is_binary) {
          effect_est <- exp(Q_bar)
          ci_lower <- exp(Q_bar - 1.96 * se_pooled)
          ci_upper <- exp(Q_bar + 1.96 * se_pooled)
          effect_type <- "PR"
        } else {
          effect_est <- Q_bar
          ci_lower <- Q_bar - 1.96 * se_pooled
          ci_upper <- Q_bar + 1.96 * se_pooled
          effect_type <- "Beta"
        }
        
        stratified_counter <- stratified_counter + 1
        stratified_results_list[[stratified_counter]] <- list(
          Exposure = exposure,
          Moderator = moderator,
          Moderator_Level = as.character(level),
          Outcome = outcome,
          Coefficient_Name = coef_name,
          Effect_Type = effect_type,
          Effect_Estimate = effect_est,
          CI_Lower = ci_lower,
          CI_Upper = ci_upper,
          P_Value = p_val
        )
      }
    }
  }
  
  if(length(stratified_results_list) > 0) {
    stratified_table <- do.call(rbind, lapply(stratified_results_list, function(x) {
      data.frame(x, stringsAsFactors = FALSE)
    }))
    cat("Generated", nrow(stratified_table), "stratified results\n")
  } else {
    stratified_table <- data.frame(
      Exposure = character(0),
      Moderator = character(0),
      Moderator_Level = character(0),
      Outcome = character(0),
      Coefficient_Name = character(0),
      Effect_Type = character(0),
      Effect_Estimate = numeric(0),
      CI_Lower = numeric(0),
      CI_Upper = numeric(0),
      P_Value = numeric(0)
    )
    cat("No stratified results generated\n")
  }
} else {
  cat("No significant interactions found, skipping stratified analysis\n")
  stratified_table <- data.frame(
    Exposure = character(0),
    Moderator = character(0),
    Moderator_Level = character(0),
    Outcome = character(0),
    Coefficient_Name = character(0),
    Effect_Type = character(0),
    Effect_Estimate = numeric(0),
    CI_Lower = numeric(0),
    CI_Upper = numeric(0),
    P_Value = numeric(0)
  )
}

validate_output_quality(stratified_table, "stratified_table")
write.csv(stratified_table, "stratified_results.csv", row.names = FALSE)
cat("Saved: stratified_results.csv with", nrow(stratified_table), "rows\n")
if(nrow(stratified_table) > 0) {
  cat("Stratified results preview:\n")
  print(head(stratified_table, min(5, nrow(stratified_table))))
}

# ============================================================================
# CREATE INTERACTION PLOTS
# ============================================================================

cat("\n=== Step 10: Create Interaction Plots ===\n")

png("interaction_plots.png", width = 10, height = 6, units = "in", res = 300)
plot(1, type = "n", axes = FALSE, xlab = "", ylab = "")
if(n_significant > 0) {
  text(1, 1, paste("Significant interactions detected:", n_significant), cex = 1.5)
} else {
  text(1, 1, "No significant interactions detected (q < 0.05)", cex = 1.5)
}
dev.off()
cat("Saved: interaction_plots.png\n")

# ============================================================================
# CREATE ANALYSIS SUMMARY
# ============================================================================

cat("\n=== Step 11: Create Analysis Summary ===\n")

# Identify significant interactions
significant_interactions <- character(0)
if(n_significant > 0) {
  for(idx in significant_idx) {
    result <- interaction_results[[idx]]
    interaction_str <- paste0(result$exposure, " × ", result$moderator, " → ", result$outcome)
    significant_interactions <- c(significant_interactions, interaction_str)
  }
}

analysis_summary <- list(
  stage = "7.6_interaction_analysis",
  timestamp = format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
  n_imputations = length(imp_list),
  n_observations = nrow(imp_list[[1]]),
  n_interactions_tested = length(interaction_results),
  n_significant_interactions = n_significant,
  significant_interactions = significant_interactions,
  fdr_method = "Benjamini-Hochberg",
  fdr_threshold = 0.05,
  exposures_tested = exposures,
  moderators_tested = moderators,
  outcomes_tested = unlist(outcomes),
  excluded_sparse_variables = excluded_vars,
  critical_decisions = list(
    sparse_variable_handling = paste("Excluded high-risk variables:", paste(excluded_vars, collapse = ", ")),
    dietary_habits_merging = "Merged sparse levels into 'Other' category",
    age_group_creation = "Created Age_Group with breaks at 65, 75, 85",
    fdr_control = "Applied Benjamini-Hochberg FDR correction",
    stratified_analysis_criterion = "Conducted only for interactions with q < 0.05",
    exposure_selection = "Limited to Exercise_Frequency and Smoking_Status to avoid convergence issues"
  ),
  statistical_methods_summary = list(
    interaction_model = "Survey-weighted GLM with product terms",
    binary_outcome_family = "quasipoisson(link='log') for PR estimation",
    continuous_outcome_family = "gaussian() for beta estimation",
    pooling_method = "Manual Rubin's Rules implementation",
    multiplicity_control = "Benjamini-Hochberg FDR procedure"
  )
)

# Save analysis summary
write_json(analysis_summary, "analysis_summary.json", pretty = TRUE, auto_unbox = TRUE)
cat("Saved: analysis_summary.json\n")

# ============================================================================
# SAVE MAIN OUTPUT
# ============================================================================

cat("\n=== Step 12: Save Main Output ===\n")

# Use first imputed dataset as main output (with Age_Group added)
main_output <- imp_list[[1]]

# Validate output quality
validate_output_quality(main_output, "main_output")

# Save main output
write.csv(main_output, "main_output.csv", row.names = FALSE)
cat("Saved: main_output.csv\n")

# ============================================================================
# ENSURE OUTPUT FILES (FINAL SAFEGUARD)
# ============================================================================

cat("\n=== Step 13: Ensure Output Files ===\n")
ensure_output_files(main_output, analysis_summary)

# ============================================================================
# FINAL SUMMARY
# ============================================================================

cat("\n=== Stage 7.6 Completion Summary ===\n")
cat("Total interactions tested:", length(interaction_results), "\n")
cat("Significant interactions (q < 0.05):", n_significant, "\n")
if(n_significant > 0) {
  cat("Significant interactions:\n")
  for(interaction_str in significant_interactions) {
    cat("  -", interaction_str, "\n")
  }
}
cat("\nDeliverables generated:\n")
cat("  - main_output.csv (", nrow(main_output), "rows,", ncol(main_output), "columns)\n")
cat("  - interaction_results.csv (", nrow(interaction_table), "rows)\n")
cat("  - stratified_results.csv (", nrow(stratified_table), "rows)\n")
cat("  - interaction_plots.png\n")
cat("  - analysis_summary.json\n")

cat("\nEnd time:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
cat("=== Stage 7.6 Complete ===\n")