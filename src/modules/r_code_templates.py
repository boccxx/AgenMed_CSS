#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R Code Templates Module - Unified management of all R code templates"""

import os
from pathlib import Path
from typing import Optional


class RCodeTemplates:
    """R Code Template Manager
    
    Provides standardized R code templates to avoid sending large amounts of template code to LLM each time.
    Uses reference approach rather than directly sending complete code to optimize token usage.
    """
    
    @staticmethod
    def mice_export_template() -> str:
        """
        MICE imputation export template
        Exports all imputed datasets as CSV files for downstream use
        """
        return '''
# === MICE Dataset Export (SAP-CONDITIONAL) ===
# Use this branch only when the final SAP specifies MICE.
# Reason: Subsequent stages run in separate R processes and cannot load .rds objects.
# If no MICE object exists, the non-MICE branch still writes main_output.csv.

if (exists("imp") && inherits(imp, "mids")) {
  m_total <- imp$m
  
  cat("Exporting", m_total, "imputed datasets as CSV...\\n")
  for (i in 1:m_total) {
    completed_data <- mice::complete(imp, action = i)
    output_file <- paste0("imputed_data_", i, ".csv")
    write.csv(completed_data, output_file, row.names = FALSE, na = "")
    if (!file.exists(output_file)) stop(paste("ERROR: Failed to write", output_file))
  }
  
  # Overwrite main_output.csv with first imputed dataset (for immediate downstream use)
  write.csv(mice::complete(imp, 1), "main_output.csv", row.names = FALSE, na = "")
  if (!file.exists("main_output.csv")) stop("ERROR: Failed to write main_output.csv")
  
  cat("All imputed datasets exported successfully\\n")
  cat("  - imputed_data_1.csv to imputed_data_", m_total, ".csv\\n")
  cat("  - main_output.csv (= imputed_data_1.csv)\\n")
} else {
  cat("No valid MICE object detected; using non-MICE export branch for main_output.csv\\n")
  if (exists("data") && is.data.frame(data)) {
    write.csv(data, "main_output.csv", row.names = FALSE, na = "")
    if (!file.exists("main_output.csv")) stop("ERROR: Failed to write main_output.csv")
    cat("main_output.csv saved (analysis-ready data without MICE export)\\n")
  } else {
    stop("ERROR: Neither MICE object nor data object found; cannot write main_output.csv")
  }
}
'''
    
    @staticmethod
    def missing_data_visualization_template() -> str:
        return '''
cat("Step 1: Missing data pattern analysis using md.pattern()\\n")
library(mice)
library(VIM)

missing_pattern <- md.pattern(data, plot = FALSE)
missing_pattern_df <- as.data.frame(missing_pattern)
missing_pattern_df$Variables <- rownames(missing_pattern_df)
missing_pattern_df <- missing_pattern_df[, c("Variables", setdiff(names(missing_pattern_df), "Variables"))]

write.csv(missing_pattern_df, "missing_data_pattern.csv", row.names = FALSE, na = "")
cat("Missing data pattern table saved: missing_data_pattern.csv\\n")

cat("Step 2: Generate missing data aggregation plot using VIM::aggr()\\n")
n_vars <- ncol(data)
cex_axis <- ifelse(n_vars > 15, 0.5, ifelse(n_vars > 10, 0.6, 0.7))
vars_with_missing <- names(data)[sapply(data, function(x) sum(is.na(x)) > 0)]
if(length(vars_with_missing) == 0) {
  cat("No missing data found, skipping aggr plot\\n")
} else {
  png("missing_data_aggr_plot.png", width = 12, height = 8, units = "in", res = 300, bg = "white")
  tryCatch({
    aggr_result <- aggr(data, col = c("#4E79A7", "#E15759"), numbers = TRUE, 
                        sortVars = TRUE, labels = names(data), 
                        cex.axis = cex_axis, gap = 2, 
                        ylab = c("Missing Data Proportion", "Variable Combinations"))
    if(inherits(aggr_result, "aggr")) {
      print(aggr_result)
    }
  }, error = function(e) {
    cat("Warning: aggr() failed, using alternative visualization:", e$message, "\\n")
    plot.new()
    text(0.5, 0.5, paste("Missing Data Aggregation Plot\\nError:", e$message), cex = 1.2)
  })
  dev.off()
  if (!file.exists("missing_data_aggr_plot.png")) stop("ERROR: Failed to save aggr plot")
  cat("Missing data aggregation plot saved: missing_data_aggr_plot.png\\n")
}

cat("Step 3: Generate missing data matrix plot using VIM::matrixplot()\\n")
if(sum(is.na(data)) > 0) {
  png("missing_data_matrixplot.png", width = 12, height = 8, units = "in", res = 300, bg = "white")
  tryCatch({
    matrix_result <- matrixplot(data, col = c("#4E79A7", "#E15759", "#F28E2B"), 
                               main = "Missing Data Matrix Plot",
                               cex.axis = cex_axis, interactive = FALSE)
    if(!is.null(matrix_result)) {
      print(matrix_result)
    }
  }, error = function(e) {
    cat("Warning: matrixplot() failed, using alternative visualization:", e$message, "\\n")
    plot.new()
    text(0.5, 0.5, paste("Missing Data Matrix Plot\\nError:", e$message), cex = 1.2)
  })
  dev.off()
  if (!file.exists("missing_data_matrixplot.png")) stop("ERROR: Failed to save matrixplot")
  cat("Missing data matrix plot saved: missing_data_matrixplot.png\\n")
} else {
  cat("Skipping missing data matrix plot: No missing values detected.\\n")
}
'''
    
    @staticmethod
    def mice_convergence_template() -> str:
        return '''
cat("Step 1: Identify variables with imputation for convergence plots\\n")
vars_imputed <- names(imp$method)[imp$method != ""]
if(length(vars_imputed) == 0) {
  cat("No variables were imputed, skipping convergence plots\\n")
} else {
  n_vars <- length(vars_imputed)
  n_plots <- min(n_vars * 2, 16)
  
  if(n_plots <= 4) {
    layout_dim <- c(2, 2)
  } else if(n_plots <= 6) {
    layout_dim <- c(3, 2)
  } else if(n_plots <= 9) {
    layout_dim <- c(3, 3)
  } else if(n_plots <= 12) {
    layout_dim <- c(4, 3)
  } else {
    layout_dim <- c(4, 4)
  }
  
  cat("Generating convergence trace plots (", n_vars, "variables, layout", paste(layout_dim, collapse="x"), ")...\\n")
  png("mice_convergence_trace_plots.png", width = 12, height = 8, units = "in", res = 300, bg = "white")
  tryCatch({
    plot_result <- plot(imp, layout = layout_dim)
    if(!is.null(plot_result)) {
      print(plot_result)
    }
  }, error = function(e) {
    cat("Warning: plot(imp) failed, trying alternative:", e$message, "\\n")
    tryCatch({
      plot(imp)
    }, error = function(e2) {
      plot.new()
      text(0.5, 0.5, paste("MICE Convergence Plots\\nError:", e2$message), cex = 1.2)
    })
  })
  dev.off()
  
  if (!file.exists("mice_convergence_trace_plots.png")) {
    stop("ERROR: Convergence trace plots not created")
  }
  cat("Convergence trace plots saved: mice_convergence_trace_plots.png\\n")
}
'''
    
    @staticmethod
    def mice_density_template() -> str:
        return '''
cat("Step 1: Identify variables suitable for density plots\\n")
vars_imputed <- names(imp$method)[imp$method != ""]
vars_numeric <- vars_imputed[sapply(vars_imputed, function(v) {
  if(v %in% names(data)) {
    is.numeric(data[[v]]) && sum(!is.na(data[[v]])) >= 10
  } else {
    FALSE
  }
})]

if(length(vars_numeric) == 0) {
  cat("No suitable variables for density plots, generating alternative visualization\\n")
  missing_summary <- data.frame(
    Variable = names(data),
    Missing_Count = sapply(data, function(x) sum(is.na(x))),
    Missing_Rate = round(sapply(data, function(x) sum(is.na(x))/length(x)*100, 2), 2)
  )
  missing_summary <- missing_summary[missing_summary$Missing_Count > 0, ]
  
  if(nrow(missing_summary) > 0) {
    library(ggplot2)
    png("mice_density_plots.png", width = 12, height = 6, units = "in", res = 300, bg = "white")
    p <- ggplot(missing_summary, aes(x = reorder(Variable, Missing_Rate), y = Missing_Rate)) +
      geom_bar(stat = "identity", fill = "#4E79A7") +
      coord_flip() +
      labs(title = "Missing Data Rate by Variable", 
           x = "Variable", 
           y = "Missing Rate (%)") +
      theme_minimal(base_size = 12) +
      theme(plot.title = element_text(hjust = 0.5, face = "bold"))
    print(p)
    dev.off()
    cat("Alternative missing rate plot saved: mice_density_plots.png\\n")
  } else {
    png("mice_density_plots.png", width = 12, height = 6, units = "in", res = 300, bg = "white")
    plot.new()
    text(0.5, 0.5, "No missing data or insufficient data for density plots", cex = 1.5)
    dev.off()
    cat("Placeholder plot saved: mice_density_plots.png\\n")
  }
} else {
  vars_for_density <- vars_numeric[1:min(6, length(vars_numeric))]
  cat("Generating density plots for", length(vars_for_density), "variables...\\n")
  
  png("mice_density_plots.png", width = 12, height = 6, units = "in", res = 300, bg = "white")
  tryCatch({
    density_formula <- as.formula(paste("~", paste(vars_for_density, collapse = " + ")))
    density_plot <- densityplot(imp, density_formula)
    print(density_plot)
  }, error = function(e) {
    cat("Density plot generation failed:", e$message, "\\n")
    missing_summary <- data.frame(
      Variable = vars_for_density,
      Missing_Count = sapply(vars_for_density, function(v) sum(is.na(data[[v]]))),
      Missing_Rate = round(sapply(vars_for_density, function(v) sum(is.na(data[[v]]))/length(data[[v]])*100, 2), 2)
    )
    library(ggplot2)
    p <- ggplot(missing_summary, aes(x = reorder(Variable, Missing_Rate), y = Missing_Rate)) +
      geom_bar(stat = "identity", fill = "#4E79A7") +
      coord_flip() +
      labs(title = "Missing Data Rate by Variable", 
           x = "Variable", 
           y = "Missing Rate (%)") +
      theme_minimal(base_size = 12) +
      theme(plot.title = element_text(hjust = 0.5, face = "bold"))
    print(p)
  })
  dev.off()
  
  if (!file.exists("mice_density_plots.png")) {
    stop("ERROR: Density plots not created")
  }
  cat("Density plots saved: mice_density_plots.png\\n")
}
'''
    
    @staticmethod
    def font_setup_template() -> str:
        """
        Unified graphics environment setup template (approximately 70 lines)
        
        Handles cross-platform font settings and uniformly configures beautification parameters for all graphics systems:
        - ggplot2: Modern theme
        - lattice: mice package graphics beautification
        - base R: Traditional graphics optimization
        """
        return '''# === Unified Graphics Environment Setup ===
library(ggplot2)

# Unified color palette (Tableau 10 colors)
plot_colors <- c("#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", 
                 "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC")

tryCatch({
  selected_font <- ''
  
  # 2. ggplot2 theme setup (modern graphics)
  theme_set(theme_minimal(base_size = 12) + 
            theme(text = element_text(family = selected_font),
                  plot.title = element_text(hjust = 0.5, size = 14, face = "bold"),
                  axis.text = element_text(size = 10),
                  axis.title = element_text(size = 11),
                  legend.position = "bottom",
                  legend.text = element_text(size = 10),
                  legend.title = element_text(size = 11),
                  strip.text = element_text(size = 10),
                  panel.grid.minor = element_blank(),
                  panel.border = element_blank()))
  
  # 3. lattice graphics setup (for mice, VIM packages, etc.)
  if(requireNamespace("lattice", quietly = TRUE)) {
    lattice::trellis.par.set(list(
      fontsize = list(text = 11, points = 9),
      superpose.line = list(col = plot_colors, lwd = 2),
      superpose.symbol = list(col = plot_colors, pch = 19, cex = 0.8),
      strip.background = list(col = "gray92"),
      strip.border = list(col = "gray70"),
      plot.line = list(col = plot_colors[1], lwd = 1.5),
      plot.symbol = list(col = plot_colors[1], pch = 19, cex = 0.8),
      box.rectangle = list(col = plot_colors[1]),
      box.umbrella = list(col = plot_colors[1], lty = 1),
      add.line = list(col = "gray50", lty = 2),
      reference.line = list(col = "gray70", lty = 2)
    ))
  }
  
  # 4. base R graphics parameters (traditional graphics optimization)
  par(las = 1,                    # Horizontal labels
      cex.lab = 1.1,              # Axis label size
      cex.axis = 0.95,            # Axis tick size
      cex.main = 1.2,             # Main title size
      col.axis = "gray20",        # Axis color
      col.lab = "gray20",         # Label color
      col.main = "black",         # Main title color
      fg = "gray50",              # Foreground color
      bty = "l")                  # Border style (L-shape)
  
  cat('Graphics environment setup successful\\n')
  cat('   - ggplot2 theme: theme_minimal (English labels)\\n')
  cat('   - lattice colors: Tableau 10\\n')
  cat('   - base R parameters: optimized\\n')
}, error = function(e) {
  # Fallback: use system default settings
  theme_set(theme_minimal(base_size = 12))
  if(requireNamespace("lattice", quietly = TRUE)) {
    lattice::trellis.par.set(list(
      superpose.line = list(lwd = 2),
      superpose.symbol = list(pch = 19, cex = 0.8)
    ))
  }
  cat('Font setup failed, using default theme\\n')
})
'''
    
    @staticmethod
    def data_reading_template(
        data_path: str,
        has_summary: bool = False,
        summary_path: Optional[str] = None
    ) -> str:
        """
        Data reading template (approximately 30 lines, excluding font setup)
        
        Args:
            data_path: Data file path
            has_summary: Whether there is a previous stage summary
            summary_path: Previous summary file path
            
        Returns:
            Data reading R code
        """
        base_code = f'''# === Data Reading and Previous Stage Information Retrieval ===

# 1. Read data (using absolute path for reliability)
if (file.exists("{data_path}")) {{
  data <- read.csv("{data_path}", stringsAsFactors = FALSE)
  cat("Successfully read data:", "{data_path}", "\\n")
  cat("Data dimensions:", nrow(data), "rows x", ncol(data), "columns\\n")
}} else {{
  stop("Error: Data file does not exist: {data_path}\\nPlease check path configuration or whether previous stage executed successfully")
}}

# 2. Basic data cleaning
library(dplyr)
library(tidyr)
data <- data %>%
  mutate_all(~ ifelse(. == "" | . == "NA", NA, .))
'''
        
        if has_summary and summary_path:
            summary_code = f'''
# 3. Read previous stage decision information
if (file.exists("{summary_path}")) {{
  prev_summary <- jsonlite::fromJSON("{summary_path}")
}} else {{
  prev_summary <- NULL
}}

# 4. Weight variable detection and preservation
weight_var_name <- NULL
if(!is.null(prev_summary) && !is.null(prev_summary$weight_detection)) {{
  if(prev_summary$weight_detection$usable_weight && 
     !is.null(prev_summary$weight_detection$weight_variable)) {{
    weight_var_name <- prev_summary$weight_detection$weight_variable
    if(weight_var_name %in% names(data)) {{
      cat("Using detected weight variable from previous stage:", weight_var_name, "\\n")
    }} else {{
      weight_var_name <- NULL
    }}
  }}
}}

if(is.null(weight_var_name)) {{
  weight_candidates <- c("Sampling_Weight", "survey_weight", "weight", "weights", "wgt")
  for(candidate in weight_candidates) {{
    if(candidate %in% names(data)) {{
      unique_vals <- unique(data[[candidate]][!is.na(data[[candidate]])])
      if(length(unique_vals) > 1 && all(unique_vals > 0)) {{
        weight_var_name <- candidate
        cat("Found weight variable:", weight_var_name, "\\n")
        break
      }}
    }}
  }}
}}

if(is.null(weight_var_name)) {{
  fuzzy_matches <- names(data)[grepl("weight", names(data), ignore.case=TRUE)]
  if(length(fuzzy_matches) > 0) {{
    for(candidate in fuzzy_matches) {{
      unique_vals <- unique(data[[candidate]][!is.na(data[[candidate]])])
      if(length(unique_vals) > 1 && all(unique_vals > 0)) {{
        weight_var_name <- candidate
        cat("Found weight variable (fuzzy match):", weight_var_name, "\\n")
        break
      }}
    }}
  }}
}}

if(is.null(weight_var_name)) {{
  if(!"survey_weight" %in% names(data)) {{
    data$survey_weight <- 1
    cat("No usable weight variable found, creating placeholder survey_weight=1\\n")
  }} else {{
    cat("Using existing survey_weight variable in data\\n")
  }}
}} else {{
  cat("Weight variable preserved:", weight_var_name, "\\n")
}}

# 5. Design variable level preservation
design_vars_to_preserve <- c()
if(!is.null(prev_summary) && !is.null(prev_summary$design)) {{
  if(!is.null(prev_summary$design$strata_variable) && 
     prev_summary$design$strata_variable != "" && 
     !is.null(prev_summary$design$strata_variable)) {{
    design_vars_to_preserve <- c(design_vars_to_preserve, prev_summary$design$strata_variable)
  }}
  if(!is.null(prev_summary$design$psu_variable) && 
     prev_summary$design$psu_variable != "" && 
     !is.null(prev_summary$design$psu_variable)) {{
    design_vars_to_preserve <- c(design_vars_to_preserve, prev_summary$design$psu_variable)
  }}
}}

for(var in design_vars_to_preserve) {{
  if(var %in% names(data)) {{
    levels_before <- unique(data[[var]][!is.na(data[[var]])])
    cat("Design variable", var, "levels:", paste(levels_before, collapse=", "), 
        "(n=", length(levels_before), ")\\n")
    
    if(length(levels_before) < 2) {{
      warning("WARNING: Design variable ", var, " has < 2 levels. Check data filtering!")
    }}
    
    data[[var]] <- factor(data[[var]], levels = levels_before)
    cat("  Preserved", length(levels(data[[var]])), "levels for", var, "\\n")
  }}
}}
'''
            return base_code + summary_code
        else:
            no_summary_code = '''
# 3. No previous stage information
prev_summary <- NULL

# 4. Weight variable detection
weight_var_name <- NULL
weight_candidates <- c("Sampling_Weight", "survey_weight", "weight", "weights", "wgt")
for(candidate in weight_candidates) {
  if(candidate %in% names(data)) {
    unique_vals <- unique(data[[candidate]][!is.na(data[[candidate]])])
    if(length(unique_vals) > 1 && all(unique_vals > 0)) {
      weight_var_name <- candidate
      cat("Found weight variable:", weight_var_name, "\\n")
      break
    }
  }
}

if(is.null(weight_var_name)) {
  fuzzy_matches <- names(data)[grepl("weight", names(data), ignore.case=TRUE)]
  if(length(fuzzy_matches) > 0) {
    for(candidate in fuzzy_matches) {
      unique_vals <- unique(data[[candidate]][!is.na(data[[candidate]])])
      if(length(unique_vals) > 1 && all(unique_vals > 0)) {
        weight_var_name <- candidate
        cat("Found weight variable (fuzzy match):", weight_var_name, "\\n")
        break
      }
    }
  }
}

if(is.null(weight_var_name)) {
  if(!"survey_weight" %in% names(data)) {
    data$survey_weight <- 1
    cat("No usable weight variable found, creating placeholder survey_weight=1\\n")
  } else {
    cat("Using existing survey_weight variable in data\\n")
  }
} else {
  cat("Weight variable preserved:", weight_var_name, "\\n")
}
'''
            return base_code + no_summary_code
    
    @staticmethod
    def output_template(section: str) -> str:
        """
        Output saving template (approximately 40 lines)
        
        Args:
            section: Stage number (e.g., "7.2")
            
        Returns:
            Output saving R code
        """
        return f'''# === Final Data Quality Validation and Standardized Output Saving ===

# 1. Final data quality validation
cat("\\n=== Final Data Quality Validation ===\\n")
cat("Final data dimensions:", nrow(data), "rows x", ncol(data), "columns\\n")

# Validate factor variable levels
factor_vars <- sapply(data, is.factor)
if(any(factor_vars)) {{
  cat("\\nFactor variable level validation:\\n")
  for(var in names(data)[factor_vars]) {{
    levels_count <- length(levels(data[[var]]))
    actual_count <- length(unique(data[[var]][!is.na(data[[var]])]))
    cat(var, ": defined", levels_count, "levels, actual", actual_count, "unique values\\n")
    if(actual_count <= 10) {{
      cat("  Actual values:", paste(unique(data[[var]][!is.na(data[[var]])]), collapse=", "), "\\n")
    }}
  }}
}}

# Validate missing values
total_missing <- sum(is.na(data))
total_cells <- nrow(data) * ncol(data)
missing_percent <- round(100 * total_missing / total_cells, 2)
cat("\\nFinal missing status:", total_missing, "missing values, accounting for", missing_percent, "%\\n")

# 2. Save main data file (for next stage use)
write.csv(data, "main_output.csv", row.names = FALSE)
cat("\\nMain data file saved: main_output.csv\\n")

# 3. Generate and save analysis findings summary (focus on key decisions affecting downstream)
analysis_summary <- list(
  stage = "{section}",
  timestamp = as.character(Sys.time()),
  data_dimensions = list(rows = nrow(data), cols = ncol(data)),
  
  # Core: Key decisions affecting downstream analysis (concise and clear)
  critical_decisions = c(
    "**MUST FILL**: List key decisions affecting downstream stages"
  ),
  
  # Core: Statistical methods execution summary (for validation)
  statistical_methods_summary = "**MUST FILL**: Names of statistical methods actually executed in this stage and main R packages",
  
  # Optional: Next stage specific requirements
  next_stage_requirements = list(
    variables_to_use = "Recommended variables to use",
    methods_to_apply = "Recommended methods"
  )
)

# Save summary
jsonlite::write_json(analysis_summary, "analysis_summary.json", auto_unbox = TRUE, pretty = TRUE)
cat("Analysis summary saved: analysis_summary.json\\n")
'''
    
    @staticmethod
    def data_transfer_guarantee_template() -> str:
        """
        Data transfer guarantee mechanism template (approximately 50 lines)
        
        Ensures that even if subsequent analysis fails, key output files can be generated to guarantee data transfer chain is not interrupted.
        This template should be used at the end of the script as the last safety net.
        
        Returns:
            Data transfer guarantee R code
        """
        return '''# === Data Transfer Guarantee Mechanism (Last Safety Net) ===

ensure_output_files <- function(data, summary_list = NULL) {
  """Force write key files to ensure data transfer"""
  
  # 1. Write main_output.csv
  tryCatch({
    write.csv(data, "main_output.csv", row.names = FALSE, fileEncoding = "UTF-8")
    cat("✓ main_output.csv written successfully\\n")
  }, error = function(e) {
    cat("✗ main_output.csv write failed:", e$message, "\\n")
    # Try to write simplified version
    tryCatch({
      write.csv(head(data, 100), "main_output.csv", row.names = FALSE)
      cat("✓ main_output.csv simplified version written successfully\\n")
    }, error = function(e2) {
      cat("✗✗ main_output.csv completely failed\\n")
    })
  })
  
  # 2. Write analysis_summary.json
  if (!is.null(summary_list)) {
    tryCatch({
      jsonlite::write_json(summary_list, "analysis_summary.json", 
                          pretty = TRUE, auto_unbox = TRUE)
      cat("✓ analysis_summary.json written successfully\\n")
    }, error = function(e) {
      cat("✗ analysis_summary.json write failed:", e$message, "\\n")
      # Write minimal version
      tryCatch({
        minimal_summary <- list(
          stage = if(is.null(summary_list$stage)) "unknown" else summary_list$stage,
          method = if(is.null(summary_list$method)) "unknown" else summary_list$method,
          status = "partial_success",
          note = "Some analysis failed, but data has been transferred"
        )
        jsonlite::write_json(minimal_summary, "analysis_summary.json", 
                            pretty = TRUE, auto_unbox = TRUE)
        cat("✓ analysis_summary.json minimal version written successfully\\n")
      }, error = function(e2) {
        cat("✗✗ analysis_summary.json completely failed\\n")
      })
    })
  }
}

# Must call at end of script:
# ensure_output_files(data, analysis_summary)
'''
    
    @staticmethod
    def statistical_validation_template() -> str:
        return '''# === Statistical Result Validation ===

validate_output_quality <- function(result_df, stage_name = "unknown", 
                                   check_columns = NULL) {
  issues <- c()
  warnings <- c()
  
  if(is.null(result_df) || nrow(result_df) == 0) {
    return(list(valid = FALSE, issues = "Empty result dataframe", warnings = NULL))
  }
  
  if(is.null(check_columns)) {
    numeric_cols <- names(result_df)[sapply(result_df, is.numeric)]
  } else {
    numeric_cols <- check_columns
  }
  
  for(col in numeric_cols) {
    if(!col %in% names(result_df)) next
    
    na_count <- sum(is.na(result_df[[col]]))
    if(na_count > 0) {
      warnings <- c(warnings, sprintf("%s: %d NA values in column '%s'", 
                                     stage_name, na_count, col))
    }
    
    inf_count <- sum(is.infinite(result_df[[col]]))
    if(inf_count > 0) {
      issues <- c(issues, sprintf("%s: %d Inf values in column '%s' (separation issue)", 
                                 stage_name, inf_count, col))
    }
    
    if(grepl("OR|PR|HR|RR", col, ignore.case = TRUE)) {
      extreme_high <- sum(result_df[[col]] > 1000, na.rm = TRUE)
      extreme_low <- sum(result_df[[col]] < 0.001 & result_df[[col]] > 0, na.rm = TRUE)
      
      if(extreme_high > 0) {
        issues <- c(issues, sprintf("%s: %d extreme high values (>1000) in '%s'", 
                                   stage_name, extreme_high, col))
      }
      if(extreme_low > 0) {
        warnings <- c(warnings, sprintf("%s: %d extreme low values (<0.001) in '%s'", 
                                       stage_name, extreme_low, col))
      }
    }
    
    if(grepl("p.value|p_value|pval", col, ignore.case = TRUE)) {
      invalid_p <- sum(result_df[[col]] < 0 | result_df[[col]] > 1, na.rm = TRUE)
      if(invalid_p > 0) {
        issues <- c(issues, sprintf("%s: %d invalid p-values (<0 or >1) in '%s'", 
                                   stage_name, invalid_p, col))
      }
    }
  }
  
  if(length(issues) > 0) {
    cat("\n=== OUTPUT QUALITY ISSUES DETECTED ===\n")
    for(issue in issues) cat("ERROR:", issue, "\n")
    for(warn in warnings) cat("WARNING:", warn, "\n")
    return(list(valid = FALSE, issues = issues, warnings = warnings))
  } else if(length(warnings) > 0) {
    cat("\n=== OUTPUT QUALITY WARNINGS ===\n")
    for(warn in warnings) cat("WARNING:", warn, "\n")
    return(list(valid = TRUE, issues = NULL, warnings = warnings))
  } else {
    cat("\nOutput quality check passed\n")
    return(list(valid = TRUE, issues = NULL, warnings = NULL))
  }
}

check_sample_size_consistency <- function(data, expected_n = NULL, stage_name = "unknown") {
  actual_n <- nrow(data)
  
  if(!is.null(expected_n) && actual_n != expected_n) {
    cat(sprintf("WARNING: Sample size inconsistency at %s\\n", stage_name))
    cat(sprintf("  Expected: %d, Actual: %d, Difference: %d\\n", 
                expected_n, actual_n, actual_n - expected_n))
    return(FALSE)
  }
  
  cat(sprintf("Sample size at %s: n = %d\\n", stage_name, actual_n))
  return(TRUE)
}

check_weight_status <- function(data, weight_var = "weight") {
  if(!weight_var %in% names(data)) {
    cat(sprintf("INFO: No weight variable '%s' found\\n", weight_var))
    return("no_weight")
  }
  
  unique_weights <- unique(data[[weight_var]])
  
  if(length(unique_weights) == 1 && unique_weights[1] == 1) {
    cat("WARNING: Placeholder weights detected (all weights = 1)\\n")
    cat("  Analysis is effectively UNWEIGHTED\\n")
    cat("  Do NOT claim 'survey-weighted' or 'population representative'\\n")
    return("placeholder")
  } else {
    cat(sprintf("INFO: %d unique weight values detected\\n", length(unique_weights)))
    return("actual_weights")
  }
}
'''
    
    @staticmethod
    def get_template_reference(template_name: str) -> str:
        """
        Get template reference description (for sending to LLM)
        
        Args:
            template_name: Template name ('font_setup', 'data_reading', 'output')
            
        Returns:
            Template reference description text
        """
        references = {
            'font_setup': '''**Graphics Environment Setup Template**:
- Configure ggplot2 theme with English labels
- Set unified color palette (Tableau 10)
- Optimize lattice and base R graphics parameters
- Use default system fonts for cross-platform compatibility''',
            
            'data_reading': '''**Data Reading Template**:
- Read CSV data file (supports fallback file names)
- Basic data cleaning (empty value handling)
- Intelligently create survey_weight variable (if not exists)
- Optional: Read previous stage's analysis_summary.json''',
            
            'output': '''**Standardized Output Template**:
- Required: Save main_output.csv (for next stage use)
- Required: Save analysis_summary.json (record key decisions)
- Data quality validation (dimensions, factor levels, missing rate)
- analysis_summary must include:
  * critical_decisions: List of key decisions affecting downstream
  * statistical_methods_summary: Statistical methods executed in this stage
  * next_stage_requirements: Recommendations for next stage (optional)''',
            
            'data_transfer': '''**Data Transfer Guarantee Template** (required):
- Call ensure_output_files(data, analysis_summary) at end of script
- Ensures key files can be generated even if analysis fails
- Includes degradation strategy: Full version → Simplified version → Minimal version
- Guarantees data transfer chain is not interrupted''',
            
            'image_generation': '''**Image Generation Template**:
- create_standard_plot() standardized image generation
- create_heatmap() heatmap generation
- create_distribution_plot() distribution plot generation
- Unified size, resolution, and font settings''',
            
            'statistical_validation': '''**Statistical Validation Template**:
- validate_output_quality(): Check NA/Inf/extreme values in result tables
- check_sample_size_consistency(): Track n across stages
- check_weight_status(): Verify if weights are placeholder or actual
- Auto-detect separation issues (OR/PR > 1000)
- Validate p-value ranges (0 to 1)'''
        }
        
        return references.get(template_name, f"Unknown template: {template_name}")
    
    @staticmethod
    def tableone_template() -> str:
        return '''
# === Table 1 Generation with Normality Testing ===
library(tableone)
library(survey)

cat("Step 1: Identify continuous and categorical variables\\n")
numeric_vars <- names(data)[sapply(data, is.numeric)]
factor_vars <- names(data)[sapply(data, is.factor)]
char_vars <- names(data)[sapply(data, is.character)]

cont_vars <- numeric_vars[numeric_vars %in% names(data)]
cont_vars <- cont_vars[!cont_vars %in% c("Sampling_Weight", "weight", "survey_weight", "wgt")]
cont_vars <- cont_vars[sapply(cont_vars, function(v) length(unique(data[[v]][!is.na(data[[v]])])) > 10)]

cat_vars <- unique(c(factor_vars, char_vars))
cat_vars <- cat_vars[cat_vars %in% names(data)]
cat_vars <- cat_vars[sapply(cat_vars, function(v) length(unique(data[[v]][!is.na(data[[v]])])) <= 20)]

numeric_cat_candidates <- numeric_vars[numeric_vars %in% names(data) & 
                                       !numeric_vars %in% cont_vars & 
                                       !numeric_vars %in% c("Sampling_Weight", "weight", "survey_weight", "wgt")]
numeric_cat_vars <- numeric_cat_candidates[sapply(numeric_cat_candidates, function(v) {
  n_unique <- length(unique(data[[v]][!is.na(data[[v]])]))
  n_unique > 1 && n_unique <= 20
})]

if(length(numeric_cat_vars) > 0) {
  cat("Converting numeric categorical variables to factor:", paste(numeric_cat_vars, collapse=", "), "\\n")
  for(v in numeric_cat_vars) {
    data[[v]] <- factor(data[[v]], levels = sort(unique(data[[v]][!is.na(data[[v]])])))
  }
  cat_vars <- unique(c(cat_vars, numeric_cat_vars))
}

for(v in cat_vars) {
  if(is.character(data[[v]])) {
    data[[v]] <- factor(data[[v]], levels = unique(data[[v]][!is.na(data[[v]])]))
  }
}

strata_var <- NULL
if(exists("prev_summary") && !is.null(prev_summary$exposure)) {
  if(!is.null(prev_summary$exposure$derived_group)) {
    strata_var <- prev_summary$exposure$derived_group
  } else if(!is.null(prev_summary$exposure$primary_exposure)) {
    strata_var <- prev_summary$exposure$primary_exposure
  }
}

if(is.null(strata_var) || !strata_var %in% names(data)) {
  stop("Error: Stratification variable not found. Check exposure definition in previous stage summary.")
}

cat("Continuous variables:", paste(cont_vars, collapse=", "), "\\n")
cat("Categorical variables:", paste(cat_vars, collapse=", "), "\\n")
cat("Stratification variable:", strata_var, "\\n")

cat("Step 2: Normality testing for continuous variables\\n")
normality_results <- list()
nonnormal_vars <- c()

for(var in cont_vars) {
  if(!var %in% names(data)) next
  
  test_results <- by(data[[var]], data[[strata_var]], function(x) {
    x_clean <- x[!is.na(x)]
    if(length(x_clean) < 3) return(NA)
    if(length(x_clean) > 5000) x_clean <- sample(x_clean, 5000)
    tryCatch(shapiro.test(x_clean)$p.value, error=function(e) NA)
  })
  
  p_values <- unlist(test_results)
  is_normal <- all(!is.na(p_values)) && all(p_values > 0.05)
  
  normality_results[[var]] <- list(
    p_values = p_values,
    is_normal = is_normal
  )
  
  if(!is_normal) {
    nonnormal_vars <- c(nonnormal_vars, var)
    cat("  ", var, ": non-normal (p-values:", paste(round(p_values, 3), collapse=", "), ")\\n")
  } else {
    cat("  ", var, ": normal (p-values:", paste(round(p_values, 3), collapse=", "), ")\\n")
  }
}

cat("Non-normal variables:", paste(nonnormal_vars, collapse=", "), "\\n")

cat("Step 3: Create survey design if weights available\\n")
weight_var <- NULL
if(exists("prev_summary") && !is.null(prev_summary$weight_detection)) {
  if(prev_summary$weight_detection$usable_weight) {
    weight_var <- prev_summary$weight_detection$weight_variable
    cat("Using weight variable:", weight_var, "\\n")
  }
}

if(!is.null(weight_var) && weight_var %in% names(data)) {
  strata_design <- NULL
  if(exists("prev_summary") && !is.null(prev_summary$design$strata_variable)) {
    strata_var_design <- prev_summary$design$strata_variable
    if(strata_var_design %in% names(data)) {
      strata_design <- as.formula(paste("~", strata_var_design))
    }
  }
  
  if(!is.null(strata_design)) {
    design <- svydesign(ids=~1, strata=strata_design, weights=as.formula(paste("~", weight_var)), data=data)
  } else {
    design <- svydesign(ids=~1, weights=as.formula(paste("~", weight_var)), data=data)
  }
  
  cat("Step 4: Generate Table 1 using svyCreateTableOne\\n")
  tab1 <- svyCreateTableOne(
    vars = c(cont_vars, cat_vars),
    strata = strata_var,
    data = design,
    factorVars = cat_vars,
    test = FALSE,
    smd = TRUE
  )
} else {
  cat("Step 4: Generate Table 1 using CreateTableOne (unweighted)\\n")
  tab1 <- CreateTableOne(
    vars = c(cont_vars, cat_vars),
    strata = strata_var,
    data = data,
    factorVars = cat_vars,
    test = FALSE,
    smd = TRUE
  )
}

cat("Step 5: Export Table 1 to CSV\\n")
tab1_print <- print(tab1, 
                    nonnormal = nonnormal_vars,
                    contDigits = 2,
                    catDigits = 1,
                    smd = TRUE,
                    showAllLevels = TRUE,
                    printToggle = FALSE)

tab1_df <- as.data.frame(tab1_print)
write.csv(tab1_df, "table1_weighted_baseline.csv", row.names = TRUE)

var_dict <- data.frame(
  variable = c(cont_vars, cat_vars),
  type = c(rep("continuous", length(cont_vars)), rep("categorical", length(cat_vars))),
  rule = c(
    ifelse(cont_vars %in% nonnormal_vars, "Weighted median [IQR]", "Weighted mean (SD)"),
    rep("Weighted estimated N and %", length(cat_vars))
  )
)
write.csv(var_dict, "table1_variable_dictionary.csv", row.names = FALSE)

cat("Table 1 generation completed\\n")
cat("  - Non-normal variables (using median [IQR]):", paste(nonnormal_vars, collapse=", "), "\\n")
cat("  - Normal variables (using mean (SD)):", 
    paste(setdiff(cont_vars, nonnormal_vars), collapse=", "), "\\n")
'''

    @staticmethod
    def correlation_matrix_template() -> str:
        return '''
cat("Step 1: Identify continuous variables for correlation matrix\\n")
numeric_vars <- names(data)[sapply(data, is.numeric)]
cont_vars <- numeric_vars[!numeric_vars %in% c("Sampling_Weight", "weight", "survey_weight", "wgt", ".imp", ".id")]
cont_vars <- cont_vars[sapply(cont_vars, function(v) {
  n_unique <- length(unique(data[[v]][!is.na(data[[v]])]))
  n_unique > 10
})]

if(length(cont_vars) < 2) {
  cat("WARNING: Less than 2 continuous variables found, skipping correlation matrix\\n")
} else {
  cat("Continuous variables for correlation:", paste(cont_vars, collapse=", "), "\\n")
  
  cat("Step 2: Check for survey weights\\n")
  use_weighted <- FALSE
  weight_var <- NULL
  svy_design_obj <- NULL
  
  if(exists("prev_summary") && !is.null(prev_summary$design)) {
    if(prev_summary$design$usable_weight && !is.null(prev_summary$design$weight_variable)) {
      weight_var <- prev_summary$design$weight_variable
      if(weight_var %in% names(data)) {
        unique_weights <- length(unique(data[[weight_var]][!is.na(data[[weight_var]])]))
        if(unique_weights > 1 && !all(data[[weight_var]] == 1, na.rm=TRUE)) {
          use_weighted <- TRUE
          if(!is.null(prev_summary$design$strata_variable) && 
             prev_summary$design$strata_variable != "" && 
             prev_summary$design$strata_variable %in% names(data) &&
             length(unique(data[[prev_summary$design$strata_variable]][!is.na(data[[prev_summary$design$strata_variable]])])) > 1) {
            svy_design_obj <- svydesign(ids = ~1, 
                                       strata = as.formula(paste("~", prev_summary$design$strata_variable)), 
                                       weights = as.formula(paste("~", weight_var)), 
                                       data = data)
          } else {
            svy_design_obj <- svydesign(ids = ~1, 
                                       weights = as.formula(paste("~", weight_var)), 
                                       data = data)
          }
          cat("Using weighted correlation (survey design)\\n")
        }
      }
    }
  }
  
  if(!use_weighted) {
    cat("Using unweighted correlation (no valid survey weights)\\n")
  }
  
  cat("Step 3: Calculate correlation matrix\\n")
  if(use_weighted && !is.null(svy_design_obj)) {
    library(survey)
    cor_formula <- as.formula(paste("~", paste(cont_vars, collapse=" + ")))
    cor_matrix <- svycor(cor_formula, design = svy_design_obj, na.rm = TRUE)
    cor_df <- as.data.frame(cor_matrix)
    method_used <- "Weighted (survey design)"
  } else {
    data_cont <- data[, cont_vars, drop = FALSE]
    data_cont <- data_cont[complete.cases(data_cont), ]
    if(nrow(data_cont) < 2) {
      cat("WARNING: Insufficient complete cases for correlation, skipping\\n")
    } else {
      cor_matrix <- cor(data_cont, use = "complete.obs", method = "pearson")
      cor_df <- as.data.frame(cor_matrix)
      method_used <- "Unweighted (Pearson)"
    }
  }
  
  if(exists("cor_df") && nrow(cor_df) > 0) {
    cat("Step 4: Save correlation matrix table\\n")
    cor_df$Variable <- rownames(cor_df)
    cor_df <- cor_df[, c("Variable", cont_vars)]
    write.csv(cor_df, "correlation_matrix.csv", row.names = FALSE, na = "")
    cat("Correlation matrix saved: correlation_matrix.csv\\n")
    cat("Method:", method_used, "\\n")
    
    cat("Step 5: Generate correlation heatmap\\n")
    library(ggplot2)
    library(reshape2)
    
    cor_long <- melt(cor_matrix, varnames = c("Var1", "Var2"), value.name = "Correlation")
    cor_long$Var1 <- factor(cor_long$Var1, levels = cont_vars)
    cor_long$Var2 <- factor(cor_long$Var2, levels = rev(cont_vars))
    
    p <- ggplot(cor_long, aes(x = Var1, y = Var2, fill = Correlation)) +
      geom_tile(color = "white", linewidth = 0.5) +
      scale_fill_gradient2(low = "#2166AC", mid = "white", high = "#B2182B", 
                          midpoint = 0, limit = c(-1, 1), 
                          name = "Correlation", guide = guide_colorbar(barwidth = 8)) +
      theme_minimal(base_size = 11) +
      theme(
        axis.text.x = element_text(angle = 45, hjust = 1, vjust = 1, size = 9),
        axis.text.y = element_text(size = 9),
        axis.title = element_blank(),
        panel.grid = element_blank(),
        plot.title = element_text(hjust = 0.5, face = "bold", size = 12),
        plot.subtitle = element_text(hjust = 0.5, size = 10),
        legend.position = "bottom"
      ) +
      coord_fixed() +
      labs(
        title = "Correlation Matrix",
        subtitle = method_used
      )
    
    if(nrow(cor_long) <= 100) {
      p <- p + geom_text(aes(label = round(Correlation, 2)), 
                        color = "black", size = 2.5, fontface = "bold")
    }
    
    ggsave("correlation_heatmap.png", plot = p, width = 10, height = 8, dpi = 300, bg = "white")
    cat("Correlation heatmap saved: correlation_heatmap.png\\n")
  }
}
'''
    
    @staticmethod
    def pooled_results_extraction_template() -> str:
        return '''
extract_coefficient_by_levels <- function(pooled_obj, var_name, levels_list, reference_level = NULL) {
  if(is.null(pooled_obj)) return(NULL)
  
  tryCatch({
    coefs <- coef(pooled_obj)
    ci <- confint(pooled_obj)
    coef_summary <- summary(pooled_obj)$coefficients
    
    all_coef_names <- names(coefs)
    
    results <- list()
    
    for(level in levels_list) {
      if(!is.null(reference_level) && level == reference_level) {
        next
      }
      
      level_escaped <- gsub("([.+*?^$(){}|\\[\\]])", "\\\\\\1", level)
      patterns <- c(
        paste0("^", var_name, level_escaped, "$"),
        paste0("^", var_name, level_escaped),
        paste0("^", var_name, ":", level_escaped),
        paste0("^", var_name, "\\.", level_escaped),
        paste0("^", var_name, level_escaped, ":"),
        paste0(var_name, ".*", level_escaped)
      )
      
      matched_name <- NULL
      for(pattern in patterns) {
        matches <- grep(pattern, all_coef_names, value = TRUE)
        if(length(matches) > 0) {
          matched_name <- matches[1]
          break
        }
      }
      
      if(!is.null(matched_name) && matched_name %in% rownames(ci) && matched_name %in% rownames(coef_summary)) {
        p_value_col <- NULL
        se_col <- NULL
        
        available_cols <- colnames(coef_summary)
        if("Pr(>|t|)" %in% available_cols) {
          p_value_col <- "Pr(>|t|)"
        } else if("Pr(>|z|)" %in% available_cols) {
          p_value_col <- "Pr(>|z|)"
        } else if("p.value" %in% available_cols) {
          p_value_col <- "p.value"
        } else if("Pr" %in% available_cols) {
          p_value_col <- "Pr"
        }
        
        if("se" %in% available_cols) {
          se_col <- "se"
        } else if("Std. Error" %in% available_cols) {
          se_col <- "Std. Error"
        } else if("std.error" %in% available_cols) {
          se_col <- "std.error"
        } else if("SE" %in% available_cols) {
          se_col <- "SE"
        }
        
        p_val <- if(!is.null(p_value_col)) coef_summary[matched_name, p_value_col] else NA
        se_val <- if(!is.null(se_col)) coef_summary[matched_name, se_col] else NA
        
        results[[level]] <- list(
          coef_name = matched_name,
          coef = coefs[matched_name],
          ci_lower = ci[matched_name, 1],
          ci_upper = ci[matched_name, 2],
          p_value = p_val,
          se = se_val
        )
      }
    }
    
    if(length(results) == 0) {
      cat("Warning: No coefficients found for", var_name, "with levels:", paste(levels_list, collapse = ", "), "\\n")
      cat("Available coefficient names:", paste(all_coef_names, collapse = ", "), "\\n")
      return(NULL)
    }
    
    return(results)
  }, error = function(e) {
    cat("Error extracting coefficients:", e$message, "\\n")
    return(NULL)
  })
}

extract_interaction_terms <- function(pooled_obj, exposure, moderator) {
  if(is.null(pooled_obj)) return(character(0))
  
  tryCatch({
    coef_names <- names(coef(pooled_obj))
    if(length(coef_names) == 0) {
      coef_names <- rownames(summary(pooled_obj))
    }
    
    patterns <- c(
      paste0("^", exposure, ".*:", moderator),
      paste0("^", exposure, ":", moderator),
      paste0("^", moderator, ".*:", exposure),
      paste0("^", moderator, ":", exposure),
      paste0(exposure, ".*\\*.*", moderator),
      paste0(moderator, ".*\\*.*", exposure),
      paste0(exposure, ".*:", moderator, ".*"),
      paste0(moderator, ".*:", exposure, ".*")
    )
    
    matched_terms <- character(0)
    for(pattern in patterns) {
      matches <- grep(pattern, coef_names, value = TRUE)
      matched_terms <- unique(c(matched_terms, matches))
    }
    
    if(length(matched_terms) == 0) {
      cat("Warning: No interaction terms found for", exposure, "×", moderator, "\\n")
      cat("Available coefficient names:", paste(coef_names, collapse = ", "), "\\n")
    }
    
    return(matched_terms)
  }, error = function(e) {
    cat("Error extracting interaction terms:", e$message, "\\n")
    return(character(0))
  })
}

get_factor_levels_from_data <- function(data, var_name) {
  if(!var_name %in% names(data)) {
    cat("Warning: Variable", var_name, "not found in data\\n")
    return(character(0))
  }
  
  if(is.factor(data[[var_name]])) {
    return(levels(data[[var_name]]))
  } else if(is.character(data[[var_name]]) || is.logical(data[[var_name]])) {
    return(sort(unique(data[[var_name]][!is.na(data[[var_name]])])))
  } else if(is.numeric(data[[var_name]])) {
    unique_vals <- sort(unique(data[[var_name]][!is.na(data[[var_name]])]))
    if(length(unique_vals) <= 20) {
      return(as.character(unique_vals))
    } else {
      cat("Warning: Variable", var_name, "has", length(unique_vals), "unique values, treating as continuous\\n")
      return(character(0))
    }
  } else {
    return(sort(unique(data[[var_name]][!is.na(data[[var_name]])])))
  }
}
'''
    
    @staticmethod
    def factor_level_validation_template() -> str:
        return '''
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
      } else if(is.factor(data[[var]])) {
        if(length(levels(data[[var]])) < min_levels) {
          warning("Factor ", var, " has only ", length(levels(data[[var]])), " level(s)")
        }
      }
    }
  }
  return(data)
}
'''
    
    @staticmethod
    def mice_data_reading_template() -> str:
        return '''
read_mice_datasets <- function(prev_stage_path = NULL, mice_stage_path = "../7.2", n_imputations = 20, prefer_mice = TRUE) {
  imp_list <- list()
  
  if(!is.null(prev_stage_path) && file.exists(prev_stage_path)) {
    cat("Reading primary data from previous stage:", prev_stage_path, "\\n")
    primary_data <- read.csv(prev_stage_path, stringsAsFactors = FALSE)
    cat("Primary data loaded:", nrow(primary_data), "rows,", ncol(primary_data), "columns\\n")
  } else {
    cat("Warning: Previous stage data not found, will use MICE datasets only\\n")
    primary_data <- NULL
  }
  
  cat("Attempting to read MICE imputed datasets from:", mice_stage_path, "\\n")
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
      cat("No MICE datasets found, using primary data as single dataset\\n")
      imp_list <- list(primary_data)
    } else {
      stop("ERROR: No data found. Neither previous stage data nor MICE datasets are available.")
    }
  } else if(!prefer_mice && !is.null(primary_data)) {
    cat("MICE datasets found but final SAP does not require MICE; using primary data as single dataset\\n")
    imp_list <- list(primary_data)
  } else {
    cat("Successfully loaded", length(imp_list), "MICE imputed datasets\\n")
    if(!is.null(primary_data)) {
      cat("Note: Primary data from previous stage available but not used (MICE datasets take precedence)\\n")
    }
  }
  
  return(imp_list)
}
'''
    
    @staticmethod
    def get_all_templates_reference() -> str:
        """
        Get reference description for all templates (optimized version: do not send complete code)
        
        Returns:
            Reference description for all templates
        """
        return f'''**R Code Standard Template Reference**:

The system provides the following standardized templates, please follow them when generating R code:

1. {RCodeTemplates.get_template_reference('font_setup')}

2. {RCodeTemplates.get_template_reference('data_reading')}

3. {RCodeTemplates.get_template_reference('output')}

4. {RCodeTemplates.get_template_reference('data_transfer')}

5. **Factor Level Validation Template** (for modeling stages):
- **validate_factor_levels()**: Validate factor levels before and after conversion, including within strata
- **safe_factor_conversion()**: Safely convert variables to factors with level preservation
- MUST use these functions to prevent single-level factor errors in model building

6. **MICE Data Reading Template** (SAP-conditional for stages requiring multiple imputation):
- **read_mice_datasets()**: Read data from previous stage's main_output.csv first, then MICE datasets only if needed
- Automatically handles fallback logic and supports `prefer_mice = FALSE` when the final SAP specifies a non-MICE missing-data strategy
- Use this function instead of hardcoding data paths when multiple imputation is required by the SAP

7. **Pooled Results Extraction Template** (for stages 7.5, 7.7):
- **extract_coefficient_by_levels()**: Smart coefficient extraction based on factor levels from data
- **extract_interaction_terms()**: Extract interaction terms from pooled models
- **get_factor_levels_from_data()**: Get actual factor levels from current stage data
- MUST use these functions instead of hardcoding coefficient names

8. **Image Generation Template**:
- **Heatmap**: Must use create_heatmap() function (automatically handles label overlap and format issues)
- **Other images**: Use create_standard_plot() or create_forest_plot() function to generate standardized images
- Unified image size (10x6 inches, 300DPI)
- Use ENGLISH for all labels, titles, and annotations

6. {RCodeTemplates.get_template_reference('statistical_validation')}
- MANDATORY: Call validate_output_quality() before writing key result tables
- MANDATORY: Call check_weight_status() at start of analysis
- MANDATORY: Call check_sample_size_consistency() when data changes

**CRITICAL: All graphics MUST use English text - no Chinese characters in plots**
- Standardized image naming (descriptive file names)
- **Forest plot auto-filtering**: create_forest_plot() automatically filters abnormal effect values (OR/PR > 1000 or < 0.001), which are usually caused by sparse variable separation issues

Important notes:
- Code should start with font setup (using logic from template 1)
- Data reading should follow structure of template 2
- Output saving **must strictly follow** template 3 to ensure generation of main_output.csv and analysis_summary.json
- **Must call template 4's ensure_output_files() function at end of script** as final safeguard for data transfer
- The critical_decisions field in analysis_summary.json is required and must record key decisions affecting downstream
'''
    
    @staticmethod
    def image_generation_template() -> str:
        """
        Standardized image generation template
        
        Solves image format and display issues:
        1. Unified image size and resolution
        2. Ensure Chinese fonts display correctly
        3. Standardized image naming
        """
        return '''# === Standardized Image Generation Template ===

# Image generation standard function
create_standard_plot <- function(plot_obj, filename, title = NULL, width = 10, height = 6) {
  """Generate standardized image file"""
  
  # Ensure filename contains descriptive information
  if (!grepl("\\\\.png$", filename)) {
    filename <- paste0(filename, ".png")
  }
  
  # Set image parameters
  png(filename, width = width, height = height, units = "in", res = 300)
  
  # If ggplot object, add title
  if (inherits(plot_obj, "ggplot")) {
    if (!is.null(title)) {
      plot_obj <- plot_obj + ggtitle(title)
    }
    print(plot_obj)
  } else {
    # Base R graphics
    if (!is.null(title)) {
      plot(plot_obj, main = title)
    } else {
      plot(plot_obj)
    }
  }
  
  dev.off()
  cat("✓ Image saved:", filename, "\\n")
}

# Heatmap generation function (standardized, for correlation matrices)
create_heatmap <- function(data, filename, title = "Correlation Heatmap", 
                          width = 12, height = 10, dpi = 300) {
  """Generate standardized heatmap, automatically handles label overlap and format issues"""
  
  # Ensure ggplot2 is loaded
  if (!requireNamespace("ggplot2", quietly = TRUE)) {
    install.packages("ggplot2", quiet = TRUE)
  }
  library(ggplot2)
  
  # Ensure filename contains .png extension
  if (!grepl("\\.png$", filename)) {
    filename <- paste0(filename, ".png")
  }
  
  # Convert data to long format (if input is matrix)
  if (is.matrix(data) || is.data.frame(data)) {
    # If correlation matrix
    if (nrow(data) == ncol(data) && all(rownames(data) == colnames(data))) {
      corr_long <- as.data.frame(as.table(as.matrix(data)))
      colnames(corr_long) <- c("Var1", "Var2", "Corr")
      
      # Use ggplot2 to generate heatmap (avoid label overlap)
      p <- ggplot(corr_long, aes(x = Var1, y = Var2, fill = Corr)) +
        geom_tile(color = "white", linewidth = 0.5) +
        scale_fill_gradient2(low = "#3778C2", mid = "white", high = "#D43F3A", 
                            midpoint = 0, limits = c(-1, 1), 
                            name = "Correlation", guide = guide_colorbar(barwidth = 0.8, barheight = 15)) +
        coord_fixed() +
        labs(title = title, x = NULL, y = NULL) +
        theme_minimal(base_size = 12) +
        theme(
          plot.title = element_text(hjust = 0.5, size = 14, face = "bold", margin = margin(b = 15)),
          axis.text.x = element_text(angle = 45, hjust = 1, vjust = 1, size = 10, 
                                    margin = margin(t = 5, r = 0, b = 0, l = 0)),
          axis.text.y = element_text(size = 10, margin = margin(r = 5)),
          panel.grid = element_blank(),
          legend.position = "right",
          legend.title = element_text(size = 11),
          legend.text = element_text(size = 10),
          plot.margin = margin(20, 20, 20, 20)
        )
      
      # Save image
      ggsave(filename = filename, plot = p, width = width, height = height, 
            dpi = dpi, units = "in", limitsize = FALSE)
      cat("✓ Heatmap saved:", filename, "\\n")
      return(invisible(p))
    }
  }
  
  # Fallback: use corrplot (if ggplot2 approach doesn't apply)
  png(filename, width = width, height = height, units = "in", res = dpi)
  if (requireNamespace("corrplot", quietly = TRUE)) {
    corrplot::corrplot(as.matrix(data), method = "color", type = "upper", 
                      order = "hclust", tl.cex = 0.7, tl.col = "black",
                      tl.srt = 45,  # Rotate labels 45 degrees
                      title = title, mar = c(0, 0, 2, 0))
  } else {
    heatmap(as.matrix(data), main = title, col = heat.colors(256), 
           margins = c(10, 10), cexRow = 0.8, cexCol = 0.8)
  }
  dev.off()
  cat("✓ Heatmap saved:", filename, "\\n")
}

# Distribution plot generation function
create_distribution_plot <- function(data, filename, title = "Variable Distribution Plot") {
  """Generate standardized distribution plot"""
  png(filename, width = 12, height = 8, units = "in", res = 300)
  
  # Set multi-panel layout
  par(mfrow = c(2, 2), mar = c(4, 4, 2, 1))
  
  # Generate different types of distribution plots
  if (is.numeric(data)) {
    hist(data, main = paste(title, "- Histogram"), xlab = "Value", col = "lightblue")
    boxplot(data, main = paste(title, "- Boxplot"), ylab = "Value")
    plot(density(data, na.rm = TRUE), main = paste(title, "- Density"))
    qqnorm(data, main = paste(title, "- Q-Q Plot"))
  }
  
  dev.off()
  cat("✓ Distribution plot saved:", filename, "\\n")
}

# Standardized forest plot (OR/PR, Beta)
create_forest_plot <- function(df, effect_type = c("OR", "PR", "Beta"),
                               est_col = NULL, lower_col = NULL, upper_col = NULL,
                               var_col = "variable", filename = "forest_plot.png",
                               title = NULL) {
  effect_type <- match.arg(effect_type)
  if (!grepl("\\.png$", filename)) filename <- paste0(filename, ".png")

  # Intelligent column name recognition
  if (is.null(est_col)) {
    est_col <- ifelse(effect_type %in% c("OR", "PR"),
                      ifelse("or" %in% names(df), "or", ifelse("pr" %in% names(df), "pr", NA)),
                      "estimate")
  }
  if (is.null(lower_col)) {
    lower_col <- ifelse(effect_type %in% c("OR", "PR"),
                        ifelse("or_lower" %in% names(df), "or_lower", ifelse("pr_lower" %in% names(df), "pr_lower", NA)),
                        ifelse("beta_lower" %in% names(df), "beta_lower", NA))
  }
  if (is.null(upper_col)) {
    upper_col <- ifelse(effect_type %in% c("OR", "PR"),
                        ifelse("or_upper" %in% names(df), "or_upper", ifelse("pr_upper" %in% names(df), "pr_upper", NA)),
                        ifelse("beta_upper" %in% names(df), "beta_upper", NA))
  }

  # Filter invalid values and abnormal effect values (caused by sparse variables/separation issues)
  if (effect_type %in% c("OR", "PR")) {
    df <- df[!is.na(df[[est_col]]) & df[[est_col]] > 0, ]
    if (!is.na(lower_col)) df <- df[!is.na(df[[lower_col]]) & df[[lower_col]] > 0, ]
    if (!is.na(upper_col)) df <- df[!is.na(df[[upper_col]]) & df[[upper_col]] > 0, ]
    # Filter abnormally large effect values (usually caused by complete separation or convergence issues)
    # OR/PR > 1000 or < 0.001 usually indicates model instability or data sparsity issues
    df <- df[df[[est_col]] <= 1000 & df[[est_col]] >= 0.001, ]
    if (nrow(df) == 0) {
      warning("Warning: All effect values were filtered (possibly all abnormal), please check model convergence and data sparsity")
    }
  } else {
    df <- df[!is.na(df[[est_col]]), ]
  }

  # Remove intercept term
  if (var_col %in% names(df)) {
    df <- df[!grepl("Intercept", df[[var_col]]), ]
  }

  # Plot
  png(filename, width = 10, height = 6, units = "in", res = 300)
  p <- ggplot(df, aes_string(x = var_col, y = est_col)) +
    geom_point(size = 3) +
    coord_flip() +
    theme_minimal()

  # Error bars
  if (!is.na(lower_col) && !is.na(upper_col) && lower_col %in% names(df) && upper_col %in% names(df)) {
    p <- p + geom_errorbar(aes_string(ymin = lower_col, ymax = upper_col), width = 0.2)
  }

  # Reference line and axis
  if (effect_type %in% c("OR", "PR")) {
    p <- p + geom_hline(yintercept = 1, linetype = "dashed", color = "red") +
      scale_y_log10()
    yl <- ifelse(effect_type == "OR", "Odds Ratio (OR)", "Prevalence Ratio (PR)")
    p <- p + labs(y = yl)
  } else {
    p <- p + geom_hline(yintercept = 0, linetype = "dashed", color = "red") +
      labs(y = "Regression Coefficient (β)")
  }

  if (!is.null(title)) p <- p + ggtitle(title)
  print(p)
  dev.off()
  cat("✓ Forest plot saved:", filename, "\n")
}
'''


__all__ = ['RCodeTemplates']

