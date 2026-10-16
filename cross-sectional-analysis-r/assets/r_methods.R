# Cross-sectional R method library

suppressPackageStartupMessages({
  library(ggplot2)
  library(showtext)
  library(readr)
  library(dplyr)
  library(jsonlite)
})

clinical_palette <- c(
  grey = "#D6D6D6",
  blue = "#9CB0C3",
  blue_dark = "#6F95AE",
  blue_deep = "#4E6F84",
  grey_dark = "#AEB8BF",
  text = "#1F2A33",
  grid = "#E7EBEE",
  bg = "#FFFFFF"
)

configure_clinical_fonts <- function() {
  if (Sys.info()[["sysname"]] == "Darwin") {
    suppressWarnings(try({
      font_add(
        family = "TNR",
        regular = "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        bold = "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        italic = "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
        bolditalic = "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf"
      )
      showtext_auto()
    }, silent = TRUE))
  }
}

theme_clinical <- function(base_size = 11, base_family = "TNR") {
  theme_classic(base_size = base_size, base_family = base_family) +
    theme(
      plot.title = element_text(face = "bold", color = clinical_palette["text"], hjust = 0),
      plot.subtitle = element_text(color = clinical_palette["text"], hjust = 0),
      axis.title = element_text(color = clinical_palette["text"]),
      axis.text = element_text(color = clinical_palette["text"]),
      axis.line = element_line(color = clinical_palette["grey_dark"], linewidth = 0.35),
      axis.ticks = element_line(color = clinical_palette["grey_dark"], linewidth = 0.35),
      legend.position = "bottom",
      legend.title = element_text(face = "bold", color = clinical_palette["text"]),
      legend.text = element_text(color = clinical_palette["text"]),
      strip.background = element_rect(fill = clinical_palette["grey"], color = clinical_palette["grey_dark"], linewidth = 0.35),
      strip.text = element_text(face = "bold", color = clinical_palette["text"]),
      panel.grid.major.x = element_line(color = clinical_palette["grid"], linewidth = 0.35),
      panel.grid.major.y = element_blank(),
      panel.grid.minor = element_blank(),
      plot.background = element_rect(fill = clinical_palette["bg"], color = NA),
      legend.key = element_rect(fill = clinical_palette["bg"], color = NA)
    )
}

save_clinical_plot <- function(plot, stem, fig_dir, width = 8, height = 5, dpi = 600) {
  dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)
  png_file <- file.path(fig_dir, paste0(stem, ".png"))
  pdf_file <- file.path(fig_dir, paste0(stem, ".pdf"))
  ggsave(
    filename = png_file,
    plot = plot,
    width = width,
    height = height,
    dpi = dpi,
    bg = clinical_palette["bg"]
  )
  ggsave(
    filename = pdf_file,
    plot = plot,
    width = width,
    height = height,
    bg = clinical_palette["bg"]
  )
  invisible(list(png = png_file, pdf = pdf_file))
}



# Shared helpers
configure_clinical_fonts()

ensure_analysis_dirs <- function(output_dir) {
  dirs <- list(
    root = output_dir,
    tables = file.path(output_dir, "tables"),
    figures = file.path(output_dir, "figures"),
    logs = file.path(output_dir, "logs"),
    report = file.path(output_dir, "report")
  )
  lapply(dirs, dir.create, recursive = TRUE, showWarnings = FALSE)
  dirs
}

write_analysis_summary <- function(output_dir, stage, methods, notes = character(), artifacts = list(), results = NULL, diagnostics = NULL) {
  summary_path <- file.path(output_dir, "analysis_summary.json")
  payload <- list(
    stage = stage,
    timestamp = as.character(Sys.time()),
    methods = methods,
    notes = notes,
    artifacts = artifacts,
    results = results,
    diagnostics = diagnostics
  )
  jsonlite::write_json(payload, summary_path, auto_unbox = TRUE, pretty = TRUE)
  invisible(summary_path)
}

write_main_output <- function(data, output_dir) {
  out <- file.path(output_dir, "main_output.csv")
  readr::write_csv(data, out)
  invisible(out)
}

write_csv_bundle <- function(data, stem, tables_dir) {
  out <- file.path(tables_dir, paste0(stem, ".csv"))
  readr::write_csv(data, out)
  invisible(out)
}

write_diagnostic_log <- function(output_dir, diagnostics) {
  out <- file.path(output_dir, "diagnostic_log.json")
  jsonlite::write_json(list(diagnostics = diagnostics), out, auto_unbox = TRUE, pretty = TRUE)
  invisible(out)
}

write_plot_bundle <- function(plot_obj, stem, figures_dir, width = 7, height = 5, dpi = 300) {
  out <- file.path(figures_dir, paste0(stem, ".png"))
  ggplot2::ggsave(out, plot = plot_obj, width = width, height = height, dpi = dpi)
  invisible(out)
}

build_design_object <- function(data, weight_var = NULL, strata_var = NULL, psu_var = NULL, design_mode = c("sample", "survey_full", "survey_weight_only")) {
  design_mode <- match.arg(design_mode)
  if (design_mode == "sample" || is.null(weight_var) || !nzchar(weight_var)) {
    return(list(type = "sample", data = data, design = NULL, metadata = list(uses_strata = FALSE, uses_psu = FALSE)))
  }
  suppressPackageStartupMessages(library(survey))
  if (design_mode == "survey_full" && !is.null(psu_var) && nzchar(psu_var)) {
    design <- survey::svydesign(
      ids = as.formula(paste0("~", psu_var)),
      strata = if (!is.null(strata_var) && nzchar(strata_var)) as.formula(paste0("~", strata_var)) else NULL,
      weights = as.formula(paste0("~", weight_var)),
      data = data,
      nest = TRUE
    )
    return(list(type = "survey_full", data = data, design = design, metadata = list(uses_strata = !is.null(strata_var) && nzchar(strata_var), uses_psu = TRUE)))
  }
  design <- survey::svydesign(
    ids = ~1,
    strata = if (!is.null(strata_var) && nzchar(strata_var)) as.formula(paste0("~", strata_var)) else NULL,
    weights = as.formula(paste0("~", weight_var)),
    data = data,
    nest = TRUE
  )
  list(
    type = "survey_weight_only",
    data = data,
    design = design,
    metadata = list(
      uses_strata = !is.null(strata_var) && nzchar(strata_var),
      uses_psu = FALSE
    )
  )
}

quote_variable <- function(x) paste0("`", gsub("`", "\\`", x, fixed = TRUE), "`")

complete_continuous_model_data <- function(data, variables, design_mode,
                                           weight_var = NULL, strata_var = NULL, psu_var = NULL) {
  design_vars <- if (design_mode == "sample") character() else c(weight_var, strata_var, psu_var)
  needed <- unique(c(variables, design_vars[nzchar(design_vars)]))
  missing <- setdiff(needed, names(data))
  if (length(missing)) stop("Required analysis fields are absent: ", paste(missing, collapse = ", "))
  out <- data[, needed, drop = FALSE]
  out <- out[stats::complete.cases(out), , drop = FALSE]
  if (design_mode != "sample") {
    if (is.null(weight_var) || !nzchar(weight_var)) stop("A weight variable is required for survey analysis.")
    valid_weight <- is.finite(out[[weight_var]]) & out[[weight_var]] > 0
    out <- out[valid_weight, , drop = FALSE]
  }
  if (!nrow(out)) stop("No complete records remain for the requested model.")
  out
}

analysis_weights <- function(data, design_mode, weight_var = NULL) {
  if (design_mode == "sample") return(rep(1, nrow(data)))
  data[[weight_var]]
}

model_reference <- function(model, design_object, confidence_level = 0.95) {
  if (design_object$type == "sample") {
    degrees_of_freedom <- stats::df.residual(model)
  } else {
    degrees_of_freedom <- survey::degf(design_object$design)
  }
  if (!is.finite(degrees_of_freedom) || degrees_of_freedom <= 0) {
    stop("Positive model/design degrees of freedom are required for coherent inference.")
  }
  list(
    degrees_of_freedom = as.numeric(degrees_of_freedom),
    critical_value = stats::qt(1 - (1 - confidence_level) / 2, df = degrees_of_freedom),
    reference_distribution = "student_t",
    confidence_level = confidence_level,
    variance_status = if (design_object$type == "survey_weight_only") {
      "INDIVIDUAL_INDEPENDENCE_WORKING_VARIANCE_FORMAL_SURVEY_VARIANCE_UNAVAILABLE"
    } else if (design_object$type == "survey_full") {
      "SURVEY_DESIGN_VARIANCE"
    } else {
      "SAMPLE_MODEL_VARIANCE"
    }
  )
}

coefficient_rows <- function(model, coefficient_names, reference, design_mode,
                             outcome_var, exposure_var, adjustment_terms = character()) {
  beta <- stats::coef(model)
  variance <- stats::vcov(model)
  coefficient_names <- intersect(coefficient_names, names(beta))
  coefficient_names <- coefficient_names[is.finite(beta[coefficient_names])]
  if (!length(coefficient_names)) return(data.frame())
  standard_error <- sqrt(diag(variance)[coefficient_names])
  estimate <- unname(beta[coefficient_names])
  statistic <- estimate / standard_error
  data.frame(
    term = coefficient_names,
    estimate = estimate,
    std_error = unname(standard_error),
    ci_low = estimate - reference$critical_value * standard_error,
    ci_high = estimate + reference$critical_value * standard_error,
    p_value = 2 * stats::pt(abs(statistic), df = reference$degrees_of_freedom, lower.tail = FALSE),
    degrees_of_freedom = reference$degrees_of_freedom,
    reference_distribution = reference$reference_distribution,
    confidence_level = reference$confidence_level,
    outcome = outcome_var,
    exposure = exposure_var,
    effect_measure = "beta coefficient",
    effect_scale = "identity-link continuous outcome scale",
    adjustment_set = paste(adjustment_terms, collapse = ";"),
    design_mode = design_mode,
    variance_status = reference$variance_status,
    stringsAsFactors = FALSE
  )
}

joint_wald_test <- function(model, coefficient_names, reference, test_label) {
  beta <- stats::coef(model)
  variance <- stats::vcov(model)
  coefficient_names <- intersect(coefficient_names, names(beta))
  coefficient_names <- coefficient_names[is.finite(beta[coefficient_names])]
  if (!length(coefficient_names)) {
    return(data.frame(
      test = test_label, statistic = NA_real_, numerator_df = 0,
      denominator_df = reference$degrees_of_freedom, p_value = NA_real_,
      tested_terms = "", status = "NONESTIMABLE_NO_COEFFICIENTS",
      stringsAsFactors = FALSE
    ))
  }
  covariance <- variance[coefficient_names, coefficient_names, drop = FALSE]
  rank <- qr(covariance)$rank
  if (rank < length(coefficient_names)) {
    return(data.frame(
      test = test_label, statistic = NA_real_, numerator_df = rank,
      denominator_df = reference$degrees_of_freedom, p_value = NA_real_,
      tested_terms = paste(coefficient_names, collapse = ";"),
      status = "NONESTIMABLE_RANK_DEFICIENT", stringsAsFactors = FALSE
    ))
  }
  b <- matrix(beta[coefficient_names], ncol = 1)
  chi_square <- as.numeric(t(b) %*% solve(covariance, b))
  statistic <- chi_square / length(coefficient_names)
  data.frame(
    test = test_label,
    statistic = statistic,
    numerator_df = length(coefficient_names),
    denominator_df = reference$degrees_of_freedom,
    p_value = stats::pf(
      statistic, length(coefficient_names), reference$degrees_of_freedom,
      lower.tail = FALSE
    ),
    tested_terms = paste(coefficient_names, collapse = ";"),
    status = "ESTIMATED_WALD_F",
    stringsAsFactors = FALSE
  )
}

aligned_model_matrix <- function(model, newdata) {
  terms_object <- stats::delete.response(stats::terms(model))
  matrix <- stats::model.matrix(
    terms_object,
    data = newdata,
    contrasts.arg = model$contrasts,
    xlev = model$xlevels
  )
  coefficient_names <- names(stats::coef(model))
  missing_columns <- setdiff(coefficient_names, colnames(matrix))
  if (length(missing_columns)) {
    matrix <- cbind(
      matrix,
      matrix(0, nrow = nrow(matrix), ncol = length(missing_columns),
             dimnames = list(NULL, missing_columns))
    )
  }
  matrix[, coefficient_names, drop = FALSE]
}

standardized_linear_prediction <- function(model, newdata, standardization_weights, reference,
                                           contrast_matrix = NULL) {
  matrix <- aligned_model_matrix(model, newdata)
  normalized_weights <- standardization_weights / sum(standardization_weights)
  average_row <- as.numeric(crossprod(normalized_weights, matrix))
  names(average_row) <- colnames(matrix)
  if (!is.null(contrast_matrix)) average_row <- average_row - contrast_matrix
  beta <- stats::coef(model)
  variance <- stats::vcov(model)
  estimate <- sum(average_row * beta)
  standard_error <- sqrt(as.numeric(t(average_row) %*% variance %*% average_row))
  c(
    estimate = estimate,
    std_error = standard_error,
    ci_low = estimate - reference$critical_value * standard_error,
    ci_high = estimate + reference$critical_value * standard_error
  )
}

validate_analysis_weights <- function(w) {
  if (any(!is.finite(w) & !is.na(w))) stop("Weights must be finite or missing.")
  if (any(w < 0, na.rm = TRUE)) stop("Negative weights are not allowed.")
  invisible(TRUE)
}

weighted_type1_quantile <- function(x, w, probs) {
  validate_analysis_weights(w)
  ok <- is.finite(x) & is.finite(w) & w > 0
  if (!any(ok)) return(rep(NA_real_, length(probs)))
  x <- x[ok]
  w <- w[ok]
  aggregated <- stats::aggregate(w, list(value = x), sum)
  aggregated <- aggregated[order(aggregated$value), , drop = FALSE]
  cumulative <- cumsum(aggregated$x) / sum(aggregated$x)
  vapply(probs, function(prob) {
    if (!is.finite(prob) || prob < 0 || prob > 1) stop("Quantile probabilities must be in [0, 1].")
    aggregated$value[which(cumulative >= prob)[1]]
  }, numeric(1))
}

weighted_linear_quantile <- function(x, w, probs) {
  validate_analysis_weights(w)
  if (any(!is.finite(probs)) || any(probs < 0 | probs > 1)) {
    stop("Quantile probabilities must be finite and in [0, 1].")
  }
  ok <- is.finite(x) & is.finite(w) & w > 0
  if (!any(ok)) return(rep(NA_real_, length(probs)))
  x <- x[ok]
  w <- w[ok]
  aggregated <- stats::aggregate(w, list(value = x), sum)
  aggregated <- aggregated[order(aggregated$value), , drop = FALSE]
  if (nrow(aggregated) == 1L) return(rep(aggregated$value[[1]], length(probs)))
  midpoint <- (cumsum(aggregated$x) - aggregated$x / 2) / sum(aggregated$x)
  stats::approx(
    x = midpoint,
    y = aggregated$value,
    xout = probs,
    method = "linear",
    ties = "ordered",
    rule = 2
  )$y
}

restricted_cubic_spline_basis <- function(x, knots, prefix = ".rcs") {
  knots <- sort(as.numeric(knots))
  if (length(knots) < 4L || any(!is.finite(knots)) || any(diff(knots) <= 0)) {
    stop("Restricted cubic splines require at least four finite, distinct knots.")
  }
  truncated_cube <- function(value, knot) pmax(value - knot, 0)^3
  last <- length(knots)
  scale <- (knots[[last]] - knots[[1]])^2
  basis <- list(x)
  for (j in seq_len(last - 2L)) {
    nonlinear <- (
      truncated_cube(x, knots[[j]]) -
        truncated_cube(x, knots[[last - 1L]]) *
          (knots[[last]] - knots[[j]]) / (knots[[last]] - knots[[last - 1L]]) +
        truncated_cube(x, knots[[last]]) *
          (knots[[last - 1L]] - knots[[j]]) / (knots[[last]] - knots[[last - 1L]])
    ) / scale
    basis[[length(basis) + 1L]] <- nonlinear
  }
  out <- as.data.frame(basis, optional = TRUE)
  names(out) <- c(paste0(prefix, "_linear"), paste0(prefix, "_nonlinear", seq_len(last - 2L)))
  out
}

weighted_distribution_summary <- function(x, w) {
  validate_analysis_weights(w)
  ok <- is.finite(x) & is.finite(w) & w > 0
  if (!any(ok)) {
    return(c(n = 0, mean = NA_real_, sd = NA_real_, p05 = NA_real_, p25 = NA_real_,
             p50 = NA_real_, p75 = NA_real_, p95 = NA_real_))
  }
  xx <- x[ok]
  ww <- w[ok]
  mu <- sum(xx * ww) / sum(ww)
  variance <- sum(ww * (xx - mu)^2) / sum(ww)
  quantiles <- weighted_type1_quantile(xx, ww, c(.05, .25, .50, .75, .95))
  c(n = length(xx), mean = mu, sd = sqrt(variance), p05 = quantiles[1], p25 = quantiles[2],
    p50 = quantiles[3], p75 = quantiles[4], p95 = quantiles[5])
}

complete_support_grid <- function(data, domain_var, category_var) {
  domains <- sort(unique(as.character(data[[domain_var]][!is.na(data[[domain_var]])])))
  categories <- sort(unique(as.character(data[[category_var]][!is.na(data[[category_var]])])))
  grid <- expand.grid(domain = domains, category = categories, stringsAsFactors = FALSE)
  observed <- as.data.frame(table(
    domain = factor(as.character(data[[domain_var]]), levels = domains),
    category = factor(as.character(data[[category_var]]), levels = categories),
    useNA = "no"
  ), stringsAsFactors = FALSE)
  names(observed)[3] <- "n"
  out <- merge(grid, observed, by = c("domain", "category"), all.x = TRUE, sort = FALSE)
  out$n[is.na(out$n)] <- 0L
  totals <- stats::aggregate(n ~ domain, out, sum)
  names(totals)[2] <- "domain_total"
  out <- merge(out, totals, by = "domain", all.x = TRUE, sort = FALSE)
  out$proportion <- ifelse(out$domain_total > 0, out$n / out$domain_total, NA_real_)
  out$support_flag <- ifelse(out$n == 0, "STRUCTURAL_ZERO",
                             ifelse(out$n < 10, "SPARSE_LT10", "OBSERVED_SUPPORT"))
  out
}

extract_count_result <- function(model,
                                 exposure_term,
                                 objective_id,
                                 stage_id,
                                 exponentiate = TRUE,
                                 component = "cond",
                                 term_match = "prefix") {
  if (inherits(model, "glmmTMB")) {
    res <- broom.mixed::tidy(model, effects = "fixed", component = component, conf.int = TRUE, exponentiate = exponentiate)
  } else {
    res <- broom::tidy(model, conf.int = TRUE, exponentiate = exponentiate)
  }
  if ("component" %in% names(res)) {
    res <- res[res$component == component, , drop = FALSE]
  }
  if (!"term" %in% names(res) && "contrast" %in% names(res)) {
    res$term <- res$contrast
  }
  if (term_match == "prefix") {
    res <- res[startsWith(res$term, exposure_term), , drop = FALSE]
  } else if (term_match == "contains") {
    res <- res[grepl(exposure_term, res$term, fixed = TRUE), , drop = FALSE]
  } else {
    res <- res[res$term == exposure_term, , drop = FALSE]
  }
  res$result_type <- "count_association_result"
  res$objective_id <- objective_id
  res$stage_id <- stage_id
  res$effect_measure <- "rate ratio"
  res$model_family <- if (inherits(model, "glmmTMB")) "zero_inflated" else if (inherits(model, "negbin")) "negative_binomial" else "count"
  res
}

extract_model_results <- function(model,
                                  exposure_term,
                                  effect_measure = c(
                                    "prevalence ratio", "odds ratio", "beta",
                                    "relative risk ratio", "rate ratio", "common odds ratio",
                                    "beta coefficient", "logit-scale coefficient"
                                  ),
                                  term_match = c("exact", "prefix", "contains"),
                                  exponentiate = NULL,
                                  component = NULL,
                                  confidence_level = 0.95,
                                  exposure_unit = "one-unit increase",
                                  exposure_contrast = NULL,
                                  adjustment_terms = character()) {
  effect_measure <- match.arg(effect_measure)
  term_match <- match.arg(term_match)
  suppressPackageStartupMessages(library(broom))
  if (is.null(exponentiate)) {
    exponentiate <- !effect_measure %in% c("beta", "beta coefficient", "logit-scale coefficient")
  }

  tidy_df <- NULL
  if (inherits(model, "glmmTMB")) {
    suppressPackageStartupMessages(library(broom.mixed))
    tidy_df <- broom.mixed::tidy(
      model, effects = "fixed", conf.int = FALSE, exponentiate = FALSE,
      component = if (is.null(component)) "cond" else component
    )
  } else if (inherits(model, "MIresult")) {
    tidy_df <- as.data.frame(summary(model))
    tidy_df$term <- rownames(tidy_df)
    names(tidy_df) <- sub("^results$", "estimate", names(tidy_df))
    names(tidy_df) <- sub("^se$", "std.error", names(tidy_df))
  } else {
    tidy_df <- broom::tidy(model, conf.int = FALSE, exponentiate = FALSE)
  }
  if (!"term" %in% names(tidy_df) && "contrast" %in% names(tidy_df)) tidy_df$term <- tidy_df$contrast
  if (!"term" %in% names(tidy_df)) return(tidy_df)

  keep <- switch(
    term_match,
    exact = tidy_df$term == exposure_term,
    prefix = startsWith(tidy_df$term, exposure_term),
    contains = grepl(exposure_term, tidy_df$term, fixed = TRUE)
  )
  out <- tidy_df[keep, , drop = FALSE]
  if (!nrow(out)) return(out)
  if (!"std.error" %in% names(out)) stop("Model extractor did not return a standard error; coherent inference cannot be registered.")

  # Use the same reference distribution for the interval and the p value.
  coefficient_table <- tryCatch(as.data.frame(summary(model)$coefficients), error = function(e) NULL)
  p_column <- if (!is.null(coefficient_table)) grep("^Pr\\(", names(coefficient_table), value = TRUE)[1] else NA_character_
  uses_t <- inherits(model, c("lm", "svyglm")) || (!is.na(p_column) && grepl("t", p_column, fixed = TRUE))
  reference_distribution <- if (uses_t) "student_t" else "normal"
  degrees_of_freedom <- if (uses_t) tryCatch(stats::df.residual(model), error = function(e) NA_real_) else NA_real_
  if (uses_t && (!is.finite(degrees_of_freedom) || degrees_of_freedom <= 0)) {
    stop("A t-referenced result requires positive residual degrees of freedom.")
  }
  alpha <- 1 - confidence_level
  critical_value <- if (uses_t) stats::qt(1 - alpha / 2, df = degrees_of_freedom) else stats::qnorm(1 - alpha / 2)
  raw_low <- out$estimate - critical_value * out$std.error
  raw_high <- out$estimate + critical_value * out$std.error
  if (exponentiate) {
    out$estimate <- exp(out$estimate)
    out$conf.low <- exp(raw_low)
    out$conf.high <- exp(raw_high)
  } else {
    out$conf.low <- raw_low
    out$conf.high <- raw_high
  }

  # Recompute the p value from the same statistic and declared reference.
  statistic <- (if (exponentiate) log(out$estimate) else out$estimate) / out$std.error
  out$statistic <- statistic
  out$p.value <- if (uses_t) {
    2 * stats::pt(abs(statistic), df = degrees_of_freedom, lower.tail = FALSE)
  } else {
    2 * stats::pnorm(abs(statistic), lower.tail = FALSE)
  }
  out$confidence_level <- confidence_level
  out$reference_distribution <- reference_distribution
  out$p_reference_distribution <- reference_distribution
  out$degrees_of_freedom <- if (uses_t) degrees_of_freedom else NA_real_
  out$critical_value <- critical_value
  out$sidedness <- "two-sided"
  out$exponentiated <- exponentiate
  out$exposure_unit <- exposure_unit
  out$exposure_contrast <- if (is.null(exposure_contrast)) exposure_unit else exposure_contrast
  out$adjustment_set <- paste(adjustment_terms, collapse = ";")
  out
}

extract_multinomial_result <- function(model,
                                       exposure_term,
                                       objective_id,
                                       stage_id,
                                       exponentiate = TRUE,
                                       term_match = "prefix") {
  res <- broom::tidy(model, conf.int = TRUE, exponentiate = exponentiate)
  if (!"term" %in% names(res) && "contrast" %in% names(res)) {
    res$term <- res$contrast
  }
  if (term_match == "prefix") {
    res <- res[startsWith(res$term, exposure_term), , drop = FALSE]
  } else if (term_match == "contains") {
    res <- res[grepl(exposure_term, res$term, fixed = TRUE), , drop = FALSE]
  } else {
    res <- res[res$term == exposure_term, , drop = FALSE]
  }
  if ("y.level" %in% names(res)) {
    res$label <- paste0(res$y.level, ": ", res$term)
  }
  res$result_type <- "multinomial_association_result"
  res$objective_id <- objective_id
  res$stage_id <- stage_id
  res$effect_measure <- "relative risk ratio"
  res$model_family <- "multinomial"
  res
}

fit_extended_model <- function(formula_obj,
                               data,
                               method_family,
                               effect_measure = NULL,
                               weight_var = NULL,
                               cluster_var = NULL,
                               ziformula = ~1,
                               corstr = "exchangeable") {
  method_family <- match.arg(
    method_family,
    choices = c(
      "multinomial_nominal",
      "bounded_proportion",
      "clustered_gee",
      "count_outcome",
      "zero_inflated_count"
    )
  )

  if (method_family == "multinomial_nominal") {
    suppressPackageStartupMessages(library(nnet))
    weights <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(data)) data[[weight_var]] else NULL
    return(nnet::multinom(formula_obj, data = data, weights = weights, trace = FALSE))
  }

  if (method_family == "bounded_proportion") {
    suppressPackageStartupMessages(library(betareg))
    weights <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(data)) data[[weight_var]] else NULL
    return(betareg::betareg(formula_obj, data = data, weights = weights))
  }

  if (method_family == "clustered_gee") {
    suppressPackageStartupMessages(library(geepack))
    if (is.null(cluster_var) || !nzchar(cluster_var) || !cluster_var %in% names(data)) {
      stop("cluster_var must be supplied for clustered_gee fits.")
    }
    gee_family <- if (identical(effect_measure, "prevalence ratio")) {
      poisson(link = "log")
    } else if (identical(effect_measure, "beta") || identical(effect_measure, "beta coefficient")) {
      gaussian(link = "identity")
    } else {
      binomial(link = "logit")
    }
    return(
      geepack::geeglm(
        formula_obj,
        data = data,
        id = data[[cluster_var]],
        weights = if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(data)) data[[weight_var]] else NULL,
        corstr = corstr,
        family = gee_family
      )
    )
  }

  if (method_family == "count_outcome") {
    weights <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(data)) data[[weight_var]] else NULL
    poisson_fit <- stats::glm(formula_obj, data = data, family = poisson(link = "log"), weights = weights)
    overdispersion <- tryCatch(sum(stats::residuals(poisson_fit, type = "pearson")^2) / stats::df.residual(poisson_fit), error = function(e) 1)
    if (is.finite(overdispersion) && overdispersion > 1.5) {
      suppressPackageStartupMessages(library(MASS))
      return(MASS::glm.nb(formula_obj, data = data, weights = weights))
    }
    return(poisson_fit)
  }

  suppressPackageStartupMessages(library(glmmTMB))
  return(
    glmmTMB::glmmTMB(
      formula_obj,
      ziformula = ziformula,
      data = data,
      family = poisson(link = "log"),
      weights = if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(data)) data[[weight_var]] else NULL
    )
  )
}

fit_primary_model <- function(formula_obj, analytic_object, family = c("modified_poisson", "logistic", "linear")) {
  family <- match.arg(family)
  if (analytic_object$type == "sample") {
    if (family == "modified_poisson") return(glm(formula_obj, data = analytic_object$data, family = poisson(link = "log")))
    if (family == "logistic") return(glm(formula_obj, data = analytic_object$data, family = binomial()))
    return(lm(formula_obj, data = analytic_object$data))
  }
  suppressPackageStartupMessages(library(survey))
  if (family == "modified_poisson") return(survey::svyglm(formula_obj, design = analytic_object$design, family = quasipoisson(link = "log")))
  if (family == "logistic") return(survey::svyglm(formula_obj, design = analytic_object$design, family = quasibinomial()))
  survey::svyglm(formula_obj, design = analytic_object$design)
}

plot_balance <- function(balance_object) {
  if (inherits(balance_object, "bal.tab")) {
    return(cobalt::love.plot(balance_object))
  }
  df <- as.data.frame(balance_object)
  value_col <- if ("smd" %in% names(df)) "smd" else if ("Diff.Adj" %in% names(df)) "Diff.Adj" else names(df)[2]
  label_col <- if ("covariate" %in% names(df)) "covariate" else names(df)[1]
  df[[label_col]] <- factor(df[[label_col]], levels = rev(unique(df[[label_col]])))
  ggplot2::ggplot(df, ggplot2::aes(x = .data[[value_col]], y = .data[[label_col]])) +
    ggplot2::geom_vline(xintercept = 0.1, linetype = 2, color = "#b33939") +
    ggplot2::geom_point(color = "#1f4e79", size = 2.5) +
    ggplot2::labs(x = "Absolute standardized mean difference", y = NULL) +
    ggplot2::theme_minimal()
}

plot_calibration <- function(calibration_df) {
  df <- as.data.frame(calibration_df)
  ggplot2::ggplot(df, ggplot2::aes(x = predicted, y = observed)) +
    ggplot2::geom_abline(intercept = 0, slope = 1, linetype = 2, color = "#7f8c8d") +
    ggplot2::geom_line(color = "#1f4e79", linewidth = 0.8) +
    ggplot2::geom_point(color = "#1f4e79", size = 2.2) +
    ggplot2::labs(x = "Predicted", y = "Observed") +
    ggplot2::theme_minimal()
}

plot_distribution <- function(data, x) {
  if (is.numeric(data[[x]])) {
    return(
      ggplot2::ggplot(data, ggplot2::aes(x = .data[[x]])) +
        ggplot2::geom_histogram(bins = 30, fill = "#4f81bd", color = "white") +
        ggplot2::labs(x = x, y = "Count") +
        ggplot2::theme_minimal()
    )
  }
  ggplot2::ggplot(data, ggplot2::aes(x = .data[[x]])) +
    ggplot2::geom_bar(fill = "#4f81bd") +
    ggplot2::labs(x = x, y = "Count") +
    ggplot2::theme_minimal() +
    ggplot2::theme(axis.text.x = ggplot2::element_text(angle = 30, hjust = 1))
}

plot_forest <- function(results_df) {
  ref_line <- if ("effect_measure" %in% names(results_df) && any(results_df$effect_measure %in% c("beta", "beta coefficient"), na.rm = TRUE)) 0 else 1
  if (!"label" %in% names(results_df)) {
    results_df$label <- if ("term" %in% names(results_df)) results_df$term else seq_len(nrow(results_df))
  }
  ggplot2::ggplot(results_df, ggplot2::aes(x = estimate, y = stats::reorder(label, estimate))) +
    ggplot2::geom_vline(xintercept = ref_line, linetype = "dashed", colour = "grey60") +
    ggplot2::geom_errorbarh(ggplot2::aes(xmin = conf.low, xmax = conf.high), height = 0.15, na.rm = TRUE) +
    ggplot2::geom_point(size = 2.3, na.rm = TRUE) +
    ggplot2::labs(x = "Estimate", y = NULL) +
    ggplot2::theme_minimal()
}

plot_marginal_effects <- function(predictions_df) {
  df <- as.data.frame(predictions_df)
  if (!"estimate" %in% names(df)) {
    if ("predicted" %in% names(df)) {
      df$estimate <- df$predicted
    } else if ("estimate" %in% tolower(names(df))) {
      names(df)[tolower(names(df)) == "estimate"] <- "estimate"
    }
  }
  if (!"term" %in% names(df)) {
    df$term <- seq_len(nrow(df))
  }
  if (!"conf.low" %in% names(df) && "ci_low" %in% names(df)) df$conf.low <- df$ci_low
  if (!"conf.high" %in% names(df) && "ci_high" %in% names(df)) df$conf.high <- df$ci_high
  ggplot2::ggplot(df, ggplot2::aes(x = term, y = estimate, group = 1)) +
    ggplot2::geom_line(color = "#1f4e79", linewidth = 0.7) +
    ggplot2::geom_point(color = "#1f4e79", size = 2.2) +
    {
      if ("conf.low" %in% names(df) && "conf.high" %in% names(df)) {
        ggplot2::geom_errorbar(ggplot2::aes(ymin = conf.low, ymax = conf.high), width = 0.1, color = "#4f81bd")
      }
    } +
    ggplot2::labs(x = NULL, y = "Adjusted estimate") +
    ggplot2::theme_minimal() +
    ggplot2::theme(axis.text.x = ggplot2::element_text(angle = 30, hjust = 1))
}

pool_model_results <- function(model_list, exposure_term, term_match = c("exact", "prefix", "contains")) {
  term_match <- match.arg(term_match)
  suppressPackageStartupMessages(library(mitools))
  estimates <- lapply(model_list, coef)
  variances <- lapply(model_list, vcov)
  pooled <- mitools::MIcombine(estimates, variances)
  out <- as.data.frame(summary(pooled))
  out$term <- rownames(out)
  keep <- switch(
    term_match,
    exact = out$term == exposure_term,
    prefix = startsWith(out$term, exposure_term),
    contains = grepl(exposure_term, out$term, fixed = TRUE)
  )
  out[keep, , drop = FALSE]
}

run_model_diagnostics <- function(model) {
  convergence <- TRUE
  if (!is.null(model$converged)) {
    convergence <- isTRUE(model$converged)
  } else if (!is.null(model$convergence)) {
    convergence <- identical(model$convergence, 0L) || identical(model$convergence, 0)
  }
  diagnostics <- list(
    model_class = paste(class(model), collapse = ","),
    convergence = convergence,
    n_obs = tryCatch(stats::nobs(model), error = function(e) NA_integer_),
    aic = tryCatch(stats::AIC(model), error = function(e) NA_real_),
    bic = tryCatch(stats::BIC(model), error = function(e) NA_real_),
    log_lik = tryCatch(as.numeric(stats::logLik(model)), error = function(e) NA_real_),
    residual_df = tryCatch(stats::df.residual(model), error = function(e) NA_real_),
    parameter_count = tryCatch(length(stats::coef(model)), error = function(e) NA_integer_),
    rank = tryCatch(model$rank, error = function(e) NA_integer_),
    max_leverage = tryCatch(max(stats::hatvalues(model), na.rm = TRUE), error = function(e) NA_real_),
    max_cooks_distance = tryCatch(max(stats::cooks.distance(model), na.rm = TRUE), error = function(e) NA_real_),
    residual_summary = tryCatch(as.list(summary(stats::residuals(model))), error = function(e) list()),
    functional_form = list(
      status = "not_assessed",
      reason = "Run a stage-specific functional-form assessment before scientific release."
    ),
    prediction_range = tryCatch(range(stats::fitted(model), na.rm = TRUE), error = function(e) c(NA_real_, NA_real_))
  )
  if (inherits(model, "glm")) {
    pearson <- tryCatch(sum(stats::residuals(model, type = "pearson")^2) / stats::df.residual(model), error = function(e) NA_real_)
    diagnostics$overdispersion_ratio <- pearson
    diagnostics$family <- model$family$family
    diagnostics$link <- model$family$link
    diagnostics$null_deviance <- tryCatch(model$null.deviance, error = function(e) NA_real_)
    diagnostics$residual_deviance <- tryCatch(model$deviance, error = function(e) NA_real_)
  }
  if (inherits(model, "lm")) {
    diagnostics$r_squared <- tryCatch(summary(model)$r.squared, error = function(e) NA_real_)
    diagnostics$adj_r_squared <- tryCatch(summary(model)$adj.r.squared, error = function(e) NA_real_)
    diagnostics$sigma <- tryCatch(summary(model)$sigma, error = function(e) NA_real_)
  }
  if (inherits(model, "geeglm")) {
    diagnostics$corstr <- model$geese$corstr
    diagnostics$working_correlation <- tryCatch(unname(model$geese$alpha), error = function(e) NA_real_)
  }
  if (inherits(model, "multinom")) {
    diagnostics$edf <- tryCatch(model$edf, error = function(e) NA_real_)
  }
  if (inherits(model, "betareg")) {
    diagnostics$pseudo_r_squared <- tryCatch(summary(model)$pseudo.r.squared, error = function(e) NA_real_)
    diagnostics$precision_phi <- tryCatch(coef(model, model = "precision"), error = function(e) NA_real_)
  }
  if (inherits(model, "glmmTMB")) {
    diagnostics$family <- tryCatch(model$modelInfo$family$family, error = function(e) NA_character_)
    diagnostics$zero_inflation <- tryCatch(any(abs(stats::coef(model)$zi) > 0), error = function(e) NA)
  }
  diagnostics
}

write_registry_artifacts <- function(output_dir,
                                     stage,
                                     methods,
                                     notes = character(),
                                     artifacts = list(),
                                     results = NULL,
                                     diagnostics = NULL) {
  if (is.data.frame(results)) {
    results <- jsonlite::fromJSON(jsonlite::toJSON(results, dataframe = "rows", auto_unbox = TRUE))
  }
  write_analysis_summary(
    output_dir = output_dir,
    stage = stage,
    methods = methods,
    notes = notes,
    artifacts = artifacts,
    results = results,
    diagnostics = diagnostics
  )
}


# Descriptive and balance methods

run_balance_assessment_bundle <- function(data,
                                          exposure_var,
                                          covariates,
                                          output_dir,
                                          weight_var = NULL,
                                          render_plot = TRUE) {

  dirs <- ensure_analysis_dirs(output_dir)
  dat <- data[, unique(c(exposure_var, covariates, weight_var)), drop = FALSE]
  dat <- stats::na.omit(dat)
  if (length(unique(dat[[exposure_var]])) != 2) {
    stop("balance_assessment_bundle currently expects a binary exposure.")
  }
  expo_levels <- unique(dat[[exposure_var]])
  group0 <- dat[dat[[exposure_var]] == expo_levels[1], , drop = FALSE]
  group1 <- dat[dat[[exposure_var]] == expo_levels[2], , drop = FALSE]
  w0 <- if (!is.null(weight_var) && nzchar(weight_var)) group0[[weight_var]] else rep(1, nrow(group0))
  w1 <- if (!is.null(weight_var) && nzchar(weight_var)) group1[[weight_var]] else rep(1, nrow(group1))

  balance_df <- do.call(
    rbind,
    lapply(covariates, function(var) {
      if (!var %in% names(dat)) return(NULL)
      x0 <- group0[[var]]
      x1 <- group1[[var]]
      if (is.numeric(x0) && is.numeric(x1)) {
        m0 <- stats::weighted.mean(x0, w0, na.rm = TRUE)
        m1 <- stats::weighted.mean(x1, w1, na.rm = TRUE)
        s0 <- sqrt(stats::weighted.mean((x0 - m0)^2, w0, na.rm = TRUE))
        s1 <- sqrt(stats::weighted.mean((x1 - m1)^2, w1, na.rm = TRUE))
        smd <- abs(m1 - m0) / sqrt((s0^2 + s1^2) / 2)
      } else {
        p0 <- stats::weighted.mean(as.numeric(as.character(x0) == unique(as.character(x0))[1]), w0, na.rm = TRUE)
        p1 <- stats::weighted.mean(as.numeric(as.character(x1) == unique(as.character(x1))[1]), w1, na.rm = TRUE)
        smd <- abs(p1 - p0)
      }
      data.frame(covariate = var, smd = smd, stringsAsFactors = FALSE)
    })
  )
  table_path <- write_csv_bundle(balance_df, "Table_BalanceAssessment", dirs$tables)
  plot_path <- if (render_plot && nrow(balance_df) > 0) write_plot_bundle(plot_balance(balance_df), "Figure_BalanceLovePlot", dirs$figures) else NULL
  write_registry_artifacts(
    output_dir,
    "descriptive",
    methods = c("balance_assessment_bundle"),
    artifacts = list(table = table_path, figure = plot_path)
  )
  invisible(balance_df)
}


run_weighted_rcs_dose_response <- function(
    data, outcome_var, exposure_var, covariates, output_dir,
    weight_var = NULL, strata_var = NULL, psu_var = NULL,
    design_mode = c("sample", "survey_full", "survey_weight_only"),
    confidence_level = 0.95, objective_id = "OBJ001", grid_points = 101L,
    knot_probs = c(.05, .35, .65, .95)) {

  design_mode <- match.arg(design_mode)
  if (!is.numeric(data[[outcome_var]]) || !is.numeric(data[[exposure_var]])) {
    stop("The outcome and exposure must both be numeric for the continuous RCS template.")
  }
  if (length(knot_probs) < 4L || any(diff(knot_probs) <= 0) ||
      min(knot_probs) < 0 || max(knot_probs) > 1) {
    stop("knot_probs must contain at least four strictly increasing probabilities in [0, 1].")
  }
  variables <- unique(c(outcome_var, exposure_var, covariates))
  analytic <- complete_continuous_model_data(
    data, variables, design_mode, weight_var, strata_var, psu_var
  )
  weights <- analysis_weights(analytic, design_mode, weight_var)
  knots <- weighted_linear_quantile(analytic[[exposure_var]], weights, knot_probs)
  if (length(unique(knots)) != length(knots)) {
    stop("Weighted spline knots are not distinct; the exposure lacks adequate support for the requested RCS.")
  }
  basis <- restricted_cubic_spline_basis(
    analytic[[exposure_var]], knots, prefix = ".dose_rcs"
  )
  analytic <- cbind(analytic, basis)
  basis_names <- names(basis)
  nonlinear_names <- basis_names[grepl("_nonlinear", basis_names, fixed = TRUE)]
  rhs <- c(
    vapply(basis_names, quote_variable, character(1)),
    vapply(covariates, quote_variable, character(1))
  )
  formula_obj <- stats::as.formula(
    paste(quote_variable(outcome_var), "~", paste(rhs, collapse = " + "))
  )
  design_object <- build_design_object(
    analytic, weight_var, strata_var, psu_var, design_mode
  )
  fit <- fit_primary_model(formula_obj, design_object, family = "linear")
  reference <- model_reference(fit, design_object, confidence_level)
  model_table <- coefficient_rows(
    fit, basis_names, reference, design_mode, outcome_var, exposure_var, covariates
  )
  model_table$objective_id <- objective_id
  model_table$stage_id <- "dose_response_stage"
  model_table$model_family <- if (design_mode == "sample") "linear" else "survey_linear"
  model_table$pooling_mode <- "none"
  model_table$result_status <- if (design_mode == "survey_weight_only") {
    "WORKING_ESTIMATE_FORMAL_SURVEY_VARIANCE_UNAVAILABLE"
  } else {
    "ESTIMATED"
  }

  overall_test <- joint_wald_test(fit, basis_names, reference, "dose_response_overall")
  nonlinear_test <- joint_wald_test(
    fit, nonlinear_names, reference, "dose_response_nonlinearity"
  )
  tests <- rbind(overall_test, nonlinear_test)
  tests$objective_id <- objective_id
  tests$outcome <- outcome_var
  tests$exposure <- exposure_var
  tests$analysis_n <- nrow(analytic)
  tests$design_mode <- design_mode
  tests$variance_status <- reference$variance_status
  tests$knot_probabilities <- paste(knot_probs, collapse = ";")
  tests$knots <- paste(signif(knots, 8), collapse = ";")

  prediction_limits <- weighted_linear_quantile(
    analytic[[exposure_var]], weights, c(.05, .95)
  )
  reference_value <- weighted_linear_quantile(
    analytic[[exposure_var]], weights, .50
  )[[1]]
  prediction_grid <- seq(
    prediction_limits[[1]], prediction_limits[[2]], length.out = grid_points
  )
  reference_data <- analytic
  reference_data[[exposure_var]] <- reference_value
  reference_basis <- restricted_cubic_spline_basis(
    reference_data[[exposure_var]], knots, prefix = ".dose_rcs"
  )
  reference_data[basis_names] <- reference_basis
  reference_matrix <- aligned_model_matrix(fit, reference_data)
  normalized_weights <- weights / sum(weights)
  reference_average_row <- as.numeric(crossprod(normalized_weights, reference_matrix))
  names(reference_average_row) <- colnames(reference_matrix)

  prediction_rows <- lapply(prediction_grid, function(value) {
    newdata <- analytic
    newdata[[exposure_var]] <- value
    new_basis <- restricted_cubic_spline_basis(
      newdata[[exposure_var]], knots, prefix = ".dose_rcs"
    )
    newdata[basis_names] <- new_basis
    adjusted_mean <- standardized_linear_prediction(
      fit, newdata, weights, reference
    )
    contrast <- standardized_linear_prediction(
      fit, newdata, weights, reference, contrast_matrix = reference_average_row
    )
    data.frame(
      exposure_value = value,
      adjusted_mean = adjusted_mean[["estimate"]],
      adjusted_mean_se = adjusted_mean[["std_error"]],
      adjusted_mean_ci_low = adjusted_mean[["ci_low"]],
      adjusted_mean_ci_high = adjusted_mean[["ci_high"]],
      contrast_to_reference = contrast[["estimate"]],
      contrast_se = contrast[["std_error"]],
      contrast_ci_low = contrast[["ci_low"]],
      contrast_ci_high = contrast[["ci_high"]],
      reference_value = reference_value,
      stringsAsFactors = FALSE
    )
  })
  prediction_table <- dplyr::bind_rows(prediction_rows)
  prediction_table$objective_id <- objective_id
  prediction_table$analysis_n <- nrow(analytic)
  prediction_table$design_mode <- design_mode
  prediction_table$standardization <- if (design_mode == "sample") {
    "equal-weight empirical standardization"
  } else {
    "supplied-weight empirical standardization"
  }
  prediction_table$variance_status <- reference$variance_status

  support_quantiles <- weighted_linear_quantile(
    analytic[[exposure_var]], weights, c(.01, .05, .25, .50, .75, .95, .99)
  )
  support_table <- data.frame(
    objective_id = objective_id,
    outcome = outcome_var,
    exposure = exposure_var,
    analysis_n = nrow(analytic),
    exposure_distinct_n = length(unique(analytic[[exposure_var]])),
    exposure_min = min(analytic[[exposure_var]]),
    exposure_p01 = support_quantiles[[1]], exposure_p05 = support_quantiles[[2]],
    exposure_p25 = support_quantiles[[3]], exposure_p50 = support_quantiles[[4]],
    exposure_p75 = support_quantiles[[5]], exposure_p95 = support_quantiles[[6]],
    exposure_p99 = support_quantiles[[7]], exposure_max = max(analytic[[exposure_var]]),
    prediction_min = prediction_limits[[1]], prediction_max = prediction_limits[[2]],
    reference_value = reference_value,
    knot_probabilities = paste(knot_probs, collapse = ";"),
    knots = paste(signif(knots, 8), collapse = ";"),
    design_mode = design_mode,
    variance_status = reference$variance_status,
    support_status = if (length(unique(analytic[[exposure_var]])) < 10L) {
      "LIMITED_DISTINCT_EXPOSURE_VALUES"
    } else "P5_P95_GRID_WITHIN_OBSERVED_SUPPORT",
    stringsAsFactors = FALSE
  )

  dirs <- ensure_analysis_dirs(output_dir)
  model_path <- write_csv_bundle(model_table, "Table_DoseResponseModel", dirs$tables)
  test_path <- write_csv_bundle(tests, "Table_DoseResponseTests", dirs$tables)
  support_path <- write_csv_bundle(support_table, "Table_DoseResponseSupport", dirs$tables)
  prediction_path <- write_csv_bundle(
    prediction_table, "Table_DoseResponsePredictions", dirs$tables
  )
  plot_object <- ggplot2::ggplot(
    prediction_table,
    ggplot2::aes(x = exposure_value, y = contrast_to_reference)
  ) +
    ggplot2::geom_ribbon(
      ggplot2::aes(ymin = contrast_ci_low, ymax = contrast_ci_high),
      fill = clinical_palette[["blue"]], alpha = .28
    ) +
    ggplot2::geom_line(color = clinical_palette[["blue_deep"]], linewidth = .85) +
    ggplot2::geom_hline(yintercept = 0, linetype = 2, color = clinical_palette[["grey_dark"]]) +
    ggplot2::geom_vline(xintercept = reference_value, linetype = 3, color = clinical_palette[["grey_dark"]]) +
    ggplot2::labs(
      x = exposure_var,
      y = paste("Standardized mean difference in", outcome_var),
      subtitle = paste("Reference exposure =", signif(reference_value, 5))
    ) +
    theme_clinical()
  figure_path <- write_plot_bundle(
    plot_object, "Figure_DoseResponse", dirs$figures, width = 7.5, height = 5.2
  )

  result_rows <- model_table
  result_rows$result_type <- "continuous_association_result"
  result_rows$label <- paste0("dose-response basis: ", result_rows$term)
  result_rows$exposure_term <- result_rows$term
  result_rows$exposure_unit <- "registered restricted-cubic-spline basis coefficient"
  result_rows$exposure_contrast <- result_rows$exposure_unit
  write_registry_artifacts(
    output_dir,
    "dose_response",
    methods = c("weighted_rcs_dose_response", "joint_wald_F", "empirical_standardization"),
    notes = c(
      "Four weighted-linear knots define an explicit linear plus nonlinear restricted-cubic-spline basis.",
      "Predictions are restricted to the supplied-weight P5-P95 exposure range and contrasted with the supplied-weight median.",
      if (design_mode == "survey_weight_only") {
        "Supplied-weight point description; formal survey variance unavailable."
      } else ""
    ),
    artifacts = list(
      list(source_path = model_path, objective_id = objective_id, stage_id = "dose_response_stage"),
      list(source_path = test_path, objective_id = objective_id, stage_id = "dose_response_stage"),
      list(source_path = support_path, objective_id = objective_id, stage_id = "dose_response_stage"),
      list(source_path = prediction_path, objective_id = objective_id, stage_id = "dose_response_stage"),
      list(
        source_path = figure_path, objective_id = objective_id, stage_id = "dose_response_stage",
        source_table_paths = c(basename(prediction_path), basename(test_path), basename(support_path))
      )
    ),
    results = result_rows
  )
  invisible(list(
    model = fit, coefficients = model_table, tests = tests,
    support = support_table, predictions = prediction_table, figure = figure_path,
    knots = knots, reference_value = reference_value, design_object = design_object
  ))
}


fit_weighted_interaction_continuous <- function(
    data, outcome_var, exposure_var, modifier_var, covariates, output_dir,
    weight_var = NULL, strata_var = NULL, psu_var = NULL,
    design_mode = c("sample", "survey_full", "survey_weight_only"),
    confidence_level = 0.95, objective_id = "OBJ001", grid_points = 41L) {

  design_mode <- match.arg(design_mode)
  if (!is.numeric(data[[outcome_var]]) || !is.numeric(data[[exposure_var]])) {
    stop("The outcome and focal exposure must both be numeric for this continuous interaction template.")
  }
  variables <- unique(c(outcome_var, exposure_var, modifier_var, covariates))
  analytic <- complete_continuous_model_data(
    data, variables, design_mode, weight_var, strata_var, psu_var
  )
  if (is.character(analytic[[modifier_var]]) || is.logical(analytic[[modifier_var]])) {
    analytic[[modifier_var]] <- factor(analytic[[modifier_var]])
  }
  if (is.factor(analytic[[modifier_var]])) {
    analytic[[modifier_var]] <- droplevels(analytic[[modifier_var]])
    if (nlevels(analytic[[modifier_var]]) < 2L) stop("The modifier must have at least two observed levels.")
  } else if (!is.numeric(analytic[[modifier_var]])) {
    stop("The modifier must be numeric, factor, character, or logical.")
  } else if (length(unique(analytic[[modifier_var]])) < 3L) {
    stop("A numeric modifier must have at least three distinct observed values.")
  }

  rhs <- c(
    paste0(quote_variable(exposure_var), " * ", quote_variable(modifier_var)),
    vapply(covariates, quote_variable, character(1))
  )
  formula_obj <- stats::as.formula(
    paste(quote_variable(outcome_var), "~", paste(rhs, collapse = " + "))
  )
  design_object <- build_design_object(
    analytic, weight_var, strata_var, psu_var, design_mode
  )
  fit <- fit_primary_model(formula_obj, design_object, family = "linear")
  reference <- model_reference(fit, design_object, confidence_level)
  coefficient_names <- names(stats::coef(fit))
  interaction_names <- coefficient_names[
    grepl(":", coefficient_names, fixed = TRUE) &
      grepl(exposure_var, coefficient_names, fixed = TRUE) &
      grepl(modifier_var, coefficient_names, fixed = TRUE)
  ]
  if (!length(interaction_names)) stop("The fitted model contains no estimable interaction coefficient.")
  reported_names <- unique(c(
    coefficient_names[grepl(exposure_var, coefficient_names, fixed = TRUE)],
    interaction_names
  ))
  model_table <- coefficient_rows(
    fit, reported_names, reference, design_mode, outcome_var, exposure_var, covariates
  )
  model_table$objective_id <- objective_id
  model_table$stage_id <- "interaction_stage"
  model_table$model_family <- if (design_mode == "sample") "linear" else "survey_linear"
  model_table$pooling_mode <- "none"
  model_table$result_status <- if (design_mode == "survey_weight_only") {
    "WORKING_ESTIMATE_FORMAL_SURVEY_VARIANCE_UNAVAILABLE"
  } else {
    "ESTIMATED"
  }

  joint_test <- joint_wald_test(fit, interaction_names, reference, "interaction_overall")
  joint_test$objective_id <- objective_id
  joint_test$outcome <- outcome_var
  joint_test$exposure <- exposure_var
  joint_test$modifier <- modifier_var
  joint_test$analysis_n <- nrow(analytic)
  joint_test$design_mode <- design_mode
  joint_test$variance_status <- reference$variance_status

  weights <- analysis_weights(analytic, design_mode, weight_var)
  exposure_limits <- weighted_linear_quantile(
    analytic[[exposure_var]], weights, c(0.05, 0.95)
  )
  if (!all(is.finite(exposure_limits)) || exposure_limits[[1]] >= exposure_limits[[2]]) {
    stop("The exposure lacks sufficient support for a P5-P95 prediction grid.")
  }
  exposure_grid <- seq(exposure_limits[[1]], exposure_limits[[2]], length.out = grid_points)

  support_rows <- list()
  prediction_rows <- list()
  row_index <- 1L
  if (is.factor(analytic[[modifier_var]])) {
    modifier_values <- levels(analytic[[modifier_var]])
    for (level in modifier_values) {
      in_level <- analytic[[modifier_var]] == level
      level_quantiles <- weighted_linear_quantile(
        analytic[[exposure_var]][in_level], weights[in_level], c(.05, .50, .95)
      )
      support_rows[[length(support_rows) + 1L]] <- data.frame(
        modifier_value = level,
        unweighted_n = sum(in_level),
        supplied_weight_sum = sum(weights[in_level]),
        exposure_distinct_n = length(unique(analytic[[exposure_var]][in_level])),
        exposure_p05 = level_quantiles[[1]], exposure_p50 = level_quantiles[[2]],
        exposure_p95 = level_quantiles[[3]],
        support_flag = if (sum(in_level) < 10L) "SPARSE_LT10" else if (
          length(unique(analytic[[exposure_var]][in_level])) < 3L
        ) "INSUFFICIENT_EXPOSURE_VARIATION" else "OBSERVED_SUPPORT",
        stringsAsFactors = FALSE
      )
      for (value in exposure_grid) {
        newdata <- analytic
        newdata[[exposure_var]] <- value
        newdata[[modifier_var]] <- factor(level, levels = levels(analytic[[modifier_var]]))
        prediction <- standardized_linear_prediction(
          fit, newdata, weights, reference
        )
        prediction_rows[[row_index]] <- data.frame(
          exposure_value = value, modifier_value = level,
          estimate = prediction[["estimate"]], std_error = prediction[["std_error"]],
          ci_low = prediction[["ci_low"]], ci_high = prediction[["ci_high"]],
          stringsAsFactors = FALSE
        )
        row_index <- row_index + 1L
      }
    }
  } else {
    modifier_values <- unique(weighted_linear_quantile(
      analytic[[modifier_var]], weights, c(.25, .50, .75)
    ))
    modifier_quantiles <- weighted_linear_quantile(
      analytic[[modifier_var]], weights, c(.05, .25, .50, .75, .95)
    )
    support_rows[[1]] <- data.frame(
      modifier_value = "continuous_summary",
      unweighted_n = nrow(analytic), supplied_weight_sum = sum(weights),
      exposure_distinct_n = length(unique(analytic[[exposure_var]])),
      exposure_p05 = exposure_limits[[1]],
      exposure_p50 = weighted_linear_quantile(analytic[[exposure_var]], weights, .50),
      exposure_p95 = exposure_limits[[2]],
      modifier_p05 = modifier_quantiles[[1]], modifier_p25 = modifier_quantiles[[2]],
      modifier_p50 = modifier_quantiles[[3]], modifier_p75 = modifier_quantiles[[4]],
      modifier_p95 = modifier_quantiles[[5]],
      support_flag = "OBSERVED_CONTINUOUS_SUPPORT",
      stringsAsFactors = FALSE
    )
    for (modifier_value in modifier_values) {
      for (value in exposure_grid) {
        newdata <- analytic
        newdata[[exposure_var]] <- value
        newdata[[modifier_var]] <- modifier_value
        prediction <- standardized_linear_prediction(
          fit, newdata, weights, reference
        )
        prediction_rows[[row_index]] <- data.frame(
          exposure_value = value,
          modifier_value = format(signif(modifier_value, 6), trim = TRUE),
          estimate = prediction[["estimate"]], std_error = prediction[["std_error"]],
          ci_low = prediction[["ci_low"]], ci_high = prediction[["ci_high"]],
          stringsAsFactors = FALSE
        )
        row_index <- row_index + 1L
      }
    }
  }
  support_table <- dplyr::bind_rows(support_rows)
  support_table$objective_id <- objective_id
  support_table$design_mode <- design_mode
  prediction_table <- dplyr::bind_rows(prediction_rows)
  prediction_table$objective_id <- objective_id
  prediction_table$analysis_n <- nrow(analytic)
  prediction_table$design_mode <- design_mode
  prediction_table$standardization <- if (design_mode == "sample") {
    "equal-weight empirical standardization"
  } else {
    "supplied-weight empirical standardization"
  }
  prediction_table$variance_status <- reference$variance_status

  dirs <- ensure_analysis_dirs(output_dir)
  model_path <- write_csv_bundle(model_table, "Table_InteractionModel", dirs$tables)
  test_path <- write_csv_bundle(joint_test, "Table_InteractionJointTest", dirs$tables)
  support_path <- write_csv_bundle(support_table, "Table_InteractionSupport", dirs$tables)
  prediction_path <- write_csv_bundle(
    prediction_table, "Table_InteractionMarginalPredictions", dirs$tables
  )
  plot_object <- ggplot2::ggplot(
    prediction_table,
    ggplot2::aes(
      x = exposure_value, y = estimate, color = modifier_value,
      fill = modifier_value, group = modifier_value
    )
  ) +
    ggplot2::geom_ribbon(
      ggplot2::aes(ymin = ci_low, ymax = ci_high), alpha = .12,
      linewidth = 0, color = NA
    ) +
    ggplot2::geom_line(linewidth = .8) +
    ggplot2::labs(
      x = exposure_var, y = paste("Standardized mean", outcome_var),
      color = modifier_var, fill = modifier_var
    ) +
    theme_clinical()
  figure_path <- write_plot_bundle(
    plot_object, "Figure_InteractionMarginalPredictions", dirs$figures,
    width = 7.5, height = 5.2
  )

  result_rows <- model_table
  result_rows$result_type <- "continuous_association_result"
  result_rows$label <- paste0("interaction: ", result_rows$term)
  result_rows$exposure_term <- result_rows$term
  result_rows$exposure_unit <- "one-unit exposure change conditional on the modifier coding"
  result_rows$exposure_contrast <- result_rows$exposure_unit
  write_registry_artifacts(
    output_dir,
    "interaction",
    methods = c("weighted_interaction_continuous", "joint_wald_F", "empirical_standardization"),
    notes = c(
      "Marginal predictions standardize over the observed analytic covariate distribution.",
      if (design_mode == "survey_weight_only") {
        "Supplied-weight point description; formal survey variance unavailable."
      } else ""
    ),
    artifacts = list(
      list(source_path = model_path, objective_id = objective_id, stage_id = "interaction_stage"),
      list(source_path = test_path, objective_id = objective_id, stage_id = "interaction_stage"),
      list(source_path = support_path, objective_id = objective_id, stage_id = "interaction_stage"),
      list(source_path = prediction_path, objective_id = objective_id, stage_id = "interaction_stage"),
      list(
        source_path = figure_path, objective_id = objective_id, stage_id = "interaction_stage",
        source_table_paths = c(basename(prediction_path), basename(support_path))
      )
    ),
    results = result_rows
  )
  invisible(list(
    model = fit, coefficients = model_table, joint_test = joint_test,
    support = support_table, predictions = prediction_table, figure = figure_path,
    design_object = design_object
  ))
}


# Missingness, prediction, and sensitivity methods
run_mi_survey_pooling_wrapper <- function(data,
                                          outcome_var,
                                          exposure_var,
                                          covariates = character(),
                                          output_dir,
                                          family = c("modified_poisson", "logistic", "linear"),
                                          effect_measure = c("prevalence ratio", "odds ratio", "beta"),
                                          m = 5,
                                          weight_var = NULL,
                                          strata_var = NULL,
                                          psu_var = NULL,
                                          design_mode = c("sample", "survey_full", "survey_weight_only"),
                                          seed = 20260415) {
  family <- match.arg(family)
  effect_measure <- match.arg(effect_measure)
  design_mode <- match.arg(design_mode)

  suppressPackageStartupMessages({
    library(mice)
  })

  dirs <- ensure_analysis_dirs(output_dir)
  model_vars <- unique(c(outcome_var, exposure_var, covariates, weight_var, strata_var, psu_var))
  dat <- data[, model_vars[model_vars %in% names(data)], drop = FALSE]

  set.seed(seed)
  imp <- mice::mice(dat, m = m, printFlag = FALSE)
  fits <- vector("list", m)
  diag_list <- vector("list", m)
  for (i in seq_len(m)) {
    completed <- mice::complete(imp, action = i)
    analytic <- build_design_object(completed, weight_var, strata_var, psu_var, design_mode)
    formula_obj <- stats::as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
    fits[[i]] <- fit_primary_model(formula_obj, analytic, family = family)
    diag_list[[i]] <- run_model_diagnostics(fits[[i]])
  }

  pooled <- pool_model_results(fits, exposure_var, term_match = "prefix")
  if ("results" %in% names(pooled)) pooled$estimate <- pooled$results
  if ("(lower" %in% names(pooled)) names(pooled)[names(pooled) == "(lower"] <- "conf.low"
  if ("upper)" %in% names(pooled)) names(pooled)[names(pooled) == "upper)"] <- "conf.high"
  if ("p" %in% names(pooled) && !"p.value" %in% names(pooled)) pooled$p.value <- pooled$p
  pooled$effect_measure <- effect_measure
  pooled$model_family <- family

  table_path <- write_csv_bundle(pooled, "Table_MI_PooledPrimary", dirs$tables)
  write_diagnostic_log(output_dir, list(imputation_count = m, pooled = TRUE, per_imputation = diag_list))
  write_registry_artifacts(
    output_dir,
    "missingness",
    methods = c("mi_survey_pooling_wrapper"),
    artifacts = list(table = table_path, diagnostics = file.path(output_dir, "diagnostic_log.json")),
    results = pooled,
    diagnostics = list(imputation_count = m, pooled = TRUE)
  )
  invisible(list(imputation = imp, models = fits, pooled = pooled, diagnostics = diag_list))
}


run_mice_pipeline <- function(data, vars_for_imputation, output_dir, m = 20, maxit = 20, seed = 42) {
  suppressPackageStartupMessages({
    library(dplyr)
    library(mice)
    library(VIM)
  })
  dirs <- ensure_analysis_dirs(output_dir)

  analytic <- data %>% select(any_of(vars_for_imputation))
  missing_prop <- colMeans(is.na(analytic))
  missing_df <- tibble(variable = names(missing_prop), missing_prop = unname(missing_prop))
  write_csv_bundle(missing_df, "Table_MissingnessProfile", dirs$tables)

  imp <- mice(analytic, m = m, maxit = maxit, seed = seed, printFlag = FALSE)
  completed <- complete(imp, action = "long", include = TRUE)
  write_csv_bundle(completed, "ImputedData_LongFormat", dirs$tables)
  write_main_output(complete(imp, action = 1), output_dir)
  write_analysis_summary(
    output_dir = output_dir,
    stage = "missing_data",
    methods = c("mice::mice"),
    notes = c("Inspect predictor matrix, convergence, and plausibility before pooled inference.")
  )
  invisible(imp)
}


run_adjusted_predictions_contrasts <- function(model,
                                               output_dir,
                                               variables = NULL,
                                               prediction_type = "response",
                                               include_comparisons = TRUE,
                                               include_slopes = FALSE,
                                               render_plot = TRUE) {

  suppressPackageStartupMessages(library(marginaleffects))
  dirs <- ensure_analysis_dirs(output_dir)

  pred_df <- as.data.frame(marginaleffects::predictions(model, by = variables, type = prediction_type))
  pred_path <- write_csv_bundle(pred_df, "Table_AdjustedPredictions", dirs$tables)

  comp_path <- NULL
  comp_df <- NULL
  if (include_comparisons) {
    comp_df <- as.data.frame(marginaleffects::comparisons(model, variables = variables, type = prediction_type))
    comp_path <- write_csv_bundle(comp_df, "Table_AdjustedComparisons", dirs$tables)
  }

  slope_path <- NULL
  slope_df <- NULL
  if (include_slopes) {
    slope_df <- as.data.frame(marginaleffects::slopes(model, variables = variables, type = prediction_type))
    slope_path <- write_csv_bundle(slope_df, "Table_AdjustedSlopes", dirs$tables)
  }

  plot_path <- NULL
  if (render_plot && nrow(pred_df) > 0) {
    plot_input <- pred_df
    if (!"estimate" %in% names(plot_input) && "predicted" %in% names(plot_input)) {
      plot_input$estimate <- plot_input$predicted
    }
    if (!"term" %in% names(plot_input)) {
      plot_input$term <- if (!is.null(variables) && length(variables) > 0 && variables[[1]] %in% names(plot_input)) {
        as.character(plot_input[[variables[[1]]]])
      } else {
        "prediction"
      }
    }
    plot_path <- write_plot_bundle(plot_marginal_effects(plot_input), "Figure_AdjustedPredictions", dirs$figures)
  }

  write_registry_artifacts(
    output_dir,
    "primary_model",
    methods = c("adjusted_predictions_contrasts"),
    artifacts = list(
      predictions = pred_path,
      comparisons = comp_path,
      slopes = slope_path,
      figure = plot_path
    )
  )
  invisible(list(predictions = pred_df, comparisons = comp_df, slopes = slope_df))
}


run_sensitivity_bundle <- function(data,
                                   outcome_var,
                                   exposure_var,
                                   covariates = character(),
                                   output_dir,
                                   trim_quantiles = c(0.01, 0.99)) {
  dirs <- ensure_analysis_dirs(output_dir)

  model_vars <- unique(c(outcome_var, exposure_var, covariates))
  dat <- data[, model_vars[model_vars %in% names(data)], drop = FALSE]
  complete_dat <- stats::na.omit(dat)
  trimmed_dat <- complete_dat
  if (is.numeric(trimmed_dat[[exposure_var]])) {
    qs <- stats::quantile(trimmed_dat[[exposure_var]], probs = trim_quantiles, na.rm = TRUE)
    trimmed_dat[[exposure_var]] <- pmin(pmax(trimmed_dat[[exposure_var]], qs[[1]]), qs[[2]])
  }

  fit_once <- function(df) {
    fml <- stats::as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
    if (length(unique(df[[outcome_var]])) <= 2) {
      stats::glm(fml, data = df, family = stats::binomial())
    } else {
      stats::lm(fml, data = df)
    }
  }

  fit_cca <- fit_once(complete_dat)
  fit_trim <- fit_once(trimmed_dat)
  tidy_cca <- broom::tidy(fit_cca, conf.int = TRUE)
  tidy_trim <- broom::tidy(fit_trim, conf.int = TRUE)
  tidy_cca <- tidy_cca[tidy_cca$term == exposure_var, , drop = FALSE]
  tidy_trim <- tidy_trim[tidy_trim$term == exposure_var, , drop = FALSE]

  out <- rbind(
    data.frame(
      sensitivity = "complete_case",
      estimate = tidy_cca$estimate,
      ci_lower = tidy_cca$conf.low,
      ci_upper = tidy_cca$conf.high,
      p_value = tidy_cca$p.value,
      stringsAsFactors = FALSE
    ),
    data.frame(
      sensitivity = "winsorized_exposure",
      estimate = tidy_trim$estimate,
      ci_lower = tidy_trim$conf.low,
      ci_upper = tidy_trim$conf.high,
      p_value = tidy_trim$p.value,
      stringsAsFactors = FALSE
    )
  )
  table_path <- write_csv_bundle(out, "Table_SensitivitySummary", dirs$tables)
  write_registry_artifacts(
    output_dir,
    "sensitivity",
    methods = c("sensitivity_bundle"),
    artifacts = list(table = table_path),
    results = out
  )
}


# Core descriptive and model wrappers
run_weighted_bivariate_bundle <- function(data, outcome_var, exposure_var, output_dir, weight_var = NULL) {
  dirs <- ensure_analysis_dirs(output_dir)

  dat <- data[, unique(c(outcome_var, exposure_var, weight_var)), drop = FALSE]
  dat <- stats::na.omit(dat)
  weights <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(dat)) dat[[weight_var]] else rep(1, nrow(dat))

  if (is.numeric(dat[[outcome_var]]) && is.numeric(dat[[exposure_var]])) {
    fit <- stats::lm(stats::as.formula(paste(outcome_var, "~", exposure_var)), data = dat, weights = weights)
    coef_row <- broom::tidy(fit)
    coef_row <- coef_row[coef_row$term == exposure_var, , drop = FALSE]
    out <- data.frame(
      analysis = "weighted_linear_association",
      outcome = outcome_var,
      exposure = exposure_var,
      estimate = coef_row$estimate,
      p_value = coef_row$p.value,
      note = "Continuous-continuous bivariate association.",
      stringsAsFactors = FALSE
    )
  } else {
    tbl <- table(dat[[exposure_var]], dat[[outcome_var]])
    test <- suppressWarnings(stats::chisq.test(tbl))
    out <- data.frame(
      analysis = "categorical_association",
      outcome = outcome_var,
      exposure = exposure_var,
      estimate = NA_real_,
      p_value = unname(test$p.value),
      note = "Categorical bivariate association; weighted extension should be used when survey design is active.",
      stringsAsFactors = FALSE
    )
  }
  table_path <- write_csv_bundle(out, "Table_BivariateBundle", dirs$tables)
  fig_path <- if (is.numeric(dat[[exposure_var]]) || is.numeric(dat[[outcome_var]])) {
    write_plot_bundle(plot_distribution(dat, exposure_var), "Figure_BivariateDistribution", dirs$figures)
  } else {
    NULL
  }
  write_registry_artifacts(
    output_dir,
    "bivariate",
    methods = c("weighted_bivariate_bundle"),
    artifacts = list(table = table_path, figure = fig_path),
    results = out
  )
}


build_weighted_table1_nonnormal_smd <- function(data, group_var, continuous_vars, categorical_vars, output_dir, weight_var = NULL) {
  dirs <- ensure_analysis_dirs(output_dir)
  vars_needed <- unique(c(group_var, continuous_vars, categorical_vars, weight_var))
  analytic <- data[, vars_needed, drop = FALSE]
  summary_rows <- list()
  groups <- unique(analytic[[group_var]])
  wmean <- function(x, w) stats::weighted.mean(x, w, na.rm = TRUE)
  ws <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(analytic)) analytic[[weight_var]] else rep(1, nrow(analytic))
  for (group in groups) {
    subset_df <- analytic[analytic[[group_var]] == group, , drop = FALSE]
    subset_w <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(subset_df)) subset_df[[weight_var]] else rep(1, nrow(subset_df))
    for (var in continuous_vars) {
      smd <- NA_real_
      if (length(groups) >= 2) {
        g1 <- analytic[analytic[[group_var]] == groups[[1]], var, drop = TRUE]
        g2 <- analytic[analytic[[group_var]] == groups[[2]], var, drop = TRUE]
        w1 <- ws[analytic[[group_var]] == groups[[1]]]
        w2 <- ws[analytic[[group_var]] == groups[[2]]]
        m1 <- wmean(g1, w1)
        m2 <- wmean(g2, w2)
        s1 <- sqrt(wmean((g1 - m1)^2, w1))
        s2 <- sqrt(wmean((g2 - m2)^2, w2))
        smd <- abs(m2 - m1) / sqrt((s1^2 + s2^2) / 2)
      }
      distribution <- weighted_distribution_summary(subset_df[[var]], subset_w)
      summary_rows[[length(summary_rows) + 1]] <- data.frame(
        variable = var, group = as.character(group), statistic = "median_iqr",
        value = paste0(round(distribution[["p50"]], 2), " [", round(distribution[["p25"]], 2), ", ", round(distribution[["p75"]], 2), "]"),
        smd = smd
      )
    }
    for (var in categorical_vars) {
      level_props <- tapply(subset_w, subset_df[[var]], sum, na.rm = TRUE)
      level_props <- level_props / sum(level_props)
      for (lvl in names(level_props)) {
        smd <- NA_real_
        if (length(groups) >= 2) {
          g1 <- analytic[analytic[[group_var]] == groups[[1]], , drop = FALSE]
          g2 <- analytic[analytic[[group_var]] == groups[[2]], , drop = FALSE]
          w1 <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(g1)) g1[[weight_var]] else rep(1, nrow(g1))
          w2 <- if (!is.null(weight_var) && nzchar(weight_var) && weight_var %in% names(g2)) g2[[weight_var]] else rep(1, nrow(g2))
          p1 <- stats::weighted.mean(as.numeric(as.character(g1[[var]]) == lvl), w1, na.rm = TRUE)
          p2 <- stats::weighted.mean(as.numeric(as.character(g2[[var]]) == lvl), w2, na.rm = TRUE)
          smd <- abs(p2 - p1)
        }
        summary_rows[[length(summary_rows) + 1]] <- data.frame(
          variable = paste(var, lvl, sep = ":"),
          group = as.character(group),
          statistic = "weighted_pct",
          value = round(100 * as.numeric(level_props[[lvl]]), 1),
          smd = smd
        )
      }
    }
  }
  out <- do.call(rbind, summary_rows)
  write_csv_bundle(out, "Table1_BaselineByExposure", dirs$tables)
  write_registry_artifacts(output_dir, "descriptive", methods = c("weighted_table1_nonnormal_smd"), artifacts = list(table = file.path(dirs$tables, "Table1_BaselineByExposure.csv")))
}


fit_weighted_linear_model <- function(data, outcome_var, exposure_var, covariates, output_dir, weight_var = NULL, strata_var = NULL, psu_var = NULL, design_mode = c("sample", "survey_full", "survey_weight_only")) {
  dirs <- ensure_analysis_dirs(output_dir)
  formula_obj <- as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
  design_obj <- build_design_object(data, weight_var, strata_var, psu_var, match.arg(design_mode))
  fit <- fit_primary_model(formula_obj, design_obj, family = "linear")
  res <- extract_model_results(
    fit, exposure_var, effect_measure = "mean difference",
    exposure_unit = "one-unit increase in the registered exposure",
    adjustment_terms = covariates
  )
  write_csv_bundle(res, "Table_PrimaryLinearModel", dirs$tables)
  write_registry_artifacts(output_dir, "primary_model", methods = c("weighted_linear_model"))
  invisible(fit)
}


fit_logistic_model <- function(data, outcome_var, exposure_var, covariates, output_dir) {
  suppressPackageStartupMessages({
    library(dplyr)
    library(broom)
    library(ggplot2)
  })
  dirs <- ensure_analysis_dirs(output_dir)

  formula_obj <- as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
  model <- glm(formula_obj, data = data, family = binomial())
  results <- tidy(model, conf.int = TRUE, exponentiate = TRUE) %>%
    filter(term != "(Intercept)") %>%
    mutate(measure = "OR")

  forest_df <- results %>% mutate(term = reorder(term, estimate))
  p <- ggplot(forest_df, aes(x = estimate, y = term)) +
    geom_vline(xintercept = 1, linetype = 2, color = clinical_palette["grey_dark"]) +
    geom_errorbar(aes(xmin = conf.low, xmax = conf.high), orientation = "y", width = 0.15, color = clinical_palette["blue_dark"]) +
    geom_point(size = 2.5, color = clinical_palette["blue_deep"]) +
    labs(title = "Adjusted odds ratios", x = "Odds ratio", y = NULL) +
    theme_clinical()

  write_csv_bundle(results, "Table_LogisticAdjustedOR", dirs$tables)
  save_clinical_plot(p, "Figure_LogisticAdjustedOR", dirs$figures, width = 8, height = 5)
  write_main_output(data, output_dir)
  write_analysis_summary(
    output_dir = output_dir,
    stage = "logistic",
    methods = c("stats::glm(binomial)"),
    notes = c("Confirm OR is the intended estimand before using this model in a common outcome setting.")
  )
  invisible(model)
}


fit_weighted_modified_poisson_pr <- function(data, outcome_var, exposure_var, covariates, output_dir, weight_var = NULL, strata_var = NULL, psu_var = NULL, design_mode = c("sample", "survey_full", "survey_weight_only")) {
  dirs <- ensure_analysis_dirs(output_dir)
  formula_obj <- as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
  design_obj <- build_design_object(data, weight_var, strata_var, psu_var, match.arg(design_mode))
  fit <- fit_primary_model(formula_obj, design_obj, family = "modified_poisson")
  res <- extract_model_results(fit, exposure_var, effect_measure = "prevalence ratio")
  write_csv_bundle(res, "Table_PrimaryModifiedPoisson", dirs$tables)
  write_registry_artifacts(output_dir, "primary_model", methods = c("weighted_modified_poisson_pr"))
  invisible(fit)
}


fit_ordinal_logit <- function(data, outcome_var, exposure_var, covariates, output_dir) {
  suppressPackageStartupMessages({
    library(dplyr)
    library(ordinal)
    library(broom)
    library(ggplot2)
  })
  dirs <- ensure_analysis_dirs(output_dir)

  formula_obj <- as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
  model <- ordinal::clm(formula_obj, data = data)
  results <- broom::tidy(model, conf.int = TRUE, exponentiate = TRUE) %>%
    filter(coef.type == "location") %>%
    mutate(measure = "Common OR")

  p <- ggplot(results %>% mutate(term = reorder(term, estimate)), aes(x = estimate, y = term)) +
    geom_vline(xintercept = 1, linetype = 2, color = clinical_palette["grey_dark"]) +
    geom_errorbar(aes(xmin = conf.low, xmax = conf.high), orientation = "y", width = 0.15, color = clinical_palette["blue_dark"]) +
    geom_point(size = 2.5, color = clinical_palette["blue_deep"]) +
    labs(title = "Ordinal logistic estimates", x = "Common odds ratio", y = NULL) +
    theme_clinical()

  write_csv_bundle(results, "Table_OrdinalLogistic", dirs$tables)
  save_clinical_plot(p, "Figure_OrdinalLogistic", dirs$figures, width = 8, height = 5)
  write_main_output(data, output_dir)
  write_analysis_summary(
    output_dir = output_dir,
    stage = "ordinal_logistic",
    methods = c("ordinal::clm"),
    notes = c("Run a proportional-odds diagnostic before final reporting.")
  )
  invisible(model)
}


# Optional outcome-family and domain extensions
run_calibration_performance_bundle <- function(data,
                                               outcome_var,
                                               prediction_var,
                                               output_dir,
                                               n_groups = 10,
                                               render_plot = TRUE) {

  dirs <- ensure_analysis_dirs(output_dir)
  dat <- data[, unique(c(outcome_var, prediction_var)), drop = FALSE]
  dat <- stats::na.omit(dat)
  dat$.pred_group <- dplyr::ntile(dat[[prediction_var]], n_groups)
  calibration_df <- dat |>
    dplyr::group_by(.pred_group) |>
    dplyr::summarise(
      predicted = mean(.data[[prediction_var]]),
      observed = mean(.data[[outcome_var]]),
      n = dplyr::n(),
      .groups = "drop"
    )
  perf_df <- dplyr::tibble(
    metric = c("brier_score"),
    estimate = c(mean((dat[[outcome_var]] - dat[[prediction_var]])^2))
  )
  table_path <- write_csv_bundle(perf_df, "Table_PerformanceMetrics", dirs$tables)
  calibration_table <- write_csv_bundle(calibration_df, "Table_CalibrationCurve", dirs$tables)
  if (render_plot) {
    plot_path <- write_plot_bundle(plot_calibration(calibration_df), "Figure_Calibration", dirs$figures)
  } else {
    plot_path <- NULL
  }
  write_registry_artifacts(
    output_dir,
    "primary_model",
    methods = c("calibration_performance_bundle"),
    artifacts = list(table_metrics = table_path, table_calibration = calibration_table, figure = plot_path),
    results = data.frame(
      label = perf_df$metric,
      estimate = perf_df$estimate,
      effect_measure = "performance metric",
      model_family = "calibration_performance",
      stage_id = "primary_model_stage",
      stringsAsFactors = FALSE
    )
  )
  invisible(list(metrics = perf_df, calibration = calibration_df))
}


run_domain_analysis_bundle <- function(data,
                                       outcome_var,
                                       domain_var,
                                       output_dir,
                                       statistic = c("mean", "prevalence"),
                                       weight_var = NULL,
                                       strata_var = NULL,
                                       psu_var = NULL,
                                       design_mode = c("sample", "survey_full", "survey_weight_only"),
                                       render_plot = TRUE) {
  statistic <- match.arg(statistic)

  dirs <- ensure_analysis_dirs(output_dir)
  dat <- data[, unique(c(outcome_var, domain_var, weight_var, strata_var, psu_var)), drop = FALSE]
  dat <- stats::na.omit(dat)
  analytic <- build_design_object(dat, weight_var, strata_var, psu_var, match.arg(design_mode))
  if (analytic$type == "sample") {
    summary_df <- dat |>
      dplyr::group_by(.data[[domain_var]]) |>
      dplyr::summarise(
        estimate = if (statistic == "prevalence") mean(.data[[outcome_var]] == 1) else mean(.data[[outcome_var]]),
        .groups = "drop"
      ) |>
      dplyr::rename(domain = 1)
  } else {
    fun <- if (statistic == "prevalence") survey::svymean else survey::svymean
    summary_df <- survey::svyby(
      stats::as.formula(paste0("~", outcome_var)),
      stats::as.formula(paste0("~", domain_var)),
      analytic$design,
      fun,
      vartype = c("se", "ci"),
      na.rm = TRUE,
      keep.names = FALSE
    ) |>
      as.data.frame() |>
      dplyr::rename(domain = 1, estimate = 2)
  }
  table_path <- write_csv_bundle(summary_df, "Table_DomainAnalysis", dirs$tables)
  if (render_plot) {
    plot_df <- dplyr::mutate(summary_df, label = domain)
    plot_path <- write_plot_bundle(plot_forest(plot_df), "Figure_DomainAnalysis", dirs$figures)
  } else {
    plot_path <- NULL
  }
  write_registry_artifacts(
    output_dir,
    "descriptive_stage",
    methods = c("domain_analysis_bundle"),
    artifacts = list(table = table_path, figure = plot_path),
    results = dplyr::mutate(
      summary_df,
      label = paste0("domain: ", domain),
      stage_id = "descriptive_stage",
      effect_measure = statistic,
      model_family = "domain_analysis"
    )
  )
  invisible(summary_df)
}


fit_bounded_proportion_model <- function(data,
                                         outcome_var,
                                         exposure_var,
                                         covariates = character(),
                                         output_dir,
                                         weight_var = NULL,
                                         render_plot = TRUE) {

  dirs <- ensure_analysis_dirs(output_dir)
  model_vars <- unique(c(outcome_var, exposure_var, covariates, weight_var))
  dat <- data[, model_vars[model_vars %in% names(data)], drop = FALSE]
  dat <- stats::na.omit(dat)
  y <- dat[[outcome_var]]
  n <- length(y)
  if (any(y <= 0 | y >= 1, na.rm = TRUE)) {
    dat[[outcome_var]] <- ((y * (n - 1)) + 0.5) / n
  }

  formula_obj <- stats::as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
  fit <- fit_extended_model(
    formula_obj = formula_obj,
    data = dat,
    method_family = "bounded_proportion",
    weight_var = weight_var
  )
  res <- extract_model_results(
    fit,
    exposure_var,
    effect_measure = "logit-scale coefficient",
    term_match = "prefix",
    exponentiate = FALSE,
    exposure_unit = "one-unit increase in the registered exposure",
    adjustment_terms = covariates
  )
  diagnostics <- run_model_diagnostics(fit)

  table_path <- write_csv_bundle(res, "Table_BoundedOutcome", dirs$tables)
  write_diagnostic_log(output_dir, diagnostics)
  if (render_plot) {
    dist_plot <- plot_distribution(dat, outcome_var)
    dist_path <- write_plot_bundle(dist_plot, "Figure_BoundedOutcomeDistribution", dirs$figures)
    effect_plot <- NULL
    if (nrow(res) > 0) {
      plot_df <- dplyr::mutate(res, label = term)
      effect_plot <- write_plot_bundle(plot_marginal_effects(plot_df), "Figure_BoundedOutcomeEffects", dirs$figures)
    }
  } else {
    dist_path <- NULL
    effect_plot <- NULL
  }
  write_registry_artifacts(
    output_dir,
    "primary_model",
    methods = c("bounded_proportion_model"),
    artifacts = list(table = table_path, figure_distribution = dist_path, figure_effects = effect_plot, diagnostics = file.path(output_dir, "diagnostic_log.json")),
    results = res,
    diagnostics = diagnostics
  )
  invisible(list(model = fit, results = res, diagnostics = diagnostics))
}


fit_count_outcome_model <- function(data,
                                    outcome_var,
                                    exposure_var,
                                    covariates = character(),
                                    output_dir,
                                    weight_var = NULL,
                                    render_plot = TRUE) {

  dirs <- ensure_analysis_dirs(output_dir)
  model_vars <- unique(c(outcome_var, exposure_var, covariates, weight_var))
  dat <- data[, model_vars[model_vars %in% names(data)], drop = FALSE]
  dat <- stats::na.omit(dat)
  formula_obj <- stats::as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))

  fit <- fit_extended_model(
    formula_obj = formula_obj,
    data = dat,
    method_family = "count_outcome",
    weight_var = weight_var
  )
  res <- extract_count_result(
    fit,
    exposure_term = exposure_var,
    objective_id = "OBJ001",
    stage_id = "primary_model_stage",
    exponentiate = TRUE,
    term_match = "prefix"
  )
  diagnostics <- run_model_diagnostics(fit)

  table_path <- write_csv_bundle(res, "Table_CountModel", dirs$tables)
  write_diagnostic_log(output_dir, diagnostics)
  if (render_plot) {
    dist_path <- write_plot_bundle(plot_distribution(dat, outcome_var), "Figure_CountDistribution", dirs$figures)
    plot_path <- if (nrow(res) > 0) write_plot_bundle(plot_forest(dplyr::mutate(res, label = term)), "Figure_CountEffects", dirs$figures) else NULL
  } else {
    dist_path <- NULL
    plot_path <- NULL
  }
  write_registry_artifacts(
    output_dir,
    "primary_model",
    methods = c("count_outcome_model"),
    artifacts = list(table = table_path, figure_distribution = dist_path, figure_effects = plot_path, diagnostics = file.path(output_dir, "diagnostic_log.json")),
    results = res,
    diagnostics = diagnostics
  )
  invisible(list(model = fit, results = res, diagnostics = diagnostics))
}


fit_clustered_gee_model <- function(data,
                                    outcome_var,
                                    exposure_var,
                                    covariates = character(),
                                    cluster_var,
                                    output_dir,
                                    effect_measure = c("prevalence ratio", "odds ratio", "beta"),
                                    weight_var = NULL,
                                    corstr = "exchangeable",
                                    render_plot = TRUE) {
  effect_measure <- match.arg(effect_measure)

  dirs <- ensure_analysis_dirs(output_dir)
  model_vars <- unique(c(outcome_var, exposure_var, covariates, cluster_var, weight_var))
  dat <- data[, model_vars[model_vars %in% names(data)], drop = FALSE]
  dat <- stats::na.omit(dat)
  formula_obj <- stats::as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))

  fit <- fit_extended_model(
    formula_obj = formula_obj,
    data = dat,
    method_family = "clustered_gee",
    effect_measure = effect_measure,
    weight_var = weight_var,
    cluster_var = cluster_var,
    corstr = corstr
  )
  res <- extract_model_results(
    fit,
    exposure_var,
    effect_measure = effect_measure,
    term_match = "prefix",
    exponentiate = effect_measure != "beta"
  )
  diagnostics <- run_model_diagnostics(fit)

  table_path <- write_csv_bundle(res, "Table_ClusteredGEE", dirs$tables)
  write_diagnostic_log(output_dir, diagnostics)
  if (render_plot && nrow(res) > 0) {
    plot_df <- dplyr::mutate(res, label = term)
    plot_path <- write_plot_bundle(plot_forest(plot_df), "Figure_ClusteredGEE", dirs$figures)
  } else {
    plot_path <- NULL
  }
  write_registry_artifacts(
    output_dir,
    "primary_model",
    methods = c("clustered_gee_model"),
    artifacts = list(table = table_path, figure = plot_path, diagnostics = file.path(output_dir, "diagnostic_log.json")),
    results = res,
    diagnostics = diagnostics
  )
  invisible(list(model = fit, results = res, diagnostics = diagnostics))
}


fit_multinomial_nominal_model <- function(data,
                                          outcome_var,
                                          exposure_var,
                                          covariates = character(),
                                          output_dir,
                                          weight_var = NULL,
                                          reference_level = NULL,
                                          render_plot = TRUE) {

  dirs <- ensure_analysis_dirs(output_dir)
  model_vars <- unique(c(outcome_var, exposure_var, covariates, weight_var))
  dat <- data[, model_vars[model_vars %in% names(data)], drop = FALSE]
  dat <- stats::na.omit(dat)
  dat[[outcome_var]] <- as.factor(dat[[outcome_var]])
  if (!is.null(reference_level) && nzchar(reference_level) && reference_level %in% levels(dat[[outcome_var]])) {
    dat[[outcome_var]] <- stats::relevel(dat[[outcome_var]], ref = reference_level)
  }

  formula_obj <- stats::as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
  fit <- fit_extended_model(
    formula_obj = formula_obj,
    data = dat,
    method_family = "multinomial_nominal",
    weight_var = weight_var
  )
  res <- extract_multinomial_result(
    fit,
    exposure_term = exposure_var,
    objective_id = "OBJ001",
    stage_id = "primary_model_stage",
    exponentiate = TRUE,
    term_match = "prefix"
  )
  diagnostics <- run_model_diagnostics(fit)

  table_path <- write_csv_bundle(res, "Table_MultinomialModel", dirs$tables)
  write_diagnostic_log(output_dir, diagnostics)
  if (render_plot && nrow(res) > 0) {
    plot_df <- dplyr::mutate(res, label = if ("y.level" %in% names(res)) paste0(y.level, ": ", term) else term)
    plot_path <- write_plot_bundle(plot_marginal_effects(plot_df), "Figure_MultinomialMarginalEffects", dirs$figures)
  } else {
    plot_path <- NULL
  }
  write_registry_artifacts(
    output_dir,
    "primary_model",
    methods = c("multinomial_nominal_model"),
    artifacts = list(table = table_path, figure = plot_path, diagnostics = file.path(output_dir, "diagnostic_log.json")),
    results = res,
    diagnostics = diagnostics
  )
  invisible(list(model = fit, results = res, diagnostics = diagnostics))
}


fit_zero_inflated_count_model <- function(data,
                                          outcome_var,
                                          exposure_var,
                                          covariates = character(),
                                          output_dir,
                                          weight_var = NULL,
                                          zi_terms = character(),
                                          render_plot = TRUE) {

  dirs <- ensure_analysis_dirs(output_dir)
  model_vars <- unique(c(outcome_var, exposure_var, covariates, weight_var, zi_terms))
  dat <- data[, model_vars[model_vars %in% names(data)], drop = FALSE]
  dat <- stats::na.omit(dat)
  formula_obj <- stats::as.formula(paste(outcome_var, "~", paste(c(exposure_var, covariates), collapse = " + ")))
  zi_formula <- if (length(zi_terms)) {
    stats::as.formula(paste("~", paste(zi_terms, collapse = " + ")))
  } else {
    ~1
  }

  fit <- fit_extended_model(
    formula_obj = formula_obj,
    data = dat,
    method_family = "zero_inflated_count",
    weight_var = weight_var,
    ziformula = zi_formula
  )
  res <- extract_count_result(
    fit,
    exposure_term = exposure_var,
    objective_id = "OBJ001",
    stage_id = "primary_model_stage",
    exponentiate = TRUE,
    component = "cond",
    term_match = "prefix"
  )
  diagnostics <- run_model_diagnostics(fit)

  table_path <- write_csv_bundle(res, "Table_ZeroInflatedCount", dirs$tables)
  write_diagnostic_log(output_dir, diagnostics)
  if (render_plot) {
    dist_path <- write_plot_bundle(plot_distribution(dat, outcome_var), "Figure_ZeroInflatedDistribution", dirs$figures)
    plot_path <- if (nrow(res) > 0) write_plot_bundle(plot_forest(dplyr::mutate(res, label = term)), "Figure_ZeroInflatedEffects", dirs$figures) else NULL
  } else {
    dist_path <- NULL
    plot_path <- NULL
  }
  write_registry_artifacts(
    output_dir,
    "primary_model",
    methods = c("zero_inflated_count_model"),
    artifacts = list(table = table_path, figure_distribution = dist_path, figure_effects = plot_path, diagnostics = file.path(output_dir, "diagnostic_log.json")),
    results = res,
    diagnostics = diagnostics
  )
  invisible(list(model = fit, results = res, diagnostics = diagnostics))
}
